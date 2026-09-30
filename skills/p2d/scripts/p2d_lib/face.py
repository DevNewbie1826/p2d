"""Face readability gate: listed eye pixels must be dark, opaque and sit on skin."""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import os
from itertools import combinations
from typing import Callable, List, Sequence, Tuple, TypedDict

import numpy as np
from PIL import Image

from .imageio import P2DError, emit, parse_hex, save_rgba, upscale

MIN_CONTRAST = 60
MAX_SKIN_DISTANCE = 110
MIN_SCLERA = 170
NEIGHBOURS = ((0, -1), (0, 1), (-1, 0), (1, 0))
EYE_COLORS = {
    "blue": ("#212591", "#1D73D6", "#FFFFFF"),
    "brown": ("#5A2000", "#944118", "#FFFFFF"),
    "green": ("#16452A", "#39965A", "#FFFFFF"),
    "yellow": ("#785000", "#DAB52A", "#FFFFFF"),
    "gold": ("#785000", "#DAB52A", "#FFFFFF"),
    "red": ("#681820", "#C63C48", "#FFFFFF"),
    "violet": ("#482070", "#9256C4", "#FFFFFF"),
    "gray": ("#343E4A", "#8898AA", "#FFFFFF"),
}


class Part(TypedDict):
    at: List[float]
    grid: List[str]


class EyeParts(TypedDict, total=False):
    left: Part
    right: Part | str
    eye: Part


class FacingParts(TypedDict):
    anchor: str
    eyes: dict[str, EyeParts]
    brows: dict[str, EyeParts]
    mouth: dict[str, Part]


class PartsSpacing(TypedDict, total=False):
    spacing: dict[str, "SpacingRule"]


class PartsLibrary(PartsSpacing):
    px: int
    facings: dict[str, FacingParts | str]


class SpacingRule(TypedDict):
    ratio: float
    min: int
    max: int


class FaceDetection(TypedDict):
    skin: Tuple[int, int] | None
    eyes: List[List[Tuple[int, int]]]
    reason: str
    expected: List[Tuple[int, int]]


def _skin_like(c: np.ndarray, skin: np.ndarray) -> bool:
    """Same warm ramp as the chosen skin pixel (a darker or lighter skin tone counts)."""
    r, g, b = (int(v) for v in c[:3])
    return r >= g >= b and r - b >= 40 and int(np.abs(c[:3].astype(int) - skin).sum()) <= MAX_SKIN_DISTANCE


def _sclera(c: np.ndarray, skin: np.ndarray, shaded: bool = False) -> bool:
    threshold = _luma(skin) - MIN_CONTRAST if shaded else _luma(skin)
    return (int(c[:3].min()) >= MIN_SCLERA and _luma(c) >= threshold
            and (not shaded or int(np.ptp(c[:3])) <= 60))


def _eye_white(c: np.ndarray, skin: np.ndarray, shaded: bool = False) -> bool:
    """A pale skin highlight is not an eye's sclera anchor."""
    return _sclera(c, skin, shaded) and not _skin_like(c, skin)


def _point(text: str) -> Tuple[int, int]:
    try:
        x, y = (int(v) for v in text.split(","))
    except ValueError:
        raise P2DError("point must be X,Y: %r" % text)
    return x, y


def _luma(c: np.ndarray) -> float:
    return 0.299 * float(c[0]) + 0.587 * float(c[1]) + 0.114 * float(c[2])


