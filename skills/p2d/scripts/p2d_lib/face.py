"""Face readability gate: listed eye pixels must be dark, opaque and sit on skin."""
from __future__ import annotations

import argparse
import os
from itertools import combinations
from typing import Callable, List, Tuple, TypedDict

import numpy as np
from PIL import Image

from .imageio import P2DError, emit, load_rgba, parse_hex, upscale

MIN_CONTRAST = 60
MAX_SKIN_DISTANCE = 110
MIN_SCLERA = 170
NEIGHBOURS = ((0, -1), (0, 1), (-1, 0), (1, 0))


class FaceDetection(TypedDict):
    skin: Tuple[int, int] | None
    eyes: List[List[Tuple[int, int]]]
    reason: str
    expected: List[Tuple[int, int]]


def _skin_like(c: np.ndarray, skin: np.ndarray) -> bool:
    """Same warm ramp as the chosen skin pixel (a darker or lighter skin tone counts)."""
    r, g, b = (int(v) for v in c[:3])
    return r >= g >= b and r - b >= 40 and int(np.abs(c[:3].astype(int) - skin).sum()) <= MAX_SKIN_DISTANCE


def _sclera(c: np.ndarray, skin: np.ndarray) -> bool:
    return int(c[:3].min()) >= MIN_SCLERA and _luma(c) >= _luma(skin)


def _eye_white(c: np.ndarray, skin: np.ndarray) -> bool:
    """A pale skin highlight is not an eye's sclera anchor."""
    return _sclera(c, skin) and not _skin_like(c, skin)


def _point(text: str) -> Tuple[int, int]:
    try:
        x, y = (int(v) for v in text.split(","))
    except ValueError:
        raise P2DError("point must be X,Y: %r" % text)
    return x, y


def _luma(c: np.ndarray) -> float:
    return 0.299 * float(c[0]) + 0.587 * float(c[1]) + 0.114 * float(c[2])


