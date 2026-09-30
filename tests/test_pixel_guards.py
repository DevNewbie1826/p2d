from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

import helpers as h
from p2d_lib import checks, pixelize


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p2d-guards-")
        self.addCleanup(self.temp.cleanup)
        self.directory = self.temp.name

    def save(self, img, name="raw.png"):
        return h.save(img, os.path.join(self.directory, name))

    def pixelize(self, img, size="16x16", *options):
        src = self.save(img)
        dst = os.path.join(self.directory, "out.png")
        return h.run_cli("pixelize", src, "--kind", "tile", "--size", size,
                         "--out", dst, *options)


class BlockGuardTest(GuardTest):
    def test_split_preserves_every_rgba_sample_in_rectangular_block(self):
        img = h.native_art(48, 32, h.DUNGEON, seed=15)
        img[..., 3] = np.arange(48 * 32, dtype=np.uint8).reshape(32, 48)
        src = self.save(img)
        dst = os.path.join(self.directory, "tiles")
        code, out, err = h.run_cli("split", src, "--unit", "16", "--out", dst, "--name", "stone")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["TILES"], "6")
        for row in range(2):
            for col in range(3):
                path = os.path.join(dst, "stone-r%dc%d@16.png" % (row, col))
                self.assertIn(path, out)
                np.testing.assert_array_equal(h.load(path), img[row * 16:(row + 1) * 16,
                                                                col * 16:(col + 1) * 16])

    def test_split_defaults_name_to_input_stem(self):
        src = self.save(h.native_art(16, 16, h.DUNGEON), "water-block.png")
        code, out, err = h.run_cli("split", src, "--unit", "16", "--out", self.directory)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.exists(os.path.join(self.directory, "water-block-r0c0@16.png")))

    def test_split_rejects_nonmultiples_and_nonpositive_units_without_writes(self):
        src = self.save(h.native_art(33, 32, h.DUNGEON))
        for unit in ("16", "0", "-1"):
            with self.subTest(unit=unit):
                dst = os.path.join(self.directory, "tiles")
                code, out, err = h.run_cli("split", src, "--unit", unit, "--out", dst)
                self.assertEqual(code, 2, out + err)
                self.assertFalse(os.path.exists(dst))

    def test_pixelize_rejects_halving_detected_native_grid(self):
        img = h.render_generated(h.native_art(32, 32, h.DUNGEON, seed=1), 4, noise=0)
        code, out, err = self.pixelize(img)
        self.assertEqual(code, 2, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.directory, "out.png")))

    def test_pixelize_accepts_block_size_and_explicit_overrides(self):
        img = h.render_generated(h.native_art(32, 32, h.DUNGEON, seed=1), 4, noise=0)
        for size, options in (("32x32", ()), ("16x16", ("--force-size",)),
                              ("16x16", ("--from-block", "32"))):
            with self.subTest(size=size, options=options):
                code, out, err = self.pixelize(img, size, *options)
                self.assertEqual(code, 0, out + err)

    def test_pixelize_does_not_reject_halving_only_one_axis(self):
        img = h.render_generated(h.native_art(32, 16, h.DUNGEON, seed=2), 4, noise=0)
        code, out, err = self.pixelize(img)
        self.assertEqual(code, 0, out + err)

    def test_pixelize_does_not_treat_unaligned_noisy_generation_as_native_block(self):
        img = h.render_generated(h.native_art(16, 16, h.DUNGEON), 4, noise=12)
        code, out, err = self.pixelize(img)
        self.assertEqual(code, 0, out + err)


