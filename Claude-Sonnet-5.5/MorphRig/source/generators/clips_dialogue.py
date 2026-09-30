"""The spoken performance clip ('dialogue'): lips, eyes, expression, hands and body authored against the real audio.

Everything is driven by source/audio/dialogue_alignment.json (produced by make_dialogue.py from the TTS duration predictor):
  * lip sync   phoneme events -> per-viseme dominance curves (Cohen-Massaro style blending, hard closure for bilabials and labiodentals)
               -> the viseme weights are keyed on ctl_face (viseme_*) and mapped to the face controls with skeleton_def.VISEMES
  * expression cross-fades between the six presets, brow flashes and nods on stressed words
  * eyes       saccades between gaze targets, micro-saccades, blinks, lids follow the gaze
  * hands      gestures placed on the words they belong to (IK arms, finger poses), body lean, breathing and weight shift
Face and gaze channels are keyed densely and reduced with a small tolerance; arms and body use sparse authored keys."""
import json
import math
import os

import numpy as np

import anim_lib as AL
import face_lib as FL
import skeleton_def as S
from anim_lib import Pose, lerp_pose
from anim_registry import clip
from clips_basic import relaxed, FK, TAU
from keypose import resolve, build_clip, foot_rest

FPS = 30
ALIGN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audio', 'dialogue_alignment.json')

# ----------------------------------------------------------------------------- small numeric helpers


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def curve(points, ts):
    """Smoothstep interpolation through (t, value) points, held before the first and after the last."""
    pts = sorted(points)
    tt = np.array([p[0] for p in pts], dtype=float)
    vv = np.array([p[1] for p in pts], dtype=float)
    i = np.clip(np.searchsorted(tt, ts, side='right') - 1, 0, len(tt) - 2)
    span = np.maximum(tt[i + 1] - tt[i], 1e-6)
    s = smooth((ts - tt[i]) / span)
    out = vv[i] + (vv[i + 1] - vv[i]) * s
    out = np.where(ts <= tt[0], vv[0], out)
    out = np.where(ts >= tt[-1], vv[-1], out)
    return out


def steps(events, ts, dur=0.10):
    """Value holds, then eases to the next value over `dur` seconds starting at the event time (saccade-like moves)."""
    ev = sorted(events)
    out = np.full(len(ts), ev[0][1], dtype=float)
    for k in range(1, len(ev)):
        t0, v0, v1 = ev[k][0], ev[k - 1][1], ev[k][1]
        s = smooth((ts - t0) / dur)
        out = np.where(ts >= t0, v0 + (v1 - v0) * s, out)
        ev[k] = (t0, v1)
    return out


def bump(ts, t0, dur, amp=1.0):
    x = (ts - t0) / dur
    return amp * np.where((x > 0) & (x < 1), np.sin(np.pi * np.clip(x, 0, 1)) ** 2, 0.0)


def lowpass(x, tau, dt):
    a = 1.0 - math.exp(-dt / tau)
    y = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def reduce_track(frames, values, eps):
    """Ramer-Douglas-Peucker on (frame, value): keep the frames needed to stay within eps of the dense track."""
    n = len(frames)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        f = frames[a:b + 1].astype(float)
        interp = values[a] + (values[b] - values[a]) * (f - frames[a]) / max(frames[b] - frames[a], 1)
        dev = np.abs(values[a:b + 1] - interp)
        k = int(np.argmax(dev))
        if dev[k] > eps:
            keep[a + k] = True
            stack.append((a, a + k))
            stack.append((a + k, b))
    return [(int(frames[i]), float(values[i])) for i in np.nonzero(keep)[0]]


# ----------------------------------------------------------------------------- alignment access


class Timing:
    def __init__(self, info):
        self.info = info
        self.words = info['words']

    def find(self, text, occ=0):
        hits = [w for w in self.words if w['text'].lower() == text.lower()]
        return hits[occ]

    def start(self, text, occ=0):
        return self.find(text, occ)['start']

    def end(self, text, occ=0):
        return self.find(text, occ)['end']


