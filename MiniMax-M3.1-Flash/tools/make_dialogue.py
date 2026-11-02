"""Generate the spoken performance for the `dialogue` clip.

    nix-shell -p piper-tts espeak-ng --run python3 tools/make_dialogue.py

Produces
    source/audio/dialogue.wav        the spoken line
    source/audio/dialogue.txt        the transcript
    source/audio/dialogue_alignment.json  word level timings

The line is original.  It is synthesised phrase by phrase with the local
piper voice so the prosody stays natural, and the words inside a phrase are
distributed over the measured phrase duration in proportion to their length.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    ".."))
AUDIO = os.path.join(ROOT, "source", "audio")
VOICE = os.path.join(AUDIO, "voice", "en_US-lessac-medium.onnx")
VOICE_CFG = VOICE + ".json"

# The original spoken line of the Operative.
PHRASES = [
    "Command, this is Operative Seven.",
    "The relay is patched and the perimeter is clear.",
    "I am moving to the extraction point now.",
    "Keep the channel open.",
    "Stay off the grid until I confirm.",
]

GAP = 0.28          # silence between phrases, seconds
LEAD = 0.25         # silence before the first word
TAIL = 0.90         # silence after the last word

# rough speaking time per word, used to spread words inside a phrase
def word_weight(w):
    letters = max(1, len(re.sub(r"[^A-Za-z]", "", w)))
    vowels = len(re.findall(r"[aeiouyAEIOUY]", w))
    return 0.55 + 0.055 * letters + 0.10 * vowels


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("command failed: %s\n%s" % (" ".join(cmd), proc.stderr))
    return proc.stdout


def wav_duration(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def synthesize(text, out_path):
    txt = os.path.join(AUDIO, "_phrase.txt")
    with open(txt, "w") as fh:
        fh.write(text)
    piper_cmd = ["piper"]
    if shutil.which("piper") is None:
        piper_cmd = ["nix-shell", "-p", "piper-tts", "--run", "piper"]
    run(piper_cmd + ["-m", VOICE, "-c", VOICE_CFG,
                      "-f", out_path, "-i", txt])
    os.remove(txt)
    return wav_duration(out_path)


def main():
    os.makedirs(AUDIO, exist_ok=True)
    tmp = os.path.join(AUDIO, "_parts")
    os.makedirs(tmp, exist_ok=True)

    phrase_audio = []
    for i, phrase in enumerate(PHRASES):
        p = os.path.join(tmp, "p%02d.wav" % i)
        dur = synthesize(phrase, p)
        phrase_audio.append((phrase, p, dur))
        print("PHRASE %d %.3fs  %s" % (i, dur, phrase))

    # ---- concatenate with the gaps
    sil = os.path.join(tmp, "sil.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=22050:cl=mono", "-t", "0.01", sil])
    sil_dur = wav_duration(sil)

    def sil_file(seconds):
        out = os.path.join(tmp, "sil_%d.wav" % int(seconds * 1000))
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "anullsrc=r=22050:cl=mono", "-t", "%.3f" % seconds, out])
        return out

    parts = [sil_file(LEAD)]
    for i, (phrase, p, dur) in enumerate(phrase_audio):
        parts.append(p)
        if i < len(phrase_audio) - 1:
            parts.append(sil_file(GAP))
    parts.append(sil_file(TAIL))
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w") as fh:
        for p in parts:
            fh.write("file '%s'\n" % os.path.abspath(p))
    wav_out = os.path.join(AUDIO, "dialogue.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listfile, "-ar", "22050", "-ac", "1", wav_out])

    total = wav_duration(wav_out)
    print("TOTAL %.3fs" % total)

    # ---- alignment
    words = []
    t = LEAD
    for (phrase, p, dur) in phrase_audio:
        toks = phrase.split()
        weights = [word_weight(w) for w in toks]
        wsum = sum(weights)
        start = t
        for w, wt in zip(toks, weights):
            d = dur * wt / wsum
            words.append({
                "word": w,
                "start": round(start, 4),
                "end": round(start + d, 4),
                "start_frame": int(round(start * 30)),
                "end_frame": int(round((start + d) * 30)),
            })
            start += d
        t += dur + GAP

    align = {
        "audio": "source/audio/dialogue.wav",
        "transcript": " ".join(PHRASES),
        "sample_rate": 22050,
        "fps": 30,
        "duration": round(total, 4),
        "lead_in": LEAD,
        "phrases": [{"text": phrase,
                     "start": round(LEAD + sum(d + GAP for (_, _, d)
                                               in phrase_audio[:i]), 4),
                     "end": round(LEAD + sum(d + GAP for (_, _, d)
                                             in phrase_audio[:i + 1])
                                  - GAP, 4)}
                    for i, (phrase, _, _) in enumerate(phrase_audio)],
        "words": words,
    }
    with open(os.path.join(AUDIO, "dialogue_alignment.json"), "w") as fh:
        json.dump(align, fh, indent=2)
    with open(os.path.join(AUDIO, "dialogue.txt"), "w") as fh:
        fh.write(" ".join(PHRASES) + "\n")

    # ---- transcript with timestamps
    with open(os.path.join(AUDIO, "dialogue_transcript.txt"), "w") as fh:
        fh.write("MORPHRIG - Operative Seven, spoken performance\n")
        fh.write("-" * 52 + "\n")
        for w in words:
            fh.write("[%6.2f - %6.2f]  %s\n"
                     % (w["start"], w["end"], w["word"]))
        fh.write("-" * 52 + "\n")
        fh.write("total %.2f s, %d words\n" % (total, len(words)))
    print("WORDS %d" % len(words))
    print("DIALOGUE_DONE")


if __name__ == "__main__":
    main()
