from __future__ import annotations

import json
import os
import shutil
import unittest

import numpy as np
from PIL import Image

import helpers as h
from p2d_lib.imageio import MAGENTA

ROWS, COLS = 4, 3
CELL_W, CELL_H = 288, 384
FEET_BOTTOM = 344
NATIVE_W, NATIVE_H = 10, 14
ROW_COLORS = [(202, 63, 53), (88, 172, 81), (77, 111, 205), (214, 193, 66)]
EYE = (245, 245, 245)
RM2K_SHEET_ROWS = [3, 2, 0, 1]


def figure(row: int, pose: int, native_h: int = NATIVE_H) -> np.ndarray:
    art = np.zeros((native_h, NATIVE_W, 4), dtype=np.uint8)
    art[:5, 2:8, :3] = ROW_COLORS[row]
    art[5:native_h, 1:9, :3] = ROW_COLORS[row]
    art[2, 3 + pose, :3] = EYE
    art[..., 3] = 255
    return art


def character_raw(scale: int = 16, tall=None, empty=None, cross: bool = False, seed: int = 11) -> np.ndarray:
    raw = np.zeros((ROWS * CELL_H, COLS * CELL_W, 4), dtype=np.uint8)
    raw[..., :3] = MAGENTA
    raw[..., 3] = 255
    for r in range(ROWS):
        for c in range(COLS):
            if empty == (r, c):
                continue
            native_h = NATIVE_H + (6 if tall == (r, c) else 0)
            big = np.repeat(np.repeat(figure(r, c, native_h), scale, 0), scale, 1).astype(np.int16)
            rng = np.random.default_rng(seed * 1000 + r * 10 + c)
            big[..., :3] = np.clip(big[..., :3] + rng.integers(-6, 7, big[..., :3].shape, dtype=np.int16), 0, 255)
            x = c * CELL_W + (CELL_W - NATIVE_W * scale) // 2
            if cross and (r, c) == (0, 0):
                x += 200
            y = r * CELL_H + FEET_BOTTOM - native_h * scale
            raw[y : y + native_h * scale, x : x + NATIVE_W * scale] = big.astype(np.uint8)
    return raw


def sheet_rgba(path: str) -> np.ndarray:
    with Image.open(path) as img:
        idx = np.array(img)
        rgba = np.array(img.convert("RGBA"))
    rgba[idx == 0, 3] = 0
    return rgba


def assert_frame_pixels(testcase: unittest.TestCase, sheet: np.ndarray, frame: np.ndarray, msg=None) -> None:
    testcase.assertEqual(sheet.shape, frame.shape, msg)
    testcase.assertTrue(np.array_equal(sheet[..., 3], frame[..., 3]), msg)
    opaque = sheet[..., 3] > 0
    testcase.assertTrue(np.array_equal(sheet[opaque][:, :3], frame[opaque][:, :3]), msg)


def run_frames(raw: str, out_dir: str, *extra: str):
    return h.run_cli(
        "frames", raw, "--rows", str(ROWS), "--cols", str(COLS), "--frame", "24x32", "--out", out_dir, *extra
    )


