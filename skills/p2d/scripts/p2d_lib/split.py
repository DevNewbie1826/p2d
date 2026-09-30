from __future__ import annotations

import argparse
import os
from typing import Callable

from .imageio import P2DError, emit, load_rgba, save_rgba


def cmd_split(args: argparse.Namespace) -> int:
    rgba = load_rgba(args.image)
    height, width = rgba.shape[:2]
    unit = args.unit
    if unit < 1:
        raise P2DError("unit must be positive")
    if width % unit or height % unit:
        raise P2DError("block size %dx%d must be a multiple of %d" % (width, height, unit))
    name = args.name or os.path.splitext(os.path.basename(args.image))[0]
    emit("TILES", (height // unit) * (width // unit))
    for row in range(height // unit):
        for col in range(width // unit):
            path = os.path.join(args.out, "%s-r%dc%d@%d.png" % (name, row, col, unit))
            save_rgba(rgba[row * unit:(row + 1) * unit, col * unit:(col + 1) * unit], path)
            emit("TILE", path)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("image", help="native block PNG (no resampling)")
    parser.add_argument("--unit", required=True, type=int, help="tile width and height in pixels")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--name", help="filename prefix (default: input stem)")
    return cmd_split
