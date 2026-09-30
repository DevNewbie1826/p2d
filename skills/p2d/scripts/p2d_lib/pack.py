from __future__ import annotations

import argparse
import os
import platform
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import color
from .imageio import P2DError, emit, emit_result, load_rgba, parse_hex, parse_int_list, parse_size, read_json, to_hex, write_json

SUPPORTED_PX = (16, 32, 48)
MAX_ATTEMPTS = 3
GEN_MIN_PIXELS = 655360
GEN_MAX_PIXELS = 8294400
GEN_MAX_EDGE = 3840
CHARACTER_FORMATS = {
    "16": {"format": "rm2k", "frame": "24x32", "rows": "up,right,down,left", "engine": "RPG Maker 2000/2003"},
    "32": {"format": "vxace", "frame": "32x32", "rows": "down,left,right,up", "engine": "RPG Maker VX/VX Ace"},
    "48": {"format": "mv", "frame": "48x48", "rows": "down,left,right,up", "engine": "RPG Maker MV/MZ"},
}


def pack_file(directory: str) -> str:
    return os.path.join(directory, "pack.json")


def load_pack(directory: str) -> Dict[str, Any]:
    return read_json(pack_file(directory))


def save_pack(directory: str, data: Dict[str, Any]) -> None:
    write_json(pack_file(directory), data)


def validate_px(values: List[int]) -> List[int]:
    bad = [v for v in values if v not in SUPPORTED_PX]
    if bad or not values:
        raise P2DError("px must be one or more of 16, 32, 48 (got %s)" % (values or "nothing"))
    return sorted(set(values))


def gen_size(w: int, h: int, target: int = 1536) -> Tuple[int, int, int]:
    if max(w, h) / min(w, h) > 3.0:
        raise P2DError("aspect %dx%d exceeds 3:1; generate a shorter piece and repeat it" % (w, h))
    best: Optional[Tuple[int, int, int, int]] = None
    for s in range(1, GEN_MAX_EDGE + 1):
        gw, gh = w * s, h * s
        if max(gw, gh) > GEN_MAX_EDGE:
            break
        if gw % 16 or gh % 16 or not (GEN_MIN_PIXELS <= gw * gh <= GEN_MAX_PIXELS):
            continue
        score = abs(max(gw, gh) - target)
        if best is None or score < best[0]:
            best = (score, gw, gh, s)
    if best is None:
        raise P2DError("no valid generation size for %dx%d" % (w, h))
    return best[1], best[2], best[3]


def _asset_size_entry(data: Dict[str, Any], name: str, px: int) -> Dict[str, Any]:
    asset = data.setdefault("assets", {}).get(name)
    if asset is None:
        raise P2DError("asset %r is not in the pack; record an attempt first" % name)
    return asset.setdefault("sizes", {}).setdefault(str(px), {"attempts": [], "accepted": None})


def cmd_doctor(_: argparse.Namespace) -> int:
    reasons = []
    emit("PYTHON", platform.python_version())
    import sys

    if sys.version_info < (3, 9):
        reasons.append("python 3.9+ required")
    try:
        import PIL

        emit("PILLOW", PIL.__version__)
    except ImportError:
        reasons.append("Pillow missing: python3 -m pip install --user pillow numpy")
    try:
        import numpy

        emit("NUMPY", numpy.__version__)
    except ImportError:
        reasons.append("numpy missing: python3 -m pip install --user pillow numpy")
    return emit_result(not reasons, reasons)


def cmd_size(args: argparse.Namespace) -> int:
    w, h = parse_size(args.logical)
    gw, gh, s = gen_size(w, h, args.target)
    emit("LOGICAL", "%dx%d" % (w, h))
    emit("GEN_SIZE", "%dx%d" % (gw, gh))
    emit("PITCH", s)
    return 0


def _palette_from(args: argparse.Namespace, limit: int) -> List[str]:
    if getattr(args, "preset", None):
        colors = color.load_palette(args.preset)
    elif getattr(args, "from_images", None):
        colors = color.extract_palette([load_rgba(p) for p in args.from_images], limit)
    else:
        return []
    if len(colors) > limit:
        raise P2DError("palette has %d colors, pack limit is %d" % (len(colors), limit))
    return [to_hex(c) for c in colors]


