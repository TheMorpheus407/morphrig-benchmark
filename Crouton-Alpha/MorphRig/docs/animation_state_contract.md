# Animation State Contract (MorphRig)

All 96 entries (85 motion + 11 pose) map 1:1 in `docs/animation_manifest.json`:
45% locomotion/turn/transition, 25% attack/cast/channel/charge, 15% hits/disables/recovery, 15% stun/knockdown/sleep/death/respawn/behavioral. See csv for authoritative forms.

## States & transitions (C++ `MorphRigAnimInstance` + `MorphRigCharacter`)
- Base locomotion: idle/walk/run/sprint/start/stop/turn/pivot/jump/fall/land; blends on `MoveAngleDeg` (8 dirs, facing independent).
- Upper-body layer: ranged/casts/aim; melee/reload/charge/channel use documented movement rules (melee/reload stop or slow move; ranged/casts allow moving; channel/charge freeze root except `charge_hold`).
- Arm IK/FK + pole vectors (Blender Control rig); UE: IK solvers assist foot planting on ≤20° slopes / ≤20 cm steps.
- Additive hits (`hit_f/b/l/r`) layer over base motion; cannot displace planted feet.
- Channel/Uplink: start -> loop -> end; `channel_interrupt`/`uplink_cancel` reachable from any point, no snap-back to pose 1.
- Charge: start -> hold -> release; `charge_cancel` safe abort.
- Stun/sleep/knockup/knockdown/getup/prone/death have explicit priorities: Death > Prone/Knockup > Stun/Sleep > Action > Locomotion. Death occurs once (override), respawn restores living stance.
- Hit-while-moving: additive layer; Death-during-cast/jump: Death override wins.
- Dash is root motion (2 m nominal, capsule driven). Blink applies teleport event (not baked displacement).
- Aim grid: yaw -60/0/+60, pitch -35/0/+35 (9 poses), upper-body only, legs planted.
- Slopes/steps: ground contact + ankle IK; no floating pelvis.
- Playback 0.5x-1.5x (`SetPlaybackSpeed`).

## Events (anim notifies, emitted once per pass, safe under blend/interrupt/stretch)
- `melee_*`: hit_start/hit_end/recovery markers.
- `ranged_fire`: muzzle. `ranged_burst`: muzzle_1/2/3.
- `reload`: handoff / insert. `deploy`: attach / release.
- `cast_*`: release. `channel_start`: channel_enter; `channel_end`: channel_release; `channel_interrupt`: interrupt.
- `blink_out`: teleport_out; `blink_in`: teleport_in.
- `walk/run`: contact_L/R; `dash_*`: contact; `jump_land`: contact.
Markers listed per-clip in `animation_manifest.json` (frame + seconds).
