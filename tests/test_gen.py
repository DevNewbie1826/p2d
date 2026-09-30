from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

import helpers as h


STUB = """import argparse, json
from pathlib import Path
from PIL import Image
p = argparse.ArgumentParser()
p.add_argument('--prompt-file')
p.add_argument('--out')
p.add_argument('--size')
p.add_argument('--quality')
p.add_argument('--ref', action='append', default=[])
p.add_argument('--mask')
a = p.parse_args()
Image.new('RGBA', (7, 5), 'red').save(a.out)
print(json.dumps({'path': a.out, 'size': '7x5', 'bytes': Path(a.out).stat().st_size,
                  'model': 'stub', 'auth': 'stub',
                  'prompt': Path(a.prompt_file).read_text(), 'requested_size': a.size,
                  'refs': a.ref, 'mask': a.mask, 'quality': a.quality}))
"""


class GenTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p2d-gen-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.stub = self.directory / "stub.py"
        self.stub.write_text(STUB)
        self.runner = shlex.join([sys.executable, str(self.stub)])
        self.prefix = self.directory / "raw" / "crate@16_a1"
        self.pack = {"assets": {"crate": {"sizes": {"16": {"attempts": [
            {"attempt": 1, "output_prefix": "raw/crate@16_a1", "prompt": "stored prompt"}
        ]}}}}}
        self.write_pack()

    def write_pack(self):
        (self.directory / "pack.json").write_text(json.dumps(self.pack))

    def run_gen(self, *extra):
        return h.run_cli("gen", str(self.directory), "--name", "crate", "--px", "16",
                         "--runner", self.runner, *extra)

    def marker(self, suffix=".gen.json"):
        return json.loads(Path(str(self.prefix) + suffix).read_text())

    def test_success_writes_raw_marker_and_consumes_reservation(self):
        code, out, err = self.run_gen()
        self.assertEqual(code, 0, err)
        raw = Path(str(self.prefix) + ".png")
        marker = self.marker()
        self.assertEqual(h.kv(out)["RAW"], str(raw))
        self.assertEqual(h.kv(out)["MARKER"], str(self.prefix) + ".gen.json")
        self.assertEqual(h.kv(out)["RESULT"], "PASS")
        self.assertEqual(marker["sha256"], hashlib.sha256(raw.read_bytes()).hexdigest())
        self.assertEqual(marker["size"], "7x5")
        self.assertGreaterEqual(marker["elapsed_s"], 0)
        self.assertEqual(Path(marker["prompt_file"]).read_text(), "stored prompt")
        self.assertEqual(marker["runtime"]["requested_size"], "1024x1024")
        self.assertEqual(marker["refs"], [])
        attempt = json.loads((self.directory / "pack.json").read_text())[
            "assets"]["crate"]["sizes"]["16"]["attempts"][0]
        self.assertEqual(attempt["status"], "generated")
        self.assertEqual(attempt["runtime_calls"], 1)

    def test_selects_newest_unfilled_attempt_with_absolute_prefix(self):
        attempts = self.pack["assets"]["crate"]["sizes"]["16"]["attempts"]
        second = self.directory / "raw" / "second"
        attempts.append({"attempt": 2, "output_prefix": str(second), "prompt": "second"})
        third = self.directory / "raw" / "third"
        third.parent.mkdir()
        Path(str(third) + ".png").write_bytes(b"existing")
        attempts.append({"attempt": 3, "output_prefix": str(third), "prompt": "third"})
        self.write_pack()
        code, out, err = self.run_gen()
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(out)["RAW"], str(second) + ".png")
        self.assertFalse(Path(str(self.prefix) + ".png").exists())

    def test_refuses_missing_or_already_filled_reservation(self):
        for attempts in ([], [{"output_prefix": str(self.stub)}]):
            with self.subTest(attempts=attempts):
                self.pack["assets"]["crate"]["sizes"]["16"]["attempts"] = attempts
                Path(str(self.stub) + ".png").write_bytes(b"raw")
                self.write_pack()
                code, _, err = self.run_gen()
                self.assertEqual(code, 2, err)

    def test_auto_uses_logical_aspect_and_explicit_size_overrides(self):
        attempt = self.pack["assets"]["crate"]["sizes"]["16"]["attempts"][0]
        for index, (logical, expected, extra) in enumerate((
                ("32x16", "1536x1024", ()), ("16x32", "1024x1536", ()),
                ("16x16", "1024x1024", ()), ("16x16", "1536x1024", ("--size", "1536x1024")))):
            with self.subTest(logical=logical):
                self.prefix = self.directory / "raw" / ("aspect-%d" % index)
                attempt["output_prefix"] = str(self.prefix)
                attempt["size"] = logical
                self.write_pack()
                code, _, err = self.run_gen(*extra)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.marker()["runtime"]["requested_size"], expected)

    def test_prompt_file_refs_mask_and_quality_are_forwarded(self):
        prompt = self.directory / "override.txt"
        prompt.write_text("override")
        code, _, err = self.run_gen("--prompt-file", str(prompt), "--ref", "a.png", "b.png",
                                   "--ref", "c.png", "--mask", "mask.png", "--quality", "high")
        self.assertEqual(code, 0, err)
        marker = self.marker()
        self.assertEqual(marker["prompt_file"], str(prompt))
        self.assertEqual(marker["refs"], ["a.png", "b.png", "c.png"])
        self.assertEqual(marker["runtime"]["prompt"], "override")
        self.assertEqual(marker["runtime"]["mask"], "mask.png")
        self.assertEqual(marker["runtime"]["quality"], "high")

    def test_three_failed_calls_consume_distinct_attempts_and_stop(self):
        self.stub.write_text("import sys\nprint('outage', file=sys.stderr)\nsys.exit(7)\n")
        for count in range(1, 4):
            code, out, err = self.run_gen()
            self.assertEqual(code, 1, err)
            self.assertEqual(h.kv(out)["RESULT"], "FAIL")
            prefix = self.directory / "raw" / ("crate@16_a%d" % count)
            marker = json.loads(Path(str(prefix) + ".failed.json").read_text())
            self.assertEqual(marker["exit_code"], 7)
            self.assertEqual(marker["failures"], 1)
        attempts = json.loads((self.directory / "pack.json").read_text())[
            "assets"]["crate"]["sizes"]["16"]["attempts"]
        self.assertEqual(len(attempts), 3)
        self.assertEqual([a["status"] for a in attempts], ["failed"] * 3)
        self.stub.write_text(STUB)
        code, _, err = self.run_gen()
        self.assertEqual(code, 2, err)
        self.assertIn("call limit", err.lower())
        self.assertIn("--max-calls", err)
        self.assertFalse(Path(str(self.prefix) + ".png").exists())
        self.assertFalse((self.directory / "raw" / "crate@16_a4.png").exists())

    def test_failed_partial_output_and_marker_survive_new_slot_retry(self):
        self.stub.write_text(STUB + "\nraise SystemExit(7)\n")
        code, _, err = self.run_gen()
        self.assertEqual(code, 1, err)
        self.stub.write_text(STUB)
        code, out, err = self.run_gen()
        self.assertEqual(code, 0, err)
        self.assertTrue(Path(str(self.prefix) + ".failed-1.png").exists())
        self.assertTrue(Path(str(self.prefix) + ".failed.json").exists())
        self.assertEqual(h.kv(out)["RAW"], str(self.directory / "raw" / "crate@16_a2.png"))
        self.assertFalse(Path(str(self.prefix) + ".png").exists())

    def test_explicit_max_calls_allows_fourth_call_and_preserves_settings(self):
        attempt = self.pack["assets"]["crate"]["sizes"]["16"]["attempts"][0]
        attempt.update(size="96x32", frame="48x32", master=False,
                       axis="none", bg="alpha", reference=None)
        self.write_pack()
        self.stub.write_text("raise SystemExit(7)\n")
        for _ in range(3):
            self.assertEqual(self.run_gen()[0], 1)
        self.stub.write_text(STUB)
        code, out, err = self.run_gen("--max-calls", "4", "--user-consent", "yes, one more")
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.directory / "raw" / "crate@16_a4.png").exists())
        attempts = json.loads((self.directory / "pack.json").read_text())[
            "assets"]["crate"]["sizes"]["16"]["attempts"]
        self.assertEqual(len(attempts), 4)
        for record in attempts:
            self.assertEqual((record["size"], record["frame"], record["bg"]),
                             ("96x32", "48x32", "alpha"))
            self.assertEqual(record["runtime_calls"], 1)

    def test_consumed_attempt_cannot_be_reused_after_files_are_removed(self):
        code, _, err = self.run_gen()
        self.assertEqual(code, 0, err)
        Path(str(self.prefix) + ".png").unlink()
        Path(str(self.prefix) + ".gen.json").unlink()
        code, _, err = self.run_gen()
        self.assertEqual(code, 2, err)
        self.assertFalse(Path(str(self.prefix) + ".png").exists())

    def test_nonpositive_max_calls_rejects_before_runtime(self):
        for limit in ("0", "-1"):
            code, _, err = self.run_gen("--max-calls", limit)
            self.assertEqual(code, 2, err)
            self.assertIn("positive", err)
        self.assertFalse(Path(str(self.prefix) + ".gen.json").exists())

    def test_invalid_json_or_missing_png_is_failure(self):
        for count, stub in enumerate(("print('{}')", STUB + "\nprint('not JSON')"), 1):
            with self.subTest(stub=stub):
                self.stub.write_text(stub)
                code, out, err = self.run_gen()
                self.assertEqual(code, 1, err)
                self.assertEqual(h.kv(out)["RESULT"], "FAIL")
                prefix = self.directory / "raw" / ("crate@16_a%d" % count)
                self.assertTrue(json.loads(Path(str(prefix) + ".failed.json").read_text())["error"])

    def test_timeout_writes_failure_marker_without_timing_luck(self):
        from p2d_lib import cli
        gen = importlib.import_module("p2d_lib.gen")
        with patch.object(gen.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("stub", 3)) as run:
            code = cli.main(["gen", str(self.directory), "--name", "crate", "--px", "16",
                             "--runner", self.runner, "--timeout", "3"])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertEqual(self.marker(".failed.json")["exit_code"], -1)

    def test_default_timeout_and_node_fallback(self):
        from p2d_lib import cli
        gen = importlib.import_module("p2d_lib.gen")
        with patch.object(gen.shutil, "which", return_value=None), patch.object(
                gen.subprocess, "run", side_effect=OSError("missing node")) as run:
            code = cli.main(["gen", str(self.directory), "--name", "crate", "--px", "16"])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_args.args[0][:2],
                         ["node", os.path.join(h.SCRIPTS, "gen_image.mjs")])
        self.assertEqual(run.call_args.kwargs["timeout"], 600)


if __name__ == "__main__":
    unittest.main()
