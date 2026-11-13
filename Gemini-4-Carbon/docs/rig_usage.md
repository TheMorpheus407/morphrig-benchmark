# MORPHRIG — Blender 5.1.1 Animator Control Rig & Facial Rig Usage Guide

Authoritative source file: [`source/Operative.blend`](../source/Operative.blend)  
Deformation skeleton & socket reference: [`docs/skeleton_and_sockets.json`](skeleton_and_sockets.json)  
Rebake & FBX export pipeline: [`tools/export_and_bake.py`](../tools/export_and_bake.py)

---

## 1. Rig Architecture Overview

`Armature` inside [`source/Operative.blend`](../source/Operative.blend) separates clean engine-ready deformation bones from non-deforming animator controls and mechanical helpers using Blender 5.1 Bone Collections:

| Bone Collection | Count | Deform (`use_deform`) | Exported to FBX | Purpose |
| :--- | :---: | :---: | :---: | :--- |
| `DEF` | **92** | `True` | **Yes** (`only_deform_bones=True`) | Single-root (`root`) connected/parented game skeleton (`pelvis`, 3-bone spine, neck/head, jaw/tongue/eyes/brows/cheeks/lips, clavicles/arms/twist/30-bone hands, thighs/calves/twist/feet/balls, `cable_01..03`, `strap_01..03`, `emitter_bone_r`, `blade_r`, `cell_bone`, `beacon_bone`). |
| `CTRL_Root_Torso` | 7 | `False` | No | `CTRL_Master` (global placement, uniform scale & custom rig sliders), `CTRL_Root_Motion` (ground root trajectory), `CTRL_COG`, `CTRL_Pelvis`, `CTRL_Spine_01..03`. |
| `CTRL_Head_Look` | 6 | `False` | No | `CTRL_Neck`, `CTRL_Head`, `CTRL_Jaw`, `CTRL_LookAt` (master target), `CTRL_LookAt_L`, `CTRL_LookAt_R` (stereo eye convergence). |
| `CTRL_Arms_IKFK` | 14 | `False` | No | `CTRL_Clavicle_L/R`, FK chains (`CTRL_FK_UpperArm_L/R`, `CTRL_FK_LowerArm_L/R`, `CTRL_FK_Hand_L/R`), IK hands (`CTRL_IK_Hand_L/R`), elbow pole targets (`CTRL_Pole_Arm_L/R`). |
| `CTRL_Hands` | 32 | `False` | No | `CTRL_Fingers_L/R` (master curl/spread drivers) + 30 individual phalanx controls (`CTRL_thumb_01..03_l/r` through `CTRL_pinky_01..03_l/r`). |
| `CTRL_Legs_IKFK` | 18 | `False` | No | FK leg chains (`CTRL_FK_Thigh_L/R`, `CTRL_FK_Calf_L/R`, `CTRL_FK_Foot_L/R`, `CTRL_FK_Ball_L/R`), IK foot controls (`CTRL_IK_Foot_L/R`), knee poles (`CTRL_Pole_Leg_L/R`), reverse-foot roll (`CTRL_FootRoll_L/R`), `CTRL_HeelPivot_L/R`, `CTRL_ToePivot_L/R`. |
| `CTRL_Face` | 15 | `False` | No | `CTRL_Brow_Inner_L/R`, `CTRL_Brow_Outer_L/R`, `CTRL_Eyelid_Upper_L/R`, `CTRL_Eyelid_Lower_L/R`, `CTRL_Cheek_L/R`, `CTRL_Lip_Upper`, `CTRL_Lip_Lower`, `CTRL_Lip_Corner_L/R`, `CTRL_Tongue`. |
| `CTRL_Props_Sec` | 10 | `False` | No | Controllable secondary chains (`CTRL_Cable_01..03`, `CTRL_Strap_01..03`), `CTRL_Blade_Deploy`, `CTRL_Emitter`, `CTRL_Cell`, `CTRL_Beacon`. |
| `MCH` | 29 | `False` | No | Hidden reverse-foot hierarchy, IK/FK target chains, twist distribution helpers, and prop constraint targets. |

---

## 2. Sidebar UI Panel (`View3D > Sidebar [N] > MorphRig`)

Opening [`source/Operative.blend`](../source/Operative.blend) registers the embedded [`morphrig_ui.py`](../source/generators/build_rig_and_skin.py) script (`use_module = True`), exposing the **MorphRig** panel in the 3D Viewport `N`-sidebar:

1. **One-Click Pose & Face Reset (`morphrig.reset_pose`)**:
   - Resets every bone transform in `Armature` to identity, restores default IK/FK switches (`legs = IK`, `arms = FK`, `eye_look_at = 1.0`), resets left/right finger curl & spread to `0.0`, and zeroes all 46 shape keys on `Operative_LOD0`.
2. **Seamless IK ↔ FK Blending & Pose-Matching (`morphrig.snap_ik_fk`)**:
   - Custom float properties on `CTRL_Master`:
     - `ik_fk_arm_l`, `ik_fk_arm_r` (`0.0 = FK`, `1.0 = IK`)
     - `ik_fk_leg_l`, `ik_fk_leg_r` (`0.0 = FK`, `1.0 = IK`, default `1.0`)
   - Clicking **Snap Arm L/R to IK** or **Snap Arm L/R to FK** (and same for **Leg L/R**) aligns the target control chain to the evaluated deformation pose and flips the switch without visual popping.
