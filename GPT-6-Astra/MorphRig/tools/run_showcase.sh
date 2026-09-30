#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT_DIR="${MORPH_CLIENT_DIR:-$TASK_DIR/build/Linux}"
CLIENT_SCRIPT="$CLIENT_DIR/MorphRig.sh"
if [[ ! -f "$CLIENT_SCRIPT" ]]; then CLIENT_SCRIPT="$CLIENT_DIR/Linux/MorphRig.sh"; fi
if [[ ! -f "$CLIENT_SCRIPT" ]]; then
  echo 'Packaged client missing. Run tools/build_linux.sh first.' >&2
  exit 1
fi
UNREAL_WRAPPER="$(python3 -c 'import json,pathlib,sys;print(pathlib.Path(json.load(open(sys.argv[1]))["unreal_engine"]["root"]).parent/"bin/ue-exec")' "$TASK_DIR/../environment.json")"
export XDG_CONFIG_HOME="$TASK_DIR/unreal/Saved/ToolHome/config"
export XDG_CACHE_HOME="$TASK_DIR/unreal/Saved/ToolHome/cache"
export XDG_DATA_HOME="$TASK_DIR/unreal/Saved/ToolHome/share"
mkdir -p "$TASK_DIR/unreal/Saved/RunLogs" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
RUN_LOG="$TASK_DIR/unreal/Saved/RunLogs/client_$(date +%Y%m%d_%H%M%S).log"
if [[ -x "$UNREAL_WRAPPER" ]]; then
  exec "$UNREAL_WRAPPER" "$CLIENT_SCRIPT" -windowed -ResX=1920 -ResY=1080 -NoTraceServer -NoTrace -NoZenAutoLaunch "-abslog=$RUN_LOG" "$@"
fi
exec "$CLIENT_SCRIPT" -windowed -ResX=1920 -ResY=1080 -NoTraceServer -NoTrace "-abslog=$RUN_LOG" "$@"
