from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest

import helpers as h
from p2d_lib import charset, pack, pixelize


class KindSpecTest(unittest.TestCase):
    def test_sizes_and_defaults_at_every_resolution(self):
        for px, frame in [(16, "24x32"), (32, "32x32"), (48, "48x48")]:
            with self.subTest(px=px):
                character = pack.kind_spec("character", px)
                self.assertEqual(character["size"], frame)
                self.assertEqual((character["pixelize_kind"], character["check_kind"]), ("prop", "frame"))
                self.assertEqual((character["anchor"], character["margin"]), ("bottom", 1))
                self.assertEqual(pack.kind_spec("tile", px)["size"], "%dx%d" % (px, px))
                self.assertEqual(pack.kind_spec("tile", px, (2, 2))["size"], "%dx%d" % (2 * px, 2 * px))
                self.assertEqual(pack.kind_spec("tile", px)["axis"], "xy")
                self.assertEqual(pack.kind_spec("wall", px)["size"], "%dx%d" % (px, 3 * px))
                self.assertEqual(pack.kind_spec("wall", px)["axis"], "x")
                self.assertEqual(pack.kind_spec("trim", px)["size"], "%dx%d" % (3 * px // 2, px // 2))
                self.assertEqual(pack.kind_spec("trim", px)["axis"], "x")
                self.assertEqual(pack.kind_spec("prop", px)["size"], "%dx%d" % (px, px))

    def test_character_engine_tables_agree(self):
        for px, fmt in [(16, "rm2k"), (32, "vxace"), (48, "mv")]:
            spec = pack.kind_spec("character", px)
            frame = charset.FORMATS[fmt]["frame"]
            self.assertEqual(spec["size"], "%dx%d" % frame)
            for shape in ("frame", "block", "sheet"):
                size = charset.FORMATS[fmt][shape]
                if size in pixelize.RPG_MAKER_SHEETS:
                    self.assertEqual(pixelize.RPG_MAKER_SHEETS[size][0], px)
                self.assertEqual(pixelize.suggest_px(*size)[0], px)


class PackStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p2d-state-")
        self.addCleanup(self.temp.cleanup)
        self.directory = os.path.join(self.temp.name, "pack")
        self.cli("init", self.directory, "--name", "test", "--px", "16")

    def cli(self, *args):
        code, out, err = h.run_cli("pack", *args)
        self.assertEqual(code, 0, out + err)
        return out

    def reserve(self, *extra):
        return self.cli("attempt", self.directory, "--name", "crate", "--kind", "prop", "--px", "16", *extra)

    def disk(self):
        with open(os.path.join(self.directory, "pack.json")) as stream:
            return json.load(stream)

    def entry(self, data):
        return data["assets"]["crate"]["sizes"]["16"]

    def image(self, path, seed=1):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rgba = h.native_art(16, 16, h.DUNGEON, seed=seed)
        rgba[[0, -1], :, 3] = 0
        rgba[:, [0, -1], 3] = 0
        return h.save(rgba, path)

    def accept(self):
        raw = self.image(h.kv(self.reserve())["OUTPUT"])
        final = self.image(os.path.join(self.directory, "assets", "crate", "crate@16.png"))
        self.cli("accept", self.directory, "--name", "crate", "--px", "16", "--raw", raw, "--file", final)
        return raw, final

    def test_paths_are_relative_and_survive_moving_pack(self):
        ref = self.image(os.path.join(self.directory, "assets", "reference.png"))
        raw = self.image(h.kv(self.reserve("--reference", ref))["OUTPUT"])
        final = self.image(os.path.join(self.directory, "assets", "crate.png"))
        self.cli("accept", self.directory, "--name", "crate", "--px", "16", "--raw", raw, "--file", final)
        data = self.disk()
        self.assertEqual(data["version"], 2)
        entry = self.entry(data)
        for path in [entry["attempts"][0]["output_prefix"], entry["attempts"][0]["reference"],
                     entry["accepted"]["file"], entry["accepted"]["raw"]]:
            self.assertFalse(os.path.isabs(path), path)
        moved = os.path.join(self.temp.name, "moved")
        shutil.move(self.directory, moved)
        entry = self.entry(pack.load_pack(moved))
        self.assertTrue(os.path.isfile(entry["accepted"]["file"]))
        self.assertTrue(os.path.isfile(entry["accepted"]["raw"]))
        self.assertTrue(os.path.isfile(entry["attempts"][0]["reference"]))
        self.assertEqual(pack.candidates(entry), [entry["accepted"]["raw"]])

    def test_legacy_absolute_paths_still_load(self):
        raw, final = self.accept()
        data = self.disk()
        data.pop("version", None)
        entry = self.entry(data)
        entry["accepted"].update(file=final, raw=raw)
        entry["attempts"][0]["output_prefix"] = os.path.splitext(raw)[0]
        pack.write_json(pack.pack_file(self.directory), data)
        loaded = self.entry(pack.load_pack(self.directory))
        self.assertEqual(loaded["accepted"]["file"], final)
        self.assertEqual(pack.candidates(loaded), [raw])

    def test_status_reports_reserved_without_raw(self):
        self.reserve()
        self.assertEqual(self.entry(self.disk())["attempts"][0]["status"], "reserved")
        out = self.cli("status", self.directory)
        self.assertIn("crate@16", out)
        self.assertIn("RESERVED_NO_RAW", out)
        self.assertEqual(h.kv(out)["RESULT"], "ATTENTION")

    def test_status_flags_untracked_assets_but_ignores_previews(self):
        self.image(os.path.join(self.directory, "assets", "crate@8x.png"))
        self.assertEqual(h.kv(self.cli("status", self.directory))["RESULT"], "OK")
        stray = self.image(os.path.join(self.directory, "assets", "nested", "stray.png"))
        out = self.cli("status", self.directory)
        self.assertIn("UNTRACKED_ASSET_FILE", out)
        self.assertIn(os.path.basename(stray), out)
        self.assertEqual(h.kv(out)["RESULT"], "ATTENTION")

    def test_status_flags_pngs_delivered_outside_assets(self):
        for folder in ("raw", "work", "previews"):
            self.image(os.path.join(self.directory, folder, "x.png"))
        self.assertEqual(h.kv(self.cli("status", self.directory))["RESULT"], "OK")
        self.image(os.path.join(self.directory, "lava@16.png"))
        self.image(os.path.join(self.directory, "tiles", "lava-r0c0@16.png"))
        out = self.cli("status", self.directory)
        self.assertIn("STRAY_PNG: lava@16.png", out)
        self.assertIn("STRAY_PNG: tiles/lava-r0c0@16.png", out)
        self.assertEqual(h.kv(out)["RESULT"], "ATTENTION")

    def test_generated_and_accepted_statuses_and_hashes(self):
        out = self.reserve()
        raw = self.image(h.kv(out)["OUTPUT"])
        self.cli("status", self.directory)
        attempt = self.entry(self.disk())["attempts"][0]
        self.assertEqual(attempt["status"], "generated")
        with open(raw, "rb") as stream:
            self.assertEqual(attempt["raw_sha256"], hashlib.sha256(stream.read()).hexdigest())
        final = self.image(os.path.join(self.directory, "assets", "crate.png"))
        self.cli("accept", self.directory, "--name", "crate", "--px", "16", "--raw", raw, "--file", final)
        self.assertEqual(self.entry(self.disk())["attempts"][0]["status"], "accepted")
        self.assertEqual(h.kv(self.cli("status", self.directory))["RESULT"], "OK")

    def test_accepted_hash_mismatch_and_missing_file(self):
        _, final = self.accept()
        self.image(final, seed=99)
        self.assertIn("ACCEPTED_HASH_MISMATCH", self.cli("status", self.directory))
        os.remove(final)
        self.assertIn("ACCEPTED_FILE_MISSING", self.cli("status", self.directory))

    def test_reuse_lost_reuses_newest_without_consuming_slot(self):
        for number in range(1, 4):
            self.assertEqual(h.kv(self.reserve())["ATTEMPT"], str(number))
        out = self.reserve("--reuse-lost")
        self.assertEqual(h.kv(out)["ATTEMPT"], "3")
        self.assertEqual(len(self.entry(self.disk())["attempts"]), 3)
        self.image(h.kv(out)["OUTPUT"])
        self.assertEqual(h.kv(self.reserve("--reuse-lost"))["ATTEMPT"], "2")
        self.image(h.kv(self.reserve("--reuse-lost"))["OUTPUT"])
        self.image(h.kv(self.reserve("--reuse-lost"))["OUTPUT"])
        code, _, err = h.run_cli("pack", "attempt", self.directory, "--name", "crate",
                                "--kind", "prop", "--px", "16", "--reuse-lost")
        self.assertEqual(code, 2)
        self.assertIn("attempt limit", err)

    def test_reference_previews_and_missing_files_are_rejected(self):
        for path in [os.path.join(self.directory, "assets", "crate@8x.png"),
                     os.path.join(self.directory, "previews", "crate.png"),
                     os.path.join(self.directory, "missing.png")]:
            if not path.endswith("missing.png"):
                self.image(path)
            code, _, _ = h.run_cli("pack", "attempt", self.directory, "--name", "crate",
                                  "--kind", "prop", "--px", "16", "--reference", path)
            self.assertEqual(code, 2, path)
        self.assertEqual(self.disk()["assets"], {})

    def test_attempt_records_defaults_and_overrides(self):
        self.reserve()
        attempt = self.entry(self.disk())["attempts"][0]
        self.assertEqual((attempt["size"], attempt["axis"], attempt["bg"]), ("16x16", "none", "key"))
        self.reserve("--size", "32x48", "--axis", "y", "--bg", "alpha")
        attempt = self.entry(self.disk())["attempts"][1]
        self.assertEqual((attempt["size"], attempt["axis"], attempt["bg"]), ("32x48", "y", "alpha"))
        self.reserve("--block", "2x2")
        self.assertEqual(self.entry(self.disk())["attempts"][2]["size"], "32x32")


if __name__ == "__main__":
    unittest.main()
