# MORPHRIG — Animation state contract

This document is the contract between the authored motion (Blender) and the
runtime (Unreal). It describes every delivered clip, the layer it belongs to,
the state it enters and leaves, the events it raises and how the runtime
picks a clip.

The machine readable version of this document is
`docs/animation_manifest.json`; the same rows are loaded into the Unreal
data table `/Game/MorphRig/DT_MorphRigClips` (row struct `FMorphRigClipEntry`).

---

## 1. Global conventions

| Property | Value |
|---|---|
| Authored frame rate | 30 fps (all clips) |
| Clip range | frame 1 … N, inclusive |
| Length | `N / 30` seconds |
| Sample rate in Unreal | 30 |
| Units | centimetres in Unreal, metres in Blender |
| Forward | -Y in Blender, +X in Unreal |
| Root bone | `root`, one per skeleton, independent from `pelvis` |
| Root motion | only the four dash clips translate `root`; everything else is in place |

Every clip bakes **all 71 deform bones on every frame**. Bones that a clip
does not use are baked at identity, so a clip can always be blended over
another clip without a pop. Face shape keys are baked on the same action
(`ACT_<clip>_face`) and travel to Unreal as morph target curves.

## 2. Layers

| Layer | Count | Blend | Description |
|---|---|---|---|
| `FullBody.Idle` | 6 | base | standing and combat idles, breathing |
| `FullBody.Locomotion` | 28 | base | walk / run / strafe in eight directions |
| `FullBody.State` | 20 | base | jump, fall, land, charge, channel, cast, blink |
| `FullBody.Action` | 22 | action | melee, ranged, reload, deploy, interact, greet |
| `FullBody.RootMotion` | 4 | base | `dash_f`, `dash_b`, `dash_l`, `dash_r` |
| `UpperBody.Aim` | 9 | aim | the calibrated aim grid |
| `Additive.HitReaction` | 4 | action | hit reactions, played as an overlay |
| `FullBody.Teleport` | 2 | base | blink and blink_strafe |
| `FullBody.Performance` | 1 | base | `dialogue`, the spoken performance |

The runtime composes three of them:

* **base layer** — the body state. Exactly one base clip is active.
* **action layer** — a one shot action blended over the base clip with a
  weight that ramps in and out. Additive hit reactions are played here as
  an overlay because the runtime graph cannot use UE additive sequences.
* **aim layer** — the nine aim poses, blended onto the **upper body only**.
  The mask starts at `spine_01`, so the legs stay planted while the torso,
  arms and head track the aim direction.

## 3. States

The Unreal side exposes `EMorphRigState` with the values `Idle`,
`Locomotion`, `Jump`, `Fall`, `Land`, `Dash`, `Blink`, `Attack`, `Cast`,
`Channel`, `Charge`, `Hit`, `Disabled`, `Death`, `Respawn`, `Performance`.

Each clip declares an entry state and an exit state. The runtime uses them
to validate a transition and to print the state trace.

| Entry state | Clips |
|---|---|
| `Ground` | all idles, locomotion, dashes, most actions |
| `Air` | `jump_up`, `fall`, `land` |
| `Combat` | `idle_combat`, the aim grid, the action layer |
| `Down` | `death_*`, `hit_*` |
| `Performance` | `dialogue` |

## 4. Event markers

Markers are baked into the action as pose markers and are listed in the
manifest as `[name, frame]`. The Unreal side reads them from the data table
and fires them from the clip time, so the trace is deterministic and does
not depend on FBX notify import.

| Marker | Fires on | Meaning |
|---|---|---|
| `footstep_l`, `footstep_r` | locomotion | foot plant, play the footstep sound |
| `dash_start` | `dash_*` | root motion begins, the capsule starts to move |
| `dash_end` | `dash_*` | root motion ends, the capsule is released |
| `hit_*` | melee, ranged | the attack connects |
| `charge_start`, `charge_end` | charge | the effect starts and stops |
| `cast_start`, `cast_end` | cast | the effect starts and stops |
| `blink_start`, `blink_end` | blink | the teleport window |
| `death_start` | `death_*` | the character is dead |
| `respawn_start` | `respawn` | the character is back |
| `speech_start`, `speech_end` | `dialogue` | the spoken line |

