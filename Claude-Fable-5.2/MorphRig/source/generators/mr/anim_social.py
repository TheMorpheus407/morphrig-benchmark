"""Emotes and the spoken performance: greet, victory, defeat, dialogue.

The dialogue clip is driven by the alignment of the real audio (source/audio/dialogue_alignment.json): every key
frame of the acting is pinned to a word of the line, the visemes come from the phoneme timings, and the body, the
gaze, the brows and the hands are authored on top of that.
"""
import json
import math
import os
import numpy as np
from .animbuild import register
from .anim_base import stand, with_face, fix_reach, dense_floor
from .pose import Pose, interp_dense, floor_pass
from .animkit import cs
from . import facedefs

AUDIO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'audio'))


def _tc(v):
    return (float(v[0]), float(-v[1]), float(v[2]))


def with_ik_fields(ctx, pose):
    """Fill the IK description (wrist, finger / palm directions, elbow hint) of FK arms from the evaluated rig, so
    a dense interpolation can run a segment in IK when only one of its two keys is an IK key."""
    q = pose.copy()
    need = [b + s for s in ('_l', '_r') for b in ('hand', 'lowerarm', 'upperarm')]
    M = ctx.pose(pose, need)
    for s in ('l', 'r'):
        a = getattr(q, 'arm_' + s)
        if a['ik']:
            continue
        H = M['hand_' + s]
        w, el, sh = H[:3, 3], M['lowerarm_' + s][:3, 3], M['upperarm_' + s][:3, 3]
        e = el - (sh + w) * 0.5
        sg = 1.0 if s == 'l' else -1.0
        a['pos'] = _tc(w)
        a['fingers'] = _tc(H[:3, 1])
        a['palm'] = _tc(H[:3, 0] * sg)
        a['elbow'] = _tc(e / np.linalg.norm(e)) if np.linalg.norm(e) > 1e-3 else (0.35 * sg, -0.75, -0.55)
    return q


def head_point(c, ctx, pose, rest_point):
    """Character-space position of a point that is rigid to the head (given in rest armature space) for a pose."""
    M = ctx.pose(pose, ['head'])['head']
    loc = np.linalg.inv(c.R.rest['head']) @ np.append(np.asarray(rest_point, float), 1.0)
    return _tc((M @ loc)[:3])


def bake_dense(c, seq, layer=None, ik_either=True):
    """Monotone dense interpolation of the key poses, an optional per-frame layer(f, pose), floor constraints."""
    poses = interp_dense(seq, c.frames, ik_either=ik_either)
    if layer is not None:
        for f, p in enumerate(poses):
            layer(f, p)
    floor_pass(poses)
    for f, p in enumerate(poses):
        p.apply(c, f, dense=True)
    return poses


def _face_keys(c, track):
    """track: {control: [(frame, value), ...]} sparse, smoothly interpolated face keys."""
    for name, pts in track.items():
        for f, v in pts:
            c.face(f, **{name: v})


# ------------------------------------------------------------------------------------ greet
@register('greet')
def greet(c, ctx):
    """Casual two-finger salute from the left brow, a nod and a smile."""
    n = c.frames
    S = stand()
    S.face = {}
    up = S.mod(cog=(-0.004, 0.006, -0.010), spine=(-1.5, 5.0, 1.0), head=(-4.0, 4.0, 3.0), clav_l=(7.0, 2.0))
    tip = head_point(c, ctx, up, (0.085, -0.115, 1.722))              # just in front of the left brow
    fd = np.array([-0.62, -0.22, 0.75])
    fd /= np.linalg.norm(fd)
    wrist = tuple(float(tip[i] - 0.178 * fd[i]) for i in range(3))
    up.arm_l.update(ik=True, pos=wrist, fingers=tuple(fd), palm=(-0.25, 0.62, -0.74), elbow=(0.92, 0.10, -0.38))
    up.fing_l.update(curl=0.0, index=0.04, middle=0.06, ring=0.92, pinky=0.95, thumb=0.75, spread=0.0, fist=0.0)
    pre = Pose.blend(S, up, 0.5)
    pre.arm_l = dict(up.arm_l, ik=True, pos=(0.40, 0.26, 1.30), fingers=(0.10, 0.45, 0.88), palm=(-0.5, 0.6, -0.6), elbow=(0.85, -0.2, -0.5))
    pre.fing_l = dict(up.fing_l, index=0.3, middle=0.3)
    out = up.mod(spine=(1.0, 3.0, 0.0), head=(5.0, 2.0, 2.0), clav_l=(3.0, 4.0))
    out.arm_l.update(pos=(0.36, 0.44, 1.56), fingers=(0.20, 0.72, 0.66), palm=(-0.55, 0.60, -0.58), elbow=(0.85, -0.10, -0.52))
    hold = out.mod(head=(1.0, 0.0, 1.0))
    hold.arm_l.update(pos=(0.37, 0.43, 1.53))
    down = Pose.blend(S, out, 0.35)
    down.arm_l = dict(out.arm_l, pos=(0.36, 0.22, 1.08), fingers=(0.25, 0.55, -0.80), palm=(-0.85, -0.35, -0.40), elbow=(0.6, -0.6, -0.5))
    down.fing_l = dict(S.fing_l)
    Sik = with_ik_fields(ctx, S)
    seq = [(0, Sik), (7, pre), (13, up), (18, up.mod(head=(-5.0, 4.0, 3.0))), (24, out), (31, hold), (43, down), (n - 6, Sik), (n, Sik)]
    for _, p in seq:
        p.look = (0.0, 3.0, 1.62)
    bake_dense(c, seq, layer=lambda f, p: setattr(p, 'breath', 0.4 * math.sin(math.pi * f / n)))
    _face_keys(c, {'expr_joy': [(0, 0.0), (10, 0.25), (22, 0.62), (40, 0.50), (n - 4, 0.0)],
                   'brow_outer_up_l': [(0, 0.0), (12, 0.45), (26, 0.30), (46, 0.0)],
                   'brow_outer_up_r': [(0, 0.0), (12, 0.35), (26, 0.22), (46, 0.0)]})
    c.blink(27)
    c.events_replace([('gesture_peak', 24)])


