# Known issues and limits

Honest list of what is not perfect, not tested, or deliberately simplified. Numbers are from the last build
(`docs/animation_manifest.json` `qa` blocks, `docs/verification/`, `docs/benchmark/`).

## Not tested

* **No presented window, no physical input, no audible sound.** The production host is headless; the packaged
  client was only run with `-RenderOffScreen` and SDL's dummy audio device. Rendering, input handling (through
  injected Slate events), traces and captured videos were inspected; a real desktop session with a monitor,
  keyboard, mouse and speakers was not available. `tools/run_showcase.sh` without `MORPHRIG_OFFSCREEN=1` starts
  the normal windowed client.
* **Windows.** Only the Linux client was built. The project uses no Linux-only runtime feature (plain C++ module,
  Slate, standard character movement), but a Windows build was not made.
* **The spoken line was never listened to.** The alignment was validated numerically against the waveform
  (sibilants, vowels and pauses sit where the alignment says) and visually in the captured video; intelligibility
  and pronunciation of the synthetic voice were not judged by ear.

## Character and look

* The face is stylised and smooth: no wrinkles, only faint pore noise in the normal map, simplified teeth (one arch per jaw),
  eyelashes as a few cards, no separate cornea shell. Lip sync is rule based (phoneme timing to viseme curves)
  without per-frame hand polish; fast consonant clusters read softer than in keyframed lip sync.
* Hair is modelled as polygon locks (no strands, no simulation). The data cable is the only simulated element.
* Skin weights are analytic. Rigid plates are bound to single bones or helper bones on purpose; in extreme poses
  they can touch or slightly intersect the suit or each other (pauldron against the gorget in the overhead reach,
  tasset and thigh plate against the hip in the deep squat and when lying down).
* Textures are procedural. Fine triplanar fabric patterns change direction where the dominant surface axis
  changes; UV islands of the hard-surface parts come from an automatic angle-based projection (many small
  islands, usable for rebaking but not hand-laid).
* LOD2 shows UV stretching on decimated parts (sleeve hem, chest decals) when it is forced at close range. The
  head keeps its full topology on every LOD.
* Height: the top of the hair crest is at 180.8 cm, the top of the skull at 178.7 cm (the 1.80 m target lies
  between the two).
* The second (rear) belt cradle is empty at rest; after a reload the spent cell is parked there only until the
  clip ends (both cells snap back to their rest mounts, see the contract).

## Animation

* `walk_f`: the QA slide number is 13.9 cm/s on one frame per step - the toe-off frame (18 -> 19), where the toe
  tip is already lifting (1.8 mm above the floor) and has travelled 4.6 mm less than the ground. Every other
  planted frame of every gait cycle measures 0.
* Hands that support the body on the floor are released when the body moves out of arm reach instead of
  stretching the arm. In a few transitions the hand therefore leaves its support a little early and travels with
  a straight arm: `death_back` (up to 18 cm around frame 26), `getup_front` (17 cm, frame 29), `knockdown_front`
  (12 cm, frame 12), `death_front` (9 cm), `sleep_start` (8 cm), `sleep_end` (7 cm), `land_heavy` (6 cm on the
  first frame), `getup_back` (5 cm).
* Knock-downs, get-ups and deaths move the feet along the floor while the body falls or rises (feet are not
  planted in those clips); this is intended but not physically simulated.
* 44 of the 96 source actions are solved per frame on the controls (`"source_keys": "dense"` in the manifest):
  the 17 generated gait cycles, start / stop / pivots / dashes (feet solved against the moving ground), the
  floor-contact clips, and greet / victory / defeat / dialogue (layered acting). Keys that linear interpolation
  reproduces within 0.1 mm / 0.02 degrees are removed, which leaves on average 6 to 38 keys per curve on the
  clips of up to 3 s and about 130 on the 500-frame dialogue. They are editable in the graph editor, but less comfortable than the
  52 sparse-keyed clips (pose keys with Bezier interpolation).
