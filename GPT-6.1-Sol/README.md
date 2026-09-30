# MorphRig Operative

Original 1.80 m human cyberpunk character, editable Blender production rig,
96 authored source actions and 96 baked deformation actions, imported Unreal
character and a native Linux showcase. The design uses a flexible aubergine
underlayer, limited graphite armor, an organic face and left arm, a cybernetic
right forearm, wrist emitter, retractable blade, removable cell and deployable
beacon. All character geometry, costume, textures, props and motions were
authored procedurally for this assignment from editable mesh/curve data.

## Run and inspect

From this folder on the supplied NixOS host:

```bash
./tools/build_linux.sh run
```

This launches `build/Linux/MorphRig.sh` through the supplied Unreal FHS
wrapper at 1920x1080. The packaged executable runs independently of the Editor.
Use the existing installed Blender 5.1.1 and Unreal Engine 5.8.3 for authoring;
their actual paths and the wrapper are supplied in `environment.json`.

The HUD displays state, body/upper clip, animation time, rate, nominal speed,
marker timing, team identifier and selected LOD. F8 displays controls. Click
the browser to search and play any of the 96 entries, or open the facial panel
to exercise individual controls and expression presets. F9 runs the combined
state demonstration and writes a state/event trace.

| Input | Action |
|---|---|
| WASD; Shift; Ctrl | Facing-preserving walk/strafe; run; forward sprint |
| Arrow keys; Y | Independent aim yaw/pitch; move and aim at a target |
| Q/E; Ctrl+Q/E | Left/right 90-degree turn; 180-degree pivot |
| Space; X; V | Jump; directional root dash; event-driven blink |
| Mouse button; F | Wrist shot; three-shot burst |
| 1/2/3; R; P | Blade combo entries; physical cell reload; beacon deploy |
| G/J/K | Directional/ground/self casts |
| Hold C/Z/U; I | Channel/charge/uplink; cancel or recover |
| H; Delete; Shift+Delete; Enter | Directional hit; front/back death; respawn |
| Backspace | Reset and return to room origin |
| F1/F2/F3/F4/F5 | Third-person/front/side/face/top-down views |
| B; text; PageUp/PageDown; Enter | Search browser; pages; play matching clip |
| T/N/L/M/O | Team variant; per-character team icons; automatic or forced LOD; material mode; skeleton |
| +/-; F9; F10; F11 | Action rate 0.5–1.5; sequence; one/ten actors; performance capture |
| Mouse wheel; Escape | Inspection distance; close browser/panel |

Clickable controls also expose rooted, silence, disarm, fear/charm/taunt,
wounded, stasis, stun, sleep, knockup, directional knockdowns and recoveries.
The team accent pairs cyan or amber with a per-character triangle/A or diamond/B icon; N toggles the icons.
Face view includes neutral plus six expressions, asymmetric controls and
seven documented viseme categories. **Speech** plays the original 13.567-second
English performance with gaze, gestures and a concern-to-confidence shift.

## Delivered files

| Deliverable | Location |
|---|---|
| Finished editable model, controls, UVs, weights, morphs, source and baked actions | [source/Operative.blend](source/Operative.blend) |
| Original editable character/rig/motion/speech generators | [source/generators/](source/generators/) |
| Packed textures and editable external PNG maps | [source/textures/](source/textures/) |
| WAV, original transcript, actual phoneme/word alignment | [source/audio/](source/audio/) |
| Centimeter skeletal mesh and authored reduced LODs | [export/](export/) |
| One FBX per required ID, 30 FPS baked bone curves | [export/animations/](export/animations/) |
| Export texture copies | [export/textures/](export/textures/) |
| UE project, imported assets, native controller/animation implementation, settings | [unreal/MorphRig.uproject](unreal/MorphRig.uproject) |
| Standalone Linux x86-64 executable and cooked runtime | [build/Linux/](build/Linux/) |
| Rig, skeleton/socket, exact 96-entry mapping and state contracts | [docs/](docs/) |
| Reproducible export/import/build/validation/capture tools | [tools/](tools/) |
| Neutral full-body turntable | [presentation/turntable.mp4](presentation/turntable.mp4) |
| Combined motion/state overview | [presentation/motion_showcase.mp4](presentation/motion_showcase.mp4) |
| Actual close-up spoken performance | [presentation/face_performance.mp4](presentation/face_performance.mp4) |
| Measured source and imported asset checks, renders, runtime traces and frame logs | [verification/](verification/) |