# ------------------------------------------------------------------------------------ victory
@register('victory')
def victory(c, ctx):
    """Fist pump with the cybernetic arm: coil, punch the sky on the toes, pull it down, settle with a grin."""
    n = c.frames
    S = stand()
    S.face = {}
    coil = S.mod(cog=(-0.006, 0.010, -0.085), cog_rot=(7.0, 4.0, 0.0), spine=(9.0, 8.0, 0.0), head=(-4.0, -6.0, 0.0), clav_r=(4.0, 6.0),
                 arm_r=dict(upper=(0.28, -0.30, -0.90), fore=(-0.05, 0.85, 0.50), hand=(0.0, 0.0, 20.0)),
                 arm_l=dict(upper=(0.34, 0.25, -0.90), fore=(0.05, 0.90, 0.40), hand=(0.0, 0.0, 20.0)))
    coil.fing_r.update(curl=1.0, thumb=0.8, fist=1.0)
    coil.fing_l.update(curl=0.85, thumb=0.6, fist=0.6)
    sky = S.mod(cog=(0.004, 0.012, 0.050), cog_rot=(-5.0, -6.0, -2.0), spine=(-9.0, -8.0, -3.0), head=(-14.0, 2.0, 0.0), clav_r=(22.0, -2.0),
                clav_l=(-2.0, -4.0),
                arm_r=dict(upper=(0.26, 0.10, 0.96), fore=(0.12, 0.02, 0.99), hand=(0.0, 0.0, 30.0)),
                arm_l=dict(upper=(0.42, -0.22, -0.88), fore=(0.30, 0.55, -0.55), hand=(0.0, 0.0, 20.0)))
    sky.fing_r.update(curl=1.0, thumb=0.8, fist=1.0)
    sky.fing_l.update(curl=1.0, thumb=0.8, fist=1.0)
    sky.foot_l.update(roll=1.25)
    sky.foot_r.update(roll=1.25)
    hang = sky.mod(cog=(0.004, 0.010, 0.040), head=(-10.0, 0.0, 0.0))
    pull = S.mod(cog=(-0.004, 0.012, -0.060), cog_rot=(5.0, 2.0, 0.0), spine=(7.0, 4.0, 0.0), head=(-2.0, 0.0, 0.0), clav_r=(6.0, 4.0),
                 arm_r=dict(upper=(0.30, 0.20, -0.92), fore=(-0.02, 0.50, 0.86), hand=(10.0, 0.0, 40.0)),
                 arm_l=dict(upper=(0.32, 0.10, -0.94), fore=(0.05, 0.80, 0.45), hand=(0.0, 0.0, 20.0)))
    pull.fing_r.update(curl=1.0, thumb=0.8, fist=1.0)
    pull.fing_l.update(curl=0.9, thumb=0.7, fist=0.8)
    proud = S.mod(cog=(-0.012, 0.004, -0.006), spine=(-3.0, 0.0, 0.0), head=(-6.0, 5.0, 2.0),
                  arm_r=dict(upper=(0.24, 0.10, -0.96), fore=(-0.02, 0.62, 0.78), hand=(6.0, 0.0, 36.0)),
                  arm_l=dict(upper=(0.26, 0.00, -0.97), bend=26.0))
    proud.fing_r.update(curl=1.0, thumb=0.8, fist=1.0)
    seq = [(0, S), (9, coil), (13, Pose.blend(coil, sky, 0.55)), (17, sky), (26, hang), (33, pull), (38, pull.mod(cog=(-0.004, 0.012, -0.072))),
           (52, proud), (70, proud.mod(head=(-4.0, -3.0, 1.0))), (n - 3, S), (n, S)]
    fix_reach([p for _, p in seq])
    for _, p in seq:
        p.look = (0.0, 3.0, 1.62)
    for f in (13, 17, 26):
        seq[[s[0] for s in seq].index(f)][1].look = (-0.4, 1.2, 3.0)
    bake_dense(c, seq, layer=lambda f, p: setattr(p, 'breath', 0.7 * math.sin(math.pi * min(1.0, f / 30.0))), ik_either=False)
    _face_keys(c, {'expr_joy': [(0, 0.0), (9, 0.2), (17, 1.0), (40, 0.9), (70, 0.6), (n - 3, 0.0)],
                   'jaw_open': [(0, 0.0), (11, 0.0), (17, 0.55), (28, 0.45), (36, 0.10), (44, 0.0)],
                   'expr_focus': [(0, 0.0), (9, 0.5), (16, 0.0)],
                   'brow_outer_up_l': [(12, 0.0), (17, 0.5), (40, 0.2), (60, 0.0)],
                   'brow_outer_up_r': [(12, 0.0), (17, 0.5), (40, 0.2), (60, 0.0)]})
    c.blink(47)
    c.blink(76)
    c.events_replace([('gesture_peak', 17), ('foot_l_contact', 31), ('foot_r_contact', 31)])


