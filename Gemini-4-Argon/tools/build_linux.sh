#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPROJECT="$REPO_ROOT/unreal/MorphRig.uproject"
IMPORT_SCRIPT="$REPO_ROOT/tools/unreal_import_assets.py"
ARCHIVE_DIR="$REPO_ROOT/build"

echo "[1/3] Compiling MorphRigEditor C++ module for Unreal Engine 5.8.3..."
/home/morpheus/UnrealEngine/bin/ue-exec \
  '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' \
  MorphRigEditor Linux Development \
  -Project="$UPROJECT" \
  -WaitMutex

echo "[2/3] Running headless UnrealEditor-Cmd to import Operative.fbx, LODs, textures, audio, 96 animations & ShowcaseArena map..."
/home/morpheus/UnrealEngine/bin/ue-exec \
  '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' \
  "$UPROJECT" \
  -run=pythonscript \
  -script="$IMPORT_SCRIPT" \
  -unattended -nop4 -nosplash -nullrhi

echo "[3/3] Packaging standalone Linux x86-64 showcase client into build/Linux/ ..."
/home/morpheus/UnrealEngine/bin/ue-exec \
  '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' \
  BuildCookRun \
  -project="$UPROJECT" \
  -noP4 \
  -platform=Linux \
  -clientconfig=Development \
  -cook -allmaps -build -stage -pak -archive \
  -archivedirectory="$ARCHIVE_DIR" \
  -utf8output

echo "Packaged Linux showcase client successfully in: $ARCHIVE_DIR/Linux"
ls -la "$ARCHIVE_DIR/Linux"
