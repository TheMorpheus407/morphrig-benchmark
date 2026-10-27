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
p = animate.apply_contacts(animate.sample_pose("idle_relaxed", 0, 90, alignment))
world = animate.world_transforms(p)
out = {"pose": {"pelvis": list(p.pelvis), "absolute": {key: list(value) for key, value in p.absolute.items()}, "rot": {key: list(value) for key, value in p.rot.items()}}, "rest": {}}
for name in ("root", "pelvis", "spine_01", "head"):
    bone = rig.data.bones[name]
    parent = bone.parent.name if bone.parent else None
    relative = world[parent].inverted() @ world[name] if parent else world[name]
    basis = animate.REST_LOCAL[name].inverted() @ relative
    out["rest"][name] = {"spec_head": list(next(item["head"] for item in spec if item["name"] == name)), "bone_head": list(bone.head), "head_local": list(bone.head_local), "matrix_local": [list(row) for row in bone.matrix_local], "rest_local": [list(row) for row in animate.REST_LOCAL[name]], "world": [list(row) for row in world[name]], "basis": [list(row) for row in basis]}
print(json.dumps(out, indent=2))
(ROOT / "docs" / "validation" / "pose_conversion.json").write_text(json.dumps(out, indent=2) + "\n")
