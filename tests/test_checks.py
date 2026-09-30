from __future__ import annotations

import os
import unittest
from typing import List

import numpy as np

import helpers as h
from p2d_lib import seam
from p2d_lib.imageio import MAGENTA

RAMP = [
    (20, 24, 28),
    (48, 36, 32),
    (72, 48, 36),
    (96, 64, 40),
    (128, 80, 44),
    (160, 104, 52),
    (196, 132, 64),
    (232, 168, 80),
]


def reasons(stdout: str) -> List[str]:
    found = []
    for line in stdout.splitlines():
        if line.startswith("FAIL_REASON:"):
            found.append(line.split(": ", 1)[1])
    return found


def periodic_tile() -> np.ndarray:
    motif = h.native_art(8, 8, h.DUNGEON, seed=1)
    return np.tile(motif, (2, 2, 1))


def prop_image() -> np.ndarray:
    img = np.zeros((16, 16, 4), dtype=np.uint8)
    img[2:14, 2:14, :3] = (80, 50, 40)
    img[2:14, 2:14, 3] = 255
    return img


def horizontal_stripes() -> np.ndarray:
    img = np.zeros((16, 16, 4), dtype=np.uint8)
    for index, color in enumerate(RAMP):
        img[:, index * 2 : index * 2 + 2, :3] = color
    img[..., 3] = 255
    return img


def vertical_bands() -> np.ndarray:
    img = np.zeros((32, 16, 4), dtype=np.uint8)
    for index, color in enumerate(RAMP):
        img[index * 4 : (index + 1) * 4, :, :3] = color
    img[..., 3] = 255
    return img


def frame_image(x0: int) -> np.ndarray:
    img = np.zeros((32, 24, 4), dtype=np.uint8)
    img[4:28, x0 : x0 + 12, :3] = (80, 50, 40)
    img[4:28, x0 : x0 + 12, 3] = 255
    return img


def outlined_prop() -> np.ndarray:
    img = prop_image()
    img[2, 2:14, :3] = (20, 24, 28)
    img[13, 2:14, :3] = (20, 24, 28)
    img[2:14, 2, :3] = (20, 24, 28)
    img[2:14, 13, :3] = (20, 24, 28)
    return img


class OutlineCheckTest(unittest.TestCase):
    def check(self, img: np.ndarray, *options: str):
        path = h.save(img, os.path.join(h.tmp(), "outline.png"))
        height, width = img.shape[:2]
        return h.run_cli("check", path, "--kind", "prop", "--size", "%dx%d" % (width, height), *options)

    def test_complete_dark_rim_passes(self):
        code, out, err = self.check(outlined_prop(), "--outline-colors", "#14181c")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "0")
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED_COORDS"], "none")

    def test_replaced_rim_pixel_fails_at_exact_coordinate(self):
        img = outlined_prop()
        img[2, 8, :3] = (80, 50, 40)
        code, out, err = self.check(img, "--outline-colors", "14181c")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "1")
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED_COORDS"], "8,2")
        self.assertEqual(reasons(out), ["OUTLINE_UNCOVERED 1"])

    def test_diagonal_staircase_rim_passes(self):
        img = np.zeros((16, 16, 4), dtype=np.uint8)
        for y in range(3, 13):
            img[y, y - 2 : 13] = (20, 24, 28, 255)
            # Only four-neighbor boundary pixels need outline color.
            img[y, y - 1 : 12, :3] = (80, 50, 40)
        img[3, 1:13, :3] = (20, 24, 28)
        img[12, 10:13, :3] = (20, 24, 28)
        code, out, err = self.check(img, "--outline-colors", "14181c")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "0")

    def test_external_hair_pixel_fails_for_frame(self):
        img = outlined_prop()
        img[1, 8] = (168, 123, 72, 255)
        path = h.save(img, os.path.join(h.tmp(), "hair.png"))
        code, out, err = h.run_cli(
            "check", path, "--kind", "frame", "--size", "16x16", "--outline-colors", "14181c"
        )
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "1")
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED_COORDS"], "8,1")

    def test_enclosed_transparency_does_not_need_inner_rim(self):
        img = outlined_prop()
        img[6:10, 6:10, 3] = 0
        code, out, err = self.check(img, "--outline-colors", "14181c")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "0")

    def test_diagonal_contact_does_not_connect_hole_to_exterior(self):
        img = outlined_prop()
        img[2, 2, 3] = 0
        img[3, 3, 3] = 0
        code, out, err = self.check(img, "--outline-colors", "14181c")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "0")

    def test_canvas_boundary_is_exterior_even_when_opaque_allowed(self):
        img = outlined_prop()[2:14, 2:14].copy()
        img[0, 5, :3] = (80, 50, 40)
        code, out, err = self.check(img, "--allow-opaque", "--outline-colors", "14181c")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "1")
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED_COORDS"], "5,0")

    def test_palette_is_explicit_and_can_contain_multiple_colors(self):
        img = outlined_prop()
        img[2, 8, :3] = (200, 210, 220)
        code, out, err = self.check(img, "--outline-colors", "14181c,#c8d2dc")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "0")

    def test_empty_and_malformed_palettes_are_rejected(self):
        for palette in ("", " ", ",", "14181c,", ",14181c", "14181c,,000000", "xyz", "##14181c"):
            with self.subTest(palette=palette):
                code, out, err = self.check(outlined_prop(), "--outline-colors", palette)
                self.assertEqual(code, 2, out + err)
                self.assertIn("outline", err.lower())

    def test_outline_flag_is_rejected_for_surface(self):
        path = h.save(periodic_tile(), os.path.join(h.tmp(), "tile.png"))
        code, out, err = h.run_cli(
            "check", path, "--kind", "tile", "--size", "16x16", "--outline-colors", "14181c"
        )
        self.assertEqual(code, 2, out + err)
        self.assertIn("outline", err.lower())

    def test_coordinates_are_bounded_but_count_is_complete(self):
        code, out, err = self.check(prop_image(), "--outline-colors", "14181c")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["OUTLINE_UNCOVERED"], "44")
        coords = h.kv(out)["OUTLINE_UNCOVERED_COORDS"].split()
        self.assertEqual(len(coords), 32)
        self.assertEqual(coords[0], "2,2")
        self.assertEqual(coords[-1], "13,12")

    def test_no_flag_keeps_existing_behavior(self):
        code, out, err = self.check(prop_image())
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("OUTLINE_UNCOVERED", h.kv(out))
        self.assertNotIn("OUTLINE_UNCOVERED_COORDS", h.kv(out))


