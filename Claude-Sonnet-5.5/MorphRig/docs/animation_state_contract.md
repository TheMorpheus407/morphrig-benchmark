# Animation state contract

This document states how the Unreal showcase chooses, layers, interrupts and times the 96 clips of `docs/animation_manifest.json`. It describes the code in `unreal/Source/MorphRig/` as delivered. The checks at the end are the ones the deterministic sequence runs in the packaged client.

## 1. Architecture

| Part | File | Job |
|---|---|---|
| `UOperativeLibrary` | `OperativeLibrary.*` | Reads the manifest (frames, loop, layer, root policy, events, foot contacts, entry/exit states) and the alignment file, resolves the 96 `UAnimSequence` assets, keeps them alive. |
| `UOperativeActionComponent` | `OperativeActionComponent.*`, `OperativeActionState.cpp` | State machine, clip timelines, once-per-pass event dispatch, movement outputs, the pose recipe of every frame. Runs on the game thread before the movement tick. |
| `UOperativeAnimInstance` and `FOperativeAnimProxy` | `OperativeAnimInstance.*` | Code-only animation controller. `Evaluate` returns true, so no Animation Blueprint graph runs. It assembles the pose from the recipe. |
| `AOperativeCharacter` | `OperativeCharacter.*` | Capsule (34 cm radius, 90 cm half height, mesh offset -90 cm, 180.05 cm to the top of the skull), movement, ground traces for the foot IK, props, beacon, dialogue audio, outline and team material state. |
| `UOperativeFaceComponent` | `OperativeFaceComponent.*` | Face layer written by code (sliders, presets, visemes, blinks, gaze) on top of, or instead of, the face channels of the clip. |
| `AShowcase*` | `Showcase*.{h,cpp}` | Room, camera views, HUD, panel, key bindings, deterministic sequence, video capture, performance log. |

Nothing in the runtime is editor-only. The module builds for Linux and uses no Linux-specific API.

## 2. Frame order

1. The player controller writes the inputs (move direction and speed, aim point, aim hold, facing mode, action rate, status flags).
2. `AOperativeCharacter::PreMovementTick` measures the ground under both feet (foot IK input) and calls `UpdateActions`.
3. `UpdateActions` advances the state (sections 3 to 8), advances the base, upper and hit timelines (which fires events, section 14), updates aim and look-at (section 10) and writes the `FOperativePoseRecipe`. It also writes `FHostOutput` (movement scale, facing, dash root motion, knockback velocity) that the character applies in the same frame.
4. The anim proxy evaluates the recipe in this order: weighted base samples, snapshot blend (section 16), aim ready pose over the upper body, upper-body clip layer, additive aim offset, additive hits, face bones and morph curves, look-at, foot IK, secondary motion.

## 3. States, priorities and acceptance

Every state has a priority. A command that needs a free state is accepted only when the rule below allows it. Commands that are refused return false and change nothing.

| State (sub-state) | Clips | Priority | Entered by |
|---|---|---|---|
| Locomotion / Idle | `idle_relaxed`, `idle_combat`, `idle_wounded` (stance from health, combat timer, aim) | 0 | default, end of any state |
| Locomotion / Start, Move, Stop, Turn, Pivot | `start_f`, blended `walk_*` `run_*` `sprint_f`, `stop_f`, `turn_l90` `turn_r90`, `pivot_l180` `pivot_r180` | 10 | movement input, facing error, direction reversal |
| Airborne (JumpStart, JumpAir, Fall, Land, LandHeavy) | `jump_start`, `jump_air`, `fall`, `jump_land`, `land_heavy` | 30 | jump command, leaving the ground for more than 0.12 s |
| Action: Greet, Victory, Defeat, Dialogue | `greet`, `victory`, `defeat`, `dialogue` | 20 | emote or dialogue command |
| Action: Melee, Reload, CastGround, CastSelf, Deploy | `melee_1..3`, `reload`, `cast_ground`, `cast_self`, `deploy` | 40 | action commands |
| Action: Channel, Charge, Uplink | `channel_*`, `charge_*`, `uplink_*` | 45 | action commands |
| Viewer | any clip | 50 | animation browser |
| Dash, Blink | `dash_f/b/l/r`, `blink_out`, `blink_in` | 55 | dash or blink command |
| Knockback | `knockback` | 65 | knockback command |
| Stun | `stun_start`, `stun_loop`, `stun_end` | 70 | stun command |
| Sleep | `sleep_start`, `sleep_loop`, `sleep_end` | 75 | sleep command |
| Knockup, Knockdown (knockdown, prone, getup) | `knockup_start`, `knockup_air`, `knockdown_*`, `prone_*`, `getup_*` | 85 | knockup or knockdown command |
| Respawning | `respawn` | 95 | respawn command |
| Dying, Dead | `death_front`, `death_back`, `dead_front`, `dead_back` | 100 | kill command, health reaching 0 |

