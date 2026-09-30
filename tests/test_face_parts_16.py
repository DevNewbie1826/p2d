"""Validate the native-pixel face library without depending on the stamp engine."""

import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "skills/p2d/scripts/p2d_lib/face_parts/16.json"
FIXTURES = ROOT / "tests/fixtures/face16"
ROLES = set(".sSldiwhpcmt")
FRONT_EYES = {
    "normal", "closed", "wink-l", "wink-r", "angry", "sad", "surprised",
    "happy", "patch-l", "patch-r", "scar-l", "scar-r", "one-eyed-l", "one-eyed-r",
}
SIDE_EYES = {"normal", "closed", "angry", "happy", "patch", "eat"}
MOUTHS = {"none", "neutral", "smile", "open", "eat", "frown"}


class FaceParts16Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with LIBRARY.open(encoding="utf-8") as stream:
            cls.library = json.load(stream)

    def parts(self):
        for facing in ("front", "left"):
            for kind in ("eyes", "brows", "mouth"):
                for name, part in self.library["facings"][facing].get(kind, {}).items():
                    yield facing, kind, name, part

    def test_required_expressions_and_facings(self):
        self.assertEqual(self.library["px"], 16)
        self.assertEqual(self.library["frame"], [24, 32])
        self.assertEqual(self.library["facings"]["right"], "mirror-of-left")
        for facing, names in (("front", FRONT_EYES), ("left", SIDE_EYES)):
            with self.subTest(facing=facing):
                data = self.library["facings"][facing]
                self.assertIsInstance(data["anchor"], str)
                self.assertTrue(data["anchor"])
                self.assertLessEqual(names, data["eyes"].keys())
                self.assertLessEqual(MOUTHS, data["mouth"].keys())
        self.assertLessEqual(
            FRONT_EYES, self.library["facings"]["front"]["brows"].keys()
        )

    def test_rectangular_grids_offsets_and_roles(self):
        for facing, kind, name, part in self.parts():
            with self.subTest(facing=facing, kind=kind, name=name):
                if kind == "mouth":
                    shapes = [part]
                elif facing == "front":
                    self.assertIn("left", part)
                    self.assertIn("right", part)
                    shapes = [part["left"]]
                    if part["right"] != "mirror":
                        self.assertIsInstance(part["right"], dict)
                        shapes.append(part["right"])
                else:
                    shapes = [part["eye"]]
                for shape in shapes:
                    self.assertEqual(len(shape["at"]), 2)
                    self.assertTrue(all(type(v) is int for v in shape["at"]))
                    grid = shape["grid"]
                    self.assertIsInstance(grid, list)
                    self.assertTrue(grid)
                    self.assertTrue(all(isinstance(row, str) and row for row in grid))
                    self.assertEqual(len({len(row) for row in grid}), 1)
                    self.assertLessEqual(set("".join(grid)), ROLES)

    def test_provenance_and_derivation_roots(self):
        sources = self.library["sources"]
        ids = {source["id"] for source in sources}
        self.assertEqual(len(ids), len(sources))
        for source in sources:
            self.assertEqual(Path(source["path"]).suffix, ".png")
            self.assertTrue(source["note"])
        for facing, kind, name, part in self.parts():
            with self.subTest(facing=facing, kind=kind, name=name):
                provenance = part["source"]
                if "id" in provenance:
                    self.assertEqual(set(provenance), {"id", "file", "box"})
                    self.assertIn(provenance["id"], ids)
                    self.assertEqual(Path(provenance["file"]).name, provenance["file"])
                else:
                    self.assertEqual(set(provenance), {"derived_from", "how"})
                    self.assertIsInstance(provenance["how"], str)
                    self.assertTrue(provenance["how"].strip())
                    self.assertNotIn("\n", provenance["how"])
                    visited = {name}
                    while "derived_from" in provenance:
                        parent = provenance["derived_from"]
                        self.assertNotIn(parent, visited, "cyclic derivation")
                        visited.add(parent)
                        catalog = self.library["facings"][facing][kind]
                        self.assertIn(parent, catalog)
                        provenance = catalog[parent]["source"]
                    self.assertIn(provenance["id"], ids)

    def test_source_boxes_are_inside_original_fixture(self):
        for facing, kind, name, part in self.parts():
            provenance = part["source"]
            if "file" not in provenance:
                continue
            with self.subTest(facing=facing, kind=kind, name=name):
                path = FIXTURES / provenance["file"]
                if not path.is_file():
                    self.skipTest(f"optional original fixture absent: {path}")
                box = provenance["box"]
                self.assertEqual(len(box), 4)
                self.assertTrue(all(type(v) is int for v in box))
                x, y, width, height = box
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                with Image.open(path) as original:
                    self.assertLessEqual(x + width, original.width)
                    self.assertLessEqual(y + height, original.height)

    def test_rm2000_normal_is_pixel_exact(self):
        """Catch a plausible but invented eye shape by checking original RGB pixels."""
        path = FIXTURES / "char-07-down-c1.png"
        if not path.is_file():
            self.skipTest(f"optional original fixture absent: {path}")
        with Image.open(path) as original:
            pixels = np.array(original.convert("RGB"))
        palette = {
            (0, 0, 0): "l",
            (176, 215, 255): "w",
            (33, 37, 145): "d",
            (255, 255, 255): "w",
            (29, 115, 214): "i",
        }
        eyes = self.library["facings"]["front"]["eyes"]["normal"]
        for side, x in (("left", 9), ("right", 13)):
            measured = [
                "".join(
                    palette[(int(pixel[0]), int(pixel[1]), int(pixel[2]))]
                    for pixel in row
                )
                for row in pixels[14:17, x:x + 2]
            ]
            self.assertEqual(eyes[side]["grid"], measured)
        self.assertEqual(eyes["left"]["at"], [-3, -1])
        self.assertEqual(eyes["right"]["at"], [1, -1])

    def test_small_expression_role_invariants(self):
        eyes = self.library["facings"]["front"]["eyes"]
        normal = eyes["normal"]
        for name, affected, other in (
            ("wink-l", "left", "right"), ("wink-r", "right", "left"),
            ("patch-l", "left", "right"), ("patch-r", "right", "left"),
            ("scar-l", "left", "right"), ("scar-r", "right", "left"),
            ("one-eyed-l", "left", "right"), ("one-eyed-r", "right", "left"),
        ):
            with self.subTest(name=name):
                part = eyes[name]
                self.assertEqual(part[other], normal[other])
                roles = "".join(part[affected]["grid"])
                if name.startswith("one-eyed"):
                    self.assertNotIn("d", roles)
                    self.assertNotIn("i", roles)
                    self.assertNotIn("w", roles)
                    self.assertEqual(roles.count("c"), 3)
                elif name.startswith("scar"):
                    self.assertEqual(roles.count("c"), 3)
                elif name.startswith("patch"):
                    self.assertEqual(roles.count("p"), 7)
                else:
                    self.assertLessEqual(set(roles), set("ls"))
        for facing in ("front", "left"):
            mouths = self.library["facings"][facing]["mouth"]
            self.assertIn("t", "".join(mouths["eat"]["grid"]))
            self.assertLessEqual(set("".join(mouths["none"]["grid"])), {"."})


if __name__ == "__main__":
    unittest.main()
