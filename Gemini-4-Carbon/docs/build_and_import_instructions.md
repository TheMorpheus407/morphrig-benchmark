# MORPHRIG — Reproducible Build, Export, Import & Packaging Instructions

All pipeline stages run **100% headlessly** (no GUI windows are opened) and keep all intermediate/temporary files inside the project directory (`TMPDIR="$PWD/.tmp_work"`).

---

## 1. Host & Toolchain Reference

Verified against [`environment.json`](../environment.json):
- **OS**: NixOS 26.05 (x86-64, Linux 6.18)
- **CPU / RAM / GPU**: AMD Ryzen 9 9950X (16C/32T), 91 GiB RAM, NVIDIA GeForce RTX 5090 (32 GiB, Vulkan SM6)
- **Blender**: `blender` (`5.1.1`)
- **Unreal Engine**: `5.8.3` (bundled Clang `20.1.8`), invoked via `$UE_EXEC` (`$HOME/UnrealEngine/bin/ue-exec` on NixOS, or directly via `$UE_ROOT` on standard Linux)
- **Media & Speech Tools**: `ffmpeg 8.0`; `espeak-ng 1.52` via `nix-shell -p espeak-ng`

---

## 2. Regenerating Source Audio, PBR Textures, `.blend` & FBX Exports (Optional)

All source files (`source/Operative.blend`, `source/textures/*.png`, `source/audio/*`, `export/Operative.fbx`, `export/animations/*.fbx`) are already built and delivered in the repository. To rebuild everything cleanly from scratch:

```bash
mkdir -p "$PWD/.tmp_work"
export TMPDIR="$PWD/.tmp_work"

# 1. Synthesize spoken dialogue WAV (48 kHz 16-bit mono) + IPA/viseme alignment JSON
nix-shell -p espeak-ng --run "python3 source/generators/generate_dialogue_audio.py"

# 2. Generate all 25 2048x2048 PBR texture maps (Team A Cyan & Team B Crimson-Amber)
python3 source/generators/generate_textures.py

# 3. Build source/Operative.blend (LOD0/1/2, 92 DEF + 131 CTRL/MCH rig, 46 shape keys,
#    96 editable CTRL_<id> + baked <id> actions) and export all FBX files + JSON manifests
blender -b --factory-startup -P tools/export_and_bake.py -- --rebuild-all

# 4. Regenerate embedded C++ animation/marker/curve metadata header if clips changed
python3 source/generators/generate_ue_meta.py
```

If an animator edits any `CTRL_<id>` or `SK_CTRL_<id>` action directly inside `source/Operative.blend`, rebake and re-export without regenerating meshes:

```bash
TMPDIR="$PWD/.tmp_work" blender -b --factory-startup -P tools/export_and_bake.py -- --rebake
```

---

## 3. Compiling Unreal C++, Importing Assets Headlessly & Packaging Linux Client

A single command compiles `MorphRigEditor`, runs headless Python import (`unreal/Scripts/import_assets.py`) if `unreal/Content/MorphRig/` is not yet populated, and packages the standalone Linux Development build into `build/Linux/`:

```bash
./tools/build_linux.sh
```

To force a clean re-import of all 25 textures, 6 master materials, `Operative.fbx` (+ LOD1/LOD2 + 10 sockets), `SW_Dialogue`, all 96 `AnimSequence`s, `ABP_Operative`, and `ShowcaseMap` before packaging:

```bash
./tools/build_linux.sh --reimport
```

### Individual Manual Steps (Equivalent to `tools/build_linux.sh`)

```bash
mkdir -p "$PWD/.tmp_work"
UE_EXEC="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"

# Step A: Compile C++ Editor module
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' \
  MorphRigEditor Linux Development \
  -Project="$PWD/unreal/MorphRig.uproject" -WaitMutex

# Step B: Run headless Python asset import & invariant assertions
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' \
  "$PWD/unreal/MorphRig.uproject" \
  -run=pythonscript -script="$PWD/unreal/Scripts/import_assets.py" \
  -nullrhi -unattended -nopause -nosplash

# Step C: Cook, stage, pak & archive standalone Linux showcase
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' BuildCookRun \
  -project="$PWD/unreal/MorphRig.uproject" \
  -noP4 -platform=Linux -clientconfig=Development -serverconfig=Development \
  -build -cook -allmaps -stage -pak -iostore -archive \
  -archivedirectory="$PWD/build" -utf8output -unattended -nullrhi
```

---

## 4. Running the Standalone Linux Showcase & Automated Modes

### Interactive Showcase (Windowed)

```bash
# On NixOS (using ue-exec wrapper; on Ubuntu/Fedora run ./build/Linux/MorphRig.sh directly):
"${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}" "$PWD/build/Linux/MorphRig.sh" -ResX=1920 -ResY=1080
```

### Headless Offscreen Verification, Benchmark & Video Capture (Zero Windows)

```bash
UE_EXEC="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"

# 1. Run deterministic combined-state showcase & write state/event trace log
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  "$PWD/build/Linux/MorphRig.sh" \
  -RenderOffScreen -AudioMixer -ResX=1920 -ResY=1080 -AutoShowcase

# 2. Run warmed-up 1 vs 10 Operatives 1920x1080 frame-time benchmark (no frame generation)
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  "$PWD/build/Linux/MorphRig.sh" \
  -RenderOffScreen -AudioMixer -NoVSync -ResX=1920 -ResY=1080 -BenchmarkPerf

# 3. Capture real-time 30 FPS PNG sequences for presentation/*.mp4
TMPDIR="$PWD/.tmp_work" "$UE_EXEC" \
  "$PWD/build/Linux/MorphRig.sh" \
  -RenderOffScreen -AudioMixer -ResX=1920 -ResY=1080 \
  -CaptureVideo=turntable -CaptureDir="$PWD/.tmp_work/cap_turntable"
```
