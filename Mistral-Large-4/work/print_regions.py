#!/usr/bin/env python3
"""Print low-energy regions of the full-line audio to calibrate clause
boundary detection."""
import array
import os
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(TASK, "work", "dlg")


def load(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def envelope(a, rate, hop_s=0.010, win_s=0.020):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    return env, hop_s


a, rate = load(os.path.join(WORK, "full.wav"))
env, hop_s = envelope(a, rate)
peak = max(env)
print("peak %.0f, %d env pts" % (peak, len(env)))

# region list at several thresholds
for rel in (0.06, 0.10, 0.15):
    thr = rel * peak
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
    merged = []
    for r in regs:
        if merged and r[0] - merged[-1][1] < 0.020:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append((r[0], r[1]))
    print("\nthreshold %.0f%%: %d regions" % (rel * 100, len(merged)))
    for r in merged:
        if r[1] - r[0] >= 0.05:
            print("   %.3f - %.3f  (%.3f s)" % (r[0], r[1], r[1] - r[0]))
