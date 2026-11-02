"""MorphRig skin binding and facial shape keys.

Weights are computed analytically from the procedural part each vertex
belongs to, which gives predictable deformation (knees bend about the knee,
fingers do not pull the palm) instead of the usual heat-map artefacts.

The facial rig is a hybrid:
  * bones   - eye gaze, eyelid upper/lower, brow, jaw
  * morphs - 8 visemes, 6 expression presets and 14 standalone control
             targets (lip closure / corners / width / pucker / funnel,
             jaw, cheek, brow raise-lower)
"""

import math
from mathutils import Vector

TAU = math.pi * 2.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def g(v, c, s):
    t = (v - c) / s
    return math.exp(-t * t)


def smoothstep(a, b, x):
    if abs(b - a) < 1e-9:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def closest_t(points, co):
    """Normalised index of the closest point on a polyline."""
    best, bi = 1e9, 0
    for i, p in enumerate(points):
        d = (p - co).length_squared
        if d < best:
            best, bi = d, i
    return bi / float(max(len(points) - 1, 1))


def chain_weights(z, nodes, widths):
    """Blend weights across a vertical bone chain.

    nodes   - [(z, bone), ...] ordered bottom to top
    widths  - blend half-width around each joint
    """
    out = {}
    for i, (zc, bone) in enumerate(nodes):
        if i == 0:
            lo = -1e9
            hi = zc + widths[0]
        elif i == len(nodes) - 1:
            lo = zc - widths[-1]
            hi = 1e9
        else:
            lo = zc - widths[i]
            hi = zc + widths[i]
        w = smoothstep(lo, hi, z)
        if w > 0.0:
            out[bone] = out.get(bone, 0.0) + w
    tot = sum(out.values())
    if tot > 1e-9:
        for k in out:
            out[k] /= tot
    return out


def normalize(w):
    tot = sum(w.values())
    if tot < 1e-9:
        return w
    return {k: v / tot for k, v in w.items()}


# ---------------------------------------------------------------------------
# per-part weight rules
# ---------------------------------------------------------------------------

TORSO_NODES = [
    (0.955, "pelvis"),
    (1.055, "spine_01"),
    (1.140, "spine_02"),
    (1.225, "spine_03"),
    (1.305, "chest"),
    (1.400, "neck_01"),
    (1.515, "head"),
]
TORSO_WIDTHS = [0.055, 0.045, 0.040, 0.040, 0.045, 0.050]


def torso_weights(co, side):
    w = chain_weights(co.z, TORSO_NODES, TORSO_WIDTHS)
    # shoulder yoke blends into the clavicle
    shoulder = smoothstep(0.125, 0.170, abs(co.x)) * smoothstep(1.30, 1.37, co.z)
    if shoulder > 0.0:
        s = "r" if side > 0 else "l"
        w["clavicle_%s" % s] = w.get("clavicle_%s" % s, 0.0) + shoulder
        w = normalize(w)
    return w


def head_weights(co):
    w = {"head": 1.0}
    # chin / lower lip follows the jaw
    front = smoothstep(-0.010, -0.045, co.y)
    jaw = smoothstep(1.612, 1.566, co.z) * front
    if jaw > 0.0:
        w = {"head": 1.0 - jaw, "jaw": jaw}
    # the brow ridge follows the brow bones, the animator can lift it
    brow = g(co.z, 1.686, 0.009) * g(abs(co.x) - 0.033, 0.0, 0.020) * front
    if brow > 0.0:
        side = "r" if co.x >= 0.0 else "l"
        w = dict(w)
        w["brow_%s" % side] = brow * 0.55
    return w


def arm_weights(co, side, arm_pts):
    s = "r" if side > 0 else "l"
    t = closest_t(arm_pts, co)
    # elbow sits at ~0.55 of the arm length
    elbow = 0.56
    up = 1.0 - smoothstep(elbow - 0.10, elbow + 0.10, t)
    w = {"upperarm_%s" % s: up, "lowerarm_%s" % s: 1.0 - up}
    clav = (1.0 - smoothstep(0.02, 0.16, t)) * 0.85
    if clav > 0.0:
        w["clavicle_%s" % s] = clav
        w = normalize(w)
    return w


def hand_weights(co, side):
    s = "r" if side > 0 else "l"
    return {"hand_%s" % s: 1.0}


