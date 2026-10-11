import bpy, math, sys
from mathutils import Vector, Matrix

TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
BLEND = TASK + "/source/Operative_rig.blend"
sys.path.insert(0, TASK + "/tools")
import rig_ops

bpy.ops.wm.open_mainfile(filepath=BLEND)
A = bpy.data.objects["Armature"]
ad = A.data
sc = bpy.context.scene


def unitY(M):
    R = M.to_3x3().copy()
    for i in range(3):
        c = R.col[i]
        if c.length > 1e-9:
            R.col[i] = c / c.length
    return R


def measure_P(bone_name):
    e = bpy.data.objects.new("tmp_P", None)
    sc.collection.objects.link(e)
    e.parent = A
    e.parent_type = 'BONE'
    e.parent_bone = bone_name
    e.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    P = e.matrix_world.copy()
    bpy.data.objects.remove(e)
    return P


def show(M):
    return "[" + " | ".join(" ".join("% .4f" % M[i][j] for j in range(4)) for i in range(3)) + "]"


for bn in ("head", "emitter", "hand_R", "spine_03", "neck_01"):
    bone = ad.bones[bn]
    arm = bone.matrix_local
    y_raw = arm.to_3x3().col[1]
    tail = arm.to_translation() + y_raw
    P1 = Matrix.Translation(tail) @ unitY(arm).to_4x4()          # tail @ unitY
    P2 = Matrix.Translation(arm.to_translation()) @ unitY(arm).to_4x4()  # head @ unitY
    P3 = arm.copy()                                              # raw arm_mat
    print("== %s (len %.4f)" % (bn, y_raw.length))
    print("  arm_mat   t=%s" % [round(v, 4) for v in arm.to_translation()])
    print("  P_meas    t=%s" % [round(v, 4) for v in measure_P(bn).to_translation()])
    print("  P1 tail@uY t=%s" % [round(v, 4) for v in P1.to_translation()])
    print("  P2 head@uY t=%s" % [round(v, 4) for v in P2.to_translation()])
    print("  P3 raw    t=%s" % [round(v, 4) for v in P3.to_translation()])
    Pm = measure_P(bn)
    print("  P_meas  R colY=%s colZ=%s" % ([round(v, 4) for v in Pm.to_3x3().col[1]],
                                           [round(v, 4) for v in Pm.to_3x3().col[2]]))
    print("  unitY   R colY=%s colZ=%s" % ([round(v, 4) for v in unitY(arm).col[1]],
                                           [round(v, 4) for v in unitY(arm).col[2]]))
    d1 = max((Pm - P1)[i][j] for i in range(4) for j in range(4))
    d2 = max((Pm - P2)[i][j] for i in range(4) for j in range(4))
    d3 = max((Pm - P3)[i][j] for i in range(4) for j in range(4))
    print("  maxdiff: P1 %.5f  P2 %.5f  P3 %.5f" % (d1, d2, d3))
    pb = A.pose.bones[bn]
    print("  pb.matrix t=%s  (at rest? %s)" % ([round(v, 4) for v in pb.matrix.to_translation()],
          max((pb.matrix - arm)[i][j] for i in range(4) for j in range(4)) < 1e-5))
