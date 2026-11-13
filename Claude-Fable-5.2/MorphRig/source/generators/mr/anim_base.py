"""Shared base poses and helpers for the authored clips."""
import copy
import math
import numpy as np
from .pose import Pose, ANK_H, solve_cog_height, leg_stretch, _lerp
from .animkit import cs, cs_rot, q_to_m, q_mul, q_axis
from . import gait, clips as clipdefs, skel


def stand():
    """S: relaxed, attentive stand (weight slightly on the right leg)."""
    p = Pose()
    p.cog = (-0.012, 0.0, -0.012)
    p.hips = (1.0, 0.0, -2.0)
    p.spine = (1.0, 0.0, 2.0)
    p.head = (-1.0, 0.0, 0.0)
    p.arm_l.update(upper=(0.17, 0.03, -1.0), bend=18.0, hand=(4.0, 0.0, 8.0))
    p.arm_r.update(upper=(0.19, 0.02, -1.0), bend=20.0, hand=(4.0, 0.0, 8.0))
    p.fing_l.update(curl=0.26, thumb=0.18, spread=0.1)
    p.fing_r.update(curl=0.22, thumb=0.15, spread=0.1)
    p.look = (0.0, 6.0, 1.66)
    p.breath = 0.0
    p.blade = 0.0
    return p


def ready():
    """R: combat ready stance - left side forward (blade arm guards), emitter arm cocked at the ribs."""
    p = Pose()
    p.foot_l.update(pos=(0.135, 0.105, 0.0), yaw=10.0)
    p.foot_r.update(pos=(-0.150, -0.185, 0.0), yaw=-40.0, roll=0.30)
    p.cog = (-0.012, -0.035, -0.078)
    p.cog_rot = (5.0, -12.0, 0.0)
    p.hips = (3.0, -8.0, 0.0)
    p.spine = (9.0, 9.0, 0.0)
    p.head = (-6.0, 11.0, 0.0)
    p.clav_l = (3.0, 6.0)
    p.clav_r = (2.0, -2.0)
    p.arm_l.update(upper=(0.30, 0.50, -0.82), fore=(-0.42, 0.62, 0.66), hand=(-6.0, 4.0, 18.0))
    p.arm_r.update(upper=(0.30, -0.02, -1.0), fore=(-0.12, 0.92, 0.36), hand=(-4.0, 0.0, 30.0))
    p.fing_l.update(curl=0.62, thumb=0.45, spread=0.0)
    p.fing_r.update(curl=0.50, thumb=0.35, spread=0.0)
    p.face = {'expr_focus': 0.55}
    p.look = (0.0, 6.0, 1.60)
    p.breath = 0.0
    p.blade = 0.0
    return p


def face_reset():
    return {'expr_focus': 0.0, 'expr_joy': 0.0, 'expr_anger': 0.0, 'expr_concern': 0.0, 'expr_surprise': 0.0,
            'expr_pain': 0.0, 'jaw_open': 0.0, 'blink_l': 0.0, 'blink_r': 0.0}


def with_face(p, **kw):
    q = p.copy()
    f = face_reset()
    f.update(q.face)
    f.update(kw)
    q.face = f
    return q


def rot2(v, yaw_deg):
    """Rotate a character-space vector (left, forward, up) about the vertical axis; + = to the left."""
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[1] * s, -v[0] * s + v[1] * c) + tuple(v[2:])


