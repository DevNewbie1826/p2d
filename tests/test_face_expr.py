import glob
import colorsys
import json
import os
import re
import unittest

import numpy as np

import helpers as h
from p2d_lib.face import detect_face, _parts_for, _face_span, FaceDetection

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
PARTS = os.path.join(FIX, "face_parts_test.json")
LIBRARIES = os.path.join(h.SCRIPTS, "p2d_lib", "face_parts")

# Exact source variants that cannot reproduce their colour-collapsed masks.
# Keys are (px, facing, expression); each reason describes that source only.
UNREPRODUCIBLE = {
    (32, 'front', 'normal-pipoya-001'): 'Female 01-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-002'): 'Female 04-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-003'): 'Female 07-1.png cell (0, 0): w merges 6 pixels; minimum colour loss 6px.',
    (32, 'front', 'normal-pipoya-004'): 'Female 09-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-005'): 'Female 10-1.png cell (0, 0): w merges 6 pixels; minimum colour loss 6px.',
    (32, 'front', 'normal-pipoya-006'): 'Female 11-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-007'): 'Female 12-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-009'): 'Female 16-1.png cell (0, 0): w merges 2 pixels; d merges 2 pixels; minimum colour loss 4px.',
    (32, 'front', 'normal-pipoya-010'): 'Female 16-1.png cell (32, 0): w merges 4 pixels; d merges 2 pixels; minimum colour loss 6px.',
    (32, 'front', 'normal-pipoya-011'): 'Female 19-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-012'): 'Female 20-1.png cell (0, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-013'): 'Female 21-1.png cell (0, 0): w merges 6 pixels; d merges 4 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-pipoya-014'): 'Female 22-1.png cell (0, 0): w merges 4 pixels; d merges 2 pixels; minimum colour loss 6px.',
    (32, 'front', 'normal-pipoya-015'): 'Female 24-1.png cell (0, 0): w merges 4 pixels; minimum colour loss 4px.',
    (32, 'front', 'normal-pipoya-016'): 'Female 25-1.png cell (0, 0): w merges 12 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-017'): 'su1 Student fmale 14.png cell (0, 0): w merges 3 pixels; minimum colour loss 3px.',
    (32, 'front', 'normal-pipoya-020'): 'su1 Student fmale 15.png cell (32, 0): w merges 3 pixels; minimum colour loss 3px.',
    (32, 'front', 'normal-pipoya-021'): 'su1 Student male 01.png cell (0, 0): l merges 2 pixels; w merges 4 pixels; d merges 3 pixels; i merges 2 pixels; minimum colour loss 11px.',
    (32, 'front', 'normal-pipoya-022'): 'su1 Student male 10.png cell (0, 0): l merges 1 pixels; w merges 2 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 5px.',
    (32, 'front', 'normal-pipoya-023'): 'su1 Student male 10.png cell (32, 0): l merges 1 pixels; w merges 3 pixels; d merges 1 pixels; i merges 2 pixels; minimum colour loss 7px.',
    (32, 'front', 'normal-pipoya-024'): 'su1 Student male 10.png cell (64, 0): l merges 2 pixels; w merges 4 pixels; d merges 2 pixels; i merges 2 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-pipoya-025'): 'su1 Student male 11.png cell (0, 0): l merges 2 pixels; w merges 4 pixels; d merges 3 pixels; i merges 2 pixels; minimum colour loss 11px.',
    (32, 'front', 'normal-pipoya-026'): 'su1 Student male 11.png cell (32, 0): l merges 2 pixels; w merges 3 pixels; d merges 3 pixels; i merges 2 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-pipoya-027'): 'su1 Student male 11.png cell (64, 0): l merges 2 pixels; w merges 3 pixels; d merges 3 pixels; i merges 2 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-pipoya-028'): 'Headmaster fmale.png cell (0, 0): l merges 12 pixels; w merges 6 pixels; d merges 2 pixels; minimum colour loss 20px.',
    (32, 'front', 'normal-pipoya-029'): 'Headmaster male.png cell (0, 0): w merges 10 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-pipoya-030'): 'Teacher fmale 01.png cell (0, 0): l merges 6 pixels; w merges 6 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-031'): 'Teacher fmale 02.png cell (0, 0): l merges 8 pixels; w merges 8 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-pipoya-032'): 'Teacher male 02.png cell (0, 0): l merges 8 pixels; w merges 8 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-pipoya-033'): 'Male 01-1.png cell (0, 0): l merges 2 pixels; w merges 6 pixels; d merges 6 pixels; i merges 2 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-pipoya-034'): 'Male 09-1.png cell (0, 0): l merges 4 pixels; w merges 3 pixels; d merges 3 pixels; i merges 2 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-pipoya-035'): 'Male 13-1.png cell (0, 0): l merges 2 pixels; w merges 6 pixels; d merges 6 pixels; i merges 2 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-pipoya-036'): 'Male 14-1.png cell (0, 0): l merges 2 pixels; w merges 6 pixels; d merges 6 pixels; i merges 2 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-pipoya-037'): 'Male 17-1.png cell (0, 0): l merges 4 pixels; minimum colour loss 4px.',
    (32, 'front', 'normal-pipoya-038'): 'Male 18-1.png cell (0, 0): l merges 2 pixels; w merges 4 pixels; d merges 1 pixels; i merges 2 pixels; minimum colour loss 9px.',
    (32, 'front', 'normal-animal-cat'): 'Cat 01-1.png cell (32, 0): w merges 4 pixels; d merges 4 pixels; minimum colour loss 8px.',
    (32, 'front', 'normal-animal-dog'): 'Dog 01-1.png cell (32, 0): w merges 6 pixels; d merges 4 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-skull'): 'Enemy 04-1.png cell (32, 0): i merges 6 pixels; d merges 10 pixels; minimum colour loss 16px.',
    (32, 'front', 'normal-low-skull'): 'Enemy 06-1.png cell (32, 0): i merges 8 pixels; d merges 10 pixels; minimum colour loss 18px.',
    (32, 'front', 'normal-armored-skull'): 'Enemy 07-1.png cell (32, 0): d merges 10 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-ghost'): 'Enemy 09-1.png cell (32, 0): d merges 8 pixels; minimum colour loss 8px.',
    (32, 'front', 'normal-ice-skull'): 'Enemy 11-1.png cell (32, 0): d merges 10 pixels; minimum colour loss 10px.',
    (32, 'front', 'normal-goblin-round'): 'Enemy 18.png cell (32, 0): d merges 10 pixels; i merges 4 pixels; minimum colour loss 14px.',
    (32, 'front', 'normal-glasses'): 'pipo-charachip_otaku01.png cell (32, 0): l merges 6 pixels; minimum colour loss 6px.',
    (32, 'front', 'normal-reindeer'): 'pipo-xmaschara04.png cell (32, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'front', 'normal-snowman-tall'): 'pipo-xmaschara06.png cell (32, 0): d merges 6 pixels; i merges 1 pixels; minimum colour loss 7px.',
    (32, 'front', 'normal'): 'Male 01-1.png cell (32, 0): w merges 8 pixels; d merges 4 pixels; minimum colour loss 12px.',
    (32, 'left', 'normal-pipoya-001'): 'Female 01-1.png cell (0, 32): l merges 3 pixels; w merges 3 pixels; d merges 3 pixels; i merges 1 pixels; minimum colour loss 10px.',
    (32, 'left', 'normal-pipoya-002'): 'Female 04-1.png cell (0, 32): w merges 3 pixels; d merges 3 pixels; l merges 1 pixels; i merges 1 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-003'): 'Female 07-1.png cell (0, 32): l merges 3 pixels; w merges 2 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 7px.',
    (32, 'left', 'normal-pipoya-004'): 'Female 09-1.png cell (0, 32): w merges 3 pixels; d merges 3 pixels; i merges 4 pixels; minimum colour loss 10px.',
    (32, 'left', 'normal-pipoya-005'): 'Female 10-1.png cell (0, 32): l merges 3 pixels; w merges 2 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 7px.',
    (32, 'left', 'normal-pipoya-006'): 'Female 11-1.png cell (0, 32): l merges 3 pixels; w merges 3 pixels; d merges 3 pixels; minimum colour loss 9px.',
    (32, 'left', 'normal-pipoya-007'): 'Female 12-1.png cell (0, 32): w merges 3 pixels; d merges 2 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-011'): 'Female 19-1.png cell (0, 32): l merges 2 pixels; w merges 1 pixels; d merges 2 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-012'): 'Female 21-1.png cell (0, 32): l merges 3 pixels; w merges 3 pixels; d merges 3 pixels; minimum colour loss 9px.',
    (32, 'left', 'normal-pipoya-013'): 'Female 22-1.png cell (0, 32): l merges 3 pixels; w merges 4 pixels; d merges 2 pixels; i merges 1 pixels; minimum colour loss 10px.',
    (32, 'left', 'normal-pipoya-015'): 'Female 25-1.png cell (0, 32): w merges 8 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-016'): 'su1 Student fmale 14.png cell (64, 32): l merges 3 pixels; d merges 1 pixels; w merges 1 pixels; i merges 1 pixels; minimum colour loss 6px.',
    (32, 'left', 'normal-pipoya-018'): 'su1 Student male 01.png cell (0, 32): l merges 1 pixels; w merges 2 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-020'): 'su1 Student male 11.png cell (0, 32): l merges 1 pixels; w merges 1 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-pipoya-021'): 'Headmaster fmale.png cell (0, 32): l merges 6 pixels; w merges 2 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-022'): 'Headmaster male.png cell (0, 32): w merges 5 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-023'): 'Teacher fmale 01.png cell (0, 32): l merges 3 pixels; w merges 3 pixels; minimum colour loss 6px.',
    (32, 'left', 'normal-pipoya-024'): 'Teacher fmale 02.png cell (0, 32): l merges 4 pixels; w merges 4 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-025'): 'Teacher male 02.png cell (0, 32): w merges 4 pixels; l merges 4 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-026'): 'Male 01-1.png cell (0, 32): l merges 1 pixels; w merges 3 pixels; d merges 3 pixels; i merges 1 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-027'): 'Male 09-1.png cell (0, 32): l merges 2 pixels; d merges 1 pixels; w merges 1 pixels; i merges 1 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-028'): 'Male 12-1.png cell (0, 32): l merges 1 pixels; w merges 2 pixels; d merges 1 pixels; i merges 1 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pipoya-029'): 'Male 14-1.png cell (0, 32): l merges 1 pixels; w merges 3 pixels; d merges 3 pixels; i merges 1 pixels; minimum colour loss 8px.',
    (32, 'left', 'normal-pipoya-031'): 'Male 18-1.png cell (0, 32): l merges 1 pixels; w merges 2 pixels; i merges 1 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-animal-cat'): 'Cat 01-1.png cell (32, 32): d merges 2 pixels; w merges 2 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-animal-dog'): 'Dog 01-1.png cell (32, 32): w merges 3 pixels; d merges 2 pixels; minimum colour loss 5px.',
    (32, 'left', 'normal-pumpkin'): 'Enemy 03-1.png cell (32, 32): l merges 3 pixels; minimum colour loss 3px.',
    (32, 'left', 'normal-skull'): 'Enemy 04-1.png cell (32, 32): d merges 4 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-low-skull'): 'Enemy 06-1.png cell (32, 32): d merges 4 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-armored-skull'): 'Enemy 07-1.png cell (32, 32): d merges 4 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-ice-skull'): 'Enemy 11-1.png cell (32, 32): d merges 4 pixels; minimum colour loss 4px.',
    (32, 'left', 'normal-goblin-round'): 'Enemy 18.png cell (32, 32): d merges 4 pixels; i merges 2 pixels; minimum colour loss 6px.',
    (32, 'left', 'normal-glasses'): 'pipo-charachip_otaku01.png cell (32, 32): l merges 3 pixels; minimum colour loss 3px.',
    (32, 'left', 'normal-reindeer'): 'pipo-xmaschara04.png cell (32, 32): w merges 3 pixels; minimum colour loss 3px.',
    (32, 'left', 'normal'): 'Male 01-1.png cell (32, 32): w merges 4 pixels; d merges 2 pixels; minimum colour loss 6px.',
    (48, 'front', 'normal-raven1-r0-c3'): 'spritesheet.png cell (144, 0): S merges 2 pixels; l merges 5 pixels; i merges 6 pixels; d merges 6 pixels; minimum colour loss 19px.',
    (48, 'front', 'normal-raven1-r0-c9'): 'spritesheet.png cell (432, 0): l merges 24 pixels; w merges 8 pixels; i merges 2 pixels; d merges 4 pixels; s merges 20 pixels; minimum colour loss 58px.',
    (48, 'front', 'normal-raven2-r0-c6'): 'spritesheet 2.png cell (288, 0): l merges 18 pixels; i merges 2 pixels; d merges 4 pixels; w merges 6 pixels; s merges 2 pixels; minimum colour loss 32px.',
    (48, 'front', 'normal-raven2-r0-c7'): 'spritesheet 2.png cell (336, 0): l merges 22 pixels; S merges 1 pixels; i merges 2 pixels; d merges 4 pixels; w merges 7 pixels; s merges 2 pixels; minimum colour loss 38px.',
    (48, 'front', 'normal-raven2-r0-c8'): 'spritesheet 2.png cell (384, 0): l merges 25 pixels; S merges 2 pixels; i merges 2 pixels; d merges 4 pixels; w merges 8 pixels; h merges 1 pixels; s merges 2 pixels; minimum colour loss 44px.',
    (48, 'front', 'normal-raven2-r4-c3'): 'spritesheet 2.png cell (144, 192): S merges 1 pixels; l merges 5 pixels; i merges 2 pixels; d merges 10 pixels; minimum colour loss 18px.',
    (48, 'front', 'normal-raven2-r4-c6'): 'spritesheet 2.png cell (288, 192): l merges 5 pixels; w merges 6 pixels; i merges 7 pixels; d merges 8 pixels; minimum colour loss 26px.',
    (48, 'front', 'normal-raven2-r4-c9'): 'spritesheet 2.png cell (432, 192): l merges 5 pixels; w merges 6 pixels; d merges 10 pixels; i merges 5 pixels; minimum colour loss 26px.',
    (48, 'front', 'normal-base-c0'): 'walk-animation.png cell (0, 0): i merges 4 pixels; minimum colour loss 4px.',
    (48, 'front', 'normal'): 'spritesheet.png cell (0, 0): S merges 2 pixels; l merges 5 pixels; i merges 2 pixels; d merges 10 pixels; minimum colour loss 19px.',
    (48, 'left', 'normal-raven1-r2-c0'): 'spritesheet.png cell (0, 96): S merges 5 pixels; l merges 5 pixels; w merges 7 pixels; minimum colour loss 17px.',
    (48, 'left', 'normal-raven1-r1-c3'): 'spritesheet.png cell (144, 48): S merges 1 pixels; d merges 1 pixels; i merges 2 pixels; minimum colour loss 4px.',
    (48, 'left', 'normal-raven1-r2-c3'): 'spritesheet.png cell (144, 96): S merges 5 pixels; l merges 5 pixels; w merges 7 pixels; minimum colour loss 17px.',
    (48, 'left', 'normal-raven1-r1-c9'): 'spritesheet.png cell (432, 48): l merges 12 pixels; i merges 1 pixels; w merges 3 pixels; s merges 12 pixels; minimum colour loss 28px.',
    (48, 'left', 'normal-raven1-r2-c9'): 'spritesheet.png cell (432, 96): S merges 10 pixels; l merges 22 pixels; d merges 1 pixels; w merges 3 pixels; s merges 16 pixels; minimum colour loss 52px.',
    (48, 'left', 'normal-raven2-r1-c6'): 'spritesheet 2.png cell (288, 48): l merges 9 pixels; i merges 1 pixels; w merges 3 pixels; s merges 1 pixels; minimum colour loss 14px.',
    (48, 'left', 'normal-raven2-r2-c6'): 'spritesheet 2.png cell (288, 96): S merges 6 pixels; l merges 20 pixels; d merges 1 pixels; w merges 3 pixels; s merges 8 pixels; minimum colour loss 38px.',
    (48, 'left', 'normal-raven2-r5-c3'): 'spritesheet 2.png cell (144, 240): S merges 2 pixels; d merges 3 pixels; i merges 1 pixels; minimum colour loss 6px.',
    (48, 'left', 'normal-raven2-r6-c3'): 'spritesheet 2.png cell (144, 288): S merges 5 pixels; l merges 2 pixels; d merges 1 pixels; w merges 7 pixels; minimum colour loss 15px.',
    (48, 'left', 'normal-raven2-r5-c6'): 'spritesheet 2.png cell (288, 240): d merges 3 pixels; i merges 1 pixels; w merges 5 pixels; minimum colour loss 9px.',
    (48, 'left', 'normal-raven2-r6-c6'): 'spritesheet 2.png cell (288, 288): l merges 5 pixels; d merges 3 pixels; i merges 1 pixels; w merges 7 pixels; minimum colour loss 16px.',
    (48, 'left', 'normal-raven2-r5-c9'): 'spritesheet 2.png cell (432, 240): d merges 4 pixels; w merges 5 pixels; minimum colour loss 9px.',
    (48, 'left', 'normal-raven2-r6-c9'): 'spritesheet 2.png cell (432, 288): l merges 5 pixels; d merges 3 pixels; w merges 7 pixels; minimum colour loss 15px.',
    (48, 'left', 'normal'): 'spritesheet.png cell (0, 48): S merges 1 pixels; d merges 3 pixels; i merges 1 pixels; minimum colour loss 5px.',
}


