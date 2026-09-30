# MorphRig – Operative

An original adult cyberpunk Operative (1.80 m) built end to end for real-time use: modelled, UV-mapped,
textured, rigged, skinned and animated in Blender 5.1.1 (editable control rig + baked actions), exported as
FBX and integrated into an Unreal Engine 5.8.3 C++ showcase with a native animation controller, a facial
rig with lip-synced dialogue, props, team variants, LODs and a packaged Linux client.

Everything in the character was produced by the scripts in `source/generators/` (procedural geometry,
Cycles-baked geometry maps + procedural PBR textures, keyed animation). No generative image/3D/motion
models, marketplace assets or paid services were used. The only third-party input is the Piper TTS voice
used to synthesise the dialogue audio (see `docs/THIRD_PARTY_ASSETS.csv`).

## Quick start
| What | How |
|---|---|
| Blender source | open `source/Operative.blend` (textures load relatively from `source/textures/`); sidebar tab **MorphRig** for pose reset, IK/FK pose matching and baking (`docs/rig_usage.md`) |
| Packaged showcase | `~/UnrealEngine/bin/ue-exec build/Linux/MorphRig.sh` (on other hosts run `build/Linux/MorphRig.sh` directly) |
| Unreal project | `unreal/MorphRig.uproject` (C++ module compiles on first open) |
| Rebuild everything | `python3 tools/export_and_bake.py` → `bash tools/build_linux.sh` → `bash tools/make_videos.sh` (`docs/build_and_import_instructions.md`) |

## Deliverable map (SPEC §11)
| Deliverable | Location |
|---|---|
| Editable production file (meshes, control rig, 112 `RIG_*` actions, 112 baked `SK_*` actions, face rig, LOD collections) | `source/Operative.blend` |
| Textures (7 PBR sets: BC, ORM, N (OpenGL), M masks; team icon atlas) | `source/textures/`, copies in `export/textures/` |
| Dialogue audio, transcript, phoneme/word alignment | `source/audio/dialogue.wav`, `dialogue.txt`, `dialogue_alignment.json` |
| Generators (procedural source of the whole character) | `source/generators/` |
| Skeletal mesh FBX (LOD0/1/2), static beacon | `export/Operative.fbx`, `export/Operative_LOD1.fbx`, `export/Operative_LOD2.fbx`, `export/props/SM_Beacon.fbx` |
| Baked animations (one skeleton-only FBX per clip, take `SK_<clip>`), face curves, clip metadata | `export/animations/*.fbx`, `face_curves.json`, `clips_meta.json` |
| Unreal project (C++ source, config, imported content, import script) | `unreal/` (`Source/MorphRig/`, `Config/`, `Content/MorphRig/`, `Scripts/import_operative.py`) |
| Packaged Linux client | `build/Linux/MorphRig.sh` |
| Documentation | `docs/rig_usage.md`, `skeleton_and_sockets.json`, `animation_manifest.json`, `animation_state_contract.md`, `material_and_lod_report.json`, `THIRD_PARTY_ASSETS.csv`, `build_and_import_instructions.md`, `known_issues.md` |
| QA data | `docs/qa/motion_qa.json` (per-clip foot slide, sole/floor, body clearance, loop seams), `docs/qa/MorphRig_Trace_packaged.txt` (deterministic sequence trace from the packaged client) |
| Performance logs | `docs/perf/MorphRig_Perf_1inst_*.json/.csv`, `docs/perf/MorphRig_Perf_10inst_*.json/.csv` |
| Tools | `tools/export_and_bake.py`, `tools/build_linux.sh`, `tools/make_videos.sh`, `tools/make_docs.py`, `tools/make_dialogue.py`, `tools/morphrig_rig_ui.py` |
| Presentation videos (captured from the packaged client) | `presentation/turntable.mp4`, `motion_showcase.mp4`, `face_performance.mp4` |

## The character in numbers
* Skeleton: 96 bones (85 deforming + 11 `sock_*` socket bones), single `root`, all bone scales 1 in Unreal,
  centimetres. 11 sockets: `hand_l_grip`, `hand_r_grip`, `muzzle_r`, `cell_slot_r`, `blade_base_r`,
  `blade_tip_r`, `beacon_holster`, `fx_chest`, `fx_head`, `fx_ground`, `fx_palm_l`.
* Triangles: LOD0 45,524 · LOD1 22,623 · LOD2 10,717 (limits 80k / 40k / 20k); 7 material slots; max 4
  influences per vertex; textures 4096 (skin, suit), 2048 (armor, cyber), 1024 (hair, eye, mouth).
* Face: 45 morph targets (brows, eyes/cheeks, full mouth set incl. width, pucker/funnel, press, rolls,
  14 visemes) + bone-driven L/R blink / wide / squint lids, jaw, 3-bone tongue, gaze; 6 expression presets
  + neutral. Viseme mapping: `docs/rig_usage.md`.
* Animation: all 96 required entries of `docs/required_animations.csv` (85 motions, 9 aim poses,
  `dead_front`, `dead_back`) + 16 extras (deformation demo, 15 face-control poses). 30 fps.
