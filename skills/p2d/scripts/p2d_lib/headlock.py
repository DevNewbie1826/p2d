from __future__ import annotations

import argparse
import os
import re
import shutil
from typing import Callable

import numpy as np

from .imageio import P2DError, emit, emit_result, load_rgba, read_json, save_rgba, write_json


def cmd_headlock(args: argparse.Namespace) -> int:
    if not os.path.isdir(args.frames_dir):
        raise P2DError("frames directory not found: %s" % args.frames_dir)
    if args.head_rows < 1:
        raise P2DError("--head-rows must be >= 1")
    if args.head_bob < 0:
        raise P2DError("--head-bob must be >= 0")

    meta_path = os.path.join(args.frames_dir, "frames.json")
    meta = read_json(meta_path) if os.path.isfile(meta_path) else None
    if meta is not None:
        rows, cols = meta["rows"], meta["cols"]
    else:
        cells = [
            (int(match[1]), int(match[2]))
            for name in os.listdir(args.frames_dir)
            for match in [re.fullmatch(r"r(\d+)c(\d+)\.png", name)]
            if match is not None
        ]
        rows = max((r for r, _ in cells), default=-1) + 1
        cols = max((c for _, c in cells), default=-1) + 1
    if cols != 3:
        raise P2DError("headlock requires exactly 3 columns (step, standing, step)")
    if rows < 1:
        raise P2DError("frames directory must contain at least one row")

    frames = {
        (r, c): load_rgba(os.path.join(args.frames_dir, "r%dc%d.png" % (r, c)))
        for r in range(rows)
        for c in range(cols)
    }
    if len({frame.shape for frame in frames.values()}) != 1:
        raise P2DError("frame files must share one size")

    before, after = [], []
    for r in range(rows):
        donor = frames[r, 1]
        occupied = np.flatnonzero(donor[..., 3].any(axis=1))
        if not len(occupied):
            raise P2DError("empty donor frame: r%dc1.png" % r)
        top = int(occupied[0])
        start = top + args.head_bob
        end = start + args.head_rows
        if end > donor.shape[0]:
            raise P2DError("head band exceeds frame height: r%dc1.png" % r)
        band = donor[top:top + args.head_rows]
        for c in (0, 2):
            frame = frames[r, c]
            before.append(float(np.any(frame[start:end] != band, axis=2).mean()))
            frame[:end] = 0
            frame[start:end] = band
            after.append(float(np.any(frame[start:end] != band, axis=2).mean()))

    drift_before = float(np.mean(before))
    drift_after = float(np.mean(after))
    out = args.out or args.frames_dir
    if os.path.abspath(out) != os.path.abspath(args.frames_dir):
        shutil.copytree(args.frames_dir, out, dirs_exist_ok=True)
    for r in range(rows):
        for c in (0, 2):
            save_rgba(frames[r, c], os.path.join(out, "r%dc%d.png" % (r, c)))
    if meta is not None:
        meta["head_lock"] = {
            "rows": args.head_rows,
            "bob": args.head_bob,
            "drift_before": round(drift_before, 4),
        }
        write_json(os.path.join(out, "frames.json"), meta)
    emit("HEAD_ROWS", args.head_rows)
    emit("HEAD_BOB", args.head_bob)
    emit("HEAD_DRIFT_BEFORE", "%.4f" % drift_before)
    emit("HEAD_DRIFT_AFTER", "%.4f" % drift_after)
    emit("LOCKED_FRAMES", len(after))
    emit("OUT", out)
    return emit_result(drift_after == 0.0)


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("frames_dir", help="directory containing r{row}c{col}.png frames")
    parser.add_argument("--head-rows", type=int, required=True, help="donor head band height in pixels")
    parser.add_argument("--head-bob", type=int, default=1, help="step head offset below standing (default: 1)")
    parser.add_argument("--out", help="copy all source files here before locking (default: in place)")
    return cmd_headlock