UNRECORDED = {
    (48, "spritesheet.png", (288, 0)): "r0-c6 is cited only by a brow; no recorded eye variant exists.",
    (48, "spritesheet.png", (288, 48)): "r1-c6 is cited only by a brow; no recorded eye variant exists.",
    (48, "spritesheet.png", (288, 96)): "r2-c6 is cited only by a brow; no recorded eye variant exists.",
    (48, "spritesheet.png", (288, 240)): "r5-c6 is cited only by a brow; no recorded eye variant exists.",
    (48, "spritesheet.png", (288, 288)): "r6-c6 is cited only by a brow; no recorded eye variant exists.",
}


def egg(px, width):
    """A symmetric skin egg with a flat eye-row span, no pre-existing eyes."""
    w, height = (24, 32) if px == 16 else (px, px)
    a = np.zeros((height, w, 4), np.uint8)
    left = (w - width) // 2
    for y in range(3, height - 4):
        inset = max(0, 3 - min(y - 3, height - 5 - y))
        a[y, left + inset:left + width - inset] = (240, 200, 160, 255)
    a[height - 4:height - 2, left + 2:left + width - 2] = (20, 20, 30, 255)
    return a


def source_case(library, facing, parts):
    """Use only the cited box and recorded offsets for explicit source anchors."""
    source = parts["source"]
    sheet = h.load(os.path.join(FIX, "face%d" % library["px"], source["file"]))
    note = next(s["note"] for s in library["sources"] if s["id"] == source["id"])
    match = re.search(r"(\d+)x(\d+) (?:animation cells|action sprite|cells)", note)
    cw, ch = tuple(map(int, match.groups())) if match else library["frame"]
    cw, ch = min(cw, sheet.shape[1]), min(ch, sheet.shape[0])
    bx, by, bw, bh = source["box"]
    fx, fy = bx // cw * cw, by // ch * ch
    a = sheet[fy:fy + ch, fx:fx + cw].copy()
    if sheet[0, 0, 3]:
        a[(a[..., :3] == sheet[0, 0, :3]).all(axis=-1), 3] = 0
    facing = "right" if source["id"].endswith("-right") else facing
    pixels = [(float(-p["at"][0] - col if flip else p["at"][0] + col),
               int(p["at"][1]) + row, role)
              for p, flip in _parts_for(parts, facing == "right")
              for row, line in enumerate(p["grid"]) for col, role in enumerate(line)]
    cx = bx - fx - min(x for x, _, _ in pixels)
    ey = by - fy - min(y for _, y, _ in pixels)
    eye_roles = ("diwh" if any(role in "diwh" for _, _, role in pixels) else
                 "l" if any(role == "l" for _, _, role in pixels) else ".")
    eyes = [(int(cx + x), ey + y) for x, y, role in pixels if role in eye_roles]
    # The local chin/centre is skin even for grey, blue or tinted source faces.
    eye_set = set(eyes)
    candidates = [(x, y) for y in range(max(0, by - fy), min(ch, by - fy + bh + 3))
                  for x in range(max(0, bx - fx), min(cw, bx - fx + bw))
                  if a[y, x, 3] and (x, y) not in eye_set]
    sx, sy = min(candidates, key=lambda p: (
        abs(p[0] - cx) + abs(p[1] - (by - fy + bh)), -int(a[p[1], p[0], :3].sum())))
    args = ["--facing", facing, "--skin", "%d,%d" % (sx, sy),
            "--eyes", *["%d,%d" % p for p in eyes]]
    samples = {}
    for x, y, role in pixels:
        if role != ".":
            samples.setdefault(role, []).append(tuple(a[ey + y, int(cx + x), :3]))
    minimum_loss = sum(len(v) - max(v.count(c) for c in set(v)) for v in samples.values())
    return a, args, (bx - fx, by - fy, bw, bh), (fx, fy), minimum_loss


