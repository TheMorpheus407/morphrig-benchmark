# Building the editable Unreal showcase

Run commands from `MorphRig/`. The supplied `../environment.json` selects the installed Blender and Unreal paths. On the supplied NixOS host, Unreal runs through the supplied `ue-exec` FHS wrapper. The runtime module contains portable Unreal C++; other supported Linux hosts can run the packaged `MorphRig.sh` directly.

```bash
tools/build_linux.sh editor
tools/import_unreal.sh
tools/build_linux.sh
tools/run_showcase.sh
```

To reimport selected corrected clips after a full import, run `MORPH_IMPORT_IDS=deploy tools/import_unreal.sh` (comma-separated IDs are accepted). Add `MORPH_IMPORT_MESH=1` when the skeleton mesh, weights or LOD FBXs changed. This preserves the shared mesh/materials and refreshes native pose validation.

Full and mesh-only Blender export also run `source/generators/export_props.py` to derive `export/Beacon.fbx` from the saved `source/Operative.blend`. For a prop-only rebuild, run `blender -b --factory-startup --python-exit-code 1 -P source/generators/export_props.py`, then `MORPH_IMPORT_BEACON=1 tools/import_unreal.sh`. This rebuilds the native static asset and checks all its imported vertices against the authored deploy pose. Repackage after any asset import.

The first command builds the native editor module. The import command requires the completed `export/Operative.fbx`, both LOD FBXs, `export/Beacon.fbx`, all 96 animation FBXs, textures, audio and authored JSON manifests. `tools/export_and_bake.py` and the Blender generation sources document source rebaking. The package command builds the Linux Development client, cooks `/Game/Showcase` and the Operative assets, and archives the executable under `build/Linux/`. The application opens directly into the interactive room. For an isolated candidate package, set `MORPH_ARCHIVE_DIR` when building and the matching `MORPH_CLIENT_DIR` when running.

The installed editor Python API supplies the FBX importer, material creation, LOD import, notify tracks and asset validation. Required editor plugins are declared in `MorphRig.uproject`; the package has no editor/Python runtime dependency. The native module uses Engine, Slate, Json, AnimationCore and AnimGraphRuntime. Blender and the installed bundled Clang/.NET toolchain are the only production build dependencies. Python 3 and Bash support the wrapper scripts.

## Coordinate and timing transfer

The authoritative Blender source uses meters, standing height 1.80 m, +Z up, −Y forward and +X anatomical left. The exporter creates a temporary centimeter copy: rest skeleton, geometry, morph deltas and **every** animated location channel scale by 100; scene unit scale becomes 0.01. Source objects and the delivered `.blend` stay in meters. This prevents the FBX armature-object removal path from scaling animated translations differently from the bind pose.

The Unreal mesh import uses unit conversion, unit import scale, and Force Front X. The animation importer persists a −90-degree import yaw before reimport because the installed classic importer otherwise retains the animation file's +Y-facing root track. This is an explicit coordinate conversion, validated against the authored source poses. Imported coordinates are `(-sourceY, -sourceX, sourceZ) × 100`, in centimeters. Dashes retain 200 cm of root travel. FBX converts periods to underscores in bone and morph names; the runtime and native data use that mapping.

The released beacon uses the same authored geometry and shared alloy/accent materials as the skinned prop. Its export bakes centimeters and the static-to-skeletal socket basis: Blender beacon-local `(x,y,z)` becomes native bone-local `(z,-x,y)`. The import rebuilds two compact material sections. At release, the runtime copies the evaluated world socket transform at unit scale, hides the skinned copy and leaves the static copy in the room. `docs/validation/beacon_native_import.json` records the 272-vertex source/native comparison, two sections and grounded 7.30 cm height; no runtime size compensation is used.

The source and imports use 30 FPS. The runtime interpolates compressed sequences, uses authored clip seconds for markers, and loads the staged facial curves without a network or external service. Speech playback sets action rate to 1x for synchronization with the delivered WAV. Other action rates are bounded to 0.5x–1.5x.

## Native asset verification

