# Terra v5: preserve material identity across walking poses

## Original purpose and diagnosis

User requests another improvement and v5 after pointing out back-view hand colors.
V4 gait/structural checks passed, but source-generated forearm/bracer appearances
changed, and whole-palette nearest RGB did not enforce skin versus equipment roles.
This request closes that actual visible defect, not a general image-editor feature.
Evidence notebook: .omo/evidence/p2d/terra-v5-materials/notepad.md.
Prior diagnostic memory: notes/facts/terra-v4-material-consistency.md.

## Affected users, ideal state and gaps

Users are this character's owner and agents generating matched walking charsets.
IS1: all12 poses depict the same green-haired, blue-eyed Terra with warm light skin,
red sleeveless outfit/sash, pale ivory forearm bracers and brown boots.
IS2: skin and bracers stay recognizable through motion/occlusion; hand shadows do not
become leather, clothing or different-colored equipment.
IS3: retain standing geometry and8 exact donor heads+1px bob, native scale,
compact alternating walk, coherent central hem and connected head/body seam.
IS4: actual RM2K sheet and complete native/8x loops deliver that consistency.
IS5: future guidance separates material/character identity from changing pose and
does not claim palette, contact, head or face PASS proves complete visual quality.

G1: v4 step bracer/hand colors and visible equipment presence differ from standing.
G2: palette mapping treats all colors as interchangeable without region identity.
G3: previous visual acceptance focused on named gait metrics and missed whole-character
continuity. G4: guidance lacks a canonical material reference and per-pose review.

## Scope and implementation

One task/worktree ../p2d-wt-terra-v5, branch p2d-terra-v5-materials, one PR.
Canonical inputs are master-a2 and4 standing frames in
p2d-out/ff6-terra/work/terra/walk-v3-a1-color25@16.
Baseline motion is v4 work/terra/walk-v4/composition-a1-palette/frames.
Fix material inventory from those real images, not an invented redesigned master.
Generate only terra-walk-v5, kind character,px16; default3calls including failures.
Use a localized image-model correction of arms/skin/bracers wherever their identity
is inconsistent. Existing-pixel guide/mask composition is allowed; scripts do not
draw new cuffs, limbs, equipment, or silhouettes. No additional asset to evade budget.
Prefer masking the intended correction area and preserving existing good poses;
inspect actual model output because a mask/prompt is not an exact-preservation guarantee.

Process with unchanged frames/pixelize gates and one shared native scale. Preserve
original donor files byte-for-byte when their materials agree with the master;
material-only model corrections to standing poses are allowed where needed, with
unchanged geometry/head/legs and a recorded native edit-region diff. The approved
front master is the material authority, not an imperfect generated standing pose.
Keep headlock14/bob1 with original head artwork. Explicitly document any
existing-pixel composition or palette processing. Never route an unclassified pixel
to a material merely because its RGB is closest to a color in the whole palette.
When material regions can be established from anatomy/reference, use only that
material's reference ramp; otherwise return to model correction or reject the candidate.
Do not introduce a general semantic-segmentation CLI solely to accept this asset.

Geometry outside the localized edit must stay unchanged where copied from v4;
where a model requires recutting a whole image, independently prove retained source
integrity and validate the actual delivered composition, not a discarded raw.
Existing reviewed v4 composition safeguards apply: preserve original failures,
retain source cut bounds/no edge/clamp, no per-frame scaling/drawn repair, explicit
uniform validation padding, unchanged strict gates and native pixel-preservation proof.

Bounded lead recovery reuses intact model-drawn cuff bands: a3 back A1x1,
a2 left B2x1, canonical master1x2. All18 anatomical translations, source bounds
and the established ivory-only ramp are recorded. No cuff/limb shape is drawn.
All alpha/head/cloth/boot and outside-cuff RGB stay exact. Independent complete
pose/loop review must accept the actual placement and skin/cuff separation.

Tracked edits: skills/p2d/references/character.md and this plan only, unless a measured
production-code defect proves necessary and the plan is amended. Runtime code changes
require behavioral RED/GREEN; docs/prompts require read-through and real visual proof,
never prose-pinning tests. Local accepted assets/evidence are ignored deliverables,
not falsely described as PNGs shipped by the PR checkout.

## Success criteria and exact QA surfaces

