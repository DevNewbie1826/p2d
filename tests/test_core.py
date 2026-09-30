from __future__ import annotations

import json
import os
import unittest

import numpy as np

import helpers as h
from p2d_lib import color, pixelize
from p2d_lib.imageio import MAGENTA, P2DError


class PixelizeTileTest(unittest.TestCase):
    def test_recovers_native_grid_from_noisy_shifted_generation(self):
        native = h.native_art(16, 16, h.DUNGEON, seed=3)
        raw = h.render_generated(native, 96, noise=14, shift=(21, -17))
        out, info = pixelize.pixelize_image(raw, "tile", (16, 16), bg="none", max_colors=16)
        self.assertEqual(out.shape, (16, 16, 4))
        rolled = np.roll(native, shift=(0, 0), axis=(0, 1))
        dist = np.abs(out[..., :3].astype(int) - rolled[..., :3].astype(int)).sum(axis=2)
        match = float((dist <= 12).mean())
        self.assertGreaterEqual(match, 0.9, info)
        self.assertTrue((out[..., 3] == 255).all())

    def test_tile_output_respects_color_cap(self):
        rng = np.random.default_rng(5)
        raw = np.zeros((1536, 1536, 4), dtype=np.uint8)
        raw[..., :3] = rng.integers(0, 256, size=(1536, 1536, 3))
        raw[..., 3] = 255
        out, _ = pixelize.pixelize_image(raw, "tile", (32, 32), bg="none", max_colors=12)
        self.assertLessEqual(len(h.unique_colors(out)), 12)


class PixelizePropTest(unittest.TestCase):
    def setUp(self):
        sprite = h.native_art(12, 14, h.DUNGEON[:5], seed=9)
        sprite[0, 0, 3] = 0
        sprite[0, 11, 3] = 0
        big = h.render_generated(sprite, 70, noise=10)
        big[..., 3] = np.where(np.repeat(np.repeat(sprite[..., 3], 70, 0), 70, 1) > 0, 255, 0)
        self.raw = h.on_background(big, (1536, 1536), (300, 250), MAGENTA)

    def test_removes_key_background_binary_alpha_and_bottom_anchor(self):
        out, info = pixelize.pixelize_image(self.raw, "prop", (16, 16), bg="key", anchor="bottom", margin=2)
        self.assertEqual(out.shape, (16, 16, 4))
        alpha = out[..., 3]
        self.assertTrue(set(np.unique(alpha).tolist()) <= {0, 255})
        self.assertTrue(alpha[15].any(), "subject must touch the bottom row")
        self.assertFalse(alpha[0].any(), "top row stays empty for a 14-tall subject")
        opaque = out[alpha > 0][:, :3].astype(int)
        magenta_like = (np.abs(opaque - np.array(MAGENTA)).sum(axis=1) < 120).sum()
        self.assertEqual(magenta_like, 0)
        self.assertEqual(info["subject"], [12, 14])

    def test_center_anchor_centers_subject(self):
        out, _ = pixelize.pixelize_image(self.raw, "prop", (32, 32), bg="key", anchor="center")
        ys, xs = np.nonzero(out[..., 3])
        self.assertLessEqual(abs((ys.min() + ys.max()) / 2 - 15.5), 1.0)
        self.assertLessEqual(abs((xs.min() + xs.max()) / 2 - 15.5), 1.0)

    def test_empty_image_is_an_error(self):
        blank = np.zeros((1024, 1024, 4), dtype=np.uint8)
        blank[..., :3] = MAGENTA
        blank[..., 3] = 255
        with self.assertRaises(P2DError):
            pixelize.pixelize_image(blank, "prop", (16, 16), bg="key")


class PaletteTest(unittest.TestCase):
    def test_pack_palette_is_used_exclusively(self):
        native = h.native_art(16, 16, h.DUNGEON, seed=4)
        raw = h.render_generated(native, 64, noise=20)
        pal = h.DUNGEON[:4]
        out, _ = pixelize.pixelize_image(raw, "tile", (16, 16), bg="none", palette=pal, max_colors=16)
        self.assertTrue(set(h.unique_colors(out)) <= set(pal))

    def test_extract_palette_returns_exact_native_colors(self):
        native = h.native_art(16, 16, h.DUNGEON[:6], seed=2)
        pal = color.extract_palette([native], 32)
        self.assertEqual(sorted(pal), sorted(h.DUNGEON[:6]))

    def test_extract_palette_caps_size(self):
        rng = np.random.default_rng(1)
        img = np.zeros((64, 64, 4), dtype=np.uint8)
        img[..., :3] = rng.integers(0, 256, size=(64, 64, 3))
        img[..., 3] = 255
        self.assertLessEqual(len(color.extract_palette([img], 32)), 32)

    def test_despeckle_removes_isolated_pixel(self):
        tile = np.zeros((8, 8, 4), dtype=np.uint8)
        tile[..., :3] = (40, 40, 40)
        tile[..., 3] = 255
        tile[4, 4, :3] = (200, 10, 10)
        cleaned = pixelize.despeckle(tile)
        self.assertEqual(tuple(cleaned[4, 4, :3]), (40, 40, 40))


