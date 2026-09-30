from __future__ import annotations

import argparse
import re
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


def _outline_colors(text: str) -> List[Tuple[int, int, int]]:
    """Parse a nonempty, explicit RGB palette without inferring dark colors."""
    entries = [entry.strip() for entry in text.split(",")]
    if not all(re.fullmatch(r"#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", entry) for entry in entries):
        raise argparse.ArgumentTypeError("outline colors must be a nonempty comma-separated HEX palette")
    return [parse_hex(entry) for entry in entries]


def _outline_gaps(rgba: Arr, palette: Sequence[Tuple[int, int, int]]) -> Tuple[int, List[Tuple[int, int]]]:
    """Count exposed non-palette pixels; sample at most 32 zero-based (x, y) locations.

    Both transparency flood-fill and foreground adjacency use four neighbors.
    A transparent padded border makes canvas edges exterior even without alpha
    pixels on the canvas. Enclosed transparent holes are not exterior. Alpha > 0
    is foreground, consistent with other checks; nonbinary alpha still fails QC.
    This tests the declared silhouette rule, not universal art quality.
    """
    transparent = np.pad(rgba[..., 3] == 0, 1, constant_values=True)
    exterior = np.zeros(transparent.shape, dtype=bool)
    exterior[0, 0] = True
    pending = [(0, 0)]
    height, width = transparent.shape
    while pending:
        y, x = pending.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width and transparent[ny, nx] and not exterior[ny, nx]:
                exterior[ny, nx] = True
                pending.append((ny, nx))
    boundary = (rgba[..., 3] > 0) & (
        exterior[:-2, 1:-1] | exterior[2:, 1:-1] | exterior[1:-1, :-2] | exterior[1:-1, 2:]
    )
    covered = np.zeros(boundary.shape, dtype=bool)
    for entry in palette:
        covered |= np.all(rgba[..., :3] == np.asarray(entry, dtype=np.uint8), axis=2)
    gaps = boundary & ~covered
    locations = [(int(x), int(y)) for y, x in np.argwhere(gaps)[:32]]
    return int(gaps.sum()), locations


# (singleton % warning above, mean cluster warning below) per kind and tile size,
# measured on original human-made 16/32/48 packs; frames use character bands.
NOISE_PROFILE = {
    ("tile", 16): (20.0, 3.0), ("tile", 32): (12.0, 5.0), ("tile", 48): (10.0, 6.0),
    ("trim", 16): (20.0, 3.0), ("trim", 32): (12.0, 5.0), ("trim", 48): (10.0, 6.0),
    ("wall", 16): (15.0, 3.0), ("wall", 32): (5.0, 10.0), ("wall", 48): (5.0, 10.0),
    ("prop", 16): (20.0, 3.0), ("prop", 32): (8.0, 6.0), ("prop", 48): (15.0, 3.0),
    ("frame", 16): (28.0, 2.0), ("frame", 32): (30.0, 2.25), ("frame", 48): (25.0, 3.0),
}


def noise_limits(kind: str, width: int, height: int) -> Optional[Tuple[float, float]]:
    unit = min(width, height)
    if kind == "frame" and (width, height) == (24, 32):
        unit = 16
    for px in (48, 32, 16):
        if unit >= px:
            return NOISE_PROFILE[(kind, px)]
    return None


def cluster_stats(rgba: Arr) -> Tuple[float, float]:
    """Percent of opaque pixels with no same-color 4-neighbor, and mean same-color 4-connected cluster size."""
    opaque = rgba[..., 3] > 0
    total = int(opaque.sum())
    if total == 0:
        return 0.0, 0.0
    rgb = rgba[..., :3].astype(np.int32)
    code = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    code = np.where(opaque, code, -1)
    padded = np.pad(code, 1, constant_values=-2)
    same = np.zeros(code.shape, dtype=bool)
    for dy, dx in ((0, 1), (2, 1), (1, 0), (1, 2)):
        same |= padded[dy : dy + code.shape[0], dx : dx + code.shape[1]] == code
    singletons = int((opaque & ~same).sum())
    seen = np.zeros(code.shape, dtype=bool)
    clusters = 0
    height, width = code.shape
    for y0, x0 in np.argwhere(opaque):
        if seen[y0, x0]:
            continue
        clusters += 1
        value = code[y0, x0]
        seen[y0, x0] = True
        pending = [(int(y0), int(x0))]
        while pending:
            y, x = pending.pop()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and not seen[ny, nx] and code[ny, nx] == value:
                    seen[ny, nx] = True
                    pending.append((ny, nx))
    return singletons / total * 100.0, total / clusters


