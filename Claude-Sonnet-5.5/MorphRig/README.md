# MorphRig: the Operative

An original adult cyberpunk humanoid, built from scratch by scripts: modelled, textured, rigged, skinned, animated (96 clips), given a facial rig with a spoken performance, and shown in an interactive Unreal Engine 5 showcase with a packaged Linux client. Produced by Claude Sonnet 5.5 for the MorphRig benchmark.

* Blender 5.1.1 source: `source/Operative.blend` (procedural; the generators are in `source/generators/`)
* Unreal Engine 5.8.3 project: `unreal/MorphRig.uproject`, packaged client: `build/Linux/`
* Height 1.80 m (180.05 cm to the top of the skull, 180.8 cm with hair; 180 cm in Unreal, no import scale), LOD0 40,088 triangles, 7 material slots, 44 face morph targets, 111 deformation bones under one root

## Quick start

```bash
tools/ue_run_packaged.sh              # interactive showcase, windowed 1920x1080 (runs inside the Unreal FHS runtime NixOS needs)
build/Linux/MorphRig.sh               # the same client on a regular Linux with Vulkan; F1 shows the controls
```

Press **F1** for the controls, **F2** for the mouse panel (every function is also a button), **F8** for the deterministic showcase sequence (it prints a state and event trace). **P** plays the speech sample in the face view, **M** opens the motion viewer with the searchable browser of all 96 clips.

## Where every deliverable is

