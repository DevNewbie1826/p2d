# Characters (RPG Maker style)

People, monsters and NPCs that walk on a 3/4 top-down map, delivered as RPG Maker character sheets. The view is the JRPG overworld view: the body is seen from the front/side with a slight top-down tilt. Never write a bare "top-down" in prompts; models draw a bird's-eye view from it.

## Conventions per px

| px | Frame | Sheet | Rows top to bottom | Engine |
|---|---|---|---|---|
| 16 | 24x32 | 288x256 indexed, 8 slots of 72x128; index 0 = transparent key | Up, Right, Down, Left | RPG Maker 2000/2003 |
| 32 | 32x32 | `$name.png` 96x128 (or 8-character 384x256) | Down, Left, Right, Up | RPG Maker VX / VX Ace |
| 48 | 48x48 | `$name.png` 144x192 (or 576x384) | Down, Left, Right, Up | RPG Maker MV / MZ |

The px is the tile unit, not the frame: a 16px character is a 24x32 frame, never 16x16; `pack accept` rejects any other character size. Pixelize every master and frame with `--size <frame>` from this table.

## Drawing budget per px (measured on original sprites)

The frame is not the drawing: a character rarely fills its cell, and a small size is a redesign, not a shrunk illustration. Budgets from original PNGs (user-supplied RM2000 charset: 8 characters / 96 frames at 16, PIPOYA 32, Clockwork Raven / Character Base 48):

| px | Goal | Subject in frame | Head | Eyes | Colors / frame | Shading |
|---|---|---|---|---|---|---|
| 16 | silhouette, readable face, connected masses | usually 14-20 x 23-28; measured 12-22 x 22-29 in 24x32 | front idle 10-15px including headgear, 43-54% | each iris 1x2 dark/light + pale blue/white sclera; front two, side one, back none | front idle 19-28; all frames 14-31; character union 22-32 (raise `--asset-colors` and pack palette limit for this style) | skin 3; hair usually 3-6 (gold hair up to 8); cloth 3-6; silver metal 4-6, tiny buckle 2, red armor 7; no random texture |
| 32 | proportion, expression, pose | about 20-29 x 27-32 | 55-60% for chibi | about 3x5 incl. lid, 1x2 pupil | 12-16 (PIPOYA-rich style 24-40: raise `--asset-colors`) | base, shadow, light per major material |
| 48 | material, individuality, animation-ready | about 22-35 x 40-47 | 45-60% | about 5x4: dark upper lid, white, 2-3px iris | 12-16 economical; rich styles 40+ (raise `--asset-colors`) | 3-5 bands; metal = narrow bright band + dark facet, cloth = broad folds, hair = highlights along locks |

What survives each step down: silhouette, dominant color masses, face/visor placement, the one identity cue (hat peak, bow gap, shield, blade), handedness. Drop first: trim, rivets, stitching, secondary straps, fletching, tiny folds. Widen a gap that must read (bow, arm) to at least 1 real pixel. Outline: dark contour colored per material is usual; pure black is optional; boot soles and tips may meet transparency.

16px construction: eyes in the measured front idle sit at x10/13 (two pixels between), usually y15-16, not a universal placement stencil. Blue irises use dark `#212591` above `#1D73D6`; brown uses `#5A2000` above `#944118`; the knight uses two `#202020` pixels per eye. Pale `#B0D7FF` and white sit beside them. A short 1px-high dark upper lid/brow separates eyes from hair or helmet; nose/mouth are omitted or implied by skin highlights, not mandatory black dots. Preserve face skin and readable eyes before adding trim. Front eyes are an identical pair (same 1x2 shape, same top row); each has a pale/white sclera pixel on its outer side. Separate big masses by value and hue, not only by outline: originals put a saturated cloth or armour color (red, blue, gold) against light metal and skin, so a silver knight needs one strong accent mass (tabard, cape lining, belt) and hair clearly lighter or darker than the armour next to it.

16px outline/shading: mostly 1px contours, brown `#290800`/skin `#621300`, navy `#00084A`/`#10186A`, gray or black per material; selected shoulder metal, hair tips, hat trim and cloth edges can meet the key without a dark enclosure. Continuous-outline packs still require enclosure. Skin commonly uses `#BF643D`, `#EE9C7B`, `#F9C19D`; hair and cloth have connected highlight bands, metal narrow bright bands. The eight front-idle frames have 31-52% same-color 4-neighbour singletons (9-28% with 8-neighbours): useful eye/trim/highlight pixels are not automatically noise.

