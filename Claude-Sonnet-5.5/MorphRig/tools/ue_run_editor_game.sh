#!/usr/bin/env bash
# Run the showcase map inside the editor binary in -game mode (uncooked content, no packaging needed). Used for fast iteration and
# headless logic tests (-nullrhi). usage: tools/ue_run_editor_game.sh <logfile> [extra engine args...]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
LOG="$(readlink -f -m "$1")"; shift
mkdir -p "$(dirname "$LOG")"
"$UE_EXEC" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$MORPHRIG_UPROJECT" /Game/Showcase/L_Showcase -game \
  -unattended -nosplash -stdout -FullStdOutLogOutput -NoSound "$@" > "$LOG" 2>&1