class SeamTest(unittest.TestCase):
    def test_offset_inverse_round_trip_is_exact(self):
        for width, height in ((16, 16), (15, 17)):
            img = h.native_art(width, height, h.DUNGEON, seed=width + height)
            for axis in ("x", "y", "xy"):
                forward = seam.offset_image(img, axis, inverse=False)
                self.assertFalse(np.array_equal(forward, img))
                self.assertTrue(np.array_equal(seam.offset_image(forward, axis, inverse=True), img))
                backward = seam.offset_image(img, axis, inverse=True)
                self.assertTrue(np.array_equal(seam.offset_image(backward, axis, inverse=False), img))

    def test_offset_command_round_trip_and_mask_emission(self):
        directory = h.tmp()
        for width, height in ((16, 16), (15, 17)):
            img = h.native_art(width, height, h.DUNGEON, seed=width * 3 + height)
            src = h.save(img, os.path.join(directory, "src-%dx%d.png" % (width, height)))
            mid = os.path.join(directory, "mid-%dx%d.png" % (width, height))
            back = os.path.join(directory, "back-%dx%d.png" % (width, height))
            code, out, err = h.run_cli("offset", src, "--axis", "xy", "--out", mid)
            self.assertEqual(code, 0, err)
            self.assertEqual(h.kv(out)["OUT"], mid)
            self.assertEqual(h.kv(out)["AXIS"], "xy")
            self.assertNotIn("MASK", h.kv(out))
            self.assertFalse(np.array_equal(h.load(mid), img))
            code, out, err = h.run_cli("offset", mid, "--axis", "xy", "--inverse", "--out", back)
            self.assertEqual(code, 0, err)
            self.assertTrue(np.array_equal(h.load(back), img))

    def test_transparent_pixels_count_as_black(self):
        img = np.zeros((8, 8, 4), dtype=np.uint8)
        img[..., :3] = (10, 20, 30)
        img[..., 3] = 255
        img[:, 0, :3] = (255, 255, 255)
        img[:, 0, 3] = 0
        img[:, -1, :3] = (255, 0, 0)
        img[:, -1, 3] = 0
        blacked = img.copy()
        blacked[:, 0, :3] = 0
        blacked[:, -1, :3] = 0
        shown = img.copy()
        shown[..., 3] = 255
        original = img.copy()
        self.assertAlmostEqual(seam.seam_ratio(img, "x"), seam.seam_ratio(blacked, "x"))
        self.assertGreater(abs(seam.seam_ratio(img, "x") - seam.seam_ratio(shown, "x")), 1.0)
        self.assertTrue(np.array_equal(img, original))

    def assert_centre_band(self, mask: np.ndarray, axis: str, band: float) -> None:
        height, width = mask.shape[:2]
        alpha = mask[..., 3]
        self.assertEqual(mask.shape, (height, width, 4))
        self.assertTrue(set(np.unique(alpha).tolist()) <= {0, 255})
        self.assertTrue((alpha == 0).any())
        self.assertTrue((alpha == 255).any())
        opaque = alpha == 255
        self.assertTrue(np.all(mask[opaque][:, :3] == 0))
        full_cols = np.where((alpha == 0).all(axis=0))[0]
        full_rows = np.where((alpha == 0).all(axis=1))[0]

        def span_ok(indices: np.ndarray, length: int, expected: int) -> None:
            self.assertEqual(len(indices), expected)
            self.assertGreater(expected, 0)
            self.assertEqual(int(indices[-1] - indices[0] + 1), expected)
            self.assertLess(abs(float(indices.mean()) - (length - 1) / 2.0), 1.0)

        if axis in ("x", "xy"):
            span_ok(full_cols, width, int(round(band * width)))
        else:
            self.assertEqual(len(full_cols), 0)
        if axis in ("y", "xy"):
            span_ok(full_rows, height, int(round(band * height)))
        else:
            self.assertEqual(len(full_rows), 0)
        expected = np.zeros((height, width), dtype=bool)
        if len(full_cols):
            expected[:, full_cols] = True
        if len(full_rows):
            expected[full_rows, :] = True
        self.assertTrue(np.array_equal(alpha == 0, expected))

    def test_mask_transparent_only_in_centre_band(self):
        cases = (("x", 32, 24, 0.25), ("y", 32, 24, 0.125), ("xy", 40, 16, 0.125))
        for axis, width, height, band in cases:
            self.assert_centre_band(seam.seam_mask(width, height, axis, band=band), axis, band)
        directory = h.tmp()
        width, height, band = 32, 24, 0.25
        src = h.save(h.native_art(width, height, h.DUNGEON, seed=2), os.path.join(directory, "src.png"))
        out = os.path.join(directory, "rolled.png")
        mask_path = os.path.join(directory, "mask.png")
        code, output, err = h.run_cli(
            "offset", src, "--axis", "x", "--band", str(band), "--out", out, "--mask", mask_path
        )
        self.assertEqual(code, 0, err)
        kv = h.kv(output)
        self.assertEqual(kv["OUT"], out)
        self.assertEqual(kv["AXIS"], "x")
        self.assertEqual(kv["MASK"], mask_path)
        written = h.load(mask_path)
        self.assertTrue(np.array_equal(written, seam.seam_mask(width, height, "x", band=band)))
        self.assert_centre_band(written, "x", band)


