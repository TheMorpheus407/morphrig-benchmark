# MORPHRIG — Complete Cyberpunk Character Production (`v1.2`)

Original cyberpunk combat operative (**Vesper-7 Tactical Field Operative**) authored end-to-end from scratch in **Blender 5.1.1**, exported via deterministic FBX/JSON pipelines, and integrated into a standalone **Unreal Engine 5.8.3** Linux x86-64 showcase (`build/Linux/MorphRig.sh`).

---

## 1. Deliverable Structure (`SPEC.md` §11 Mapping)

All deliverables reside directly under the repository root `./`:

| Path | Description |
| :--- | :--- |
| `README.md` | Project overview, controls, reproducible headless pipeline commands, and measured performance report. |
| `source/Operative.blend` | Editable Blender 5.1.1 master file: `Operative_LOD0` (`29,268` tris, 46 shape keys), `Operative_LOD1` (`15,218` tris), `Operative_LOD2` (`7,608` tris), `Armature` (`92` `DEF` + `131` `CTRL`/`MCH` bones), 6 PBR materials (`//textures/*.png`), embedded `morphrig_ui.py` sidebar rig panel, and 96 editable `CTRL_<id>` + baked `<id>` actions. |
| `source/textures/*.png` | 25 original `2048x2048` PBR texture maps (BaseColor, Tangent-Space OpenGL Normal, Packed `ORM` `[R=AO, G=Roughness, B=Metallic]`, Emissive, Team Mask, and Team B Crimson-Amber variants). |
| `source/audio/` | `dialogue.txt` (original 36-word spoken script), `dialogue.wav` (`16.484s`, 48 kHz 16-bit mono PCM), and `dialogue_alignment.json` (phoneme & 13-viseme timestamps). |
| `source/generators/*.py` | Deterministic offline generators for character geometry, rig/skinning, textures, 96-clip animation library, dialogue synthesis/alignment, and Unreal C++ metadata tables. |
| `export/Operative.fbx` | Game-ready character mesh + `92`-bone `DEF` skeleton + `46` shape keys (`Operative_LOD1.fbx` and `Operative_LOD2.fbx` alongside). |
| `export/animations/<id>.fbx` | All **96** required motion clips and calibration poses baked at `30 FPS` (`85` clips + `11` poses) plus `morph_curves.json`. |
| `export/textures/*.png` | Exported `2048x2048` PBR texture set consumed by headless Unreal import. |
| `unreal/MorphRig.uproject` | Unreal Engine `5.8.3` C++ & Python project (`Source/MorphRig`, `Source/MorphRigEditor`, `Scripts/import_assets.py`, `Content/MorphRig/...`). |
| `build/Linux/` | Packaged standalone Linux x86-64 Development client (`build/Linux/MorphRig.sh`). |
| `docs/rig_usage.md` | Animator guide for the Blender control rig, IK/FK snap operators, reverse-foot controls, prop handoffs, and facial/viseme rig. |
| `docs/skeleton_and_sockets.json` | Complete 92-bone `DEF` hierarchy, axes, units, rest transforms, and 10 gameplay sockets. |
| `docs/animation_manifest.json` | 96-entry manifest mapping every `required_animations.csv` ID to Blender actions, FBX takes, Unreal assets, frame ranges, loop/root-motion policy, layers, markers, and entry/exit states. |
| `docs/animation_state_contract.md` | State machine contract, transition priorities, pose-snapshot crossfade interruption rules, layered blending, and bitmask-deduplicated event guarantees. |
| `docs/material_and_lod_report.json` | Triangle counts, LOD screen-size thresholds, 6-slot material breakdown, and GPU/disk texture memory report. |
| `docs/performance_report.json` | Measured `1920x1080` Vulkan SM6 benchmark results for `1` and `10` simultaneous Operatives (`frame_generation: false`). |
| `docs/THIRD_PARTY_ASSETS.csv` | Provenance and licensing ledger confirming 100% original character/rig/texture/animation authorship. |
| `docs/build_and_import_instructions.md` | Step-by-step headless rebuild, export, Unreal import, packaging, and verification reference. |
| `docs/known_issues.md` | Engineering trade-offs and documented system boundaries. |
| `tools/export_and_bake.py` | Headless Blender 5.1.1 script (`--rebuild-all` or `--rebake`) baking `CTRL_<id>` to `DEF` and exporting all FBXs and JSON manifests. |
| `tools/build_linux.sh` | Reproducible headless Unreal C++ build, Python asset import, and Linux `BuildCookRun` packaging script. |
| `presentation/turntable.mp4` | `1920x1080` `30 FPS` neutral full-body 360° turntable demonstrating Team A (Vanguard Cyan) and Team B (Helix Crimson-Amber) (`12.0s`). |
| `presentation/motion_showcase.mp4` | `1920x1080` `30 FPS` deterministic 18-step motion, combat, prop handoff, arbitrary interruption, 18.5° slope / 20 cm step Ground IK, death/respawn, and 10-operative top-down showcase (`32.0s`). |
| `presentation/face_performance.mp4` | `1920x1080` `30 FPS` (`48 kHz` AAC audio) close-up spoken facial performance with synchronized lip-sync, blinks, eye darts, emotional arc, and upper-body wrist-console check (`16.484s`). |

