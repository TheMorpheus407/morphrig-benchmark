# MORPHRIG showcase - controls and command reference

The showcase is the packaged client `build/Linux/MorphRig.sh` (start it with `tools/run_showcase.sh`). The same
list is available in the application: **F1** (overlay) and the **Help** tab of the panel (**F2**).
Nothing in this document requires a source change: every required state can be reached with a key, a panel
button or a console command.

## 1. Keyboard and mouse

| Group | Input | Action |
|---|---|---|
| Move | `W A S D` | move relative to the camera (eight directions) |
| | `Left Shift` | sprint (forward travel only, not while aiming or wounded) |
| | `Left Ctrl` | walk |
| | `M` | toggle strafe/aim mode (facing follows the aim point, default) and travel mode (facing follows the travel direction; uses `start_f`, `stop_f`, `pivot_*`) |
| Aim | mouse | aim point on the floor plane, lifted by the aim height |
| | mouse wheel | aim height (aim pitch). While dragging a target: target height. In orbit view: zoom |
| | `RMB` (hold) | raise the emitter arm (aim stance) |
| | `Tab` | lock the aim on the next movable target / release the lock |
| | `LMB` on a target | select and drag the target on the floor |
| Act | `LMB` | fire one shot |
| | `B` / `R` | three-shot burst / reload |
| | `F` | melee; press again inside the combo window to chain `melee_2`, `melee_3` |
| | `Space` | jump |
| | `Q` | dash in the held `W A S D` direction relative to the facing (no direction = forward) |
| | `E` | blink to the cursor (max 6 m) |
| Cast | `1` `2` `3` | directional cast / ground cast at the cursor / self cast |
| | `C` (hold) | channel: press = start, release = normal finish |
| | `G` (hold) | charge: press = start, release = fire with the reached charge level |
| | `X` | **interrupt** the channel / cancel the charge / cancel the uplink |
| | `T` / `U` | deploy the beacon / start the uplink (completes after 3 s, then blinks to the spawn point) |
| Hits | `7` `8` `9` `0` | additive hit from front / left / back / right |
| | `4` `5` `6` | stun 2 s / sleep 5 s (any hit wakes) / knock-back |
| | `-` | knock-up (lands in `knockdown_back`, then gets up) |
| | `[` `]` | knock-down from a front hit (`knockdown_back`) / from a back hit (`knockdown_front`) |
| Life | `K` / `L` | death from a front hit (`death_front`) / from a back hit (`death_back`) |
| | `P` | respawn (only when dead) |
| | `Backspace` | reset the character to a clean living state at the spawn point |
| | `I` | wounded presentation on/off |
| Emote | `Z` `V` `N` | greet / victory / defeat |
| | `Enter` | speech sample (`dialogue` clip with audio and subtitles; switches to the head-and-shoulders view) |
| View | `Home` `End` | top-down 55 degrees (gameplay view) / third-person close |
| | `PgUp` `PgDn` | full-body front / full-body side |
| | `Insert` `H` | face close-up (chin to hair top) / head and shoulders (lips and hand gestures; used by the speech sample) |
| | `Delete` | free orbit (`RMB` drag, wheel zoom) |
| | `F9` | cycle the views (top, third, front, side, head and shoulders, face, orbit) |
| Show | `F1` `F2` `F3` | help overlay / panel / data HUD |
| | `F4` | skeleton overlay (green deform bones, orange twist/helper bones, magenta props and cable) |
| | `F5` `F6` `F10` | team A/B accent / outline (solid for A, dashed for B) / ground ring (solid+chevron for A, segmented+bar for B) |
| | `F7` `F8` | LOD auto/0/1/2 / textured, wireframe, normals, clay |
| | `O` | one or ten Operatives (nine on autopilot) |
| | `,` `.` | action rate -0.25 / +0.25 (0.5x - 1.5x) |
| | `F11` | run the deterministic showcase sequence |
| Console | `~` | `mr <command>` (section 3) |

Soft status flags (root, silence, disarm, stasis, fear, charm, taunt) are on the **States** tab and available as
`mr flag <name> on|off`.

## 2. Panel (F2)

| Tab | Content |
|---|---|
| Help | this key list, quick buttons (sequence, reset, speech) |
| Animations | motion viewer: search box (matches id, form and layer, several terms allowed) over all 96 entries; click an entry to play it on the character. Play/pause, loop, rate slider, scrub slider, front/side camera, skeleton. Additive hit clips are shown over the combat idle, aim poses and upper-body clips as their authored full-body pose |
| Face | gaze sliders (independent eye look with eyelid follow), the seven expression presets, the 14 visemes and every individual control with left and right separately; reset, auto-blink, look-at-camera, face camera, head-and-shoulders camera, speech |
| Character | team A/B, outline, ground ring, LOD, display mode, skeleton, cameras, 1/10 instances, strafe/travel, wounded, turn left/right, jump to ramp/steps/station/spawn, speed limit, action rate, foot IK / cable simulation / helper bones / look-at switches |
| States | every action, the channel/charge/uplink start-finish-interrupt buttons, hits, disables, status flags, death/respawn/reset, emotes, sequence |