class DetectionTest(unittest.TestCase):
    def test_detect_pitch_of_upscaled_native_art(self):
        native = h.native_art(16, 16, h.DUNGEON, seed=6)
        big = np.repeat(np.repeat(native, 4, 0), 4, 1)
        self.assertEqual(pixelize.detect_pitch(big), 4)

    def test_checkerboard_is_detected(self):
        yy, xx = np.mgrid[0:512, 0:512]
        board = ((yy // 32 + xx // 32) % 2).astype(np.uint8)
        img = np.zeros((512, 512, 4), dtype=np.uint8)
        img[..., :3] = np.where(board[..., None] == 1, 204, 255)
        img[..., 3] = 255
        img[200:300, 200:300, :3] = (120, 60, 30)
        self.assertTrue(pixelize.is_checkerboard(img))
        flat = img.copy()
        flat[..., :3] = MAGENTA
        self.assertFalse(pixelize.is_checkerboard(flat))


class CliTest(unittest.TestCase):
    def test_top_help_lists_every_command(self):
        code, out, _ = h.run_cli("--help")
        self.assertEqual(code, 0)
        for name in ["pixelize", "check", "frames", "charset", "preview", "pack", "size", "offset"]:
            self.assertIn(name, out)

    def test_size_for_square_tile_and_character_sheet(self):
        code, out, _ = h.run_cli("size", "16x16")
        self.assertEqual(code, 0, out)
        kv = h.kv(out)
        w, hh = [int(v) for v in kv["GEN_SIZE"].split("x")]
        self.assertEqual((w, hh), (1536, 1536))
        code, out, _ = h.run_cli("size", "72x128")
        kv = h.kv(out)
        w, hh = [int(v) for v in kv["GEN_SIZE"].split("x")]
        self.assertEqual((w % 16, hh % 16), (0, 0))
        self.assertTrue(655360 <= w * hh <= 8294400)
        self.assertAlmostEqual(w / hh, 72 / 128, places=3)

    def test_size_rejects_extreme_aspect(self):
        code, _, err = h.run_cli("size", "64x8")
        self.assertEqual(code, 2)
        self.assertIn("aspect", err)

    def test_pack_init_stores_px_and_show_reports_unset(self):
        d = h.tmp()
        code, out, err = h.run_cli("pack", "init", os.path.join(d, "a"), "--name", "a", "--px", "16,32")
        self.assertEqual(code, 0, err)
        with open(os.path.join(d, "a", "pack.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["px"], [16, 32])
        code, out, _ = h.run_cli("pack", "show", os.path.join(d, "a"))
        self.assertEqual(h.kv(out)["PX"], "16,32")
        h.run_cli("pack", "init", os.path.join(d, "b"), "--name", "b")
        code, out, _ = h.run_cli("pack", "show", os.path.join(d, "b"))
        self.assertEqual(h.kv(out)["PX"], "unset")

    def test_pack_rejects_unsupported_px(self):
        d = h.tmp()
        code, _, err = h.run_cli("pack", "init", os.path.join(d, "c"), "--name", "c", "--px", "24")
        self.assertEqual(code, 2)
        self.assertIn("16, 32, 48", err)

    def test_pack_palette_from_existing_asset_and_pixelize_uses_it(self):
        d = h.tmp()
        native = h.native_art(16, 16, h.DUNGEON[:5], seed=7)
        ref = h.save(np.repeat(np.repeat(native, 4, 0), 4, 1), os.path.join(d, "ref.png"))
        pack = os.path.join(d, "p")
        h.run_cli("pack", "init", pack, "--name", "p", "--px", "16")
        code, out, err = h.run_cli("pack", "palette", pack, "--from", ref)
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(out)["PALETTE_COLORS"], "5")
        raw = h.save(h.render_generated(h.native_art(16, 16, h.DUNGEON, seed=8), 96), os.path.join(d, "raw.png"))
        dst = os.path.join(d, "tile.png")
        code, out, err = h.run_cli("pixelize", raw, "--kind", "tile", "--size", "16x16", "--pack", pack, "--out", dst, "--scale", "4")
        self.assertEqual(code, 0, err)
        self.assertTrue(set(h.unique_colors(h.load(dst))) <= set(h.DUNGEON[:5]))
        self.assertEqual(h.load(os.path.join(d, "tile@4x.png")).shape, (64, 64, 4))

    def test_attempt_reservation_limit_and_candidate_retention(self):
        d = h.tmp()
        pack = os.path.join(d, "p")
        h.run_cli("pack", "init", pack, "--name", "p", "--px", "16")
        outputs = []
        for i in range(3):
            code, out, err = h.run_cli("pack", "attempt", pack, "--name", "crate", "--kind", "prop", "--px", "16")
            self.assertEqual(code, 0, err)
            self.assertEqual(h.kv(out)["ATTEMPT"], str(i + 1))
            outputs.append(h.kv(out)["OUTPUT"])
            h.save(h.native_art(4, 4, h.DUNGEON, seed=i), outputs[-1])
        code, _, err = h.run_cli("pack", "attempt", pack, "--name", "crate", "--kind", "prop", "--px", "16")
        self.assertEqual(code, 2)
        self.assertIn("attempt limit reached (3)", err)
        stray = h.save(h.native_art(4, 4, h.DUNGEON, seed=9), os.path.join(d, "stray.png"))
        rgba = h.native_art(16, 16, h.DUNGEON, seed=1)
        rgba[[0, -1], :, 3] = 0
        rgba[:, [0, -1], 3] = 0
        final = h.save(rgba, os.path.join(d, "crate.png"))
        code, _, err = h.run_cli("pack", "accept", pack, "--name", "crate", "--px", "16", "--raw", stray, "--file", final)
        self.assertEqual(code, 2)
        code, out, err = h.run_cli("pack", "accept", pack, "--name", "crate", "--px", "16", "--raw", outputs[1], "--file", final)
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(out)["CANDIDATES_KEPT"], "3")
        self.assertTrue(all(os.path.exists(o) for o in outputs))

    def test_character_accept_requires_engine_frame_or_sheet_size(self):
        d = h.tmp()
        pack = os.path.join(d, "p")
        h.run_cli("pack", "init", pack, "--name", "p", "--px", "16")
        code, out, err = h.run_cli("pack", "attempt", pack, "--name", "knight-master", "--kind", "character", "--px", "16")
        self.assertEqual(code, 0, err)
        raw = h.save(h.native_art(4, 4, h.DUNGEON, seed=1), h.kv(out)["OUTPUT"])
        square = h.save(h.native_art(16, 16, h.DUNGEON, seed=1), os.path.join(d, "sq.png"))
        code, _, err = h.run_cli("pack", "accept", pack, "--name", "knight-master", "--px", "16", "--raw", raw, "--file", square)
        self.assertEqual(code, 2)
        self.assertIn("24x32", err)
        rgba = h.native_art(24, 32, h.DUNGEON, seed=1)
        rgba[[0, -1], :, 3] = 0
        rgba[:, [0, -1], 3] = 0
        frame = h.save(rgba, os.path.join(d, "fr.png"))
        code, _, err = h.run_cli("pack", "accept", pack, "--name", "knight-master", "--px", "16",
                                "--raw", raw, "--file", frame, "--no-face", "back-view size fixture")
        self.assertEqual(code, 0, err)

    def test_inspect_reports_pitch_and_px(self):
        d = h.tmp()
        native = h.native_art(32, 32, h.DUNGEON, seed=1)
        path = h.save(np.repeat(np.repeat(native, 3, 0), 3, 1), os.path.join(d, "x.png"))
        code, out, _ = h.run_cli("inspect", path)
        kv = h.kv(out)
        self.assertEqual(kv["PITCH"], "3")
        self.assertEqual(kv["LOGICAL_SIZE"], "32x32")
        self.assertEqual(kv["SUGGESTED_PX"], "32")

    def test_raw_check_key_background(self):
        d = h.tmp()
        sprite = h.native_art(10, 10, h.DUNGEON, seed=2)
        good = h.save(h.on_background(np.repeat(np.repeat(sprite, 50, 0), 50, 1), (1024, 1024), (200, 200), MAGENTA), os.path.join(d, "g.png"))
        code, out, _ = h.run_cli("raw-check", good, "--bg", "key")
        self.assertEqual(code, 0, out)
        self.assertEqual(h.kv(out)["RESULT"], "PASS")
        gray = h.on_background(np.repeat(np.repeat(sprite, 50, 0), 50, 1), (1024, 1024), (200, 200), (90, 140, 90))
        bad = h.save(gray, os.path.join(d, "b.png"))
        code, out, _ = h.run_cli("raw-check", bad, "--bg", "key")
        self.assertEqual(code, 1)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")

    def test_raw_check_opaque_surface_rejects_transparency(self):
        d = h.tmp()
        surface = np.full((64, 64, 4), (40, 90, 200, 255), dtype=np.uint8)
        solid = h.save(surface, os.path.join(d, "solid.png"))
        code, out, _ = h.run_cli("raw-check", solid, "--bg", "none")
        self.assertEqual(code, 0, out)
        surface[8:40, 8:40, 3] = 0
        holed = h.save(surface, os.path.join(d, "holed.png"))
        code, out, _ = h.run_cli("raw-check", holed, "--bg", "none")
        self.assertEqual(code, 1, out)
        self.assertGreater(float(h.kv(out)["TRANSPARENT_PERCENT"]), 0)


if __name__ == "__main__":
    unittest.main()
