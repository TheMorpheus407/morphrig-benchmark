# Build and import instructions

Everything below runs from the `MorphRig/` folder. Commands were run on the reference host (NixOS, Blender 5.1.1, Unreal Engine 5.8.3, ffmpeg 8.0). The Blender asset is produced procedurally by the generator scripts in `source/generators/`; no step needs an interactive edit.

## 1. Requirements

| Tool | Used for | Notes |
|---|---|---|
| Blender 5.1.1 (`blender` on the PATH) | build, export, QA renders | headless: `blender -b --factory-startup -P script.py -- args` |
| Python 3.13 (system) | validation scripts | plain standard library |
| ffmpeg 8.0 | contact sheets, video encoding, audio muxing | |
| piper-tts 1.4.2 with eSpeak NG | speech synthesis (`tools/piper_py.sh`) | already in `/nix/store` on the host; otherwise `nix-build '<nixpkgs>' -A piper-tts --no-out-link` and set `PIPER_TTS_OUT` to the resulting store path |
| Whisper (`whisper` CLI, model `small.en`) | independent check of the alignment | optional, only `verify_dialogue.py` needs it |
| Unreal Engine 5.8.3 via `ue-exec` | import, build, packaging | see section 6 |

## 2. Build `source/Operative.blend`

```bash
blender -b --factory-startup -P source/generators/build_all.py -- --blend "$PWD/source/Operative.blend"
```

The build takes about 10 seconds without textures and about one minute with a texture bake. Options: `--bake-textures` (force a bake), `--no-textures` (skip UV/material setup), `--no-clips` (rig and meshes only). Textures are baked into `source/textures/` when they are missing or when the UV layout changed (a hash of the UVs is stored in `texture_manifest.json`).

Pipeline steps inside `build_all.py`: deformation skeleton (`skeleton_def.py`, `rig_skeleton.py`) → meshes and skin weights (`build_character.py` with `body_base.py`, `head.py`, `hands.py`, `hs.py`, `cyber_arm.py`, `accessories.py`, `hair.py`, `skinning.py`) → UV atlases, textures, materials (`uvtex.py`, `paint.py`) → control rig and drivers (`build_rig.py`) → face shape keys and controls (`face_shapes.py`) → 96 clip actions and 7 skinning test poses (`clips_*.py`, `pose_tests.py`) → embedded tools panel (`mr_tools.py`) → save.

Source authorship: everything is procedural (numpy geometry, Blender Python). No mesh, texture, motion or skinning data comes from a third party.

## 3. Textures

`source/textures/T_<Material>_<map>.png`, Unreal conventions (see `docs/material_and_lod_report.json` for sizes and memory):

| Suffix | Content |
|---|---|
| `BC` | base colour, sRGB |
| `N` | tangent normal map, DirectX convention (green down); the Blender materials flip the green channel |
| `ORM` | R = ambient occlusion, G = roughness, B = metallic (linear) |
| `E` | emission intensity (linear), team coloured in the shader (Cyber only) |
| `TM` | team mask (linear): R accent paint, G circle icon (team A), B diamond icon (team B); Suit, Armor, Cyber |

The same files are used by the Blender materials and by the Unreal import (one copy: `export/textures` is a relative symbolic link to `source/textures`).

## 4. Speech (optional, the shipped take is already in `source/audio/`)

```bash
tools/piper_py.sh source/generators/make_dialogue.py        # WAV, transcript, alignment (needs source/audio/voice/*.onnx)
python3 source/generators/verify_dialogue.py                # Whisper cross-check, written into dialogue_alignment.json
```

The voice model is not rebuilt by the scripts. If `source/audio/voice/en_US-ljspeech-high.onnx` is missing, download it (public domain training data, MIT repository, checksums in `docs/THIRD_PARTY_ASSETS.csv`):

```bash
B=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high
mkdir -p source/audio/voice && cd source/audio/voice
curl -LO $B/en_US-ljspeech-high.onnx && curl -LO $B/en_US-ljspeech-high.onnx.json
curl -L $B/MODEL_CARD -o MODEL_CARD_en_US-ljspeech-high.txt
```

A new synthesis run gives a slightly different take (the model adds random noise). After a rerun, rebuild the .blend so the `dialogue` clip follows the new alignment (its length follows the audio).

## 5. Export for Unreal

```bash
blender -b source/Operative.blend -P tools/export_and_bake.py -- --out "$PWD"
```

