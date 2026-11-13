#!/usr/bin/env bash
# MORPHRIG: build the editor module, import the exported assets and package the Linux x86-64 showcase client.
#
#   tools/build_linux.sh                 full run: editor build -> import -> cook/stage/pak -> MorphRig/build/Linux
#   tools/build_linux.sh --skip-import   keep the current Content/ (no re-import)
#   tools/build_linux.sh --import-only   editor build + import, no packaging
#
# Environment: UE_EXEC (runtime wrapper, e.g. the ue-exec of environment.json) or UE_ROOT (native engine install).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
ue_lock
SKIP_IMPORT=0
IMPORT_ONLY=0
for a in "$@"; do
  case "$a" in
    --skip-import) SKIP_IMPORT=1 ;;
    --import-only) IMPORT_ONLY=1 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done
LOGDIR="$MORPHRIG_ROOT/unreal/Saved/Logs"
mkdir -p "$LOGDIR"

echo "[1/3] editor module build"
ue_run Engine/Build/BatchFiles/Linux/Build.sh MorphRigEditor Linux Development -project="$UPROJECT" -waitmutex > "$LOGDIR/morphrig_build_editor.log" 2>&1 \
  || { grep -E "error" "$LOGDIR/morphrig_build_editor.log" | head -30; echo "editor build failed: $LOGDIR/morphrig_build_editor.log"; exit 1; }

if [ $SKIP_IMPORT -eq 0 ]; then
  echo "[2/3] asset import + verification"
  MORPHRIG_SKIP_EDITOR_BUILD=1 "$TOOLS_DIR/ue_import.sh"
else
  echo "[2/3] import skipped"
fi
[ $IMPORT_ONLY -eq 1 ] && exit 0

echo "[3/3] cook + package (Linux, Development client)"
rm -rf "$MORPHRIG_ROOT/build/Linux"
set +e
ue_run Engine/Build/BatchFiles/RunUAT.sh BuildCookRun -project="$UPROJECT" -platform=Linux -clientconfig=Development \
  -build -cook -stage -pak -archive -archivedirectory="$MORPHRIG_ROOT/build" -nop4 -utf8output -unattended -noxge -nodebuginfo \
  > "$LOGDIR/morphrig_package.log" 2>&1
CODE=$?
set -e
ue_clean_config
if grep -q "LogPakFile: Warning: Missing file" "$LOGDIR/morphrig_package.log"; then
  grep "LogPakFile: Warning: Missing file" "$LOGDIR/morphrig_package.log" | sed -E 's/^.*(LogPakFile)/\1/' | head -8
  echo "PACKAGING FAILED: staged files disappeared while packaging (was unreal/Content modified concurrently?)"
  exit 1
fi
if [ $CODE -ne 0 ] || ! grep -q "BUILD SUCCESSFUL" "$LOGDIR/morphrig_package.log"; then
  grep -E "Error|error:" "$LOGDIR/morphrig_package.log" | grep -v "0 error" | head -40
  echo "PACKAGING FAILED (exit $CODE) - log: $LOGDIR/morphrig_package.log"
  exit 1
fi
grep -E "Warning: |warning: " "$LOGDIR/morphrig_package.log" | grep -v "LogInit: Display" | sed -E 's/^.*(Log[A-Za-z]+: Warning)/\1/' | sort | uniq -c | sort -rn | head -12 || true
du -sh "$MORPHRIG_ROOT/build/Linux" | sed 's/^/packaged size: /'
echo "PACKAGE OK -> $MORPHRIG_ROOT/build/Linux/MorphRig.sh   (start it with tools/run_showcase.sh)"