# ----------------------------------------------------------------------------- lip sync
# (dominance strength, width factor): closure shapes are strong and narrow so they win at their moment; tongue-only consonants are weak
# so the lips keep following the vowels around them.
DOM = {'PP': (1.9, 0.60), 'FF': (1.6, 0.65), 'TH': (1.0, 0.75), 'DD': (0.55, 0.75), 'KK': (0.55, 0.75), 'CH': (0.95, 0.85), 'SS': (0.85, 0.80),
       'RR': (0.90, 0.90), 'AA': (1.0, 0.95), 'EE': (1.0, 0.95), 'IH': (0.9, 0.95), 'OH': (1.0, 0.95), 'OO': (1.0, 0.95), 'sil': (0.9, 0.90)}
VOWELS = {'AA', 'EE', 'IH', 'OH', 'OO'}


def viseme_track(info, N, articulation=None):
    """Per-frame viseme weights (sum 1 incl. 'sil'), plus hard-closure envelopes for PP and FF."""
    names = list(S.VISEMES)
    idx = {n: i for i, n in enumerate(names)}
    ts = np.arange(N + 1) / FPS
    num = np.zeros((len(names), N + 1))
    den = np.full(N + 1, 0.06)
    num[idx['sil']] += 0.06
    cl_pp = np.zeros(N + 1)
    cl_ff = np.zeros(N + 1)
    for p in info['phonemes']:
        a, b = p['start'], p['end']
        d = max(b - a, 0.045)
        c = 0.5 * (a + b)
        alpha, wf = DOM[p['viseme']]
        theta = wf * d + 0.025
        D = alpha * np.exp(-(np.abs(ts - c) / theta) ** 1.3)
        w = p['weight']
        if p['viseme'] in VOWELS:
            w *= 1.12 if p.get('stress') == 2 else (0.92 if p.get('stress') == 0 else 1.0)
            if articulation is not None:
                w *= float(np.interp(c, articulation[0], articulation[1]))
        num[idx[p['viseme']]] += D * w
        num[idx['sil']] += D * (1.0 - w)
        den += D
        if p['viseme'] in ('PP', 'FF'):
            env = np.clip(1.0 - ((ts - c) / (0.5 * d + 0.03)) ** 2, 0.0, 1.0)
            env = smooth(env * 1.6)
            if p['viseme'] == 'PP':
                cl_pp = np.maximum(cl_pp, env)
            else:
                cl_ff = np.maximum(cl_ff, env)
    wts = num / den
    return names, wts, cl_pp, cl_ff


def speech_channels(info, N, articulation=None):
    """Viseme weights -> face control values using skeleton_def.VISEMES: returns (morph dict, jaw01, tongue01, viseme weights dict)."""
    names, wts, cl_pp, cl_ff = viseme_track(info, N, articulation)
    morph = {m: np.zeros(N + 1) for m in S.MORPH_TARGETS}
    jaw = np.zeros(N + 1)
    tongue = np.zeros(N + 1)
    for i, n in enumerate(names):
        v = S.VISEMES[n]
        for m, val in v['morphs'].items():
            morph[m] += wts[i] * val
        jaw += wts[i] * v['jaw_open']
        tongue += wts[i] * v.get('tongue', 0.0)
    morph['lip_press'] = np.maximum(morph['lip_press'], 0.95 * cl_pp)
    morph['lip_tuck_lower'] = np.maximum(morph['lip_tuck_lower'], 0.95 * cl_ff)
    jaw = jaw * (1.0 - 0.85 * cl_pp) * (1.0 - 0.55 * cl_ff)
    return morph, jaw, tongue, {n: wts[i] for i, n in enumerate(names)}


# ----------------------------------------------------------------------------- performance script


