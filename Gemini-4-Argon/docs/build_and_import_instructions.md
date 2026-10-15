# Build, Export, and Unreal Engine 5.8.3 Import Instructions

## 1. Environment & Toolchain

All scripts and build commands use the local NixOS x86-64 environment declared in [`environment.json`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/environment.json):

- **Blender**: `/run/current-system/sw/bin/blender` (`5.1.1`)
- **Unreal Engine 5.8.3**: `/home/morpheus/UnrealEngine/5.8.3`
- **NixOS FHS Wrapper**: `/home/morpheus/UnrealEngine/bin/ue-exec` (required around all Unreal Engine binaries and packaged executables on NixOS)
- **FFmpeg**: `/run/current-system/sw/bin/ffmpeg` (`8.1`)

---

## 2. Rebuilding Source Assets from Scratch

Every source asset in `source/` and `export/` can be regenerated deterministically from the repository root:

### Step 2.1 — Spoken Dialogue Audio & Phoneme/Viseme Alignment
```bash
python3 source/generators/generate_dialogue_audio.py
```
Generates:
- `source/audio/dialogue.wav` (14.50 s, 44.1 kHz, 16-bit mono PCM)
- `source/audio/dialogue.txt`
- `source/audio/dialogue_alignment.json` (word, phoneme, viseme, brow, and blink intervals)

### Step 2.2 — PBR Texture Sets (Team A & Team B Variants)
```bash
python3 source/generators/generate_textures.py
```
Generates 42 `1024x1024` PNG textures across 6 material slots (`M_Operative_Skin`, `M_Operative_Eyes`, `M_Operative_Suit`, `M_Operative_Armor`, `M_Operative_CyberArm`, and `M_Operative_Props_Accent` for both `TeamA` Cyan / Hex-Chevron and `TeamB` Amber / Crossed-Diamond) in `source/textures/` and `export/textures/`.

### Step 2.3 — Authoritative Blender File (`source/Operative.blend`)
```bash
blender -b -P source/generators/build_operative_blend.py
```
Builds `source/Operative.blend` containing:
- `Operative_LOD0` (`39,070` tris), `Operative_LOD1` (`16,334` tris), `Operative_LOD2` (`5,602` tris)
- `Armature_Operative` (93 single-root deformation bones + `CTRL_*`/`MCH_*` animator rig)
- 38 facial and corrective Shape Keys on `Operative_LOD0`
- All 96 required actions (`30 FPS`) + 7 extreme deformation stress-test poses

### Step 2.4 — Bake & Export FBX Deliverables (`export/`)
```bash
blender -b source/Operative.blend -P tools/export_and_bake.py
```
Exports:
- `export/Operative.fbx` (LOD0 mesh + 93 deformation bones + 38 Morph Targets)
- `export/Operative_LOD1.fbx` and `export/Operative_LOD2.fbx`
- All 96 baked animation FBX files in `export/animations/<id>.fbx` (`only_deform_bones=True`, `bake_step=1.0`, `30 FPS`, `add_leaf_bones=False`)
- Updates `docs/skeleton_and_sockets.json`, `docs/animation_manifest.json`, and `docs/material_and_lod_report.json`

---

## 3. Compiling, Importing into Unreal Engine 5.8.3, and Packaging Linux Standalone Client

Run the single reproducible build script from the repository root:

```bash
./tools/build_linux.sh
```

What `tools/build_linux.sh` performs:
1. **Compiles `MorphRigEditor`**: Runs `/home/morpheus/UnrealEngine/bin/ue-exec /home/morpheus/UnrealEngine/5.8.3/Engine/Build/BatchFiles/Linux/Build.sh MorphRigEditor Linux Development` against `unreal/MorphRig.uproject`.
2. **Headless Asset Import & Map Setup**: Runs `UnrealEditor-Cmd` with `-run=pythonscript -script=tools/unreal_import_assets.py` to deterministically import:
   - `/Game/MorphRig/Textures/*` (PBR BaseColor, ORM, Normal, Emissive maps)
   - `/Game/MorphRig/Audio/dialogue` (`USoundWave`)
   - `/Game/MorphRig/Character/Operative` (`USkeletalMesh` + `Operative_Skeleton` + 38 Morph Targets + LOD1/LOD2)
   - `/Game/MorphRig/Character/M_Operative_*` (6 PBR Materials wired to textures)
   - `/Game/MorphRig/Animations/<id>` (all 96 `UAnimSequence` assets bound to `Operative_Skeleton`)
   - `/Game/Maps/ShowcaseArena` (`UWorld` default showcase map)
3. **Packages Standalone Linux Client**: Executes `RunUAT.sh BuildCookRun` to build, cook, stage, pak, and archive the standalone Linux x86-64 client into `build/Linux/`.

---

## 4. Running the Packaged Standalone Showcase Client

### Interactive Mode (1920x1080 Windowed)
```bash
/home/morpheus/UnrealEngine/bin/ue-exec ./build/Linux/MorphRig.sh -ResX=1920 -ResY=1080 -Windowed
```

### Automated Deterministic Showcase Sequence (with Trace & Performance Log Output)
```bash
/home/morpheus/UnrealEngine/bin/ue-exec ./build/Linux/MorphRig.sh -ResX=1920 -ResY=1080 -Windowed -ShowcaseSequence -AutoQuit
```
Writes the complete state/event/interruption/performance trace to `unreal/Saved/MorphRigShowcaseTrace.json` (or `build/Linux/MorphRig/Saved/MorphRigShowcaseTrace.json`).

---

## 5. Rendering Presentation Videos (`presentation/*.mp4`)

To re-render the three 1920x1080 30 FPS H.264 `.mp4` presentation videos directly from `source/Operative.blend`:

```bash
blender -b source/Operative.blend -P tools/render_presentation_videos.py
```
Outputs:
- `presentation/turntable.mp4`
- `presentation/motion_showcase.mp4`
- `presentation/face_performance.mp4` (with `source/audio/dialogue.wav` audio stream)
