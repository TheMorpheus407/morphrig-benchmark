"""Measure saved Blender prop and hand transforms without changing the asset."""
from pathlib import Path
import json
import bpy

ROOT = Path(__file__).resolve().parents[1]
rig = bpy.data.objects["Operative_DEF"]
rig.animation_data_create()
for bone in rig.pose.bones:
    for constraint in bone.constraints:
        constraint.influence = 0.0
records = {}
for clip, frames in (("reload", (0, 15, 26, 34, 46, 53, 60)), ("deploy", (0, 8, 16, 30, 35, 44, 48))):
    action = bpy.data.actions[clip]
    rig.animation_data.action = action
    rig.animation_data.action_slot = action.slots[0]
    rows = []
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        bones = {}
        for name in ("root", "pelvis", "hand.L", "hand.R", "cell", "beacon"):
            bone = rig.pose.bones[name]
            bones[name] = {
                "component_m": list(bone.matrix.translation),
                "basis_location_m": list(bone.matrix_basis.translation),
                "basis_quaternion": list(bone.matrix_basis.to_quaternion()),
            }
        rows.append({"frame": frame, "bones": bones})
    records[clip] = rows
weights = {}
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for group in obj.vertex_groups:
        if group.name in ("cell", "beacon"):
            weights[obj.name + ":" + group.name] = sum(any(g.group == group.index and g.weight > 0 for g in v.groups) for v in obj.data.vertices)
result = {"clips": records, "weighted_vertices": weights}
(ROOT / "docs" / "validation" / "source_prop_motion.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2), flush=True)
