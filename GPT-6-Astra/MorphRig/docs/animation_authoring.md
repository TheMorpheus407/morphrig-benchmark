# Animation source and timing

The 96 required entries are individually authored by `source/generators/animations.py`. The script constructs contact trajectories, anticipation/action/recovery poses, anatomically constrained two-bone limb solutions, finger articulation and acting beats for this Operative's dimensions. It uses no downloaded animation data. Every inventory ID has an editable `EDIT__<id>` action, a sampled deformation action named exactly `<id>`, and a facial Key action `FACE__<id>`. The animator may directly edit the FK curves or match them into the character's IK controls.

The scene and all actions use 30 samples per second, metres, +Z up and -Y forward. Anatomical left is +X. Root is independent of pelvis. Ordinary locomotion keeps root translation at zero; the controller supplies travel. Dash root translations are exactly two metres with eased acceleration/deceleration. Blink records anticipation/settle and a teleport event, with no baked translation. Loop clips include a duplicate final sample; runtime phase wraps over `[first,last)`.

Walk, run and sprint use separate stance fractions, swing clearances, pelvis motion, torso lean and arm patterns. The eight directions preserve torso facing and trace foot paths along the requested travel direction; lateral gaits use staggered fore/aft foot lanes. A planted foot's backward velocity is tied to 1.5, 4.0 or 6.5 metres per second. Runtime playback should scale to controller speed and blend neighbouring directions, keeping facing independent. Turn/pivot yaw is authored in pelvis with explicit stepping foot rotations; the host updates facing on completion.

The aim grid uses yaw -60/0/+60 degrees and pitch -35/0/+35 degrees. Negative yaw is character-left; positive pitch is up. Samples hold lower-body contact, with yaw divided between chest, head and the emitter arm. Apply above the pelvis. Directional hit clips are upper-body additive deltas relative to the neutral authored pose; do not replace lower-body travel with them.

Reload includes left-hand extraction and seating of the removable emitter cell, with evaluated cell-bone transforms. Deploy uses one shared upright beacon/left-hand trajectory from hip carry through a deep kneeling placement. A clearance arc brings the hand over the carry box, the palm faces its rear surface with curled fingers and an opposing thumb on the upper rim, and a raised withdrawal clears the box after release. The prop reaches an exact floor transform before the release marker, then stays fixed while the hand opens and rises. The blade retracts before floor poses; floor hand orientation and a minimum knee clearance keep fingers, weapon and knees above the floor during transitions. Explicit markers identify grip, extraction, insertion, release and activation. A runtime integration can use these already-baked prop-bone transforms or carry out equivalent socket attachment at the markers, but must never apply both.

The spoken performance uses the delivered WAV's actual eSpeak phoneme timing, with 45 ms coarticulation anticipation and 55 ms release. The transcript transitions from concern into focus around six seconds and confidence late in the line. Facial curves include alternating blinks, brow asymmetry, smiles, gaze changes and phoneme-driven articulation; body hand gestures emphasize reassurance and direction. `facial_animation_curves.json` records the same sampled values for deterministic runtime use if an importer does not retain FBX morph curves.

Source generator and export commands:

```sh
blender -b source/Character_Master.blend -P tools/build_animations.py
blender -b source/Operative.blend -P tools/export_and_bake.py
```

`animation_manifest.json` is the authoritative inventory map and event timing contract. `animation_validation.json` records source timing and root displacement measurements. Static poses contain two identical samples for robust FBX import. Additional `TEST__` poses are rig deformation checks and do not count towards the 96 entries.

## Edit, rebake, export

Open `source/Operative.blend`, select the armature and the desired `EDIT__<id>` source action. FK quaternion curves are directly editable. To animate with IK, use the embedded `rig_tools` pose-matching helper before switching `arm_ik.L/R` or `leg_ik.L/R`; key the target, pole, heel/toe and switch properties in this source action. The source remains editable after baking.

Bake the evaluated controls to the named deformation action before exporting:

```sh
blender -b source/Operative.blend -P tools/rebake_action.py -- --clip reload
blender -b source/Operative.blend -P tools/export_and_bake.py
```

Use `--all` instead of `--clip reload` to bake the entire library. The bake samples live constraints and controller curves at every authored 30 FPS sample, writes resolved local transforms for the deformation skeleton, preserves source actions and restores the user's constraint settings. Export disables constraints only while exporting those resolved actions, preventing a second IK solve. Facial `FACE__<id>` curves are editable on the mesh's shape-key datablock and are sampled directly into FBX.

## Export units and import comparison

The Blender production source remains in metres at object scale one. For FBX only, `prepare_centimeter_export()` converts the in-memory skeleton rest coordinates, mesh vertices, every shape-key coordinate, and **all bone location curves** by 100, then declares a 0.01-metre scene unit. FBX therefore stores centimetre coordinates with identity armature transforms. This avoids loss of animated translation when Unreal strips Blender's armature object; applying the conversion only to the dash root would leave pelvis and prop motion incorrect. The source file is never saved by the exporter. Full and `--mesh-only` exports also rebuild `export/Beacon.fbx` from the saved Operative mesh. The static replacement uses explicit centimetres, the native beacon socket basis and the same alloy/emissive material slots; `--clips-only` leaves that static asset unchanged.

`docs/blender_pose_samples.json` contains evaluated source world-bone matrices at matching times for idle, run, floor, reload, deploy and dash. The Unreal import validation compares these samples after its documented axis conversion. A two-metre dash must import as 200 centimetres, and the floor-pose pelvis translation must retain its full magnitude.

`tools/test_rebake_action.py` changes a temporary source hand key by 0.35 radians, rebakes it, exports baseline and changed FBX files, reimports both and compares their animation samples. It does not save the edited production blend. The test accounts for Blender's FBX reimport start-frame offset instead of comparing unrelated samples.

`tools/validate_deploy_grip.py` audits every baked deploy sample against the closed rigid beacon body, rather than treating nearest-surface contact alone as sufficient. The final action has no hand vertices inside that body, less than 0.13 mm opposing-thumb contact separation during carriage, and a grounded released beacon. Results are in `docs/deploy_grip_validation.json`.
