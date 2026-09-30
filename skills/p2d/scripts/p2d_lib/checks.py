from __future__ import annotations

import argparse
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import color, pack, pixelize, seam
from .imageio import MAGENTA, Arr, P2DError, emit, emit_result, load_rgba, parse_hex, parse_size

SURFACE = ("tile", "wall", "trim")
CUTOUT = ("prop", "frame")
KINDS = SURFACE + CUTOUT


def default_axis(kind: str, width: int, height: int) -> str:
    if kind == "tile":
        return "xy"
    if kind == "wall":
        return "x"
    if kind == "trim":
        return "x" if width >= height else "y"
    if kind in CUTOUT:
        return "none"
    raise P2DError("unknown kind %r (%s)" % (kind, ", ".join(KINDS)))


def _checked_axes(axis: str) -> List[str]:
    if axis == "xy":
        return ["x", "y"]
    if axis in ("x", "y"):
        return [axis]
    if axis == "none":
        return []
    raise P2DError("axis must be x, y, xy or none")


def _palette(data: Optional[Dict[str, Any]]) -> List[Tuple[int, int, int]]:
    if not data or not data.get("palette"):
        return []
    return [parse_hex(entry) for entry in data["palette"]]


def _outside_palette(rgba: Arr, palette: Sequence[Tuple[int, int, int]]) -> int:
    pixels = rgba[..., :3][rgba[..., 3] > 0]
    if len(pixels) == 0 or not palette:
        return 0
    matched = np.zeros(len(pixels), dtype=bool)
    for entry in palette:
        matched |= np.all(pixels == np.asarray(entry, dtype=np.uint8), axis=1)
    return int((~matched).sum())


def _edge_touch(rgba: Arr) -> str:
    height, width = rgba.shape[:2]
    box = pixelize.subject_bbox(rgba[..., 3])
    if box is None:
        return "none"
    x0, y0, x1, y1 = box
    sides = []
    if y0 == 0:
        sides.append("top")
    if x0 == 0:
        sides.append("left")
    if x1 == width:
        sides.append("right")
    if y1 == height:
        sides.append("bottom")
    return ",".join(sides) if sides else "none"


def _color_cap(args: argparse.Namespace, data: Optional[Dict[str, Any]]) -> int:
    if args.max_colors is not None:
        return int(args.max_colors)
    if data is not None and data.get("asset_colors") is not None:
        return int(data["asset_colors"])
    return 16


def _key_color(args: argparse.Namespace, data: Optional[Dict[str, Any]]) -> Tuple[int, int, int]:
    if args.key:
        return parse_hex(args.key)
    if data is not None and data.get("key"):
        return parse_hex(data["key"])
    return MAGENTA


def cmd_check(args: argparse.Namespace) -> int:
    rgba = load_rgba(args.image)
    height, width = rgba.shape[:2]
    expected_w, expected_h = parse_size(args.size)
    data = pack.load_pack(args.pack) if args.pack else None
    palette = _palette(data)
    cap = _color_cap(args, data)
    key = _key_color(args, data)
    axis = args.axis or default_axis(args.kind, width, height)
    alpha = rgba[..., 3]
    colors = color.count_colors(rgba)
    binary = bool(np.all((alpha == 0) | (alpha == 255)))
    opaque = alpha > 0
    residue = int((pixelize.key_mask(rgba, key) & opaque).sum()) if opaque.any() else 0
    transparent = int((alpha == 0).sum())
    percent = float(transparent / alpha.size * 100.0) if alpha.size else 0.0
    edges = _edge_touch(rgba)
    ratios = [(name, seam.seam_ratio(rgba, name)) for name in _checked_axes(axis)]
    outside = _outside_palette(rgba, palette) if palette else 0

    reasons: List[str] = []
    if (width, height) != (expected_w, expected_h):
        reasons.append("size is %dx%d, expected %dx%d" % (width, height, expected_w, expected_h))
    if colors > cap:
        reasons.append("colors %d over the cap of %d" % (colors, cap))
    if palette and outside:
        reasons.append("OUT_OF_PALETTE %d" % outside)
    if not binary:
        reasons.append("alpha is not binary")
    if residue:
        reasons.append("KEY_RESIDUE %d" % residue)
    if args.kind in SURFACE and transparent:
        reasons.append("transparent pixels in a %s" % args.kind)
    for name, ratio in ratios:
        if ratio > args.seam_max:
            reasons.append("SEAM_%s %.4f too high" % (name.upper(), ratio))
    if args.kind in CUTOUT and not opaque.any():
        reasons.append("no opaque pixel")
    if args.kind in CUTOUT and transparent == 0 and not args.allow_opaque:
        reasons.append("%s has no transparent pixels" % args.kind)
    if args.kind == "frame":
        touched = [side for side in ("top", "left", "right") if side in edges.split(",")]
        if touched:
            reasons.append("frame touches %s edge" % ",".join(touched))

    emit("SIZE", "%dx%d" % (width, height))
    emit("COLORS", colors)
    if palette:
        emit("OUT_OF_PALETTE", outside)
    emit("ALPHA_BINARY", "yes" if binary else "no")
    emit("KEY_RESIDUE", residue)
    emit("TRANSPARENT_PERCENT", round(percent, 2))
    for name, ratio in ratios:
        emit("SEAM_%s" % name.upper(), "%.4f" % ratio)
    emit("EDGE_TOUCH", edges)
    return emit_result(not reasons, reasons)


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image")
    parser.add_argument("--kind", required=True, choices=list(KINDS))
    parser.add_argument("--size", required=True, help="expected size WxH")
    parser.add_argument("--pack", help="pack directory: palette, asset color cap and key")
    parser.add_argument("--max-colors", type=int, default=None, help="color cap (default: pack asset_colors or 16)")
    parser.add_argument(
        "--axis",
        choices=["x", "y", "xy", "none"],
        default=None,
        help="seam axes (default: tile xy, wall x, trim x if width >= height else y, prop/frame none)",
    )
    parser.add_argument("--seam-max", type=float, default=1.6, help="fail when a checked seam ratio is above this")
    parser.add_argument("--key", default=None, help="key color (default: pack key or #ff00ff)")
    parser.add_argument("--allow-opaque", action="store_true", help="allow a prop or frame with no transparent pixels")
    return cmd_check