`tools/verify_unreal.py`, run with Unreal's `-run=pythonscript -script=...`, reloads the persisted skeleton and animations. It records bone names, morph targets, reference positions, clip lengths and root deltas in `docs/unreal_pose_validation.json`. It also compares compressed native poses against `docs/blender_pose_samples.json`, including root, pelvis, head, hands, feet, cell and beacon. Results are in `docs/unreal_source_pose_comparison.json`. The full importer writes `docs/unreal_import_validation.json` with the actual 96 assets, LOD vertices/sections and material/morph counts.

Event markers are stored as native `UMorphMarker` notifies and also in the staged manifest. Runtime marker execution is centralized and deduplicated by action generation, loop and marker identity. `animation_state_contract.md` explains state priorities, layering, movement locks and interruption semantics.

## Automation and evidence

```bash
tools/run_showcase.sh -MorphDemo -MorphSeconds=52 -MorphEvidenceDir="$PWD/docs/validation/runtime_demo"
tools/run_showcase.sh -MorphTerrain -MorphSeconds=8 -MorphEvidenceDir="$PWD/docs/validation/runtime_terrain"
tools/run_showcase.sh -MorphInstances=10 -MorphSeconds=35 -MorphEvidenceDir="$PWD/docs/validation/performance_10"
tools/run_showcase.sh -MorphCapture=face -MorphScreenshotAt=5 -MorphSeconds=6
```

`-MorphCapture=turntable`, `face`, or `motion` selects a demonstration view. Aim targets occupy a separate area beside the normal room's ramp and stair lanes. Use `-MorphTerrain -MorphCapture=terrain` for an elevated slope/step view with hidden panels; this mode positions targets behind the camera's walking lane to keep contacts visible. Add `-MorphShowUI` to retain panels and current state data. `-MorphClip=ID` previews an exact inventory entry. `-MorphScreenshotAt=T` writes a viewport PNG under `build/Linux/MorphRig/Saved/Screenshots` for the packaged client. `-MorphCaptureDir=/absolute/task/path` enables numbered PNG frames; `-MorphCaptureFPS=30` fixes the simulation timestep for synchronized video capture. Render captures are excluded from frame-time benchmarking. FFmpeg can encode the PNG sequence with the supplied WAV for the face performance.

Performance runs use the real wall-clock frame timestep, no generated frames and no frame-rate cap. CSV logs record actual viewport resolution, frame time, actor count, LOD, clip and action rate. The first 10 seconds are marked as warmup. One and ten actors are separate runs. Runtime LOD thresholds are 0.45 and 0.18 screen size. Close inspection uses LOD0; the 1080p gameplay camera places the body at approximately 125 pixels. The UI also includes a one/ten toggle, explicit LOD selection, normal-material inspection and skeleton overlay.

Build, import and runtime logs stay under `unreal/Saved/`. Writable DDC, the AutomationTool cook-log directory and tool configuration stay in the project. Zen cooked-output storage is disabled; cooking writes local files, then creates the packaged IoStore/Pak archives. The installed engine's packaged DDC is read-only. `-NoTraceServer` prevents the editor from autostarting a trace-store process. Do not run multiple editor/cooker processes against this same project's shader work directory simultaneously.

## Application controls

The left panel contains camera/material/LOD/team controls and a searchable browser for every clip. The right panel scrolls as a whole and contains action, interruption, modifier, aim and facial controls. Individual eyes, left/right blinks, expression shapes and visemes can be exercised independently. Each manual eye slider spans -1 to +1: yaw maps to +/-25 degrees and pitch to +/-12 degrees. Manual vertical look includes a bounded 2.4 mm socket recession to keep the iris behind the lid. Positive yaw looks to the character's right; positive pitch looks up. These offsets are separate from the authored speech gaze. Browser selection resets attachments and previews a clip; loops repeat and one-shots hold their final frame.

WASD moves in the room; Shift runs and Ctrl sprints. Q/E changes facing independently, with authored stationary turns. Right mouse adjusts aim. Space jumps, Z dashes, J blinks, F fires, R reloads, C casts, G channels, H charges, U starts Uplink, B deploys, and 1/2/3 select melee attacks. Enter finishes/releases; X interrupts/cancels or starts recovery. Delete triggers death; the Respawn button restores life. V cycles cameras, T switches team, L cycles LOD, O toggles skeleton, I toggles wounded presentation, N switches one/ten actors, P pauses, Backspace resets, F9 starts the deterministic sequence, Tab hides panels, and Escape exits.