def sample():
    a = np.zeros((32, 24, 4), np.uint8)
    a[2:8, 6:18] = (70, 80, 90, 255)
    a[8:19, 6:18] = (240, 200, 160, 255)
    a[19:30, 7:17] = (20, 20, 30, 255)
    for x, side in ((10, -1), (13, 1)):
        a[10, x] = (20, 20, 30, 255)
        a[11, x] = (33, 37, 145, 255)
        a[12, x] = (29, 115, 214, 255)
        a[12, x + side] = (255, 255, 255, 255)
    return a


class FaceExpressionTest(unittest.TestCase):
    def stamp(self, a=None, expr="normal", *extra):
        d = h.tmp()
        src = h.save(sample() if a is None else a, os.path.join(d, "src.png"))
        out = os.path.join(d, "out.png")
        code, text, err = h.run_cli("face", src, "--stamp", out, "--parts", PARTS,
                                   "--expr", expr, *extra)
        self.assertEqual(code, 0, text + err)
        return out, h.load(out), text

    def test_normal_preserves_eye_region_and_passes_auto(self):
        out, a, text = self.stamp()
        self.assertTrue(np.array_equal(a[10:13, 9:15], sample()[10:13, 9:15]))
        for key in ("STAMPED", "EXPR", "FACING", "EYE_COLORS_ADDED", "CLIPPED", "NEXT"):
            self.assertIn(key, h.kv(text))
        code, text, err = h.run_cli("face", out, "--auto")
        self.assertEqual(code, 0, text + err)

    def test_intended_closed_sides_do_not_fail_missing_eye(self):
        for expr in ("closed", "wink-l", "patch-l", "one-eyed-l"):
            with self.subTest(expr=expr):
                out, a, _ = self.stamp(None, expr)
                self.assertFalse(np.array_equal(a[10:13, 9:15], sample()[10:13, 9:15]))
                code, text, err = h.run_cli("face", out, "--auto", "--expr", expr,
                                           "--parts", PARTS)
                self.assertEqual(code, 0, text + err)
                self.assertNotIn("EYE_PAIR: FAIL", text)

    def test_named_and_explicit_eye_colors(self):
        for value, dark, light in (
            ("brown", (90, 32, 0), (148, 65, 24)),
            ("#212591,#1D73D6,#FFFFFF", (33, 37, 145), (29, 115, 214)),
        ):
            out, a, text = self.stamp(None, "normal", "--eye-color", value)
            self.assertEqual(tuple(a[11, 10, :3]), dark)
            self.assertEqual(tuple(a[12, 10, :3]), light)
            self.assertIn("EYE_COLORS_ADDED", text)
            code, text, err = h.run_cli("face", out, "--auto")
            self.assertEqual(code, 0, text + err)

    def test_single_hex_derived_ramp_contrast_hue_and_gate(self):
        luma = lambda c: .299*c[0] + .587*c[1] + .114*c[2]
        for value in ("#3FA0FF", "3FA0FF", "#FFD020"):
            with self.subTest(value=value):
                out, a, text = self.stamp(None, "normal", "--eye-color", value)
                ramp = h.kv(text)["EYE_RAMP"].split()
                self.assertEqual(len(ramp), 4)
                dark, light, highlight, white = [
                    tuple(int(c[i:i+2], 16) for i in (1, 3, 5)) for c in ramp]
                self.assertLess(luma(dark), luma(light))
                self.assertGreaterEqual(luma((240, 200, 160))-luma(dark), 60)
                self.assertGreaterEqual(abs(luma((240, 200, 160))-luma(light)), 25)
                dh, ds, _ = colorsys.rgb_to_hsv(*(v/255 for v in dark))
                lh, _, _ = colorsys.rgb_to_hsv(*(v/255 for v in light))
                self.assertLessEqual(min(abs(dh-lh), 1-abs(dh-lh))*360, 20)
                self.assertGreater(luma(highlight), luma(light))
                self.assertEqual(white, (255, 255, 255))
                if value == "#FFD020":
                    self.assertGreater(dark[0], dark[2]*2)
                    self.assertGreater(dark[1], dark[2]*2)
                    self.assertGreater(ds, .5)
                code, text, err = h.run_cli("face", out, "--auto")
                self.assertEqual(code, 0, text + err)

    def test_single_hex_reuses_near_white_and_snaps_close_palette(self):
        a = sample()
        a[12, 9] = a[12, 14] = (248, 248, 248, 255)
        _, _, text = self.stamp(a, "normal", "--eye-color", "#1E74D5", "--snap-palette")
        ramp = h.kv(text)["EYE_RAMP"].split()
        self.assertEqual(ramp[1], "#1D73D6")
        self.assertEqual(ramp[3], "#F8F8F8")
        self.assertNotIn("#1D73D6", h.kv(text)["EYE_COLORS_ADDED"])
        self.assertNotIn("#F8F8F8", h.kv(text)["EYE_COLORS_ADDED"])

    def test_sad_with_bright_lower_iris_passes_without_expression_hint(self):
        out, _, _ = self.stamp(None, "sad", "--eye-color", "#3FA0FF")
        code, text, err = h.run_cli("face", out, "--auto")
        self.assertEqual(code, 0, text + err)
        self.assertIn("EYE_PAIR: PASS", text)

    def test_highlight_role_uses_derived_highlight(self):
        _, a, text = self.stamp(None, "highlight", "--eye-color", "#3FA0FF")
        highlight = h.kv(text)["EYE_RAMP"].split()[2]
        self.assertEqual("#%02X%02X%02X" % tuple(a[10, 9, :3]), highlight)
        self.assertIn(highlight, h.kv(text)["EYE_COLORS_ADDED"])

    def test_real_frame_derived_bright_iris_passes_auto(self):
        source = h.load(os.path.join(FIX, "rm2k-blue-down.png"))
        out, a, _ = self.stamp(source, "normal", "--key", "#009392",
                               "--eye-color", "#3FA0FF", "--snap-palette")
        self.assertEqual(len(detect_face(a)["eyes"]), 2)
        code, text, err = h.run_cli("face", out, "--auto")
        self.assertEqual(code, 0, text + err)

    def test_mouth_keep_erase_and_brow_clipping(self):
        a = sample()
        a[14, 10:13] = (100, 40, 20, 255)
        _, kept, _ = self.stamp(a)
        self.assertTrue(np.array_equal(kept[14, 10:13], a[14, 10:13]))
        _, erased, _ = self.stamp(a, "normal", "--mouth", "none")
        self.assertTrue(np.all(erased[14, 10:13] == (240, 200, 160, 255)))
        a[9, 9] = (70, 80, 90, 255)
        _, stamped, text = self.stamp(a, "normal", "--brows", "angry")
        self.assertEqual(tuple(stamped[9, 9]), tuple(a[9, 9]))
        self.assertEqual(h.kv(text)["CLIPPED"], "1")

    def test_auto_side_and_right_mirror(self):
        for side, x in (("left", 10), ("right", 13)):
            a = sample()
            other = 13 if x == 10 else 10
            a[10:13, other - (other == 10):other + 1 + (other == 13)] = (240, 200, 160, 255)
            _, stamped, text = self.stamp(a)
            self.assertEqual(h.kv(text)["FACING"], side)
            self.assertEqual(tuple(stamped[11, x, :3]), (33, 37, 145))

    def test_px_override_and_unknown_parts_are_errors(self):
        a = np.pad(sample(), ((0, 4), (0, 4), (0, 0)))
        self.stamp(a, "normal", "--px", "16")
        src = h.save(sample(), os.path.join(h.tmp(), "src.png"))
        code, text, err = h.run_cli("face", src, "--stamp", os.path.join(h.tmp(), "out.png"),
                                   "--parts", PARTS, "--expr", "absent")
        self.assertEqual(code, 2, text + err)
        self.assertIn("absent", err)

    def test_normal_all_available_library_source_frames(self):
        files = sorted(glob.glob(os.path.join(LIBRARIES, "*.json")))
        self.assertEqual(len(files), 3)
        checked, exceptions, unrecorded = 0, set(), set()
        for path in files:
            with open(path) as f:
                library = json.load(f)
            frames = set()
            for facing, config in library["facings"].items():
                if not isinstance(config, dict):
                    continue
                # Prefer the named recorded variant over the default template.
                variants = sorted(config["eyes"].items(),
                                  key=lambda item: not item[0].startswith("normal-"))
                for expr, parts in variants:
                    source = parts.get("source", {})
                    if "file" not in source:
                        continue
                    original, anchors, box, cell, minimum_loss = source_case(library, facing, parts)
                    frame_id = (source["file"], cell)
                    if frame_id in frames:
                        continue
                    frames.add(frame_id)
                    key = (library["px"], facing, expr)
                    with self.subTest(px=library["px"], file=source["file"],
                                      cell=cell, variant=expr):
                        d = h.tmp()
                        frame = h.save(original, os.path.join(d, "frame.png"))
                        out = os.path.join(d, "out.png")
                        code, text, err = h.run_cli(
                            "face", frame, "--stamp", out, "--parts", path,
                            "--px", str(library["px"]), "--expr", expr, *anchors)
                        self.assertEqual(code, 0, text + err)
                        stamped = h.load(out)
                        x, y, w, height = box
                        region = (slice(max(0, y - 1), y + height + 1),
                                  slice(max(0, x - 1), x + w + 1))
                        changed = int(np.any(original[region] != stamped[region], axis=-1).sum())
                        if key in UNREPRODUCIBLE:
                            self.assertGreater(minimum_loss, 2,
                                               "exception requires intrinsic role-colour loss")
                            self.assertGreater(changed, 2, "remove the now-reproducible exception")
                            exceptions.add(key)
                        else:
                            self.assertLessEqual(changed, 2, text)
                            checked += 1
            sources = {s["id"]: s for s in library["sources"]}
            references = []

            def visit(node):
                if isinstance(node, dict):
                    if "file" in node.get("source", {}):
                        references.append(node["source"])
                    for value in node.values():
                        visit(value)
                elif isinstance(node, list):
                    for value in node:
                        visit(value)

            visit(library)
            source_frames = set()
            for source in references:
                sheet = h.load(os.path.join(FIX, "face%d" % library["px"], source["file"]))
                note = sources[source["id"]]["note"]
                match = re.search(r"(\d+)x(\d+) (?:animation cells|action sprite|cells)", note)
                cw, ch = tuple(map(int, match.groups())) if match else library["frame"]
                cw, ch = min(cw, sheet.shape[1]), min(ch, sheet.shape[0])
                cell = (source["box"][0] // cw * cw, source["box"][1] // ch * ch)
                source_frames.add((source["file"], cell))
            missing = {(library["px"], filename, cell)
                       for filename, cell in source_frames - frames}
            self.assertEqual(missing, {key for key in UNRECORDED if key[0] == library["px"]})
            unrecorded.update(missing)
        self.assertEqual(exceptions, set(UNREPRODUCIBLE))
        self.assertEqual(unrecorded, set(UNRECORDED))
        self.assertGreater(checked, 0)

    def test_face_width_controls_gap_and_exact_mirror_symmetry(self):
        for px, widths in ((16, (8, 13)), (32, (13, 22)), (48, (19, 30))):
            with open(os.path.join(LIBRARIES, "%d.json" % px)) as f:
                library = json.load(f)
            rule = library["spacing"]["front"]
            for width in widths:
                with self.subTest(px=px, width=width):
                    a = egg(px, width)
                    d = h.tmp()
                    src = h.save(a, os.path.join(d, "src.png"))
                    out = os.path.join(d, "out.png")
                    code, text, err = h.run_cli("face", src, "--stamp", out,
                                               "--expr", "normal", "--eye-color", "#3FA0FF")
                    self.assertEqual(code, 0, text + err)
                    values = h.kv(text)
                    expected = min(rule["max"], max(rule["min"],
                                   int(np.floor(rule["ratio"] * width + .5))))
                    # Two identical iris widths need gap parity equal to face width.
                    if expected % 2 != width % 2:
                        expected = expected - 1 if expected > rule["min"] else expected + 1
                    self.assertEqual(int(values["FACE_W"]), width)
                    self.assertEqual(int(values["EYE_GAP"]), expected)
                    stamped = h.load(out)
                    changed = np.any(a != stamped, axis=-1)
                    left = (a.shape[1] - width) // 2
                    self.assertTrue(np.array_equal(changed[:, left:left + width],
                                                   changed[:, left:left + width][:, ::-1]))
                    self.assertTrue(np.array_equal(stamped[:, left:left + width],
                                                   stamped[:, left:left + width][:, ::-1]))

    def test_skin_span_does_not_expand_through_white_headgear_to_an_ear(self):
        a = sample()
        a[11, 2] = (240, 200, 160, 255)
        a[11, 3:6] = (255, 255, 255, 255)
        detection: FaceDetection = {
            "skin": (6, 13), "eyes": [[(10, 11), (10, 12)], [(13, 11), (13, 12)]],
            "reason": "", "expected": [(10, 11), (13, 11)]}
        self.assertEqual(_face_span(a, detection, 11), (6, 17))

    def test_scar_remains_visible_with_a_dark_brown_outline_palette(self):
        a = sample()
        a[28, 7] = (36, 22, 12, 255)
        d = h.tmp()
        src = h.save(a, os.path.join(d, "src.png"))
        out = os.path.join(d, "out.png")
        code, text, err = h.run_cli("face", src, "--stamp", out, "--expr", "scar-l",
                                   "--facing", "front")
        self.assertEqual(code, 0, text + err)
        self.assertTrue((h.load(out)[..., :3] == (164, 24, 32)).all(axis=-1).any())

    def test_eye_gap_override_moves_pair_and_rejects_impossible_parity(self):
        a = egg(32, 22)
        d = h.tmp()
        src = h.save(a, os.path.join(d, "src.png"))
        out = os.path.join(d, "out.png")
        code, text, err = h.run_cli("face", src, "--stamp", out, "--expr", "normal",
                                   "--eye-gap", "2", "--eye-color", "#3FA0FF")
        self.assertEqual(code, 0, text + err)
        self.assertEqual(h.kv(text)["EYE_GAP"], "2")
        code, text, err = h.run_cli("face", src, "--stamp", out, "--expr", "normal",
                                   "--eye-gap", "3")
        self.assertEqual(code, 2, text + err)

    def test_side_eye_uses_measured_leading_edge_margin(self):
        for px, width in ((16, 12), (32, 22), (48, 30)):
            with open(os.path.join(LIBRARIES, "%d.json" % px)) as f:
                rule = json.load(f)["spacing"]["side"]
            a = egg(px, width)
            left = (a.shape[1] - width) // 2
            margin = min(rule["max"], max(rule["min"],
                         int(np.floor(rule["ratio"] * width + .5))))
            for facing in ("left", "right"):
                with self.subTest(px=px, facing=facing):
                    d = h.tmp()
                    src = h.save(a, os.path.join(d, "src.png"))
                    out = os.path.join(d, "out.png")
                    code, text, err = h.run_cli(
                        "face", src, "--stamp", out, "--expr", "normal",
                        "--facing", facing, "--eye-color", "#3FA0FF")
                    self.assertEqual(code, 0, text + err)
                    colors = h.kv(text)["EYE_RAMP"].split()[:2]
                    stamped = h.load(out)
                    core = np.zeros(stamped.shape[:2], bool)
                    for color in colors:
                        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
                        core |= (stamped[..., :3] == rgb).all(axis=-1)
                    xs = np.where(core)[1]
                    self.assertEqual(int(xs.min()) if facing == "left" else int(xs.max()),
                                     left + margin if facing == "left" else left + width - 1 - margin)

    def test_default_normal_real_frames_pass_auto_pair(self):
        for name in ("rm2k-down.png", "rm2k-knight-down.png", "knight-asym-16.png"):
            with self.subTest(frame=name):
                d = h.tmp()
                out = os.path.join(d, "out.png")
                code, text, err = h.run_cli("face", os.path.join(FIX, name),
                                           "--stamp", out, "--expr", "normal",
                                           "--key", "#009392")
                self.assertEqual(code, 0, text + err)
                code, text, err = h.run_cli("face", out, "--auto")
                self.assertEqual(code, 0, text + err)
                self.assertIn("EYE_PAIR: PASS", text)
