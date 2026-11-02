# MORPHRIG — Rig usage

The Operative lives in `source/Operative.blend`. It contains one armature
(`Operative_Rig`) that carries **two** bone layers in the same rig:

* the **deformation skeleton** (71 deform bones) that actually skinds the mesh
  and that is exported to Unreal,
* the **animator control rig** (36 `CTRL_*` bones) that an animator drives.

The control rig is fully live inside Blender. Unreal does not need it: every
delivered clip is baked onto the deformation skeleton, so the exported
animation plays back exactly as authored (see `docs/animation_state_contract.md`).

---

## 1. Coordinate system and scale

| Property | Value |
|---|---|
| Units | metres (Blender), centimetres (Unreal) |
| Forward | **-Y** in Blender, **+X** in Unreal |
| Up | **+Z** in both |
| Right | **+X** in Blender, **+Y** in Unreal |
| Character height | 1.80 m, feet on Z = 0 |
| Neutral pose | ground origin, arms down, feet flat |

The FBX is written with `axis_forward='-Z'`, `axis_up='Y'` and
`global_scale=100.0`, so the Unreal importer converts the scene itself. The
character measures 180 cm in Unreal with **no** import scale repair.

## 2. Root and pelvis separation

There is exactly **one** root bone, `root`. It is independent from `pelvis`:

```
root
└── pelvis
    └── spine_01 → spine_02 → spine_03 → chest
                    ├── neck_01 → head
                    ├── clavicle_r → upperarm_r → lowerarm_r → hand_r → fingers
                    └── clavicle_l → upperarm_l → lowerarm_l → hand_l → fingers
```

* `root` carries the root motion. The four dash clips translate it by a
  nominal 2 m; every other clip keeps it at the origin.
* `pelvis` carries the body weight shift, hip rotation and the stance.

## 3. Control rig

All controls are `CTRL_*` pose bones. Their constraint influence defaults to
`0.0`, so the rig plays back the baked clips untouched until an animator
raises the influence of the controls they want to use.

| Control | Drives | Constraint |
|---|---|---|
| `CTRL_root` | `root` | Copy Rotation |
| `CTRL_pelvis` | `pelvis` | Copy Rotation |
| `CTRL_torso` | `spine_01` | Copy Rotation |
| `CTRL_neck` | `neck_01` | Copy Rotation |
| `CTRL_lookat` | `head` | Damped Track (TRACK_Y) |
| `CTRL_hand_r/l` | `lowerarm_r/l` | IK, 2 bone chain, pole target `CTRL_elbow_*` |
| `CTRL_elbow_r/l` | – | pole target of the arm IK |
| `CTRL_foot_r/l` | `calf_r/l` | IK, 2 bone chain, pole target `CTRL_knee_*` |
| `CTRL_knee_r/l` | – | pole target of the leg IK |
| `CTRL_heel_r/l` | `heel_r/l` | Copy Rotation (heel pivot) |
| `CTRL_ball_r/l` | `ball_r/l` | Copy Rotation (toe pivot) |
| `CTRL_curl_r/l` | – | drives the whole hand curl |
| `CTRL_spread_r/l` | – | drives the finger spread |
| `CTRL_thumb/index/middle/ring/pinky_r/l` | `finger_<name>_01..03_*` | Copy Rotation per segment (individual finger control) |
| `CTRL_scale` | – | global uniform scale driver on `root` |

### How to use the rig

