"""MorphRig skeleton and animator control rig.

Design
------
One Blender armature holds two bone families:

  * deform bones  - exported to Unreal (FBX `use_armature_deform_only`)
  * control bones - Blender only, named ``CTRL_*``; they drive the deform
                    bones through Copy Rotation / IK / Damped Track
                    constraints so an animator can work in IK, FK or a mix.

Conventions (Blender, metres): forward = -Y, up = +Z, right = +X.
The character's right side is +X, so side ``+1`` maps to the ``_r`` suffix.

Bone rest frames are built explicitly so every bone has a predictable
local axis set (local X is the character's +X for all limb/spine bones).
"""

import math
from mathutils import Vector, Matrix

import mr_core
from mr_core import parallel_transport_frames

TAU = math.pi * 2.0
D2R = math.pi / 180.0

# ---------------------------------------------------------------------------
# landmark heights (mirrors mr_body.P)
# ---------------------------------------------------------------------------

L = dict(
    ground=0.000, ankle=0.092, knee=0.520, hip=0.950, waist=1.055,
    spine1=1.055, spine2=1.140, spine3=1.225, chest=1.305, clav=1.393,
    shoulder=1.405, elbow=1.120, wrist=0.890, neck=1.400, neck_top=1.510,
    head_pivot=1.515, eye=1.665, brow=1.690, jaw=1.603,
)

FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

# per-finger (length, radius, across-offset, up-offset, splay)
FINGER_TABLE = {
    "thumb":  dict(length=0.070, radius=0.0108, dx=-0.0355, dy=-0.0040,
                   splay=-0.62, base=0.72, curl=0.34),
    "index":  dict(length=0.090, radius=0.0098, dx=-0.0268, dy=0.0080,
                   splay=-0.11, base=1.00, curl=0.10),
    "middle": dict(length=0.095, radius=0.0101, dx=-0.0090, dy=0.0084,
                   splay=0.00, base=1.00, curl=0.10),
    "ring":   dict(length=0.088, radius=0.0094, dx=0.0090, dy=0.0082,
                   splay=0.08, base=1.00, curl=0.11),
    "pinky":  dict(length=0.072, radius=0.0084, dx=0.0270, dy=0.0066,
                   splay=0.17, base=1.00, curl=0.13),
}

FINGER_SEG = (0.44, 0.33, 0.23)


def finger_joints(knuckle, fwd, right, up, fname):
    """Joint positions of one finger: root + three phalanx tips.

    The mesh generator uses the same function so the geometry and the
    skeleton always line up.
    """
    ft = FINGER_TABLE[fname]
    root_p = knuckle + right * ft["dx"] + up * ft["dy"]
    if fname == "thumb":
        d = (fwd * ft["base"] - right * ft["splay"] - up * 0.30).normalized()
    else:
        d = (fwd + right * ft["splay"] - up * 0.02).normalized()
    pts = [root_p]
    p = root_p
    prev = d
    for seg in range(3):
        ln = ft["length"] * FINGER_SEG[seg]
        p = p + prev * ln
        pts.append(p)
        prev = (prev + up * (ft["curl"] * 0.35)).normalized()
    return pts


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def side_suffix(side):
    """side +1 (character right, +X) -> 'r';  side -1 -> 'l'."""
    return "r" if side > 0 else "l"


def hand_frame(side, wrist, palm_dir):
    """Return (fwd, right, up) for a hand.

    fwd   - palm / finger direction
    right - towards the character's right for the right hand (+X)
    up    - dorsal side of the palm
    """
    fwd = Vector(palm_dir).normalized()
    right = Vector((1.0, 0.0, 0.0))
    right = right - fwd * right.dot(fwd)
    if right.length < 1e-6:
        right = Vector((0.0, 1.0, 0.0))
    right.normalize()
    up = fwd.cross(right).normalized()
    if side < 0:
        right = -right
    return fwd, right, up


def _ortho_frame(y_axis, up_ref):
    y = Vector(y_axis).normalized()
    ref = Vector(up_ref)
    if abs(ref.dot(y)) > 0.995:
        ref = Vector((1.0, 0.0, 0.0))
    z = (ref - y * ref.dot(y)).normalized()
    x = y.cross(z).normalized()
    return x, y, z


