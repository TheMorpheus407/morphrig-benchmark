"""MorphRig Operative — animator control-rig operators and panel.

This file is embedded in source/Operative_rig.blend as a Text datablock with
"Register" enabled, so it runs automatically whenever the .blend is opened.
It is deliberately self-contained (no imports from the generator scripts) so
the delivered .blend keeps working on any machine.

Workflow (see docs/rig_usage.md):
  1. Pose the control rig (Operative_Controls): FK chains, IK targets + pole
     vectors, foot roll, finger curl/spread, face controls, look-at target.
  2. Press "Apply Controls to Skeleton" — the deformation skeleton
     (Armature) is driven from the controls (IK/FK blend, look-at, face).
  3. Animate the deformation skeleton directly, or key the controls and
     re-apply; "Match FK to IK" snaps the FK chain onto the current skeleton
     pose when switching IK/FK. "Reset Pose" restores the rest pose.
"""
import bpy
import math
from mathutils import Vector, Matrix, Quaternion

ARM_NAME = "Armature"
CTRL_NAME = "Operative_Controls"
MESH_NAME = "Operative"

# ------------------------------------------------------------------ face data
# Expression presets (SPEC section 7: six readable presets + neutral).
# Values map to control properties / shape keys (see apply_controls).
PRESETS = {
    "neutral":  {},
    "joy":      {"smile_L": 0.9, "smile_R": 0.9, "cheek_L": 0.7, "cheek_R": 0.7,
                 "brow_raise": 0.3, "squint": 0.25, "jaw_open": 0.08, "lip_width": 0.2},
    "anger":    {"frown_L": 0.7, "frown_R": 0.7, "brow_raise": -0.85, "squint": 0.55,
                 "jaw_open": 0.18, "lip_close": 0.4},
    "sadness":  {"frown_L": 0.45, "frown_R": 0.45, "brow_raise": 0.55,
                 "lip_width": -0.35, "jaw_open": 0.06, "squint": -0.2},
    "surprise": {"brow_raise": 1.0, "jaw_open": 0.55, "squint": -0.6, "lip_width": -0.25},
    "pain":     {"squint": 0.85, "frown_L": 0.6, "frown_R": 0.6, "brow_raise": -0.5,
                 "jaw_open": 0.3, "lip_close": 0.85, "lip_width": 0.3},
    "focus":    {"squint": 0.3, "brow_raise": -0.2, "jaw_open": 0.05, "lip_close": 0.5,
                 "smile_L": 0.15, "smile_R": 0.15},
}

# Viseme set for the dialogue performance (documented mapping, SPEC section 7):
# lip-closure (MBP), labiodental (FV), open vowels (AW/IH), wide vowel (EE),
# rounded vowels (OO/UW/R), tongue-to-teeth (L/TH), consonants (KG/SZ).
VISEMES = {
    "REST": {},
    "MBP": {"lip_close": 1.0, "jaw_open": 0.08},
    "FV":  {"lip_close": 0.55, "jaw_open": 0.18},
    "OO":  {"pucker": 1.0, "jaw_open": 0.3},
    "UW":  {"pucker": 0.6, "lip_width": -0.5, "jaw_open": 0.35},
    "AW":  {"jaw_open": 0.95, "lip_width": 0.45},
    "EE":  {"smile_L": 0.85, "smile_R": 0.85, "lip_width": 0.85, "jaw_open": 0.2},
    "IH":  {"lip_width": 0.5, "jaw_open": 0.25},
    "OH":  {"pucker": 0.5, "jaw_open": 0.5},
    "L":   {"tongue": 1.0, "jaw_open": 0.45},
    "TH":  {"tongue": 0.6, "jaw_open": 0.3},
    "KG":  {"jaw_open": 0.15, "lip_width": -0.2},
    "SZ":  {"smile_L": 0.45, "smile_R": 0.45, "jaw_open": 0.15, "lip_close": 0.2},
    "R":   {"pucker": 0.4, "jaw_open": 0.3},
}

# Control property defaults (on the Operative_Controls object).
DEFAULTS = {
    "global_scale": 1.0,
    "secondary": 0.6,
    "ik_fk_arm_L": 0.0, "ik_fk_arm_R": 0.0,
    "ik_fk_leg_L": 0.0, "ik_fk_leg_R": 0.0,
    "curl_L": 0.0, "curl_R": 0.0,
    "spread_L": 0.0, "spread_R": 0.0,
    "foot_roll_L": 0.0, "foot_roll_R": 0.0,
    "roll_pivot_L": 0, "roll_pivot_R": 0,
    "toe_curl_L": 0.0, "toe_curl_R": 0.0,
    "blink_L": 0.0, "blink_R": 0.0,
    "squint": 0.0, "brow_raise": 0.0, "jaw_open": 0.0,
    "smile_L": 0.0, "smile_R": 0.0,
    "frown_L": 0.0, "frown_R": 0.0,
    "lip_close": 0.0, "lip_width": 0.0, "pucker": 0.0,
    "cheek_L": 0.0, "cheek_R": 0.0, "tongue": 0.0,
    "look_auto": True, "look_pitch": 0.0, "look_yaw": 0.0,
}

