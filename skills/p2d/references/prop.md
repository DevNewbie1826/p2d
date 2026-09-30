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
Designed as a <W>x<H> pixel grid: each pixel a large crisp square block. Dark selective outline, light from the top-left.
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

## Deliverables

`<name>@<P>.png` per px with its `@8x` preview.
