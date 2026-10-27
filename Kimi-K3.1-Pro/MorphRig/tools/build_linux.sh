#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT="$ROOT/unreal/MorphRig/MorphRig.uproject"
ENVIRONMENT_JSON="${MORPHRIG_ENVIRONMENT:-$ROOT/../environment.json}"
PYTHON="${PYTHON:-python3}"

if [[ ! -f "$PROJECT" ]]; then
    echo "Missing project: $PROJECT" >&2
    exit 2
fi
if [[ ! -f "$ENVIRONMENT_JSON" ]]; then
    echo "Missing environment manifest: $ENVIRONMENT_JSON" >&2
    exit 2
fi

IFS=$'\t' read -r UE_EXEC UAT < <("$PYTHON" - "$ENVIRONMENT_JSON" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
engine = manifest["unreal_engine"]
wrapper = engine["runtime_wrapper"].split()[0]
uat = str(Path(engine["root"]) / "Engine" / "Build" / "BatchFiles" / "RunUAT.sh")
print(wrapper + "\t" + uat)
PY
)

if [[ ! -x "$UE_EXEC" ]]; then
    echo "ue-exec is not executable: $UE_EXEC" >&2
    exit 2
fi
if [[ ! -f "$UAT" ]]; then
    echo "RunUAT was not found: $UAT" >&2
    exit 2
fi

mkdir -p "$ROOT/build/Linux"
printf 'Building MorphRig Linux x86-64 Development into %s/build/Linux\n' "$ROOT"
"$UE_EXEC" "$UAT" BuildCookRun \
    "-project=$PROJECT" \
    -platform=Linux \
    -clientconfig=Development \
    -build -cook -stage -pak -archive \
    "-archivedirectory=$ROOT/build/Linux"
