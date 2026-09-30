from __future__ import annotations

import argparse
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from . import color
from .imageio import (
    MAGENTA,
    Arr,
    P2DError,
    emit,
    emit_result,
    load_rgba,
    parse_hex,
    parse_size,
    save_rgba,
    scaled_path,
    upscale,
)

KINDS = ("tile", "wall", "trim", "prop")
SURFACE_KINDS = ("tile", "wall", "trim")
DEFAULT_TOL = 120.0


def key_mask(rgba: Arr, key: Tuple[int, int, int] = MAGENTA, tol: float = DEFAULT_TOL) -> Arr:
    rgb = rgba[..., :3].reshape(-1, 3)
    dist = color.redmean_distance(rgb, np.array([key], dtype=np.uint8))[:, 0].reshape(rgba.shape[:2])
    mask = dist <= tol
    if tuple(key) == MAGENTA:
        r = rgba[..., 0].astype(np.int32)
        g = rgba[..., 1].astype(np.int32)
        b = rgba[..., 2].astype(np.int32)
        mask |= (r >= 120) & (b >= 120) & (g <= r - 70) & (g <= b - 70) & (np.abs(r - b) <= 100)
    return mask


def remove_background(rgba: Arr, mode: str, key: Tuple[int, int, int] = MAGENTA, tol: float = DEFAULT_TOL) -> Arr:
    out = rgba.copy()
    if mode == "none":
        out[..., 3] = 255
    elif mode == "alpha":
        out[..., 3] = np.where(rgba[..., 3] >= 128, 255, 0)
    elif mode == "key":
        transparent = key_mask(rgba, key, tol) | (rgba[..., 3] < 128)
        out[..., 3] = np.where(transparent, 0, 255)
    else:
        raise P2DError("unknown background mode %r (key, alpha, none)" % mode)
    return out


def subject_bbox(alpha: Arr) -> Optional[Tuple[int, int, int, int]]:
    ys, xs = np.nonzero(alpha > 0)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _integral(values: Arr) -> Arr:
    s = np.zeros((values.shape[0] + 1, values.shape[1] + 1), dtype=np.float64)
    s[1:, 1:] = values.cumsum(axis=0).cumsum(axis=1)
    return s


def _boxes(origin: float, pitch: float, count: int, limit: int, inner: float) -> Tuple[Arr, Arr]:
    start = origin + (np.arange(count) + (1 - inner) / 2) * pitch
    end = start + pitch * inner
    lo = np.clip(np.floor(start).astype(np.int64), 0, limit - 1)
    hi = np.clip(np.ceil(end).astype(np.int64), 1, limit)
    hi = np.maximum(hi, lo + 1)
    return lo, hi


def _box_sum(s: Arr, x0: Arr, x1: Arr, y0: Arr, y1: Arr) -> Arr:
    return s[y1][:, x1] - s[y0][:, x1] - s[y1][:, x0] + s[y0][:, x0]


def _grid_cost(lum_s: Arr, lum2_s: Arr, xs: Tuple[Arr, Arr], ys: Tuple[Arr, Arr]) -> float:
    area = (ys[1] - ys[0])[:, None] * (xs[1] - xs[0])[None, :]
    mean = _box_sum(lum_s, xs[0], xs[1], ys[0], ys[1]) / area
    mean2 = _box_sum(lum2_s, xs[0], xs[1], ys[0], ys[1]) / area
    return float(np.maximum(mean2 - mean * mean, 0).mean())


