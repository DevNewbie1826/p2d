from __future__ import annotations

import argparse
import copy
import hashlib
import io
import os
import re
from contextlib import redirect_stdout
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import color
from .imageio import P2DError, emit, load_rgba, parse_hex, parse_int_list, parse_size, read_json, to_hex, write_json

SUPPORTED_PX = (16, 32, 48)
MAX_ATTEMPTS = 3
GEN_MIN_PIXELS = 655360
GEN_MAX_PIXELS = 8294400
GEN_MAX_EDGE = 3840
KIND_TABLE = {
    "tile": {"pixelize_kind": "tile", "check_kind": "tile", "units": (1, 1), "anchor": "center", "margin": 0, "axis": "xy", "bg": "none"},
    "wall": {"pixelize_kind": "wall", "check_kind": "wall", "units": (1, 3), "anchor": "center", "margin": 0, "axis": "x", "bg": "none"},
    "trim": {"pixelize_kind": "trim", "check_kind": "trim", "units": (1.5, 0.5), "anchor": "center", "margin": 0, "axis": "x", "bg": "none"},
    "prop": {"pixelize_kind": "prop", "check_kind": "prop", "units": (1, 1), "anchor": "bottom", "margin": 1, "axis": "none", "bg": "key"},
    "character": {
        "pixelize_kind": "prop", "check_kind": "frame", "anchor": "bottom", "margin": 1, "axis": "none", "bg": "key",
        "formats": {
            "16": {"format": "rm2k", "frame": "24x32", "rows": "up,right,down,left", "engine": "RPG Maker 2000/2003"},
            "32": {"format": "vxace", "frame": "32x32", "rows": "down,left,right,up", "engine": "RPG Maker VX/VX Ace"},
            "48": {"format": "mv", "frame": "48x48", "rows": "down,left,right,up", "engine": "RPG Maker MV/MZ"},
        },
    },
    "animation": {"pixelize_kind": "prop", "check_kind": "frame", "units": (1, 1), "anchor": "bottom", "margin": 1, "axis": "none", "bg": "key"},
    "fx": {"pixelize_kind": "prop", "check_kind": "frame", "units": (1, 1), "anchor": "center", "margin": 1, "axis": "none", "bg": "key"},
}


