"""Generate one raw per reservation, including a fresh reservation on retry."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time
from typing import Callable

from PIL import Image

from . import pack
from .imageio import P2DError, emit, emit_result, parse_size, read_json, write_json


def cmd_gen(args: argparse.Namespace) -> int:
    if args.max_calls <= 0:
        raise P2DError("--max-calls must be positive")
    if args.timeout <= 0:
        raise P2DError("--timeout must be positive")
    directory = Path(args.dir).absolute()
    data = pack.load_pack(str(directory))
    entry = data.get("assets", {}).get(args.name, {}).get("sizes", {}).get(
        str(args.px), {}
    )
    attempts = entry.get("attempts", [])
    if entry.get("accepted"):
        raise P2DError("%s@%d is already accepted" % (args.name, args.px))
    for candidate in attempts:
        prefix = candidate["output_prefix"]
        failed = prefix + ".failed.json"
        if Path(failed).exists():
            candidate.setdefault("runtime_calls", read_json(failed).get("failures", 1))
            candidate["status"] = "failed"
        else:
            candidate.setdefault("runtime_calls", int(
                candidate["status"] != "reserved" or Path(prefix + ".gen.json").exists()))
    calls = sum(candidate["runtime_calls"] for candidate in attempts)
    if calls >= args.max_calls:
        raise P2DError("generation call limit reached (%d) for %s@%d; stop and report the outage "
                       "or use --max-calls N only with explicit user consent"
                       % (args.max_calls, args.name, args.px))
    attempt = next((candidate for candidate in reversed(attempts)
                    if candidate["status"] == "reserved" and not candidate["runtime_calls"]
                    and not pack.candidates({"attempts": [candidate]})), None)
    if attempt is None and attempts and attempts[-1]["status"] == "failed":
        number = len(attempts) + 1
        attempt = {key: value for key, value in attempts[-1].items()
                   if key not in ("attempt", "output_prefix", "status", "runtime_calls", "raw_sha256")}
        attempt.update(attempt=number, output_prefix=pack.attempt_prefix(
            str(directory), args.name, args.px, number), status="reserved", runtime_calls=0)
        attempts.append(attempt)
        pack.save_pack(str(directory), data)
        emit("ATTEMPT", number)
    if attempt is None:
        raise P2DError("no reserved attempt without a raw for %s@%d" % (args.name, args.px))

    prefix = Path(attempt["output_prefix"])
    raw = Path(str(prefix) + ".png")
    marker = str(prefix) + ".gen.json"
    failed = str(prefix) + ".failed.json"
    size = args.size
    if size == "auto":
        w, h = parse_size(attempt.get("size") or "1x1")
        size = "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    exit_code = -1
    try:
        if args.prompt_file:
            prompt_file = Path(args.prompt_file).absolute()
            prompt = prompt_file.read_text(encoding="utf-8")
        else:
            prompt = attempt.get("prompt") or ""
            prompt_file = Path(str(prefix) + ".prompt.txt")
            prompt_file.write_text(prompt, encoding="utf-8")
        if not prompt.strip():
            raise P2DError("provide --prompt-file or a stored attempt prompt")
        runtime = str(Path(__file__).resolve().parents[1] / "gen_image.mjs")
        command = shlex.split(args.runner) if args.runner else [
            "bun" if shutil.which("bun") else "node", runtime
        ]
        command += ["--prompt-file", str(prompt_file), "--out", str(raw),
                    "--size", size, "--quality", args.quality]
        for ref in args.ref:
            command += ["--ref", ref]
        if args.mask:
            command += ["--mask", args.mask]
        attempt["status"] = "generating"
        attempt["runtime_calls"] = 1
        pack.save_pack(str(directory), data)
        proc = subprocess.run(command, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=args.timeout)
        exit_code = proc.returncode
        if exit_code:
            raise P2DError(proc.stderr.strip() or proc.stdout.strip() or
                           "runtime exited with code %d" % exit_code)
        result = json.loads(proc.stdout)
        if not isinstance(result, dict):
            raise P2DError("runtime stdout must be a JSON object")
        with Image.open(raw) as image:
            if image.format != "PNG":
                raise P2DError("runtime output must be a PNG")
            image.load()
            actual_size = "%dx%d" % image.size
        write_json(marker, {
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "size": actual_size,
            "elapsed_s": time.monotonic() - started,
            "prompt_file": str(prompt_file),
            "refs": args.ref,
            "runtime": result,
        })
    except (OSError, ValueError, P2DError, subprocess.TimeoutExpired) as exc:
        # Keep partial candidates and markers; retries use a new reservation.
        if raw.exists():
            raw.rename(str(prefix) + ".failed-1.png")
        write_json(failed, {"error": str(exc), "exit_code": exit_code, "failures": 1})
        attempt["status"] = "failed"
        pack.save_pack(str(directory), data)
        emit("ERROR", str(exc))
        emit("MARKER", failed)
        return emit_result(False)
    attempt["status"] = "generated"
    attempt["raw_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
    pack.save_pack(str(directory), data)
    emit("RAW", str(raw))
    emit("MARKER", marker)
    return emit_result(True)


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("dir")
    parser.add_argument("--name", required=True)
    parser.add_argument("--px", type=int, required=True)
    parser.add_argument("--prompt-file")
    parser.add_argument("--size", choices=["auto", "1024x1024", "1536x1024", "1024x1536"],
                        default="auto")
    parser.add_argument("--ref", nargs="+", action="extend", default=[])
    parser.add_argument("--mask")
    parser.add_argument("--quality", choices=["high"], default="high")
    parser.add_argument("--runner", help="override runtime command (e.g. a test stub)")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-calls", type=int, default=pack.MAX_ATTEMPTS,
                        help="call cap per asset/px (default 3); raising it requires explicit user consent")
    return cmd_gen