def _groups(points: List[Tuple[int, int]], colours: np.ndarray | None = None) -> List[List[Tuple[int, int]]]:
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
                    if colours is not None:
                        hue = colorsys.rgb_to_hsv(*(float(v)/255 for v in colours[y, x, :3]))[0]
                        other = colorsys.rgb_to_hsv(*(float(v)/255 for v in colours[q[1], q[0], :3]))[0]
                        delta = abs(hue-other)
                        if min(delta, 1-delta) > 20/360:
                            continue
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
            if n[3] and (_skin_like(n, skin) or _sclera(n, skin, w == 32)):
                face_sides += 1
    # Dense irises have interior pixels with no skin sides. Judge their exposed
    # perimeter, while retaining the two-sides-per-pixel rule for thin cores.
    dense = len({x for x, _ in group}) > 1 and len({y for _, y in group}) > 1
    needed = (2 if front else 1) * (
        int(np.ceil(np.sqrt(len(group)))) if dense or len(group) > 6 else len(group))
    if face_sides < needed:
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
                        and _eye_white(rgba[ny, nx], ramp, w == 32)):
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
            and (_skin_like(rgba[y + dy, x + dx], ramp) or _sclera(rgba[y + dy, x + dx], ramp, w == 32))
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
                sides.append(_skin_like(n, skin) or _sclera(n, skin, w == 32))
                whites.append(_eye_white(n, skin, w == 32))
        if sum(sides) >= 2 or (sum(sides) and any(whites) and int(rgba[y, x, 2]) > int(rgba[y, x, 0])):
            candidates.add((x, y))
    anchors = {p for p in candidates if any(
        0 <= nx < w and rgba[p[1], nx, 3] and _eye_white(rgba[p[1], nx], skin, w == 32)
        for nx in (p[0] - 1, p[0] + 1)) and (
            int(np.ptp(rgba[p[1], p[0], :3])) >= 40 or
            sum(0 <= nx < w and rgba[p[1], nx, 3] and
                (_skin_like(rgba[p[1], nx], skin) or _sclera(rgba[p[1], nx], skin, w == 32))
                for nx in (p[0] - 1, p[0] + 1)) >= 2)}
    if not anchors:
        anchors = {p for p in candidates if any(
            0 <= p[0] + dx < w and 0 <= p[1] + dy < h and rgba[p[1] + dy, p[0] + dx, 3]
            and _eye_white(rgba[p[1] + dy, p[0] + dx], skin, w == 32) for dx, dy in NEIGHBOURS)}
    if anchors:
        candidates = anchors
    # Preserve a differently coloured upper/lower iris pixel with one face side;
    # do not grow sideways into adjacent hair or outline.
    for x, y in sorted(candidates):
        if not any(0 <= nx < w and rgba[y, nx, 3] and _eye_white(rgba[y, nx], skin, w == 32)
                   for nx in (x - 1, x + 1)):
            continue
        for ny in (y - 1, y + 1):
            if (x, ny) not in dark:
                continue
            sides = sum(0 <= nx < w and rgba[ny, nx, 3] and
                        (_skin_like(rgba[ny, nx], skin) or _sclera(rgba[ny, nx], skin, w == 32))
                        for nx in (x - 1, x + 1))
            if sides >= 2 or (sides and int(np.ptp(rgba[ny, x, :3])) >= 40):
                candidates.add((x, ny))
    coloured = {(x, y) for x, y in near
                if 0 <= x < w and 0 <= y < stop and rgba[y, x, 3]
                and int(np.ptp(rgba[y, x, :3])) >= 40
                and not _skin_like(rgba[y, x], skin)
                and _luma(median) - _luma(rgba[y, x]) >= 25}
    stack = list(coloured)
    while stack:
        x, y = stack.pop()
        for dx, dy in NEIGHBOURS:
            nx, ny = x+dx, y+dy
            if not (0 <= nx < w and 0 <= ny < stop) or (nx, ny) in coloured:
                continue
            c = rgba[ny, nx]
            if (c[3] and int(np.ptp(c[:3])) >= 40 and not _skin_like(c, skin)
                    and _luma(median) - _luma(c) >= 25):
                coloured.add((nx, ny))
                stack.append((nx, ny))
    # Bright lower iris pixels can be less than 60 below skin. A sclera
    # neighbour identifies them; keep the dark-core contrast test in _judge.
    coloured_groups = [g for g in _groups(sorted(coloured), rgba) if any(
        0 <= x+dx < w and 0 <= y+dy < h and rgba[y+dy, x+dx, 3]
        and _eye_white(rgba[y+dy, x+dx], skin, w == 32)
        for x, y in g for dx, dy in NEIGHBOURS)]
    if w == 32:
        # One iris can cross hue/contrast thresholds between its dark core and
        # lower ramp. Keep compact iris pieces separate from wide hair ramps.
        compact = [g for g in coloured_groups
                   if max(x for x, _ in g) - min(x for x, _ in g) <= 1
                   and max(y for _, y in g) - min(y for _, y in g) <= 3]
        cores = candidates | {p for g in compact for p in g}
        for x, y in sorted(cores):
            if not any(0 <= nx < w and _eye_white(rgba[y, nx], skin, True)
                       for nx in (x - 1, x + 1)):
                continue
            for nx, ny in ((x, y + 1), (x + (1 if x < w / 2 else -1), y + 1)):
                if (nx, ny) in coloured:
                    cores.add((nx, ny))
        candidates = cores
        coloured_groups = []
    groups = [g for g in _groups(sorted(candidates)) + coloured_groups
              if 1 <= len(g) <= max(6, (w//8)**2)]
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
        eyes = min(pairs, key=lambda pair: (
            -sum(len(g) for g in pair) if w >= 32 else 0,
            sum(distance(g) for g in pair)))
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



def _luma_of(c: Sequence[int] | np.ndarray) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def stamp_eyes(a: np.ndarray, detection: FaceDetection, spacing: SpacingRule,
               eye_colors: List[Tuple[int, int, int]] | None = None) -> Tuple[np.ndarray, int, int, int]:
    """Redraw both front eyes with the measured RM2000 construction, palette-preserving.

    Per eye (left eye shown, right eye mirrored): a dark lid pixel above the iris,
    a 1x2 iris (dark over light) and a light sclera pixel on the outer side, at
    x = centre -2 / +1 (two pixels apart), same top row for both eyes.
    """
    h, w = a.shape[:2]
    if (w, h) != (24, 32):
        raise P2DError("--stamp draws the RM2000 16px eye construction and needs a 24x32 frame, got %dx%d" % (w, h))
    if detection["skin"] is None:
        raise P2DError("--stamp needs a face region: %s" % detection["reason"])
    sx, sy = detection["skin"]
    skin = a[sy, sx, :3].astype(int)
    opaque = a[..., 3] > 0
    colours = np.unique(a[opaque][:, :3], axis=0)
    lumas = np.array([_luma_of(c) for c in colours])
    darkest = colours[int(np.argmin(lumas))]
    candidates = [c for c in colours if _luma_of(c) < _luma_of(skin) - 60 and int(c[2]) > int(c[0])]
    iris_light = max(candidates, key=_luma_of) if candidates else colours[int(np.argsort(lumas)[1])]
    dark_blue = [c for c in candidates if _luma_of(c) < _luma_of(iris_light)]
    iris_dark = min(dark_blue, key=_luma_of) if dark_blue else darkest
    sclera = colours[int(np.argmax(lumas))]
    if eye_colors:
        iris_dark, iris_light, sclera = (np.array(c) for c in eye_colors)
    eyes = detection["eyes"]
    if len(eyes) == 2:
        top = min(y for g in eyes for _, y in g)
    else:
        skin_mask = np.zeros((h, w), bool)
        for y in range(h):
            for x in range(w):
                if opaque[y, x] and _skin_like(a[y, x], skin):
                    skin_mask[y, x] = True
        ys = np.nonzero(skin_mask)[0]
        top = int(ys.min()) + max(1, (int(ys.max()) - int(ys.min())) // 3)
    x0, x1 = _face_span(a, detection, top)
    face_w = x1 - x0 + 1
    gap = min(spacing["max"], max(spacing["min"],
              int(np.floor(spacing["ratio"] * face_w + .5))))
    if gap % 2 != face_w % 2:
        gap = gap - 1 if gap > spacing["min"] else gap + 1
    lx, rx = (x0 + x1 - gap - 1) // 2, (x0 + x1 + gap + 1) // 2
    out = a.copy()
    iris_set = {tuple(int(v) for v in c) for c in candidates}
    for g in eyes:
        gx = [x for x, _ in g]
        gy = [y for _, y in g]
        for y in range(max(0, min(gy)), min(h, max(gy) + 3)):
            for x in range(max(0, min(gx)), min(w, max(gx) + 1)):
                if (x, y) in g or tuple(int(v) for v in out[y, x, :3]) in iris_set:
                    out[y, x, :3] = skin
    for x, side in ((lx, -1), (rx, 1)):
        out[top - 1, x, :3] = darkest
        out[top, x, :3] = iris_dark
        out[top + 1, x, :3] = iris_light
        out[top, x + side, :3] = skin
        out[top + 1, x + side, :3] = sclera
        out[top - 1:top + 2, x, 3] = 255
        out[top:top + 2, x + side, 3] = 255
    return out, lx, rx, top


def _eye_colors(text: str | None) -> List[Tuple[int, int, int]] | None:
    if not text:
        return None
    values = EYE_COLORS.get(text.lower(), tuple(text.split(",")))
    if len(values) != 3:
        raise P2DError("--eye-color needs a named ramp or DARK,LIGHT,SCLERA")
    colors = [parse_hex(v) for v in values]
    if _luma_of(colors[0]) >= _luma_of(colors[1]):
        raise P2DError("eye dark colour must be darker than eye light colour")
    return colors


def _derived_eye_ramp(text: str, a: np.ndarray, detection: FaceDetection,
                      snap: bool) -> List[Tuple[int, int, int]]:
    skin_point = detection["skin"]
    if skin_point is None:
        raise P2DError("--eye-color needs a detected face skin colour")
    sx, sy = skin_point
    skin_luma = _luma(a[sy, sx])
    color = parse_hex(text)
    hue, saturation, value = colorsys.rgb_to_hsv(*(v / 255 for v in color))

    def rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
        return int(r * 255), int(g * 255), int(b * 255)

    light = color
    if abs(_luma_of(light) - skin_luma) < 25:
        value *= max(0, skin_luma - 26) / max(1, _luma_of(light))
        light = rgb(hue, saturation, value)
    dark_hue = hue + 8 / 360 if hue < .25 or hue > 11 / 12 else hue
    dark_saturation = min(1, saturation + .15)
    dark_value = value * .55
    dark = rgb(dark_hue, dark_saturation, dark_value)
    limit = min(skin_luma - 61, _luma_of(light) - 1)
    if _luma_of(dark) > limit:
        dark_value *= max(0, limit) / max(1, _luma_of(dark))
        dark = rgb(dark_hue, dark_saturation, dark_value)
    highlight = rgb(hue, saturation * .5, value + (1-value) * .65)
    palette = [tuple(int(v) for v in c) for c in np.unique(a[a[..., 3] > 0][:, :3], axis=0)]
    whites = [c for c in palette if min(c) >= 230]
    white = max(whites, key=_luma_of) if whites else (255, 255, 255)
    ramp = [dark, light, highlight, white]
    if snap:
        for index, c in enumerate(ramp):
            nearest = min(palette, key=lambda p: sum((p[j]-c[j])**2 for j in range(3)))
            distance = sum((nearest[j]-c[j])**2 for j in range(3))
            contrast_ok = (
                (index != 0 or skin_luma - _luma_of(nearest) >= 60)
                and (index != 1 or abs(skin_luma - _luma_of(nearest)) >= 25))
            if distance <= 24**2 and contrast_ok:
                ramp[index] = nearest
        if _luma_of(ramp[0]) >= _luma_of(ramp[1]):
            ramp[0] = dark
    return ramp


def _load_parts(a: np.ndarray, args: argparse.Namespace) -> PartsLibrary:
    h, w = a.shape[:2]
    px = args.px or {(24, 32): 16, (32, 32): 32, (48, 48): 48}.get((w, h))
    if px is None:
        raise P2DError("face parts need 24x32, 32x32 or 48x48; use --px for another master shape")
    path = args.parts or os.path.join(os.path.dirname(__file__), "face_parts", "%d.json" % px)
    try:
        with open(path, encoding="utf-8") as f:
            library: PartsLibrary = json.load(f)
    except (OSError, ValueError) as exc:
        raise P2DError("cannot read face parts %s: %s" % (path, exc))
    if library.get("px") != px or not isinstance(library.get("facings"), dict):
        raise P2DError("face parts %s must have px %d and facings" % (path, px))
    return library


def _face_anchor(a: np.ndarray, detection: FaceDetection, facing: str,
                 anchor: str = "") -> Tuple[str, float, int]:
    if detection["skin"] is None:
        raise P2DError("--stamp needs a face region: %s" % detection["reason"])
    sx, sy = detection["skin"]
    skin = a[sy, sx, :3].astype(int)
    h, w = a.shape[:2]
    rows = np.where(a[..., 3].any(axis=1))[0]
    stop = min(h, int(rows[0]) + int(np.ceil((rows[-1] - rows[0] + 1) * .6)))
    region = [(x, y) for y in range(stop) for x in range(w)
              if a[y, x, 3] and _skin_like(a[y, x], skin)]
    if "skin-region centre" not in anchor:
        region = next(g for g in _groups(region) if (sx, sy) in g)
    skin_cx = (min(x for x, _ in region) + max(x for x, _ in region)) / 2
    eyes = detection["eyes"]
    if facing == "auto":
        facing = "front" if len(eyes) != 1 else (
            "left" if np.mean([x for x, _ in eyes[0]]) < skin_cx else "right")
    if eyes:
        centres = [float(np.mean([x for x, _ in g])) for g in eyes]
        cx = sum(centres) / len(centres)
        ey = min(y for g in eyes for _, y in g)
    else:
        cx = skin_cx
        y0, y1 = min(y for _, y in region), max(y for _, y in region)
        ey = y0 + max(1, (y1 - y0) // 3)
    if "skin-region centre" in anchor:
        cx = float(np.floor(skin_cx + .5))
    elif "integer pixel centre" in anchor:
        cx = float(np.floor(cx + .5))
    return facing, cx, ey


def _parts_for(parts: EyeParts, mirror: bool = False) -> List[Tuple[Part, bool]]:
    if "eye" in parts:
        return [(parts["eye"], mirror)]
    left = parts.get("left")
    if left is None:
        raise P2DError("eye/brow part needs left or eye")
    right = parts.get("right")
    result = [(left, mirror)]
    if right == "mirror":
        result.append((left, not mirror))
    elif isinstance(right, dict):
        result.append((right, mirror))
    return result


def _face_span(a: np.ndarray, detection: FaceDetection, ey: int) -> Tuple[int, int]:
    """Skin envelope at the eye row, bridging eyes/sclera but not stray ear pixels."""
    skin_point = detection["skin"]
    if skin_point is None:
        raise P2DError("--stamp needs a face region")
    sx, sy = skin_point
    skin = a[sy, sx, :3].astype(int)
    eye_points = {p for group in detection["eyes"] for p in group}
    centre = np.mean([x for x, _ in eye_points]) if eye_points else sx
    columns = [x for x in range(a.shape[1]) if a[ey, x, 3] and (
        _skin_like(a[ey, x], skin) or (x, ey) in eye_points)]
    columns = sorted(set(columns) | {
        nx for x, y in eye_points if y == ey for nx in (x - 1, x + 1)
        if 0 <= nx < a.shape[1] and a[ey, nx, 3]
        and _eye_white(a[ey, nx], skin)})
    if not columns:
        # Explicit neutral/tinted skin anchors need no warm-skin heuristic.
        columns = [x for x in range(a.shape[1]) if a[ey, x, 3] and
                   int(np.abs(a[ey, x, :3].astype(int) - skin).sum()) <= MAX_SKIN_DISTANCE]
    if not columns:
        columns = [sx]
    groups = _groups([(x, ey) for x in columns])
    if len(detection["eyes"]) == 2:
        # Hair may split the exposed skin between two eyes. Keep both sides,
        # but never connect an isolated ear through white helmet highlights.
        regions = [g for g in groups if any(p in eye_points for p in g)]
        if regions:
            return min(x for g in regions for x, _ in g), max(x for g in regions for x, _ in g)
    region = min(groups, key=lambda g: (
        min(abs(x - centre) for x, _ in g), -len(g)))
    return min(x for x, _ in region), max(x for x, _ in region)


def _front_shifts(parts: List[Tuple[Part, bool]], gap: int) -> List[float]:
    """Place the normal inner iris columns symmetrically around the face centre."""
    shifts = []
    for index, (part, flip) in enumerate(parts):
        cols = [float(-part["at"][0] - col if flip else part["at"][0] + col)
                for line in part["grid"] for col, role in enumerate(line) if role in "di"]
        shifts.append((-(gap + 1) / 2 - max(cols)) if index == 0 else
                      ((gap + 1) / 2 - min(cols)))
    return shifts


def stamp_parts(a: np.ndarray, detection: FaceDetection, library: PartsLibrary,
                expr: str, mouth: str, brows: str | None, facing: str,
                eye_colors: List[Tuple[int, int, int]] | None = None,
                eye_highlight: Tuple[int, int, int] | None = None,
                eye_gap: int | None = None, anchored: bool = False
                ) -> Tuple[np.ndarray, str, int, List[Tuple[int, int, int]], int, int]:
    if anchored:
        if facing == "auto":
            facing = "front" if len(detection["eyes"]) > 1 else "left"
        cx, ey = 0., 0
    else:
        facing, cx, ey = _face_anchor(a, detection, facing)
    mirror = library["facings"].get(facing) == "mirror-of-left"
    config = library["facings"].get("left" if mirror else facing)
    if not isinstance(config, dict):
        raise P2DError("face parts have no facing %s" % facing)
    if not anchored:
        _, cx, ey = _face_anchor(a, detection, facing, config.get("anchor", ""))
    eyes: EyeParts | None = config.get("eyes", {}).get(expr)
    if eyes is None:
        raise P2DError("face parts have no expression %s for %s" % (expr, facing))
    pixels: List[Tuple[float, int, str]] = []
    if anchored:
        pixels = [(float(-p["at"][0] - col if flip else p["at"][0] + col),
                   int(p["at"][1]) + row, role)
                  for p, flip in _parts_for(eyes, mirror)
                  for row, line in enumerate(p["grid"]) for col, role in enumerate(line)]
        eye_roles = ("diwh" if any(role in "diwh" for _, _, role in pixels) else
                     "l" if any(role == "l" for _, _, role in pixels) else ".")
        template = [(x, y) for x, y, role in pixels if role in eye_roles]
        points = [p for group in detection["eyes"] for p in group]
        cx = float(np.mean([x for x, _ in points]) - np.mean([x for x, _ in template]))
        ey = min(y for _, y in points) - min(y for _, y in template)
    x0, x1 = _face_span(a, detection, ey)
    face_w = x1 - x0 + 1
    gap = 0
    spacing = library.get("spacing")
    dynamic = spacing is not None and not anchored and not expr.startswith("normal-")
    shifts = [0., 0.]
    if dynamic or eye_gap is not None:
        cx = (x0 + x1) / 2
        normal = config["eyes"]["normal"]
        normal_parts = _parts_for(normal, mirror)
        if facing == "front":
            if eye_gap is not None:
                gap = eye_gap
            else:
                if spacing is None:
                    raise P2DError("face parts need spacing metadata")
                rule = spacing["front"]
                gap = min(rule["max"], max(
                    rule["min"], int(np.floor(rule["ratio"] * face_w + .5))))
            if gap < 0:
                raise P2DError("--eye-gap must be nonnegative")
            if gap % 2 != face_w % 2:
                if eye_gap is not None:
                    raise P2DError("--eye-gap parity must match FACE_W for a symmetric pair")
                gap = gap - 1 if gap > 1 else gap + 1
            shifts = _front_shifts(normal_parts, gap)
            if expr in ("normal", "closed", "happy", "surprised", "eat"):
                eyes = {**eyes, "right": "mirror"}
                shifts[1] = -shifts[0]
        else:
            if eye_gap is not None:
                raise P2DError("--eye-gap requires front facing")
            if spacing is None:
                raise P2DError("face parts need spacing metadata")
            rule = spacing["side"]
            margin = min(rule["max"], max(rule["min"],
                         int(np.floor(rule["ratio"] * face_w + .5))))
            part, flip = normal_parts[0]
            core = [(-part["at"][0] - col if flip else part["at"][0] + col)
                    for line in part["grid"] for col, role in enumerate(line) if role in "di"]
            shifts[0] = ((x0 + margin - cx - min(core)) if facing == "left" else
                         (x1 - margin - cx - max(core)))
    elif facing == "front":
        cores = []
        for part, flip in _parts_for(eyes, mirror):
            cols = [(-part["at"][0] - col if flip else part["at"][0] + col)
                    for line in part["grid"] for col, role in enumerate(line) if role in "di"]
            if cols:
                cores.append((min(cols), max(cols)))
        if len(cores) == 2:
            gap = int(cores[1][0] - cores[0][1] - 1)
    layers = [(part, flip, "eyes") for part, flip in _parts_for(eyes, mirror)]
    if brows:
        brow_parts = config.get("brows", {}).get(brows)
        if brow_parts is None:
            raise P2DError("face parts have no brows %s for %s" % (brows, facing))
        layers.extend((part, flip, "brows") for part, flip in _parts_for(brow_parts, mirror))
    if mouth != "keep":
        mouth_part = config.get("mouth", {}).get(mouth)
        if mouth_part is None:
            raise P2DError("face parts have no mouth %s for %s" % (mouth, facing))
        layers.append((mouth_part, mirror, "mouth"))
    skin_point = detection["skin"]
    if skin_point is None:
        raise P2DError("--stamp needs a face region")
    sx, sy = skin_point
    skin = a[sy, sx, :3].astype(int)
    colors = np.unique(a[a[..., 3] > 0][:, :3], axis=0)
    ordered = sorted(colors, key=_luma_of)
    darkest = ordered[0]
    eye_points = {p for g in detection["eyes"] for p in g}
    iris = sorted({tuple(int(v) for v in a[y, x, :3]) for x, y in eye_points},
                  key=_luma_of)
    dark = np.array(iris[0]) if iris else darkest
    light = np.array(iris[-1]) if iris else ordered[min(1, len(ordered)-1)]
    white = ordered[-1]
    if eye_colors:
        dark, light, white = (np.array(c) for c in eye_colors)
    highlight = np.array(eye_highlight) if eye_highlight is not None else white
    ramp = [(int(c[0]), int(c[1]), int(c[2])) for c in (dark, light, highlight, white)]
    shadows = [c for c in ordered if _skin_like(c, skin) and _luma_of(c) < _luma_of(skin)]
    warm = [c for c in ordered if int(c[0]) > int(c[1]) >= int(c[2])]
    cloth = [c for c in ordered if not _skin_like(c, skin)]
    reds = [c for c in ordered if int(c[0]) >= 100
            and int(c[0]) > 2 * max(1, int(c[1]))
            and int(c[0]) > 2 * max(1, int(c[2]))]
    roles = {"s": skin, "S": shadows[-1] if shadows else (skin * .8).astype(int),
             "l": darkest, "d": dark, "i": light, "w": white, "h": highlight,
             "p": cloth[0] if cloth else darkest,
             "c": reds[0] if reds else np.array((164, 24, 32)),
             "m": warm[0] if warm else darkest, "t": warm[-1] if warm else skin}
    if anchored:
        # Recorded variants retain source-local ramps, not the darkest garment.
        for role in "lSdiwh":
            samples = [a[ey + y, int(np.floor(cx + x + .5)), :3]
                       for x, y, r in pixels if r == role]
            if samples:
                values, counts = np.unique(samples, axis=0, return_counts=True)
                roles[role] = values[int(np.argmax(counts))]
        if eye_colors:
            roles.update(d=dark, i=light, w=white, h=highlight)
        ramp = [(int(roles[r][0]), int(roles[r][1]), int(roles[r][2])) for r in "dihw"]
    h, w = a.shape[:2]
    old_colors = {tuple(int(v) for v in a[y, x, :3]) for x, y in eye_points}
    old_face = set(eye_points)
    for x, y in eye_points:
        # A lid immediately above an iris and its adjacent sclera belong to the face.
        for nx, ny in ((x, y-1), (x-1, y), (x+1, y)):
            if not (0 <= nx < w and 0 <= ny < h and a[ny, nx, 3]):
                continue
            sides = sum(0 <= nx+dx < w and 0 <= ny+dy < h
                        and _skin_like(a[ny+dy, nx+dx], skin) for dx, dy in NEIGHBOURS)
            if (_eye_white(a[ny, nx], skin) and sides >= 1) or (
                    ny == y-1 and np.array_equal(a[ny, nx, :3], darkest) and sides >= 2):
                old_face.add((nx, ny))
    out = a.copy()
    if dynamic:
        for x, y in old_face:
            out[y, x, :3] = skin
    clipped = 0
    eye_index = 0
    for part, flip, kind in layers:
        dx, dy = part["at"]
        grid = part["grid"]
        shift = shifts[eye_index] if kind == "eyes" else 0.
        eye_index += kind == "eyes"
        if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
            raise P2DError("face part grid must be nonempty and rectangular")
        for row, line in enumerate(grid):
            for col, role in enumerate(line):
                x = int(np.floor(cx + (-dx-col if flip else dx+col) + shift + .5))
                y = ey + int(dy) + row
                if role != "." and role not in roles:
                    raise P2DError("unknown face role %s" % role)
                if not (0 <= x < w and 0 <= y < h):
                    clipped += role != "."
                    continue
                pixel = a[y, x]
                rgb = tuple(int(v) for v in pixel[:3])
                editable = bool(pixel[3]) and (
                    _skin_like(pixel, skin) or (x, y) in old_face or rgb in old_colors
                    or (anchored and kind == "eyes"))
                # Mouth pixels are dark marks surrounded by skin, not a hair edge.
                if kind == "mouth" and pixel[3]:
                    sides = sum(0 <= x+ox < w and 0 <= y+oy < h
                                and _skin_like(a[y+oy, x+ox], skin) for ox, oy in NEIGHBOURS)
                    editable = editable or sides >= 2
                if role == "." and kind != "mouth":
                    continue
                if editable and ((kind == "mouth" and not _skin_like(pixel, skin)) or (kind == "eyes" and (
                        (x, y) in eye_points or _eye_white(pixel, skin) or rgb in old_colors))):
                    out[y, x, :3] = skin
                if role == ".":
                    continue
                if not editable:
                    clipped += 1
                    continue
                out[y, x, :3] = roles[role]
                out[y, x, 3] = 255
    return out, facing, clipped, ramp, gap, face_w


def _expression_pair(a: np.ndarray, detection: FaceDetection,
                     args: argparse.Namespace) -> FaceDetection:
    """Read both open eyes at one shared stamped anchor, not nearby helmet pixels."""
    if detection["skin"] is None:
        return detection
    library = _load_parts(a, args)
    facing, _, ey = _face_anchor(a, detection, args.facing)
    config = library["facings"].get(facing)
    if not isinstance(config, dict) or args.expr not in config.get("eyes", {}):
        return detection
    parts = _parts_for(config["eyes"][args.expr])
    if len(parts) != 2 or not all(
            any(role in "diwh" for line in part["grid"] for role in line)
            for part, _ in parts):
        return detection
    _, cx, _ = _face_anchor(a, detection, facing, config.get("anchor", ""))
    spacing = library.get("spacing")
    dynamic = spacing is not None and not args.expr.startswith("normal-")
    gaps = [args.eye_gap] if args.eye_gap is not None else (
        list(range(spacing["front"]["min"], spacing["front"]["max"] + 1))
        if dynamic and spacing is not None else [0])
    centres = [cx]
    if dynamic:
        x0, x1 = _face_span(a, detection, ey)
        measured = (x0 + x1) / 2
        if abs(measured - cx) == .5:
            centres.append(measured)
    layouts = []
    for centre, gap in ((centre, gap) for centre in centres for gap in gaps):
        shifts = _front_shifts(_parts_for(config["eyes"]["normal"]), gap) if dynamic else [0., 0.]
        eyes: EyeParts = config["eyes"][args.expr]
        if dynamic and args.expr in ("normal", "closed", "happy", "surprised", "eat"):
            eyes = {**eyes, "right": "mirror"}
            shifts[1] = -shifts[0]
        layouts.append([
            [(int(np.floor(centre + (-part["at"][0] - col if flip else part["at"][0] + col)
                           + shifts[index] + .5)), int(part["at"][1]) + y, role)
             for y, line in enumerate(part["grid"]) for col, role in enumerate(line)
             if role in "diwh"]
            for index, (part, flip) in enumerate(_parts_for(eyes))])
    sx, sy = detection["skin"]
    skin = a[sy, sx, :3].astype(int)
    height = max(len(part["grid"]) for part, _ in parts)
    # A lid or scar can move the heuristic's top row. Require every eye role
    # to match at a single row: searching each eye separately would hide shifts.
    anchors = sorted(range(max(0, ey - height), min(a.shape[0], ey + height + 1)),
                     key=lambda y: (abs(y - ey), y))
    for row, layout in ((row, layout) for row in anchors for layout in layouts):
        regions = [[(x, row + y, role) for x, y, role in region] for region in layout]
        samples: dict[str, List[Tuple[int, int, int]]] = {}
        valid = True
        for region in regions:
            for x, y, role in region:
                if not (0 <= x < a.shape[1] and 0 <= y < a.shape[0]) or not a[y, x, 3]:
                    valid = False
                    break
                pixel = a[y, x]
                if role in "wh":
                    valid = valid and _eye_white(pixel, skin, a.shape[1] == 32)
                else:
                    valid = valid and not _skin_like(pixel, skin) and not _eye_white(
                        pixel, skin, a.shape[1] == 32)
                    if role == "d":
                        valid = valid and _luma(skin) - _luma(pixel) >= MIN_CONTRAST
                samples.setdefault(role, []).append((int(pixel[0]), int(pixel[1]), int(pixel[2])))
        # Stamping uses one ramp for both sides. A misplaced pixel must not be
        # replaced by a differently coloured lid, scar or helmet highlight.
        if valid and all(len(set(values)) == 1 for values in samples.values()):
            groups = [[(x, y) for x, y, role in region if role in "di"]
                      or [(x, y) for x, y, _ in region] for region in regions]
            return {**detection, "eyes": groups, "reason": ""}
    # Recorded source variants can keep occluded pixels rather than overwrite
    # them (for example normal-alex under a helmet). Keep the heuristic gate
    # for those, including its original asymmetry and skin checks.
    if args.expr.startswith("normal-"):
        return detection
    return {**detection, "reason": "eye regions do not match expression %s at a shared anchor" % args.expr}


def cmd_face(args: argparse.Namespace) -> int:
    if not os.path.exists(args.image):
        raise P2DError("file not found: %s" % args.image)
    with open(args.image, "rb") as stream:
        image_bytes = stream.read()
    with Image.open(io.BytesIO(image_bytes)) as image:
        a = np.array(image.convert("RGBA"), dtype=np.uint8)
    if args.key:
        key = np.array(parse_hex(args.key), dtype=np.uint8)
        a[(a[..., :3] == key).all(axis=-1), 3] = 0
    h, w = a.shape[:2]
    if getattr(args, "stamp", None):
        detection: FaceDetection | None = detect_face(a, _point(args.skin) if args.skin else None)
        if args.eyes:
            if not args.skin:
                raise P2DError("--stamp --eyes requires --skin")
            points = [_point(p) for p in args.eyes]
            skin_point = _point(args.skin)
            for x, y in points + [skin_point]:
                if not (0 <= x < w and 0 <= y < h) or not a[y, x, 3]:
                    raise P2DError("face anchor %d,%d is outside the opaque frame" % (x, y))
            detection = {"skin": skin_point, "eyes": _groups(points),
                         "reason": "", "expected": points}
        color_text = args.eye_color or args.eye_colors
        ramp = None
        if color_text and color_text.lower() not in EYE_COLORS and "," not in color_text:
            ramp = _derived_eye_ramp(color_text, a, detection, args.snap_palette)
            eye_colors = [ramp[0], ramp[1], ramp[3]]
        else:
            eye_colors = _eye_colors(color_text)
        existing = {tuple(int(v) for v in c) for c in a[a[..., 3] > 0][:, :3]}
        legacy = (w, h) == (24, 32) and not (
            args.expr or args.parts or args.px or args.eye_color or args.brows or args.snap_palette
            or args.mouth != "keep" or args.facing != "auto" or args.eye_gap is not None
            or args.eyes)
        if legacy:
            spacing = _load_parts(a, args).get("spacing")
            if spacing is None:
                raise P2DError("face parts need spacing metadata")
            out, lx, rx, top = stamp_eyes(a, detection, spacing["front"], eye_colors)
            facing, clipped = "front", 0
            stamp_info = "%d %d %d -> %s" % (lx, rx, top, args.stamp)
            ramp = [(int(c[0]), int(c[1]), int(c[2])) for c in
                    (out[top, lx, :3], out[top+1, lx, :3],
                     out[top+1, lx-1, :3], out[top+1, lx-1, :3])]
            gap = rx - lx - 1
            x0, x1 = _face_span(a, detection, top)
            face_w = x1 - x0 + 1
        else:
            if detection["skin"] is None:
                raise P2DError("--stamp needs a face region (24x32, 32x32 or 48x48): %s" %
                               detection["reason"])
            out, facing, clipped, ramp, gap, face_w = stamp_parts(
                a, detection, _load_parts(a, args), args.expr or "normal",
                args.mouth, args.brows, args.facing, eye_colors,
                ramp[2] if ramp is not None else None, args.eye_gap, bool(args.eyes))
            stamp_info = args.stamp
        save_rgba(out, args.stamp)
        emit("STAMPED", stamp_info)
        emit("EXPR", args.expr or "normal")
        emit("FACING", facing)
        emit("EYE_GAP", gap)
        emit("FACE_W", face_w)
        added = sorted({tuple(int(v) for v in c) for c in out[out[..., 3] > 0][:, :3]}
                       - existing)
        eye_added = list(dict.fromkeys(c for c in ramp if c in added))
        emit("EYE_COLORS_ADDED", " ".join("#%02X%02X%02X" % c for c in eye_added) or "none")
        emit("EYE_RAMP", " ".join("#%02X%02X%02X" % c for c in ramp))
        emit("CLIPPED", clipped)
        emit("NEXT", "open the image, then run face --auto --expr %s on it" % (args.expr or "normal"))
        return 0
    auto = getattr(args, "auto", False)
    if not auto and (not args.eyes or not args.skin):
        raise P2DError("manual face mode requires --eyes and --skin")
    if auto and args.eyes:
        raise P2DError("--auto cannot be combined with --eyes")
    detection = detect_face(a, _point(args.skin) if args.skin else None) if auto else None
    expression_pair = False
    if detection is not None and getattr(args, "expr", None):
        original = detection
        detection = _expression_pair(a, detection, args)
        expression_pair = detection is not original and not detection["reason"]
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
    closed_sides = 0
    open_sides = None
    if getattr(args, "expr", None):
        # These names declare that an absent iris is intentional, not a defect.
        closed_sides = 2 if args.expr in ("closed", "happy") else int(
            args.expr.startswith(("wink-", "patch-", "one-eyed-")) or args.expr == "patch")
        if args.expr in ("closed", "happy", "patch"):
            open_sides = 0
        if getattr(args, "parts", None):
            library = _load_parts(a, args)
            facing, _, _ = _face_anchor(a, detection, args.facing) if detection is not None else (
                args.facing if args.facing != "auto" else "front", 0, 0)
            config = library["facings"].get(facing)
            if config == "mirror-of-left":
                config = library["facings"].get("left")
            front_config = library["facings"].get("front")
            if (args.facing == "auto" and isinstance(front_config, dict)
                    and args.expr in front_config.get("eyes", {})
                    and (not isinstance(config, dict) or args.expr not in config.get("eyes", {}))):
                config, facing = front_config, "front"
            if not isinstance(config, dict) or args.expr not in config.get("eyes", {}):
                raise P2DError("face parts have no expression %s for %s" % (args.expr, facing))
            parts = _parts_for(config["eyes"][args.expr])
            open_sides = sum(any(role in "diwh" for row in part["grid"] for role in row)
                             for part, _ in parts)
            closed_sides = len(parts) - open_sides
        if detection is not None and detection["skin"] is not None and closed_sides:
            failures = [reason for reason in failures if not reason.startswith("fewer eyes than expected")]
            if args.expr.startswith(("wink-", "patch-", "one-eyed-")):
                centre = sum(x for x, _ in detection["expected"]) / 2
                closed_left = args.expr.endswith("-l")
                groups = [g for g in groups if (
                    float(np.mean([x for x, _ in g])) > centre if closed_left
                    else float(np.mean([x for x, _ in g])) < centre)]
                eye_set = {p for g in groups for p in g}
            if (open_sides if open_sides is not None else int(closed_sides == 1)) and not groups:
                failures.append("missing open eye for expression %s" % args.expr)
    emit("EYES", len(groups))
    for i, group in enumerate(groups, 1):
        if closed_sides == 2 or open_sides == 0:
            continue
        problems = [] if expression_pair else _judge(a, skin, group, eye_set, len(groups) > 1)
        label = " ".join("%d,%d" % p for p in group)
        emit("EYE_%d" % i, "%s %s" % (label, "PASS" if not problems else "FAIL " + "; ".join(problems)))
        if problems:
            failures.append(label)
    if len(groups) == 2 and not closed_sides:
        shapes = []
        tops = []
        for group in groups:
            left, top = min(x for x, _ in group), min(y for _, y in group)
            shapes.append({(x - left, y - top) for x, y in group})
            tops.append(top)
        right_width = max(x for x, _ in shapes[1])
        mirrored = {(right_width - x, y) for x, y in shapes[1]}
        if not expression_pair and (
                (shapes[0] != shapes[1] and shapes[0] != mirrored) or tops[0] != tops[1]):
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
    emit("IMAGE_SHA256", hashlib.sha256(image_bytes).hexdigest())
    emit("RESULT", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image", help="finished character frame or face PNG")
    parser.add_argument("--stamp", metavar="OUT", help="stamp face parts into OUT (bare 24x32 stamp preserves the legacy RM2000 construction)")
    parser.add_argument("--expr", metavar="NAME", help="eye expression (default normal); with --auto declares intentionally closed/covered eyes")
    parser.add_argument("--mouth", default="keep", help="mouth part name (default keep)")
    parser.add_argument("--brows", metavar="NAME", help="brow part name")
    parser.add_argument("--facing", choices=("front", "left", "right", "auto"), default="auto")
    parser.add_argument("--eye-color", metavar="NAME|HEX|DARK,LIGHT,SCLERA", help="named ramp, one hex colour with automatic shading, or three explicit hex colours")
    parser.add_argument("--eye-gap", type=int, metavar="N", help="front inner iris gap; parity must match face width")
    parser.add_argument("--snap-palette", action="store_true", help="snap derived ramp colours to frame palette within RGB distance 24")
    parser.add_argument("--parts", metavar="FILE", help="face-part JSON (default face_parts/<px>.json)")
    parser.add_argument("--px", type=int, choices=(16, 32, 48), help="master size for nonstandard frame shapes")
    parser.add_argument("--eye-colors", metavar="DARK,LIGHT,SCLERA", help="with --stamp: dedicated eye colours (RM2000 blue eyes: #212591,#1D73D6,#FFFFFF); new colours are reported")
    parser.add_argument("--auto", action="store_true", help="detect skin and eyes without typing coordinates")
    parser.add_argument("--eyes", nargs="+", help="every eye pixel X,Y (1-based counting not used: 0,0 is top-left)")
    parser.add_argument("--skin", help="one face skin pixel X,Y (optional hint with --auto)")
    parser.add_argument("--key", help="background color of an opaque sheet (e.g. #009392), treated as transparent")
    parser.add_argument("--scale", type=int, default=8, help="nearest-neighbour scale of the head crop")
    parser.add_argument("--out", help="crop path (default <image>-face@<scale>x.png)")
    return cmd_face
