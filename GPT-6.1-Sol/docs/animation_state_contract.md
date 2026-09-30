# Animation state contract

The runtime is native C++ in `unreal/Source/MorphRig`. `AMorphOperative` owns
state priorities, clip clocks and event execution. `UMorphAnimInstance` and
`FMorphAnimProxy` sample the imported `UAnimSequence` assets, blend local bone
poses, then apply ground contact and source-authored morph controls. This
project uses this native controller in place of an Animation Blueprint graph.
Every required ID remains a distinct imported reusable animation asset.

## Coordinates and identity

Blender sources use meters, +X right, -Y forward, +Z up. Unreal uses
centimeters, +X forward, anatomical right -Y and +Z up. The verified legacy
FBX basis maps source (x,y,z) to Unreal (-100y,-100x,100z). FBX import scale is 1.
The authoring deformation skeleton has one ground `root`, independent from
`pelvis`. Unreal replaces periods in FBX bone names with underscores:
`hand.R` becomes `hand_R`, and similarly for fingers and paired facial bones.
The importer records the complete measured Unreal hierarchy and bounds in
`verification/unreal_import_report.json`.

Aim yaw is -60 left / 0 center / +60 right in the operative's frame; pitch
is -35 down / 0 level / +35 up. The nine authored samples are bilinearly
blended. The mask begins at `spine_01`, leaving pelvis and planted legs to
locomotion. Facing remains independent from travel: A/D strafe, S retreats,
and directional walk/run cycles blend between the nearest two 45-degree
samples using a common normalized cycle phase.

## Layers and movement

| Layer | Clips | Movement rule |
|---|---|---|
| Locomotion | three idles, eight walk/run directions, sprint, starts/stops, turns/pivots | capsule and CharacterMovement own travel; reference speeds 150/400/650 cm/s |
| Upper body | ranged_fire, ranged_burst, cast_directional | continue locomotion; action and aim apply above spine_01 |
| Aim | nine aim_* samples | independently adjusted yaw/pitch, lower-body pose preserved |
| Additive reaction | hit_f/b/l/r | local rotation/translation delta from combat neutral, masked above spine_01 |
| Full body | melee, reload, ground/self cast, channel, charge, deploy, uplink, dialogue and social clips | planted or explicit host-controlled motion; one full-body action owns the bones |
| Airborne/recovery | jump, fall, land, knockup, knockdown, prone, getup | CharacterMovement handles collision/gravity; front/back family retained |
| Terminal | death_front/back, dead_front/back, respawn | death clears actions and fires once; dead pose holds until respawn |

Full-body states block unrelated actions until recovery or explicit
interruption. Channel, charge and uplink transitions crossfade from the
current evaluated pose for 140 ms. This also handles a cancel during the
start clip and a release at any time during a sustained loop. Upper-body
weights fade over about 100 ms. Transitions do not restart the outgoing
clip; snapshot blending preserves the current pose through interruption.
The transition snapshot retains the sampled pose before ground IK. The new
blended pose receives one ground correction, so a transition on a slope
cannot double the pelvis adjustment or sole rotation. A separate final pose
cache retains the fully corrected pose for stasis.

The four dash clips contain authored root translation. The native host
extracts root displacement over each advanced clip-time interval with
`UAnimSequence::ExtractRootMotionFromRange`, rotates it into actor space and
moves the CharacterMovement capsule with collision sweep. Evaluation strips
the same root translation from the mesh. Blink has no baked actor travel;
`teleport_actor` moves the capsule once, then `blink_in` plants at the new
position. Knockback travel and knockup launch are host controlled.

## Sustained and exceptional states

| Entry | Sustained state | Complete / recover | Interrupt |
|---|---|---|---|
| channel_start | channel_loop | channel_end | channel_interrupt |
| charge_start | charge_hold | charge_release | charge_cancel |
| uplink_start | uplink_loop | uplink_end | uplink_cancel |
| stun_start | stun_loop | stun_end | death overrides |
| sleep_start | sleep_loop | sleep_end | death overrides |
| knockup_start | knockup_air | land_heavy on actual capsule landing | death overrides |
| knockdown_front | prone_front | getup_front | death overrides |
| knockdown_back | prone_back | getup_back | death overrides |
| death_front | dead_front | respawn | held terminal state |
| death_back | dead_back | respawn | held terminal state |

Death preempts cast, locomotion, sustained actions and airborne motion,
clears upper-body/hit tracks and stops speech. Respawn clears disables,
facial overrides and deployed prop instances and restores a living ready
state, including cleared wounded/attention states, pending movement and aim.
Priority values are death/dead 100, knockup 85, knockdown/prone/getup 80,
stun 70, sleep 60, and other actions 0. Respawn bypasses the terminal guard
and resets the disable flags explicitly. Stasis pauses clip clocks, capsule movement, speech and the evaluated
pose. Stasis disables the CharacterMovement component tick as well as the
pose clock; an airborne capsule therefore remains exactly at its suspended
position. Exit, reset, respawn and a death override restore movement ticking.
Root prevents translation while eligible upper-body actions remain
available. Silence suppresses casts/channel/charge/uplink. Disarm suppresses
ranged/melee/reload. Fear/charm/taunt reuse authored locomotion and attention
states and have visible HUD indicators. Wounded switches the idle presentation.

