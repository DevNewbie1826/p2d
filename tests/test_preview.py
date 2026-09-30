from __future__ import annotations

import json
import os
import unittest

import numpy as np

import helpers as h
from p2d_lib import color
from p2d_lib.edit import touch
from p2d_lib.imageio import P2DError, write_json


BG = (68, 68, 68)


def _solid(w, h, rgb, alpha=255):
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., 0] = rgb[0]
    img[..., 1] = rgb[1]
    img[..., 2] = rgb[2]
    img[..., 3] = alpha
    return img


def _rgb(sheet, y, x):
    return (int(sheet[y, x, 0]), int(sheet[y, x, 1]), int(sheet[y, x, 2]))


class PreviewTest(unittest.TestCase):
    def test_preview_shows_16_and_32_at_the_same_display_size(self):
        d = h.tmp()
        small = _solid(16, 16, (0, 160, 0))
        small[0, 0, :3] = (250, 0, 0)
        large = _solid(32, 32, (240, 200, 0))
        large[0, 0, :3] = (0, 0, 250)
        skipped = _solid(4, 4, (255, 0, 255))
        paths = [
            h.save(small, os.path.join(d, "crate@16.png")),
            h.save(skipped, os.path.join(d, "crate@16@8x.png")),
            h.save(large, os.path.join(d, "crate@32.png")),
        ]
        out = os.path.join(d, "sheet.png")
        code, text, err = h.run_cli("preview", paths[0], paths[1], paths[2], "--out", out, "--unit", "128")
        self.assertEqual(code, 0, err)
        kv = h.kv(text)
        self.assertEqual(kv["OUT"], out)
        self.assertEqual(kv["ITEMS"], "2")
        self.assertEqual(kv["SIZE"], "280x128")
        sheet = h.load(out)
        self.assertEqual(sheet.shape, (128, 280, 4))
        self.assertTrue(np.all(sheet[0:8, 0:8, :3] == (250, 0, 0)))
        self.assertTrue(np.all(sheet[0:8, 8:16, :3] == (0, 160, 0)))
        self.assertEqual(_rgb(sheet, 127, 127), (0, 160, 0))
        self.assertTrue(np.all(sheet[0:128, 128:152, :3] == BG))
        self.assertTrue(np.all(sheet[0:4, 152:156, :3] == (0, 0, 250)))
        self.assertTrue(np.all(sheet[0:4, 156:160, :3] == (240, 200, 0)))
        self.assertEqual(_rgb(sheet, 127, 279), (240, 200, 0))
        self.assertFalse(np.any(np.all(sheet[..., :3] == (255, 0, 255), axis=-1)))

    def test_repeat_doubles_displayed_size(self):
        d = h.tmp()
        small = _solid(16, 16, (0, 160, 0))
        small[0, 0, :3] = (250, 0, 0)
        large = _solid(32, 32, (240, 200, 0))
        large[0, 0, :3] = (0, 0, 250)
        a = h.save(small, os.path.join(d, "crate@16.png"))
        b = h.save(large, os.path.join(d, "crate@32.png"))
        out = os.path.join(d, "repeat.png")
        code, text, err = h.run_cli("preview", a, b, "--out", out, "--unit", "128", "--repeat", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(text)["SIZE"], "536x256")
        self.assertEqual(h.kv(text)["ITEMS"], "2")
        sheet = h.load(out)
        self.assertEqual(sheet.shape, (256, 536, 4))
        self.assertEqual(_rgb(sheet, 0, 0), (250, 0, 0))
        self.assertEqual(_rgb(sheet, 0, 127), (0, 160, 0))
        self.assertEqual(_rgb(sheet, 0, 128), (250, 0, 0))
        self.assertEqual(_rgb(sheet, 128, 128), (250, 0, 0))
        self.assertEqual(_rgb(sheet, 0, 256), BG)
        self.assertEqual(_rgb(sheet, 0, 279), BG)
        self.assertEqual(_rgb(sheet, 0, 280), (0, 0, 250))
        self.assertEqual(_rgb(sheet, 0, 407), (240, 200, 0))
        self.assertEqual(_rgb(sheet, 0, 408), (0, 0, 250))
        self.assertEqual(_rgb(sheet, 255, 535), (240, 200, 0))

    def test_preview_bottom_aligns_and_skips_upscaled_names(self):
        d = h.tmp()
        tall = _solid(16, 32, (80, 0, 0))
        short = _solid(32, 32, (0, 80, 0))
        noise = _solid(3, 3, (255, 0, 255))
        out = os.path.join(d, "row.png")
        code, text, err = h.run_cli(
            "preview",
            h.save(noise, os.path.join(d, "tall@16@8x.png")),
            h.save(tall, os.path.join(d, "tall@16.png")),
            h.save(short, os.path.join(d, "tall@32.png")),
            "--out",
            out,
            "--unit",
            "128",
        )
        self.assertEqual(code, 0, err)
        kv = h.kv(text)
        self.assertEqual(kv["ITEMS"], "2")
        self.assertEqual(kv["SIZE"], "280x256")
        sheet = h.load(out)
        self.assertEqual(_rgb(sheet, 0, 0), (80, 0, 0))
        self.assertEqual(_rgb(sheet, 255, 127), (80, 0, 0))
        self.assertEqual(_rgb(sheet, 0, 152), BG)
        self.assertEqual(_rgb(sheet, 127, 152), BG)
        self.assertEqual(_rgb(sheet, 128, 152), (0, 80, 0))
        self.assertEqual(_rgb(sheet, 255, 279), (0, 80, 0))
        self.assertFalse(np.any(np.all(sheet[..., :3] == (255, 0, 255), axis=-1)))

    def test_preview_keeps_a_group_together_when_wrapping(self):
        d = h.tmp()
        solo = h.save(_solid(16, 16, (10, 0, 0)), os.path.join(d, "solo.png"))
        pair32 = h.save(_solid(32, 32, (0, 10, 0)), os.path.join(d, "pair@32.png"))
        pair16 = h.save(_solid(16, 16, (0, 0, 10)), os.path.join(d, "pair@16.png"))
        out = os.path.join(d, "wrap.png")
        code, text, err = h.run_cli(
            "preview", solo, pair32, pair16, "--out", out, "--unit", "128", "--width", "300"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(text)["ITEMS"], "3")
        self.assertEqual(h.kv(text)["SIZE"], "280x280")
        sheet = h.load(out)
        self.assertEqual(_rgb(sheet, 0, 0), (10, 0, 0))
        self.assertEqual(_rgb(sheet, 0, 152), BG)
        self.assertEqual(_rgb(sheet, 152, 0), (0, 10, 0))
        self.assertEqual(_rgb(sheet, 152, 128), BG)
        self.assertEqual(_rgb(sheet, 152, 151), BG)
        self.assertEqual(_rgb(sheet, 152, 152), (0, 0, 10))

    def test_preview_scales_by_unit_over_px_and_composites_alpha(self):
        d = h.tmp()
        brick = h.save(_solid(48, 48, (9, 9, 9)), os.path.join(d, "brick@48.png"))
        out = os.path.join(d, "brick.png")
        code, text, err = h.run_cli("preview", brick, "--out", out, "--unit", "128")
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(text)["SIZE"], "96x96")
        sheet = h.load(out)
        self.assertTrue(np.all(sheet[..., :3] == (9, 9, 9)))

        wide = h.save(_solid(32, 16, (1, 2, 3)), os.path.join(d, "wide@16.png"))
        out = os.path.join(d, "wide.png")
        code, text, err = h.run_cli("preview", wide, "--out", out, "--unit", "128")
        self.assertEqual(code, 0, err)
        self.assertEqual(h.kv(text)["SIZE"], "256x128")

        ghost = _solid(16, 16, (255, 255, 255))
        ghost[0, 0, 3] = 0
        path = h.save(ghost, os.path.join(d, "ghost.png"))
        out = os.path.join(d, "ghost-sheet.png")
        code, _, err = h.run_cli("preview", path, "--out", out, "--unit", "32", "--bg", "#112233")
        self.assertEqual(code, 0, err)
        sheet = h.load(out)
        self.assertEqual(sheet.shape, (32, 32, 4))
        self.assertTrue(np.all(sheet[0:2, 0:2, :3] == (0x11, 0x22, 0x33)))
        self.assertTrue(np.all(sheet[0:2, 2:4, :3] == (255, 255, 255)))

    def test_help_lists_preview_and_atlas_options(self):
        code, out, err = h.run_cli("preview", "--help")
        self.assertEqual(code, 0, err)
        self.assertIn("--unit", out)
        self.assertIn("--repeat", out)
        self.assertIn("--width", out)
        self.assertIn("--gap", out)
        code, out, err = h.run_cli("atlas", "--help")
        self.assertEqual(code, 0, err)
        self.assertIn("--cols", out)
        self.assertIn("--padding", out)
        code, out, err = h.run_cli("touch", "--help")
        self.assertEqual(code, 0, err)
        self.assertIn("--set", out)
        self.assertIn("--clear", out)


