# MorphRig animation state contract (Unreal runtime)

Implementation: `unreal/Source/MorphRig/` – `AMorphOperative` (state machine, layers, events, IK inputs) and
`UMorphAnimInstance` / `FMorphAnimProxy` (native pose evaluation, no AnimGraph). Clip table:
`Content/MorphRig/Data/clips.json` (generated from the manifest). All clips are 30 fps; playback interpolates.

## Layers (evaluated every frame, in this order)
1. **Base (full body)** – a blend stack. Entries cross-fade (new entry fades in, older ones fade out); an entry
   is either one clip or the *locomotion node*.
   * Locomotion node: idle (`idle_relaxed` / `idle_combat` / `idle_wounded` by stance) + the two nearest of the
     eight directional cycles for walk and run (+ `sprint_f`), all sampled at one shared normalised phase.
     Direction = velocity relative to body facing (facing is independent: it follows the aim point in strafe
     mode). Gait weights from speed (150 cm/s walk, 400 run, 650 sprint); cycle frequency follows the controller
     velocity so contacts stay in sync at any speed.
2. **Upper body** – `ranged_fire`, `ranged_burst`, `reload`, `cast_directional` while moving, blended on the
   spine_01 (35 %) → spine_02 (70 %) → spine_03-and-children (100 %) mask. Legs keep the base.
3. **Aim** – bilinear blend of the nine calibrated aim samples (yaw -60/0/+60, left positive; pitch -35/0/+35,
   up positive) on the spine_02-and-up mask while aiming (RMB / L). Clamped to the grid.
4. **Additive** – directional hits (`hit_f/b/l/r`, local-space additive, base = frame 0) on top of anything
   except Dead / Down / Respawn; face control poses (`ctl_*`) and gaze poses.
5. **Look-at** – head/neck (40/60 %) toward the camera or aim point when idle, ±70° yaw, ±40° pitch.
6. **Ground adaptation** – per-foot traces, pelvis lowered by the lower foot, two-bone IK per leg with sole
   alignment to the ground normal (slopes ≤ 20°, steps ≤ 20 cm). Faded out while airborne or lying.
7. **Face** – morph curves from the clip (dialogue lip sync, expressions) + face-panel overrides.

## States and priorities
Higher priority interrupts lower; equal priority may replace; lower requests are ignored while a higher state
runs. `Locomotion`, `Transition`, `Emote`, `Dialogue` and `Preview` are always interruptible.

| State | Prio | Clips | Exit |
|---|---|---|---|
| Locomotion | 0 | locomotion node | – |
| Transition | 5 | `start_f` (→ walk at exit phase 0.516), `stop_f`, `turn_l90/r90` (idle facing change > 60°), `pivot_l180/r180` (reversal > 140° while moving, non-strafe) | clip end, actor yaw applied at the end |
| Airborne | 10 | `jump_start` → launch on `takeoff` event → `jump_air` → `fall` after 0.75 s → `jump_land` or `land_heavy` (air > 0.9 s or v > 950 cm/s) | landing clip end |
| Emote / Dialogue | 12 | `greet`, `victory`, `defeat`, `dialogue` (+ audio, starts on frame 0) | clip end |
| Preview | 14 | any clip from the browser | Enter / Resume |
| Action | 20 | `melee_1` → `melee_2` → `melee_3` (a queued click hands over at 55 % of the clip, never before the clip's `hit_end`), `cast_*`, `deploy` | clip end |
| Channel | 20 | `channel_start` → `channel_loop` (held) → `channel_end` on release; `channel_interrupt` on X, a hit, or any higher state | clip end |
| Charge | 20 | `charge_start` → `charge_hold` (held) → `charge_release` on release (any time, even during start); `charge_cancel` on C | clip end |
| Uplink | 20 | `uplink_start` → `uplink_loop` → `uplink_end` after 2.6 s held; `uplink_cancel` if released early or hit | clip end |
| Dash | 25 | `dash_f/b/l/r` from input direction; **root motion** (2 m) moves the capsule | clip end |
| Blink | 25 | `blink_out` → actor teleport 5 m on the `blink_teleport` event → `blink_in` | clip end |
| Knockback | 40 | `knockback`; the host launches the capsule backward (travel is not baked) | clip end |
| Stun, Sleep | 50 | `stun_start/loop/end` (3 s); `sleep_start/loop/end` (N again or 7 s) | end clip |
| Knockup, Down | 60 | `knockup_start` (launch) → `knockup_air` → on landing `knockdown_back`; `knockdown_front/back` → `prone_front/back` (3.2 s) → `getup_front/back` | getup end |
| Respawn | 90 | `respawn` (props restored) | clip end → Locomotion |
| Dead | 100 | `death_front/back` → held `dead_front/back` (exact last frame of the death clip) | only Respawn |

Rules:
* **Death** overrides every state (also airborne, casting, channelling), clears additive layers and happens
  once; further death requests are ignored until respawn.
* **Front/back choice**: a hit from the front throws the body backward → `knockdown_back` / `prone_back` /
  `getup_back`; from behind → the `_front` set. Death uses the impact side (`death_front` = front impact).
* **Movement rules**: locomotion, upper-body actions and aim allow travel. Melee, casts ground/self, channel,
  charge, uplink, deploy, stun, sleep, down, dead, emotes and dialogue keep the feet planted (controller
  velocity is braked to zero). Dash / knockback / knockup / blink move the capsule themselves.
* **Interruption** never resets a clip to its first frame: the interrupting clip cross-fades from the current
  pose (blend stack), including mid-`channel_start` or mid-`charge_start`.
* **Hits while moving** are additive, so feet stay synced with locomotion.
* **Contradictory full-body states** cannot fight over bones: only one base state owns the base layer; upper-body
  and aim layers are masked and faded out on entering any non-locomotion state.

## Events
Blender pose markers are imported as `UMorphEventNotify` notifies (track "Morph"). The controller dispatches
them itself: only the newest (primary) slot of a layer fires, each marker fires once per crossing of its time
(loops handled by wrap), fading-out or interrupted slots never fire, so blends, loops and interruptions cannot
duplicate events. Rate scaling (`[` / `]`, 0.5–1.5×) only changes playback speed; events are still crossings
of authored times, so no hits are invented. Events with runtime effects: `takeoff`, `blink_teleport`,
`beacon_release`, `muzzle_fire*`, `cast_release`, `charge_release`, `channel_pulse`, `hit_start`. All events are
shown in the HUD log and written to the sequence trace.

## Deterministic showcase sequence
F9 (or `-MorphSequence [-MorphExit]`) runs a fixed 108 s script with a fixed 1/60 s step covering locomotion,
transitions, jump, dash, melee combo, layered fire / burst / reload while walking, casts, channel interrupted
by a hit, charge release and cancel, deploy, uplink, blink, hit while running, stun, knockback, knockdown
front, knockup → back, sleep, death during a cast, ignored second death, respawn, death while airborne,
respawn, greet, dialogue and victory. The trace (`time, state, clip, trace, speed`) is written to
`Saved/Logs/MorphRig_Trace.txt`.
