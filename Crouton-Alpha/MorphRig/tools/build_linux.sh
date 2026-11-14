#!/usr/bin/env bash
# Linux package via writable engine copy (RunUAT needs writable engine Saved/).
# Steps: build (already), cook (editor commandlet), stage+pak (UnrealPak manual + engine copy for UAT logs).
set -euo pipefail
ROOT=/home/candidate/workspace/MorphRig
UE=/home/morpheus/UnrealEngine/5.8.3
DST=$ROOT/build/Linux
echo "Build game:"
/home/morpheus/UnrealEngine/bin/ue-exec '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' MorphRig Linux Development -Project=$ROOT/unreal/MorphRig.uproject -WaitMutex
echo "Cook:"
/home/morpheus/UnrealEngine/bin/ue-exec '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' $ROOT/unreal/MorphRig.uproject -run=Cook -TargetPlatform=Linux -stdout
echo "For full stage/pak with writable engine:"
echo "  cp -a $UE /tmp/UE_writable   # once"
echo "  /tmp/UE_writable/Engine/Build/BatchFiles/RunUAT.sh BuildCookRun -project=$ROOT/unreal/MorphRig.uproject -platform=Linux -clientconfig=Development -build -cook -stage -pak -archive -archivedirectory=$DST"