# ------------------------------------------------------------------------------------ defeat
@register('defeat')
def defeat(c, ctx):
    """Looks up in disbelief, then everything sinks: shoulders, head and knees; a slow head shake before recovering."""
    n = c.frames
    S = stand()
    S.face = {}
    disb = S.mod(cog=(-0.010, -0.012, -0.008), spine=(-6.0, 0.0, 0.0), head=(-16.0, 0.0, 0.0), clav_l=(5.0, -3.0), clav_r=(5.0, -3.0),
                 arm_l=dict(upper=(0.30, 0.10, -0.95), fore=(0.45, 0.55, -0.70), hand=(-20.0, 0.0, -30.0)),
                 arm_r=dict(upper=(0.30, 0.10, -0.95), fore=(0.45, 0.55, -0.70), hand=(-20.0, 0.0, -30.0)))
    disb.fing_l.update(curl=0.08, thumb=0.0, spread=0.7)
    disb.fing_r.update(curl=0.08, thumb=0.0, spread=0.7)
    disb.look = (0.0, 2.0, 3.2)
    sink = S.mod(cog=(-0.016, 0.016, -0.075), cog_rot=(6.0, 0.0, 0.0), hips=(-4.0, 0.0, 0.0), spine=(22.0, 0.0, 0.0), head=(26.0, 0.0, 0.0),
                 clav_l=(-7.0, 10.0), clav_r=(-7.0, 10.0),
                 arm_l=dict(upper=(0.10, 0.20, -0.97), bend=8.0, hand=(10.0, 0.0, 10.0)),
                 arm_r=dict(upper=(0.11, 0.20, -0.97), bend=8.0, hand=(10.0, 0.0, 10.0)))
    sink.fing_l.update(curl=0.35, thumb=0.25, spread=0.0)
    sink.fing_r.update(curl=0.35, thumb=0.25, spread=0.0)
    sink.look = (0.0, 0.8, 0.2)
    sh1 = sink.mod(head=(27.0, 13.0, 2.0), spine=(22.0, 3.0, 0.0))
    sh2 = sink.mod(head=(28.0, -12.0, -2.0), spine=(23.0, -3.0, 0.0))
    sh3 = sink.mod(head=(26.0, 7.0, 1.0), spine=(21.0, 1.0, 0.0), cog=(-0.016, 0.014, -0.068))
    rec = Pose.blend(sink, S, 0.6)
    rec.look = (0.0, 3.0, 1.2)
    seq = [(0, S), (10, disb), (18, disb.mod(head=(-17.0, 2.0, 0.0))), (32, sink), (42, sh1), (51, sh2), (59, sh3), (70, rec), (n - 2, S), (n, S)]
    fix_reach([p for _, p in seq])
    S.look = (0.0, 6.0, 1.66)
    bake_dense(c, seq, layer=lambda f, p: setattr(p, 'breath', 0.9 * math.sin(math.pi * min(1.0, f / 16.0)) if f < 16 else -0.8 * math.sin(math.pi * min(1.0, (f - 16) / 50.0))),
               ik_either=False)
    _face_keys(c, {'expr_surprise': [(0, 0.0), (8, 0.45), (18, 0.30), (28, 0.0)],
                   'expr_concern': [(0, 0.0), (14, 0.2), (32, 0.85), (60, 0.8), (n - 2, 0.0)],
                   'expr_pain': [(22, 0.0), (34, 0.22), (58, 0.12), (72, 0.0)],
                   'jaw_open': [(0, 0.0), (9, 0.22), (20, 0.14), (30, 0.0)],
                   'blink_l': [(26, 0.0), (33, 0.85), (40, 0.55), (62, 0.45), (72, 0.0)],
                   'blink_r': [(26, 0.0), (33, 0.85), (40, 0.55), (62, 0.45), (72, 0.0)]})
    c.events_replace([('gesture_peak', 32)])


# ------------------------------------------------------------------------------------ dialogue
def load_alignment():
    with open(os.path.join(AUDIO_DIR, 'dialogue_alignment.json'), encoding='utf-8') as f:
        return json.load(f)


SEG_INTENSITY = {'urgent': 1.0, 'relief': 0.86, 'confident': 0.95, 'warm': 0.88}


