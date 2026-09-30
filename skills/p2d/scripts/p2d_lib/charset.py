from __future__ import annotations

import argparse
import os
from typing import Callable, Dict, Tuple

import numpy as np
from PIL import Image

from . import color
from . import pack as pack_mod
from .imageio import Arr, MAGENTA, P2DError, emit, load_rgba, parse_hex, save_rgba

DIRECTIONS = ("down", "left", "right", "up")
DLRU = ("down", "left", "right", "up")
FORMATS = {
    "rm2k": {"frame": (24, 32), "rows": ("up", "right", "down", "left"), "block": (72, 128), "sheet": (288, 256), "slots": (4, 2)},
    "vxace": {"frame": (32, 32), "rows": DLRU, "block": (96, 128), "sheet": (384, 256), "slots": (4, 2)},
    "mv": {"frame": (48, 48), "rows": DLRU, "block": (144, 192), "sheet": (576, 384), "slots": (4, 2)},
}


def _load_frames(frames_dir: str) -> Dict[Tuple[int, int], Arr]:
    frames: Dict[Tuple[int, int], Arr] = {}
    for r in range(4):
        for c in range(3):
            path = os.path.join(frames_dir, "r%dc%d.png" % (r, c))
            if not os.path.exists(path):
                raise P2DError("missing frame %s" % path)
            frames[(r, c)] = load_rgba(path)
    return frames


def _decode_indexed(img: Image.Image) -> Arr:
    rgba = np.array(img.convert("RGBA"))
    if img.mode == "P":
        rgba[np.array(img) == 0, 3] = 0
    return rgba


def _load_sheet(path: str, size: Tuple[int, int]) -> Arr:
    with Image.open(path) as img:
        if img.size != size:
            raise P2DError("existing sheet %s is %dx%d, expected %dx%d" % (path, img.size[0], img.size[1], size[0], size[1]))
        sheet = _decode_indexed(img)
    canvas = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    mask = sheet[..., 3] > 0
    canvas[mask] = sheet[mask]
    return canvas


def _save_indexed(sheet: Arr, path: str, key: Tuple[int, int, int]) -> None:
    opaque = sheet[sheet[..., 3] > 0][:, :3]
    unique = np.unique(opaque, axis=0) if len(opaque) else np.zeros((0, 3), np.uint8)
    if len(unique) > 255:
        raise P2DError("sheet has %d opaque colors, an 8-bit indexed sheet allows 255" % len(unique))
    ordered = color.sort_palette([(int(c[0]), int(c[1]), int(c[2])) for c in unique])
    index = np.zeros(sheet.shape[:2], dtype=np.uint8)
    for i, rgb in enumerate(ordered):
        match = (sheet[..., 3] > 0) & (sheet[..., :3] == np.array(rgb, dtype=np.uint8)).all(axis=2)
        index[match] = i + 1
    palette = [int(v) for v in key] + [v for rgb in ordered for v in rgb]
    palette += [0] * (768 - len(palette))
    img = Image.fromarray(index)
    img.putpalette(palette)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    img.save(path, transparency=0)


def _prefixed_out(path: str, single: bool, is_object: bool) -> str:
    directory, base = os.path.split(path)
    prefix = ("!" if is_object else "") + ("$" if single else "")
    if not prefix or base.startswith(prefix):
        return path
    return os.path.join(directory, prefix + base.lstrip("!$"))


