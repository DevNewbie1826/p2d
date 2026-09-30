from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from .imageio import Arr, P2DError, parse_hex, to_hex

RGB = Tuple[int, int, int]
PALETTE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "palettes")


def redmean_distance(a: Arr, b: Arr) -> Arr:
    """Perceptual RGB distance ("redmean" approximation); a is Nx3, b is Mx3, result NxM."""
    a = a.astype(np.float64)[:, None, :]
    b = b.astype(np.float64)[None, :, :]
    rmean = (a[..., 0] + b[..., 0]) / 2.0
    d = a - b
    return np.sqrt((2 + rmean / 256.0) * d[..., 0] ** 2 + 4 * d[..., 1] ** 2 + (2 + (255 - rmean) / 256.0) * d[..., 2] ** 2)


def nearest_index(colors: Arr, palette: Arr) -> Arr:
    if len(colors) == 0:
        return np.zeros((0,), dtype=np.int64)
    out = np.empty(len(colors), dtype=np.int64)
    step = 4096
    for start in range(0, len(colors), step):
        out[start : start + step] = redmean_distance(colors[start : start + step], palette).argmin(axis=1)
    return out


def _cluster(colors: Arr, threshold: float = 36.0) -> Arr:
    colors = np.asarray(colors, dtype=np.uint8).reshape(-1, 3)
    if len(colors) > 20000:
        colors = ((colors.astype(np.int64) >> 3) << 3 | 4).astype(np.uint8)
    unique, counts = np.unique(colors, axis=0, return_counts=True)
    order = np.argsort(-counts, kind="stable")
    centers: List[Arr] = []
    weights: List[float] = []
    for i in order:
        c = unique[i].astype(np.float64)
        if centers:
            d = redmean_distance(c[None, :], np.array(centers))[0]
            j = int(d.argmin())
            if d[j] <= threshold:
                total = weights[j] + float(counts[i])
                centers[j] = (centers[j] * weights[j] + c * counts[i]) / total
                weights[j] = total
                continue
        centers.append(c)
        weights.append(float(counts[i]))
    return np.clip(np.round(np.array(centers)), 0, 255).astype(np.uint8)