def cmd_pack(args: argparse.Namespace) -> int:
    action = args.action
    if action == "init":
        if os.path.exists(pack_file(args.dir)) and not args.force:
            raise P2DError("pack.json already exists in %s (use --force to overwrite)" % args.dir)
        data: Dict[str, Any] = {
            "name": args.name,
            "px": validate_px(parse_int_list(args.px)) if args.px else None,
            "max_colors": args.max_colors,
            "asset_colors": args.asset_colors,
            "key": to_hex(parse_hex(args.key)),
            "palette": [],
            "style": {"view": args.view, "light": args.light, "outline": args.outline, "notes": args.notes or ""},
            "character": CHARACTER_FORMATS,
            "assets": {},
        }
        data["palette"] = _palette_from(args, args.max_colors)
        os.makedirs(args.dir, exist_ok=True)
        for sub in ("raw", "assets", "previews", "work"):
            os.makedirs(os.path.join(args.dir, sub), exist_ok=True)
        save_pack(args.dir, data)
        emit("PACK", pack_file(args.dir))
        return _show(data)
    data = load_pack(args.dir)
    if action == "show":
        return _show(data)
    if action == "set":
        if args.px:
            data["px"] = validate_px(parse_int_list(args.px))
        for field in ("light", "outline", "view", "notes"):
            value = getattr(args, field, None)
            if value:
                data["style"][field] = value
        if args.asset_colors:
            data["asset_colors"] = args.asset_colors
        save_pack(args.dir, data)
        return _show(data)
    if action == "palette":
        limit = args.max or int(data.get("max_colors", 32))
        palette = _palette_from(args, limit)
        if not palette:
            raise P2DError("give --from IMAGE... or --preset NAME")
        data["palette"] = palette
        save_pack(args.dir, data)
        emit("PALETTE_COLORS", len(palette))
        emit("PALETTE", " ".join(palette))
        return 0
    if action == "attempt":
        return _attempt(args, data)
    if action == "accept":
        return _accept(args, data)
    raise P2DError("unknown pack action %r" % action)


def attempt_prefix(directory: str, name: str, px: int, number: int) -> str:
    return os.path.join(directory, "raw", "%s@%d_a%d" % (name, px, number))


def _attempt(args: argparse.Namespace, data: Dict[str, Any]) -> int:
    px = validate_px([args.px])[0]
    assets = data.setdefault("assets", {})
    asset = assets.setdefault(args.name, {"kind": args.kind, "axis": args.axis, "variant_of": args.variant_of, "sizes": {}})
    if asset.get("kind") != args.kind:
        raise P2DError("asset %r is a %s, not a %s" % (args.name, asset.get("kind"), args.kind))
    if args.axis and not asset.get("axis"):
        asset["axis"] = args.axis
    entry = asset.setdefault("sizes", {}).setdefault(str(px), {"attempts": [], "accepted": None})
    if entry["accepted"]:
        raise P2DError("%s@%d is already accepted (%s)" % (args.name, px, entry["accepted"]["file"]))
    if len(entry["attempts"]) >= MAX_ATTEMPTS:
        raise P2DError(
            "attempt limit reached (%d) for %s@%d: do not generate again; pick the best kept candidate or record a manual task"
            % (MAX_ATTEMPTS, args.name, px)
        )
    number = len(entry["attempts"]) + 1
    prefix = attempt_prefix(args.dir, args.name, px, number)
    os.makedirs(os.path.dirname(prefix), exist_ok=True)
    entry["attempts"].append({"attempt": number, "output_prefix": prefix, "reference": args.reference, "prompt": args.prompt})
    save_pack(args.dir, data)
    emit("ASSET", args.name)
    emit("PX", px)
    emit("ATTEMPT", number)
    emit("REMAINING", MAX_ATTEMPTS - number)
    emit("OUTPUT", prefix + ".png")
    return 0


def candidates(entry: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    for attempt in entry.get("attempts", []):
        prefix = attempt["output_prefix"]
        folder, stem = os.path.dirname(prefix), os.path.basename(prefix)
        if os.path.isdir(folder):
            found += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(stem))
    return found


def _accept(args: argparse.Namespace, data: Dict[str, Any]) -> int:
    px = validate_px([args.px])[0]
    entry = _asset_size_entry(data, args.name, px)
    raw = os.path.realpath(args.raw)
    prefixes = [os.path.realpath(a["output_prefix"]) for a in entry["attempts"]]
    if not os.path.exists(raw) or not any(raw.startswith(pfx) for pfx in prefixes):
        raise P2DError("%s is not a candidate of a reserved attempt for %s@%d" % (args.raw, args.name, px))
    if not os.path.exists(args.file):
        raise P2DError("processed file not found: %s" % args.file)
    entry["accepted"] = {"file": args.file, "raw": args.raw}
    save_pack(args.dir, data)
    emit("ACCEPTED", "%s@%d -> %s" % (args.name, px, args.file))
    emit("CANDIDATES_KEPT", len(candidates(entry)))
    return 0


