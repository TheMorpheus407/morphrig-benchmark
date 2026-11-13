#!/usr/bin/env bash
# Re-import everything under export/ into the Unreal project (headless). Safe to run after every re-export.
#   tools/ue_import.sh            wipe generated content, build editor module if needed, import, verify
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
ue_lock
LOG="$MORPHRIG_ROOT/unreal/Saved/Logs/morphrig_import.log"
mkdir -p "$(dirname "$LOG")"
# generated content is rebuilt from scratch: stale assets would otherwise be reused silently
rm -rf "$MORPHRIG_ROOT/unreal/Content/Operative" "$MORPHRIG_ROOT/unreal/Content/Showcase" "$MORPHRIG_ROOT/unreal/Content/MorphRigData"
if [ "${MORPHRIG_SKIP_EDITOR_BUILD:-0}" != "1" ]; then
  ue_run Engine/Build/BatchFiles/Linux/Build.sh MorphRigEditor Linux Development -project="$UPROJECT" -waitmutex > "$LOG.build" 2>&1 \
    || { tail -40 "$LOG.build"; echo "editor module build failed (see $LOG.build)"; exit 1; }
fi
set +e
ue_run Engine/Binaries/Linux/UnrealEditor-Cmd "$UPROJECT" -run=pythonscript -script="$TOOLS_DIR/unreal_import.py" \
  -unattended -nosplash -nullrhi -stdout -FullStdOutLogOutput > "$LOG" 2>&1
CODE=$?
set -e
ue_clean_config
grep -E "MORPHRIG_IMPORT" "$LOG" | grep -v "LogInit: Display" | sed -E 's/^\[[^]]*\]\[ *[0-9]+\]//' | tail -${MORPHRIG_IMPORT_TAIL:-45}
if [ $CODE -ne 0 ] || ! grep -q "MORPHRIG_IMPORT IMPORT OK" "$LOG"; then
  grep -E "Error" "$LOG" | grep -v "LogInit: Display" | head -30
  echo "IMPORT FAILED (exit $CODE) - full log: $LOG"
  exit 1
fi
echo "IMPORT OK - report: $MORPHRIG_ROOT/unreal/Saved/MorphRigImportReport.json"
