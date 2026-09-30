# Plan: p2d — OMO skill for prompt-to-2D pixel-art game assets

## Original request (purpose boundary)

User (Korean, this session): build **p2d**, an OMO skill that turns a prompt (colloquial Korean/English text and/or reference images) into 2D pixel-art game assets, absorbing the strengths of the analyzed skills (generate2dsprite, creating-sprites, PixelLab API, Pixel Art Engine, plus Kevin-Herr tiles and Picxel concepts). Build everything at once (no milestones). "Re-read the whole conversation, miss nothing." Conventions (color counts, RPG Maker formats, etc.) follow standard practice; every other open choice follows the assistant's earlier recommendations.

Blockers for this work: the request not delivered, a regression introduced by this change, or invalid proof. Anything else is a follow-up note.

## Requirement ledger (every decision from the conversation)

| # | Requirement | Source in conversation |
|---|---|---|
| R1 | Skill for prompt -> 2D pixel-art game assets; input = colloquial text and/or reference images | first message; "레퍼런스는 이미지일때도 있지만 구어체로 원할때도 있어" (shared chat) |
| R2 | Asset kinds: floor `tile`, `wall` (incl. 3/4 top+front face), `trim` (repeat strips), `prop` (crates, barrels, pillars), `character`, plus `animation` | dungeon reference image; "인물들 캐릭터도" ; "한번에 다 만들거야" |
| R3 | Pack-level style lock: one shared palette, light direction (top-left), outline rule, pixel density — cohesive packs like the reference image | analysis turn 2/3 |
| R4 | Real pixelization post-process (grid/pitch, per-cell mode color, palette quantization, binary alpha, orphan-pixel cleanup) — the gap none of the analyzed skills fill | analysis turn 1 |
| R5 | QC: raw transparency/checkerboard, seams as pixel invariants, color caps, character scale/anchor gates; diagnose-then-fix; max 3 attempts; keep all candidates; compare with references visually | analysis turns |
| R6 | Variants (lighter/darker/damaged) of the same asset | reference image rows |
| R7 | Resolutions 16/32/48 (tile unit). Explicit single or multiple values are honored; if unspecified ask (multi-select); store answer in pack.json and reuse within the pack; with a pixel-art reference, detect and suggest | "16 32 48 명시한거 ... 명시 안하면 물어보기"; assistant refinement accepted |
| R8 | Multi-resolution = per-size redraw using the accepted version as identity reference (largest first), never a mechanical downscale; reference pairs are 16/32 versions of one asset | "이미지속 쌍은 16 32 버전이 맞을거임" |
| R9 | Generation canvas recommendation (1536 square divisible by 16/32/48; 1024 for exploration); script computes a valid size for any logical canvas | direction turn |
| R10 | OMO only; image generation = GPT only through OMO's image tool (`generate_image`, or native `image_generation`), following `gpt-image-gen`; no Grok, no API keys, no backend code | "그록은 제외", "omo 용으로만" |
| R11 | Magenta `#FF00FF` key background by default for prop/character; tile/wall/trim opaque; `background: transparent` optional when `generate_image` exists | OMO direction turn |
| R12 | Strict progressive disclosure: L1 description (trigger only), L2 SKILL.md (~100-150 lines: pipeline, hard rules, routing table), L3 one reference per topic read only when needed, no reference->reference chains, `qc.md` only on failure, scripts self-document via `--help` | "점진적 공개를 철저히" |
| R13 | Layout: `SKILL.md`, `references/{pack,tile,wall,trim,prop,character,animation,qc}.md`, `scripts/p2d.py` (+ library), `palettes/` | proposed skeleton, accepted |
| R14 | RPG Maker (쯔꾸르) view: prompts must say "JRPG/RPG Maker overworld sprite, front-facing 3/4 view", never bare "top-down" | RM2000 charset image turn |
| R15 | Character conventions: 16 -> RM2000/2003 24x32 frames (rows Up,Right,Down,Left; 8-bit indexed, 256 entries, index 0 transparent; 72x128 single / 288x256 x8); 32 -> VX/VX Ace 32x32; 48 -> MV/MZ 48x48 (rows Down,Left,Right,Up; `$` single 3x4, else 12x8 cells; `!` objects no offset); center column = standing; key-color background option | "관행에 맞게 처리해" |
| R16 | Character flow: front master idle -> user approval -> 4 directions -> walk frames -> deterministic sheet; small-res face repair | character direction turn |
| R17 | Animation (full): per-action multi-row grids (2x2/2x3/..., never raw 1xN for bodies), FX split from body, shared scale profile + feet anchor, QC gates (scale CV <= 0.08, anchor std <= 0.05 for grounded actions), GIF preview | "한번에 다 만들거야" |
| R18 | Palette: pack <= 32 colors, asset <= 16 colors (DB32/Endesga-32 convention); extract from existing project assets if given, else from the first accepted asset; presets available | "색 수 같은거 ... 관행적으로" |
| R19 | Output under `p2d-out/<pack>/` in the working project, path overridable | recommendation accepted |
| R20 | Python + Pillow (+ numpy) scripts, dependency check on first run; Python 3.9 compatible (host python3 is 3.9.6) | recommendation accepted |
| R21 | Skill name `p2d`; source in this repo; linked into OMO's global skill path (symlink) so OMO discovers it; repo is also an OMO package (`package.json` `pi.skills`) | recommendation accepted |
| R22 | Licensing: reuse ideas from MIT skills; Picxel (GPL-3.0) and Raing5Days (no license) concepts only, no copied code | analysis turn |
| R23 | Excluded: Grok, PixelLab, autotiles/engine tileset formats, milestones | user decisions |

