from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
from numpy.typing import NDArray
from PIL import Image

Img = NDArray[np.uint8]
Arr = NDArray[Any]

MAGENTA = (255, 0, 255)


class P2DError(Exception):
    pass


def load_rgba(path: str) -> Img:
    if not os.path.exists(path):
        raise P2DError("file not found: %s" % path)
    with Image.open(path) as img:
        return np.array(img.convert("RGBA"), dtype=np.uint8)


def save_rgba(arr: Arr, path: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8)).save(path)
    return path


def upscale(arr: Arr, factor: int) -> Arr:
    if factor < 1:
        raise P2DError("scale must be >= 1")
    return np.repeat(np.repeat(arr, factor, axis=0), factor, axis=1)


def scaled_path(path: str, factor: int) -> str:
    root, ext = os.path.splitext(path)
    return "%s@%dx%s" % (root, factor, ext or ".png")


def parse_size(text: str) -> Tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", text or "")
    if not match:
        raise P2DError("size must look like WxH, got %r" % text)
    w, h = int(match.group(1)), int(match.group(2))
    if w < 1 or h < 1:
        raise P2DError("size must be positive, got %r" % text)
    return w, h


def parse_hex(text: str) -> Tuple[int, int, int]:
    value = (text or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise P2DError("color must be #RRGGBB, got %r" % text)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def to_hex(rgb: Iterable[int]) -> str:
    r, g, b = [int(v) for v in list(rgb)[:3]]
    return "#%02x%02x%02x" % (r, g, b)


def parse_int_list(text: str) -> List[int]:
    try:
        return [int(part) for part in str(text).replace(" ", "").split(",") if part]
    except ValueError:
        raise P2DError("expected comma separated integers, got %r" % text)


def emit(key: str, value: Any) -> None:
    print("%s: %s" % (key, value))


def emit_result(ok: bool, reasons: Iterable[str] = ()) -> int:
    for reason in reasons:
        emit("FAIL_REASON", reason)
    emit("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise P2DError("file not found: %s" % path)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, data: Dict[str, Any]) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path
