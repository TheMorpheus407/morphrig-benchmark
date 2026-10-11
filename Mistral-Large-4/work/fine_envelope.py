#!/usr/bin/env python3
"""Fine-grained envelope dump of the full-line audio tail (and head) to
settle word boundary ground truth by eye."""
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


a, rate = load(os.path.join(WORK, "full.wav"))
hop = int(0.010 * rate)
win = int(0.020 * rate)
env = []
for s in range(0, max(1, len(a) - win), hop):
    acc = 0
    for v in a[s:s + win]:
        acc += v * v
    env.append((acc / win) ** 0.5)
peak = max(env)


def dump(t0, t1, label):
    print("\n%s  [%.2f, %.2f] s, env %% of peak, 10 ms rows of 5 pts (50 ms):"
          % (label, t0, t1))
    i0 = int(t0 / 0.010)
    i1 = int(t1 / 0.010)
    for i in range(i0, i1, 5):
        row = env[i:i + 5]
        bar = "".join("#" if e > 0.30 * peak else
                      ("+" if e > 0.12 * peak else
                       ("." if e > 0.04 * peak else " ")) for e in row)
        print("  %6.2f |%s|" % (i * 0.010, bar))


dump(11.40, 13.25, "clause 6: or we lose everything")
dump(0.00, 1.60, "clause 1: Hold the lane")
dump(5.90, 7.20, "clause 4 start: Keep your")