Acceptance rules:

* **Jump** needs Locomotion (or an action of priority 40 or lower after its `control_return`), a grounded character and no Root or Stasis flag.
* **Dash and blink** need a grounded character in Locomotion, or in an action that is sustained (channel, charge, uplink), inside a cancel window or past `control_return`. The action is cancelled first. Root and Stasis refuse them.
* **Melee, reload, ground and self cast, deploy** (priority 40) and **channel, charge, uplink** (priority 45): accepted in Locomotion; refused in the air; inside another action only after `control_return` or inside a cancel window and only when the new priority is not more than 5 below the running one. A second melee press inside the running melee queues the next combo step (up to `melee_3`).
* **Fire, burst, directional cast** run on the upper layer and need Locomotion without Turn or Pivot. A press during a running upper clip is queued and starts when that clip ends (or, near its end, replaces it).
* **Greet, victory, defeat, dialogue** start from idle or stop, or through the priority-20 rule.
* **Disables** are refused when the running priority is at or above their threshold: knockback 65, stun 70, sleep 75, knockup and knockdown 85. A second stun or sleep extends the running one. A disable cancels a running action, clears the upper layer and blends from the current pose.
* **Kill** is accepted in every state except Dying, Dead and Respawning, and only once until a respawn. It cancels everything else. **Respawn** is accepted in Dead only.
* **Flags**: Root sets the movement scale to 0 and refuses jump, dash and blink. Silence refuses casts, channel, charge and uplink and interrupts a running sustained action. Disarm refuses melee, fire, burst, reload and deploy and clears a running ranged upper clip. Stasis stops the clock of the controller (time step 0, speed 0) and refuses commands that need time.

## 4. Movement and control per state

`FHostOutput` is what the character applies. `Move scale` multiplies the gait speed, `turn` is the yaw rate limit.

| State | Move scale | Turn rate | Control returned |
|---|---|---|---|
| Idle, Move, Start, Stop | 1 | 720 deg/s (540 in movement-facing mode) | yes |
| Turn | 0, yaw driven by the clip progress | driven | no |
| Pivot | 0.55, yaw driven | driven | no |
| Jump start | 0 | 720 | yes |
| Jump air, fall | 1 (air control 0.35) | 720 | yes |
| Land | 0.35 until `control_return`, then 1 | 720 | at `control_return` |
| Land heavy | 0 until `control_return`, braking | 720 | at `control_return` |
| Dash | 0, the capsule follows the root translation of the dash clip, yaw fixed | 0 | no |
| Blink | 0, yaw fixed | 0 | no |
| Melee | 0 | 220 | at `control_return` or `melee_recover` |
| Reload, deploy, greet, victory, defeat, dialogue | 0 | 0 | at `control_return` |
| Cast ground, cast self | 0 | 120 | at `control_return` or cancel window |
| Channel, charge | 0 | 90 | no (sustained), interrupt or release |
| Uplink | 0 | 0 | no, cancel or complete |
| Stun, sleep, knockdown chain, knockup | 0, no air control | 0 | no |
| Knockback | host velocity `travel_dir * v0 * (1 - u)` over the clip, total distance as requested | 0 | no |
| Dying, Dead, Respawning | 0 | 0 | no |
| Viewer | 0 | 0 | no |

When control returns during an action and the player gives move input, the action finishes with a 0.2 s blend into locomotion.

## 5. Locomotion

