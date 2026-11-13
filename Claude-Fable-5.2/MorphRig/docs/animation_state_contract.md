# Operative animation state contract

This document defines how the 96 inventory entries are combined at runtime. It is the specification the
Unreal controller (`UOperativeAnimInstance` + `UOperativeStateComponent`, C++) implements and the
reference for any later game integration. All clip timing, marker frames, speeds and prop tracks are read
from `docs/animation_manifest.json` (packaged with the showcase) - nothing in this contract depends on a
hard-coded frame number.

## 1. Conventions

| Item | Convention |
|---|---|
| Sample rate | 30 fps authored/baked; runtime interpolates. `duration = frame_end / 30`. Loops repeat frame 0 on the last frame. |
| Travel direction | degrees relative to body facing, 0 = forward, +90 = character's left, -90 = right, 180 = back. |
| Aim | yaw + = towards the character's left, pitch + = up. Grid yaw -60 / 0 / +60, pitch -35 / 0 / +35. |
| Hit direction | `hit_f` = the hit arrives **from** the front (attacker in front), `hit_b` from behind, `hit_l` from the character's left, `hit_r` from the right. |
| Root | In-place clips never move the `root` bone. Dash clips translate `root` by 200 cm (root motion drives the capsule). Turn/pivot clips rotate the body **inside** the clip while `root` stays fixed (see 3.3). |
| Nominal speeds | walk 150 cm/s, run 400 cm/s, sprint 650 cm/s. |
| Locomotion phase | every walk/run/sprint loop starts with the left foot contact at normalized phase 0 and has the right foot contact at phase 0.5. |
| Playback rate | action rate multiplier 0.5x - 1.5x (showcase control) scales the clip clock of actions; marker times scale with the clock, events are never re-timed independently. |

## 2. Evaluation layers (bottom to top)

1. **Base layer** - exactly one full-body source at a time: the locomotion blend (section 3) or a
   full-body state clip (actions with `layer = fullbody`, disables, death, respawn, emotes).
   Changes cross-fade from the *current evaluated pose* (pose snapshot blend, 0.12 - 0.25 s), never by
   restarting the previous clip, so an interruption cannot pop back to a first frame.
2. **Upper-body action layer** - clips with `layer = upperbody` (ranged, directional cast, reload, charge)
   are blended over the base from `spine_01` upwards with per-bone weights
   (`spine_01` 0.35, `spine_02` 0.7, `spine_03` and everything above 1.0; pelvis and legs 0) while the
   base layer keeps driving the legs. When the character stands still the same clips play on this layer
   over the idle.
3. **Aim layer** - two steps with one weight `AimWeight`: (a) the upper body (same per-bone mask as the
   upper-body layer) is blended towards the `aim_level_center` pose, which raises the emitter arm into
   the firing line; (b) a mesh-space additive built from the nine aim poses relative to
   `aim_level_center`, bilinear in (yaw, pitch), is added on spine, clavicles, arms, neck and head.
   Legs and pelvis are never touched, so planted feet cannot be rotated through the floor. Upper-body
   action clips (`ranged_*`, `cast_directional`, `charge_*`) are authored around `aim_level_center`, so
   they receive step (b) only. `AimWeight` is 1 while aiming or firing, 0 during full-body states that
   own the arms (melee, deploy, disables, death ...), with a 0.15 s blend.
4. **Additive hit layer** - `hit_f/b/l/r` are local-space additives relative to their own frame 0,
   weighted by the hit direction, applied to spine/neck/head/clavicles/upper arms. They layer over idle,
   locomotion and actions without restarting them and never move the feet.
5. **Look-at** - head/neck/eyes turn towards the attention target with clamps (neck+head 70 deg yaw,
   eyes 32 deg); disabled in disables/death/sleep.
6. **Ground adaptation** - per-foot traces, two-bone leg IK, foot pitch/roll to the surface normal and a
   pelvis drop, active on the locomotion/idle base only; smoothed, clamped to 25 cm.
7. **Procedural bones** - twist and half-rotation helper bones are re-solved from the final limb pose
   (same rules as the Blender rig, see `skeleton_and_sockets.json`), then the cable chain spring
   simulation and prop re-attachment (section 7).
8. **Face** - morph curves and baked face bones from the playing clips, plus the face control layer
   (direct controls, visemes, expression presets, automatic blinks, eyelid follow), see section 8.

