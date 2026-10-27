# Operative rig usage

## Open the source

Open `source/Operative.blend` in the installed Blender. No paid add-on, downloaded body/head, linked character library, or external motion set is required. The character, costume, props, UVs, skin weights, face shapes and motion were generated specifically for this assignment; the generators are in `source/generators/`.

Source units are **meters**, with `scale_length = 1.0`. Z is up, the neutral character faces **-Y**, anatomical left is +X, and the root is at the ground origin. The highest normal hair point is 1.80 m. Source timing is **30 FPS** with inclusive frame ranges. Unreal uses centimeters; see `skeleton_and_sockets.json` for the audited axis conversion and sockets.

All texture images are packed in the `.blend` and also supplied as editable PNG files in `source/textures/`. There are three body LOD meshes, a shared face/morph mesh and shared equipped props. LOD1/2 collections are hidden initially; unhide the desired collection and hide the others to inspect them. Do not export all three LOD collections as one character.

## Enable the animator panel

The `.blend` contains the finished asset; running a generator is not necessary to use it. In a Text Editor, select the embedded `START_HERE_Rig_Controls.py` and choose **Run Script** (Alt-P). In the 3D View, open the N sidebar and the **MorphRig** tab. Automatic script execution is not required, and a security prompt to enable scripts globally can be declined.

The same readable source is `source/generators/rig_controls.py`. Its operators can also be called from Blender's Python console, for example:

```python
bpy.ops.operative.reset_pose()
bpy.ops.operative.select_clip()
bpy.ops.operative.bake_range()
```

## Two-skeleton workflow

- `Operative_CTRL` is the editable animator skeleton. It has ordinary FK bones, `CTRL_hand.L/R`, `CTRL_foot.L/R`, elbow/knee pole controls, heel/toe pivots and `CTRL_look`.
- `Operative_DEF` is the connected, 70-bone export hierarchy. `root` is its only parentless bone and is independent of `pelvis`. Copy Transforms constraints carry the evaluated control pose, including IK, into this skeleton.
- `Operative_Body_LOD0/1/2`, `Operative_Face`, and `Operative_Props` are skinned to `Operative_DEF`. Hard accessories have intentional rigid weights; organic joints use blended weights and volume preservation. The maximum source influence count is three.

Use `Operative_CTRL` for normal posing and source animation. To inspect or edit a baked action directly, select `Operative_DEF` and temporarily set its Copy Transforms constraint influences to zero. Restore them before returning to the control-driven view.

`Reset Operative Pose` detaches the active playback actions without deleting them, resets transforms, facial values, IK settings and global scale, and restores the ground-origin neutral. It does not delete source curves or baked actions. Scale `Operative_CTRL` at the object level for an obvious global-scale change; the deformation skeleton follows. Use the same reset command to restore scale.

## Select and edit motion

Enter an ID in **Clip ID**, then choose **Select / Play Clip**. All 96 IDs from `docs/animation_manifest.json` are present. The command selects:

- `SOURCE_<id>` on `Operative_CTRL`: editable control-skeleton curves;
- `<id>` on `Operative_DEF`: the baked deformation action;
- `<id>_FACE` on the face shape-key data: facial curves for that clip.

The action ranges and event definitions match the manifest. In this Blender version, event markers are stored as each action's structured `event_markers` property. Selecting a clip mirrors those definitions onto the scene timeline with their exact frame numbers. Static poses have one sample at frame zero. Loop samples repeat their first pose at the last inclusive frame.

Edit the source action's curves, or detach the action and pose/keyframe the controls. **Bake Current Range** evaluates the control rig over the current scene frame range and keys the resulting local transforms into the selected deformation action. It preserves the editable source action and does not regenerate the mesh or other clips. Save the `.blend` after rebaking. To update export files afterward:

```sh
blender -b source/Operative.blend --python-exit-code 1 \
  -P tools/export_and_bake.py -- --animations-only
```

The exporter disables control-constraint evaluation and exports the baked deformation channels. It resets only its temporary export pose, not the saved source pose. A temporary export skeleton converts every rest matrix exactly once to centimeters with the same parents; bone-location curves and mesh-object scale are converted explicitly. These changes are not saved to the meter-based `.blend`.

Mesh export joins temporary copies of the body, face and props into one skinned mesh per LOD and verifies that all facial shapes survive the join. Original source parts remain separate and editable. The eleven static poses keep one source key; an identical export-only next-frame key lets Unreal import and hold them without treating them as motion clips.

## IK, poles, contacts and fingers

