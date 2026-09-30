"""Face readability gate: listed eye pixels must be dark, opaque and sit on skin."""
from __future__ import annotations

import argparse
import os
from typing import Callable, List, Tuple

import numpy as np
from PIL import Image

from .imageio import P2DError, emit, load_rgba, parse_hex, upscale

MIN_CONTRAST = 60
MAX_SKIN_DISTANCE = 110
MIN_SCLERA = 170


def _skin_like(c: np.ndarray, skin: np.ndarray) -> bool:
    """Same warm ramp as the chosen skin pixel (a darker or lighter skin tone counts)."""
    r, g, b = (int(v) for v in c[:3])
    return r >= g >= b and r - b >= 40 and int(np.abs(c[:3].astype(int) - skin).sum()) <= MAX_SKIN_DISTANCE


def _sclera(c: np.ndarray, skin: np.ndarray) -> bool:
    return int(c[:3].min()) >= MIN_SCLERA and _luma(c) >= _luma(skin)


def _point(text: str) -> Tuple[int, int]:
    try:
        x, y = (int(v) for v in text.split(","))
    except ValueError:
        raise P2DError("point must be X,Y: %r" % text)
    return x, y


def _luma(c: np.ndarray) -> float:
    return 0.299 * float(c[0]) + 0.587 * float(c[1]) + 0.114 * float(c[2])


def cmd_face(args: argparse.Namespace) -> int:
    a = load_rgba(args.image).copy()
    if args.key:
        key = np.array(parse_hex(args.key), dtype=np.uint8)
        a[(a[..., :3] == key).all(axis=-1), 3] = 0
    h, w = a.shape[:2]
    points = [_point(p) for p in args.eyes] + [_point(args.skin)]
    for x, y in points:
        if not (0 <= x < w and 0 <= y < h):
            raise P2DError("point %d,%d is outside %dx%d" % (x, y, w, h))
    sx, sy = _point(args.skin)
    skin = a[sy, sx, :3].astype(int)
    if a[sy, sx, 3] == 0:
        raise P2DError("skin point %d,%d is transparent" % (sx, sy))
    eyes = [_point(p) for p in args.eyes]
    eye_set = set(eyes)
    failures: List[str] = []
    groups: List[List[Tuple[int, int]]] = []
    seen = set()
    for p in eyes:
        if p in seen:
            continue
        stack, group = [p], []
        seen.add(p)
        while stack:
            q = stack.pop()
            group.append(q)
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                n = (q[0] + dx, q[1] + dy)
                if n in eye_set and n not in seen:
                    seen.add(n)
                    stack.append(n)
        groups.append(sorted(group))
    emit("EYES", len(groups))
    for i, group in enumerate(groups, 1):
        problems = []
        for x, y in group:
            px = a[y, x]
            if px[3] == 0:
                problems.append("%d,%d transparent" % (x, y))
        darkest = min(_luma(a[y, x]) for x, y in group)
        if _luma(skin) - darkest < MIN_CONTRAST:
            problems.append("contrast %.0f < %d vs skin" % (_luma(skin) - darkest, MIN_CONTRAST))
        face_sides = 0
        for x, y in group:
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in eye_set or not (0 <= nx < w and 0 <= ny < h):
                    continue
                n = a[ny, nx]
                if n[3] and (_skin_like(n, skin) or _sclera(n, skin)):
                    face_sides += 1
        need = (2 if len(groups) > 1 else 1) * len(group)  # a side-view eye touches the profile edge
        if face_sides < need:
            problems.append("not on skin (%d skin/sclera sides for %d eye pixels, need 2 each): hair, helmet or outline covers it" % (face_sides, len(group)))
        label = " ".join("%d,%d" % p for p in group)
        emit("EYE_%d" % i, "%s %s" % (label, "PASS" if not problems else "FAIL " + "; ".join(problems)))
        if problems:
            failures.append(label)
    opaque_rows = np.where(a[..., 3].any(axis=1))[0]
    top = int(opaque_rows[0]) if len(opaque_rows) else 0
    bottom = min(h, max(y for _, y in eyes) + max(3, h // 8))
    crop = a[top:bottom]
    out = args.out or os.path.splitext(args.image)[0] + "-face@%dx.png" % args.scale
    Image.fromarray(upscale(crop, args.scale), "RGBA").save(out)
    emit("CROP", out)
    emit("RESULT", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image", help="finished character frame or face PNG")
    parser.add_argument("--eyes", nargs="+", required=True, help="every eye pixel X,Y (1-based counting not used: 0,0 is top-left)")
    parser.add_argument("--skin", required=True, help="one face skin pixel X,Y")
    parser.add_argument("--key", help="background color of an opaque sheet (e.g. #009392), treated as transparent")
    parser.add_argument("--scale", type=int, default=8, help="nearest-neighbour scale of the head crop")
    parser.add_argument("--out", help="crop path (default <image>-face@<scale>x.png)")
    return cmd_face
