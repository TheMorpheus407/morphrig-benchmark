# Runtime animation and event contract

The showcase uses `UMorphAnimInstance` and its native animation proxy. It evaluates the imported, compressed `AnimSequence` assets from `animation_manifest.json`. The full source lives in `unreal/Source/MorphRig`. Blender is authoritative for motion and facial curves; the runtime adds blending, bounded terrain correction, actor travel and interaction state.

## Evaluation order

1. Velocity chooses eight walk or run directions in the actor's facing coordinates. Walk, run and forward sprint reference speeds are 150, 400 and 650 cm/s. Phase is preserved when switching travel clips, with a 0.16 s crossfade. Playback scales with measured velocity independently of the action-rate slider, preserving travel contact at 0.5x and 1.5x action rates. Starts, stops, stationary quarter turns and reversal pivots enter their authored clips.
2. The nine aim poses interpolate across yaw −60/0/+60 and pitch −35/0/+35. Negative yaw is the character's left; positive pitch is up. The blend mask starts at `spine_01`, preserving locomotion on the legs.
3. An action blends in over 0.12 s. Upper-body actions preserve travel. A replacement action blends from the interrupted action's actual current pose. The outgoing sequence stops advancing, so unexecuted outgoing markers cannot fire after interruption. Completed actions fade into travel.
4. Directional hits add their local rotational displacement relative to that hit clip's own first frame, restricted above the pelvis. This preserves the planted lower body.
5. Two-bone leg correction adapts ankle height and orientation to the traced support surface. Ground offsets reference the mesh ground plane, preserving authored swing clearance. A bounded pelvis shift supports unequal foot heights. Full-body airborne, floor, recovery and terminal clips retain their authored contacts. The room ramp is 20 degrees; each stair rise is 20 cm.
6. Independent eye offsets are applied locally. Face shapes sample the staged authored facial curves in clip seconds and combine with the inspection controls. The dialogue action sets playback to 1x, matching its audio.

## Priority and transitions

Death has priority 100 and rejects repeated deaths. The matching dead pose holds. Explicit respawn bypasses terminal priority, cleans deployed attachments, and restores a living state. Knockup/knockdown/prone/getup have priority 80, stun 70, sleep 60, jump/fall/landing 50, sustained actions 30, other actions 20. Hit reactions are a separate upper-body additive layer. Lower-priority user requests cannot replace a higher-priority full-body state.

`channel_start → channel_loop`, `charge_start → charge_hold`, and `uplink_start → uplink_loop` advance automatically. Enter finishes/releases; X interrupts/cancels from either entry or sustained motion. Each path has an authored exit. Stun and sleep hold until Enter/X requests their recovery. Front/back knockdowns choose their matching prone and getup clips. Death during a cast or jump interrupts the action once. Respawn is a distinct authored action.

Movement is allowed during travel, jump/fall, start/stop and explicitly marked upper-body actions such as ranged fire and directional cast. Melee, reload, charge, channel, Uplink, deployment and full-body disables lock translation until their action or exit completes. Root prevents translation while allowing eligible upper-body actions. Silence suppresses casts/channel/charge; disarm suppresses ranged and melee. Applying silence enters the authored interrupt/cancel exit for a live channel or charge. Applying silence to a single cast, or disarm to an attack, invalidates its remaining markers and fades its frozen outgoing pose. Root blocks voluntary dash, blink and jump requests and stops current controller travel. Fear travels away, charm travels toward the target, and taunt redirects attention; these movements obey translation locks and are cleared by death. Stasis freezes the current pose, controller travel, animation clocks and speech audio.

Browser selection resets to a clean character and previews any of the 96 clips in full-body mode. Loops repeat; one-shots and poses hold their final frame. Reset exits preview. Keyboard movement also exits a locomotion-compatible preview.

## Root motion, props and markers

Root-motion dash displacement is extracted from the imported root track and applied to the collision capsule. Root translation is removed from the displayed pose; the mesh stays centered on the capsule. Other travel is controlled in centimeters by the character movement component. Blink executes one guarded translation at `blink_teleport`; its exit cannot execute a second teleport. Turns and pivots author pelvis rotation and commit actor facing at completion.

The manifest supplies event names and times. Imported sequences also contain native `UMorphMarker` notify objects on their `MorphRig` track. Runtime event execution uses a generation, loop and marker identity, advancing through actual clip time. Changing playback rate changes the crossing time without creating extra attacks. Interruptions invalidate the old action's future markers. Current event name and timing appear in the panel and the trace.

Cell manipulation is baked on the `cell` bone, including grip, extraction, insertion and release. Beacon motion follows its authored bone until `beacon_release`; the exact authored standalone beacon mesh is placed at that world transform and the equipped bone is hidden. Reset/respawn restore the equipped presentation. The emitter muzzle and blade anchors are authored skeleton bones. Marker flashes make muzzle/contact timing visible without adding combat logic.

## Reproducible inspection

F9 executes the scripted combined-state sequence: moving burst, moving hit/cast, interrupted channel, charge release, interrupted Uplink, reload, deploy, root-motion dash, death during jump, held death, respawn, knockdown/recovery, blink, slow/fast melee and stun recovery. Every state and event is logged. The browser, action buttons and individual facial controls remain available for focused inspection. Source controls support 0.5x–1.5x action rate; speech playback uses 1x.

The code is native portable Unreal C++; no runtime editor module, OS-specific input handler or external runtime animation service is required.
