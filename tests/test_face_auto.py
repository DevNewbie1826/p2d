import os
import tempfile
import unittest

import numpy as np

import helpers as h
from p2d_lib import face as gate
from test_face import face, SKIN, EYE


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def full_subject():
    a = face()
    a[16:30, 8:16] = (100, 100, 120, 255)
    return a


class FaceAutoTest(unittest.TestCase):
    def test_detects_front_cores_without_coordinates(self):
        a = full_subject()
        result = gate.detect_face(a)
        self.assertEqual(result["eyes"], [[(9, 11)], [(14, 11)]])
        skin = result["skin"]
        self.assertIsNotNone(skin)
        assert skin is not None
        x, y = skin
        self.assertEqual(tuple(a[y, x]), SKIN)
        self.assertFalse(result["reason"])

    def test_real_front_and_side_frames_pass(self):
        for name, count in (("rm2k-down.png", 2), ("rm2k-right.png", 1),
                            ("rm2k-knight-down.png", 2), ("rm2k-blue-down.png", 2)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                code, out, err = h.run_cli(
                    "face", os.path.join(FIXTURES, name), "--auto", "--key", "#009392",
                    "--out", os.path.join(d, "crop.png"))
                values = h.kv(out)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(values["RESULT"], "PASS")
                self.assertEqual(int(values["EYES"]), count)
                self.assertIn("SKIN", values)
                self.assertIn("EYE_CANDIDATES", values)
                self.assertTrue(os.path.isfile(values["CROP"]))

    def test_eyes_in_hair_fail_with_repair_positions(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = h.run_cli(
                "face", os.path.join(FIXTURES, "knight-bad-16.png"), "--auto",
                "--out", os.path.join(d, "crop.png"))
            values = h.kv(out)
            self.assertEqual(code, 1, out + err)
            self.assertEqual(values["RESULT"], "FAIL")
            self.assertIn("HINT", values)
            self.assertRegex(values["HINT"], r"\d+,\d+.*\d+,\d+")

    def test_missing_front_eye_is_not_accepted_as_side(self):
        a = full_subject()
        a[11, 14] = SKIN
        result = gate.detect_face(a)
        self.assertTrue(result["reason"])

    def test_no_skin_region_fails_with_hint(self):
        with tempfile.TemporaryDirectory() as d:
            p = h.save(np.zeros((32, 24, 4), np.uint8), os.path.join(d, "blank.png"))
            code, out, err = h.run_cli("face", p, "--auto", "--out", os.path.join(d, "crop.png"))
            self.assertEqual(code, 1, out + err)
            self.assertEqual(h.kv(out)["RESULT"], "FAIL")
            self.assertIn("HINT", h.kv(out))

    def test_skin_hint_uses_a_real_skin_coordinate(self):
        result = gate.detect_face(full_subject(), skin_hint=(10, 13))
        self.assertEqual(result["skin"], (10, 13))
        self.assertEqual(result["eyes"], [[(9, 11)], [(14, 11)]])


class EyePairTest(unittest.TestCase):
    def test_asymmetric_knight_fails_in_both_modes(self):
        for flags in (("--auto",), ("--eyes", "10,10", "13,10", "13,11", "--skin", "11,11")):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                code, out, err = h.run_cli(
                    "face", os.path.join(FIXTURES, "knight-asym-16.png"), *flags,
                    "--out", os.path.join(d, "crop.png"))
                self.assertEqual(code, 1, out + err)
                self.assertEqual(h.kv(out)["RESULT"], "FAIL")
                self.assertEqual(h.kv(out)["EYE_PAIR"], "FAIL front eyes differ in shape/height")

    def test_equal_size_different_shape_front_eyes_fail(self):
        a = face()
        a[12, 9] = EYE
        a[11, 15] = EYE
        with tempfile.TemporaryDirectory() as d:
            p = h.save(a, os.path.join(d, "shape.png"))
            code, out, _ = h.run_cli(
                "face", p, "--eyes", "9,11", "9,12", "14,11", "15,11", "--skin", "10,13")
            self.assertEqual(code, 1, out)
            self.assertEqual(h.kv(out)["EYE_PAIR"], "FAIL front eyes differ in shape/height")

    def test_same_shape_at_different_heights_fails(self):
        a = full_subject()
        a[11, 14] = SKIN
        a[12, 14] = EYE
        with tempfile.TemporaryDirectory() as d:
            p = h.save(a, os.path.join(d, "height.png"))
            code, out, _ = h.run_cli("face", p, "--auto")
            self.assertEqual(code, 1, out)
            self.assertEqual(h.kv(out)["EYE_PAIR"], "FAIL front eyes differ in shape/height")


if __name__ == "__main__":
    unittest.main()