3. **Reverse-Foot Roll & Pivots**:
   - Rotate `CTRL_FootRoll_L/R` on local `+X` to roll cleanly up onto the ball of the foot while keeping the toe planted; rotate `-X` to rock back onto `CTRL_HeelPivot_L/R`.
   - `CTRL_ToePivot_L/R` and `CTRL_HeelPivot_L/R` provide explicit swivel/tilt pivots for sharp turns (`turn_l90`, `turn_r90`, `pivot_l180`, `pivot_r180`) without ground penetration.
4. **Hands & Fingers**:
   - `CTRL_Fingers_L` and `CTRL_Fingers_R` carry driven custom properties `curl` (`-0.5 .. +1.2`) and `spread` (`-0.5 .. +1.0`) for rapid fist/relax/splay posing, layered additively with the 30 individual `CTRL_<finger>_01..03_l/r` bones for exact prop contact.
5. **Head & Stereo Eye Look-At**:
   - `CTRL_Master["eye_look_at"]` (`0..1`) and `CTRL_Master["head_look_at"]` (`0..1`) blend damped tracking toward `CTRL_LookAt` (`CTRL_LookAt_L` / `CTRL_LookAt_R` parented to `CTRL_LookAt` for vergence adjustments).
6. **Prop Space-Switching & Constraint Handoffs**:
   - `CTRL_Master["cell_in_hand_l"]` (`0..1`): switches `cell_bone` between the wrist-emitter breech (`emitter_bone_r`) and left-hand grip (`hand_l`) during `reload`.
   - `CTRL_Master["beacon_in_hand_l"]` (`0..1`) & `CTRL_Master["beacon_planted"]` (`0..1`): switches `beacon_bone` smoothly from rear-right belt dock (`pelvis`) → left hand (`hand_l`) → planted world ground (`root`) during `deploy` without slipping.
   - `CTRL_Blade_Deploy` local `-Y` translation extends/retracts `blade_r` along the cybernetic forearm housing during `melee_1`, `melee_2`, and `melee_3`.

---

## 3. Hybrid Facial Rig, Visemes & Expression Presets

`Operative_LOD0` combines **19 facial deformation bones** (`jaw`, `tongue_01..02`, `eye_l/r`, `eyelid_upper/lower_l/r`, `brow_inner/outer_l/r`, `cheek_l/r`, `lip_upper/lower`, `lip_corner_l/r`) with **46 Shape Keys** in `source/Operative.blend` (`45` non-zero `UMorphTarget`s on `/Game/MorphRig/Character/Operative`, plus zero-delta `V_SIL` rest key):

- **Asymmetric Left/Right & Oral Controls (21 keys)**:
  - Eyelids & Brows: `blink_l/r`, `squint_l/r`, `brow_up_l/r`, `brow_down_l/r`
  - Cheeks & Expressions: `cheek_raise_l/r`, `smile_l/r`, `frown_l/r`
  - Jaw, Lips & Tongue: `jaw_open`, `lip_close`, `mouth_wide`, `mouth_pucker`, `mouth_funnel`, `tongue_up`, `tongue_out`
- **Joint Volume-Preservation Correctives (6 keys)**:
  - `corr_shoulder_up_l/r`, `corr_elbow_bend_l/r`, `corr_knee_bend_l/r`
- **Calibrated Speech Visemes (13 keys, mapped in [`source/audio/dialogue_alignment.json`](../source/audio/dialogue_alignment.json))**:
  - `V_SIL` (rest), `V_MBP` (bilabial closure), `V_FV` (labiodental), `V_TH` (interdental tongue), `V_TDNL` (alveolar), `V_SZ` (sibilant dental), `V_KG` (velar/glottal), `V_AA` (open vowel), `V_EE` (wide front vowel), `V_EH` (mid-open vowel), `V_OH` (rounded mid-back vowel), `V_OU` (close rounded pucker), `V_ER` (rhotic).
- **Expression Presets (6 keys)**:
  - `expr_joy_confidence`, `expr_anger`, `expr_concern_sadness`, `expr_surprise`, `expr_pain`, `expr_focus`.

---

## 4. Editing & Rebaking Animations (`CTRL_<id>` → `<id>`)

Every entry in [`required_animations.csv`](../required_animations.csv) has **both**:
1. Editable animator control action `CTRL_<id>` (and editable facial shape-key action `SK_CTRL_<id>`) keyed on `CTRL_*` rig bones and properties.
2. Baked deformation action `<id>` (and `SK_<id>`) sampled at 30 FPS on the 92 `DEF` bones.

After modifying any `CTRL_<id>` or `SK_CTRL_<id>` action in [`source/Operative.blend`](../source/Operative.blend), rebake and re-export all FBX takes and manifests headlessly with:

```bash
blender -b --factory-startup -P tools/export_and_bake.py -- --rebake
```
