#!/usr/bin/env bash
# Rebuild using the installed engine from environment.json. All task outputs,
# scratch files, compiler logs, imported data and DDC stay in the task folder.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_root"
ue_runtime="$(python3 -c 'import json; print(json.load(open("environment.json"))["unreal_engine"]["runtime_wrapper"].split(" — ")[0])')"
project="$task_root/unreal/MorphRig.uproject"
mkdir -p verification/logs unreal/Saved/Temp unreal/Saved/DerivedDataCache unreal/Saved/ConfigHome unreal/Saved/CacheHome
export TMPDIR="$task_root/unreal/Saved/Temp"
export XDG_CONFIG_HOME="$task_root/unreal/Saved/ConfigHome"
export XDG_CACHE_HOME="$task_root/unreal/Saved/CacheHome"
export uebp_LogFolder="$task_root/verification/logs/UAT"
export uebp_FinalLogFolder="$task_root/verification/logs/UAT"
case "${1:-package}" in
  editor)
    env "UE-LocalDataCachePath=$task_root/unreal/Saved/DerivedDataCache" "$ue_runtime" '$UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh' MorphRigEditor Linux Development "-Project=$project" -NoEngineChanges -NoHotReloadFromIDE "-Log=$task_root/verification/logs/cpp_editor.log" 2>&1 | tee verification/logs/build_editor_console.log
    ;;
  import)
    shift
    env "UE-LocalDataCachePath=$task_root/unreal/Saved/DerivedDataCache" "$ue_runtime" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' "$project" -unattended -nop4 -nosplash -notraceserver -traceautostart=0 -NullRHI -run=pythonscript "-script=$task_root/tools/import_unreal.py" "-abslog=$task_root/verification/logs/unreal_import.log" "-UserDir=$task_root/unreal/Saved/User" "$@" > verification/logs/import_console.log 2>&1
    ;;
  package)
    if [[ $# -gt 0 ]]; then shift; fi
    env "UE-LocalDataCachePath=$task_root/unreal/Saved/DerivedDataCache" "$ue_runtime" '$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh' BuildCookRun "-project=$project" -platform=Linux -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$task_root/build/Linux" -unattended -nop4 -utf8output "-abslog=$task_root/verification/logs/package.log" "$@" 2>&1 | tee verification/logs/package_console.log
    mkdir -p "$task_root/build/Linux/Licenses/unreal"
    cp -R "$task_root/docs/licenses/unreal/." "$task_root/build/Linux/Licenses/unreal/"
    ;;
  run)
    shift
    env "UE-LocalDataCachePath=$task_root/unreal/Saved/DerivedDataCache" "$ue_runtime" "$task_root/build/Linux/MorphRig.sh" -ResX=1920 -ResY=1080 -windowed -NoVSync -notraceserver -traceautostart=0 "-UserDir=$task_root/unreal/Saved/User" "$@"
    ;;
  preview)
    shift
    env "UE-LocalDataCachePath=$task_root/unreal/Saved/DerivedDataCache" "$ue_runtime" '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor' "$project" -game -ResX=1920 -ResY=1080 -windowed -NoVSync -notraceserver -traceautostart=0 "-UserDir=$task_root/unreal/Saved/User" "$@"
    ;;
  *) printf '%s\n' 'Usage: tools/build_linux.sh [editor|import|package|run [client options]|preview [client options]]' >&2; exit 2;;
esac
