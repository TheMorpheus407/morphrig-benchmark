#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE="$TASK_DIR/docs/validation/performance"
mkdir -p "$EVIDENCE"

# Run after this project's render, import and build workers have finished.
# No MorphCaptureDir: the client must use its ordinary wall clock.
cp "$TASK_DIR/unreal/Config/DefaultEngine.ini" "$EVIDENCE/DefaultEngine.ini"
cp "$TASK_DIR/unreal/Config/DefaultGameUserSettings.ini" "$EVIDENCE/DefaultGameUserSettings.ini"
date --iso-8601=seconds > "$EVIDENCE/started.txt"
nvidia-smi > "$EVIDENCE/gpu_before.txt"
uptime > "$EVIDENCE/host_load_before.txt"
for COUNT in 1 10; do
  RUN_DIR="$EVIDENCE/${COUNT}_actors"
  mkdir -p "$RUN_DIR"
  printf '%s\n' '1920x1080, Vulkan SM6, default showcase lighting and visible UI, automatic LOD, ordinary wall clock, 45 seconds, first 10 seconds discarded' > "$RUN_DIR/settings.txt"
  bash "$TASK_DIR/tools/run_showcase.sh" "-MorphInstances=$COUNT" \
    -MorphSeconds=45 "-MorphEvidenceDir=$RUN_DIR" > "$RUN_DIR/stdout.log" 2>&1
done
nvidia-smi > "$EVIDENCE/gpu_after.txt"
date --iso-8601=seconds > "$EVIDENCE/finished.txt"
python3 "$TASK_DIR/tools/analyze_performance.py" \
  "$EVIDENCE/1_actors/frames_1_actors.csv" \
  "$EVIDENCE/10_actors/frames_10_actors.csv"
