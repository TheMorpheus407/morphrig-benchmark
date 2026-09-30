# MorphRig Operative

An original stylized cyberpunk character authored from mesh data, with an organic left arm, cybernetic right forearm, wrist emitter, forearm blade, removable cell and deployable beacon. Blender is the editable source; Unreal provides the interactive character showcase. All character geometry and required motion were created for this assignment.

Launch the packaged Linux showcase from the supplied task folder:

```bash
bash MorphRig/tools/run_showcase.sh
```

The launcher uses the prepared NixOS FHS wrapper identified by `environment.json`. On a conventional compatible Linux system, the packaged `MorphRig.sh` can be started directly. The packaged client runs without the Unreal Editor. Application paths for rebuilding come from the supplied `../environment.json`; the assignment and closed animation inventory remain in `../SPEC.md` and `../required_animations.csv`.

Scroll the right-hand panel to reach additional controls; Face view brings facial controls to the top. The on-screen panel provides a searchable browser for all 96 entries, action controls, playback rate, camera selection, face presets, individual morph/eye controls, team accents, material inspection and LOD selection. Search and select a clip to preview it; Backspace restores normal interaction. Use the panel's Respawn control after death.

| Control | Behavior |
|---|---|
| W/A/S/D | Travel independently of facing |
| Shift / Ctrl | Run / forward sprint |
| Q / E | Turn facing |
| Right mouse drag | Aim adjustment |
| Space / Z / J | Jump / forward dash / blink |
| 1 / 2 / 3 | Three distinct melee attacks |
| F / R / C | Wrist fire / reload / directional cast |
| G / H / U | Channel / charge / Uplink |
| Enter / X | Finish or release / interrupt or cancel |
| B / K / Delete | Deploy beacon / stun / front death |
| V | Cycle close, front, side, top-down and face views |
| T / L / O | Team accent / LOD / skeleton overlay |
| N / I / P | One or ten instances / wounded stance / pause |
| F9 | Deterministic combined-state demonstration |
| Backspace / Tab / Escape | Reset / panel visibility / quit |

Additional casts, directional hits, disables, recoveries, back death and every remaining required entry are available in the panel. Team identity uses a shape cue as well as color. The demonstration prints state changes and event crossings to its evidence logs.

| Deliverable | Location |
|---|---|
| Editable production character and action library | `source/Operative.blend` |
| Geometry/rig master, generators and rig helpers | `source/Character_Master.blend`, `source/generators/` |
| Original textures | `source/textures/`, `export/textures/` |
| Speech, original transcript and phoneme alignment | `source/audio/dialogue.wav`, `dialogue.txt`, `dialogue_alignment.json` |
| Exported mesh and reduced LODs | `export/Operative.fbx`, `Operative_LOD1.fbx`, `Operative_LOD2.fbx` |
| Named baked animation FBXs | `export/animations/` |
| Unreal source, imported content and configuration | `unreal/MorphRig.uproject`, `unreal/Content/`, `unreal/Source/`, `unreal/Config/` |
| Standalone Linux package | `build/Linux/` |
| Rig controls and editing instructions | `docs/rig_usage.md`, `docs/animation_authoring.md` |
| Bone hierarchy, axes and attachment anchors | `docs/skeleton_and_sockets.json` |
| Every required ID, timing, layer, event and asset path | `docs/animation_manifest.json` |
| Runtime state and interruption rules | `docs/animation_state_contract.md` |
| Actual geometry/material/texture accounting | `docs/material_and_lod_report.json` |
| Supporting-asset provenance | `docs/THIRD_PARTY_ASSETS.csv` |
| Rebuild and real import workflow | `docs/build_and_import_instructions.md` |
| Remaining limitations and acceptance evidence | `docs/known_issues.md`, `docs/validation/` |
| Neutral turntable, motion overview and spoken performance | `presentation/turntable.mp4`, `motion_showcase.mp4`, `face_performance.mp4` |

The standing source is 1.80 m tall, grounded at Z=0, with identity object transforms, meters, +Z up and −Y forward. Export performs an explicit centimeter conversion; Unreal uses +X forward. Imported names replace periods with underscores, as documented in the skeleton/import reports. The skeleton has 64 deformation bones and one root independent of the pelvis. The eight shared character materials cover its equipped props. The source contains 33 morph keys, including a reserved zero-deformation cybernetic wrist key. Unreal imports all 32 intentionally nonempty targets, with four additional independent eye controls. The imported inventory is recorded in `docs/unreal_import_validation.json`.

All source actions use 30 FPS. `EDIT__<id>` preserves editable motion and `<id>` is the baked action. `FACE__<id>` contains facial curves. Seven `TEST__` poses exercise demanding deformations. The rig guide covers live IK/FK matching, finger controls, foot pivots, reset and corrective shapes. After editing, use the explicit rebake tool before export:

```bash
blender -b MorphRig/source/Operative.blend --python-exit-code 1 \
  -P MorphRig/tools/rebake_action.py -- --clip reload
blender -b MorphRig/source/Operative.blend --python-exit-code 1 \
  -P MorphRig/tools/export_and_bake.py
```

The dialogue is a 13.93-second original English performance synthesized locally with eSpeak NG. Its phoneme timings come from the same synthesis callbacks as the PCM audio. The facial animation uses distinct closure, labiodental, vowel and tongue shapes, gaze changes, asymmetry and a shift from concern to confidence. Voice generation is reproducible through `tools/create_dialogue.py`; the output voice is deliberately synthetic.

Validation scripts inspect actual Blender data and evaluated motion, actual Unreal assets, packaged runtime behavior, event traces and warmed frame-time samples. The video source is identified in its presentation timeline file. Presentation renders use the delivered real-time mesh and materials. Source files, baked assets and the executable remain the primary deliverables.

The final warmed packaged client measured **628 FPS with one actor** and **579 FPS with ten** at 1920×1080 on the supplied RTX 5090 / Ryzen 9950X host. The ten-actor camera is wider and selects LOD1, while the single close view uses LOD0. All recorded warmed frames stayed below 16.67 ms. See the [performance report](docs/performance_report.md) for settings, percentiles and raw logs, and the [validation index](docs/validation/README.md) for the scope of each check.