## Marker execution and rate

`docs/animation_manifest.json` is the timing authority. The importer also
places `UMorphMarkerNotify` markers in the imported sequences for inspection.
Native runtime event execution uses manifest clocks rather than evaluating
the same editor notifies a second time. The HUD shows clip time, playback
rate and the last seven state/events; `Saved/Verification/state_events.jsonl`
contains the complete actor/state/event trace.

Each active track owns an increasing token, cycle number and last executed
clip time. Advancing a track visits only markers in `(previous_time,
current_time]`. At a true loop boundary, the cycle advances and the cursor
resets once. Replacing/interruption destroys the old cursor. A blended-out
pose has no event cursor and cannot emit another contact. Blade windows,
three muzzle events, reload contacts, beacon release, cast release,
channel/charge transitions and foot contacts are thus clip-time events.

Rate is clamped to 0.5..1.5. Events follow the scaled clock once per token
and loop cycle. In-place movement speed and gait phase use the same nominal
reference speeds, so a rate change does not silently double the number of
contacts. Speech audio pitch/time follows the same rate. The deterministic
sequence includes representative 0.5x and 1.5x actions.

## Contact and facial evaluation

Interactive start/stop retains the authored transition torso over the
directional gait. Gait phase follows actual capsule travel, including the
current movement-component update before pose evaluation, so acceleration
and long frames retain the authored stance velocity. Startup phase matches
the preceding left support ankle. Continuing gait legs remain current
through torso-only interruption snapshots. The browser plays the complete
original start/stop assets for inspection.

During start/stop and stationary recovery, world contact anchors retain
planted support through the blend; they release from the authored gait
support phase as the foot swings. Reset and teleport clear that history.
Stationary contacts persist after stop completion until the next deliberate
step. Their ground queries and IK use the same target X/Y. Ordinary travel
uses the current authored gait X/Y. Interactive transition foot events come
from the actual gait track; full-asset browser playback retains source events.

CharacterMovement handles the floor, a 20-degree ramp and 20-cm steps.
Runtime ground traces supply foot height and normals; capsule-relative
targets update immediately when collision moves the capsule onto a step.
The animation proxy samples the current authored lower-body pose, including
the transition snapshot, in game-thread `PreUpdate` after CharacterMovement.
Ground queries use that pose's foot X/Y; the worker applies IK to the same
pose. Neither query placement nor stance detection uses the preceding
corrected socket pose.
Support queries cover the measured boot footprint: 18.6 cm forward,
4.45 cm behind the ankle and 5.15 cm to either side. Each candidate ankle
height subtracts that point's predicted rotated sole offset from the hit
height. Imported toe skin weights provide the independently posed toe
surface. Continuous planes use analytical surface heights; discontinuities
use per-vertex toe rays, so a toe crossing a riser raises the foot before
the ankle itself reaches the higher tread. The ankle's queried normal
remains authoritative for rotation while adjacent surfaces affect height.
Only normals meeting CharacterMovement's walkable-floor threshold drive
sole rotation; a ramp's exposed side face supplies height collision only.
The clearance margin is 1 mm on continuous planes and 3.5 mm at surface
edges, accommodating vertices that blend shin and ankle influences.
Height collision correction can apply during
swing without forcing the stance rotation onto an authored lifted foot.
Two-bone IK preserves the current authored foot X/Y during ordinary travel,
retains the transition contact target where described above, and corrects height
without stretching. Stance weight comes from the current sampled foot lift,
so the previous corrected pose cannot turn a swing foot into a plant.
Pelvis lowering derives from each leg's length and horizontal reach, with a
32-cm bound and smooth upward recovery. Actual ramp/stair playback uses less
than 21 cm of that allowance. Swinging feet retain their authored lift;
full-body floor/airborne states retain their authored poses. The IK runs in the native runtime and
requires no editor component or physics daemon.

The close-up face panel exercises every exported anatomical morph
individually, including separate L/R blinks, squints, brows, cheeks, smile,
frown and eye pitch/yaw. Eye controls accept -1..1; other controls accept
0..1. Speech uses the baked facial bones and resets slider overrides before
playback. The seven portable viseme sliders compose anatomical controls:

| Control | Anatomical mapping at value 1 |
|---|---|
| closure | lip_close=1, jaw=0 |
| labiodental | jaw=.12, width=.20 |
| open | jaw=.75 |
| wide | width=1, jaw=.30 |
| round | pucker=.85, jaw=.30 |
| tongue | tongue=1, jaw=.22 |
| consonant | jaw=.12, width=.15 |

## Reuse

To integrate the authored assets into a future game, keep the documented
bone/socket names and root policy, stage the manifest, and supply movement,
aim, action and interruption requests through `AMorphOperative`. The native
module uses Engine/Core/AnimationCore interfaces and portable C++; no
Linux-specific runtime API is used. The Linux wrapper belongs to the build
environment, separate from the reusable runtime.
