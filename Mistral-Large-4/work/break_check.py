#!/usr/bin/env python3
"""Independent duration check: synthesize the transcript with an SSML
<break> between every word, measure each word's energy segment, and compare
segment durations with the aligned word durations."""
import array
import json
import os
import re
import subprocess
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(TASK, "source", "audio")
WORK = os.path.join(TASK, "work", "dlg")
SPEED = 140


def load(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def segments(a, rate, hop_s=0.010, win_s=0.020, rel_thr=0.05):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    peak = max(env)
    thr = rel_thr * peak
    segs = []
    in_seg = False
    for i, e in enumerate(env):
        if e > thr and not in_seg:
            in_seg = True
            start = i
        elif e <= thr and in_seg:
            in_seg = False
            segs.append((start * hop_s, i * hop_s))
    if in_seg:
        segs.append((start * hop_s, len(env) * hop_s))
    # merge segments separated by < 200 ms (intra-word dips; the inserted
    # SSML breaks are >= 330 ms)
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < 0.200:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append((s[0], s[1]))
    return merged


def main():
    with open(os.path.join(AUDIO, "dialogue.txt")) as f:
        transcript = f.read().strip()
    with open(os.path.join(AUDIO, "dialogue_alignment.json")) as f:
        align = json.load(f)
    toks = re.findall(r"[A-Za-z']+|[.,!?;:]", transcript)
    words = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z']", t):
            punct = ""
            if i + 1 < len(toks) and re.match(r"[.,!?;:]", toks[i + 1]):
                punct = toks[i + 1]
                i += 1
            words.append(t + punct)
        i += 1

    ssml = '<break time="350ms"/>'.join(words)
    path = os.path.join(WORK, "breaks.wav")
    r = subprocess.run(["espeak-ng", "-m", "-v", "en-us", "-s", str(SPEED),
                        "-p", "40", "-w", path, ssml],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("espeak-ng SSML failed:", r.stderr[:200])
        return 1
    a, rate = load(path)
    segs = segments(a, rate)
    print("break-mode: %d energy segments for %d words, audio %.3f s"
          % (len(segs), len(words), len(a) / rate))
    if len(segs) != len(words):
        print("segment/word count mismatch; segment durations:")
        for s in segs:
            print("   %.3f-%.3f (%.3f)" % (s[0], s[1], s[1] - s[0]))
        return 1
    print("\n idx word          aligned   break-mode  ratio")
    ratios = []
    for i, (wd, s) in enumerate(zip(align["words"], segs)):
        ad = wd["end"] - wd["start"]
        bd = s[1] - s[0]
        ratio = ad / bd if bd > 1e-6 else 0
        ratios.append(ratio)
        print("  [%02d] %-12s %6.3f   %6.3f   %5.2f"
              % (i, wd["word"], ad, bd, ratio))
    ratios.sort()
    print("\nratio aligned/break-mode: min=%.2f  median=%.2f  max=%.2f"
          % (ratios[0], ratios[len(ratios) // 2], ratios[-1]))
    print("(break-mode makes every word utterance-final, so ratios < 1 "
          "are expected; a tight band means consistent timing)")
    print("BREAK_CHECK_DONE")


if __name__ == "__main__":
    main()
