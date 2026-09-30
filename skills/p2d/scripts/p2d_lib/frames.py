from __future__ import annotations

import argparse
import math
import os
from typing import Any, Callable, Dict, List, Sequence, Tuple

import numpy as np
from PIL import Image

from . import color
from . import pack as pack_mod
from . import pixelize
from .imageio import (
    MAGENTA,
    Arr,
    P2DError,
    emit,
    emit_result,
    load_rgba,
    parse_hex,
    parse_int_list,
    parse_size,
    read_json,
    save_rgba,
    upscale,
    write_json,
)

SCALE_CV_MAX = 0.08
ANCHOR_STD_MAX = 0.05
GIF_MAX_COLORS = 255


def _cell_span(total: int, parts: int, index: int) -> Tuple[int, int]:
    return int(index * total / parts), int((index + 1) * total / parts)


def _whitespace_spans(occupied: Arr, parts: int, axis: str) -> List[Tuple[int, int]]:
    """Cut only at unique, fully empty internal gaps near equal-grid boundaries."""
    total = len(occupied)
    transitions = np.diff(np.r_[False, ~occupied, False].astype(np.int8))
    gaps = [
        (int(start), int(end))
        for start, end in zip(np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1))
        if start > 0 and end < total
    ]
    cuts = [0]
    used: List[Tuple[int, int]] = []
    radius = total / parts / 4
    for index in range(1, parts):
        expected = index * total / parts
        candidates = [(start, end) for start, end in gaps if start <= expected + radius and end > expected - radius]
        if len(candidates) != 1:
            raise P2DError(
                "whitespace layout: %s separator %d near %.1f has %d empty gaps (missing or ambiguous)"
                % (axis, index, expected, len(candidates))
            )
        start, end = candidates[0]
        cut = (start + end) // 2
        if (start, end) in used or not expected - radius <= cut <= expected + radius:
            raise P2DError("whitespace layout: %s separator %d is ambiguous or too far from its expected boundary" % (axis, index))
        used.append((start, end))
        cuts.append(cut)
    cuts.append(total)
    return list(zip(cuts[:-1], cuts[1:]))


def _place(grid: Arr, size: Tuple[int, int], anchor: str, dx: int) -> Tuple[Arr, bool]:
    w, h = size
    gh, gw = grid.shape[:2]
    y = h - gh if anchor == "feet" else (h - gh) // 2
    x = int(round((w - gw) / 2.0)) + dx
    clamped = x < 0 or y < 0 or x + gw > w or y + gh > h
    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    sy, sx = max(0, -y), max(0, -x)
    dy, dxp = max(0, y), max(0, x)
    hh = min(gh - sy, h - dy)
    ww = min(gw - sx, w - dxp)
    if hh > 0 and ww > 0:
        canvas[dy : dy + hh, dxp : dxp + ww] = grid[sy : sy + hh, sx : sx + ww]
    return canvas, clamped


def _opaque_chunks(images: Sequence[Arr]) -> List[Arr]:
    return [im[im[..., 3] > 0][:, :3] for im in images]


