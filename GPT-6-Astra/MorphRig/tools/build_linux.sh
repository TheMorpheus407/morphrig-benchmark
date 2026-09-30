#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENT_FILE="${TASK_DIR}/../environment.json"
ARCHIVE_DIR="${MORPH_ARCHIVE_DIR:-$TASK_DIR/build/Linux}"
UNREAL_DIR="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["unreal_engine"]["root"])' "$ENVIRONMENT_FILE")"
UNREAL_WRAPPER="$(dirname "$UNREAL_DIR")/bin/ue-exec"
mkdir -p "$TASK_DIR/unreal/Saved/BuildLogs" "$TASK_DIR/unreal/Saved/ToolHome" "$TASK_DIR/unreal/Saved/ToolHome/config" "$TASK_DIR/unreal/Saved/ToolHome/cache" "$TASK_DIR/unreal/Saved/ToolHome/share"
export DOTNET_CLI_HOME="$TASK_DIR/unreal/Saved/ToolHome"
export XDG_CACHE_HOME="$TASK_DIR/unreal/Saved/ToolHome/cache"
export XDG_CONFIG_HOME="$TASK_DIR/unreal/Saved/ToolHome/config"
export XDG_DATA_HOME="$TASK_DIR/unreal/Saved/ToolHome/share"
export uebp_EngineSavedFolder="$TASK_DIR/unreal/Saved/BuildLogs/Automation"
export uebp_LogFolder="$TASK_DIR/unreal/Saved/BuildLogs/Automation"
export uebp_FinalLogFolder="$TASK_DIR/unreal/Saved/BuildLogs/Automation"
if [[ "${1:-package}" == editor || "${1:-package}" == game ]]; then
  BUILD_TARGET=MorphRig
  if [[ "$1" == editor ]]; then BUILD_TARGET=MorphRigEditor; fi
  shift
  "$UNREAL_WRAPPER" "$UNREAL_DIR/Engine/Build/BatchFiles/Linux/Build.sh" "$BUILD_TARGET" Linux Development "-Project=$TASK_DIR/unreal/MorphRig.uproject" -MaxParallelActions=8 -NoUBA -NoHotReloadFromIDE "-Log=$TASK_DIR/unreal/Saved/BuildLogs/ubt.log" "$@" 2>&1 | tee "$TASK_DIR/unreal/Saved/BuildLogs/${BUILD_TARGET}.log"
else
  unset UBT_EXTRA_ARGS || true
  "$UNREAL_WRAPPER" "$UNREAL_DIR/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun "-project=$TASK_DIR/unreal/MorphRig.uproject" -noP4 -platform=Linux -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$ARCHIVE_DIR" -utf8output -UbtArgs="-MaxParallelActions=8 -NoUBA" -AdditionalCookerOptions="-NoTraceServer -NoTrace -NoZenAutoLaunch -SkipZenStore" 2>&1 | tee "$TASK_DIR/unreal/Saved/BuildLogs/package.log"
fi
