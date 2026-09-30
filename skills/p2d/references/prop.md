# Props

Single objects with a transparent background: crates, barrels, pots, chests, tables, doors, signs, pillars, statues, trees, items and icons.

## Size and anchor

| Prop | Canvas | Anchor |
|---|---|---|
| small object standing on the floor (crate, barrel, pot, chest) | 1x1 tile (PxP) | `bottom` |
| tall object (pillar, statue, tree, lamp post) | 1x2 to 1x4 tiles (e.g. `16x64`) | `bottom` |
| wide object (table, bed, cart) | 2x1 or 2x2 tiles | `bottom` |
| item or UI icon (potion, key, sword) | 1x1 tile | `center`, `--margin 1` |

Floor objects end up touching the bottom row (pixelize `--anchor bottom`); items float centred. In the generated image the object always keeps a magenta margin on all sides so `raw-check` can see the key border. Use `--margin N` to keep empty logical pixels around the subject when it must not fill the canvas.

## Prompt template

```
A single <object> as a game prop for a 2D RPG Maker-style map, 3/4 top-down view showing the top and the front, <material, colors, details>.
Exactly one object, centred, fully inside the image with a clear magenta margin on every side (pixelize moves floor objects down to the bottom row).
Designed as a <W>x<H> pixel grid: each pixel a flat single-color sample. Use the pack's outline convention and light direction.
Flat solid #FF00FF magenta background everywhere around the object, no shadow on the background, no floor, no text, no other objects.
<pack line from SKILL.md>
```

Choose another key color only when the object itself is magenta or pink; pass the same color to `pack init --key` or `--key`.

## Process

```
p2d.py raw-check RAW --bg key
p2d.py pixelize RAW --kind prop --size WxH --anchor bottom --pack DIR --out DIR/assets/<name>/<name>@<P>.png --scale 8
p2d.py check DIR/assets/<name>/<name>@<P>.png --kind prop --size WxH --pack DIR
```

Add `--despeckle` when single stray pixels remain inside flat areas. A square object that truly fills its tile with no transparent corner needs `--allow-opaque` on `check`.

## Outline and plane review

Inspect the native PNG and integer-nearest enlargement; color count and transparency PASS alone cannot approve the art.

- Separate the silhouette, material thickness, joins and highlights. For a crate, top/front/side planes and the front brace must read as distinct surfaces rather than parallel decorative bands.
- Use a consistent outline convention across the pack. One logical pixel is a useful small-sprite starting point, not a universal rule: thicker shadow edges or structural beams need an intentional material/light reason.
- When the user requests a continuous outline, do not reinterpret it as selective outlining. Interior colors must not escape the enclosing contour at corners or highlight edges. Record that convention in pack.json and inspect the whole exterior silhouette, not just the bounding box.
- Check corners and diagonal step runs for accidental thickness changes, doubled rims and isolated dark pixels. Avoid a bright stripe following every dark outline equally; highlights should describe the light-facing material, not trace the entire silhouette.
- Two adjacent rows are not inherently wrong. Reject them when an outline and highlight merge into an unintended thick band, obscure the plane transition, or create pillow-shaded/embossed edges.
- If these fail, keep the candidate unaccepted. For local repairs use `touch` with pack colors and recheck the complete silhouette; for unclear geometry regenerate from the corrected description. Do not blindly thin every edge or erase intentional beam thickness.

For a continuous-outline pack, explicitly choose its intended outline color(s) from the palette and run `check FILE --kind prop --size WxH --pack DIR --outline-colors '#222034'` (replace the example color with the pack's choice; comma-separate alternatives). `OUTLINE_UNCOVERED` must be zero. This checks foreground pixels adjacent to 4-connected exterior transparency; canvas edges count as exterior and enclosed holes do not. It does not judge plane geometry, intentional shading, or outline thickness. Diagnose the reported coordinates before using `touch`; save a sibling corrected file and review it at 1x and integer enlargement.

## Deliverables

`<name>@<P>.png` per px with its `@8x` preview.
