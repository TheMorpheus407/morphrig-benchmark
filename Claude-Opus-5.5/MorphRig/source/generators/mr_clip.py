"""MorphRig clip container, rig-action writer and skeleton baker (Blender)."""
import math
import numpy as np
import bpy
from mathutils import Matrix, Quaternion

from mr_anim import Realizer, DEG

INTERP = {"BEZIER", "LINEAR", "CONSTANT"}
DISCRETE = ("[parent]",)


class Clip:
    def __init__(self, cid, frames, loop=False, form="one_shot", root="in_place", speed=0.0,
                 layer="full_body", entry="", exit="", notes=""):
        self.id = cid
        self.frames = int(frames)          # last frame index; clip spans 0..frames
        self.loop = loop
        self.form = form
        self.root = root
        self.speed = speed                 # nominal travel speed cm/s
        self.layer = layer
        self.entry = entry
        self.exit = exit
        self.notes = notes
        self.keys = []                     # (frame, pose, interp)
        self.layers = []                   # callables(frame, channels) -> None (in-place additive)
        self.markers = []                  # (frame, name)
        self.dense = False
        self.contacts = {}                 # side -> list of (f0, f1) planted ranges (QA)
        self.extra = {}

    def key(self, frame, pose, interp="BEZIER"):
        assert interp in INTERP
        self.keys.append((float(frame), pose, interp))
        return self

    def marker(self, frame, name):
        self.markers.append((int(round(frame)), name))
        return self

    @property
    def duration(self):
        return self.frames / 30.0


# ---------------------------------------------------------------- channel interpolation
def _is_quat(name):
    return name.endswith(".quat")


def _hermite(p0, p1, m0, m1, t, dt):
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * dt * m0 + (-2 * t3 + 3 * t2) * p1
            + (t3 - t2) * dt * m1)


def evaluate_channels(clip, keyed, frames):
    """keyed: list of (frame, channels, interp) sorted; returns dict name -> (len(frames), k)."""
    names = list(keyed[0][1].keys())
    F = np.array([k[0] for k in keyed])
    out = {}
    n = len(keyed)
    loop = clip.loop
    period = clip.frames
    for nm in names:
        V = np.array([np.asarray(k[1][nm], float) for k in keyed])
        if _is_quat(nm):
            for i in range(1, n):
                if np.dot(V[i], V[i - 1]) < 0:
                    V[i] = -V[i]
        # tangents
        M = np.zeros_like(V)
        for i in range(n):
            if loop:
                ip = (i - 1) % (n - 1) if i == 0 else i - 1
                inx = 1 if i == n - 1 else i + 1
                fp = F[ip] - (period if i == 0 else 0)
                fn = F[inx] + (period if i == n - 1 else 0)
                vp, vn = V[ip], V[inx]
            else:
                if i == 0 or i == n - 1:
                    continue
                fp, fn, vp, vn = F[i - 1], F[i + 1], V[i - 1], V[i + 1]
            m = (vn - vp) / max(fn - fp, 1e-6)
            # clamp at extrema (componentwise)
            d0 = V[i] - vp
            d1 = vn - V[i]
            m = np.where(d0 * d1 <= 0, 0.0, m)
            M[i] = m
        res = np.zeros((len(frames), V.shape[1]))
        for j, f in enumerate(frames):
            if f <= F[0]:
                res[j] = V[0]
                continue
            if f >= F[-1]:
                res[j] = V[-1]
                continue
            i = int(np.searchsorted(F, f, side="right") - 1)
            interp = keyed[i][2]
            if any(nm.endswith(d) for d in DISCRETE):
                interp = "CONSTANT"
            dt = F[i + 1] - F[i]
            t = (f - F[i]) / dt
            if interp == "CONSTANT":
                res[j] = V[i]
            elif interp == "LINEAR":
                res[j] = V[i] * (1 - t) + V[i + 1] * t
            else:
                res[j] = _hermite(V[i], V[i + 1], M[i], M[i + 1], t, dt)
        if _is_quat(nm):
            res /= np.linalg.norm(res, axis=1, keepdims=True)
        out[nm] = res
    return out


