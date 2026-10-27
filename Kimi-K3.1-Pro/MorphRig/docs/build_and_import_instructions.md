# Build and import instructions

All commands below run from the delivered `MorphRig/` directory. Use the installed Blender and Unreal Engine installations stated in the task's `environment.json`; do not substitute a different shared-tool version. Project scripts derive their own location. The Unreal wrapper can also be selected explicitly with `UE_EXEC=/path/to/ue-exec`.

## Prerequisites

- Blender as supplied in `environment.json`, including its bundled Python/NumPy and FBX exporter.
- Unreal Engine 5 and its supplied `ue-exec` FHS wrapper, editor, C++ toolchain and `RunUAT.sh`.
- The installed `ProceduralMeshComponent` plugin, declared in `unreal/MorphRig/MorphRig.uproject` and used for the ramp's matching top-surface collision. It is included with the engine; no download or paid add-on is needed.
- `ffmpeg` for presentation encoding.
- Only if regenerating the supplied voice: `nix-shell`, with `espeak-ng` as described in `THIRD_PARTY_ASSETS.csv`. The finished WAV is already included, so speech synthesis is not a build dependency.

No paid plug-in, third-party character, downloaded skeleton/motion set, voice-cloning service or external game asset is used.

## Reproduce the editable source

The delivered `.blend` is already complete. These commands are for deliberate regeneration or editing; a full generator rebuild replaces manual changes, so preserve an edited copy first.

```sh
# Optional: regenerate original speech and its measured alignment.
python3 source/generators/synthesize_dialogue.py

# Prepare the finite 96-entry inventory from the included machine-readable copy.
python3 source/generators/prepare_inventory.py

# Generate original geometry, UVs, materials, rigs and all baked motion.
blender -b --factory-startup --python-exit-code 1 \
  -P source/generators/build_operative.py

# Validate analytic motion, saved actions, skin weights, UVs and texture links.
blender -b source/Operative.blend --python-exit-code 1 -P tools/check_motion.py
blender -b source/Operative.blend --python-exit-code 1 -P tools/validate_source.py

# Render representative source/contact/facial checks.
blender -b source/Operative.blend --python-exit-code 1 -P tools/render_motion_checks.py
python3 tools/assemble_contact_sheets.py
```

For an iterative manual edit, open the existing `.blend`, run the embedded `START_HERE_Rig_Controls.py`, edit the source controls/curves, use **Bake Current Range**, and save. This does not require a full generator rebuild. `docs/rig_usage.md` describes the exact control and facial workflows.

`source/generators/bake_inventory.py` rebakes the existing generated asset without rebuilding its mesh. `source/generators/build_operative.py -- --model-only` regenerates only geometry/materials/rigs, leaving the separate animation-bake step for later.

## Export Blender sources

```sh
blender -b source/Operative.blend --python-exit-code 1 -P tools/export_and_bake.py
blender -b source/Operative.blend --python-exit-code 1 -P tools/export_beacon.py
```

Optional explicit stages are `-- --mesh-only` and `-- --animations-only`.

Outputs:

- `export/Operative.fbx`, `Operative_LOD1.fbx`, `Operative_LOD2.fbx`;
- 96 named files in `export/animations/`;
- `export/Beacon.fbx`, containing only the authored beacon subset with UVs and materials, for the independent deployed prop;
- the complete authored texture set in `export/textures/`.

FBX export uses the source unit metadata, no extra import-scale repair, deform bones only, no leaf bones, a connected root, and the actual baked action/face channels. Temporary export joins retain all 26 shapes plus Basis. Original source body/face/prop objects remain separate.

The exporter does not save its temporary bind pose or disabled constraints back into the editable `.blend`.

## Compile the native module and import assets

Compile the native project before starting the editor import, because it is a C++ project, not a content-only project:

```sh
tools/build_linux.sh
```

`tools/build_linux.sh` uses the supplied wrapper/toolchain and packages a Linux Development client. If only the editor target needs to be rebuilt during iteration, the equivalent direct command is available through the supplied wrapper as documented by the installed `Build.sh` usage; the script is the authoritative reproducible full build.