def bone_matrix(head, tail, up_ref=(0.0, 1.0, 0.0)):
    x, y, z = _ortho_frame(Vector(tail) - Vector(head), up_ref)
    m = Matrix.Identity(4)
    m.col[0][:3] = x
    m.col[1][:3] = y
    m.col[2][:3] = z
    m.translation = Vector(head)
    return m


# ---------------------------------------------------------------------------
# bone specification
# ---------------------------------------------------------------------------

class Bone:
    __slots__ = ("name", "head", "tail", "parent", "deform", "up_ref", "kind")

    def __init__(self, name, head, tail, parent=None, deform=True,
                 up_ref=(0.0, 1.0, 0.0), kind="bone"):
        self.name = name
        self.head = Vector(head)
        self.tail = Vector(tail)
        self.parent = parent
        self.deform = deform
        self.up_ref = Vector(up_ref)
        self.kind = kind

    def matrix(self):
        return bone_matrix(self.head, self.tail, self.up_ref)


def build_bone_specs(eye_l=None, eye_r=None):
    """Return the full ordered list of Bone objects."""
    bones = []
    add = bones.append

    # ---- spine / root -----------------------------------------------------
    add(Bone("root", (0, 0, 0.0), (0, 0, 0.10), None, True))
    add(Bone("pelvis", (0, 0, L["hip"]), (0, 0, L["spine1"]), "root", True))
    add(Bone("spine_01", (0, 0, L["spine1"]), (0, 0, L["spine2"]), "pelvis", True))
    add(Bone("spine_02", (0, 0, L["spine2"]), (0, 0, L["spine3"]), "spine_01", True))
    add(Bone("spine_03", (0, 0, L["spine3"]), (0, 0, L["chest"]), "spine_02", True))
    add(Bone("chest", (0, 0, L["chest"]), (0, 0, 1.400), "spine_03", True))
    add(Bone("neck_01", (0, 0, L["neck"]), (0, 0, L["neck_top"]), "chest", True))
    # the head bone points forward so a Damped Track can aim the face
    add(Bone("head", (0, 0, L["head_pivot"]), (0, -0.055, L["head_pivot"]),
             "neck_01", True, up_ref=(0, 0, 1)))

    # ---- face -------------------------------------------------------------
    for side, ec in ((1, eye_r), (-1, eye_l)):
        s = side_suffix(side)
        if ec is None:
            ec = Vector((side * 0.0335, -0.0795, L["eye"]))
        ec = Vector(ec)
        add(Bone("eye_%s" % s, ec, ec + Vector((0, -0.018, 0)), "head", True,
                 up_ref=(0, 0, 1)))
        add(Bone("eyelid_upper_%s" % s, ec, ec + Vector((0, 0, 0.030)),
                 "eye_%s" % s, True, up_ref=(0, -1, 0)))
        add(Bone("eyelid_lower_%s" % s, ec, ec + Vector((0, 0, -0.026)),
                 "eye_%s" % s, True, up_ref=(0, -1, 0)))
        # the brow bone pivots inside the skull, its tip reaches the brow
        # ridge.  Rotating it lifts the brow ridge of the head.
        add(Bone("brow_%s" % s, (side * 0.0340, -0.0680, L["brow"]),
                 (side * 0.0340, -0.1010, L["brow"]), "head", True,
                 up_ref=(0, 0, 1)))
    add(Bone("jaw", (0, -0.056, L["jaw"]), (0, -0.074, 1.582), "head", True,
             up_ref=(0, 0, 1)))

    # ---- arms -------------------------------------------------------------
    for side in (1, -1):
        s = side_suffix(side)
        sx = float(side)
        cl_head = (sx * 0.030, 0.0, L["clav"])
        cl_tail = (sx * 0.176, 0.0, L["shoulder"])
        ua_head = cl_tail
        ua_tail = (sx * 0.236, -0.014, L["elbow"])
        la_head = ua_tail
        la_tail = (sx * 0.272, -0.031, L["wrist"])
        palm_dir = Vector((sx * 0.12, -0.78, -0.61)).normalized()
        fwd, right, up = hand_frame(side, la_tail, palm_dir)
        knuckle = Vector(la_tail) + fwd * mr_core.KNUCKLE_DIST
        hd_head = la_tail
        hd_tail = knuckle

        add(Bone("clavicle_%s" % s, cl_head, cl_tail, "chest", True,
                 up_ref=(0, -1, 0)))
        add(Bone("upperarm_%s" % s, ua_head, ua_tail, "clavicle_%s" % s, True,
                 up_ref=(0, 1, 0)))
        add(Bone("lowerarm_%s" % s, la_head, la_tail, "upperarm_%s" % s, True,
                 up_ref=(0, 1, 0)))
        add(Bone("hand_%s" % s, hd_head, hd_tail, "lowerarm_%s" % s, True,
                 up_ref=(0, 0, 1)))

        # twist bones (non deforming, they carry the volume-preserving roll)
        add(Bone("upperarm_twist_%s" % s,
                 Vector(ua_head).lerp(Vector(ua_tail), 0.55),
                 ua_tail, "upperarm_%s" % s, False, up_ref=(0, 1, 0)))
        add(Bone("forearm_twist_%s" % s,
                 Vector(la_head).lerp(Vector(la_tail), 0.55),
                 la_tail, "lowerarm_%s" % s, False, up_ref=(0, 1, 0)))

        # fingers
        for fname in FINGER_NAMES:
            ft = FINGER_TABLE[fname]
            joints = finger_joints(knuckle, fwd, right, up, fname)
            parent = "hand_%s" % s
            for seg in range(3):
                add(Bone("finger_%s_%02d_%s" % (fname, seg + 1, s),
                         joints[seg], joints[seg + 1], parent, True,
                         up_ref=(0, 0, 1)))
                parent = "finger_%s_%02d_%s" % (fname, seg + 1, s)

        # forearm blade mount (right arm only) - the blade mesh runs along
        # this bone, so scaling the bone's Y axis extends it
        if side > 0:
            import mr_body
            ac, _ = mr_body.arm_axis(1)
            frames = parallel_transport_frames(ac)
            d = (ac[-1] - ac[-5]).normalized()
            tg, rt, upv = frames[-5]
            side_v = Vector((1.0, 0.0, 0.0))
            side_v = (side_v - d * side_v.dot(d)).normalized()
            up = d.cross(side_v).normalized()
            bbase = ac[-5] + up * 0.026 - side_v * 0.012
            add(Bone("blade_r", bbase, bbase + d * 0.25, "lowerarm_r", True,
                     up_ref=(0, 0, 1)))

    # ---- legs -------------------------------------------------------------
    for side in (1, -1):
        s = side_suffix(side)
        sx = float(side)
        th_head = (sx * 0.088, 0.0, L["hip"])
        th_tail = (sx * 0.096, 0.003, L["knee"])
        cf_head = th_tail
        cf_tail = (sx * 0.100, 0.0, L["ankle"])
        ft_head = cf_tail
        ft_tail = (sx * 0.100, -0.112, 0.030)
        bl_head = ft_tail
        bl_tail = (sx * 0.100, -0.166, 0.018)
        add(Bone("thigh_%s" % s, th_head, th_tail, "pelvis", True, up_ref=(0, 1, 0)))
        add(Bone("calf_%s" % s, cf_head, cf_tail, "thigh_%s" % s, True, up_ref=(0, 1, 0)))
        add(Bone("foot_%s" % s, ft_head, ft_tail, "calf_%s" % s, True, up_ref=(0, 1, 0)))
        add(Bone("heel_%s" % s, ft_head, (sx * 0.100, 0.048, 0.012),
                 "foot_%s" % s, True, up_ref=(0, 1, 0)))
        add(Bone("ball_%s" % s, bl_head, bl_tail, "foot_%s" % s, True, up_ref=(0, 1, 0)))

    # ---- secondary motion -------------------------------------------------
    add(Bone("hair_01", (0.0, 0.070, 1.735), (0.0, 0.092, 1.640), "head", True,
             up_ref=(0, 1, 0)))
    add(Bone("hair_02", (0.0, 0.092, 1.640), (0.0, 0.098, 1.540), "hair_01", True,
             up_ref=(0, 1, 0)))
    # shoulder cable: the bones follow the authored cable path so secondary
    # motion can be driven along the real curve
    add(Bone("cable_01", (0.000, 0.112, 1.330), (-0.055, 0.135, 1.318), "chest",
             True, up_ref=(0, 1, 0)))
    add(Bone("cable_02", (-0.055, 0.135, 1.318), (-0.115, 0.120, 1.270), "cable_01",
             True, up_ref=(0, 1, 0)))
    add(Bone("cable_03", (-0.115, 0.120, 1.270), (-0.176, 0.010, 1.196), "cable_02",
             True, up_ref=(0, 1, 0)))

    # ---- control rig ------------------------------------------------------
    add(Bone("CTRL_root", (0, 0, 0.0), (0, 0, 0.30), None, False, up_ref=(0, 1, 0)))
    add(Bone("CTRL_pelvis", (0, 0, L["hip"]), (0, 0, L["hip"] + 0.09),
             "CTRL_root", False, up_ref=(0, 1, 0)))
    add(Bone("CTRL_torso", (0, 0, L["spine1"]), (0, 0, 1.40),
             "CTRL_root", False, up_ref=(0, 1, 0)))
    add(Bone("CTRL_neck", (0, 0, L["neck"]), (0, 0, L["neck_top"]),
             "CTRL_torso", False, up_ref=(0, 1, 0)))
    add(Bone("CTRL_head", (0, 0, L["head_pivot"]), (0, -0.06, L["head_pivot"]),
             "CTRL_neck", False, up_ref=(0, 0, 1)))
    add(Bone("CTRL_lookat", (0, -0.60, L["eye"]), (0, -0.66, L["eye"]),
             "CTRL_root", False, up_ref=(0, 0, 1)))
    add(Bone("CTRL_scale", (0.30, 0.0, 0.0), (0.36, 0.0, 0.0), None, False,
             up_ref=(0, 1, 0)))

    for side in (1, -1):
        s = side_suffix(side)
        sx = float(side)
        add(Bone("CTRL_hand_%s" % s, (sx * 0.290, -0.148, 0.799),
                 (sx * 0.310, -0.168, 0.789), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_elbow_%s" % s, (sx * 0.240, -0.420, 1.180),
                 (sx * 0.240, -0.480, 1.180), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_foot_%s" % s, (sx * 0.100, -0.040, 0.060),
                 (sx * 0.100, -0.090, 0.050), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_knee_%s" % s, (sx * 0.100, -0.420, 0.520),
                 (sx * 0.100, -0.470, 0.520), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_heel_%s" % s, (sx * 0.100, 0.030, 0.030),
                 (sx * 0.100, 0.060, 0.020), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_ball_%s" % s, (sx * 0.100, -0.150, 0.030),
                 (sx * 0.100, -0.190, 0.020), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_curl_%s" % s, (sx * 0.240, -0.120, 0.760),
                 (sx * 0.240, -0.160, 0.760), "CTRL_root", False, up_ref=(0, 0, 1)))
        add(Bone("CTRL_spread_%s" % s, (sx * 0.290, -0.120, 0.760),
                 (sx * 0.290, -0.160, 0.760), "CTRL_root", False, up_ref=(0, 0, 1)))
        for fname in FINGER_NAMES:
            add(Bone("CTRL_%s_%s" % (fname, s), (sx * 0.240, -0.120, 0.780),
                     (sx * 0.240, -0.160, 0.780), "CTRL_root", False, up_ref=(0, 0, 1)))
    return bones