def cmd_frames(args: argparse.Namespace) -> int:
    fw, fh = parse_size(args.frame)
    if args.rows < 1 or args.cols < 1:
        raise P2DError("--rows and --cols must be >= 1")
    subject_height = args.subject_height if args.subject_height is not None else fh - 2
    if subject_height < 1:
        raise P2DError("--subject-height must be >= 1")
    palette = None
    max_colors = args.max_colors
    key = parse_hex(args.key) if args.key else MAGENTA
    if args.pack:
        data = pack_mod.load_pack(args.pack)
        palette = [parse_hex(c) for c in data.get("palette") or []] or None
        max_colors = max_colors or int(data.get("asset_colors", 16))
        if not args.key and data.get("key"):
            key = parse_hex(data["key"])
    if args.palette:
        palette = color.load_palette(args.palette)
    cap = max_colors or 16
    img = pixelize.remove_background(load_rgba(args.raw), args.bg, key, args.tol)
    ih, iw = img.shape[:2]
    yspans = [_cell_span(ih, args.rows, r) for r in range(args.rows)]
    xspans = [_cell_span(iw, args.cols, c) for c in range(args.cols)]
    if args.layout == "whitespace":
        occupied = img[..., 3] > 0
        yspans = _whitespace_spans(occupied.any(axis=1), args.rows, "row")
        xspans = _whitespace_spans(occupied.any(axis=0), args.cols, "column")
    entries: List[Dict[str, Any]] = []
    for r, (y0, y1) in enumerate(yspans):
        for c, (x0, x1) in enumerate(xspans):
            cell = img[y0:y1, x0:x1]
            ch, cw = cell.shape[:2]
            box = pixelize.subject_bbox(cell[..., 3])
            meta: Dict[str, Any] = {
                "row": r,
                "col": c,
                "file": "r%dc%d.png" % (r, c),
                "cell_bounds": [x0, y0, x1, y1],
                "empty": box is None,
                "source_edge_touch": False,
                "paste_clamped": False,
                "bbox": None,
                "bbox_height": 0,
                "bottom_y": 0,
                "grid": [0, 0],
            }
            if box is not None:
                bx0, by0, bx1, by1 = box
                meta.update(
                    bbox=[bx0, by0, bx1, by1],
                    bbox_height=int(by1 - by0),
                    bottom_y=int(by1),
                    source_edge_touch=bool(bx0 <= 1 or by0 <= 1 or cw - bx1 <= 1 or ch - by1 <= 1),
                )
            entries.append({"meta": meta, "cell": cell, "box": box, "cw": cw})
    heights = [e["meta"]["bbox_height"] for e in entries if e["box"] is not None]
    if args.profile:
        profile = read_json(args.profile)
        if "pitch" not in profile:
            raise P2DError("profile %s has no pitch" % args.profile)
        pitch = float(profile["pitch"])
    elif heights:
        pitch = float(np.median(heights)) / subject_height
    else:
        raise P2DError("no subject found in any cell of %s" % args.raw)
    if pitch < 1:
        raise P2DError("shared pitch %.3f is below one raw pixel; lower --subject-height" % pitch)
    canvases: List[Arr] = []
    for entry in entries:
        meta, cell, box = entry["meta"], entry["cell"], entry["box"]
        canvas = np.zeros((fh, fw, 4), dtype=np.uint8)
        if box is not None:
            bx0, by0, bx1, by1 = box
            # ceil of bh/pitch with an epsilon so the median frame is not 1 row too tall
            gcols = int(math.ceil((bx1 - bx0) / pitch - 1e-9))
            grows = int(math.ceil((by1 - by0) / pitch - 1e-9))
            ox, oy = pixelize.best_phase(cell, float(bx0), float(by0), pitch, pitch, gcols, grows, 0.5)
            grid = pixelize.trim_transparent(pixelize.sample_grid(cell, ox, oy, pitch, pitch, gcols, grows))
            gh, gw = grid.shape[:2]
            dx = int(round(((bx0 + bx1) / 2.0 - entry["cw"] / 2.0) / pitch))
            canvas, clamped = _place(grid, (fw, fh), args.anchor, dx)
            meta["paste_clamped"] = clamped
            meta["grid"] = [int(gw), int(gh)]
        canvases.append(canvas)
    chunks = _opaque_chunks(canvases)
    opaque = np.concatenate([chunk for chunk in chunks if len(chunk)]) if any(len(c) for c in chunks) else np.zeros((0, 3), np.uint8)
    if len(opaque):
        reduced = color.reduce_colors(opaque, cap, palette)
        pos = 0
        for canvas, chunk in zip(canvases, chunks):
            if len(chunk):
                canvas[canvas[..., 3] > 0, :3] = reduced[pos : pos + len(chunk)]
                pos += len(chunk)
    heights = [e["meta"]["bbox_height"] for e in entries if e["box"] is not None]
    bottoms = [e["meta"]["bottom_y"] for e in entries if e["box"] is not None]
    scale_cv = float(np.std(heights) / np.mean(heights)) if heights else 0.0
    anchor_std = float(np.std(bottoms) / (ih / args.rows)) if bottoms else 0.0
    if args.layout == "whitespace":
        normalized_bottoms = [
            e["meta"]["bottom_y"] / (e["meta"]["cell_bounds"][3] - e["meta"]["cell_bounds"][1])
            for e in entries if e["box"] is not None
        ]
        anchor_std = float(np.std(normalized_bottoms)) if normalized_bottoms else 0.0
    empty_names = [e["meta"]["file"] for e in entries if e["meta"]["empty"]]
    touch_names = [e["meta"]["file"] for e in entries if e["meta"]["source_edge_touch"]]
    clamp_names = [e["meta"]["file"] for e in entries if e["meta"]["paste_clamped"]]
    reasons: List[str] = []
    if empty_names:
        reasons.append("%d empty frame(s): %s" % (len(empty_names), ", ".join(empty_names)))
    if touch_names:
        reasons.append("%d frame(s) touch a cell border (subject is cut): %s" % (len(touch_names), ", ".join(touch_names)))
    if clamp_names:
        reasons.append("%d frame(s) did not fit and were cropped: %s" % (len(clamp_names), ", ".join(clamp_names)))
    if not args.loose:
        if scale_cv > SCALE_CV_MAX:
            reasons.append("scale_cv %.3f > %.2f (inconsistent subject size; --loose only for jump/attack actions)" % (scale_cv, SCALE_CV_MAX))
        if anchor_std > ANCHOR_STD_MAX:
            reasons.append("anchor_y_std %.3f > %.2f (feet drift between frames)" % (anchor_std, ANCHOR_STD_MAX))
    ok = not reasons
    os.makedirs(args.out, exist_ok=True)
    for entry, canvas in zip(entries, canvases):
        save_rgba(canvas, os.path.join(args.out, entry["meta"]["file"]))
    report = {
        "source": args.raw,
        "frame": [fw, fh],
        "rows": args.rows,
        "cols": args.cols,
        "layout": args.layout,
        "anchor": args.anchor,
        "subject_height": subject_height,
        "pitch": round(pitch, 4),
        "scale_cv": round(scale_cv, 4),
        "anchor_y_std": round(anchor_std, 4),
        "empty_frames": empty_names,
        "edge_touch_frames": touch_names,
        "clamped_frames": clamp_names,
        "result": "PASS" if ok else "FAIL",
        "frames": [e["meta"] for e in entries],
    }
    write_json(os.path.join(args.out, "frames.json"), report)
    if args.write_profile:
        write_json(
            args.write_profile,
            {
                "pitch": round(pitch, 6),
                "frame": "%dx%d" % (fw, fh),
                "anchor": args.anchor,
                "subject_height": subject_height,
                "source": args.raw,
            },
        )
    emit("FRAMES", args.rows * args.cols)
    emit("PITCH", round(pitch, 3))
    emit("SCALE_CV", round(scale_cv, 4))
    emit("ANCHOR_Y_STD", round(anchor_std, 4))
    emit("EDGE_TOUCH_FRAMES", len(touch_names))
    emit("EMPTY_FRAMES", len(empty_names))
    emit("CLAMPED_FRAMES", len(clamp_names))
    emit("OUT", args.out)
    return emit_result(ok, reasons)


