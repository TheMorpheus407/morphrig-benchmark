#!/usr/bin/env python3
"""Test: tail-appended prefix synthesis removes the word-final-lengthening
bias. P_k = speech(synth("[[prefix_k @]]")); true_k = P_k - P_0 (constant
tail). Compare resulting word boundaries with envelope ground truth."""
import array
import os
import subprocess
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(TASK, "work", "dlg")
VOICE = ["-v", "en-us", "-s", "140", "-p", "40"]

CLAUSES = [
    ("h'oUld D@2 l'eIn", ["h'oUld", "D@2", "l'eIn"], 0.030, 1.110),
    ("O@ wi: l'u:z 'EvrI2T,IN", ["O@", "wi:", "l'u:z", "'EvrI2T,IN"],
     11.760, 13.180),
]
# envelope ground truth word starts (None = no clear gap)
TRUTH = [
    [0.040, 0.480, 0.660, 1.110],
    [11.760, 11.950, 12.300, 12.720, 13.180],
]

MULTI = ["tS", "dZ", "aI", "aU", "eI", "oU", "@U",
         "a:", "A:", "Q:", "E:", "I:", "O:", "U:", "u:", "i:", "o:",
         "@:", "3:", "8:", "2:"]
SINGLES = set("pbmfvdTtDdnNszSZlrjwhkg@AEIOUaeiou0238^VcqQxJyJ")
MODIFIERS = set("2,#-")
SKIPMARKS = set("'_,! :")


def tokenize(mnem):
    units = []
    i, n = 0, len(mnem)
    while i < n:
        c = mnem[i]
        if c in SKIPMARKS:
            i += 1
            continue
        if c in MODIFIERS:
            if units and units[-1][1] == i:
                s0, e0, b0 = units[-1]
                units[-1] = (s0, i + 1, b0)
            i += 1
            continue
        tok = None
        for m in MULTI:
            if mnem.startswith(m, i):
                tok = m
                break
        if tok is None:
            tok = c
        units.append((i, i + len(tok), tok))
        i += len(tok)
    return units


def synth(path, text):
    r = subprocess.run(["espeak-ng"] + VOICE + ["-w", path, text],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return path


def speech_of(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    hop = int(0.010 * rate)
    win = int(0.020 * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    peak = max(env)
    if peak <= 0:
        return 0.0, 0.0
    thr = 0.05 * peak
    onset = None
    for i in range(len(env)):
        if env[i] > thr and all(env[j] > thr * 0.5
                               for j in range(i, min(len(env), i + 3))):
            onset = i * 0.010
            break
    offset = None
    for i in range(len(env) - 1, -1, -1):
        if env[i] > thr and all(env[j] > thr * 0.5
                               for j in range(max(0, i - 2), i + 1)):
            offset = (i + 1) * 0.010
            break
    if onset is None or offset is None or offset <= onset:
        return 0.0, 0.0
    return onset, offset


for ci, (mnem, word_mnems, ws_c, we_s) in enumerate(CLAUSES):
    units = tokenize(mnem)
    cum = [0]
    for wm in word_mnems:
        cum.append(cum[-1] + len(tokenize(wm)))
    # tail-appended prefix speech
    P = []
    for k in range(0, len(units) + 1):
        pfx = "[[" + mnem[:units[k - 1][1]] + " @]]" if k > 0 else "[[@]]"
        path = os.path.join(WORK, "tp_c%d_%03d.wav" % (ci, k))
        synth(path, pfx)
        o, f = speech_of(path)
        P.append(f - o if f > o else 0.0)
    # plain prefix speech (v3 method)
    Q = []
    for k in range(0, len(units) + 1):
        pfx = "[[" + mnem[:units[k - 1][1]] + "]]" if k > 0 else "[[]]"
        path = os.path.join(WORK, "tq_c%d_%03d.wav" % (ci, k))
        synth(path, pfx)
        o, f = speech_of(path)
        Q.append(f - o if f > o else 0.0)
    T = P[0]
    true = [p - T for p in P]
    true = [max(0.0, t) for t in true]
    S_true = true[-1]
    S_q = Q[-1]
    slot = we_s - ws_c
    print("\nclause %d: slot [%.3f, %.3f] speech %.3f, tail T=%.3f, "
          "S_true=%.3f, S_plain=%.3f"
          % (ci + 1, ws_c, we_s, slot, T, S_true, S_q))
    print("  word   truth   v3(plain)  tail-method   break-ratio")
    # break-mode durations for ratio comparison
    BREAK = [[0.42, 0.17, 0.41], [0.20, 0.21, 0.42, 0.80]]
    bd = BREAK[ci]
    bsum = sum(bd)
    for wi in range(len(word_mnems)):
        u0, u1 = cum[wi], cum[wi + 1]
        t_v3 = ws_c + slot * Q[u0] / S_q if S_q > 0 else ws_c
        t_tail = ws_c + slot * true[u0] / S_true if S_true > 0 else ws_c
        t_brk = ws_c + slot * sum(bd[:wi]) / bsum
        print("  %-6s %6.3f  %6.3f (%+5.3f)  %6.3f (%+5.3f)  %6.3f (%+5.3f)"
              % (word_mnems[wi][:6], TRUTH[ci][wi], t_v3,
                 t_v3 - TRUTH[ci][wi], t_tail, t_tail - TRUTH[ci][wi],
                 t_brk, t_brk - TRUTH[ci][wi]))
    t_v3 = ws_c + slot * Q[-1] / S_q
    t_tail = ws_c + slot * true[-1] / S_true
    print("  end    %6.3f  %6.3f (%+5.3f)  %6.3f (%+5.3f)"
          % (TRUTH[ci][-1], t_v3, t_v3 - TRUTH[ci][-1],
             t_tail, t_tail - TRUTH[ci][-1]))
