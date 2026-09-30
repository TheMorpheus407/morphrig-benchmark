# Operative rig usage

`source/Operative.blend` is the animated production scene. `source/Character_Master.blend` is its reset character and rig source. All character mesh data, UVs, textures, rig fitting, weights and facial targets were authored procedurally for this project by `source/generators/character.py`. Meshes remain ordinary editable Blender mesh data. No runtime add-on is required.

Blender source units are metres, +Z up, −Y forward, anatomical left at +X. The neutral standing mesh spans ground Z=0 to Z=1.800. Objects retain identity transforms. The exporter transforms a temporary export copy of mesh data, shape keys, skeleton coordinates and bone-location curves from metres to centimetres, then writes FBX unit metadata. The editable source remains in metres. `root` is the only hierarchy root, independent from `pelvis`. Bones beginning `CTRL_` are animator helpers and must be omitted from the deformation-only FBX.

## Animator panel and reset

Open the embedded `rig_tools.py` text in Blender's Text Editor and choose **Run Script** once. The 3D View sidebar then has a **MorphRig** tab containing Reset, arm/leg matching, finger curl/spread, foot roll, heel/toe pivots, look blend, global scale and all face/corrective sliders. This explicit load avoids requiring Blender's automatic Python execution setting.

The equivalent console reset command is:

```python
exec(bpy.data.texts['rig_tools.py'].as_string())
reset_pose()
```

Reset detaches the active action without deleting it, clears bone offsets, resets IK/FK blends to FK, resets expression values and restores uniform scale 1. Choose the action again in the Action Editor to resume its playback. Source actions and their baked counterparts remain in the file.

## Body controls

The green/red deformation bones are directly keyable FK controls. Use `root` for ground movement, `pelvis` for body height and independent weight shifts, `spine_01`, `spine_02` and `chest` for torso articulation, and `neck` / `head` for gaze and acting. `global_scale` uniformly scales the whole armature including its mesh and all IK targets. For export, retain scale 1.

Choose **arm → IK** or **leg → IK** for either side in the panel. The command matches the hand/foot target and pole to the current pose before switching. Move `CTRL_hand_ik.L/R`, `CTRL_foot_ik.L/R`, `CTRL_elbow_pole.L/R` and `CTRL_knee_pole.L/R` in Pose Mode. IK targets include hand/foot orientation. Choose the corresponding FK button to preserve the solved pose in the directly keyable bones.

```python
match_switch('arm', 'L', True)   # preserve current pose and enter IK
match_switch('arm', 'L', False)  # preserve solved pose and return to FK
```

The foot control hierarchy uses real heel and toe pivot locations. Positive `foot_roll` rotates about the toe pivot; negative values rotate about the heel. Dedicated `heel_pivot` and `toe_pivot` sliders add adjustment. In IK mode the ankle target follows the pivot arc, and the foot bone follows target rotation. Set planted contact by moving the foot IK control; use the knee pole to keep the intended bend direction.

`finger_curl.L/R` adds a whole-hand grip through separate nondeforming finger controls. `finger_spread.L/R` fans the first phalanges. The `thumb/index/middle/ring/pinky.01/02/03.L/R` deformation bones remain individually keyable for contact refinement. The additive helper constraints default to zero, so they do not overwrite authored phalanx rotations. Local Z is the normal curl axis for the non-thumb fingers in this rest orientation; local X changes lateral splay.

`CTRL_look` sets a shared attention target when `look_at` is above zero. Set that blend to zero for independent eye direction using `eye.L` and `eye.R`. `jaw` and `tongue` remain independently articulated. Use either jaw bone motion or the `jaw_open` facial slider deliberately; stacking both at full strength exaggerates the result.

`shoulder_raise.L/R`, `hip_flex.L/R` and `wrist_flex.L/R` are editable corrective shape sliders. The animation authoring records suitable values for the demanding pose tests. They can be adjusted manually in the panel for new poses. Skin deformation uses normalized weights, at most two influences per vertex and linear blend skinning in both Blender and Unreal (Preserve Volume disabled). Hard accessories and the mechanical right sleeve/forearm use intentionally rigid bone weights; the organic sleeve, neck, forearm and fingers use blended joint rings. The ceramic shoulder cuffs have open ends and distal clearance to prevent closed cap surfaces cutting across the cloth in crossed-arm and recovery poses.

