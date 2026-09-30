import os
import unittest

import numpy as np

import helpers as h

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def body(w, hgt):
    a = np.zeros((32, 24, 4), np.uint8)
    x0 = (24 - w) // 2
    a[31 - hgt:31, x0:x0 + w] = (200, 180, 160, 255)
    a[31 - hgt:31, x0] = (20, 20, 20, 255)
    return a


class ProportionTest(unittest.TestCase):
    def run_check(self, img, *extra):
        p = h.save(img, os.path.join(h.tmp(), "f.png"))
        return h.run_cli("check", p, "--kind", "frame", "--size", "24x32", *extra)

    def test_thin_tall_16px_character_fails_chibi_proportion(self):
        code, out, err = self.run_check(body(13, 26), "--master")
        self.assertEqual(code, 1, out + err)
        self.assertIn("PROPORTION", out)
        self.assertIn("chibi", out)

    def test_original_like_proportion_passes(self):
        code, out, err = self.run_check(body(17, 25), "--master")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("FAIL_REASON: PROPORTION", out)

    def test_side_original_passes_plain_frame_check(self):
        a = h.load(os.path.join(FIX, "face16", "char-01-left-c1.png"))
        key = a[0, 0, :3].copy()
        a[np.all(a[..., :3] == key, axis=2), 3] = 0
        code, out, err = self.run_check(a, "--max-colors", "28")
        self.assertEqual(code, 0, out + err)

    def test_real_rm2k_frame_passes(self):
        p = os.path.join(FIX, "rm2k-down.png")
        code, out, err = h.run_cli("check", p, "--kind", "frame", "--size", "24x32", "--key", "#009392")
        self.assertNotIn("PROPORTION", out.replace("PROPORTION:", ""))
