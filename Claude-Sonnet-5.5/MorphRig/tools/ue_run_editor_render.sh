#!/usr/bin/env bash
# Like ue_run_editor_game.sh but with the full editor binary and rendering (use -RenderOffScreen for no window). Slow at first start
# because shaders of the uncooked content are compiled. usage: tools/ue_run_editor_render.sh <logfile> [engine args...]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
LOG="$(readlink -f -m "$1")"; shift
mkdir -p "$(dirname "$LOG")"
"$UE_EXEC" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor' "$MORPHRIG_UPROJECT" /Game/Showcase/L_Showcase -game \
  -unattended -nosplash -stdout -FullStdOutLogOutput -NoSound "$@" > "$LOG" 2>&1