The short cable uses `cable.01` and `cable.02`. They can be directly keyed. `bake_secondary(start, end)` provides a deterministic damped response driven by pelvis motion at 30 Hz; it writes ordinary bone keyframes and does not require simulation at runtime.

## Face and speech

The facial mesh includes fitted eyelid and lip loops stitched into the skull, separate eyes/irises/pupils, upper and lower teeth, an interior mouth and tongue. All three LODs contain 33 source shape keys. The final Unreal import exposes the 32 intentionally nonempty targets. The source retains 33 shape keys, including reserved `wrist_flex.R` with zero authored delta on the rigid cybernetic forearm. That empty reserved target is intentionally omitted from the final Unreal import. All facial controls are included. Unreal replaces periods with underscores in both bone and morph names; the exact mapping is recorded in `skeleton_and_sockets.json`. The eyelids include protected globe recession during both blink and squint to prevent iris/globe intersections after linear export interpolation.

| Controls | Function |
| --- | --- |
| `blink.L/R`, `squint.L/R` | Independent full lid closure and restrained lid narrowing |
| `brow_up.L/R`, `brow_down.L/R` | Independent eyebrow and surrounding skin movement |
| `cheek.L/R`, `smile.L/R`, `frown.L/R` | Cheek response and independent mouth corners |
| `jaw_open`, `lip_close`, `mouth_wide`, `pucker`, `funnel` | General facial articulation |
| `viseme_AA` | Open vowel /ɑ, a/ |
| `viseme_EE` | Wide vowel /i, e/ |
| `viseme_OH` | Open rounded vowel /o, ɔ/ |
| `viseme_OO` | Narrow rounded vowel /u, w/ |
| `viseme_FV` | Lower lip toward upper teeth for /f, v/ |
| `viseme_MBP` | Closed lips for /m, b, p/ |
| `viseme_L`, `viseme_TH` | Tongue-to-teeth and interdental articulation |

Expression presets are `neutral`, `joy_confidence`, `anger`, `concern_sadness`, `surprise`, `pain`, and `focus`. Apply one with `expression('joy_confidence')`. Presets combine independent values and remain editable. The speech animation uses actual audio alignment plus overlapping visemes and authored gaze/gesture changes; `source/audio/dialogue_alignment.json` records the timing.

## Props, LODs and exporting

The cybernetic right forearm carries the wrist emitter, blade and removable cell. `emitter_muzzle`, `blade_base`, `blade_tip`, `cell` and `beacon` are deformation/socket bones. The cell and beacon have individually weighted geometry for explicit handoff animation. `export/Beacon.fbx` contains the exact beacon geometry in native beacon-bone local centimetres for persistent runtime deployment after release. `export_props.py` converts source bone-local `(x,y,z)` to native `(z,−x,y)` and preserves the two shared alloy/accent materials. The imported static mesh is checked vertex-by-vertex against the posed skeletal beacon, so release uses the socket transform at unit scale.

`Operative_LOD0`, `Operative_LOD1`, and `Operative_LOD2` share the skeleton and material order. Only LOD0 is visible by default. LOD1/2 use fewer authored loft/feature segments, retaining facial targets and skin weights. Their triangle counts are recorded in `material_and_lod_report.json`. Do not enable all three meshes at once for a beauty render.

Run the provided export-and-bake utility after modifying source actions. It selects the intended LOD and deformation skeleton and bakes constraints at 30 FPS. Do not export studio lights, the floor, cameras or animator helper bones as character geometry.

## Verification evidence

`docs/rig_validation.json` records the measured neutral bounds, one deformation root, zero loose vertices and numeric control tests. The maximum measured rest-pose IK/FK matching joint error was under 0.024 mm. The finger curl test moved the fingertip 105 mm, foot roll moved the ankle on a 78 mm pivot arc, and the scale test produced `(1.25, 1.25, 1.25)`. `docs/rig_validation/` contains actual neutral, isolated blink, jaw/open-vowel, lip-closure and asymmetric expression renders. Demanding body poses are separately supplied as editable `TEST__...` actions.
