from pathlib import Path
import sys
import bpy
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source" / "generators"))
import animate
from character import skeleton_spec
spec = skeleton_spec()
animate.SPEC = spec
rig = bpy.data.objects["Operative_DEF"]
animate.REST = {item["name"]: rig.data.bones[item["name"]] for item in spec}
animate.PARENT = {item["name"]: item["parent"] for item in spec}
animate.ORDER = [item["name"] for item in spec]
animate.REST_LOCAL = {name: (animate.REST[animate.PARENT[name]].matrix_local.inverted() @ animate.REST[name].matrix_local if animate.PARENT[name] else animate.REST[name].matrix_local.copy()) for name in animate.ORDER}
alignment = json.loads((ROOT / "source" / "audio" / "dialogue_alignment.json").read_text())
for label, p in (("support", animate.kneel_pose(True)), ("frame58", animate.sample_pose("getup_back", 58 / 90, 90, alignment))):
    before = animate.world_transforms(p)
    print(label, "before", list(before["upperarm.R"].translation), "clavicle", [list(row) for row in before["clavicle.R"]], "rot", {name: list(value) for name, value in p.rot.items()}, "local", {name: list(value) for name, value in p.local.items() if "clavicle" in name})
    result = animate.apply_contacts(p)
    world = animate.world_transforms(result)
    print(label, "target", list(p.arm_targets["R"]), "shoulder", list(world["upperarm.R"].translation), "elbow", list(world["forearm.R"].translation), "wrist", list(world["hand.R"].translation), "spine", {name: list(world[name].translation) for name in ("pelvis", "spine_01", "spine_02", "spine_03", "neck", "clavicle.R")})
for name in ("upperarm.R", "forearm.R"):
    item = next(item for item in spec if item["name"] == name)
    print(name, "length", (animate.V(item["tail"]) - animate.V(item["head"])).length)