# ---------------------------------------------------------------- action writing
def _data_path(ch):
    if ch.endswith(".loc"):
        return f'pose.bones["{ch[:-4]}"].location', 3
    if ch.endswith(".rot"):
        return f'pose.bones["{ch[:-4]}"].rotation_euler', 3
    if ch.endswith(".quat"):
        return f'pose.bones["{ch[:-5]}"].rotation_quaternion', 4
    b, p = ch.split("[", 1)
    return f'pose.bones["{b}"]["{p[:-1]}"]', 1


def _group(ch):
    return ch.split(".")[0].split("[")[0]


def new_action(obj, name):
    act = bpy.data.actions.get(name)
    if act:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new('OBJECT', obj.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type='KEYFRAME')
    cb = strip.channelbag(slot, ensure=True)
    return act, slot, cb


AUTO_CLAMPED = None


def write_fcurves(cb, series, frames, interp="LINEAR", cyclic=False, constant_channels=(), per_key_interp=None):
    """Write keyframes. series: name -> (nkeys, k). per_key_interp: list of interp names per key."""
    global AUTO_CLAMPED
    if AUTO_CLAMPED is None:
        AUTO_CLAMPED = bpy.types.Keyframe.bl_rna.properties['handle_left_type'].enum_items['AUTO_CLAMPED'].value
    frames = np.asarray(frames, float)
    nk = len(frames)
    ids = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}
    for ch, vals in series.items():
        path, k = _data_path(ch)
        for i in range(vals.shape[1]):
            fc = cb.fcurves.new(path, index=i, group_name=_group(ch))
            kp = fc.keyframe_points
            kp.add(nk)
            co = np.empty(2 * nk)
            co[0::2] = frames
            co[1::2] = vals[:, i]
            kp.foreach_set("co", co)
            if any(ch.endswith(d) for d in constant_channels):
                itp = [0] * nk
            elif per_key_interp is not None:
                itp = [ids[x] for x in per_key_interp]
            else:
                itp = [ids[interp]] * nk
            kp.foreach_set("interpolation", itp)
            kp.foreach_set("handle_left_type", [AUTO_CLAMPED] * nk)
            kp.foreach_set("handle_right_type", [AUTO_CLAMPED] * nk)
            if cyclic:
                fc.modifiers.new('CYCLES')
            fc.update()


