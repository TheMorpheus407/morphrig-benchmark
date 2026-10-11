import bpy, json
from mathutils import Matrix

A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]

def m2l(m):
    return [[round(c, 6) for c in row] for row in m]

def dump_arm(arm, label):
    out = {}
    for pb in arm.pose.bones:
        b = pb.bone
        out[b.name] = {
            "parent": b.parent.name if b.parent else None,
            "rest_world": m2l(b.matrix_local),
            "head": [round(v, 5) for v in b.head_local],
            "tail": [round(v, 5) for v in b.tail_local],
            "length": round(b.length, 5),
        }
    print(label, json.dumps(out))
    return out

d = dump_arm(A, "DEFORM")
c = dump_arm(C, "CTRL")

# mapping pairs used by apply_controls: control -> deform bone it drives
pairs = [("ctrl_root","root"),("ctrl_pelvis","pelvis"),("ctrl_chest","spine_02"),
         ("fk_clavicle_L","clavicle_L"),("fk_clavicle_R","clavicle_R"),
         ("fk_upper_arm_L","upper_arm_L"),("fk_upper_arm_R","upper_arm_R"),
         ("fk_forearm_L","forearm_L"),("fk_forearm_R","forearm_R"),
         ("fk_hand_L","hand_L"),("fk_hand_R","hand_R"),
         ("fk_thigh_L","thigh_L"),("fk_thigh_R","thigh_R"),
         ("fk_shin_L","shin_L"),("fk_shin_R","shin_R"),
         ("fk_foot_L","foot_L"),("fk_foot_R","foot_R"),
         ("fk_toe_L","toe_L"),("fk_toe_R","toe_R")]
print("PAIRCHECK")
for cn, dn in pairs:
    cw = Matrix(c[cn]["rest_world"]); dw = Matrix(d[dn]["rest_world"])
    err = max(abs(a-b) for ra, rb in zip(cw, dw) for a, b in zip(ra, rb))
    print(f"{cn:18s} -> {dn:14s} rest_world_err={err:.2e}  ctrl_parent={c[cn]['parent']}")
# prop bones parents
print("PROP_PARENTS")
for n in ("emitter","blade","cell_new","cell_spent","beacon","cable_01","cable_02","cable_03"):
    print(n, "parent=", d[n]["parent"], "head=", d[n]["head"], "rest_world_t=", [round(r[3],4) for r in d[n]["rest_world"]])
# key rest frames
print("RESTFRAMES")
for n in ("root","pelvis","spine_02","spine_03","neck_01","head","clavicle_L","upper_arm_L","forearm_L","hand_L","hand_R",
          "thigh_L","shin_L","foot_L","toe_L","emitter","blade","cell_new","cell_spent","beacon","jaw","eye_L"):
    M = Matrix(d[n]["rest_world"])
    print(n, "X=", [round(v,3) for v in M.col[0]], "Y=", [round(v,3) for v in M.col[1]], "Z=", [round(v,3) for v in M.col[2]], "t=", [round(v,4) for v in M.row[3][:3]] if False else [round(M.row[0][3],4), round(M.row[1][3],4), round(M.row[2][3],4)])