* Dialogue: 17.6 s original line ("East lane is mine. …"), lip sync from the phoneme alignment, gaze
  changes, emotional shift (confident → concern → anger → resolve), gestures (point east, fist to heart,
  console taps, point "hold the line", hand on chest).
* Props: wrist emitter (muzzle socket), deployable forearm blade, removable power cell (reload hands it to
  the belt charger and back), deployable beacon (placed on the floor, replaced by a static mesh in Unreal).
* Team variants: A cyan / chevron, B orange / ring (material parameter), stencil outline + team icon.

## Showcase controls (also shown in-game, F1)
| Group | Keys |
|---|---|
| Move | WASD (camera relative), Shift sprint, Ctrl/Caps walk toggle, F11 strafe (face aim) toggle, F10 stance relaxed/combat/wounded |
| Aim | hold RMB / L lock; M aim at the selected target (Tab selects, arrows + PgUp/PgDn move it) |
| Traversal | Space jump, Q dash (input direction, root motion 2 m), E blink |
| Fight | LMB melee (click again for the combo), RMB tap fire / hold burst, R reload, 1 cast directional, 2 cast ground, 3 cast self |
| Held | 4 channel (X interrupt), 5 charge (release fires, C cancels), 6 deploy beacon, 7 uplink (release early = cancel) |
| Reactions | H hit (cycles direction, Shift = back), T stun, K knockback, U knockup, J knockdown (Shift = from behind), N sleep / wake |
| Life | Del death (Shift = back impact), Z respawn, G greet, V victory, B defeat, P dialogue with audio, Enter resume, Backspace reset |
| View | F2 camera (third person / top-down 55° / side / front / face close-up / orbit), wheel zoom, `,` `.` orbit, O skeleton overlay |
| Panels | F3 face panel (every L/R control, visemes, presets), F4 searchable animation browser (Shift+click plays on the motion-viewer pedestal), F5 team A/B, F6 LOD auto/0/1/2, F7 1 or 10 operatives, F8 outline + icon |
| Sequence | F9 deterministic 108 s showcase sequence (trace in `Saved/Logs/MorphRig_Trace.txt`), `[` `]` action rate 0.5–1.5× |

The HUD shows state, clip, time/frame, speed, layer weights, camera, team, LOD, FPS and an event log with a
clip timeline and marker ticks. Command-line modes (`-MorphSequence`, `-MorphBench`, `-MorphCapture`,
`-MorphInstances`) are listed in `docs/build_and_import_instructions.md`.

## Verification that was actually run
* Blender motion QA over all 112 clips (`docs/qa/motion_qa.json`): foot slide, sole height, mesh-vs-floor,
  hand/forearm/cyber-arm vs body/gear clearance, pelvis drift and loop seams. Automatic floor and contact
  correction runs during authoring. Remaining deviations are listed in `docs/known_issues.md`.
* Unreal import: headless import of mesh, LODs, 45 morph targets, sockets, 112 animations with their
  event notifies (count checked against the markers), face curves, audio and the map. Rendered checks of
  materials, team colours, LODs, face close-up and dialogue in the running game.
* Packaged client (`build/Linux`): the deterministic sequence produced the same trace as the editor run
  (`docs/qa/MorphRig_Trace_packaged.txt`): locomotion, start/stop/turn, jump + landing, 2 m root-motion dash,
  melee 1-2-3 combo with balanced hit windows, layered fire/burst/reload while walking, casts, channel
  interrupted by a hit, charge release and cancel, deploy, uplink, blink, stun, knockback, knockdowns,
  knockup landing on the back, sleep/wake, death overriding a cast, ignored second death, respawn, death
  in the air, greet, dialogue with audio, victory.

## Performance (packaged Development client, 1920×1080 windowed, no frame generation, vsync off)
Host: AMD Ryzen 9 9950X (16 C / 32 T), 92 GB RAM, RTX 5090 (driver 595.71), Vulkan SM6, NixOS / KDE Plasma
Wayland. 10 s warm-up, 30 s capture, autopilot cycling through states on every operative.

| Operatives | avg FPS | frame ms avg / p50 / p95 / p99 | game thread avg | render thread avg | GPU avg | frames > 16.7 ms |
|---|---|---|---|---|---|---|
| 1 | 254.7 | 3.93 / 2.10 / 9.47 / 12.37 | 1.86 ms | 1.71 ms | 3.39 ms | 27 of 7,643 (0.4 %) |
| 10 | 143.9 | 6.95 / 7.21 / 11.98 / 15.90 | 2.20 ms | 2.10 ms | 6.30 ms | 43 of 4,317 (1.0 %) |

The 60 FPS target holds on average and at p99. Short render-thread stalls in 10 ms steps occur every few
seconds in every configuration tried (see `docs/known_issues.md`). Lighting: one shadowed key light and a
shadowless fill that stay at ±30° to the view direction (every camera sees the lit side), a sky light and
sky atmosphere; no dynamic GI (Lumen off), screen-space reflections.
