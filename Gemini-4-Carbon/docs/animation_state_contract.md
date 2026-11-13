# MORPHRIG — Animation State Machine, Layering & Event Contract

Runtime implementation:
- [`UMorphRigAnimInstance`](../unreal/Source/MorphRig/Public/MorphRigAnimInstance.h) / [`MorphRigAnimInstance.cpp`](../unreal/Source/MorphRig/Private/MorphRigAnimInstance.cpp)
- [`AMorphRigCharacter`](../unreal/Source/MorphRig/Public/MorphRigCharacter.h) / [`MorphRigCharacter.cpp`](../unreal/Source/MorphRig/Private/MorphRigCharacter.cpp)
- Machine-readable clip & marker table: [`docs/animation_manifest.json`](animation_manifest.json)

---

## 1. Priority Hierarchy & Contradiction Prevention

Full-body state transitions are governed by a deterministic integer priority hierarchy (`UMorphRigAnimInstance::GetStatePriority`) so contradictory states never fight over the same deformation bones:

| Priority | State Group (`EMorphRigPrimaryState`) | Active Clips | Interruption & Override Rules |
| :---: | :--- | :--- | :--- |
| **50 (Highest)** | **Terminal Death & Respawn** (`DeathDying`, `DeadHeld`, `Respawning`) | `death_front`, `death_back`, `dead_front`, `dead_back`, `respawn` | Overrides all ongoing locomotion, jumps, casts, channels, dashes, and hard disables. Death triggers **once** (`IsDeadOrDying()` blocks duplicate deaths) and settles seamlessly into its matching connected pose (`dead_front` / `dead_back`). Only `TriggerRespawn()` exits `DeadHeld`, playing `respawn` and restoring clean props and `Locomotion`. |
| **40** | **Hard Crowd-Control Disables** (`DisableStun*`, `DisableSleep*`, `DisableKnockback`, `DisableKnockup*`, `DisableKnockdown`, `DisableProne`, `DisableGetup`) | `stun_start/loop/end`, `sleep_start/loop/end`, `knockback`, `knockup_start/air`, `knockdown_front/back`, `prone_front/back`, `getup_front/back` | Cancels active abilities, channels, charges, uplinks, dashes, and upper-body layers cleanly via pose snapshot. Front vs. back knockdown (`knockdown_front` → `prone_front` → `getup_front` vs. `knockdown_back` → `prone_back` → `getup_back`) is selected explicitly from impact direction without swapping orientation mid-recovery. |
| **30** | **Mobility Overrides** (`MobilityDash`, `MobilityBlink`) | `dash_f`, `dash_b`, `dash_l`, `dash_r`, `blink_out`, `blink_in` | Cancels lower-priority abilities/channels; blocked when **Rooted**, **Stasis**, Hard-Disabled, or Dead. `dash_*` extracts authored 200 cm root motion onto the Actor Capsule while zeroing mesh-local XY to prevent double translation. `blink_out` triggers instant world-space capsule relocation on the `teleport_event` / `blink_teleport` marker before playing `blink_in`. |
| **20** | **Full-Body Combat, Casts, Sustained Actions & Social** (`AbilityOneShot`, `Channel*`, `Charge*`, `Uplink*`) | `melee_1`, `melee_2`, `melee_3`, `reload`, `cast_self`, `cast_ground`, `channel_start/loop/end/interrupt`, `charge_start/hold/release/cancel`, `deploy`, `uplink_start/loop/end/cancel`, `greet`, `victory`, `defeat`, `dialogue` | Suppresses locomotion translation while active. `melee_1 → melee_2 → melee_3` chains combo windows cleanly or settles back to combat idle after any swing. |
| **15** | **Direct Clip Browser Inspect** (`DirectClipInspect`) | Any of the 96 clips | Used by the interactive searchable 96-clip HUD browser for direct frame-accurate inspection; yields cleanly to any gameplay command or `Reset`. |
| **10** | **Grounded & Aerial Locomotion** (`Locomotion`) | `idle_*`, 8-dir `walk_*` / `run_*`, `sprint_f`, `start_f`, `stop_f`, `turn_l90`, `turn_r90`, `pivot_l180`, `pivot_r180`, `jump_start`, `jump_air`, `fall`, `jump_land`, `land_heavy` | Default continuous layer supporting independent body facing, upper-body combat/cast layering, 9-sample Aim Grid, Look-At, and Ground IK. |