def _show(data: Dict[str, Any]) -> int:
    emit("NAME", data.get("name"))
    emit("PX", ",".join(str(p) for p in data["px"]) if data.get("px") else "unset")
    emit("PALETTE_COLORS", len(data.get("palette") or []))
    emit("MAX_COLORS", data.get("max_colors"))
    emit("ASSET_COLORS", data.get("asset_colors"))
    emit("KEY", data.get("key"))
    style = data.get("style") or {}
    emit("STYLE", "view=%s light=%s outline=%s" % (style.get("view"), style.get("light"), style.get("outline")))
    if style.get("notes"):
        emit("NOTES", style["notes"])
    for name, asset in (data.get("assets") or {}).items():
        sizes = []
        for px, entry in sorted(asset.get("sizes", {}).items(), key=lambda kv: int(kv[0])):
            state = "accepted" if entry.get("accepted") else "attempts=%d/%d" % (len(entry.get("attempts", [])), MAX_ATTEMPTS)
            sizes.append("%s:%s" % (px, state))
        emit("ASSET", "%s kind=%s %s" % (name, asset.get("kind"), " ".join(sizes)))
    return 0


def cmd_palette(args: argparse.Namespace) -> int:
    colors = color.extract_palette([load_rgba(p) for p in args.images], args.max)
    color.write_hex_file(args.out, colors)
    emit("OUT", args.out)
    emit("PALETTE_COLORS", len(colors))
    emit("PALETTE", " ".join(to_hex(c) for c in colors))
    return 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    if name == "doctor":
        return cmd_doctor
    if name == "size":
        parser.add_argument("logical", help="logical canvas WxH, e.g. 16x16, 16x48, 72x128")
        parser.add_argument("--target", type=int, default=1536, help="preferred longest edge (1024 for quick exploration)")
        return cmd_size
    if name == "palette":
        parser.add_argument("images", nargs="+", help="existing pixel-art images at native or integer-upscaled size")
        parser.add_argument("--max", type=int, default=32)
        parser.add_argument("--out", required=True, help="output .hex file")
        return cmd_palette
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="create DIR/pack.json and raw/ assets/ previews/ work/")
    init.add_argument("dir")
    init.add_argument("--name", required=True)
    init.add_argument("--px", help="comma list of 16,32,48; omit when the user has not said (ask first)")
    init.add_argument("--max-colors", type=int, default=32, help="pack palette size limit")
    init.add_argument("--asset-colors", type=int, default=16, help="per-asset color cap")
    init.add_argument("--key", default="#ff00ff")
    init.add_argument("--view", default="rpg-maker-3/4")
    init.add_argument("--light", default="top-left")
    init.add_argument("--outline", default="dark selective outline")
    init.add_argument("--notes")
    init.add_argument("--preset", help="start from a palette preset or .hex file")
    init.add_argument("--from", dest="from_images", nargs="+", help="extract the palette from existing project assets")
    init.add_argument("--force", action="store_true")
    show = sub.add_parser("show", help="print pack state")
    show.add_argument("dir")
    setp = sub.add_parser("set", help="update px or style fields")
    setp.add_argument("dir")
    setp.add_argument("--px")
    setp.add_argument("--light")
    setp.add_argument("--outline")
    setp.add_argument("--view")
    setp.add_argument("--notes")
    setp.add_argument("--asset-colors", type=int)
    pal = sub.add_parser("palette", help="set the pack palette")
    pal.add_argument("dir")
    pal.add_argument("--from", dest="from_images", nargs="+")
    pal.add_argument("--preset")
    pal.add_argument("--max", type=int)
    att = sub.add_parser("attempt", help="reserve a generation attempt BEFORE calling generate_image (max 3 per asset and px)")
    att.add_argument("dir")
    att.add_argument("--name", required=True)
    att.add_argument("--kind", required=True, choices=["tile", "wall", "trim", "prop", "character", "animation", "fx"])
    att.add_argument("--px", type=int, required=True)
    att.add_argument("--reference", help="accepted asset passed to generate_image as identity/style reference")
    att.add_argument("--variant-of", help="base asset name when this is a variant")
    att.add_argument("--axis", choices=["x", "y", "xy", "none"], default=None, help="repeat axis for tile/wall/trim")
    att.add_argument("--prompt", help="prompt text used (reproducibility)")
    acc = sub.add_parser("accept", help="mark the chosen candidate and its processed file")
    acc.add_argument("dir")
    acc.add_argument("--name", required=True)
    acc.add_argument("--px", type=int, required=True)
    acc.add_argument("--raw", required=True, help="chosen generated file (must come from a reserved attempt)")
    acc.add_argument("--file", required=True)
    return cmd_pack