def best_phase(rgba: Arr, ox: float, oy: float, px: float, py: float, cols: int, rows: int, spread: float) -> Tuple[float, float]:
    lum = rgba[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    lum = np.where(rgba[..., 3] > 0, lum, 0.0)
    lum_s, lum2_s = _integral(lum), _integral(lum * lum)
    h, w = lum.shape
    best = (float("inf"), ox, oy)
    for dx in np.linspace(-spread * px, spread * px, 9):
        xs = _boxes(ox + dx, px, cols, w, 0.6)
        for dy in np.linspace(-spread * py, spread * py, 9):
            ys = _boxes(oy + dy, py, rows, h, 0.6)
            cost = _grid_cost(lum_s, lum2_s, xs, ys)
            if cost < best[0] - 1e-9:
                best = (cost, ox + dx, oy + dy)
    return best[1], best[2]


def _dominant(pixels: Arr) -> Arr:
    buckets = (pixels[:, 0].astype(np.int64) >> 3) << 10 | (pixels[:, 1].astype(np.int64) >> 3) << 5 | (pixels[:, 2].astype(np.int64) >> 3)
    values, counts = np.unique(buckets, return_counts=True)
    winner = values[counts.argmax()]
    return pixels[buckets == winner].mean(axis=0)


def sample_grid(rgba: Arr, ox: float, oy: float, px: float, py: float, cols: int, rows: int) -> Arr:
    h, w = rgba.shape[:2]
    inner = 0.6 if min(px, py) >= 3 else 1.0
    x0, x1 = _boxes(ox, px, cols, w, inner)
    y0, y1 = _boxes(oy, py, rows, h, inner)
    out = np.zeros((rows, cols, 4), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            cell = rgba[y0[r] : y1[r], x0[c] : x1[c]].reshape(-1, 4)
            opaque = cell[cell[:, 3] > 0]
            if len(opaque) * 2 <= len(cell):
                continue
            out[r, c, :3] = np.clip(np.round(_dominant(opaque[:, :3])), 0, 255)
            out[r, c, 3] = 255
    return out


def trim_transparent(grid: Arr) -> Arr:
    box = subject_bbox(grid[..., 3])
    if box is None:
        return grid[:0, :0]
    x0, y0, x1, y1 = box
    return grid[y0:y1, x0:x1]


def despeckle(rgba: Arr) -> Arr:
    out = rgba.copy()
    h, w = rgba.shape[:2]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if rgba[y, x, 3] == 0:
                continue
            neighbours = [rgba[y - 1, x], rgba[y + 1, x], rgba[y, x - 1], rgba[y, x + 1]]
            if any(n[3] == 0 for n in neighbours):
                continue
            first = neighbours[0][:3]
            if all((n[:3] == first).all() for n in neighbours) and not (rgba[y, x, :3] == first).all():
                out[y, x, :3] = first
    return out


def apply_palette(rgba: Arr, max_colors: int, palette: Optional[Sequence[Tuple[int, int, int]]]) -> Arr:
    out = rgba.copy()
    mask = out[..., 3] > 0
    if mask.any():
        out[mask, :3] = color.reduce_colors(out[mask, :3], max_colors, palette)
    out[..., 3] = np.where(mask, 255, 0)
    return out


def place(grid: Arr, size: Tuple[int, int], anchor: str) -> Arr:
    w, h = size
    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    gh, gw = grid.shape[:2]
    x = (w - gw) // 2
    y = h - gh if anchor == "bottom" else (h - gh) // 2
    canvas[y : y + gh, x : x + gw] = grid
    return canvas


def pixelize_image(
    rgba: Arr,
    kind: str,
    size: Tuple[int, int],
    palette: Optional[Sequence[Tuple[int, int, int]]] = None,
    max_colors: int = 16,
    bg: Optional[str] = None,
    key: Tuple[int, int, int] = MAGENTA,
    tol: float = DEFAULT_TOL,
    anchor: str = "bottom",
    margin: int = 0,
    do_despeckle: bool = False,
) -> Tuple[Arr, Dict[str, Any]]:
    if kind not in KINDS:
        raise P2DError("unknown kind %r (%s)" % (kind, ", ".join(KINDS)))
    if anchor not in ("bottom", "center"):
        raise P2DError("anchor must be bottom or center")
    w, h = size
    mode = bg or ("none" if kind in SURFACE_KINDS else "key")
    img = remove_background(rgba, mode, key, tol)
    ih, iw = img.shape[:2]
    info: Dict[str, Any] = {"background": mode}
    if kind in SURFACE_KINDS:
        px, py = iw / w, ih / h
        ox, oy = best_phase(img, 0.0, 0.0, px, py, w, h, 0.25)
        out = sample_grid(img, ox, oy, px, py, w, h)
        info.update(pitch=[round(px, 3), round(py, 3)], phase=[round(ox, 2), round(oy, 2)], subject=[w, h])
    else:
        box = subject_bbox(img[..., 3])
        if box is None:
            raise P2DError("no subject found after removing the %s background" % mode)
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        avail_w = w - 2 * margin
        avail_h = h - (margin if anchor == "bottom" else 2 * margin)
        if avail_w < 1 or avail_h < 1:
            raise P2DError("margin %d leaves no room in %dx%d" % (margin, w, h))
        pitch = max(bw / avail_w, bh / avail_h)
        cols = int(min(avail_w, max(1, round(bw / pitch))))
        rows = int(min(avail_h, max(1, round(bh / pitch))))
        ox = (x0 + x1) / 2 - cols * pitch / 2
        oy = y1 - rows * pitch if anchor == "bottom" else (y0 + y1) / 2 - rows * pitch / 2
        ox, oy = best_phase(img, ox, oy, pitch, pitch, cols, rows, 0.5)
        grid = trim_transparent(sample_grid(img, ox, oy, pitch, pitch, cols, rows))
        if grid.size == 0:
            raise P2DError("subject vanished while sampling; check the background mode")
        out = place(grid, size, anchor)
        info.update(pitch=[round(pitch, 3), round(pitch, 3)], phase=[round(ox, 2), round(oy, 2)], subject=[int(grid.shape[1]), int(grid.shape[0])])
    if do_despeckle:
        out = despeckle(out)
    out = apply_palette(out, max_colors, palette)
    info["colors"] = color.count_colors(out)
    return out, info


def detect_pitch(rgba: Arr, max_pitch: int = 64) -> int:
    def change_positions(axis: int) -> Arr:
        diff = np.any(np.diff(rgba.astype(np.int16), axis=axis) != 0, axis=2)
        return diff.sum(axis=1 - axis)

    best = 1
    col_changes = change_positions(1)
    row_changes = change_positions(0)
    if col_changes.sum() == 0 and row_changes.sum() == 0:
        return 1
    for p in range(2, max_pitch + 1):
        ok = True
        for changes in (col_changes, row_changes):
            total = changes.sum()
            if total == 0:
                continue
            positions = np.arange(1, len(changes) + 1)
            aligned = max(changes[(positions - phase) % p == 0].sum() for phase in range(p))
            if aligned / total < 0.98:
                ok = False
                break
        if ok:
            best = p
    return best


def is_checkerboard(rgba: Arr) -> bool:
    h, w = rgba.shape[:2]
    band = max(4, min(h, w) // 10)
    strips = [rgba[:band], rgba[-band:], rgba[:, :band].transpose(1, 0, 2), rgba[:, -band:].transpose(1, 0, 2)]
    grays = 0
    total = 0
    transitions = []
    for strip in strips:
        rgb = strip[..., :3].astype(np.int32)
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        lum = rgb.mean(axis=2)
        gray = (sat < 18) & (lum > 140)
        grays += int(gray.sum())
        total += gray.size
        row = lum[band // 2]
        if gray[band // 2].mean() > 0.8:
            lo, hi = row.min(), row.max()
            if hi - lo >= 12:
                level = row > (lo + hi) / 2
                transitions.append(int(np.count_nonzero(level[1:] != level[:-1])))
    if total == 0 or grays / total < 0.8 or not transitions:
        return False
    return min(transitions) >= 4


RPG_MAKER_SHEETS = {
    (288, 256): (16, "RPG Maker 2000/2003 CharSet (8 characters)"),
    (72, 128): (16, "RPG Maker 2000/2003 single character"),
    (24, 32): (16, "RPG Maker 2000/2003 single frame"),
    (384, 256): (32, "RPG Maker VX/VX Ace 8-character sheet"),
    (96, 128): (32, "RPG Maker VX/VX Ace $ single character"),
    (576, 384): (48, "RPG Maker MV/MZ 8-character sheet"),
    (144, 192): (48, "RPG Maker MV/MZ $ single character"),
}


def suggest_px(lw: int, lh: int) -> Tuple[Optional[int], str]:
    if (lw, lh) in RPG_MAKER_SHEETS:
        return RPG_MAKER_SHEETS[(lw, lh)]
    for p in (48, 32, 16):
        if lw % p == 0 and lh % p == 0 and min(lw, lh) == p:
            return p, "one tile unit"
    for p in (16, 32, 48):
        if lw % p == 0 and lh % p == 0:
            return p, "multiple of the tile unit"
    return None, "not a multiple of 16, 32 or 48"


def _key_residue(rgba: Arr, key: Tuple[int, int, int]) -> float:
    opaque = rgba[..., 3] > 0
    if not opaque.any():
        return 0.0
    return float((key_mask(rgba, key) & opaque).sum() / opaque.sum())


def cmd_inspect(args: argparse.Namespace) -> int:
    with Image.open(args.image) as img:
        mode = img.mode
    rgba = load_rgba(args.image)
    h, w = rgba.shape[:2]
    pitch = detect_pitch(rgba)
    emit("SIZE", "%dx%d" % (w, h))
    emit("MODE", mode)
    emit("COLORS", color.count_colors(rgba))
    emit("TRANSPARENT_PERCENT", round(float((rgba[..., 3] == 0).mean() * 100), 2))
    emit("PITCH", pitch)
    if pitch > 1 or color.count_colors(rgba) <= 256:
        lw, lh = w // pitch, h // pitch
        emit("LOGICAL_SIZE", "%dx%d" % (lw, lh))
        px, why = suggest_px(lw, lh)
        emit("SUGGESTED_PX", px if px else "none")
        emit("PX_REASON", why)
    else:
        emit("LOGICAL_SIZE", "unknown (not pixel aligned; looks like a raw generation)")
        emit("SUGGESTED_PX", "none")
    emit("CHECKERBOARD", "yes" if is_checkerboard(rgba) else "no")
    emit("KEY_RESIDUE_PERCENT", round(_key_residue(rgba, parse_hex(args.key)) * 100, 2))
    return 0


def cmd_raw_check(args: argparse.Namespace) -> int:
    with Image.open(args.image) as img:
        has_alpha = "A" in img.getbands() or "transparency" in img.info
    rgba = load_rgba(args.image)
    key = parse_hex(args.key)
    checker = is_checkerboard(rgba)
    reasons: List[str] = []
    emit("CHECKERBOARD_DETECTED", "yes" if checker else "no")
    if checker:
        reasons.append("painted checkerboard instead of a real background")
    if args.bg == "alpha":
        transparent = float((rgba[..., 3] < 128).mean() * 100)
        emit("ALPHA_CHANNEL", "yes" if has_alpha else "no")
        emit("TRANSPARENT_PERCENT", round(transparent, 2))
        if not has_alpha or transparent < 10:
            reasons.append("needs a real alpha channel with at least 10% transparent pixels")
    elif args.bg == "key":
        mask = key_mask(rgba, key)
        h, w = mask.shape
        band = max(2, min(h, w) // 50)
        border = np.concatenate([mask[:band].ravel(), mask[-band:].ravel(), mask[:, :band].ravel(), mask[:, -band:].ravel()])
        emit("KEY_COVERAGE_PERCENT", round(float(mask.mean() * 100), 2))
        emit("KEY_BORDER_PERCENT", round(float(border.mean() * 100), 2))
        if mask.mean() < 0.10 or border.mean() < 0.90:
            reasons.append("background must be flat key color (>=10% of pixels, >=90% of the border)")
    else:
        transparent = float((rgba[..., 3] < 255).mean() * 100)
        emit("TRANSPARENT_PERCENT", round(transparent, 2))
        if transparent > 0:
            reasons.append("an opaque surface raw has transparent pixels; regenerate with an opaque, fully painted field")
    return emit_result(not reasons, reasons)


def cmd_pixelize(args: argparse.Namespace) -> int:
    from . import pack as pack_mod

    size = parse_size(args.size)
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
    rgba = load_rgba(args.image)
    out, info = pixelize_image(
        rgba,
        args.kind,
        size,
        palette=palette,
        max_colors=max_colors or 16,
        bg=args.bg,
        key=key,
        tol=args.tol,
        anchor=args.anchor,
        margin=args.margin,
        do_despeckle=args.despeckle,
    )
    save_rgba(out, args.out)
    emit("OUT", args.out)
    emit("SIZE", "%dx%d" % size)
    emit("BACKGROUND", info["background"])
    emit("PITCH", "%sx%s" % tuple(info["pitch"]))
    emit("SUBJECT", "%dx%d" % tuple(info["subject"]))
    emit("COLORS", info["colors"])
    emit("PALETTE", "pack/palette file" if palette else "median-cut")
    if args.scale:
        preview = scaled_path(args.out, args.scale)
        save_rgba(upscale(out, args.scale), preview)
        emit("PREVIEW", preview)
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    if name == "inspect":
        parser.add_argument("image")
        parser.add_argument("--key", default="#ff00ff", help="key color for residue report")
        return cmd_inspect
    if name == "raw-check":
        parser.add_argument("image")
        parser.add_argument("--bg", choices=["key", "alpha", "none"], default="key", help="background the generation was asked for")
        parser.add_argument("--key", default="#ff00ff")
        return cmd_raw_check
    parser.add_argument("image", help="generated image (any size)")
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--size", required=True, help="logical output size WxH, e.g. 16x16 or 16x48")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pack", help="pack dir: uses its palette, asset color cap and key")
    parser.add_argument("--palette", help="palette .hex file or preset name (overrides pack palette)")
    parser.add_argument("--max-colors", type=int, default=None, help="color cap (default: pack asset_colors or 16)")
    parser.add_argument("--bg", choices=["key", "alpha", "none"], default=None, help="default: none for tile/wall/trim, key for prop")
    parser.add_argument("--key", default=None, help="key color, default #ff00ff or the pack key")
    parser.add_argument("--tol", type=float, default=DEFAULT_TOL, help="key distance tolerance")
    parser.add_argument("--anchor", choices=["bottom", "center"], default="bottom", help="prop placement")
    parser.add_argument("--margin", type=int, default=0, help="empty logical pixels kept around a prop")
    parser.add_argument("--despeckle", action="store_true", help="remove isolated single pixels")
    parser.add_argument("--scale", type=int, default=0, help="also write NAME@Kx.png nearest-neighbour preview")
    return cmd_pixelize