class AtlasTest(unittest.TestCase):
    def test_atlas_json_matches_pixel_content(self):
        d = h.tmp()
        images = {}
        paths = []
        for name, rgb in (("a", (200, 0, 0)), ("b", (0, 180, 0)), ("c", (0, 0, 160))):
            images[name] = _solid(4, 4, rgb)
            images[name][0, 0, :3] = (rgb[0] // 2, rgb[1], rgb[2])
            paths.append(h.save(images[name], os.path.join(d, name + ".png")))
        out = os.path.join(d, "atlas.png")
        code, text, err = h.run_cli("atlas", *paths, "--out", out, "--padding", "2")
        self.assertEqual(code, 0, err)
        kv = h.kv(text)
        self.assertEqual(kv["OUT"], out)
        self.assertEqual(kv["ITEMS"], "3")
        self.assertTrue(os.path.isfile(kv["JSON"]))
        with open(kv["JSON"], encoding="utf-8") as handle:
            meta = json.load(handle)
        sheet = h.load(out)
        self.assertEqual(sheet.shape, (10, 10, 4))
        self.assertEqual(meta["a"], {"x": 0, "y": 0, "w": 4, "h": 4})
        self.assertEqual(meta["b"], {"x": 6, "y": 0, "w": 4, "h": 4})
        self.assertEqual(meta["c"], {"x": 0, "y": 6, "w": 4, "h": 4})
        for name, spec in meta.items():
            x, y, w, hh = spec["x"], spec["y"], spec["w"], spec["h"]
            self.assertTrue(np.array_equal(sheet[y : y + hh, x : x + w], images[name]))
        self.assertEqual(int(sheet[0, 4, 3]), 0)
        self.assertEqual(int(sheet[4, 0, 3]), 0)

    def test_atlas_cells_follow_the_largest_image(self):
        d = h.tmp()
        small = _solid(2, 2, (255, 0, 0))
        wide = _solid(5, 3, (0, 0, 255))
        wide[0, 0, :3] = (0, 255, 255)
        out = os.path.join(d, "cells.png")
        code, text, err = h.run_cli(
            "atlas",
            h.save(small, os.path.join(d, "small.png")),
            h.save(wide, os.path.join(d, "wide.png")),
            "--out",
            out,
            "--cols",
            "1",
            "--padding",
            "0",
        )
        self.assertEqual(code, 0, err)
        with open(h.kv(text)["JSON"], encoding="utf-8") as handle:
            meta = json.load(handle)
        sheet = h.load(out)
        self.assertEqual(sheet.shape, (6, 5, 4))
        self.assertEqual(meta["small"], {"x": 0, "y": 0, "w": 2, "h": 2})
        self.assertEqual(meta["wide"], {"x": 0, "y": 3, "w": 5, "h": 3})
        self.assertTrue(np.array_equal(sheet[0:2, 0:2], small))
        self.assertTrue(np.array_equal(sheet[3:6, 0:5], wide))
        self.assertEqual(int(sheet[0, 4, 3]), 0)


class TouchTest(unittest.TestCase):
    def test_touch_sets_and_clears_logical_pixels(self):
        img = _solid(6, 4, (8, 8, 8))
        out = touch(img, [(5, 3, (255, 0, 0)), (0, 0, (0, 255, 0))], [(0, 1)], [(255, 0, 0), (0, 255, 0)])
        self.assertEqual(tuple(int(v) for v in out[3, 5]), (255, 0, 0, 255))
        self.assertEqual(tuple(int(v) for v in out[0, 0]), (0, 255, 0, 255))
        self.assertEqual(int(out[1, 0, 3]), 0)
        self.assertEqual(tuple(int(v) for v in out[0, 1]), (8, 8, 8, 255))
        self.assertEqual(tuple(int(v) for v in img[3, 5]), (8, 8, 8, 255))

        d = h.tmp()
        src = h.save(img, os.path.join(d, "face.png"))
        dest = os.path.join(d, "face-out.png")
        pack = os.path.join(d, "pack")
        os.makedirs(pack)
        write_json(os.path.join(pack, "pack.json"), {"palette": ["#ff0000", "#080808"]})
        code, text, err = h.run_cli(
            "touch",
            src,
            "--set",
            "5,3=#ff0000",
            "--clear",
            "0,1",
            "--pack",
            pack,
            "--out",
            dest,
        )
        self.assertEqual(code, 0, err)
        kv = h.kv(text)
        self.assertEqual(kv["OUT"], dest)
        self.assertEqual(kv["CHANGED"], "2")
        got = h.load(dest)
        self.assertEqual(tuple(int(v) for v in got[3, 5]), (255, 0, 0, 255))
        self.assertEqual(int(got[1, 0, 3]), 0)
        self.assertEqual(tuple(int(v) for v in got[2, 2]), (8, 8, 8, 255))

    def test_touch_rejects_off_palette_and_out_of_range(self):
        img = _solid(4, 4, (8, 8, 8))
        palette = [(255, 0, 0)]
        with self.assertRaises(P2DError):
            touch(img, [(0, 0, (255, 0, 1))], [], palette)
        with self.assertRaises(P2DError):
            touch(img, [(4, 0, (255, 0, 0))], [], palette)
        with self.assertRaises(P2DError):
            touch(img, [], [(-1, 0)], palette)
        with self.assertRaises(P2DError):
            touch(img, [], [(0, 4)], palette)
        self.assertTrue(np.array_equal(img[..., :3], np.full((4, 4, 3), 8, dtype=np.uint8)))

        d = h.tmp()
        src = h.save(img, os.path.join(d, "face.png"))
        dest = os.path.join(d, "nope.png")
        pal = os.path.join(d, "one.hex")
        with open(pal, "w", encoding="utf-8") as handle:
            handle.write("ff0000\n")
        code, _, err = h.run_cli("touch", src, "--set", "0,0=#00ff00", "--palette", pal, "--out", dest)
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", err)
        self.assertFalse(os.path.exists(dest))
        code, _, err = h.run_cli("touch", src, "--set", "9,0=#ff0000", "--palette", pal, "--out", dest)
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", err)
        free = touch(img, [(1, 1, (1, 2, 3))], [], None)
        self.assertEqual(tuple(int(v) for v in free[1, 1]), (1, 2, 3, 255))


class PalettePresetTest(unittest.TestCase):
    def test_lospec_presets_load_with_expected_counts(self):
        db = color.load_palette("db32")
        endesga = color.load_palette("endesga-32")
        pico = color.load_palette("pico-8")
        self.assertEqual(len(db), 32)
        self.assertEqual(len(endesga), 32)
        self.assertEqual(len(pico), 16)
        self.assertEqual(len(set(db)), 32)
        self.assertEqual(len(set(endesga)), 32)
        self.assertEqual(len(set(pico)), 16)
        self.assertEqual(db[0], (0, 0, 0))
        self.assertEqual(db[5], (223, 113, 38))
        self.assertEqual(db[-1], (138, 111, 48))
        self.assertEqual(endesga[0], (190, 74, 47))
        self.assertEqual(endesga[-1], (194, 133, 105))
        self.assertEqual(pico[0], (0, 0, 0))
        self.assertEqual(pico[8], (255, 0, 77))
        self.assertEqual(pico[-1], (255, 204, 170))
        for name, count in (("db32", 32), ("endesga-32", 32), ("pico-8", 16)):
            path = os.path.join(color.PALETTE_DIR, name + ".hex")
            with open(path, encoding="utf-8") as handle:
                lines = [line.strip() for line in handle if line.strip()]
            self.assertEqual(len(lines), count)
            for line in lines:
                self.assertRegex(line, r"^[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()
