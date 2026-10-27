#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${UE_EXEC:-}" ]; then
    WRAPPER=$UE_EXEC
elif [ -f "$ROOT/../environment.json" ]; then
    WRAPPER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["unreal_engine"]["runtime_wrapper"].split(" ")[0])' "$ROOT/../environment.json")
elif command -v ue-exec >/dev/null 2>&1; then
    WRAPPER=$(command -v ue-exec)
else
    printf '%s\n' 'Set UE_EXEC to the supplied Unreal FHS wrapper.' >&2
    exit 2
fi
PROJECT="$ROOT/unreal/MorphRig/MorphRig.uproject"
if [ ! -f "$PROJECT" ]; then
    printf '%s\n' "Missing $PROJECT" >&2
    exit 2
fi
python3 - "$ROOT" "$@" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
options = root / "unreal" / "MorphRig" / "Saved" / "ImportOptions.json"
options.parent.mkdir(parents=True, exist_ok=True)
options.write_text(json.dumps({"arguments": [arg for arg in sys.argv[2:] if arg != "--"]}, indent=2) + "\n", encoding="utf-8")
PY
"$WRAPPER" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$PROJECT" -run=pythonscript -script="$ROOT/unreal/MorphRig/Tools/import_operative.py" -unattended -nop4 -python-exit-code=1
exec "$WRAPPER" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$PROJECT" -run=pythonscript -script="$ROOT/unreal/MorphRig/Tools/import_beacon.py" -unattended -nop4 -python-exit-code=1
