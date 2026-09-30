#!/usr/bin/env bash
# Build the MorphRig Unreal showcase for Linux x86-64.
#   1. compile the C++ editor module (the import script needs UMorphEventNotify)
#   2. import / refresh the exported Operative assets (skip with SKIP_IMPORT=1)
#   3. BuildCookRun: build, cook, stage, pak and archive the client into MorphRig/build/Linux
# Requires the exported asset (python3 MorphRig/tools/export_and_bake.py) and the NixOS FHS wrapper
# ue-exec (override with UE_EXEC=...).  Run from anywhere:  bash MorphRig/tools/build_linux.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
UEX="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"
PROJ="$ROOT/unreal/MorphRig.uproject"
OUT="$ROOT/build/Linux"
LOGS="$ROOT/build/logs"
mkdir -p "$LOGS"

echo "== compile editor module"
"$UEX" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' MorphRigEditor Linux Development \
    -Project="$PROJ" -WaitMutex 2>&1 | tee "$LOGS/build_editor.log" | tail -3

if [ "${SKIP_IMPORT:-0}" != "1" ]; then
    echo "== import assets"
    MR_ROOT="$ROOT" "$UEX" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$PROJ" \
        -run=pythonscript -script="$ROOT/unreal/Scripts/import_operative.py" \
        -unattended -nosplash -nullrhi -NoSound -FullStdOutLogOutput 2>&1 | tee "$LOGS/import.log" | grep "MR_IMPORT" || true
    grep -q "MR_IMPORT DONE" "$LOGS/import.log" || { echo "import failed, see $LOGS/import.log"; exit 1; }
fi

echo "== BuildCookRun (Linux, Development)"
"$UEX" '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' BuildCookRun -project="$PROJ" -platform=Linux \
    -clientconfig=Development -build -cook -stage -pak -archive -archivedirectory="$OUT" \
    -noP4 -utf8output 2>&1 | tee "$LOGS/package.log" | tail -5
echo "packaged client: $OUT/MorphRig.sh"
