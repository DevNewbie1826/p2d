# Face parts schema (p2d_lib/face_parts/<px>.json)

One file per tile px (16, 32, 48). Shapes only; colours come from roles at stamp time.

{
  "px": 16,
  "frame": [24, 32],
  "sources": [{"id": "rm2k-user", "path": "<original png>", "note": "..."}],
  "facings": {
    "front": {
      "anchor": "cx = x centre between the two eye groups (or skin-region centre), ey = top row of the iris",
      "eyes": {
        "<expr>": {
          "left":  {"at": [dx, dy], "grid": ["..", ".."]},
          "right": "mirror" | {"at": [dx, dy], "grid": [...]},
          "source": {"id": "rm2k-user", "file": "char-01-down-c1.png", "box": [x, y, w, h]} | {"derived_from": "<expr>", "how": "..."}
        }
      },
      "brows": { "<expr>": {...same shape...} },
      "mouth": { "<expr>": {"at": [dx, dy], "grid": [...], "source": ...} }
    },
    "left":  {"anchor": "...", "eyes": {"<expr>": {"eye": {...}, "source": ...}}, "mouth": {...}},
    "right": "mirror-of-left"
  }
}

- "at" is the top-left of the grid relative to the anchor (cx, ey); for "right": "mirror" the right part is the left grid flipped horizontally and placed mirrored around cx.
- grid characters (roles):
  . keep the pixel underneath        s skin (detected)        S skin shadow (darker skin ramp step)
  l lid / brow / dark outline (darkest colour)                 d iris dark      i iris light
  w sclera / eye white                h eye highlight          p patch / band   c scar
  m mouth dark                        t mouth inner (tongue / teeth light)
- Required expressions (front, all px): normal, closed, wink-l, wink-r, angry, sad, surprised, happy (smile/closed-arc), patch-l, patch-r, scar-l, scar-r, one-eyed-l, one-eyed-r (lost eye: closed + scar, the other normal).
- Mouths (front): none, neutral, smile, open, eat (chewing, open with t), frown. At 16px "none" and 1-2px mouths are expected (RM2000 mostly omits mouths).
- Side facing ("left"; "right" is its mirror): normal, closed, angry, happy, patch (visible side), eat.
- Every part MUST cite a source box in an original PNG, or "derived_from" an extracted part with a one-line "how" (derived parts are allowed only for expressions no original shows).
- Eye colour sets live in the engine (face.py), e.g. blue {d:#212591,i:#1D73D6,w:#FFFFFF}, brown {d:#5A2000,i:#944118,w:#FFFFFF}; skin roles come from the frame.
