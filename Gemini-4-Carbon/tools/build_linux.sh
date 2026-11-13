#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# MORPHRIG — Reproducible Headless Unreal Engine 5.8.3 Linux Packaging Script
# ==============================================================================
# Produces standalone Linux x86-64 showcase client in:
#   ./build/Linux/MorphRig.sh
#
# Zero GUI windows are opened at any stage.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPROJECT="$ROOT_DIR/unreal/MorphRig.uproject"
ARCHIVE_ROOT="$ROOT_DIR/build"
UE_EXEC="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"

run_ue() {
  local script_rel="$1"
  shift
  if [[ -x "$UE_EXEC" ]]; then
    "$UE_EXEC" "\$UE_ROOT/$script_rel" "$@"
  elif [[ -n "${UE_ROOT:-}" && -x "$UE_ROOT/$script_rel" ]]; then
    "$UE_ROOT/$script_rel" "$@"
  else
    echo "[MorphRig] ERROR: Set UE_EXEC (NixOS wrapper) or UE_ROOT (Unreal Engine 5.8 root)." >&2
    exit 1
  fi
}

mkdir -p "$ROOT_DIR/.tmp_work"
export TMPDIR="$ROOT_DIR/.tmp_work"

echo "[MorphRig] 1/3 Building MorphRigEditor (Linux Development)..."
run_ue "Engine/Build/BatchFiles/Linux/Build.sh" \
  MorphRigEditor Linux Development \
  -Project="$UPROJECT" \
  -WaitMutex

if [[ ! -f "$ROOT_DIR/unreal/Content/MorphRig/Maps/ShowcaseMap.umap" ]]; then
  echo "[MorphRig] 2/3 Importing character, textures, materials, audio & 96 animations headlessly..."
  run_ue "Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "$UPROJECT" \
    -run=pythonscript \
    -script="$ROOT_DIR/unreal/Scripts/import_assets.py" \
    -nullrhi -unattended -nopause -nosplash
else
  echo "[MorphRig] 2/3 Unreal assets already imported at unreal/Content/MorphRig/ (pass --reimport to force)."
  if [[ "${1:-}" == "--reimport" ]]; then
    run_ue "Engine/Binaries/Linux/UnrealEditor-Cmd" \
      "$UPROJECT" \
      -run=pythonscript \
      -script="$ROOT_DIR/unreal/Scripts/import_assets.py" \
      -nullrhi -unattended -nopause -nosplash
  fi
fi

echo "[MorphRig] 3/3 Running BuildCookRun for standalone Linux Development client..."
rm -rf "$ARCHIVE_ROOT/Linux"
run_ue "Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun \
  -project="$UPROJECT" \
  -noP4 \
  -platform=Linux \
  -clientconfig=Development \
  -serverconfig=Development \
  -build \
  -cook \
  -allmaps \
  -stage \
  -pak \
  -iostore \
  -archive \
  -archivedirectory="$ARCHIVE_ROOT" \
  -utf8output \
  -unattended \
  -nullrhi

# Normalize UAT output folder name if UAT wrote LinuxNoEditor or LinuxClient
if [[ ! -d "$ARCHIVE_ROOT/Linux" ]]; then
  if [[ -d "$ARCHIVE_ROOT/LinuxNoEditor" ]]; then
    mv "$ARCHIVE_ROOT/LinuxNoEditor" "$ARCHIVE_ROOT/Linux"
  elif [[ -d "$ARCHIVE_ROOT/LinuxClient" ]]; then
    mv "$ARCHIVE_ROOT/LinuxClient" "$ARCHIVE_ROOT/Linux"
  fi
fi

if [[ ! -f "$ARCHIVE_ROOT/Linux/MorphRig.sh" ]]; then
  echo "[MorphRig] ERROR: Expected packaged launcher at $ARCHIVE_ROOT/Linux/MorphRig.sh" >&2
  exit 1
fi

chmod +x "$ARCHIVE_ROOT/Linux/MorphRig.sh"
echo "[MorphRig] Packaged standalone Linux showcase ready at: $ARCHIVE_ROOT/Linux/MorphRig.sh"