def build_performance(info, N):
    T = Timing(info)
    ts = np.arange(N + 1) / FPS
    st, en = T.start, T.end

    # --- emotional arc: worry -> resolve -> warmth (name, weight) cues
    cues = [
        (0.0, 'focus', 0.25),
        (st('Listen') - 0.10, 'focus', 0.65),
        (en('Listen') + 0.20, 'focus', 0.40),
        (st('network') - 0.05, 'concern_sadness', 0.55),
        (st('collapsing'), 'concern_sadness', 0.85),
        (en('dark'), 'concern_sadness', 0.85),
        (st('But') - 0.30, 'concern_sadness', 0.30),
        (st('But') + 0.05, 'focus', 0.85),
        (st('hold'), 'focus', 1.0),
        (en('lane', 1), 'focus', 0.75),
        (st('stabilize'), 'joy_confidence', 0.40),
        (en('relay'), 'joy_confidence', 0.55),
        (st('Keep'), 'joy_confidence', 0.55),
        (en('alive'), 'joy_confidence', 0.65),
        (st('beacon'), 'joy_confidence', 0.55),
        (st("I'll"), 'joy_confidence', 0.80),
        (st('behind'), 'joy_confidence', 0.95),
        (en('you'), 'joy_confidence', 0.85),
        (ts[-1], 'focus', 0.20),
    ]
    poses = [FL.expression(n, w) for _, n, w in cues]
    ct = np.array([c[0] for c in cues])

    def expr_at(t):
        i = int(np.clip(np.searchsorted(ct, t, side='right') - 1, 0, len(ct) - 2))
        if t <= ct[0]:
            return poses[0]
        if t >= ct[-1]:
            return poses[-1]
        s = float(smooth((t - ct[i]) / (ct[i + 1] - ct[i])))
        return lerp_pose(poses[i], poses[i + 1], s)

    # --- gaze (yaw left +, pitch up +): eye targets at the words they belong to
    gaze = [
        (0.0, 0, 0), (st('network') - 0.12, 30, 9), (st('every') - 0.02, 12, -2), (st('lane') + 0.03, -6, -4), (st('district'), -22, -8),
        (st('going') - 0.04, -6, -16), (en('dark') + 0.10, 4, -22), (st('But') - 0.15, 0, 2), (st('north') - 0.08, -30, 4),
        (en('lane', 1) + 0.05, 0, 1), (st('relay') - 0.10, 20, -14), (en('relay') + 0.02, 0, 1), (st('beacon') - 0.05, -14, -24),
        (en('beacon') + 0.12, 0, 2), (st('behind') - 0.10, 0, 0), (ts[-1], 0, 0),
    ]
    gy = steps([(t, y) for t, y, _ in gaze], ts, 0.11)
    gp = steps([(t, p) for t, _, p in gaze], ts, 0.11)
    rng = np.random.default_rng(11)
    tm, micro = 0.35, []
    while tm < ts[-1]:
        micro.append((tm, rng.uniform(-0.6, 0.6), rng.uniform(-0.45, 0.45)))
        tm += rng.uniform(0.35, 0.8)
    gy = gy + steps([(0.0, 0.0)] + [(t, y) for t, y, _ in micro], ts, 0.04)
    gp = gp + steps([(0.0, 0.0)] + [(t, p) for t, _, p in micro], ts, 0.04)

    # --- blinks: in pauses and at gaze shifts
    blink_t = [0.30, 1.42, 2.90, 3.36, 5.98, 7.98, 9.90, 12.62, 14.30]
    blink = np.zeros(N + 1)
    for tb in blink_t:
        blink = np.maximum(blink, np.where((ts >= tb) & (ts < tb + 0.075), smooth((ts - tb) / 0.075), 0.0))
        blink = np.maximum(blink, np.where((ts >= tb + 0.075) & (ts < tb + 0.115), 1.0, 0.0))
        blink = np.maximum(blink, np.where((ts >= tb + 0.115) & (ts < tb + 0.27), 1.0 - smooth((ts - tb - 0.115) / 0.155), 0.0))
    blink_r = np.interp(ts - 0.012, ts, blink)

    # --- articulation: softer while worried, tighter while determined
    art = ([0.0, st('network'), en('dark'), st('But'), en('lane', 1), ts[-1]], [1.0, 0.92, 0.85, 1.0, 1.0, 1.0])

    morph, jaw01, tongue01, vis = speech_channels(info, N, art)

    # --- emphasis: brow flash and head nod on stressed words
    emph = [('Listen', 0, 4.0, 0.30), ('network', 0, 3.0, 0.25), ('collapsing', 0, 3.0, 0.25), ('dark', 0, 3.5, 0.15), ('hold', 0, 4.0, 0.35),
            ('north', 0, 3.0, 0.30), ('stabilize', 0, 3.0, 0.25), ('alive', 0, 3.0, 0.30), ('beacon', 0, 3.0, 0.20), ('behind', 0, 4.0, 0.35), ('you', 0, 4.0, 0.15)]
    nod = np.zeros(N + 1)
    brow = np.zeros(N + 1)
    for w, occ, ang, br in emph:
        t0 = st(w, occ)
        nod += bump(ts, t0 - 0.03, 0.30, ang)
        brow += bump(ts, t0 - 0.05, 0.34, br)
    brow = np.clip(brow, 0.0, 0.5)

    # --- head follows the gaze (yaw 45 %, pitch 35 %, slightly late), plus a slow drift
    drift_y = 1.6 * np.sin(TAU * ts / 5.3 + 0.6) + 1.0 * np.sin(TAU * ts / 2.9)
    drift_p = 0.9 * np.sin(TAU * ts / 4.1 + 1.3)
    head_yaw = lowpass(0.45 * gy, 0.14, 1 / FPS) + drift_y
    head_pitch = lowpass(0.35 * gp, 0.14, 1 / FPS) + drift_p
    breath = 0.5 - 0.5 * np.cos(TAU * ts / 3.6)

    # --- body: lean and twist by section
    lean = curve([(0, 1.0), (st('Listen') - 0.1, 1.0), (st('Listen'), 5.0), (en('Listen') + 0.3, 2.0), (st('collapsing'), 5.0), (st('dark'), 9.0), (st('But') - 0.1, 6.0),
                  (st('But') + 0.1, 1.0), (st('hold'), 5.0), (en('lane', 1), 2.0), (st('Keep'), 2.5), (st('beacon'), 4.0), (st("I'll"), 3.0), (st('behind'), 6.0), (en('you'), 3.0), (ts[-1], 1.0)], ts)
    twist = curve([(0, 0), (st('north') - 0.15, 0), (st('north'), -6.0), (en('lane', 1) + 0.1, -6.0), (st('stabilize') - 0.1, 0.0), (st('beacon') - 0.1, 0), (st('beacon'), -3.0), (st("I'll") - 0.2, 0.0), (ts[-1], 0)], ts)
    sway = 0.010 * np.sin(TAU * ts / 4.6 + 0.3)
    return dict(ts=ts, T=T, expr_at=expr_at, gy=gy, gp=gp, blink_l=blink, blink_r=blink_r, morph=morph, jaw01=jaw01, tongue01=tongue01, vis=vis,
                nod=nod, brow=brow, head_yaw=head_yaw, head_pitch=head_pitch, breath=breath, lean=lean, twist=twist, sway=sway)