class TouchGuardTest(GuardTest):
    def run_touch(self, img, count, *options):
        src = self.save(img)
        dst = os.path.join(self.directory, "touched.png")
        sets = []
        for x in range(count):
            sets.extend(("--set", "%d,0=#506070" % x))
        return h.run_cli("touch", src, "--out", dst, *sets, *options)

    def test_nine_changes_fail_without_writing(self):
        img = np.full((16, 16, 4), (20, 30, 40, 255), dtype=np.uint8)
        code, out, err = self.run_touch(img, 9)
        self.assertEqual(code, 2, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.directory, "touched.png")))

    def test_eight_changes_pass_and_force_many_allows_nine(self):
        img = np.full((16, 16, 4), (20, 30, 40, 255), dtype=np.uint8)
        for count, options in ((8, ()), (9, ("--force-many",))):
            code, out, err = self.run_touch(img, count, *options)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(h.kv(out)["CHANGED"], str(count))

    def test_two_percent_uses_opaque_count_and_exact_boundary(self):
        img = np.full((32, 32, 4), (20, 30, 40, 255), dtype=np.uint8)
        for count, expected in ((20, 0), (21, 2)):
            code, out, err = self.run_touch(img, count)
            self.assertEqual(code, expected, out + err)
        img[1:, :, 3] = 0
        code, out, err = self.run_touch(img, 9)
        self.assertEqual(code, 2, out + err)

    def test_repeated_and_unchanged_requests_count_actual_pixels(self):
        img = np.full((16, 16, 4), (80, 96, 112, 255), dtype=np.uint8)
        code, out, err = self.run_touch(img, 16)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["CHANGED"], "0")


class DuplicatedEdgeTest(GuardTest):
    def check(self, img, kind="tile", axis="xy"):
        src = self.save(img)
        height, width = img.shape[:2]
        return h.run_cli("check", src, "--kind", kind, "--size", "%dx%d" % (width, height),
                         "--axis", axis, "--allow-noise")

    def test_copied_edges_fail_for_each_surface_and_axis(self):
        native = np.repeat(np.repeat(h.native_art(8, 8, h.DUNGEON, seed=4), 2, 0), 2, 1)
        for kind in ("tile", "wall", "trim"):
            for axis in ("x", "y"):
                with self.subTest(kind=kind, axis=axis):
                    img = native.copy()
                    if axis == "x":
                        img[:, -1] = img[:, 0]
                    else:
                        img[-1] = img[0]
                    code, out, err = self.check(img, kind, axis)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("FAIL_REASON: SEAM_%s_DUPLICATED_EDGE" % axis.upper(), out)

    def test_flat_stripes_and_native_periodic_edges_pass(self):
        flat = np.full((16, 16, 4), (40, 50, 60, 255), dtype=np.uint8)
        stripes = flat.copy()
        stripes[4:12, :, :3] = (80, 90, 100)
        motif = h.native_art(8, 8, h.DUNGEON, seed=1)
        periodic = np.tile(motif, (2, 2, 1))
        for img in (flat, stripes, periodic):
            code, out, err = self.check(img)
            self.assertEqual(code, 0, out + err)

    def test_unchecked_axis_does_not_fail_duplicated_edge(self):
        img = h.native_art(16, 16, h.DUNGEON, seed=4)
        img[:, -1] = img[:, 0]
        code, out, err = self.check(img, axis="none")
        self.assertEqual(code, 0, out + err)