def snap_ik_to_fk(realizer, ch):
    """Pose matching: put c_hand_ik / elbow pole where the FK arm puts the hand, and
    c_foot_ik / knee pole where FK-authored legs put the foot (legs stay in IK mode)."""
    sides = ch.pop("@snap", [])
    legs = ch.pop("@snap_leg", [])
    if not sides and not legs:
        return ch
    rig = realizer.rig
    pbs = rig.pose.bones
    if rig.animation_data:
        rig.animation_data.action = None
    for name, val in ch.items():
        if name.endswith(".loc"):
            pbs[name[:-4]].location = tuple(val)
        elif name.endswith(".rot"):
            pbs[name[:-4]].rotation_euler = tuple(val)
        elif name.endswith(".quat"):
            pbs[name[:-5]].rotation_quaternion = tuple(val)
        else:
            b, p = name.split("[", 1)
            pbs[b][p[:-1]] = float(val[0])
    bpy.context.view_layer.update()
    from mr_anim import mat_to_quat
    Rst = realizer.m.rest
    for s in legs:
        Fw = np.array(pbs[f"c_foot_fk_{s}"].matrix)
        rel = np.linalg.inv(Rst[f"c_foot_ik_{s}"]) @ Rst[f"mch_ankle_ik_{s}"]
        Cw = Fw @ np.linalg.inv(rel)
        B = np.linalg.inv(Rst[f"c_foot_ik_{s}"]) @ Cw
        ch[f"c_foot_ik_{s}.loc"] = B[:3, 3]
        ch[f"c_foot_ik_{s}.quat"] = mat_to_quat(B[:3, :3])
        ch[f"c_foot_ik_{s}[roll]"] = np.array([0.0])
        ch[f"c_ball_ik_{s}.rot"] = ch.get(f"c_ball_fk_{s}.rot", np.zeros(3)).copy()
        hip = np.array(pbs[f"c_thigh_fk_{s}"].matrix)[:3, 3]
        knee = np.array(pbs[f"c_calf_fk_{s}"].matrix)[:3, 3]
        ank = Fw[:3, 3]
        dvec = knee - 0.5 * (hip + ank)
        nn = np.linalg.norm(dvec)
        fwd = Fw[:3, 1]
        dirv = dvec / nn if nn > 2e-3 else fwd
        pole_w = knee + dirv * 0.45
        relp = np.linalg.inv(Rst[f"c_foot_ik_{s}"]) @ Rst[f"c_knee_pole_{s}"]
        Wp = Cw @ relp
        ch[f"c_knee_pole_{s}.loc"] = (np.linalg.inv(Wp) @ np.append(pole_w, 1.0))[:3]
    for s in sides:
        Hw = np.array(pbs[f"hand_{s}"].matrix)
        sh = np.array(pbs[f"upperarm_{s}"].matrix)[:3, 3]
        el = np.array(pbs[f"lowerarm_{s}"].matrix)[:3, 3]
        rest = realizer.hand_rest[s]
        B = np.linalg.inv(rest) @ Hw
        ch[f"c_hand_ik_{s}.loc"] = B[:3, 3]
        ch[f"c_hand_ik_{s}.quat"] = mat_to_quat(B[:3, :3])
        mid = 0.5 * (sh + Hw[:3, 3])
        dvec = el - mid
        nrm_ = np.linalg.norm(dvec)
        pole = el + (dvec / nrm_ if nrm_ > 1e-4 else np.array([0, 1.0, 0])) * 0.4
        pr = realizer.m.rest[f"c_elbow_pole_{s}"]
        ch[f"c_elbow_pole_{s}.loc"] = (np.linalg.inv(pr) @ np.append(pole, 1.0))[:3] - \
            (np.linalg.inv(pr) @ np.append(pr[:3, 3], 1.0))[:3]
    return ch


def prepare_keys(realizer, clip):
    keys = sorted(clip.keys, key=lambda k: k[0])
    keyed = [(f, snap_ik_to_fk(realizer, realizer.realize(p)), it) for f, p, it in keys]
    if clip.loop and keyed[-1][0] != clip.frames:
        keyed.append((float(clip.frames), keyed[0][1], keyed[0][2]))
    return keyed


def write_keyed(rig, clip, keyed, name=None):
    """Write realized keys (channel dicts) as the control-rig action."""
    name = name or f"RIG_{clip.id}"
    act, slot, cb = new_action(rig, name)
    series = None
    if clip.dense or clip.layers:
        frames = np.arange(0, clip.frames + 1)
        series = evaluate_channels(clip, keyed, frames)
        for layer in clip.layers:
            layer(frames, series)
        write_fcurves(cb, series, frames, interp="LINEAR", cyclic=False, constant_channels=DISCRETE)
    else:
        names = list(keyed[0][1].keys())
        fr = [k[0] for k in keyed]
        series = {}
        for nm in names:
            V = np.array([np.asarray(k[1][nm], float) for k in keyed])
            if _is_quat(nm):
                for i in range(1, len(V)):
                    if np.dot(V[i], V[i - 1]) < 0:
                        V[i] = -V[i]
            series[nm] = V
        write_fcurves(cb, series, fr, cyclic=clip.loop, constant_channels=DISCRETE,
                      per_key_interp=[k[2] for k in keyed])
    act.frame_range = (0, clip.frames)
    act.use_frame_range = True
    act.use_cyclic = clip.loop
    for f, nm in clip.markers:
        m = act.pose_markers.new(nm)
        m.frame = f
    act["mr_clip"] = clip.id
    act["mr_form"] = clip.form
    act["mr_loop"] = int(clip.loop)
    act["mr_root"] = clip.root
    act["mr_speed_cms"] = float(clip.speed)
    act["mr_layer"] = clip.layer
    return act, series