def lipsync_tracks(al, n_frames):
    """{viseme: per-frame weights} from the phoneme alignment.

    * every phoneme opens its viseme a little before it sounds (anticipation) and releases it after it,
    * lip closures (PP) and lip-to-teeth contacts (FF) win over the surrounding vowels and are guaranteed one fully
      formed frame even when the phoneme is shorter than a frame,
    * vowels are scaled by stress, reduced vowels read smaller; the sum of all visemes never exceeds 1."""
    fps = float(al['clip']['fps'])
    f0 = al['clip']['audio_start_frame']
    names = [v for v in facedefs.VISEMES if v != 'sil']
    W = {v: np.zeros(n_frames + 1) for v in names}
    t = (np.arange(n_frames + 1) - f0) / fps
    seg_int = {s['index']: SEG_INTENSITY.get(s['emotion'], 1.0) for s in al['segments']}
    seg_of_word = [w['segment'] for w in al['words']]
    sm = lambda x: x * x * (3 - 2 * x)
    forced = []
    for p in al['phonemes']:
        v = p['viseme']
        if v not in W:
            continue
        s, e = p['start'], p['end']
        g = p.get('strength', 1.0) * seg_int[seg_of_word[p['word']]]
        if p.get('vowel'):
            g *= {'primary': 1.0, 'secondary': 0.90}.get(p.get('stress'), 0.74)
            ta, tr = 0.075, 0.085
        elif v in ('PP', 'FF'):
            ta, tr = 0.060, 0.040
        else:
            ta, tr = 0.055, 0.060
        a = sm(np.clip((t - (s - ta)) / ta, 0.0, 1.0)) * sm(np.clip(((e + tr) - t) / tr, 0.0, 1.0))
        W[v] = np.maximum(W[v], g * a)
        if v in ('PP', 'FF', 'TH'):
            forced.append((int(round(f0 + 0.5 * (s + e) * fps)), v, g))
    for f, v, g in forced:
        if 0 <= f <= n_frames:
            W[v][f] = max(W[v][f], g)
    close = np.clip(W['PP'] * 0.95 + W['FF'] * 0.70 + W['TH'] * 0.35, 0.0, 0.97)
    for v in names:
        if v not in ('PP', 'FF', 'TH'):
            W[v] = W[v] * (1.0 - close)
    tot = sum(W.values())
    k = np.where(tot > 1.0, 1.0 / np.maximum(tot, 1e-6), 1.0)
    for v in names:
        W[v] = W[v] * k
    return W


def _word_frame(al, word, k=0, edge='start'):
    hits = [w for w in al['words'] if w['word'].lower() == word.lower()]
    w = hits[k]
    return al['clip']['audio_start_frame'] + w[edge] * al['clip']['fps']


