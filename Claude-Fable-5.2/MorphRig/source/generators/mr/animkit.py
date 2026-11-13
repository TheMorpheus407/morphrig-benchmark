"""Animation authoring kit for RIG_Operative.

Poses are written in *character space*: x = left, y = forward, z = up (metres), rotations as
(pitch forward, yaw left, roll left) in degrees. The kit converts them to control-bone channels, stores
sparse (Bezier) or dense keys and writes one Blender action per clip. Nothing here evaluates the scene.
"""
import math
import numpy as np
from . import skel, rig as rigmod, clips as clipdefs

FPS = clipdefs.FPS


# ------------------------------------------------------------------------------------ math helpers
def q_axis(axis, deg):
    a = math.radians(deg) * 0.5
    ax = np.asarray(axis, dtype=np.float64)
    ax = ax / max(np.linalg.norm(ax), 1e-12)
    return np.array([math.cos(a), ax[0] * math.sin(a), ax[1] * math.sin(a), ax[2] * math.sin(a)])


def q_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def q_conj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def q_to_m(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def m_to_q(m):
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])
    return q / np.linalg.norm(q)


def q_between(a, b):
    """Shortest arc rotation taking unit vector a to b."""
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    c = np.cross(a, b)
    d = float(np.dot(a, b))
    if d < -0.999999:
        ax = np.cross(a, [1, 0, 0])
        if np.linalg.norm(ax) < 1e-6:
            ax = np.cross(a, [0, 1, 0])
        return q_axis(ax, 180.0)
    q = np.array([1.0 + d, c[0], c[1], c[2]])
    return q / np.linalg.norm(q)


def q_slerp(a, b, t):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    d = float(np.dot(a, b))
    if d < 0:
        b = -b
        d = -d
    if d > 0.9995:
        q = a + (b - a) * t
        return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    return (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)


def cs(v):
    """character space (left, forward, up) -> Blender armature space."""
    return np.array([v[0], -v[1], v[2]], dtype=np.float64)


def cs_rot(pitch=0.0, yaw=0.0, roll=0.0):
    """Body-axis delta rotation as a quaternion in armature space.
    pitch + = lean forward, yaw + = turn left, roll + = lean to the left."""
    qy = q_axis((0, 0, 1), yaw)
    qp = q_axis((1, 0, 0), pitch)
    qr = q_axis((0, 1, 0), roll)
    return q_mul(qy, q_mul(qp, qr))


