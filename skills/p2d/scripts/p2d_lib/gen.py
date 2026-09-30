"""Generate a reserved raw without changing the pack's attempt ledger."""
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

from .imageio import P2DError, emit, emit_result, parse_size, read_json, write_json


def cmd_gen(args: argparse.Namespace) -> int:
    directory = Path(args.dir).absolute()
    data = read_json(str(directory / "pack.json"))
    attempts = data.get("assets", {}).get(args.name, {}).get("sizes", {}).get(
        str(args.px), {}
    ).get("attempts", [])
    attempt = None
    prefix = None
    for candidate in reversed(attempts):
        prefix = Path(candidate["output_prefix"])
        if not prefix.is_absolute():
            prefix = directory / prefix
        if not Path(str(prefix) + ".png").exists():
            attempt = candidate
            break
    if attempt is None or prefix is None:
        raise P2DError("no reserved attempt without a raw for %s@%d" % (args.name, args.px))

    raw = Path(str(prefix) + ".png")
    marker = str(prefix) + ".gen.json"
    failed = str(prefix) + ".failed.json"
    failures = read_json(failed).get("failures", 1) if Path(failed).exists() else 0
    if failures >= 5:
        raise P2DError("five failures for this attempt; report the outage before generating again")
    if args.timeout <= 0:
        raise P2DError("--timeout must be positive")
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
        failures += 1
        # Keep partial candidates, but free the reserved raw path for a retry.
        if raw.exists():
            raw.rename(str(prefix) + ".failed-%d.png" % failures)
        write_json(failed, {"error": str(exc), "exit_code": exit_code, "failures": failures})
        emit("ERROR", str(exc))
        emit("MARKER", failed)
        return emit_result(False)
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
    return cmd_gen
