# MORPHRIG — Build and import instructions

Everything below runs on Linux x86-64. The paths assume the repository root
is the current working directory.

---

## 0. Tooling

| Tool | Version used | Notes |
|---|---|---|
| Blender | 5.1.1 | authoritative source, geometry, rig, animation, textures |
| Unreal Engine | 5.8.3 | runtime, cooking, packaging |
| ffmpeg | system | encodes the presentation videos |
| piper-tts | nix package | renders the spoken line, build time only |

The engine is referenced, not vendored:

```bash
export UE_ROOT=/home/morpheus/UnrealEngine/5.8.3
export UE_EXEC=/home/morpheus/UnrealEngine/bin/ue-exec   # runs a command inside the engine FHS
```

## 1. Rebuild the character, the rig and the textures

```bash
blender -b --factory-startup -P source/generators/build_character.py -- \
    --textures source/textures --out source/Operative.blend
```

This writes the armature, the mesh, the automatic skin weights, the face
shape keys, the eight materials and the 24 textures. It takes about six
seconds.

## 2. Bake the 96 clips

```bash
blender -b --factory-startup -P source/generators/build_animations.py -- \
    --out source/Operative.blend
```

Every clip bakes all 71 deform bones on every frame. The script writes
`docs/animation_manifest.json`.

### 2a. Validate the authored poses (optional but recommended)

```bash
blender -b --factory-startup -P source/generators/validate_pose.py
```

The script compares every authored pose against Blender's own evaluation of
the rig and reports the mismatches. The current result is **0 errors over
72 poses in 15 clips**.

### 2b. Validate the skinning (optional but recommended)

```bash
blender -b --factory-startup -P source/generators/validate_skin.py
```

The script checks that no vertex is left unbound, that the evaluated mesh
never grows an edge much longer than the rest mesh, and that no vertex still
carries the generic `body` tag. It writes `docs/skin_report.json` and exits
with a non zero code on a problem. The current result is **PASS**.

## 3. Build the LODs

```bash
blender -b --factory-startup -P source/generators/build_lods.py
```

Writes `docs/material_and_lod_report.json`:

| LOD | Triangles | Limit |
|---|---|---|
| LOD0 | 38 902 | 80 000 |
| LOD1 | 23 810 | 40 000 |
| LOD2 | 13 057 | 20 000 |

## 4. Export the FBX files

```bash
blender -b --factory-startup -P source/generators/export_fbx.py
```

Produces

```
export/Operative.fbx                 the mesh with all 96 actions
export/animations/<clip>.fbx         one file per clip
export/LOD/Operative_LOD1.fbx
export/LOD/Operative_LOD2.fbx
export/textures/<material>_<map>.png
docs/animation_manifest.json
docs/skeleton_and_sockets.json
```

The FBX is written with `global_scale=1.0`, `axis_forward='-Z'` and
`axis_up='Y'`, so Unreal imports it as 180 cm tall with the correct axes and
**without** any import scale repair.

Two corrections are applied while the files are written, both of them are
undone afterwards, so `source/Operative.blend` keeps the authored values:

| Constant | Value | Why |
|---|---|---|
| `FBX_UNIT_FIX` | `100.0` | Blender writes the bone animation curves in metres but scales the mesh and the bone rest hierarchy into centimetres, so the location curves are multiplied by 100 to arrive in Unreal as centimetres |
| `FBX_YAW` | `90°` | the Blender character faces `-Y`, Unreal expects the character of an actor to face `+X`, so the armature is turned around Z while the files are written |

Both are described in [`known_issues.md`](known_issues.md) §17 and §23, and
both are written into `docs/animation_manifest.json` under
`fbx_export_corrections`.

To refresh only the documentation, without rewriting the FBX files:

```bash
blender -b --factory-startup -P source/generators/export_fbx.py -- --manifest-only
```

It rebuilds `docs/animation_manifest.json` and `docs/skeleton_and_sockets.json`
from the blend and leaves every file in `export/` untouched.


## 5. Render the speech (only needed when the line changes)

```bash
nix-shell -p piper-tts --run "python3 tools/make_dialogue.py"
```

Produces `source/audio/dialogue.wav` (12.533 s), the transcript and the
alignment JSON with one entry per word.

## 6. Build the Unreal module

```bash
"$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' \
    MorphRigEditor Linux Development \
    -project="$PWD/unreal/MorphRig.uproject" -waitmutex

"$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' \
    MorphRig Linux Development \
    -project="$PWD/unreal/MorphRig.uproject" -waitmutex
```

## 7. Import into Unreal

```bash
"$UE_EXEC" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' \
    "$PWD/unreal/MorphRig.uproject" \
    -run=pythonscript -script="$PWD/tools/ue_import.py" \
    -unattended -nopause -nosplash -nullrhi -NoLogTimes
```

The script is idempotent, it overwrites what it created before. It produces

