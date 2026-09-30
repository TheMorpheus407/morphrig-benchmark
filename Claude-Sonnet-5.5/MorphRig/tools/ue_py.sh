#!/usr/bin/env bash
# Run a Python script inside the headless Unreal editor of the MorphRig project.
# usage: tools/ue_py.sh <script.py> <logfile> [extra editor args...]
# The script path must live under $HOME (the FHS sandbox cannot enter /tmp).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
SCRIPT="$(readlink -f "$1")"; LOG="$(readlink -f -m "$2")"; shift 2
mkdir -p "$(dirname "$LOG")"
"$UE_EXEC" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$MORPHRIG_UPROJECT" \
  -run=pythonscript -script="$SCRIPT" -nullrhi -unattended -nosplash -stdout -FullStdOutLogOutput "$@" > "$LOG" 2>&1
