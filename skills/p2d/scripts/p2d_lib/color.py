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


def _merge_least_used(colors: Arr, indices: Arr, palette: Arr, cap: int) -> Tuple[Arr, Arr]:
    counts = np.bincount(indices, minlength=len(palette))
    alive = [i for i in range(len(palette)) if counts[i] > 0]
    while len(alive) > cap:
        victim = min(alive, key=lambda i: counts[i])
        rest = [i for i in alive if i != victim]
        target = rest[int(redmean_distance(palette[[victim]], palette[rest]).argmin())]
        indices[indices == victim] = target
        counts[target] += counts[victim]
        counts[victim] = 0
        alive = rest
    remap = {old: new for new, old in enumerate(alive)}
    new_indices = np.array([remap[int(i)] for i in indices], dtype=np.int64)
    return palette[alive], new_indices


def reduce_colors(colors: Arr, max_colors: int, palette: Optional[Sequence[RGB]] = None) -> Arr:
    if max_colors < 1:
        raise P2DError("max colors must be >= 1")
    colors = np.asarray(colors, dtype=np.uint8).reshape(-1, 3)
    if len(colors) == 0:
        return colors
    if palette:
        pal = np.array(palette, dtype=np.uint8)
        idx = nearest_index(colors, pal)
    else:
        unique = np.unique(colors, axis=0)
        pal = unique if len(unique) <= max_colors else _cluster(colors)
        idx = nearest_index(colors, pal)
    pal, idx = _merge_least_used(colors, idx, pal, max_colors)
    return pal[idx]


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
