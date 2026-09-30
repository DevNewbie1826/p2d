from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest

import numpy as np

import helpers as h
from p2d_lib import pack
from test_face import face


class AcceptGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p2d-accept-")
        self.addCleanup(self.temp.cleanup)
        self.directory = os.path.join(self.temp.name, "pack")
        self.ok("init", self.directory, "--name", "gate", "--px", "16")

    def ok(self, *args):
        code, out, err = h.run_cli("pack", *args)
        self.assertEqual(code, 0, out + err)
        return out

    def reserve(self, kind="prop", *extra):
        out = self.ok("attempt", self.directory, "--name", "asset", "--kind", kind,
                      "--px", "16", *extra)
        self.raw = h.save(h.native_art(4, 4, h.DUNGEON), h.kv(out)["OUTPUT"])
        self.final = os.path.join(self.directory, "assets", "asset.png")
        a = face() if kind == "character" else np.zeros((16, 16, 4), dtype=np.uint8)
        if kind == "character":
            a[18:30, 3:21] = (100, 100, 120, 255)
        if kind != "character":
            a[2:-2, 2:-2] = (100, 80, 60, 255)
        h.save(a, self.final)

    def accept(self, *extra):
        return h.run_cli("pack", "accept", self.directory, "--name", "asset",
                         "--px", "16", "--raw", self.raw, "--file", self.final, *extra)

    def disk(self):
        with open(pack.pack_file(self.directory)) as stream:
            return json.load(stream)

    def entry(self):
        return self.disk()["assets"]["asset"]["sizes"]["16"]

    def reject(self, message, *extra):
        before = self.disk()
        code, out, err = self.accept(*extra)
        self.assertEqual(code, 2, out + err)
        self.assertIn(message, err)
        self.assertEqual(self.disk(), before)

    def report(self, image=None):
        code, out, err = h.run_cli("face", image or self.final, "--eyes", "9,11", "14,11",
                                  "--skin", "10,13")
        self.assertEqual(code, 0, out + err)
        path = os.path.join(self.directory, "work", "face.txt")
        with open(path, "w") as stream:
            stream.write(out)
        return path

    def test_qc_failure_leaves_pack_unchanged(self):
        self.reserve()
        a = h.load(self.final)
        a[3, 3, 3] = 128
        h.save(a, self.final)
        self.reject("check fails: alpha is not binary")

    def test_palette_and_color_cap_are_enforced(self):
        self.reserve()
        self.ok("palette", self.directory, "--preset", "pico-8")
        self.reject("OUT_OF_PALETTE")
        self.ok("set", self.directory, "--asset-colors", "1")
        a = h.load(self.final)
        a[3, 3] = (255, 255, 255, 255)
        h.save(a, self.final)
        self.reject("colors 2 over the cap of 1")

    def test_success_records_qc_metrics(self):
        self.reserve()
        code, out, err = self.accept()
        self.assertEqual(code, 0, out + err)
        qc = self.entry()["accepted"]["qc"]
        self.assertEqual(qc["result"], "PASS")
        self.assertEqual(qc["metrics"]["SIZE"], "16x16")
        self.assertEqual(qc["metrics"]["ALPHA_BINARY"], "yes")
        self.assertNotIn("FAIL_REASON", qc["metrics"])

    def test_attempt_size_override_is_checked(self):
        self.reserve("prop", "--block", "2x2")
        self.reject("expected 32x32")
        a = np.zeros((32, 32, 4), dtype=np.uint8)
        a[2:-2, 2:-2] = (100, 80, 60, 255)
        h.save(a, self.final)
        self.assertEqual(self.accept()[0], 0)

    def test_replace_requires_flag_and_preserves_history(self):
        self.reserve()
        self.assertEqual(self.accept()[0], 0)
        previous = self.entry()["accepted"]
        self.reject("--replace")
        for _ in range(2):
            self.assertEqual(self.accept("--replace")[0], 0)
        self.assertEqual(self.entry()["history"], [previous, previous])
        moved = os.path.join(self.temp.name, "moved")
        shutil.move(self.directory, moved)
        entry = pack.load_pack(moved)["assets"]["asset"]["sizes"]["16"]
        self.assertTrue(os.path.isfile(entry["history"][0]["file"]))

    def test_failed_replacement_keeps_previous_and_history(self):
        self.reserve()
        self.assertEqual(self.accept()[0], 0)
        h.save(h.native_art(16, 16, h.DUNGEON), self.final)
        self.reject("check fails:", "--replace")

    def test_character_report_is_hashed_and_movable(self):
        self.reserve("character")
        report = self.report()
        self.assertEqual(self.accept("--face-report", report)[0], 0)
        record = self.entry()["accepted"]["face_report"]
        self.assertFalse(os.path.isabs(record["path"]))
        with open(report, "rb") as stream:
            self.assertEqual(record["sha256"], hashlib.sha256(stream.read()).hexdigest())
        moved = os.path.join(self.temp.name, "moved")
        shutil.move(self.directory, moved)
        record = pack.load_pack(moved)["assets"]["asset"]["sizes"]["16"]["accepted"]["face_report"]
        self.assertTrue(os.path.isfile(record["path"]))

    def test_wrong_file_failed_and_incomplete_reports_are_rejected(self):
        self.reserve("character")
        other = h.save(face(), os.path.join(self.directory, "work", "other.png"))
        report = self.report(other)
        self.reject("face report", "--face-report", report)
        for text in ("RESULT: PASS\n", "CROP: anything.png\nRESULT: FAIL\n"):
            with open(report, "w") as stream:
                stream.write(text)
            self.reject("face report", "--face-report", report)
        self.reject("face report", "--face-report", report + ".missing")

    def test_character_auto_face_success_records_report(self):
        self.reserve("character")
        a = h.load(self.final)
        a[16:30, 8:16] = (100, 100, 120, 255)
        h.save(a, self.final)
        code, out, err = self.accept()
        self.assertEqual(code, 0, out + err)
        report = self.entry()["accepted"]["face_report"]
        path = os.path.join(self.directory, report["path"])
        with open(path, "rb") as stream:
            self.assertEqual(report["sha256"], hashlib.sha256(stream.read()).hexdigest())

    def test_animation_auto_face_failure_needs_explicit_exemption(self):
        self.reserve("animation")
        self.reject("face check fails")
        code, out, err = self.accept("--no-face", "visored helmet")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry()["accepted"]["no_face"], "visored helmet")
        self.assertNotIn("face_report", self.entry()["accepted"])

    def test_empty_or_conflicting_face_options_are_rejected(self):
        self.reserve("character")
        self.reject("--no-face", "--no-face", " ")
        self.reject("not allowed", "--no-face", "back", "--face-report", self.report())


if __name__ == "__main__":
    unittest.main()