def _groups(points: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
    """Partition points into deterministic 4-connected groups."""
    remaining = set(points)
    groups = []
    for p in points:
        if p not in remaining:
            continue
        remaining.remove(p)
        stack, group = [p], []
        while stack:
            x, y = stack.pop()
            group.append((x, y))
            for dx, dy in NEIGHBOURS:
                q = (x + dx, y + dy)
                if q in remaining:
                    remaining.remove(q)
                    stack.append(q)
        groups.append(sorted(group))
    return groups


def _judge(a: np.ndarray, skin: np.ndarray, group: List[Tuple[int, int]],
           eye_set: set[Tuple[int, int]], front: bool) -> List[str]:
    """Apply the same opacity, contrast and face-side rule in either mode."""
    h, w = a.shape[:2]
    problems = ["%d,%d transparent" % (x, y) for x, y in group if not a[y, x, 3]]
    contrast = _luma(skin) - min(_luma(a[y, x]) for x, y in group)
    if contrast < MIN_CONTRAST:
        problems.append("contrast %.0f < %d vs skin" % (contrast, MIN_CONTRAST))
    face_sides = 0
    for x, y in group:
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if (nx, ny) in eye_set or not (0 <= nx < w and 0 <= ny < h):
                continue
            n = a[ny, nx]
            if n[3] and (_skin_like(n, skin) or _sclera(n, skin)):
                face_sides += 1
    if face_sides < (2 if front else 1) * len(group):
        problems.append("not on skin (%d skin/sclera sides for %d eye pixels, need 2 each): hair, helmet or outline covers it" % (face_sides, len(group)))
    return problems


def detect_face(rgba: np.ndarray, skin_hint: Tuple[int, int] | None = None) -> FaceDetection:
    """Find a warm face ramp and small dark eye cores in the subject's upper 60%."""
    h, w = rgba.shape[:2]
    rows = np.where(rgba[..., 3].any(axis=1))[0]
    fallback = [(max(0, w // 2 - 2), h // 3), (min(w - 1, w // 2 + 1), h // 3)]
    empty: FaceDetection = {"skin": None, "eyes": [], "reason": "no face region", "expected": fallback}
    if not len(rows):
        return empty
    stop = min(h, int(rows[0]) + int(np.ceil((rows[-1] - rows[0] + 1) * .6)))
    warm = []
    for y, x in zip(*np.where(rgba[:stop, :, 3] > 0)):
        r, g, b = (int(v) for v in rgba[y, x, :3])
        if r >= g >= b and r - b >= 40:
            warm.append((int(x), int(y)))
    if not warm:
        return empty
    if skin_hint is not None:
        sx, sy = skin_hint
        if not (0 <= sx < w and 0 <= sy < h):
            raise P2DError("point %d,%d is outside %dx%d" % (sx, sy, w, h))
        if not rgba[sy, sx, 3]:
            raise P2DError("skin point %d,%d is transparent" % (sx, sy))
        seed = skin_hint
    else:
        # Bright warm skin, rather than brown hair/outline or a yellow metal ramp.
        seeds = [p for p in warm if int(rgba[p[1], p[0], 0]) - int(rgba[p[1], p[0], 1])
                 >= int(rgba[p[1], p[0], 0]) / 10]
        seed = max(seeds or warm, key=lambda p: _luma(rgba[p[1], p[0]]))
    ramp = rgba[seed[1], seed[0], :3].astype(int)
    skin_points = {p for p in warm if _skin_like(rgba[p[1], p[0]], ramp)}
    if not skin_points:
        return empty
    ramp = np.median([rgba[y, x, :3] for x, y in sorted(skin_points)], axis=0)
    area = set(skin_points)
    # A white sclera can separate two parts of a tiny face. Only bridge two pixels,
    # never flood-fill connected white helmet highlights.
    for _ in range(2):
        for x, y in sorted(area):
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if (0 <= nx < w and 0 <= ny < stop and rgba[ny, nx, 3]
                        and _eye_white(rgba[ny, nx], ramp)):
                    area.add((nx, ny))
    near = set(area)
    for x, y in area:
        near.update((x + dx, y + dy) for dx, dy in NEIGHBOURS)
    for x, y in sorted(near):
        if not (0 <= x < w and 0 <= y < stop and rgba[y, x, 3]):
            continue
        if _luma(ramp) - _luma(rgba[y, x]) < MIN_CONTRAST:
            continue
        sides = sum(
            0 <= x + dx < w and 0 <= y + dy < h and rgba[y + dy, x + dx, 3]
            and (_skin_like(rgba[y + dy, x + dx], ramp) or _sclera(rgba[y + dy, x + dx], ramp))
            for dx, dy in NEIGHBOURS)
        if sides >= 2:
            area.add((x, y))
    region = max(_groups(sorted(area)), key=lambda g: (len(g), -min(y for _, y in g)))
    face_skin = [p for p in region if p in skin_points]
    if not face_skin:
        return empty
    median = np.median([rgba[y, x, :3] for x, y in face_skin], axis=0)
    sample = skin_hint or min(face_skin, key=lambda p: (
        float(np.abs(rgba[p[1], p[0], :3].astype(int) - median).sum()), p))
    skin = rgba[sample[1], sample[0], :3].astype(int)
    near = set(region)
    for x, y in region:
        near.update((x + dx, y + dy) for dx, dy in NEIGHBOURS)
    dark = {(x, y) for x, y in near if 0 <= x < w and 0 <= y < stop and rgba[y, x, 3]
            and _luma(median) - _luma(rgba[y, x]) >= MIN_CONTRAST}
    candidates = set()
    for x, y in sorted(dark):
        sides = []
        whites = []
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and rgba[ny, nx, 3]:
                n = rgba[ny, nx]
                sides.append(_skin_like(n, skin) or _sclera(n, skin))
                whites.append(_eye_white(n, skin))
        if sum(sides) >= 2 or (sum(sides) and any(whites) and int(rgba[y, x, 2]) > int(rgba[y, x, 0])):
            candidates.add((x, y))
    anchors = {p for p in candidates if any(
        0 <= nx < w and rgba[p[1], nx, 3] and _eye_white(rgba[p[1], nx], skin)
        for nx in (p[0] - 1, p[0] + 1)) and (
            int(np.ptp(rgba[p[1], p[0], :3])) >= 40 or
            sum(0 <= nx < w and rgba[p[1], nx, 3] and
                (_skin_like(rgba[p[1], nx], skin) or _sclera(rgba[p[1], nx], skin))
                for nx in (p[0] - 1, p[0] + 1)) >= 2)}
    if not anchors:
        anchors = {p for p in candidates if any(
            0 <= p[0] + dx < w and 0 <= p[1] + dy < h and rgba[p[1] + dy, p[0] + dx, 3]
            and _eye_white(rgba[p[1] + dy, p[0] + dx], skin) for dx, dy in NEIGHBOURS)}
    if anchors:
        candidates = anchors
    # Preserve a differently coloured upper/lower iris pixel with one face side;
    # do not grow sideways into adjacent hair or outline.
    for x, y in sorted(candidates):
        if not any(0 <= nx < w and rgba[y, nx, 3] and _eye_white(rgba[y, nx], skin)
                   for nx in (x - 1, x + 1)):
            continue
        for ny in (y - 1, y + 1):
            if (x, ny) not in dark:
                continue
            sides = sum(0 <= nx < w and rgba[ny, nx, 3] and
                        (_skin_like(rgba[ny, nx], skin) or _sclera(rgba[ny, nx], skin))
                        for nx in (x - 1, x + 1))
            if sides >= 2 or (sides and int(np.ptp(rgba[ny, x, :3])) >= 40):
                candidates.add((x, ny))
    groups = [g for g in _groups(sorted(candidates)) if 1 <= len(g) <= 6]
    x0, x1 = min(x for x, _ in face_skin), max(x for x, _ in face_skin)
    y0, y1 = min(y for _, y in face_skin), max(y for _, y in face_skin)
    cx, ey = (x0 + x1) / 2, y0 + (y1 - y0) / 3
    expected = [(max(0, int(cx) - 1), int(ey)), (min(w - 1, int(cx) + 2), int(ey))]
    def distance(group: List[Tuple[int, int]]) -> float:
        return abs(sum(x for x, _ in group) / len(group) - cx) + abs(min(y for _, y in group) - ey)
    pairs = []
    for left, right in combinations(groups, 2):
        if abs(min(y for _, y in left) - min(y for _, y in right)) > 1:
            continue
        lx = sum(x for x, _ in left) / len(left)
        rx = sum(x for x, _ in right) / len(right)
        if not (lx < cx < rx and rx - lx >= 2):
            continue
        eye_set = set(left + right)
        if not _judge(rgba, skin, left, eye_set, True) and not _judge(rgba, skin, right, eye_set, True):
            pairs.append([left, right])
    if pairs:
        eyes = min(pairs, key=lambda pair: sum(distance(g) for g in pair))
        reason = ""
    else:
        valid = [g for g in groups if not _judge(rgba, skin, g, set(g), False)]
        eyes = [min(valid, key=distance)] if valid else []
        columns = np.where(rgba[..., 3].any(axis=0))[0]
        subject_centre = (int(columns[0]) + int(columns[-1])) / 2
        # A broad centred face expects two eyes; a profile's skin lies to one side.
        front = x1 - x0 >= 5 and abs(cx - subject_centre) <= .5
        reason = "fewer eyes than expected (%d/%d)" % (len(eyes), 2 if front else 1) if not eyes or front else ""
    return {"skin": sample, "eyes": eyes, "reason": reason, "expected": expected}


def cmd_face(args: argparse.Namespace) -> int:
    a = load_rgba(args.image).copy()
    if args.key:
        key = np.array(parse_hex(args.key), dtype=np.uint8)
        a[(a[..., :3] == key).all(axis=-1), 3] = 0
    h, w = a.shape[:2]
    auto = getattr(args, "auto", False)
    if not auto and (not args.eyes or not args.skin):
        raise P2DError("manual face mode requires --eyes and --skin")
    if auto and args.eyes:
        raise P2DError("--auto cannot be combined with --eyes")
    detection = detect_face(a, _point(args.skin) if args.skin else None) if auto else None
    if detection is not None:
        emit("SKIN", "%d,%d" % detection["skin"] if detection["skin"] is not None else "none")
        emit("EYE_CANDIDATES", " | ".join(" ".join("%d,%d" % p for p in g) for g in detection["eyes"]) or "none")
        eyes = [p for g in detection["eyes"] for p in g]
        skin_point = detection["skin"]
    else:
        eyes = [_point(p) for p in args.eyes]
        skin_point = _point(args.skin)
    points = eyes + ([skin_point] if skin_point is not None else [])
    for x, y in points:
        if not (0 <= x < w and 0 <= y < h):
            raise P2DError("point %d,%d is outside %dx%d" % (x, y, w, h))
    sx, sy = skin_point or (0, 0)
    skin = a[sy, sx, :3].astype(int)
    if skin_point is not None and a[sy, sx, 3] == 0:
        raise P2DError("skin point %d,%d is transparent" % (sx, sy))
    eye_set = set(eyes)
    failures: List[str] = [detection["reason"]] if detection is not None and detection["reason"] else []
    groups = _groups(eyes)
    emit("EYES", len(groups))
    for i, group in enumerate(groups, 1):
        problems = _judge(a, skin, group, eye_set, len(groups) > 1)
        label = " ".join("%d,%d" % p for p in group)
        emit("EYE_%d" % i, "%s %s" % (label, "PASS" if not problems else "FAIL " + "; ".join(problems)))
        if problems:
            failures.append(label)
    if len(groups) == 2:
        shapes = []
        tops = []
        for group in groups:
            left, top = min(x for x, _ in group), min(y for _, y in group)
            shapes.append({(x - left, y - top) for x, y in group})
            tops.append(top)
        if shapes[0] != shapes[1] or tops[0] != tops[1]:
            emit("EYE_PAIR", "FAIL front eyes differ in shape/height")
            failures.append("front eyes differ in shape/height")
        else:
            emit("EYE_PAIR", "PASS")
    if detection is not None and failures:
        emit("HINT", "%s; expected eye positions %s; repair with touch and rerun face --auto" %
             (failures[0], " ".join("%d,%d" % p for p in detection["expected"])))
    opaque_rows = np.where(a[..., 3].any(axis=1))[0]
    top = int(opaque_rows[0]) if len(opaque_rows) else 0
    bottom = min(h, max((y for _, y in eyes), default=max(top + 1, h // 3)) + max(3, h // 8))
    crop = a[top:bottom]
    out = args.out or os.path.splitext(args.image)[0] + "-face@%dx.png" % args.scale
    Image.fromarray(upscale(crop, args.scale), "RGBA").save(out)
    emit("CROP", out)
    emit("RESULT", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image", help="finished character frame or face PNG")
    parser.add_argument("--auto", action="store_true", help="detect skin and eyes without typing coordinates")
    parser.add_argument("--eyes", nargs="+", help="every eye pixel X,Y (1-based counting not used: 0,0 is top-left)")
    parser.add_argument("--skin", help="one face skin pixel X,Y (optional hint with --auto)")
    parser.add_argument("--key", help="background color of an opaque sheet (e.g. #009392), treated as transparent")
    parser.add_argument("--scale", type=int, default=8, help="nearest-neighbour scale of the head crop")
    parser.add_argument("--out", help="crop path (default <image>-face@<scale>x.png)")
    return cmd_face
