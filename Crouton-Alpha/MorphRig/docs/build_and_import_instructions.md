# Build & Import Instructions

Environment: Blender 5.1.1, UE 5.8.3 (see `environment.json`), NixOS x86_64 RTX 5090.

## 1. Regenerate character (once, from pristine primitives)
`blender -b --factory-startup -P MorphRig/source/generators/build_character.py`
`blender -b --factory-startup -P /tmp/lods_redo.py` equivalents (LOD1/LOD2 decimation of Operative_Body; see generator).

## 2. Author animations (Blender)
`blender -b --factory-startup -P MorphRig/source/generators/build_animations.py`

## 3. Export (Blender)
`blender -b --factory-startup -P MorphRig/tools/export_and_bake.py -- /abs/Operative.blend /abs/export`
Writes `export/Operative.fbx` + `export/animations/*.fbx` (96, armature+mesh single-strip baked).

## 4. Import (Unreal, headless)
Build game module: `ue-exec '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' MorphRigEditor Linux Development -Project=/abs/MorphRig.uproject -WaitMutex`
`ue-exec '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' /abs/MorphRig.uproject -run=pythonscript -script=/abs/unreal/import_morphrig.py -unattended`
AnimBP: `unreal/make_anim5.py`, Character BP: `unreal/make_showcase2.py`, level: `unreal/make_level4.py` + `make_level5.py`, GameMode: `unreal/make_gm.py`.

## 5. Package Linux (RunUAT blocked by RO engine Saved dir)
Workaround used: writable engine copy + `RunUAT.sh BuildCookRun ... -archivedirectory=/abs/build/Linux`.
Scripted equivalent Cook: `UnrealEditor-Cmd ... -run=Cook -TargetPlatform=Linux ...`
Manual stage/pak: see `tools/build_linux.sh` (build → cook → stage/pak via UnrealPak).

## 6. Run packaged client
`ue-exec /abs/build/Linux/MorphRig/Binaries/Linux/MorphRig`

## Dialogue audio
`espeak-ng -v en+fl3 -s 125` per sentence + 1.2 s silences → `source/audio/dialogue.wav` (15.35 s), `dialogue.txt`, `dialogue_alignment.json`.
