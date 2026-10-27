# Animation state contract

The 96 IDs in `animation_manifest.json` are the closed inventory. Facial presets and visemes are additional controls, not extra motion entries. All native sequences use the same `root`-based 70-bone skeleton. Source timing is 30 FPS; ordinary runtime interpolation does not change event semantics. Static entries retain one source key, with an identical export-only next-frame key for Unreal compatibility; the native pose is held rather than advanced as motion.

## Coordinates, speed and layering

- The Blender source is meter-based, Z-up, forward -Y, anatomical left +X. Unreal is centimeter-based and Z-up. The measured source-to-Unreal matrix is `[[0,-1,0],[-1,0,0],[0,0,1]]`, placing the body forward along actor +X with zero additional mesh yaw and unit scale. All 96 authored clips import directly onto the original reference skeleton. Only the root frame is aligned to that reference through the public animation-data-model API. Root translation is transformed by the measured inverse import-frame rotation, preserving nominal displacement; every other local bone channel is preserved. The four dash clips are translation-only: the native root track drives the swept capsule, with left = -Y and right = +Y, not an actor teleport or a post-hoc yaw correction. Measurements and socket bases are recorded in `skeleton_and_sockets.json`.
- Locomotion direction is relative to body facing, not camera facing. Walk, run and forward sprint use nominal speeds of 150, 400 and 650 cm/s. The controller adjusts travel speed and cycle/contact timing together rather than rotating a forward clip to imitate strafing.
- Nine aim samples form a yaw-left/right and pitch-down/up grid. Yaw left is +60 degrees, right -60; pitch up +35, down -35. Aim is an upper-body layer and must not rotate planted legs through the floor.
- The upper-body mask begins at `spine_03` and includes clavicles, arms, hands, fingers, neck/head, eyes and facial curves. It excludes root, pelvis and leg chains. Directional hit reactions use `idle_relaxed` frame zero as their additive reference and do not replace planted-leg motion. They are stored as rotation-offset mesh-space additives. Direct browser playback and outgoing cross-fades convert those deltas into complete local poses using the same reference; only the dedicated hit layer consumes the raw additive deltas.
- The global action-rate control is bounded to 0.5x–1.5x. Events remain tied to authored animation time. Changing speed cannot manufacture extra hits.

## State priority

Higher-priority states own the full-body output; lower-priority states cannot continue fighting for the same bones.

1. **Death**: overrides every nonterminal action, including cast, channel, charge, jump and reload. A living-to-dead transition occurs once. Further death requests while dead do not restart the clip.
2. **Respawn**: accepted only from dead. Restores a living, controllable idle and valid prop/attachment state. It is newly authored reconstruction, not reverse death playback or a Blink.
3. **Knockup/knockdown/prone**: forced incapacitation. Front/back selection is explicit and chooses the matching recovery.
4. **Stun/sleep/getup**: suppress normal actions until control returns. Sleep remains a living state with breathing. Stun remains stable and alive.
5. **Stasis**: holds the current evaluated pose and suppresses marker dispatch until released; it does not substitute for stun, sleep or knockup.
6. **Full-body actions**: melee, reload, deploy, knockback, starts/stops, turns/pivots, landing, greeting, victory, defeat and dialogue.
7. **Channel/Uplink/charge**: sustained action state with explicit entry, loop, finish and interruption.
8. **Travel/idle and upper-body overlays**: directional locomotion, aim, ranged attacks, directional cast and additive hits.

A lower-priority request is rejected without partially applying a contradictory full-body pose. An accepted higher-priority interruption starts from the currently evaluated action time and a short pose blend; it does not teleport to frame zero of the previous sustained clip. Full-body actions clear any active additive hit; hits remain available over locomotion and upper-body actions.

## Movement and interruption rules

| Action family | Movement rule | Interruption rule |
|---|---|---|
| Ranged fire/burst, directional cast | Upper-body over idle/travel; independent facing and aim | Ends after recovery; hit, incapacitation or death may override |
| Melee | Full-body; capsule travel locked until the documented recovery phase | Recovery marker re-enables travel; forced reactions/death override |
| Reload | Full-body contact sequence; travel locked | Forced reactions/death override; cell returns to the emitter on reset/respawn |
| Deploy | Full-body squat and beacon contact; travel locked | Forced reactions/death override; reset restores the attachment state |
| Charge | Start/hold/release/cancel are planted-foot states; no capsule-driven gait while holding | Release or cancel is valid from any held time; forced states cancel stored charge |
| Channel | Start/loop/end/interrupt use planted feet | Finish or interrupt at any valid point, with no return to the start pose |
| Uplink | Start/loop/end/cancel use planted feet | Cancel at any valid point; successful Blink is a separate later action |
| Jump/fall/landing | CharacterMovement controls capsule height; clips supply anticipation, airborne and compression poses | Death/incapacitation overrides; landing selects normal or heavy recovery |
| Dash | Root motion drives a swept CharacterMovement capsule, nominally 200 cm | Collision can truncate actual travel; death/incapacitation cancels remaining drive |
| Blink | Anticipation/plant clips contain no actor displacement | Teleport is a single event at the marked phase, followed by a ground-valid placement |

Root/disable prevents translation while retaining eligible upper-body actions. Silence suppresses casts, channel, charge, Uplink and Blink. Disarm suppresses emitter fire, blade melee and reload. Death and forced incapacitation take priority over all three disables.

## Sustained actions

