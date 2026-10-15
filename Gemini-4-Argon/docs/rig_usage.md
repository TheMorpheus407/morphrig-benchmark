# MorphRig v1.2 — Control Rig & Deformation Skeleton Usage Guide

## 1. Rig Architecture Overview

The authoritative character rig lives in [`source/Operative.blend`](../source/Operative.blend) on the single Armature object **`OperativeRig`**.

To keep the exported Unreal Engine hierarchy 100% clean while giving animators full interactive controls in Blender, `OperativeRig` separates bones into three Armature Bone Collections:

| Bone Collection | Deform (`use_deform`) | Exported to FBX | Purpose |
| :--- | :--- | :--- | :--- |
| **`DEF_Export`** | `True` (except `root` container) | **Yes** (93 bones) | Single-root game deformation skeleton (`root` -> `pelvis` -> spine, limbs, twist bones, 30 finger phalanges, facial bones, weapon/prop sockets, secondary chains). |
| **`CTRL_Animator`** | `False` | **No** | Interactive animator control bones (`CTRL_*`) for IK/FK limbs, pole targets, foot roll, finger curl/spread, head/eye look-at, jaw, and secondary chains. |
| **`MCH_Internal`** | `False` | **No** | Internal mechanical helper bones (`MCH_heel_l/r`, `MCH_toe_l/r`) for multi-stage foot-roll pivots. |

---

## 2. Coordinate, Scale & Facing Conventions

* **Standing Height**: `1.800 m` (`180.0 cm` in Unreal Engine at `1.0` uniform import scale).
* **Blender Axes**: `+Z` Up, `-Y` Forward, `-X` Character Right (`+X` Character Left).
* **Ground Contact**: Rest pose boot soles sit flush on world `Z = 0.000 m`.
* **Root Bone**: `root` sits at world origin `(0.0, 0.0, 0.0)` with identity rotation `(0, 0, 0)` and uniform scale `(1, 1, 1)`.

---

## 3. Animator Control Guide (`CTRL_Animator`)

### 3.1 Master & Core Torso Controls
* **`CTRL_master`**: Global character placement control at `(0, 0, 0)`. Holds custom rig properties:
  * `ik_fk_arm_l` (`0.0` = FK, `1.0` = IK)
  * `ik_fk_arm_r` (`0.0` = FK, `1.0` = IK)
  * `ik_fk_leg_l` (`0.0` = FK, `1.0` = IK)
  * `ik_fk_leg_r` (`0.0` = FK, `1.0` = IK)
  * `secondary_spring_strength` (`0.0 .. 1.0`)
  * `team_variant` (`0` = Team A Cyan Hex-Chevron, `1` = Team B Amber Crossed-Diamond)
* **`CTRL_root`**: Root-motion trajectory control for dashes (`dash_f`, `dash_b`, `dash_l`, `dash_r`).
* **`CTRL_pelvis`** -> **`CTRL_spine_01`** -> **`CTRL_spine_02`** -> **`CTRL_spine_03`** -> **`CTRL_neck`** -> **`CTRL_head`**: FK torso, neck, and head orientation chain.

### 3.2 Arms, Twist Bones & Finger Controls
* **FK Arm Controls**: `CTRL_clavicle_l/r` -> `CTRL_fk_upperarm_l/r` -> `CTRL_fk_lowerarm_l/r` -> `CTRL_fk_hand_l/r`.
* **IK Arm Controls**: `CTRL_ik_hand_l/r` (wrist goal) + `CTRL_pole_arm_l/r` (elbow pole vector).
* **Twist Distribution**: `upperarm_twist_01_l/r` and `lowerarm_twist_01_l/r` distribute axial twist smoothly between shoulder/elbow and elbow/wrist so `pose_forearm_twist` (`±90°` wrist pronation/supination) preserves forearm volume without candy-wrapper collapse.
* **Finger Master Controls (`CTRL_fingers_l`, `CTRL_fingers_r`)**:
  * Custom properties: `curl_all`, `spread_all`, `thumb_curl`, `index_curl`, `middle_curl`, `ring_curl`, `pinky_curl`.
  * Individual phalange pose bones (`thumb_01..03_l/r`, `index_01..03_l/r`, `middle_01..03_l/r`, `ring_01..03_l/r`, `pinky_01..03_l/r`) remain directly rotatable for fine grip adjustments on `prop_cell` and `prop_beacon`.