Eye gate at every px applies to front/side, not the back: both eyes (one in side view) must be visible, not covered by hair, helmet shadow or outline; reject/redraw or `touch` on failure. Walking: stable foot baseline, head bob at most 1px, legs and arms redrawn (not the body shifted sideways). At 16px A/B heads and eyes are 1px below standing; foot tips may vary 0-1px (measured bottom y30-31). Alternate legs and opposing arms; redraw sleeves, hem, trailing hair and cloak as needed. Side views narrow the face/body and show one eye, nose/cheek edge and overlapping limbs, not a squashed front; wide hats may retain their width. Back views replace the face with hair/headgear and back clothing. Mirror only genuinely symmetric designs.

Three columns per row: step A, standing, step B. Walking plays stand, A, stand, B. A `!` prefix (charset `--object`) is for objects that should sit on the grid without the upward offset.

## Flow

### 1. Master (front idle)

Reserve `pack attempt DIR --name <char>-master --kind character --px P --prompt "..."`, then generate with `size <frame>`:

```
An RPG Maker style JRPG overworld character sprite of <who: outfit, hair, colors, props>, facing the viewer (front view with a slight top-down tilt), standing still, full body, chibi proportions with <head/eyes/colors/shading from the budget row for P>. <16: "native 24x32 frame for 16px tiles, subject about 14-20 x 23-28px (wide headgear up to 22px), head including headgear about half the subject height, about 19-28 colors; two readable 1x2 dark/light irises with pale blue/white sclera and visible skin, short dark upper lids, nose/mouth implied by skin; 1px material-colored selective contour, skin 3 tones, connected hair/cloth highlights and narrow metal light bands, no random texture"; 32: "one expression cue and a deliberate stance"; 48: "materials told apart by highlight shape, one personal asymmetry">.
Exactly one character, centred, whole body inside the image with a clear magenta margin on every side.
Designed as a <frame W>x<frame H> pixel grid: each pixel a flat single-color sample. Use the pack's outline convention and light direction. If the outline is continuous, hair tips, face colors and equipment remain enclosed by it; no exposed interior colors at silhouette gaps.
Flat solid #FF00FF magenta background everywhere, no shadow, no floor, no text.
<pack line from SKILL.md>
```

```
p2d.py pixelize RAW --kind prop --size <frame> --anchor bottom --margin 1 --pack DIR --out DIR/work/<char>/master@<P>.png --scale 8
p2d.py face DIR/work/<char>/master@<P>.png --eyes <every eye-core X,Y> --skin <face-skin X,Y> --scale 8
```

