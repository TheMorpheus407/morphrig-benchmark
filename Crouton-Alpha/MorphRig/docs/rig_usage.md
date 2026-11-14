# MorphRig Rig Usage Guide

Source rig lives in `MorphRig/source/Operative.blend`: two armatures.

- `Operative_Deform` — exportable deformation skeleton (64 bones, 1 root, meters, forward -Y, up +Z, 180 cm ground-origin neutral pose). FBX-exported; names stable across animations/LODs.
- `Operative_Control` — animator control rig (FK/IK endpoints, pole vectors, foot roll/heel/toe, hand controls). Constraints/IK are **not** exported live; bake intended motion to the deformation skeleton (see `tools/export_and_bake.py`).

## Animator controls (Control rig)
- `ctrl_root` / `ctrl_pelvis` — global transform; root is separate from pelvis. Reset to rest with:
  `pose_reset` operator / button in `args` menu (calls `bpy.ops.pose.armature_reset()` per layer) — or via `tools/pose_reset.py` (`blender -b --factory-startup -P tools/pose_reset.py -- source/Operative.blend`).
- `ctrl_hand_ik_L/R` — hand IK; pole via `pole_elbow_L/R`. Switch to FK pose matcher copies pose (standard hand FK bones: `upperarm_*`, `lowerarm_*`, `hand_*`).
- `ctrl_foot_ik_L/R` + `ctrl_ankle_roll_*` + `ctrl_toe_*` — foot IK, roll, heel/toe pivots; planted contact by pinning foot IK and pelvis height (ground adaption for ≤20° slopes / ≤20 cm steps is UE-side IK assisted).
- Fingers: `index/middle/ring/pinky_01..03_*` + `thumb_01..03_*` curl/spread for prop contact (emitter muzzle on `lowerarm_R`, blade on `lowerarm_L`, power cell, beacon).
- Torso/neck/head: `spine_01..03`, `neck_01`, `head` + eye bones `eye_L/R` (look-at). `jaw` for jaw.

## Facial rig (Shape Keys on Operative_Body; function in UE via morph/blend targets)
Controls: `Blink_L`, `Blink_R`, `Squint`, `BrowRaise`, `BrowLower`, `CheekRaise`, `JawOpen`, `LipClosure`, `Smile`, `Frown`, `Pucker`, `Viseme_A/I/U/O/M/F/L`, presets `Preset_Joy/Anger/Sadness/Surprise/Pain/Focus`.
Symmetric/asymmetric expressions, closed lips (mouth interior + teeth/tongue geometry, no holes), eyelids follow eyeballs (eye bones + lids via shape keys). Neutral state included.

## Secondary motion
Cable (`cable` mesh on backpack) + short hair tail are procedural followers; bake into secondary motions via linear-blend or simple spring node on `spine_03` sway; `tools/export_and_bake.py` bakes to deformation skeleton. Keep amplitude bounded to settle (no runaway sim).

## Re-baking
1. Edit pose on Control rig in Blender.
2. `blender -b --factory-startup -P MorphRig/tools/export_and_bake.py -- source/Operative.blend export`
3. `UnrealEditor-Cmd MorphRig.uproject -run=pythonscript -script=unreal/import_morphrig.py -unattended` (imports mesh+clips against `Operative_Deform_Skeleton`).

## Pose reset
`blender -b --factory-startup -P MorphRig/tools/pose_reset.py -- source/Operative.blend`
