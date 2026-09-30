"""MorphRig animator control rig (MR_Rig) that drives the export skeleton (MR_Skeleton).

Layout
  * Every export bone has a same-named 'mirror' bone in MR_Rig.  MR_Skeleton copies
    their world transforms (COPY_TRANSFORMS), so baking is a straight sample.
  * FK/IK limbs: c_*_fk controls, mch_*_ik chains with IK constraints, c_hand_ik_*,
    c_foot_ik_* with heel/toe-tip/ball pivots and a 'roll' property, pole controls.
    The mirror limb bones blend FK->IK by the 'ik_fk' property (1 = IK).
  * Spine/neck/head, clavicles, fingers, jaw, tongue, hair tail, blade: the mirror bones
    are the FK controls themselves (keyable).
  * c_torso (centre of gravity) is separate from the pelvis ('hips'); root is the
    global control (scale it for global scaling).
  * c_fingers_* masters add curl (X) and spread (Z) on top of per-phalanx FK.
  * c_look aims both eyes; eyelids are driven by c_face properties + gaze pitch.
  * c_face carries shape-key and viseme properties (drivers feed the head mesh).
  * prop_cell / prop_beacon switch parents (forearm/hand, holster/hand/root) with a
    'parent' property; their own transform is a keyable offset in the active space.
"""
import math
import bpy
from mathutils import Vector, Matrix

RIG = "MR_Rig"
SKEL = "MR_Skeleton"

LIMB_LEG = ["thigh", "calf", "foot", "ball"]
LIMB_ARM = ["upperarm", "lowerarm", "hand"]
FINGERS = ["index", "middle", "ring", "pinky"]


