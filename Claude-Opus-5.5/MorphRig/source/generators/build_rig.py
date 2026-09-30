"""Stage C1: add the animator control rig (MR_Rig) and hook the export skeleton to it.

Usage:
  blender -b --factory-startup -P build_rig.py -- --in stageB.blend --out stageC.blend
"""
import sys
import os
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import bpy
from mathutils import Matrix, Vector
import mr_rig
import mr_skeleton
import mr_hand
import mr_face_list
from mr_params import J, H, FOOT_DIR_L, nrm, v


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def mat_from_axes(origin, y_axis, z_hint):
    y = nrm(y_axis)
    z = nrm(z_hint - np.dot(z_hint, y) * y)
    x = np.cross(y, z)
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = x[i], y[i], z[i], origin[i]
    return M


def landmarks(skel):
    ex = {}
    ex["torso"] = v(0, 0.02, 0.99)
    for s, sg in (("l", 1.0), ("r", -1.0)):
        fd = FOOT_DIR_L.copy()
        fd[0] *= sg
        ex[f"foot_dir_{s}"] = fd
        ex[f"heel_{s}"] = J[f"heel_{s}"].copy()
        te = J[f"toe_end_{s}"].copy()
        te[2] = 0.0
        ex[f"toe_tip_{s}"] = te
        ex[f"knee_pole_{s}"] = J[f"calf_{s}"] + v(0, -0.45, 0)
        ex[f"elbow_pole_{s}"] = J[f"lowerarm_{s}"] + v(0, 0.40, 0)
        Rl, _ = mr_hand.hand_frame("l")
        back = -Rl[:, 2].copy()
        if s == "r":
            back[0] *= -1
        ex[f"hand_back_{s}"] = back
    ex["look"] = v(0, -1.50, H["eye_l"][2])
    ex["face"] = v(0.10, -0.09, 1.62)
    ex["face_props"] = mr_face_list.FACE_PROPS
    # prop grips (prop matrix expressed in the left hand bone space)
    hand_rest = skel.data.bones["hand_l"].matrix_local.copy()
    Rl, _ = mr_hand.hand_frame("l")
    palm_n = Rl[:, 2]
    thumb = Rl[:, 1]
    fingers = Rl[:, 0]
    socks = {n: p for n, b, p, d in mr_skeleton.socket_list()}
    grip = socks["hand_l_grip"]
    cell_world = mat_from_axes(grip + palm_n * 0.004 + fingers * 0.004, thumb, -palm_n)
    ex["cell_grip"] = hand_rest.inverted() @ cell_world
    # beacon: dome (bone Z) toward the palm (palm faces the dome), bone Y along the fingers
    bea_world = mat_from_axes(grip + palm_n * 0.010, fingers, -palm_n)
    ex["beacon_grip"] = hand_rest.inverted() @ bea_world
    return ex


def verify_rest(skel, rig, tol=1e-4):
    bpy.context.view_layer.update()
    errs = []
    for pb in skel.pose.bones:
        d = (pb.matrix - pb.bone.matrix_local)
        err = max(abs(d[i][j]) for i in range(4) for j in range(4))
        errs.append((err, pb.name))
    errs.sort(reverse=True)
    print("REST_CHECK worst", [(round(e, 5), n) for e, n in errs[:6]])
    return errs[0][0] < tol


def add_shape_drivers(rig):
    """Head shape keys follow the c_face properties (1:1); eyeSquint also follows squint_*."""
    head = bpy.data.objects["MR_Head"]
    keys = head.data.shape_keys
    n = 0
    for kb in keys.key_blocks[1:]:
        fc = kb.driver_add("value")
        drv = fc.driver
        drv.type = 'SCRIPTED'
        var = drv.variables.new()
        var.name = "p"
        var.targets[0].id = rig
        var.targets[0].data_path = f'pose.bones["c_face"]["{kb.name}"]'
        if kb.name.startswith("eyeSquint_"):
            side = kb.name[-1]
            v2 = drv.variables.new()
            v2.name = "q"
            v2.targets[0].id = rig
            v2.targets[0].data_path = f'pose.bones["c_face"]["squint_{side}"]'
            drv.expression = "min(p + 0.6*q, 1.0)"
        else:
            drv.expression = "p"
        n += 1
    print("SHAPE_DRIVERS", n)


def main():
    args = parse()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.inp))
    skel = bpy.data.objects["MR_Skeleton"]
    bl = mr_skeleton.build_bone_list()
    ex = landmarks(skel)
    rig = mr_rig.build_rig(skel, bl, ex)
    add_shape_drivers(rig)
    ok = verify_rest(skel, rig)
    # simple expression check for drivers (must not need Python auto-exec)
    bad = []
    for fc in rig.animation_data.drivers:
        if not fc.driver.is_simple_expression:
            bad.append(fc.data_path)
    print("DRIVERS", len(rig.animation_data.drivers), "non-simple", bad[:5])
    # animator tools (reset pose, IK/FK pose matching, bake) embedded as a registered text block
    ui = os.path.join(os.path.dirname(HERE), "..", "tools", "morphrig_rig_ui.py")
    txt = bpy.data.texts.get("morphrig_rig_ui.py") or bpy.data.texts.new("morphrig_rig_ui.py")
    txt.from_string(open(os.path.abspath(ui)).read())
    txt.use_module = True
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("SAVED", args.out, "rest_ok", ok)


if __name__ == "__main__":
    main()
