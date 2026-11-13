# Build and import instructions

The delivery is rebuilt in two independent halves: **Blender** generates the character, rig, textures and clips
and writes `source/Operative.blend`, `export/` and the data documents in `docs/`; **Unreal** imports `export/` +
`docs/` and packages the Linux showcase. Paths are relative to the `MorphRig/` folder.

## Blender

### B1. Prerequisites

| Item | Value |
|---|---|
| Blender | 5.1.1 (`blender` on the PATH; the slotted action API of 4.4+ is required). Runs headless; Cycles is used once for the ambient-occlusion bake (GPU via OptiX if present, CPU otherwise) |
| Other tools | `ffmpeg` (only for development preview sheets and the audio resample) |
| Python | only Blender's bundled Python and numpy; no add-ons, no external Python packages |
| Speech synthesis (only to regenerate the audio) | Piper TTS 1.4.2 and its bundled eSpeak NG phonemiser (`nix-shell -p piper-tts espeak-ng` on the reference host) plus the voice `en_US-ljspeech-high` from `https://huggingface.co/rhasspy/piper-voices` (see `docs/THIRD_PARTY_ASSETS.csv`) |

Run Blender without a display variable in a headless shell (`DISPLAY= blender -b ...`); on the reference host the
software GL context of a virtual X server crashes Blender, while a display-less background process works.

### B2. Full build (procedural source -> .blend -> exports)

```sh
blender -b --factory-startup -P tools/export_and_bake.py
```

About 8 minutes on the reference host (5 of them for the 4096 px skin maps). Stages and outputs:

| Stage | Module | Output |
|---|---|---|
| geometry, weights, face shape keys, UVs (unwrap per part, pack per material) | `mr/charmesh.py` and the geometry modules | mesh `Operative_LOD0` |
| textures (painted in UV space from the rest mesh, AO baked with Cycles) | `mr/texgen.py` | `source/textures/*`, copied to `export/textures/*` + `texture_manifest.json` |
| materials with the two team variants | `mr/materials.py` | in the .blend |
| LOD1, LOD2 | `mr/lod.py` | meshes `Operative_LOD1/2` |
| deformation skeleton, control rig, shape-key drivers, rig UI | `mr/armature.py`, `mr/rig.py`, `mr/rigui.py` | `SKEL_Operative`, `RIG_Operative`, text `morphrig_ui.py` |
| 96 clips: source action -> cable simulation -> bake on the skeleton + morph curves, QA numbers | `mr/anim_*.py`, `mr/secondary.py`, `mr/bake.py` | actions `<id>`, `BAKED_<id>`, `BAKED_<id>.morph` |
| documents | `mr/docsgen.py` | `docs/skeleton_and_sockets.json`, `face_controls.json`, `animation_manifest.json`, `material_and_lod_report.json` |
| save | | `source/Operative.blend` (textures linked with relative paths) |
| export | `mr/export.py` | `export/Operative.fbx`, `Operative_LOD1.fbx`, `Operative_LOD2.fbx`, `export/animations/<id>.fbx` (96), `export/props/SM_Beacon.fbx`, `SM_PowerCell.fbx` |

Options: `--reuse-textures` (skip painting when `source/textures` is current), `--tex-scale 0.25` (quick preview
maps), `--clips a,b,c` (development subset; the manifest is then marked `partial`), `--no-export`, `--no-blend`,
`--out <dir>` (write everything into another folder).

The build asserts the hard limits (LOD triangle budgets 80k / 40k / 20k, at most 8 bone influences, at most 8
material slots, clip durations against `required_animations.csv`, all drivers being simple expressions) and
stops if one is violated.

### B3. After editing animation in the .blend

```sh
blender -b source/Operative.blend -P tools/export_and_bake.py -- --from-blend --clips reload,walk_f
```

Re-bakes the named source actions (all 96 without `--clips`) on the deformation skeleton, saves the file,
rewrites their FBX files and updates frame counts in `docs/animation_manifest.json`. See `docs/rig_usage.md`.

### B4. Export conventions

* Blender data stays in metres. For the export an in-memory copy is converted to centimetres (joints, mesh and
  shape-key coordinates, translation curves x100, unit scale 0.01), so the FBX carries unscaled joints in
  centimetres and Unreal imports with uniform scale 1.0. That state is never saved.
* The armature object is named `Armature` while exporting (Unreal drops a null node of exactly that name instead
  of adding an extra root joint); the first joint is `root`.
