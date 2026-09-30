# Operative rig usage

This document explains how to pose, animate, bake and extend the Operative in `source/Operative.blend`. The file holds two armatures:

| Object | Purpose |
|---|---|
| `Operative_Control` | The animator rig: 201 bones (controls, mechanism bones, the blended arm/leg chains). All clip actions (`A_<id>`, 96 of them) animate this object. |
| `Operative_Skeleton` | The deformation skeleton: 111 bones, exactly one root (`root`), a connected hierarchy, stable names. It follows the control rig through `MR_FOLLOW` copy-transform constraints and is the only armature that is exported. |

The meshes (`Operative_Body`, `_Head`, `_Eyes`, `_Mouth`, `_Hand_R`, `_CyberArm_L`, `_Boots`, `_Gear`, `_Braid`, `_Cable`, `_Hair`) are skinned to the deformation skeleton. The power cell and beacon props (`Operative_Prop_PowerCell`, `Operative_Prop_Beacon`) are separate objects that follow the prop bones.

## 1. Conventions

* Units: Blender metres in the source, centimetres in the FBX and Unreal (the exporter bakes the ×100 in a temporary scene, so the FBX unit scale is 1 and Unreal needs no import scale).
* Axes: Z up, the character faces +X, the character's left is +Y, the origin sits on the ground between the feet. Unreal receives `(x, y, z)` as `(x, -y, z)`.
* Bone frame: local Y runs head to tail, local Z is the flexion hint, X = Y × Z. Positive X rotation is forward flexion for spine, limbs and head. Right-side bones are exact mirrors of the left side.
* Height: 1.80 m to the top of the skull (180.05 cm), 180.8 cm to the top of the hair cap; the same values in Unreal, no scale correction.
* Frame rate: 30 fps. Clip frame *n* is Blender frame *n + 1*. `action["mr_frames"]` holds the clip length in 30 fps intervals.

## 2. The tools panel

Run the text `MorphRig_Tools.py` once (Text Editor, Run Script). Blender only starts embedded scripts automatically when auto-run is allowed, so this step is needed in a default installation. The panel appears in the 3D View sidebar under the **MorphRig** tab. The same file is stored as `source/generators/mr_tools.py`.

| Section | What it does |
|---|---|
| Rig | Reset pose (all bones and all control properties back to their defaults), reset face, global scale, secondary influence, look-at strength |
| IK / FK | Blend slider per limb and two match buttons (see section 4), foot roll |
| Hands | Curl, spread and per-finger curl sliders for both hands |
| Face | Neutral plus six expression presets with a weight, fourteen viseme buttons, independent blink and gaze sliders, every face slider |
| Team accent | Team A (cyan, circle icon) or team B (magenta, diamond icon), rim outline strength |
| Clips | Searchable list of the 96 actions. The play button assigns the action and sets the scene range to 1 … 1 + frames at 30 fps |
| Bake | Secondary motion, visemes to face controls, action onto the deformation skeleton |

## 3. Control layout

Bone collections: World, Torso, Mechanism, Face, Secondary, Arm FK, Arm IK, Fingers, Leg FK, Leg IK, Props.

**Root and pelvis.** `ctl_root` carries root motion and turn yaw. Scaling `ctl_root` uniformly scales the whole character (the follow constraints keep the deformation skeleton exact). `ctl_pelvis` moves and rotates the hips independently from the root, which lets a clip lower or lay the body down without moving the root. The deformation root is a separate bone that never follows the pelvis.

**Spine, neck, head.** `ctl_spine_01..03`, `ctl_neck_01..02` and `ctl_head` are FK controls.

**Look-at.** `ctl_look_target` is a world control in front of the face. Its properties `look_eyes` and `look_head` (0 to 1) decide how strongly the eyes and the head aim at it (damped-track constraints). At 0 the eyes and head take only their own controls.