## Affected users and ideal state

Users: (a) the human game developer asking OMO for assets in Korean; (b) the OMO agent that loads p2d and must follow it with minimal context; (c) the game engine / RPG Maker that consumes the files.

| IS | Property of the delivered skill | Reason |
|---|---|---|
| IS1 | OMO discovers `p2d` from this repo (package manifest and global skill path) with zero loader diagnostics | R10, R21 |
| IS2 | Only frontmatter is always loaded; SKILL.md routes to exactly the references a request needs; references never chain | R12 |
| IS3 | `p2d.py pixelize` turns a generated image into an exact-size, palette-limited, binary-alpha pixel asset whose cells are uniform | R4, R18 |
| IS4 | `p2d.py check` gives machine-readable PASS/FAIL per kind (size, colors, palette membership, alpha, key residue, seams, edge contact) with exit code | R5 |
| IS5 | Tiles/walls/trims can be made seamless by the offset+mask repaint workflow and verified by seam metrics | R2, R5 |
| IS6 | Characters: frames cut from generated grids with one shared scale and feet anchor, QC metrics, RPG Maker sheets in 2000 and VX/MV layouts, walk/action GIFs | R15-R17 |
| IS7 | Pack state (`pack.json`) holds px list, palette, style lock, asset registry; px is asked once when absent | R3, R7, R19 |
| IS8 | A pack preview reproduces the reference-image presentation (grey background, same display size per tile unit, 16/32 pairs side by side) and tile repeat previews | R8, reference image |
| IS9 | End to end, an agent following only the skill produces a usable dungeon pack at 16+32 and an RPG Maker character with walk and an action | R1, R2 |

GAPs: everything is missing today (empty folder, no git). GAP-n = IS-n absent.

## Design

### Repository

```
p2d/                            # repo root = OMO package
├── package.json                # {"name":"p2d","pi":{"skills":["skills/p2d"]}}
├── README.md                   # Korean: install (packages / symlink), examples
├── .gitignore                  # __pycache__, p2d-out/, .omo/ runtime
├── scripts/verify.mjs          # senpi DefaultResourceLoader + progressive-disclosure audit
├── tests/                      # python unittest (stdlib), synthetic images
└── skills/p2d/
    ├── SKILL.md
    ├── references/{pack,tile,wall,trim,prop,character,animation,qc}.md
    ├── palettes/{db32,endesga-32,pico-8}.hex
    └── scripts/
        ├── p2d.py              # thin entry: sys.path + p2d_lib.cli.main()
        └── p2d_lib/{__init__,imageio,color,pixelize,seam,checks,frames,charset,preview,pack,cli}.py
```

### CLI contract (`python3 <skill>/scripts/p2d.py <cmd>`; every command has `--help`; outputs `KEY: value` lines, final `RESULT: PASS|FAIL` for checks, exit 1 on FAIL or error)