def cmd_charset(args: argparse.Namespace) -> int:
    fmt = FORMATS[args.format]
    order = [part.strip().lower() for part in args.order.split(",") if part.strip()]
    if sorted(order) != sorted(DIRECTIONS):
        raise P2DError("--order must name the four generation rows down,left,right,up in any order")
    if args.format == "rm2k" and (args.sheet != "single" or args.object):
        raise P2DError("--sheet and --object apply to vxace/mv formats")
    if not 0 <= args.slot <= 7:
        raise P2DError("--slot must be 0..7")
    if args.sheet == "single" and args.format != "rm2k" and args.slot != 0:
        raise P2DError("--slot needs --sheet eight")
    fw, fh = fmt["frame"]
    frames = _load_frames(args.frames)
    for (r, c), arr in sorted(frames.items()):
        if arr.shape[1] != fw or arr.shape[0] != fh:
            raise P2DError("frame r%dc%d is %dx%d, %s needs %dx%d" % (r, c, arr.shape[1], arr.shape[0], args.format, fw, fh))
    key = parse_hex(args.key) if args.key else MAGENTA
    if args.pack and not args.key:
        data = pack_mod.load_pack(args.pack)
        if data.get("key"):
            key = parse_hex(data["key"])
    gen_row = {name: idx for idx, name in enumerate(order)}
    by_dir = {d: [frames[(gen_row[d], p)] for p in range(3)] for d in DIRECTIONS}
    if args.mirror_right:
        by_dir["right"] = [np.ascontiguousarray(np.flip(by_dir["left"][p], axis=1)) for p in range(3)]
    sheet_rows = fmt["rows"]
    if args.format == "rm2k":
        sw, sh = fmt["sheet"]
        bw, bh = fmt["block"]
        sheet = _load_sheet(args.out, (sw, sh)) if os.path.exists(args.out) else np.zeros((sh, sw, 4), dtype=np.uint8)
        bx, by = (args.slot % fmt["slots"][0]) * bw, (args.slot // fmt["slots"][0]) * bh
        for d, direction in enumerate(sheet_rows):
            for p in range(3):
                sheet[by + d * fh : by + (d + 1) * fh, bx + p * fw : bx + (p + 1) * fw] = by_dir[direction][p]
        _save_indexed(sheet, args.out, key)
        out_path = args.out
    else:
        if args.sheet == "single":
            sheet = np.zeros((fh * 4, fw * 3, 4), dtype=np.uint8)
            for d, direction in enumerate(sheet_rows):
                for p in range(3):
                    sheet[d * fh : (d + 1) * fh, p * fw : (p + 1) * fw] = by_dir[direction][p]
        else:
            sw, sh = fmt["sheet"]
            bw, bh = fmt["block"]
            sheet = _load_sheet(args.out, (sw, sh)) if os.path.exists(args.out) else np.zeros((sh, sw, 4), dtype=np.uint8)
            bx, by = (args.slot % fmt["slots"][0]) * bw, (args.slot // fmt["slots"][0]) * bh
            for d, direction in enumerate(sheet_rows):
                for p in range(3):
                    sheet[by + d * fh : by + (d + 1) * fh, bx + p * fw : bx + (p + 1) * fw] = by_dir[direction][p]
        out_path = _prefixed_out(args.out, args.sheet == "single", args.object)
        save_rgba(sheet, out_path)
    emit("OUT", out_path)
    emit("FORMAT", args.format)
    emit("SIZE", "%dx%d" % (sheet.shape[1], sheet.shape[0]))
    emit("SLOT", args.slot)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--format", choices=["rm2k", "vxace", "mv"], required=True, help="engine sheet format")
    parser.add_argument("--frames", required=True, help="4x3 frames dir from `p2d.py frames` (r{row}c{col}.png)")
    parser.add_argument("--out", required=True, help="output sheet file")
    parser.add_argument("--order", default="down,left,right,up", help="direction of each generation row")
    parser.add_argument("--mirror-right", action="store_true", help="build the right row as the mirrored left row")
    parser.add_argument("--slot", type=int, default=0, help="character slot 0-7 in multi-character sheets")
    parser.add_argument("--key", default=None, help="transparent key color at palette index 0 (default #ff00ff or the pack key)")
    parser.add_argument("--pack", help="pack dir providing the key color")
    parser.add_argument("--sheet", choices=["single", "eight"], default="single", help="vxace/mv: $ single character or the 8-character sheet")
    parser.add_argument("--object", action="store_true", help='vxace/mv: add the "!" prefix (objects without display offset)')
    return cmd_charset