**Arms.** Per side: `ctl_clavicle`, FK chain `ctl_upperarm_fk`, `ctl_lowerarm_fk`, `ctl_hand_fk`, and the IK set `ctl_hand_ik` (world-oriented control at the wrist) with the pole `ctl_pole_arm`. The custom property `ik_fk` on `ctl_hand_ik_*` blends the chains (0 = FK, 1 = IK; both arms start in FK).

The FK upper arm rests in an A-pose (about 32 degrees out of the body's frontal plane). Its Euler values are therefore not body angles: flexion turns about an axis that is tilted with the arm, so an arm raised above the shoulders swings across the body unless it is abducted first, and two raised arms end up crossed. The clip generators avoid this with `anim_lib.arm_fk(..., sagittal=True)` (`FKS(...)` in the clip modules), which takes the elevation about the body's lateral axis (`flex`) and the angle between the arm and the body's sagittal plane (`abd`, about 12 = hanging at the side, 0 = in the plane) and converts them to the Euler values of the control bone.

**Legs.** `ctl_thigh_fk`, `ctl_calf_fk`, `ctl_foot_fk`, `ctl_ball_fk` and the IK set `ctl_foot_ik` with the pole `ctl_pole_leg`. `ik_fk` on `ctl_foot_ik_*` blends (default 1 = IK). Reverse-foot roll is driven by the properties `roll` (degrees, negative pivots on the heel, positive rolls over the ball and then the toe) and `roll_break` (the angle where the pivot moves from ball to toe tip). `ctl_foot_ik` rotation X/Y/Z is bank, pitch and yaw around the ground contact.

**Hands and fingers.** Each hand has FK controls per finger joint (`ctl_index_01_l`, …, metacarpals included) plus the helper bone `ctl_hand_pose_l/r` with the properties `curl`, `spread`, `thumb_curl`, `index_curl`, `middle_curl`, `ring_curl`, `pinky_curl`. The helper values are added on top of the FK controls through drivers, so poses can be keyed either way. A closed fist is `curl` 1.05, a pointing hand is `curl` 1.05 with `index_curl` −1.05.

**Correctives and twist.** Shoulder, elbow, wrist, hip and knee each have a half-angle helper bone (`shoulder_half_*`, `elbow_half_*`, `wrist_half_*`, `hip_half_*`, `knee_half_*`) that copies half of the parent rotation. Upper arm, forearm, thigh and calf carry two twist bones each (`*_twist_01/02`, 0.33 and 0.66 of the roll). All of them are constraints on the deformation skeleton, so they work in Unreal after baking without extra setup.

**Props.** `ctl_blade` slides the forearm blade out along its local Y (0 = retracted, 0.22 m = extended). The power cell and the beacon are moved by the prop bones `prop_cell` and `prop_beacon`. Every clip that handles a prop contains a baked follow track for them (cell in the forearm slot, in the pouch or in a hand; beacon in the dock, in a hand or on the floor), computed from the rigid grip transforms so the prop cannot slip.

**Secondary motion.** `ctl_hair_01..05` (braid) and `ctl_cable_01..05` (cable on the left forearm) are FK controls. See section 8.

## 4. IK/FK matching

The buttons in the panel (or `mr_tools.snap(ctl, "ARM_l", "FK_TO_IK")`, limb names `ARM_l`, `ARM_r`, `LEG_l`, `LEG_r`) work on the current frame:

* **FK ← IK** copies the blended result onto the FK controls and sets `ik_fk` to 0. It is exact.
* **IK ← FK** moves the IK control to the current wrist or ankle transform, searches the pole direction until the elbow or knee lands where it was, resets `roll`, and sets `ik_fk` to 1. In tests the hand and foot match to 0.02 mm and 0.0°, the elbow to 0.2 mm and the knee to 0.1 mm. The roll of the upper arm about its own axis can differ by up to about 7° because an IK chain derives that roll from the pole.

Key the property `ik_fk` on the frame you switch on, and key the FK and IK controls too, otherwise the interpolation between the two poses is used.

Match first, then switch. Blending `ik_fk` over many frames between two arm poses that are far apart (for example an IK hand on the floor and an FK arm folded at the face) can pop the hand or the elbow by 30 cm or more within one frame (an early version of `sleep_start` did). The clip is now authored the safe way: it stays IK until an FK key holds the same pose (`keypose.fk_like`), then continues in FK.

## 5. Face rig

Everything for the face lives on `ctl_face`, the jaw, the tongue, the eyes and the lids.

* **Morph channels.** `ctl_face` holds 44 float properties (0 to 1), each one drives a shape key of `Operative_Head` (the shape-key value has a driver reading the property):
  `brow_up_in_l/r`, `brow_up_out_l/r`, `brow_down_l/r`, `brow_pinch`, `squint_l/r`, `eye_wide_l/r`, `cheek_raise_l/r`, `cheek_puff_l/r`, `cheek_suck`, `nose_wrinkle_l/r`, `nostril_flare_l/r`, `mouth_smile_l/r`, `mouth_frown_l/r`, `mouth_wide`, `mouth_narrow`, `dimple_l/r`, `mouth_shift_l/r`, `mouth_pucker`, `mouth_funnel`, `lip_press`, `lip_up_l/r`, `lip_down_l/r`, `lip_roll_up`, `lip_roll_down`, `lip_tuck_lower`, `chin_raise`, `jaw_open_corr`, `lip_corner_down_l/r`.
* **Eyes.** `ctl_eye_l` and `ctl_eye_r` rotate independently: X = pitch up, Z = yaw to the character's left (degrees). The upper lids follow the eye pitch automatically (`MR_LIDFOLLOW`).
* **Blinks.** `ctl_lid_up_l/r` closes with negative X rotation (−36° closes the lid), `ctl_lid_lo_l/r` closes with positive X (+15°). Left and right are independent, so winks and asymmetric blinks work. The lids close around the eyeball centre without a gap.
* **Jaw and tongue.** `ctl_jaw` opens with negative X rotation (24° maximum) and moves sideways and forward. `ctl_tongue_01..03` lift with negative X. The teeth and tongue meshes are `Operative_Mouth`; the mouth cavity is closed geometry behind the lips, so the mouth never shows a hole through the head.
* **Expression presets.** Neutral plus `joy_confidence`, `anger`, `concern_sadness`, `surprise`, `pain` and `focus`. The panel applies them with a weight; the data is `face_lib.EXPRESSIONS`. All of them can be mixed with the individual channels, asymmetric versions are made by editing the `_l`/`_r` channels.
* **Close lips.** `lip_press` at 0.95 or higher closes the lips into a single line with the jaw closed. The lip edge in the neutral pose already touches.

### Viseme controls and mapping

`ctl_face` also carries fourteen helper properties `viseme_<name>` (0 to 1). They are inputs for the panel and for the baking operator. The mapping below is the documented one (it is not a proprietary standard). Applying a viseme with weight *w* sets the listed morph channels to *w × value*, opens the jaw to *w × jaw open* of its 24° range, and lifts the tongue by *w × tongue*. A mix of visemes is the weighted sum, clamped to 1 per channel.

| Viseme | Jaw open | Face morphs (weight) | Tongue | Sounds (ARPAbet) |
|---|---|---|---|---|
| `sil` | 0.00 | - | 0.0 | silence |
| `PP` | 0.05 | lip_press 1, mouth_narrow 0.2 | 0.0 | p b m |
| `FF` | 0.10 | lip_tuck_lower 1, mouth_wide 0.15 | 0.0 | f v |
| `TH` | 0.22 | lip_up_l 0.2, lip_up_r 0.2, mouth_wide 0.15 | 0.8 | th dh |
| `DD` | 0.20 | mouth_wide 0.25 | 0.6 | t d n l |
| `KK` | 0.28 | mouth_wide 0.2 | 0.3 | k g ng |
| `CH` | 0.15 | mouth_pucker 0.5, mouth_funnel 0.45 | 0.0 | ch jh sh zh |
| `SS` | 0.10 | mouth_wide 0.45, lip_up_l 0.15, lip_up_r 0.15 | 0.4 | s z |
| `RR` | 0.20 | mouth_pucker 0.35, mouth_narrow 0.25 | 0.0 | r er |
| `AA` | 0.85 | lip_down_l 0.3, lip_down_r 0.3, mouth_wide 0.1 | 0.0 | aa ah ao |
| `EE` | 0.35 | mouth_wide 0.75, mouth_smile_l 0.2, mouth_smile_r 0.2 | 0.0 | iy ih ey eh ae |
| `IH` | 0.40 | mouth_wide 0.4 | 0.0 | ih ah ax |
| `OH` | 0.55 | mouth_funnel 0.75, mouth_narrow 0.35 | 0.0 | ow oy |
| `OO` | 0.25 | mouth_pucker 1, mouth_narrow 0.5 | 0.0 | uw uh w |

Coverage of the shape classes the speech needs: lip closure (`PP`), labiodental (`FF`), open vowel (`AA`), wide vowel (`EE`, `IH`), rounded vowel (`OH`, `OO`), tongue to teeth (`TH`, `DD`), other consonants (`KK`, `CH`, `SS`, `RR`).

**From phonemes to visemes in the speech clip.** `source/generators/make_dialogue.py` maps the eSpeak IPA symbols of the spoken text to these visemes (a weight below 1 opens the mouth less, for reduced vowels):

| Viseme | IPA symbols (weight if not 1) |
|---|---|
| `PP` | p b m |
| `FF` | f v |
| `TH` | θ ð (0.9) |
| `DD` | t d n (0.9) l ɫ ɾ (0.8) ʔ (0.3) |
| `KK` | k ɡ g ŋ (0.9) x (0.8) |
| `CH` | ʃ ʒ tʃ dʒ |
| `SS` | s z |
| `RR` | ɹ r ɻ ɚ (0.9) ɝ |
| `OO` | w (0.85) ʊ (0.7) u |
| `EE` | j (0.6) ɛ (0.8) e (0.85) i |
| `IH` | h (0.4) ə (0.55) ɜ (0.7) ᵻ (0.6) ɪ |
| `AA` | ɑ ɒ (0.8) ɐ (0.5) a (0.8) æ (0.75) ʌ (0.55) |
| `OH` | ɔ (0.95) o |

The diphthongs `əʊ` and `eɪ` are merged into one `OH` or `EE` shape. Stressed vowels open about 12 % more, unstressed ones about 8 % less.

## 6. The spoken performance (`dialogue`)

* Audio: `source/audio/dialogue.wav` (22.05 kHz mono, 16.6 s), transcript `dialogue.txt`, alignment `dialogue_alignment.json` (sentences, words, phonemes with start and end times in seconds, viseme timeline, the pauses, and the result of an independent recognition check).
* Text: about holding a lane and stabilising a network, five sentences ("Listen." … "I'll be right behind you."). The emotional arc goes from worry (`concern_sadness`) over resolve (`focus`) to warmth (`joy_confidence`). The two `emotion_shift` markers in the clip mark the turns.
* Voice: Piper `en_US-ljspeech-high` (public-domain LJ Speech recordings, trained from scratch). The voice model is patched to expose its duration predictor, which gives the exact number of samples for every phoneme, so the alignment belongs to the rendered audio and is not estimated. `verify_dialogue.py` transcribes the WAV with Whisper as a second opinion (all 39 words recognised; the median difference is 0.11 s at word starts and 0.05 s at word ends, Whisper's own timing is the coarser of the two).
* Regenerate: `tools/piper_py.sh source/generators/make_dialogue.py`, then `python3 source/generators/verify_dialogue.py`. The synthesis uses random noise, so a rerun gives a slightly different take; the clip length follows the audio length (`clip_table.py` reads the alignment file).
* Animation: lips come from per-viseme dominance curves (strong, narrow curves for `PP` and `FF` so closures are complete, weak ones for tongue-only consonants), keyed densely on the face controls and reduced with a small tolerance. The `viseme_*` properties are keyed as well, so the viseme track can be edited and baked again with **Bake visemes to face controls**. Eyes make saccades between gaze targets tied to the words, micro-saccades, and blinks in the pauses. Brows flash on stressed words, the head nods on them. The hands gesture on the words they belong to (attention palm, mesh and collapse for the network, sweep for the lanes, point to the north lane, level and join for the relay, rising fingers for the signal, hand on the chest for the beacon, open palm for the last sentence).

## 7. Team accent

Two variants share mesh and rig. `scene["mr_team"]` (0 = A, 1 = B) selects colour and icon in the Blender materials, `scene["mr_outline"]` (0 to 1) adds a rim outline in the team colour. Team A is cyan with a circle icon, team B magenta with a diamond icon, so the teams differ by shape as well as by colour. The icons sit on the chest and back plates (channels G and B of `T_Armor_TM.png`), the accent paint is channel R of the team masks, and the glowing strips read `T_Cyber_E.png`.

## 8. Secondary motion

`Bake secondary motion` simulates the braid (`hair_*`) and the cable (`cable_*`) as position-based spring chains attached to the head and the left forearm and keys their FK controls over the scene range for the current action. Settings per chain are in `mr_tools.CHAINS` (stiffness along the chain, damping, gravity, maximum angle). `ctl_root["secondary_influence"]` scales the result (0 gives the rigid follow pose). The simulation runs six passes over the range so looping actions come back to their start state; the chains settle and cannot run away because of the shape-matching term and the angle limit.

The exported clips carry no baked secondary motion. The Unreal controller simulates the same two chains at runtime (a switch in the showcase panel turns it off). Bake it in Blender when a clip must ship with the motion inside, and export with the baked keys.

## 9. Adding or changing a clip

1. Author the motion with the key-pose helpers (`keypose.py`, `anim_lib.py`, `gait.py`) in one of the `clips_*.py` modules, or animate the control rig by hand and keep the action name `A_<id>`.
2. Rebuild: `blender -b --factory-startup -P source/generators/build_all.py -- --blend source/Operative.blend` (add `--bake-textures` to rebake the textures; they are also rebaked automatically when the UV layout changes).
3. Export: `blender -b source/Operative.blend -P tools/export_and_bake.py -- --out "$PWD" --only <id>`.
4. Import into Unreal with `tools/ue_import_all.sh anims`.

## 10. Skinning, LODs and limits

* 111 deformation bones, 106 carry weights, at most 6 influences per vertex (limit 8).
* Deformation topology: rings around shoulders, elbows, wrists, fingers, hips, knees and ankles; radial rings around the eyes; a closed mouth cavity behind the lips.
* LOD0 40,088 triangles (44 morph targets), LOD1 20,043, LOD2 8,818. Seven material slots, textures up to 2048 × 2048. The full numbers are in `docs/material_and_lod_report.json`.

## 11. Evidence images

Rendered from `source/Operative.blend` with the scripts in `source/generators/` (see `docs/build_and_import_instructions.md`, section 7):

* `docs/skinning_pose_tests.png`: the skinning demonstration required by the rig section of the spec. Rows: overhead reach, deep squat, crossed-arm reach, large torso twist, kneeling, planted hand support, closed grip around the beacon. Columns: front, left, back, three-quarter. Each pose is a one-frame action `A_pt_<name>` in the .blend (not part of the 96 exported clips). The floor poses were tuned numerically: the boots and the planted hand touch the floor within 3 mm, the kneeling knee rests at 6.5 cm.
* `docs/face_expressions.png`: row 1 neutral, `joy_confidence`, `anger`, `concern_sadness`, `surprise`; row 2 `pain`, `focus`, then three asymmetric examples built from single left/right channels (left wink with a one-sided smile, right smirk with a raised left brow, a side glance with a puffed left cheek).
* `docs/face_visemes.png`: the 13 mouth shapes in table order without `sil`: `PP FF TH DD KK` / `CH SS RR AA EE` / `IH OH OO`.
