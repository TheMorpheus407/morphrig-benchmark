"""MorphRig deformation skeleton definition (export skeleton).

Bone axes: Y along the bone (Blender convention).  Z is aligned with the
'roll' reference given per bone so that primary flexion is a rotation about
the local X axis for limbs, spine and fingers.
"""
import numpy as np
from mr_params import J, H, EYE_R, nrm, v, mirror
import mr_hand

FWD = v(0, -1, 0)   # character forward in Blender space
UP = v(0, 0, 1)


def _bone(name, head, tail, parent, zref, deform=True, connect=False):
    return dict(name=name, head=np.asarray(head, float), tail=np.asarray(tail, float),
                parent=parent, zref=np.asarray(zref, float), deform=deform, connect=connect)


def build_bone_list():
    B = []
    B.append(_bone("root", v(0, 0, 0), v(0, -0.25, 0), None, UP))
    B.append(_bone("pelvis", J["pelvis"], J["spine_01"], "root", FWD))
    B.append(_bone("spine_01", J["spine_01"], J["spine_02"], "pelvis", FWD))
    B.append(_bone("spine_02", J["spine_02"], J["spine_03"], "spine_01", FWD))
    B.append(_bone("spine_03", J["spine_03"], J["neck_01"], "spine_02", FWD))
    B.append(_bone("neck_01", J["neck_01"], J["neck_02"], "spine_03", FWD))
    B.append(_bone("neck_02", J["neck_02"], J["head"], "neck_01", FWD))
    B.append(_bone("head", J["head"], J["head_end"], "neck_02", FWD))
    # face
    for s in ("l", "r"):
        c = H["eye_" + s]
        B.append(_bone("eye_" + s, c, c + v(0, -0.022, 0), "head", UP))
        B.append(_bone("lid_upper_" + s, c, c + v(0, -0.018, 0.004), "head", UP))
        B.append(_bone("lid_lower_" + s, c, c + v(0, -0.018, -0.004), "head", UP))
    jaw_head = H["jaw"]
    chin = v(0, -0.074, 1.566)
    B.append(_bone("jaw", jaw_head, chin, "head", v(0, -0.3, -1)))
    # tongue from the back of the mouth to the tip, just above the lower teeth
    t0 = v(0, -0.030, 1.590)
    t1 = v(0, -0.050, 1.594)
    t2 = v(0, -0.066, 1.597)
    t3 = v(0, -0.080, 1.599)
    B.append(_bone("tongue_01", t0, t1, "jaw", UP))
    B.append(_bone("tongue_02", t1, t2, "tongue_01", UP))
    B.append(_bone("tongue_03", t2, t3, "tongue_02", UP))
    # hair tail (secondary motion chain), gathered at the back of the head
    hp = [v(0, 0.098, 1.730), v(0, 0.124, 1.700), v(0, 0.136, 1.660), v(0, 0.140, 1.620), v(0, 0.140, 1.585)]
    parent = "head"
    for k in range(4):
        nm = f"hair_tail_{k + 1:02d}"
        B.append(_bone(nm, hp[k], hp[k + 1], parent, v(0, 1, 0)))
        parent = nm
    # arms
    for s in ("l", "r"):
        sg = 1.0 if s == "l" else -1.0
        S, E, W = J["upperarm_" + s], J["lowerarm_" + s], J["hand_" + s]
        B.append(_bone("clavicle_" + s, J["clavicle_" + s], S, "spine_03", UP))
        # arm roll reference: forward projected (flexion about local X)
        B.append(_bone("upperarm_" + s, S, E, "clavicle_" + s, FWD))
        B.append(_bone("upperarm_twist_01_" + s, S + 0.5 * (E - S), E, "upperarm_" + s, FWD))
        B.append(_bone("lowerarm_" + s, E, W, "upperarm_" + s, FWD))
        B.append(_bone("lowerarm_twist_01_" + s, E + 0.6 * (W - E), W, "lowerarm_" + s, FWD))
        hj = mr_hand.hand_joints_world(s)
        mid_mcp = hj["middle_01"][0]
        # hand: Z toward the back of the hand
        Rl, _ = mr_hand.hand_frame("l")
        back = -Rl[:, 2].copy()
        if s == "r":
            back[0] *= -1
        B.append(_bone("hand_" + s, W, mid_mcp, "lowerarm_" + s, back))
        for f in mr_hand.FINGERS:
            h, t = hj[f + "_metacarpal"]
            B.append(_bone(f"{f}_metacarpal_{s}", h, t, "hand_" + s, back))
            par = f"{f}_metacarpal_{s}"
            for k in range(3):
                h, t = hj[f"{f}_0{k + 1}"]
                nm = f"{f}_0{k + 1}_{s}"
                B.append(_bone(nm, h, t, par, back))
                par = nm
        par = "hand_" + s
        # thumb roll: Z = thumbnail normal, so -X rotation (the finger 'curl' convention) flexes the
        # thumb toward its pad, i.e. across the palm toward the index/middle fingers
        pad = Rl @ nrm(v(0.0, -0.75, 0.66))        # hand-local: toward the index side + palmar
        thumb_z = -pad
        if s == "r":
            thumb_z[0] *= -1
        for k in range(3):
            h, t = hj[f"thumb_0{k + 1}"]
            nm = f"thumb_0{k + 1}_{s}"
            B.append(_bone(nm, h, t, par, thumb_z))
            par = nm
    # cyber extras (right forearm)
    import mr_gear
    a = mr_gear.cyber_anchor_points()
    piv = a["blade_pivot"]
    B.append(_bone("blade_r", piv, piv + a["blade_axis_fold"] * 0.10, "lowerarm_r", a["top"]))
    cs = a["cell_slot"]
    B.append(_bone("prop_cell", cs, cs + a["cell_axis"] * 0.05, "lowerarm_r", a["top"]))
    # legs
    for s in ("l", "r"):
        Hh, K, A = J["thigh_" + s], J["calf_" + s], J["foot_" + s]
        B.append(_bone("thigh_" + s, Hh, K, "pelvis", FWD))
        B.append(_bone("thigh_twist_01_" + s, Hh + 0.5 * (K - Hh), K, "thigh_" + s, FWD))
        B.append(_bone("calf_" + s, K, A, "thigh_" + s, FWD))
        B.append(_bone("foot_" + s, A, J["ball_" + s], "calf_" + s, UP))
        B.append(_bone("ball_" + s, J["ball_" + s], J["toe_end_" + s], "foot_" + s, UP))
    # beacon prop on the belt holster (back of the belt)
    bc = BEACON_HOLSTER
    B.append(_bone("prop_beacon", bc, bc + v(0, 0, 0.06), "pelvis", v(0, 1, 0)))
    # socket bones (non-deforming): exported with the skeleton so Unreal sockets sit on exact,
    # animated anchors (hand grips, emitter muzzle, cell slot, blade base/tip, effect anchors)
    B += socket_bones()
    return B


