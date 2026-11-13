#!/usr/bin/env bash
# Shared environment for the MORPHRIG Unreal tool scripts (source this file).
#   UE_EXEC  wrapper that runs a command inside the Unreal runtime environment and sets UE_ROOT
#            (on the NixOS reference host: the `ue-exec` documented in environment.json).
#            Leave it empty on a host where the engine runs natively and set UE_ROOT instead.
TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MORPHRIG_ROOT="$(cd "$TOOLS_DIR/.." && pwd)"
UPROJECT="$MORPHRIG_ROOT/unreal/MorphRig.uproject"
ENV_JSON="$MORPHRIG_ROOT/../environment.json"

if [ -z "${UE_EXEC:-}" ] && [ -z "${UE_ROOT:-}" ] && [ -f "$ENV_JSON" ]; then
  UE_EXEC="$(python3 - "$ENV_JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
w = d.get('unreal_engine', {}).get('runtime_wrapper', '')
print(w.split(' ')[0] if w else '')
PY
)"
fi
if [ -n "${UE_EXEC:-}" ] && [ ! -x "$UE_EXEC" ]; then
  echo "UE_EXEC=$UE_EXEC is not executable" >&2
  exit 2
fi
# Scripts that only start the packaged client (MORPHRIG_CLIENT_ONLY=1) need neither the wrapper nor an engine.
if [ -z "${UE_EXEC:-}" ] && [ -z "${UE_ROOT:-}" ] && [ "${MORPHRIG_CLIENT_ONLY:-0}" != "1" ]; then
  echo "Set UE_EXEC (runtime wrapper) or UE_ROOT (engine root) first." >&2
  exit 2
fi

# ue_run <path below the engine root> [args...]
ue_run() {
  local rel="$1"; shift
  if [ -n "${UE_EXEC:-}" ]; then
    "$UE_EXEC" "\$UE_ROOT/$rel" "$@"
  else
    "$UE_ROOT/$rel" "$@"
  fi
}

# ue_run_abs <absolute executable/script> [args...]   (packaged client, etc.)
ue_run_abs() {
  if [ -n "${UE_EXEC:-}" ]; then
    "$UE_EXEC" "$@"
  else
    "$@"
  fi
}

# ue_clean_config: the editor adds a machine-specific section (random SecurityToken of the Android file server plugin)
# to DefaultEngine.ini whenever it runs; it is not part of the project, so it is removed again after editor runs.
ue_clean_config() {
  local ini="$MORPHRIG_ROOT/unreal/Config/DefaultEngine.ini"
  [ -f "$ini" ] || return 0
  python3 - "$ini" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
t = re.sub(r'\n*\[/Script/AndroidFileServerEditor\.AndroidFileServerRuntimeSettings\][^\[]*', '\n', s).rstrip('\n') + '\n'
if t != s:
    open(p, 'w', encoding='utf-8').write(t)
PY
}

# ue_lock: import and packaging both rewrite unreal/Content; two of them at the same time produce a broken package.
# A pid file (not flock: engine helper processes that outlive the script would inherit and keep a lock descriptor).
ue_lock() {
  [ "${MORPHRIG_LOCK_HELD:-0}" = "1" ] && return 0
  local lock="$MORPHRIG_ROOT/unreal/Saved/.morphrig_content.lock"
  mkdir -p "$(dirname "$lock")"
  if [ -f "$lock" ]; then
    local pid; pid=$(cat "$lock" 2>/dev/null || true)
    if [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null; then
      echo "another MORPHRIG import / build is running (pid $pid, $lock)"; exit 1
    fi
  fi
  echo $$ > "$lock"
  export MORPHRIG_LOCK_HELD=1
  MORPHRIG_LOCK_FILE="$lock"
  trap 'rm -f "$MORPHRIG_LOCK_FILE"' EXIT
}
