"""Face readability gate: listed eye pixels must be dark, opaque and sit on skin."""
from __future__ import annotations

import argparse
import os
from typing import Callable, List, Tuple

import numpy as np
from PIL import Image

from .imageio import P2DError, emit, load_rgba, upscale

MIN_CONTRAST = 60
MAX_SKIN_DISTANCE = 60


def _point(text: str) -> Tuple[int, int]:
    try:
        x, y = (int(v) for v in text.split(","))
    except ValueError:
        raise P2DError("point must be X,Y: %r" % text)
    return x, y


def _luma(c: np.ndarray) -> float:
    return 0.299 * float(c[0]) + 0.587 * float(c[1]) + 0.114 * float(c[2])


def cmd_face(args: argparse.Namespace) -> int:
    a = load_rgba(args.image)
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
    for i, (x, y) in enumerate(eyes, 1):
        px = a[y, x]
        problems = []
        if px[3] == 0:
            problems.append("transparent")
        elif _luma(skin) - _luma(px) < MIN_CONTRAST:
            problems.append("contrast %.0f < %d vs skin" % (_luma(skin) - _luma(px), MIN_CONTRAST))
        skin_sides = 0
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in eye_set or not (0 <= nx < w and 0 <= ny < h):
                continue
            n = a[ny, nx]
            if n[3] and np.abs(n[:3].astype(int) - skin).sum() <= MAX_SKIN_DISTANCE:
                skin_sides += 1
        if skin_sides < 2:
            problems.append("not on skin (%d skin sides < 2): hair, helmet or outline covers it" % skin_sides)
        state = "PASS" if not problems else "FAIL " + "; ".join(problems)
        emit("EYE_%d" % i, "%d,%d %s" % (x, y, state))
        if problems:
            failures.append("%d,%d" % (x, y))
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
    parser.add_argument("--scale", type=int, default=8, help="nearest-neighbour scale of the head crop")
    parser.add_argument("--out", help="crop path (default <image>-face@<scale>x.png)")
    return cmd_face
