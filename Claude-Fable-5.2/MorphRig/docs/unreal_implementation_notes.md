# Unreal implementation notes

Scope: the C++ module `unreal/Source/MorphRig`, the import script and the automation around the packaged
showcase. Behaviour is specified by `docs/animation_state_contract.md`; this file says how it is implemented,
where it deviates and what was verified.

## 1. Classes

| Class | File | Role |
|---|---|---|
| `FMorphRigData` | `MorphRigData.*` | runtime database parsed from `Content/MorphRigData/*.json` (manifest clips with markers, speeds, prop tracks; bones, helper rules, sockets; face controls, visemes, expressions; dialogue alignment). Nothing about clips or bones is hard-coded elsewhere except the contract's layer-root names (`spine_01..03`, limb names used for IK) |
| `UMorphEventNotify` | `MorphEventNotify.*` | `UAnimNotify` with `EventName`; one per manifest marker on every imported sequence (static delegate `OnEvent` for games that play the sequences through the stock animation system) |
| `UMorphRigEditorLibrary` | `MorphRigEditorLibrary.*` | editor-time helpers for the import script (sockets, LOD triangle/influence counts, morph statistics, morph curve metadata, LOD screen sizes). Bodies are `WITH_EDITOR` only |
| `UOperativeAnimInstance` + `FOperativeAnimProxy` | `OperativeAnimInstance.*`, `OperativeAnimTypes.h` | **native animation controller**: no AnimBlueprint/AnimGraph. The proxy's `Evaluate()` builds the pose on the animation worker from one `FOperativeAnimInput` snapshot per frame |
| `UOperativeStateComponent` | `OperativeStateComponent.*` | game-thread state logic: gait blend, clip cursors, priorities, action rules, status flags, marker dispatch, face control layer, foot traces; writes the `FOperativeAnimInput` |
| `UOperativeMovementComponent` | `OperativeMovementComponent.*` | `UCharacterMovementComponent` with a forced horizontal velocity (root-motion dashes, host-driven knock-back) |
| `AOperativeCharacter` | `OperativeCharacter.*` | capsule 30x90, mesh (yaw -90, z -92), team materials, outline overlay, ground ring, display modes, LOD forcing, event-driven effects, dialogue audio, autopilot for the extra instances |
| `AShowcaseDirector` | `ShowcaseDirector.*` | instances, cameras, command interpreter (`mr ...`), automation scripts, deterministic sequence, capture, benchmark, trace file, input injection |
| `AShowcasePlayerController` | `ShowcasePlayerController.*` | keyboard/mouse polling -> commands and per-frame intent, target dragging, orbit camera |
| `AShowcaseHUD` | `ShowcaseHUD.*` | canvas HUD (appears in frame captures): state/clip/marker bars, events, skeleton overlay, labels, captions, subtitles, help |
| `SShowcasePanel` | `SShowcasePanel.*` | Slate panel: help, searchable animation browser, face sliders, character options, state buttons |
| `AShowcaseRoom`, `AShowcaseFX` | `ShowcaseRoom.*`, `ShowcaseFX.*` | room from engine basic shapes (floor, 20 degree ramp, nine 20 cm steps, platform, three movable aim targets, prop station, viewer dais, backdrop dome, lights); pooled basic-shape effects |
| `AShowcaseGameMode` | `ShowcaseGameMode.*` | spawns the director, sets controller and HUD classes |

Tick order per frame: director (script, clock) -> player controller (intent) -> state component -> movement component
-> skeletal mesh (pose evaluation). The order is enforced with tick prerequisites.

## 2. Pose evaluation (`FOperativeAnimProxy::Evaluate`)

All clip sampling uses `UAnimSequence::GetAnimationPose`; the clip clocks are owned by the game thread, the worker
only samples at the times it is given.

1. **Base**: weighted blend of up to eight samples (`BlendPosesTogether`): the gait set (two walk + two run
   directions, sprint, idle) or the single clip that owns the base layer. Root-motion clips are sampled with the
   root locked; an optional root yaw offset (turn/pivot compensation) is applied to `root`.
