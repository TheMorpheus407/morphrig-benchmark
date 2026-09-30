"""Shared clip registry, expression helpers and procedural layers."""
import math
import numpy as np
from mr_anim import DEG
from mr_face_list import EXPRESSIONS

REGISTRY = {}


def clip(cid):
    def deco(fn):
        REGISTRY[cid] = fn
        return fn
    return deco


def expr(name, w=1.0, **extra):
    """Expression preset scaled by w (face props only; jaw handled by pose['jaw'])."""
    d = {k: v * w for k, v in EXPRESSIONS[name].items() if k != "jaw"}
    d.update(extra)
    return d


def expr_jaw(name, w=1.0):
    return EXPRESSIONS[name].get("jaw", 0.0) * w


def face_mix(*parts):
    out = {}
    for d in parts:
        for k, v in d.items():
            out[k] = max(out.get(k, 0.0), v)
    return out


def breathing(amp=1.0, period=None, phase=0.0):
    def layer(frames, S):
        n = frames[-1]
        per = period or n
        cycles = max(1, round(n / per))
        w = 2 * math.pi * cycles * frames / n + phase
        br = np.sin(w)
        S["spine_02.rot"][:, 0] += -0.9 * DEG * amp * br
        S["spine_03.rot"][:, 0] += -0.8 * DEG * amp * br
        for s in "lr":
            S[f"clavicle_{s}.rot"][:, 0] += 1.2 * DEG * amp * (0.5 + 0.5 * br)
        S["neck_01.rot"][:, 0] += 0.5 * DEG * amp * br
    return layer


def blinks(times, dur_close=2, dur_open=4, amount=1.0, side="LR"):
    def layer(frames, S):
        for t0 in times:
            for f in frames:
                x = f - t0
                if 0 <= x <= dur_close:
                    v = x / dur_close
                elif dur_close < x <= dur_close + dur_open:
                    v = 1.0 - (x - dur_close) / dur_open
                else:
                    continue
                v = v * v * (3 - 2 * v) * amount
                for sd in side:
                    key = f"c_face[blink_{sd}]"
                    S[key][int(f), 0] = max(S[key][int(f), 0], v)
    return layer


def sway_noise(seed, amp_deg=0.6, chans=("head.rot", "neck_02.rot"), harmonics=(1, 2, 3)):
    """Periodic pseudo-noise (integer-cycle sines) for loop-safe micro motion."""
    rng = np.random.default_rng(seed)
    coeffs = {c: [(h, rng.uniform(-1, 1, 3), rng.uniform(0, 2 * np.pi, 3)) for h in harmonics] for c in chans}

    def layer(frames, S):
        n = frames[-1]
        for c, terms in coeffs.items():
            for h, a, ph in terms:
                for k in range(3):
                    S[c][:, k] += amp_deg * DEG * a[k] / h * np.sin(2 * np.pi * h * frames / n + ph[k])
    return layer


def tremble(chans, amp_deg=0.6, seed=0, harmonics=(5, 7, 9, 11)):
    """Fast periodic tremor (integer cycles per clip) for sustained effort."""
    return sway_noise(seed, amp_deg, chans, harmonics)
