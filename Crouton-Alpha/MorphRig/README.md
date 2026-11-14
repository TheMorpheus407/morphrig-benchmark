# MorphRig — Cyberpunk Operative (Crouton Alpha)

Original adult humanoid cyberpunk Operative: fully modeled, textured, rigged, skinned, animated (96 entries), facial-synchronized speech, Unreal showcase.

## Deliverable map
| Required | Location |
|---|---|
| `README.md` | `MorphRig/README.md` (this file) |
| `source/Operative.blend` | `MorphRig/source/Operative.blend` |
| `source/textures/` | `MorphRig/source/textures/` (1024 PNG basecolor+roughness × 8 mats) |
| `source/audio/` | `MorphRig/source/audio/` (dialogue.wav 15.35 s, dialogue.txt, dialogue_alignment.json) |
| `source/generators/` | `MorphRig/source/generators/` (build_character.py, build_animations.py) |
| `export/Operative.fbx` | `MorphRig/export/Operative.fbx` |
| `export/animations/` | `MorphRig/export/animations/` (96 baked FBX) |
| `export/textures/` | `MorphRig/export/textures/` |
| `unreal/` | `MorphRig/unreal/` (MorphRig.uproject, Source, Config, Content) |
| `build/Linux/` | `MorphRig/build/Linux/` (packaged client; see build notes) |
| `docs/` | `MorphRig/docs/` (rig_usage.md, skeleton_and_sockets.json, animation_manifest.json, animation_state_contract.md, material_and_lod_report.json, THIRD_PARTY_ASSETS.csv, build_and_import_instructions.md, known_issues.md) |
| `tools/` | `MorphRig/tools/` (export_and_bake.py, export_clips.py, pose_reset.py, build_linux.sh) |
| `presentation/` | `MorphRig/presentation/` (turntable.mp4, motion_showcase.mp4, face_performance.mp4) |

## Character
1.80 m, meters source → centimeters in Unreal (180 cm, no undocumented rescale). Forward -Y (Blender) / +X (Unreal), up +Z. Ground-origin neutral pose. Left forearm cybernetic (blade), right wrist emitter, removable power cell, deployable beacon/drone. Two team variants (A cyan / B orange: emissive + outline icon, not color alone). ≤8 material slots (8), ≤8 bone influences (≤4 actual), LOD0 17,680 tris / LOD1 8,840 / LOD2 4,420 (distinct meshes), 64 deformation bones.

## Showcase controls (in-app; no source edit needed)
- Move: WASD (8-dir walk/run/sprint blends, independent facing), Space jump, Shift sprint.
- Camera: Third-person (0), Full-body close (1), Top-down (2), Face close-up (3) — keys 1-4.
- Animation browser: searchable list of all 96 clips; select + play. Buttons: melee (1/2/3), ranged fire/burst, reload, cast x3, dash x4, blink in/out, channel start/loop/end/interrupt, charge start/hold/release/cancel, deploy, uplink start/loop/end/cancel, hits x4 (additive), stun, sleep, knockup/knockdown/getup, death front/back, respawn, greet/victory/defeat, dialogue (+ speech sample play).
- Aim: sliders yaw -60..60 / pitch -35..35 (9-pose layer).
- Sliders: playback speed 0.5x-1.5x, LOD 0/1/2, team A/B.
- Face panel: blink L/R, squint, brow, cheek, jaw, lip closure, smile/frown, pucker, visemes M/F/A/I/U/O/L, 6 presets (joy/confidence, anger, concern/sadness, surprise, pain, focus).
- Buttons: Reset character, Interrupt action, Run deterministic sequence (prints state/event trace), Toggle 1/10 instances, frame-time log overlay.
- Room: floor, ~14° ramp, 4 steps (18 cm), movable targets, prop-contact station.

## Deterministic sequence
`RunDeterministicSequence` steps: idle_combat → walk_f → run_fr → melee_1 → ranged_fire → reload → channel_start → channel_loop → channel_interrupt → hit_f → stun_start → stun_end → dash_f → jump_start → jump_air → jump_land → dialogue → victory, printing state/event trace.

## Perf
1/10 instance toggle; target 60 FPS @ 1920×1080 (Vulkan SM6) on reference RTX 5090 host; frame-time logs via HUD (see known_issues for settings).

## Rebuild
`docs/build_and_import_instructions.md` (Blender generators → export → headless import → cook → package).

## Author info
Character geometry/rig/animations authored by procedural Blender Python (generators listed above); third-party items in `docs/THIRD_PARTY_ASSETS.csv`.