### 3.3 Legs & Foot-Roll Controls
* **IK Leg Controls**: `CTRL_ik_foot_l/r` (planted foot goal) + `CTRL_pole_leg_l/r` (knee pole vector).
* **Foot Roll & Banking**: `CTRL_foot_roll_l/r` drives heel-strike pivot (`MCH_heel_l/r`), ball-roll lift (`ball_l/r`), and toe-off pivot (`MCH_toe_l/r`).
* **FK Leg Controls**: `CTRL_fk_thigh_l/r` -> `CTRL_fk_calf_l/r` -> `CTRL_fk_foot_l/r` -> `CTRL_fk_ball_l/r`.

### 3.4 Facial Rig (Skeletal Bones + 38 Shape Keys)
* **Gaze & Look-At**: `CTRL_look_at` (master gaze target in front of the face) with individual eye offsets `CTRL_eye_l` and `CTRL_eye_r` driving `eye_l` and `eye_r`.
* **Jaw & Oral Cavity**: `CTRL_jaw` / `jaw` bone + `tongue_01` and `tongue_02` bones inside the oral cavity, plus `eyelid_upper_l/r`, `eyelid_lower_l/r`, `brow_inner_l/r`, `brow_mid_l/r`, `brow_outer_l/r`, `cheek_l/r`, `nostril_l/r`, `lip_upper_mid/l/r`, `lip_lower_mid/l/r`, `lip_corner_l/r`.
* **38 Shape Keys (Morph Targets)** on `Operative_LOD0`:
  * **Eyelids & Brows**: `blink_l`, `blink_r`, `squint_l`, `squint_r`, `brow_raise_l`, `brow_raise_r`, `brow_lower_l`, `brow_lower_r`
  * **Cheeks & Lips**: `cheek_raise_l`, `cheek_raise_r`, `cheek_puff`, `smile_l`, `smile_r`, `frown_l`, `frown_r`, `jaw_open`, `jaw_left`, `jaw_right`, `lip_close`, `mouth_wide`, `mouth_narrow`, `mouth_pucker`, `mouth_funnel`, `tongue_up`, `tongue_out`
  * **6 Expression Presets**: `expr_joy_confidence`, `expr_anger`, `expr_concern_sadness`, `expr_surprise`, `expr_pain`, `expr_focus`
  * **11 Speech Visemes**: `viseme_SIL`, `viseme_MBP`, `viseme_FV`, `viseme_TH`, `viseme_TDNL`, `viseme_SZ`, `viseme_KG`, `viseme_AA`, `viseme_EE`, `viseme_OH`, `viseme_OO`
  * **6 Joint Volume-Preservation Correctives**: `corr_shoulder_up_l`, `corr_shoulder_up_r`, `corr_knee_bend_l`, `corr_knee_bend_r`, `corr_hip_bend_l`, `corr_hip_bend_r`

---

## 4. Embedded Blender Operators (`morphrig_rig_tools.py`)

An embedded Python script (`morphrig_rig_tools.py`) inside `source/Operative.blend` registers two animator operators:

1. **Pose Reset (`morphrig.reset_pose`)**:
   * Resets all pose bones on `OperativeRig` to rest transform `(loc=0, rot=identity, scale=1)` and zeroes all 38 Shape Keys on `Operative_LOD0` (`value = 0.0`).
2. **IK <-> FK Seamless Pose Match (`morphrig.snap_ik_fk`)**:
   * Matches `CTRL_ik_hand_*` / `CTRL_ik_foot_*` world transforms to the current FK chain (or vice versa) and toggles the `ik_fk_*` switch on `CTRL_master` without visual popping.

---

## 5. Rebuilding & Exporting to FBX

To regenerate `source/Operative.blend` from source and export all FBX files:

```bash
blender -b --factory-startup --python-exit-code 1 -P source/generators/build_operative_blend.py
blender -b source/Operative.blend --python-exit-code 1 -P tools/export_and_bake.py
```
