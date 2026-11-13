#!/usr/bin/env bash
# Warmed-up frame-time benchmark of the PACKAGED client at 1920x1080 with 1 and 10 animated Operatives.
# Writes <label>_frames.csv and <label>.json (settings, CPU/RAM/GPU) to docs/benchmark/ plus host details.
#   tools/run_benchmark.sh            (MORPHRIG_OFFSCREEN=0 to measure in a normal window on a desktop)
set -euo pipefail
export MORPHRIG_CLIENT_ONLY=1    # only the packaged client is started: no engine installation needed
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
OUT="$MORPHRIG_ROOT/docs/benchmark"
mkdir -p "$OUT"
export MORPHRIG_OFFSCREEN="${MORPHRIG_OFFSCREEN:-1}"
export MORPHRIG_RESX=1920 MORPHRIG_RESY=1080
{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "render_offscreen: $MORPHRIG_OFFSCREEN"
  echo "kernel: $(uname -sr)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
  echo "logical_cpus: $(nproc)"
  echo "ram_total_kb: $(grep MemTotal /proc/meminfo | awk '{print $2}')"
  # load from other workloads on a shared host distorts frame times: record it with the result
  echo "load_average_before_run (1/5/15 min, $(nproc) logical CPUs): $(cut -d' ' -f1-3 /proc/loadavg)"
  echo "cpu_busy_before_run: $( (head -1 /proc/stat; sleep 1; head -1 /proc/stat) | awk 'NR==1{for(i=2;i<=9;i++)a[i]=$i} NR==2{t=0;for(i=2;i<=9;i++){d[i]=$i-a[i];t+=d[i]} printf "%.0f %% (idle %.0f %%, iowait %.0f %%)", 100*(t-d[5]-d[6])/t, 100*d[5]/t, 100*d[6]/t}')"
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "gpu: $(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | head -1)"
    echo "gpu_before_run (util %, memory used, other workloads share this GPU): $(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | head -1)"
  fi
} > "$OUT/host.txt"
"$TOOLS_DIR/run_showcase.sh" -nosplash -MorphQuit -MorphScript="$TOOLS_DIR/scripts/benchmark.txt" -MorphBenchDir="$OUT" \
  -MorphTrace="$OUT/benchmark_trace.log" > "$OUT/client.log" 2>&1 || { tail -20 "$OUT/client.log"; echo "benchmark run failed"; exit 1; }
grep "BENCH" "$OUT/benchmark_trace.log" | sed -E 's/^\[[^]]*\] //'
rm -f "$OUT/client.log"
ls -la "$OUT"