2. **Wounded overlay** and **upper-body layer**: per-bone blend with the contract mask (`spine_01` 0.35,
   `spine_02` 0.7, `spine_03` and descendants 1, prop bones 1). The upper source is either the active upper-body
   action clip or, while aiming without an action, the `aim_level_center` pose weighted by `AimWeight`
   (aim step a).
3. **Inertial blend**: whenever a base or upper source changes, the state component bumps a transition serial; the
   proxy then measures per-bone offset and velocity between its previous two outputs and the new source pose and
   decays them with the quintic inertialization polynomial over the requested time (0.08 - 0.35 s). The new source is
   animated from its first frame, the previous clip is never sampled again, so interruptions blend from the pose that
   was on screen.
4. **Hit additives**: local-space delta of each active hit clip against its own frame 0, weighted by direction
   (the two neighbouring clips; clips and directions are the manifest entries with `layer = additive` and their
   `hit_from_deg`) on spine, neck, head, clavicles and upper arms.
5. **Aim additive** (aim step b): mesh-space rotation delta `aim(yaw, pitch) * inverse(aim_level_center)`,
   bilinear over the 3x3 grid read from the manifest, applied to `spine_01` and all its descendants only.
6. **Look-at**: neck 40 % / head 100 % towards the attention point, clamped relative to the chest (70 deg yaw,
   +40/-35 deg pitch); eyes with the limits of `face_controls.json`; eyelids follow the procedural eye pitch.
7. **Ground adaptation**: per-foot vertical offsets and surface normals from game-thread traces, pelvis drop,
   analytic two-bone IK (`AnimationCore::SolveTwoBoneIK`) keeping the authored knee direction, foot aligned to the
   surface. Active on grounded locomotion only; offsets clamped to 25 cm and smoothed.
8. **Face bone controls** (jaw, lids, tongue offsets from the control layer). `final(control) = clamp01(clip +
   layer)` also holds for these bone-driven controls: the amount the playing clips and the eyelid follow already
   contribute along a control (twist of the bone relative to its reference pose about the control's axis, or the
   projection for translations) is measured and only the remainder up to the full offset is added, so a baked blink
   plus an automatic one cannot over-rotate a lid. Then the **procedural helper
   bones** exactly as in `skeleton_and_sockets.json` (`half`, `untwist`, `twist`), then **prop re-attachment**
   (prop follows its holder with the transform authored in the owning clip), hidden props (scale ~0) and the
   **cable chain** (Verlet points in world space, spring towards the animated pose, length constraint, cone limit
   32 + 9*n degrees per link, automatic reset on teleports and NaN; sub-stepped at 90 Hz).
9. **Curves**: clip morph curves + control-layer additions, clamped to 0..1 and flagged as morph-target curves.

Stasis returns the stored last pose and curves without advancing anything.

**Floor-contact clips** (knock-downs, prone loops, get-ups, sleep, deaths and dead poses, respawn, `land_heavy`,
`cast_ground`, `deploy`; a clip may also set `"floor_contact": true|false` in the manifest) are played untouched:
while one of them owns the base layer the upper-body layer, both aim steps and the hit additive are switched off
(the hit layer fades over 0.12 s), look-at is off outside locomotion/air anyway and ground adaptation only runs in
the locomotion state. Planted hands, knees and feet therefore stay exactly where the clip puts them.

**Morph targets that failed the import check** (`import_report.json` -> `morph_targets.disabled`, only possible with
placeholder data because final data fails the import instead) are never driven; the HUD and the trace say how many.

## 3. State logic notes

* **Clip cursors and markers**: every activation has an id; `Advance()` collects the markers in `(last, now]`,
  loops wrap once per cycle, entering a clip at an offset skips earlier markers, and a handler that replaces the
  clip stops the remaining markers of the old one. Only the owner of a layer has a cursor, so blended-out clips cannot
  fire. Rate changes scale the cursor speed only. Gait foot contacts come from the dominant clip on the shared phase.