## 3. Locomotion

### 3.1 Inputs
`Velocity` (world), `Facing` (actor yaw), `bStrafe` (facing is controlled independently - aim/target
mode), `bSprint`, `bWounded`, `bGrounded`.

Local travel direction `dir = atan2(v . left, v . forward)` and speed `s = |v_xy|`.

* **Strafe / aim mode** (default in the showcase): the actor keeps facing the aim target; all eight
  directional gaits are used. Facing and travel are fully independent.
* **Travel mode**: the actor turns towards its velocity (540 deg/s) and uses the forward family, with
  `start_f`, `stop_f`, `pivot_l180/r180` and `sprint_f`.

### 3.2 Gait blend
* Direction: the two clips adjacent to `dir` (45 deg sectors) are blended linearly by angle.
* Speed: idle <-> walk below 150 cm/s (by `s / 150`), walk <-> run between 150 and 400 cm/s,
  run <-> `sprint_f` between 400 and 650 cm/s (sprint only when `bSprint` and |dir| < 30 deg).
* All loops share one normalized phase. `phase += dt * rate / T`, where `T` is the weight-blended
  cycle length and `rate = s / v_nominal_blended`, clamped to 0.5 - 1.5, so that foot speed follows the
  controller speed without sliding.
* Foot contact events are taken from the dominant clip only.

### 3.3 Starts, stops, turns and pivots
* `start_f` / `stop_f` (travel mode): played as base one-shots when the character begins to move from
  idle / comes to rest from a run; they blend into the loop at the matching foot phase.
* `turn_l90` / `turn_r90`: when idle and the desired facing differs by more than 60 deg. At clip start
  the actor yaw snaps by +-90 deg and the controller applies a constant compensating root yaw offset of
  -+90 deg to the mesh for the duration of the clip; because the clip itself turns the body by 90 deg,
  the body turns smoothly in world space and the offset is removed when the clip ends on the idle pose.
* `pivot_l180` / `pivot_r180`: same mechanism with 180 deg, used in travel mode when the input reverses
  (|delta| > 135 deg) at run speed. Controller velocity is braked and re-accelerated by the host.

### 3.4 Air
`jump_start` (anticipation; the capsule is launched at the `jump_takeoff` marker) -> `jump_air` (loop while
rising / short jumps) -> `fall` (loop after 0.45 s of descent or a drop > 150 cm) -> `jump_land` (impact
speed < 900 cm/s) or `land_heavy` (>= 900 cm/s). Walking off a ledge enters `fall` directly. Air control
steers the capsule; the upper-body and aim layers stay available in `jump_air`.

### 3.5 Wounded presentation
`bWounded` replaces `idle_relaxed`/`idle_combat` by `idle_wounded`; while moving, the wounded idle's
upper body is overlaid at 0.6 on the gait, speed is capped at walk and sprint is disabled.

## 4. Actions

`R` = rooted (movement input ignored), `M` = may move, `UB` = upper-body layer.

