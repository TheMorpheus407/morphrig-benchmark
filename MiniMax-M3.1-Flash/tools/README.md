# MORPHRIG tools

Every helper that builds, checks or measures the delivery. They all run from
the repository root and they all write their output inside the repository.

## Build and import

| Tool | What it does |
|---|---|
| `build_linux.sh` | builds the game target, cooks the content, stages it and archives the Linux x86-64 client into `build/Linux/` |
| `ue_import.py` | imports the FBX files, the textures, the animations, the materials, the data table, the audio and the level into the Unreal project (`MORPHRIG_STAGES` selects a subset of the stages) |
| `ue_verify.py` | reads the imported project back and writes `build/ue_verify.json`: the clip list, the LODs, the material slots, the skeleton, the bounds and the root motion clips |
| `verify_delivery.py` | the delivery check, 27 checks over the layout, the clips, the budgets, the rig, the videos and the third party manifest |

## Capture and measurement

| Tool | What it does |
|---|---|
| `run_showcase.sh` | runs the packaged client with the deterministic showcase and copies the frame time log into `build/perf/` (`--instances`, `--seconds`, `--width`, `--height`, `--offscreen`) |
| `make_perf_report.py` | builds `docs/performance_report.md` from the captured runs |
| `capture_client_views.sh` | writes the five camera views of the packaged client into `docs/screenshots/` |
| `render_videos.sh` | renders the three presentation videos from `source/Operative.blend` with Cycles on the CPU |
| `make_dialogue.py` | renders the spoken line with Piper and writes the waveform, the transcript and the word alignment |

## Probes

These are the diagnostic scripts that were used to find and to prove the
defects listed in [`../docs/known_issues.md`](../docs/known_issues.md). They
are kept because every number in the documentation can be reproduced with them.

| Tool | What it proves |
|---|---|
| `probe_fbx_root.py` | the root bone translation inside an exported animation FBX, re-imported into Blender. It shows the 2 m of the dash clips in the file |
| `fbx_anim_hash.py` | a hash over every animated bone channel of an exported FBX. Two exports of the same clip have to produce the same hash, the FBX binary format itself cannot be compared byte by byte |
| `fbx_probe.py` | the unit scale factor and the mesh size of a binary FBX, without opening Unreal |
| `fbx_units.py` | the global settings and the local transforms of an FBX, read straight from the binary |
| `ue_dash_probe.py` | whether root motion is enabled on the imported dash clips and what the root track looks like |
| `ue_dash_probe2.py` | which animation helpers the commandlet exposes and what the imported sequences report |
| `ue_dash_probe3.py` | the root bone track of the imported dash clips, frame by frame |
| `ue_track_probe.py` | how Unreal stores the root bone animation inside the imported sequence |
| `ue_bone_pose.py` | the bone orientations of the imported skeleton, the evidence for the `operative_rig` bone above the root |

The Unreal probes run in the commandlet:

```bash
"$UE_EXEC" "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "$PWD/unreal/MorphRig.uproject" \
    -run=pythonscript -script="$PWD/tools/ue_bone_pose.py" \
    -unattended -nopause -nosplash -nullrhi -NoLogTimes
```

The Blender probes run in Blender:

```bash
blender -b --factory-startup -P tools/probe_fbx_root.py -- export/animations/dash_f.fbx
```
