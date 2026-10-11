#!/usr/bin/env python3
"""Probe: empty-prefix synthesis + modifier round-trip durations."""
import subprocess
import wave

VOICE = ["-v", "en-us", "-s", "150", "-p", "40"]


def synth(path, text):
    r = subprocess.run(["espeak-ng"] + VOICE + ["-w", path, text],
                       capture_output=True, text=True)
    return r.returncode, r.stderr.strip()


def dur(path):
    try:
        w = wave.open(path)
        d = w.getnframes() / w.getframerate()
        info = (w.getframerate(), w.getnchannels(), w.getsampwidth())
        w.close()
        return d, info
    except Exception as e:
        return -1.0, str(e)


for label, s in [("empty", ""), ("brackets", "[[]]"), ("D", "[[D]]"),
                 ("D@2", "[[D@2]]"), ("st", "[[st]]"),
                 ("stabilize", "[[st'eIbI2l,aIz]]"), ("nobody", "[[n'oUb0di]]"),
                 ("while", "[[w'aIl]]"), ("crosses", "[[kr'O2sI#z]]")]:
    rc, err = synth("/tmp/e_t.wav", s)
    d, info = dur("/tmp/e_t.wav")
    print("%-10s rc=%d dur=%.3f %s err=%r" % (label, rc, d, info, err[:60]))
