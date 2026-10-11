#!/usr/bin/env python3
"""Quick test: does espeak-ng accept [[...]] phoneme-mnemonic input, and do
prefix syntheses give increasing durations (usable as phoneme timing)?"""
import subprocess
import wave

VOICE = ["-v", "en-us", "-s", "145", "-p", "40"]


def synth(path, text):
    r = subprocess.run(["espeak-ng"] + VOICE + ["-w", path, text],
                       capture_output=True, text=True)
    return r.returncode, r.stderr.strip()


def dur(path):
    try:
        w = wave.open(path)
        d = w.getnframes() / w.getframerate()
        w.close()
        return d
    except Exception:
        return -1.0


for label, s in [("full", "[[h@l'oU]]"), ("p1", "[[h]]"), ("p2", "[[h@l]]"),
                 ("stress", "[[h'oUld]]"), ("ipa-like", "[[həloʊ]]")]:
    rc, err = synth("/tmp/t_%s.wav" % label, s)
    print("%-10s rc=%d dur=%.3f err=%r" % (label, rc, dur("/tmp/t_%s.wav" % label), err[:80]))