class FramesCommandTest(unittest.TestCase):
    def test_pass_grid_cuts_12_anchored_frames_with_shared_palette(self):
        d = h.tmp()
        raw = h.save(character_raw(), os.path.join(d, "raw.png"))
        out_dir = os.path.join(d, "frames")
        code, so, se = run_frames(raw, out_dir)
        self.assertEqual(code, 0, se)
        kv = h.kv(so)
        self.assertEqual(kv["RESULT"], "PASS")
        self.assertAlmostEqual(float(kv["PITCH"]), 224 / 30, delta=0.001)
        union = set()
        for r in range(ROWS):
            for c in range(COLS):
                path = os.path.join(out_dir, "r%dc%d.png" % (r, c))
                frame = h.load(path)
                self.assertEqual(frame.shape, (32, 24, 4), path)
                self.assertTrue(frame[31, ..., 3].any(), "feet anchor: bottom row opaque")
                self.assertFalse(frame[0, ..., 3].any(), "head leaves the top row free")
                self.assertTrue(set(np.unique(frame[..., 3]).tolist()) <= {0, 255})
                union |= set(h.unique_colors(frame))
        self.assertLessEqual(len(union), 16)
        for r in range(ROWS):
            colors = h.unique_colors(h.load(os.path.join(out_dir, "r%dc1.png" % r)))
            near = min(np.abs(np.array(c) - np.array(ROW_COLORS[r])).sum() for c in colors)
            self.assertLessEqual(near, 40, "row %d keeps its generation color" % r)
        with open(os.path.join(out_dir, "frames.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["result"], "PASS")
        self.assertEqual(len(data["frames"]), 12)
        self.assertEqual(len({tuple(f["grid"]) for f in data["frames"]}), 1, "shared pitch -> equal grids")

    def test_scale_cv_fail_and_loose_pass(self):
        d = h.tmp()
        raw = h.save(character_raw(tall=(2, 1)), os.path.join(d, "tall.png"))
        out_dir = os.path.join(d, "frames")
        code, so, se = run_frames(raw, out_dir, "--subject-height", "20")
        self.assertEqual(code, 1, so + se)
        kv = h.kv(so)
        self.assertEqual(kv["RESULT"], "FAIL")
        self.assertGreater(float(kv["SCALE_CV"]), 0.08)
        with open(os.path.join(out_dir, "frames.json")) as fh:
            self.assertEqual(json.load(fh)["result"], "FAIL")
        loose_dir = os.path.join(d, "loose")
        code, so, se = run_frames(raw, loose_dir, "--subject-height", "20", "--loose")
        self.assertEqual(code, 0, so + se)
        self.assertEqual(h.kv(so)["RESULT"], "PASS")

    def test_empty_frame_fails(self):
        d = h.tmp()
        raw = h.save(character_raw(empty=(1, 2)), os.path.join(d, "holed.png"))
        out_dir = os.path.join(d, "frames")
        code, so, _ = run_frames(raw, out_dir)
        self.assertEqual(code, 1)
        kv = h.kv(so)
        self.assertEqual(kv["RESULT"], "FAIL")
        self.assertEqual(kv["EMPTY_FRAMES"], "1")
        self.assertTrue(any("empty" in line.lower() for line in so.splitlines() if line.startswith("FAIL_REASON")))
        blank = h.load(os.path.join(out_dir, "r1c2.png"))
        self.assertEqual(blank.shape, (32, 24, 4))
        self.assertFalse(blank[..., 3].any())

    def test_subject_crossing_a_cell_border_fails(self):
        d = h.tmp()
        raw = h.save(character_raw(cross=True), os.path.join(d, "cross.png"))
        code, so, _ = run_frames(raw, os.path.join(d, "frames"))
        self.assertEqual(code, 1)
        kv = h.kv(so)
        self.assertEqual(kv["RESULT"], "FAIL")
        self.assertGreaterEqual(int(kv["EDGE_TOUCH_FRAMES"]), 1)

    def test_write_profile_then_profile_reuses_the_pitch(self):
        d = h.tmp()
        raw_a = h.save(character_raw(), os.path.join(d, "a.png"))
        prof = os.path.join(d, "profile.json")
        code, _, se = run_frames(raw_a, os.path.join(d, "fa"), "--write-profile", prof)
        self.assertEqual(code, 0, se)
        with open(prof) as fh:
            pdata = json.load(fh)
        self.assertTrue({"pitch", "frame", "anchor", "subject_height", "source"} <= set(pdata))
        raw_b = h.save(character_raw(scale=17, seed=12), os.path.join(d, "b.png"))
        code, _, se = run_frames(raw_b, os.path.join(d, "fb"), "--profile", prof)
        self.assertEqual(code, 0, se)
        with open(os.path.join(d, "fb", "frames.json")) as fh:
            bdata = json.load(fh)
        self.assertAlmostEqual(bdata["pitch"], pdata["pitch"], delta=0.001)
        self.assertGreater(abs(pdata["pitch"] - 238 / 30), 0.4, "own median would give another pitch")

    def test_center_anchor_centres_the_subject(self):
        d = h.tmp()
        raw = h.save(character_raw(), os.path.join(d, "raw.png"))
        out_dir = os.path.join(d, "frames")
        code, _, se = run_frames(raw, out_dir, "--anchor", "center")
        self.assertEqual(code, 0, se)
        frame = h.load(os.path.join(out_dir, "r0c1.png"))
        self.assertFalse(frame[0, ..., 3].any(), "top row free")
        self.assertFalse(frame[31, ..., 3].any(), "bottom row free")
        self.assertTrue(frame[15, ..., 3].any() and frame[16, ..., 3].any())

    def test_write_profile_and_profile_are_exclusive(self):
        d = h.tmp()
        raw = h.save(character_raw(), os.path.join(d, "raw.png"))
        code, _, se = run_frames(raw, os.path.join(d, "f"), "--write-profile", "p.json", "--profile", "p.json")
        self.assertEqual(code, 2)
        self.assertIn("profile", se)


class CharsetRm2kTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = h.tmp()
        raw = h.save(character_raw(), os.path.join(cls.d, "raw.png"))
        cls.frames = os.path.join(cls.d, "frames")
        code, _, se = run_frames(raw, cls.frames)
        if code != 0:
            raise AssertionError(se)

    def frame(self, r: int, c: int) -> np.ndarray:
        return h.load(os.path.join(self.frames, "r%dc%d.png" % (r, c)))

    def test_rm2k_sheet_layout_palette_and_row_order(self):
        out = os.path.join(self.d, "sheet.png")
        code, so, se = h.run_cli("charset", "--format", "rm2k", "--frames", self.frames, "--out", out)
        self.assertEqual(code, 0, se)
        kv = h.kv(so)
        self.assertEqual(kv["OUT"], out)
        self.assertEqual(kv["SIZE"], "288x256")
        self.assertEqual(kv["SLOT"], "0")
        with Image.open(out) as img:
            self.assertEqual(img.mode, "P")
            self.assertEqual(img.size, (288, 256))
            pal = img.getpalette() or []
            engine_rgba = np.array(img.convert("RGBA"))
        self.assertEqual(len(pal), 768)
        self.assertEqual(tuple(pal[:3]), MAGENTA)
        self.assertEqual(engine_rgba[0, 0, 3], 0, "index 0 must decode as transparent")
        sheet = sheet_rgba(out)
        for d, gen in enumerate(RM2K_SHEET_ROWS):
            for p in range(3):
                region = sheet[d * 32 : (d + 1) * 32, p * 24 : (p + 1) * 24]
                assert_frame_pixels(self, region, self.frame(gen, p), (d, p))

    def test_mirror_right_replaces_right_with_mirrored_left(self):
        out = os.path.join(self.d, "mirror.png")
        code, _, se = h.run_cli(
            "charset", "--format", "rm2k", "--frames", self.frames, "--out", out, "--mirror-right"
        )
        self.assertEqual(code, 0, se)
        sheet = sheet_rgba(out)
        for p in range(3):
            region = sheet[32:64, p * 24 : (p + 1) * 24]
            assert_frame_pixels(self, region, np.flip(self.frame(1, p), axis=1), p)
            self.assertFalse(np.array_equal(region, self.frame(2, p)), p)
        down = sheet[64:96]
        assert_frame_pixels(self, down[:, :24], self.frame(0, 0))

    def test_second_slot_keeps_the_first(self):
        out = os.path.join(self.d, "slots.png")
        code, _, se = h.run_cli("charset", "--format", "rm2k", "--frames", self.frames, "--out", out, "--slot", "0")
        self.assertEqual(code, 0, se)
        first = sheet_rgba(out).copy()
        code, so, se = h.run_cli("charset", "--format", "rm2k", "--frames", self.frames, "--out", out, "--slot", "1")
        self.assertEqual(code, 0, se)
        self.assertEqual(h.kv(so)["SLOT"], "1")
        merged = sheet_rgba(out)
        self.assertTrue(np.array_equal(merged[0:128, 0:72], first[0:128, 0:72]))
        for d, gen in enumerate(RM2K_SHEET_ROWS):
            for p in range(3):
                region = merged[d * 32 : (d + 1) * 32, 72 + p * 24 : 72 + (p + 1) * 24]
                assert_frame_pixels(self, region, self.frame(gen, p), (d, p))

    def test_custom_order_remaps_generation_rows(self):
        out = os.path.join(self.d, "reordered.png")
        code, _, se = h.run_cli(
            "charset", "--format", "rm2k", "--frames", self.frames, "--out", out, "--order", "up,down,left,right"
        )
        self.assertEqual(code, 0, se)
        sheet = sheet_rgba(out)
        for d, direction in enumerate(["up", "right", "down", "left"]):
            gen = {"up": 0, "down": 1, "left": 2, "right": 3}[direction]
            for p in range(3):
                region = sheet[d * 32 : (d + 1) * 32, p * 24 : (p + 1) * 24]
                assert_frame_pixels(self, region, self.frame(gen, p), (d, p))

    def test_wrong_frame_size_is_a_user_error(self):
        bad = os.path.join(self.d, "badsize")
        shutil.copytree(self.frames, bad)
        h.save(np.zeros((16, 16, 4), dtype=np.uint8), os.path.join(bad, "r2c0.png"))
        code, _, se = h.run_cli("charset", "--format", "rm2k", "--frames", bad, "--out", os.path.join(self.d, "x.png"))
        self.assertEqual(code, 2)
        self.assertIn("24x32", se)

    def test_missing_frame_file_is_a_user_error(self):
        holed = os.path.join(self.d, "holed")
        shutil.copytree(self.frames, holed)
        os.remove(os.path.join(holed, "r3c2.png"))
        code, _, se = h.run_cli("charset", "--format", "rm2k", "--frames", holed, "--out", os.path.join(self.d, "y.png"))
        self.assertEqual(code, 2)
        self.assertIn("r3c2.png", se)


class CharsetVxAceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = h.tmp()
        raw = h.save(character_raw(), os.path.join(cls.d, "raw.png"))
        cls.frames = os.path.join(cls.d, "frames32")
        code, _, se = h.run_cli(
            "frames", raw, "--rows", str(ROWS), "--cols", str(COLS), "--frame", "32x32", "--out", cls.frames
        )
        if code != 0:
            raise AssertionError(se)

    def frame(self, r: int, c: int) -> np.ndarray:
        return h.load(os.path.join(self.frames, "r%dc%d.png" % (r, c)))

    def test_single_sheet_gets_dollar_prefix_and_default_rows(self):
        base = os.path.join(self.d, "knight.png")
        code, so, se = h.run_cli("charset", "--format", "vxace", "--frames", self.frames, "--out", base)
        self.assertEqual(code, 0, se)
        kv = h.kv(so)
        self.assertTrue(kv["OUT"].endswith("$knight.png"), kv["OUT"])
        self.assertFalse(os.path.exists(base))
        path = os.path.join(self.d, "$knight.png")
        with Image.open(path) as img:
            self.assertEqual(img.mode, "RGBA")
            self.assertEqual(img.size, (96, 128))
        sheet = h.load(path)
        for d in range(4):
            for p in range(3):
                region = sheet[d * 32 : (d + 1) * 32, p * 32 : (p + 1) * 32]
                self.assertTrue(np.array_equal(region, self.frame(d, p)), (d, p))

    def test_object_eight_sheet_places_the_slot(self):
        base = os.path.join(self.d, "squad.png")
        code, so, se = h.run_cli(
            "charset",
            "--format",
            "vxace",
            "--frames",
            self.frames,
            "--out",
            base,
            "--sheet",
            "eight",
            "--object",
            "--slot",
            "3",
        )
        self.assertEqual(code, 0, se)
        self.assertEqual(h.kv(so)["SIZE"], "384x256")
        path = os.path.join(self.d, "!squad.png")
        self.assertTrue(os.path.exists(path), path)
        sheet = h.load(path)
        self.assertEqual(sheet.shape, (256, 384, 4))
        bx, by = (3 % 4) * 96, (3 // 4) * 128
        for d in range(4):
            for p in range(3):
                region = sheet[by + d * 32 : by + (d + 1) * 32, bx + p * 32 : bx + (p + 1) * 32]
                self.assertTrue(np.array_equal(region, self.frame(d, p)), (d, p))
        self.assertEqual(sheet[5, 5, 3], 0, "outside the slot stays transparent")
        self.assertEqual(sheet[100, 300, 3], 255, "inside the slot is opaque")


class GifTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = h.tmp()
        raw = h.save(character_raw(), os.path.join(cls.d, "raw.png"))
        cls.frames = os.path.join(cls.d, "frames")
        code, _, se = run_frames(raw, cls.frames)
        if code != 0:
            raise AssertionError(se)

    def test_sequence_loop_duration_and_transparency(self):
        out = os.path.join(self.d, "walk.gif")
        files = [os.path.join(self.frames, "r0c%d.png" % c) for c in range(3)]
        code, so, se = h.run_cli("gif", *files, "--out", out, "--sequence", "1,0,1,2")
        self.assertEqual(code, 0, se)
        kv = h.kv(so)
        self.assertEqual(kv["FRAMES"], "4")
        self.assertEqual(kv["OUT"], out)
        with Image.open(out) as img:
            self.assertEqual(int(getattr(img, "n_frames", 1)), 4)
            self.assertEqual(img.size, (96, 128))
            self.assertEqual(img.info.get("duration"), 150)
            self.assertEqual(img.info.get("loop"), 0)
            first = np.array(img.convert("RGBA"))
        self.assertEqual(first[0, 0, 3], 0, "transparent background stays transparent")

    def test_colored_background_fills_transparent_pixels(self):
        out = os.path.join(self.d, "bg.gif")
        files = [os.path.join(self.frames, "r1c%d.png" % c) for c in range(2)]
        code, _, se = h.run_cli("gif", *files, "--out", out, "--bg", "#204080", "--scale", "2", "--duration", "100")
        self.assertEqual(code, 0, se)
        with Image.open(out) as img:
            self.assertEqual(int(getattr(img, "n_frames", 1)), 2)
            self.assertEqual(img.size, (48, 64))
            self.assertEqual(img.info.get("duration"), 100)
            first = np.array(img.convert("RGBA"))
        self.assertTrue((first[..., 3] == 255).all())
        self.assertEqual(tuple(first[0, 0, :3]), (32, 64, 128))


if __name__ == "__main__":
    unittest.main()