* **Facing modes**: aim (the body turns to the aim point), movement (the body turns to the movement direction), locked. Travel and facing are independent in aim mode, so the eight walk and run clips are used as strafes.
* **Direction blend**: the signed angle between facing and velocity (left positive) selects two neighbouring sectors of `f, fl, l, bl, b, br, r, fr` and blends them linearly. Gait weights follow the ground speed: walk up to 210 cm/s, run from 210 to 290 cm/s, sprint from 470 to 600 cm/s (sprint only within about 40 to 80 degrees of forward). The three nominal speeds are 150, 400 and 650 cm/s (manifest `nominal_speed_cm_s`).
* **Phase and rate**: the loop phase advances by `speed * dt / stride`, with the stride of the blended clips (`nominal speed * duration`), so the feet follow the ground and the playback rate is speed divided by nominal speed. When a move starts, the phase is matched to the feet of the pose that is leaving (foot positions from the clip library).
* **Start**: from idle with input inside 55 degrees of forward, at least 0.15 s of idle and a speed below 60 cm/s, `start_f` plays; otherwise the move starts directly with phase matching.
* **Stop**: input released while faster than 90 cm/s and within 75 degrees of forward plays `stop_f` with braking; slower stops blend to idle over 0.25 s. New input during the stop restarts the move.
* **Turn**: in idle, a facing error above 75 degrees (not in locked mode) plays `turn_l90` or `turn_r90`; the actor yaw follows the clip progress (smooth step) towards the clamped error. Move input after 30 percent of the clip starts the move.
* **Pivot**: in movement-facing mode, a move faster than 150 cm/s with a facing error above 150 degrees plays `pivot_l180` or `pivot_r180` at 0.55 speed with the yaw driven by the clip.
* **Idle stance**: `idle_wounded` below 35 percent health or with the wounded override, `idle_combat` while aiming, after a ranged or cast command (2 s hold) or with the combat flag, else `idle_relaxed`. A stance change blends over 0.35 s.

## 6. Airborne, dash, blink

* **Jump**: `jump_start` plays with the movement locked; the launch happens at its `jump_takeoff` event (or at the end of the clip); `jump_air` loops. After 0.9 s or a vertical speed below -900 cm/s the pose changes to `fall`. Landing plays `land_heavy` when the fall speed exceeded 800 cm/s or the air time 1.6 s, otherwise `jump_land`.
* **Dash**: the clip is chosen from the input direction relative to the body (within 45 degrees forward, beyond 135 degrees backward, otherwise left or right). The root translation of the clip in Unreal centimetres is sampled per frame and becomes the capsule motion; the mesh stays on the capsule (the mesh root is locked in XY, so the mesh cannot drift). Nominal displacement 200 cm. A dash ends in locomotion; a dash that loses the ground for 0.25 s goes to airborne.
* **Blink**: `blink_out` plays; at its `blink_vanish` event (or at the end of the clip) the actor is teleported along the requested direction (600 cm from the `B` key, 500 cm in the sequence; a capsule sweep shortens the distance in front of obstacles, and the destination is put on the floor found below it); the mesh is hidden during the jump and shown again at `blink_appear`; `blink_in` plays at the destination. The clips carry no travel.

## 7. Actions

| Action | Phases | Rules |
|---|---|---|
| Melee | `melee_1`, then `melee_2`, `melee_3` when the next press was queued before the recover or cancel window | The hit window opens at `melee_hit_begin` and closes at `melee_hit_end` (a serial number counts the windows). During the window the character sweeps three spheres of 14 cm along `blade_base` to `blade_tip` (plus 30 cm) and reports every actor once per window. At `melee_recover` the cancel window opens. Without a queued press the action finishes at the end of the clip. |
| Reload | `reload` | Events `reload_eject`, `reload_handoff`, `reload_insert`, `reload_complete` mark the cell hand-off (the prop bone tracks are baked into the clip). |
| Cast ground, cast self | `cast_ground`, `cast_self` | `cast_release` is the gameplay moment. |
| Deploy | `deploy` | `deploy_attach` recalls the attached beacon into the hand, `deploy_release` spawns the world beacon at the prop bone transform and hides the attached one, `deploy_settle` ends the placement. |
| Channel | phase 0 `channel_start`, 1 `channel_loop`, 2 `channel_end`, 3 `channel_interrupt` | `channel_sustain_begin` starts the sustain. A release request goes to phase 2 at any point of phase 0 or 1 (no restart of the clip). An interrupt (manual, damage, silence) goes to phase 3 from any point and blends from the current pose. The loop ends by itself after 12 s. |
| Charge | phase 0 `charge_start`, 1 `charge_hold`, 2 `charge_release`, 3 `charge_cancel` | The charge is full at the `charge_full` marker of `charge_start` (manifest time). A release at any time plays `charge_release`; a cancel or an interrupt plays `charge_cancel`; a hold of 10 s cancels. |
| Uplink | phase 0 `uplink_start`, 1 `uplink_loop`, 2 `uplink_end`, 3 `uplink_cancel` | The loop runs 3 s, then completes (`uplink_complete`). A cancel or interrupt at any point plays `uplink_cancel`. |
| Greet, victory, defeat | the clip | Finish at the end of the clip or when control returns and the player moves. |
| Dialogue | `dialogue` at rate 1 | The WAV starts with clip frame 0 (offset 0, the lead-in silence is inside the file), the clip drives the face completely, automatic blinking is off. Stopping the action or any cancel stops the audio. |