* **Gait**: one normalised phase for all loops (each clip is sampled at `phase * its own duration`, so directions
  with different frame counts stay in step); cycle length and nominal speed are the weight-blended values of the
  clips that are actually mixed; rate = controller speed / blended nominal speed, clamped 0.5 - 1.5.
* **Start / stop / pivot** (travel mode): when the manifest gives a `speed_profile` for the clip, the capsule
  velocity follows it while the clip plays (start: along the input direction, the actor keeps turning towards it;
  stop: along the travel direction; pivot: along the old travel direction, ending reversed), scaled to the speed the
  clip was entered with (0.5 - 1.6) - trace line `PROFILE ...`. Without a profile the movement component's own
  acceleration and braking are used. `exit_phase` (when given) is the gait phase the loop continues from. New travel
  input cancels `stop_f`.
* **Turns / pivots**: the actor yaw snaps at clip start, the proxy applies the opposite root yaw offset during the
  clip (which contains the body turn) and drops it with the clip. If another base clip interrupts a turn the
  remaining rotation is absorbed by the inertial blend. A turn in place needs the aim to stay outside +-60 degrees
  for 0.12 s (debounce).
* **Dash**: the root track delta of the tick (`ExtractRootMotionFromRange`) is converted to a world velocity and
  forced through the movement component, so the capsule follows floors, steps and walls with the normal walking
  code while the mesh root stays locked.
* **Death during air / prone**, **knock-up landing**, **reload cancel**, **charge/channel/uplink exits**,
  **refusals** follow the contract tables; every decision is written to the trace
  (`STATE`, `CLIP`, `EVENT`, `REFUSED`, `INTERRUPT`, ...).

* **Automatic face presets**: pain for stun / knock states and as a short pulse on a hit, low pain while wounded,
  surprise / joy / anger for fear / charm / taunt, closed lids in sleep and death, slack jaw in death. Actions and
  emotes get no automatic preset - their clips carry the authored face animation. Automatic blinks run in
  locomotion, air and action states.

## 4. Materials

Both masters are Default Lit (the skin master was a subsurface material at first; its red scatter colour washed out
the painted brows, stubble and lips and brightened the shadow side, so it was dropped).

`M_Operative` / `M_OperativeSkin` parameters: `BaseColorTex`, `NormalTex`, `ORMTex` (R AO, G roughness, B metallic),
`MaskTex` (R team accent area, G icon A, B icon B, A emissive weight), `TeamColor`, `IconSelect` (0 = G, 1 = B),
`AccentEmissive`, `IconEmissive`, `RoughnessScale`, `HitFlash`, `Dissolve` (masked noise dissolve used by blink and
respawn). Team switching swaps the per-slot instances `..._TeamA/_TeamB`; the mesh and rig are untouched.
Colour-independent team cues: icon channel, outline style (`M_Outline` overlay, solid vs dashed) and ground ring
shape (`M_TeamRing`, solid ring + chevron vs segmented ring + bar).

### Lighting and close-up cameras

Three movable directional lights (key with virtual shadow maps, two fills without shadows) and a sky light. SMRT uses
16 rays x 8 samples for the directional light and the key has a 3 degree source angle. The room key (pitch -52,
yaw 35) lights the character from behind in its default facing; seen from the front this left the face in the fill
with a ragged shadow terminator across forehead and cheeks (occluder distance ~0, so no source angle softens it). In
the front / side / turntable views and the face / head-and-shoulders close-ups the key therefore follows the view
(35 or 32 degrees beside it, 42 or 30 degrees above); the close-ups also use shadow amount 0.6, source angle 7 degrees
and 0.62x key intensity. `mr shadow ...` changes these values at runtime.

The `face` and `bust` cameras take the position of the `head` bone (damped, speed 6), never its rotation, look along
the actor's facing and frame about 35 cm / 68 cm of height (horizontal FOV 30 degrees at 118 cm / 225 cm).

## 5. Data the asset side controls

