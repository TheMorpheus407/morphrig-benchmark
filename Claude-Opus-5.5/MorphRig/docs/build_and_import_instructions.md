# Build and import instructions

Reference host: NixOS x86-64, RTX 5090, Blender 5.1.1 (`blender` on PATH), Unreal Engine 5.8.3 prebuilt at
`~/UnrealEngine/5.8.3`, run through the FHS wrapper `~/UnrealEngine/bin/ue-exec`. All paths below are relative
to the delivery folder's parent (the folder that contains `MorphRig/`).

## 0. Nothing to rebuild to use the asset
* Blender: open `MorphRig/source/Operative.blend` (textures are referenced relatively from `source/textures`).
* Unreal: open `MorphRig/unreal/MorphRig.uproject` (the C++ module compiles on first open) or run the packaged
  client `MorphRig/build/Linux/MorphRig.sh` (through `ue-exec` on NixOS).

## 1. Blender source → exported asset
```
python3 MorphRig/tools/export_and_bake.py                  # full rebuild, ~1 h
python3 MorphRig/tools/export_and_bake.py --from anims     # re-author / bake clips only
python3 MorphRig/tools/export_and_bake.py --from export    # export only
python3 MorphRig/tools/make_docs.py                        # docs/*.json from the export
```
Stages: character (meshes, skeleton, weights, shape keys, costume, UVs) → textures (Cycles bakes of geometry
maps + procedural PBR maps, GPU/OptiX if present, CPU otherwise) → LODs → control rig → animation authoring
with floor / hand-body contact correction, hair-tail simulation, bake and motion QA (`docs/qa/motion_qa.json`)
→ `source/Operative.blend` → FBX export. Intermediates go to `MorphRig/build/intermediate/` (disposable).

Export conventions: FBX in centimetres (the exporter converts an in-memory copy: scene unit scale 0.01, bones,
meshes, shape keys and location keys ×100, `FBX_SCALE_NONE`), so every bone including `root` has scale 1 in
Unreal and extracted root motion is in true centimetres; forward
-Z / up Y in FBX terms (Blender -Y forward, +Z up), armature node `Armature` so Unreal adds no extra root,
`use_mesh_modifiers=False` (keeps shape keys → morph targets), one skeleton-only FBX per clip
(`export/animations/<clip>.fbx`, take `SK_<clip>`), `face_curves.json` (per-frame morph weights evaluated from
the rig drivers) and `clips_meta.json` (frames, loop, form, root policy, layer, markers, entry/exit).

The dialogue audio is regenerated (optional) with
`nix-shell -p piper-tts espeak-ng --run "python3 MorphRig/tools/make_dialogue.py --voice <dir with en_US-john-medium.onnx(.json)>"`;
the voice model is not part of the delivery (see THIRD_PARTY_ASSETS.csv for source and hashes).

## 2. Unreal import and Linux package
```
bash MorphRig/tools/build_linux.sh                 # compile + import + BuildCookRun
SKIP_IMPORT=1 bash MorphRig/tools/build_linux.sh   # package only (assets already imported)
```
1. Builds the `MorphRigEditor` target (C++ module `MorphRig`).
2. Runs `unreal/Scripts/import_operative.py` headless (`UnrealEditor-Cmd -run=pythonscript`, env `MR_ROOT`):
   textures (normal maps flipped to DirectX green), master material + 7 instances (team parameter), helper
   materials (floor grid, blocks, targets, FX, team icon, stencil outline post-process), `SK_Operative` via
   Interchange with morph targets, LOD1/LOD2 (`SkeletalMeshEditorSubsystem.ImportLOD`), sockets on the
   `sock_*` bones, morph-target curve metadata, every clip as `A_<clip>` with `UMorphEventNotify` notifies,
   face curves, additive settings (hits, `ctl_*`), root motion (dash), `SW_Dialogue`, `SM_Beacon`,
   `Content/MorphRig/Data/clips.json` and the map `/Game/MorphRig/Maps/Showcase`.
   Every run that imports the mesh deletes and recreates `SK_Operative`, its skeleton and all `A_*` animations
   (a merge into an existing skeleton would keep a stale reference pose, and a replacing animation import would
   duplicate notifies). Partial animation re-import against the existing skeleton:
   `MR_STAGE=anims MR_ONLY=walk_f,dialogue`.
3. `RunUAT BuildCookRun -platform=Linux -clientconfig=Development -build -cook -stage -pak -archive` into
   `MorphRig/build/Linux`. Logs: `MorphRig/build/logs/`.

The project has no Linux-only runtime dependencies (plain C++/Slate/Engine modules); a Windows build uses the
same project with `-platform=Win64`.

## 3. Command-line modes of the showcase client
| Option | Effect |
|---|---|
| `-MorphSequence [-MorphExit]` | run the deterministic sequence, write `Saved/Logs/MorphRig_Trace.txt` |
| `-MorphBench=30 -MorphBenchWarmup=5 -MorphInstances=10 [-MorphExit]` | performance capture → `Saved/Logs/MorphRig_Perf_*.json/.csv` |
| `-MorphInstances=10` | start with ten operatives |
| `-MorphCapture=turntable|showcase|face -MorphCaptureDir=<abs>` | fixed-step 30 fps frame capture for the presentation videos |
| `-MorphTeam=1`, `-MorphLOD=0..3` (0 auto, n = LOD n-1), `-MorphOutline` | start with team B / a forced LOD / the team outline |
| `-ResX=1920 -ResY=1080 -windowed` | resolution used for all measurements |

## 4. Presentation videos
`bash MorphRig/tools/make_videos.sh` runs the three capture modes of the packaged client and encodes
`presentation/turntable.mp4`, `motion_showcase.mp4`, `face_performance.mp4` (with `source/audio/dialogue.wav`
muxed at the capture's dialogue start) using ffmpeg.
