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
| Water | 1-3 connected ripple/crest groups or a quiet flat field | 2-4 ripple groups or cells | 3-6 groups + subordinate arcs | light pixels belong to crests; no white confetti, no black ripple outlines |
| Lava | 1-2 dark cooling pockets split by a connected hot path | 2-4 pockets, 1-2 branching channels | 3-6 pockets + eddies | yellow only inside the hottest channel; emissive, no top-left stone highlight |
| Grass (walkable) | calm base + 0-3 connected tufts/notches | 3-6 low-contrast clumps | 6-10 tuft groups | yellow-green tips, darker roots; no square sprinkles |
| Stone / cobble | 2-4 masses | 3-6 masses, 1-2 cracks | 4-8 masses + chips | one crack network; no bright rim around every stone |

Colors per tile: about 3-8 at 16, 4-12 at 32, 4-16 at 48. Smaller px = fewer, larger features, not the same pattern shrunk. Prompt: `<N>px <material> tile built from <budget> coherent connected <features> on a broad calm field; no random isolated pixels`.

Background is opaque: skip the key color. With a reference tile, say `image 1 is the style reference: match its palette, pixel density and shading`.

## Process

```
p2d.py raw-check RAW --bg none
p2d.py pixelize RAW --kind tile --size PxP --pack DIR --out DIR/assets/<name>/<name>@<P>.png --scale 8
p2d.py check DIR/assets/<name>/<name>@<P>.png --kind tile --size PxP --pack DIR
p2d.py preview DIR/assets/<name>/<name>@<P>.png --repeat 3 --out DIR/previews/<name>@<P>-repeat.png
```

`check` measures seams in x and y (`SEAM_X`, `SEAM_Y`) and speckle (`NOISE_REVIEW: yes` = scattered isolated pixels for a tile of this px; redraw with the feature budget unless the singles are deliberate). Read the 3x3 repeat preview: a visible grid, a line, or a repeated blotch at the tile border is a failure even when the numbers pass.

## Fixing a seam (offset and repaint)

1. `p2d.py offset RAW --axis xy --out WORK/<name>-offset.png --mask WORK/<name>-mask.png` moves the borders into the centre and writes a repaint mask.
2. Reserve a new attempt, then call the image tool with `reference_image_paths=[offset image]`, `mask_image_path=mask`, prompt: `Repaint only the masked cross so the <material> continues seamlessly; keep every other pixel, the palette and the pixel size unchanged.`
3. `p2d.py offset EDITED --axis xy --inverse --out RAW_FIXED`, then pixelize and check again.

## Deliverables

`<name>@<P>.png` per px, its `@8x` preview, and the repeat preview. Record `--axis xy` on `pack attempt` for the asset.
