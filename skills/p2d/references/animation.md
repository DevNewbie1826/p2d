# Animations and effects

Action loops for a character that already has an approved master or walking sheet: idle, attack, cast, hurt, jump, death, plus separate effect sheets (slash arcs, sparks, spells, projectiles).

## Grid per action

One action and one facing per raw generation. Multi-row grids only; a raw single row (1xN) drifts sideways.

| Frames | Grid (rows x cols) |
|---|---|
| 4 | 2x2 |
| 6 | 2x3 |
| 8 | 2x4 |
| 9 | 3x3 |
| 12 | 3x4 |

Frame size = the character frame for the px (24x32, 32x32, 48x48). A weapon or pose that needs room gets a wider frame (e.g. 48x32 at px 16) while the body keeps its walking height.

Default facing: toward the viewer (down) on maps; left for side-view battlers. Name each sheet `<char>-<action>-<facing>`.

## Body sheet prompt

Reserve `pack attempt DIR --name <char>-<action>-<facing> --kind animation --px P --reference <approved master or walk raw>`, canvas `size <cols*W>x<rows*H>`.

```
Image 1 is the approved character. Draw a <N>-frame <action> animation of exactly this character facing <facing>, same design, colors and proportions.
Exactly <N> equal cells in <rows> rows and <cols> columns, read left to right, top to bottom: <frame 1: anticipation>, <frame 2: ...>, ..., <last: recovery>.
Body only: no slash arc, trail, spark, projectile, dust or impact effect.
Same body size in every cell, <grounded actions: feet on the same line in every cell>, the whole body and weapon inside the central 70% of each cell, nothing crosses a cell edge, no lines between cells.
RPG Maker style JRPG sprite, chibi proportions, each pixel a crisp square block, <pack line>. Flat solid #FF00FF magenta background.
```

Process with the walking height so the body scale matches the walk:

```
p2d.py frames RAW --rows R --cols C --frame WxH --subject-height <subject_height from the walk profile JSON> --out DIR/work/<char>/<action>@<P> --pack DIR
```

Grounded actions (idle, attack, cast, hurt) must pass strict QC. Jumps, knockback, death and anything whose silhouette changes on purpose add `--loose`, then are judged visually. `--profile` reuses the exact raw-pixel pitch and is only valid for a raw with the same canvas size and grid as the profiled one.

## Effects

Effects are their own sheets layered by the game: reserve `--kind fx`, same grid rules, prompt `only the <effect>, no character`, then `frames ... --anchor center --loose`.

## Deliverables

```
p2d.py gif DIR/work/<char>/<action>@P/r0c0.png DIR/work/<char>/<action>@P/r0c1.png ... --duration 100 --out DIR/previews/<char>-<action>@P.gif
p2d.py atlas DIR/work/<char>/<action>@P/r*.png --cols C --out DIR/assets/<char>/<char>-<action>@P.png
```

Read the GIF's frames (or the atlas at `@8x` via `preview`) before accepting: the body must not grow or shrink, feet must not slide on grounded actions.