def body_params(P, f):
    """Continuous body state at frame f as keypose fields (feet stay planted)."""
    br, lean, tw = P['breath'][f], P['lean'][f], P['twist'][f]
    return dict(pelvis=(0.0, P['sway'][f], -0.028 - 0.004 * br), pelvis_rot=(0, 0, 0.4 * tw),
                spine=(0.8 * br + 0.6 * lean, tw + 0.8 * math.sin(TAU * f / FPS / 3.1), 0.6 * math.sin(TAU * f / FPS / 4.6)),
                neck=(P['head_pitch'][f] * -1.0 + P['nod'][f] - 0.4 * lean, P['head_yaw'][f], 0.0))


# ----------------------------------------------------------------------------- hand gestures
def _ik(target, dirn, palm, hint):
    return ('ik', dict(target=target, dir=dirn, palm=palm, elbow_hint=hint))


REST = FK(flex=4, abd=-20, elbow=14)
OPEN = dict(curl=0.05, spread=0.6)
FIST = dict(curl=1.05, spread=0.0)
POINT_R = dict(curl=1.05, index=-1.05, spread=0.0)
LOOSE = dict(curl=0.25)


def gestures(T):
    """Per arm: list of (time, arm spec, hand dict). Rest keys sit at both ends of every gesture so IK/FK blends stay short."""
    st, en = T.start, T.end
    R, L = [], []
    rest = lambda t, h=LOOSE: (t, REST, h)
    # "Listen." : right hand up, palm forward (attention)
    R += [rest(st('Listen') - 0.30), (st('Listen') - 0.02, _ik((0.30, -0.26, 1.27), (0.0, -0.10, 1.0), (1, 0, 0), (0.04, -0.44, 1.15)), OPEN),
          (en('Listen') + 0.20, _ik((0.31, -0.27, 1.29), (0.0, -0.10, 1.0), (1, 0, 0), (0.04, -0.45, 1.16)), OPEN), rest(en('Listen') + 0.75)]
    # "The network is collapsing": both hands form a mesh, then drop open
    R += [(st('network') - 0.18, REST, LOOSE), (st('network') + 0.10, _ik((0.36, -0.15, 1.22), (1, 0.4, 0.1), (0, 1, 0.2), (0.05, -0.36, 1.08)), dict(curl=0.55, spread=0.5)),
          (st('collapsing') + 0.05, _ik((0.36, -0.15, 1.24), (1, 0.4, 0.1), (0, 1, 0.2), (0.05, -0.36, 1.08)), dict(curl=0.6, spread=0.5)),
          (st('collapsing') + 0.40, _ik((0.36, -0.29, 1.00), (1, 0, -0.1), (0, 0, -1), (0.02, -0.42, 0.98)), dict(curl=0.0, spread=1.0))]
    L += [rest(st('network') - 0.20), (st('network') + 0.10, _ik((0.36, 0.15, 1.22), (1, -0.4, 0.1), (0, -1, 0.2), (0.05, 0.36, 1.08)), dict(curl=0.55, spread=0.5)),
          (st('collapsing') + 0.05, _ik((0.36, 0.15, 1.24), (1, -0.4, 0.1), (0, -1, 0.2), (0.05, 0.36, 1.08)), dict(curl=0.6, spread=0.5)),
          (st('collapsing') + 0.40, _ik((0.36, 0.29, 1.00), (1, 0, -0.1), (0, 0, -1), (0.02, 0.42, 0.98)), dict(curl=0.0, spread=1.0)),
          (st('and') + 0.05, _ik((0.30, 0.30, 1.00), (1, 0, -0.1), (0, 0, -1), (0.02, 0.42, 0.98)), dict(curl=0.05, spread=0.8)), rest(st('lane') + 0.20)]
    # "every lane into the district": the right hand sweeps across, then leads forward
    R += [(st('every') - 0.05, _ik((0.34, 0.02, 1.16), (1, -0.3, 0), (0, 0, -1), (0.0, -0.32, 1.16)), dict(curl=0.05, spread=0.3)),
          (en('lane') + 0.02, _ik((0.34, -0.40, 1.16), (0.3, -1, 0), (0, 0, -1), (0.02, -0.52, 1.10)), dict(curl=0.05, spread=0.3)),
          (st('district') + 0.15, _ik((0.46, -0.24, 1.14), (1, -0.2, -0.1), (0, 0, -1), (0.06, -0.46, 1.08)), dict(curl=0.05, spread=0.4)),
          (st('going'), _ik((0.40, -0.22, 1.08), (1, -0.1, -0.2), (0, 0, -1), (0.04, -0.44, 1.02)), OPEN),
          (en('dark'), _ik((0.36, -0.24, 0.98), (1, 0, -0.3), (0, 0, -1), (0.02, -0.44, 0.96)), dict(curl=0.2, spread=0.4)), rest(en('dark') + 0.65)]
    # "But I can hold": right fist at the chest, left palm out to hold
    R += [(st('But') - 0.10, REST, LOOSE), (st('But') + 0.12, _ik((0.30, -0.16, 1.24), (0.5, 0.6, 0.6), (0, 0.5, 0.9), (0.02, -0.40, 1.12)), FIST),
          (st('hold') + 0.05, _ik((0.32, -0.16, 1.16), (0.5, 0.6, 0.6), (0, 0.5, 0.9), (0.02, -0.40, 1.06)), FIST)]
    L += [(st('But') - 0.05, REST, LOOSE), (st('can') + 0.02, _ik((0.34, 0.24, 1.24), (0.0, 0.10, 1.0), (1, 0, 0), (0.02, 0.44, 1.10)), OPEN),
          (en('hold') + 0.25, _ik((0.35, 0.24, 1.26), (0.0, 0.10, 1.0), (1, 0, 0), (0.02, 0.44, 1.12)), OPEN), (st('north') + 0.10, REST, LOOSE)]
    # "the north lane": point to the right
    R += [(st('north') - 0.12, _ik((0.24, -0.46, 1.30), (0.2, -1, 0.1), (0, 0, -1), (-0.02, -0.52, 1.12)), POINT_R),
          (st('north') + 0.10, _ik((0.24, -0.62, 1.33), (0.05, -1, 0.1), (0, 0, -1), (-0.02, -0.58, 1.14)), POINT_R),
          (en('lane', 1) + 0.15, _ik((0.25, -0.60, 1.31), (0.05, -1, 0.1), (0, 0, -1), (-0.02, -0.58, 1.13)), POINT_R),
          (en('lane', 1) + 0.50, REST, LOOSE)]
    # "if you stabilize the relay": both hands level out, then come together
    R += [(st('stabilize') - 0.05, _ik((0.36, -0.32, 1.20), (1, -0.1, 0), (0, 0, -1), (0.02, -0.46, 1.10)), dict(curl=0.1, spread=0.2)),
          (en('stabilize') - 0.05, _ik((0.36, -0.36, 1.12), (1, -0.1, 0), (0, 0, -1), (0.02, -0.48, 1.06)), dict(curl=0.1, spread=0.2)),
          (st('relay') + 0.12, _ik((0.38, -0.10, 1.18), (1, 0.15, 0.15), (0, 0.6, -0.2), (0.04, -0.34, 1.08)), dict(curl=0.35, spread=0.1)),
          (en('relay') + 0.15, _ik((0.38, -0.10, 1.18), (1, 0.15, 0.15), (0, 0.6, -0.2), (0.04, -0.34, 1.08)), dict(curl=0.35, spread=0.1)),
          (st('Keep') - 0.05, REST, LOOSE)]
    L += [(st('stabilize') - 0.05, _ik((0.36, 0.32, 1.20), (1, 0.1, 0), (0, 0, -1), (0.02, 0.46, 1.10)), dict(curl=0.1, spread=0.2)),
          (en('stabilize') - 0.05, _ik((0.36, 0.36, 1.12), (1, 0.1, 0), (0, 0, -1), (0.02, 0.48, 1.06)), dict(curl=0.1, spread=0.2)),
          (st('relay') + 0.12, _ik((0.38, 0.10, 1.18), (1, -0.15, 0.15), (0, -0.6, -0.2), (0.04, 0.34, 1.08)), dict(curl=0.35, spread=0.1)),
          (en('relay') + 0.15, _ik((0.38, 0.10, 1.18), (1, -0.15, 0.15), (0, -0.6, -0.2), (0.04, 0.34, 1.08)), dict(curl=0.35, spread=0.1)),
          (st('Keep') - 0.05, REST, LOOSE)]
    # "Keep the signal alive": the left hand rises with spreading fingers
    L += [(st('signal') - 0.10, _ik((0.32, 0.28, 1.06), (0.5, 0.2, 0.8), (0, 0, 1), (0.0, 0.44, 0.96)), dict(curl=0.3, spread=0.3)),
          (st('alive') + 0.05, _ik((0.34, 0.26, 1.34), (0.5, 0.1, 0.9), (1, 0, 0.2), (0.0, 0.46, 1.16)), dict(curl=0.0, spread=1.0)),
          (en('alive') + 0.20, _ik((0.34, 0.26, 1.36), (0.5, 0.1, 0.9), (1, 0, 0.2), (0.0, 0.46, 1.17)), dict(curl=0.0, spread=1.0)), rest(st('trust') + 0.35)]
    # "trust the beacon": right hand flat on the chest
    R += [(st('trust') - 0.12, _ik((0.13, -0.10, 1.27), (0.2, 1, 0.3), (-1, 0, 0.2), (-0.02, -0.40, 1.16)), dict(curl=0.05, spread=0.0)),
          (st('beacon') + 0.05, _ik((0.13, -0.10, 1.27), (0.2, 1, 0.3), (-1, 0, 0.2), (-0.02, -0.40, 1.16)), dict(curl=0.05, spread=0.0)),
          (en('beacon') + 0.05, _ik((0.13, -0.10, 1.27), (0.2, 1, 0.3), (-1, 0, 0.2), (-0.02, -0.40, 1.16)), dict(curl=0.05, spread=0.0)),
          (st("I'll") + 0.10, REST, LOOSE)]
    # "I'll be right behind you": the right hand opens palm up towards the listener
    R += [(st('right') - 0.10, _ik((0.40, -0.26, 1.12), (1, -0.05, 0.15), (0, 0, 1), (0.04, -0.46, 1.02)), dict(curl=0.1, spread=0.5)),
          (st('behind') + 0.10, _ik((0.44, -0.24, 1.14), (1, -0.05, 0.15), (0, 0, 1), (0.05, -0.46, 1.03)), dict(curl=0.05, spread=0.6)),
          (en('you') + 0.10, _ik((0.42, -0.24, 1.13), (1, -0.05, 0.15), (0, 0, 1), (0.05, -0.46, 1.03)), dict(curl=0.1, spread=0.5)),
          (en('you') + 0.65, REST, LOOSE)]
    for lst in (R, L):
        lst.sort(key=lambda k: k[0])
    return R, L


