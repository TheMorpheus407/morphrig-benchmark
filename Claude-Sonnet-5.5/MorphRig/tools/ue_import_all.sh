#!/usr/bin/env bash
# Idempotent full import of export/ and docs/ into the Unreal project.
# usage: tools/ue_import_all.sh [steps]      steps: comma list of mesh,clips,props,audio,materials,assets,level (default: all)
# Builds the editor module first (the data asset and the notify class are C++), then runs tools/ue_import_all.py in UnrealEditor-Cmd.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ue_env.sh"
STEPS="${1:-mesh,clips,props,audio,materials,assets,level}"
LOG="$MORPHRIG_ROOT/unreal/Saved/Logs/ue_import_all.log"
mkdir -p "$(dirname "$LOG")"
"$HERE/ue_build_editor.sh" > "$MORPHRIG_ROOT/unreal/Saved/Logs/ue_build_editor.log" 2>&1 || { tail -30 "$MORPHRIG_ROOT/unreal/Saved/Logs/ue_build_editor.log"; exit 1; }
"$HERE/ue_py.sh" "$HERE/ue_import_all.py" "$LOG" "-MRSteps=$STEPS" || true
grep -a "MRIMPORT" "$LOG" | sed 's/^\[[^]]*\]\[[^]]*\]LogPython: //' || true
if grep -aq "MRIMPORT SUMMARY failed=\[\]" "$LOG"; then echo "IMPORT OK"; else echo "IMPORT FAILED (see $LOG)"; exit 1; fi