| Command | Purpose |
|---|---|
| `doctor` | verify python>=3.9, Pillow, numpy; print install hint |
| `size WxH [--min-edge 1024]` | valid generate_image size for a logical canvas (multiple of 16, aspect 1:3..3:1, 655,360..8,294,400 px), integer pitch preferred; prints `GEN_SIZE`, `PITCH_X`, `PITCH_Y` |
| `inspect IMG` | size, color count, alpha stats, detected fake-pixel pitch, suggested logical size and px class (16/32/48), checkerboard flag, key residue |
| `raw-check IMG --bg key\|alpha\|none` | raw generation checks: alpha present/% transparent, painted checkerboard, key coverage |
| `pack init DIR --name N [--px 16,32] [--palette FILE\|PRESET] [--from IMG...] [--max-colors 32] [--asset-colors 16] [--light top-left] [--notes TXT]` | create `pack.json` |
| `pack show DIR` / `pack set DIR --px ... ` / `pack palette DIR --from IMG... [--max 32]` / `pack add DIR --name --kind --px --file [--status]` | read/update pack |
| `palette extract IMG... --max N --out FILE` | palette hex from images |
| `offset IMG --axis x\|y\|xy --out OUT [--mask OUT] [--band 0.125]` | roll by half (seam repaint); mask transparent band = repaint area |
| `pixelize IMG --kind tile\|wall\|trim\|prop --size WxH --out OUT [--pack DIR] [--palette FILE] [--max-colors N] [--bg key\|alpha\|none] [--key HEX] [--tol N] [--anchor bottom\|center] [--margin N] [--despeckle] [--scale K]` | core conversion |
| `check IMG --kind tile\|wall\|trim\|prop\|frame --size WxH [--pack DIR] [--max-colors N] [--axis x\|y\|xy] [--seam-max 1.6]` | QC with RESULT |
| `frames RAW --rows R --cols C --frame WxH --out DIR [--anchor feet\|center] [--subject-height N] [--write-profile P \| --profile P] [--pack DIR] [--bg key\|alpha] [--loose]` | cut grid, shared-scale pixelize, anchor, `frames.json` QC (scale_cv, anchor_y_std, edge_touch, empty) + RESULT |
| `charset --format rm2k\|vxace\|mv --frames DIR --out FILE [--order down,left,right,up] [--mirror-right] [--slot 0-7] [--key HEX]` | RPG Maker sheet from a 4x3 frames dir (generation order = Down,Left,Right,Up; cols = stepA, stand, stepB) |
| `gif FRAME... --out OUT [--duration 150] [--scale 4] [--sequence 0,1,2,1]` | animation preview |
| `atlas FILE... --out OUT [--cols N] [--json]` | generic sheet + coordinates |
| `preview FILE... --out OUT [--unit 128] [--bg #444444] [--repeat N]` | pack contact sheet / tile repeat preview |

### Pixelize algorithm (IS3)

1. Load RGBA. Background: `key` (distance to key <= tol, plus magenta-dominant hue) -> alpha 0; `alpha` (alpha < 128 -> 0); `none`.
2. Region: tile/wall/trim use the full image (auto-trim a uniform border if present); prop uses the opaque bbox fitted into `size - margin` with aspect kept, anchored bottom (entities) or center (items).
3. Pitch from target size; phase search (offset in [-pitch/2, pitch/2]) minimizing within-cell variance.
4. Cell color = dominant color bucket (5-bit/channel) of the cell's inner 60%; transparent if >50% of the cell is transparent.
5. Palette: nearest pack palette color (redmean distance), then cap to max colors by merging least-used into nearest; without palette, median-cut to the cap (no dithering).
6. Optional despeckle (isolated single pixels). Binary alpha. Optional `@Kx` nearest upscale.

### Seam metric (IS5)

ratio = mean wrap-neighbor distance / mean adjacent distance inside; PASS if ratio <= 1.6 for each requested axis (tile xy, wall y, trim along its length).

### Character metrics (IS6)

Per frame in raw space: subject bbox; `scale_cv` = std/mean of bbox height, `anchor_y_std` = std(bottom)/cell height, edge touch, empty. Grounded default gates 0.08 / 0.05; `--loose` for jumps/attacks with big silhouette change reports without failing on scale. Shared pitch from the profile (written from the accepted idle/master sheet).

### Skill prose (R12)

- `SKILL.md` <= 150 lines: when to use; setup (`doctor`); px rule; pack/output rule; 6-step pipeline; hard rules; routing table (kind/situation -> reference); image-tool rule (follow `gpt-image-gen`, magenta key, size from `p2d.py size`, save raw under `raw/`).
- Each reference self-contained for its kind: plan defaults, sizes per px, prompt template, script invocations, checks, deliverables. `qc.md` = failure diagnosis table, read only on FAIL.

## QA scenarios (user side)