def rotate_pose(p, yaw, pivot=(0.0, 0.0)):
    """Rotate everything that lives in root space about a vertical axis through pivot."""
    q = p.copy()

    def rp(v):
        r = rot2((v[0] - pivot[0], v[1] - pivot[1], v[2]), yaw)
        return (r[0] + pivot[0], r[1] + pivot[1], r[2])
    pel = (skel.J['pelvis'][0] + p.cog[0], -skel.J['pelvis'][1] + p.cog[1], p.cog[2])
    npel = rp(pel)
    q.cog = (npel[0] - skel.J['pelvis'][0], npel[1] + skel.J['pelvis'][1], p.cog[2])
    # yaw composes with the existing pitch/roll: rotate the lean direction as well
    q.cog_rot = (p.cog_rot[0], p.cog_rot[1] + yaw, p.cog_rot[2])
    for s in ('l', 'r'):
        ft = getattr(q, 'foot_' + s)
        ft['pos'] = rp(ft['pos'])
        ft['yaw'] = ft['yaw'] + yaw
        if ft['knee'] is not None:
            ft['knee'] = rot2(ft['knee'], yaw)
        a = getattr(q, 'arm_' + s)
        a['pos'] = rp(a['pos'])
        a['fingers'] = rot2(a['fingers'], yaw)
        a['palm'] = rot2(a['palm'], yaw)
        if a['elbow'] is not None:
            a['elbow'] = rot2(a['elbow'], yaw)
    if q.look is not None:
        q.look = rp(q.look)
    return q


def foot_at(ankle, yaw=0.0, pitch=0.0, lean=0.0, **kw):
    """Foot dict whose ankle joint sits at the given character-space position for an arbitrary orientation."""
    dq = q_mul(q_axis((0, 0, 1), yaw), q_mul(q_axis((1, 0, 0), -pitch), q_axis((0, 1, 0), lean)))
    off = q_to_m(dq) @ np.array([0.0, 0.0, ANK_H])
    off_c = (off[0], -off[1], off[2])
    d = dict(pos=(ankle[0] - off_c[0], ankle[1] - off_c[1], ankle[2] - off_c[2]), yaw=yaw, pitch=pitch, lean=lean,
             roll=0.0, bank=0.0, toe=0.0, knee=None)
    d.update(kw)
    return d


def keys(clip, seq, loop=False):
    """seq: list of (frame, Pose). Applies sparse keys."""
    for f, p in seq:
        p.apply(clip, f)


def breathe(clip, n_cycles, amp=0.5, phase=0.0, frames=None):
    n = frames or clip.frames
    steps = max(4 * n_cycles, 4)
    for i in range(steps + 1):
        f = n * i / steps
        clip.breath(f, amp * math.sin(2 * math.pi * (n_cycles * i / steps + phase)))


def gait_pose(kind, phase, direction='f'):
    meta = clipdefs.BY_ID[('sprint_f' if kind == 'sprint' else kind + '_' + direction)]
    N = gait.CYCLE[kind][direction]
    poses, info = _gait_cache(kind, direction)
    f = int(round(phase * N)) % N
    return poses[f].copy()


_GC = {}


def _gait_cache(kind, direction):
    key = (kind, direction)
    if key not in _GC:
        meta = clipdefs.BY_ID[('sprint_f' if kind == 'sprint' else kind + '_' + direction)]
        N = gait.CYCLE[kind][direction]
        _GC[key] = gait.gait_poses(kind, meta['travel_dir_deg'], meta['nominal_speed'], N)
    return _GC[key]


def fix_reach(poses, limit=0.985):
    solve_cog_height(poses, limit=limit)
    return poses


# ------------------------------------------------------------------------------------ dense helpers
def _cr(a, b, c, d, t):
    """Catmull-Rom through b..c for numbers / tuples / dicts (non numeric values switch at t = 0.5)."""
    if b is None or c is None:
        return copy.deepcopy(c if t >= 0.5 else b)
    if isinstance(b, dict):
        out = {}
        for k in b:
            if k in c:
                out[k] = _cr(a.get(k, b[k]) if isinstance(a, dict) else b[k], b[k], c[k], d.get(k, c[k]) if isinstance(d, dict) else c[k], t)
            else:
                out[k] = copy.deepcopy(b[k])
        return out
    if isinstance(b, bool):
        return c if t >= 0.5 else b
    if isinstance(b, (int, float)):
        a = b if not isinstance(a, (int, float)) or isinstance(a, bool) else a
        d = c if not isinstance(d, (int, float)) or isinstance(d, bool) else d
        return 0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3)
    if isinstance(b, (tuple, list)):
        aa = a if isinstance(a, (tuple, list)) and len(a) == len(b) else b
        dd = d if isinstance(d, (tuple, list)) and len(d) == len(c) else c
        return tuple(_cr(aa[i], b[i], c[i], dd[i], t) for i in range(len(b)))
    return copy.deepcopy(c if t >= 0.5 else b)


