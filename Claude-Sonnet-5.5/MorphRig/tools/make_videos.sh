#!/usr/bin/env bash
# Records the three presentation videos from the PACKAGED Linux client and encodes them into presentation/.
# The client renders offscreen at a fixed 30 fps time step and writes one PNG per frame (capture modes of the showcase director);
# ffmpeg turns the frames into H.264 and, for the face video, muxes source/audio/dialogue.wav.
#
# usage: tools/make_videos.sh [turntable] [motion] [face]      (default: all three)
#   CAP_DIR=/path        where the temporary frames go (default build/capture; removed after encoding unless KEEP_FRAMES=1)
#   FACE_AUDIO_SKIP=0.033  seconds cut from the start of the audio (the clip starts one time step before the first captured frame)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAP="${CAP_DIR:-$ROOT/build/capture}"
SKIP="${FACE_AUDIO_SKIP:-0.033}"
mkdir -p "$ROOT/presentation" "$CAP"
modes=("$@")
[ "${#modes[@]}" -eq 0 ] && modes=(turntable motion face)

encode() {   # encode <frames dir> <output.mp4> [audio.wav]
  local dir="$1" out="$2" audio="${3:-}"
  local common=(-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart)
  if [ -n "$audio" ]; then
    ffmpeg -y -loglevel error -framerate 30 -i "$dir/frame_%05d.png" -ss "$SKIP" -i "$audio" \
      -filter_complex "[1:a]aresample=48000,apad[a]" -map 0:v -map "[a]" "${common[@]}" -c:a aac -b:a 192k -shortest "$out"
  else
    ffmpeg -y -loglevel error -framerate 30 -i "$dir/frame_%05d.png" "${common[@]}" "$out"
  fi
}

for m in "${modes[@]}"; do
  echo "== capture: $m"
  rm -rf "$CAP/$m"; mkdir -p "$CAP/$m"
  "$ROOT/tools/ue_run_packaged.sh" -RenderOffScreen -CaptureMode="$m" -CaptureDir="$CAP/$m" -NoPanel > "$CAP/$m.log" 2>&1 || true
  n=$(find "$CAP/$m" -name 'frame_*.png' | wc -l)
  echo "   $n frames"
  [ "$n" -gt 30 ] || { echo "capture $m produced too few frames, see $CAP/$m.log" >&2; exit 1; }
  case "$m" in
    turntable) encode "$CAP/$m" "$ROOT/presentation/turntable.mp4" ;;
    motion)    encode "$CAP/$m" "$ROOT/presentation/motion_showcase.mp4" ;;
    face)      encode "$CAP/$m" "$ROOT/presentation/face_performance.mp4" "$ROOT/source/audio/dialogue.wav" ;;
    *) echo "unknown mode $m" >&2; exit 1 ;;
  esac
  [ "${KEEP_FRAMES:-0}" = "1" ] || rm -rf "$CAP/$m"
done
ls -la "$ROOT/presentation"