Run the headless import after the editor module exists:

```sh
tools/run_import.sh -- --skip-events   # geometry, materials, LODs, sockets, audio and animation transfer only
# Compile/provide the native MorphEventNotify class, then perform the complete import:
tools/run_import.sh
# Fresh-process persisted-asset audit:
tools/run_import.sh -- --audit-only
```

The normal import is complete only when the native named-event class is available and the full audit, including event assets and facial curves, passes. A mesh-only diagnostic mode is `-- --mesh-only`; `-- --animations-only` reuses the existing skeletal mesh.

The importer deliberately pins the FBX factory, samples animation at 30 Hz, imports blend-shape curves, and builds explicit materials and sockets from actual Unreal reference transforms. The authoritative `.blend` stays in meters. Before export, a temporary copy of the deformation skeleton has its connected flags detached and every rest matrix scaled exactly once from meters to centimeters; the parent hierarchy is unchanged. Mesh-object export scale is 100 and exported bone-location curves are converted to centimeters. These temporary transforms are not saved back to the source. FBX uses `FBX_SCALE_UNITS` with `apply_unit_scale=False`, `bake_space_transform=False`, `global_scale=1`, triangulated geometry and tangent-space export. Unreal consumes the explicit centimeter transforms with `convert_scene_unit=False` and `import_uniform_scale=1.0`, not a second conversion or an undocumented import-scale repair. The production mesh uses the measured original source-to-Unreal matrix `[[0,-1,0],[-1,0,0],[0,0,1]]`, with the mesh forward at actor +X and zero additional yaw. All 96 authored clips import directly onto the original production skeleton with `force_front_x_axis=True` and `MATCH_UP_FORWARD_AXES`. The importer aligns only the root frame to the mesh reference through the public animation-data-model API. Root translation receives the measured inverse import-frame rotation, preserving nominal displacement; all 70 tracks, the connected hierarchy, every other local bone channel and float facial curves are preserved. No component-space bone retarget or scale repair is applied.

LOD0 is imported first. The supported `SkeletalMeshEditorSubsystem.import_lod` API then imports the authored LOD1 and LOD2 files into that base mesh, retaining the common skeleton, materials and facial shapes. Triangle counts are checked against the actual source meshes. `export/Operative.fbx` is the primary LOD0 asset; `export/Operative_LOD0.fbx`, `Operative_LOD1.fbx`, and `Operative_LOD2.fbx` are the explicit per-LOD import sources. The importer does not merge all three LODs into one skeletal mesh.

The eleven static entries remain one-frame authored poses in Blender. For Unreal's FBX importer, which rejects zero-length takes, the exporter duplicates each pose's sole key at the next frame without changing its value. The native asset therefore spans at most one 30 FPS sampling interval and is held as a pose by the controller; it is not a new motion clip or an extra inventory entry. All bone and facial channels are retained.

The four directional hit clips use `AAT_RotationOffsetMeshSpace` with `idle_relaxed` frame zero as their reference. The import audit records this setting and checks the dash displacement through the measured source-to-Unreal basis: native forward is +X, backward -X, left -Y, and right +Y. At runtime, the additive layer consumes deltas, while direct playback and outgoing cross-fades convert them to complete local poses before ordinary blending.

The four dash clips are translation-only. The controller uses `ExtractRootTrackTransform` and the actual root-track translation delta, with no additional yaw, to sweep the capsule. The import audit separately checks sampled track translation, mesh-local displacement and final actor-space direction. The mesh faces actor +X with zero additional mesh yaw, and packaged verification checks root orientation against the actual mesh reference for every required entry. This is not an actor teleport or an import-scale repair.

Mesh, materials and sockets are imported before the static beacon, so the beacon uses the current measured mesh basis. The deformation skeleton is explicitly persisted before any animation import. Asset import tasks save their generated packages. The importer additionally saves the completed mesh and clips explicitly and records `docs/validation/unreal_save_report.json`; `--audit-only` then reloads them in a fresh editor process. A report based only on an in-memory import is not accepted as final evidence.

