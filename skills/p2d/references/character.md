# Characters (RPG Maker style)

People, monsters and NPCs that walk on a 3/4 top-down map, delivered as RPG Maker character sheets. The view is the JRPG overworld view: the body is seen from the front/side with a slight top-down tilt. Never write a bare "top-down" in prompts; models draw a bird's-eye view from it.

## Conventions per px

| px | Frame | Sheet | Rows top to bottom | Engine |
|---|---|---|---|---|
| 16 | 24x32 | 288x256 indexed, 8 slots of 72x128; index 0 = transparent key | Up, Right, Down, Left | RPG Maker 2000/2003 |
| 32 | 32x32 | `$name.png` 96x128 (or 8-character 384x256) | Down, Left, Right, Up | RPG Maker VX / VX Ace |
| 48 | 48x48 | `$name.png` 144x192 (or 576x384) | Down, Left, Right, Up | RPG Maker MV / MZ |

Three columns per row: step A, standing, step B. Walking plays stand, A, stand, B. A `!` prefix (charset `--object`) is for objects that should sit on the grid without the upward offset.

## Flow

### 1. Master (front idle)

Reserve `pack attempt DIR --name <char>-master --kind character --px P --prompt "..."`, then generate with `size <frame>`:

```
An RPG Maker style JRPG overworld character sprite of <who: outfit, hair, colors, props>, facing the viewer (front view with a slight top-down tilt), standing still, full body, chibi proportions with the head about one third of the height.
Exactly one character, centred, whole body inside the image with a clear magenta margin on every side.
Designed as a <frame W>x<frame H> pixel grid: each pixel a large crisp square block. Dark outline, light from the top-left.
Flat solid #FF00FF magenta background everywhere, no shadow, no floor, no text.
<pack line from SKILL.md>
```

```
p2d.py pixelize RAW --kind prop --size <frame> --anchor bottom --margin 1 --pack DIR --out DIR/work/<char>/master@<P>.png --scale 8
```

### 2. Approval gate

Show the `@8x` master and ask the user to approve or give changes (`ask_user_question`: Approve / Change something; without the tool, ask in the reply and end the turn). Generate NOTHING for directions or walking until the user approves. Changes = a new attempt with the previous master as reference. On approval: `pack accept DIR --name <char>-master ...`.

### 3. Walking sheet (4 directions x 3 frames in one generation)

Build a geometry reference before generation:

```
p2d.py anchor MASTER.png --rows 4 --cols 3 --cell 256x256 --margin 32 --out DIR/work/<char>/walk-guide.png
```

Use the accepted native PNG as MASTER, not the high-resolution raw. Read the guide image into context. Reserve `pack attempt DIR --name <char>-walk --kind character --px P --reference DIR/work/<char>/walk-guide.png`. Generate at the guide's 3:4 aspect ratio; the delivery frame remains 24x32, 32x32 or 48x48 regardless of raw cell shape. The guide repeats existing artwork; it is a pose-position reference, not the finished animation.

```
The displayed guide locks character identity, exact cell centers, body scale and foot baselines. Change only poses and facing, never zoom or reposition a character to fill a cell. Preserve the flat pixel style without beveled or embossed blocks.
Exactly 12 equal cells in 4 rows and 3 columns, no lines, borders or gaps drawn between cells.
Row 1 faces the viewer (down), row 2 faces left, row 3 faces right, row 4 faces away (up, back view).
Column 1: left foot forward. Column 2: standing still. Column 3: right foot forward.
Same size in every cell, feet on the same line in every cell, the whole body inside the central 70% of each cell, nothing crosses a cell edge.
RPG Maker style JRPG overworld sprite, chibi proportions, each pixel a crisp square block, <pack line>.
Flat solid #FF00FF magenta background.
```

```
p2d.py frames RAW --rows 4 --cols 3 --frame <frame> --out DIR/work/<char>/walk@<P> --pack DIR --write-profile DIR/work/<char>/walk@<P>.profile.json
```

`frames` must print `RESULT: PASS` before you continue.

Inspect the raw first if equal-cell cuts report clipped figures. When every figure is intact and fully empty background gaps separate rows and columns, try `--layout whitespace`; missing or ambiguous gaps must fail, not be guessed. It does not permit relaxed QC. Set one shared `--subject-height` with room for the widest walking pose (24 in a 24x32 frame is a starting point); never scale individual frames. If anchor or scale drift remains, regenerate using the guide rather than use `--loose` for walking.

### 4. Face check and repair

Read `preview DIR/work/<char>/walk@<P>/*.png --unit 256 --out ...`. At 24x32 and 32x32 the eyes are 1-2 pixels: if eyes are missing, merged into hair, or at different heights across the three columns of a row, fix them with `touch`:

```
p2d.py touch FRAME --set X,Y=#RRGGBB --set X,Y=#RRGGBB --pack DIR --out FRAME
p2d.py check FRAME --kind frame --size <frame> --pack DIR
```

Keep the approved identity: same eye color and spacing as the master, same outline, no new colors, no change to the silhouette.

### 5. Sheet and preview

```
p2d.py charset --format rm2k --frames DIR/work/<char>/walk@16 --pack DIR --slot 0 --out DIR/assets/<char>/<Pack>Charset@16.png
p2d.py charset --format vxace --frames DIR/work/<char>/walk@32 --pack DIR --out DIR/assets/<char>/<char>@32.png
p2d.py charset --format mv --frames DIR/work/<char>/walk@48 --pack DIR --out DIR/assets/<char>/<char>@48.png
p2d.py gif DIR/work/<char>/walk@P/r0c0.png DIR/work/<char>/walk@P/r0c1.png DIR/work/<char>/walk@P/r0c2.png --sequence 1,0,1,2 --out DIR/previews/<char>-walk-down@P.gif
```

rm2k sheets hold 8 characters: give each character of the pack its own `--slot` in the same file. `--mirror-right` builds the right row from the left row; use it only for left-right symmetric designs (nothing held in one hand). `pack accept DIR --name <char>-walk --px P --raw RAW --file <sheet>`.

Several px: finish the largest px first; each smaller px is its own walking-sheet generation with the accepted larger sheet raw as reference ("same character redrawn for a <frame> grid, simplified").
