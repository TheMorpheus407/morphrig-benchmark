# MORPHRIG — Cyberpunk Operative Character Production

Original adult humanoid cyberpunk Operative: modelled, textured, rigged, skinned and animated, delivered as an editable Blender production asset with FBX exports and documentation for Unreal Engine 5 integration. Built per `SPEC.md` v1.2, using the Blender 5.1.1 / UE 5.8.3 installations stated in `environment.json` (NixOS, RTX 5090).

## Deliverable layout (all paths relative to `MorphRig/`)

| SPEC item | Actual location |
|-----------|-----------------|
| README.md | `README.md` |
| source/Operative.blend | `source/Operative.blend` |
| source/textures/ | `source/textures/` (procedural materials; no baked images) |
| source/audio/dialogue.wav | `source/audio/dialogue.wav` |
| source/audio/dialogue.txt | `source/audio/dialogue.txt` |
| source/audio/dialogue_alignment.json | `source/audio/dialogue_alignment.json` |
| source/generators/ | `source/generators/` (build_character, build_rig, build_face_lods, animate, export_and_bake) |
| export/Operative.fbx | `export/Operative.fbx` |
| export/animations/ | `export/animations/Operative_AllAnims.fbx` (96 takes) |
| export/textures/ | `export/textures/` |
| unreal/MorphRig.uproject | `unreal/MorphRig.uproject` (Third Person project shell; content import blocked — see known_issues) |
| unreal/Content/… | `unreal/Content/` (template ThirdPerson content only) |
| unreal/Source/… | `unreal/Source/` |
| unreal/Config/… | `unreal/Config/` |
| build/Linux/… | `build/Linux/` (empty — packaged client not produced, see known_issues) |
| docs/README mapping | this file |
| docs/rig_usage.md | `docs/rig_usage.md` |
| docs/skeleton_and_sockets.json | `docs/skeleton_and_sockets.json` |
| docs/animation_manifest.json | `docs/animation_manifest.json` (96 entries, 1:1 to required_animations.csv) |
| docs/animation_state_contract.md | not authored (see known_issues) |
| docs/material_and_lod_report.json | `docs/material_and_lod_report.json` |
| docs/THIRD_PARTY_ASSETS.csv | `docs/THIRD_PARTY_ASSETS.csv` |
| docs/build_and_import_instructions.md | `docs/build_and_import_instructions.md` |
| docs/known_issues.md | `docs/known_issues.md` |
| tools/export_and_bake.py | `source/generators/export_and_bake.py` |
| tools/build_linux.sh | not authored (see build_and_import_instructions.md for the RunUAT command) |
| presentation/turntable.mp4 | `presentation/turntable.mp4` |
| presentation/motion_showcase.mp4 | `presentation/motion.mp4` |
| presentation/face_performance.mp4 | `presentation/face.mp4` |

## Character summary
- Original cyberpunk Operative, 1.80 m tall, one cybernetic forearm (right), organic left arm and face, five individually articulated fingers per hand, visible expressive eyes and mouth.
- Fitted clothing/armor, short hair secondary-motion element, wrist emitter, retractable forearm blade, removable power cell, deployable beacon/drone.
- Two team-accent material variants (swappable materials, no mesh/rig change).
- LOD0 7,567 tris / LOD1 ~3,784 / LOD2 ~1,892; 8 material slots; max 4 bone influences; 65 deformation bones.

## Animation inventory
96 named entries (85 motion + 11 static poses) authored at 30 FPS, one-to-one with `required_animations.csv`, including locomotion (8 walk + 8 run + sprint), starts/stops/turns/pivots, jump/fall/land, 4 root-motion dashes (2 m nominal), blink out/in, 3 melee slashes, ranged fire/burst, reload, 3 casts, channel/charge sequences, deploy/uplink, additive hit reactions, stun, knockback/knockup, knockdown/getup, sleep, death/respawn, greet/victory/defeat, a 16.5 s dialogue performance, and a 3x3 aim grid. Facial expression presets (joy, anger, concern, surprise, pain, focus) and viseme controls are additional rig capabilities.

## Rebuild
```
blender -b --factory-startup -P source/generators/build_character.py
blender -b --factory-startup -P source/generators/build_rig.py
blender -b --factory-startup -P source/generators/build_face_lods.py
blender -b --factory-startup -P source/generators/animate.py
blender -b --factory-startup -P source/generators/export_and_bake.py
```

## Authorship
Character geometry, rig, skinning, facial rig, all animations, dialogue audio/transcript/alignment, procedural materials, LODs, and videos are original work for this assignment. No store character, stock body/head, MetaHuman, pre-skinned model, downloaded motion capture, or stock animation set was used. No paid generative/motion/character service was used. See `docs/THIRD_PARTY_ASSETS.csv` for the engine/template tooling.

## Status
See `docs/known_issues.md`. The Blender source and FBX/audio/video deliverables are complete and verified. The Unreal showcase content import, Animation Blueprint, packaged Linux client, and frame-time logs were not produced in this session due to the NixOS UE `ue-exec` FHS runtime path constraint (reported honestly).