* One FBX per clip, take name = clip id, 30 fps, every bone keyed on every frame, no simplification. Pose entries
  are two identical frames. Each clip FBX contains the `MorphProxy` mesh whose 32 shape-key curves become the
  morph-target curves of the animation asset.
* Axis conversion: Unreal component space = Blender (x, -y, z) x 100; details and per-bone reference positions
  in `docs/skeleton_and_sockets.json`.
* Prop static meshes (`export/props`) are stored upright in the prop's own frame: origin at the prop bone head,
  the bone's Y axis (the prop's "up") maps to +Z.

### B5. Regenerating the spoken line

```sh
# once: patch a copy of the voice so that it also returns phoneme durations
python3 -m piper.patch_voice_with_alignment en_US-ljspeech-high.onnx --output patched/en_US-ljspeech-high.onnx
# audio + transcript + alignment (run with the Python that has piper-tts installed)
python3 -I source/generators/dialogue_audio.py patched/en_US-ljspeech-high.onnx source/audio
```

Writes `source/audio/dialogue.wav` (48 kHz mono), `dialogue.txt` and `dialogue_alignment.json`. The clip length
and the markers of `dialogue` follow the alignment file automatically on the next build.

## Unreal

Everything below runs headless from a shell. No step needs the Unreal Editor UI, a store asset or a paid
plugin; the only engine plugins the project enables are `PythonScriptPlugin` and `EditorScriptingUtilities`
(editor-only, used by the import script).

### U1. Prerequisites

| Item | Value |
|---|---|
| Engine | the Unreal Engine 5 installation named in `environment.json` (the project was built and verified with 5.8.3, official prebuilt Linux build, bundled clang toolchain) |
| Host wrapper | on the NixOS reference host every engine binary has to be started through the `ue-exec` wrapper from `environment.json`; the tool scripts read that path from `../environment.json` automatically. Override with `UE_EXEC=/path/to/ue-exec`, or set `UE_ROOT=/path/to/engine` on a host where the engine runs natively |
| Other tools | `bash`, `python3` (only to parse JSON in the scripts), `ffmpeg` (video encode), optional `nvidia-smi` (benchmark host note) |
| Client-only scripts | `run_showcase.sh`, `run_benchmark.sh` and `capture_presentation.sh` only start the packaged client: on a host where it runs natively they need neither the wrapper nor an engine installation (without `../environment.json`, `UE_EXEC` and `UE_ROOT` the client is started directly) |
| Inputs | `export/Operative.fbx`, `export/Operative_LOD1.fbx`, `export/Operative_LOD2.fbx`, `export/animations/<id>.fbx` (96), `export/textures/*`, optional `export/props/*.fbx`, `docs/animation_manifest.json`, `docs/skeleton_and_sockets.json`, `docs/face_controls.json`, `source/audio/dialogue.wav|.txt|dialogue_alignment.json` |

### U2. One command

```sh
tools/build_linux.sh            # editor module build -> import + verification -> cook, stage, pak -> build/Linux
tools/run_showcase.sh           # start the packaged client (1920x1080 window)
```

After a re-export the complete Unreal side is one command (stages can be named individually, in this order):

```sh
tools/ue_full_cycle.sh                 # = build verify bench capture
tools/ue_full_cycle.sh build verify    # re-import + package, then the unattended checks
```

| Stage | Does | Writes |
|---|---|---|
| `build` | `tools/build_linux.sh` (deletes the generated Content folders, re-imports, packages) | `unreal/Content/{Operative,Showcase,MorphRigData}`, `unreal/Saved/MorphRigImportReport.json`, `build/Linux/` |
| `verify` | packaged client, offscreen, fixed 30 fps step: deterministic sequence, injected-input self-test, motion-viewer pass; each trace checked by `tools/verify_trace.py` | `docs/verification/{sequence,ui_selftest,browse_all}_trace.log`, `*_verify.txt`, `import_summary.txt` |
| `bench` | `tools/run_benchmark.sh` | `docs/benchmark/` |
| `capture` | `tools/capture_presentation.sh all` | `presentation/turntable.mp4`, `motion_showcase.mp4` + `_trace.log`, `face_performance.mp4` + `_trace.log` |

The script stops at the first failing stage with a non-zero exit code. Rough times on the reference host: build
4-6 min, verify 3 min, bench 2 min, capture 10-15 min (the motion sequence is about 6000 lossless frames).