def leg_weights(co, side, leg_pts):
    s = "r" if side > 0 else "l"
    t = closest_t(leg_pts, co)
    knee = 0.50
    up = 1.0 - smoothstep(knee - 0.10, knee + 0.10, t)
    w = {"thigh_%s" % s: up, "calf_%s" % s: 1.0 - up}
    return w


def finger_weights(part, co):
    # part name: finger_<name>_<seg>_<side>
    bits = part.split("_")
    side = bits[-1]
    seg = int(bits[-2])
    fname = "_".join(bits[1:-2])
    bone = "finger_%s_%02d_%s" % (fname, seg, side)
    prev = "finger_%s_%02d_%s" % (fname, max(seg - 1, 1), side)
    if seg == 1:
        return {bone: 1.0}
    return {bone: 0.86, prev: 0.14}


def boot_weights(co, side):
    s = "r" if side > 0 else "l"
    # heel (behind the ankle) -> heel bone, ball/toe -> ball bone
    heel = smoothstep(0.010, -0.030, co.y)
    toe = smoothstep(-0.090, -0.130, co.y)
    w = {"foot_%s" % s: 0.0}
    w["heel_%s" % s] = heel
    w["ball_%s" % s] = toe
    w["foot_%s" % s] = max(0.0, 1.0 - heel - toe)
    w = {k: v for k, v in w.items() if v > 1e-4}
    return normalize(w)


RIGID_PARTS = {
    "eye_r": {"eye_r": 1.0},
    "eye_l": {"eye_l": 1.0},
    "iris_r": {"eye_r": 1.0},
    "iris_l": {"eye_l": 1.0},
    "pupil_r": {"eye_r": 1.0},
    "pupil_l": {"eye_l": 1.0},
    "lid_up_r": {"eyelid_upper_r": 1.0},
    "lid_up_l": {"eyelid_upper_l": 1.0},
    "lid_lo_r": {"eyelid_lower_r": 1.0},
    "lid_lo_l": {"eyelid_lower_l": 1.0},
    "brow_r": {"brow_r": 1.0},
    "brow_l": {"brow_l": 1.0},
    "teeth_up": {"head": 1.0},
    "teeth_lo": {"jaw": 1.0},
    "tongue": {"jaw": 1.0},
    "mouth_cav": {"head": 1.0},
    "blade_r": {"blade_r": 1.0},
    "cell_r": {"hand_r": 1.0},
    "beacon": {"hand_r": 1.0},
    "chest_plate": {"chest": 1.0},
    "back_pack": {"chest": 1.0},
    "collar": {"neck_01": 1.0},
    "belt": {"pelvis": 1.0},
    "belt_pouch": {"thigh_r": 0.0},
    "cyber_arm": {"lowerarm_r": 1.0},
    "emitter": {"lowerarm_r": 1.0},
}


# Hard costume pieces that need a designed, non-uniform binding so they do
# not tear away from the body in demanding poses.
GEAR_BLEND = {
    # part            {bone: weight}
    "pauldron_r": {"clavicle_r": 0.55, "upperarm_r": 0.45},
    "pauldron_l": {"clavicle_l": 0.55, "upperarm_l": 0.45},
    "legplate_r": {"calf_r": 0.80, "thigh_r": 0.20},
    "legplate_l": {"calf_l": 0.80, "thigh_l": 0.20},
    "bootcuff_r": {"calf_r": 0.85, "foot_r": 0.15},
    "bootcuff_l": {"calf_l": 0.85, "foot_l": 0.15},
}


