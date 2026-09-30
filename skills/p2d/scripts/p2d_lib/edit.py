from __future__ import annotations

import argparse
import re
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np

from . import color
from .imageio import Arr, P2DError, emit, load_rgba, parse_hex, save_rgba, to_hex
from .pack import load_pack

RGB = Tuple[int, int, int]
_SET = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*=\s*(#?[0-9A-Fa-f]{6}|#?[0-9A-Fa-f]{3})\s*$")
_CLEAR = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*$")


def _as_rgb(color: object) -> RGB:
    if isinstance(color, str):
        return parse_hex(color)
    if not isinstance(color, Sequence):
        raise P2DError("color must be #RRGGBB, got %r" % (color,))
    picked = list(color)[:3]
    if len(picked) != 3:
        raise P2DError("color must be #RRGGBB, got %r" % (color,))
    try:
        values = (int(picked[0]), int(picked[1]), int(picked[2]))
    except (TypeError, ValueError):
        raise P2DError("color must be #RRGGBB, got %r" % (color,))
    if any(channel < 0 or channel > 255 for channel in values):
        raise P2DError("color must be #RRGGBB, got %r" % (color,))
    return values


def _check_pixel(x: int, y: int, width: int, height: int) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        raise P2DError("pixel %d,%d is outside 0..%d, 0..%d" % (x, y, width - 1, height - 1))


def touch(
    rgba: Arr,
    sets: Sequence[Sequence[Any]],
    clears: Sequence[Sequence[Any]],
    palette: Optional[Sequence[object]] = None,
) -> Arr:
    src = np.asarray(rgba)
    if src.ndim != 3 or src.shape[2] != 4:
        raise P2DError("touch expects an RGBA image")
    height, width = int(src.shape[0]), int(src.shape[1])
    parsed_sets: List[Tuple[int, int, RGB]] = []
    for item in sets or []:
        if len(item) != 3:
            raise P2DError("set needs x, y and a color")
        x, y = int(item[0]), int(item[1])
        parsed_sets.append((x, y, _as_rgb(item[2])))
    parsed_clears: List[Tuple[int, int]] = []
    for item in clears or []:
        if len(item) < 2:
            raise P2DError("clear needs x, y")
        parsed_clears.append((int(item[0]), int(item[1])))
    for x, y, _color in parsed_sets:
        _check_pixel(x, y, width, height)
    for x, y in parsed_clears:
        _check_pixel(x, y, width, height)
    allowed = None
    if palette is not None:
        allowed = {_as_rgb(entry) for entry in palette}
    if allowed is not None:
        for _x, _y, rgb in parsed_sets:
            if rgb not in allowed:
                raise P2DError("color %s is not in the palette" % to_hex(rgb))
    out = np.array(src, dtype=np.uint8, copy=True)
    for x, y in parsed_clears:
        out[y, x] = (0, 0, 0, 0)
    for x, y, rgb in parsed_sets:
        out[y, x, 0] = rgb[0]
        out[y, x, 1] = rgb[1]
        out[y, x, 2] = rgb[2]
        out[y, x, 3] = 255
    return out


def _parse_set(text: str) -> Tuple[int, int, RGB]:
    match = _SET.fullmatch(text or "")
    if not match:
        raise P2DError("set must look like X,Y=#RRGGBB, got %r" % text)
    return int(match.group(1)), int(match.group(2)), parse_hex(match.group(3))


def _parse_clear(text: str) -> Tuple[int, int]:
    match = _CLEAR.fullmatch(text or "")
    if not match:
        raise P2DError("clear must look like X,Y, got %r" % text)
    return int(match.group(1)), int(match.group(2))


def _resolve_palette(args: argparse.Namespace) -> Optional[Sequence[RGB]]:
    if args.palette:
        return color.load_palette(args.palette)
    if args.pack:
        data = load_pack(args.pack)
        return [_as_rgb(entry) for entry in (data.get("palette") or [])]
    return None


def cmd_touch(args: argparse.Namespace) -> int:
    rgba = load_rgba(args.image)
    sets = [_parse_set(text) for text in (args.set or [])]
    clears = [_parse_clear(text) for text in (args.clear or [])]
    out = touch(rgba, sets, clears, _resolve_palette(args))
    changed = int(np.any(out != rgba, axis=-1).sum())
    save_rgba(out, args.out)
    emit("OUT", args.out)
    emit("CHANGED", changed)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    if name != "touch":
        raise P2DError("unknown command %s" % name)
    parser.add_argument("image", help="logical PNG to edit")
    parser.add_argument("--set", action="append", default=None, help="X,Y=#RRGGBB (repeatable)")
    parser.add_argument("--clear", action="append", default=None, help="X,Y pixel to make transparent (repeatable)")
    parser.add_argument("--pack", help="pack directory; colors must belong to its palette")
    parser.add_argument("--palette", help="palette .hex file or preset (overrides --pack)")
    parser.add_argument("--out", required=True)
    return cmd_touch
