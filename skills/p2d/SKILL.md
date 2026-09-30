---
name: p2d
description: Makes 2D pixel-art game assets from a colloquial prompt and/or reference image, using OMO's GPT image tool plus deterministic pixelize and QC scripts - seamless floor tiles, 3/4 walls, trims, props (crates, barrels, pillars, items), RPG Maker-style characters and charsets (2000, VX Ace, MV/MZ), animations, variants, and matched 16/32/48 px packs. Use when the user asks for pixel art, 도트, sprites, tiles, tilesets, props, characters, charsets, animations, or game assets.
---

# p2d

The image model draws; the scripts turn drawings into exact pixel grids and prove them. Run every command as `python3 <this skill dir>/scripts/p2d.py <command>`; `--help` on any command lists its options. Once per session run `doctor`.

## Hard rules

1. Sprite art comes only from the image tool. Scripts never draw art; they cut, pixelize, check, and assemble.
2. Never shrink or grow art with smooth filters or plain nearest-neighbour. Every generated image goes through `pixelize` (or `frames`).
3. Reserve before you generate: `pack attempt` must succeed for EVERY image-tool call for that asset and px. Exit 2 means three attempts are used: stop generating that asset and read `references/qc.md`.
4. Never delete candidates. Raws stay in `raw/`; rejected work stays on disk.
5. One pack, one style: every asset in a pack uses the pack palette, light direction, outline rule, and view in pack.json.
6. Show the user every result through the `@8x` preview (read the PNG), next to its references.

## 1. Pack and px - before any generation

- A pack is one style set in the user's project: `p2d-out/<pack>/` unless the user names a folder. `pack show DIR` if it exists, otherwise `pack init DIR --name <pack>`.
- `px` is the tile unit: 16, 32 or 48. Take it from the request (one or several values); otherwise from pack.json; otherwise ASK and wait. Ask with `ask_user_question`, multiSelect, options 16 / 32 / 48 (recommend the one `inspect` suggests when the user gave pixel-art references). If that tool is unavailable, ask in your reply and end the turn. No generation happens before px is known; an unanswered or dismissed question is NOT an answer - never pick a default px yourself, stay stopped until the user names one. Store the answer: `pack set DIR --px 16,32`.
- Palette: pack <= 32 colors, each asset <= 16. Source, in order: the user's existing assets (`pack palette DIR --from <files>`), a preset they name (`--preset db32|endesga-32|pico-8`), otherwise the first accepted asset of the pack (`pack palette DIR --from <accepted png>`; re-run `pixelize` for that asset afterwards).
- Style lock defaults: RPG Maker-style 3/4 view, light from the top-left, dark selective outline. Change them only on request: `pack set DIR --light ... --notes ...`.

## 2. Plan

Split the request into assets: name (slug), kind, px list, variants, references. Read ONLY the references that match:

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
2. `size WxH` for the logical canvas the reference file names; use its `GEN_SIZE`.
3. If the image tool errors (e.g. 404, no provider), stop and tell the user it needs an image-capable OpenAI credential; never substitute code-drawn art. Otherwise call the image tool as the `gpt-image-gen` skill directs (`generate_image`, or the native `image_generation` tool when present) with that size, `output_path` = `OUTPUT`, `n` up to 4. Props, characters and effects go on a flat `#FF00FF` background. References go in `reference_image_paths` with their role stated in the prompt.
4. Several px values: generate the LARGEST first. After it is accepted, each smaller px is its own redraw with the accepted larger raw as reference and `--reference` on the reservation.

Every prompt = the kind template from its reference + this pack line: `Pixel art for a 2D RPG Maker-style game, <view>, light from the <light>, <outline>, limited palette of about <asset_colors> colors<, palette hexes if the pack has them>, crisp square pixels, no anti-aliasing, no text, no watermark.`

## 4. Pixelize, check, accept

1. `raw-check RAW --bg key` for key backgrounds (`--bg none` for opaque surfaces).
2. `pixelize RAW --kind K --size WxH --pack DIR --out DIR/assets/<name>/<name>@<px>.png --scale 8` (the kind reference gives extra flags).
3. `check FILE --kind K --size WxH --pack DIR` must print `RESULT: PASS`.
4. Read the `@8x` PNG beside the references and earlier accepted assets: silhouette, readability at 1x, style match.
5. `pack accept DIR --name N --px P --raw RAW --file FILE`.

A FAIL at any step: read `references/qc.md`.

## 5. Deliver

`preview DIR/assets/*/*.png --out DIR/previews/pack.png` (reference-style sheet: 16/32 versions side by side), read it, show it, and list the delivered files with their sizes.