---

## 2. Character, Rig, Materials & Animation Summary

- **Scale & Silhouette**: `1.80 m` (`180.0 cm` in Unreal) standing height, soles planted at `Z = 0.0`, facing axis consistent across Blender and Unreal. Asymmetrical tactical crop-jacket, high-collar dorsal neural mantle (`cable_01..03`), left tactical pauldron, hip utility strap (`strap_01..03`), right-forearm retractable mono-blade (`blade_r`), right-wrist compact arc emitter (`emitter_bone_r`) with removable power cell (`cell_bone`), and detachable belt beacon (`beacon_bone`).
- **LOD Hierarchy & Budgets**:
  - `LOD0` (`ScreenSize 1.00`): `29,268` triangles (`<= 80,000` budget), max `4` bone weights/vertex, `46` Blender shape keys (`45` active non-zero `UMorphTarget`s in Unreal + neutral `V_SIL`).
  - `LOD1` (`ScreenSize 0.45`): `15,218` triangles (`<= 40,000` budget).
  - `LOD2` (`ScreenSize 0.20`): `7,608` triangles (`<= 20,000` budget).
- **Materials & Team Readability**: `6` PBR material slots (`<= 8` budget): `M_Skin_FaceBody`, `M_Eyes_Mouth`, `M_Hair`, `M_Suit_Fabric`, `M_CyberArmor`, and `M_Props_Tech`. Supports instant runtime switching between **Team A (Vanguard Cyan + Diamond Crest/Beacon)** and **Team B (Helix Crimson-Amber + Double-Chevron Crest/Beacon)** with optional secondary silhouette/icon cues for `52°` top-down MOBA readability (`~120 px` character height).
- **Skeleton & Sockets**: Single-root (`root`) hierarchy of `92` deformation bones (`<= 140` budget) + `10` verified Unreal `USkeletalMeshSocket`s (`socket_hand_r`, `socket_hand_l`, `socket_emitter_muzzle`, `socket_blade_base`, `socket_blade_tip`, `socket_holster_hip_r`, `socket_back_mount`, `socket_chest_fx`, `socket_head_fx`, `socket_root_fx`).
- **Complete 96-Clip Motion Inventory & Runtime Systems**:
  - Phase-synchronized 8-direction Walk (`150 cm/s`), Run (`400 cm/s`), and Sprint (`650 cm/s`) with starts, stops, `90°` turns (`turn_l90/r90`), `180°` pivots (`pivot_l180/r180`), and Jump/Fall/Land (`jump_start`, `jump_air`, `fall`, `jump_land`, `land_heavy`).
  - Cached 9-sample Aim Offset Grid (`±60°` yaw, `±35°` pitch) + stereo eye/head Look-At (`CTRL_LookAt` / runtime `ApplyLookAtAndGroundIKAndSprings`).
  - Upper-body layered combat (`ranged_fire`, `ranged_burst`, `reload`, `cast_directional`, `cast_ground`, `cast_self`), full-body 3-hit melee combo (`melee_1..3`), root-motion 4-way dashes (`dash_f/b/l/r`, `200 cm` travel), marker-driven `blink_out` → `teleport_event` → `blink_in`, and beacon `deploy`.
  - Pose-snapshot crossfade on arbitrary interruptions (`channel_loop` → `channel_interrupt`, `charge_hold` → `charge_cancel`, `uplink_loop` → `uplink_cancel`, hard disables, and terminal `death_front`/`death_back` → `respawn`) eliminating frame-0 snaps, plus bitmask-deduplicated animation event markers.
  - Analytical two-bone leg Ground IK + pelvis height adaptation tested on `18.5°` slopes (`<= 20°`) and `10 / 15 / 20 cm` steps, plus critically-damped secondary angular springs on `cable_01..03` and `strap_01..03`.