Immediately after pixelizing every master, run `face`, open its `CROP`, and require every `EYE_n` and `RESULT` to PASS before approval. Use the coordinate and repair rules in step 4.

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
<16: "Row 1 up/back, row 2 right, row 3 down/front, row 4 left"; 32/48: "Row 1 down/front, row 2 left, row 3 right, row 4 up/back">.
Column 1: left foot forward. Column 2: standing still. Column 3: right foot forward.
<16: "Preserve native 24x32 scale and identity, about 19-28 colors per pose, stable foot baseline with at most 1px foot-tip variation; A/B head and eyes 1px below standing. Alternate legs and opposing arms, redraw sleeves/hem/hair/cloak, never translate the whole sprite sideways. Front has two 1x2 dark/light irises with pale/white sclera and visible skin; side has one readable eye and a narrower face/body with overlapping limbs; back has no eyes. Keep material-colored 1px contours and connected shading bands. Wide hats may stay wide (up to 22px); leave key around the contained subject, no fixed 70% width cap"; 32/48: "Same size in every cell, feet on the same line, the whole body inside the central 70% of each cell">. Nothing crosses a cell edge.
RPG Maker style JRPG overworld sprite, chibi proportions, each pixel a crisp square block, <pack line>.
Flat solid #FF00FF magenta background.
```

```
p2d.py frames RAW --rows 4 --cols 3 --frame <frame> --out DIR/work/<char>/walk@<P> --pack DIR --write-profile DIR/work/<char>/walk@<P>.profile.json
```

`frames` must print `RESULT: PASS` before you continue. After cutting walk frames, the `face` gate in step 4 is REQUIRED on at least one down, one left and one right frame.

Inspect the raw first if equal-cell cuts report clipped figures. When every figure is intact and fully empty background gaps separate rows and columns, try `--layout whitespace`; missing or ambiguous gaps must fail, not be guessed. It does not permit relaxed QC. Set one shared `--subject-height` with room for the widest walking pose (24 in a 24x32 frame is a starting point); never scale individual frames. If anchor or scale drift remains, regenerate using the guide rather than use `--loose` for walking.

### 4. Face check and repair

REQUIRED after every master pixelization and walk-frame cut: run `face` on the master and one down, left and right frame, list every dark iris/pupil pixel (both pixels of a 1x2 core, both front eyes), and choose an actual face-skin pixel. Coordinates are native frame pixels, 0-based, not preview coordinates. White/pale sclera is not listed as an eye core; it counts as face around the eye. Each eye (a connected group of listed pixels) needs face (skin tone or sclera) on 2 sides per eye pixel, or 1 per pixel for a single side-view eye; all 24 front/side idle frames of the measured RM2000 charset pass, a knight whose eyes sit in hair fails. For an opaque sheet pass its background with `--key`:

```
p2d.py face FRAME --eyes <X,Y X,Y ...> --skin <X,Y> --scale 8
```

Every `EYE_n` and `RESULT` must PASS: opaque eyes, skin-minus-eye luma contrast at least 60, at least two skin-colored 4-neighbours per listed pixel. Open each emitted `CROP`; verify eyes, skin, brows and implied nose/mouth at native size and 8x. The measured RM2000 white-sclera construction can fail the skin-neighbour gate even when readable: do not claim source sprites pass it or waive a FAIL on new assets. Reject/redraw or `touch`, rerun `face`, and reopen the crop before accepting.

Read `preview DIR/work/<char>/walk@<P>/*.png --unit 256 --out ...` and inspect all 12 frames. At 24x32 and 32x32 the eye core is 1-2 pixels per eye: if eyes disappear or merge into hair, fix them with `touch`. Compare eye height relative to the head, allowing the intentional 1px 16px walking bob:

```
p2d.py touch FRAME --set X,Y=#RRGGBB --set X,Y=#RRGGBB --pack DIR --out FRAME
p2d.py check FRAME --kind frame --size <frame> --pack DIR
```

Keep the approved identity: same eye color and spacing as the master, same outline, no new colors, no change to the silhouette.

For a continuous-outline pack, run `check FRAME --kind frame --size <frame> --pack DIR --outline-colors '<chosen dark palette colors, comma-separated>'` on the master and every delivered frame. Zero uncovered exterior boundary pixels is required; frame containment alone cannot detect hair/interior colors escaping the contour. Enclosed holes are ignored by this check. Inspect reported coordinates, preserve hair/eye identity, repair a sibling with `touch` if appropriate, and recheck. A closed contour alone does not prove good art.

### 5. Sheet and preview

```
p2d.py charset --format rm2k --frames DIR/work/<char>/walk@16 --pack DIR --slot 0 --out DIR/assets/<char>/<Pack>Charset@16.png
p2d.py charset --format vxace --frames DIR/work/<char>/walk@32 --pack DIR --out DIR/assets/<char>/<char>@32.png
p2d.py charset --format mv --frames DIR/work/<char>/walk@48 --pack DIR --out DIR/assets/<char>/<char>@48.png
p2d.py gif DIR/work/<char>/walk@P/r<R>c0.png DIR/work/<char>/walk@P/r<R>c1.png DIR/work/<char>/walk@P/r<R>c2.png --sequence 1,0,1,2 --out DIR/previews/<char>-walk-down@P.gif
```

For the down-walk GIF, use `R=2` at 16px and `R=0` at 32/48px.

rm2k sheets hold 8 characters: give each character of the pack its own `--slot` in the same file. `--mirror-right` builds the right row from the left row; use it only for left-right symmetric designs (nothing held in one hand). `pack accept DIR --name <char>-walk --px P --raw RAW --file <sheet>`.

Several px: finish the largest px first; each smaller px is its own walking-sheet generation with the accepted larger sheet raw as reference ("same character redrawn natively for a <frame> grid: keep silhouette, colors, face placement, identity cue and handedness; drop <the list above>"). Compare sizes side by side at 1x and 8x: identity visible only at 8x is a failure.
