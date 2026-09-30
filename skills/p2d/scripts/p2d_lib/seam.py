from __future__ import annotations

import argparse
from typing import Callable, Tuple

import numpy as np

from .imageio import Arr, P2DError, emit, load_rgba, save_rgba

AXES = ("x", "y", "xy")


def _paired_redmean(a: Arr, b: Arr) -> Arr:
    # Paired form of color.redmean_distance (same weights, no NxN matrix).
    left = np.asarray(a, dtype=np.float64).reshape(-1, 3)
    right = np.asarray(b, dtype=np.float64).reshape(-1, 3)
    rmean = (left[:, 0] + right[:, 0]) / 2.0
    delta = left - right
    return np.sqrt(
        (2.0 + rmean / 256.0) * delta[:, 0] ** 2
        + 4.0 * delta[:, 1] ** 2
        + (2.0 + (255.0 - rmean) / 256.0) * delta[:, 2] ** 2
    )


def _on_black(rgba: Arr) -> Arr:
    rgb = np.array(rgba[..., :3], copy=True)
    rgb[rgba[..., 3] == 0] = 0
    return rgb


def _mean_paired(a: Arr, b: Arr) -> float:
    if np.size(a) == 0 or np.size(b) == 0:
        return 0.0
    return float(_paired_redmean(a, b).mean())


def seam_ratio(rgba: Arr, axis: str) -> float:
    if axis not in ("x", "y"):
        raise P2DError("seam axis must be x or y")
    rgb = _on_black(rgba)
    if axis == "x":
        wrap = _mean_paired(rgb[:, -1], rgb[:, 0])
        interior = _mean_paired(rgb[:, :-1], rgb[:, 1:]) if rgb.shape[1] > 1 else 0.0
    else:
        wrap = _mean_paired(rgb[-1], rgb[0])
        interior = _mean_paired(rgb[:-1], rgb[1:]) if rgb.shape[0] > 1 else 0.0
    return wrap / (interior + 1e-6)


def offset_image(rgba: Arr, axis: str, inverse: bool = False) -> Arr:
    if axis not in AXES:
        raise P2DError("axis must be x, y or xy")
    out = rgba
    sign = -1 if inverse else 1
    height, width = rgba.shape[:2]
    if axis in ("x", "xy"):
        out = np.roll(out, sign * (width // 2), axis=1)
    if axis in ("y", "xy"):
        out = np.roll(out, sign * (height // 2), axis=0)
    return out


def _span(length: int, band: float) -> Tuple[int, int]:
    width = int(round(float(band) * length))
    if width < 0:
        width = 0
    if width > length:
        width = length
    start = length // 2 - width // 2
    if start < 0:
        start = 0
    if start + width > length:
        start = length - width
    return start, start + width


def seam_mask(w: int, h: int, axis: str, band: float = 0.125) -> Arr:
    if axis not in AXES:
        raise P2DError("axis must be x, y or xy")
    mask = np.zeros((h, w, 4), dtype=np.uint8)
    mask[..., 3] = 255
    if axis in ("x", "xy"):
        x0, x1 = _span(w, band)
        mask[:, x0:x1, 3] = 0
    if axis in ("y", "xy"):
        y0, y1 = _span(h, band)
        mask[y0:y1, :, 3] = 0
    return mask


def cmd_offset(args: argparse.Namespace) -> int:
    rgba = load_rgba(args.image)
    out = offset_image(rgba, args.axis, inverse=args.inverse)
    save_rgba(out, args.out)
    emit("OUT", args.out)
    emit("AXIS", args.axis)
    if args.mask:
        height, width = out.shape[:2]
        save_rgba(seam_mask(width, height, args.axis, args.band), args.mask)
        emit("MASK", args.mask)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image")
    parser.add_argument("--axis", required=True, choices=["x", "y", "xy"], help="roll horizontally, vertically, or both")
    parser.add_argument("--out", required=True)
    parser.add_argument("--mask", help="write a repaint mask; transparent pixels are the centre band")
    parser.add_argument("--band", type=float, default=0.125, help="centre band size as a fraction of width and/or height")
    parser.add_argument("--inverse", action="store_true", help="roll the other way so a previous offset is undone")
    return cmd_offset
