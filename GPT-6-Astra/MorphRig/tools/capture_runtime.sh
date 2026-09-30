#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MOTION="$TASK_DIR/presentation/frames/runtime_delivery_motion"
TERRAIN="$TASK_DIR/presentation/frames/runtime_delivery_terrain"
DEMO_LOG="$TASK_DIR/docs/validation/runtime_delivery_demo"
TERRAIN_LOG="$TASK_DIR/docs/validation/runtime_delivery_terrain"
mkdir -p "$MOTION" "$TERRAIN" "$DEMO_LOG" "$TERRAIN_LOG"
python3 - "$MOTION" "$TERRAIN" <<'PY'
from pathlib import Path
import sys
for directory in map(Path, sys.argv[1:]):
    for frame in directory.glob('frame_*.png'):
        frame.unlink()
PY
bash "$TASK_DIR/tools/run_showcase.sh" -MorphCapture=motion -MorphShowUI \
  -MorphSeconds=50 -MorphCaptureFPS=30 "-MorphCaptureDir=$MOTION" \
  "-MorphEvidenceDir=$DEMO_LOG" > "$DEMO_LOG/stdout.log" 2>&1
python3 "$TASK_DIR/tools/audit_runtime_trace.py" "$DEMO_LOG/state_event_trace.log" --demo
bash "$TASK_DIR/tools/run_showcase.sh" -MorphTerrain -MorphCapture=terrain \
  -MorphSeconds=7 -MorphCaptureFPS=30 "-MorphCaptureDir=$TERRAIN" \
  "-MorphEvidenceDir=$TERRAIN_LOG" > "$TERRAIN_LOG/stdout.log" 2>&1
# A platform can skip a screenshot during initial swapchain creation. Glob input
# consumes every captured frame instead of stopping at that initial index gap.
ffmpeg -y -hide_banner -loglevel warning \
  -framerate 30 -pattern_type glob -i "$MOTION/frame_*.png" \
  -framerate 30 -pattern_type glob -i "$TERRAIN/frame_*.png" \
  -filter_complex '[0:v][1:v]concat=n=2:v=1:a=0[v]' -map '[v]' \
  -c:v libx264 -threads 8 -preset medium -crf 18 -pix_fmt yuv420p \
  -movflags +faststart "$TASK_DIR/presentation/motion_showcase.mp4" \
  > "$TASK_DIR/docs/validation/encode_motion.log" 2>&1
