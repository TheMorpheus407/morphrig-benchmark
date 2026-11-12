# MORPHRIG — Build & Import Instructions

## 1. Rebuild the Blender source (authoritative asset)
Requires Blender 5.1.1 (see `environment.json`). Run, in order, from the `MorphRig/` folder:

```
/run/current-system/sw/bin/blender -b --factory-startup -P source/generators/build_character.py
/run/current-system/sw/bin/blender -b --factory-startup -P source/generators/build_rig.py
/run/current-system/sw/bin/blender -b --factory-startup -P source/generators/build_face_lods.py
/run/current-system/sw/bin/blender -b --factory-startup -P source/generators/animate.py
```

This produces `source/Operative.blend` containing the modelled, textured, rigged, skinned character, facial shape keys, LODs, and all 96 named actions.

## 2. Export FBX + baked animations
```
/run/current-system/sw/bin/blender -b --factory-startup -P source/generators/export_and_bake.py
```
Produces:
- `export/Operative.fbx` — bind-pose skinned mesh + skeleton (no animation).
- `export/animations/Operative_AllAnims.fbx` — all 96 actions as takes.

The export uses a constraint-free copy of the deformation skeleton so the baked actions drive the bones directly. Original editable controls remain in the `.blend`.

## 3. Unreal Engine import
Requires UE 5.8.3 via the `ue-exec` wrapper (see `environment.json`).

Open the project:
```
ue-exec '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor' /abs/MorphRig/unreal/MorphRig.uproject
```

Import (headless Python commandlet):
```
ue-exec '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' /abs/MorphRig/unreal/MorphRig.uproject -run=pythonscript -script=/abs/import_script.py -log
```
Where `import_script.py` imports `export/Operative.fbx` as a SkeletalMesh (content `/Game/Characters/Operative`) and `export/animations/Operative_AllAnims.fbx` as AnimSequences bound to that skeleton (content `/Game/Characters/Operative/Animations`). Map each manifest ID to its take one-to-one.

Then create the Animation Blueprint covering the full inventory (locomotion blendspace, transitions, combat, abilities, reactions, terminal states) and the showcase level (neutral room, ramp, steps, movable aim targets, prop-contact station, motion viewer, facial close-up, team-accent switch, LOD switch, aim/locomotion/jump/dash/blink/attack/cast/channel/charge/hits/death/respawn controls, animation browser, instance-count toggle 1 vs 10).

## 4. Package the Linux x86-64 showcase client
```
ue-exec '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' BuildCookRun \
  -project=/abs/MorphRig/unreal/MorphRig.uproject \
  -platform=Linux -clientconfig=Development -build -cook -stage -pak -archive \
  -archivedirectory=/abs/MorphRig/build/Linux
```
The packaged client runs outside the Unreal Editor. Windows packaging is not required. The asset/project must not depend on Linux-only runtime behavior.

## Notes
- Use the installed Blender 5.1.1 and UE 5.8.3 stated in `environment.json`; do not switch versions.
- No paid runtime plugin, no missing linked content, no absolute private-machine paths.
- All generators and reproducible commands are in `source/generators/` and `tools/`.