def interp(seq, n_frames):
    """Dense list of poses (frame 0..n_frames) through sparse key poses [(frame, Pose)] using Catmull-Rom."""
    seq = sorted(seq, key=lambda t: t[0])
    fr = [s[0] for s in seq]
    ps = [s[1] for s in seq]
    out = []
    for f in range(n_frames + 1):
        k = 0
        while k < len(fr) - 2 and f >= fr[k + 1]:
            k += 1
        f0, f1 = fr[k], fr[k + 1]
        t = min(1.0, max(0.0, (f - f0) / float(max(f1 - f0, 1e-6))))
        a = ps[max(k - 1, 0)]
        d = ps[min(k + 2, len(ps) - 1)]
        p = Pose()
        for key in p.__dict__:
            setattr(p, key, _cr(getattr(a, key), getattr(ps[k], key), getattr(ps[k + 1], key), getattr(d, key), t))
        out.append(p)
    return out


class FootPlan:
    """Foot placement for clips where the floor moves under the character (start/stop/pivot, root-motion dashes).

    shift(f) -> (dx, dy): cumulative displacement of the floor in character space at frame f. A planted foot follows
    the floor exactly; swings interpolate between the lift-off point and the given contact point."""

    def __init__(self, side, pos, yaw, shift, roll=0.0):
        self.side = side
        self.shift = shift
        self.segs = [dict(kind='stance', f0=0, pos=(pos[0], pos[1]), yaw=yaw, roll_in=roll, roll_out=0.0, f1=None)]

    def step(self, f_off, f_on, pos, yaw, lift=0.09, roll_off=1.0, roll_on=-0.35, pitch=-20.0, via=None):
        st = self.segs[-1]
        st['f1'] = f_off
        st['roll_out'] = roll_off
        self.segs.append(dict(kind='swing', f0=f_off, f1=f_on, pos=(pos[0], pos[1]), yaw=yaw, lift=lift, pitch=pitch, roll_on=roll_on, via=via))
        self.segs.append(dict(kind='stance', f0=f_on, pos=(pos[0], pos[1]), yaw=yaw, roll_in=roll_on, roll_out=0.0, f1=None))
        return self

    def _stance_pos(self, seg, f):
        s0 = self.shift(seg['f0'])
        s1 = self.shift(f)
        return (seg['pos'][0] + s1[0] - s0[0], seg['pos'][1] + s1[1] - s0[1])

    def eval(self, f, last_frame):
        sm = lambda t: (lambda u: u * u * (3 - 2 * u))(min(1.0, max(0.0, t)))
        for i, seg in enumerate(self.segs):
            f1 = seg['f1'] if seg['f1'] is not None else last_frame + 1
            if not (seg['f0'] <= f < f1 or (i == len(self.segs) - 1 and f >= seg['f0'])):
                continue
            if seg['kind'] == 'stance':
                xy = self._stance_pos(seg, f)
                r_in = seg['roll_in'] * (1.0 - sm((f - seg['f0']) / 3.0))
                r_out = 0.0
                if seg['f1'] is not None and seg['roll_out']:
                    r_out = seg['roll_out'] * sm((f - (seg['f1'] - 5.0)) / 5.0)
                return dict(pos=(xy[0], xy[1], 0.0), yaw=seg['yaw'], pitch=0.0, roll=(r_out if r_out else r_in), bank=0.0, toe=0.0, knee=None, lean=0.0)
            prev = self.segs[i - 1]
            p0 = self._stance_pos(prev, seg['f0'])
            t = (f - seg['f0']) / float(max(seg['f1'] - seg['f0'], 1))
            e = sm(t)
            if seg.get('via') is not None:
                # styled airborne foot: lift-off -> via pose -> contact
                a = dict(pos=(p0[0], p0[1], 0.0), yaw=prev['yaw'], pitch=0.0, roll=prev['roll_out'], bank=0.0, toe=0.0, knee=None, lean=0.0)
                b = dict(seg['via'])
                d = dict(pos=(seg['pos'][0], seg['pos'][1], 0.0), yaw=seg['yaw'], pitch=0.0, roll=seg['roll_on'], bank=0.0, toe=0.0, knee=None, lean=0.0)
                if t < 0.5:
                    out = _lerp(a, b, sm(t / 0.5))
                else:
                    out = _lerp(b, d, sm((t - 0.5) / 0.5))
                out['knee'] = b.get('knee')
                out['pos'] = (out['pos'][0], out['pos'][1], out['pos'][2] + 0.035 * math.sin(math.pi * t) ** 0.6)
                return out
            xy = (p0[0] + (seg['pos'][0] - p0[0]) * e, p0[1] + (seg['pos'][1] - p0[1]) * e)
            z = seg['lift'] * math.sin(math.pi * t) ** 1.2
            yaw = prev['yaw'] + (seg['yaw'] - prev['yaw']) * e
            roll = prev['roll_out'] * (1.0 - sm(t / 0.45)) + seg['roll_on'] * sm((t - 0.65) / 0.35)
            pitch = seg['pitch'] * math.sin(math.pi * min(1.0, t / 0.7)) * (1 if t < 0.7 else 0)
            lim = math.degrees(math.asin(min(1.0, max(0.0, z - 0.008) / 0.234)))
            pitch = max(pitch, -lim)
            return dict(pos=(xy[0], xy[1], z), yaw=yaw, pitch=pitch, roll=roll, bank=0.0, toe=0.0, knee=None, lean=0.0)
        return None


