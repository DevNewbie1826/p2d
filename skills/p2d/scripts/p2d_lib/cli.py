"""Each command module exposes configure(name, parser) -> handler(args) -> exit code."""
from __future__ import annotations

import argparse
import importlib
import sys
from typing import List

from .imageio import P2DError

COMMANDS = {
    "doctor": ("pack", "Check python, Pillow and numpy are available."),
    "size": ("pack", "Valid generate_image size for a logical canvas (e.g. 16x16)."),
    "pack": ("pack", "Create or update pack.json (px, palette, style lock, assets)."),
    "palette": ("pack", "Extract a palette (.hex) from existing pixel-art images."),
    "inspect": ("pixelize", "Describe an image: colors, alpha, detected pixel pitch, suggested px."),
    "raw-check": ("pixelize", "Check a raw generation: real alpha, key background, painted checkerboard."),
    "pixelize": ("pixelize", "Convert a generated image into an exact-size, palette-limited pixel asset."),
    "offset": ("seam", "Roll an image by half (and write a repaint mask) to fix tile seams."),
    "check": ("checks", "QC a finished asset: size, colors, palette, alpha, seams, edges."),
    "frames": ("frames", "Cut a generated grid into shared-scale, anchored animation frames + QC."),
    "gif": ("frames", "Animated GIF preview from frame PNGs."),
    "charset": ("charset", "Assemble an RPG Maker character sheet (2000, VX Ace, MV/MZ)."),
    "touch": ("edit", "Set or clear individual logical pixels (small face/detail repairs) within the palette."),
    "atlas": ("preview", "Pack PNGs into one sheet with a coordinate JSON."),
    "preview": ("preview", "Contact sheet (reference-style pack view) or tile repeat preview."),
}


def _top_help() -> str:
    width = max(len(n) for n in COMMANDS)
    lines = [
        "usage: p2d.py <command> [options]",
        "",
        "commands:",
    ]
    for name, (_, text) in COMMANDS.items():
        lines.append("  %s  %s" % (name.ljust(width), text))
    lines += ["", "Run `p2d.py <command> --help` for that command's options."]
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_top_help())
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print("ERROR: unknown command %r" % name, file=sys.stderr)
        print(_top_help(), file=sys.stderr)
        return 2
    module = importlib.import_module("p2d_lib." + COMMANDS[name][0])
    parser = argparse.ArgumentParser(prog="p2d.py " + name, description=COMMANDS[name][1])
    handler = module.configure(name, parser)
    args = parser.parse_args(rest)
    try:
        return int(handler(args))
    except P2DError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
