"""Validate the native-32 role library against its original PNG fixtures."""

import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image

ROOT: Final = Path(__file__).resolve().parents[1]
LIBRARY: Final = ROOT / "skills/p2d/scripts/p2d_lib/face_parts/32.json"
FIXTURES: Final = ROOT / "tests/fixtures/face32"
ROLES: Final = set(".sSldiwhpcmt")
FRONT: Final = {
    "normal", "closed", "wink-l", "wink-r", "angry", "sad", "surprised",
    "happy", "patch-l", "patch-r", "scar-l", "scar-r",
    "one-eyed-l", "one-eyed-r",
}
SIDE: Final = {"normal", "closed", "angry", "happy", "patch", "eat"}
MOUTHS: Final = {"none", "neutral", "smile", "open", "eat", "frown"}


class FaceParts32Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.library = json.loads(LIBRARY.read_text())

    def test_native_frame_and_facings(self) -> None:
        data = self.library
        self.assertEqual(set(data), {"px", "frame", "sources", "facings", "spacing"})
        self.assertEqual(data["px"], 32)
        self.assertEqual(data["frame"], [32, 32])
        self.assertEqual(set(data["facings"]), {"front", "left", "right"})
        self.assertEqual(data["facings"]["right"], "mirror-of-left")

    def test_required_expressions(self) -> None:
        for facing, required in (("front", FRONT), ("left", SIDE)):
            parts = self.library["facings"][facing]
            with self.subTest(facing=facing):
                self.assertEqual(set(parts), {"anchor", "eyes", "brows", "mouth"})
                self.assertTrue(parts["anchor"].strip())
                self.assertTrue(required <= parts["eyes"].keys())
                self.assertTrue(required <= parts["brows"].keys())
                self.assertTrue(MOUTHS <= parts["mouth"].keys())

    def test_rectangular_role_grids_and_integer_offsets(self) -> None:
        for facing in ("front", "left"):
            for group in ("eyes", "brows", "mouth"):
                for name, part in self.library["facings"][facing][group].items():
                    with self.subTest(facing=facing, group=group, name=name):
                        if group == "mouth":
                            self.assertEqual(set(part), {"at", "grid", "source"})
                            shapes = [part]
                        elif facing == "front":
                            self.assertEqual(set(part), {"left", "right", "source"})
                            shapes = [part["left"]]
                            if part["right"] == "mirror":
                                self.assertNotEqual(part["left"]["grid"], ["."])
                            else:
                                shapes.append(part["right"])
                        else:
                            self.assertEqual(set(part), {"eye", "source"})
                            shapes = [part["eye"]]
                        for shape in shapes:
                            self.assertEqual(set(shape) - {"source"}, {"at", "grid"})
                            self.assertEqual(len(shape["at"]), 2)
                            self.assertTrue(all(type(n) is int for n in shape["at"]))
                            grid = shape["grid"]
                            self.assertGreater(len(grid), 0)
                            self.assertGreater(len(grid[0]), 0)
                            self.assertTrue(all(len(row) == len(grid[0]) for row in grid))
                            self.assertTrue(set("".join(grid)) <= ROLES)
                            # Every shape must fit a 32px frame when anchored at (16,13).
                            x, y = shape["at"]
                            self.assertGreaterEqual(16 + x, 0)
                            self.assertGreaterEqual(13 + y, 0)
                            self.assertLessEqual(16 + x + len(grid[0]), 32)
                            self.assertLessEqual(13 + y + len(grid), 32)

    def test_sources_are_original_native_png_copies(self) -> None:
        sources = self.library["sources"]
        self.assertEqual(len({s["id"] for s in sources}), len(sources))
        self.assertEqual({s["path"] for s in sources},
                         {str(p.relative_to(ROOT)) for p in FIXTURES.glob("*.png")})
        for source in sources:
            with self.subTest(source=source["id"]):
                self.assertEqual(set(source), {"id", "path", "note"})
                path = ROOT / source["path"]
                self.assertEqual(path.parent, FIXTURES)
                self.assertNotIn("-8x", path.name)
                checksum = re.search(r"sha256=([0-9a-f]{64})", source["note"])
                assert checksum is not None, source["id"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 checksum.group(1))
                with Image.open(path) as image:
                    self.assertIn(image.size, {(96, 128), (64, 96)})

    def test_every_part_has_bounded_source_or_direct_derivation(self) -> None:
        sources = {s["id"]: s for s in self.library["sources"]}
        for facing in ("front", "left"):
            for group in ("eyes", "brows", "mouth"):
                parts = self.library["facings"][facing][group]
                for name, part in parts.items():
                    with self.subTest(facing=facing, group=group, name=name):
                        source = part["source"]
                        if "derived_from" in source:
                            self.assertEqual(set(source), {"derived_from", "how"})
                            self.assertIn(source["derived_from"], parts)
                            self.assertIn("id", parts[source["derived_from"]]["source"])
                            self.assertTrue(source["how"].strip())
                            self.assertNotIn("\n", source["how"])
                        else:
                            self.assertEqual(set(source), {"id", "file", "box"})
                            self.assertIn(source["id"], sources)
                            path = ROOT / sources[source["id"]]["path"]
                            self.assertEqual(path.name, source["file"])
                            self.assertEqual(len(source["box"]), 4)
                            self.assertTrue(all(type(n) is int for n in source["box"]))
                            x, y, w, h = source["box"]
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertGreater(w, 0)
                            self.assertGreater(h, 0)
                            with Image.open(path) as image:
                                self.assertLessEqual(x + w, image.width)
                                self.assertLessEqual(y + h, image.height)
                                self.assertTrue(np.array(image.convert("RGBA"))[
                                    y:y + h, x:x + w, 3].any())

    def test_measured_normal_roles_match_original_pixels(self) -> None:
        palette = {
            (83, 71, 33): "l", (46, 30, 34): "d",
            (92, 46, 0): "d", (150, 79, 0): "i",
            (217, 217, 217): "w", (217, 217, 221): "w",
            (242, 242, 242): "w", (146, 138, 140): "w",
            (255, 255, 255): "w", (238, 190, 147): ".",
            (255, 225, 175): ".",
        }
        with Image.open(FIXTURES / "Male 01-1.png") as image:
            pixels = np.array(image.convert("RGBA"))
        for facing, key, x, y in (
            ("front", "left", 43, 12), ("front", "right", 51, 12),
            ("left", "eye", 44, 44),
        ):
            expected = ["".join(palette[tuple(c[:3])] for c in row)
                        for row in pixels[y:y + 5, x:x + 3]]
            with self.subTest(facing=facing, key=key):
                actual = self.library["facings"][facing]["eyes"]["normal"][key]
                self.assertEqual(actual["grid"], expected)
                self.assertEqual(sum(row.count("d") for row in actual["grid"][:3]), 2)

    def test_knight_eye_is_one_native_pixel(self) -> None:
        part = self.library["facings"]["front"]["eyes"]["normal-knight"]
        with Image.open(FIXTURES / "knight_walk4frame.png.png") as image:
            pixels = np.array(image.convert("RGBA"))
        for key, x in (("left", 18), ("right", 20)):
            self.assertEqual(part[key]["grid"], ["i"])
            self.assertEqual(tuple(pixels[9, x, :3]), (83, 138, 238))

    def test_lost_eye_and_eating_keep_distinct_roles(self) -> None:
        eyes = self.library["facings"]["front"]["eyes"]
        for name, lost, retained in (
            ("one-eyed-l", "left", "right"),
            ("one-eyed-r", "right", "left"),
        ):
            with self.subTest(expression=name):
                self.assertEqual(eyes[name][retained], eyes["normal"][retained])
                roles = set("".join(eyes[name][lost]["grid"]))
                self.assertTrue({"l", "c", "s"} <= roles)
                self.assertFalse({"d", "i", "w", "h"} & roles)
        for facing in ("front", "left"):
            grid = self.library["facings"][facing]["mouth"]["eat"]["grid"]
            self.assertTrue({"m", "t"} <= set("".join(grid)))

    def test_required_mouths_leave_normal_eyes_clear(self) -> None:
        for facing in ("front", "left"):
            parts = self.library["facings"][facing]
            normal = parts["eyes"]["normal"]
            shapes = [normal["left"], normal["right"]] if facing == "front" else [
                normal["eye"]]
            eye_bottom = max(s["at"][1] + len(s["grid"]) - 1 for s in shapes)
            for name in MOUTHS - {"none"}:
                with self.subTest(facing=facing, expression=name):
                    self.assertGreater(parts["mouth"][name]["at"][1], eye_bottom)


if __name__ == "__main__":
    unittest.main()
