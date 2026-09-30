import json
import os
import tempfile
import unittest

import helpers as h


class CallConsentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p2d-consent-")
        self.addCleanup(self.temp.cleanup)
        self.dir = os.path.join(self.temp.name, "pack")
        code, out, err = h.run_cli("pack", "init", self.dir, "--name", "c", "--px", "16")
        self.assertEqual(code, 0, out + err)

    def attempt(self, *extra):
        return h.run_cli("pack", "attempt", self.dir, "--name", "t", "--kind", "tile", "--px", "16", *extra)

    def fill(self):
        for _ in range(3):
            code, out, err = self.attempt()
            self.assertEqual(code, 0, out + err)
            h.save(h.native_art(4, 4, h.DUNGEON), h.kv(out)["OUTPUT"])

    def test_raising_the_cap_without_quoted_consent_is_rejected(self):
        self.fill()
        code, out, err = self.attempt("--max-calls", "4")
        self.assertEqual(code, 2, out + err)
        self.assertIn("--user-consent", err)

    def test_quoted_consent_is_recorded(self):
        self.fill()
        code, out, err = self.attempt("--max-calls", "4", "--user-consent", "네 한 번 더 해도 돼")
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(self.dir, "pack.json")) as f:
            data = json.load(f)
        attempts = data["assets"]["t"]["sizes"]["16"]["attempts"]
        self.assertEqual(attempts[-1]["user_consent"], "네 한 번 더 해도 돼")

    def test_gen_also_requires_consent_above_default(self):
        code, out, err = h.run_cli("gen", self.dir, "--name", "t", "--px", "16", "--prompt-file", __file__,
                                   "--max-calls", "5", "--runner", "true")
        self.assertEqual(code, 2, out + err)
        self.assertIn("--user-consent", err)