Lighting: the room key light is fixed in the gameplay views (top-down, third person, orbit). In the inspection views
(front, side, turntable) and the close-ups (face, head and shoulders) the key follows the view from the three-quarter
front, and the close-ups use a softer, weaker key so that hair, brow and nose shadows stay clean.

The data HUD (F3) shows: state and flags, base clip and upper clip with time/frame/activation id and a marker bar,
controller speed, travel direction, gait phase and rate, current gait blend, aim yaw/pitch/weight, ground adaptation
offsets, ammo/charge/beacon, automatic expression, prop contact distance while a clip lists a prop track, team/LOD/
display/camera, instance count, frame time, projected body height in pixels, and the last dispatched events
(time, marker, clip, clip time, activation id). The lower left shows the most recent commands, refusals and state
changes.

## 3. Commands

All commands work in the console as `mr <command>`, in automation scripts, with `-MorphExec="cmd; cmd"` and are
what the keys and buttons call. `on|off` arguments also accept `toggle` (or nothing = toggle).

### Character
| Command | Meaning |
|---|---|
| `jump`, `drop` | jump; lift the character 360 cm for a long fall (`fall`, `land_heavy`) |
| `dash f|b|l|r|<deg>` | ground dash, root motion drives the capsule |
| `blink [x y]` | blink to world x y (default 4.5 m forward) |
| `melee`, `fire`, `burst`, `reload` | attacks |
| `cast directional|ground|self` | casts |
| `channel start|release|interrupt` | sustained channel |
| `charge start|release|cancel` | charge |
| `deploy`, `uplink start|cancel` | beacon, recall gesture |
| `turn l|r` | 90 degree turn in place |
| `hit f|b|l|r|<deg> [heavy]` | additive hit from that side (heavy interrupts a channel) |
| `stun [s]`, `sleep [s]`, `knockback [dir]`, `knockup`, `knockdown front|back` | disables (`front|back` = side the hit comes from) |
| `kill front|back`, `respawn`, `reset` | death (side the lethal hit comes from), respawn, clean reset |
| `flag root|silence|disarm|stasis|fear|charm|taunt on|off [x y]` | status flags, optional source position |
| `wounded on|off`, `strafe on|off`, `rate <0.5..1.5>` | presentation, movement mode, action rate |
| `emote greet|victory|defeat|dialogue`, `speech` | emotes |
| `view <clip id>`, `view refpose` | motion viewer: play one of the 96 entries / show the bind pose |
| `viewer pause|play|toggle|loop on/off|rate <r>|scrub <0..1>|exit` | viewer transport |
| `face <control> <0..1>`, `face reset` | individual face control (names of `face_controls.json`; unknown names are refused in the trace) |
| `viseme <name> <0..1>`, `expr <name> <0..1>` | viseme / expression preset weight (same rule) |
| `gaze <yaw> <pitch>`, `gaze off`, `lookcam on|off`, `autoblink on|off` | eyes |
| `bone <name>` | trace the bone's current local rotation / translation relative to its reference pose |
| `team A|B`, `outline on|off`, `ring on|off` | team accent and its colour-independent cues |
| `lod auto|0|1|2`, `display textured|wireframe|normals|clay` | LOD and display mode |
| `footik|secondary|helpers|lookat on|off` | procedural layers |
| `goto spawn|station|viewer|ramp|steps|top` or `goto <x> <y>` | teleport |
| `all <character command>` | apply to every instance |

### Showcase
| Command | Meaning |
|---|---|
| `cam top|third|front|side|face|bust|orbit|turntable [deg/s]|cycle` | cameras. `face` and `bust` follow the head bone (position only, lightly damped) and stay in front of the body whatever the aim / strafe facing is |
| `camdist <cm>` | distance of the current view: `face` (default 118, 40-400) and `bust` (default 225, 80-600) have their own, in every other view it sets the top-down distance (default 1840) |
| `orbit <yaw> <pitch> <dist>` | free orbit camera |
| `shadow <amount> <angle> [<close amount> <close angle> [<close key scale> <yaw offset> <elevation>]]` | key light: shadow darkness 0..1 and source angle in degrees (defaults 1 3, close-ups 0.6 7 with a key at 0.62x intensity, 32 degrees beside the view, 30 degrees above) |
| `instances 1|10`, `select <index>` | instance count, instance addressed by character commands |
| `hud`, `panel`, `skeleton`, `help` `on|off`, `panel tab help|anim|face|char|states` | overlays |
| `aimtarget <index>|cycle`, `target <index> <x> <y> <z>` | lock / move an aim target |
| `light <key> <fill> <fill> <sky>` | light intensities (defaults 1.9 0.32 0.22 0.3) |
| `caption <text>` | caption line at the bottom (empty = off) |
| `sequence`, `script <file>`, `stopscript` | deterministic sequence, automation script |
| `shot <file.png> [ui]` | screenshot of the frame in which the command runs; `ui` includes the Slate panel. In a script the next command runs one frame later, so no `wait` is needed after `shot` (typed in the console together with other commands, put `shot` last) |
| `autoshot <seconds> <dir>`, `autoshot off` | one screenshot every `<seconds>` of showcase time (quick visual review of a long script) |
| `capture start <dir>|default [fps]`, `capture stop` | fixed time step frame dump (`frame_00000.png` ...) |
| `bench <warm-up s> <sample s> <label>` | frame-time benchmark, writes `<label>_frames.csv` and `<label>.json` |
| `exec <console command>`, `quit` | engine console command, exit |