| Asset | Path |
|---|---|
| Skeletal mesh | `/Game/MorphRig/Meshes/SK_Operative` |
| Skeleton | `/Game/MorphRig/Meshes/Operative_Skeleton` |
| 3 LODs inside the mesh | LOD0 / LOD1 / LOD2 |
| 96 animations | `/Game/MorphRig/Animations/A_<clip>` |
| 24 textures | `/Game/MorphRig/Textures/<material>_<map>` |
| 8 materials | `/Game/MorphRig/Materials/M_<material>` |
| Team accent instance | `/Game/MorphRig/Materials/MI_M_Accent` |
| Normal view material | `/Game/MorphRig/Materials/M_ViewNormal` |
| Clay view material | `/Game/MorphRig/Materials/M_ViewClay` |
| Clip table | `/Game/MorphRig/DT_MorphRigClips` |
| Speech | `/Game/MorphRig/Audio/S_Dialogue` |
| Showcase level | `/Game/MorphRig/Maps/L_MorphRigShowroom` |

A JSON report is written to `build/ue_import_report.json`. The report is
rewritten and flushed after every stage, so an interrupted run still leaves a
valid file behind.

### 7a. Importing only some stages

The import runs every stage by default. `MORPHRIG_STAGES` selects a subset,
which is useful when only one part of the production changed:

```bash
MORPHRIG_STAGES="animations" "$UE_EXEC" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' ...
```

The available stage names are `clean`, `textures`, `mesh`, `lods`,
`animations`, `materials`, `viewmaterials`, `assign`, `table`, `audio`,
`level` and `save`.

### 7a. Import details that matter

* **Morph targets.** The mesh is imported with `import_morph_targets` on, so
  the 30 face shape keys arrive as morph targets. The face animation travels
  as morph target curves on the `A_dialogue` sequence.
* **Root motion.** `enable_root_motion` is set on the four dash sequences.
  Everything else keeps the Unreal default. The root bone of the Operative is
  the second bone of the imported skeleton, the exporter writes the armature
  object as a bone of its own, so the runtime measures the root motion on the
  `root` bone and not on the first bone of the skeleton. See
  [`known_issues.md`](known_issues.md) §18 and §22.

* **LODs.** `USkeletalMeshEditorSubsystem::import_lod` adds LOD1 and LOD2 to
  the imported mesh from the two LOD FBX files, so the mesh really has three
  different LODs.
* **Materials.** Every material has a `BaseColorTexture`, a `NormalTexture`
  and an `ORMTexture` parameter plus the usual roughness, metallic and
  ambient occlusion links. `M_Accent` additionally has a `TeamColor` vector
  parameter that multiplies its base colour; `M_Energy` drives the emissive
  channel.
* **View materials.** `M_ViewNormal` is an unlit material that shows the world
  space normal of the surface, `M_ViewClay` is a flat grey. The runtime swaps
  the eight authored slots of the Operative for these two while the shading
  view is not "textured" (`M` in the showcase). They are helper materials and
  are not part of the eight slot budget of the character.

## 8. Package the Linux client

```bash
tools/build_linux.sh
```

This builds the `MorphRig` game target, cooks the content, stages it, packs
it and archives it into `build/Linux`. The result is a self contained
client:

```
build/Linux/MorphRig.sh                   the launcher
build/Linux/MorphRig/Binaries/Linux/     the engine and the game
build/Linux/MorphRig/Content/             the cooked content
build/Linux/Engine/                       the shared engine runtime
```

### 8a. Run the client and capture the performance log

```bash
cd build/Linux
./MorphRig.sh /Game/MorphRig/Maps/L_MorphRigShowroom \
    -windowed -ResX=1920 -ResY=1080 -log -abslog="$PWD/morphrig_client.log"
```

The client writes

* `Saved/Logs/MorphRigPerf.csv` — one row per second with the frame count,
  the average, minimum, maximum and 99th percentile frame time, the frame
  rate and the physical memory in use, followed by the measured cost of the
  game thread, the render thread, the GPU, the HUD, the operative tick and
  the animation update,
* `Saved/Logs/MorphRig.log` — the full log, including the `PERF_MACHINE`
  line with the CPU, RAM and GPU of the machine and the `PERF_SUMMARY` line
  with the totals of the run,
* the `showcase step=…` trace of the deterministic showcase sequence.

## 9. Render the presentation videos

```bash
tools/render_videos.sh --samples 24
```

Each video is rendered by its own Blender process with Cycles on the CPU and
encoded with ffmpeg. The PNG frames are kept in `presentation/_frames_*` so
an interrupted run resumes instead of starting over.

| Video | Content |
|---|---|
| `presentation/turntable.mp4` | the Operative seen from all sides, 6 s, 1080 x 1920 |
| `presentation/motion_showcase.mp4` | twelve delivered clips in sequence, 13 s, 1280 x 720 |
| `presentation/face_performance.mp4` | the spoken performance, close up, with the audio, 12.5 s, 1080 x 1080 |

## 10. Folder map

```
source/            the authoritative Blender source
  Operative.blend  the character, the rig, the 96 actions
  generators/      the generators, one module per topic
  textures/        the 24 generated textures
  audio/           the spoken line, the alignment, the voice model
export/            the FBX files and the exported textures
unreal/            the Unreal project and the C++ runtime module
build/Linux/       the packaged client
docs/              the documentation and the reports
tools/             the build, import and render helpers
presentation/      the three videos
```