| Action | Clips | Movement | Interrupt / cancel rules |
|---|---|---|---|
| Melee combo | `melee_1` -> `melee_2` -> `melee_3` | R until `recovery` | Next attack input inside `combo_window`..end chains to the next clip. After `recovery` movement or another action cancels the tail. Hit window = `hit_begin`..`hit_end`. Blade extends at `blade_extend`, retracts at `blade_retract` or when the combo ends. |
| Ranged shot / burst | `ranged_fire`, `ranged_burst` | M, UB + aim | Not while disarmed. One projectile per `muzzle_n` marker. Re-fire allowed after `recovery`. |
| Directional cast | `cast_directional` | M, UB + aim | Effect at `cast_release`. Cancelled by silence/stun before release = no effect. |
| Ground cast | `cast_ground` | R | Effect at `cast_release` at the ground target. Movement allowed after `recovery`. |
| Self cast | `cast_self` | R | Effect at `cast_release`. |
| Reload | `reload` | M at walk speed, UB | Cancel before `reload_insert` = no ammo, props snap back to their mounts with a 0.1 s blend. After `reload_insert` the reload counts. Fire input is ignored during reload. |
| Charge | `charge_start` -> `charge_hold` (loop) -> `charge_release` / `charge_cancel` | M at walk speed, UB + aim | Release may be requested at any time after `charge_begin`; charge level = time since `charge_begin` / 1.5 s (clamped). Release before `charge_ready` cross-fades from the current pose into `charge_release` (weak release). Cancel input, silence or disarm -> `charge_cancel`. Stun/knock/death drop the charge without a cancel clip. |
| Channel | `channel_start` -> `channel_loop` -> `channel_end` / `channel_interrupt` | R | Emission between `channel_begin` and the end. Normal end (button released or 4 s elapsed) -> `channel_end`. Forced end (movement command, heavy hit, silence, interrupt key) -> `channel_interrupt`. Either can happen at any point of start or loop; the exit clip is cross-faded from the current pose. |
| Uplink (recall) | `uplink_start` -> `uplink_loop` -> `uplink_end` / `uplink_cancel` | R, feet planted | Completes after 3 s of loop -> `uplink_end` (`uplink_complete`), the following blink is a separate action. Any damage, movement command or disable -> `uplink_cancel`. |
| Deploy beacon | `deploy` | R | Hand takes the beacon at `deploy_grab`, releases at `deploy_release` (a world beacon is spawned, the carried beacon bone is hidden until restock). Cancel before release returns the beacon to the belt. |
| Dash | `dash_f/b/l/r` | root motion, 200 cm | Not cancellable; ends early only by death/knock. Capsule follows the root motion and sweeps against the world. |
| Blink | `blink_out` -> teleport -> `blink_in` | R | The actor is teleported at `blink_vanish`; the mesh is hidden between `blink_vanish` and `blink_appear`. Travel is never baked into the clips. |
| Emotes | `greet`, `victory`, `defeat`, `dialogue` | R | Cancelled by movement or any action input. `dialogue` starts the WAV at `line_start`. |

## 5. Disables, death and priorities

Priority (higher wins, lower is interrupted without playing its exit clip unless stated):

1. **Death** - `death_front` (lethal hit from the front: thrown onto the back, ends face-up) or
   `death_back` (lethal hit from behind: falls forward, ends face-down). Plays exactly once, then holds
   `dead_front` / `dead_back` (identical to the final frame). Overrides every non-terminal state,
   clears actions, charge, channel and status flags, ignores all further input and hits. If the
   character is already prone, the dead pose that matches the lying side is blended in directly. If the
   character is airborne the clip plays while the capsule keeps falling.
2. **Respawn** - only from dead: actor is moved to the spawn point, props/attachments and all layers are
   reset, `respawn` plays once (invulnerable), then idle.
3. **Stasis** - freezes the complete evaluated pose (clock stopped, no events, no hit additives) until
   released, then continues exactly where it stopped.
4. **Knock-up / knock-down** - `knockup_start` -> `knockup_air` (loop while airborne) -> on landing
   `knockdown_back` from its `ground_impact` marker -> `prone_back` -> `getup_back`.
   A grounded knock-down plays `knockdown_back` when the hit came from the front and `knockdown_front`
   when it came from behind, followed by the matching `prone_*` loop (1.2 s) and `getup_*`.
   `knockback` is the standing reaction to forced backward travel (host moves the capsule).
5. **Stun** - `stun_start` -> `stun_loop` -> `stun_end`.
6. **Sleep** - `sleep_start` -> `sleep_loop` -> `sleep_end`; any damage wakes the character.
7. **Soft flags** - *root*: no translation, upper-body actions still allowed; *silence*: no cast /
   channel / charge / uplink (active ones are interrupted); *disarm*: no melee / ranged; *fear*, *charm*,
   *taunt*: forced travel (away from / towards the source) with the normal locomotion set, a face preset
   (surprise / joy / anger) and attention on the source. A floating state label marks these flags; it
   never replaces the authored stun / sleep / knock animation.
8. **Actions** (section 4), then **locomotion**.

A higher-priority state that arrives during a lower one wins immediately (for example death during a
cast or a jump, stun during a channel). Hits while moving only add the additive reaction. A new
equal-priority disable restarts its own chain from the current pose. Contradictory full-body states can
never overlap because the base layer has a single owner.

Recovery always ends in idle/locomotion with a valid pose: `getup_*`, `stun_end`, `sleep_end`,
`respawn`, `knockback` hand control back at their `control_regained` marker.

## 6. Events

Markers are stored per clip in the manifest and as notifies on the imported sequences.