- **Channel:** `channel_start` → `channel_loop` → `channel_end`, or any valid phase → `channel_interrupt`. The loop has restrained motion rather than a frozen body. Completion and forced interruption are distinct.
- **Charge:** `charge_start` → `charge_hold` → `charge_release`, or `charge_hold` → `charge_cancel`. Release time is not fixed to the end of a hold.
- **Uplink:** `uplink_start` → `uplink_loop` → `uplink_end`, or `uplink_cancel`. The feet stay planted throughout the loop. A later teleport is not embedded in the Uplink.

The controller retains the outgoing action and its current time during the fade. Repeated end/cancel requests in the same phase do not emit duplicate transition events. Unreal's per-evaluation object cleanup releases engine references without clearing playback state, fades or event traversal. Masked blends explicitly assign the current output pose into their base context; the installed pose-context copy constructor does not itself copy the pose.

## Incapacitation and recovery

`knockdown_front` and `death_front` end in their authored face-down poses; `knockdown_back` and `death_back` end in face-up poses. `dead_front` and `dead_back` exactly match their corresponding death endpoints, including facial values. `getup_front/back` select the correct floor family and use supporting contacts rather than a vertical mesh translation.

`knockup_start/air` is involuntary and distinct from `jump_start/air`. `stun_start/loop/end` remains alive. `sleep_start/loop/end` is a separate sustained living state. Death during a jump or sustained action cancels that action's pending gameplay events before entering the death clip.

## Root motion and contacts

Only `dash_f/b/l/r` have the `root_motion` policy. Their source root translates exactly 2 m. The mesh does not use an additional actor translation for the same distance. The controller extracts root motion for the elapsed clip interval and sweeps the capsule; it does not simply slide the mesh away from the capsule.

In-place locomotion, turns, pivots and action clips do not supply actor travel. Turn/pivot foot placement and their single facing-commit event establish the new facing. Blink displacement is an event, never baked travel. Nominal travel speed and root policy are explicit for every manifest entry.

Grounded movement uses CharacterMovement for capsule-compatible 20 cm steps and a 20-degree ramp. Before foot IK, a nonpositive mesh-relative vertical offset is interpolated toward the supported floor hit minus the capsule bottom, compensating the engine's floor margin so authored ground contacts meet the actual floor. The offset releases smoothly while airborne; the capsule and source scale are unchanged. Foot placement traces on the game thread and bounded two-bone IK/normal adjustment are applied only in appropriate grounded states. Targets are limited to the room floor, ramp and steps, with a ±12 cm search grid and a 20 cm height/pelvis bound. A candidate more than 3 cm above the resting ankle height is treated as an intentional swing foot and is not pulled down. Dashes, knockback, get-up recovery, airborne, prone, sleeping and dead poses use their authored contacts rather than this solver. Contact targets reset on clip changes and large actor moves/turns. Pelvis reach is computed from the current evaluated pose, propagated through the hierarchy before solving, and bounded to 20 cm downward. This is room-specific support, not arbitrary rough-terrain behavior. The three-bone cable is bounded and bakeable; a ragdoll is not substituted for authored recovery or death clips.

## Props and markers

The right forearm carries the emitter and attached blade; the cell and beacon have stable skeleton attachments and authored contact transforms. The left hand performs cell manipulation and beacon placement. Reload events are `CellGrip`, `CellDetach`, `CellSeat`, `CellRelease`; deployment uses `DeployGrip`, `DeployContact`, `DeployRelease`.

At `DeployContact`, the authored beacon is on the room floor and the fingers reach it. `DeployRelease` places a `UStaticMeshComponent` containing the beacon-only subset of the authored geometry and UVs at the evaluated socket transform, hides the original skinned beacon, and leaves that independent prop in the world while the body recovers. No replacement mesh, skeleton or material is used. Reset, respawn and a new deployment hide the released copy and restore the stowed beacon. The source action retains the beacon on the floor through its end. Deployment is authored for the level showcase floor, not arbitrary terrain placement.

Named event data covers melee contact windows, each muzzle event, reload handoffs, deployment, casts, charge/channel transitions, Uplink, foot plants/releases, facing commits, teleport phases and death/respawn. Burst markers have payload indices 1, 2 and 3. Melee has explicit `MeleeWindowBegin`, `MeleeWindowEnd` and `Recovery` markers.

Runtime event dispatch uses the active action instance, authored event identity and loop cycle. An event fires at most once per crossing even if a fade, loop, rate change or interruption spans multiple evaluation paths. An interrupted action cannot leave an active melee hit window behind. Marker name, time, speed and current state are visible in the showcase and in the deterministic `MR_STATE`/`MR_EVENT` trace.

## Facial and audio control

Clip curves drive the imported morph targets. The control panel can override each left/right facial control and each viseme independently, including explicit zero weights. Six expression presets plus neutral are available without changing the skeleton. Eye bones have independent gaze controls.

`dialogue` owns the authored body/face performance and plays `Dialogue.wav` from its speech-start transition. The transcript and measured alignment accompany the source. Gaze, blinks, emotional change, lip-closure, labiodental, vowel, rounded/funnel, tongue-to-teeth and consonant shapes are part of the performance; jaw movement alone is not accepted as speech.

## Verification

`docs/validation/` contains source, import and runtime evidence. `unreal_import_audit.json` records imported skeletons, LODs, morphs, timing and event assets. The packaged `-MorphVerify` route exercises all named clips and representative combined states; `-MorphDemo=states` prints the deterministic combined-state trace. Actual rendered presentation captures and performance logs are separate from these machine checks.

Capture and demo modes explicitly advance the native animation controller by 1/30 second per engine tick, so screenshot cost does not change authored clip timing or the number of rendered frames. Normal interactive playback and the benchmark use real elapsed time. The close-up presentation uses the original `dialogue.wav` at its source timing when encoding; it is not a pitch-shifted or time-stretched replacement voice.
