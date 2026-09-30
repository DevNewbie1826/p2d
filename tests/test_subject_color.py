from __future__ import annotations

import os
import unittest

import numpy as np

import helpers as h
from p2d_lib import color, pixelize


class SubjectHeightTest(unittest.TestCase):
    def setUp(self):
        self.directory = h.tmp()
        raw = np.zeros((160, 120, 4), dtype=np.uint8)
        raw[20:140, 40:80] = (90, 100, 110, 255)
        self.source = h.save(raw, os.path.join(self.directory, "raw.png"))
        self.out = os.path.join(self.directory, "out.png")

    def run_height(self, height, *options):
        return h.run_cli(
            "pixelize", self.source, "--kind", "prop", "--size", "24x32",
            "--bg", "alpha", "--anchor", "bottom", "--margin", "1",
            "--subject-height", str(height), "--out", self.out, *options,
        )

    def test_requested_opaque_height_and_bottom_margin(self):
        code, stdout, stderr = self.run_height(26)
        self.assertEqual(code, 0, stdout + stderr)
        ys, xs = np.where(h.load(self.out)[..., 3] > 0)
        self.assertEqual(int(ys.max() - ys.min() + 1), 26)
        self.assertEqual(int(ys.max()), 30)
        self.assertEqual(int(xs.max() - xs.min() + 1), 9)

    def test_height_exceeding_available_canvas_is_error(self):
        code, stdout, stderr = self.run_height(32)
        self.assertEqual(code, 2)
        self.assertIn("--subject-height", stdout + stderr)
        self.assertIn("canvas", stdout + stderr)

    def test_nonpositive_height_is_error(self):
        code, stdout, stderr = self.run_height(0)
        self.assertEqual(code, 2)
        self.assertIn("positive", stdout + stderr)

    def test_surface_kind_rejects_subject_height(self):
        code, stdout, stderr = self.run_height(26, "--kind", "tile")
        self.assertEqual(code, 2)
        self.assertIn("prop", stdout + stderr)


class ProtectedColorTest(unittest.TestCase):
    def setUp(self):
        self.directory = h.tmp()
        self.eye = (1, 2, 3)
        self.raw = np.zeros((32, 24, 4), dtype=np.uint8)
        # Sixteen frequent, well-separated colors; a tiny enclosed eye core.
        colors = [(r, g, b) for r in (60, 180) for g in (60, 180)
                  for b in (40, 100, 160, 220)]
        for i, rgb in enumerate(colors):
            self.raw[2 * i:2 * i + 2, :, :] = (*rgb, 255)
        self.raw[4, 10:12] = (*self.eye, 255)
        self.source = h.save(self.raw, os.path.join(self.directory, "colors.png"))
        self.out = os.path.join(self.directory, "out.png")

    def run_colors(self, *options):
        return h.run_cli(
            "pixelize", self.source, "--kind", "prop", "--size", "24x32",
            "--bg", "alpha", "--max-colors", "16", "--out", self.out, *options,
        )

    def test_auto_preserves_two_pixel_eye_and_reports_color(self):
        code, stdout, stderr = self.run_colors()
        self.assertEqual(code, 0, stdout + stderr)
        self.assertNotIn(self.eye, color.color_table(h.load(self.out)))
        code, stdout, stderr = self.run_colors("--protect-auto")
        self.assertEqual(code, 0, stdout + stderr)
        table = color.color_table(h.load(self.out))
        self.assertEqual(table[self.eye], 2)
        self.assertEqual(len(table), 16)
        self.assertIn("#010203", h.kv(stdout)["PROTECTED"].lower())

    def test_explicit_protection_survives_similar_color_clustering(self):
        rgb = np.array([(100, 100, 100)] * 40 + [(101, 100, 100)] * 2
                       + [(240, 240, 240)] * 30, dtype=np.uint8)
        out = color.reduce_colors(rgb, 2, protect=[(101, 100, 100)])
        self.assertEqual(tuple(out[40]), (101, 100, 100))
        self.assertEqual(len(np.unique(out, axis=0)), 2)

    def test_explicit_cli_and_over_cap_error(self):
        code, stdout, stderr = self.run_colors("--protect", "010203")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(color.color_table(h.load(self.out))[self.eye], 2)
        code, stdout, stderr = self.run_colors(
            "--protect", "010203,3c3c28", "--max-colors", "1")
        self.assertEqual(code, 2)
        self.assertIn("protected colours exceed --max-colors", stdout + stderr)

    def test_highlights_and_eye_location_and_boundary_rules(self):
        rgba = np.full((20, 20, 4), (120, 120, 120, 255), dtype=np.uint8)
        rgba[3, 3:5, :3] = (80, 80, 80)  # dark eye, low contrast
        rgba[15, 3:5, :3] = (90, 90, 90)  # lower-half low contrast
        rgba[15, 12:14, :3] = (250, 250, 250)  # highlight
        rgba[0, 12:14, :3] = (1, 1, 1)  # not surrounded
        rgba[8, 3:10, :3] = (2, 2, 2)  # too large
        protected = color.protected_colors_auto(rgba)
        self.assertEqual(set(protected), {(80, 80, 80), (250, 250, 250)})

    def test_protection_survives_external_palette_and_despeckle(self):
        rgba = np.full((10, 10, 4), (120, 120, 120, 255), dtype=np.uint8)
        rgba[2, 3] = (1, 2, 3, 255)
        for mode in ("legacy", "auto"):
            out, info = pixelize.pixelize_image(
                rgba, "prop", (10, 10), bg="alpha", max_colors=2,
                palette=[(120, 120, 120)], protect_auto=True, do_despeckle=mode)
            self.assertEqual(color.color_table(out)[self.eye], 1)


if __name__ == "__main__":
    unittest.main()
