# Build and import instructions

The required installed versions and paths are in `environment.json`.
`tools/build_linux.sh` reads that file and runs the supplied Unreal FHS
wrapper. All project outputs, compiler/UAT logs, scratch files, configuration
and local Derived Data Cache are directed inside this delivery folder.
Blender is the authority for mesh, rig, textures, morphs and all 96 motions.

From this folder, after the source export is complete:

```bash
blender -b source/Operative.blend -P tools/export_and_bake.py
./tools/build_linux.sh editor
./tools/build_linux.sh import
./tools/build_linux.sh package
./tools/build_linux.sh run
```

The export command supports the arguments documented in the source tool.
The importer creates `/Game/Operative/SK_Operative`,
`/Game/Operative/Operative_Skeleton`, three authored LODs, eight materials,
authored texture maps, sockets, the detached authored beacon, dialogue WAV,
the `/Game/Showcase/Showcase` map and all named animation sequences. It stages
the manifest and dialogue alignment in `unreal/Content/Data`. Full import
requires all 96 IDs; a missing FBX, failed import or wrong root/scale is an
error. Its measured asset report is `verification/unreal_import_report.json`.
It also extracts LOD0 boot-region reference vertices and their imported skin
weights to `unreal/Content/Data/boot_surface_bindings.json`. Runtime toe
support and the terrain surface diagnostic use this delivered mesh data.

For an early mesh/LOD/material smoke import while motion export is underway,
use `./tools/build_linux.sh import -MorphMeshOnly`. That mode explicitly
records an incomplete import and cannot substitute for final full import.
The project module can also be compiled before importing any character data.
`./tools/build_linux.sh import -MorphReimportClip=reload` selectively replaces
one exact clip and refreshes the material/socket setup while retaining the
other imported animation assets. `-MorphInspectOnly` refreshes the same
material/socket setup and measures existing assets without reimporting motion.
The importer checks each material connection, enables skeletal/morph usage,
and matches authored normal-map strength at 0.55. Source OpenGL tangent
normal textures import with green-channel conversion, sRGB disabled and
normal-map compression.
Multiple selective IDs are accepted as a comma-separated value.

The packaged client is `build/Linux/MorphRig.sh`. Running through
`tools/build_linux.sh run` uses the NixOS FHS/Vulkan setup and requests
1920x1080, screen percentage 100, VSync off and no generated frames. The
runtime source uses portable Engine APIs, so future Windows integration
requires the normal Windows target build rather than a runtime rewrite.
Packaging also copies the retained engine and font notices from
`docs/licenses/unreal/` to `build/Linux/Licenses/unreal/`.

## Controls

| Input | Operation |
|---|---|
| WASD | move relative to facing; A/D strafe and S retreats |
| Shift / Ctrl | run / forward sprint |
| Arrow keys | independent aim yaw and pitch |
| Q / E, Ctrl+Q/E | left/right 90-degree turn or 180-degree pivot |
| Space | jump, airborne pose and actual capsule landing |
| X | dash in current movement direction; default forward |
| V | blink out, one actor teleport event, blink in |
| Left mouse / F | moving wrist shot / three-shot burst |
| 1 / 2 / 3 | three authored forearm-blade melee attacks |
| R | power-cell reload |
| G / J / K | directional / ground / self cast |
| Hold C / Z / U | channel / charge / uplink; key release completes |
| I | interrupt/cancel current sustained state, recover from disable |
| P | authored beacon manipulation and deployment |
| H | hit reaction; movement direction chooses hit side |
| Delete / Shift+Delete | front/back death |
| Enter | respawn |
| Backspace | reset state and return to room origin |
| F1/F2/F3/F4/F5 | third-person/front/side/facial/top-down inspection |
| Mouse wheel | inspection distance |
| B | searchable browser for all 96 clips; click a row to play |
| Type in browser | case-insensitive search; Space inserts underscore |
| PageUp/PageDown, Enter | browser pages / play first visible row |
| Escape | close browser/face panel |
| F4 face panel | select a control, click -/+; next page exposes all controls |
| T / L / M / O | team accents / auto-or-authored LOD / materials / skeleton |
| N | toggle the per-actor triangle/A or diamond/B team icons |
| Y | move the aim target and enable target aiming |
| +/- | action rate 0.5x..1.5x |
| F8/F9/F10/F11 | help / deterministic sequence / one-ten instances / frame log |

All sustained states, disables, directional knockdowns, recoveries, reset,
speech playback and rate controls also have clickable HUD buttons. Facial
presets are neutral, joy/confidence, anger, concern, surprise, pain and focus.
Facial close-up enforces LOD0 while its panel is open, retaining the complete
authored morph controls. LOD1/2 retain the facial skeleton for baked speech;
inspect and switch the lower LODs in the full-body views.
The HUD projects an A/triangle or B/diamond identifier above each actor,
including all ten instances, alongside the two material accents. This
remains readable independently of color; N toggles the projected icons.

## Reproducible runtime verification

```bash
./tools/build_linux.sh run -MorphSequence -MorphAutoExit
./tools/build_linux.sh run -MorphInventorySweep -MorphAutoExit
./tools/build_linux.sh run -MorphTerrainTest -MorphAutoExit
./tools/build_linux.sh run -MorphTerrainTest -MorphRampStop -MorphAutoExit
./tools/build_linux.sh run -MorphPerf -MorphAutoExit
./tools/build_linux.sh run -MorphPerf10 -MorphPerf -MorphAutoExit
./tools/build_linux.sh run -MorphClip=dialogue -MorphView=3 -MorphExitSeconds=18
./tools/build_linux.sh run -MorphTurntable -MorphNoHUD -MorphExitSeconds=15
```