# control prop -> shape key name (the mesh's tongue morph is "tongue_out")
MORPH_KEYS = [("lip_close", "lip_close"), ("smile_L", "smile_L"),
              ("smile_R", "smile_R"), ("frown_L", "frown_L"),
              ("frown_R", "frown_R"), ("lip_width", "lip_width"),
              ("pucker", "pucker"), ("cheek_L", "cheek_L"),
              ("cheek_R", "cheek_R"), ("tongue", "tongue_out")]

# ------------------------------------------------------------------ math helpers
def rest_local(bone):
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted() @ bone.matrix_local


class _DM:
    """Desired armature-space pose matrices, set in parent-before-child order,
    so children never need a depsgraph update to read their parent's pose."""

    def __init__(self):
        self.m = {}

    def set(self, pb, M):
        bone = pb.bone
        if bone.parent is None:
            basis = bone.matrix_local.inverted() @ M
        else:
            pM = self.m.get(bone.parent.name, pb.parent.matrix)
            basis = rest_local(bone).inverted() @ pM.inverted() @ M
        loc = basis.to_translation()
        R = basis.to_3x3()
        sc = Vector((R.col[0].length, R.col[1].length, R.col[2].length))
        for i in range(3):
            if sc[i] > 1e-9:
                R.col[i] = R.col[i] / sc[i]
        pb.rotation_mode = 'XYZ'
        pb.location = loc
        pb.rotation_euler = R.to_euler('XYZ')
        pb.scale = sc
        self.m[pb.name] = M