* `animation_manifest.json`: clip list, durations, markers, `layer`, `gait`, `nominal_speed_cm_s`,
  `travel_dir_deg`, `turn_yaw_deg`, `aim_yaw_deg`/`aim_pitch_deg`, `hit_from_deg`, `final_pose`,
  `root_motion.displacement_cm`.
* Optional **`prop_tracks`** per clip (frames, 30 fps):
  `[{"prop": "prop_cell", "holder": "hand_l", "frame_start": 14, "frame_end": 26}, ...]` (`start`/`end` and the
  grouped form `[{"prop": ..., "segments": [{"holder", "start", "end"}]}]` are accepted too). While a segment is active
  the prop bone is re-attached to the holder bone with the clip-authored relative transform and the HUD shows the
  distance between the prop bone and the holder's hand socket. `holder` may be any bone of the skeleton (for example
  `lowerarm_r` for a cell that sits in the emitter, `pelvis` for one in the belt cradle); a holder that is not a bone
  (`"world"`) is ignored - the baked motion is used as it is.
* Optional **`speed_profile`** for `start_f`, `stop_f`, `pivot_*`: one value per frame (`frame_end + 1` values),
  speed along the facing at clip start, in m/s as authored (values <= 30) or cm/s; `speed_profile_cm_s` and
  `{"m_s": [...]}` / `{"cm_s": [...]}` are accepted as well. Optional `exit_phase` / `entry_phase` (0..1).
* Optional **`floor_contact`** (bool) per clip, see section 2.
* `face_controls.json`: morph names, controls, bone control offsets (`unreal_quat_xyzw`, `unreal_loc_cm`),
  visemes, expressions, eye limits.
* `dialogue_alignment.json`: words and phonemes for the subtitle line; `clip.audio_start_time`.

## 6. Deviations from the contract and limits

1. **Aim weight when an aim-authored action starts cold** (contract: 0.15 s blend): `AimWeight` ramps linearly in
   0.15 s for the aim stance, but when `ranged_*`, `cast_directional` or `charge_*` starts while the weight is still
   below 1 it is set to 1 immediately and the pose change is carried by the action's inertial blend (0.08 - 0.12 s);
   otherwise a shot whose muzzle marker sits on frame 2 would leave before the arm points at the target.
2. **Blend type**: the contract says "pose snapshot blend"; implemented as an inertial blend from the last two
   output poses (same guarantee, the new clip keeps moving during the blend).
3. **Automatic recall**: after `uplink_complete` the showcase starts a separate blink to the spawn point 0.6 s
   later so the "later blink" is visible; a game would trigger its own teleport.