1. Select the control, press `R`/`G` and raise the **influence** of the
   matching constraint to 1.0 (in the bone's *Constraints* tab) before
   posing, otherwise the constraint will fight your manual edit.
2. **IK / FK**: the arm and leg chains are IK driven. To work in FK, set the
   IK influence to 0 and pose `upperarm_*`, `lowerarm_*`, `thigh_*`, `calf_*`
   directly.
3. **Pole vectors**: `CTRL_elbow_*` and `CTRL_knee_*` are the pole targets.
   Slide them around the limb to change the bend direction without moving the
   end effector.
4. **Pose matching**: the baked clips all start from the same stance, so any
   clip can be used as the match pose. The exported clips carry the whole
   body, so an animator who wants a different entry pose re-bakes the clip
   (see §6).
5. **Foot roll**: `CTRL_heel_*` and `CTRL_ball_*` are independent pivots. The
   heel pivot rolls the foot around the ankle, the ball pivot rolls it around
   the toe joint, so a foot roll can be split between heel strike and toe
   off.
6. **Finger curl / spread / individual**: `CTRL_curl_*` bends all fingers of
   one hand, `CTRL_spread_*` fans them apart, and the five per-finger
   controls bend a single digit segment by segment.
7. **Look at**: `CTRL_lookat` drives the head through a damped track. The
   eyes are driven separately by the `eye_r` / `eye_l` deform bones.
8. **Global scale**: the custom property `global_scale` on the armature
   object (0.1 … 3.0) drives a uniform scale on `root`.
9. **Resettable rest pose**: `source/generators/mr_anim.py::reset_pose` puts
   every deform bone back to its rest transform. The bake pipeline calls it
   before every clip, so no clip inherits leftovers from the previous one.
10. **Secondary motion**: the shoulder cables (`cable_01` … `cable_03`) are
    not posed directly. Their motion is derived from the arm chain by the
    rig generator, so they follow the shoulder and lag behind it.

## 4. Face rig

The face is a shape key rig on `Operative_Body`. 29 shape keys besides
`Basis` are exposed; each one is a 0 … 1 slider.

### Lips and mouth

| Shape key | Effect |
|---|---|
| `lip_close` | full lip closure |
| `lip_smile` | corners up and back |
| `lip_frown` | corners down |
| `lip_wide` | mouth stretched wide |
| `lip_narrow` | mouth narrowed |
| `lip_pucker` | lips pushed forward |
| `lip_funnel` | lips formed into an O |
| `jaw_open` | jaw dropped, mouth open |
| `jaw_open_small` | slight jaw drop |

### Cheeks, brows, eyes

| Shape key | Effect |
|---|---|
| `cheek_raise_l` / `cheek_raise_r` | cheek raise, independent per side |
| `brow_up_l` / `brow_up_r` | brow raised, independent per side |
| `brow_down_l` / `brow_down_r` | brow lowered (frown), independent per side |
| `eye_r` / `eye_l` | eyeball rotation (look at), independent per side |
| `eyelid_upper_r/l`, `eyelid_lower_r/l` | eyelid closure |
| `jaw` | jaw rotation |

The brow itself is painted into the face atlas, so it follows the skull
exactly. The brow shape keys move the skin of the brow ridge and the paint
travels with it. In addition the `brow_l` / `brow_r` bones pivot inside the
skull and carry a skin weight on the brow ridge, so the brow can also be
lifted by rotating those bones.

### Visemes

`vis_sil`, `vis_mb`, `vis_eh`, `vis_ee`, `vis_oo`, `vis_ff`, `vis_th`,
`vis_l` — eight mouth shapes that cover the phoneme classes of the
delivered line.

### Expression presets

Six presets, each a single slider that mixes the underlying shapes:
`expr_joy`, `expr_anger`, `expr_concern`, `expr_surprise`, `expr_pain`,
`expr_focus`. The neutral face is the rest state (all sliders at 0).

### Blinking

`eyelid_upper_r/l` and `eyelid_lower_r/l` are separate, so the left and the
right eye can blink independently; the delivered `blink_*` clips and the
`blink_in` / `blink_out` performance use this.

## 5. Skinning

* Weights are generated automatically by `source/generators/mr_skin.py` from
  the proximity of each vertex to the bone chain — there is no hand painted
  weight map in the delivery.
* Every vertex is bound to at most 8 bones.
* The finger segments 2 and 3 are real, separate bones, and the finger
  geometry is generated from the same `mr_rig.finger_joints()` function that
  creates the bones, so mesh and rig always line up.

## 6. Re-authoring clips

Clips are authored in `source/generators/mr_clips.py`. Each clip is a
function that receives a normalised time `t` in 0 … 1 and returns a `Pose`.
The pose is described in **authoring intent** (bone name → world or local
rotation), so the order in which the bones are written does not matter.

```python
@clip("wave", 45, form="one_shot", markers=[("wave_start", 1), ("wave_end", 45)])
def wave(t, rig):
    p = Pose(rig)
    stance(p)
    p.arm(1, pitch=-35.0, elbow=25.0)
    breathe(p, t, amount=0.6)
    return p
```

Bake and export afterwards:

```bash
blender -b --factory-startup -P source/generators/build_animations.py -- --out source/Operative.blend
blender -b --factory-startup -P source/generators/export_fbx.py
```

`source/generators/validate_pose.py` compares every authored pose against
Blender's own evaluation of the rig and reports any mismatch. It currently
reports **0 errors over 71 poses in 15 clips**.
