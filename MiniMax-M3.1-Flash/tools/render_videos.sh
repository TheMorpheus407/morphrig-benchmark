#!/usr/bin/env bash
# Render the three MORPHRIG presentation videos.
#
#   tools/render_videos.sh [--samples N] [--only turntable|motion|face]
#                            [--fresh]
#
# Each video is rendered by its own Blender process, so a crash in one does
# not take the others down, and the PNG frames are resumed when they exist.
# --fresh drops the frames first, which is needed after the asset changed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLENDER="${BLENDER:-/run/current-system/sw/bin/blender}"
OUTDIR="$ROOT/presentation"
LOGDIR="$ROOT/build/video_logs"
SAMPLES=16
ONLY=""
FRESH=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --samples) SAMPLES="$2"; shift 2 ;;
        --only)    ONLY="$2";    shift 2 ;;
        --outdir)  OUTDIR="$2";  shift 2 ;;
        --fresh)   FRESH=1;      shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$OUTDIR" "$LOGDIR"

if [[ "$FRESH" -eq 1 ]]; then
    echo "=== dropping the frames of the previous build ==="
    for DIR in _frames_turntable _frames_motion _frames_face; do
        if [[ -d "$OUTDIR/$DIR" ]]; then
            find "$OUTDIR/$DIR" -type f -name '*.png' -delete
        fi
    done
fi

for VIDEO in turntable motion face; do
    if [[ -n "$ONLY" && "$ONLY" != "$VIDEO" ]]; then
        continue
    fi
    echo "=== rendering $VIDEO ==="
    "$BLENDER" -b --factory-startup \
        -P "$ROOT/source/generators/render_videos.py" -- \
        --outdir "$OUTDIR" --only "$VIDEO" --samples "$SAMPLES" \
        > "$LOGDIR/$VIDEO.log" 2>&1 || {
            echo "video $VIDEO failed, see $LOGDIR/$VIDEO.log" >&2
            tail -20 "$LOGDIR/$VIDEO.log" >&2
            exit 1
        }
    grep -E "RENDER_DONE|VIDEO " "$LOGDIR/$VIDEO.log" || true
done

echo "videos in $OUTDIR"
ls -la "$OUTDIR"/*.mp4
