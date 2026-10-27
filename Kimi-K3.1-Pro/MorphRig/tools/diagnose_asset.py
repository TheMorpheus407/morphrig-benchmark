from pathlib import Path
import bpy
import json

ROOT = Path(__file__).resolve().parents[1]
result = {}
depsgraph = bpy.context.evaluated_depsgraph_get()
for name in ("Operative_CTRL", "Operative_DEF"):
    obj = bpy.data.objects[name]
    record = {"action": str(obj.animation_data.action), "slot": str(obj.animation_data.action_slot), "bones": {}}
    for bone_name in ("root", "pelvis", "spine_01", "spine_03", "head"):
        bone = obj.pose.bones[bone_name]
        record["bones"][bone_name] = {
            "head": list(bone.head), "tail": list(bone.tail),
            "matrix": [list(row) for row in bone.matrix],
            "basis": [list(row) for row in bone.matrix_basis],
            "constraints": [(c.name, c.influence) for c in bone.constraints],
        }
    result[name] = record
for name in ("Operative_Body_LOD0", "Operative_Face", "Operative_Props"):
    obj = bpy.data.objects[name]
    result[name] = {"bounds": [list(v) for v in obj.evaluated_get(depsgraph).bound_box], "visible": not obj.hide_render}
print(json.dumps(result, indent=2))
(ROOT / "docs" / "validation" / "control_pose_diagnosis.json").write_text(json.dumps(result, indent=2) + "\n")