| ID | Surface / invocation | PASS observable |
|---|---|---|
| Q1 | `node scripts/verify.mjs` (senpi DefaultResourceLoader on repo; plus default loader with cwd=/tmp after symlink `~/.agents/skills/p2d`) | prints `PASS` lines: skill `p2d` found at `skills/p2d/SKILL.md`, diagnostics `[]`, found globally |
| Q2 | same script, disclosure audit | SKILL.md <= 150 lines, description <= 1024 chars, every `references/*.md` linked from SKILL.md, no reference links another reference, every script command in docs exists in `p2d.py --help` |
| Q3 | `python3 -m unittest discover -s tests -v` | `OK`, 0 failures/errors |
| Q4 | E2E pack: fresh agent loads only p2d, request "어두운 던전 재질 팩 만들어줘. 16이랑 32로. 조약돌 바닥(어두운 변형 하나 포함), 석벽, 나무 상자, 나무 통, 가로 트림" with output in a temp project | each asset has 16 and 32 PNG of exact size; `check` RESULT PASS for all (wall axis x); pack.json shows per-size raw + reference (distinct raws), variant entry with `variant_of`, all candidates kept; `preview.png` exists; visual verdict (read of preview) = crisp grid, cohesive palette, reads like the reference |
| Q5 | E2E px reuse: same pack, "나무 문도 추가" (no px) | produced at 16 and 32 without asking |
| Q6 | E2E px missing: new pack, "돌 바닥 타일 만들어줘" | child's first turn ends with the px question (16/32/48, multiple allowed) and its transcript has zero `generate_image` calls in that turn; after the lead answers "16" via task_send, generation calls appear, the tile is made at 16 only and pack.json px = [16] |
| Q7 | E2E character: "은발 기사 캐릭터, 16px, 걷기" | child's transcript shows the master-approval request ending a turn with zero direction/walk `generate_image` calls before the lead's approval message; after approval: rm2k `…charset.png` 288x256, mode P, 256-entry palette, index 0 = key, knight in slot 0 with rows Up/Right/Down/Left; frames RESULT PASS; walk GIF exists; visual verdict |
| Q8 | E2E animation: "그 기사 32px 공격 모션" | 2x2 grid frames at 32x32 (VX Ace convention), frames.json RESULT PASS (loose where appropriate), GIF; FX not baked into body |

## Test decision

Behavioral TDD for the Python library (runtime behavior): each command's core behavior gets a failing unittest first with synthetic images (upscaled known pixel grids + noise/offset, magenta backgrounds, periodic vs non-periodic tiles, grid sheets with drifting subjects, charset order/index checks). Prose (SKILL.md, references, README) gets read-through QA plus the machine audit (Q2), never wording tests.

## Tasks and DAG

One task (one worktree `p2d-skill`, one branch, one PR/merge).

