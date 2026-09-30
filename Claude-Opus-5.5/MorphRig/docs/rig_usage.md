# MorphRig Operative – rig usage

File: `source/Operative.blend` (Blender 5.1.1, no add-ons required). Everything in it was produced by the
scripts in `source/generators/` (procedural source), but the file is a normal editable production file.

## Conventions
* Units metres, +Z up, the character faces **-Y**, character left = **+X**, ground origin at (0,0,0), height 1.80 m.
* Rest pose: A-pose (arms 45° down). Unreal receives centimetres: the exporter converts an in-memory copy to cm (all bone scales 1) – no import scaling.
* Two armatures:
  * **MR_Rig** – animator control rig (edit this). Actions `RIG_<clip>` hold the editable keys.
  * **MR_Skeleton** – export/deformation skeleton (96 bones: 85 bones + 11 non-deforming `sock_*` socket bones,
    single root `root` independent of `pelvis`). Every bone copies MR_Rig (COPY_TRANSFORMS), actions `SK_<clip>`
    are the baked results that are exported.
* Meshes are skinned to MR_Skeleton (max 4 influences). LOD1/LOD2 copies live in the hidden collections
  `MR_LOD1` / `MR_LOD2`.

## Tools panel (3D View ▸ Sidebar ▸ **MorphRig**)
Provided by the text block `morphrig_rig_ui.py` (registered on load if Python auto-run is trusted; otherwise
open it in the Text Editor and press *Run Script*, or install `tools/morphrig_rig_ui.py` as an add-on).
* **Reset Pose** – all controls back to rest, face properties 0, arm IK off (FK), leg IK on.
* **arm_l / arm_r / leg_l / leg_r: `FK = pose`, `IK = pose`** – pose matching: the chosen chain is snapped to the
  current pose and the `ik_fk` switch is set accordingly, so switching never pops.
* **Bake Active Action** – samples the active `RIG_<clip>` onto MR_Skeleton as `SK_<clip>` (keys every frame,
  markers and `mr_meta` copied).

## Controls (MR_Rig)
| Control | Purpose |
|---|---|
| `root` | world placement / root motion (dash clips); scale this bone for global scaling |
| `c_torso` | centre of gravity (moves hips + upper body, legs stay planted in IK) |
| `pelvis`, `spine_01..03`, `neck_01/02`, `head` | FK torso / neck / head |
| `c_look` | look-at target (eyes aim at it; eyelids follow gaze pitch) |
| `clavicle_l/r` | shoulder elevation / protraction |
| `c_upperarm_fk_*`, `c_lowerarm_fk_*`, `c_hand_fk_*` | FK arm |
| `c_hand_ik_*` (+ `ik_fk` property), `c_elbow_pole_*` | IK arm and elbow pole vector |
| `c_thigh_fk_*`, `c_calf_fk_*`, `c_foot_fk_*`, `c_ball_fk_*` | FK leg |
| `c_foot_ik_*` (+ `ik_fk`, `roll`), `c_ball_ik_*`, `c_knee_pole_*` | IK leg; `roll` < 0 rocks on the heel, 0–0.5 on the ball (pivot on the floor contact), > 0.5 on the toe tip; `c_ball_ik` bends the toes |
| `c_fingers_*` | finger master: rotate X = curl all fingers (thumb 55 %), Z = spread |
| `index/middle/ring/pinky/thumb_01..03_*`, `*_metacarpal_*` | individual finger phalanges for prop contact |
| `jaw`, `tongue_01..03` | jaw open / sideways (X / Z), tongue curl |
| `c_face` | face properties (see below) |
| `blade_r` | forearm blade: rotate Z 0 → -180° to deploy |
| `prop_cell` (`parent` 0 forearm cradle / 1 left hand) | removable power cell |
| `prop_beacon` (`parent` 0 belt holster / 1 left hand / 2 world) | deployable beacon |
| `hair_tail_01..04` | tied hair tail (secondary motion, see below) |

Twist bones (`upperarm_twist_01`, `lowerarm_twist_01`, `thigh_twist_01`) and eye / eyelid bones are driven
automatically.

## Face (`c_face` custom properties, 0..1)
* Bone driven: `blink_L/R`, `wide_L/R`, `squint_L/R` (drive `lid_upper/lower_*`; squint also drives the
  `eyeSquint_*` shape key). Lids follow gaze pitch from `c_look` automatically.
