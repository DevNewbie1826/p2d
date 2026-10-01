# p2d: close the gap between our walking charset and the user's RM2000 reference

Original request (2026-10-01, user, Korean): "2026-10-01-13-54-56.mp4 영상 올림 우리가 만든거랑 니가 학습한거랑 뭐가 다른지 좀 분석해서 개선해줘. 변경사항은 계속 반영해도 됨. 영상은 시청후 삭제 바람." (Uploaded a video: analyze how what we made differs from what you learned, and improve it. Changes may be shipped continuously. Delete the video after watching.)

## Discovery (video analysed, then deleted)

The 5.7 s, 926x714 video shows an animated side-by-side: row "REFERENCE" = an authentic RPG Maker 2000 charset girl (brown hair, headband, blue tunic, red gloves/boots, sword) walking Up/Left/Down/Right; row "MINE (Terra sheet)" = our Terra walk sheet (v1). Both rows are drawn at the same pixel pitch (8.3 video px per logical px, fitted by grid search), so native frames were reconstructed and measured. Comparison sheet: `.omo/evidence/p2d/video-compare/ref-vs-v1-vs-v2@5x.png` (reconstructed reference | v1 | v2). Video file and extracted frames deleted (receipt in the evidence notes).

Measured differences (native px):

| Property | Reference (RM2000) | Ours (v1 / v2 Terra) |
|---|---|---|
| Subject size, front/side | 16 x 23 (step frames 24) | 14-17 x 26-27 |
| Width/height | 0.68-0.70 | 0.54-0.62 |
| Head share | ~12 of 23 rows (>50%), oversized gloves/boots | ~12 of 26, slim limbs: reads lanky |
| Head across the walk cycle | pixel-identical; only a 1 px bob, legs/arms redrawn | redrawn every frame: head-band agreement 0.51-0.92, eye shape/color changes (side face gate failed 6/6 on v2) |
| Eyes | big 1x2 blue iris + white sclera, read at 1x | small, drifted to green on down row |
| Materials | saturated distinct masses (royal blue, crimson, white) inside a dark contour | pastel greens/red, noisy hair highlights |

Root cause of the visible jitter and the side-face failures: the image model redraws the head in every walking cell, and nothing in the pipeline restores the approved head. Root cause of the lanky look: the 16px budget recommends `--subject-height 26` and the prompt does not demand the RM2000 stocky build.

## Affected users and ideal state

Users: the p2d user generating RPG Maker walking charsets (16px first), and agents following `skills/p2d` in fresh sessions.

| ID | IS (ideal state) | Reason |
|---|---|---|
| IS1 | A cut walking-frame directory can keep each row's standing frame head pixel-identical in both step frames, with the RM2000 1 px bob, through a new CLI command `headlock FRAMES_DIR --head-rows N [--head-bob B]` that runs after `frames` (and after any face repair of the standing donors), reports `HEAD_DRIFT` before and after, and records `head_lock` in frames.json | the reference keeps the head fixed; our redrawn heads jitter and break the face gate; a separate command lets donors be repaired (face --stamp/touch) before they are copied |
| IS2 | `frames` and every other command behave exactly as before | no regression for existing sheets and tests |
| IS3 | character.md tells agents to use head lock for walking and gives the reference-measured 16px build (about 16x23-24, width/height about 0.7, head about half, oversized hands/boots, saturated material masses, readable 1x2 eyes) instead of the lanky 26-row default | fresh sessions must reproduce the improvement from the skill alone |
| IS4 | Applied to a new Terra walk (v3) from the user-approved master, the improved pipeline yields a sheet whose step heads equal the stand heads (drift 0) and whose front/side face gates agree with the stand frame | proves the change on the user's actual asset |

| GAP | Today | Closed by |
|---|---|---|
| G1 | no head lock; HEAD drift not measured | node `headlock` |
| G2 | doc recommends 26 rows for 16px and no head-lock step | node `docs` |
| G3 | no evidence on the real asset | node `qa` |

## Success criteria and QA scenarios

- C1 (IS1, happy): `python3 -m unittest tests.test_characters -v` includes new headlock tests (RED first on unchanged code, then GREEN): synthetic 4x3 frames dir whose step heads differ from the stand; after `headlock DIR --head-rows N` the top-N band of each of the 8 step frames equals the stand's band shifted down by the bob (default 1), rows above it are transparent, rows below are the step frame's own, `HEAD_DRIFT_BEFORE` > 0, `HEAD_DRIFT_AFTER` = 0, frames.json gets `head_lock`.
- C2 (IS1, edge): missing dir / missing r{r}c{c}.png, N < 1, bob < 0, or N + bob beyond the frame height (or an empty standing frame) exits with a user error (exit 2, no traceback) and leaves the files unchanged.
- C3 (IS2, regression): full suite `npm test` green; `frames` on `p2d-out/ff6-terra/raw/terra-walk-v2@16_a1.png` writes PNGs byte-identical on the branch and on `main` (sha256 compare).
- C4 (IS4, real surface, compliant route): generate a NEW walk asset `terra-walk-v3` (its own 3-call budget, no consent needed) from the user-approved Terra master following the UPDATED character.md; `frames` must print `RESULT: PASS` under the unchanged gates (no `--loose`); every standing donor (down/left/right) must pass `face --auto` (repair with `face --stamp`/`touch` first if not); then `headlock`; PASS = all 8 step heads identical to their donors (python compare 8/8), `face --auto` PASS on all 9 down/left/right frames, charset + 4 GIFs built and visually inspected beside the reconstructed reference sheet. If no attempt reaches `frames RESULT: PASS` within the budget, C4 is reported as FAIL with the best candidate's metrics (never waived).
- C5 (IS3, docs): read-through QA of character.md: head-lock step present in the walking flow with the exact flags, 16px build numbers cite the reference measurement, no contradiction with the master proportion gate (0.62) and existing budgets.

WHEN TO STOP: I'll stop right away when the PR with C1-C5 evidence is APPROVED by the ultrabrain review, merged to main, C4 re-confirmed on merged main, worktree/branch removed, and the user has the report.

## Test decision

Behavioral TDD for the new `headlock` command behavior in `tests/test_characters.py` (the file that already holds `frames` tests). Docs get read-through QA only.

## Tasks and DAG (one task, one worktree `../p2d-wt-walkref`, branch `p2d-walk-reference`)

- `headlock` (deep-low): new `skills/p2d/scripts/p2d_lib/headlock.py`, its registration in `skills/p2d/scripts/p2d_lib/cli.py`, tests in `tests/test_characters.py`. RED -> GREEN -> refactor.
- `docs` (writing): `skills/p2d/references/character.md` only (+ `skills/p2d/SKILL.md` only if a router line needs the flag). Parallel with `headlock` (disjoint files).
- `qa` (deep-low, after both): C3 regression compare, C4 real-asset run, charset/GIF, visual comparison sheet, evidence under the evidence root.
- then PR, ultrabrain review, merge (lead).

## Out of scope (follow-ups)

- F1: the main checkout carries an uncommitted, untested `pack accept --allow-noise` change from an earlier session (`skills/p2d/scripts/p2d_lib/pack.py`).
- F2: `anchor_y_std` measures feet drift in the raw cells although `frames` re-anchors every output frame to the bottom; Terra sheets failed at 0.060-0.066 while their delivered baselines were stable. Changing gate semantics is not required by this request.

## Follow-up file

`<ulw-loop evidenceRoot>/follow-ups.md` (absolute path recorded below once the loop initializes).