---

## 2. Independent Facing, 8-Direction Gaits & Locomotion Sub-States

1. **Decoupled Travel & Facing**:
   - `UCharacterMovementComponent::bOrientRotationToMovement` is `false`. World movement vector is projected into the character's independent facing frame (`LocalVelForward`, `LocalVelRight`).
   - Nominal reference speeds:
     - **Walk**: `150 cm/s` (`walk_f`, `walk_fl`, `walk_fr`, `walk_l`, `walk_r`, `walk_b`, `walk_bl`, `walk_br`)
     - **Run**: `400 cm/s` (`run_f`, `run_fl`, `run_fr`, `run_l`, `run_r`, `run_b`, `run_bl`, `run_br`)
     - **Forward Sprint**: `650 cm/s` (`sprint_f`, forward cone `<= 35°`; lateral/backward commands automatically clamp to run tier)
     - **Wounded Presentation**: `idle_wounded` at rest and blended stride dampening at `210 cm/s` when `bWounded` is active.
2. **Phase-Synchronized 8-Way Angular Blending**:
   - A continuous normalized gait phase (`GaitPhase` in `[0, 1)`) advances proportional to actual controller ground speed and `ActionPlayRate`, sampling adjacent directional sectors at identical normalized contact phases so diagonal transitions never cross-step or skate.
3. **Starts, Stops, Turns, Pivots & Aerial Cycle**:
   - Rapid acceleration from idle triggers `start_f`; braking from travel triggers `stop_f`.
   - Facing yaw deltas while stationary trigger `turn_l90` or `turn_r90`; sharp `>= 135°` velocity reversals at run speed trigger `pivot_l180` or `pivot_r180`.
   - Airborne vertical state transitions deterministically through `jump_start` → `jump_air` → `fall` (on extended downward drop) → `jump_land` (normal landing) or `land_heavy` (high-fall compression landing).

---

## 3. Pose-Snapshot Arbitrary-Point Interruption Guarantee

When an ongoing multi-stage action (`channel_start`/`channel_loop`, `charge_start`/`charge_hold`, `uplink_start`/`uplink_loop`, or any cast/jump interrupted by a disable or death) exits or cancels at an **arbitrary frame**:
- `UMorphRigAnimInstance::RequestPoseSnapshot(BlendTime)` captures `LastEvaluatedPose` (all 92 bone transforms) and `LastEvaluatedCurves` (all 46 morph curves) on the worker thread.
- The outgoing snapshot crossfades smoothly via cubic Hermite decay (`0.14s–0.22s`) into `channel_interrupt`, `charge_cancel`, `charge_release`, `uplink_cancel`, or `death_front/back`.
- The character **never** teleports back to frame 0 of the interrupted clip.

---

## 4. Upper-Body Layering, Aim Grid & Additive Hit Reactions

Evaluated in strict order inside `FMorphRigAnimInstanceProxy::Evaluate`:

1. **Base Pose** (`Locomotion` 8-way blend or active full-body clip).
2. **Upper-Body `spine_01` Branch** (`UpperBodyMask`: `spine_01..03`, `neck_01`, `head`, facial bones, `clavicle_l/r`, arms, hands, `emitter_bone_r`, `blade_r`, `cell_bone`, `cable_01..03`):
   - Supports moving `ranged_fire`, `ranged_burst`, `reload` (handoff between `hand_l` and `emitter_bone_r` preserved across upper torso), and `cast_directional` while the lower body walks or runs in any of the 8 directions.
