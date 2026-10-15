# MorphRig v1.2 — Animation State Machine, Layering & Priority Contract

## 1. Multi-Layer Evaluation Architecture

The runtime animation system (`UMorphRigAnimInstance` / `FMorphRigAnimInstanceProxy` in [`unreal/Source/MorphRig/MorphRigAnimInstance.cpp`](../unreal/Source/MorphRig/MorphRigAnimInstance.cpp) and `AMorphRigCharacter` in [`unreal/Source/MorphRig/MorphRigCharacter.cpp`](../unreal/Source/MorphRig/MorphRigCharacter.cpp)) evaluates seven coordinated pose & curve layers at 60+ FPS:

1. **Layer 1 — Base Full-Body & 8-Way Locomotion Layer**:
   * Evaluates either the active full-body action (`UAnimSequence`) or the 8-way directional locomotion blend (`walk_f/fl/l/bl/b/br/r/fr`, `run_f/fl/l/bl/b/br/r/fr`, `sprint_f`, `idle_combat`/`idle_relaxed`/`idle_wounded`) driven by 2D velocity and local movement angle.
   * **Arbitrary-Midpoint Crossfade**: Every base transition records the outgoing `PrevBaseSeq` and its exact current playback time `PrevBaseTime`, crossfading over `0.15s` without ever resetting the outgoing clip to frame 0.
2. **Layer 2 — Upper-Body Action Layer (`spine_01` and all descendant bones)**:
   * Layers upper-body combat and ability clips (`ranged_fire`, `ranged_burst`, `reload`, `cast_directional`, `cast_self`, `channel_start`, `channel_loop`, `channel_end`, `channel_interrupt`, `uplink_start`, `uplink_loop`, `uplink_end`, `uplink_cancel`) onto `spine_01..03`, `neck_01..02`, `head`, `clavicle_l/r`, and both arms while the lower body (`pelvis`, `thigh_l/r`, `calf_l/r`, `foot_l/r`, `ball_l/r`) continues locomotion uninterrupted.
3. **Layer 3 — 9-Point Calibrated Aim Offset Grid Layer**:
   * Computes additive bone rotation deltas relative to `aim_level_center` across the 9 calibrated grid poses (`aim_down_left`, `aim_down_center`, `aim_down_right`, `aim_level_left`, `aim_level_center`, `aim_level_right`, `aim_up_left`, `aim_up_center`, `aim_up_right`) driven by `AimYaw` (`[-75°, +75°]`) and `AimPitch` (`[-55°, +55°]`) toward the movable 3D `AimTargetActor`.
4. **Layer 4 — Additive Hit-Reaction Layer**:
   * Evaluates `hit_f`, `hit_b`, `hit_l`, and `hit_r` as an upper-body additive delta relative to `idle_combat` so impact reactions layer over standing or moving states without sliding or snapping planted feet.
5. **Layer 5 — Spoken Dialogue & Facial Performance Layer**:
   * Synchronizes the 436-frame `dialogue` action (facial bones + 11 viseme curves + 6 expression preset curves) to the playback clock of `dialogue.wav` on `DialogueAudioComp`.
6. **Layer 6 — Interactive Facial & Gaze Override Layer**:
   * Applies live gaze tracking (`eye_l`, `eye_r`), manual blink pulses (`blink_l`, `blink_r`), jaw opening (`jaw_open`), and expression preset switching (`expr_focus`, `expr_anger`, `expr_surprise`, `expr_pain`, `expr_joy_confidence`, `expr_concern_sadness`).
7. **Layer 7 — Ground Adaptation Layer (20° Slope & 20 cm Step IK)**:
   * Performs downward world traces from `foot_l` and `foot_r`, shifts `pelvis` vertically by `min(FootOffsetZ_L, FootOffsetZ_R)`, and applies analytic hip/knee flexion and ankle pitch alignment so feet plant cleanly on slopes up to `20°` and steps up to `20 cm`.

---

## 2. State Priority Matrix & Interruption Rules

Every animation state is assigned a deterministic priority level (`EMorphRigPriority`):

