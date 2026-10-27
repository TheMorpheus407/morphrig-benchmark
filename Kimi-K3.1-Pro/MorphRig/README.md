# MorphRig — Operative

An original adult cyberpunk Operative with an uncovered human-like face, fitted underlayers, limited rigid armor, an organic left arm, a cybernetic right forearm, an integrated emitter and blade, a removable power cell, and a deployable beacon. The character, costume, props, UVs, skinning, facial shapes, and required animation were authored procedurally for this assignment; no stock body/head, finished character, mannequin, motion-capture clip, or downloaded animation set is used.

The delivery contains editable Blender sources, named FBX exports, a native Unreal Engine character showcase, a standalone Linux client, and rendered presentations. The demonstration is intentionally a small character room, not a game economy, networked game, enemy simulation, or city scene.

## Run the showcase

The Linux x86-64 Development client is packaged under `build/Linux/` and runs without the Unreal Editor. On the supplied NixOS host, use the prepared `ue-exec` wrapper to launch the generated `MorphRig.sh`. On a compatible Linux installation with the required runtime libraries, the launch script can be run directly.

```sh
cd build/Linux
/home/morpheus/UnrealEngine/bin/ue-exec ./MorphRig.sh -windowed -ResX=1920 -ResY=1080
```

Use `F1` to toggle the control panel. The panel contains a searchable browser for **all 96 required IDs**, current clip/time/rate/event data, and buttons/sliders for the remaining states. No source-code edit is needed to inspect a required state.

### Keyboard and mouse

| Input | Function |
|---|---|
| W / A / S / D | Move relative to current character facing; camera orbit does not rotate movement or aim |
| Mouse | Inspection-camera yaw/pitch |
| Left Shift | Forward sprint |
| Space | Jump |
| F | Forward root-motion dash; other dash directions are in the browser |
| B | Blink anticipation, event teleport, and destination plant |
| Left mouse | Wrist-emitter single shot |
| R | Three-shot burst with three distinct muzzle events |
| M | Forearm-blade melee |
| Q / E | Turn left/right with authored foot placement |
| C | Start/sustain channel; release C to finish |
| X | Interrupt the active channel midway |
| V | Start/hold charge; release V to release |
| Z | Cancel stored charge |
| Tab | Cycle third-person, front, side, top-down and facial inspection |
| Y | Play the spoken dialogue performance |
| T | Switch cyan/I and amber/II teams |
| K | Respawn from death |
| Backspace | Reset the character and showcase |
| F1 | Toggle controls and input focus |

The on-screen panel adds locomotion speed/direction, calibrated aim, playback 0.5x–1.5x, reload, casts, deployment, Uplink, hits, stun/sleep, knockup/knockdown/getup, death, root/silence/disarm/stasis, wounded presentation, LOD0/1/2, one/ten instances, all six expression presets, independent eyes, and every facial/viseme control. It also includes the prop-contact station and the in-app key guide.

A normal user can move and aim simultaneously, fire while moving, interrupt a sustained action, switch teams/LODs, play every clip, inspect the face up close, reset, and play speech. Death, respawn, stun, sleep, knockup, knockdown and getup follow explicit priorities described in `docs/animation_state_contract.md`.

### Deterministic routes

Pass these to the packaged launch script through the supplied wrapper, not to Blender. From `build/Linux/`:

```sh
UE_EXEC=/home/morpheus/UnrealEngine/bin/ue-exec
"$UE_EXEC" ./MorphRig.sh -MorphVerify
"$UE_EXEC" ./MorphRig.sh -MorphDemo=states
"$UE_EXEC" ./MorphRig.sh -MorphCapture=turntable
"$UE_EXEC" ./MorphRig.sh -MorphCapture=motion
"$UE_EXEC" ./MorphRig.sh -MorphCapture=face
"$UE_EXEC" ./MorphRig.sh -MorphBenchmark
```

From the project root, `python3 unreal/MorphRig/Tools/verify_runtime.py` runs the packaged inventory and behavior checks and rejects stale reports or nonzero client exits. `python3 tools/capture_presentations.py` captures and encodes all three presentations.

`-MorphVerify` loads all 96 clips and checks transitions, terrain and layering, all 26 individual facial controls, independent eye rotations, swing-foot lift, team/LOD controls, action completion and prop contacts/release. It also checks every clip's root orientation against the mesh reference and measures the deployed beacon's actual skinned lowest vertex against the floor. `-MorphDemo=states` prints the deterministic `MR_STATE`/`MR_EVENT` trace. Capture modes render the delivered real-time character with live clip/event captions for the three presentations. Benchmark mode records warmed one- and ten-instance frame-time samples at 1920x1080 without frame generation. Actual results, rather than an assumed 60 FPS claim, are in `docs/validation/`.

## Asset facts

