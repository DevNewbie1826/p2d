# Floor tiles

Square surfaces that repeat in both directions: cobblestone, slate, dirt, grass, planks, carpet, water, lava.

## Size

One tile unit: `PxP` (16x16, 32x32, 48x48). Larger textures are several tiles of the same unit, e.g. a 2x2 block `32x32` at px 16; each tile inside must still repeat.

## Prompt template

```
A single seamless tileable <material> floor texture, seen from above for a 2D RPG Maker-style map, filling the entire square image edge to edge.
<surface details: stone shapes, cracks, grout, moss, wear>.
Designed as a <P>x<P> pixel grid: each pixel a large crisp square block, about <P> blocks across.
Even lighting with the light from the top-left, no perspective, no vignette, no border, no frame, no objects, no characters, no shadow at the edges.
<pack line from SKILL.md>
```

## Structure before texture (measured on original 16/32/48 tiles)

A tile is a few connected features on a calm field, never evenly scattered single pixels. A feature = one connected crest, pocket, tuft or stone mass. Budget per tile and say it in the prompt:

| Material | 16 | 32 | 48 | Rule |
|---|---|---|---|---|
| Water | 2-3 stepped ripple contours, each a connected line of 3+ pixels | 3-5 ripple contours or wave cells | 4-6 contours + subordinate arcs | the ripple family is visible at 1x; a plain field with a couple of dashes is a FAIL unless the user asked for still water; light pixels belong to crests; no white confetti, no black ripple outlines |
| Lava | 1-2 dark cooling pockets split by a connected hot path | 2-4 pockets, 1-2 branching channels | 3-6 pockets + eddies | yellow only inside the hottest channel; emissive, no top-left stone highlight |
| Grass (walkable) | calm base + 0-3 connected tufts/notches | 3-6 low-contrast clumps | 6-10 tuft groups | yellow-green tips, darker roots; no square sprinkles |
| Stone / cobble | 2-4 masses | 3-6 masses, 1-2 cracks | 4-8 masses + chips | one crack network; no bright rim around every stone |

## Continuity: many tiles must read as one surface

A seamless edge is not enough: laid out on a map, a tile with one big motif stamps a visible grid. Like RPG Maker floor tiles:

- Never frame the tile: no channel, crack, ripple or color band running along the border; no single big motif centred in the tile. Put features off-centre, crossing the edges at different points on each side.
- Big-scale features are low contrast; strong contrast only on small accents.
- REQUIRED for water, lava, grass, sand, snow and any material with big features (pockets, wave cells, large stones, tufts): generate a seamless block of 2x2 tiles in one image (`--size` 2P x 2P, same prompt plus `a 2x2 tile block, features spread unevenly across it`), deliver it as `<name>-block@<P>.png`, and still check it with `--kind tile`.
- For large floors also make 1-2 variants (`--variant-of`) that swap feature positions, so the map can mix them.
- REQUIRED before `pack accept`: write `preview FILE --repeat 4 --unit <2P> --out DIR/previews/<name>@<P>-repeat.png`, open it and state in one line whether the tile grid or a repeating stamp is visible (features all pointing the same way, the same blob in every cell). Visible = FAIL even when every check passes; regenerate as a 2x2 block.

Colors per tile: about 3-8 at 16, 4-12 at 32, 4-16 at 48. Smaller px = fewer, larger features, not the same pattern shrunk. At 16 the same features must still read: water keeps continuous wave lines (not scattered dots), lava keeps crust plates separated by glowing cracks (not a checker of 3-colour blocks); name the 2-4 features of the accepted larger tile in the 16 prompt and reject a 16 whose features cannot be pointed to in the sizes preview. Prompt: `<N>px <material> tile built from <budget> coherent connected <features> on a broad calm field; no random isolated pixels`.

Background is opaque: skip the key color. With a reference tile, say `image 1 is the style reference: match its palette, pixel density and shading`.

## Process

```
p2d.py raw-check RAW --bg none
p2d.py pixelize RAW --kind tile --size PxP --pack DIR --out DIR/assets/<name>/<name>@<P>.png --scale 8
p2d.py check DIR/assets/<name>/<name>@<P>.png --kind tile --size PxP --pack DIR
p2d.py preview DIR/assets/<name>/<name>@<P>.png --repeat 4 --unit <2P> --out DIR/previews/<name>@<P>-repeat.png
```

`check` measures seams in x and y (`SEAM_X`, `SEAM_Y`) and speckle (`NOISE` FAIL = scattered isolated pixels for a tile of this px: redraw with fewer, larger connected features). Read the 4x4 repeat preview: a visible grid, a line, or a repeated blotch at the tile border is a failure even when the numbers pass.

## Fixing a seam (offset and repaint)

1. `p2d.py offset RAW --axis xy --out WORK/<name>-offset.png --mask WORK/<name>-mask.png` moves the borders into the centre and writes a repaint mask.
2. Reserve a new attempt, then run `gen_image.mjs --ref <offset image> --mask <mask>` with the prompt `Repaint only the masked cross so the <material> continues seamlessly; keep every other pixel, the palette and the pixel size unchanged.`
3. `p2d.py offset EDITED --axis xy --inverse --out RAW_FIXED`, then pixelize and check again.

## Deliverables

`<name>@<P>.png` per px, its `@8x` preview, and the repeat preview. Record `--axis xy` on `pack attempt` for the asset.

## Native blocks and pixel guards

Pixelize a generated 2x2 block at its full logical size, check it, then cut it with `split` (no resampling):

```sh
p2d.py pixelize RAW --kind tile --size 32x32 --pack DIR --out DIR/assets/water/water-block@16.png
p2d.py check DIR/assets/water/water-block@16.png --kind tile --size 32x32 --pack DIR
p2d.py split DIR/assets/water/water-block@16.png --unit 16 --out DIR/assets/water --name water
```

`split` writes `<name>-r{row}c{col}@P.png` (0-based). The 2x2 block is the repeatable unit: its four pieces tile only in their block positions, they are NOT independently seamless tiles. Deliver the block (and its pieces for tilesets). If the user needs a single PxP tile that repeats by itself, generate and check that tile separately; never shrink or crop the block to get it. `pixelize` refuses a --size that halves the generated grid (the lava mistake); do not bypass it with `--force-size`. `pixelize --despeckle auto` replaces only isolated pixels by the majority neighbour colour (capped at 3%) and prints `DESPECKLED: n`; `check` prints `NOISE_HINT` with the rate it would reach. Never lower `--max-colors` below the budget to pass NOISE (`COLORS_BELOW_BUDGET`); redraw with fewer, larger features instead.
