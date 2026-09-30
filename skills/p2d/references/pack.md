# Packs: several assets, variants, several px

## Order of work

1. `pack show DIR` (or `pack init`). px must be known (SKILL.md section 1).
2. Palette: if pack.json has none and the user gave existing assets, `pack palette DIR --from <their pngs>` first. `inspect <their png>` also reports `SUGGESTED_PX`.
3. Make the most representative surface first (usually the main floor tile) at the largest px. Accept it, then `pack palette DIR --from <that png>` if the pack still has no palette and re-run `pixelize` for it so it uses the pack palette.
4. Every later generation gets 1-2 accepted pack assets as style references: `Image N is a style reference from the same game: match its palette, pixel density, outline and lighting; do not copy its subject.`
5. Put the pack palette in each prompt when it exists: `use only these colors: #.., #.., ...`.

## Several px: largest first, then redraw

For each asset: generate, pixelize, check and accept the largest px. Each smaller px is a NEW generation (never a resize of the larger file):

```
p2d.py pack attempt DIR --name <name> --kind <kind> --px <small> --reference <accepted larger raw> --prompt "..."
```

```
Image 1 is the approved <W>x<H> version of this <asset>. Redraw the same <asset> as a <w>x<h> pixel-art <kind> for the same game: same design, materials, colors and lighting, the same <N> major <features> in the same places (merge only the smallest), simplified for the smaller grid (fewer and bigger details, clear silhouette), each pixel a crisp square block. <background rule of the kind>.
```

Before writing it, count the major features (pockets, ripples, stones, planes) in the accepted larger version and name that number. After pixelizing, read both sizes side by side: if the smaller one no longer reads as the same design (different layout, a feature gone or invented), it is a FAIL even when `check` passes.

Pass the accepted larger raw with `--ref`. Pixelize with the smaller `--size`, check, accept.

## Variants

A variant keeps shape, size and pixel density and changes one property: lighter, darker, damaged, mossy, snowy, open/closed, color swap.

```
p2d.py pack attempt DIR --name <base>-<variant> --kind <kind> --px P --variant-of <base> --reference <accepted base raw at P> --prompt "..."
```

```
Image 1 is the approved <asset>. Make a <variant> variant of exactly this asset: change only <what changes>; keep the outline, shape, size, pixel grid, lighting and style. <background rule of the kind>.
```

Make the variant at every px the base has, each with that px's base raw as reference.

## Layout

```
DIR/pack.json                         px, palette, style lock, attempts, accepted files
DIR/raw/<name>@<px>_a<k>*.png         every generation (never deleted)
DIR/assets/<name>/<name>@<px>.png     delivered asset (+ @8x preview)
DIR/work/...                          offsets, masks, frames
DIR/previews/pack.png                 reference-style overview
```

Finish with `p2d.py preview DIR/assets/*/*.png --out DIR/previews/pack.png` and, when the game wants one image, `p2d.py atlas DIR/assets/*/*@<px>.png --out DIR/assets/atlas@<px>.png`.
