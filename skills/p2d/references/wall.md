# Walls (3/4 view)

Wall faces in the RPG Maker 3/4 view: stone or brick walls, cliff faces, wooden walls, hedges and fences that run sideways along a map. A wall piece repeats horizontally; tall walls may also stack vertically.

## Shape

- Width: 1 tile unit (P). Height: 2-4 tile units; default 3 (e.g. `16x48` at px 16, `32x96` at px 32).
- Top rows show the wall's upper surface or capstones; the rest is the vertical face with the light from the top-left; the bottom row may darken into the floor contact.
- Repeat axis: `x` (sideways). Use `xy` only when the user wants a face that also stacks upward.
- Free-standing pillars, columns, statues or a single wall end are props (they have transparent sides), not walls.

## Front-facing 3/4 construction (from original JRPG tilesets)

The top is a plane (a walkable cap band in its own material), not a bright outline. The front face is darker, with vertically elongated masses and one shared crack network: 2-4 principal masses at 16, 3-6 at 32, 4-8 at 48. A dark break where the cap turns down; the lip continues through corners and interior tiles never invent a new lip. No bevel around each stone. Walls are the cleanest kind: expect few isolated pixels (`NOISE_REVIEW`).

## Prompt template

```
One seamless section of a <material> wall for a 2D RPG Maker-style map in 3/4 top-down view, <W>x<H> tile proportions (<W/P> tile wide, <H/P> tiles tall).
Top edge shows the wall top / capstones seen from above; below it the front face with <bricks, mortar, cracks, moss, torch brackets>.
The left and right edges must continue seamlessly when the piece repeats sideways. It fills the entire image edge to edge.
Designed as a <W>x<H> pixel grid: each pixel a crisp square block. Light from the top-left, no perspective vanishing, no border, no floor, no characters.
<pack line from SKILL.md>
```

`size WxH` gives the canvas (aspect must be at most 3:1; 1x3 tiles is exactly 3:1).

## Process

```
p2d.py pixelize RAW --kind wall --size WxH --pack DIR --out DIR/assets/<name>/<name>@<P>.png --scale 8
p2d.py check DIR/assets/<name>/<name>@<P>.png --kind wall --size WxH --pack DIR
p2d.py preview DIR/assets/<name>/<name>@<P>.png --repeat 3 --out DIR/previews/<name>@<P>-repeat.png
```

`check --kind wall` measures the x seam by default; pass `--axis xy` for stacking walls. Seam repair is the offset-and-repaint method with `--axis x` (or `xy`): `p2d.py offset RAW --axis x --out OFFSET --mask MASK`, repaint the masked band with the image tool (reserve an attempt first), `p2d.py offset EDITED --axis x --inverse --out FIXED`.

Record `--axis x` (or `xy`) on `pack attempt`.