| Marker | Clips |
|---|---|
| `foot_l_contact`, `foot_r_contact` | all gaits, starts/stops/turns/pivots, landings, get-ups, blink-in |
| `jump_takeoff`, `land_impact` | jump start, landings |
| `dash_start`, `dash_end` | dashes |
| `blink_vanish`, `blink_appear` | blink |
| `blade_extend`, `hit_begin`, `hit_end`, `combo_window`, `recovery`, `blade_retract` | melee |
| `muzzle_1..3`, `recovery` | ranged |
| `reload_eject`, `reload_stow`, `reload_grab_new`, `reload_insert`, `reload_done` | reload hand-offs |
| `cast_release`, `recovery` | casts |
| `channel_begin`, `channel_tick`, `channel_complete`, `channel_interrupted` | channel |
| `charge_begin`, `charge_ready`, `charge_pulse`, `charge_released`, `charge_cancelled` | charge |
| `deploy_grab`, `deploy_release` | deploy attach / release |
| `uplink_begin`, `uplink_pulse`, `uplink_complete`, `uplink_cancelled` | uplink |
| `stun_begin`, `sleep_begin`, `knockup_launch`, `knockback_begin`, `ground_impact`, `settled`, `hand_plant`, `control_regained` | disables |
| `death_begin`, `ground_impact`, `death_settled`, `respawn_materialize`, `respawn_active` | death / respawn |
| `line_start`, `gesture_hold`, `emotion_shift`, `gesture_push`, `line_end` | dialogue (audio starts at `line_start`; the gesture markers are presentation cues) |
| `hit_peak` | additive hit reactions (largest displacement) |
| `gesture_peak` | greet, victory, defeat |

Dispatch rules:

* Every activation of a clip owns one cursor. A marker fires when the cursor crosses its time moving
  forward, exactly once per pass (once per cycle for loops).
* Only the active owner of a layer fires. A clip that is blending out, was interrupted or is frozen by
  stasis fires nothing more - an interrupted melee therefore cannot produce a late hit window.
* Rate changes (0.5x - 1.5x) scale the cursor speed; they never add or drop markers.
* When a clip is entered at an offset (for example `knockdown_back` from `ground_impact`), markers before
  the entry time are skipped, not replayed.
* The showcase logs each event with world time, clip, clip time, marker and activation id.

## 7. Props and attachments

| Prop bone | Rest parent | Used by |
|---|---|---|
| `blade_l` | `lowerarm_l` (retracted) | melee - slides along its local axis |
| `prop_cell` | `lowerarm_r` (seated in the emitter) | reload |
| `prop_cell_spare` | `pelvis` (belt pouch) | reload |
| `prop_beacon` | `pelvis` (belt, back) | deploy |

Prop motion is baked into the clips. Each clip lists `prop_tracks` (prop, holder bone, frame range). At
runtime, after all layers, a held prop is re-attached to its holder with the clip-authored relative
transform so that additive hits, aim or IK cannot open a gap between hand and prop. Outside a
manipulating clip, and on respawn/cancel, props sit on their rest mounts.

Reload swap: the left hand pulls `prop_cell` out of the emitter, parks it in the empty rear belt cradle
(socket `cell_cradle_rear`), takes `prop_cell_spare` from the front cradle and seats it in the emitter
(socket `cell_slot`). When the clip ends both prop bones return to their rest mounts on the same frame;
the two cells are identical, so the emitter keeps showing a seated cell and the belt a spare one.
`deploy` leaves `prop_beacon` on the ground from `deploy_release` on (holder `world` in the prop track:
the bone stays where it was released, in root space, until the clip ends).

## 8. Face

* Clips carry morph curves (names = morph targets) and baked rotations for `jaw`, `tongue_*`, `eye_*`
  and `lid_*`.
* The face control layer adds, on top of the clip: direct controls, viseme and expression preset
  weights (all defined in `docs/face_controls.json`), automatic blinks (suppressed while a clip animates
  the lids, in sleep/death) and eyelid follow for procedural eye look-at.
* `final(control) = clamp01(clip + direct + sum(viseme * w) + sum(expression * w))`.
* Expression presets: neutral, joy, anger, concern, surprise, pain, focus. Disables select presets
  automatically (stun: pain, sleep: closed eyes, death: eyes closed + jaw slack).