def write_rig_action(rig, realizer, clip, name=None):
    """Realize key poses (+ procedural layers) and write the control-rig action."""
    keyed = prepare_keys(realizer, clip)
    return write_keyed(rig, clip, keyed, name)


def assign_action(obj, act):
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = act
    if act.slots:
        obj.animation_data.action_slot = act.slots[0]


# ---------------------------------------------------------------- baking
def bake_skeleton(skel, rig, f0, f1, props=()):
    """Sample the constrained export skeleton; return dict of local basis arrays + props."""
    sc = bpy.context.scene
    bones = [pb.name for pb in skel.pose.bones]
    rest = {b.name: b.matrix_local.copy() for b in skel.data.bones}
    parent = {b.name: (b.parent.name if b.parent else None) for b in skel.data.bones}
    rest_local = {}
    for n in bones:
        p = parent[n]
        rest_local[n] = rest[n] if p is None else rest[p].inverted() @ rest[n]
    rest_local_inv = {n: m.inverted() for n, m in rest_local.items()}
    nf = f1 - f0 + 1
    loc = {n: np.zeros((nf, 3)) for n in bones}
    rot = {n: np.zeros((nf, 4)) for n in bones}
    scl = {n: np.zeros((nf, 3)) for n in bones}
    world = {n: np.zeros((nf, 4, 4)) for n in bones}
    pv = {p: np.zeros(nf) for p in props}
    for i, f in enumerate(range(f0, f1 + 1)):
        sc.frame_set(f)
        mats = {n: skel.pose.bones[n].matrix.copy() for n in bones}
        for n in bones:
            p = parent[n]
            local = mats[n] if p is None else mats[p].inverted() @ mats[n]
            basis = rest_local_inv[n] @ local
            l, q, s = basis.decompose()
            if i > 0:
                prev = rot[n][i - 1]
                if prev[0] * q.w + prev[1] * q.x + prev[2] * q.y + prev[3] * q.z < 0:
                    q = -q
            loc[n][i] = l
            rot[n][i] = (q.w, q.x, q.y, q.z)
            scl[n][i] = s
            world[n][i] = np.array(mats[n])
        for p in props:
            pv[p][i] = float(rig.pose.bones["c_face"].get(p, 0.0))
    return dict(bones=bones, loc=loc, rot=rot, scl=scl, world=world, props=pv)


def write_baked_action(skel, baked, name, f0=0):
    act, slot, cb = new_action(skel, name)
    nf = len(next(iter(baked["loc"].values())))
    frames = np.arange(f0, f0 + nf)
    series = {}
    for n in baked["bones"]:
        series[f"{n}.loc"] = baked["loc"][n]
        series[f"{n}.quat"] = baked["rot"][n]
        series[f"{n}.scl"] = baked["scl"][n]
    # custom writer for scale paths
    for ch, vals in series.items():
        if ch.endswith(".scl"):
            path = f'pose.bones["{ch[:-4]}"].scale'
        else:
            path, _ = _data_path(ch)
        for i in range(vals.shape[1]):
            fc = cb.fcurves.new(path, index=i, group_name=_group(ch))
            kp = fc.keyframe_points
            kp.add(nf)
            co = np.empty(2 * nf)
            co[0::2] = frames
            co[1::2] = vals[:, i]
            kp.foreach_set("co", co)
            kp.foreach_set("interpolation", [1] * nf)
            fc.update()
    act.frame_range = (f0, f0 + nf - 1)
    act.use_frame_range = True
    return act