def solve_2bone_ik(A, E, W, target, pole):
    A = Vector(A); E = Vector(E); W = Vector(W); T = Vector(target)
    L1 = (E - A).length
    L2 = (W - E).length
    d = (T - A).length
    d = min(max(d, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    u = T - A
    u = u.normalized() if u.length > 1e-9 else (W - A).normalized()
    cos_a = (L1 * L1 + d * d - L2 * L2) / (2.0 * L1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    pv = Vector(pole) - A
    v = pv - u * pv.dot(u)
    if v.length < 1e-6:
        v = Vector((0, 0, 1)) - u * u.z
        if v.length < 1e-6:
            v = Vector((1, 0, 0)) - u * u.x
    v.normalize()
    # law of cosines: the joint sits at distance L1 from A, at angle a from the
    # A->target axis, on the pole side.  (u*(L1*cos_a) + v*(L1*sin_a) has length
    # L1 and puts the effector exactly L2 from the joint.)
    E_new = A + (u * (L1 * cos_a) + v * (L1 * sin_a))
    return E_new, A + u * d


def dir_pose_matrix(rest_M, new_dir, new_head=None):
    rest_dir = rest_M.col[1].normalized()
    nd = Vector(new_dir)
    if nd.length < 1e-9:
        return rest_M.copy()
    nd = nd.normalized()
    q = rest_dir.rotation_difference(nd)
    R = q.to_matrix().to_4x4() @ rest_M.to_3x3().to_4x4()
    head = Vector(new_head) if new_head is not None else rest_M.to_translation()
    return Matrix.Translation(head) @ R


def look_rotations(from_pos, to_pos):
    d = Vector(to_pos) - Vector(from_pos)
    if d.length < 1e-9:
        return 0.0, 0.0
    d.normalize()
    return math.atan2(d.x, -d.y), math.asin(max(-1.0, min(1.0, d.z)))


def _unit_rot(M):
    R = M.to_3x3().copy()
    for i in range(3):
        c = R.col[i]
        if c.length > 1e-9:
            R.col[i] = c / c.length
    return R


def lerp_matrices(A, B, t):
    if t <= 0.0:
        return A.copy()
    if t >= 1.0:
        return B.copy()
    loc = A.to_translation().lerp(B.to_translation(), t)
    q = _unit_rot(A).to_quaternion().slerp(_unit_rot(B).to_quaternion(), t)
    R = q.to_matrix()
    sA = A.to_3x3()
    sB = B.to_3x3()
    sc = Vector((sA.col[0].length, sA.col[1].length, sA.col[2].length)).lerp(
        Vector((sB.col[0].length, sB.col[1].length, sB.col[2].length)), t)
    for i in range(3):
        R.col[i] = R.col[i] * sc[i]
    return Matrix.Translation(loc) @ R.to_4x4()


def clamp(v, a, b):
    return max(a, min(b, v))


# ------------------------------------------------------------------ accessors
def arm():
    return bpy.data.objects.get(ARM_NAME)


def ctrl():
    return bpy.data.objects.get(CTRL_NAME)


def mesh():
    return bpy.data.objects.get(MESH_NAME)


def gp(name, default=0.0):
    C = ctrl()
    return C.get(name, default) if C else default


# ------------------------------------------------------------------ core ops
def reset_pose():
    A = arm(); C = ctrl(); M = mesh()
    if A is None or C is None:
        return
    for k, v in DEFAULTS.items():
        C[k] = v
    for pb in A.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
        pb.rotation_mode = 'XYZ'
    for cb in C.pose.bones:
        cb.matrix_basis = Matrix.Identity(4)
        cb.rotation_mode = 'XYZ'
    # controls back to their rest positions
    for name in ("ctrl_root", "ctrl_pelvis", "ctrl_chest", "ctrl_neck", "ctrl_head"):
        cb = C.pose.bones.get(name)
        if cb is not None:
            cb.location = (0.0, 0.0, 0.0)
            cb.rotation_euler = (0.0, 0.0, 0.0)
            cb.scale = (1.0, 1.0, 1.0)
    # IK targets / poles back to rest heads
    ad = A.data
    for side in ("L", "R"):
        for tgt, bone_name in ((f"ik_hand_{side}", f"hand_{side}"),
                               (f"ik_foot_{side}", f"foot_{side}")):
            cb = C.pose.bones.get(tgt)
            if cb is not None:
                cb.location = (0.0, 0.0, 0.0)
        for pole, bone_name in ((f"pole_elbow_{side}", f"forearm_{side}"),
                                 (f"pole_knee_{side}", f"shin_{side}")):
            cb = C.pose.bones.get(pole)
            if cb is not None:
                # pole controls are authored at their pole position, so the
                # rest state is an identity basis (no extra offset)
                cb.location = (0.0, 0.0, 0.0)
    look = C.pose.bones.get("ctrl_look")
    if look is not None:
        look.location = (0.0, 0.0, 0.0)
    # shape keys to zero
    if M is not None and M.data.shape_keys is not None:
        for kb in M.data.shape_keys.key_blocks:
            kb.value = 0.0
    # stop any action playback
    if A.animation_data is not None:
        A.animation_data.action = None
    bpy.context.view_layer.update()


def apply_controls():
    """Bake the control rig state onto the deformation skeleton + shape keys."""
    A = arm(); C = ctrl(); M = mesh()
    if A is None or C is None:
        return
    bpy.context.view_layer.update()  # fresh control pose matrices
    pbs = A.pose.bones
    dm = _DM()
    # clear
    for pb in pbs:
        pb.matrix_basis = Matrix.Identity(4)
        pb.rotation_mode = 'XYZ'
    gs = float(gp("global_scale", 1.0))
    sec = float(gp("secondary", 0.6))

    # ---- root / pelvis / spine (body controls). Every bone inherits its
    # parent's current pose and applies the control's local basis delta, so
    # root motion and global_scale propagate through the whole body.
    cr = C.pose.bones["ctrl_root"]
    root = pbs["root"]
    gsM = Matrix.Diagonal((gs, gs, gs, 1.0))
    # ctrl_root shares the root bone's rest frame, so the control's basis
    # (scaled) is exactly the deformation root's basis
    root.matrix_basis = cr.matrix_basis @ gsM
    dm.m["root"] = cr.matrix @ gsM
    cp = C.pose.bones["ctrl_pelvis"]
    dm.set(pbs["pelvis"], dm.m["root"] @ rest_local(pbs["pelvis"].bone)
           @ cp.matrix_basis)
    dm.set(pbs["spine_01"], dm.m["pelvis"] @ rest_local(pbs["spine_01"].bone))
    cc = C.pose.bones["ctrl_chest"]
    dm.set(pbs["spine_02"], dm.m["spine_01"] @ rest_local(pbs["spine_02"].bone)
           @ cc.matrix_basis)
    dm.set(pbs["spine_03"], dm.m["spine_02"] @ rest_local(pbs["spine_03"].bone))
    cn = C.pose.bones["ctrl_neck"]

    # ---- look-at (necks first, then head, then eyes: _DM must be filled in
    # parent-before-child order, otherwise set() falls back to the parent's
    # stale pose matrix and the parent's motion leaks into the child).
    # Every chain is anchored at its parent's CURRENT pose (not at the rest
    # position), so a posed/moving body carries the head along.
    head_rest = pbs["head"].bone.matrix_local
    head_pos = head_rest.to_translation()
    if bool(gp("look_auto", True)):
        yaw, pitch = look_rotations(head_pos, C.pose.bones["ctrl_look"].matrix.to_translation())
    else:
        yaw = math.radians(float(gp("look_yaw", 0.0)))
        pitch = math.radians(float(gp("look_pitch", 0.0)))
    yaw = clamp(yaw, math.radians(-75), math.radians(75))
    pitch = clamp(pitch, math.radians(-45), math.radians(45))
    parent_name = "spine_03"
    for neck_name, ctrl_name in (("neck_01", "ctrl_neck"), ("neck_02", None)):
        nb = pbs[neck_name].bone
        n_rest = nb.matrix_local
        if ctrl_name is not None:
            cnb = C.pose.bones[ctrl_name]
            base = cnb.matrix_basis.to_3x3()
            for i in range(3):
                c = base.col[i]
                if c.length > 1e-9:
                    base.col[i] = c / c.length
            base = base.to_4x4()
        else:
            base = Matrix.Identity(4)
        f = 0.4 if neck_name == "neck_01" else 0.15
        # armature-frame look delta, conjugated into the bone's local frame
        D_arm = (Matrix.Rotation(yaw * f, 4, 'Z')
                 @ Matrix.Rotation(-pitch * f, 4, 'X') @ base)
        R3 = n_rest.to_3x3()
        delta = R3.inverted().to_4x4() @ D_arm @ R3.to_4x4()
        dm.set(pbs[neck_name], dm.m[parent_name] @ rest_local(nb) @ delta)
        parent_name = neck_name
    ch = C.pose.bones["ctrl_head"]
    # the control's basis (delta from its own rest frame), not its full pose
    # matrix -- the rest frame is applied once, via rest_local below
    R_ch = ch.matrix_basis.to_3x3()
    for i in range(3):
        c = R_ch.col[i]
        if c.length > 1e-9:
            R_ch.col[i] = c / c.length
    D_arm = (Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-pitch, 4, 'X')
             @ R_ch.to_4x4())
    R3 = head_rest.to_3x3()
    delta = R3.inverted().to_4x4() @ D_arm @ R3.to_4x4()
    dm.set(pbs["head"], dm.m["neck_02"] @ rest_local(pbs["head"].bone) @ delta)

    # ---- eyes (identity frames: X=right, Y=+Y, Z=up)
    eye_yaw = clamp(yaw, math.radians(-60), math.radians(60))
    eye_pitch = clamp(pitch, math.radians(-35), math.radians(35))
    D_eye = Matrix.Rotation(eye_yaw, 4, 'Z') @ Matrix.Rotation(-eye_pitch, 4, 'X')
    for side in ("L", "R"):
        eb = pbs[f"eye_{side}"].bone
        dm.set(pbs[f"eye_{side}"], dm.m["head"] @ rest_local(eb) @ D_eye)

    # ---- arms
    for side in ("L", "R"):
        ikfk = float(gp(f"ik_fk_arm_{side}", 0.0))
        dm.set(pbs[f"clavicle_{side}"],
               dm.m["spine_03"] @ rest_local(pbs[f"clavicle_{side}"].bone)
               @ C.pose.bones[f"fk_clavicle_{side}"].matrix_basis)
        ua = pbs[f"upper_arm_{side}"].bone.matrix_local
        fa = pbs[f"forearm_{side}"].bone.matrix_local
        # IK chain anchored at the shoulder's CURRENT position (the clavicle
        # is posed), not at the rest position, so IK arms follow the body
        A0 = (dm.m[f"clavicle_{side}"]
              @ rest_local(pbs[f"upper_arm_{side}"].bone)).to_translation()
        E0 = A0 + gs * (fa.to_translation() - ua.to_translation())
        W0 = A0 + gs * (pbs[f"hand_{side}"].bone.matrix_local.to_translation()
                        - ua.to_translation())
        ik_t = gs * C.pose.bones[f"ik_hand_{side}"].matrix.to_translation()
        pole = gs * C.pose.bones[f"pole_elbow_{side}"].matrix.to_translation()
        E_new, T_new = solve_2bone_ik(A0, E0, W0, ik_t, pole)
        # IK bone matrices carry the global scale: dir_pose_matrix returns
        # rest-scale bones, so without gsM an IK limb at global_scale != 1
        # keeps its full rest length anchored at the scaled shoulder/hip
        M_ik_upper = dir_pose_matrix(ua, E_new - A0, A0) @ gsM
        M_ik_fore = dir_pose_matrix(fa, T_new - E_new, E_new) @ gsM
        M_fk_upper = (dm.m[f"clavicle_{side}"]
                      @ rest_local(pbs[f"upper_arm_{side}"].bone)
                      @ C.pose.bones[f"fk_upper_arm_{side}"].matrix_basis)
        dm.set(pbs[f"upper_arm_{side}"], lerp_matrices(M_fk_upper, M_ik_upper, ikfk))
        M_fk_fore = (dm.m[f"upper_arm_{side}"]
                     @ rest_local(pbs[f"forearm_{side}"].bone)
                     @ C.pose.bones[f"fk_forearm_{side}"].matrix_basis)
        dm.set(pbs[f"forearm_{side}"], lerp_matrices(M_fk_fore, M_ik_fore, ikfk))
        # hand follows the FK control, blended onto the IK effector in IK mode
        M_hand = (dm.m[f"forearm_{side}"]
                  @ rest_local(pbs[f"hand_{side}"].bone)
                  @ C.pose.bones[f"fk_hand_{side}"].matrix_basis)
        if ikfk > 0.0:
            M_hand = (Matrix.Translation(M_hand.to_translation().lerp(T_new, ikfk))
                      @ M_hand.to_3x3().to_4x4())
        dm.set(pbs[f"hand_{side}"], M_hand)
        # twist bones: half of the limb bend about the limb axis, inheriting
        # the posed limb (not anchored at the rest position)
        for tw, limb in ((f"upper_arm_twist_{side}", f"upper_arm_{side}"),
                         (f"forearm_twist_{side}", f"forearm_{side}")):
            tb = pbs[tw].bone
            limb_pb = pbs[limb]
            q_delta = (limb_pb.bone.matrix_local.col[1].normalized()).rotation_difference(
                (dm.m[limb].col[1]).normalized())
            q_half = Quaternion((1.0, 0.0, 0.0, 0.0)).slerp(q_delta, 0.5)
            R3 = tb.matrix_local.to_3x3()
            delta = R3.inverted().to_4x4() @ q_half.to_matrix().to_4x4() @ R3.to_4x4()
            dm.set(pbs[tw], dm.m[limb] @ rest_local(tb) @ delta)
        # fingers: curl (+X = curl down) and spread (+Z splays toward +X on L)
        curl = float(gp(f"curl_{side}", 0.0))
        spread = float(gp(f"spread_{side}", 0.0))
        s = -1.0 if side == "L" else 1.0
        spread_signs = {"thumb": 1.0, "index": 1.0, "middle": 0.0, "ring": -1.0, "pinky": -2.0}
        for finger, ssign in spread_signs.items():
            for i in (1, 2, 3):
                pb = pbs[f"f_{finger}_0{i}_{side}"]
                pb.rotation_euler = (curl * 1.25 * (1.0 + 0.1 * (i - 1)), 0.0, 0.0)
            pb1 = pbs[f"f_{finger}_01_{side}"]
            pb1.rotation_euler[2] = -s * ssign * spread * 0.35

    # ---- legs
    for side in ("L", "R"):
        ikfk = float(gp(f"ik_fk_leg_{side}", 0.0))
        th = pbs[f"thigh_{side}"].bone.matrix_local
        sh = pbs[f"shin_{side}"].bone.matrix_local
        # IK chain anchored at the hip's CURRENT position (the pelvis is
        # posed), not at the rest position, so IK legs follow the body
        A0 = (dm.m["pelvis"]
              @ rest_local(pbs[f"thigh_{side}"].bone)).to_translation()
        K0 = A0 + gs * (sh.to_translation() - th.to_translation())
        F0 = A0 + gs * (pbs[f"foot_{side}"].bone.matrix_local.to_translation()
                        - th.to_translation())
        ik_t = gs * C.pose.bones[f"ik_foot_{side}"].matrix.to_translation()
        pole = gs * C.pose.bones[f"pole_knee_{side}"].matrix.to_translation()
        K_new, F_new = solve_2bone_ik(A0, K0, F0, ik_t, pole)
        M_ik_thigh = dir_pose_matrix(th, K_new - A0, A0) @ gsM
        M_ik_shin = dir_pose_matrix(sh, F_new - K_new, K_new) @ gsM
        # FK chains inherit the posed parent (pelvis / thigh), so root motion
        # and global_scale propagate; at scale 1 this reproduces the authored
        # control matrices exactly
        M_fk_thigh = (dm.m["pelvis"] @ rest_local(pbs[f"thigh_{side}"].bone)
                      @ C.pose.bones[f"fk_thigh_{side}"].matrix_basis)
        dm.set(pbs[f"thigh_{side}"], lerp_matrices(M_fk_thigh, M_ik_thigh, ikfk))
        M_fk_shin = (dm.m[f"thigh_{side}"] @ rest_local(pbs[f"shin_{side}"].bone)
                     @ C.pose.bones[f"fk_shin_{side}"].matrix_basis)
        dm.set(pbs[f"shin_{side}"], lerp_matrices(M_fk_shin, M_ik_shin, ikfk))
        # foot: FK basis inherited from the posed shin + roll about the pivot
        M_foot = (dm.m[f"shin_{side}"] @ rest_local(pbs[f"foot_{side}"].bone)
                  @ C.pose.bones[f"fk_foot_{side}"].matrix_basis)
        roll = math.radians(float(gp(f"foot_roll_{side}", 0.0)))
        piv = int(gp(f"roll_pivot_{side}", 0))
        ankle = M_foot.to_translation()
        if piv == 1:
            pivot = ankle + Vector((0.0, 0.045, -0.070))
        elif piv == 2:
            pivot = ankle + Vector((0.0, -0.140, -0.035))
        else:
            pivot = ankle
        if abs(roll) > 1e-7:
            M_foot = (Matrix.Translation(pivot) @ Matrix.Rotation(roll, 4, 'X')
                      @ Matrix.Translation(-pivot) @ M_foot)
        # ankle follows the IK effector in IK mode (foot keeps its FK rotation)
        if ikfk > 0.0:
            M_foot = (Matrix.Translation(M_foot.to_translation().lerp(F_new, ikfk))
                      @ M_foot.to_3x3().to_4x4())
        dm.set(pbs[f"foot_{side}"], M_foot)
        # toe: rigid child of the foot's final pose, carrying the fk_toe
        # control basis plus a curl about the toe joint's own (local X) axis
        M_toe = (dm.m[f"foot_{side}"] @ rest_local(pbs[f"toe_{side}"].bone)
                 @ C.pose.bones[f"fk_toe_{side}"].matrix_basis)
        tc = float(gp(f"toe_curl_{side}", 0.0)) * math.radians(55)
        M_toe = M_toe @ Matrix.Rotation(tc, 4, 'X')
        dm.set(pbs[f"toe_{side}"], M_toe)
        for tw, limb in ((f"thigh_twist_{side}", f"thigh_{side}"),
                         (f"shin_twist_{side}", f"shin_{side}")):
            tb = pbs[tw].bone
            limb_pb = pbs[limb]
            q_delta = (limb_pb.bone.matrix_local.col[1].normalized()).rotation_difference(
                (dm.m[limb].col[1]).normalized())
            q_half = Quaternion((1.0, 0.0, 0.0, 0.0)).slerp(q_delta, 0.5)
            R3 = tb.matrix_local.to_3x3()
            delta = R3.inverted().to_4x4() @ q_half.to_matrix().to_4x4() @ R3.to_4x4()
            dm.set(pbs[tw], dm.m[limb] @ rest_local(tb) @ delta)

    # ---- face bones (lids/brow/jaw inherit the posed head)
    blink_l = float(gp("blink_L", 0.0)); blink_r = float(gp("blink_R", 0.0))
    squint = clamp(float(gp("squint", 0.0)), -1.0, 1.0)
    brow = float(gp("brow_raise", 0.0))
    jaw_o = float(gp("jaw_open", 0.0))
    for side, bl in (("L", blink_l), ("R", blink_r)):
        for lid, sgn in ((f"lid_upper_{side}", 1.0), (f"lid_lower_{side}", -1.0)):
            lb = pbs[lid].bone
            ang = sgn * (math.radians(56.0) * bl + math.radians(25.0) * squint) \
                - eye_pitch * 0.6 * sgn
            R3 = lb.matrix_local.to_3x3()
            delta = R3.inverted().to_4x4() @ Matrix.Rotation(ang, 4, 'X') @ R3.to_4x4()
            dm.set(pbs[lid], dm.m["head"] @ rest_local(lb) @ delta)
        bb = pbs[f"brow_{side}"].bone
        R3 = bb.matrix_local.to_3x3()
        v = R3.inverted() @ Vector((0.0, 0.0, 0.008 * brow))
        dm.set(pbs[f"brow_{side}"],
               dm.m["head"] @ rest_local(bb) @ Matrix.Translation(v))
    jb = pbs["jaw"].bone
    R3 = jb.matrix_local.to_3x3()
    delta = R3.inverted().to_4x4() @ Matrix.Rotation(math.radians(65.0) * jaw_o, 4, 'X') \
        @ R3.to_4x4()
    dm.set(pbs["jaw"], dm.m["head"] @ rest_local(jb) @ delta)

    # ---- secondary motion: cables follow pelvis lean (baked spring preview),
    # each cable inheriting its parent's current pose
    pelvis_R = dm.m["pelvis"].to_3x3()
    pelvis_Y = (pelvis_R @ Vector((0.0, 1.0, 0.0)))
    lean = math.atan2(-pelvis_Y.y, max(1e-6, pelvis_Y.z))
    # relative to the pelvis rest tilt so the cables sit exactly at rest
    pelvis_rest_Y = pbs["pelvis"].bone.matrix_local.to_3x3() @ Vector((0.0, 1.0, 0.0))
    lean -= math.atan2(-pelvis_rest_Y.y, max(1e-6, pelvis_rest_Y.z))
    cable_parent = {"cable_01": "spine_03", "cable_02": "cable_01",
                    "cable_03": "pelvis"}
    for i, cname in enumerate(("cable_01", "cable_02", "cable_03")):
        cb = pbs[cname].bone
        ang = -sec * lean * (0.9 - 0.2 * i)
        R3 = cb.matrix_local.to_3x3()
        delta = R3.inverted().to_4x4() @ Matrix.Rotation(ang, 4, 'X') @ R3.to_4x4()
        dm.set(pbs[cname], dm.m[cable_parent[cname]] @ rest_local(cb) @ delta)

    # ---- shape keys (facial morphs)
    if M is not None and M.data.shape_keys is not None:
        for prop, k in MORPH_KEYS:
            kb = M.data.shape_keys.key_blocks.get(k)
            if kb is not None:
                kb.value = clamp(float(gp(prop, 0.0)), -1.0, 1.0)

    bpy.context.view_layer.update()


def match_fk_to_ik():
    """Snap FK control chains and IK targets onto the current skeleton pose."""
    A = arm(); C = ctrl()
    if A is None or C is None:
        return
    bpy.context.view_layer.update()
    chains = []
    for side in ("L", "R"):
        chains.append((f"fk_clavicle_{side}", f"clavicle_{side}", "ctrl_chest"))
        chains.append((f"fk_upper_arm_{side}", f"upper_arm_{side}", f"fk_clavicle_{side}"))
        chains.append((f"fk_forearm_{side}", f"forearm_{side}", f"fk_upper_arm_{side}"))
        chains.append((f"fk_hand_{side}", f"hand_{side}", f"fk_forearm_{side}"))
        chains.append((f"fk_thigh_{side}", f"thigh_{side}", "ctrl_pelvis"))
        chains.append((f"fk_shin_{side}", f"shin_{side}", f"fk_thigh_{side}"))
        chains.append((f"fk_foot_{side}", f"foot_{side}", f"fk_shin_{side}"))
        chains.append((f"fk_toe_{side}", f"toe_{side}", f"fk_foot_{side}"))
    for fk_name, def_name, parent_ctrl in chains:
        fc = C.pose.bones.get(fk_name)
        dp = A.pose.bones.get(def_name)
        if fc is None or dp is None:
            continue
        fc.rotation_euler = dp.rotation_euler.copy()
        pc = C.pose.bones.get(parent_ctrl)
        if pc is not None:
            # place the control head exactly on the deformation bone's pose head
            rl = rest_local(fc.bone)
            t = (rl.to_3x3().inverted()
                 @ (pc.matrix.inverted() @ dp.matrix.to_translation()
                    - rl.to_translation()))
            fc.location = t
    for side in ("L", "R"):
        for tgt, def_name in ((f"ik_hand_{side}", f"hand_{side}"),
                              (f"ik_foot_{side}", f"foot_{side}")):
            tc = C.pose.bones.get(tgt)
            dp = A.pose.bones.get(def_name)
            if tc is not None and dp is not None:
                # the IK controls' rest frames are generally not identity, so
                # the world-space delta must be brought into bone-local space
                tc.location = (tc.bone.matrix_local.to_3x3().inverted()
                               @ (dp.matrix.to_translation()
                                  - tc.bone.matrix_local.to_translation()))
    bpy.context.view_layer.update()


def apply_face_props(props):
    C = ctrl()
    if C is None:
        return
    for k, v in props.items():
        C[k] = v
    apply_controls()


# ------------------------------------------------------------------ operators
class OPR_OT_reset_pose(bpy.types.Operator):
    bl_idname = "opr.reset_pose"
    bl_label = "Reset Pose"
    bl_description = "Reset controls, deformation skeleton and shape keys to the rest pose"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        reset_pose()
        self.report({'INFO'}, "Pose reset")
        return {'FINISHED'}


class OPR_OT_apply_controls(bpy.types.Operator):
    bl_idname = "opr.apply_controls"
    bl_label = "Apply Controls to Skeleton"
    bl_description = ("Bake the control rig (IK/FK, poles, foot roll, fingers, "
                      "look-at, face, secondary) onto the deformation skeleton")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        apply_controls()
        self.report({'INFO'}, "Controls applied to skeleton")
        return {'FINISHED'}


class OPR_OT_match_fk(bpy.types.Operator):
    bl_idname = "opr.match_fk"
    bl_label = "Match FK to IK"
    bl_description = "Snap the FK control chains and IK targets onto the current skeleton pose"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        match_fk_to_ik()
        self.report({'INFO'}, "FK matched to skeleton")
        return {'FINISHED'}


class OPR_OT_face(bpy.types.Operator):
    bl_idname = "opr.face"
    bl_label = "Apply Face"
    bl_description = "Apply an expression preset or viseme to the face controls"
    bl_options = {'REGISTER', 'UNDO'}
    name: bpy.props.StringProperty(name="Name", default="neutral")
    kind: bpy.props.StringProperty(name="Kind", default="preset")

    def execute(self, context):
        table = PRESETS if self.kind == "preset" else VISEMES
        props = table.get(self.name)
        if props is None:
            self.report({'ERROR'}, "Unknown %s: %s" % (self.kind, self.name))
            return {'CANCELLED'}
        # clear face props first so presets compose cleanly
        C = ctrl()
        for k in list(DEFAULTS.keys()):
            if k.startswith(("blink", "squint", "brow", "jaw", "smile", "frown",
                             "lip", "pucker", "cheek", "tongue")):
                C[k] = DEFAULTS[k]
        apply_face_props(props)
        self.report({'INFO'}, "%s applied: %s" % (self.kind, self.name))
        return {'FINISHED'}


class OPR_OT_play_action(bpy.types.Operator):
    bl_idname = "opr.play_action"
    bl_label = "Play Action"
    bl_description = "Assign a skeleton action to the armature and play it"
    bl_options = {'REGISTER'}
    name: bpy.props.StringProperty(name="Action", default="")

    def execute(self, context):
        A = arm()
        act = bpy.data.actions.get(self.name)
        if A is None or act is None:
            self.report({'ERROR'}, "Action not found: %s" % self.name)
            return {'CANCELLED'}
        A.animation_data_create()
        A.animation_data.action = act
        sc = context.scene
        sc.frame_start = max(1, int(act.frame_start))
        sc.frame_end = max(int(act.frame_end), sc.frame_start + 1)
        self.report({'INFO'}, "Playing %s" % self.name)
        return {'FINISHED'}


class OPR_OT_stop_action(bpy.types.Operator):
    bl_idname = "opr.stop_action"
    bl_label = "Stop Action"
    bl_options = {'REGISTER'}

    def execute(self, context):
        A = arm()
        if A is not None and A.animation_data is not None:
            A.animation_data.action = None
        return {'FINISHED'}


# ------------------------------------------------------------------ panel
class VIEW3D_PT_operative_rig(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Operative"
    bl_label = "Operative Rig"

    @classmethod
    def poll(cls, context):
        return ctrl() is not None and arm() is not None

    def draw(self, context):
        layout = self.layout
        C = ctrl()
        A = arm()
        col = layout.column(align=True)
        col.operator("opr.reset_pose", icon='LOOP_BACK')
        col.operator("opr.apply_controls", icon='ARMATURE_DATA')
        col.operator("opr.match_fk", icon='SNAP_ON')
        layout.separator()
        box = layout.box(); box.label(text="Global")
        box.prop(C, '["global_scale"]', slider=True)
        box.prop(C, '["secondary"]', slider=True)
        for side in ("L", "R"):
            box = layout.box(); box.label(text="Arm %s" % side)
            box.prop(C, '["ik_fk_arm_%s"]' % side, slider=True)
            box.prop(C, '["curl_%s"]' % side, slider=True)
            box.prop(C, '["spread_%s"]' % side, slider=True)
            box = layout.box(); box.label(text="Leg %s" % side)
            box.prop(C, '["ik_fk_leg_%s"]' % side, slider=True)
            box.prop(C, '["foot_roll_%s"]' % side, slider=True)
            box.prop(C, '["roll_pivot_%s"]' % side)
            box.prop(C, '["toe_curl_%s"]' % side, slider=True)
        box = layout.box(); box.label(text="Face")
        row = box.row(align=True)
        row.prop(C, '["blink_L"]', slider=True); row.prop(C, '["blink_R"]', slider=True)
        box.prop(C, '["squint"]', slider=True)
        box.prop(C, '["brow_raise"]', slider=True)
        box.prop(C, '["jaw_open"]', slider=True)
        for k in ("lip_close", "smile_L", "smile_R", "frown_L", "frown_R",
                  "lip_width", "pucker", "cheek_L", "cheek_R", "tongue"):
            box.prop(C, '["%s"]' % k, slider=True)
        box = layout.box(); box.label(text="Look")
        box.prop(C, '["look_auto"]')
        row = box.row(align=True)
        row.prop(C, '["look_yaw"]'); row.prop(C, '["look_pitch"]')
        row.enabled = not bool(C.get("look_auto", True))
        box = layout.box(); box.label(text="Expression presets")
        for name in PRESETS:
            box.operator("opr.face", text=name.replace("_", " ").title()).name = name
        box = layout.box(); box.label(text="Visemes")
        for name in VISEMES:
            op = box.operator("opr.face", text=name)
            op.name = name; op.kind = "viseme"
        box = layout.box(); box.label(text="Action preview")
        row = box.row(align=True)
        row.operator("opr.play_action", text="Play").name = "idle_relaxed"
        row.operator("opr.stop_action", text="Stop")
        acts = sorted(a.name for a in bpy.data.actions)
        if acts:
            box.label(text="%d actions in file" % len(acts))


classes = (
    OPR_OT_reset_pose,
    OPR_OT_apply_controls,
    OPR_OT_match_fk,
    OPR_OT_face,
    OPR_OT_play_action,
    OPR_OT_stop_action,
    VIEW3D_PT_operative_rig,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if not hasattr(bpy.types, "OPR_OT_reset_pose"):
    register()