DEFORM_BONES = None


def deform_bone_names(specs):
    return [b.name for b in specs if b.deform]


# ---------------------------------------------------------------------------
# armature construction
# ---------------------------------------------------------------------------

def create_armature(specs, name="Operative_Rig"):
    """Create the Blender armature object with all bones and constraints."""
    import bpy
    arm_data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    made = {}
    for b in specs:
        eb = arm_data.edit_bones.new(b.name)
        eb.head = b.head
        eb.tail = b.tail
        eb.roll = 0.0
        eb.use_deform = b.deform
        made[b.name] = eb
    for b in specs:
        if b.parent:
            made[b.parent].use_connect = False
            made[b.name].parent = made[b.parent]
            made[b.name].use_connect = False
    # apply the explicit rest frames
    for b in specs:
        eb = made[b.name]
        eb.head = b.head
        eb.tail = b.tail
        m = b.matrix()
        eb.matrix = m
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj, made


# ---------------------------------------------------------------------------
# constraints (control rig behaviour)
# ---------------------------------------------------------------------------

def _copy_rot(pb, target, mix=1.0, space='LOCAL'):
    c = pb.constraints.new('COPY_ROTATION')
    c.target = _arm_of(target)
    c.subtarget = target
    c.mix_mode = 'REPLACE'
    c.use_x = c.use_y = c.use_z = True
    c.influence = mix
    c.owner_space = space
    c.target_space = space
    return c


