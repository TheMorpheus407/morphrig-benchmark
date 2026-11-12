# MORPHRIG — Rig Usage Guide (source/Operative.blend)

## Scope
The editable Blender production asset contains the Operative character, a usable animator control rig, an exportable deformation skeleton, facial rig (shape keys + bones), 96 named actions, and LODs. The armature is `Operative_Armature`; a constraint-free export copy is used for FBX baking.

## Units & scale
- Blender source: meters. Character stands 1.80 m tall, feet at Z=0, clean ground-origin neutral pose.
- Unreal: centimeters. Import at 180 cm with no import-scale repair.
- All animation authored at 30 FPS.

## Deformation skeleton
One stable root (`root`) independent from the pelvis, connected hierarchy, 65 deformation bones, max 4 bone influences per vertex. Bone names/attachments stable across animations and LODs. See `docs/skeleton_and_sockets.json` for the full bone list and sockets (left_hand, right_hand, wrist_emitter, emitter_muzzle, blade_base, blade_tip, power_cell, beacon, effect_chest, effect_head).

## Animator controls (separate Blender objects)
- `CTRL_root`, `CTRL_pelvis`, `CTRL_spine`, `CTRL_head` — root/pelvis separation, torso, head.
- `FK_upperarm_*`, `FK_lowerarm_*`, `FK_hand_*` — FK arms.
- `IK_hand_*` (`IK_hand_l`, `IK_hand_r`) + `POLE_arm_*` — IK arms with pole vector.
- `IK_hand_*` carries a custom property `ik_fk` (0 = FK, 1 = IK) driving an IK/FK blend on the arm.
- `FK_thigh_*`, `FK_shin_*`, `FK_foot_*`, `IK_foot_*` (`IK_foot_l`, `IK_foot_r`) + `POLE_leg_*` — IK/FK legs with same `ik_fk` blend.
- `ROLL_foot_*` — foot roll (heel/toe pivot via `COPY_ROTATION` driven by `roll` custom property).
- `TOE_*` — toe pivot.
- `CTRL_look`, `CTRL_look_l`, `CTRL_look_r` — head and independent left/right eye look.
- Facial: `CTRL_jaw`, `CTRL_brow_l/r`, `CTRL_lip_upper`, `CTRL_lip_lower`, `CTRL_cheek_l/r`, `CTRL_mouth_l/r`, `CTRL_eyelid_u_l/r`.

## Pose reset
Select the armature, Pose mode, then `Pose > Clear Transform > All` (or Alt-G / Alt-R / Alt-S on selected bones) to return to the documented rest pose. A pose-reset button can be added as a Blender operator binding the same clear-transform.

## IK/FK switching
Set `ik_fk` on `IK_hand_l`/`IK_hand_r` (arms) and `IK_foot_l`/`IK_foot_r` (legs) to 0 (FK) or 1 (IK). Constraint influences blend (`1 - ik_fk` for FK copy-transforms, `ik_fk` for IK solver). Match FK to IK pose manually before switching back to avoid snapping.

## Facial rig
Shape keys on `Head` plus facial deformation bones. Blink (L/R), squint, brow raise/lower, jaw open/thrust, lip closure, corners (smile/frown), width, pucker/funnel, cheek, tongue.

### Six expression presets (shape-key values, apply all at once)
- joy/confidence: smile 0.7, brow_raise 0.3, jaw_open 0.1
- anger: frown 0.6, brow_lower 0.5, jaw_open 0.2
- concern/sadness: frown 0.5, lip_corner_down, brow_lower 0.3, jaw_open 0.15
- surprise: brow_raise 0.6, jaw_open 0.5, smile 0.1
- pain: frown 0.5, brow_lower 0.4, jaw_open 0.3, squint 0.6
- focus: brow_raise 0.2, jaw_open 0.05, lips neutral

### Viseme controls (documented mapping)
closed = M/B/P, lipteeth = F/V, open_a = open vowel A, wide_e = wide vowel E/I, rounded_o = rounded vowel O/U, tongue_teeth = T/D/N. Mapping is in `source/audio/dialogue_alignment.json`.

## Authored performance
`dialogue` action (15.0 s, 450 frames) with `source/audio/dialogue.wav`, `dialogue.txt` transcript, and `dialogue_alignment.json` (time-aligned visemes + cues at 3.0s gesture_hand, 7.5s emotion_shift, 12.0s phrase_end).

## Export
Run `source/generators/export_and_bake.py` to produce `export/Operative.fbx` (bind-pose skinned mesh) and `export/animations/Operative_AllAnims.fbx` (all 96 actions as takes). A procedural generator is allowed, but the delivered `.blend` already contains the finished assets.

## Deformation vs controls
Blender constraints/controllers do not export as live Unreal constraints; their intended motion is baked to the deformation skeleton. Keep original editable controls in Blender. Facial morphs/bones, skinning, attachments, materials, and event markers must survive actual import into Unreal.