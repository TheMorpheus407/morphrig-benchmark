# Rig usage guide - RIG_Operative

`source/Operative.blend` (Blender 5.1) contains the animator control rig, the deformation skeleton that is
exported, the skinned character at three LODs and all 96 clips as editable actions plus their baked versions.

## 1. What is in the file

| Datablock | Purpose |
|---|---|
| `RIG_Operative` (armature, collection *Rig*) | the rig you animate. 191 bones: controls + mechanism |
| `SKEL_Operative` (armature, collection *Export*, hidden) | 84 deformation bones, one `root`. Every bone copies the world transform of the rig bone with the same name (constraint `RIG`). This is the skeleton in every FBX |
| `Operative_LOD0` / `_LOD1` / `_LOD2` (collection *Character*) | the skinned mesh, 6 material slots, 32 face shape keys on every LOD (driven by the rig) |
| `MorphProxy` (collection *Export*, hidden) | three-vertex helper mesh that carries the baked morph curves inside each animation FBX |
| actions `<clip id>` | editable source animation on `RIG_Operative` (96) |
| actions `BAKED_<clip id>` and `BAKED_<clip id>.morph` | baked result on `SKEL_Operative` / shape key values (what was exported) |
| actions `DEMO_<name>` | one-frame deformation test poses |
| text `morphrig_ui.py` | the rig UI (sidebar tab **MorphRig**) |

The rig itself needs no Python: all drivers are simple expressions. Only the UI panel is a script - allow
*Auto Run Python Scripts* when opening the file (or press *Run Script* on `morphrig_ui.py` once).

Units are metres, +Z up, the character faces -Y, its left is +X, the floor is z = 0 and the origin lies between
the feet. The rest pose is an A-pose, height 1.80 m.

## 2. Controls

Bone collections (Armature properties > Bone Collections): **Root, Torso, Arm IK, Arm FK, Leg IK, Leg FK, Fingers,
Face, Props, Secondary**; *MCH* (mechanism) is hidden. All controls use quaternion rotation.

| Control | Does |
|---|---|
| `root` | moves / turns / scales the whole character. Root motion clips key it; in-place clips leave it at the origin. Its scale is the **global scale** (panel: *Global Scale*, 0.5x / 1x / 2x buttons) |
| `cog` | centre of gravity: pelvis position and whole-torso lean. Property `breath` (-1..1) adds chest expansion under the spine controls |
| `hips` | rotates the pelvis without moving the spine |
| `spine_01`, `spine_02`, `spine_03`, `neck_01`, `head` | FK torso chain |
| `clavicle_l/r` | shoulder girdle (shrug, protraction) |
| `upperarm_fk`, `lowerarm_fk`, `hand_fk` `_l/_r` | FK arm |
| `hand_ik_l/r`, `elbow_pole_l/r` | IK arm (hand control lives in root space). Property `arm_ik` on `hand_ik` blends FK (0) to IK (1) |
| `fingers_l/r` | properties `curl_thumb`, `curl_index`, `curl_middle`, `curl_ring`, `curl_pinky`, `spread`, `fist` (0..1). The individual finger bones (`index_01_l` ...) can be rotated on top |
| `foot_ik_l/r`, `knee_pole_l/r` | IK leg, default. Properties on `foot_ik`: `leg_ik` (FK 0 .. IK 1), `roll` (-1 heel .. 0 flat .. 1 ball .. 2 toe tip), `bank` (inner/outer edge), `heel_pivot`, `toe_pivot` (yaw around heel / toe tip, radians), `toe_bend` (extra toe flex, 45 degrees per unit) |
| `thigh_fk`, `calf_fk`, `foot_fk`, `toe_fk` `_l/_r` | FK leg |
| `look_target`, `eye_target_l/r` | the eyes aim at their targets (`eye_target_*` are children of `look_target`; move one of them for cross-eyed / independent looks). Properties on `face`: `eyes_track`, `head_track` (the head turns to the target), `lid_follow` (eyelids follow the eyeball pitch) |
| `face` (box above the head) | all face channels as properties, see section 3 |
| `jaw`, `tongue_01`, `tongue_02`, `eye_l/r`, `lid_upper_l/r`, `lid_lower_l/r` | direct FK on top of the property driven motion |
| `blade_l` | forearm blade: local Y location 0 .. 0.17 m extends it (panel: *Blade extend*) |
| `prop_cell`, `prop_cell_spare`, `prop_beacon` | prop carriers. Rest parents: emitter forearm / belt / belt. Properties `hold_hand_l`, `hold_hand_r` (0/1) attach the prop to the grip bone `HOLD_<prop>_<hand>`; move the HOLD bone to set the grip. With both at 0 the prop bone can be keyed freely relative to its rest parent |
| `cable_01` .. `cable_04` | data cable at the back of the head (secondary motion, section 5) |

