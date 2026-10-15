# MORPHRIG — Cyberpunk Operative ("Vex") Character Production & Unreal Engine 5.8.3 Showcase

An original, fully modeled, textured, rigged, skinned, and animated 1.80 m humanoid cyberpunk Operative (**"Vex"**) authored in **Blender 5.1.1** and integrated into a standalone real-time **Unreal Engine 5.8.3** Linux x86-64 showcase client.

---

## 1. Deliverable Layout & File Map

| Deliverable Path | Description |
| :--- | :--- |
| [`README.md`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/README.md) | Master documentation, controls reference, and deliverable map |
| [`source/Operative.blend`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/source/Operative.blend) | Authoritative Blender 5.1.1 file with `Operative_LOD0..2`, `Armature_Operative` (93 deform bones + `CTRL_*`/`MCH_*` control rig), 38 Shape Keys, and 96 actions + 7 stress-test poses |
| `source/textures/*.png` | 42 procedural `1024x1024` PBR texture maps (BaseColor, Metallic, Roughness, Normal, AO, Emissive, packed ORM) including `TeamA` and `TeamB` variants |
| [`source/audio/dialogue.wav`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/source/audio/dialogue.wav) | 14.50 s spoken tactical dialogue audio (`44.1 kHz`, 16-bit mono PCM) |
| [`source/audio/dialogue.txt`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/source/audio/dialogue.txt) | Verbatim transcript of the spoken dialogue line |
| [`source/audio/dialogue_alignment.json`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/source/audio/dialogue_alignment.json) | Word, phoneme, viseme, brow, and blink timing intervals |
| `source/generators/*.py` | First-party procedural generators (`build_operative_blend.py`, `generate_textures.py`, `generate_dialogue_audio.py`) |
| [`export/Operative.fbx`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/export/Operative.fbx) | Exported game-ready SkeletalMesh (`LOD0`, 93 deform bones, 38 Morph Targets, 6 materials) |
| [`export/Operative_LOD1.fbx`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/export/Operative_LOD1.fbx) | Exported `LOD1` SkeletalMesh (`16,334` triangles) |
| [`export/Operative_LOD2.fbx`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/export/Operative_LOD2.fbx) | Exported `LOD2` SkeletalMesh (`5,602` triangles) |
| `export/animations/*.fbx` | All 96 required baked skeletal animation clips (`30 FPS`, `only_deform_bones=True`) |
| `export/textures/*.png` | Exported PBR texture sets |
| [`unreal/MorphRig.uproject`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/unreal/MorphRig.uproject) | Unreal Engine 5.8.3 project (`MorphRig` C++ module + imported `/Game/MorphRig/...` content) |
| [`build/Linux/MorphRig.sh`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/build/Linux/MorphRig.sh) | Packaged standalone Linux x86-64 showcase client |
| [`docs/rig_usage.md`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/rig_usage.md) | Animator control rig, IK/FK switches, prop sockets, and facial rig documentation |
| [`docs/skeleton_and_sockets.json`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/skeleton_and_sockets.json) | Complete 93-bone hierarchy, rest transforms, axes, units, and 9 gameplay/VFX sockets |
| [`docs/animation_manifest.json`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/animation_manifest.json) | Manifest of all 96 required animations with frame ranges, layers, root-motion policy, event markers, and entry/exit states |
| [`docs/animation_state_contract.md`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/animation_state_contract.md) | 7-layer animation architecture, priority rules, arbitrary-midpoint interruption, and event deduplication contract |
| [`docs/material_and_lod_report.json`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/material_and_lod_report.json) | Triangle budgets, material slots, VRAM footprint, and 1920x1080 1-instance vs. 10-instance performance metrics |
| [`docs/THIRD_PARTY_ASSETS.csv`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/THIRD_PARTY_ASSETS.csv) | Asset provenance and authorship manifest |
| [`docs/build_and_import_instructions.md`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/build_and_import_instructions.md) | End-to-end reproducible build, export, import, and packaging instructions |
| [`docs/known_issues.md`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/docs/known_issues.md) | Production notes and NixOS FHS execution details |
| [`tools/export_and_bake.py`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/tools/export_and_bake.py) | Deterministic Blender -> FBX baker & exporter |
| [`tools/build_linux.sh`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/tools/build_linux.sh) | Reproducible UE 5.8.3 build, headless Python asset import, and Linux packaging script |
| [`presentation/turntable.mp4`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/presentation/turntable.mp4) | 1920x1080 30 FPS full-body + close-up + top-down + Team A/B + LOD0/1/2 turntable |
| [`presentation/motion_showcase.mp4`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/presentation/motion_showcase.mp4) | 1920x1080 30 FPS locomotion, dash, blink, melee combo, reload, deploy, stun, death/respawn, and stress-test showcase |
| [`presentation/face_performance.mp4`](file:///home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Gemini-4-Argon/presentation/face_performance.mp4) | 1920x1080 30 FPS close-up spoken dialogue performance with synchronized audio, visemes, emotions, gaze, and blinks |

---

## 2. Character, Geometry, Materials & Rig Summary

- **Standing Scale**: `1.80 m` (`180.0 cm` in Unreal Engine without import scale overrides), ground-origin at `[0, 0, 0]`, facing `-Y` in Blender / `+X` in Unreal (`Z-up`).
- **Triangle Counts & Budgets**:
  - `Operative_LOD0`: **`39,070` triangles** (limit `<= 80,000`)
  - `Operative_LOD1`: **`16,334` triangles** (`41.8%` of LOD0, limit `<= 40,000`)
  - `Operative_LOD2`: **`5,602` triangles** (`14.3%` of LOD0, limit `<= 20,000`)
- **Materials & Team Variants**:
  - **6 Material Slots** (`<= 8` limit): `M_Operative_Skin`, `M_Operative_Eyes`, `M_Operative_Suit`, `M_Operative_Armor`, `M_Operative_CyberArm`, `M_Operative_Props_Accent`.
  - **Team A (`0`)**: Electric Cyan (`#00F0FF`) emissive + **Hex-Chevron** chest/dorsal/beacon insignia + cyan silhouette rim.
  - **Team B (`1`)**: Solar Amber (`#FF9900`) emissive + **Crossed-Diamond** chest/dorsal/beacon insignia + amber silhouette rim (distinguishable by geometry/pattern independently of color).
- **Deformation Skeleton & Control Rig**:
  - **93 Deformation Bones** under a single `root` bone (`<= 4` bone weights per vertex, normalized to `1.0`), including twist bones on upper/lower limbs, 30 finger phalanges (5 articulated fingers per hand), integrated right-forearm emitter (`emitter_mount_r`, `emitter_muzzle_r`, `cell_socket_r`, `prop_cell`) and retractable melee blade (`blade_mount_r`, `blade_extend_r`), deployable `prop_beacon`, secondary-motion chains (`neural_tether_01..03`, `belt_strap_01..02`), and facial bones (`jaw`, `tongue_01..02`, `eye_l/r`, `eyelid_*`, `brow_*`, `lip_*`).
  - **38 Shape Keys / Morph Targets** on `Operative_LOD0`: 6 core expressions (`emotion_neutral`, `emotion_angry`, `emotion_determined`, `emotion_pain`, `emotion_surprised`, `emotion_sad`), 14 speech visemes (`viseme_sil`, `viseme_AA`, `viseme_E`, `viseme_I`, `viseme_O`, `viseme_U`, `viseme_M_B_P`, `viseme_F_V`, `viseme_L`, `viseme_S_Z`, `viseme_SH_CH`, `viseme_TH`, `viseme_K_G`, `viseme_R`), 12 independent L/R blink, eye-wide, brow, cheek, nose-sneer, and jaw-clench shapes, and 6 joint-angle corrective shapes (`corr_shoulder_up_l/r`, `corr_elbow_bend_l/r`, `corr_knee_bend_l/r`).

---

## 3. Running the Packaged Linux Showcase Client & Interactive Controls

### Launch Interactive Showcase (1920x1080 Windowed)
```bash
/home/morpheus/UnrealEngine/bin/ue-exec ./build/Linux/MorphRig.sh /Game/Maps/ShowcaseArena -ResX=1920 -ResY=1080 -Windowed
```

### Launch Deterministic Automated Showcase Sequence
```bash
/home/morpheus/UnrealEngine/bin/ue-exec ./build/Linux/MorphRig.sh /Game/Maps/ShowcaseArena -ResX=1920 -ResY=1080 -Windowed -ShowcaseSequence -AutoQuit
```

### Interactive Keyboard & Mouse Controls

| Input | Action |
| :--- | :--- |
| **`W` / `A` / `S` / `D`** | 8-Way Strafe / Omnidirectional Locomotion (`walk_*`, `run_*`, start/stop/turn transitions) |
| **`Mouse X / Y`** | Orbit Camera around Operative |
| **`I` / `J` / `K` / `L`** | Move 3D Aim Target Sphere (`Up` / `Left` / `Down` / `Right`) to drive 9-point Aim Offset (`±90°` yaw, `±60°` pitch) |
| **`Spacebar`** | Jump (`jump_start` -> `jump_Apex` -> `fall_loop` -> `land_light` / `land_roll`) |
| **`Q`** | Directional Root-Motion Dash (`dash_f/b/l/r`, `2.0 m` travel) |
| **`E`** | Event-Driven Blink Teleport (`blink_out` -> `4.0 m` instant displacement -> `blink_in`) |
| **`F`** | 3-Hit Melee Blade Combo (`melee_1` -> `melee_2` -> `melee_3` with combo window chaining) |
| **`Left Mouse Button`** | Ranged Wrist-Emitter Single Shot (`ranged_single`, usable while moving) |
| **`Right Mouse Button`** | Ranged Wrist-Emitter 3-Round Burst (`ranged_burst`, usable while moving) |
| **`R`** | Physical Prop-Contact Reload (`reload`: `prop_cell` transfers to `weapon_l` and inserts back into `cell_socket_r`) |
| **`C`** | Channel Ability (`channel_start` -> `channel_loop` -> `channel_release`) |
| **`V`** | Charge Ability (`charge_start` -> `charge_hold` -> `charge_release`) |
| **`G`** | Deploy Beacon Prop (`deploy`: left hand detaches `prop_beacon` from belt and places on floor) |
| **`B`** | Toggle Interact / Neural Uplink (`interact_uplink`) |
| **`X`** | **Arbitrary-Midpoint Interrupt** (cleanly crossfades from current live pose into `channel_interrupt` / `idle_combat` without frame-0 snapping) |
| **`1`** | Additive Hit Reaction (`hit_front` / `hit_back` / `hit_left` / `hit_right`) |
| **`2`** | Crowd-Control Stun (`stun_loop`, blocks combat/movement until expired or interrupted) |
| **`3`** | Crowd-Control Knockdown (`knockdown_start` -> `knockdown_loop` -> `knockdown_getup`) |
| **`4`** | Crowd-Control Sleep (`sleep_loop`) |
| **`5`** | Terminal Death (`death_front` -> `dead_front`, blocks all lower-priority actions) |
| **`6`** | Respawn (`respawn` -> `idle_combat`, resets character to arena center) |
| **`7` / `8` / `9`** | Teleport to **20° Slope** (`7`), **20 cm Stepped Platform** (`8`), or **Flat Floor** (`9`) to inspect Foot/Pelvis Ground IK |
| **`T`** | Trigger 14.50 s **Spoken Dialogue Performance** (`dialogue` + `face_dialogue_line_01` + `dialogue.wav` audio) |
| **`Y`** | Cycle Manual Facial Expression (`Neutral`, `Angry`, `Determined`, `Pain`, `Surprised`, `Sad`) |
| **`U`** | Trigger Manual Eyelid Blink (`face_blink_both`) |
| **`M`** | Toggle **Team A** (Cyan / Hex-Chevron) vs. **Team B** (Amber / Crossed-Diamond) Material & Insignia Variant |
| **`N`** | Cycle Forced LOD (`Auto` -> `LOD0` -> `LOD1` -> `LOD2`) |
| **`P`** | Toggle **1 vs. 10 Simultaneous Animated Operatives** (1920x1080 real-time performance benchmark) |
| **`Tab`** | Cycle Camera Preset (`Third-Person`, `Full-Body Front/Side`, `Top-Down 52.5° Gameplay @ ~120px`, `Facial Close-Up`, `Foot IK Close-Up`) |
| **`[` / `]` / `Enter`** | Searchable Animation Browser: Previous (`[`), Next (`]`), Play Selected Clip (`Enter`) across all 96 required IDs |
| **`-` / `=`** | Adjust Animation Playback Rate (`0.5x` to `1.5x` in `0.1x` increments) |
| **`0`** | Run Deterministic Automated Showcase Sequence |

---

## 4. Reproducible Build & Export Commands

```bash
# 1. Regenerate dialogue audio & phoneme/viseme alignment
python3 source/generators/generate_dialogue_audio.py

# 2. Regenerate 1024x1024 PBR texture sets (Team A & Team B)
python3 source/generators/generate_textures.py

# 3. Rebuild source/Operative.blend (meshes, LODs, rig, 38 shape keys, 96 actions)
blender -b -P source/generators/build_operative_blend.py

# 4. Bake & export Operative.fbx, LOD1/2, and all 96 animation FBXs + JSON manifests
blender -b source/Operative.blend -P tools/export_and_bake.py

# 5. Render the three 1080p presentation MP4 videos
blender -b source/Operative.blend -P tools/render_presentation_videos.py

# 6. Compile UE 5.8.3 C++ module, import all assets headlessly, and package Linux client
./tools/build_linux.sh
```
