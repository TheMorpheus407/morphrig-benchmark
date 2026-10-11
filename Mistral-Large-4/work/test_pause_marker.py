#!/usr/bin/env python3
"""Does '_' act as a pause inside espeak-ng phoneme-input [[...]]?"""
import array
import subprocess
import wave

VOICE = ["-v", "en-us", "-s", "140", "-p", "40"]


def synth(path, text):
    r = subprocess.run(["espeak-ng"] + VOICE + ["-w", path, text],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return path


def load(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def env_peaks(a, rate, hop_s=0.010, win_s=0.020):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    return env, hop_s


def regions(a, rate):
    env, hop_s = env_peaks(a, rate)
    peak = max(env)
    thr = 0.05 * peak
    regs = []
    in_reg = False
    for i, e in enumerate(env):
        if e <= thr and not in_reg:
            in_reg = True
            start = i
        elif e > thr and in_reg:
            in_reg = False
            regs.append((start * hop_s, i * hop_s))
    if in_reg:
        regs.append((start * hop_s, len(env) * hop_s))
    return regs, len(a) / rate


CASES = [
    ("no pause", "[[w'0tS k'i:p]]"),
    ("underscore", "[[w'0tS _ k'i:p]]"),
    ("underscore_nospace", "[[w'0tS_ k'i:p]]"),
    ("underscore_bang", "[[w'0tS _! k'i:p]]"),
    ("comma", "[[w'0tS , k'i:p]]"),
    ("two words only", "[[wi: st'and]]"),
]

for label, s in CASES:
    a, rate = load(synth("/tmp/pp.wav", s))
    regs, dur = regions(a, rate)
    gaps = ["%.3f-%.3f (%.3f)" % (r[0], r[1], r[1] - r[0]) for r in regs]
    print("%-18s dur=%.3f  gaps: %s" % (label, dur, "; ".join(gaps) or "none"))
