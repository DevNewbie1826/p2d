"""Repeat an accepted native sprite without resampling or drawing new pixels."""
from __future__ import annotations

import argparse
import os
from typing import Callable

import numpy as np
from PIL import UnidentifiedImageError

from .imageio import P2DError, emit, load_rgba, parse_hex, parse_size, save_rgba, upscale, write_json


def cmd_anchor(args: argparse.Namespace) -> int:
    if args.rows < 1 or args.cols < 1:
        raise P2DError("--rows and --cols must be >= 1")
    cw, ch = parse_size(args.cell)
    if args.scale is not None and args.scale < 1:
        raise P2DError("--scale must be >= 1")
    if args.margin < 1:
        raise P2DError("--margin must be >= 1")
    key = parse_hex(args.key)
    try:
        source = load_rgba(args.input)
    except (UnidentifiedImageError, OSError) as exc:
        raise P2DError("cannot read image %s: %s" % (args.input, exc)) from exc
    alpha = source[..., 3]
    if np.any((alpha != 0) & (alpha != 255)):
        raise P2DError("anchor requires binary alpha (0 or 255); partial alpha would change pixels")
    occupied = np.nonzero(alpha == 255)
    if not len(occupied[0]):
        raise P2DError("empty source: no opaque sprite pixels in %s" % args.input)
    sh, sw = source.shape[:2]
    fitting = min((cw - 2 * args.margin) // sw, (ch - 2 * args.margin) // sh)
    scale = args.scale if args.scale is not None else fitting
    if scale < 1 or scale > fitting:
        raise P2DError("source %dx%d at scale %d cannot fit cell %dx%d with margin %d" % (sw, sh, scale, cw, ch, args.margin))
    sprite = upscale(source, scale)
    height, width = sprite.shape[:2]
    x, y = (cw - width) // 2, ch - args.margin - height
    # Exclusive boundary immediately below the lowest opaque source pixel.
    baseline = y + (int(occupied[0].max()) + 1) * scale
    cell = np.empty((ch, cw, 4), dtype=np.uint8)
    cell[:] = (*key, 255)
    region = cell[y:y + height, x:x + width]
    mask = sprite[..., 3] == 255
    region[mask] = sprite[mask]
    sheet = np.tile(cell, (args.rows, args.cols, 1))
    save_rgba(sheet, args.out)
    json_path = os.path.splitext(args.out)[0] + ".json"
    write_json(json_path, {
        "source": args.input,
        "source_size": [int(sw), int(sh)],
        "scale": scale,
        "rows": args.rows,
        "cols": args.cols,
        "sheet": [cw * args.cols, ch * args.rows],
        "cell": [cw, ch],
        "offset": [int(x), int(y)],
        "margin": args.margin,
        "foot_baseline": baseline,
        "key": args.key,
        "out": args.out,
    })
    emit("OUT", args.out)
    emit("JSON", json_path)
    emit("SCALE", scale)
    emit("SIZE", "%dx%d" % (cw * args.cols, ch * args.rows))
    emit("CELL", "%dx%d" % (cw, ch))
    emit("ROWS", args.rows)
    emit("COLS", args.cols)
    emit("FOOT_BASELINE", baseline)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("input", help="accepted native sprite; binary alpha (0 or 255) required")
    parser.add_argument("--rows", type=int, required=True, help="positive number of equal cell rows")
    parser.add_argument("--cols", type=int, required=True, help="positive number of equal cell columns")
    parser.add_argument("--cell", required=True, help="cell WxH in output pixels; one-pixel clear margin on every side")
    parser.add_argument("--out", required=True, help="output PNG; matching JSON sidecar is also written")
    parser.add_argument("--key", default="#ff00ff", help="opaque background HEX color (default: #ff00ff)")
    parser.add_argument("--scale", type=int, help="integer nearest upscale; default: largest fitting the entire source canvas")
    parser.add_argument("--margin", type=int, default=1, help="minimum clear pixels on all sides; use 32 for 256x256 generation-guide cells")
    parser.epilog = (
        "The full source canvas is horizontally centered and bottom aligned inside the margin. "
        "Transparent pixels become the key color; opaque RGBA pixels remain exact. "
        "FOOT_BASELINE is the cell-local exclusive boundary below the lowest opaque pixel "
        "(add row * cell height for a sheet coordinate). No guides are drawn."
    )
    return cmd_anchor