| Required entry | Location |
|---|---|
| `README.md` | this file |
| `source/Operative.blend` | `source/Operative.blend` (contains the character, both armatures, 96 clip actions `A_<id>`, 7 skinning test poses `A_pt_*`, the panel script `MorphRig_Tools.py`) |
| `source/textures/` | `source/textures/` (25 PNG, plus `texture_manifest.json`) |
| `source/audio/dialogue.wav`, `.txt`, `_alignment.json` | `source/audio/dialogue.wav`, `dialogue.txt`, `dialogue_alignment.json` (the voice model used to make them is in `source/audio/voice/`) |
| `source/generators/` | `source/generators/` (all Python that builds the asset; `required_animations.csv` is the task's inventory, copied there so the folder builds on its own) |
| `export/Operative.fbx` | `export/Operative.fbx` (LOD0 and skeleton), `Operative_LOD1.fbx`, `Operative_LOD2.fbx`, props in `export/props/` |
| `export/animations/` | `export/animations/<id>.fbx`, one baked take per required clip (96) |
| `export/textures/` | a relative link to `source/textures/`: one set of files, no duplicate on disk; the Unreal import and the Blender materials read the same files (Unreal conventions: BC, DirectX N, ORM, E, TM) |
| `unreal/` | `unreal/MorphRig.uproject`, `unreal/Source/`, `unreal/Config/`, `unreal/Content/` |
| `build/Linux/` | `build/Linux/MorphRig.sh` and the packaged content |
| `docs/rig_usage.md` | `docs/rig_usage.md` |
| `docs/skeleton_and_sockets.json` | `docs/skeleton_and_sockets.json` (111 bones, axes, units, 21 sockets) |
| `docs/animation_manifest.json` | `docs/animation_manifest.json` |
| `docs/animation_state_contract.md` | `docs/animation_state_contract.md` |
| `docs/material_and_lod_report.json` | `docs/material_and_lod_report.json` |
| `docs/THIRD_PARTY_ASSETS.csv` | `docs/THIRD_PARTY_ASSETS.csv` |
| `docs/build_and_import_instructions.md` | `docs/build_and_import_instructions.md` |
| `docs/known_issues.md` | `docs/known_issues.md` |
| `tools/export_and_bake.py`, `tools/build_linux.sh` | `tools/export_and_bake.py`, `tools/build_linux.sh` (more scripts in `tools/`) |
| `presentation/*.mp4` | `presentation/turntable.mp4`, `motion_showcase.mp4`, `face_performance.mp4` |

Extra files: `docs/skinning_pose_tests.png`, `docs/face_expressions.png`, `docs/face_visemes.png` (evidence renders), `docs/export_report.json`, `docs/perf/` (frame-time logs with their own README), `docs/showcase_sequence_trace.txt` (the state and event trace of the deterministic sequence), `docs/unreal_import_report.txt` (what the Unreal import and the package reported), `tools/verify_delivery.py` (the delivery checker) and the Unreal helper scripts `tools/ue_*.sh`.

## The character

A stylised-to-semi-realistic operative in a fitted technical suit with a few hard armour pieces. The **right arm and the face are organic**, the **left forearm is visibly cybernetic** with an integrated wrist emitter (ranged attacks), a retractable forearm blade (melee) and a slot that holds a removable power cell (reload). A small deployable beacon rides in a dock on the right hip. Secondary motion: a braid and a cable on the left forearm. No coat or cape hides the legs. Two team variants share mesh and rig: team A cyan with circle icons, team B magenta with diamond icons, and an optional rim outline, so the teams differ by shape as well as by colour.

| Item | Value |
|---|---|
| Geometry | LOD0 40,088 / LOD1 20,043 / LOD2 8,818 triangles (limits 80k / 40k / 20k) |
| Materials | 7 slots for the character and both props together (limit 8): suit, skin, eye, mouth, armor, cyber, hair |
| Textures | 25 PNG, largest 2048 x 2048 (limit 4096); estimated 41 MiB compressed in Unreal |
| Skinning | 111 deformation bones, 106 weighted, at most 6 influences per vertex (limit 8) |
| Face | 44 morph targets, jaw, tongue, independent eyes and lids, 6 expression presets, 14 viseme shapes |
| Mesh hygiene | no loose vertices, no zero-area faces, no non-manifold edges (checked on all 13 meshes) |

## Rig

`Operative_Control` is the animator rig (IK/FK with exact matching, poles, reverse-foot roll, fingers, torso/neck/head, look-at, root/pelvis separation, global scale, shoulder/hip/wrist correctives, twist bones, secondary-motion chains), `Operative_Skeleton` is the exported deformation skeleton. Everything is described in `docs/rig_usage.md`. The sidebar panel **MorphRig** (script `MorphRig_Tools.py` inside the .blend, run it once from the Text Editor) provides reset, IK/FK snapping, face presets and visemes, team switch, the clip list and the bake functions. `docs/skinning_pose_tests.png` shows the required skinning demonstration poses.

## Animation

96 named entries at 30 fps (85 motion, 11 static poses), all authored with the key-pose and gait generators in `source/generators/`, all present as Blender actions, baked FBX files and Unreal assets, mapped one to one in `docs/animation_manifest.json` (frames, duration, loop flag, root-motion policy, layer, event markers, entry/exit states, Unreal path). Nominal speeds 150 / 400 / 650 cm/s for walk / run / sprint; the four dashes carry 200 cm of root motion. Checked automatically: every duration lies in the range of the inventory, every loop closes with a bone error of 0.0 cm, stance skating stays within 3 cm, the mesh stays within 1.6 cm of the floor except three sleep transitions (`docs/known_issues.md`).

## Facial performance

`source/audio/dialogue.wav` (16.6 s): "Listen. The network is collapsing, and every lane into the district is going dark. But I can hold the north lane, if you stabilize the relay. Keep the signal alive, and trust the beacon. I'll be right behind you." Synthesised locally with Piper (voice `en_US-ljspeech-high`, public-domain training data). The alignment comes from the synthesis itself (exact samples per phoneme) and was checked with Whisper. The `dialogue` clip carries the lips (phoneme-driven viseme blending with complete closures for p/b/m and f/v), gaze shifts, blinks, an emotional arc from worry over resolve to warmth, brow and head emphasis and hand gestures on the words. The viseme mapping is in `docs/rig_usage.md`.

## Unreal showcase

A neutral room with a floor, a ramp (20 degrees), steps (up to 20 cm), movable aim targets, a prop-contact station and a motion viewer. Views: third person, front, side, top-down (the room walls are hidden there, the floor goes on), face close-up (a frontal, softer key light so the nose does not shade the mouth), hands close-up. Overlays for skeleton, sockets, foot IK, aim and look rays, and a live display of state, clip, time, speed and event markers. The animation controller (native code, no editor-only components) covers the whole inventory and is documented in `docs/animation_state_contract.md`.

### Controls

The same list is in the application (F1). Every key has a button in the mouse panel (F2).

**Locomotion**

| Keys | Effect |
|---|---|
| W A S D | move relative to the camera (independent facing: the body turns to the aim, gait follows the direction) |
| Shift / Ctrl | sprint (650 cm/s) / walk (150 cm/s); default run (400 cm/s) |
| Mouse | aim point (floor, targets); RMB hold or Caps Lock = aim pose while moving |
| Q | facing mode: aim / movement / locked |

**Mobility**

| Keys | Effect |
|---|---|
| Space | jump (jump_start, air, land; long fall gives fall and heavy landing) |
| V | dash 2 m (root motion of dash_f/b/l/r, direction from WASD relative to the body) |
| B | blink 6 m towards the movement direction (teleport is an event) |

**Combat**

| Keys | Effect |
|---|---|
| LMB | ranged fire (upper body layer, works while moving) |
| F | three shot burst |
| E | forearm blade: press again inside the combo window for melee 2 and 3 |
| R | reload (power cell out of the forearm slot, from the pouch, back in) |

**Casts**

| Keys | Effect |
|---|---|
| 1 / 2 / 3 | directional cast (moving) / ground cast at the cursor / self cast |
| 4 (hold) | channel: start, sustain while held, release ends it, X interrupts at any point |
| 5 (hold) / C | charge: release at any time fires, C cancels |
| 6 | deploy the beacon (attached prop spawns as a world beacon at the release event) |
| 7 | uplink (3 s recall gesture); 7 again or X cancels |
| X | interrupt channel / uplink / charge, stop emote and speech |

**Emotes**

| Keys | Effect |
|---|---|
| G / H / O / P | greet / victory / defeat / speech sample (dialogue clip and audio, face view) |

**Hits and disables**

| Keys | Effect |
|---|---|
| Up Down Left Right | directional additive hit reaction: from front / back / left / right |
| T / Y / N / U | stun / sleep and wake / knockback / knockup |
| J / Z | knockdown from a front hit (lands face up) / from a back hit (face down), then prone and getup |
| K / L / Backspace | kill (death once) / respawn / reset the character |
| F9 F10 F11 F12 | toggle root / silence / disarm / stasis |

**Animation**

| Keys | Effect |
|---|---|
| - / = | action rate 0.5x .. 1.5x (events scale with it and never duplicate) |
| M | motion viewer: character to the pedestal, animation browser plays any of the 96 clips |

**Views**

| Keys | Effect |
|---|---|
| Tab | cycle views (third person / front / side / top-down / face / hands) |
| Home PgUp PgDn End Ins Del | third person / front / side / top-down / face / hands (prop contact) |
| MMB drag, wheel | orbit and zoom in the orbiting views |

**Display**

| Keys | Effect |
|---|---|
| F1 F2 F3 | help overlay / panel / overlays (skeleton, sockets, foot IK, aim and look rays) |
| F4 F5 F6 | render mode (textured, normals, wireframe, clay) / forced LOD (auto, 0, 1, 2) / team A or B |
| F7 F8 | 1 or 10 animated Operatives / start the deterministic showcase sequence |
| ; (semicolon) | team outline on / off (the icon on the suit stays; the face view draws without the outline) |
| 0 | studio backdrop (plain floor and background, test props hidden) / test room |

**Targets**

| Keys | Effect |
|---|---|
| , . I | select next target / move the selected target to the cursor / patrol on and off |

### Mouse panel (F2)

Every function is also a button, toggle or slider in the panel, so the showcase works with the mouse alone. Sections:

| Section | Contents |
|---|---|
| View, render, team, LOD, instances | six views, render mode (textured, normals, wireframe, clay), forced LOD (auto, 0, 1, 2), team A or B, outline, studio backdrop, overlays (skeleton, sockets with IK and rays, everything with labels), 1 or 10 Operatives, run the showcase sequence, target selection and patrol, help |
| Locomotion, aim, stance | walk, run, sprint, facing mode, eight direction buttons with a speed slider (manual locomotion), manual aim sliders (yaw, pitch), aim pose, combat stance, wounded, always aim, foot IK and secondary motion on or off, action rate, health |
| Actions | jump, dash, blink, fire, burst, melee chain, reload, the three casts, channel, charge, beacon, uplink, interrupt, greet, victory, defeat, speech sample |
| Hits, disables, death | four directional hits, stun, sleep and wake, knockback, knockup, both knockdowns, kill from the front or the back, respawn, reset, toggles for root, silence, disarm and stasis |
| Animation browser (96 clips) | search by id, form or behaviour, play any clip in the motion viewer with loop, pause, scrub and speed 0.5x to 1.5x |
| Face control panel | six expression presets, clear, speech sample, look at the camera, automatic blink, clip face weight, jaw, tongue, blink and gaze sliders, 14 viseme sliders, left and right sliders for all 44 morph targets |


## Verification summary

Everything below was run on the delivered files; the numbers are those of the last run.

| Area | How it was checked | Result |
|---|---|---|
| Delivery | `python3 tools/verify_delivery.py --blender`: layout, manifest against the inventory, limits, dialogue files, videos, private paths, temporary files, Blender file opens | 26 checks, 0 failed |
| Geometry, materials | `docs/material_and_lod_report.json` (measured on the meshes in Blender) | LOD0 40,088 / LOD1 20,043 / LOD2 8,818 triangles, 7 material slots, textures up to 2048, at most 6 influences, 111 bones with one root, 180.05 cm (180.8 cm with hair) |
| Animation content | Blender QA in `source/generators/qa_lib.py` on all 96 clips, then again on the imported assets in Unreal | durations in range, 30 loops close within 1.5 cm (0.0 cm measured), dashes 200.0 cm of root motion, walk 150 / run 400 / sprint 650 cm/s, death clips end on the dead poses (0.0 cm) |
| Controller | deterministic sequence in the packaged client (`docs/showcase_sequence_trace.txt`, exit status 0) | 59 of 59 checks, 507 events without a duplicate, 0 pose spikes, capsule travel of the dashes 200.0 / 200.0 / 199.5 / 199.5 cm, blink 500 cm |
| Foot IK | ramp of 20 degrees, five 20 cm stairs and curbs of 10, 15 and 20 cm, IK on and off | mean height error of the planted feet 1.92 / 0.79 / 0.47 cm (12.21 / 1.88 / 1.97 cm with IK off), peak penetration 0.00 / 0.02 / 1.81 cm (15.72 / 2.30 / 6.81 cm with IK off) |
| Speech | `source/generators/verify_dialogue.py` (Whisper `small.en`) and the sequence check | 39 of 39 words found, audio and clip 16.6 s, audio starts with the clip |
| Frame time | `docs/perf/` (1920 x 1080 windowed, VSync off) | 1 Operative: 502 FPS on average, slowest frame 11.4 ms; 10 Operatives: 383 FPS, 1 percent low 93 FPS, slowest frame 11.7 ms |
| Visual inspection | contact sheets across the whole length of the three videos, close-ups of the face, the eyes, the torso and the shadows, wireframe and UV overlap checks of the head | the defects found this way were fixed; what remains is in `docs/known_issues.md` |

The three videos are recorded by `tools/make_videos.sh` from the packaged client of this folder. Remaining imperfections (stylised face, procedural textures, LOD1 and LOD2 without morph targets, no Animation Blueprint asset, Development build, Linux only, warped quads beside the eye and mouth rings, nine hidden UV overlaps) are listed with their numbers in `docs/known_issues.md`.

## Reproducing everything

`docs/build_and_import_instructions.md` has the commands: rebuild the .blend (`build_all.py`), regenerate the speech (`make_dialogue.py`), export (`export_and_bake.py`), import into Unreal (`tools/ue_import_all.sh`), package (`tools/build_linux.sh`) and record the videos (`tools/make_videos.sh`).

## Authorship and third-party material

The character geometry, skinning, rig, textures and all 96 clips are produced by the generators in this folder (procedurally, no interactive editing, no downloaded meshes, motion data or textures). The only third-party inputs are the speech voice model, the tools that ran it and the engines; they are listed with licences in `docs/THIRD_PARTY_ASSETS.csv`.