| Priority Level | Enum Name | Included Clips | Interruption & Blocking Rules |
| :--- | :--- | :--- | :--- |
| **0 (Lowest)** | `Locomotion` | `idle_*`, `walk_*`, `run_*`, `sprint_f`, `start_f`, `stop_f`, `turn_*`, `pivot_*`, `greet`, `victory`, `defeat`, `dialogue`, `aim_*` | Can be interrupted at any frame by any higher-priority state. |
| **1** | `JumpAir` | `jump_start`, `jump_air`, `jump_land`, `fall`, `land_heavy` | Chains `jump_start -> jump_air -> jump_land -> idle_combat`. |
| **2** | `CombatAbility` | `melee_1..3`, `ranged_fire`, `ranged_burst`, `reload`, `cast_*`, `channel_*`, `charge_*`, `deploy`, `uplink_*` | Supports arbitrary-midpoint interruption: interrupting `channel_loop` transitions from current `ActionElapsed` into `channel_interrupt`; interrupting `uplink_loop` transitions into `uplink_cancel`; interrupting `charge_hold` transitions into `charge_cancel`. |
| **3** | `EvadeDashBlink` | `dash_f`, `dash_b`, `dash_l`, `dash_r`, `blink_out`, `blink_in` | Cancels active `CombatAbility` states from their current midpoint. |
| **4** | `CrowdControl` | `stun_start`, `stun_loop`, `stun_end`, `sleep_start`, `sleep_loop`, `sleep_end`, `knockback` | Blocks all `Locomotion`, `JumpAir`, `CombatAbility`, and `EvadeDashBlink` requests (`PRIORITY_BLOCKED`) until `stun_end` / `sleep_end` finishes. |
| **5** | `Knockdown` | `knockup_start`, `knockup_air`, `knockdown_front`, `knockdown_back`, `prone_front`, `prone_back`, `getup_front`, `getup_back` | Overrides `CrowdControl` and lower states; blocks lower inputs until `getup_front` or `getup_back` completes. |
| **6 (Highest)** | `Terminal` | `death_front`, `death_back`, `dead_front`, `dead_back`, `respawn` | Overrides all other states. Once in `death_*` or `dead_*`, **all** non-respawn inputs are blocked (`PRIORITY_BLOCKED_BY_DEATH`) until `respawn` is triggered. |

---

## 3. Root Motion vs. Event-Driven Teleport Contract

* **Ground Dashes (`dash_f`, `dash_b`, `dash_l`, `dash_r`)**:
  * Authored with `root` bone displacement (`2.0 m` / `200 cm` horizontal travel over `0.40s`) and capsule tracking in `AMorphRigCharacter::UpdateDashAndBlinkMotion`, emitting `dash_start` (`0.03s`) and `dash_stop` (`0.36s`) events.
* **Blink Teleport (`blink_out` -> `blink_in`)**:
  * Authored **in-place** (`root` stays at `(0,0,0)`). At the `blink_vanish` event marker (`0.25s` at the end of `blink_out`), the host controller teleports the character actor `400 cm` forward (`SetActorLocation`), chains into `blink_in`, and emits `blink_appear` (`0.03s`).

---

## 4. Physical Prop Contact Contract (`reload` & `deploy`)

* **`reload` (`prop_cell`)**:
  * Normally attached to `cell_socket_r` on the right cybernetic forearm housing.
  * At `cell_eject` (`0.40s`, frame 12), `PropCellComp` switches attachment to `weapon_l` (left hand) as the left hand pulls the spent cell out and inserts the fresh cell.
  * At `cell_insert` (`1.35s`, frame 41), `PropCellComp` snaps back onto `cell_socket_r`.
* **`deploy` (`prop_beacon`)**:
  * At the start of `deploy`, `PropBeaconComp` attaches to `weapon_l` (left hand).
  * At `object_release` (`0.72s`, frame 22), `PropBeaconComp` detaches into world space and lands on the arena floor in front of the character.

---

## 5. Sync & Gameplay Event Markers

All markers are stored as Blender `PoseMarkers` on each Action (exported in `docs/animation_manifest.json`) and evaluated in `AMorphRigCharacter::EvaluateClipMarkers`:

| Event Marker Name | Clips | Purpose |
| :--- | :--- | :--- |
| `foot_l_contact`, `foot_r_contact` | All `walk_*`, `run_*`, `sprint_f`, `start_f`, `stop_f`, `turn_*`, `pivot_*`, `jump_land`, `land_heavy` | Left and right foot plant synchronization & footstep audio/VFX cues. |
| `hit_window_start`, `hit_window_end` | `melee_1`, `melee_2`, `melee_3` | Active forearm-blade damage frames. |
| `combo_window_open`, `combo_window_close` | `melee_1`, `melee_2`, `melee_3` | Input buffering window to chain `melee_1 -> melee_2 -> melee_3`. |
| `muzzle_flash` | `ranged_fire` (1x), `ranged_burst` (3x), `cast_directional`, `charge_release` | Wrist-emitter projectile/beam discharge timestamps. |
| `cell_eject`, `cell_insert` | `reload` | Hand-to-cell contact transfer timestamps (`cell_socket_r <-> weapon_l`). |
| `object_release` | `deploy` | Beacon detachment timestamp (`weapon_l -> world`). |
| `dash_start`, `dash_stop` | `dash_f`, `dash_b`, `dash_l`, `dash_r` | Root-motion burst start and recovery timestamps. |
| `blink_vanish`, `blink_appear` | `blink_out`, `blink_in` | Actor teleport vanish and arrival timestamps. |
