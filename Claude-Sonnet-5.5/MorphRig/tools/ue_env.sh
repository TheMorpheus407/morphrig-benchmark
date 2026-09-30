# Shared environment for the MorphRig tools. Source it, do not execute it.
# UE_EXEC runs a command inside the Unreal FHS runtime that NixOS needs (see docs/build_and_import_instructions.md).
export UE_EXEC="${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}"
export MORPHRIG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MORPHRIG_UPROJECT="$MORPHRIG_ROOT/unreal/MorphRig.uproject"
