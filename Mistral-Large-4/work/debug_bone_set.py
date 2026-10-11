"""Empirical probe 5: NONZERO roll deltas + rotated-parent child + real bones.
Determines the working recipe for setting an EditBone's full rest frame in 5.1.
"""
import bpy
import json
import math
import os
import sys
import traceback
from mathutils import Vector, Matrix

TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
GEN = os.path.join(TASK, "source", "generators")
sys.path.insert(0, GEN)
from morphrig_lib import bone_frame, x_hint_for  # noqa: E402

OUT = []


def log(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s, flush=True)


def rv(v, n=6):
    return "(" + ", ".join(("%." + str(n) + "f") % c for c in v[:3]) + ")"


def mat_str(M):
    return "\n".join("    " + " ".join("%9.6f" % M[i][j] for j in range(4))
                     for i in range(4))


def frame_diff(Ma, Mb):
    A3 = Ma.to_3x3()
    B3 = Mb.to_3x3()
    return max(abs(A3[i][j] - B3[i][j]) for i in range(3) for j in range(3))


def make_frame(head, y_raw, x_hint):
    head = Vector(head)
    y_raw = Vector(y_raw)
    y = y_raw.normalized()
    x = Vector(x_hint) if x_hint is not None else Vector((1, 0, 0))
    x = x - y * x.dot(y)
    if x.length < 1e-6:
        x = Vector((0, 0, 1)) - y * y.z
        x = x - y * x.dot(y)
    x.normalize()
    z = x.cross(y)
    return Matrix.Translation(head) @ Matrix((x, y_raw, z)).transposed().to_4x4()


def unit_y(M):
    Mu = M.copy()
    c = Mu.col[1].xyz.normalized()
    Mu.col[1] = Vector((c.x, c.y, c.z, 0.0))
    return Mu


def yraw(M):
    return M.to_3x3().col[1].copy()


def fix_B(eb, Mdes, sign):
    """head/tail + manual roll."""
    eb.head = Mdes.to_translation()
    eb.tail = Mdes.to_translation() + yraw(Mdes)
    R0 = eb.matrix.to_3x3()
    Rdes = Mdes.to_3x3()
    for i in range(3):
        c = Rdes.col[i]
        if c.length > 1e-9:
            Rdes.col[i] = c.normalized()
    D = R0.inverted() @ Rdes
    q = D.to_quaternion()
    eb.roll = sign * 2.0 * math.atan2(q.y, q.w)


def fix_C(eb, Mdes):
    """head/tail first (nonzero length), then unit-Y matrix assign, then tail."""
    eb.head = Mdes.to_translation()
    eb.tail = Mdes.to_translation() + yraw(Mdes)
    eb.matrix = unit_y(Mdes)
    eb.tail = Mdes.to_translation() + yraw(Mdes)


def check_obj(b, Mdes, tag):
    """Compare an OBJECT-mode bone against the desired armature-space frame."""
    head = Mdes.to_translation()
    yr = yraw(Mdes)
    tail = head + yr
    Rdes = Mdes.to_3x3().copy()
    for i in range(3):
        c = Rdes.col[i]
        if c.length > 1e-9:
            Rdes.col[i] = c.normalized()
    d_head = (b.head_local - head).length
    d_tail = (b.tail_local - tail).length
    d_len = abs(b.length - yr.length)
    Ml = b.matrix_local
    d_rot = frame_diff(Ml, Matrix.Translation(head) @ Rdes.to_4x4())
    ok = max(d_head, d_tail, d_len, d_rot) < 1e-6
    log("%s: head %.2e tail %.2e len %.2e rot %.2e -> %s" %
        (tag, d_head, d_tail, d_len, d_rot, "OK" if ok else "FAIL"))
    return ok


