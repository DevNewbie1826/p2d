# Trims

Thin strips that repeat along one direction: floor borders, carpet edges, stone edging, wall friezes, ledges, rails.

## Shape

- Thickness: half a tile unit (P/2). Length: 1.5 tile units, so the canvas is exactly 3:1 (`24x8` horizontal or `8x24` vertical at px 16; `48x16` / `16x48` at px 32; `72x24` / `24x72` at px 48).
- Pattern budget at 8 px thickness (px 16): one light top edge row, one dark bottom/shadow row, and between them ONE simple motif repeated 2-3 times per strip (studs, short grooves, brick joints), each motif a connected 2-4 px shape on a flat field. No carved scrollwork, no mottled texture: it turns into 1 px noise. Write the motif count into the prompt (`<N> identical square studs evenly spaced on a flat band`). At px 32/48 keep the same motif and count, only thicker, so both sizes read as one pack.
- Horizontal trims repeat along `x`, vertical trims along `y`. Make the two orientations as separate assets (`<name>-h`, `<name>-v`) unless the user wants only one.

## Prompt template

```
A seamless horizontal (or vertical) <material> trim strip for a 2D RPG Maker-style map, 3:1 proportions, filling the whole image edge to edge.
<pattern: bricks, carved stone, wood grain, rope, metal studs>, the pattern continues seamlessly at the two short ends.
Designed as a <W>x<H> pixel grid: each pixel a crisp square block. Light from the top-left, no border, no background outside the strip, no objects.
<pack line from SKILL.md>
```

## Process

```
p2d.py pixelize RAW --kind trim --size WxH --pack DIR --out DIR/assets/<name>/<name>@<P>.png --scale 8
p2d.py check DIR/assets/<name>/<name>@<P>.png --kind trim --size WxH --pack DIR
p2d.py preview DIR/assets/<name>/<name>@<P>.png --repeat 3 --out DIR/previews/<name>@<P>-repeat.png
```

`check --kind trim` measures the seam along the long side. Repair a seam with `p2d.py offset RAW --axis x` (horizontal) or `--axis y` (vertical) plus a masked repaint, as for tiles.

Record `--axis x` or `--axis y` on `pack attempt`.