def apply_dense(clip, poses, plans=(), reach=True, smooth=2):
    """Write per-frame keys; foot plans override the feet; pelvis height is constrained by leg reach."""
    n = len(poses) - 1
    for f, p in enumerate(poses):
        for pl in plans:
            ft = pl.eval(f, n)
            if ft is not None:
                old = getattr(p, 'foot_' + pl.side)
                if old.get('knee') is not None:
                    ft['knee'] = old['knee']
                setattr(p, 'foot_' + pl.side, ft)
    if reach:
        solve_cog_height(poses, limit=0.985, smooth=smooth)
    from .pose import fix_knee
    for p in poses:                       # knees never dip into the floor
        for s in ('l', 'r'):
            fix_knee(p, s, 0.052)
    for f, p in enumerate(poses):
        p.apply(clip, f, dense=True)
    return poses


# ------------------------------------------------------------------------------------ kneeling
def kneel(base, knee='r', lean=50.0, wrist=None, wrist_side='r', back=0.36, knee_z=0.062, yaw=None, reach=0.93):
    """Stable kneel: the 'knee' side knee rests on the ground behind the planted front foot. If a wrist target
    (character space) is given, the torso leans further until that arm can reach it."""
    from .pose import kneel_height, arm_stretch
    p = base.copy()
    front = 'l' if knee == 'r' else 'r'
    sk = 1.0 if knee == 'l' else -1.0
    ff = getattr(p, 'foot_' + front)
    ff.update(roll=0.0, pitch=0.0)
    py = ff['pos'][1] - back
    px = 0.03 * sk
    setattr(p, 'foot_' + knee, tucked(0.150 * sk, py - 0.125, yaw=(-8.0 * -sk if yaw is None else yaw), pitch=-72.0, knee=(0.10 * sk, 1.0, -0.40)))
    ff['knee'] = (0.12 * -sk, 1.0, 0.25)
    cy = base.cog_rot[1]
    sw = 1.0 if wrist_side == 'l' else -1.0
    roll, extra, clav = 0.0, 0.0, (0.0, 0.0)
    for _ in range(40):
        p.cog = (px, py + 0.006, -0.60)
        p.cog_rot = (lean * 0.50 + extra, cy * 0.5, roll)
        p.hips = (lean * 0.10, 0.0, -roll * 0.4)
        p.spine = (lean * 0.42, base.spine[1] * 0.4, roll * 0.6)
        p.head = (-lean * 0.30 - extra * 0.6, base.head[1] * 0.5, -roll)
        if wrist is not None:
            setattr(p, 'clav_' + wrist_side, clav)
        kneel_height(p, knee, knee_z=knee_z)
        if wrist is None or arm_stretch(p, wrist_side, wrist) <= reach:
            break
        if lean < 86.0:
            lean += 4.0
        elif abs(roll) < 14.0:                      # drop the reaching shoulder: side bend + clavicle
            roll += 3.5 * sw
            clav = (max(clav[0] - 3.0, -12.0), min(clav[1] + 5.0, 20.0))
        elif extra < 24.0:                          # fold further at the hips
            extra += 3.0
        else:
            break
    return p