### IK / FK switching with snapping

Panel **Arms and Legs**: per limb a `FK <> IK` slider and two buttons.

* **Snap to IK** - the IK control and the pole are moved onto the current pose, then the limb switches to IK.
* **Snap to FK** - the FK controls take over the current (IK solved) pose, then the limb switches to FK.

The pose does not change (measured on clip poses: below 0.1 mm and 0.1 degrees on the arms; on the legs the joint
positions are exact, the foot is within 0.1 degrees and the toe joint within 0.7 degrees; foot roll / bank / pivot
values are folded into the control transform when snapping to IK and the remaining toe angle goes to `toe_bend`). With auto-keying enabled the buttons key the
affected controls and the switch property on the current frame.

### Reset

Panel button **Reset Pose** returns every control to the rest pose and every property to its default
(**Selected** does the same for the selected bones only). The showcase application has the same function
(`Backspace`, `mr reset`).

## 3. Face

Channels are 0..1 properties on the `face` control (panel **Face**):

* 32 shape-key channels: `brow_inner_up_l/r`, `brow_outer_up_l/r`, `brow_down_l/r`, `squint_l/r`, `cheek_raise_l/r`,
  `cheek_puff_l/r`, `nose_sneer_l/r`, `smile_l/r`, `frown_l/r`, `mouth_wide_l/r`, `upper_lip_up_l/r`,
  `lower_lip_down_l/r`, `pucker`, `funnel`, `lip_press`, `mouth_close`, `lip_roll_upper`, `lip_roll_lower`,
  `labiodental`, `chin_raise`;
* bone channels: `jaw_open`, `jaw_left`, `jaw_right`, `jaw_forward`, `blink_l/r`, `eye_wide_l/r`, `squint_l/r`
  (lids), `tongue_up`, `tongue_out`;
* presets `expr_joy`, `expr_anger`, `expr_concern`, `expr_surprise`, `expr_pain`, `expr_focus` (neutral = all 0);
* visemes `vis_PP`, `vis_FF`, `vis_TH`, `vis_DD`, `vis_KK`, `vis_CH`, `vis_SS`, `vis_RR`, `vis_AA`, `vis_EH`,
  `vis_EE`, `vis_OH`, `vis_OO`.

Final channel value = clamp01(direct value + sum(viseme x weight) + sum(preset x weight)). Left and right
channels are independent, so asymmetric expressions are made by keying one side. The exact weights, bone
amounts and the Unreal conversions are in `docs/face_controls.json`.

| Viseme | Sounds | Main shape |
|---|---|---|
| `PP` | p b m | lips pressed, jaw closed |
| `FF` | f v | lower lip to the upper teeth |
| `TH` | th (thin, the) | tongue tip between the teeth |
| `DD` | t d n l | tongue up, small opening |
| `KK` | k g ng h | open, tongue back |
| `CH` | sh zh ch j | funnel with slight pucker |
| `SS` | s z | narrow, wide lips, teeth close |
| `RR` | r er | light pucker |
| `AA` | a (father, back) | jaw open wide |
| `EH` | e, schwa | medium opening, slightly wide |
| `EE` | ee, i, y | wide lips, small opening |
| `OH` | o, aw | rounded, open |
| `OO` | oo, w | tight pucker |

The speech clip `dialogue` keys the visemes per frame from `source/audio/dialogue_alignment.json` (phoneme
timings of the actual audio; the IPA to viseme table is the `viseme_map` in that file) and layers brows, lids,
presets, gaze and blinks on top.

## 4. Corrective helpers and twist bones

These deformation bones are procedural (constraints in the rig, baked into every clip, recomputed at runtime
in Unreal from the same rules, see `procedural_bones` in `docs/skeleton_and_sockets.json`):