class CheckTest(unittest.TestCase):
    def test_speckle_noise_fails_singleton_cap_but_clusters_pass(self):
        directory = h.tmp()
        rng = np.random.default_rng(7)
        colors = np.array([[40, 60, 160, 255], [90, 120, 220, 255], [240, 240, 255, 255]], dtype=np.uint8)
        noise = colors[rng.integers(0, 3, size=(16, 16))]
        noisy = h.save(noise, os.path.join(directory, "noise.png"))
        code, out, err = h.run_cli("check", noisy, "--kind", "tile", "--size", "16x16", "--max-singletons", "20")
        kv = h.kv(out)
        self.assertEqual(code, 1, out + err)
        self.assertGreater(float(kv["SINGLETON_PERCENT"]), 20)
        self.assertTrue(any("SINGLETON" in reason for reason in reasons(out)))
        blocks = colors[np.kron(rng.integers(0, 3, size=(4, 4)), np.ones((4, 4), dtype=int))]
        clean = h.save(blocks, os.path.join(directory, "clean.png"))
        code, out, err = h.run_cli(
            "check", clean, "--kind", "tile", "--size", "16x16", "--axis", "none", "--max-singletons", "20"
        )
        self.assertEqual(code, 0, out + err)
        self.assertLessEqual(float(h.kv(out)["SINGLETON_PERCENT"]), 20)
        self.assertGreater(float(h.kv(out)["MEAN_CLUSTER"]), 3)
        self.assertEqual(h.kv(out)["NOISE_REVIEW"], "no")
        code, out, err = h.run_cli("check", noisy, "--kind", "tile", "--size", "16x16", "--axis", "none")
        self.assertTrue(h.kv(out)["NOISE_REVIEW"].startswith("yes"), out)

    def test_periodic_native_tile_passes(self):
        directory = h.tmp()
        tile = periodic_tile()
        path = h.save(tile, os.path.join(directory, "tile.png"))
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16")
        self.assertEqual(code, 0, out + err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "PASS")
        self.assertEqual(reasons(out), [])
        self.assertEqual(kv["SIZE"], "16x16")
        self.assertEqual(int(kv["COLORS"]), len(h.unique_colors(tile)))
        self.assertNotIn("OUT_OF_PALETTE", kv)
        self.assertEqual(kv["ALPHA_BINARY"], "yes")
        self.assertEqual(int(kv["KEY_RESIDUE"]), 0)
        self.assertEqual(float(kv["TRANSPARENT_PERCENT"]), 0.0)
        self.assertLessEqual(float(kv["SEAM_X"]), 1.6)
        self.assertLessEqual(float(kv["SEAM_Y"]), 1.6)
        self.assertEqual(kv["EDGE_TOUCH"], "top,left,right,bottom")

    def test_horizontal_gradient_fails_seam_x(self):
        directory = h.tmp()
        path = h.save(horizontal_stripes(), os.path.join(directory, "grad.png"))
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16")
        self.assertEqual(code, 1, out + err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "FAIL")
        self.assertGreater(float(kv["SEAM_X"]), 1.6)
        self.assertLessEqual(float(kv["SEAM_Y"]), 1.6)
        self.assertTrue(any("seam" in reason.lower() and "x" in reason.lower() for reason in reasons(out)))

    def test_wall_repeats_in_x_but_vertical_gradient_fails_as_tile(self):
        directory = h.tmp()
        path = h.save(vertical_bands(), os.path.join(directory, "wall.png"))
        code, out, err = h.run_cli("check", path, "--kind", "wall", "--size", "16x32")
        self.assertEqual(code, 0, out + err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "PASS")
        self.assertIn("SEAM_X", kv)
        self.assertNotIn("SEAM_Y", kv)
        self.assertLessEqual(float(kv["SEAM_X"]), 1.6)
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x32")
        self.assertEqual(code, 1, out + err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "FAIL")
        self.assertGreater(float(kv["SEAM_Y"]), 1.6)
        self.assertLessEqual(float(kv["SEAM_X"]), 1.6)
        self.assertTrue(any("seam" in reason.lower() and "y" in reason.lower() for reason in reasons(out)))

    def test_wrong_size_fails(self):
        directory = h.tmp()
        path = h.save(periodic_tile(), os.path.join(directory, "tile.png"))
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "32x32")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertEqual(h.kv(out)["SIZE"], "16x16")
        found = reasons(out)
        self.assertTrue(found)
        self.assertTrue(all("size" in reason.lower() for reason in found))

    def test_too_many_colors_fails(self):
        directory = h.tmp()
        path = h.save(periodic_tile(), os.path.join(directory, "tile.png"))
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16")
        self.assertEqual(code, 0, out + err)
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16", "--max-colors", "3")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertGreater(int(h.kv(out)["COLORS"]), 3)
        found = reasons(out)
        self.assertTrue(any("color" in reason.lower() for reason in found))
        self.assertTrue(all("color" in reason.lower() for reason in found))

    def test_out_of_palette_color_fails(self):
        directory = h.tmp()
        palette = h.DUNGEON[:4]
        ref = np.zeros((4, 8, 4), dtype=np.uint8)
        for index, color in enumerate(palette):
            ref[index, :, :3] = color
        ref[..., 3] = 255
        ref_path = h.save(ref, os.path.join(directory, "ref.png"))
        pack = os.path.join(directory, "pack")
        code, _, err = h.run_cli("pack", "init", pack, "--name", "dungeon", "--px", "16")
        self.assertEqual(code, 0, err)
        code, _, err = h.run_cli("pack", "palette", pack, "--from", ref_path)
        self.assertEqual(code, 0, err)
        good = np.zeros((16, 16, 4), dtype=np.uint8)
        good[..., :3] = palette[0]
        good[..., 3] = 255
        good_path = h.save(good, os.path.join(directory, "good.png"))
        code, out, err = h.run_cli("check", good_path, "--kind", "tile", "--size", "16x16", "--pack", pack)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(int(h.kv(out)["OUT_OF_PALETTE"]), 0)
        bad = good.copy()
        bad[6:8, 6:8, :3] = (0, 180, 40)
        bad_path = h.save(bad, os.path.join(directory, "bad.png"))
        code, out, err = h.run_cli("check", bad_path, "--kind", "tile", "--size", "16x16", "--pack", pack)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertEqual(int(h.kv(out)["OUT_OF_PALETTE"]), 4)
        found = reasons(out)
        self.assertTrue(any("palette" in reason.lower() for reason in found))
        self.assertTrue(all("palette" in reason.lower() for reason in found))

    def test_non_binary_alpha_fails(self):
        directory = h.tmp()
        good = prop_image()
        good_path = h.save(good, os.path.join(directory, "good.png"))
        code, out, err = h.run_cli("check", good_path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 0, out + err)
        bad = good.copy()
        bad[8, 8, 3] = 128
        bad_path = h.save(bad, os.path.join(directory, "bad.png"))
        code, out, err = h.run_cli("check", bad_path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertEqual(h.kv(out)["ALPHA_BINARY"], "no")
        found = reasons(out)
        self.assertTrue(any("alpha" in reason.lower() for reason in found))
        self.assertTrue(all("alpha" in reason.lower() for reason in found))

    def test_magenta_residue_fails(self):
        directory = h.tmp()
        good = prop_image()
        good_path = h.save(good, os.path.join(directory, "good.png"))
        code, out, err = h.run_cli("check", good_path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(int(h.kv(out)["KEY_RESIDUE"]), 0)
        bad = good.copy()
        bad[8, 8, :3] = MAGENTA
        bad_path = h.save(bad, os.path.join(directory, "bad.png"))
        code, out, err = h.run_cli("check", bad_path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertGreater(int(h.kv(out)["KEY_RESIDUE"]), 0)
        found = reasons(out)
        self.assertTrue(any("key" in reason.lower() for reason in found))
        self.assertTrue(all("key" in reason.lower() for reason in found))

    def test_prop_with_transparent_corners_passes(self):
        directory = h.tmp()
        path = h.save(prop_image(), os.path.join(directory, "prop.png"))
        code, out, err = h.run_cli("check", path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 0, out + err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "PASS")
        self.assertEqual(kv["EDGE_TOUCH"], "none")
        self.assertGreater(float(kv["TRANSPARENT_PERCENT"]), 0.0)
        self.assertNotIn("SEAM_X", kv)
        self.assertNotIn("SEAM_Y", kv)

    def test_frame_touching_left_edge_fails(self):
        directory = h.tmp()
        clear = h.save(frame_image(4), os.path.join(directory, "clear.png"))
        code, out, err = h.run_cli("check", clear, "--kind", "frame", "--size", "24x32")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("left", h.kv(out)["EDGE_TOUCH"].split(","))
        touching = h.save(frame_image(0), os.path.join(directory, "touch.png"))
        code, out, err = h.run_cli("check", touching, "--kind", "frame", "--size", "24x32")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertIn("left", [part.strip() for part in h.kv(out)["EDGE_TOUCH"].split(",")])
        found = reasons(out)
        self.assertTrue(any("left" in reason.lower() for reason in found))
        self.assertTrue(all("left" in reason.lower() or "edge" in reason.lower() for reason in found))

    def test_opaque_prop_fails_unless_allowed(self):
        directory = h.tmp()
        img = np.zeros((16, 16, 4), dtype=np.uint8)
        img[..., :3] = (80, 50, 40)
        img[..., 3] = 255
        path = h.save(img, os.path.join(directory, "solid.png"))
        code, out, err = h.run_cli("check", path, "--kind", "prop", "--size", "16x16")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(float(h.kv(out)["TRANSPARENT_PERCENT"]), 0.0)
        self.assertTrue(any("transparent" in reason.lower() or "opaque" in reason.lower() for reason in reasons(out)))
        code, out, err = h.run_cli("check", path, "--kind", "prop", "--size", "16x16", "--allow-opaque")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(h.kv(out)["RESULT"], "PASS")

    def test_surface_with_transparent_pixel_fails(self):
        directory = h.tmp()
        tile = periodic_tile()
        path = h.save(tile, os.path.join(directory, "solid.png"))
        code, _, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16", "--axis", "none")
        self.assertEqual(code, 0, err)
        tile = tile.copy()
        tile[0, 0, 3] = 0
        path = h.save(tile, os.path.join(directory, "hole.png"))
        code, out, err = h.run_cli("check", path, "--kind", "tile", "--size", "16x16", "--axis", "none")
        self.assertEqual(code, 1, out + err)
        found = reasons(out)
        self.assertTrue(any("transparent" in reason.lower() for reason in found))
        self.assertTrue(all("transparent" in reason.lower() for reason in found))


if __name__ == "__main__":
    unittest.main()