`tools/build_linux.sh --skip-import` re-packages without touching `unreal/Content`, `--import-only` stops after
the import. Typical times on the reference host: editor module 15-40 s, import 1 min, package 1.5-3.5 min.
Logs: `unreal/Saved/Logs/morphrig_build_editor.log`, `morphrig_import.log`, `morphrig_package.log`.

### U3. Re-import after every re-export

```sh
tools/ue_import.sh
```

The script deletes the generated content folders (`unreal/Content/Operative`, `Content/Showcase`,
`Content/MorphRigData`) and rebuilds them from `export/` and `docs/` - stale assets are never reused. It runs
`tools/unreal_import.py` in `UnrealEditor-Cmd -run=pythonscript -nullrhi` and does the following:

1. **Skeletal mesh** `/Game/Operative/Mesh/SK_Operative` from `export/Operative.fbx` (`FbxImportUI`, routed through
   Interchange; morph targets on, scene/unit conversion on, uniform import scale 1.0, imported normals),
   `LOD1`/`LOD2` with `SkeletalMeshEditorSubsystem.import_lod`, LOD screen sizes 1.0 / 0.35 / 0.14.
2. **Checks against `skeleton_and_sockets.json`**: first bone is `root`, bone count and names, component-space
   reference positions (tolerance 0.05 cm), mesh bottom at 0 and top at about 180 cm (for non-placeholder data).
3. **Morph targets**: every name of `face_controls.json` must exist; each morph is marked as a morph curve on the
   skeleton; morphs that are empty or move a vertex by more than 12 cm are reported as implausible (fatal for final
   data; with placeholder data they are listed in the report as `disabled` and the runtime never drives them).
4. **Sockets** from the JSON: the relative transform is computed from the imported reference pose
   (`UMorphRigEditorLibrary::AddOrUpdateSocket`), the resulting component-space position must match within 0.01 cm.
5. **96 AnimSequences** under `/Game/Operative/Animations/<id>` (30 fps, exported time range, morph curves from the
   `MorphProxy` blend-shape channels). Length must equal the manifest duration (tolerance 1.5 ms). Root motion is
   enabled on the `root_motion` clips and their root displacement is compared with the manifest (0.5 cm). Every
   manifest event becomes a `UMorphEventNotify` (track `MorphRig`) with `EventName` set.
6. **Textures** (`texture_manifest.json`): base colour sRGB; normal maps as `TC_Normalmap` with the green channel
   flipped (Blender bakes OpenGL normals); ORM and mask as linear `TC_Masks`. Images larger than 4096 fail.
7. **Materials** (built by script, no hand-made asset): masters `M_Operative` and `M_OperativeSkin` (both Default Lit),
   one instance per slot `MI_Operative_<Slot>` and the two team variants `MI_Operative_<Slot>_TeamA/_TeamB`
   (accent colour + icon channel), debug materials `M_Debug_Wireframe/_Normals/_Clay`, the overlay outline
   `M_Outline`, and the showcase materials in `/Game/Showcase`. Mesh slots are assigned by slot name; more than
   eight slots fail.
8. **Audio** `/Game/Operative/Audio/dialogue`, optional **props** `export/props/SM_Beacon.fbx`, `SM_PowerCell.fbx`
   as static meshes in `/Game/Operative/Props` (engine basic shapes are used when they are absent).
9. **Runtime data**: copies of the three JSON documents, `dialogue_alignment.json`, `dialogue.txt` and
   `texture_manifest.json` go to `unreal/Content/MorphRigData/` (staged into the pak as non-asset files) together
   with `import_report.json`.
10. **Summary** in the log (`MORPHRIG_IMPORT ...` lines) and in `unreal/Saved/MorphRigImportReport.json`:
    per-LOD triangles/vertices/max bone influences (limits 80k/40k/20k and 8), material slots, textures with sizes
    and a GPU memory estimate (block-compressed formats, full mip chain), per-clip length/frames/curves/notifies,
    socket error, morph statistics. Any mismatch raises, the commandlet exits non-zero and `ue_import.sh` prints
    `IMPORT FAILED`.

Import and packaging both rewrite `unreal/Content`; the scripts take a pid lock
(`unreal/Saved/.morphrig_content.lock`) and refuse to run twice at the same time, and packaging fails when a staged
file disappears while the pak is written. After editor runs the scripts remove the machine-specific
`AndroidFileServer` section the editor adds to `DefaultEngine.ini`.

Inputs flagged `"placeholder": true` are accepted with a warning (some checks are relaxed) and the showcase HUD
shows `[PLACEHOLDER ASSETS]`.

