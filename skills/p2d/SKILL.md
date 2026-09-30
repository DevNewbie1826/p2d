---
name: p2d
description: Makes 2D pixel-art game assets from a colloquial prompt and/or reference image, using OMO's GPT image tool plus deterministic pixelize and QC scripts - seamless floor tiles, 3/4 walls, trims, props (crates, barrels, pillars, items), RPG Maker-style characters and charsets (2000, VX Ace, MV/MZ), animations, variants, and matched 16/32/48 px packs. Use when the user asks for pixel art, 도트, sprites, tiles, tilesets, props, characters, charsets, animations, or game assets.
---

# p2d

The image model draws; the scripts turn drawings into exact pixel grids and prove them. Run every command as `python3 <this skill dir>/scripts/p2d.py <command>`; `--help` on any command lists its options. Once per session run `doctor`.

## Hard rules

1. Sprite art comes only from the image tool. Scripts never draw art; they cut, pixelize, check, and assemble.
2. Never shrink or grow art with smooth filters or plain nearest-neighbour. Every generated image goes through `pixelize` (or `frames`).
3. Reserve before you generate: EVERY image-tool call, including a failed call or retry, consumes its own attempt for that asset and px. Run `pack attempt` before the first call; `gen` auto-reserves on retry. The default limit is three calls; at the limit stop and read `references/qc.md`. To go past three you must first ask the user (`ask_user_question`: stop and keep the best candidate / allow N more calls) and pass their words: `--max-calls N --user-consent "<their words>"` on `gen` and `pack attempt`. Seam repair, offsets and masked repaints are calls too; never raise the cap yourself.
4. Never delete candidates. Raws stay in `raw/`; rejected work stays on disk.
5. One pack, one style: every asset in a pack uses the pack palette, light direction, outline rule, and view in pack.json.
6. Show native-size results and their integer nearest-neighbour `@8x` previews next to references. Reject beveled/embossed pixel tiles, per-pixel highlights, halos, blurred boundaries and within-cell gradients. A numeric PASS does not establish visual quality; distinguish viewer interpolation from defects in the actual PNG.
7. When generation is delegated, the image-capable GPT child owns generation, correction and visual QC. Return only processed deliverables and their paths to the main chat; keep raw candidates and guides in the child's workspace. If the user requests subagent-only generation, do not silently fall back to parent generation. Verify direct native access before promising parallel image work. Use disjoint asset outputs and serialize writes to each shared pack.json.

## 1. Pack and px - before any generation

- A pack is one style set in the user's project: `p2d-out/<pack>/` unless the user names a folder. `pack show DIR` if it exists, otherwise `pack init DIR --name <pack>`.
- `px` is the tile unit: 16, 32 or 48. Take it from the request (one or several values); otherwise from pack.json; otherwise ASK and wait. Ask with `ask_user_question` using `multiSelect: true` (the user may pick several sizes) and options 16 / 32 / 48 (recommend the one `inspect` suggests when the user gave pixel-art references). If that tool is unavailable, ask in your reply and end the turn. No generation happens before px is known; an unanswered or dismissed question is NOT an answer - never pick a default px yourself, stay stopped until the user names one. Store the answer: `pack set DIR --px 16,32`.
- Palette: pack <= 32 colors; character frames may use up to 28, other assets <= 16. RM2000 originals measured 19-28 front idle and 14-31 across 96 frames. Before processing characters, use `pack set DIR --asset-colors 28` (the CLI default is 16); restore `--asset-colors 16` for other assets. Exceed 28 only for a richer style the user asks for, with `pack set DIR --asset-colors N`. Source, in order: the user's existing assets (`pack palette DIR --from <files>`), a preset they name (`--preset db32|endesga-32|pico-8`), otherwise the first accepted asset of the pack (`pack palette DIR --from <accepted png>`; re-run `pixelize` for that asset afterwards).
- Style lock defaults: RPG Maker-style 3/4 view, light from the top-left, dark selective outline. Change them only on request: `pack set DIR --light ... --notes ...`.
- View (구도/시점): when the user describes it in their own words ("정면에서 살짝 위", "탑다운", "옆모습"), turn it into ONE precise English phrase (e.g. `front-facing JRPG 3/4 view: front face and a narrow top face visible, camera slightly above, no isometric diamond, no bird-eye view`), store it with `pack set DIR --view "<phrase>"`, and paste it unchanged as `<view>` into every prompt of the pack. Review every result against it; a result drawn from another angle is a FAIL. Without a user view: props and walls use front-facing 3/4, characters JRPG overworld 3/4, floor tiles the flat map-floor surface of that same view.

## 2. Plan

Split the request into assets: name (slug), kind, px list, variants, references. A user drawing, sketch or photo is the design authority: save it into the pack (`refs/`), open it, list its features in words (hair shape and direction, glasses shape, brows, nose, mouth, face outline, pose, proportions), pass it to every generation with `--ref` as image 1 (`image 1 is the user's design: keep every listed feature, shape and placement; only restyle it as pixel art`), and reject any result that drops, adds or reshapes a listed feature. If a user says an image is attached but you cannot see it, say so and ask for a file path before generating. Read ONLY the references that match:

| The request involves | Read |
|---|---|
| floor, ground, road, water surface, any repeating texture tile | [references/tile.md](references/tile.md) |
| wall face, cliff face, fence or hedge run, anything repeating sideways | [references/wall.md](references/wall.md) |
| border strip, trim, edging, ledge line, frieze | [references/trim.md](references/trim.md) |
| crate, barrel, pillar, furniture, item, icon, door, any single object | [references/prop.md](references/prop.md) |
| person, monster, NPC, walking sprite, RPG Maker charset | [references/character.md](references/character.md) |
| attack, cast, hurt, jump, idle loop, spell or hit effect | [references/animation.md](references/animation.md) |
| several assets, variants, more than one px, palette or style questions | [references/pack.md](references/pack.md) |
| any `raw-check`, `check`, or `frames` result is FAIL | [references/qc.md](references/qc.md) |

## 3. Generate

1. `pack attempt DIR --name N --kind K --px P --prompt "<prompt>" [--reference FILE] [--variant-of BASE]` prints `OUTPUT`.
2. `size WxH` for the logical canvas the reference file names; use its aspect ratio and a generation size supported by the selected surface. Actual generated dimensions may differ; inspect them before processing.
3. Generate with `p2d.py gen DIR --name N --px P --prompt-file PROMPT.txt --size auto --quality high [--ref FILE ...] [--mask MASK.png]` (the bundled ChatGPT-subscription runtime, no API key or other skill). It consumes the newest unused reservation, takes 1-3 minutes and writes `<prefix>.gen.json` (MARKER) on success or `<prefix>.failed.json` on failure. Launch it in the background with a completion monitor and wait for it in the same turn; never end your turn while it runs. On FAIL rerun the command: each retry gets a new attempt and output prefix, keeping failed candidates and markers. After three calls for this asset/px it exits 2: report the outage; `--max-calls N` above three requires explicit user consent. `--mask` repaints only the mask's transparent area of the first `--ref`. An expired login is reported, not refreshed: ask the user to log in again.
   If the runtime cannot authenticate, read `gpt-image-gen` and call exposed native `image_gen.imagegen` DIRECTLY, OUTSIDE eval. Never call `tool.image_generation(...)` in eval: native server tools are not local eval functions. Absence from `tool_search` or `tool_schema` does not prove native unavailability. `generate_image` is a separate API gateway, not a subscription fallback.
   Display local references before native edits. Native tools may save under `generated-images/`: verify the returned file exists, open it, preserve the original, then copy it to reserved `OUTPUT`. Do not assume native tools accept API-only size/output/reference parameters. Props, characters and effects use flat `#FF00FF`. If the actual native tool is unavailable or fails, report the precise limitation without guessed function calls, silent provider changes or code-drawn substitutes.
4. Several px values: generate the LARGEST first. After it is accepted, each smaller px is its own redraw with the accepted larger raw as reference and `--reference` on the reservation.

Every prompt = the kind template from its reference + this pack line: `Flat raster pixel art for a 2D RPG Maker-style game, <view>, light from the <light> on the depicted subject only, <outline>, limited palette of about <asset_colors> colors<, palette hexes if the pack has them>. Pixels are flat single-color samples, not physical blocks: no bevel, embossing, raised tiles, per-pixel lighting, glossy rims, halos, within-pixel gradients, antialiasing or blur. Hard grid-aligned color changes, no text, no watermark.`

## 4. Pixelize, check, accept

1. Inspect the actual file, not only the requested background. For props/characters/effects, run `inspect RAW`: genuine alpha transparency uses `raw-check RAW --bg alpha` and `--bg alpha` consistently in `pixelize`/`frames`; an opaque flat key background uses `--bg key`. Do not regenerate a valid transparent PNG merely because magenta was requested. Painted checkerboards are not transparency. Opaque tile/wall/trim surfaces use `--bg none`.
2. `pixelize RAW --kind K --size WxH --pack DIR --out DIR/assets/<name>/<name>@<px>.png --scale 8` (the kind reference gives extra flags).
3. `check FILE --kind K --size WxH --pack DIR` must print `RESULT: PASS`; tiles, walls and trims FAIL on scattered speckle (`NOISE`); props and frames print `NOISE_REVIEW: yes` for you to inspect (qc.md).
4. Read the native PNG and `@8x` PNG beside the references and accepted assets: silhouette, readability at 1x, style match, flat color cells and hard edges. Do not judge a smoothly zoomed screenshot as the source PNG. If bevel-like shading remains across logical pixels, regenerate or repair the affected color clusters; palette quantization alone cannot remove that design.
5. `pack accept DIR --name N --px P --raw RAW --file FILE` reruns `check` and refuses a FAIL (pack.json unchanged). Characters and animation frames also need a passing face gate (it runs `face --auto` itself, or pass `--face-report`; `--no-face "reason"` only for back views or visored helmets). Replacing an accepted entry needs `--replace` (the old one stays in history). Accept only what also passed your visual review. Before you report, run `pack status DIR`.

A FAIL at any step: read `references/qc.md`.

## 5. Deliver

`pack status DIR` must end RESULT: OK; then `preview DIR/assets/*/*.png --out DIR/previews/pack.png` (reference-style sheet: 16/32 versions side by side), read it, show it, and list the delivered files with their sizes.