try:
    log("BLENDER", bpy.app.version_string)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ad = bpy.data.armatures.new("T")
    A = bpy.data.objects.new("TA", ad)
    bpy.context.scene.collection.objects.link(A)
    bpy.context.view_layer.objects.active = A
    bpy.ops.object.mode_set(mode='EDIT')

    def show(eb, tag):
        M = eb.matrix
        log("%s head %s tail %s len %.6f roll %.6f" %
            (tag, rv(eb.head), rv(eb.tail), eb.length, eb.roll))
        log("%s   col0 %s col1 %s col2 %s" %
            (tag, rv(M.col[0]), rv(M.col[1]), rv(M.col[2])))

    # ------------------------------------------------ R1: +Y bone, nonzero roll
    # desired: X=(0,0,1), Y=(0,1,0), Z=(-1,0,0)  (x_hint (0,0,1))
    M1 = make_frame((0, 0, 0), (0, 1, 0), (0, 0, 1))
    log("R1 desired:\n" + mat_str(M1))
    eb = ad.edit_bones.new("r1_default")
    eb.head = Vector((0, 0, 0))
    eb.tail = Vector((0, 1, 0))
    show(eb, "R1-default-frame")
    for nm, sgn in (("r1_Bp", +1.0), ("r1_Bm", -1.0)):
        e = ad.edit_bones.new(nm)
        fix_B(e, M1, sgn)
        d = frame_diff(e.matrix, M1)
        log("R1 fix_B sign %+.0f framediff %.9f roll %.6f" % (sgn, d, e.roll))
    e = ad.edit_bones.new("r1_C")
    fix_C(e, M1)
    d = frame_diff(e.matrix, M1)
    log("R1 fix_C framediff %.9f roll %.6f" % (d, e.roll))

    # ------------------------------------------------ R2: +X bone (degenerate)
    # desired: X=(0,0,1), Y=(1,0,0), Z=(0,1,0)
    M2 = make_frame((0, 0, 0), (1, 0, 0), (0, 0, 1))
    log("R2 desired:\n" + mat_str(M2))
    eb = ad.edit_bones.new("r2_default")
    eb.head = Vector((0, 0, 0))
    eb.tail = Vector((1, 0, 0))
    show(eb, "R2-default-frame")
    for nm, sgn in (("r2_Bp", +1.0), ("r2_Bm", -1.0)):
        e = ad.edit_bones.new(nm)
        fix_B(e, M2, sgn)
        d = frame_diff(e.matrix, M2)
        log("R2 fix_B sign %+.0f framediff %.9f roll %.6f" % (sgn, d, e.roll))
    e = ad.edit_bones.new("r2_C")
    fix_C(e, M2)
    d = frame_diff(e.matrix, M2)
    log("R2 fix_C framediff %.9f roll %.6f" % (d, e.roll))

    # ------------------------------------------------ R4: rotated parent child
    # parent: head (0,0,0), tail (0,0,1), x_hint (0,1,0) -> frame X=(0,1,0) Y=(0,0,1) Z=(1,0,0)?
    Mp = make_frame((0, 0, 0), (0, 0, 1), (0, 1, 0))
    ebp = ad.edit_bones.new("r4_parent")
    fix_C(ebp, Mp)
    show(ebp, "R4-parent")
    # child desired (armature space): head (0.2,0.1,0.5), y_raw (0,0.3,0.1), hint (1,0,0)
    M4 = make_frame((0.2, 0.1, 0.5), (0.0, 0.3, 0.1), (1, 0, 0))
    # also a child with NONZERO roll delta vs its default frame
    M4b = make_frame((0.2, 0.1, 0.5), (0.0, 0.3, 0.1), (0, 0, 1))
    for nm, Md in (("r4_child_C", M4), ("r4_childroll_C", M4b)):
        e = ad.edit_bones.new(nm)
        e.parent = ebp
        fix_C(e, Md)
        show(e, nm)
    e = ad.edit_bones.new("r4_child_B")
    e.parent = ebp
    fix_B(e, M4b, +1.0)
    e = ad.edit_bones.new("r4_child_Bm")
    e.parent = ebp
    fix_B(e, M4b, -1.0)

    # ------------------------------------------------ R5: real rig bones
    SPEC = json.load(open(os.path.join(TASK, "work", "rig_spec.json")))
    BONES = {b["name"]: b for b in SPEC["bones"]}
    order = [b["name"] for b in SPEC["bones"]]
    parent_of = {b["name"]: b["parent"] for b in SPEC["bones"]}
    ebs = {}
    for nm in order:
        b = BONES[nm]
        e = ad.edit_bones.new("x_" + nm)
        hint = x_hint_for(nm, b["head"], b["tail"])
        ebs[nm] = (e, bone_frame(b["head"], b["tail"], hint))
    for nm in order:
        p = parent_of[nm]
        if p:
            ebs[nm][0].parent = ebs[p][0]
    for nm in order:
        e, Md = ebs[nm]
        fix_C(e, Md)

    bpy.ops.object.mode_set(mode='OBJECT')
    log("=== OBJECT MODE ground truth ===")
    check_obj(ad.bones["r1_C"], M1, "R1 fix_C")
    check_obj(ad.bones["r1_Bp"], M1, "R1 fix_B +1")
    check_obj(ad.bones["r1_Bm"], M1, "R1 fix_B -1")
    check_obj(ad.bones["r2_C"], M2, "R2 fix_C")
    check_obj(ad.bones["r2_Bp"], M2, "R2 fix_B +1")
    check_obj(ad.bones["r2_Bm"], M2, "R2 fix_B -1")
    check_obj(ad.bones["r4_parent"], Mp, "R4 parent")
    check_obj(ad.bones["r4_child_C"], M4, "R4 child fix_C")
    check_obj(ad.bones["r4_childroll_C"], M4b, "R4 childroll fix_C")
    check_obj(ad.bones["r4_child_B"], M4b, "R4 childroll fix_B +1")
    check_obj(ad.bones["r4_child_Bm"], M4b, "R4 childroll fix_B -1")
    n_ok = 0
    n_bad = []
    for nm in order:
        b = ad.bones["x_" + nm]
        if check_obj(b, ebs[nm][1], "bone " + nm):
            n_ok += 1
        else:
            n_bad.append(nm)
    log("REAL BONES fix_C: %d/%d OK, bad=%s" % (n_ok, len(order), n_bad))
    log("DEBUG_DONE")
except Exception:
    log("FATAL", traceback.format_exc())
finally:
    with open(TASK + "/work/debug_bone_set_out.txt", "w") as f:
        f.write("\n".join(OUT))