_ARM = {"obj": None}


def _arm_of(bone_name):
    return _ARM["obj"]


def build_constraints(obj, specs):
    """Wire the control rig to the deform skeleton."""
    global _ARM
    _ARM["obj"] = obj
    pb = obj.pose.bones

    def target_of(name):
        return obj.pose.bones[name]

    # root / pelvis separation: CTRL_root drives root
    for bc, targets in (("CTRL_root", ("root",)),
                        ("CTRL_pelvis", ("pelvis",)),
                        ("CTRL_torso", ("spine_01", "spine_02", "spine_03", "chest")),
                        ("CTRL_neck", ("neck_01",))):
        c = pb[bc].constraints.new('COPY_ROTATION')
        c.target = obj
        c.subtarget = targets[0]
        c.mix_mode = 'REPLACE'
        c.influence = 0.0
        c.owner_space = 'LOCAL'
        c.target_space = 'LOCAL'

    # head look-at (damped track on the forward pointing head bone)
    c = pb["head"].constraints.new('DAMPED_TRACK')
    c.target = obj
    c.subtarget = "CTRL_lookat"
    c.track_axis = 'TRACK_Y'
    c.influence = 0.0

    # arm / leg IK chains
    for side in (1, -1):
        s = side_suffix(side)
        ik = pb["lowerarm_%s" % s].constraints.new('IK')
        ik.target = obj
        ik.subtarget = "CTRL_hand_%s" % s
        ik.chain_count = 2
        ik.pole_target = obj
        ik.pole_subtarget = "CTRL_elbow_%s" % s
        ik.iterations = 60
        ik.influence = 0.0

        ik = pb["calf_%s" % s].constraints.new('IK')
        ik.target = obj
        ik.subtarget = "CTRL_foot_%s" % s
        ik.chain_count = 2
        ik.pole_target = obj
        ik.pole_subtarget = "CTRL_knee_%s" % s
        ik.iterations = 60
        ik.influence = 0.0

        # foot roll / heel / toe pivots
        for ctrl, dform in (("CTRL_heel_%s" % s, "heel_%s" % s),
                            ("CTRL_ball_%s" % s, "ball_%s" % s)):
            c = pb[dform].constraints.new('COPY_ROTATION')
            c.target = obj
            c.subtarget = ctrl
            c.mix_mode = 'REPLACE'
            c.influence = 0.0
            c.owner_space = 'LOCAL'
            c.target_space = 'LOCAL'

        # finger curl / spread / individual finger controls
        for fname in FINGER_NAMES:
            for seg in (1, 2, 3):
                bn = "finger_%s_%02d_%s" % (fname, seg, s)
                c = pb[bn].constraints.new('COPY_ROTATION')
                c.target = obj
                c.subtarget = "CTRL_%s_%s" % (fname, s)
                c.mix_mode = 'REPLACE'
                c.influence = 0.0
                c.owner_space = 'LOCAL'
                c.target_space = 'LOCAL'

    # global scale driver
    obj["global_scale"] = 1.0
    ui = obj.id_properties_ui("global_scale")
    ui.update(min=0.1, max=3.0, soft_min=0.5, soft_max=2.0,
              description="Uniform scale of the whole Operative")
    fcurve = obj.driver_add('pose.bones["root"].scale', 0)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    var = drv.variables.new()
    var.name = "gs"
    var.type = 'SINGLE_PROP'
    var.targets[0].id = obj
    var.targets[0].data_path = '["global_scale"]'
    drv.expression = "gs"
    for axis in (1, 2):
        fc = obj.driver_add('pose.bones["root"].scale', axis)
        fc.driver.type = 'SCRIPTED'
        v = fc.driver.variables.new()
        v.name = "gs"
        v.type = 'SINGLE_PROP'
        v.targets[0].id = obj
        v.targets[0].data_path = '["global_scale"]'
        fc.driver.expression = "gs"
    return obj


def bone_map(obj):
    """name -> rest matrix in armature space."""
    out = {}
    for b in obj.data.bones:
        out[b.name] = b.matrix_local.copy()
    return out
