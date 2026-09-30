#!/usr/bin/env bash
# Compile the MorphRig editor target (needed for headless import scripts).
# usage: tools/ue_build_editor.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
"$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' MorphRigEditor Linux Development \
  -Project="$MORPHRIG_UPROJECT" -WaitMutex
