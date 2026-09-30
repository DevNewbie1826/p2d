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

When four directions are requested, deliver down, left, right and up as four separately generated action sheets. Do not silently substitute one facing or put unrelated directions into an attack grid. Use the matching standing frame for each direction as its identity and geometry reference.

## Body sheet prompt

For grounded actions, first build an anchor guide from the accepted native standing frame for the requested facing:

```
p2d.py anchor STANDING.png --rows R --cols C --cell 256x256 --margin 32 --out DIR/work/<char>/<action>-<facing>-guide.png
```

Read the guide into context and reserve `pack attempt DIR --name <char>-<action>-<facing> --kind animation --px P --reference GUIDE`. Preserve its aspect ratio and geometry during generation. Use the same cell geometry and integer scale for compatible actions at the same px. A different target px needs a separately redrawn and accepted standing reference first, not an enlarged smaller sprite.

```
Image 1 is the approved character. Draw a <N>-frame <action> animation of exactly this character facing <facing>, same design, colors and proportions.
The displayed anchor guide fixes cell centers, standing body scale and feet baselines. Change only the poses, never zoom individual frames or fill the empty margins.
Exactly <N> equal cells in <rows> rows and <cols> columns, read left to right, top to bottom: <frame 1: anticipation>, <frame 2: ...>, ..., <last: recovery>.
Body only: no slash arc, trail, spark, projectile, dust or impact effect.
For fixed-cell sword attacks, use a short blade, bent elbows and a compact chop beside the torso; no lunge or extended thrust. Keep the blade below the top of the head and the total pose width below standing character height.
Same body size in every cell, <grounded actions: feet on the same line in every cell>, the whole body and weapon inside the central 70% of each cell, nothing crosses a cell edge, no lines between cells.
RPG Maker style JRPG sprite, chibi proportions, each pixel a crisp square block, <pack line>. Flat solid #FF00FF magenta background.
```

Process with the walking height so the body scale matches the walk:

```
p2d.py frames RAW --rows R --cols C --frame WxH --subject-height <subject_height from the walk profile JSON> --out DIR/work/<char>/<action>@<P> --pack DIR
```

Grounded actions (idle, attack, cast, hurt) must pass strict QC. Jumps, knockback, death and anything whose silhouette changes on purpose add `--loose`, then are judged visually. `--profile` reuses the exact raw-pixel pitch and is only valid for a raw with the same canvas size and grid as the profiled one.

`scale_cv` measures the entire opaque silhouette, including weapons; it is not a body/anatomy detector. Inspect head, torso and limb thickness before diagnosing a failure. For the default compact attack, regenerate with the weapon inside the common silhouette envelope. If the user explicitly wants overhead swings or lunges, preserve that action and use a documented action-specific review rather than pretending the generic numeric gate measures anatomy.

If equal cuts intersect intact figures separated by empty background bands, inspect the raw and try `--layout whitespace`. Missing or ambiguous separators must remain failures. If a blade widens the pose beyond the delivery frame, request a more compact pose or an explicitly wider delivery frame without shrinking only that action's body. Do not use `--loose` merely to make a failed attack pass.

## Effects

Effects are their own sheets layered by the game: reserve `--kind fx`, same grid rules, prompt `only the <effect>, no character`, then `frames ... --anchor center --loose`.

## Deliverables

```
p2d.py gif DIR/work/<char>/<action>@P/r0c0.png DIR/work/<char>/<action>@P/r0c1.png ... --duration 100 --out DIR/previews/<char>-<action>@P.gif
p2d.py atlas DIR/work/<char>/<action>@P/r*.png --cols C --out DIR/assets/<char>/<char>-<action>@P.png
```

Read the GIF's frames (or the atlas at `@8x` via `preview`) before accepting: the body must not grow or shrink, feet must not slide on grounded actions.