`-MorphSequence` exercises moving aim/fire/casts, hits, root dash, blink,
channel completion/interruption, variable charge release/cancel, reload,
deploy, uplink cancel, stun, sleep, forced launch, both knockdown/recovery
families, death during cast/jump, respawn, speech, slow/fast actions and stasis.
Its trace prints to the client log and `Saved/Verification/state_events.jsonl`.
`-MorphInventorySweep` plays every required imported asset in order, looping
sustained entries for two cycles and holding static poses intentionally.

`-MorphPerf` records five seconds of warmup followed by 30 seconds of frame,
game-thread, render-thread and GPU timings. CSV and JSON include resolution,
instance count, CPU, physical/process RAM, GPU/RHI, mean and p95/p99 values.
Each `-MorphPerf10` run spawns nine further animated Operatives and measures
all ten. Performance target assessment uses these actual results, not an
estimated benchmark. Client files live under its `Saved/Verification` folder;
the final `verification/` report retains the measured sample and host details.
After retaining both runtime CSV/JSON pairs in `verification/`, run
`python3 -B tools/summarize_performance.py`. This verifies measured duration,
frame counts and settings, recomputes every timing statistic, and records
the delivered executable and CSV SHA256 identities in both summaries and
`performance_validation.json`.

`-MorphTerrainTest` walks the actual capsule up the room's 20-degree ramp,
then across its five 20-cm risers. It writes `terrain_contacts.csv` with actor
height/speed, left/right ankle and traced ground heights, actually applied
IK height weights, separate stance/rotation weights, evaluated pelvis
offset and complete foot X/Y/Z. It also skins
the 1,938 imported LOD0 boot-region vertices using the completed bone buffer
and records minimum surface clearance, vertices inside the solid steps and
maximum step penetration separately for each boot. A swing foot raised by
collision can have height weight 1 and stance weight 0; its clearance is
interpreted as swing lift. The same imported directional gait remains the
authoritative foot X/Y trajectory; ground IK adjusts ankle height and slope
rotation. Directional blends account for the virtual reference-speed change
between neighboring 45-degree samples.
The CSV also records active body ID/time, base ID and the actually evaluated
gait phase. These fields distinguish authored support from swing and expose
startup, transition completion and stopping for horizontal contact review.
Interactive start/stop uses the authored torso over the moving gait, with
world contact anchors during transition and stationary recovery.
`-MorphRampStop` stops midway up the ramp before traversing the steps, testing
the transition to a planted idle on the slope. Measurements run from
`OnBoneTransformsFinalized` after the current skeletal bone buffer is
published. This pairs the rendered ankle pose, capsule and ground hit from
the same update, rather than combining the preceding pose with the current
capsule at a step edge. Sole-normal errors are recorded separately; authored
heel/toe rotation remains part of the gait.
The diagnostic forces LOD0 to match its measured vertex bindings. An ankle
can sit above the lower tread while its toe is supported by the next one;
whole-boot clearance supplies the contact check at those boundaries. Both
full traversal and the stopped replay cover footprint contact. Earlier
failed diagnostics remain beside the final records for comparison.

The retained packaged acceptance traces are
`verification/state_sequence.jsonl` and `verification/inventory_events.jsonl`.
Run `python3 tools/validate_runtime.py --help` for the audit commands; the
corresponding `sequence_validation.json` and `inventory_validation.json`
record marker deduplication, combined states, root travel, blink visibility
and airborne stasis checks. Packaged terrain samples and their measured
bounds are in `verification/terrain_contacts.csv`,
`verification/ramp_stop_contacts.csv` and `verification/terrain_validation.json`.
The state audits can be reproduced directly:

```bash
python3 tools/validate_runtime.py verification/state_sequence.jsonl --sequence --output verification/sequence_validation.json
python3 tools/validate_runtime.py verification/inventory_events.jsonl --inventory --output verification/inventory_validation.json
```

The warmed one/ten-character results are explained in
`docs/performance_report.md`, with the per-frame CSV and JSON retained in
`verification/`.

For an automated image, add `-MorphScreenshotAt=4` and optionally
`-MorphScreenshot=/absolute/path/inside/this/folder/image.png`. The default
is `Saved/Verification/showcase.png`. `-MorphClip=<exact_ID>`,
`-MorphView=0..4` and `-MorphRate=.5..1.5` support isolated inspection without
source edits. `-MorphNoHUD` removes the controls from presentation captures.

For recording, `-MorphStartDelay=5` holds the neutral pose for five runtime
seconds before starting `-MorphClip`, `-MorphAction`, `-MorphSequence` or the
turntable orbit. The delay defaults to zero. The `presentation_start` trace
contains `epoch` UTC Unix seconds to millisecond precision; every trace row
also carries this wall-clock timestamp. Dialogue starts in the following
`enter dialogue` row, allowing capture timestamps and the source WAV to align.
`-MorphExitSeconds` and screenshot times remain relative to application play
start, including the delay.

Primary implementation references are the installed Unreal 5.8.3 headers
`AnimInstanceProxy.h`, `AnimSequence.h`, `AnimationPoseData.h`,
`SkeletalMeshEditorSubsystem.h`, `AnimationBlueprintLibrary.h` and
`InputKeyEventArgs.h`. Epic's [skeletal mesh editor subsystem API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SkeletalMeshEditorSubsystem)
documents authored LOD import; Epic's [animation library API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimationLibrary)
documents sequence marker creation and bone-pose inspection.
Epic's [material editing API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MaterialEditingLibrary)
defines graph connection names and material parameter inspection.