* Shape keys on `MR_Head` (same names as the Unreal morph targets): brows (`browInnerUp_L/R`, `browOuterUp_L/R`,
  `browDown_L/R`), eyes/cheeks (`eyeSquint_L/R`, `cheekRaise_L/R`, `cheekPuff`, `noseSneer_L/R`), mouth
  (`mouthSmile_L/R`, `mouthFrown_L/R`, `mouthStretch_L/R` = width, `mouthPucker`, `mouthFunnel`, `mouthPress`,
  `mouthRollUpper/Lower`, `mouthUpperUp_L/R`, `mouthLowerDown_L/R`, `mouthClose`, `mouthLeft/Right`).
* Teeth, gums and tongue: `MR_Mouth` (upper row on the head, lower row on the jaw, tongue on `tongue_01..03`).
* Expression presets (source of truth `source/generators/mr_face_list.py`): neutral, joy, anger, concern,
  surprise, pain, focus. The Unreal face panel exposes the same presets.

### Viseme controls (documented mapping, no proprietary standard)
Each viseme is a shape key; its jaw opening and tongue pose are added by the lip-sync generator
(`clip_dialogue.py`) from `VISEME_JAW_DEG` / `VISEME_TONGUE`.

| Viseme | Phonemes (IPA from eSpeak) | Mouth shape | Jaw ° | Tongue |
|---|---|---|---|---|
| `V_MBP` | p b m | lips pressed closed (full closure is forced on one frame per bilabial) | 0 | – |
| `V_FV` | f v | lower lip to upper teeth (labiodental) | 2 | – |
| `V_TH` | θ ð | slightly open, tongue between teeth | 5 | tip forward to teeth |
| `V_LNT` | t d n l ɾ | narrow, tongue tip up | 5.5 | tip to ridge |
| `V_SS` | s z | teeth near, lips stretched | 1.5 | raised |
| `V_CH` | ʃ ʒ tʃ dʒ | lips funnelled forward | 3.5 | raised |
| `V_KG` | k ɡ ŋ h x | open, back of tongue up | 7 | back up |
| `V_R` | ɹ r ɚ ɜ | rounded, slightly pursed | 5 | curled |
| `V_AA` | a ɑ æ ʌ ɐ | open vowel | 17 | – |
| `V_EH` | ɛ e ə | mid open | 11 | – |
| `V_EE` | i j ʲ | wide vowel (stretch + slight smile) | 6 | – |
| `V_IH` | ɪ ᵻ | mid wide | 8 | – |
| `V_OH` | ɒ ɔ o | rounded open | 12 | – |
| `V_OO` | u ʊ w | rounded vowel / pucker | 5 | – |

## Props and contacts
* Power cell: during `reload` the left hand grips the cell (`prop_cell.parent` 0 → 1), charges it on the belt's
  front-left charger pad and re-seats it (1 → 0). Hand/cell contact is exact because the cell is parented to the
  hand bone while held.
* Beacon: `deploy` grabs it from the back of the belt (`prop_beacon.parent` 0 → 1) and places it on the floor
  (→ 2, world). Unreal hides the skinned beacon at the `beacon_release` event and spawns `SM_Beacon` there.
* Blade: `blade_r` rotates the forearm blade out for `melee_*` (event `blade_out`).

## Secondary motion
The hair tail (`hair_tail_01..04`) is simulated deterministically per clip (`mr_secondary.py`: damped verlet
chain driven by the head, gravity, floor and head/neck/back capsule collisions, loops cross-faded) and baked
as ordinary keys of the rig action. Edit the keys directly, or rebuild the clip to re-simulate.

## Editing a clip
1. Select MR_Rig, pick `RIG_<clip>` in the Action editor, edit keys (the frame range and pose markers are
   the events exported to Unreal).
2. Press **Bake Active Action** (or re-run the pipeline for that clip:
   `python3 MorphRig/tools/export_and_bake.py --from anims --only <clip>` which re-authors from the generator).
3. Export with `python3 MorphRig/tools/export_and_bake.py --from export --only <clip>` and re-import in Unreal
   (`MR_STAGE=anims MR_ONLY=<clip>` for `unreal/Scripts/import_operative.py`).

Note: re-running the generator stage rebuilds clips from their procedural source; manual key edits should be
baked with the panel and exported without re-running `--from anims`.

## Deformation demonstration
The extra action `RIG_demo_deformation` shows overhead reach, deep squat, crossed-arm reach, large torso twist,
kneeling, planted hand support and closed grip (markers name each pose).
