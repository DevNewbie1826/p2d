import os
import unittest

import numpy as np
from PIL import Image

import helpers as h

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def colors(path):
    a = np.array(Image.open(path).convert("RGBA"))
    return {tuple(c) for c in a[a[..., 3] > 0][:, :3]}


def left_and_mirrored_right_eye_boxes(path, top, lx, rx):
    a = np.array(Image.open(path).convert("RGBA")).astype(int)
    left = a[top - 1:top + 2, lx - 1:lx + 1, :3]
    right = a[top - 1:top + 2, rx:rx + 2, :3][:, ::-1]
    return left, right


class FaceStampTest(unittest.TestCase):
    def stamp(self, name):
        src = os.path.join(FIX, name)
        out = os.path.join(h.tmp(), "stamped.png")
        code, text, err = h.run_cli("face", src, "--stamp", out)
        return src, out, code, text, err

    def test_stamp_repairs_asymmetric_knight_and_passes_gate(self):
        src, out, code, text, err = self.stamp("knight-asym-16.png")
        self.assertEqual(code, 0, text + err)
        kv = h.kv(text)
        self.assertIn("STAMPED", kv)
        code, text, err = h.run_cli("face", out, "--auto")
        self.assertEqual(code, 0, text + err)
        self.assertIn("EYE_PAIR: PASS", text)

    def test_stamped_eyes_are_mirror_identical_and_rm2k_shaped(self):
        src, out, code, text, err = self.stamp("knight-asym-16.png")
        self.assertEqual(code, 0, text + err)
        kv = h.kv(text)
        lx, rx, top = (int(v) for v in kv["STAMPED"].split()[0:3])
        left, right = left_and_mirrored_right_eye_boxes(out, top, lx, rx)
        self.assertTrue(np.array_equal(left, right), "left eye must equal mirrored right eye")
        a = np.array(Image.open(out).convert("RGBA")).astype(int)
        lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        lid, iris_top, iris_bottom, sclera = a[top - 1, lx], a[top, lx], a[top + 1, lx], a[top + 1, lx - 1]
        self.assertLess(lum(lid), lum(iris_bottom))
        self.assertLess(lum(iris_top), lum(iris_bottom))
        self.assertGreater(lum(sclera), lum(iris_bottom))

    def test_stamp_uses_only_existing_colors(self):
        src, out, code, text, err = self.stamp("knight-asym-16.png")
        self.assertEqual(code, 0, text + err)
        self.assertTrue(colors(out) <= colors(src))

    def test_stamp_with_eye_colors_draws_bright_iris_and_white_sclera(self):
        src = os.path.join(FIX, "knight-asym-16.png")
        out = os.path.join(h.tmp(), "stamped.png")
        code, text, err = h.run_cli("face", src, "--stamp", out, "--eye-colors", "#212591,#1D73D6,#FFFFFF")
        self.assertEqual(code, 0, text + err)
        self.assertTrue({(0x21, 0x25, 0x91), (0x1D, 0x73, 0xD6), (0xFF, 0xFF, 0xFF)} <= colors(out))
        self.assertIn("EYE_COLORS_ADDED", text)
        code, text, err = h.run_cli("face", out, "--auto")
        self.assertEqual(code, 0, text + err)

    def test_stamp_refuses_non_16px_frames(self):
        big = h.save(np.zeros((48, 48, 4), np.uint8), os.path.join(h.tmp(), "b.png"))
        code, text, err = h.run_cli("face", big, "--stamp", os.path.join(h.tmp(), "o.png"))
        self.assertEqual(code, 2, text + err)
        self.assertIn("24x32", err)


if __name__ == "__main__":
    unittest.main()
