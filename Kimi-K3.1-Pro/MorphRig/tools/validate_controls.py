"""Exercise the delivered animator commands without changing the saved .blend."""
from pathlib import Path
import sys
import json
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source" / "generators"))
import rig_controls
rig_controls.register()
results = []
for label, call in [
    ("reset", lambda: bpy.ops.operative.reset_pose()),
    ("clip_selection", lambda: bpy.ops.operative.select_clip()),
    ("match_ik", lambda: bpy.ops.operative.match_ik()),
    ("match_fk", lambda: bpy.ops.operative.match_fk()),
    ("finger_curl_spread", lambda: bpy.ops.operative.apply_fingers()),
    ("heel_toe_roll", lambda: bpy.ops.operative.apply_foot_roll()),
    ("facial_preset", lambda: bpy.ops.operative.expression(preset="joy")),
    ("range_rebake", lambda: bpy.ops.operative.bake_range()),
]:
    try:
        value = call()
        passed = 'FINISHED' in value
        error = "" if passed else repr(value)
    except Exception as exception:
        passed, error = False, str(exception)
    results.append({"operator": label, "passed": passed, "error": error})
bpy.context.scene["operative_clip"] = "idle_relaxed"
bpy.context.scene.frame_start = 0
bpy.context.scene.frame_end = 2
try:
    value = bpy.ops.operative.bake_range()
    results.append({"operator": "three_frame_range_rebake", "passed": 'FINISHED' in value, "error": ""})
except Exception as exception:
    results.append({"operator": "three_frame_range_rebake", "passed": False, "error": str(exception)})
result = {"status": "PASS" if all(item["passed"] for item in results) else "FAIL", "operators": results}
(ROOT / "docs" / "validation" / "blender_controls.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result), flush=True)
if result["status"] != "PASS":
    raise RuntimeError("Blender animator command validation failed")