| Bones | Rule | Purpose |
|---|---|---|
| `upperarm_twist_l/r`, `thigh_twist_l/r` | follow the limb swing but not its twist | no candy-wrapper at shoulder / hip |
| `lowerarm_twist_l/r` | take the twist of the hand | forearm pronation spreads along the forearm |
| `shoulder_helper`, `elbow_helper`, `hip_helper`, `knee_helper` `_l/_r` | half of the child joint rotation | keep volume on the outside of bent joints, carry the pauldron / knee pads / tasset |

Deformation test poses (panel **Deformation test poses**, actions `DEMO_*`): overhead reach, deep squat,
crossed arm reach, torso twist, kneeling, hand support, closed grip.

## 5. Secondary motion

The data cable has four FK controls. **Bake Cable** (panel, or `mr.secondary.bake_cable`) simulates it for the
action that is assigned to the rig (damped chain following the head, collision with head / neck / back / floor)
and keys the four controls on every frame; loops are simulated until periodic. Delete those keys to animate the
cable by hand or re-run the bake after changing the body animation. All 96 delivered clips were baked this way.
In Unreal the cable is either played from the clip or simulated live (showcase switch *cable simulation*).

## 6. Working with the clips

* Assign a source action (named exactly like the clip id, e.g. `reload`) to `RIG_Operative`. Scene rate is 30 fps;
  frame 0 is the first frame, loops repeat frame 0 on their last frame.
* 52 clips are sparse pose keys with auto-clamped Bezier interpolation. The other 44 (`"source_keys": "dense"` in
  the manifest: generated gait cycles, start / stop / pivots / dashes, floor-contact clips, the emotes and the
  dialogue) were solved per frame (contacts, layers) and are stored with linear interpolation; keys that the
  interpolation reproduces within 0.1 mm / 0.02 degrees were removed. Edit them with the graph editor (or
  re-author them in the generator, section 7).
* Event markers are pose markers of the source action (see "Re-bake and export after an edit").
* Custom properties of an action: `loop` (bool), `clip_form`.
* `SKEL_Operative` follows the rig while its custom property `follow_rig` is 1 (constraints `RIG` unmuted). To
  look at a baked action, mute them (`mr.rig.set_follow(skel, False)`) and assign `BAKED_<id>`.

### Re-bake and export after an edit

```sh
# all clips that exist as actions in the file (or a subset with --clips a,b,c)
blender -b source/Operative.blend -P tools/export_and_bake.py -- --from-blend --clips reload,walk_f
```

This samples the edited source actions on the deformation skeleton, replaces `BAKED_<id>` (+ `.morph`),
rewrites `export/animations/<id>.fbx` and updates frame counts and event markers in
`docs/animation_manifest.json`. Event markers are the **pose markers of the source action** (Dope Sheet >
Action Editor > Marker, "Show Pose Markers"): move, rename, add or delete them there. Then re-import in Unreal
with `tools/ue_import.sh`.

## 7. Regenerating everything

The character, rig, textures and clips are generated by `source/generators` (procedural source; nothing in the
.blend was edited interactively):

```sh
blender -b --factory-startup -P tools/export_and_bake.py            # full build, about 8 minutes
blender -b --factory-startup -P tools/export_and_bake.py -- --reuse-textures
```

A full build overwrites `source/Operative.blend`; keep interactive edits in a copy or move them into the
generator modules (`mr/anim_*.py` for clips, `mr/rig.py` for the rig).

| Module | Content |
|---|---|
| `mr/skel.py` | joints, deformation bones, sockets |
| `mr/body.py`, `hand.py`, `head.py`, `hair.py`, `outfit.py`, `cyber.py` | geometry |
| `mr/faceshapes.py`, `facedefs.py` | face shape keys, controls, visemes, presets |
| `mr/uvtools.py`, `texgen.py`, `materials.py`, `lod.py` | UVs, textures, materials, LODs |
| `mr/rig.py`, `rigui.py`, `secondary.py` | control rig, UI, cable simulation |
| `mr/clips.py`, `anim_base.py`, `anim_move.py`, `anim_combat.py`, `anim_react.py`, `anim_social.py`, `gait.py` | clip table and authored animation |
| `mr/bake.py`, `export.py`, `docsgen.py` | baking, FBX export, data documents |
| `dialogue_audio.py` | speech synthesis + alignment |