About 35 seconds. It writes `export/Operative.fbx` (LOD0 with the skeleton), `export/Operative_LOD1.fbx`, `export/Operative_LOD2.fbx`, `export/props/*.fbx`, one baked `export/animations/<id>.fbx` per required clip (bones plus the morph-target curves of the face), and the JSON documents `docs/animation_manifest.json`, `docs/skeleton_and_sockets.json`, `docs/material_and_lod_report.json`, `docs/export_report.json`. Options: `--only walk_f,idle_relaxed` (a subset of clips), `--no-mesh`, `--no-clips`.

Export conventions: metres in Blender become centimetres in the FBX through a temporary scene scaled by 100 (FBX unit scale 1), armature object `Armature`, 30 fps, Blender frame = 1 + clip frame, single `root` bone. Unreal receives `(x, y, z)` as `(x, -y, z)`. The character is 180 cm tall without an import scale.

## 6. Unreal import, build and run

The project is `unreal/MorphRig.uproject` (module `MorphRig`, runtime code in `unreal/Source/MorphRig/`, no editor-only code). On the reference host Unreal runs through the FHS wrapper `~/UnrealEngine/bin/ue-exec`, because NixOS cannot start the engine binaries directly. `tools/ue_env.sh` sets `UE_EXEC`, `MORPHRIG_ROOT` and `MORPHRIG_UPROJECT`, and every helper below sources it. Paths handed to `ue-exec` must lie below `$HOME`. On a normal Linux install set `UE_EXEC` to `env` (or any launcher that starts the command) and keep `$UE_ROOT` pointing at the engine.

The delivery does not contain build products: `unreal/Binaries`, `unreal/Intermediate`, `unreal/Saved` and `unreal/DerivedDataCache` are created by the commands below (the first editor build and the first cook take several minutes longer than the repeats).

### 6.1 Compile the editor module

```bash
tools/ue_build_editor.sh          # MorphRigEditor, Linux, Development (about 10 s when nothing changed)
```

### 6.2 Import export/ and docs/ into the project

```bash
tools/ue_import_all.sh            # all steps
tools/ue_import_all.sh clips      # one or more steps: mesh,clips,props,audio,materials,assets,level
```

The import runs in `UnrealEditor-Cmd` (Python, `-nullrhi`, about 1 to 3 minutes) and is idempotent: every step replaces what it owns, so it can be repeated after every Blender export. The `mesh` step deletes and recreates the skeleton, the mesh and the physics asset (a reimport onto an old skeleton keeps its old bone positions), so the `clips` step has to follow it: import `mesh,clips` together or run all steps. The log is `unreal/Saved/Logs/ue_import_all.log`; the last line must read `IMPORT OK`.

| Step | Reads | Creates in `unreal/Content/` |
|---|---|---|
| `mesh` | `export/Operative.fbx`, `_LOD1.fbx`, `_LOD2.fbx`, `docs/skeleton_and_sockets.json` | `Operative/Mesh/SK_Operative` (LOD0 to 2, 44 morph targets), skeleton, physics asset, the 21 sockets |
| `clips` | `export/animations/*.fbx`, `docs/animation_manifest.json` | 96 `AnimSequence` assets `Operative/Anims/<id>`: root motion for `dash_*`, additive type for `hit_*`, one notify per manifest event, morph curves kept only where the manifest lists them |
| `props` | `export/props/*.fbx` | `SM_PowerCell`, `SM_Beacon` |
| `audio` | `source/audio/dialogue.wav` | `Operative/Audio/dialogue` |
| `materials` | `source/textures/*.png` | textures (BC, N, ORM, E, TM with the right compression and colour space), master materials, 7 slot instances for team A and team B, outline, debug, room and effect materials |
| `assets` | manifest, sockets, alignment | `Operative/DA_OperativeAssets` (hard references and the JSON texts the runtime reads) |
| `level` | none | `Showcase/L_Showcase` (room actor, player start, game mode) |

### 6.3 Package the Linux client

```bash
tools/build_linux.sh              # BuildCookRun: Linux, Development client, pak, archived into build/Linux
```

An incremental package takes about 1.5 minutes; the first cook of a fresh checkout takes longer. The log is `unreal/Saved/Logs/build_linux.log`; the script ends with `PACKAGE OK`. The client starts with `build/Linux/MorphRig.sh` (on a normal Linux with a Vulkan driver) or with `tools/ue_run_packaged.sh` (through `ue-exec`).