# ----------------------------------------------------------------------------- the clip
def prune_rests(seq, min_gap=0.30):
    """A rest key only counts when the arm has time to reach it. A rest within min_gap seconds of a gesture key on either side is
    dropped, so the arm goes from gesture to gesture instead of cutting through rest within a frame or two (IK to FK in one frame
    moved the hand by up to 44 cm)."""
    keep = []
    for i, k in enumerate(seq):
        if k[1][0] == 'fk' and 0 < i < len(seq) - 1:
            p, n = seq[i - 1], seq[i + 1]
            if (p[1][0] != 'fk' and k[0] - p[0] < min_gap) or (n[1][0] != 'fk' and n[0] - k[0] < min_gap):
                continue
        keep.append(k)
    return keep


ARM_BONES = ('ctl_clavicle_', 'ctl_upperarm_fk_', 'ctl_lowerarm_fk_', 'ctl_hand_fk_', 'ctl_hand_ik_', 'ctl_pole_arm_', 'ctl_hand_pose_')
BODY_BONES = ('ctl_pelvis', 'ctl_spine_0', 'ctl_neck_0', 'ctl_head')


def _pick(pose, prefixes, side=None):
    out = Pose()
    for (b, kind, i), v in pose.items():
        if any(b.startswith(p) for p in prefixes) and (side is None or b.endswith('_' + side)):
            out[(b, kind, i)] = v
    return out