Every interruption uses the snapshot blend of section 16, so no clip restarts from its first pose.

## 8. Disables, knockdown chain, death, respawn

* **Stun**: `stun_start`, `stun_loop` (until the duration ran out), `stun_end`, then idle.
* **Sleep**: `sleep_start`, `sleep_loop` (until the duration ran out or a hit or wake command), `sleep_end`, then idle.
* **Knockback**: `knockback` with the host velocity of section 4, then idle.
* **Knockup**: `knockup_start`; at its `knockup_launch` event the host launches the capsule; `knockup_air` loops until the ground is reached (after at least 0.15 s); then the knockdown chain starts.
* **Knockdown and getup**: the side is chosen from the hit direction relative to the facing. A hit from the front throws the character onto its back (`knockdown_back`, `prone_back`, `getup_back`), a hit from behind onto its front (`knockdown_front`, `prone_front`, `getup_front`). Prone lasts 1.2 s, then the getup clip plays and ends in idle.
* **Death**: the side follows the hit direction (front hit: `death_front`, back hit: `death_back`). It cancels every running action, clears the upper layer and the hit layers, and fires `death_impact` once. When the clip ends, the base becomes the matching `dead_front` or `dead_back` (paused). Both death clips end on the first pose of their dead pose (0.0 cm difference in the verified run). Death from any state, including a death during a cast or in the air, happens once.
* **Respawn**: from Dead only. `respawn` plays; props, the deployed beacon, blade and cell state, hit layers and the secondary motion are reset; health is 1; at the end the state is idle. The `respawn_activate` event marks the moment the character is alive again.

## 9. Layers

| Layer | Source | Bones | Blend |
|---|---|---|---|
| Base | one clip or the weighted locomotion set | all | snapshot blend for changes of source |
| Aim ready | `aim_level_center` | `spine_01` and up (arms, hands, fingers, blade, props; not face, braid, cable) | alpha 0 to 1 at 9 per second while aiming, back at 12 |
| Upper | `ranged_fire`, `ranged_burst`, `cast_directional` | same mask | 0.07 s in, 0.12 s out, ends 0.12 s before the clip end; only in Locomotion |
| Aim offset | the eight non-centre aim poses as additive offsets of `aim_level_center` | same mask | bilinear in yaw and pitch, weight equal to the aim ready alpha |
| Hits | `hit_f`, `hit_b`, `hit_l`, `hit_r` (additive), two slots | all | weight fades over the last 40 percent; scale 0.35 in knockdown, knockup and sleep, 0 in death states |
| Face | face bones and morph curves of the base clip, then the code layer | jaw, tongue, eyes, lids, 44 morph targets | section 13 |
| Look-at | head yaw and pitch, eye yaw and pitch | neck, head, eyes | alpha follows the look or aim state at 6 per second |
| Foot IK | ground traces | pelvis, thighs, calves, feet | section 11 |
| Secondary | braid and cable chains | `hair_01..05`, `cable_01..05` | section 12 |

Hit direction: the hit travels from the attacker to the victim; the angle of the opposite vector relative to the facing picks the clip (within 45 degrees `hit_f`, beyond 135 degrees `hit_b`, otherwise `hit_l` or `hit_r`). A hit does not change the state. It interrupts a running channel, charge or uplink only when it carries damage. A hit wakes a sleeper.

## 10. Aim and look-at

* Aim angles are relative to the body: yaw -60 to +60 degrees (left positive), pitch -35 to +35 degrees (up positive), smoothed at 14 per second. The nine aim clips sit on the grid yaw (right, centre, left) by pitch (down, level, up) with these signs.
* Aim only acts in Locomotion without Turn or Pivot; the legs are never rotated by the aim layer.
* Look-at splits the angle to the target: 65 percent of the yaw goes to the head (limit 60 degrees) and the rest to the eyes (limit 25 degrees); pitch 60 percent to the head (limit 30 degrees), the rest to the eyes (limit 20 degrees). While aiming, the aim yaw already applied is subtracted.