### 6.4 Run

```bash
tools/ue_run_packaged.sh                                    # interactive showcase, windowed 1920x1080, F1 shows the controls
tools/ue_run_packaged.sh -RenderOffScreen -ShowcaseSequence -ExitAfterSequence -NoPanel -SequenceTrace=/path/trace.txt
tools/ue_run_packaged.sh -PerfLog=$PWD/docs/perf/perf_10_instances.csv -Instances=10 -ExitAfterPerf
```

| Switch | Effect |
|---|---|
| `-ShowcaseSequence`, `-ExitAfterSequence` | run the deterministic sequence (19 steps, 59 checks, 158 s of simulated time at a fixed 30 fps step, about 10 s of wall time on the reference machine) and quit afterwards; `SHOWCASE_TRACE` lines go to the log and to `Saved/ShowcaseTrace.txt` (`-SequenceTrace=` changes the file). The exit status is 0 when every check passed and 2 when one failed |
| `-NoPanel`, `-NoUI`, `-NoOutline`, `-NoStudio`, `-NoDialogue` | start without the mouse panel, without the HUD, without the team outline, without the studio backdrop of the captures, without the speech in the face capture |
| `-View=`, `-Team=`, `-LOD=`, `-RenderMode=`, `-Overlay=`, `-Studio`, `-Instances=` | initial view, team, forced LOD, render mode, overlay, studio backdrop, number of instances |
| `-CaptureMode=turntable|motion|face`, `-CaptureDir=`, `-CaptureEvery=`, `-MaxCaptureFrames=` | fixed 30 fps time step and one PNG per frame (used by `tools/make_videos.sh`) |
| `-PerfLog=`, `-Instances=1|10`, `-PerfWarmup=`, `-PerfWarmupSeconds=`, `-PerfFrames=`, `-PerfSeconds=`, `-ExitAfterPerf` | frame-time log (CSV plus a summary with hardware and settings); the defaults are 240 frames and 5 s of warm-up and a 20 s sample |
| `-Shot=`, `-ShotClip=`, `-ShotTime=`, `-ShotFrame=`, `-TracePose`, `-SeqFrom=`, `-SeqTo=` | single screenshots and partial sequences for debugging |

`-RenderOffScreen` keeps every window off the desktop. The performance run is the only one that needs the window (windowed 1920x1080, VSync off).

### 6.5 Presentation videos

```bash
tools/make_videos.sh              # turntable, motion and face (or name the ones you want)
```

The script runs the packaged client offscreen in the three capture modes, encodes the PNG frames with ffmpeg (H.264, CRF 18, 30 fps) into `presentation/`, muxes `source/audio/dialogue.wav` into the face video (the clip starts one time step before the first frame, `FACE_AUDIO_SKIP` cuts 0.033 s from the audio) and deletes the frames. The turntable shows the neutral studio floor: one revolution of team A without outline, one of team B with the rim outline. The motion video is the deterministic sequence with the HUD. The face video is the dialogue close-up with subtitles.

### 6.6 Check the delivery

```bash
python3 tools/verify_delivery.py --blender
```

Checks the layout, the manifest against the inventory, the LOD, material, texture and skeleton limits, the dialogue files, the videos and the absence of private paths, temporary files and missing texture links.

## 7. QA scripts (Blender)

| Script | What it produces |
|---|---|
| `source/generators/qa_pose_tests.py -- OUT.png [--hq]` | the skinning demonstration sheet (`docs/skinning_pose_tests.png`) |
| `source/generators/qa_face_sheets.py -- DIR` | `face_expressions.png` and `face_visemes.png` (`docs/`) |
| `source/generators/qa_lib.py` | contact sheets, loop error, ground clearance and skating helpers used by the clip tests |

## 8. Reproducibility notes

* Geometry, weights, rig, clips and textures rebuild to the same content from the scripts. Two builds made hours apart gave FBX files whose meshes (vertex positions, UVs, skin weights, shape keys) and animation curves compare equal after re-import for every unchanged part; only timestamps and internal ids inside the files differ. The UV layout hash is stable between runs.
* The only non-deterministic step is speech synthesis (see section 4); the shipped WAV and alignment belong together.
* The `.blend` stores its texture paths relative to `source/`, so the folder can be moved as a whole.
