#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TASK_ROOT"
ffmpeg -y -framerate 30 -i presentation/frames/turntable/%05d.png -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart presentation/turntable.mp4
ffmpeg -y -framerate 30 -i presentation/frames/motion/%05d.png -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart presentation/motion_showcase.mp4
ffmpeg -y -framerate 30 -i presentation/frames/face/%05d.png -i source/audio/dialogue.wav -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart presentation/face_performance.mp4
