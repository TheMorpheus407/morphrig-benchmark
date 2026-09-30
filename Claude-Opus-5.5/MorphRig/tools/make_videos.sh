#!/usr/bin/env bash
# Render the presentation videos from the packaged showcase client (fixed 30 fps capture, 1920x1080).
#   presentation/turntable.mp4        neutral full-body turntable (10 s)
#   presentation/motion_showcase.mp4  deterministic state/motion sequence with HUD (108 s)
#   presentation/face_performance.mp4 face close-up speech performance with the dialogue audio
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
UEX="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"
GAME="$ROOT/build/Linux/MorphRig.sh"
CAP="$ROOT/build/capture"
OUT="$ROOT/presentation"
mkdir -p "$OUT"
for mode in turntable face showcase; do
    rm -rf "${CAP:?}/$mode"
    mkdir -p "$CAP/$mode"
    "$UEX" "$GAME" -MorphCapture="$mode" -MorphCaptureDir="$CAP/$mode" -ResX=1920 -ResY=1080 -windowed \
        -NoVerifyGC -unattended > "$CAP/$mode.log" 2>&1 || true
    n=$(ls "$CAP/$mode" | grep -c '\.png$' || true)
    echo "$mode: $n frames"
done
enc() { ffmpeg -loglevel error -y -framerate 30 -i "$CAP/$1/$1_%05d.png" "${@:3}" -c:v libx264 -pix_fmt yuv420p -crf 18 "$OUT/$2"; }
enc turntable turntable.mp4
enc showcase motion_showcase.mp4
# the dialogue clip (and its audio) starts on capture frame 15 = 0.5 s
ffmpeg -loglevel error -y -framerate 30 -i "$CAP/face/face_%05d.png" -itsoffset 0.5 -i "$ROOT/source/audio/dialogue.wav" \
    -map 0:v -map 1:a -c:v libx264 -pix_fmt yuv420p -crf 16 -c:a aac -b:a 192k -shortest "$OUT/face_performance.mp4"
ls -la "$OUT"