def kind_spec(kind: str, px: int, block: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    validate_px([px])
    if kind not in KIND_TABLE:
        raise P2DError("unknown asset kind %r" % kind)
    spec = KIND_TABLE[kind]
    if block is not None and min(block) <= 0:
        raise P2DError("block dimensions must be positive")
    if kind == "character":
        size = spec["formats"][str(px)]["frame"]
    else:
        units = block if block is not None else spec["units"]
        size = "%dx%d" % (int(px * units[0]), int(px * units[1]))
    return {**{field: spec[field] for field in ("pixelize_kind", "check_kind", "anchor", "margin", "axis", "bg")}, "size": size}


def pack_file(directory: str) -> str:
    return os.path.join(directory, "pack.json")


def load_pack(directory: str) -> Dict[str, Any]:
    data = read_json(pack_file(directory))
    _pack_paths(data, lambda path: os.path.abspath(os.path.join(directory, path)))
    _refresh_attempts(data)
    return data


def save_pack(directory: str, data: Dict[str, Any]) -> None:
    stored = copy.deepcopy(data)
    stored["version"] = 2
    _pack_paths(stored, lambda path: os.path.relpath(os.path.realpath(path), os.path.realpath(directory)))
    write_json(pack_file(directory), stored)


def _pack_paths(data: Dict[str, Any], convert: Callable[[str], str]) -> None:
    """Convert only path-bearing fields, leaving prompts and metadata intact."""
    for asset in data.get("assets", {}).values():
        for entry in asset.get("sizes", {}).values():
            records: List[Tuple[Dict[str, Any], Tuple[str, ...]]] = [
                (attempt, ("output_prefix", "reference")) for attempt in entry.get("attempts", [])
            ]
            accepted_records = list(entry.get("history", []))
            if entry.get("accepted"):
                accepted_records.append(entry["accepted"])
            for accepted in accepted_records:
                records.append((accepted, ("file", "raw")))
                if accepted.get("face_report"):
                    records.append((accepted["face_report"], ("path",)))
            for record, fields in records:
                for field in fields:
                    if record.get(field):
                        record[field] = convert(record[field])


def _sha256(path: str) -> str:
    with open(path, "rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _refresh_attempts(data: Dict[str, Any]) -> None:
    """Discover generated raws without overriding explicit failed/rejected states."""
    for asset in data.get("assets", {}).values():
        for entry in asset.get("sizes", {}).values():
            accepted = entry.get("accepted")
            for attempt in entry.get("attempts", []):
                raws = candidates({"attempts": [attempt]})
                attempt.setdefault("status", "reserved")
                if raws and attempt["status"] == "reserved":
                    attempt["status"] = "generated"
                if raws and "raw_sha256" not in attempt:
                    attempt["raw_sha256"] = _sha256(raws[0])
                if accepted and os.path.realpath(accepted["raw"]) in [os.path.realpath(p) for p in raws]:
                    attempt["status"] = "accepted"


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
            "character": KIND_TABLE["character"]["formats"],
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
    if action == "status":
        return _status(args.dir, data)
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
    return os.path.abspath(os.path.join(directory, "raw", "%s@%d_a%d" % (name, px, number)))


def _attempt(args: argparse.Namespace, data: Dict[str, Any]) -> int:
    px = validate_px([args.px])[0]
    reference = os.path.abspath(args.reference) if args.reference else None
    if reference:
        resolved = os.path.realpath(reference)
        if not os.path.isfile(reference) or "@8x" in os.path.basename(resolved).lower() or "previews" in resolved.split(os.sep):
            raise P2DError("--reference must exist and must not be an @8x preview or a file under previews/")
    spec = kind_spec(args.kind, px, parse_size(args.block) if args.block else None)
    size = "%dx%d" % parse_size(args.size) if args.size else spec["size"]
    axis, bg = args.axis or spec["axis"], args.bg or spec["bg"]
    if args.kind == "trim" and axis == "y" and not args.size and not args.block:
        w, height = parse_size(size)
        size = "%dx%d" % (height, w)
    assets = data.setdefault("assets", {})
    asset = assets.setdefault(args.name, {"kind": args.kind, "axis": axis, "variant_of": args.variant_of, "sizes": {}})
    if asset.get("kind") != args.kind:
        raise P2DError("asset %r is a %s, not a %s" % (args.name, asset.get("kind"), args.kind))
    if args.axis and not asset.get("axis"):
        asset["axis"] = args.axis
    entry = asset.setdefault("sizes", {}).setdefault(str(px), {"attempts": [], "accepted": None})
    if entry["accepted"]:
        raise P2DError("%s@%d is already accepted (%s)" % (args.name, px, entry["accepted"]["file"]))
    lost = next((a for a in reversed(entry["attempts"]) if a["status"] == "reserved" and not candidates({"attempts": [a]})), None) if args.reuse_lost else None
    if lost is None and len(entry["attempts"]) >= MAX_ATTEMPTS:
        raise P2DError(
            "attempt limit reached (%d) for %s@%d: do not generate again; pick the best kept candidate or record a manual task"
            % (MAX_ATTEMPTS, args.name, px)
        )
    number = lost["attempt"] if lost is not None else len(entry["attempts"]) + 1
    prefix = lost["output_prefix"] if lost is not None else attempt_prefix(args.dir, args.name, px, number)
    os.makedirs(os.path.dirname(prefix), exist_ok=True)
    record = {"attempt": number, "output_prefix": prefix, "reference": reference, "prompt": args.prompt,
              "size": size, "axis": axis, "bg": bg, "status": "reserved"}
    if lost is not None:
        lost.update(record)
    else:
        entry["attempts"].append(record)
    save_pack(args.dir, data)
    emit("ASSET", args.name)
    emit("PX", px)
    emit("ATTEMPT", number)
    emit("REMAINING", MAX_ATTEMPTS - len(entry["attempts"]))
    emit("OUTPUT", prefix + ".png")
    return 0


def candidates(entry: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    for attempt in entry.get("attempts", []):
        prefix = attempt["output_prefix"]
        folder, stem = os.path.dirname(prefix), os.path.basename(prefix)
        if os.path.isdir(folder):
            found += sorted(os.path.join(folder, f) for f in os.listdir(folder)
                            if f.startswith(stem) and f.lower().endswith(".png")
                            and "@8x" not in f.lower() and os.path.isfile(os.path.join(folder, f)))
    return found


def _accept(args: argparse.Namespace, data: Dict[str, Any]) -> int:
    from . import checks, face

    px = validate_px([args.px])[0]
    entry = _asset_size_entry(data, args.name, px)
    if entry.get("accepted") and not args.replace:
        raise P2DError("%s@%d is already accepted (use --replace to overwrite)" % (args.name, px))
    raw = os.path.realpath(args.raw)
    chosen = next((a for a in entry["attempts"] if raw in [os.path.realpath(p) for p in candidates({"attempts": [a]})]), None)
    if chosen is None:
        raise P2DError("%s is not a candidate of a reserved attempt for %s@%d" % (args.raw, args.name, px))
    if not os.path.exists(args.file):
        raise P2DError("processed file not found: %s" % args.file)
    asset = data["assets"][args.name]
    kind = asset["kind"]
    spec = kind_spec(kind, px)
    size = chosen.get("size", spec["size"])
    if kind == "character":
        w, height = parse_size(kind_spec("character", px)["size"])
        allowed = tuple("%dx%d" % (w * x, height * y) for x, y in ((1, 1), (3, 4), (12, 8)))
        rgba = load_rgba(args.file)
        size = "%dx%d" % (rgba.shape[1], rgba.shape[0])
        if size not in allowed:
            raise P2DError("character at %dpx must be %s (frame, block or sheet); got %s" % (px, " or ".join(allowed), size))
    parser = argparse.ArgumentParser()
    checks.configure("check", parser)
    check_args = parser.parse_args([args.file, "--kind", spec["check_kind"], "--size", size,
                                   "--pack", args.dir, "--axis", chosen.get("axis", asset.get("axis") or spec["axis"])])
    output = io.StringIO()
    with redirect_stdout(output):
        code = checks.cmd_check(check_args)
    fields = [line.split(": ", 1) for line in output.getvalue().splitlines() if ": " in line]
    if code:
        raise P2DError("check fails: %s" % "; ".join(value for key, value in fields if key == "FAIL_REASON"))
    metric_names = {"SIZE", "COLORS", "OUT_OF_PALETTE", "ALPHA_BINARY", "KEY_RESIDUE",
                    "TRANSPARENT_PERCENT", "SEAM_X", "SEAM_Y", "EDGE_TOUCH",
                    "SINGLETON_PERCENT", "MEAN_CLUSTER", "NOISE_REVIEW"}
    accepted = {"file": os.path.abspath(args.file), "raw": raw, "sha256": _sha256(args.file),
                "qc": {"result": "PASS", "metrics": {key: value for key, value in fields if key in metric_names}}}
    if args.no_face is not None:
        if not args.no_face.strip():
            raise P2DError("--no-face needs a nonempty reason")
        accepted["no_face"] = args.no_face
    elif kind in ("character", "animation") or args.face_report:
        report_path = args.face_report
        if report_path:
            try:
                with open(report_path, encoding="utf-8") as stream:
                    report = stream.read()
            except (OSError, UnicodeError) as error:
                raise P2DError("face report cannot be read: %s" % error) from error
        else:
            output = io.StringIO()
            with redirect_stdout(output):
                code = face.cmd_face(argparse.Namespace(image=args.file, auto=True, eyes=None, skin=None,
                                                       key=None, scale=8, out=None))
            report = output.getvalue()
            if code:
                raise P2DError("face check fails (run p2d.py face ... > report.txt or use --no-face REASON): %s"
                               % report.strip())
            report_path = os.path.join(args.dir, "work", "%s@%d-face-%s.txt" % (args.name, px, accepted["sha256"]))
        lines = report.splitlines()
        crops = [line[len("CROP: "):].strip() for line in lines if line.startswith("CROP: ")]
        results = [line for line in lines if line.startswith("RESULT:")]
        stem = os.path.splitext(os.path.abspath(args.file))[0]
        if results != ["RESULT: PASS"] or len(crops) != 1 or not re.fullmatch(
                re.escape(stem) + r"-face@[1-9][0-9]*x\.png", os.path.abspath(crops[0])):
            raise P2DError("face report must contain RESULT: PASS and the default CROP for this exact file")
        if not args.face_report:
            with open(report_path, "w", encoding="utf-8") as stream:
                stream.write(report)
        accepted["face_report"] = {"path": os.path.abspath(report_path), "sha256": _sha256(report_path)}
    chosen["status"] = "accepted"
    chosen["raw_sha256"] = _sha256(raw)
    if entry.get("accepted"):
        entry.setdefault("history", []).append(copy.deepcopy(entry["accepted"]))
    entry["accepted"] = accepted
    save_pack(args.dir, data)
    emit("ACCEPTED", "%s@%d -> %s" % (args.name, px, args.file))
    emit("CANDIDATES_KEPT", len(candidates(entry)))
    return 0


def _status(directory: str, data: Dict[str, Any]) -> int:
    attention = False
    accepted_files = set()
    for name, asset in sorted(data.get("assets", {}).items()):
        for px, entry in sorted(asset.get("sizes", {}).items(), key=lambda item: int(item[0])):
            flags = []
            for attempt in entry.get("attempts", []):
                if attempt["status"] == "reserved" and not candidates({"attempts": [attempt]}):
                    flags.append("RESERVED_NO_RAW(a%d)" % attempt["attempt"])
            accepted = entry.get("accepted")
            if accepted:
                accepted_files.add(os.path.realpath(accepted["file"]))
                if not os.path.isfile(accepted["file"]):
                    flags.append("ACCEPTED_FILE_MISSING")
                elif accepted.get("sha256") and _sha256(accepted["file"]) != accepted["sha256"]:
                    flags.append("ACCEPTED_HASH_MISMATCH")
            states = ",".join("a%d=%s" % (a["attempt"], a["status"]) for a in entry.get("attempts", []))
            emit("ASSET", "%s@%s %s %s" % (name, px, states, " ".join(flags)))
            attention |= bool(flags)
    for folder, _, files in os.walk(os.path.join(directory, "assets")):
        for filename in sorted(files):
            path = os.path.join(folder, filename)
            if filename.lower().endswith(".png") and "@8x" not in filename.lower() and os.path.realpath(path) not in accepted_files:
                emit("UNTRACKED_ASSET_FILE", os.path.relpath(path, directory))
                attention = True
    for folder, subdirs, files in os.walk(directory):
        rel = os.path.relpath(folder, directory)
        if rel == ".":
            subdirs[:] = [d for d in subdirs if d not in ("assets", "raw", "work", "previews")]
        for filename in sorted(files):
            if filename.lower().endswith(".png"):
                emit("STRAY_PNG", os.path.relpath(os.path.join(folder, filename), directory).replace(os.sep, "/"))
                attention = True
    save_pack(directory, data)
    emit("RESULT", "ATTENTION" if attention else "OK")
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
    status = sub.add_parser("status", help="reconcile attempts and report missing, changed or untracked files")
    status.add_argument("dir")
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
    shape = att.add_mutually_exclusive_group()
    shape.add_argument("--size", help="logical canvas WxH")
    shape.add_argument("--block", help="canvas in tile units, e.g. 2x2")
    att.add_argument("--bg", choices=["key", "alpha", "none"], help="background mode (default from kind)")
    att.add_argument("--reuse-lost", action="store_true", help="reuse the newest reserved attempt without a raw")
    acc = sub.add_parser("accept", help="mark the chosen candidate and its processed file")
    acc.add_argument("dir")
    acc.add_argument("--name", required=True)
    acc.add_argument("--px", type=int, required=True)
    acc.add_argument("--raw", required=True, help="chosen generated file (must come from a reserved attempt)")
    acc.add_argument("--file", required=True)
    face_options = acc.add_mutually_exclusive_group()
    face_options.add_argument("--face-report", help="text output of face for this file, using its default crop path")
    face_options.add_argument("--no-face", metavar="REASON", help="record why a back view or visored helmet needs no face check")
    acc.add_argument("--replace", action="store_true", help="replace an accepted entry, keeping the previous record in history")
    return cmd_pack