def _median_cut(colors: Arr, k: int) -> Arr:
    strip = Image.fromarray(colors.reshape(1, -1, 3).astype(np.uint8))
    quant = strip.quantize(colors=k, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = quant.getpalette() or []
    used = sorted(set(np.array(quant).ravel().tolist()))
    return np.array([raw[i * 3 : i * 3 + 3] for i in used], dtype=np.uint8)


def _merge_least_used(colors: Arr, indices: Arr, palette: Arr, cap: int,
                     protect: Sequence[RGB] = ()) -> Tuple[Arr, Arr]:
    counts = np.bincount(indices, minlength=len(palette))
    alive = [i for i in range(len(palette)) if counts[i] > 0]
    protected = set(protect)
    locked = {i for i in alive if tuple(palette[i]) in protected}
    if len(locked) > cap:
        raise P2DError("protected colours exceed --max-colors")
    while len(alive) > cap:
        victim = min((i for i in alive if i not in locked), key=lambda i: counts[i])
        rest = [i for i in alive if i != victim]
        target = rest[int(redmean_distance(palette[[victim]], palette[rest]).argmin())]
        indices[indices == victim] = target
        counts[target] += counts[victim]
        counts[victim] = 0
        alive = rest
    remap = {old: new for new, old in enumerate(alive)}
    new_indices = np.array([remap[int(i)] for i in indices], dtype=np.int64)
    return palette[alive], new_indices


def reduce_colors(colors: Arr, max_colors: int, palette: Optional[Sequence[RGB]] = None,
                  protect: Sequence[RGB] = ()) -> Arr:
    if max_colors < 1:
        raise P2DError("max colors must be >= 1")
    colors = np.asarray(colors, dtype=np.uint8).reshape(-1, 3)
    if len(colors) == 0:
        return colors
    protected = set(protect)
    if len(protected) > max_colors:
        raise P2DError("protected colours exceed --max-colors")
    locked = np.array(sorted(protected), dtype=np.uint8).reshape(-1, 3)
    protected_mask = np.zeros(len(colors), dtype=bool)
    for rgb in locked:
        protected_mask |= np.all(colors == rgb, axis=1)
    if palette:
        pal = np.array(palette, dtype=np.uint8)
    else:
        unique = np.unique(colors, axis=0)
        unprotected = colors[~protected_mask]
        pal = unique if len(unique) <= max_colors else (
            _cluster(unprotected) if len(unprotected) else locked)
    if len(locked):
        pal = np.unique(np.concatenate([pal, locked]), axis=0)
    idx = nearest_index(colors, pal)
    pal, idx = _merge_least_used(colors, idx, pal, max_colors, protect)
    return pal[idx]


def protected_colors_auto(rgba: Arr) -> List[RGB]:
    """Protect enclosed, four-connected color clusters of at most six pixels."""
    height, width = rgba.shape[:2]
    opaque = rgba[..., 3] > 0
    ys = np.flatnonzero(opaque.any(axis=1))
    if not len(ys):
        return []
    midpoint = (int(ys[0]) + int(ys[-1]) + 1) / 2
    luma = rgba[..., :3] @ np.array([0.299, 0.587, 0.114])
    visited = np.zeros((height, width), dtype=bool)
    protected = set()
    for y, x in np.argwhere(opaque):
        if visited[y, x]:
            continue
        rgb = rgba[y, x, :3]
        stack = [(int(y), int(x))]
        visited[y, x] = True
        cluster = []
        neighbours = set()
        enclosed = True
        while stack:
            cy, cx = stack.pop()
            cluster.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if not (0 <= ny < height and 0 <= nx < width) or not opaque[ny, nx]:
                    enclosed = False
                elif np.array_equal(rgba[ny, nx, :3], rgb):
                    if not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
                else:
                    neighbours.add((ny, nx))
        if not enclosed or len(cluster) > 6 or not neighbours:
            continue
        lum = float(luma[y, x])
        boundary = np.array([luma[ny, nx] for ny, nx in neighbours])
        eye = lum < 128 and all(cy < midpoint for cy, _ in cluster) and np.all(boundary > lum)
        contrast = np.all(np.abs(boundary - lum) >= 80)
        if eye or contrast:
            protected.add(tuple(int(c) for c in rgb))
    return sort_palette(protected)


def extract_palette(images: Iterable[Arr], max_colors: int) -> List[RGB]:
    chunks = []
    for rgba in images:
        opaque = rgba[rgba[..., 3] >= 128][:, :3]
        if len(opaque):
            chunks.append(opaque)
    if not chunks:
        raise P2DError("no opaque pixels to extract a palette from")
    colors = np.concatenate(chunks).astype(np.uint8)
    unique, counts = np.unique(colors, axis=0, return_counts=True)
    if len(unique) > max_colors:
        pal = _cluster(colors)
        pal, _ = _merge_least_used(colors, nearest_index(colors, pal), pal, max_colors)
        unique = pal
    return sort_palette([(int(c[0]), int(c[1]), int(c[2])) for c in unique])


def sort_palette(colors: Iterable[RGB]) -> List[RGB]:
    return sorted(set(colors), key=lambda c: (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2], c))


def read_hex_file(path: str) -> List[RGB]:
    colors = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.split(";")[0].strip()
            if line:
                colors.append(parse_hex(line))
    if not colors:
        raise P2DError("palette file has no colors: %s" % path)
    return colors


def preset_names() -> List[str]:
    if not os.path.isdir(PALETTE_DIR):
        return []
    return sorted(name[:-4] for name in os.listdir(PALETTE_DIR) if name.endswith(".hex"))


def load_palette(spec: str) -> List[RGB]:
    if os.path.exists(spec):
        return read_hex_file(spec)
    preset = os.path.join(PALETTE_DIR, spec + ".hex")
    if os.path.exists(preset):
        return read_hex_file(preset)
    raise P2DError("unknown palette %r (file path or preset: %s)" % (spec, ", ".join(preset_names()) or "none"))


def write_hex_file(path: str, colors: Iterable[RGB]) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for c in colors:
            handle.write(to_hex(c)[1:] + "\n")
    return path


def count_colors(rgba: Arr) -> int:
    opaque = rgba[rgba[..., 3] > 0][:, :3]
    return int(len(np.unique(opaque, axis=0))) if len(opaque) else 0


def color_table(rgba: Arr) -> Dict[RGB, int]:
    opaque = rgba[rgba[..., 3] > 0][:, :3]
    if not len(opaque):
        return {}
    unique, counts = np.unique(opaque, axis=0, return_counts=True)
    return {(int(c[0]), int(c[1]), int(c[2])): int(n) for c, n in zip(unique, counts)}
