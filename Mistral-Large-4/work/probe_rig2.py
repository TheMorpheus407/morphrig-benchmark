import bpy, json, sys, math
sys.path.insert(0, "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/tools")
import rig_ops
from mathutils import Vector

BLEND = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative_rig.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)

out = {}

A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]
out["object_transforms"] = {
    o.name: {"loc": list(o.location), "rot": list(o.rotation_euler),
             "scale": list(o.scale)}
    for o in (A, C, M)}

sk = M.data.shape_keys
out["shape_keys"] = [kb.name for kb in sk.key_blocks]

# rest world matrices of deformation bones (armature space == world if identity)
def wm(pb):
    return pb.matrix.copy()

rest = {}
for pb in A.pose.bones:
    rest[pb.name] = wm(pb)
out["n_pose_bones"] = len(A.pose.bones)
out["n_ctrl_bones"] = len(C.pose.bones)
out["ctrl_bone_names"] = sorted(pb.name for pb in C.pose.bones)
out["def_bone_names"] = sorted(pb.name for pb in A.pose.bones)

def pos(name):
    return list(rest[name].to_translation())

# key landmarks
land = ["root", "pelvis", "spine_01", "spine_02", "spine_03",
        "neck_01", "neck_02", "head", "jaw",
        "clavicle_L", "clavicle_R", "upper_arm_L", "upper_arm_R",
        "forearm_L", "forearm_R", "hand_L", "hand_R",
        "thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R",
        "toe_L", "toe_R", "emitter", "blade", "cell_new", "cell_spent",
        "beacon", "cable_01", "cable_02", "cable_03"]
out["landmarks"] = {n: pos(n) for n in land if n in rest}

def dist(a, b):
    return (rest[a].to_translation() - rest[b].to_translation()).length

out["lengths"] = {
    "thigh_L": dist("thigh_L", "shin_L"), "shin_L": dist("shin_L", "foot_L"),
    "thigh_R": dist("thigh_R", "shin_R"), "shin_R": dist("shin_R", "foot_R"),
    "upper_arm_L": dist("upper_arm_L", "forearm_L"),
    "forearm_L": dist("forearm_L", "hand_L"),
    "upper_arm_R": dist("upper_arm_R", "forearm_R"),
    "forearm_R": dist("forearm_R", "hand_R"),
    "foot_L": dist("foot_L", "toe_L"), "foot_R": dist("foot_R", "toe_R"),
    "spine": dist("pelvis", "spine_03"),
    "neck_head": dist("neck_01", "head"),
    "pelvis_hip_L": dist("pelvis", "thigh_L"), "pelvis_hip_R": dist("pelvis", "thigh_R"),
    "shoulder_L": dist("spine_03", "upper_arm_L"),
    "shoulder_R": dist("spine_03", "upper_arm_R"),
}

# side check: which hand is +X
out["hand_L_x"] = pos("hand_L")[0]
out["hand_R_x"] = pos("hand_R")[0]
out["foot_L_x"] = pos("foot_L")[0]
out["foot_R_x"] = pos("foot_R")[0]
out["head_fwd"] = list((rest["head"].to_3x3() @ Vector((0, -1, 0))))
out["head_up"] = list((rest["head"].to_3x3() @ Vector((0, 0, 1))))

# foot bone axes: heel at +Y behind ankle?
out["toe_rel_foot_L"] = list((rest["foot_L"].to_3x3().inverted() @ rest["toe_L"].to_translation()) - rest["foot_L"].to_translation())
out["toe_rel_foot_R"] = list((rest["foot_R"].to_3x3().inverted() @ rest["toe_R"].to_translation()) - rest["foot_R"].to_translation())

# control rest positions
crest = {pb.name: list(pb.matrix.to_translation()) for pb in C.pose.bones}
out["ctrl_rest"] = crest

# sockets
out["sockets"] = {}
for e in bpy.data.objects:
    if e.type == 'EMPTY' and e.parent is not None and e.parent.name == "Armature":
        out["sockets"][e.name] = {
            "parent_bone": e.parent_bone,
            "world": list(e.matrix_world.to_translation()),
        }

# actions present?
out["actions"] = [a.name for a in bpy.data.actions]

# ---- tongue fix verification
rig_ops.reset_pose()
C["tongue"] = 1.0
C["jaw_open"] = 0.5
rig_ops.apply_controls()
kb = M.data.shape_keys.key_blocks.get("tongue_out")
out["tongue_test"] = None if kb is None else kb.value
out["jaw_test_bone_z"] = (A.pose.bones["jaw"].matrix.to_3x3() @ Vector((0, 0, 1))).z
rig_ops.reset_pose()

# ---- prop bone parenting (are they children of deformation bones?)
out["prop_parents"] = {n: (A.pose.bones[n].bone.parent.name if A.pose.bones[n].bone.parent else None)
                       for n in ("emitter", "blade", "cell_new", "cell_spent", "beacon")}

# vertex groups count + max weights per vertex
vg = len(M.vertex_groups)
out["vertex_groups"] = vg
maxw = 0
for v in M.data.vertices:
    ws = sorted((g.weight for g in v.groups), reverse=True)[:3]
    maxw = max(maxw, len([w for w in ws if w > 1e-6]))
out["max_influences_nonzero"] = maxw

# mesh bounds
zs = [v.co.z for v in M.data.vertices]
ys = [v.co.y for v in M.data.vertices]
xs = [v.co.x for v in M.data.vertices]
out["mesh_bounds"] = {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)], "z": [min(zs), max(zs)]}
out["n_tris"] = len(M.data.polygons)
out["n_verts"] = len(M.data.vertices)

# scene
sc = bpy.context.scene
out["scene"] = {"fps": sc.render.fps, "frame_start": sc.frame_start,
                "frame_end": sc.frame_end, "unit_scale": sc.unit_settings.scale_length}

with open("/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/work/rig_measure.json", "w") as f:
    json.dump(out, f, indent=1)
print("PROBE_DONE")
print(json.dumps({k: out[k] for k in ("shape_keys", "tongue_test", "hand_L_x", "hand_R_x",
                                      "n_tris", "n_verts", "vertex_groups", "max_influences_nonzero",
                                      "scene", "actions", "n_pose_bones", "n_ctrl_bones")}, indent=1))
print("lengths:", json.dumps(out["lengths"], indent=1))
print("landmarks:", json.dumps(out["landmarks"], indent=1))
