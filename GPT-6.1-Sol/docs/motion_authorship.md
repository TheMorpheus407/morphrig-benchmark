# Authored motion source

All 96 required entries are authored in `source/generators/motions.py` for
this Operative. It contains analytical directional gaits, a complete set of
intentional action/contact key poses, procedural breathing and secondary
curves, the nine calibrated aim poses, exact held death endpoints, and the
word/phoneme-driven speech performance. There are 85 moving entries and 11
static entries. No downloaded motion, stock character, motion capture,
retargeted third-party clip, or external generative service is used.

`pose_at(id, seconds, duration)` returns absolute wrist/ankle targets and a
separate pelvis/root pose in Blender metres. Forward is −Y, right +X, up +Z.
Targets already include facing rotation; the baker applies dash root
translation uniformly to the body and all targets. In-place entries have
exactly zero root translation. All four dash roots move a nominal 2 metres.
Blink root translation stays zero; its disappearance/teleport/reappearance
markers belong to the actor controller.

Each motion has its own preparation, active phase and recovery or sustained
state. The three blade strikes have separate diagonal, reverse/upward and
overhead finishing paths. A three-shot burst contains three recoil cycles.
Channel completion relaxes and lowers the emitter; forced interruption
recoils asymmetrically. Charge release transfers weight into an extension;
cancel safely vents and folds inward. Uplink completion acknowledges success;
cancel withdraws and restores attention. Knockup is a helpless backward
arch/flail distinct from voluntary jumping. Sleep uses a supported seated
posture. Respawn activates a folded living stance, scans, opens the hands
and settles independently of either death trajectory.

Face-down falls progress through knees and palms to a floor pose. Face-up
falls lose balance backward, catch on one arm and settle on the back.
The two getups use different supporting palm, knee, seat and foot phases.
Their death variants commit once and settle into their corresponding exact
`dead_front`/`dead_back` poses. Prone states retain subtle life motion;
terminal poses intentionally hold without breathing.

The eight walk/run directions retain body facing. During every planted
phase, foot target velocity is exactly the negative nominal controller
velocity: 150 cm/s walk, 400 cm/s run, 650 cm/s sprint. The capsule's travel
therefore cancels the target's relative movement. Lateral and diagonal
returns route feet around separate fore/aft tracks; arm asymmetry preserves
the cybernetic side. Running folds and pumps the arms, has shorter support
and higher airborne heel return; sprint adds full-effort forward lean and
flight. Pelvis height analytically follows the most extended supported leg
without modifying the planted trajectories or nominal speed.

The source joint transforms mirror the actual fitted skeleton. Every
30 FPS wrist and ankle target fits the source bone lengths. Prop grasp
targets use a geometric closed-hand anchor with individual finger curls.
During reload the organic hand remains on the animated cell until insertion
and release; the emitter stays on the cybernetic arm. During deploy the
beacon follows that same grasp until ground placement. Outside manipulation,
the cell/beacon targets are omitted and their rig sockets own attachment.
The deployed beacon center is 0.045 metres above the floor, placing its
base at approximately 0.004 metres.

`entry_metadata(csv_row)` supplies exact 30 FPS frame intervals, inclusive
sample counts, loop flags, speed, layer, entry/exit states, priority and
frame-quantized events. Static poses have two identical samples to support
Unreal import. The nine aim samples use yaw −60/0/+60 degrees and pitch
−35/0/+35 degrees; yaw is positive toward character right and pitch positive
up. Their legs and pelvis remain stable while torso, wrists and gaze aim.

Hits are an upper-body additive layer referenced to the neutral skeleton;
the runtime preserves the current base locomotion's leg pose. Ranged
shots/bursts and directional casts are upper-body actions. Melee, reload,
charge, channel, deploy and Uplink own their full-body stance. Runtime
interruptions blend from the captured evaluated pose into the interrupt
curve and preserve base support rather than restarting the source stance.
The animation controller owns event-instance deduplication, priorities,
capsule movement, slope/step IK, and action-rate playback; its exact native
contract is documented in `animation_state_contract.md`.

Run the focused source audit:

```bash
python3 -B source/generators/motions.py
```

`docs/motion_validation.json` records finite inventory coverage, exact
durations/events, distinct sampled curves, clean loop boundaries, terminal
pose equality, root policies/displacement, every-frame limb reach, grasp
anchor equality and analytical support velocity. This data audit is
complemented by the production pipeline's Blender/Unreal deformation,
contact and rendered inspection.

Speech/tool provenance for the third-party manifest: the transcript,
performance curves and delivered synthetic audio are original work. Local
eSpeak NG 1.52.0.1 supplies its built-in `en-us` synthetic voice through Nix;
the synthesis tool is GPL-3.0-or-later and is a build dependency. No external
voice model, recording or speech engine binary is redistributed with the
asset.
