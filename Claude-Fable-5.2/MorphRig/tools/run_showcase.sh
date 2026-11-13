#!/usr/bin/env bash
# Start the packaged Linux showcase client (no Unreal Editor involved).
#   tools/run_showcase.sh                         interactive, 1920x1080 window
#   MORPHRIG_OFFSCREEN=1 tools/run_showcase.sh    headless (no presentable display, e.g. Xvfb / CI); add automation flags:
#       -MorphSequence -MorphQuit                 run the deterministic sequence, then exit
#       -MorphScript=/abs/script.txt -MorphQuit   run an automation script
#       -MorphCapture=/abs/frames -MorphFPS=30    fixed-step frame dump
#       -MorphExec="team B; cam face"             commands at start-up
set -euo pipefail
export MORPHRIG_CLIENT_ONLY=1    # only the packaged client is started: no engine installation needed
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
CLIENT="$MORPHRIG_ROOT/build/Linux/MorphRig.sh"
[ -f "$CLIENT" ] || { echo "packaged client missing: run tools/build_linux.sh first"; exit 1; }
ARGS=(-ResX="${MORPHRIG_RESX:-1920}" -ResY="${MORPHRIG_RESY:-1080}" -windowed)
if [ "${MORPHRIG_OFFSCREEN:-0}" = "1" ]; then
  ARGS+=(-RenderOffScreen -ForceRes -unattended)
  # headless hosts usually have no sound device either: let SDL open its silent dummy device so the audio
  # engine (and the dialogue audio component) runs normally. Override with MORPHRIG_AUDIODRIVER=pulseaudio etc.
  export SDL_AUDIODRIVER="${MORPHRIG_AUDIODRIVER:-dummy}"
fi
ue_run_abs "$CLIENT" "${ARGS[@]}" "$@"