@register('dialogue')
def dialogue(c, ctx):
    """"Operative to all teams ..." - urgent comms call, a stop gesture, work on the fore-arm console, then relief."""
    al = load_alignment()
    n = c.frames
    fps = al['clip']['fps']
    F0 = al['clip']['audio_start_frame']
    W = lambda word, k=0, edge='start': _word_frame(al, word, k, edge)
    seg_f = [(F0 + s['start'] * fps, F0 + s['end'] * fps) for s in al['segments']]

    S = stand()
    S.face = {}
    cam = (0.0, 3.0, 1.62)

    # --- key poses -------------------------------------------------------------------------------------------
    con_r = dict(ik=False, upper=(0.20, 0.52, -0.83), fore=(-0.86, 0.36, 0.36), hand=(-6.0, 0.0, 62.0))   # console fore-arm
    comm = S.mod(cog=(-0.006, 0.010, -0.016), spine=(5.0, -5.0, 0.0), head=(7.0, -6.0, 0.0), clav_r=(3.0, 10.0), arm_r=con_r,
                 arm_l=dict(upper=(0.20, -0.02, -1.0), bend=24.0, hand=(4.0, 0.0, 12.0)))
    comm.fing_r.update(curl=0.42, thumb=0.30, spread=0.1)
    comm.fing_l.update(curl=0.55, thumb=0.40)
    comm2 = comm.mod(spine=(3.0, -2.0, 0.0), head=(1.0, -2.0, 0.0), cog=(-0.004, 0.014, -0.014))

    relay = S.mod(cog=(0.012, 0.004, -0.010), cog_rot=(-2.0, 6.0, 0.0), spine=(-4.0, 13.0, 2.0), head=(-12.0, 24.0, 2.0), clav_l=(10.0, 2.0),
                  arm_l=dict(upper=(0.52, 0.48, 0.50), fore=(0.46, 0.56, 0.68), hand=(-4.0, 0.0, 40.0)),
                  arm_r=dict(upper=(0.20, 0.36, -0.91), fore=(-0.62, 0.66, 0.20), hand=(-6.0, 0.0, 50.0)))
    relay.fing_l.update(curl=0.0, index=0.0, middle=0.92, ring=0.95, pinky=0.95, thumb=0.70, spread=0.0)
    relay.fing_r.update(curl=0.50, thumb=0.35)
    relay2 = relay.mod(arm_l=dict(upper=(0.50, 0.52, 0.52), fore=(0.44, 0.60, 0.69)), head=(-13.0, 26.0, 2.0))

    wide = S.mod(cog=(-0.004, 0.022, -0.030), cog_rot=(4.0, 0.0, 0.0), spine=(5.0, 0.0, 0.0), head=(-3.0, 0.0, 0.0), clav_l=(7.0, -6.0), clav_r=(7.0, -6.0),
                 arm_l=dict(upper=(0.46, 0.10, -0.88), fore=(0.62, 0.74, -0.24), hand=(-18.0, 0.0, -70.0)),
                 arm_r=dict(upper=(0.40, 0.14, -0.90), fore=(0.52, 0.80, -0.30), hand=(-18.0, 0.0, -70.0)))
    wide.fing_l.update(curl=0.06, thumb=0.0, spread=0.85)
    wide.fing_r.update(curl=0.06, thumb=0.0, spread=0.85)
    wide2 = wide.mod(arm_l=dict(upper=(0.54, 0.06, -0.84), fore=(0.74, 0.64, -0.18)), arm_r=dict(upper=(0.48, 0.10, -0.87), fore=(0.64, 0.72, -0.26)),
                     cog=(-0.004, 0.026, -0.034))

    hold = S.mod(cog=(-0.004, 0.018, -0.022), cog_rot=(3.0, -4.0, 0.0), spine=(4.0, -6.0, 0.0), head=(3.0, 8.0, 0.0), clav_l=(4.0, 14.0),
                 arm_r=dict(upper=(0.24, -0.08, -0.97), bend=30.0, hand=(0.0, 0.0, 14.0)))
    hold.arm_l.update(ik=True, pos=hold.chest_point((0.20, 0.40, 0.11)), fingers=(0.04, 0.16, 0.99), palm=(0.0, 1.0, -0.10), elbow=(0.62, -0.30, -0.72))
    hold.fing_l.update(curl=0.0, thumb=0.0, spread=0.55)
    hold.fing_r.update(curl=0.95, thumb=0.75, fist=0.9)
    hold_push = hold.mod(cog=(-0.004, 0.030, -0.026), spine=(6.0, -6.0, 0.0), head=(5.0, 8.0, 0.0))
    hold_push.arm_l.update(pos=hold_push.chest_point((0.19, 0.47, 0.10)))
    hold_b = hold.mod(head=(2.0, 6.0, 0.0))
    hold_b.arm_l.update(pos=hold_b.chest_point((0.21, 0.41, 0.07)))
    hold_c = hold_push.mod(head=(6.0, 5.0, 0.0))
    hold_c.arm_l.update(pos=hold_c.chest_point((0.19, 0.46, 0.05)))

    give = S.mod(cog=(-0.006, 0.012, -0.016), spine=(4.0, 2.0, 0.0), head=(2.0, -2.0, 1.0), clav_r=(3.0, 10.0), arm_r=con_r)
    give.arm_l.update(ik=True, pos=give.chest_point((0.25, 0.33, 0.12)), fingers=(-0.10, 0.20, 0.97), palm=(-0.90, 0.40, 0.0), elbow=(0.60, -0.35, -0.72))
    give.fing_l.update(curl=0.0, index=0.0, middle=0.95, ring=0.95, pinky=0.95, thumb=0.75, spread=0.0)
    give.fing_r.update(curl=0.42, thumb=0.30)
    give2 = give.mod(head=(6.0, -3.0, 1.0))
    give2.arm_l.update(pos=give2.chest_point((0.24, 0.36, 0.14)))

    # console work: left fingers on the upper side of the right fore-arm (measured on the posed rig)
    work = S.mod(cog=(-0.006, 0.014, -0.024), spine=(11.0, -5.0, 0.0), head=(17.0, -7.0, 0.0), clav_r=(3.0, 12.0), clav_l=(2.0, 12.0), arm_r=con_r)
    work.fing_r.update(curl=0.42, thumb=0.30)
    M = ctx.pose(work, ['lowerarm_r', 'hand_r'])
    el, wr = M['lowerarm_r'][:3, 3], M['hand_r'][:3, 3]
    fdir = np.array([-0.62, -0.50, -0.60])                               # armature space: to the right, forward, down
    fdir /= np.linalg.norm(fdir)

    def tap_pose(along, lift, base=work, press=0.0):
        p = base.copy()
        tip = el + (wr - el) * along + np.array([0.0, 0.0, 0.050 + lift])
        w = tip - fdir * 0.168
        p.arm_l.update(ik=True, pos=_tc(w), fingers=_tc(fdir), palm=(-0.10, -0.42, -0.90), elbow=(0.72, -0.20, -0.66))
        p.fing_l.update(curl=0.62, index=0.20 + press, middle=0.34, ring=0.70, pinky=0.78, thumb=0.45, spread=0.2, fist=0.0)
        return p

    work_look = _tc(el + (wr - el) * 0.55 + np.array([0.0, 0.0, 0.05]))
    there = work.mod(spine=(8.0, -4.0, 0.0), head=(12.0, -6.0, 0.0))
    lift_off = S.mod(cog=(-0.008, 0.006, -0.010), spine=(1.0, -2.0, 0.0), head=(-3.0, 0.0, 2.0), clav_l=(-3.0, 0.0), clav_r=(-3.0, 4.0),
                     arm_r=dict(upper=(0.22, 0.42, -0.88), fore=(-0.66, 0.60, 0.30), hand=(-4.0, 0.0, 40.0)))
    lift_off.arm_l.update(ik=True, pos=lift_off.chest_point((0.27, 0.30, -0.04)), fingers=(0.10, 0.80, 0.55), palm=(-0.55, 0.20, -0.80), elbow=(0.60, -0.45, -0.66))
    lift_off.fing_l.update(curl=0.25, thumb=0.15, spread=0.3)
    lift_off.fing_r.update(curl=0.35, thumb=0.25)

    back = S.mod(cog=(-0.012, 0.002, -0.008), spine=(-1.0, 3.0, -1.0), head=(-2.0, -3.0, 4.0), clav_l=(-4.0, -2.0), clav_r=(-4.0, -2.0),
                 arm_r=dict(upper=(0.22, 0.14, -0.96), fore=(-0.30, 0.86, -0.02), hand=(0.0, 0.0, 30.0)))
    back.arm_l.update(ik=True, pos=back.chest_point((0.30, 0.30, -0.20)), fingers=(0.42, 0.88, 0.14), palm=(0.10, -0.12, 0.98), elbow=(0.50, -0.62, -0.60))
    back.fing_l.update(curl=0.12, thumb=0.0, spread=0.45)
    back.fing_r.update(curl=0.40, thumb=0.30)
    back2 = back.mod(head=(-1.0, -2.0, 3.0))
    back2.arm_l.update(pos=back2.chest_point((0.31, 0.32, -0.23)))

    push = S.mod(cog=(0.000, 0.034, -0.026), cog_rot=(4.0, -9.0, 0.0), spine=(6.0, -12.0, 0.0), head=(-2.0, 16.0, 0.0), clav_l=(6.0, 20.0),
                 arm_r=dict(upper=(0.26, -0.20, -0.94), bend=38.0, hand=(0.0, 0.0, 14.0)))
    push.arm_l.update(ik=True, pos=push.chest_point((0.13, 0.515, 0.10)), fingers=(0.02, 0.99, 0.10), palm=(-0.98, 0.02, -0.18), elbow=(0.55, -0.20, -0.81))
    push.fing_l.update(curl=0.02, thumb=0.10, spread=0.0)
    push.fing_r.update(curl=0.95, thumb=0.75, fist=0.9)
    push_pre = Pose.blend(back, push, 0.35)
    push_pre.arm_l = dict(push.arm_l, pos=push_pre.chest_point((0.24, 0.24, 0.16)), fingers=(0.0, 0.70, 0.71), palm=(-0.98, 0.0, -0.2))
    push_pre.fing_l = dict(push.fing_l)
    push2 = push.mod(head=(0.0, 14.0, 0.0))
    push2.arm_l.update(pos=push2.chest_point((0.13, 0.50, 0.07)))

    thanks = S.mod(cog=(-0.012, 0.004, -0.010), spine=(3.0, 2.0, -2.0), head=(5.0, 2.0, -5.0), clav_l=(3.0, 16.0),
                   arm_r=dict(upper=(0.19, 0.03, -1.0), bend=22.0, hand=(4.0, 0.0, 10.0)))
    thanks.arm_l.update(ik=True, pos=thanks.chest_point((0.118, 0.172, 0.022)), fingers=(-0.78, 0.10, 0.62), palm=(-0.14, -0.985, 0.0), elbow=(0.80, -0.28, -0.53))
    thanks.fing_l.update(curl=0.10, thumb=0.10, spread=0.25)
    thanks.fing_r.update(curl=0.24, thumb=0.16)
    thanks2 = thanks.mod(head=(9.0, 0.0, -6.0), spine=(5.0, 2.0, -2.0))
    thanks2.arm_l.update(pos=thanks2.chest_point((0.118, 0.172, 0.022)))
    thanks3 = thanks.mod(head=(3.0, 1.0, -3.0))
    thanks3.arm_l.update(pos=thanks3.chest_point((0.118, 0.172, 0.022)))
    release = Pose.blend(thanks, S, 0.5)
    release.arm_l = dict(thanks.arm_l, pos=(0.33, 0.20, 1.12), fingers=(0.20, 0.60, -0.78), palm=(-0.90, -0.30, -0.30), elbow=(0.6, -0.6, -0.5))
    release.fing_l = dict(S.fing_l)

    # --- timing: every key is pinned to the audio ---------------------------------------------------------------
    f_all = W('all')
    f_relay = W('relay')
    f_fail = W('failing')
    f_wide = W('wide')
    f_open_e = W('open', 0, 'end')
    f_hold = W('Hold')
    f_pos = W('positions') + 5
    f_give = W('Give')
    f_thirty = W('thirty')
    f_sec_e = W('seconds', 0, 'end')
    f_ill = W("I'll")
    f_self_e = W('myself', 0, 'end')
    f_there = W('There')
    f_signal = W('Signal')
    f_back = W('back')
    f_push = W('Push')
    f_fwd = W('forward')
    f_thank = W('thank')
    f_trust = W('trusting')
    f_me_e = W('me', 1, 'end')

    seq = [(0, S), (F0 + 5, comm), (f_all + 2, comm2), (f_relay - 9, comm2.mod(head=(0.0, 4.0, 0.0))),
           (f_relay + 3, relay), (f_fail + 8, relay2), (f_wide - 14, Pose.blend(relay2, wide, 0.45)),
           (f_wide + 2, wide), (f_open_e, wide2), (f_hold - 5, Pose.blend(wide2, hold, 0.7)),
           (f_hold + 3, hold_push), (f_hold + 9, hold), (f_pos, hold_c), (f_pos + 8, hold_b),
           (f_give - 2, give), (f_thirty + 2, give2)]
    # console: taps on the stressed syllables, then silent work during the pause
    taps = [f_ill + 3, W('stabilize') + 6, W('stabilize') + 13, W('network') + 5, W('myself') + 4, f_self_e + 1,
            f_self_e + 8, f_self_e + 14, f_self_e + 20, f_there + 1]
    alongs = [0.52, 0.40, 0.60, 0.46, 0.66, 0.50, 0.38, 0.62, 0.48, 0.55]
    seq.append((f_sec_e - 2, tap_pose(0.50, 0.035)))
    for i, (tf, al_) in enumerate(zip(taps, alongs)):
        last = i == len(taps) - 1
        base = there if last else work
        if i > 0:
            seq.append((tf - 3, tap_pose(0.5 * (al_ + alongs[i - 1]), 0.026, base=work)))
        seq.append((tf, tap_pose(al_, 0.0, base=base, press=0.12 if last else 0.05)))
    seq += [(f_there + 6, tap_pose(0.55, 0.004, base=there)), (f_there + 15, lift_off), (f_signal + 2, back), (f_back + 10, back2),
            (f_push - 5, push_pre), (f_push + 4, push), (f_fwd + 10, push2), (f_thank - 3, Pose.blend(push2, thanks, 0.55)),
            (f_thank + 6, thanks), (f_trust + 4, thanks2), (f_me_e, thanks3), (n - 9, release), (n - 1, S), (n, S)]
    seq = sorted(seq, key=lambda x: x[0])
    seq = [(f, with_ik_fields(ctx, p)) for f, p in seq]

    # --- gaze: fast saccades between held targets ------------------------------------------------------------------
    looks = [(0, (0.0, 6.0, 1.66)), (F0 + 3, (-0.25, 0.9, 1.30)), (f_all - 3, cam), (f_relay - 4, (2.2, 3.0, 2.9)), (f_fail + 12, (2.0, 3.0, 2.7)),
             (f_wide - 9, (0.6, 5.0, 1.40)), (f_wide + 6, cam), (f_hold - 3, cam), (f_give - 3, cam), (f_thirty + 6, work_look),
             (f_ill + 8, (work_look[0] + 0.05, work_look[1], work_look[2] + 0.01)), (W('network') + 2, (work_look[0] - 0.05, work_look[1], work_look[2])),
             (f_self_e + 10, (work_look[0] + 0.04, work_look[1], work_look[2])), (f_there + 9, cam), (f_back + 14, (-0.5, 3.0, 1.55)), (f_back + 22, cam),
             (f_push - 2, (1.4, 6.0, 1.75)), (f_thank - 2, cam), (f_trust + 6, (0.05, 2.0, 1.30)), (f_trust + 15, cam), (n - 8, (0.0, 6.0, 1.66))]

    def look_at(f):
        k = 0
        while k < len(looks) - 1 and f >= looks[k + 1][0]:
            k += 1
        a = np.array(looks[k][1])
        if k == 0:
            return tuple(a)
        prev = np.array(looks[k - 1][1])
        u = min(1.0, max(0.0, (f - looks[k][0] + 1) / 3.0))            # 3-frame saccade
        u = u * u * (3 - 2 * u)
        return tuple(prev + (a - prev) * u)

    # --- stress accents: small head beats on the primary stressed vowels -----------------------------------------------
    beats = [F0 + p['start'] * fps + 1.5 for p in al['phonemes'] if p.get('vowel') and p.get('stress') == 'primary']
    beat_amp = lambda f: 2.4 if f < f_there else 1.5

    def layer(f, p):
        p.look = look_at(f)
        calm = 1.0 if f < f_there else 0.6
        p.breath = calm * 0.55 * math.sin(2 * math.pi * f / 96.0)
        nod = sum(math.exp(-((f - b) / 2.6) ** 2) for b in beats)
        p.head = (p.head[0] + beat_amp(f) * nod, p.head[1] + 0.9 * math.sin(2 * math.pi * f / 210.0), p.head[2] + 0.5 * math.sin(2 * math.pi * f / 150.0 + 1.0))
        p.cog = (p.cog[0] + 0.004 * math.sin(2 * math.pi * f / 180.0), p.cog[1] + 0.003 * math.sin(2 * math.pi * f / 130.0 + 0.5), p.cog[2])
        p.spine = (p.spine[0] + 0.5 * nod, p.spine[1] + 0.8 * math.sin(2 * math.pi * f / 240.0 + 2.0), p.spine[2])

    bake_dense(c, seq, layer=layer)

    # --- lips: visemes from the phoneme alignment -----------------------------------------------------------------
    Wv = lipsync_tracks(al, n)
    for v, arr in Wv.items():
        for f in range(n + 1):
            c.face(f, **{'vis_' + v: float(arr[f])})
        c.dense.add(('face', 'prop:vis_' + v))
    # small inhale before every phrase, lips pressed while concentrating in the pause
    jaw = [(0, 0.0)]
    for (a, b) in seg_f:
        jaw += [(a - 7, 0.0), (a - 2, 0.10), (a + 1, 0.0)]
    jaw.append((n, 0.0))

    # --- face: brows, lids, expression presets ---------------------------------------------------------------------------
    e_shift = f_there
    trk = {
        'jaw_open': jaw,
        'expr_focus': [(0, 0.0), (F0 + 4, 0.45), (f_relay - 4, 0.25), (f_wide, 0.0), (f_hold - 2, 0.35), (f_give, 0.30), (f_ill, 0.70),
                       (e_shift - 3, 0.75), (e_shift + 8, 0.05), (f_push, 0.35), (f_thank, 0.0), (n, 0.0)],
        'brow_inner_up_l': [(0, 0.0), (f_relay - 2, 0.10), (f_fail, 0.62), (f_wide + 2, 0.70), (f_open_e + 3, 0.30), (f_hold - 2, 0.0), (e_shift, 0.0),
                            (e_shift + 12, 0.20), (f_push, 0.0), (f_thank + 2, 0.34), (f_me_e, 0.30), (n - 6, 0.0)],
        'brow_inner_up_r': [(0, 0.0), (f_relay - 2, 0.10), (f_fail, 0.56), (f_wide + 2, 0.66), (f_open_e + 3, 0.28), (f_hold - 2, 0.0), (e_shift, 0.0),
                            (e_shift + 12, 0.20), (f_push, 0.0), (f_thank + 2, 0.30), (f_me_e, 0.26), (n - 6, 0.0)],
        'brow_down_l': [(0, 0.0), (F0 + 4, 0.20), (f_relay, 0.34), (f_wide, 0.10), (f_hold - 3, 0.20), (f_hold + 2, 0.74), (f_pos + 6, 0.66), (f_give, 0.36),
                        (f_ill, 0.30), (e_shift - 6, 0.34), (e_shift + 3, 0.0), (f_push + 2, 0.24), (f_thank, 0.0), (n, 0.0)],
        'brow_down_r': [(0, 0.0), (F0 + 4, 0.20), (f_relay, 0.28), (f_wide, 0.10), (f_hold - 3, 0.20), (f_hold + 2, 0.74), (f_pos + 6, 0.66), (f_give, 0.36),
                        (f_ill, 0.30), (e_shift - 6, 0.34), (e_shift + 3, 0.0), (f_push + 2, 0.24), (f_thank, 0.0), (n, 0.0)],
        'brow_outer_up_l': [(0, 0.0), (f_wide - 6, 0.0), (f_wide + 2, 0.40), (f_open_e, 0.20), (f_hold - 3, 0.0), (e_shift - 7, 0.0), (e_shift - 1, 0.55),
                            (e_shift + 10, 0.22), (f_back + 6, 0.30), (f_push, 0.10), (f_thank, 0.12), (n - 6, 0.0)],
        'brow_outer_up_r': [(0, 0.0), (f_wide - 6, 0.0), (f_wide + 2, 0.40), (f_open_e, 0.20), (f_hold - 3, 0.0), (e_shift - 7, 0.0), (e_shift - 1, 0.50),
                            (e_shift + 10, 0.20), (f_back + 6, 0.24), (f_push, 0.10), (f_thank, 0.12), (n - 6, 0.0)],
        'eye_wide_l': [(0, 0.0), (f_fail - 2, 0.0), (f_fail + 4, 0.30), (f_wide + 2, 0.50), (f_open_e + 4, 0.10), (f_hold, 0.0), (e_shift - 7, 0.0),
                       (e_shift - 2, 0.55), (e_shift + 6, 0.0), (n, 0.0)],
        'eye_wide_r': [(0, 0.0), (f_fail - 2, 0.0), (f_fail + 4, 0.30), (f_wide + 2, 0.50), (f_open_e + 4, 0.10), (f_hold, 0.0), (e_shift - 7, 0.0),
                       (e_shift - 2, 0.55), (e_shift + 6, 0.0), (n, 0.0)],
        'squint_l': [(0, 0.0), (f_hold - 2, 0.0), (f_hold + 3, 0.34), (f_pos + 8, 0.28), (f_give, 0.10), (n, 0.0)],
        'squint_r': [(0, 0.0), (f_hold - 2, 0.0), (f_hold + 3, 0.34), (f_pos + 8, 0.28), (f_give, 0.10), (n, 0.0)],
        'nose_sneer_l': [(0, 0.0), (f_hold - 2, 0.0), (f_hold + 3, 0.22), (f_pos + 8, 0.14), (f_give, 0.0), (n, 0.0)],
        'nose_sneer_r': [(0, 0.0), (f_hold - 2, 0.0), (f_hold + 3, 0.22), (f_pos + 8, 0.14), (f_give, 0.0), (n, 0.0)],
        'lip_press': [(0, 0.0), (f_self_e + 2, 0.0), (f_self_e + 8, 0.55), (e_shift - 6, 0.50), (e_shift - 2, 0.0), (n, 0.0)],
        'expr_joy': [(0, 0.0), (e_shift - 2, 0.0), (e_shift + 10, 0.50), (f_signal, 0.56), (f_back + 12, 0.62), (f_push - 2, 0.34), (f_fwd + 8, 0.36),
                     (f_thank + 4, 0.72), (f_me_e + 4, 0.80), (n - 9, 0.35), (n - 1, 0.0), (n, 0.0)],
        'expr_concern': [(0, 0.0), (f_fail - 4, 0.0), (f_fail + 6, 0.30), (f_open_e, 0.34), (f_hold - 3, 0.0), (n, 0.0)],
    }
    _face_keys(c, trk)
    for bf in (F0 - 3, f_all - 5, f_relay - 6, f_wide - 11, f_hold - 6, f_give - 6, f_thirty + 4, f_self_e + 4, e_shift + 7, f_back + 13,
               f_push - 5, f_thank - 5, n - 12):
        c.blink(int(round(bf)))
    # slow, warm blink on "trusting"
    for side in ('l', 'r'):
        for f, v in [(f_trust + 3, 0.0), (f_trust + 7, 1.0), (f_trust + 10, 1.0), (f_trust + 16, 0.0)]:
            c.prop('face', 'blink_' + side, int(round(f)), v)
    ev = dict((e['name'], e['frame']) for e in c.meta['events'])
    c.events_replace([('line_start', ev['line_start']), ('gesture_hold', int(round(f_hold + 3))), ('emotion_shift', ev['emotion_shift']),
                      ('gesture_push', int(round(f_push + 4))), ('line_end', ev['line_end'])])