## 11. Foot IK and ground contact

* The capsule steps up 20 cm (`MaxStepHeight`) and walks on floors up to 32 degrees; the showcase room has a 20 degree ramp, five stairs of 20 cm and curbs of 10, 15 and 20 cm.
* Per foot, a line trace runs at the foot position from 55 cm above to 45 cm below the mesh origin. The offset is clamped to +-28 cm and smoothed at 22 per second; the surface normal is smoothed at 14 per second. The pelvis follows the lowest foot (never up), smoothed at 12 per second, so the pelvis does not float.
* A foot counts as planted when its animated ankle height is within 1.5 to 8.5 cm of the rest height. Planted feet are moved by a two-bone IK (`SolveTwoBoneIK`, knee towards the front) to the ground height; the foot rotates towards the ground normal, up to 25 degrees. Swinging feet keep the animation.
* IK runs in Locomotion, Land and JumpStart, Action, Stun and Blink, and is off in the air, dash, disables and death.

## 12. Secondary motion

The braid (`hair_01..05`, from the head) and the cable (`cable_01..05`, from the left forearm) run a position-based spring chain per frame: stiffness 0.10 and 0.14, damping 0.94 and 0.92, gravity factor 0.9 and 0.7, the chain root pinned to the animated bone, bone lengths kept. The chains restart from the animated pose after a teleport, blink, respawn or reset (`SecondaryResetSerial`) and after a jump of more than 150 cm of the chain root. The panel switch turns the simulation off and the chains follow the clip. The clips carry no baked secondary motion.

## 13. Face

The base clip drives the face bones (`jaw`, `eye_l/r`, `lid_up_*`, `lid_lo_*`, `tongue_01..03`) and the morph target curves. `UOperativeFaceComponent` adds a code layer: 44 morph sliders (left and right channels individually), the six expression presets, 14 viseme controls, jaw opening (24 degrees at 1), tongue lift, blink per eye, gaze, automatic blinking and eyelids that follow the eye pitch (upper lid 0.45, lower lid 0.25). `ClipFaceWeight` chooses how much of the clip face is used. The dialogue action and the face capture run with the code layer empty so the authored performance is shown unchanged.

## 14. Events

**Source.** Events come from the manifest (`events` of each clip, 59 names, 246 entries). A small fallback table in `OperativeActionComponent.cpp` adds an event only when the manifest clip has none of that name; such events are marked `source=fallback` in the trace and drawn yellow in the marker timeline. The manifest time is never moved.

**Once per pass.** Every timeline has a pass id (a new one at each start and at each loop wrap). An event fires when the clip time passes its time; the index advances before the handler runs. A guard on (pass id, role, index) counts and rejects a second firing, and the counter is shown in the HUD and trace (`duplicate_events=0` in the verified run). Blends, snapshots, layer fades and interrupts do not restart a pass. An interrupted clip fires no later events.

**Action rate.** Times are clip times, so the events scale with the rate and never duplicate. The dialogue always plays at rate 1.

**Catalog and hooks** (marker names as in the manifest):

