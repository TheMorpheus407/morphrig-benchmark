"""High level body pose description used by the clip authoring code (character space: left, forward, up)."""
import copy
import math
import numpy as np
from . import skel
from .animkit import cs, cs_rot, q_mul, q_to_m, q_axis

ANK_H = float(skel.J['foot_l'][2])
J = skel.J


def _lerp(a, b, t):
    if a is None or b is None:
        return copy.deepcopy(b if t >= 0.5 else a)
    if isinstance(a, dict):
        out = {}
        for k in set(a) | set(b):
            if k in a and k in b:
                out[k] = _lerp(a[k], b[k], t)
            else:
                out[k] = copy.deepcopy(a.get(k, b.get(k)))
        return out
    if isinstance(a, bool):
        return b if t >= 0.5 else a
    if isinstance(a, (int, float)):
        return a + (b - a) * t
    if isinstance(a, (tuple, list, np.ndarray)):
        return tuple(float(x + (y - x) * t) for x, y in zip(a, b))
    return b if t >= 0.5 else a


class Pose:
    """All fields are plain data so poses can be copied, blended and mirrored."""

    def __init__(self):
        self.cog = (0.0, 0.0, 0.0)
        self.cog_rot = (0.0, 0.0, 0.0)          # pitch, yaw, roll
        self.hips = (0.0, 0.0, 0.0)
        self.spine = (0.0, 0.0, 0.0)
        self.spine_dist = (0.30, 0.35, 0.35)
        self.head = (0.0, 0.0, 0.0)
        self.clav_l = (0.0, 0.0)
        self.clav_r = (0.0, 0.0)
        arm = dict(ik=False, upper=(0.17, 0.02, -1.0), fore=None, bend=16.0, hint=(0.0, 1.0, 0.0), hand=(0.0, 0.0, 0.0),
                   pos=(0.25, 0.1, 1.0), fingers=(0.0, 1.0, 0.0), palm=(0.0, 0.0, -1.0), elbow=None)
        self.arm_l = copy.deepcopy(arm)
        self.arm_r = copy.deepcopy(arm)
        self.arm_r['pos'] = (-0.25, 0.1, 1.0)
        fing = dict(curl=0.22, fist=0.0, spread=0.0, thumb=0.15, index=None, middle=None, ring=None, pinky=None)
        self.fing_l = copy.deepcopy(fing)
        self.fing_r = copy.deepcopy(fing)
        self.foot_l = dict(pos=(0.105, -0.02, 0.0), yaw=7.0, pitch=0.0, roll=0.0, bank=0.0, toe=0.0, knee=None, lean=0.0)
        self.foot_r = dict(pos=(-0.105, -0.02, 0.0), yaw=-7.0, pitch=0.0, roll=0.0, bank=0.0, toe=0.0, knee=None, lean=0.0)
        self.face = {}
        self.look = None
        self.breath = None
        self.blade = None
        self.skip = ()              # e.g. ('arm_l', 'fing_l'): parts authored separately (measured contacts)

    # ---- editing
    def copy(self):
        return copy.deepcopy(self)

    def mod(self, **kw):
        p = self.copy()
        for k, v in kw.items():
            cur = getattr(p, k)
            if isinstance(cur, dict) and isinstance(v, dict):
                cur.update(copy.deepcopy(v))
            else:
                setattr(p, k, copy.deepcopy(v))
        return p

    def mirrored(self):
        p = self.copy()
        mx = lambda v: (-v[0], v[1], v[2])
        p.cog = mx(self.cog)
        p.cog_rot = (self.cog_rot[0], -self.cog_rot[1], -self.cog_rot[2])
        p.hips = (self.hips[0], -self.hips[1], -self.hips[2])
        p.spine = (self.spine[0], -self.spine[1], -self.spine[2])
        p.head = (self.head[0], -self.head[1], -self.head[2])
        p.clav_l, p.clav_r = self.clav_r, self.clav_l
        for a, b in (('arm_l', 'arm_r'), ('arm_r', 'arm_l')):
            src = copy.deepcopy(getattr(self, b))
            src['pos'] = mx(src['pos'])
            src['fingers'] = mx(src['fingers'])
            src['palm'] = mx(src['palm'])
            if src['elbow'] is not None:
                src['elbow'] = mx(src['elbow'])
            setattr(p, a, src)
        p.fing_l, p.fing_r = copy.deepcopy(self.fing_r), copy.deepcopy(self.fing_l)
        for a, b in (('foot_l', 'foot_r'), ('foot_r', 'foot_l')):
            src = copy.deepcopy(getattr(self, b))
            src['pos'] = mx(src['pos'])
            src['yaw'] = -src['yaw']
            src['lean'] = -src['lean']
            if src['knee'] is not None:
                src['knee'] = mx(src['knee'])
            setattr(p, a, src)
        face = {}
        for k, v in self.face.items():
            if k.endswith('_l'):
                face[k[:-2] + '_r'] = v
            elif k.endswith('_r'):
                face[k[:-2] + '_l'] = v
            else:
                face[k] = v
        p.face = face
        if self.look is not None:
            p.look = mx(self.look)
        return p

    @staticmethod
    def blend(a, b, t):
        p = Pose()
        for k in p.__dict__:
            setattr(p, k, _lerp(getattr(a, k), getattr(b, k), t))
        return p

    # ---- torso kinematics (for chest-relative targets and the leg reach solver)
    def torso(self):
        cr = q_to_m(cs_rot(*self.cog_rot))
        cp = J['pelvis'] + cs(self.cog)
        hr = cr @ q_to_m(cs_rot(*self.hips))
        hips = {s: cp + hr @ (J['thigh_' + s] - J['pelvis']) for s in ('l', 'r')}
        R = cr
        p = cp + cr @ (J['spine_01'] - J['pelvis'])
        chain = [('spine_01', 'spine_02'), ('spine_02', 'spine_03')]
        R = R @ q_to_m(cs_rot(*[v * self.spine_dist[0] for v in self.spine]))
        p2 = p + R @ (J['spine_02'] - J['spine_01'])
        R2 = R @ q_to_m(cs_rot(*[v * self.spine_dist[1] for v in self.spine]))
        p3 = p2 + R2 @ (J['spine_03'] - J['spine_02'])
        R3 = R2 @ q_to_m(cs_rot(*[v * self.spine_dist[2] for v in self.spine]))
        return dict(cog_p=cp, cog_R=cr, hip=hips, chest_p=p3, chest_R=R3, pelvis_R=hr)

    def shoulder_R(self, side):
        """Orientation (armature space) of the frame the FK upper arm lives in: chest rotation + clavicle offset."""
        t = self.torso()
        up, fwd = getattr(self, 'clav_' + side)
        sg = 1.0 if side == 'l' else -1.0
        d = q_mul(q_axis((0, 1, 0), -up * sg), q_axis((0, 0, 1), -fwd * sg))
        return t['chest_R'] @ q_to_m(d)

    def shoulder(self, side):
        """Armature-space shoulder joint: the clavicle swings about its own joint on the chest."""
        t = self.torso()
        cl = t['chest_p'] + t['chest_R'] @ (J['clavicle_' + side] - J['spine_03'])
        return cl + self.shoulder_R(side) @ (J['upperarm_' + side] - J['clavicle_' + side])

    def chest_point(self, v):
        """Point given relative to the spine_03 joint in chest axes (left, forward, up) -> character space."""
        t = self.torso()
        w = t['chest_p'] + t['chest_R'] @ cs(v)
        return (float(w[0]), float(-w[1]), float(w[2]))

    def chest_dir(self, v):
        t = self.torso()
        w = t['chest_R'] @ cs(v)
        return (float(w[0]), float(-w[1]), float(w[2]))

    # ---- write to a clip
    def apply(self, clip, f, dense=False):
        tor = self.torso()
        clip.cog(f, self.cog, *self.cog_rot)
        clip.hips(f, *self.hips)
        clip.spine(f, *self.spine, dist=self.spine_dist)
        clip.head(f, *self.head)
        clip.clavicle('l', f, *self.clav_l)
        clip.clavicle('r', f, *self.clav_r)
        for s in ('l', 'r'):
            a = getattr(self, 'arm_' + s)
            if ('arm_' + s) not in self.skip:
                clip.arm_mode(s, f, a['ik'])
                if a['ik']:
                    sh = self.shoulder(s)
                    clip.hand_ik(s, f, a['pos'], a['fingers'], a['palm'], a['elbow'], shoulder=sh)
                else:
                    clip.arm_fk(s, f, a['upper'], a['fore'], a['bend'], a['hint'], a['hand'])
            if ('fing_' + s) not in self.skip:
                fg = getattr(self, 'fing_' + s)
                per = {n: (fg[n] if fg.get(n) is not None else fg['curl']) for n in ('thumb', 'index', 'middle', 'ring', 'pinky')}
                clip.fingers(s, f, fist=fg['fist'], spread=fg['spread'], **per)
            ft = getattr(self, 'foot_' + s)
            clip.foot(s, f, ft['pos'], ft['yaw'], ft['pitch'], ft['roll'], ft['bank'], ft['toe'], ft['knee'], ft['lean'], hip=tor['hip'][s])
        if self.face:
            clip.face(f, **self.face)
        if self.look is not None:
            clip.look(f, self.look)
        if self.breath is not None:
            clip.breath(f, self.breath)
        if self.blade is not None:
            clip.blade(f, self.blade)
        if dense:
            clip.dense.update(set(clip.keys.keys()))