def build_weights(mb, obj, ctx):
    """Create vertex groups and assign weights.  Returns a stats dict."""
    import bpy
    groups = {}
    for b in set(sum([list(w.keys()) for w in []], [])):
        pass
    stats = {"vertices": 0, "max_influences": 0, "unweighted": 0}

    arm_pts = {}
    leg_pts = {}
    for side in (1, -1):
        arm_pts[side] = ctx["arm_pts"][side]
        leg_pts[side] = ctx["leg_pts"][side]

    for i, part in enumerate(mb.part):
        part = part or "body"
        co = mb.verts[i]
        w = None
        if part == "torso":
            w = torso_weights(co, 1 if co.x > 0 else -1)
        elif part == "neck":
            # the neck is the top of the torso, it shares its bone chain
            w = torso_weights(co, 1 if co.x > 0 else -1)
        elif part == "head":
            w = head_weights(co)
        elif part in ("arm_r", "arm_l"):
            side = 1 if part.endswith("_r") else -1
            w = arm_weights(co, side, arm_pts[side])
        elif part in ("hand_r", "hand_l"):
            side = 1 if part.endswith("_r") else -1
            w = hand_weights(co, side)
        elif part.startswith("finger_"):
            w = finger_weights(part, co)
        elif part in ("leg_r", "leg_l"):
            side = 1 if part.endswith("_r") else -1
            w = leg_weights(co, side, leg_pts[side])
        elif part in ("boot_r", "boot_l"):
            side = 1 if part.endswith("_r") else -1
            w = boot_weights(co, side)
        elif part in ("hair_01", "hair_02", "hair_03"):
            n = int(part[-1])
            w = {"hair_%02d" % n: 1.0}
        elif part.startswith("cable_"):
            n = int(part[-1])
            w = {"cable_%02d" % n: 1.0}
        elif part in RIGID_PARTS:
            w = dict(RIGID_PARTS[part])
            w = {k: v for k, v in w.items() if v > 1e-4}
        elif part in GEAR_BLEND:
            w = dict(GEAR_BLEND[part])
        if w is None:
            stats["unweighted"] += 1
            continue
        w = normalize(w)
        if len(w) > 8:
            w = dict(sorted(w.items(), key=lambda kv: -kv[1])[:8])
        stats["vertices"] += 1
        stats["max_influences"] = max(stats["max_influences"], len(w))
        for name, val in w.items():
            if val <= 1e-4:
                continue
            g = groups.get(name)
            if g is None:
                g = obj.vertex_groups.get(name)
                if g is None:
                    g = obj.vertex_groups.new(name=name)
                groups[name] = g
            g.add([i], val, 'REPLACE')
    stats["groups"] = len(groups)
    return stats


# ---------------------------------------------------------------------------
# facial shape keys
# ---------------------------------------------------------------------------

JAW_PIVOT = Vector((0.0, -0.056, 1.603))

# The shape key offsets are authored on the whole body, so they read very
# small on a 230 mm head.  This factor brings them to the scale of a real
# face: a jaw that opens about 10 mm, lips that move about 10 mm and brows
# that travel about 15 mm.  Without it the expressions are invisible in a
# close up.
SHAPE_KEY_GAIN = 3.0


def _mouth_mask(co):
    front = smoothstep(-0.020, -0.055, co.y)
    m = g(co.z, 1.595, 0.020) * g(abs(co.x), 0.0, 0.028)
    return front * m


def _lip_mask(co, zc, hz, hw=0.026):
    front = smoothstep(-0.020, -0.055, co.y)
    return front * g(co.z, zc, hz) * g(abs(co.x), 0.0, hw)


def _corner_mask(co):
    front = smoothstep(-0.020, -0.050, co.y)
    return front * g(co.z, 1.595, 0.016) * g(abs(co.x), 0.026, 0.014)


def _brow_mask(co, side):
    front = smoothstep(-0.040, -0.075, co.y)
    return front * g(co.z, 1.690, 0.014) * g(abs(co.x) - 0.034, 0.0, 0.024)


def _cheek_mask(co, side):
    front = smoothstep(-0.010, -0.050, co.y)
    return front * g(co.z, 1.618, 0.020) * g(abs(co.x) - 0.048, 0.0, 0.024)


def _jaw_region(co):
    front = smoothstep(-0.010, -0.050, co.y)
    return front * smoothstep(1.618, 1.560, co.z)


def _under_eye_mask(co):
    """The skin band directly below the eye, where a squint piles up."""
    front = smoothstep(-0.005, -0.045, co.y)
    return front * g(co.z, 1.638, 0.013) * g(abs(co.x) - 0.030, 0.0, 0.020)


def _rot_about(p, pivot, axis, ang):
    q = Vector((0, 0, 0))
    v = p - pivot
    c, s = math.cos(ang), math.sin(ang)
    ax = Vector(axis).normalized()
    return pivot + v * c + ax.cross(v) * s + ax * (ax.dot(v)) * (1 - c)