The `ik_arm_L/R` and `ik_leg_L/R` properties blend between FK and a two-bone IK chain without stretch. Use **Match FK to IK** before enabling IK, and **Match IK to FK** before returning to FK. The matching commands preserve the evaluated end pose and place the pole controls near the current joint.

- Move `CTRL_hand.L/R` for wrist targets and `CTRL_elbow.L/R` for elbow poles.
- Move `CTRL_foot.L/R` for planted-foot targets and `CTRL_knee.L/R` for knee poles.
- Set `foot_roll_L/R` and choose **Apply Heel / Toe Roll**. Positive roll uses the toe pivot; negative roll uses the heel pivot. The command enables/matches leg IK when necessary.
- `CTRL_heel.L/R` and `CTRL_toe_pivot.L/R` expose the physical pivot locations. Keep planted targets on the contact surface and rebake the desired range.

Each hand has curl properties for thumb, index, middle, ring and little finger, plus spread. **Apply Curl / Spread** applies them to all three phalanges. Individual `thumb_01..03`, `index_01..03`, `middle_01..03`, `ring_01..03` and `pinky_01..03` bones remain available for contact corrections. Source animation may override a manual change when playback advances; key the change or detach the playback action first.

The neck/head can be posed normally. `CTRL_look` and `look_at_weight` provide the head look-at control. `eye.L` and `eye.R` are separate bones for independent gaze. A three-bone cable provides bounded, bakeable secondary motion; it does not require a runtime simulation plug-in.

## Prop contacts

The `cell` and `beacon` bones carry authored contact trajectories. `SOURCE_reload` manipulates the cell with the left hand and seats it again; `SOURCE_deploy` lowers the beacon to the floor and leaves it there through the end of the action. Edit these bone curves together with the hand and individual finger controls, then rebake the selected range. Do not substitute a marker-only attachment change for the actual hand/object contact. In Unreal, `DeployRelease` retains the beacon at its evaluated world transform as an independent static mesh exported from the same authored beacon vertices; reset, respawn or a new deployment restores the stowed prop.

## Face and speech

The `Operative_Face` mesh has 26 editable shapes plus Basis:

- `JawOpen`, `LipClosed`, `MouthWidth`, `Pucker`, `Funnel`;
- independent `Blink.L/R`, `Squint.L/R`, `BrowRaise.L/R`, `BrowLower.L/R`, `Cheek.L/R`;
- independent `Smile.L/R` and `Frown.L/R`;
- `Viseme_MBP`, `Viseme_FV`, `Viseme_AA`, `Viseme_EE`, `Viseme_OO`, `Viseme_TH`, `Viseme_CH`.

The panel exposes the shapes individually and seven buttons: neutral, joy/confidence, anger, concern/sadness, surprise, pain and focus. The jaw bone, lower teeth and tongue are also articulated. Authored speech primarily uses facial shapes; avoid unintentionally doubling jaw rotation and `JawOpen` unless that combination is desired. Eyelid skin covers the eye during a full blink while the eyeball remains independently articulated.

The viseme mapping is authored for this project, not a proprietary standard:

| Control | Meaning |
|---|---|
| MBP | Lip closure for m/b/p |
| FV | Labiodental contact for f/v |
| AA | Open vowel with jaw opening |
| EE | Wide vowel and increased mouth width |
| OO | Rounded vowel/funnel and pucker |
| TH | Tongue-to-teeth shape |
| CH | Postalveolar consonant/lip shape |

`source/audio/dialogue.wav` is an original 15.2-second assembled synthetic English performance. `dialogue.txt` is its transcript and `dialogue_alignment.json` contains measured word intervals and authored phoneme/viseme intervals. The `dialogue` action includes the corresponding lip shapes, independent gaze, blinks, focus-to-concern-to-confidence acting and hand/body gestures. It is not jaw flapping alone.

## Material variants and deformation checks

`Operative_CTRL["Team"]` selects cyan or amber accents in the Blender material. Unreal additionally supplies **I/II** text identification so the team distinction is not color-only. Mesh and skeleton do not change.

Useful poses for checking deformation include `victory` for overhead reach, `deploy` for a deep squat, `cast_self` for crossed arms, `melee_2` for torso twist, `getup_front/back` for kneeling and planted support, and `reload` for a closed grip and cell contact. `tools/render_motion_checks.py` renders representative checks. `tools/check_motion.py` tests analytic endpoint/root behavior, and `tools/validate_source.py` reopens and evaluates all saved actions, weights, UVs, loops and death/dead matching. Both include standing rest-space assertions to prevent posed/rest coordinate mix-ups.
