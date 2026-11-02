#!/usr/bin/env bash
# Package the MORPHRIG showcase client for Linux x86-64.
#
#   tools/build_linux.sh [--skip-cook] [--configuration Development]
#
# Output: build/Linux/<project>/MorphRig.sh  (a self contained client)
# The script builds the game target, cooks the content, stages it and
# archives it into build/Linux.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UE_ROOT="${UE_ROOT:-/home/morpheus/UnrealEngine/5.8.3}"
UE_EXEC="${UE_EXEC:-/home/morpheus/UnrealEngine/bin/ue-exec}"
PROJECT="$ROOT/unreal/MorphRig.uproject"
ARCHIVE="$ROOT/build/Linux"
CONFIG="Development"
SKIP_COOK=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-cook)   SKIP_COOK=1; shift ;;
        --configuration) CONFIG="$2"; shift 2 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$ARCHIVE"

echo "=== 1/3  building the game target ==="
"$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' \
    MorphRig Linux "$CONFIG" \
    -project="$PROJECT" -waitmutex

if [[ "$SKIP_COOK" -eq 0 ]]; then
    echo "=== 2/3  cooking and packaging ==="
    "$UE_EXEC" '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' \
        BuildCookRun \
        -project="$PROJECT" \
        -noP4 \
        -platform=Linux \
        -clientconfig="$CONFIG" \
        -build \
        -cook \
        -cookflavour=Development \
        -stage \
        -pak \
        -archive \
        -archivedirectory="$ARCHIVE" \
        -unattended \
        -utf8output
else
    echo "=== 2/3  cooking skipped ==="
fi

echo "=== 3/3  result ==="
find "$ARCHIVE" -maxdepth 3 -type f -name "*.sh" -o -maxdepth 3 -type f -name "*.pak" | head -20
du -sh "$ARCHIVE" 2>/dev/null || true
echo "client: $ARCHIVE"
