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

## Spacing metadata and reproduction

`normal` is the default design per px, not a universal source reconstruction.
Recorded names such as `normal-rm-03` and `normal-raven2-r0-c6` retain their
source geometry. Source reproduction uses that variant, its cited box and
explicit `--skin X,Y --eyes X,Y ...` anchors; these also work for neutral/tinted
faces that the warm-skin detector cannot recognise. The engine infers the
template anchor from those eye coordinates and keeps source-local role colours.
Dots preserve occluded pixels. One colour per role cannot reproduce every
source ramp: the regression test lists each intrinsically lossy source and its
minimum pixel loss, plus the five brow-only frames lacking an eye variant.

Each JSON adds only top-level `spacing` metadata:

```
"spacing": {
  "front": {"ratio": 0.3333333333, "min": 1, "max": 4},
  "side":  {"ratio": 0.25, "min": 0, "max": 4},
  "measured": {"front_n": 11, "side_n": 9, "front_face_w": [5,6,10], ...}
}
```

The eye-row skin envelope bridges the original eye/sclera opening, not hair or
an isolated ear. `front` is the number of empty columns between **iris bounds**
(not lids or sclera); `side` is the leading-edge-to-iris margin. Compute
`floor(ratio * FACE_W + 0.5)`, then clamp to `[min,max]`. For a front pair,
adjust down by one (up at the minimum) to match face-width parity, and place
the mirrored identical default eyes around `(skin_left + skin_right)/2`.
Both integer and half-integer skin centres remain exact. `--eye-gap N` overrides
the front gap; a negative gap or incompatible parity is an error. Deliberate
wink/patch/scar expressions can differ between sides. Output includes
`EYE_GAP` (0 for a profile) and `FACE_W`. Custom libraries without metadata retain
their recorded offsets; explicit source anchors retain geometry.

| px | Front gap ratio / clamp | Side margin ratio / clamp | Front / side samples |
|---|---|---|---|
| 16 | 0.3333333333 / 1..4 | 0.25 / 0..4 | 11 / 9 |
| 32 | 0.3846153846 / 1..7 | 0.2 / 0..4 | 28 / 23 |
| 48 | 0.4358974359 / 1..14 | 0.3809523810 / 0..6 | 6 / 8 |

`measured` arrays are `[min, median, max]`: face widths at the eye row,
inner iris gaps, outer iris span (inclusive), and iris-to-face-edge margins.
Ratios are sample medians of gap/width or margin/width. Original sources are the
RM2K user charset, Puny/Alex 16px originals, PIPOYA/knight 32px originals and
Raven 48px uploads under `/tmp/p2d-study`, with source copies in test fixtures.
Occluded/non-warm samples are excluded only from the spacing fit, never silently
from reproduction. The 16/48 front caps extrapolate up to twice the observed
maximum gap for wider faces; the 32px and side caps are observed maxima.