def _gif_palette(colors: Arr) -> List[int]:
    flat = [0, 0, 0]
    for rgb in colors:
        flat += [int(v) for v in rgb]
    return flat + [0] * (768 - len(flat))


def cmd_gif(args: argparse.Namespace) -> int:
    if args.duration <= 0:
        raise P2DError("--duration must be positive milliseconds")
    if args.scale < 1:
        raise P2DError("--scale must be >= 1")
    sequence = parse_int_list(args.sequence) if args.sequence else list(range(len(args.frames)))
    for i in sequence:
        if not 0 <= i < len(args.frames):
            raise P2DError("sequence index %d is outside the %d given frame file(s)" % (i, len(args.frames)))
    composed = []
    for i in sequence:
        frame = load_rgba(args.frames[i])
        if args.scale > 1:
            frame = upscale(frame, args.scale)
        if args.bg != "transparent":
            fill = np.array(parse_hex(args.bg), dtype=np.uint8)
            frame = frame.copy()
            frame[..., :3] = np.where(frame[..., 3:4] > 0, frame[..., :3], fill)
            frame[..., 3] = 255
        composed.append(frame)
    shapes = {frame.shape[:2] for frame in composed}
    if len(shapes) != 1:
        raise P2DError("frame files must share one size, got %s" % sorted("%dx%d" % s for s in shapes))
    chunks = _opaque_chunks(composed)
    opaque = np.concatenate([chunk for chunk in chunks if len(chunk)]) if any(len(c) for c in chunks) else np.zeros((0, 3), np.uint8)
    pal = np.unique(color.reduce_colors(opaque, GIF_MAX_COLORS, None), axis=0) if len(opaque) else np.zeros((0, 3), np.uint8)
    flat_palette = _gif_palette(pal)
    images: List[Image.Image] = []
    for frame in composed:
        index = np.zeros(frame.shape[:2], dtype=np.uint8)
        mask = frame[..., 3] > 0
        if mask.any():
            index[mask] = (color.nearest_index(frame[mask][:, :3], pal) + 1).astype(np.uint8)
        img = Image.fromarray(index)
        img.putpalette(flat_palette)
        images.append(img)
    images[0].save(
        args.out,
        save_all=True,
        append_images=images[1:],
        duration=args.duration,
        loop=0,
        disposal=2,
        transparency=0,
    )
    emit("OUT", args.out)
    emit("FRAMES", len(sequence))
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    if name == "gif":
        parser.add_argument("frames", nargs="+", help="frame PNG files, all one logical size")
        parser.add_argument("--out", required=True)
        parser.add_argument("--duration", type=int, default=150, help="milliseconds per frame")
        parser.add_argument("--scale", type=int, default=4, help="nearest-neighbour upscale factor")
        parser.add_argument("--sequence", help="comma list of 0-based indexes into the files (default: all in order)")
        parser.add_argument("--bg", default="transparent", help="transparent or #RRGGBB")
        return cmd_gif
    parser.add_argument("raw", help="generated grid image")
    parser.add_argument("--rows", type=int, required=True, help="generation rows in the grid")
    parser.add_argument("--cols", type=int, required=True, help="generation columns in the grid")
    parser.add_argument("--layout", choices=["fixed", "whitespace"], default="fixed",
                        help="fixed equal cells (default), or unique empty separators within one quarter cell of each boundary")
    parser.add_argument("--frame", required=True, help="logical frame size WxH, e.g. 24x32")
    parser.add_argument("--out", required=True, help="output dir for r{row}c{col}.png and frames.json")
    parser.add_argument("--anchor", choices=["feet", "center"], default="feet", help="vertical anchoring of the subject")
    parser.add_argument("--subject-height", type=int, default=None, help="subject height in frame px (default: frame height - 2)")
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("--write-profile", help="write the shared pitch profile JSON for later runs")
    profile.add_argument("--profile", help="reuse the shared pitch from a profile JSON")
    parser.add_argument("--pack", help="pack dir: palette, asset color cap and key")
    parser.add_argument("--palette", help="palette .hex file or preset name (overrides the pack palette)")
    parser.add_argument("--max-colors", type=int, default=None, help="color cap (default: pack asset_colors or 16)")
    parser.add_argument("--bg", choices=["key", "alpha"], default="key", help="background the generation was asked for")
    parser.add_argument("--key", default=None, help="key color, default #ff00ff or the pack key")
    parser.add_argument("--tol", type=float, default=pixelize.DEFAULT_TOL, help="key distance tolerance")
    parser.add_argument("--loose", action="store_true", help="do not fail on scale_cv/anchor_y_std (jump/attack actions)")
    return cmd_frames