| Node | Write scope | Depends |
|---|---|---|
| N1 scaffold | package.json, README stub, .gitignore, scripts/verify.mjs, skills/p2d/scripts/p2d.py, p2d_lib/__init__.py, imageio.py, cli.py (registry), tests/helpers.py | — |
| N2 core | p2d_lib/color.py, pixelize.py, pack.py (+ `doctor`, `size`, `inspect`, `raw-check`, `palette`, `pack`, `pixelize` wiring), tests/test_core.py | N1 |
| N3 seams+checks | p2d_lib/seam.py, checks.py (`offset`, `check`), tests/test_checks.py | N2 |
| N4 characters | p2d_lib/frames.py, charset.py (`frames`, `charset`, `gif`), tests/test_characters.py | N2 |
| N5 presentation | p2d_lib/preview.py (`preview`, `atlas`), p2d_lib/edit.py (`touch`), palettes/*.hex, tests/test_preview.py | N2 |
| N6 prose | SKILL.md, references/*.md, README.md | N1 (CLI contract above) |
| N7 integration | cli wiring review, Q1-Q3 | N3-N6 |
| N8 E2E QA | Q4-Q8 in a temp project | N7 |
| N9 closing | per wish verification: combined QA, PR/merge, final review, cleanup, symlink install | N8 |

Parallel: N3, N4, N5, N6 run concurrently (disjoint files); `cli.py` registration lines for N3-N5 are pre-declared in N1 as imports of modules that each node creates (each module exposes `register(subparsers)`).

## Gate round 1 amendments (category-based plan review, deep-high)

1. **RM2000 export (R15/Q7):** `charset --format rm2k` always writes the 288x256 indexed engine sheet (8 slots, 4x2, each 72x128); `--slot 0-7` chooses the slot and merges into an existing 288x256 sheet when `--out` exists. The 72x128 block is an intermediate only. Q7 verifies 288x256, mode P, 256-entry palette, index 0 = key, character in slot 0, rows Up/Right/Down/Left.
2. **Wall axis (R2/R5/Q4):** 3/4 walls repeat horizontally along a wall run: default seam axis `x` for `wall`; `--axis xy` for walls that also stack vertically. Trims repeat along their length (`x` for horizontal, `y` for vertical). The same axis is used for `offset`, `check`, and `preview --repeat`. pack.json records each asset's axis.
3. **Variants (R6):** `pack.md` defines the variant workflow: accepted asset (raw + pixelized) as `reference_image_paths`, prompt = same asset with only the variant change (lighter/darker/damaged/mossy), same px and canvas, pixelize with the pack palette, `pack add --variant-of NAME`. Q4 includes one variant (dark cobblestone).
4. **Per-size redraw evidence (R8/Q4):** `pack add` records `raw` (the generation file) and `reference` (the accepted larger-size asset used as identity reference). Q4 verifies each smaller px entry has its own raw file (distinct hash from the larger size's raw) and a `reference` pointing at the accepted larger asset, and that the generate_image call for it passed that reference.
5. **Interaction gates (R7/R16/Q6/Q7):** SKILL.md: ask with `ask_user_question` (16/32/48 multi-select) when available; otherwise ask in the reply and stop the turn. Q6 and Q7 run in a real child session: the child must end its turn with the px question / master-approval request and no generation for the dependent step; the lead then answers via task_send and verifies generation happens only after the answer (file timestamps / absence before, presence after).
6. **Attempt limit and candidate retention (R5):** `pack add` records every candidate (`status: candidate|accepted|rejected`, `attempt`, `raw`), never deletes files, and refuses a 4th generation attempt for the same asset+px with exit 2 (`attempt limit reached (3)`), instructing to record a manual task. Unit-tested (Q3). SKILL.md and qc.md state the loop; Q4 verifies raw candidates remain on disk.
7. **Face repair (R16):** new `touch IMG --set X,Y=#RRGGBB ... [--pack DIR] --out OUT` command (N5 scope, module `edit.py`) for small logical-pixel repairs restricted to the pack palette; `character.md` defines the trigger (eyes/mouth unreadable in the @8x view of front/side frames at 16/24x32) and the rule to keep identity, palette and frame geometry; re-run `check`/`frames` afterward. Unit-tested.
8. **Q2 detail:** the audit runs `--help` for every command and nested `pack` actions named in the docs.

## Gate round 2 amendments

9. **Pre-generation attempt reservation (R5):** `pack attempt DIR --name --kind --px [--reference] [--variant-of] [--axis] [--prompt]` runs BEFORE every `generate_image` call for that asset+px. It reserves attempt k (1..3), prints `ATTEMPT` and the `OUTPUT` raw path prefix (`raw/<name>@<px>_a<k>`) to pass as `output_path`, and exits 2 with `attempt limit reached (3)` on a 4th reservation. SKILL.md hard rule: no `generate_image` call for an asset without a successful reservation for that call. `pack accept` accepts only raw files that live under a reserved attempt prefix. Proof: unit test of the 4th-reservation refusal and prefix-only acceptance (Q3), plus a trace audit in Q4/Q7/Q8: in the child's full transcript every `generate_image` call is preceded by a successful `pack attempt` for the same asset+px, and no asset+px has more than 3 generation calls.
10. **Interaction-gate proof (Q6/Q7):** the lead reads the child's full tool-call transcript (`task_output` mode full) and requires zero `generate_image` calls in the turn that asked the px question / master-approval request; dependent generation calls appear only after the lead's answer message.

## Out of scope

Grok/PixelLab backends, API-key backends, autotile/Wang/blob tilesets, engine-specific tileset exports (Tiled/Godot/RPG Maker chipsets), generic (non-OMO) host support, milestones.

## Follow-up file

Evidence directory: `/Volumes/storage/workspace/p2d/.omo/evidence/ulw/01a0f058-d795-73a3-8178-bb9c186cbb18/` (ulw-loop evidenceRoot; gitignored). Follow-up file: `/Volumes/storage/workspace/p2d/.omo/evidence/ulw/01a0f058-d795-73a3-8178-bb9c186cbb18/follow-ups.md` — created only if a real out-of-scope finding appears.
