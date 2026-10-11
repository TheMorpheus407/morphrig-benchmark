#!/usr/bin/env python3
"""Measure speech onset/offset (energy-based) of the full-line text audio
and the full phoneme-string audio, to check lead-in/lead-out padding."""
import array
import os
import subprocess
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(TASK, "work", "dlg")
VOICE = ["-v", "en-us", "-s", "140", "-p", "40"]

MNEM_FULL = ("h'oUld D@2 l'eIn D@2 n'Etw3:k st'eIz aU3z n'oUb0di kr'O2sI#z_! "
             "w,aIl wi: st'and w'0tS k'i:p jU@r- 'aIz ,Vp_:_: and jU@ s'El "
             "st'Edi wi: st'eIbI2l,aIz D@2 gr'Id t@g'ED3 O@ wi: l'u:z "
             "'EvrI2T,IN")


def load(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def env_of(a, rate, hop_s=0.010, win_s=0.020):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    return env, hop_s


def speech_region(path, label):
    a, rate = load(path)
    dur = len(a) / rate
    env, hop_s = env_of(a, rate)
    peak = max(env)
    thr = 0.04 * peak
    # onset: first index above thr sustained 40 ms
    onset = None
    i = 0
    while i < len(env):
        if env[i] > thr:
            if all(env[j] > thr * 0.5 for j in range(i, min(len(env), i + 4))):
                onset = i * hop_s
                break
        i += 1
    offset = None
    i = len(env) - 1
    while i >= 0:
        if env[i] > thr:
            if all(env[j] > thr * 0.5 for j in range(max(0, i - 3), i + 1)):
                offset = (i + 1) * hop_s
                break
        i -= 1
    print("%-12s dur=%.3f  speech=[%.3f, %.3f]  lead_in=%.3f  lead_out=%.3f"
          % (label, dur, onset, offset, onset, dur - offset))
    # print envelope profile (0.25 s buckets, % of peak)
    buckets = []
    bs = int(0.25 / hop_s)
    for s in range(0, len(env), bs):
        seg = env[s:s + bs]
        buckets.append(int(100 * max(seg) / peak))
    line = " ".join("%3d" % b for b in buckets)
    print("  env%%: " + line)
    return dur, onset, offset


# text audio
a, rate = load(os.path.join(WORK, "full.wav"))
dur_t, onset_t, offset_t = speech_region(os.path.join(WORK, "full.wav"), "text")

# phoneme-string audio
p = os.path.join(WORK, "phstr.wav")
subprocess.run(["espeak-ng"] + VOICE + ["-w", p, "[[" + MNEM_FULL + "]]"],
               capture_output=True, text=True)
dur_p, onset_p, offset_p = speech_region(p, "phonemes")

print("\nsummary: text speech %.3f s, phoneme-string speech %.3f s, ratio %.3f"
      % (offset_t - onset_t, offset_p - onset_p,
         (offset_t - onset_t) / (offset_p - onset_p)))
