"""Validate the original-backed 48px face-part data, independently of face.py."""

import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "skills/p2d/scripts/p2d_lib/face_parts/48.json"
FRONT = {
    "normal", "closed", "wink-l", "wink-r", "angry", "sad", "surprised",
    "happy", "patch-l", "patch-r", "scar-l", "scar-r", "one-eyed-l", "one-eyed-r",
}
SIDE = {"normal", "closed", "angry", "happy", "patch", "eat"}
MOUTHS = {"none", "neutral", "smile", "open", "eat", "frown"}
ROLES = set(".sSldiwhpcmt")
ORIGINALS = {
    "spritesheet.png":
        "1d7829c4560e1be8358cb9df2f218dcc7214c8a8715f39cca102b77f7e913c22",
    "spritesheet 2.png":
        "27ea091f8851525823813166dcfeda039781c228b81a40ffb6927f7adb6236f3",
    "walk-animation.png":
        "f9719e519308457b5cc3b176a7b3e1b2191708eac2ce9455c37755f4fae362a5",
    "Shisu_Model-Sheet.png":
        "9ec789377d5de3578ce9561483833741fc5023be5a540b26b860c74be0731175",
}


class FaceParts48Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with LIBRARY.open(encoding="utf-8") as stream:
            cls.library = json.load(stream)

    def test_frame_and_required_expressions(self):
        self.assertEqual(self.library["px"], 48)
        self.assertEqual(self.library["frame"], [48, 48])
        self.assertEqual(set(self.library["facings"]), {"front", "left", "right"})
        self.assertEqual(self.library["facings"]["right"], "mirror-of-left")
        for facing, expressions in (("front", FRONT), ("left", SIDE)):
            data = self.library["facings"][facing]
            self.assertIsInstance(data["anchor"], str)
            self.assertTrue(data["anchor"])
            for group in ("eyes", "brows"):
                self.assertTrue(expressions <= set(data[group]))
            self.assertTrue(MOUTHS <= set(data["mouth"]))

    def test_original_fixture_bytes_and_native_cells(self):
        ids = set()
        names = set()
        for source in self.library["sources"]:
            self.assertNotIn(source["id"], ids)
            ids.add(source["id"])
            path = ROOT / source["path"]
            self.assertEqual(path.parent, ROOT / "tests/fixtures/face48")
            names.add(path.name)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), ORIGINALS[path.name]
            )
            with Image.open(path) as image:
                self.assertEqual(image.width % 48, 0)
                self.assertEqual(image.height % 48, 0)
        self.assertEqual(names, set(ORIGINALS))

    def check_grid(self, shape):
        self.assertEqual(set(shape), {"at", "grid"})
        at, rows = shape["at"], shape["grid"]
        self.assertIsInstance(at, list)
        self.assertEqual(len(at), 2)
        self.assertTrue(all(type(value) is int for value in at))
        self.assertIsInstance(rows, list)
        self.assertTrue(rows)
        self.assertTrue(all(isinstance(row, str) and row for row in rows))
        width = len(rows[0])
        self.assertTrue(all(len(row) == width for row in rows))
        self.assertTrue(set("".join(rows)) <= ROLES)
        # The preview's (24, 21) anchor must fit every part without clipping.
        self.assertGreaterEqual(24 + at[0], 0)
        self.assertGreaterEqual(21 + at[1], 0)
        self.assertLessEqual(24 + at[0] + width, 48)
        self.assertLessEqual(21 + at[1] + len(rows), 48)

    def test_rectangular_role_grids_and_part_shapes(self):
        for facing in ("front", "left"):
            for group in ("eyes", "brows", "mouth"):
                for expression, part in self.library["facings"][facing][group].items():
                    with self.subTest(facing=facing, group=group, expression=expression):
                        if group == "mouth":
                            self.assertEqual(set(part), {"at", "grid", "source"})
                            self.check_grid({key: part[key] for key in ("at", "grid")})
                        elif facing == "front":
                            self.assertEqual(set(part), {"left", "right", "source"})
                            self.check_grid(part["left"])
                            if part["right"] != "mirror":
                                self.check_grid(part["right"])
                        else:
                            self.assertEqual(set(part), {"eye", "source"})
                            self.check_grid(part["eye"])

    def test_every_part_has_original_box_or_extracted_base(self):
        sources = {source["id"]: source for source in self.library["sources"]}
        for facing in ("front", "left"):
            for group in ("eyes", "brows", "mouth"):
                parts = self.library["facings"][facing][group]
                for expression, part in parts.items():
                    with self.subTest(facing=facing, group=group, expression=expression):
                        citation = part["source"]
                        if "derived_from" in citation:
                            self.assertEqual(set(citation), {"derived_from", "how"})
                            self.assertIn(citation["derived_from"], parts)
                            base = parts[citation["derived_from"]]["source"]
                            self.assertIn("id", base)  # No dangling/cyclic derivations.
                            self.assertIsInstance(citation["how"], str)
                            self.assertTrue(citation["how"].strip())
                            self.assertNotIn("\n", citation["how"])
                        else:
                            self.assertEqual(set(citation), {"id", "file", "box"})
                            self.assertIn(citation["id"], sources)
                            path = ROOT / sources[citation["id"]]["path"]
                            self.assertEqual(citation["file"], path.name)
                            self.assertEqual(len(citation["box"]), 4)
                            self.assertTrue(
                                all(type(value) is int for value in citation["box"])
                            )
                            x, y, width, height = citation["box"]
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertGreater(width, 0)
                            self.assertGreater(height, 0)
                            with Image.open(path) as image:
                                self.assertLessEqual(x + width, image.width)
                                self.assertLessEqual(y + height, image.height)
                            shapes = (
                                [part] if group == "mouth" else
                                [part["left"], part["right"]] if facing == "front" else
                                [part["eye"]]
                            )
                            for shape in shapes:
                                if shape != "mirror":
                                    self.assertLessEqual(len(shape["grid"][0]), width)
                                    self.assertLessEqual(len(shape["grid"]), height)

    def test_expression_semantics(self):
        front = self.library["facings"]["front"]["eyes"]
        for suffix, target, other in (("l", "left", "right"), ("r", "right", "left")):
            self.assertEqual(front["wink-" + suffix][other], front["normal"][other])
            self.assertEqual(front["wink-" + suffix][target], front["closed"][target])
            for expression in ("patch-", "scar-", "one-eyed-"):
                self.assertEqual(
                    front[expression + suffix][other], front["normal"][other]
                )
            lost = "".join(front["one-eyed-" + suffix][target]["grid"])
            self.assertIn("c", lost)
            self.assertIn("l", lost)
            self.assertFalse(set(lost) & set("diwh"))
            self.assertIn("p", "".join(front["patch-" + suffix][target]["grid"]))
        for facing in ("front", "left"):
            mouths = self.library["facings"][facing]["mouth"]
            self.assertEqual(set("".join(mouths["none"]["grid"])), {"."})
            self.assertIn("t", "".join(mouths["eat"]["grid"]))
            self.assertIn("m", "".join(mouths["eat"]["grid"]))


if __name__ == "__main__":
    unittest.main()