## 5. Root motion policy

| Clip group | Root motion | Effect on the capsule |
|---|---|---|
| `dash_f`, `dash_b`, `dash_l`, `dash_r` | 2.0 m nominal | the capsule is driven by the clip |
| everything else | in place | the capsule is driven by the player input |

Unreal 5.8 no longer has a `MOVE_RootMotion` movement mode. While the
animation produces root motion, `UCharacterMovementComponent` keeps the root
motion velocity instead of recomputing it from the input, so the dash moves
the capsule exactly as authored. The dash clips are therefore played on the
**base** layer, not on the action layer, so the pose and the displacement
come from the same sequence.

The imported dash sequences have `enable_root_motion` set, all other
sequences keep the Unreal default.

## 6. Clip selection at runtime

```
if state == Performance          -> dialogue
else if a dash is running        -> dash_<direction>
else if a one shot action runs   -> action layer over the base clip
else if the player is aiming     -> aim grid pose on the aim layer
else                             -> locomotion or idle on the base layer
```

Locomotion selection uses the local movement vector:

| Condition | Clip |
|---|---|
| speed < 10 cm/s | `idle_neutral` or `idle_combat` |
| speed < 250 cm/s | `walk_<dir>` |
| speed >= 250 cm/s | `run_<dir>` |

`<dir>` is `f`, `b`, `l`, `r`, `fl`, `fr`, `bl`, `br`.

## 7. Deterministic showcase sequence

The showcase sequence is a fixed table of steps with fixed durations, so two
runs produce the same trace. It is started and stopped with the `Showcase`
action.

| # | State | Clip | Duration | Aim layer |
|---|---|---|---|---|
| 1 | Idle | `idle_combat` | 2.0 s | no |
| 2 | Locomotion | `walk_f` | 2.5 s | no |
| 3 | Locomotion | `run_f` | 2.0 s | no |
| 4 | Aim | `aim_level_center` | 1.5 s | yes |
| 5 | Aim | `aim_up_left` | 1.5 s | yes |
| 6 | Attack | `melee_1` | 1.2 s | no |
| 7 | Attack | `ranged_fire` | 0.8 s | no |
| 8 | Cast | `cast_directional` | 1.2 s | no |
| 9 | Charge | `charge_start` | 1.0 s | no |
| 10 | Channel | `channel_start` | 0.8 s | no |
| 11 | Channel | `channel_loop` | 2.0 s | no |
| 12 | Hit | `hit_f` | 0.8 s | no |
| 13 | Dash | `dash_f` | 0.8 s | no |
| 14 | Blink | `blink_out` | 0.6 s | no |
| 15 | Death | `death_front` | 2.5 s | no |
| 16 | Respawn | `respawn` | 2.0 s | no |

The trace is written to the Unreal log through the `LogMorphRig` category
and is also listed on the HUD:

```
showcase start steps=16
showcase step=1 state=Idle clip=idle_combat
showcase step=2 state=Locomotion clip=walk_f
...
showcase step=15 state=Death clip=death_front
```

The aim steps drive the **base** layer with the aim pose and enable the aim
overlay, the other steps play on the action layer.

## 8. Spoken performance

`dialogue` is 450 frames (15.0 s). The recorded line is 12.533 s long and
the alignment file `source/audio/dialogue_alignment.json` holds 33 words
with their absolute start and end times inside that window.

The clip maps its normalised time onto the alignment window with
`alignment_time = t * 15.0`, so the lip shapes follow the audio exactly
while the line is spoken, and the last 2.47 s are a settle of the body
acting.

* audio: `source/audio/dialogue.wav` (12.533 s, 22 050 Hz mono)
* transcript: `source/audio/dialogue_transcript.txt`
* alignment: `source/audio/dialogue_alignment.json`

The line is original:

> Command, this is Operative Seven. The relay is patched and the perimeter is
> clear. I am moving to the extraction point now. Keep the channel open. Stay
> off the grid until I confirm.
