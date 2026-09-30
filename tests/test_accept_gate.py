from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
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

    def test_face_report_is_bound_to_checked_image_bytes(self):
        self.reserve("character")
        report = self.report()
        a = h.load(self.final)
        a[20, 10] = (101, 100, 120, 255)
        h.save(a, self.final)
        self.reject("face report image hash", "--face-report", report)

    def test_face_prints_checked_image_sha256(self):
        self.reserve("character")
        report = self.report()
        with open(report) as stream:
            self.assertEqual(h.kv(stream.read()).get("IMAGE_SHA256"),
                             pack._sha256(self.final))

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
        self.reserve("animation", "--size", "16x16", "--frame", "16x16")
        self.reject("face check fails")
        code, out, err = self.accept("--no-face", "visored helmet")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry()["accepted"]["no_face"], "visored helmet")
        self.assertNotIn("face_report", self.entry()["accepted"])

    def atlas(self, touch):
        a = np.zeros((32, 32, 4), dtype=np.uint8)
        for r in range(2):
            for c in range(2):
                a[r * 16 + 2:r * 16 + 14, c * 16 + 3:c * 16 + 13] = (100, 80, 60, 255)
        if touch:
            a[20:26, 16:18] = (100, 80, 60, 255)
        h.save(a, self.final)

    def test_animation_atlas_checks_every_cell(self):
        self.reserve("animation", "--size", "32x32", "--frame", "16x16")
        self.atlas(touch=True)
        self.reject("r1c1", "--no-face", "test")
        self.atlas(touch=False)
        code, out, err = self.accept("--no-face", "test")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry()["accepted"]["qc"]["cells"], 4)

    def test_rm2000_animation_uses_character_frame_not_tile_unit(self):
        self.reserve("animation", "--size", "48x64")
        a = np.zeros((64, 48, 4), dtype=np.uint8)
        for r in range(2):
            for c in range(2):
                a[r * 32 + 3:r * 32 + 29, c * 24 + 3:c * 24 + 21] = (100, 80, 60, 255)
        h.save(a, self.final)
        code, out, err = self.accept("--no-face", "back view")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry()["attempts"][0]["frame"], "24x32")
        self.assertEqual(self.entry()["accepted"]["qc"]["cells"], 4)

    def test_documented_body_and_fx_attempt_save_accept_flow(self):
        doc = os.path.join(h.ROOT, "skills", "p2d", "references", "animation.md")
        with open(doc) as stream:
            commands = re.findall(r"`(pack attempt DIR[^`]+)`", stream.read())
        guide = h.save(np.zeros((32, 32, 4), dtype=np.uint8),
                       os.path.join(self.directory, "work", "guide.png"))
        for kind in ("animation", "fx"):
            with self.subTest(kind=kind):
                command = next((text for text in commands if "--kind " + kind in text), None)
                self.assertIsNotNone(command, "document a complete reservation command for " + kind)
                values = {"DIR": self.directory, "<char>-<action>-<facing>": "body",
                          "<char>-<effect>-<facing>": "effect", "P": "32",
                          "AWxAH": "64x64", "WxH": "32x32", "GUIDE": guide}
                argv = [values.get(token, token) for token in shlex.split(command)]
                code, out, err = h.run_cli(*argv)
                self.assertEqual(code, 0, out + err)
                name = argv[argv.index("--name") + 1]
                a = np.zeros((64, 64, 4), dtype=np.uint8)
                for r in range(2):
                    for c in range(2):
                        a[r * 32 + 3:r * 32 + 29, c * 32 + 5:c * 32 + 27] = (100, 80, 60, 255)
                raw = h.save(a, h.kv(out)["OUTPUT"])
                final = h.save(a, os.path.join(self.directory, "assets", name + ".png"))
                code, out, err = h.run_cli("pack", "accept", self.directory, "--name", name,
                                          "--px", "32", "--raw", raw, "--file", final,
                                          "--no-face", "faceless test sheet")
                self.assertEqual(code, 0, out + err)

    def test_wide_animation_frames_pass_and_interior_clipping_names_cell(self):
        self.reserve("animation", "--size", "96x32", "--frame", "48x32")
        a = np.zeros((32, 96, 4), dtype=np.uint8)
        a[3:29, 4:44] = (100, 80, 60, 255)
        a[3:29, 52:92] = (100, 80, 60, 255)
        a[12:20, 48:52] = (100, 80, 60, 255)
        h.save(a, self.final)
        self.reject("r0c1: frame touches left edge", "--no-face", "back view")
        a[12:20, 48:52] = 0
        h.save(a, self.final)
        code, out, err = self.accept("--no-face", "back view")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry()["accepted"]["qc"]["cells"], 2)
        attempt = self.entry()["attempts"][0]
        self.assertEqual((attempt["size"], attempt["frame"]), ("96x32", "48x32"))

    def test_empty_or_conflicting_face_options_are_rejected(self):
        self.reserve("character")
        self.reject("--no-face", "--no-face", " ")
        self.reject("not allowed", "--no-face", "back", "--face-report", self.report())

    def test_character_master_acceptance_rejects_thin_front(self):
        self.reserve("character", "--master")
        a = np.zeros((32, 24, 4), dtype=np.uint8)
        a[5:31, 6:19] = (100, 80, 60, 255)
        h.save(a, self.final)
        self.reject("PROPORTION", "--no-face", "visored helmet")


if __name__ == "__main__":
    unittest.main()
