import subprocess
import sys
import unittest

import helpers as h


class DoctorTest(unittest.TestCase):
    def test_doctor_reports_missing_dependencies(self):
        # -S hides site-packages, so Pillow/numpy are unavailable.
        proc = subprocess.run([sys.executable, "-S", h.P2D, "doctor"], capture_output=True, text=True)
        out = h.kv(proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(out.get("RESULT"), "FAIL")
        self.assertIn("pip install", proc.stdout)


if __name__ == "__main__":
    unittest.main()