- **Height:** 1.80 m / 180 cm; no undocumented import-scale repair.
- **Source:** Blender meters, Z-up, forward -Y, anatomical left +X, ground-origin root. Unreal uses centimeters; imported facing and actor-space yaw are documented.
- **Skeleton:** 70 deformation bones, exactly one independent `root`, connected named hierarchy, fingers with all three phalanges, eyes/jaw/tongue/teeth, and bounded secondary cable.
- **Skinning:** explicit normalized weights, at most three effective influences per exported vertex.
- **Facial controls:** 26 editable shapes plus Basis, independent eyes/blinks/brows/cheeks/lips, six expression presets and seven documented viseme families.
- **Animation:** 96 required entries: 85 motion entries and 11 static poses, all at 30 FPS with editable source and baked deformation actions.
- **Materials:** eight shared character/equipped-prop material slots; cyan/I and amber/II variants use the same mesh and rig, with a text distinction in addition to color.
- **Textures:** 24 authored PNG maps, maximum dimension 2048, supplied in both source and export folders. The `.blend` packs its image dependencies.

Authored triangle counts, including face and equipped props:

| LOD | Triangles | Required maximum |
|---|---:|---:|
| LOD0 | 26,326 | 80,000 |
| LOD1 | 21,482 | 40,000 |
| LOD2 | 19,062 | 20,000 |

These are genuinely reduced meshes, not duplicate copies. Face/morph topology and equipped props are retained while body topology is reduced. `docs/material_and_lod_report.json` includes source and imported counts, material/UV/bone information, and labeled texture-memory estimates. `docs/unreal_import_audit.json` records the actual imported asset rather than only the generator's intention.

## Editable Blender workflow

Open `source/Operative.blend` with the supplied Blender. All required actions, meshes, materials and facial shapes are already present. No paid runtime plug-in or external linked character content is needed.

In the Text Editor, run the embedded `START_HERE_Rig_Controls.py`, then use the **MorphRig** sidebar tab. `Operative_CTRL` contains the editable controls; `Operative_DEF` is the export skeleton. `SOURCE_<id>` is the editable control action, `<id>` is the baked deformation action, and `<id>_FACE` contains the facial curves.

The panel provides pose reset, clip selection, IK/FK matching, pole controls, heel/toe roll, finger curl/spread and individual adjustments, look-at, facial controls, team accents, and **Bake Current Range** for rebaking an edited pose without recreating the asset. See `docs/rig_usage.md` for the complete workflow and viseme mapping.

The 15.2-second original English performance has its WAV, transcript, measured word timing and authored viseme alignment in `source/audio/`. Voice generation is local and documented; there is no voice cloning or paid speech service.

## Delivery map

The task's example has `unreal/MorphRig.uproject`; this delivery nests the project one level further for a clean native project root. The actual mapping is:

| Required deliverable | Actual location |
|---|---|
| Editable Blender asset | `source/Operative.blend` |
| Editable generators | `source/generators/` |
| Source textures | `source/textures/` |
| Voice, transcript and alignment | `source/audio/dialogue.wav`, `dialogue.txt`, `dialogue_alignment.json` |
| Main FBX | `export/Operative.fbx` |
| Additional LOD FBX files | `export/Operative_LOD1.fbx`, `Operative_LOD2.fbx` |
| Independent authored beacon | `export/Beacon.fbx` and `unreal/MorphRig/Content/Operative/ST_Beacon.uasset` |
| 96 named baked FBX takes | `export/animations/<id>.fbx` |
| Export textures | `export/textures/` |
| Unreal project | `unreal/MorphRig/MorphRig.uproject` |
| Native content | `unreal/MorphRig/Content/Operative/` |
| C++ source | `unreal/MorphRig/Source/MorphRig/` |
| Project configuration | `unreal/MorphRig/Config/` |
| Standalone Linux archive | `build/Linux/` |
| Rig guide | `docs/rig_usage.md` |
| Skeleton and sockets | `docs/skeleton_and_sockets.json` |
| Complete one-to-one animation mapping | `docs/animation_manifest.json` |
| State/layer/interruption rules | `docs/animation_state_contract.md` |
| Material, LOD and texture report | `docs/material_and_lod_report.json` |
| Supporting asset/tool manifest | `docs/THIRD_PARTY_ASSETS.csv` |
| Rebuild and import instructions | `docs/build_and_import_instructions.md` |
| Remaining measured limitations | `docs/known_issues.md` |
| Export and Linux build commands | `tools/export_and_bake.py`, `tools/build_linux.sh` |
| Turntable | `presentation/turntable.mp4` |
| Motion/state presentation | `presentation/motion_showcase.mp4` |
| Actual close-up speech | `presentation/face_performance.mp4` |

The editor-only asset importer is `unreal/MorphRig/Tools/import_operative.py`; `tools/run_import.sh` invokes it with the supplied Unreal wrapper. The packaged client does not depend on Python or the editor. `tools/validate_delivery.py` cross-checks the delivery and records missing evidence rather than silently passing it.

## Verification and remaining issues

`docs/validation/` contains source evaluation, analytical motion checks, import logs, native runtime traces and rendered inspection. `rendered_inspection.json` lists the reviewed captures; `delivery_validation.json` records the current cross-deliverable result. Isolated performance status and the remaining measurement command are documented explicitly in `docs/known_issues.md`. Presentation videos come from the delivered character/project, not a replacement model or a separately substituted cinematic character.

See `docs/known_issues.md` for remaining measured limitations and `docs/build_and_import_instructions.md` for the full reproducible source → FBX → Unreal → Linux workflow. No external deployment or publication is performed.