---

## 3. Interactive Showcase Controls (`build/Linux/MorphRig.sh`)

| Input | Action |
| :--- | :--- |
| `W` / `A` / `S` / `D` | Continuous 8-direction locomotion relative to character facing |
| `Left Ctrl` / Default / `Left Shift` | Speed tier override: Walk (`150 cm/s`) / Run (`400 cm/s`) / Sprint (`650 cm/s`) |
| `Q` / `E` | Rotate character facing yaw independently (`-110°/s` / `+110°/s`) to inspect strafing & turn-in-place |
| `I` / `K`, `J` / `L`, `U` / `O` | Move the 3D glowing Aim/Look-At Target Orb (`±Z`, `±Y`, `±X`) |
| `Right Mouse Drag` | Free camera orbit around the Operative (`Yaw` & `Pitch`) |
| `Mouse Wheel` | Camera zoom (`58–1600 cm`), or scroll list when the `96 Clips` browser tab is open |
| `1` – `8` | Camera presets: `1` Orbit Close, `2` Full-Body Front, `3` Side, `4` Top-Down `52°` MOBA, `5` `~120 px` Readability, `6` Facial Close-Up, `7` `18.5°` Ramp & `10–20 cm` Steps IK, `8` Wide Studio / Prop Station |
| `SpaceBar` | Jump (`jump_start` → `jump_air` / `fall` → `jump_land` / `land_heavy`) |
| `F` | Advance 3-hit retractable forearm-blade combo (`melee_1` → `melee_2` → `melee_3`) |
| `G` | Trigger layered upper-body `ranged_burst` (`muzzle_fire_1..3` while moving or aiming) |
| `R` | Trigger two-handed power-cell `reload` (`cell_detach` → `cell_swap` → `cell_insert`) |
| `C` | Start sustained `channel_start` → `channel_loop`, or trigger immediate `channel_interrupt` interruption |
| `V` | Play synchronized 16.48s close-up `dialogue` performance (`SW_Dialogue` + 45 facial morph curves) |
| `B` | Trigger `blink_out` (`teleport_event` +260 cm) → `blink_in` |
| `Z` | Trigger root-motion forward dash (`dash_f`, nominal `200 cm`) |
| `X` | Trigger terminal `death_front` (holds final pose indefinitely), or `respawn` when dead |
| `T` | Toggle Team A (Vanguard Cyan) ↔ Team B (Helix Crimson-Amber) |
| `H` | Show / hide interactive left HUD control drawer |
| `BackSpace` | Full character, prop, audio, and position reset to `(0, 0, 90 cm)` |
| **Left HUD Drawer (`4 Tabs`)** | **Tab 1 (`States & IK`)**: clickable triggers for all combat/sustained/CC/disable states, `LOD Auto/0/1/2`, Skeleton Overlay, Ground IK toggle, `1` vs `10` Operatives, and Play Rate (`0.5x / 1.0x / 1.5x`). **Tab 2 (`96 Clips`)**: live keyboard-searchable browser for all 96 clips & poses. **Tab 3 (`Face & Lip`)**: interactive manual sliders/buttons for asymmetric facial controls, 13 visemes, and 6 expression presets. **Tab 4 (`Help [H]`)**: on-screen control reference. |