# ------------------------------------------------------------------ widgets
def _widget(name, verts, edges, coll):
    ob = bpy.data.objects.get(name)
    if ob:
        return ob
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def make_widgets():
    coll = bpy.data.collections.get("MR_Widgets")
    if coll is None:
        coll = bpy.data.collections.new("MR_Widgets")
        bpy.context.scene.collection.children.link(coll)
    n = 32
    circ = [(math.cos(2 * math.pi * i / n), 0.0, math.sin(2 * math.pi * i / n)) for i in range(n)]
    circ_e = [(i, (i + 1) % n) for i in range(n)]
    W = {}
    W["circle"] = _widget("WGT_circle", circ, circ_e, coll)
    sq = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
    W["square"] = _widget("WGT_square", sq, [(0, 1), (1, 2), (2, 3), (3, 0)], coll)
    cube = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    ce = [(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    W["cube"] = _widget("WGT_cube", cube, ce, coll)
    sph = []
    se = []
    for ax in range(3):
        base = len(sph)
        for i in range(n):
            a = 2 * math.pi * i / n
            p = [0.0, 0.0, 0.0]
            p[(ax + 1) % 3] = math.cos(a)
            p[(ax + 2) % 3] = math.sin(a)
            sph.append(tuple(p))
            se.append((base + i, base + (i + 1) % n))
    W["sphere"] = _widget("WGT_sphere", sph, se, coll)
    # root: circle with arrow toward -Y (forward)
    rv = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    re = [(i, (i + 1) % n) for i in range(n)]
    k = len(rv)
    rv += [(0, -1.0, 0), (0, -1.35, 0), (-0.12, -1.2, 0), (0.12, -1.2, 0)]
    re += [(k, k + 1), (k + 1, k + 2), (k + 1, k + 3)]
    W["root"] = _widget("WGT_root", rv, re, coll)
    # foot: flat rectangle on the ground plane (local XY of bone = X, Z)
    fv = [(-0.5, 0, -0.3), (0.5, 0, -0.3), (0.5, 0, 1.2), (-0.5, 0, 1.2)]
    W["foot"] = _widget("WGT_foot", [(x, z, 0) for x, _, z in fv], [(0, 1), (1, 2), (2, 3), (3, 0)], coll)
    coll.hide_render = True
    coll.hide_viewport = True
    return W


# ------------------------------------------------------------------ helpers
def _prop(pb, name, val, lo, hi, desc=""):
    pb[name] = float(val)
    ui = pb.id_properties_ui(name)
    ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, default=float(val), description=desc)
    pb.property_overridable_library_set(f'["{name}"]', True)


def _driver(owner, path, index, expr, variables):
    fc = owner.driver_add(path, index) if index is not None else owner.driver_add(path)
    drv = fc.driver
    drv.type = 'SCRIPTED'
    drv.expression = expr
    for vname, target_id, dpath in variables:
        var = drv.variables.new()
        var.name = vname
        var.type = 'SINGLE_PROP'
        var.targets[0].id = target_id
        var.targets[0].data_path = dpath
    return fc


def _copy_tf(pb, rig, sub, infl=1.0, name=None):
    c = pb.constraints.new('COPY_TRANSFORMS')
    c.target = rig
    c.subtarget = sub
    c.target_space = 'WORLD'
    c.owner_space = 'WORLD'
    c.influence = infl
    if name:
        c.name = name
    return c


def build_rig(skel, bone_data, extra):
    """skel: MR_Skeleton object. bone_data: list of dicts (name, head, tail, zref, parent).
    extra: dict of landmark vectors (heel_l, toe_tip_l, knee_pole_l, elbow_pole_l, look, face, torso)."""
    W = make_widgets()
    sc = bpy.context.scene
    col = bpy.data.collections.get("MR_Rig")
    ad = bpy.data.armatures.new(RIG)
    rig = bpy.data.objects.new(RIG, ad)
    col.objects.link(rig)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = ad.edit_bones
    geo = {b["name"]: b for b in bone_data}

    def add(name, head, tail, zref, parent=None, deform=False):
        e = eb.new(name)
        e.head = Vector(head)
        e.tail = Vector(tail)
        e.align_roll(Vector(zref))
        e.use_deform = deform
        if parent:
            e.parent = eb[parent]
        return e

    # 1) mirror bones (same geometry as export bones); parents adjusted below
    for b in bone_data:
        add(b["name"], b["head"], b["tail"], b["zref"])
    # 2) controls & mechanism
    V = lambda x: Vector(tuple(x))
    add("c_torso", extra["torso"], V(extra["torso"]) + Vector((0, 0, 0.12)), (0, -1, 0))
    for s in ("l", "r"):
        for part in LIMB_LEG:
            g = geo[f"{part}_{s}"]
            add(f"c_{part}_fk_{s}", g["head"], g["tail"], g["zref"])
        for part in ("thigh", "calf"):
            g = geo[f"{part}_{s}"]
            add(f"mch_{part}_ik_{s}", g["head"], g["tail"], g["zref"])
        ank = V(geo[f"foot_{s}"]["head"])
        fd = V(extra[f"foot_dir_{s}"])
        add(f"c_foot_ik_{s}", ank, ank + fd * 0.12, (0, 0, 1))
        heel = V(extra[f"heel_{s}"])
        toe = V(extra[f"toe_tip_{s}"])
        ball = V(geo[f"ball_{s}"]["head"])
        add(f"mch_heel_{s}", heel, heel + fd * 0.05, (0, 0, 1))
        add(f"mch_toetip_{s}", toe, toe + fd * 0.04, (0, 0, 1))
        # heel-off pivots on the floor contact under the ball (not the joint 3.4 cm above it),
        # so a rolling foot keeps its contact point planted
        ball_floor = Vector((ball.x, ball.y, 0.0))
        add(f"mch_ballpivot_{s}", ball_floor, ball_floor + fd * 0.04, (0, 0, 1))
        g = geo[f"foot_{s}"]
        add(f"mch_ankle_ik_{s}", g["head"], g["tail"], g["zref"])
        g = geo[f"ball_{s}"]
        add(f"c_ball_ik_{s}", g["head"], g["tail"], g["zref"])
        kp = V(extra[f"knee_pole_{s}"])
        add(f"c_knee_pole_{s}", kp, kp + Vector((0, -0.05, 0)), (0, 0, 1))
        g = geo[f"thigh_{s}"]
        add(f"mch_thigh_notwist_{s}", g["head"], g["tail"], g["zref"])
        # arms
        for part in LIMB_ARM:
            g = geo[f"{part}_{s}"]
            add(f"c_{part}_fk_{s}", g["head"], g["tail"], g["zref"])
        for part in ("upperarm", "lowerarm"):
            g = geo[f"{part}_{s}"]
            add(f"mch_{part}_ik_{s}", g["head"], g["tail"], g["zref"])
        g = geo[f"hand_{s}"]
        add(f"c_hand_ik_{s}", g["head"], g["tail"], g["zref"])
        ep = V(extra[f"elbow_pole_{s}"])
        add(f"c_elbow_pole_{s}", ep, ep + Vector((0, 0.05, 0)), (0, 0, 1))
        g = geo[f"upperarm_{s}"]
        add(f"mch_upperarm_notwist_{s}", g["head"], g["tail"], g["zref"])
        # finger master above the back of the hand
        hb = geo[f"hand_{s}"]
        hh, ht = V(hb["head"]), V(hb["tail"])
        back = V(extra[f"hand_back_{s}"])
        mid = hh.lerp(ht, 0.55) + back * 0.045
        add(f"c_fingers_{s}", mid, mid + (ht - hh).normalized() * 0.04, back)
    lk = V(extra["look"])
    add("c_look", lk, lk + Vector((0, -0.05, 0)), (0, 0, 1))
    fc = V(extra["face"])
    add("c_face", fc, fc + Vector((0, 0, 0.03)), (0, -1, 0))
    # 3) parenting
    par = {
        "root": None, "c_torso": "root", "pelvis": "c_torso", "spine_01": "c_torso",
        "c_look": "head", "c_face": "head",
        "prop_cell": "root", "prop_beacon": "root",
    }
    for b in bone_data:
        nm = b["name"]
        if nm not in par:
            par[nm] = b["parent"]
    for s in ("l", "r"):
        par.update({
            f"c_thigh_fk_{s}": "pelvis", f"c_calf_fk_{s}": f"c_thigh_fk_{s}", f"c_foot_fk_{s}": f"c_calf_fk_{s}",
            f"c_ball_fk_{s}": f"c_foot_fk_{s}",
            f"mch_thigh_ik_{s}": "pelvis", f"mch_calf_ik_{s}": f"mch_thigh_ik_{s}",
            f"c_foot_ik_{s}": "root", f"mch_heel_{s}": f"c_foot_ik_{s}", f"mch_toetip_{s}": f"mch_heel_{s}",
            f"mch_ballpivot_{s}": f"mch_toetip_{s}", f"mch_ankle_ik_{s}": f"mch_ballpivot_{s}",
            f"c_ball_ik_{s}": f"mch_toetip_{s}", f"c_knee_pole_{s}": f"c_foot_ik_{s}",
            f"mch_thigh_notwist_{s}": "pelvis",
            f"thigh_{s}": "pelvis", f"calf_{s}": f"thigh_{s}", f"foot_{s}": f"calf_{s}", f"ball_{s}": f"foot_{s}",
            f"c_upperarm_fk_{s}": f"clavicle_{s}", f"c_lowerarm_fk_{s}": f"c_upperarm_fk_{s}",
            f"c_hand_fk_{s}": f"c_lowerarm_fk_{s}",
            f"mch_upperarm_ik_{s}": f"clavicle_{s}", f"mch_lowerarm_ik_{s}": f"mch_upperarm_ik_{s}",
            f"c_hand_ik_{s}": "root", f"c_elbow_pole_{s}": "root",
            f"mch_upperarm_notwist_{s}": f"clavicle_{s}",
            f"upperarm_{s}": f"clavicle_{s}", f"lowerarm_{s}": f"upperarm_{s}", f"hand_{s}": f"lowerarm_{s}",
            f"c_fingers_{s}": f"hand_{s}",
        })
    for nm, p in par.items():
        if nm in eb and p:
            eb[nm].parent = eb[p]
            eb[nm].use_connect = False
    bpy.ops.object.mode_set(mode='POSE')
    pbs = rig.pose.bones

    # rotation modes: quaternion for controls driven by constraints, euler for FK convenience
    for pb in pbs:
        pb.rotation_mode = 'XYZ'
    for nm in ("root", "c_torso", "pelvis") + tuple(f"c_foot_ik_{s}" for s in "lr") + tuple(f"c_hand_ik_{s}" for s in "lr"):
        pbs[nm].rotation_mode = 'QUATERNION'
    # 4) constraints ---------------------------------------------------------
    for s in ("l", "r"):
        # leg IK
        ik = pbs[f"mch_calf_ik_{s}"].constraints.new('IK')
        ik.target = rig
        ik.subtarget = f"mch_ankle_ik_{s}"
        ik.pole_target = rig
        ik.pole_subtarget = f"c_knee_pole_{s}"
        ik.chain_count = 2
        ik.use_stretch = False
        ik.name = "IK"
        ik = pbs[f"mch_lowerarm_ik_{s}"].constraints.new('IK')
        ik.target = rig
        ik.subtarget = f"c_hand_ik_{s}"
        ik.pole_target = rig
        ik.pole_subtarget = f"c_elbow_pole_{s}"
        ik.chain_count = 2
        ik.use_stretch = False
        ik.name = "IK"
        # properties
        _prop(pbs[f"c_foot_ik_{s}"], "ik_fk", 1.0, 0.0, 1.0, "0 = FK, 1 = IK")
        _prop(pbs[f"c_foot_ik_{s}"], "roll", 0.0, -1.0, 1.0, "<0 heel pivot, 0..0.5 ball, >0.5 toe tip")
        _prop(pbs[f"c_hand_ik_{s}"], "ik_fk", 0.0, 0.0, 1.0, "0 = FK, 1 = IK")
        # final leg bones: FK then IK copy
        for part, fk, ikb in (("thigh", f"c_thigh_fk_{s}", f"mch_thigh_ik_{s}"),
                              ("calf", f"c_calf_fk_{s}", f"mch_calf_ik_{s}"),
                              ("foot", f"c_foot_fk_{s}", f"mch_ankle_ik_{s}"),
                              ("ball", f"c_ball_fk_{s}", f"c_ball_ik_{s}")):
            pb = pbs[f"{part}_{s}"]
            _copy_tf(pb, rig, fk, 1.0, "FK")
            c = _copy_tf(pb, rig, ikb, 1.0, "IK")
            _driver(c, "influence", None, "v", [("v", rig, f'pose.bones["c_foot_ik_{s}"]["ik_fk"]')])
        for part, fk, ikb in (("upperarm", f"c_upperarm_fk_{s}", f"mch_upperarm_ik_{s}"),
                              ("lowerarm", f"c_lowerarm_fk_{s}", f"mch_lowerarm_ik_{s}"),
                              ("hand", f"c_hand_fk_{s}", f"c_hand_ik_{s}")):
            pb = pbs[f"{part}_{s}"]
            _copy_tf(pb, rig, fk, 1.0, "FK")
            c = _copy_tf(pb, rig, ikb, 0.0, "IK")
            _driver(c, "influence", None, "v", [("v", rig, f'pose.bones["c_hand_ik_{s}"]["ik_fk"]')])
        # foot roll drivers
        roll = ("r", rig, f'pose.bones["c_foot_ik_{s}"]["roll"]')
        _driver(pbs[f"mch_heel_{s}"], "rotation_euler", 0, "-min(r,0)*0.60", [roll])
        _driver(pbs[f"mch_ballpivot_{s}"], "rotation_euler", 0, "-min(max(r,0),0.5)*1.30", [roll])
        _driver(pbs[f"mch_toetip_{s}"], "rotation_euler", 0, "-max(r-0.5,0)*1.40", [roll])
        # twist helpers
        dt = pbs[f"mch_thigh_notwist_{s}"].constraints.new('DAMPED_TRACK')
        dt.target = rig
        dt.subtarget = f"calf_{s}"
        c = pbs[f"thigh_twist_01_{s}"].constraints.new('COPY_ROTATION')
        c.target = rig
        c.subtarget = f"mch_thigh_notwist_{s}"
        c.target_space = c.owner_space = 'WORLD'
        c.influence = 0.5
        dt = pbs[f"mch_upperarm_notwist_{s}"].constraints.new('DAMPED_TRACK')
        dt.target = rig
        dt.subtarget = f"lowerarm_{s}"
        c = pbs[f"upperarm_twist_01_{s}"].constraints.new('COPY_ROTATION')
        c.target = rig
        c.subtarget = f"mch_upperarm_notwist_{s}"
        c.target_space = c.owner_space = 'WORLD'
        c.influence = 0.5
        # forearm twist: take 60% of the hand orientation, then re-aim along the forearm
        c = pbs[f"lowerarm_twist_01_{s}"].constraints.new('COPY_ROTATION')
        c.target = rig
        c.subtarget = f"hand_{s}"
        c.target_space = c.owner_space = 'LOCAL'
        c.influence = 0.6
        dt = pbs[f"lowerarm_twist_01_{s}"].constraints.new('DAMPED_TRACK')
        dt.target = rig
        dt.subtarget = f"hand_{s}"
        dt.head_tail = 0.0
        # finger master: curl (X) and spread (Z) added in local space
        for f in FINGERS + ["thumb"]:
            for k in (1, 2, 3):
                pb = pbs[f"{f}_0{k}_{s}"]
                c = pb.constraints.new('COPY_ROTATION')
                c.name = "curl"
                c.target = rig
                c.subtarget = f"c_fingers_{s}"
                c.target_space = c.owner_space = 'LOCAL'
                c.use_y = c.use_z = False
                c.mix_mode = 'ADD'
                c.influence = (0.55 if f == "thumb" else 1.0) * (0.85 if k == 3 else 1.0)
            if f != "thumb":
                c = pbs[f"{f}_01_{s}"].constraints.new('COPY_ROTATION')
                c.name = "spread"
                c.target = rig
                c.subtarget = f"c_fingers_{s}"
                c.target_space = c.owner_space = 'LOCAL'
                c.use_x = c.use_y = False
                c.mix_mode = 'ADD'
                spread = {"index": 1.0, "middle": 0.25, "ring": -0.55, "pinky": -1.0}[f]
                c.invert_z = spread < 0
                c.influence = abs(spread)
    # eyes aim at the look target
    for s in ("l", "r"):
        c = pbs[f"eye_{s}"].constraints.new('DAMPED_TRACK')
        c.target = rig
        c.subtarget = "c_look"
    # face properties (lids + shape keys are driven from here)
    face = pbs["c_face"]
    for nm in extra["face_props"]:
        lo = -1.0 if nm in ("jawSide", "mouthLeftRight") else 0.0
        _prop(face, nm, 0.0, lo, 1.0)
    # eyelid drivers: blink (close), wide, squint, gaze follow (pitch from c_look)
    for s, S in (("l", "L"), ("r", "R")):
        vars_ = [("b", rig, f'pose.bones["c_face"]["blink_{S}"]'),
                 ("w", rig, f'pose.bones["c_face"]["wide_{S}"]'),
                 ("q", rig, f'pose.bones["c_face"]["squint_{S}"]'),
                 ("lz", rig, 'pose.bones["c_look"].location[2]'),
                 ("ly", rig, 'pose.bones["c_look"].location[1]')]
        _driver(pbs[f"lid_upper_{s}"], "rotation_euler", 0,
                "-b*0.66 + w*0.16 - q*0.12 + 0.55*atan2(lz, 1.5+ly)*(1-b)", vars_)
        _driver(pbs[f"lid_lower_{s}"], "rotation_euler", 0,
                "b*0.10 + q*0.20 - w*0.05 + 0.35*atan2(lz, 1.5+ly)*(1-b)", vars_)
    # props: parent switching
    def child_of(pb, target_bone, inv, name):
        c = pb.constraints.new('CHILD_OF')
        c.name = name
        c.target = rig
        c.subtarget = target_bone
        c.inverse_matrix = inv
        c.set_inverse_pending = False
        return c
    rest = {pb.name: pb.bone.matrix_local.copy() for pb in pbs}
    cell = pbs["prop_cell"]
    _prop(cell, "parent", 0.0, 0.0, 1.0, "0 = forearm cradle, 1 = left hand")
    c0 = child_of(cell, "lowerarm_r", rest["lowerarm_r"].inverted(), "in_cradle")
    c1 = child_of(cell, "hand_l", extra["cell_grip"] @ rest["prop_cell"].inverted(), "in_hand")
    _driver(c0, "influence", None, "1-p", [("p", rig, 'pose.bones["prop_cell"]["parent"]')])
    _driver(c1, "influence", None, "p", [("p", rig, 'pose.bones["prop_cell"]["parent"]')])
    bea = pbs["prop_beacon"]
    _prop(bea, "parent", 0.0, 0.0, 2.0, "0 = holster, 1 = left hand, 2 = ground (root space)")
    c0 = child_of(bea, "pelvis", rest["pelvis"].inverted(), "in_holster")
    c1 = child_of(bea, "hand_l", extra["beacon_grip"] @ rest["prop_beacon"].inverted(), "in_hand")
    c2 = child_of(bea, "root", rest["prop_beacon"].inverted(), "on_ground")
    _driver(c0, "influence", None, "max(1-p,0)", [("p", rig, 'pose.bones["prop_beacon"]["parent"]')])
    _driver(c1, "influence", None, "max(1-abs(p-1),0)", [("p", rig, 'pose.bones["prop_beacon"]["parent"]')])
    _driver(c2, "influence", None, "max(p-1,0)", [("p", rig, 'pose.bones["prop_beacon"]["parent"]')])
    # global properties on root
    _prop(pbs["root"], "tail_stiffness", 0.35, 0.0, 1.0, "hair tail spring stiffness (bake)")
    _prop(pbs["root"], "tail_damping", 0.25, 0.0, 1.0, "hair tail damping (bake)")
    _prop(pbs["root"], "tail_gravity", 0.6, 0.0, 2.0, "hair tail gravity factor (bake)")
    bpy.ops.object.mode_set(mode='OBJECT')

    # 5) IK pole angles: search the angle that preserves the rest pose
    for s in ("l", "r"):
        _fit_pole(rig, f"mch_calf_ik_{s}", f"mch_thigh_ik_{s}", "calf_" + s)
        _fit_pole(rig, f"mch_lowerarm_ik_{s}", f"mch_upperarm_ik_{s}", "lowerarm_" + s)

    # 6) display: collections, colours, shapes
    _organize(rig, W)
    # 7) export skeleton follows the rig
    for pb in skel.pose.bones:
        c = pb.constraints.new('COPY_TRANSFORMS')
        c.name = "MR_follow_rig"
        c.target = rig
        c.subtarget = pb.name
        c.target_space = c.owner_space = 'WORLD'
    return rig


def _fit_pole(rig, ik_bone, root_bone, ref_name):
    con = rig.pose.bones[ik_bone].constraints["IK"]
    best = None
    rest_calf = rig.data.bones[ik_bone].matrix_local
    rest_root = rig.data.bones[root_bone].matrix_local
    for deg in range(-180, 180, 1):
        con.pole_angle = math.radians(deg)
        bpy.context.view_layer.update()
        m1 = rig.pose.bones[ik_bone].matrix
        m0 = rig.pose.bones[root_bone].matrix
        err = (m1.col[0].xyz - rest_calf.col[0].xyz).length + (m0.col[0].xyz - rest_root.col[0].xyz).length \
            + (m1.col[1].xyz - rest_calf.col[1].xyz).length
        if best is None or err < best[0]:
            best = (err, deg)
    con.pole_angle = math.radians(best[1])
    bpy.context.view_layer.update()
    print("POLE", ik_bone, best[1], "err", round(best[0], 5))


def _organize(rig, W):
    ad = rig.data
    cols = {}
    for nm in ("Root_Torso", "Spine_Head", "Arm_IK", "Arm_FK", "Leg_IK", "Leg_FK", "Fingers", "Face",
               "Props_Blade", "Hair", "Mechanism", "Deform_Mirror"):
        cols[nm] = ad.collections.new(nm)
    cols["Mechanism"].is_visible = False
    cols["Deform_Mirror"].is_visible = False
    pbs = rig.pose.bones

    def put(nm, cname, shape=None, scale=1.0, palette='THEME09'):
        b = ad.bones[nm]
        cols[cname].assign(b)
        pb = pbs[nm]
        if shape:
            pb.custom_shape = W[shape]
            pb.custom_shape_scale_xyz = (scale, scale, scale)
            pb.use_custom_shape_bone_size = False
        b.color.palette = palette
    put("root", "Root_Torso", "root", 0.45, 'THEME02')
    put("c_torso", "Root_Torso", "circle", 0.22, 'THEME02')
    put("pelvis", "Root_Torso", "circle", 0.17, 'THEME09')
    for nm in ("spine_01", "spine_02", "spine_03", "neck_01", "neck_02", "head"):
        put(nm, "Spine_Head", "circle", 0.14 if "spine" in nm else 0.07, 'THEME09')
    put("c_look", "Face", "sphere", 0.02, 'THEME11')
    put("c_face", "Face", "square", 0.02, 'THEME11')
    for nm in ("jaw", "tongue_01", "tongue_02", "tongue_03"):
        put(nm, "Face", "circle", 0.015, 'THEME11')
    for s in "lr":
        pal = 'THEME01' if s == "l" else 'THEME04'
        put(f"clavicle_{s}", "Spine_Head", "circle", 0.05, pal)
        for part in LIMB_LEG:
            put(f"c_{part}_fk_{s}", "Leg_FK", "circle", 0.08 if part != "ball" else 0.04, pal)
        put(f"c_foot_ik_{s}", "Leg_IK", "foot", 0.09, pal)
        put(f"c_ball_ik_{s}", "Leg_IK", "circle", 0.04, pal)
        put(f"c_knee_pole_{s}", "Leg_IK", "sphere", 0.025, pal)
        for part in LIMB_ARM:
            put(f"c_{part}_fk_{s}", "Arm_FK", "circle", 0.06, pal)
        put(f"c_hand_ik_{s}", "Arm_IK", "cube", 0.045, pal)
        put(f"c_elbow_pole_{s}", "Arm_IK", "sphere", 0.025, pal)
        put(f"c_fingers_{s}", "Fingers", "square", 0.02, pal)
        for f in FINGERS + ["thumb"]:
            for k in (1, 2, 3):
                put(f"{f}_0{k}_{s}", "Fingers", "circle", 0.012, pal)
            if f != "thumb":
                put(f"{f}_metacarpal_{s}", "Fingers", "circle", 0.012, pal)
        for nm in (f"mch_thigh_ik_{s}", f"mch_calf_ik_{s}", f"mch_heel_{s}", f"mch_toetip_{s}",
                   f"mch_ballpivot_{s}", f"mch_ankle_ik_{s}", f"mch_upperarm_ik_{s}", f"mch_lowerarm_ik_{s}",
                   f"mch_thigh_notwist_{s}", f"mch_upperarm_notwist_{s}"):
            put(nm, "Mechanism")
        for nm in (f"thigh_{s}", f"calf_{s}", f"foot_{s}", f"ball_{s}", f"upperarm_{s}", f"lowerarm_{s}",
                   f"hand_{s}", f"upperarm_twist_01_{s}", f"lowerarm_twist_01_{s}", f"thigh_twist_01_{s}",
                   f"eye_{s}", f"lid_upper_{s}", f"lid_lower_{s}"):
            put(nm, "Deform_Mirror")
    put("blade_r", "Props_Blade", "circle", 0.03, 'THEME04')
    put("prop_cell", "Props_Blade", "cube", 0.02, 'THEME03')
    put("prop_beacon", "Props_Blade", "cube", 0.03, 'THEME03')
    for k in range(1, 5):
        put(f"hair_tail_{k:02d}", "Hair", "circle", 0.02, 'THEME06')