def load_info():
    with open(ALIGN_PATH, encoding='utf-8') as fh:
        return json.load(fh)


@clip('dialogue')
def dialogue(e):
    info = load_info()
    N = e['frames']
    P = build_performance(info, N)
    ts = P['ts']
    frames = np.arange(N + 1)
    c = build_clip('dialogue', e, [], loop=False, note=f'spoken performance synchronised to source/audio/dialogue.wav ({info["audio"]["duration_s"]} s): '
                   'phoneme-driven lips, gaze, blinks, emotional arc, hand gestures and body acting')
    c.meta.update(audio='source/audio/dialogue.wav', transcript='source/audio/dialogue.txt', alignment='source/audio/dialogue_alignment.json',
                  audio_offset_s=0.0, sample_rate=info['audio']['sample_rate'])

    # ---- body keys every 3 frames (feet and root stay planted: constant keys at both ends)
    base = relaxed()
    for f in sorted(set(range(0, N + 1, 3)) | {N}):
        k = dict(base)
        k.update(body_params(P, f))
        pose = resolve(k)
        c.key(f, _pick(pose, BODY_BONES))
    k0 = resolve(dict(base, **body_params(P, 0)))
    for f in (0, N):
        c.key(f, _pick(k0, ('ctl_root', 'ctl_foot_ik_', 'ctl_pole_leg_')))

    # ---- arms: authored gesture keys (IK) between FK rest keys
    Rk, Lk = gestures(P['T'])
    for side, lst in (('r', Rk), ('l', Lk)):
        seq = prune_rests([(0.0, REST, LOOSE)] + [g for g in lst if 0.0 < g[0] < ts[-1] - 0.25] + [(ts[-1], REST, LOOSE)])
        for t, spec, hand in seq:
            f = int(round(t * FPS))
            k = dict(base)
            k.update(body_params(P, f))
            k['a' + side] = spec
            k['h' + side] = hand
            pose = resolve(k)
            c.key(f, _pick(pose, ARM_BONES, side))

    # ---- face: expression + speech + emphasis, keyed densely then reduced
    morph_names = list(S.MORPH_TARGETS)
    val = {m: np.zeros(N + 1) for m in morph_names}
    jaw_expr = np.zeros(N + 1)
    lid_expr = np.zeros(N + 1)
    for f in frames:
        ep = P['expr_at'](ts[f])
        for m in morph_names:
            val[m][f] = ep.get(('ctl_face', m, 0), 0.0)
        jaw_expr[f] = -ep.get(('ctl_jaw', 'rot', 0), 0.0) / FL.JAW_MAX
        lid_expr[f] = ep.get(('ctl_lid_up_l', 'rot', 0), 0.0)
    for m in morph_names:
        val[m] = val[m] + P['morph'][m]
    for m in ('brow_up_out_l', 'brow_up_out_r'):
        val[m] = val[m] + P['brow']
    jaw01 = np.clip(jaw_expr + P['jaw01'], 0.0, 1.0)
    val['jaw_open_corr'] = np.maximum(val['jaw_open_corr'], np.clip(P['jaw01'] * 1.1, 0.0, 1.0))
    for m in morph_names:
        v = np.clip(val[m], 0.0, 1.0)
        for f, x in reduce_track(frames, v, 0.004):
            c.key(f, Pose().prop('ctl_face', m, x))
    for f, x in reduce_track(frames, -FL.JAW_MAX * jaw01, 0.10):
        c.key(f, Pose().rot('ctl_jaw', (x, 0.0, 0.0)))
    for tb, name in ((0, 'ctl_tongue_01'), (1, 'ctl_tongue_02'), (2, 'ctl_tongue_03')):
        gain = (-18.0, -22.0, -16.0)[tb]
        for f, x in reduce_track(frames, gain * np.clip(P['tongue01'], 0, 1), 0.12):
            c.key(f, Pose().rot(name, (x, 0.0, 0.0)))
    # viseme controls (documented mapping in docs/rig_usage.md): keyed for reference and for editing
    for vname, arr in P['vis'].items():
        if vname == 'sil':
            continue
        for f, x in reduce_track(frames, np.clip(arr, 0, 1), 0.01):
            c.key(f, Pose().prop('ctl_face', 'viseme_' + vname, x))

    # ---- eyes and lids
    for side, blink in (('l', P['blink_l']), ('r', P['blink_r'])):
        up = (lid_expr + 0.35 * P['gp']) * (1.0 - blink) + FL.LID_CLOSE_UP * blink
        lo = FL.LID_CLOSE_LO * blink + (-0.12 * P['gp']) * (1.0 - blink)
        for f, x in reduce_track(frames, up, 0.25):
            c.key(f, Pose().rot(f'ctl_lid_up_{side}', (x, 0.0, 0.0)))
        for f, x in reduce_track(frames, lo, 0.2):
            c.key(f, Pose().rot(f'ctl_lid_lo_{side}', (x, 0.0, 0.0)))
        for axis, arr in ((0, P['gp']), (2, P['gy'])):
            for f, x in reduce_track(frames, arr, 0.12):
                p = Pose()
                p[(f'ctl_eye_{side}', 'rot', axis)] = x
                c.key(f, p)

    # ---- markers
    T = P['T']
    fr = lambda t: int(round(t * FPS))
    c.event('dialogue_start', fr(T.words[0]['start']))
    for s in info['sentences']:
        c.event('dialogue_line', fr(s['start']), index=s['index'])
    c.event('emotion_shift', fr(T.start('But')), frm='concern_sadness', to='focus')
    c.event('emotion_shift', fr(T.start('stabilize')), frm='focus', to='joy_confidence')
    c.event('dialogue_end', fr(T.words[-1]['end']))
    return c