def cmd_check(args: argparse.Namespace) -> int:
    if args.outline_colors is not None and args.kind not in CUTOUT:
        raise P2DError("--outline-colors is only supported for prop/frame")
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
    noise_rgba = rgba
    if args.kind == "frame" and args.key:
        # Original keyed sheets are opaque; exclude their declared key from
        # character noise statistics without hiding alpha/residue QC failures.
        noise_rgba = rgba.copy()
        noise_rgba[np.all(rgba[..., :3] == np.asarray(key), axis=2), 3] = 0
    singleton_percent, mean_cluster = cluster_stats(noise_rgba)

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
        if args.kind in SURFACE and colors > 1:
            strips = rgba.transpose(1, 0, 2) if name == "x" else rgba
            if len(strips) > 2 and np.array_equal(strips[0], strips[-1]):
                # A zero wrap difference is suspicious only if an inner transition
                # exists: flat fields and stripes parallel to this axis are valid.
                inner_diff = (np.any(strips[0] != strips[1]) or np.any(strips[-1] != strips[-2]))
                if inner_diff:
                    # Identical opposite edges may be a copied edge or a natural period;
                    # it cannot be told apart from pixels alone, so ask for review.
                    emit("SEAM_%s_EDGE_REVIEW" % name.upper(), "opposite edges identical: check the 4x4 repeat for a copied edge")
        if ratio > args.seam_max:
            reasons.append("SEAM_%s %.4f too high" % (name.upper(), ratio))
    if args.max_singletons is not None and singleton_percent > args.max_singletons:
        reasons.append("SINGLETON_PERCENT %.1f over %.1f (speckle noise)" % (singleton_percent, args.max_singletons))
    if args.kind in CUTOUT and not opaque.any():
        reasons.append("no opaque pixel")
    if args.kind in CUTOUT and transparent == 0 and not args.allow_opaque:
        reasons.append("%s has no transparent pixels" % args.kind)
    if args.kind == "frame":
        touched = [side for side in ("top", "left", "right") if side in edges.split(",")]
        if touched:
            reasons.append("frame touches %s edge" % ",".join(touched))
    if args.outline_colors is not None:
        uncovered, locations = _outline_gaps(rgba, args.outline_colors)
        if uncovered:
            reasons.append("OUTLINE_UNCOVERED %d" % uncovered)
        emit("OUTLINE_UNCOVERED", uncovered)
        emit("OUTLINE_UNCOVERED_COORDS", " ".join("%d,%d" % point for point in locations) or "none")

    emit("SIZE", "%dx%d" % (width, height))
    emit("COLORS", colors)
    budget = {16: 3, 32: 4, 48: 4}.get(min(width, height))
    if args.kind == "tile" and budget is not None and args.max_colors is not None and cap < budget:
        emit("COLORS_BELOW_BUDGET", "%d below tile %dpx minimum %d" % (cap, min(width, height), budget))
    if palette:
        emit("OUT_OF_PALETTE", outside)
    emit("ALPHA_BINARY", "yes" if binary else "no")
    emit("KEY_RESIDUE", residue)
    emit("TRANSPARENT_PERCENT", round(percent, 2))
    for name, ratio in ratios:
        emit("SEAM_%s" % name.upper(), "%.4f" % ratio)
    emit("EDGE_TOUCH", edges)
    emit("SINGLETON_PERCENT", "%.1f" % singleton_percent)
    emit("MEAN_CLUSTER", "%.2f" % mean_cluster)
    limits = noise_limits(args.kind, width, height)
    if limits is not None:
        flagged = singleton_percent > limits[0] or mean_cluster < limits[1]
        if args.kind == "frame" and (width, height) == (24, 32) and 31.0 <= singleton_percent <= 52.0:
            flagged = False
        emit("NOISE_REVIEW", "yes (singleton > %.0f%% or cluster < %.2f)" % limits if flagged else "no")
        if flagged and args.kind in SURFACE and not args.allow_noise:
            reasons.append(
                "NOISE: scattered isolated pixels for a %s of this px (singleton %.1f%%, cluster %.2f)"
                % (args.kind, singleton_percent, mean_cluster)
            )
            cleaned, _, _ = pixelize.despeckle_auto(rgba)
            target, _ = cluster_stats(cleaned)
            emit("NOISE_HINT", "--despeckle auto would reach %.1f%% singletons (3%% change cap)" % target)
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
    parser.add_argument(
        "--max-singletons",
        type=float,
        default=None,
        help="fail when more than this percent of opaque pixels have no same-color 4-neighbor (speckle noise)",
    )
    parser.add_argument(
        "--allow-noise",
        action="store_true",
        help="tile/wall/trim: do not fail on NOISE_REVIEW (only for a deliberately dithered or dense style the user asked for)",
    )
    parser.add_argument("--key", default=None, help="key color (default: pack key or #ff00ff)")
    parser.add_argument("--allow-opaque", action="store_true", help="allow a prop or frame with no transparent pixels")
    parser.add_argument(
        "--outline-colors",
        type=_outline_colors,
        default=None,
        metavar="HEX[,HEX...]",
        help="prop/frame only: require these RGB colors on the 4-neighbor exterior silhouette; "
        "canvas boundary is exterior, enclosed transparent holes are ignored. "
        "Reports count and up to 32 zero-based x,y coordinates (row order); "
        "checks this outline rule, not overall art quality",
    )
    return cmd_check