The presentation recordings use the delivered standalone realtime character,
not a separate high-detail model. The supplied dialogue WAV is muxed at the
client's traced speech start to preserve alignment without recording desktop
audio. Capture settings and timestamps are retained in
`verification/presentation/*_capture.json`.

The final delivery audit passes 138 checks with no failures; the independent
Blender audit passes 926. The final recorded combined-state sequence passes
all ten checks, and inventory playback covers all 96 entries. These results,
their input identities and the terrain/performance evidence are retained in
[verification/delivery_validation.json](verification/delivery_validation.json)
and [docs/quality_review.md](docs/quality_review.md).

## Edit, rebuild and validate

Open the finished `.blend` directly; its textures are packed and external
paths are relative. Run the embedded `Operative_Animator_Panel.py` in Blender's
Text Editor to enable reset and matched IK/FK switches. Existing control
actions can be edited and rebaked without regenerating geometry. See
[rig_usage.md](docs/rig_usage.md) and [facial_mapping.md](docs/facial_mapping.md).

```bash
blender -b source/Operative.blend -P tools/export_and_bake.py
./tools/build_linux.sh editor
./tools/build_linux.sh import
./tools/build_linux.sh package
blender --python-exit-code 1 -b source/Operative.blend -P tools/validate_asset.py
./tools/build_linux.sh run -MorphSequence -MorphAutoExit
./tools/build_linux.sh run -MorphInventorySweep -MorphAutoExit
./tools/build_linux.sh run -MorphPerf -MorphAutoExit
./tools/build_linux.sh run -MorphPerf10 -MorphPerf -MorphAutoExit
python3 -B tools/capture_presentation.py all
python3 -B tools/review_presentation.py
python3 -B tools/validate_delivery.py
```

The full original procedural rebuild starts with
`blender -b --factory-startup -P source/generators/build_character.py`; the
already delivered file does not require this. Speech generation uses the
permitted local eSpeak NG dependency. Capture uses Nix `ffmpeg-full`,
`xdotool` and `xwininfo` with the active XWayland display. Builds, compiler
logs, derived data, capture scratch and project settings stay in this folder.
Frame-sheet extraction also uses Python Pillow. The delivery validator checks
the recorded source, executable and media identities, the independent terrain
review, all 96 imported assets, and the warmed performance frame logs.

Source units are meters, facing -Y and up +Z. FBX geometry, bind positions
and translations are explicitly authored in centimeters at export, imported
with scale 1. The measured UE conversion faces +X, anatomical right -Y.
[skeleton_and_sockets.json](docs/skeleton_and_sockets.json) documents every
deformation bone, source/UE name and attachment. There is one ground root
independent from pelvis, 79 deformation bones and at most five effective
skin influences in the delivered LODs.

LOD triangle counts are 40,940 / 21,698 / 11,053, with eight material slots
including equipped props. Ten original 256x256 maps use approximately
3.33 MiB uncompressed with mipmaps. See the measured
[material_and_lod_report.json](docs/material_and_lod_report.json),
[Unreal import report](verification/unreal_import_report.json),
[quality review](docs/quality_review.md) and
[known_issues.md](docs/known_issues.md). Exact frame counts, event markers,
root policies, layers and states are in
[animation_manifest.json](docs/animation_manifest.json).

The final standalone Vulkan measurements at 1920x1080 use five seconds of
warmup followed by thirty seconds of actual frame samples. One character
measured 1.858 ms mean / 2.247 ms p95; ten animated characters measured
1.994 ms mean / 2.509 ms p95. No sampled frame exceeded 16.667 ms, with VSync
and generated frames disabled. Settings, hardware, percentiles and raw
game/render/GPU frame logs are in [performance_report.md](docs/performance_report.md)
and `verification/performance_*_instances.*`.

External support and tool provenance is recorded in
[THIRD_PARTY_ASSETS.csv](docs/THIRD_PARTY_ASSETS.csv). No stock character,
downloaded skeletal motion, paid asset or voice clone was used. Unreal engine
support content and packaged runtime remain subject to Epic's Engine EULA.