* The eight directional gaits are generated from one parametric gait model (per-direction stride, pelvis and
  arm styling); they are genuine directional cycles with matching contacts, not rotated copies, but they share
  one style.
* Aim poses were calibrated for the emitter arm; with the aim layer at the grid corners (yaw 60, pitch 35
  degrees) the shoulder is near its limit.
* Lowest sole point over all clips: -0.4 cm (`jump_start`, one frame during the push-off).

## Pipeline

* A full Blender build takes about 8 minutes on the idle reference host (5 of them for the 4096 px skin maps; with
  `--reuse-textures` under 2 minutes). One production build ran while other workloads loaded the shared host and
  took 31 minutes. A full build regenerates everything, so interactive edits must be re-baked with `--from-blend`
  (see `docs/rig_usage.md`) or moved into the generators.
* Blender must be started without a display variable on the headless host (`DISPLAY= blender -b ...`).
* The speech tool chain (Piper, voice model) is only needed to regenerate the audio and is not part of the
  delivery; the voice model must be downloaded separately (URL and hashes in `THIRD_PARTY_ASSETS.csv`).
* A presentation capture needs about 8 GB of temporary disk space (lossless frames before the encode).

## Unreal

* **Deviations from `animation_state_contract.md`** (details in `unreal_implementation_notes.md`, section 6):
  the aim weight snaps to 1 when an aim-authored action starts cold instead of blending for 0.15 s (the action's
  own blend carries the pose change); blends are inertial blends from the pose on screen instead of pose
  snapshots; `stop_f` starts immediately when the input is released and does not wait for the clip's
  `entry_phase`; the hit and aim clips stay ordinary sequences and their additive deltas are computed at
  runtime (so all 96 entries can be viewed directly).
* **Floor-contact clips are authored for level ground.** Knock-downs, get-ups, sleep, deaths, `land_heavy`,
  `cast_ground` and `deploy` are played without ground adaptation, upper-body layer or additive hits so that
  their contacts stay exact. On the ramp or on the steps the body therefore lies in the plane of the capsule's
  floor point and does not conform to the slope. Ground adaptation (foot traces, pelvis drop, two-bone IK) runs
  in the locomotion state only.
* **No ragdoll, cloth or physics asset.** The only simulated element is the data cable (Verlet chain); it is
  reset on teleports.
* **Props** are bones of the character mesh. At `deploy_release` a separate static-mesh beacon
  (`export/props/SM_Beacon.fbx`) is spawned where the hand put it and the belt beacon is hidden; after 8 s the
  showcase removes the world beacon and restocks the belt (a second deploy is refused until then). After a
  reload both power cells snap back to their rest mounts when the clip ends.
* The packaged client is a **Development** configuration (console and automation commands enabled, about
  850 MB with the engine runtime); a Shipping configuration was not built.
* The ten-instance mode puts nine Operatives on a fixed autopilot schedule (strafing around a point while aiming
  at it; shots, bursts, casts, hits, jumps, dashes, melee and reloads); it is a load test, not AI.
* The benchmark and all captures run offscreen at a forced 1920x1080; a presented window with vertical sync
  will show different frame pacing.
* Benchmark numbers depend on what else runs on the shared production host. Six runs of the final character
  (two on earlier package builds, four on later ones) gave between 320 and 575 fps on average with one Operative
  while other jobs used up to about a third of the CPU; a seventh run that coincided with another job taking
  89 % of the CPU and 19 GB of GPU memory dropped to 90 fps (99th percentile 63 ms) and was discarded. The
  delivered logs (`docs/benchmark/`) are from the last run, made on the final package, and record the host load
  at its start.
* HUD text is small at 1080p (it is laid out to leave the character visible in captures).
* Dialogue audio starts at the `line_start` marker and is not re-synchronised when the motion viewer is
  scrubbed.
