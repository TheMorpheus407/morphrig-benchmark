#!/usr/bin/env bash
# Stand-in for ue-exec on hosts without the NixOS FHS runtime (untested on the reference host, where ue-exec is required).
# Expands $UE_ROOT in the first argument like ue-exec does and runs it. usage: UE_ROOT=/path/to/UnrealEngine-5.8 UE_EXEC=tools/ue_exec_plain.sh tools/ue_import_all.sh
set -euo pipefail
: "${UE_ROOT:?set UE_ROOT to the Unreal Engine 5.8 root folder}"
cmd=$(eval echo "$1"); shift
exec "$cmd" "$@"