### U4. Package details

`build_linux.sh` calls `RunUAT BuildCookRun -platform=Linux -clientconfig=Development -build -cook -stage -pak
-archive -nodebuginfo`. Output: `build/Linux/MorphRig.sh`, `build/Linux/MorphRig/`, `build/Linux/Engine/`
(about 0.8 GB). Cooked content: the map `/Game/Maps/Showcase` plus the always-cook directories
`/Game/Operative`, `/Game/Showcase`, `/Engine/BasicShapes`, `/Engine/EngineResources` (assets are loaded by path
at runtime so a re-import never needs a code change). A Development client is packaged on purpose: it keeps the
console (`~`, `mr ...`) and the log.

Renderer settings (`unreal/Config/DefaultEngine.ini`): Vulkan SM6 on Linux (DX12 SM6 declared for Windows),
no baked lighting, virtual shadow maps, Lumen GI off (`r.DynamicGlobalIlluminationMethod=0`), screen-space
reflections, TAA at 100 % screen percentage (no upscaling, no frame generation), motion blur and auto exposure off,
texture streaming off (small texture set, deterministic captures), VSync off.

### U5. Running

```sh
tools/run_showcase.sh                                   # interactive
MORPHRIG_OFFSCREEN=1 tools/run_showcase.sh -MorphSequence -MorphQuit -MorphFixedFps=30   # headless deterministic run
```

`run_showcase.sh` passes `-windowed -ResX=1920 -ResY=1080`; with `MORPHRIG_OFFSCREEN=1` it adds
`-RenderOffScreen -ForceRes -unattended` for hosts without a presentable display. All automation options are listed
in `docs/showcase_controls.md`. The state/event trace is written to `MorphRig/Saved/MorphRigTrace.log` below the
client (or `-MorphTrace=<file>`).

Note on the build sandbox used for this delivery: its only display is an Xvfb server that offers no
Vulkan-presentable surface, so the packaged client could only be executed with `-RenderOffScreen` there
(GPU rendering on the RTX 5090 through Vulkan, verified in the log). The windowed start path is the stock engine
one and is the default of `run_showcase.sh`.

### U6. Presentation videos and benchmark

```sh
tools/capture_presentation.sh all        # turntable.mp4, motion_showcase.mp4 (+ trace), face_performance.mp4 (+ audio)
tools/run_benchmark.sh                   # docs/benchmark/*.csv, *.json, host.txt, benchmark_trace.log
```

Both use the packaged client. Capture runs with a fixed 30 fps time step and writes lossless PNG frames
(`MORPHRIG_CAPTURE_DIR`, default `unreal/Saved/Capture`; the motion sequence needs several GB) which are encoded
with x264 (CRF 17) and then removed (`MORPHRIG_KEEP_FRAMES=1` keeps them). The client hands every read-back frame to
the engine's image write queue, so PNG compression runs on worker threads (30 frames per second and more on the
reference host instead of 3 - 8 with the engine's own synchronous screenshot writer). `face_performance.mp4` muxes
`source/audio/dialogue.wav`; its delay is read from the capture trace (time of the `line_start` marker minus time
of the first captured frame), so picture and sound stay locked to the clip. The benchmark renders in real time
(no fixed step), warms up for 10 s and samples 20 s for one and for ten Operatives at 1920x1080.

### U7. Windows / other targets

The module uses only engine-portable code (no platform API, no editor-only component at runtime, legacy key polling
for input, engine basic shapes for the room). Windows settings are declared in `DefaultEngine.ini`; packaging for
Windows was not part of this assignment and was not run.

### U8. Project layout

```text
unreal/MorphRig.uproject
unreal/Config/Default{Engine,Game,Input}.ini
unreal/Source/MorphRig/           C++ module (see docs/unreal_implementation_notes.md)
unreal/Content/Maps/Showcase      empty map; the room is built at runtime
unreal/Content/Operative/...      generated by the import
unreal/Content/Showcase/...       generated by the import (materials)
unreal/Content/MorphRigData/...   generated by the import (runtime JSON)
tools/ue_env.sh                   locates the engine / wrapper for the scripts
tools/ue_import.sh, tools/unreal_import.py
tools/build_linux.sh, tools/run_showcase.sh
tools/capture_presentation.sh, tools/run_benchmark.sh, tools/scripts/*.txt
tools/ue_full_cycle.sh, tools/verify_trace.py
docs/verification/, docs/benchmark/   written by the scripts above
```
