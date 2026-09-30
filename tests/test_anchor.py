from __future__ import annotations

import json
import os
import unittest

import numpy as np

import helpers as h


class AnchorTest(unittest.TestCase):
    def setUp(self):
        self.directory = h.tmp()
        # Asymmetric art with transparent padding and a transparent interior.
        self.sprite = np.zeros((5, 4, 4), dtype=np.uint8)
        self.sprite[1:4, 1:3] = (12, 34, 56, 255)
        self.sprite[1, 1] = (99, 88, 77, 255)
        self.sprite[2, 2] = (200, 100, 50, 0)
        self.source = h.save(self.sprite, os.path.join(self.directory, "native.png"))
        self.out = os.path.join(self.directory, "anchor.png")

    def run_anchor(self, *options, source=None):
        return h.run_cli(
            "anchor", source or self.source, "--rows", "2", "--cols", "3",
            "--cell", "18x22", "--out", self.out, *options,
        )

    def assert_sheet(self, scale, key):
        sheet = h.load(self.out)
        self.assertEqual(sheet.shape, (44, 54, 4))
        scaled = np.repeat(np.repeat(self.sprite, scale, axis=0), scale, axis=1)
        height, width = scaled.shape[:2]
        x, y = (18 - width) // 2, 22 - 1 - height
        expected = np.empty((22, 18, 4), dtype=np.uint8)
        expected[:] = (*key, 255)
        region = expected[y:y + height, x:x + width]
        mask = scaled[..., 3] == 255
        region[mask] = scaled[mask]
        baselines = []
        for row in range(2):
            for col in range(3):
                cell = sheet[row * 22:(row + 1) * 22, col * 18:(col + 1) * 18]
                np.testing.assert_array_equal(cell, expected)
                occupied = np.any(cell[..., :3] != key, axis=-1)
                baselines.append(int(np.nonzero(occupied)[0].max()) + 1)
                np.testing.assert_array_equal(cell[y:y + height, x:x + width][mask], scaled[mask])
        self.assertEqual(baselines, [y + 4 * scale] * 6)
        with open(os.path.splitext(self.out)[0] + ".json", encoding="utf-8") as handle:
            meta = json.load(handle)
        self.assertEqual(meta["scale"], scale)
        self.assertEqual(meta["sheet"], [54, 44])
        self.assertEqual(meta["cell"], [18, 22])
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(meta["cols"], 3)
        self.assertEqual(meta["source_size"], [4, 5])
        self.assertEqual(meta["offset"], [x, y])
        self.assertEqual(meta["foot_baseline"], baselines[0])
        self.assertEqual(meta["out"], self.out)

    def test_automatic_scale_preserves_every_cell_and_baseline(self):
        code, text, err = self.run_anchor()
        self.assertEqual(code, 0, err)
        values = h.kv(text)
        self.assertEqual(values["SCALE"], "4")
        self.assertEqual(values["SIZE"], "54x44")
        self.assertEqual(values["CELL"], "18x22")
        self.assertEqual(values["FOOT_BASELINE"], "17")
        self.assertEqual(values["OUT"], self.out)
        self.assertEqual(values["JSON"], os.path.splitext(self.out)[0] + ".json")
        self.assert_sheet(4, (255, 0, 255))
        first = h.load(self.out)
        code, _, err = self.run_anchor()
        self.assertEqual(code, 0, err)
        np.testing.assert_array_equal(h.load(self.out), first)

    def test_custom_key_and_explicit_integer_scale(self):
        code, text, err = self.run_anchor("--key", "112233", "--scale", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(text)["SCALE"], "2")
        self.assert_sheet(2, (17, 34, 51))

    def test_explicit_margin_keeps_background_on_every_side(self):
        code, text, err = self.run_anchor("--margin", "4", "--scale", "2")
        self.assertEqual(code, 0, err)
        sheet = h.load(self.out)
        for row in range(2):
            for col in range(3):
                cell = sheet[row * 22:(row + 1) * 22, col * 18:(col + 1) * 18]
                occupied = np.any(cell[..., :3] != (255, 0, 255), axis=-1)
                self.assertFalse(occupied[:4].any())
                self.assertFalse(occupied[-4:].any())
                self.assertFalse(occupied[:, :4].any())
                self.assertFalse(occupied[:, -4:].any())
        self.assertEqual(h.kv(text)["FOOT_BASELINE"], "16")

    def test_rejects_nonpositive_geometry_and_invalid_scale(self):
        for option, value in (
            ("--rows", "0"), ("--rows", "-1"), ("--cols", "0"), ("--cols", "-1"),
            ("--cell", "0x22"), ("--cell", "18x0"), ("--cell", "-1x22"),
            ("--scale", "0"), ("--scale", "-1"), ("--scale", "1.5"),
        ):
            with self.subTest(option=option, value=value):
                code, _, err = self.run_anchor(option + "=" + value)
                self.assertEqual(code, 2)
                self.assertTrue(err)
                self.assertFalse(os.path.exists(self.out))

    def test_rejects_oversize_without_cropping_or_downscaling(self):
        for options in (("--scale", "5"), ("--cell", "5x5"), ("--cell", "2x2")):
            with self.subTest(options=options):
                code, _, err = self.run_anchor(*options)
                self.assertEqual(code, 2)
                self.assertIn("fit", err)
                self.assertFalse(os.path.exists(self.out))

    def test_rejects_partial_alpha(self):
        self.sprite[1, 1, 3] = 128
        h.save(self.sprite, self.source)
        code, _, err = self.run_anchor()
        self.assertEqual(code, 2)
        self.assertIn("binary alpha", err)
        self.assertFalse(os.path.exists(self.out))

    def test_rejects_missing_empty_and_unreadable_input(self):
        empty = h.save(np.zeros((5, 4, 4), dtype=np.uint8), os.path.join(self.directory, "empty.png"))
        unreadable = os.path.join(self.directory, "zero.png")
        with open(unreadable, "wb"):
            pass
        for path, reason in (
            (os.path.join(self.directory, "missing.png"), "file not found"),
            (empty, "empty"), (unreadable, "read"),
        ):
            with self.subTest(path=path):
                code, _, err = self.run_anchor(source=path)
                self.assertEqual(code, 2)
                self.assertIn(reason, err)
                self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