---

## 4. Reproducible Build, Import & Execution Commands

All build, export, import, packaging, trace, and benchmark workflows run **100% headlessly** without opening desktop windows:

```bash
mkdir -p "$PWD/.tmp_work"
export TMPDIR="$PWD/.tmp_work"
UE_EXEC="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"

# 1. Optional: Rebuild Blender master file + bake & export all FBXs + JSON manifests from scratch
blender -b --factory-startup -P tools/export_and_bake.py -- --rebuild-all

# 2. Build Unreal C++ modules, run headless Python asset import (if needed) & package Linux client
./tools/build_linux.sh              # pass --reimport to force fresh FBX/texture/audio import

# 3. Launch packaged Linux showcase interactively (1920x1080)
"$UE_EXEC" "$PWD/build/Linux/MorphRig.sh" -ResX=1920 -ResY=1080

# 4. Run headless deterministic 18-step combined state showcase & emit trace log
"$UE_EXEC" "$PWD/build/Linux/MorphRig.sh" \
  -RenderOffScreen -AudioMixer -NoVSync -ResX=1920 -ResY=1080 -AutoShowcase

# 5. Run headless warmed-up 1920x1080 performance benchmark (1 vs 10 simultaneous Operatives)
"$UE_EXEC" "$PWD/build/Linux/MorphRig.sh" \
  -RenderOffScreen -AudioMixer -NoVSync -ResX=1920 -ResY=1080 -BenchmarkPerf
```

See [`docs/build_and_import_instructions.md`](docs/build_and_import_instructions.md) for individual stage commands and video capture flags.

---

## 5. Measured Real-Time Performance (`1920x1080`, No Frame Generation)

Measured directly from the packaged Linux Development client (`build/Linux/MorphRig.sh`) via `-BenchmarkPerf` after shader/pipeline warmup (`360` initial warmup frames + `150` crowd warmup frames; full details in [`docs/performance_report.json`](docs/performance_report.json)):

- **Hardware**: AMD Ryzen 9 9950X (16-Core / 32-Thread), 91.9 GiB RAM, NVIDIA GeForce RTX 5090 (32 GiB)
- **Resolution & Upscaling**: `1920x1080` native (`100%` screen percentage, **no upscaling**, **frame generation disabled**)
- **RHI & Render Settings**: Vulkan SM6 (`SF_VULKAN_SM6`), Cascaded Shadow Maps, Screen-Space Reflections, Temporal Anti-Aliasing, Bloom, Dynamic GI Off
- **Active Character Features**: 92-bone `DEF` skeleton, 45 active GPU morph targets (`LOD0`), phase-synced 8-direction locomotion, cached 9-sample Aim Grid, upper-body layered actions, local-space additive hit reactions, analytical two-bone Ground IK + pelvis adaptation, damped secondary springs, automatic `LOD0/LOD1/LOD2`

| Scenario (`240` Sampled Frames Each) | Avg Frame Time | Avg FPS | `p50` Frame Time | `p95` Frame Time | `p99` Frame Time | Target (`SPEC.md` §10) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1 Moving Operative (`one_operative`)** | **`10.231 ms`** | **`97.74 FPS`** | `9.098 ms` | `19.089 ms` | `21.991 ms` | `>= 60.0 FPS` (**Pass**) |
| **10 Simultaneous Operatives (`ten_simultaneous_operatives`)** | **`14.086 ms`** | **`70.99 FPS`** | `13.857 ms` | `21.811 ms` | `29.701 ms` | Documented (`> 60 FPS` achieved) |