# Each entry: name -> function(co) -> Vector offset
def _key_functions():
    K = {}

    def lip_close(co):
        w = _lip_mask(co, 1.595, 0.017)
        if w <= 0.0:
            return Vector((0, 0, 0))
        up = _lip_mask(co, 1.6025, 0.008, 0.024)
        dn = _lip_mask(co, 1.5885, 0.009, 0.026)
        z = (-0.0022 * up) + (0.0022 * dn)
        return Vector((0, 0.0006 * w, z))

    def lip_smile(co):
        c = _corner_mask(co)
        if c <= 0.0:
            return Vector((0, 0, 0))
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((sgn * 0.0026 * c, -0.0010 * c, 0.0040 * c))

    def lip_frown(co):
        c = _corner_mask(co)
        if c <= 0.0:
            return Vector((0, 0, 0))
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((-sgn * 0.0016 * c, 0.0008 * c, -0.0038 * c))

    def lip_wide(co):
        c = _corner_mask(co)
        if c <= 0.0:
            return Vector((0, 0, 0))
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((sgn * 0.0032 * c, 0.0, 0.0))

    def lip_narrow(co):
        c = _corner_mask(co)
        if c <= 0.0:
            return Vector((0, 0, 0))
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((-sgn * 0.0030 * c, 0.0, 0.0))

    def lip_pucker(co):
        m = _mouth_mask(co)
        if m <= 0.0:
            return Vector((0, 0, 0))
        c = _corner_mask(co)
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((-sgn * 0.0026 * c, -0.0042 * m, 0.0))

    def lip_funnel(co):
        m = _mouth_mask(co)
        if m <= 0.0:
            return Vector((0, 0, 0))
        c = _corner_mask(co)
        sgn = 1.0 if co.x >= 0 else -1.0
        return Vector((-sgn * 0.0034 * c, -0.0030 * m, 0.0))

    def jaw_open(co):
        r = _jaw_region(co)
        if r <= 0.0:
            return Vector((0, 0, 0))
        p = _rot_about(co, JAW_PIVOT, (1, 0, 0), math.radians(-13.0))
        return (p - co) * r

    def jaw_open_small(co):
        r = _jaw_region(co)
        if r <= 0.0:
            return Vector((0, 0, 0))
        p = _rot_about(co, JAW_PIVOT, (1, 0, 0), math.radians(-7.0))
        return (p - co) * r

    def cheek(side):
        def f(co):
            w = _cheek_mask(co, side)
            if w <= 0.0:
                return Vector((0, 0, 0))
            sgn = 1.0 if co.x >= 0 else -1.0
            return Vector((0, -0.0008 * w, 0.0030 * w))
        return f

    def brow_up(side):
        def f(co):
            w = _brow_mask(co, side)
            if w <= 0.0:
                return Vector((0, 0, 0))
            sgn = 1.0 if co.x >= 0 else -1.0
            return Vector((-sgn * 0.0010 * w, 0.0, 0.0050 * w))
        return f

    def brow_down(side):
        def f(co):
            w = _brow_mask(co, side)
            if w <= 0.0:
                return Vector((0, 0, 0))
            sgn = 1.0 if co.x >= 0 else -1.0
            return Vector((sgn * 0.0018 * w, 0.0004 * w, -0.0034 * w))
        return f

    def squint(co):
        # the skin under the eye lifts and the cheek below it pushes up
        u = _under_eye_mask(co)
        c = _cheek_mask(co, 1)
        if u <= 0.0 and c <= 0.0:
            return Vector((0, 0, 0))
        return Vector((0, -0.0008 * u, 0.0026 * u + 0.0018 * c))

    K["lip_close"] = lip_close
    K["lip_smile"] = lip_smile
    K["lip_frown"] = lip_frown
    K["lip_wide"] = lip_wide
    K["lip_narrow"] = lip_narrow
    K["lip_pucker"] = lip_pucker
    K["lip_funnel"] = lip_funnel
    K["jaw_open"] = jaw_open
    K["jaw_open_small"] = jaw_open_small
    K["cheek_raise_l"] = cheek(-1)
    K["cheek_raise_r"] = cheek(1)
    K["brow_up_l"] = brow_up(-1)
    K["brow_up_r"] = brow_up(1)
    K["brow_down_l"] = brow_down(-1)
    K["brow_down_r"] = brow_down(1)
    K["squint"] = squint

    # ---- visemes ---------------------------------------------------------
    K["vis_sil"] = lip_close
    K["vis_mb"] = lambda co: (lip_close(co) * 0.7 +
                              Vector((0, 0, 0.0022 * _lip_mask(co, 1.5885, 0.009, 0.026))))
    K["vis_eh"] = lambda co: (jaw_open_small(co) +
                              Vector((0, 0, 0.0026 * _lip_mask(co, 1.5885, 0.010, 0.026))))
    K["vis_ee"] = lambda co: (lip_wide(co) * 0.85 +
                              Vector((0, 0, 0.0014 * _lip_mask(co, 1.5885, 0.010, 0.026))))
    K["vis_oo"] = lambda co: (lip_pucker(co) * 0.95 +
                              Vector((0, 0, 0.0018 * _lip_mask(co, 1.5885, 0.010, 0.026))))
    K["vis_ff"] = lambda co: (lip_close(co) * 0.55 +
                              Vector((0, 0, 0.0032 * _lip_mask(co, 1.5895, 0.010, 0.026))))
    K["vis_th"] = lambda co: (jaw_open_small(co) * 0.45 +
                              Vector((0, 0, 0.0016 * _lip_mask(co, 1.5885, 0.010, 0.026))))
    K["vis_l"] = lambda co: (jaw_open_small(co) * 0.55 +
                              Vector((0, 0, 0.0016 * _lip_mask(co, 1.5885, 0.010, 0.026))))

    # ---- expression presets ---------------------------------------------
    def expr_joy(co):
        d = lip_smile(co) * 1.25
        d += Vector((0, -0.0006 * _cheek_mask(co, 1), 0.0032 * _cheek_mask(co, 1)))
        d += Vector((0, 0, 0.0016 * _brow_mask(co, 1)))
        d += Vector((0, 0, 0.0012 * _lip_mask(co, 1.6025, 0.008, 0.024)))
        return d

    def expr_anger(co):
        d = brow_down(1)(co) * 1.35
        d += lip_close(co) * 1.1
        d += Vector((0, 0, 0.0016 * _lip_mask(co, 1.6025, 0.008, 0.024)))
        d += Vector((-1.0 if co.x >= 0 else 1.0, 0, 0)) * (0.0012 * _cheek_mask(co, 1))
        return d

    def expr_concern(co):
        d = brow_up(1)(co) * 0.80
        d += lip_frown(co) * 1.20
        d += Vector((1.0 if co.x >= 0 else -1.0, 0, 0)) * (0.0018 * _brow_mask(co, 1))
        return d

    def expr_surprise(co):
        d = brow_up(1)(co) * 1.9
        d += jaw_open_small(co) * 1.5
        d += Vector((0, 0, 0.0014 * _lip_mask(co, 1.6025, 0.008, 0.024)))
        d += Vector((0, 0, -0.0022 * _lip_mask(co, 1.5885, 0.009, 0.026)))
        return d

    def expr_pain(co):
        d = brow_up(1)(co) * 1.5
        d += Vector((-1.0 if co.x >= 0 else 1.0, 0, 0)) * (0.0026 * _brow_mask(co, 1))
        d += jaw_open_small(co) * 1.35
        d += lip_frown(co) * 0.9
        return d

    def expr_focus(co):
        d = brow_down(1)(co) * 0.75
        d += lip_close(co) * 0.85
        d += Vector((0, 0, 0.0008 * _lip_mask(co, 1.6025, 0.008, 0.024)))
        return d

    K["expr_joy"] = expr_joy
    K["expr_anger"] = expr_anger
    K["expr_concern"] = expr_concern
    K["expr_surprise"] = expr_surprise
    K["expr_pain"] = expr_pain
    K["expr_focus"] = expr_focus
    return K


VISEME_LIST = ["vis_sil", "vis_mb", "vis_eh", "vis_ee", "vis_oo",
               "vis_ff", "vis_th", "vis_l"]
EXPRESSION_LIST = ["expr_joy", "expr_anger", "expr_concern",
                   "expr_surprise", "expr_pain", "expr_focus"]


def build_shape_keys(obj, mb, face_parts=("head", "brow_r", "brow_l")):
    """Create the facial morph targets on `obj`."""
    import bpy
    key_funcs = _key_functions()
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    idxs = []
    for part in face_parts:
        idxs.extend(mb.part_indices(part))
    idxs = sorted(set(idxs))
    created = []
    for name, fn in key_funcs.items():
        sk = obj.shape_key_add(name=name, from_mix=False)
        sk.value = 0.0
        sk.slider_min = -1.0
        sk.slider_max = 1.0
        for i in idxs:
            co = mb.verts[i]
            off = fn(co)
            if off.length_squared > 0.0:
                sk.data[i].co = co + off * SHAPE_KEY_GAIN
        created.append(name)
    return created
