import os
import unittest

import numpy as np

import helpers as h

SKIN = (240, 200, 160, 255)
HAIR = (200, 200, 210, 255)
EYE = (30, 40, 90, 255)
OUT = (20, 20, 20, 255)


def face(eyes_visible=True):
    a = np.zeros((32, 24, 4), np.uint8)
    a[2:8, 6:18] = HAIR
    a[8:16, 6:18] = SKIN
    a[8:16, 5] = OUT
    a[8:16, 18] = OUT
    if eyes_visible:
        a[11, 9] = EYE
        a[11, 14] = EYE
    else:
        a[8:12, 6:18] = HAIR
        a[11, 9] = EYE
        a[11, 14] = EYE
    return a


class FaceTest(unittest.TestCase):
    def test_visible_eyes_on_skin_pass(self):
        d = h.tmp()
        p = h.save(face(True), os.path.join(d, "f.png"))
        code, out, err = h.run_cli("face", p, "--eyes", "9,11", "14,11", "--skin", "10,13", "--scale", "8")
        self.assertEqual(code, 0, err)
        kv = h.kv(out)
        self.assertEqual(kv["RESULT"], "PASS")
        self.assertTrue(os.path.exists(kv["CROP"]))

    def test_eyes_buried_in_hair_fail(self):
        d = h.tmp()
        p = h.save(face(False), os.path.join(d, "f.png"))
        code, out, _ = h.run_cli("face", p, "--eyes", "9,11", "14,11", "--skin", "10,13")
        self.assertEqual(code, 1)
        self.assertEqual(h.kv(out)["RESULT"], "FAIL")
        self.assertIn("not on skin", out)

    def test_eye_same_as_skin_fails(self):
        d = h.tmp()
        a = face(True)
        a[11, 9] = SKIN
        p = h.save(a, os.path.join(d, "f.png"))
        code, out, _ = h.run_cli("face", p, "--eyes", "9,11", "14,11", "--skin", "10,13")
        self.assertEqual(code, 1)
        self.assertIn("contrast", out)


if __name__ == "__main__":
    unittest.main()
