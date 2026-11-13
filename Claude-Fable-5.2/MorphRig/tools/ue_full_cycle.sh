#!/usr/bin/env bash
# One command for the whole Unreal side after a (re-)export:
#
#   tools/ue_full_cycle.sh                 build + verify + bench + capture
#   tools/ue_full_cycle.sh build verify    only the named stages, in this order: build verify bench capture
#
#   build    tools/build_linux.sh: editor module, clean re-import of export/ + docs/ (stale Content folders are deleted),
#            cook + package to build/Linux                         (MORPHRIG_SKIP_IMPORT=1 keeps the imported content)
#   verify   packaged client, offscreen, fixed 30 fps time step: deterministic sequence, injected-input self-test and
#            motion-viewer pass over all 96 entries; each trace is checked by tools/verify_trace.py
#            -> docs/verification/{sequence,ui_selftest,browse_all}_trace.log, *_verify.txt, import_summary.txt
#   bench    tools/run_benchmark.sh -> docs/benchmark/
#   capture  tools/capture_presentation.sh all -> presentation/*.mp4 (+ traces)
#
# Every stage is idempotent (outputs are replaced). The script stops at the first failing stage and prints a summary.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ue_env.sh"
STAGES=("$@"); [ ${#STAGES[@]} -gt 0 ] || STAGES=(build verify bench capture)
VER="$MORPHRIG_ROOT/docs/verification"
SCRIPTS="$TOOLS_DIR/scripts"
SUMMARY=()
fail() { SUMMARY+=("FAILED  $1"); printf '%s\n' "${SUMMARY[@]}"; exit 1; }
has_stage() { local s; for s in "${STAGES[@]}"; do [ "$s" = "$1" ] || [ "$s" = "all" ] && return 0; done; return 1; }

run_checked() {  # run_checked <name> <client args...>  -> trace + verify report in docs/verification
  local name="$1"; shift
  rm -f "$VER/${name}_trace.log" "$VER/${name}_verify.txt"
  MORPHRIG_OFFSCREEN="${MORPHRIG_OFFSCREEN:-1}" "$TOOLS_DIR/run_showcase.sh" -nosplash -MorphQuit -MorphFixedFps=30 \
    -MorphTrace="$VER/${name}_trace.log" "$@" > "$VER/${name}_client.log" 2>&1 || { tail -15 "$VER/${name}_client.log"; return 1; }
  python3 "$TOOLS_DIR/verify_trace.py" "$VER/${name}_trace.log" > "$VER/${name}_verify.txt" 2>&1
  local rc=$?
  tail -n +2 "$VER/${name}_verify.txt" | sed "s/^/  [$name] /"
  rm -f "$VER/${name}_client.log"
  return $rc
}

if has_stage build; then
  if [ "${MORPHRIG_SKIP_IMPORT:-0}" = "1" ]; then "$TOOLS_DIR/build_linux.sh" --skip-import; else "$TOOLS_DIR/build_linux.sh"; fi \
    || fail "build (see unreal/Saved/Logs/morphrig_*.log)"
  SUMMARY+=("ok      build -> build/Linux ($(du -sh "$MORPHRIG_ROOT/build/Linux" | cut -f1))")
fi
if has_stage verify; then
  mkdir -p "$VER"
  grep -h "MORPHRIG_IMPORT" "$MORPHRIG_ROOT/unreal/Saved/Logs/morphrig_import.log" 2>/dev/null | sed -E 's/^.*MORPHRIG_IMPORT ?//' > "$VER/import_summary.txt" || true
  run_checked sequence -MorphSequence || fail "verify: deterministic sequence (docs/verification/sequence_verify.txt)"
  run_checked ui_selftest -MorphScript="$SCRIPTS/ui_selftest.txt" || fail "verify: injected-input self-test (docs/verification/ui_selftest_verify.txt)"
  run_checked browse_all -MorphScript="$SCRIPTS/browse_all.txt" || fail "verify: motion viewer pass (docs/verification/browse_all_verify.txt)"
  SUMMARY+=("ok      verify -> docs/verification (sequence, ui_selftest, browse_all: no rule violated)")
fi
if has_stage bench; then
  "$TOOLS_DIR/run_benchmark.sh" || fail "bench"
  SUMMARY+=("ok      bench -> docs/benchmark")
fi
if has_stage capture; then
  "$TOOLS_DIR/capture_presentation.sh" all || fail "capture"
  SUMMARY+=("ok      capture -> presentation/turntable.mp4, motion_showcase.mp4, face_performance.mp4")
fi
printf '%s\n' "${SUMMARY[@]}"