def smooth01(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------------------------ rig rest data
class RigRest:
    def __init__(self):
        defs = rigmod.define_bones()
        self.rest = {}
        self.parent = {}
        for d in defs:
            fr = skel.frame_from(d['tail'] - d['head'], d['zhint'])
            m = np.eye(4)
            m[:3, :3] = fr
            m[:3, 3] = d['head']
            self.rest[d['name']] = m
            self.parent[d['name']] = d['parent']
        self.J = {k: np.array(v, float) for k, v in skel.J.items()}

    def R(self, bone):
        return self.rest[bone][:3, :3]

    def head(self, bone):
        return self.rest[bone][:3, 3].copy()

    def fk_basis(self, bone, delta_q):
        """Pose-basis quaternion for an FK bone given a delta rotation expressed in armature axes."""
        qr = m_to_q(self.R(bone))
        return q_mul(q_conj(qr), q_mul(delta_q, qr))

    def root_basis(self, bone, pos=None, rot_m=None, delta_q=None):
        """Basis (loc, quat) for a bone parented to the (unposed) root from an armature-space target."""
        M = self.rest[bone]
        Rr = M[:3, :3]
        loc = None
        if pos is not None:
            loc = Rr.T @ (np.asarray(pos, float) - M[:3, 3])
        q = None
        if rot_m is not None:
            q = m_to_q(Rr.T @ rot_m)
        elif delta_q is not None:
            q = m_to_q(Rr.T @ q_to_m(delta_q) @ Rr)
        return loc, q


_REST = None


def rest():
    global _REST
    if _REST is None:
        _REST = RigRest()
    return _REST


def reset_rest():
    global _REST
    _REST = None


# ------------------------------------------------------------------------------------ clip container
class Clip:
    """Keys for one action. Channels: (bone, 'loc') -> 3 floats, (bone, 'rot') -> quaternion wxyz,
    (bone, 'scale') -> 3 floats, (bone, 'prop:<name>') -> float."""

    def __init__(self, cid, frames=None):
        self.id = cid
        self.meta = clipdefs.BY_ID[cid]
        self.frames = int(frames if frames is not None else self.meta['frames'])
        self.loop = self.meta['form'] == 'loop'
        self.keys = {}          # channel -> {frame: value}
        self.dense = set()      # channels written with linear per-frame keys
        self.events = [dict(e) for e in self.meta['events']]
        self.prop_tracks = []
        self.notes = {}
        self.R = rest()

    # ---- raw keys
    def key(self, bone, chan, frame, value):
        self.keys.setdefault((bone, chan), {})[float(frame)] = np.atleast_1d(np.asarray(value, dtype=np.float64)).copy()

    def prop(self, bone, name, frame, value):
        self.key(bone, 'prop:' + name, frame, [float(value)])

    def set_event(self, name, frame):
        for e in self.events:
            if e['name'] == name:
                e['frame'] = int(frame)
                return
        self.events.append(dict(name=name, frame=int(frame)))

    def events_replace(self, lst):
        self.events = [dict(name=n, frame=int(f)) for (n, f) in lst]

    # ---- torso
    def cog(self, f, pos=(0, 0, 0), pitch=0.0, yaw=0.0, roll=0.0):
        """pos = offset from the rest pelvis position (left, forward, up)."""
        loc, q = self.R.root_basis('cog', pos=self.R.head('cog') + cs(pos), delta_q=cs_rot(pitch, yaw, roll))
        self.key('cog', 'loc', f, loc)
        self.key('cog', 'rot', f, q)

    def root(self, f, pos=(0, 0, 0), yaw=0.0):
        self.key('root', 'loc', f, cs(pos))
        self.key('root', 'rot', f, cs_rot(0, yaw, 0))

    def fk(self, bone, f, pitch=0.0, yaw=0.0, roll=0.0, q=None):
        d = q if q is not None else cs_rot(pitch, yaw, roll)
        self.key(bone, 'rot', f, self.R.fk_basis(bone, d))

    def hips(self, f, pitch=0.0, yaw=0.0, roll=0.0):
        self.fk('hips', f, pitch, yaw, roll)

    def spine(self, f, pitch=0.0, yaw=0.0, roll=0.0, dist=(0.30, 0.35, 0.35)):
        for b, w in zip(('spine_01', 'spine_02', 'spine_03'), dist):
            self.fk(b, f, pitch * w, yaw * w, roll * w)

    def head(self, f, pitch=0.0, yaw=0.0, roll=0.0, neck=0.4):
        self.fk('neck_01', f, pitch * neck, yaw * neck, roll * neck)
        self.fk('head', f, pitch * (1 - neck), yaw * (1 - neck), roll * (1 - neck))

    def clavicle(self, side, f, up=0.0, fwd=0.0):
        """shoulder girdle: up = shrug (deg), fwd = protraction (deg)."""
        sg = 1.0 if side == 'l' else -1.0
        d = q_mul(q_axis((0, 1, 0), -up * sg), q_axis((0, 0, 1), -fwd * sg))
        self.fk('clavicle_' + side, f, q=d)

    def breath(self, f, v):
        self.prop('cog', 'breath', f, v)

    # ---- arms
    def arm_mode(self, side, f, ik):
        self.prop('hand_ik_' + side, 'arm_ik', f, 1.0 if ik else 0.0)

    def arm_fk(self, side, f, upper=(0.15, 0.0, -1.0), fore=None, bend=12.0, hint=(0.0, 1.0, 0.0), hand=(0.0, 0.0, 0.0)):
        """FK arm in chest space (left, forward, up); 'left' is mirrored for the right arm so + always means outwards.
        upper = upper-arm direction, fore = fore-arm direction (or bend angle towards hint when None),
        hand = (flexion, radial deviation, pronation) in degrees."""
        sg = 1.0 if side == 'l' else -1.0
        R = self.R
        u = cs((upper[0] * sg, upper[1], upper[2]))
        u = u / np.linalg.norm(u)
        h = cs((hint[0] * sg, hint[1], hint[2]))
        h = h - u * np.dot(h, u)
        if np.linalg.norm(h) < 1e-6:
            h = cs((0.0, 0.0, 1.0)) - u * np.dot(cs((0.0, 0.0, 1.0)), u)
        h = h / np.linalg.norm(h)
        if fore is not None:
            v = cs((fore[0] * sg, fore[1], fore[2]))
            v = v / np.linalg.norm(v)
        else:
            a = math.radians(bend)
            v = math.cos(a) * u + math.sin(a) * h
        x = np.cross(u, v)
        if np.linalg.norm(x) < 1e-5:
            x = np.cross(u, h)
        x = x / np.linalg.norm(x)
        z = np.cross(x, u)
        M = np.stack([x, u, z], axis=1)
        ub = 'upperarm_fk_' + side
        self.key(ub, 'rot', f, m_to_q(R.R(ub).T @ M))
        theta = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))
        rest_theta = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(R.R(ub)[:, 1], R.R('lowerarm_fk_' + side)[:, 1]))))))
        self.key('lowerarm_fk_' + side, 'rot', f, q_axis((1, 0, 0), theta - rest_theta))
        hx = q_axis((0, 0, 1), -hand[0] * sg)
        hd = q_axis((1, 0, 0), hand[1])
        ht = q_axis((0, 1, 0), hand[2] * sg)
        self.key('hand_fk_' + side, 'rot', f, q_mul(ht, q_mul(hx, hd)))

    def hand_matrix(self, side, fingers, palm):
        """Armature-space rotation matrix of a hand from the pointing direction of the fingers and the direction
        the palm faces (character space)."""
        y = cs(fingers)
        y = y / np.linalg.norm(y)
        p = cs(palm)
        p = p - y * np.dot(p, y)
        p = p / max(np.linalg.norm(p), 1e-9)
        x = p if side == 'l' else -p
        z = np.cross(x, y)
        return np.stack([x, y, z], axis=1)

    def hand_ik(self, side, f, pos, fingers=(0, 1, 0), palm=(0, 0, -1), elbow=None, rot_m=None, shoulder=None):
        """IK hand: wrist position (character space), orientation from fingers/palm directions,
        elbow = direction hint for the elbow (character space)."""
        R = self.R
        hb = 'hand_ik_' + side
        M = rot_m if rot_m is not None else self.hand_matrix(side, fingers, palm)
        loc, q = R.root_basis(hb, pos=cs(pos), rot_m=M)
        self.key(hb, 'loc', f, loc)
        self.key(hb, 'rot', f, q)
        sg = 1.0 if side == 'l' else -1.0
        sh = R.J['upperarm_' + side] if shoulder is None else np.asarray(shoulder, float)
        mid = (sh + cs(pos)) * 0.5
        e = cs(elbow) if elbow is not None else cs((0.35 * sg, -0.75, -0.55))
        e = e / np.linalg.norm(e)
        pl, _ = R.root_basis('elbow_pole_' + side, pos=mid + e * 0.45)
        self.key('elbow_pole_' + side, 'loc', f, pl)

    def fingers(self, side, f, curl=None, fist=None, spread=None, **per):
        fb = 'fingers_' + side
        if fist is not None:
            self.prop(fb, 'fist', f, fist)
        if spread is not None:
            self.prop(fb, 'spread', f, spread)
        if curl is not None:
            for n in rigmod.FINGER_NAMES:
                self.prop(fb, 'curl_' + n, f, curl)
        for n, v in per.items():
            self.prop(fb, 'curl_' + n, f, v)

    # ---- legs
    def foot(self, side, f, pos, yaw=0.0, pitch=0.0, roll=0.0, bank=0.0, toe=0.0, knee=None, lean=0.0, hip=None):
        """IK foot. pos = position of the sole point under the ankle (left, forward, up above ground).
        yaw + = toes turned to the left, pitch + = toes up (rotation of the control itself),
        roll = heel(-)/ball/toe(+) roll property, bank = edge roll property, lean = sideways tilt (deg)."""
        R = self.R
        fb = 'foot_ik_' + side
        ank_h = R.J['foot_' + side][2]
        dq = q_mul(q_axis((0, 0, 1), yaw), q_mul(q_axis((1, 0, 0), -pitch), q_axis((0, 1, 0), lean)))
        Rm = q_to_m(dq)
        p = cs(pos) + Rm @ np.array([0.0, 0.0, ank_h])
        loc, q = R.root_basis(fb, pos=p, delta_q=dq)
        self.key(fb, 'loc', f, loc)
        self.key(fb, 'rot', f, q)
        self.prop(fb, 'roll', f, roll)
        self.prop(fb, 'bank', f, bank)
        self.prop(fb, 'toe_bend', f, toe)
        kd = cs(knee) if knee is not None else Rm @ np.array([0.0, -1.0, 0.0])
        kd = kd / np.linalg.norm(kd)
        hip = R.J['thigh_' + side] if hip is None else np.asarray(hip, float)
        mid = (hip + p) * 0.5
        pl, _ = R.root_basis('knee_pole_' + side, pos=mid + kd * 0.55)
        self.key('knee_pole_' + side, 'loc', f, pl)

    # ---- face
    def face(self, f, **vals):
        for k, v in vals.items():
            self.prop('face', k, f, v)

    def look(self, f, target):
        """eye target position in character space (left, forward, up)."""
        loc, _ = self.R.root_basis('look_target', pos=cs(target))
        self.key('look_target', 'loc', f, loc)

    def blink(self, f, dur=5, amount=1.0):
        for side in ('l', 'r'):
            self.prop('face', 'blink_' + side, f - 1, 0.0)
            self.prop('face', 'blink_' + side, f + 1, amount)
            self.prop('face', 'blink_' + side, f + dur, 0.0)

    # ---- props
    def blade(self, f, extend):
        self.key('blade_l', 'loc', f, [0.0, skel.BLADE_TRAVEL * extend, 0.0])

    def prop_hold(self, prop, holder, f, on):
        """Attach (1) / release (0) a prop to a hand through its HOLD bone. Keys are stepped by doubling."""
        self.prop(prop, 'hold_' + holder, f, 1.0 if on else 0.0)

    def hold_grip(self, prop, holder, f, prop_in_hand):
        """Set the HOLD bone so that the prop sits at the 4x4 matrix prop_in_hand (hand bone space)."""
        R = self.R
        hb = 'HOLD_%s_%s' % (prop, holder)
        rest_local = np.linalg.inv(R.rest[holder]) @ R.rest[hb]
        basis = np.linalg.inv(rest_local) @ prop_in_hand
        self.key(hb, 'loc', f, basis[:3, 3])
        self.key(hb, 'rot', f, m_to_q(basis[:3, :3]))

    def prop_world(self, prop, f, M):
        """Key a prop control so that it sits at armature-space matrix M, assuming its rest parent is at rest pose
        relative to M (use only while the parent is unposed, e.g. beacon left on the ground uses prop_root instead)."""
        R = self.R
        basis = np.linalg.inv(R.rest[prop]) @ M
        self.key(prop, 'loc', f, basis[:3, 3])
        self.key(prop, 'rot', f, m_to_q(basis[:3, :3]))

    def prop_basis(self, prop, f, basis):
        self.key(prop, 'loc', f, basis[:3, 3])
        self.key(prop, 'rot', f, m_to_q(basis[:3, :3] / np.linalg.norm(basis[:3, :3], axis=0, keepdims=True)))

    # ---- utilities
    def copy_frame(self, src, dst, channels=None):
        for ch, d in self.keys.items():
            if channels is not None and ch not in channels:
                continue
            if float(src) in d:
                d[float(dst)] = d[float(src)].copy()

    def hold(self, src, dst):
        self.copy_frame(src, dst)

    def close_loop(self):
        """Loops: make the last frame equal the first for every channel."""
        n = float(self.frames)
        for ch, d in self.keys.items():
            if 0.0 in d:
                d[n] = d[0.0].copy()


