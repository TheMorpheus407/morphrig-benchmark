#!/usr/bin/env python3
"""Verify dialogue_alignment.json against the actual audio:
1. envelope of the full line with word boundaries overlaid (do boundaries
   land in/near low-energy dips?)
2. isolated-word envelope cross-correlation (independent estimate of each
   word's start offset and time-warp) vs the alignment's word starts
3. phoneme monotonicity / containment checks
"""
import array
import json
import os
import subprocess
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(TASK, "source", "audio")
WORK = os.path.join(TASK, "work", "dlg")

SPEED = 140
VOICE = ["-v", "en-us", "-s", str(SPEED), "-p", "40"]


def load_wav(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def envelope(a, rate, hop_s=0.020, win_s=0.030):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    return env, hop_s


def synth_word(word):
    path = os.path.join(WORK, "vw_%s.wav" % word)
    subprocess.run(["espeak-ng"] + VOICE + ["-w", path, word],
                   capture_output=True, text=True)
    return load_wav(path)


def best_offset(word_env, line_env, hop_s, est_start, search=0.6,
                lambdas=None):
    """Slide the (time-warped) word envelope over the line envelope near
    est_start; return (best_start, best_lambda, best_score)."""
    if lambdas is None:
        lambdas = [0.6 + 0.05 * i for i in range(15)]
    n = len(word_env)
    best = None
    lo = max(0, int((est_start - search) / hop_s))
    hi = min(len(line_env) - 1, int((est_start + search) / hop_s))
    for lam in lambdas:
        m = max(2, int(n * lam))
        warped = [word_env[min(n - 1, int(i / lam))] for i in range(m)]
        # normalize
        wmax = max(warped) or 1.0
        warped = [v / wmax for v in warped]
        for off in range(lo, hi):
            if off + m > len(line_env):
                break
            seg = line_env[off:off + m]
            smax = max(seg) or 1.0
            seg = [v / smax for v in seg]
            score = sum((x - y) ** 2 for x, y in zip(warped, seg)) / m
            if best is None or score < best[2]:
                best = (off * hop_s, lam, score)
    return best


def main():
    with open(os.path.join(AUDIO, "dialogue_alignment.json")) as f:
        align = json.load(f)
    a, rate = load_wav(os.path.join(WORK, "dialogue_22k.wav"))
    env, hop_s = envelope(a, rate)
    peak = max(env)
    dur = len(a) / rate
    print("audio %.3f s, envelope %d pts @ %.0f ms, peak %.0f"
          % (dur, len(env), hop_s * 1000, peak))

    # --- 1. boundaries vs local energy dips
    print("\nword boundaries vs local envelope minimum (+/-0.15 s):")
    worst = 0.0
    for wd in align["words"]:
        b = wd["start"]
        if wd["index"] == 0:
            continue
        lo = max(0, int((b - 0.15) / hop_s))
        hi = min(len(env), int((b + 0.15) / hop_s))
        seg = env[lo:hi]
        minpos = lo + seg.index(min(seg))
        dip = minpos * hop_s
        # energy at boundary relative to local max
        atb = env[min(len(env) - 1, int(b / hop_s))]
        locmax = max(seg) or 1.0
        rel = atb / locmax
        worst = max(worst, abs(dip - b))
        print("  [%02d] %-12s b=%6.3f  dip=%6.3f  d=%+6.3f  E(b)/Emax=%.2f"
              % (wd["index"], wd["word"], b, dip, dip - b, rel))
    print("max |boundary - nearest dip| = %.3f s" % worst)

    # --- 2. isolated-word cross-correlation for a sample of words
    print("\nisolated-word envelope correlation (independent estimate):")
    sample = [0, 4, 7, 13, 22, 25, 29]
    for i in sample:
        wd = align["words"][i]
        wa, wrate = synth_word(wd["word"])
        wenv, _ = envelope(wa, wrate)
        est = wd["start"]
        bstart, lam, score = best_offset(wenv, env, hop_s, est)
        print("  [%02d] %-12s align=%6.3f  xcorr=%6.3f  diff=%+6.3f  "
              "lambda=%.2f  rms=%.3f"
              % (i, wd["word"], est, bstart, bstart - est, lam, score ** 0.5))

    # --- 3. phoneme checks
    print("\nphoneme checks:")
    bad = 0
    for ph in align["phonemes"]:
        if ph["end"] < ph["start"] - 1e-9:
            bad += 1
    for wd in align["words"]:
        phs = [p for p in align["phonemes"] if p["word_index"] == wd["index"]]
        for p in phs:
            if p["start"] < wd["start"] - 1e-4 or p["end"] > wd["end"] + 1e-4:
                bad += 1
                print("  OUT OF SLOT: %s %s in word %s" % (p["phoneme"], p, wd["word"]))
        for p, q in zip(phs, phs[1:]):
            if q["start"] < p["end"] - 1e-4:
                bad += 1
    mono = all(align["phonemes"][k]["start"] <= align["phonemes"][k + 1]["start"]
               for k in range(len(align["phonemes"]) - 1))
    print("  phonemes=%d, violations=%d, globally monotonic=%s"
          % (len(align["phonemes"]), bad, mono))
    print("  duration=%.3f s, frames=%d, visemes=%d"
          % (align["duration_seconds"], align["duration_frames"],
             len(align["visemes"])))
    print("VERIFY_DONE")


if __name__ == "__main__":
    main()
