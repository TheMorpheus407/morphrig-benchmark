#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UNREAL_DIR="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["unreal_engine"]["root"])' "$TASK_DIR/../environment.json")"
UNREAL_WRAPPER="$(dirname "$UNREAL_DIR")/bin/ue-exec"
IMPORT_SCRIPT="$TASK_DIR/tools/import_unreal.py"
if [[ -n "${MORPH_IMPORT_IDS:-}" ]]; then IMPORT_SCRIPT="$TASK_DIR/tools/import_clip_updates.py"; fi
if [[ "${MORPH_IMPORT_BEACON:-}" == 1 ]]; then IMPORT_SCRIPT="$TASK_DIR/tools/import_beacon.py"; fi
mkdir -p "$TASK_DIR/unreal/Saved/BuildLogs" "$TASK_DIR/unreal/Saved/ToolHome/config" "$TASK_DIR/unreal/Saved/ToolHome/cache" "$TASK_DIR/unreal/Saved/ToolHome/share"
export XDG_CONFIG_HOME="$TASK_DIR/unreal/Saved/ToolHome/config"
export XDG_CACHE_HOME="$TASK_DIR/unreal/Saved/ToolHome/cache"
export XDG_DATA_HOME="$TASK_DIR/unreal/Saved/ToolHome/share"
"$UNREAL_WRAPPER" "$UNREAL_DIR/Engine/Binaries/Linux/UnrealEditor-Cmd" "$TASK_DIR/unreal/MorphRig.uproject" -run=pythonscript "-script=$IMPORT_SCRIPT" -unattended -nosplash -nullrhi -NoSound -NoZenAutoLaunch -NoTraceServer -NoTrace "-abslog=$TASK_DIR/unreal/Saved/BuildLogs/import.log" > "$TASK_DIR/unreal/Saved/BuildLogs/import_stdout.log" 2>&1