C001 material happy:
`p2d.py gen PACK --name terra-walk-v5 --px16 --prompt-file PROMPT --ref GUIDE MASTER
[--mask MASK] --size auto --quality high`, reserved first; <=3calls.
Inspect original/master, standing reference and all12 final native/8x frames.
Record a per-frame inventory for skin, both visible bracers/hands, red cloth/sash,
brown boots, hair/eyes with actual material-region evidence and annotated crops.
PASS only if every visible region has the same material identity/reference hue,
equipment remains present at its anatomical location (or justified occluded), and
four complete160ms loops do not show palette/equipment popping. No fresh hand-color
rule substitutes for this general character-identity review. Reject unexplained
skin/bracer/leather swaps even if color values fit the allowed palette.

C002 identity/edge:
`headlock FRAMES --head-rows14 --head-bob1` and independent RGBA compares:
Original standing files remain unchanged on disk; v5 standing frames either retain
their original hashes or have model-origin material-only differences confined to
annotated arm/bracer/hand regions, with exact original pixels outside those regions.
All original standing alpha/pose geometry and all original head artwork stay exact.
Heads8/8 original donor+1; no clipping or erased shoulders.
`face FRAME --auto` for9front/side frames: PASS with front EYES2/EYE_PAIR PASS.
`check FRAME --kind frame --size24x32 --pack PACK` for12frames: PASS<=28colors.
Strict final `frames COMPOSITION --rows4 --cols3 --frame24x32 --bg ACTUAL
--subject-height25 --max-colors28 --out VALIDATION` must PASS without --loose.
If using existing native composition, uniform processing/alignment is documented
and every reprocessed source pixel is proven equal. Original raw failures stay FAIL.
Final headlocked standing is26rows and eight steps are25rows after1px bob.
Measured typical height25 preserves the actual common8px source grid. Using26
selected pitch7.6923 and stretched standing to27rows; that failed equality trial
remains diagnostic. This is calibration to original pixels, not a gate waiver.
Preserve compact gait: front contacts opposite standing midpoint; side travel<=3px;
central back hem/head distance varies<=1px; seam joins continuous, anatomy plausible.
Contact numbers and seam alpha overlap alone never prove a natural/identical character.

C003 delivered-surface/regression:
`charset --format rm2k --frames FRAMES --pack PACK --slot0 --out SHEET` produces288x256
indexed sheet; decode actual mapping12/12. Four `gif rRc0 rRc1 rRc2 --sequence1,0,1,2
--duration160 --scale1|8 --bg '#404040' --out GIF`; decode16/16 per scale and inspect
every direction's complete loop beside v4/material reference. `pack accept ...`
and `pack status`: accepted v5 and RESULT OK. No procedural placeholder art.
`npm test`, `npm run verify`, changed-file diagnostics; build only if package has
a build script (previously none). Final reviewer checks material quality itself,
not only proof arrays. On main, confirm approved artifact hash and real gate/exports;
reuse unchanged evidence honestly. Show native sheet,12-frame8x preview and GIF paths.

## DAG and routing

Lead owns material-reference interpretation, final visual judgment and integration.
One deep-low image-capable producer owns v5 generation/local processing and evidence;
it is a coupled multimodal correction, not independent color and pose lanes.
Writing node follows producer proof to update character.md only with the mechanism
actually used and required identity review. This avoids prescribing an unproven tool.
Quick regression node follows docs/art and runs the mechanical checks.
Lead verifies every produced artifact, opens PR, runs one ultrabrain product review,
then merges and verifies main. Checkpoint schema audit only if the loop requires it.

## Exclusions, evidence and stop

Evidence /Volumes/storage/workspace/p2d/.omo/evidence/p2d/terra-v5-materials.
Follow-ups /Volumes/storage/workspace/p2d/.omo/evidence/p2d/terra-v5-materials/follow-ups.md.
Preserve main's unrelated pack.py --allow-noise edit and previous F1-F5 contracts.
No new upload/video exists; keep earlier deletion receipt and do not resurrect files.
Clean runtime temporary resources, not accepted artifacts or retained raw candidates.
Stop after v5 identity/gait are proven, PR ultrabrain APPROVED and merged, main proof,
worktree/branch/resource cleanup, and v5 delivery plus Korean results/limits report.
