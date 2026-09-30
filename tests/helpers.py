from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "p2d", "scripts")
P2D = os.path.join(SCRIPTS, "p2d.py")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

DUNGEON = [
    (34, 32, 52),
    (69, 40, 60),
    (102, 57, 49),
    (143, 86, 59),
    (223, 113, 38),
    (217, 160, 102),
    (238, 195, 154),
    (105, 106, 106),
]


def native_art(w: int, h: int, colors: Sequence[Tuple[int, int, int]], seed: int = 0) -> NDArray[Any]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(colors), size=(h, w))
    pal = np.array(colors, dtype=np.uint8)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = pal[idx]
    rgba[..., 3] = 255
    return rgba


def render_generated(
    native: NDArray[Any],
    scale: int,
    noise: int = 8,
    shift: Tuple[int, int] = (0, 0),
    seed: int = 1,
) -> NDArray[Any]:
    big = np.repeat(np.repeat(native, scale, axis=0), scale, axis=1).astype(np.int16)
    if shift != (0, 0):
        big = np.roll(big, shift=(shift[1], shift[0]), axis=(0, 1))
    rng = np.random.default_rng(seed)
    big[..., :3] += rng.integers(-noise, noise + 1, size=big[..., :3].shape, dtype=np.int16)
    return np.clip(big, 0, 255).astype(np.uint8)


def on_background(
    sprite: NDArray[Any], canvas: Tuple[int, int], at: Tuple[int, int], bg: Tuple[int, int, int]
) -> NDArray[Any]:
    w, h = canvas
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = bg
    out[..., 3] = 255
    x, y = at
    sh, sw = sprite.shape[:2]
    mask = sprite[..., 3] > 0
    region = out[y : y + sh, x : x + sw]
    region[mask] = sprite[mask]
    return out


def save(arr: NDArray[Any], path: str) -> str:
    Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8)).save(path)
    return path


def load(path: str) -> NDArray[Any]:
    with Image.open(path) as img:
        return np.array(img.convert("RGBA"))


def run_cli(*args: str, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, P2D] + list(args), capture_output=True, text=True, cwd=cwd
    )
    return proc.returncode, proc.stdout, proc.stderr


def kv(stdout: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in stdout.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            out.setdefault(key.strip(), value.strip())
    return out


def tmp() -> str:
    return tempfile.mkdtemp(prefix="p2d-test-")


def unique_colors(rgba: NDArray[Any]) -> List[Tuple[int, int, int]]:
    opaque = rgba[rgba[..., 3] > 0][:, :3]
    return sorted({(int(c[0]), int(c[1]), int(c[2])) for c in opaque})
