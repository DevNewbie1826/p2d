from __future__ import annotations

import argparse
import math
import os
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .imageio import Arr, P2DError, emit, load_rgba, parse_hex, save_rgba, upscale, write_json

_UPSCALE = re.compile(r"@\d+x")
_PX = re.compile(r"@(16|32|48)(?!\d)")
Entry = Tuple[str, Arr]


def _base_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split("@", 1)[0]


def _scale_for(unit: int, px: int, name: str) -> int:
    if unit < 1 or px < 1:
        raise P2DError("unit and px must be positive")
    scale = unit // px
    if scale < 1:
        raise P2DError("unit %d is smaller than px %d for %s" % (unit, px, name))
    return scale


def _load_preview(path: str, unit: int, default_px: int, repeat: int) -> Optional[Entry]:
    name = os.path.basename(path)
    if _UPSCALE.search(name):
        return None
    match = _PX.search(name)
    px = int(match.group(1)) if match else default_px
    scale = _scale_for(unit, px, name)
    rgba = load_rgba(path)
    if repeat > 1:
        rgba = np.tile(rgba, (repeat, repeat, 1))
    if scale > 1:
        rgba = upscale(rgba, scale)
    return _base_name(path), np.ascontiguousarray(rgba, dtype=np.uint8)


def _group(entries: Sequence[Entry]) -> List[List[Entry]]:
    order: List[str] = []
    groups: Dict[str, List[Entry]] = {}
    for base, image in entries:
        if base not in groups:
            groups[base] = []
            order.append(base)
        groups[base].append((base, image))
    return [groups[name] for name in order]


def _group_width(group: Sequence[Entry], gap: int) -> int:
    return sum(int(image.shape[1]) for _, image in group) + gap * (len(group) - 1)


def _over(canvas: Arr, src: Arr, x: int, y: int) -> None:
    height, width = int(src.shape[0]), int(src.shape[1])
    region = canvas[y : y + height, x : x + width]
    alpha = src[..., 3:4].astype(np.float64) / 255.0
    mixed = src[..., :3].astype(np.float64) * alpha + region[..., :3].astype(np.float64) * (1.0 - alpha)
    region[..., :3] = np.clip(np.round(mixed), 0, 255).astype(np.uint8)


def _sheet(entries: Sequence[Entry], gap: int, wrap: int, bg: Tuple[int, int, int]) -> Arr:
    rows: List[List[Tuple[int, Arr]]] = []
    row: List[Tuple[int, Arr]] = []
    x = 0
    for group in _group(entries):
        width = _group_width(group, gap)
        if row and x + gap + width > wrap:
            rows.append(row)
            row = []
            x = 0
        if row:
            x += gap
        for index, (_, image) in enumerate(group):
            if index:
                x += gap
            row.append((x, image))
            x += int(image.shape[1])
    if row:
        rows.append(row)
    placed: List[Tuple[int, int, Arr]] = []
    y = 0
    right = 0
    for line in rows:
        row_h = max(int(image.shape[0]) for _, image in line)
        for left, image in line:
            placed.append((left, y + row_h - int(image.shape[0]), image))
            right = max(right, left + int(image.shape[1]))
        y += row_h + gap
    height = y - gap if rows else 0
    canvas = np.zeros((height, right, 4), dtype=np.uint8)
    canvas[..., 0] = bg[0]
    canvas[..., 1] = bg[1]
    canvas[..., 2] = bg[2]
    canvas[..., 3] = 255
    for left, top, image in placed:
        _over(canvas, image, left, top)
    return canvas


def cmd_preview(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        raise P2DError("repeat must be >= 1")
    if args.gap < 0:
        raise P2DError("gap must be >= 0")
    if args.width < 1:
        raise P2DError("width must be >= 1")
    entries = []
    for path in args.files:
        entry = _load_preview(path, args.unit, args.px, args.repeat)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise P2DError("no images to preview")
    canvas = _sheet(entries, args.gap, args.width, parse_hex(args.bg))
    save_rgba(canvas, args.out)
    emit("OUT", args.out)
    emit("ITEMS", len(entries))
    emit("SIZE", "%dx%d" % (canvas.shape[1], canvas.shape[0]))
    return 0


def cmd_atlas(args: argparse.Namespace) -> int:
    if args.padding < 0:
        raise P2DError("padding must be >= 0")
    loaded: List[Tuple[str, Arr]] = []
    seen = set()
    for path in args.files:
        key = os.path.splitext(os.path.basename(path))[0]
        if key in seen:
            raise P2DError("duplicate atlas name %r" % key)
        seen.add(key)
        loaded.append((key, load_rgba(path)))
    count = len(loaded)
    cols = args.cols if args.cols is not None else int(math.ceil(math.sqrt(count)))
    if cols < 1:
        raise P2DError("cols must be >= 1")
    cell_w = max(int(image.shape[1]) for _, image in loaded)
    cell_h = max(int(image.shape[0]) for _, image in loaded)
    rows = int(math.ceil(count / float(cols)))
    width = cols * cell_w + (cols - 1) * args.padding
    height = rows * cell_h + (rows - 1) * args.padding
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    mapping: Dict[str, Dict[str, int]] = {}
    for index, (key, image) in enumerate(loaded):
        x = (index % cols) * (cell_w + args.padding)
        y = (index // cols) * (cell_h + args.padding)
        ih, iw = int(image.shape[0]), int(image.shape[1])
        canvas[y : y + ih, x : x + iw] = image
        mapping[key] = {"x": x, "y": y, "w": iw, "h": ih}
    save_rgba(canvas, args.out)
    json_path = os.path.splitext(args.out)[0] + ".json"
    write_json(json_path, mapping)
    emit("OUT", args.out)
    emit("JSON", json_path)
    emit("ITEMS", count)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    if name == "atlas":
        parser.add_argument("files", nargs="+", help="PNG images to pack")
        parser.add_argument("--out", required=True)
        parser.add_argument("--cols", type=int, default=None, help="columns (default: ceil of sqrt of the image count)")
        parser.add_argument("--padding", type=int, default=0, help="empty pixels between cells")
        return cmd_atlas
    if name != "preview":
        raise P2DError("unknown command %s" % name)
    parser.add_argument("files", nargs="+", help="logical PNG assets")
    parser.add_argument("--out", required=True)
    parser.add_argument("--unit", type=int, default=128, help="display size in pixels of one tile unit")
    parser.add_argument("--px", type=int, default=16, help="tile unit when the name has no @16/@32/@48 marker")
    parser.add_argument("--bg", default="#444444", help="sheet background")
    parser.add_argument("--repeat", type=int, default=1, help="tile each image NxN before scaling")
    parser.add_argument("--width", type=int, default=2560, help="wrap groups onto the next row past this width")
    parser.add_argument("--gap", type=int, default=24, help="pixels between images")
    return cmd_preview