def all_channels(clip):
    return sorted(clip.keys.keys())


# ------------------------------------------------------------------------------------ writing actions
# tolerances of the key reduction of dense channels: metres, quaternion components, property units
DENSE_TOL = {'loc': 1.0e-4, 'rot': 1.5e-4, 'scale': 1.0e-4, 'prop': 2.0e-3}


def write_action(clip, rig_ob, name=None):
    """Create the editable source action for the control rig from a Clip."""
    import bpy
    from . import animio
    act, slot, cb = animio.new_action(name or clip.id, rig_ob, 'OBJECT')
    n = clip.frames
    for (bone, chan), d in sorted(clip.keys.items()):
        frames = np.array(sorted(d.keys()))
        vals = np.array([d[f] for f in frames])
        dense = (bone, chan) in clip.dense
        if chan == 'rot':
            for i in range(1, len(vals)):
                if np.dot(vals[i], vals[i - 1]) < 0:
                    vals[i] = -vals[i]
        fr, vl = frames, vals
        if clip.loop and not dense and len(frames) >= 2 and frames[0] == 0.0 and frames[-1] == float(n):
            # cyclic padding so the auto handles at the loop point match (C1 continuous cycle)
            pre = frames[-2] - n
            post = frames[1] + n
            v_pre, v_post = vals[-2].copy(), vals[1].copy()
            if chan == 'rot':
                if np.dot(v_pre, vals[0]) < 0:
                    v_pre = -v_pre
                if np.dot(v_post, vals[-1]) < 0:
                    v_post = -v_post
            fr = np.concatenate([[pre], frames, [post]])
            vl = np.vstack([v_pre, vals, v_post])
        interp = 'LINEAR' if dense else 'BEZIER'
        if dense and len(fr) > 2:
            # per-frame solved channels: drop the keys that linear interpolation reproduces anyway
            tol = DENSE_TOL.get(chan, DENSE_TOL['prop'])
            idx = animio.reduce_keys(fr, vl, tol)
            fr, vl = fr[idx], vl[idx]
        if chan == 'loc':
            path, group = animio.bone_path(bone, 'location'), bone
        elif chan == 'rot':
            path, group = animio.bone_path(bone, 'rotation_quaternion'), bone
        elif chan == 'scale':
            path, group = animio.bone_path(bone, 'scale'), bone
        else:
            path, group = 'pose.bones["%s"]["%s"]' % (bone, chan[5:]), bone
        for k in range(vl.shape[1]):
            animio.set_curve(cb, path, k, fr, vl[:, k], group, interp=interp, compress=False)
    act.frame_start = 0
    act.frame_end = n
    act.use_frame_range = True
    try:
        act.use_cyclic = bool(clip.loop)
    except Exception:
        pass
    act['morphrig_clip'] = clip.id
    return act, slot
