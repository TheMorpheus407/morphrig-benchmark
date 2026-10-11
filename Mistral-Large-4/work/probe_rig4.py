import bpy, json, sys, math
sys.path.insert(0, "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/tools")
import rig_ops
from mathutils import Vector, Matrix

BLEND = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative_rig.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
out = {}
A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]

out["def_parents"] = {pb.name: (pb.bone.parent.name if pb.bone.parent else None)
                      for pb in A.pose.bones}

# ---- rest-pose deviation: reset + apply, compare pose matrix to bone rest
rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()
dev = {}
for pb in A.pose.bones:
    R = pb.matrix
    B = pb.bone.matrix_local
    dpos = (R.to_translation() - B.to_translation()).length
    q = R.to_3x3().to_quaternion().rotation_difference(B.to_3x3().to_quaternion())
    ang = abs(q.angle)
    if dpos > 1e-5 or ang > 1e-4:
        dev[pb.name] = {"dpos": round(dpos, 6), "angle_deg": round(math.degrees(ang), 4)}
out["rest_pose_deviation"] = dev
out["rest_pose_clean"] = len(dev) == 0

# ---- control rest vs deformation rest rotation angles (FK chains)
ang = {}
for side in ("L", "R"):
    for d, c in (("upper_arm", "fk_upper_arm"), ("forearm", "fk_forearm"), ("hand", "fk_hand"),
                 ("thigh", "fk_thigh"), ("shin", "fk_shin"), ("foot", "fk_foot"), ("toe", "fk_toe")):
        dn = f"{d}_{side}"; cn = f"{c}_{side}"
        dM = A.pose.bones[dn].bone.matrix_local.to_3x3()
        cM = C.pose.bones[cn].bone.matrix_local.to_3x3()
        q = dM.to_quaternion().rotation_difference(cM.to_quaternion())
        ang[dn] = round(math.degrees(abs(q.angle)), 3)
out["ctrl_vs_def_rest_angle_deg"] = ang

# ---- sockets: full matrices + evaluated world
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
sock = {}
for e in bpy.data.objects:
    if e.type == 'EMPTY' and e.parent is not None and e.parent.name == "Armature":
        ev = e.evaluated_get(dg)
        sock[e.name] = {
            "parent_bone": e.parent_bone,
            "world": list(e.matrix_world.to_translation()),
            "world_eval": list(ev.matrix_world.to_translation()),
            "basis": [list(r) for r in e.matrix_basis],
            "parent_inverse": [list(r) for r in e.matrix_parent_inverse],
        }
out["sockets"] = sock

# ---- key bone rest matrices (full) for authoring
rest_full = {}
for n in ("head", "jaw", "eye_L", "eye_R", "lid_upper_L", "brow_L", "emitter", "blade",
          "cell_new", "cell_spent", "beacon", "hand_L", "hand_R", "foot_L", "toe_L",
          "upper_arm_L", "forearm_L", "thigh_L", "shin_L", "root", "pelvis", "spine_03"):
    rest_full[n] = {"pos": list(A.pose.bones[n].bone.matrix_local.to_translation()),
                    "mat": [list(r) for r in A.pose.bones[n].bone.matrix_local]}
out["rest_full"] = rest_full

# ---- prop bone chains
out["prop_chain"] = {n: (A.pose.bones[n].bone.parent.name if A.pose.bones[n].bone.parent else None)
                     for n in ("emitter", "blade", "cell_new", "cell_spent", "beacon",
                               "cable_01", "cable_02", "cable_03")}

with open("/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/work/rig_measure4.json", "w") as f:
    json.dump(out, f, indent=1)
print("PROBE4_DONE")
print("rest_pose_clean:", out["rest_pose_clean"])
print("rest_pose_deviation:", json.dumps(dev, indent=0))
print("ctrl_vs_def_rest_angle_deg:", json.dumps(ang, indent=0))
print("def_parents:", json.dumps(out["def_parents"], indent=0))
print("prop_chain:", json.dumps(out["prop_chain"], indent=0))
for n, s in sock.items():
    print("socket %-18s bone=%-10s world=%s eval=%s" % (n, s["parent_bone"],
          [round(v, 3) for v in s["world"]], [round(v, 3) for v in s["world_eval"]]))
