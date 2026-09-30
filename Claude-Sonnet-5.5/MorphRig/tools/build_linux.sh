#!/usr/bin/env bash
# Full BuildCookRun of the MorphRig showcase for Linux (Development client, pak, without debug symbol files, archived into build/Linux).
# usage: tools/build_linux.sh          (log: unreal/Saved/Logs/build_linux.log)
# UAT appends the platform folder to the archive directory, so the packaged client ends up in build/Linux/MorphRig.sh.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
LOG="$MORPHRIG_ROOT/unreal/Saved/Logs/build_linux.log"
mkdir -p "$(dirname "$LOG")" "$MORPHRIG_ROOT/build"
"$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' BuildCookRun \
  -project="$MORPHRIG_UPROJECT" -platform=Linux -clientconfig=Development \
  -build -cook -stage -pak -nodebuginfo -archive -archivedirectory="$MORPHRIG_ROOT/build" \
  -unattended -utf8output -nop4 -map=/Game/Showcase/L_Showcase 2>&1 | tee "$LOG" | grep -a "BUILD SUCCESSFUL\|BUILD FAILED\|Error:\|error:\|ExitCode\|Cook.*complete\|Stage command\|Archive command" || true
if grep -aq "BUILD SUCCESSFUL" "$LOG"; then echo "PACKAGE OK: $MORPHRIG_ROOT/build/Linux"; else echo "PACKAGE FAILED, see $LOG"; exit 1; fi