3. **Calibrated 9-Sample Aim Grid (`ApplyAimGridLayer`)**:
   - Samples the 3×3 pose grid (`aim_down_left` .. `aim_up_right`) and extracts local-space bone deltas relative to `aim_level_center`.
   - **Explicit Sign Convention**:
     - `AimYawDeg`: **`-60°` = Left**, **`0°` = Center**, **`+60°` = Right**
     - `AimPitchDeg`: **`-35°` = Down**, **`0°` = Level**, **`+35°` = Up**
   - Masked strictly to `UpperBodyMask` (`pelvis`, `thigh_l/r`, `calf_l/r`, `foot_l/r`, `ball_l/r`, and `root` receive zero weight), guaranteeing planted feet never rotate or slide through the floor.
4. **Local-Space Additive Hit Layer (`ApplyAdditiveHitLayer`)**:
   - `hit_f`, `hit_b`, `hit_l`, `hit_r` are evaluated as local-space bone deltas relative to `idle_combat` frame 0 (`AAT_LocalSpaceBase` / `ABPT_AnimFrame`), attenuated on `pelvis` (`0.22`) and masked out of leg chains so hits read clearly over both idle and running gaits without foot snapping.
5. **Ground-Adaptation IK, Head/Eye Look-At & Secondary Settle**:
   - **Ground IK**: Line traces under `foot_l` and `foot_r` compute per-foot vertical offsets and surface normals up to **20° slope** and **20 cm step** delta; `PelvisOffsetZ` drops smoothly to `min(FootOffsetZ_L, FootOffsetZ_R)` so the stance leg never hyperextends, and closed-form analytical 2-bone IK preserves each leg's animated knee-bend plane without ankle inversion.
   - **Look-At**: Damped component-space tracking rotates `head` (clamped `±55°` yaw, `±32°` pitch) and stereo `eye_l` / `eye_r` (`±22°` yaw, `±15°` pitch) toward the movable `AimTargetOrb`.
   - **Secondary Settle**: Critically damped angular spring-damper overlays on `cable_01..03` (`ω = 14 rad/s, ζ = 0.72`, clamped `±0.32 rad`) and `strap_01..03` (`ω = 16 rad/s, ζ = 0.75`, clamped `±0.28 rad`) react to capsule acceleration/yaw velocity and settle cleanly to zero without runaway oscillation.

---

## 5. Soft Crowd-Control States (Reuse Policy — SPEC §8)

- **Root (`bRooted`)**: Zeroes horizontal travel velocity while allowing upper-body attacks, casts, aim, and reload.
- **Silence (`bSilenced`)**: Rejects `cast_self`, `cast_directional`, `cast_ground`, `channel_start`, `charge_start`, and `TriggerBlink()` while preserving locomotion and weapon attacks.
- **Disarm (`bDisarmed`)**: Rejects `melee_*`, `ranged_fire`, `ranged_burst`, and `reload` while preserving locomotion and casts.
- **Fear / Charm / Taunt (`bFeared`, `bCharmed`, `bTaunted`)**: Reuse authored walk/run locomotion cycles with autonomous destination override (fleeing away from target on Fear, slow approach with relaxed expression on Charm, aggressive approach toward target with `expr_anger` on Taunt).
- **Stasis (`bStasis`)**: Freezes animation timers, movement, and morph curves at the exact instantaneous pose (`StasisPose`) until released.

---

## 6. Event Marker Deduplication & Play-Rate Scaling (`0.5x – 1.5x`)

- Every clip maintains a 64-bit per-cycle `FiredMask` (`FMorphRigEventTracker`).
- Each marker (`foot_contact_l/r`, `melee_hit_start/end`, `muzzle_fire`, `reload_eject/insert/lock`, `cast_release`, `channel_ready/release`, `charge_ready/release`, `deploy_pickup/place/release`, `blink_vanish/appear`, `uplink_complete`, `respawn_ready`) fires **at most once** when `PrevTime < MarkerTime <= CurrTime`.
- Loop wraps reset `FiredMask` cleanly once per cycle; state interruptions clear the outgoing tracker without firing future unreached markers; `ActionPlayRate` scaling across **`0.5x` to `1.5x`** scales `DeltaSeconds` linearly without inventing duplicate hits or skipping markers.
