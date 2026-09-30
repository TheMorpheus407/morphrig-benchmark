#!/usr/bin/env bash
# Runs a Python script inside the piper-tts environment (nixpkgs piper-tts 1.4.2 with eSpeak NG). No nix build is needed when the
# package is already in the store. Usage: tools/piper_py.sh script.py [args...]
# PIPER_TTS_OUT can point at another piper-tts store path (for example from `nix-build '<nixpkgs>' -A piper-tts --no-out-link`).
set -euo pipefail
PIPER_TTS_OUT="${PIPER_TTS_OUT:-$(ls -d /nix/store/*-piper-tts-1.4.2 2>/dev/null | head -n 1)}"
if [ -z "${PIPER_TTS_OUT}" ] || [ ! -x "${PIPER_TTS_OUT}/bin/.piper-wrapped" ]; then
  echo "piper-tts 1.4.2 not found in /nix/store. Realise it once with: nix-build '<nixpkgs>' -A piper-tts --no-out-link" >&2
  exit 1
fi
WRAPPED="${PIPER_TTS_OUT}/bin/.piper-wrapped"
PY="$(head -n 1 "${WRAPPED}" | sed 's/^#!//')"
export PYTHONNOUSERSITE=true
export PIPER_WRAPPED="${WRAPPED}"
exec "${PY}" -c '
import os, re, runpy, site, sys
src = open(os.environ["PIPER_WRAPPED"]).read()
for p in dict.fromkeys(re.findall(r"\x27(/nix/store/[^\x27]*site-packages)\x27", src)):
    site.addsitedir(p)
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
' "$@"
