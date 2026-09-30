#!/usr/bin/env bash
# Run the packaged Linux client from build/Linux (inside the UE FHS runtime that NixOS needs).
# usage: tools/ue_run_packaged.sh [engine args...]
#   examples:
#     tools/ue_run_packaged.sh                                   interactive showcase (windowed 1920x1080)
#     tools/ue_run_packaged.sh -RenderOffScreen -ShowcaseSequence -ExitAfterSequence -NoPanel
#     tools/ue_run_packaged.sh -RenderOffScreen -CaptureMode=turntable -CaptureDir=$PWD/build/capture/turntable
#     tools/ue_run_packaged.sh -PerfLog=$PWD/docs/perf/perf_10.csv -Instances=10 -ExitAfterPerf
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
BIN="$MORPHRIG_ROOT/build/Linux/MorphRig.sh"
[ -x "$BIN" ] || { echo "packaged client missing: run tools/build_linux.sh first" >&2; exit 1; }
cd "$MORPHRIG_ROOT/build/Linux"
"$UE_EXEC" "$BIN" -windowed -ResX=1920 -ResY=1080 -stdout -FullStdOutLogOutput "$@"