class AutoDespeckleTest(GuardTest):
    def flat(self, size=16):
        return np.full((size, size, 4), (40, 50, 60, 255), dtype=np.uint8)

    def test_auto_uses_majority_not_only_unanimous_neighbors(self):
        img = self.flat()
        img[5, 5, :3] = (150, 100, 80)
        img[4, 5, :3] = (90, 80, 70)
        img[3, 5, :3] = (90, 80, 70)
        cleaned, changed, capped = pixelize.despeckle_auto(img)
        self.assertEqual(tuple(cleaned[5, 5]), (40, 50, 60, 255))
        self.assertEqual(changed, 1)
        self.assertFalse(capped)
        np.testing.assert_array_equal(cleaned[3:5, 5], img[3:5, 5])

    def test_auto_preserves_same_color_pairs_and_ties(self):
        img = self.flat()
        img[5, 5, :3] = (150, 100, 80)
        img[4:6, 4, :3] = (90, 80, 70)
        img[4, 5, :3] = (90, 80, 70)
        cleaned, changed, capped = pixelize.despeckle_auto(img)
        np.testing.assert_array_equal(cleaned, img)
        self.assertEqual(changed, 0)
        self.assertFalse(capped)

    def test_auto_handles_border_singletons_and_ignores_transparency(self):
        img = self.flat()
        img[0, 0, :3] = (150, 100, 80)
        img[8, 8] = (150, 100, 80, 0)
        cleaned, changed, capped = pixelize.despeckle_auto(img)
        self.assertEqual(tuple(cleaned[0, 0]), (40, 50, 60, 255))
        np.testing.assert_array_equal(cleaned[8, 8], img[8, 8])
        self.assertEqual(changed, 1)
        self.assertFalse(capped)

    def test_auto_caps_changes_at_three_percent_of_opaque_pixels(self):
        img = self.flat()
        for y in (2, 5, 8, 11):
            for x in (2, 5, 8, 11):
                img[y, x, :3] = (150, 100, 80)
        cleaned, changed, capped = pixelize.despeckle_auto(img)
        self.assertEqual(changed, 7)
        self.assertEqual(int(np.any(cleaned != img, axis=2).sum()), 7)
        self.assertTrue(capped)
        img[12:, :, 3] = 0
        _, changed, capped = pixelize.despeckle_auto(img)
        self.assertEqual(changed, 5)
        self.assertTrue(capped)

    def test_cli_auto_reports_count_and_cap_and_legacy_flag_still_works(self):
        img = self.flat()
        for y in (2, 5, 8, 11):
            for x in (2, 5, 8, 11):
                img[y, x, :3] = (150, 100, 80)
        code, out, err = self.pixelize(img, "16x16", "--despeckle", "auto")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["DESPECKLED"], "7")
        self.assertIn("DESPECKLE_CAPPED", h.kv(out))
        code, out, err = self.pixelize(img, "16x16", "--despeckle")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(h.unique_colors(h.load(os.path.join(self.directory, "out.png")))), 1)


class NoiseReportingTest(GuardTest):
    def test_noise_hint_predicts_actual_capped_auto_singleton_rate(self):
        img = h.native_art(16, 16, h.DUNGEON, seed=19)
        src = self.save(img)
        code, out, err = h.run_cli("check", src, "--kind", "tile", "--size", "16x16", "--axis", "none")
        self.assertEqual(code, 1, out + err)
        self.assertIn("NOISE_HINT", h.kv(out))
        cleaned, _, _ = pixelize.despeckle_auto(img)
        target, _ = checks.cluster_stats(cleaned)
        self.assertIn("%.1f%%" % target, h.kv(out)["NOISE_HINT"])

    def test_tile_color_budget_warns_only_below_minimum(self):
        for px, minimum in ((16, 3), (32, 4), (48, 4)):
            img = np.full((px, px, 4), (40, 50, 60, 255), dtype=np.uint8)
            src = self.save(img)
            for cap in (minimum - 1, minimum):
                code, out, err = h.run_cli("check", src, "--kind", "tile",
                                         "--size", "%dx%d" % (px, px), "--max-colors", str(cap))
                self.assertEqual(code, 0, out + err)
                self.assertEqual("COLORS_BELOW_BUDGET" in h.kv(out), cap < minimum)

    def test_original_rm2000_keyed_frame_is_within_noise_range(self):
        src = os.path.join(h.ROOT, "tests", "fixtures", "rm2k-down.png")
        _, out, err = h.run_cli("check", src, "--kind", "frame", "--size", "24x32",
                               "--key", "#009392", "--max-colors", "32")
        values = h.kv(out)
        self.assertGreaterEqual(float(values["SINGLETON_PERCENT"]), 31, out + err)
        self.assertLessEqual(float(values["SINGLETON_PERCENT"]), 52, out + err)
        self.assertEqual(values["NOISE_REVIEW"], "no")

    def test_frames_outside_original_range_still_request_review(self):
        img = h.native_art(24, 32, h.DUNGEON, seed=8)
        img[:2, :, 3] = 0
        img[:, :2, 3] = 0
        img[:, -2:, 3] = 0
        src = self.save(img)
        _, out, err = h.run_cli("check", src, "--kind", "frame", "--size", "24x32")
        self.assertGreater(float(h.kv(out)["SINGLETON_PERCENT"]), 52, out + err)
        self.assertTrue(h.kv(out)["NOISE_REVIEW"].startswith("yes"), out)