### Script-only intent (used instead of keyboard/mouse while a script runs)
`move <x> <y> [seconds]` (world direction; with a duration the script waits for it), `move stop`, `walk on|off`,
`sprint on|off`, `speed <cm/s>|off`, `aim on|off`, `aimat <x> <y> <z>`, `aimclear`, `wait <seconds>`,
`waitidle [timeout]` (until the character is back in plain locomotion), `scriptinput off` (let injected or real
keyboard/mouse input through while the script continues), `log <text>` (trace line; `log SEQUENCE ...` also shows as a
caption).

Input injection for unattended UI tests (goes through Slate, i.e. the real input path):
`key <KeyName> down|up|tap`, `mouse <x 0..1> <y 0..1> move|click|down|up|clickright|downright|upright|wheelup|wheeldown`, `type <text>`.

## 4. Command line

| Option | Meaning |
|---|---|
| `-MorphSequence` | start the deterministic sequence |
| `-MorphScript=<file>` | run an automation script |
| `-MorphExec="cmd; cmd"` | run commands after start-up |
| `-MorphQuit` | exit when the script/sequence has finished |
| `-MorphCapture=<dir> [-MorphFPS=30]` | capture every frame from the first one with a fixed time step |
| `-MorphCaptureDir=<dir>` | directory used by `capture start default` |
| `-MorphFixedFps=<n>` | fixed time step without capture (fast deterministic verification runs) |
| `-MorphTrace=<file>` | state/event trace file (default `MorphRig/Saved/MorphRigTrace.log` next to the client) |
| `-MorphBenchDir=<dir>` | benchmark output directory |
| `-MorphInstances=<1..10>` | initial instance count |
| `-RenderOffScreen` | engine option: no window (headless hosts); everything above works with it |

## 5. Deterministic showcase sequence

`F11`, `mr sequence` or `-MorphSequence`. Fixed order, about 200 s of game time with the current clip lengths (the
script waits for clips to finish, so the total follows the manifest); with `-MorphFixedFps=30` or a capture the trace
is identical on every run. Chapters (each one is a `SEQUENCE ...` line in the trace and a caption):

1. idle, eight-direction walk and run with independent facing (aim point fixed while the travel direction rotates)
2. ranged shot, burst and directional cast **while running** (upper-body layer + aim offset; the trace line of each
   upper-body clip carries the controller speed)
3. aim grid: the nine calibrated samples (yaw -60/0/+60 x pitch -35/0/+35) with planted feet
4. travel mode: start, sprint, stop, 180 degree pivots to both sides, 90 degree turns in place to both sides
5. jump, running jump, long fall with heavy landing
6. four dashes (root motion drives the capsule) and blinks (teleport event)
7. melee combo 1-2-3 with hit windows, single slash
8. reload **while walking**; reload cancelled by a dash before `reload_insert`
9. charge: early release, full release, cancel
10. channel: interrupted midway; channel finished normally
11. ground cast, self cast, deploy at the prop station, uplink cancelled by damage, uplink completed + recall blink
12. additive hits from four sides **while running**
13. stun, sleep woken by damage, knock-back, knock-up, both knock-downs with their get-ups
14. death during a cast (second death refused), respawn, death during a jump, respawn
15. root / silence / disarm (refusals are traced) / stasis / fear / charm / taunt
16. wounded presentation
17. ramp (20 degrees) and steps (20 cm risers) with ground adaptation, walking and running
18. action rate 0.5x and 1.5x
19. greet, victory, defeat, speech sample in the head-and-shoulders view

`tools/verify_trace.py <trace>` checks a trace against the event rules of the contract (once per pass, nothing after
an interruption, clip-time order, entry offsets, single death, muzzle counts, manifest names), reports the inventory
coverage (all 96 entries) and, for a sequence trace, 22 expectations on the combined states (for example "ranged_fire
started while moving", "channel interrupted midway", "death during a jump"). The trace of the run that produced
`presentation/motion_showcase.mp4` is stored as `presentation/motion_showcase_trace.log`; the trace of the last
verification run is `docs/verification/sequence_trace.log` with its report `sequence_verify.txt`.

## 6. Unattended checks

| Script | What it does |
|---|---|
| `tools/scripts/ui_selftest.txt` | drives the application only with injected mouse / keyboard events (through Slate): panel tab click, typing in the search box, list selection, focus click, reset, aim while moving and fire, channel interrupted midway, charge, jump, dash, melee combo, hit, stun, death, respawn, view / display hot-keys, speech sample |
| `tools/scripts/browse_all.txt` | selects every one of the 96 entries in the motion viewer |
| `tools/ue_full_cycle.sh verify` | runs the sequence and both scripts on the packaged client with a fixed 30 fps step and checks the three traces (`docs/verification/`) |
