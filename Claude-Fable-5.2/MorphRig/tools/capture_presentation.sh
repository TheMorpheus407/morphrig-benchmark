#!/usr/bin/env bash
# Capture the presentation videos from the PACKAGED showcase client (fixed 30 fps time step, lossless frames, x264 encode).
#
#   tools/capture_presentation.sh all | turntable | motion | face
#
# Frames go to $MORPHRIG_CAPTURE_DIR (default: unreal/Saved/Capture, several GB for the motion sequence) and are
# removed after a successful encode unless MORPHRIG_KEEP_FRAMES=1. The client renders offscreen by default
# (MORPHRIG_OFFSCREEN=0 uses a normal window on a desktop).
set -euo pipefail
export MORPHRIG_CLIENT_ONLY=1    # only the packaged client is started: no engine installation needed
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
WHAT="${1:-all}"
CAP="${MORPHRIG_CAPTURE_DIR:-$MORPHRIG_ROOT/unreal/Saved/Capture}"
OUT="$MORPHRIG_ROOT/presentation"
AUDIO="$MORPHRIG_ROOT/source/audio/dialogue.wav"
mkdir -p "$CAP" "$OUT"
export MORPHRIG_OFFSCREEN="${MORPHRIG_OFFSCREEN:-1}"

encode() {  # encode <frames dir> <output mp4> [audio file] [audio delay seconds]
  local dir="$1" out="$2" audio="${3:-}" delay="${4:-0}"
  local n; n=$(ls "$dir" | grep -c '^frame_.*\.png$' || true)
  [ "$n" -gt 0 ] || { echo "no frames in $dir"; return 1; }
  if [ -n "$audio" ]; then
    local ms; ms=$(python3 -c "print(int(round(float('$delay')*1000)))")
    ffmpeg -y -loglevel error -framerate 30 -i "$dir/frame_%05d.png" -i "$audio" \
      -filter_complex "[1:a]adelay=${ms}:all=1[a]" -map 0:v -map "[a]" \
      -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart "$out"
  else
    ffmpeg -y -loglevel error -framerate 30 -i "$dir/frame_%05d.png" \
      -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -movflags +faststart "$out"
  fi
  echo "encoded $out ($n frames, $(du -h "$out" | cut -f1))"
  [ "${MORPHRIG_KEEP_FRAMES:-0}" = "1" ] || rm -rf "$dir"
}

run_client() {  # run_client <name> <extra args...>
  local name="$1"; shift
  rm -rf "$CAP/$name"; mkdir -p "$CAP/$name"
  "$TOOLS_DIR/run_showcase.sh" -nosplash -MorphQuit -MorphTrace="$CAP/$name.trace.log" "$@" > "$CAP/$name.client.log" 2>&1 \
    || { tail -20 "$CAP/$name.client.log"; echo "client run failed: $CAP/$name.client.log"; return 1; }
}

if [ "$WHAT" = "all" ] || [ "$WHAT" = "turntable" ]; then
  run_client turntable -MorphScript="$TOOLS_DIR/scripts/turntable.txt" -MorphCaptureDir="$CAP/turntable"
  encode "$CAP/turntable" "$OUT/turntable.mp4"
fi

if [ "$WHAT" = "all" ] || [ "$WHAT" = "motion" ]; then
  # the deterministic showcase sequence, captured from its first frame; its trace is the state/event log of the video
  run_client motion -MorphSequence -MorphCapture="$CAP/motion" -MorphFPS=30
  cp "$CAP/motion.trace.log" "$OUT/motion_showcase_trace.log"
  encode "$CAP/motion" "$OUT/motion_showcase.mp4"
fi

if [ "$WHAT" = "all" ] || [ "$WHAT" = "face" ]; then
  run_client face -MorphScript="$TOOLS_DIR/scripts/face_performance.txt" -MorphCaptureDir="$CAP/face"
  # audio sync: the WAV starts at the traced line_start marker, measured from the traced first captured frame
  DELAY=$(python3 - "$CAP/face.trace.log" <<'PY'
import re, sys
start = line = None
for l in open(sys.argv[1], encoding='utf-8', errors='replace'):
    m = re.match(r'\[\s*([0-9.]+)\]\s+(.*)', l)
    if not m:
        continue
    t, body = float(m.group(1)), m.group(2)
    if body.startswith('CAPTURE first frame') and start is None:
        start = t
    if body.startswith('EVENT line_start') and start is not None and line is None:
        line = t
print('%.3f' % ((line - start) if (start is not None and line is not None) else 0.0))
PY
)
  echo "dialogue audio delay relative to the first frame: ${DELAY}s"
  cp "$CAP/face.trace.log" "$OUT/face_performance_trace.log"
  encode "$CAP/face" "$OUT/face_performance.mp4" "$AUDIO" "$DELAY"
fi
