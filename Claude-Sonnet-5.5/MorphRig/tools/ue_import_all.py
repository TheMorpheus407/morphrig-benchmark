"""MORPHRIG: idempotent full import of export/ and docs/ into the Unreal project (run inside UnrealEditor-Cmd).

usage:  tools/ue_import_all.sh [steps]        (steps: comma list of mesh,clips,props,audio,materials,assets,level; default all)
This file is the driver; the pieces live in tools/ue_import/*.py.

Every step re-applies everything it owns (replace_existing=True, sockets/notifies/curves rebuilt), so the lead can refresh
export/ clip by clip and run the import again. The clip list and all clip settings come from docs/animation_manifest.json.
"""
import os
import sys
import json
import time
import traceback

import unreal

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "ue_import"))

import common as C          # noqa: E402  (shared helpers: logging, paths, asset tools)
import mesh_import          # noqa: E402
import clip_import          # noqa: E402
import props_audio          # noqa: E402
import materials            # noqa: E402
import assets_level         # noqa: E402


def steps_from_command_line():
    cl = unreal.SystemLibrary.get_command_line()
    for tok in cl.split():
        if tok.startswith("-MRSteps="):
            return [s for s in tok.split("=", 1)[1].split(",") if s]
    return ["mesh", "clips", "props", "audio", "materials", "assets", "level"]


def main():
    t0 = time.time()
    steps = steps_from_command_line()
    C.log("START steps=%s root=%s" % (",".join(steps), ROOT))
    ctx = C.Context(ROOT)
    failed = []
    table = [("mesh", mesh_import.run), ("clips", clip_import.run), ("props", props_audio.run_props), ("audio", props_audio.run_audio),
             ("materials", materials.run), ("assets", assets_level.run_assets), ("level", assets_level.run_level)]
    for name, fn in table:
        if name not in steps:
            continue
        t1 = time.time()
        try:
            fn(ctx)
            C.log("STEP_OK %s %.1fs" % (name, time.time() - t1))
        except Exception:
            failed.append(name)
            C.log("STEP_FAILED %s\n%s" % (name, traceback.format_exc()))
    C.log("SUMMARY failed=%s total=%.1fs" % (failed, time.time() - t0))
    if failed:
        raise RuntimeError("import steps failed: %s" % failed)


main()