Native content is under `unreal/MorphRig/Content/Operative/`:

- `SK_Operative` and its skeleton;
- `Animations/<id>` for every manifest ID;
- `Materials/`, `Textures/`, and `Audio/Dialogue`;
- the copied `animation_manifest.json`, transcript and alignment.

The editor-only importer is `unreal/MorphRig/Tools/import_operative.py`. The packaged game does not execute Python or require editor scripting.

## Run and verify the packaged Linux client

After the final content import, run `tools/build_linux.sh` again so cooking/staging includes every native asset. The archive is under `build/Linux/`. Use its generated launch script through the supplied `ue-exec` wrapper; the client itself does not require the Unreal Editor.

```sh
# From the archive's launch-script directory on the supplied host:
UE_EXEC=/home/morpheus/UnrealEngine/bin/ue-exec
"$UE_EXEC" ./MorphRig.sh -windowed -ResX=1920 -ResY=1080
"$UE_EXEC" ./MorphRig.sh -MorphVerify
"$UE_EXEC" ./MorphRig.sh -MorphDemo=states
"$UE_EXEC" ./MorphRig.sh -MorphCapture=turntable
"$UE_EXEC" ./MorphRig.sh -MorphCapture=motion
"$UE_EXEC" ./MorphRig.sh -MorphCapture=face
"$UE_EXEC" ./MorphRig.sh -MorphBenchmark
```

On the supplied NixOS host, launch the same scripts with `ue-exec` rather than bypassing the required FHS runtime. Runtime verification, capture and benchmark outputs belong in the packaged project's `Saved/` directory; copy final reports to `docs/validation/` and encoded videos to `presentation/`.

The in-app control guide and `README.md` document interactive controls. Every required clip is available through the searchable browser; the deterministic sequences supplement, rather than replace, interactive control.

From the project root, use `python3 unreal/MorphRig/Tools/verify_runtime.py` to launch the packaged native checks and reject stale or failed reports. `python3 tools/capture_presentations.py` captures and encodes the turntable, motion/state overview and facial performance with live clip/event captions. After other GPU work has stopped, `python3 tools/benchmark_linux.py` measures one and ten instances at 1920x1080, with three-second warmups, eight-second raw frame-time samples, frame generation disabled, VSync off and no FPS cap. It writes `docs/validation/performance.json` and the client log; actual FPS is reported rather than assumed. The GPU-isolation check refuses competing work unless explicitly overridden with `MORPH_BENCH_ALLOW_SHARED_GPU=1`.

Partial animation imports retain the native socket transforms and measured mesh basis when rebuilding their report. A full import is required after changing geometry, socket positions or LOD topology. `tools/audit_prop_motion.py` and `unreal/MorphRig/Tools/audit_transforms.py` provide source and native bone-motion diagnostics; these are audits, not a replacement for the rendered contact checks.

## Validation and reporting

```sh
python3 tools/generate_reports.py
```

- `docs/source_geometry_report.json`: generated source counts.
- `docs/validation/source_asset_validation.json`: saved Blender evaluation and asset checks.
- `docs/validation/analytic_motion.json`: all analytic clip/root/endpoint/support checks.
- `docs/unreal_import_audit.json`: actual imported mesh, skeleton, LOD, morph, timing and event data.
- `docs/material_and_lod_report.json`: measured source and imported LOD/material/texture information with labeled memory estimates.
- `docs/validation/`: runtime traces, performance logs and rendered inspection evidence.

A report saying an export or import was requested is not treated as proof of a working asset. Final verification requires the persisted native audit and the packaged client's actual rendering/state tests.

After the native report, state trace, reviewed presentations and measured performance are present, run `python3 tools/validate_delivery.py`. It cross-checks the complete delivery and writes `docs/validation/delivery_validation.json`; it must return `PASS` before handoff.