4. **Travel-mode pivots** are triggered by a reversed input (> 135 degrees) above 300 cm/s; braking and
   re-acceleration follow the clip's `speed_profile` when the manifest has one, otherwise the movement component's
   own friction/acceleration. `stop_f` starts immediately when the input is released above 280 cm/s (it does not wait
   for the clip's `entry_phase`; the inertial blend covers the phase difference).
5. **Sprint** needs the sprint key, a forward travel direction (|dir| < 30 degrees) and no aim stance.
6. **Engine additive assets are not used**: hit and aim clips stay ordinary absolute sequences (so every one of the
   96 entries can be viewed directly); the additive deltas are computed at runtime as described above.
7. Root-motion clips viewed in the motion viewer move the capsule and are put back on the dais at every loop.
8. Dialogue audio is started at `line_start`; it is not re-synchronised if the viewer is scrubbed.
9. No ragdoll, cloth or physics asset is used; the only simulated element is the cable chain.

## 7. Engine observations (UE 5.8.3)

* Changing `FApp::SetUseFixedTimeStep` from inside an actor tick is reverted by the engine's per-task time context;
  the director applies it from `FCoreDelegates::OnBeginFrame`.
* `FScreenshotRequest` compresses and writes the PNG on the game thread (3 - 8 frames per second at 1920x1080). While
  a capture runs the director binds `UGameViewportClient::OnScreenshotCaptured`, which makes the engine hand over the
  read-back pixels instead, and enqueues an `FImageWriteTask` per frame (throttled when more than 24 are pending).
* Morph curves are flagged on the skeleton at import and additionally on the curve elements written by the proxy.
* The FBX path is Interchange (the `FbxImportUI` options are converted). A Blender armature object must be named
  `Armature` to be dropped as a null root (handled by the exporter).

## 8. Verification

Automated, repeatable on the packaged client (`tools/ue_full_cycle.sh verify`, outputs in `docs/verification/`):

| Check | Evidence |
|---|---|
| import | `import_summary.txt`: root bone, bone count and reference pose error, mesh height, LOD triangles / influences, material slots, morph targets (missing / implausible / per LOD), sockets with position error, 96 clips with notifies, root-motion displacement of the dashes, textures with a GPU memory estimate, props |
| deterministic sequence | `sequence_trace.log`, `sequence_verify.txt`: event rules A-G, coverage of all 96 entries, 22 combined-state expectations (rule H) |
| interaction through Slate | `ui_selftest_trace.log`, `ui_selftest_verify.txt`: 9 expectations (rule I) |
| motion viewer | `browse_all_trace.log`, `browse_all_verify.txt`: 96 of 96 entries selected and started (rule J) |
| frame time | `docs/benchmark/*.json`, `*_frames.csv`, `host.txt` (GPU load before the run is recorded; the GPU is shared on the build host) |

Final dataset, import: `root`, 84 bones, reference pose error 0.0001 cm, mesh 0.00 - 180.76 cm, LOD triangles
38178 / 20249 / 12700 with at most 8 influences, 6 material slots, 32 morph targets on all three LODs (none
implausible), 15 sockets (error 0.0 cm), 96 clips (84 with curves, 189 notifies), dashes +-200 cm, 22 textures
(largest 4096, about 81 MB block-compressed with mips), 2 props.

Looked at by eye on the final dataset (screenshots of the editor `-game` build and stills taken from the three
presentation videos of the packaged client): face and head-and-shoulders views in neutral, expression presets,
visemes, blink and eye look; the speech clip at its gesture markers; third person, front, top-down; deploy and
reload close-ups; contact sheets of the complete sequence and of the turntable (textured, wireframe, clay, normals,
LOD 1 / 2, skeleton overlay, team B).

Measured:

* ground adaptation (final export, HUD read-out of the packaged client): standing sideways on the 20 degree ramp
  the ankles are 9.8 / 9.9 cm above the surface with ground adaptation (feet moved +1.6 / -5.1 cm, pelvis lowered
  5.1 cm; the ankle joint of the flat foot is 9.8 cm high) and 8.2 / 16.1 cm without it;
* top-down view: projected body height 119 px at 1920x1080 (LOD1 is selected automatically at that distance);
* face bone controls (final export, `mr bone` on the packaged client): `blink_l` turns `lid_upper_l` by 40.50 deg
  and `lid_lower_l` by 11.00 deg while the right lids stay open, `jaw_open` turns `jaw` by 21.00 deg, `tongue_out`
  moves `tongue_01` by 1.10 cm - the offsets listed in `face_controls.json`; eyes 28 deg down -> the upper lid follows
  by 17.39 deg, and a full blink on top ends at the control's 40.50 deg, not beyond;
* world beacon at `deploy_release` (final export): placed 1.0 cm above the floor with its up axis at (0, 0, 1);
* speech sample: the WAV is muxed 0.733 s after the first captured frame, which is the frame that shows clip frame 9
  (`line_start`);
* `speed_profile`: with a synthetic profile `start_f` reached run speed at its last frame, `stop_f` ended at 0 cm/s
  and a pivot ended at run speed in the reversed direction; the final manifest's profiles are used by the same code
  (trace lines `PROFILE ...` in `sequence_trace.log`).

Not verifiable in the build sandbox: a presented window (the sandbox display has no Vulkan surface, all runs used
`-RenderOffScreen`) and audible sound (no audio device; the audio engine runs on SDL's dummy driver and the dialogue
component reports playing; the WAV in `face_performance.mp4` is muxed by `ffmpeg`).
