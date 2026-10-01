# Terra walking body follow-up

Request: user uploaded a new video because walking still looks awkward; diagnose and improve.
Video viewed across its whole 3.75-second duration and deleted together with extracted
frames, as explicitly requested. Evidence notebook:
.omo/evidence/p2d/walk-followup/notepad.md.

## Affected user, ideal state and measured gaps

Only walking-charset users and agents generating their assets are affected.
IS1: front A/B alternate contacting boots; side steps are compact rather than kicks.
IS2: garment landmarks and head bob remain coherent, with a readable collar connection.
IS3: approved four standing donors, identity, scale, blue eyes and exact headlock survive.
IS4: character guidance requires real pose inspection, not just numerical head/face PASS.
IS5: existing CLI contracts and unrelated local changes remain untouched.

G1: v3 front A/B contacts both x10..11 at y31 (travel zero).
G2: side contact-center travel 6/6.5px versus reference 2.5/3px.
G3: back central hem ends y24 in steps versus y25 standing while head moves down1;
relative head-to-hem distance contracts2. Front chest width remains stable; broad torso
inflation is not proven. G4: copied head ends y20, body starts y21; inspect that junction
explicitly. No disconnected neck was established. GIF order1,0,1,2 is already correct.

## Scope and implementation

One worktree ../p2d-wt-walkbody, branch p2d-walk-body-followup, one PR.
Correct the eight A/B body poses through image-model artwork, not script-drawn limbs.
Keep all four standing-frame PNGs byte-identical to v3. Restore their head bands through
existing headlock; do not extend the head band into shoulders or add a new gait CLI.
Generate a bounded terra-walk-v4 asset using v3 artwork/native master as identity references
and explicit native-coordinate compact gait requirements. Maximum three calls for this asset;
keep every candidate and do not relax frames or face gates. An edit can use a processing-only
guide/mask composed from existing pixels; its script must not invent art.
Inspect the model's actual body pixels before acceptance. If a full-sheet candidate is used,
replace its standing donors with the original four only after strict frames PASS and shared
scale confirmation. Then lock heads and verify poses again. Copying donor art is processing.

Update skills/p2d/references/character.md only: compact side stride, actual front boot
alternation, coherent torso/hem bob, collar seam inspection and full GIF visual QA.
No production CLI change is planned: existing processing faithfully preserved malformed
generated poses. Do not add tests that pin prose. If a code defect is observed and becomes
necessary, amend the plan and use behavioral RED/GREEN for that change.

## Scenarios and binary observables

C001 happy/pose: generate through existing `p2d.py gen ... --name terra-walk-v4 --px 16`;
run strict `frames RAW --rows 4 --cols 3 --frame 24x32 --bg <actual> --subject-height 26`.
PASS requires frames PASS without --loose, front A/B lowest-contact centers opposite sides
of standing boot midpoint; left/right paired contact travel <=3 native pixels. Contact
centers are a useful proxy, not a complete gait proof: visually replay all four directions
at native and8x beside v3 and reconstructed reference. Reject implausible alternating poses
even if contact numbers pass. If no candidate passes within three calls, report FAIL.

C002 identity/edge: compare SHA256 of all four copied standing donors to v3;
`headlock DIR --head-rows 14` must give exact eight head bands donor+1 and no clipping.
`face FRAME --auto` for all nine front/side frames: PASS, front explicitly two eyes/pair.
`check FRAME --kind frame --size 24x32 --pack PACK`: all12 PASS within28-color cap.
Measure manually identified central back hem: no upward step while head moves downward;
head-to-hem distance varies <=1px. Inspect y20/21 seam, sleeves and sash at8x;
no disconnected neck/collar, erased shoulders or stray patches. Head bob and hem criterion
must be met by coherent body artwork, not by simply shifting the entire body.

C003 regression/surfaces: `npm test` green, `npm run verify` all checks PASS;
no build script existed in prior run, confirm package.json before claiming build.
`charset --format rm2k --frames DIR ...` and four
`gif rRc0.png rRc1.png rRc2.png --sequence 1,0,1,2 --duration 160 --scale 8`:
decode actual sheet/GIF mappings, require12/12 cell mapping and16/16 GIF-frame matches.
`pack accept ... --name terra-walk-v4` then `pack status`: RESULT OK.
Read-through documentation; no numeric PASS substitutes for visual judgment.

## Topology

Completed read-only deep-low assessment and lead independently reproduced contact metrics.
Lead owns measured acceptance, plan, donor preservation, integration and final visual QA.
After gate, one deep-low image-capable worker owns model generation and character.md update
because gait guidance and generated proof are coupled. Worker may edit only character.md,
QA processing helpers and its new v4 candidate paths; serialize shared pack.json writes.
Use existing CLI; no new artistic drawing code. Lead opens PR and gets one ultrabrain review.

## Evidence, exclusions and cleanup

Evidence root /Volumes/storage/workspace/p2d/.omo/evidence/p2d/walk-followup.
Follow-ups file /Volumes/storage/workspace/p2d/.omo/evidence/p2d/walk-followup/follow-ups.md.
Main uncommitted pack.py --allow-noise and existing raw-anchor, face-auto and empty-palette
contracts remain outside scope; preserve existing edits. New output must pass current gates.
Delete temporary processing artifacts/resources after captures; retain requested asset
candidates and validation evidence. Video and extraction deletion already confirmed.

## Stop

PR ultrabrain APPROVED, merged, real improved asset confirmed on main, temporary resources,
worktree and task branches removed, and Korean result/limits report delivered.

## Reviewed recovery delta

st_01a0f657 approved a processing-only recovery conditionally, not v4 acceptance.
Three calls exhausted; no further call without consent. Attempt1 original raw and
failed cut metadata remain FAIL and unchanged. Its only clipped cell r3c1 is unused.
All eight retained step cuts have no source-edge/clamp; source shared pitch12.576923.
Compose those eight existing PNGs with the four original donors. Uniform transparent
cell padding is permitted to validate actual composition without source-edge contact.
Record source cell bounds/hashes and provenance. No art drawing, pose repair or per-frame
scaling. Run unchanged strict geometry gates on this composition and prove exact RGBA
preservation across reprocessing. For this preservation probe use its actual union
palette so geometry validation does not secretly recolor source pixels; final twelve
frame checks still enforce the unchanged28-color cap. Preserve four donor bytes,
headlock14/bob1 and unchanged body pixels below band. Every original gait/hem/seam/face,
actual charset/GIF and visual criterion remains required. A composite PASS is never
represented as containment proof for the rejected original raw.