SOCKET_PARENT = {"hand_l_grip": "hand_l", "hand_r_grip": "hand_r", "muzzle_r": "lowerarm_r",
                 "cell_slot_r": "lowerarm_r", "blade_base_r": "blade_r", "blade_tip_r": "blade_r",
                 "beacon_holster": "pelvis", "fx_chest": "spine_03", "fx_head": "head", "fx_ground": "root",
                 "fx_palm_l": "hand_l"}


def socket_bones():
    import mr_gear
    a = mr_gear.cyber_anchor_points()
    fire = nrm(J["hand_r"] - J["lowerarm_r"])
    blade_dir = nrm(a["blade_axis_fold"])
    dirs = {"muzzle_r": fire, "cell_slot_r": nrm(a["cell_axis"]), "blade_base_r": blade_dir,
            "blade_tip_r": blade_dir, "fx_ground": v(0, -1, 0), "fx_head": v(0, 0, 1), "fx_chest": v(0, -1, 0)}
    out = []
    for name, bone, pos, _desc in socket_list():
        d = dirs.get(name, v(0, 0, 1) if name.startswith("fx") else nrm(J[bone.replace("hand", "hand")] - J["lowerarm_" + bone[-1]]) if bone.startswith("hand") else v(0, 0, 1))
        zr = v(0, 0, 1) if abs(np.dot(d, v(0, 0, 1))) < 0.9 else v(0, -1, 0)
        out.append(_bone("sock_" + name, pos, pos + d * 0.03, SOCKET_PARENT[name], zr, deform=False))
    return out


BEACON_HOLSTER = v(0.0, 0.122, 0.968)

# UE sockets (bone, world location in rest pose, description)
def socket_list():
    import mr_gear
    a = mr_gear.cyber_anchor_points()
    hj_l = mr_hand.hand_joints_world("l")
    hj_r = mr_hand.hand_joints_world("r")
    grip_l = 0.5 * (hj_l["middle_01"][0] + J["hand_l"]) + mr_hand.hand_frame("l")[0][:, 2] * 0.028
    rl = mr_hand.hand_frame("l")[0][:, 2].copy()
    rr = rl.copy()
    rr[0] *= -1
    grip_r = 0.5 * (hj_r["middle_01"][0] + J["hand_r"]) + rr * 0.028
    return [
        ("hand_l_grip", "hand_l", grip_l, "Left palm grip centre (cell/beacon handling)"),
        ("hand_r_grip", "hand_r", grip_r, "Right (cyber) palm grip centre"),
        ("muzzle_r", "lowerarm_r", a["muzzle"], "Wrist emitter muzzle; +X of socket = fire direction"),
        ("cell_slot_r", "lowerarm_r", a["cell_slot"], "Power cell cradle on the cyber forearm"),
        ("blade_base_r", "blade_r", a["blade_pivot"], "Forearm blade pivot/base"),
        ("blade_tip_r", "blade_r", a["blade_pivot"] + a["blade_axis_fold"] * 0.31, "Forearm blade tip (folded rest pose)"),
        ("beacon_holster", "pelvis", BEACON_HOLSTER, "Beacon holster on the back of the belt"),
        ("fx_chest", "spine_03", v(0, -0.12, 1.33), "Chest effect anchor"),
        ("fx_head", "head", v(0, 0.0, 1.80), "Overhead effect anchor"),
        ("fx_ground", "root", v(0, 0, 0), "Ground effect anchor (casts, blink)"),
        ("fx_palm_l", "hand_l", grip_l + rl * 0.02, "Left palm effect anchor (self cast)"),
    ]
