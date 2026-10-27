from pathlib import Path
import bpy
import json

ROOT = Path(__file__).resolve().parents[1]
rig = bpy.data.objects["Operative_DEF"]
ctrl = bpy.data.objects["Operative_CTRL"]
ctrl.animation_data.action = None
for bone in rig.pose.bones:
    for constraint in bone.constraints:
        constraint.influence = 0.0
result = []
for name in ("idle_relaxed", "walk_l", "run_fr", "jump_air", "death_back", "aim_up_right"):
    action = bpy.data.actions[name]
    slots = [{"handle": slot.handle, "identifier": slot.identifier, "target_id_type": slot.target_id_type} for slot in action.slots]
    rig.animation_data.action = action
    for mode in ("automatic", "explicit"):
        if mode == "explicit":
            for slot in action.slots:
                if slot.identifier == rig.name or slot.identifier == "OB" + rig.name:
                    rig.animation_data.action_slot = slot
        bpy.context.scene.frame_set(0)
        bpy.context.view_layer.update()
        result.append({"clip": name, "mode": mode, "selected_slot": str(rig.animation_data.action_slot), "slots": slots, "pelvis": list(rig.pose.bones["pelvis"].head), "head": list(rig.pose.bones["head"].head), "root": list(rig.pose.bones["root"].head)})
print(json.dumps(result, indent=2))
(ROOT / "docs" / "validation" / "action_slots.json").write_text(json.dumps(result, indent=2) + "\n")
