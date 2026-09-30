# When a check fails

Read the `FAIL_REASON` lines, find the row, apply the fix. A new generation needs a new `pack attempt` first; after three attempts the asset gets no more generations.

## Diagnose

| Symptom | Fix |
|---|---|
| `raw-check`: checkerboard detected | The model painted fake transparency. New attempt: `flat solid #FF00FF magenta background, not a checkerboard, no pattern`. |
| `raw-check`: key coverage or border too low | Scenery, floor or frame around the subject. Remove scene words; add `nothing but flat magenta around the object`. |
| `check`: KEY_RESIDUE > 0 | Re-run `pixelize` with `--tol 150` (up to 180). If the subject itself is pink or purple, re-generate on another key (`--key #00ffff`, same key in the prompt). |
| `check`: colors over the cap | Re-run `pixelize` with `--pack DIR` (pack palette) or a lower `--max-colors`; if detail is lost, ask the model for fewer colors. |
| `check`: OUT_OF_PALETTE | Re-run `pixelize` with `--pack DIR`. |
| `check`: transparent pixels in a tile/wall/trim | Pixelize with `--bg none`; regenerate if the art has holes. |
| `check`: SEAM_X / SEAM_Y too high | `offset RAW --axis <x, y or xy> --out OFFSET --mask MASK`; new attempt: `gen_image.mjs --ref OFFSET --mask MASK` with `repaint only the masked band so the pattern continues seamlessly`; then `offset EDITED --axis <same> --inverse --out FIXED` and pixelize again. |
| `check`: NOISE (tile/wall/trim FAIL) or NOISE_REVIEW yes (prop/frame) | Too many pixels without a same-color neighbour (`SINGLETON_PERCENT`) or clusters too small (`MEAN_CLUSTER`) for this kind and px (bands measured on original packs). Look at the @8x: if the singles are eyes, blade tips, trim or one sparkle, it is fine; if they are scattered texture, new attempt with the feature budget from the kind reference (`N connected <features> on a calm field, no isolated pixels`). Never pass `--allow-noise` unless the user asked for a dithered or dense style. |
| Mushy, noisy or blurry cells after pixelize | The model drew detail finer than the grid. New attempt: `bold, simple shapes, each pixel a large square block, about <P> blocks across`. |
| Subject too small or too big in the tile | `--margin`, `--anchor`, or a prompt that says `fills the tile` / `small object`. |
| `frames`: EMPTY_FRAMES | The grid has fewer drawings than cells. Restate `exactly N equal cells in R rows and C columns`. |
| `frames`: EDGE_TOUCH_FRAMES or CLAMPED_FRAMES | Parts cross cells. `smaller character, whole body inside the central 70% of each cell`; or use a wider `--frame`. |
| `frames`: SCALE_CV too high | Poses drawn at different sizes. Restate `same size in every cell`, pass the approved master as reference. Deliberate size changes (jump, death) use `--loose`. |
| `frames`: ANCHOR_Y_STD too high | `feet on the same line in every cell`. |
| Wrong row order in a sheet | Regenerate, or fix it with `charset --order` naming the rows as generated. |
| Style drifts from the pack | Add accepted pack assets as style references and the palette hex list. |
| Face unreadable at 24x32 / 32x32 | `touch FRAME --set X,Y=#RRGGBB ... --pack DIR --out FRAME` with pack colors only; keep the master's eye color, spacing and outline; re-run `check FRAME --kind frame`. |

## Choose the best attempt

Compare ALL kept candidates of all attempts (read their `@8x` previews side by side with the references), not only the latest. Accept the best one with `pack accept`.

## Attempt limit reached

`pack attempt` exit 2 means three attempts are used. Do not generate again and do not reset pack.json. A numeric PASS is necessary, not sufficient: never accept a candidate that fails the visual review (features, eyes, repeat, sizes) because attempts ran out. If no candidate passes both, tell the user which check fails, show the best candidate, and record it as a manual follow-up (`pack set DIR --notes "manual: <asset> <reason>"`).

Never loosen `--seam-max`, the frame gates, or the color caps to turn a FAIL into a PASS without telling the user why.

## Pixel guard diagnostics

- `requested size halves the generated grid`: pixelize at the block size and use `split`.
- `SEAM_X_EDGE_REVIEW` / `SEAM_Y_EDGE_REVIEW`: opposite edges are identical. A natural period can do this, a copied edge also does: open the 4x4 repeat; never copy an edge to fix a seam, repaint continuity (`offset` + masked edit).
- `NOISE_HINT`: the singleton rate `--despeckle auto` would reach; re-run QC after it.
- `COLORS_BELOW_BUDGET`: the colour cap is below the tile budget (16: 3, 32: 4, 48: 4); review lost features.
- `touch` refuses more than max(8, 2% of opaque pixels) changed pixels (exit 2). A repair that needs more is a redraw, not a touch; `--force-many` only when the user asked for a hand edit.
- 24x32 (16px) character frames with 31-52% singletons (the measured RM2000 range) do not ask for noise review; other frame sizes keep the review.

## Acceptance gate

`pack accept` reruns `check` with the asset kind, the reserved size and axis and the pack palette; a FAIL exits 2 with `check fails: <reasons>`. Characters and animation frames also need a passing face gate (automatic, or `--face-report`; `--no-face "reason"` only for back views and visored helmets). Fix the cause and accept again; never loosen checks to get through. `--replace` is needed to overwrite an accepted entry; the previous one is kept in history.