# ------------------------------------------------------------------------------------ leg reach helpers
L_THIGH = float(np.linalg.norm(J['calf_l'] - J['thigh_l']))
L_CALF = float(np.linalg.norm(J['foot_l'] - J['calf_l']))
LEG_MAX = L_THIGH + L_CALF
_HEEL = np.array([0.0, 0.046, -ANK_H])
_BALL = np.array([0.003, -0.142, -ANK_H + 0.028])
_TOE = np.array([0.005, -0.234, -ANK_H])


def _rx(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ankle_position(foot):
    """Armature-space ankle position that the leg IK will be asked to reach for a foot dict (roll included)."""
    yaw, pitch, lean = foot['yaw'], foot['pitch'], foot.get('lean', 0.0)
    dq = q_mul(q_axis((0, 0, 1), yaw), q_mul(q_axis((1, 0, 0), -pitch), q_axis((0, 1, 0), lean)))
    Rm = q_to_m(dq)
    pc = cs(foot['pos']) + Rm @ np.array([0.0, 0.0, ANK_H])
    r = foot.get('roll', 0.0)
    th_h = 30.0 * min(r, 0.0)
    th_t = 60.0 * max(r - 1.0, 0.0)
    th_b = 30.0 * min(max(r, 0.0), 1.0)
    p = np.zeros(3)                                   # ankle in control-local coordinates
    p = _BALL + _rx(th_b) @ (p - _BALL)
    p = _TOE + _rx(th_t) @ (p - _TOE)
    p = _HEEL + _rx(th_h) @ (p - _HEEL)
    return pc + Rm @ p


def leg_stretch(pose):
    """(left, right) distance hip -> ankle target divided by the leg length; > 1 means the IK cannot reach."""
    t = pose.torso()
    out = []
    for s in ('l', 'r'):
        a = ankle_position(getattr(pose, 'foot_' + s))
        out.append(float(np.linalg.norm(a - t['hip'][s])) / LEG_MAX)
    return out


def solve_cog_height(poses, limit=0.985, iters=30, smooth=0.0, loop=False):
    """Lower the cog of each pose (in place) until both legs can reach their targets; optional temporal smoothing."""
    n = len(poses)
    drop = np.zeros(n)
    for i, p in enumerate(poses):
        lo, hi = 0.0, 0.5
        if max(leg_stretch(p)) <= limit:
            continue
        base = p.cog
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            p.cog = (base[0], base[1], base[2] - mid)
            if max(leg_stretch(p)) > limit:
                lo = mid
            else:
                hi = mid
        drop[i] = hi
        p.cog = base
    if smooth > 0 and n > 2:
        # keep the constraint (drop can only grow) while smoothing over time
        for _ in range(int(smooth)):
            d2 = drop.copy()
            for i in range(n):
                a = drop[(i - 1) % n] if loop else drop[max(i - 1, 0)]
                b = drop[(i + 1) % n] if loop else drop[min(i + 1, n - 1)]
                d2[i] = max(drop[i], 0.25 * a + 0.5 * drop[i] + 0.25 * b)
            drop = d2
    for i, p in enumerate(poses):
        if drop[i] > 0:
            p.cog = (p.cog[0], p.cog[1], p.cog[2] - float(drop[i]))
    return drop


def knee_position(pose, side):
    """Armature-space knee joint position for the leg IK (same pole construction as Clip.foot)."""
    t = pose.torso()
    hip = t['hip'][side]
    ft = getattr(pose, 'foot_' + side)
    ank = ankle_position(ft)
    dq = q_mul(q_axis((0, 0, 1), ft['yaw']), q_mul(q_axis((1, 0, 0), -ft['pitch']), q_axis((0, 1, 0), ft.get('lean', 0.0))))
    Rm = q_to_m(dq)
    kd = cs(ft['knee']) if ft.get('knee') is not None else Rm @ np.array([0.0, -1.0, 0.0])
    kd = kd / np.linalg.norm(kd)
    ctl = cs(ft['pos']) + Rm @ np.array([0.0, 0.0, ANK_H])
    pole = (hip + ctl) * 0.5 + kd * 0.55
    d = ank - hip
    L = float(np.linalg.norm(d))
    L = min(L, LEG_MAX * 0.9999)
    a = (L_THIGH ** 2 - L_CALF ** 2 + L * L) / (2 * L)
    h = math.sqrt(max(L_THIGH ** 2 - a * a, 0.0))
    ax = d / max(np.linalg.norm(d), 1e-9)
    pv = pole - hip
    perp = pv - ax * float(np.dot(pv, ax))
    perp = perp / max(np.linalg.norm(perp), 1e-9)
    return hip + ax * a + perp * h


def kneel_height(pose, side, knee_z=0.060, lo=-0.90, hi=0.0):
    """Adjust the cog height (in place) so that the knee of 'side' rests on the ground."""
    base = pose.cog
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        pose.cog = (base[0], base[1], mid)
        if max(leg_stretch(pose)) > 0.995:
            hi = mid
            continue
        z = knee_position(pose, side)[2]
        if z > knee_z:
            hi = mid
        else:
            lo = mid
    pose.cog = (base[0], base[1], 0.5 * (lo + hi))
    return pose


ARM_MAX = float(np.linalg.norm(J['lowerarm_l'] - J['upperarm_l']) + np.linalg.norm(J['hand_l'] - J['lowerarm_l']))


def arm_stretch(pose, side, wrist_cs):
    """distance shoulder -> wrist target divided by the arm length (> 1: the IK hand cannot reach)."""
    t = pose.torso()
    sh = pose.shoulder(side)
    return float(np.linalg.norm(cs(wrist_cs) - sh)) / ARM_MAX


# ------------------------------------------------------------------------------------ floor contact helpers
def _foot_frame(ft):
    dq = q_mul(q_axis((0, 0, 1), ft['yaw']), q_mul(q_axis((1, 0, 0), -ft['pitch']), q_axis((0, 1, 0), ft.get('lean', 0.0))))
    Rm = q_to_m(dq)
    pc = cs(ft['pos']) + Rm @ np.array([0.0, 0.0, ANK_H])
    return pc, Rm


def sole_points(ft):
    """Armature-space heel / ball / toe sole points of a foot dict (roll pivots and toe bend included)."""
    pc, Rm = _foot_frame(ft)
    r = ft.get('roll', 0.0)
    th_h = 30.0 * min(r, 0.0)
    th_t = 60.0 * max(r - 1.0, 0.0)
    th_b = 30.0 * min(max(r, 0.0), 1.0)
    ball_s = np.array([_BALL[0], _BALL[1], -ANK_H])
    heel = _HEEL.copy()
    toe = _TOE.copy()
    toe = _BALL + _rx(-45.0 * ft.get('toe', 0.0)) @ (toe - _BALL)      # the toes hinge at the ball joint
    heel = _BALL + _rx(th_b) @ (heel - _BALL)
    pts = {'heel': heel, 'ball': ball_s.copy(), 'toe': toe}
    for k in pts:
        p = pts[k]
        p = _TOE + _rx(th_t) @ (p - _TOE)
        p = _HEEL + _rx(th_h) @ (p - _HEEL)
        pts[k] = pc + Rm @ p
    return pts


def _rotate_about(v, axis, ang):
    axis = axis / max(np.linalg.norm(axis), 1e-9)
    c, s = math.cos(ang), math.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * float(np.dot(axis, v)) * (1 - c)


def fix_knee(pose, side, min_z=0.052):
    """Swing the knee direction about the hip-ankle axis until the knee is not below the floor."""
    k = knee_position(pose, side)
    if k[2] >= min_z:
        return False
    ft = getattr(pose, 'foot_' + side)
    t = pose.torso()
    hip = t['hip'][side]
    ank = ankle_position(ft)
    axis = ank - hip
    pc, Rm = _foot_frame(ft)
    kd0 = cs(ft['knee']) if ft.get('knee') is not None else Rm @ np.array([0.0, -1.0, 0.0])
    best = None
    for i in range(1, 37):
        for sg in (1.0, -1.0):
            kd = _rotate_about(kd0, axis, sg * math.radians(5.0 * i))
            ft['knee'] = (float(kd[0]), float(-kd[1]), float(kd[2]))
            if knee_position(pose, side)[2] >= min_z:
                best = ft['knee']
                break
        if best is not None:
            break
    if best is None:
        ft['knee'] = (0.0, 0.0, 1.0)
    return True


def _swivel_offset(a, m, b, pole):
    """Signed angle (radians, about the axis a -> b) from the rest mid-joint direction to the rest pole direction.
    The rig's IK constraints carry a pole angle calibrated on the rest pose, so the solved elbow / knee is always
    rotated by this constant against the direction of the pole target."""
    ax = (b - a) / np.linalg.norm(b - a)
    re = (m - a) - ax * float(np.dot(m - a, ax))
    rp = (pole - a) - ax * float(np.dot(pole - a, ax))
    re /= np.linalg.norm(re)
    rp /= np.linalg.norm(rp)
    return math.atan2(float(np.dot(ax, np.cross(re, rp))), float(np.dot(re, rp)))


# rest pole targets as placed by rig.define_bones
ELBOW_SWIVEL = {s: _swivel_offset(J['upperarm_' + s], J['lowerarm_' + s], J['hand_' + s], J['lowerarm_' + s] + np.array([0.0, 0.32, -0.05]))
                for s in ('l', 'r')}


def elbow_position(pose, side):
    a = getattr(pose, 'arm_' + side)
    t = pose.torso()
    sh = pose.shoulder(side)
    w = cs(a['pos'])
    sg = 1.0 if side == 'l' else -1.0
    e = cs(a['elbow']) if a.get('elbow') is not None else cs((0.35 * sg, -0.75, -0.55))
    e = e / np.linalg.norm(e)
    pole = (sh + w) * 0.5 + e * 0.45
    l1 = float(np.linalg.norm(J['lowerarm_l'] - J['upperarm_l']))
    l2 = float(np.linalg.norm(J['hand_l'] - J['lowerarm_l']))
    d = w - sh
    L = min(float(np.linalg.norm(d)), (l1 + l2) * 0.9999)
    aa = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    h = math.sqrt(max(l1 * l1 - aa * aa, 0.0))
    ax = d / max(np.linalg.norm(d), 1e-9)
    pv = pole - sh
    perp = pv - ax * float(np.dot(pv, ax))
    perp = perp / max(np.linalg.norm(perp), 1e-9)
    perp = _rotate_about(perp, ax, -ELBOW_SWIVEL[side])       # the solved elbow, not the pole direction
    return sh + ax * aa + perp * h, sh, w


def fix_elbow(pose, side, min_z=0.036):
    a = getattr(pose, 'arm_' + side)
    if not a.get('ik'):
        return False
    e, sh, w = elbow_position(pose, side)
    if e[2] >= min_z:
        return False
    sg = 1.0 if side == 'l' else -1.0
    e0 = cs(a['elbow']) if a.get('elbow') is not None else cs((0.35 * sg, -0.75, -0.55))
    axis = w - sh
    for i in range(1, 37):
        for s2 in (1.0, -1.0):
            ed = _rotate_about(e0, axis, s2 * math.radians(5.0 * i))
            a['elbow'] = (float(ed[0]), float(-ed[1]), float(ed[2]))
            if elbow_position(pose, side)[0][2] >= min_z:
                return True
    return True


CLAMP_LOG = {'max': 0.0, 'at': None}


def clamp_arm(pose, side, limit=0.985):
    """Pull an IK hand target back onto the reachable sphere around the shoulder (returns the distance moved)."""
    a = getattr(pose, 'arm_' + side)
    if not a.get('ik'):
        return 0.0
    t = pose.torso()
    sh = pose.shoulder(side)
    w = cs(a['pos'])
    d = w - sh
    L = float(np.linalg.norm(d))
    if L <= ARM_MAX * limit:
        return 0.0
    w2 = sh + d * (ARM_MAX * limit / L)
    a['pos'] = (float(w2[0]), float(-w2[1]), float(w2[2]))
    return L - ARM_MAX * limit


def floor_pass(poses, knee_z=0.052, hand_z=0.026, elbow_z=0.036):
    """Keep feet, knees, hands and elbows of every pose on or above the floor (in place); IK hands that the
    body has moved out of reach are released towards the shoulder instead of stretching the arm."""
    CLAMP_LOG['max'] = 0.0
    CLAMP_LOG['at'] = None
    for i, p in enumerate(poses):
        for s in ('l', 'r'):
            moved = clamp_arm(p, s)
            if moved > CLAMP_LOG['max']:
                CLAMP_LOG['max'] = moved
                CLAMP_LOG['at'] = (s, i)
    for p in poses:
        for s in ('l', 'r'):
            ft = getattr(p, 'foot_' + s)
            lo = min(v[2] for v in sole_points(ft).values())
            # an upside-down foot (lying prone) rests on its instep: clamp the ankle instead
            pc, Rm = _foot_frame(ft)
            if Rm[2, 2] < 0.2:
                lo = min(lo, ankle_position(ft)[2] - 0.045)
            if lo < 0.0:
                ft['pos'] = (ft['pos'][0], ft['pos'][1], ft['pos'][2] - lo)
            fix_knee(p, s, knee_z)
            a = getattr(p, 'arm_' + s)
            if a.get('ik'):
                if a['pos'][2] < hand_z:
                    a['pos'] = (a['pos'][0], a['pos'][1], hand_z)
                fix_elbow(p, s, elbow_z + (0.006 if s == 'r' else 0.0))      # the cybernetic fore-arm is thicker
    return poses


# ------------------------------------------------------------------------------------ dense interpolation (monotone cubic)
def canon(pose):
    """Canonical numeric form: FK arms carry explicit fore-arm directions, feet carry explicit knee directions."""
    p = pose.copy()
    for s in ('l', 'r'):
        a = getattr(p, 'arm_' + s)
        u = np.array(a['upper'], float)
        u = u / np.linalg.norm(u)
        if a.get('fore') is None:
            h = np.array(a['hint'], float)
            h = h - u * float(np.dot(h, u))
            if np.linalg.norm(h) < 1e-6:
                h = np.array([0.0, 0.0, 1.0]) - u * u[2]
            h = h / np.linalg.norm(h)
            b = math.radians(a['bend'])
            v = math.cos(b) * u + math.sin(b) * h
            a['fore'] = tuple(float(x) for x in v)
        a['upper'] = tuple(float(x) for x in u)
        if a.get('elbow') is None:
            sg = 1.0 if s == 'l' else -1.0
            a['elbow'] = (0.35 * sg, -0.75, -0.55)
        a.pop('rot_m', None)
        ft = getattr(p, 'foot_' + s)
        if ft.get('knee') is None:
            pc, Rm = _foot_frame(ft)
            kd = Rm @ np.array([0.0, -1.0, 0.0])
            ft['knee'] = (float(kd[0]), float(-kd[1]), float(kd[2]))
        fg = getattr(p, 'fing_' + s)
        for n in ('thumb', 'index', 'middle', 'ring', 'pinky'):
            if fg.get(n) is None:
                fg[n] = fg['curl']
    if p.look is None:
        p.look = (0.0, 6.0, 1.6)
    if p.breath is None:
        p.breath = 0.0
    if p.blade is None:
        p.blade = 0.0
    return p


_SKIP_KEYS = ('ik', 'bend', 'hint', 'skip')


def _flatten(obj, out, path=''):
    if isinstance(obj, dict):
        for k in sorted(obj):
            if k in _SKIP_KEYS:
                continue
            _flatten(obj[k], out, path + '/' + k)
    elif isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return
    elif isinstance(obj, (int, float)):
        out.append((path, float(obj)))
    elif isinstance(obj, (tuple, list)):
        for i, v in enumerate(obj):
            _flatten(v, out, path + '/%d' % i)


def _unflatten(obj, vals, path=''):
    if isinstance(obj, dict):
        return {k: (obj[k] if k in _SKIP_KEYS else _unflatten(obj[k], vals, path + '/' + k)) for k in obj}
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        return vals.get(path, float(obj))
    if isinstance(obj, (tuple, list)):
        return tuple(_unflatten(v, vals, path + '/%d' % i) for i, v in enumerate(obj))
    return obj


def interp_dense(seq, n_frames, ik_either=False):
    """Per-frame poses through sparse keys with monotone cubic interpolation (no overshoot, holds stay still)."""
    from .util import Pchip
    seq = sorted(seq, key=lambda t: t[0])
    frames = [float(f) for f, _ in seq]
    cps = [canon(p) for _, p in seq]
    faces = set()
    for p in cps:
        faces.update(p.face.keys())
    for p in cps:
        for k in faces:
            p.face.setdefault(k, 0.0)
    flat = []
    for p in cps:
        o = []
        _flatten({k: v for k, v in p.__dict__.items()}, o)
        flat.append(o)
    paths = [k for k, _ in flat[0]]
    for o in flat[1:]:
        assert [k for k, _ in o] == paths, 'pose structure differs between keys'
    Y = np.array([[v for _, v in o] for o in flat])
    if len(frames) == 1:
        return [cps[0].copy() for _ in range(n_frames + 1)]
    pc = Pchip(frames, Y)
    out = []
    for f in range(n_frames + 1):
        y = pc(float(f))
        vals = dict(zip(paths, [float(v) for v in y]))
        k = 0
        while k < len(frames) - 1 and f >= frames[k + 1]:
            k += 1
        base = cps[k]
        p = Pose()
        d = _unflatten({kk: vv for kk, vv in base.__dict__.items()}, vals)
        for kk, vv in d.items():
            setattr(p, kk, vv)
        for s in ('l', 'r'):
            a = getattr(p, 'arm_' + s)
            a['ik'] = base.__dict__['arm_' + s]['ik']
            if ik_either and k + 1 < len(cps) and f > frames[k]:
                # a segment that touches an IK key is evaluated in IK (the FK key carries measured IK fields)
                a['ik'] = a['ik'] or cps[k + 1].__dict__['arm_' + s]['ik']
            for key in ('upper', 'fore'):
                v = np.array(a[key], float)
                a[key] = tuple(float(x) for x in v / max(np.linalg.norm(v), 1e-9))
        out.append(p)
    return out