| Event | Clips | Effect in the showcase |
|---|---|---|
| `foot_plant`, `foot_lift` (`foot=l/r`) | locomotion, turns, pivots, jumps, melee, dash and others (48 and 42 entries) | traced, drawn on the timeline |
| `idle_breath`, `breath_in`, `channel_pulse`, `charge_pulse`, `uplink_pulse`, `stun_sway_peak`, `fall_loop_point`, `jump_apex`, `tumble_half`, `aim_hold`, `dead_hold`, `defeat_slump` | idle, holds, loops | traced |
| `control_return` (34 clips) | actions, landings, emotes | control returns to the player |
| `cancel_window_begin`, `cancel_window_end` | fire, burst, reload, casts, channel start, deploy | opens or closes the cancel window |
| `jump_takeoff` | `jump_start` | launches the capsule |
| `land_contact`, `land_impact_heavy` | `jump_land`, `blink_in`, `land_heavy` | traced |
| `dash_begin`, `dash_end` | dashes | traced |
| `blink_vanish`, `blink_appear` | `blink_out`, `blink_in` | teleport of the actor, mesh shown again |
| `melee_hit_begin`, `melee_hit_end`, `melee_recover` | `melee_1..3` | hit window (serial), each actor reported once per window; recover opens the combo window |
| `blade_extend`, `blade_retract` | melee, victory | blade prop state |
| `muzzle_fire` (`index=0..2`) | `ranged_fire`, `ranged_burst` | shot spawn, counted |
| `reload_eject`, `reload_handoff`, `reload_insert`, `reload_complete` | `reload` | cell hand-off hooks |
| `cast_release` | casts | cast spawn |
| `channel_sustain_begin`, `channel_release`, `channel_interrupted` | channel clips | sustain flag |
| `charge_full`, `charge_release`, `charge_cancel` | charge clips | charge full flag, release, cancel |
| `deploy_attach`, `deploy_release`, `deploy_settle` | `deploy` | beacon recall, spawn, settle |
| `uplink_sustain_begin`, `uplink_complete`, `uplink_cancelled` | uplink clips | traced |
| `hit_peak` | hits, disables | traced |
| `stun_begin`, `knockup_launch`, `ground_impact`, `getup_stand`, `sleep_settle` | disables | `knockup_launch` launches the capsule |
| `death_impact` | death clips | traced once |
| `respawn_activate` | `respawn` | living state restored |
| `dialogue_start`, `dialogue_line`, `dialogue_end`, `emotion_shift` | `dialogue` | subtitles and word highlight follow the alignment |

In the animation browser (Viewer state) events are displayed and traced and have no gameplay effect.

## 15. Action rate

`SetActionRate` accepts 0.5 to 1.5. It scales the rate of clips started afterwards (actions, jumps, dashes, disables, upper clips); locomotion follows the ground speed, hits and the dialogue play at 1. The sequence step `action_rate_0_5x_and_1_5x` plays the melee chain at both rates and checks that each hit window opens once per swing.

## 16. Interruption blending

Whenever the base source changes discontinuously, the controller requests a snapshot with a blend time (typically 0.06 s for dash and blink, 0.08 to 0.15 s for actions and disables, 0.2 to 0.35 s for returns and stance changes). The proxy stores the pose it displayed in the previous frame (bones and morph values) and blends from it over the requested time with a smooth step. A channel that is interrupted therefore leaves the last pose of its loop and moves into `channel_interrupt`; it never jumps to a first frame. A change of level of detail rebuilds the bone map and invalidates a running snapshot for that frame.

## 17. Deterministic showcase sequence

`-ShowcaseSequence` (or `F8`) runs 19 steps (158 s of simulated time at a fixed 30 fps step) and prints `SHOWCASE_TRACE` lines (state changes, clips, events, checks) to the log and to `Saved/ShowcaseTrace.txt`:
locomotion (walk, run, sprint, stop); eight directions with independent facing; aim while moving with fire, burst and cast; jump, run jump, long fall; foot IK on the ramp, the stairs and the curbs; four dashes; blink; melee chain; action rate 0.5 and 1.5; reload and casts; channel with sustain, interrupt and release; charge with early release, late release and cancel; deploy; uplink with cancel and completion; hits while moving; stun, sleep and knockback; knockup and knockdown with getup in both directions; death during a cast and respawn, death in the air; the dialogue.

Result in the packaged client (`docs/showcase_sequence_trace.txt`): 59 checks, 59 passed, 0 duplicate events, 507 events, 0 pose spikes. A runtime pose spike is a frame to frame movement of head, pelvis, hands or feet above 40 cm (or above 1.35 times the largest step of the playing clip, times the play rate) in the frames after a state change; Blink, Respawning and Dead are not counted. The process exit status is 0 when every check passed and 2 when one failed. Content checks read the imported assets: 30 loops close within 1.5 cm on head, pelvis, hands, feet and chest; the death clips end on their dead poses within 3 cm (measured 0.0 cm); the dash root travel is 200.0 cm for all four; no standing clip has its head below 110 cm; no clip except melee, dash and blink has a step above 45 cm between two frames of head, pelvis, hands or feet. Runtime checks: walk speed 150, run speed 400 and sprint speed 650 cm/s; capsule displacement along the dash axis 200.0, 200.0, 199.5 and 199.5 cm for dash_f, _l, _b and _r; blink distance 500 cm; foot IK on the ramp, stairs and curbs (planted error and penetration are in the trace); the top-down view shows the character 118 px tall in a 1080 px frame; the dialogue lasts 16.60 s with the audio starting at clip frame 0.