def foot_clear(x, y, yaw=0.0, pitch=0.0, clear=0.03, **kw):
    """Airborne foot at (x, y) whose lowest point (toe or heel) is 'clear' above the ground for the given pitch."""
    a = math.radians(abs(pitch))
    reach = 0.234 if pitch < 0 else 0.046
    z = clear + reach * math.sin(a) + ANK_H * math.cos(a)
    return foot_at((x, y, z), yaw=yaw, pitch=pitch, **kw)


def dense_floor(clip, seq, n=None, reach_frames=None, breath=None):
    """Bake a floor-contact clip densely: monotone interpolation of the key poses, then per-frame floor constraints."""
    from .pose import interp_dense, floor_pass
    n = clip.frames if n is None else n
    poses = interp_dense(seq, n)
    if breath is not None:
        for f, p in enumerate(poses):
            p.breath = breath(f)
    floor_pass(poses)
    if reach_frames:
        sub = [poses[f] for f in range(reach_frames[0], reach_frames[1] + 1)]
        solve_cog_height(sub, limit=0.99, smooth=2)
    for f, p in enumerate(poses):
        p.apply(clip, f, dense=True)
    return poses


def extend_leg(pose, side, out=0.05, direction=-1.0, ankle_z=0.058, stretch=0.997, yaw=0.0, pitch=-172.0, knee=None):
    """Lay a leg out straight from the hip (lying poses). direction -1 = towards the feet-back (prone), +1 = forward (supine)."""
    from .pose import LEG_MAX
    t = pose.torso()
    hip = t['hip'][side]                      # armature space
    sg = 1.0 if side == 'l' else -1.0
    L = LEG_MAX * stretch
    dz = ankle_z - hip[2]
    dx = out * sg
    hy = math.sqrt(max(L * L - dz * dz - dx * dx, 1e-6))
    ank_cs = (hip[0] + dx, -hip[1] + direction * hy, ankle_z)
    ft = foot_at(ank_cs, yaw=yaw, pitch=pitch, knee=knee)
    setattr(pose, 'foot_' + side, ft)
    return ft


def tucked(x, y, yaw=0.0, pitch=-76.0, knee=None, **kw):
    """Kneeling / crawling foot: toes curled under and flat on the floor, heel up. (x, y) = ankle position."""
    a = math.radians(-pitch)
    z = 0.028 + 0.142 * math.sin(a) + (ANK_H - 0.028) * math.cos(a)        # the ball joint rests 2.8 cm above the floor
    return foot_at((x, y, z), yaw=yaw, pitch=pitch, toe=-pitch / 45.0, knee=knee, **kw)
