#!/usr/bin/env python3
"""Generate original, locally synthesized dialogue and measured word timing."""
from pathlib import Path
import array
import json
import math
import re
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "source" / "audio"
WORK = ROOT / "source" / "audio" / ".synthesis"
TEXT = "Hold the lane. Keep the network steady. I've got the relay. Watch the left flank. Now. Stabilize the link on my signal. Good. We hold together."


def synth():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    words = TEXT.split()
    entries = []
    rate = 105
    for index, token in enumerate(words):
        path = WORK / f"word_{index:02d}.wav"
        subprocess.run([
            "nix-shell", "-p", "espeak-ng", "--run",
            f"espeak-ng -v en-us -s {rate} -p 32 -a 145 -g 3 -w {path} {token!r}"
        ], check=True, stdout=subprocess.DEVNULL)
        with wave.open(str(path), "rb") as reader:
            rate_hz = reader.getframerate()
            samples = array.array('h', reader.readframes(reader.getnframes()))
        frame = max(1, int(rate_hz * .012))
        levels = [max(abs(v) for v in samples[i:i + frame]) for i in range(0, len(samples), frame)]
        active = [i for i, value in enumerate(levels) if value > 100]
        if active:
            start = max(0, active[0] * frame - int(rate_hz * .018))
            end = min(len(samples), (active[-1] + 1) * frame + int(rate_hz * .024))
            samples = samples[start:end]
        samples = normalize(samples, rate_hz)
        entries.append({"token": token, "samples": samples, "rate": rate_hz})

    assembled = array.array('h')
    cursor = 0.0
    for index, entry in enumerate(entries):
        assembled.extend(entry["samples"])
        entry["start"] = cursor
        cursor += len(entry["samples"]) / entry["rate"]
        entry["end"] = cursor
        punctuation = entry["token"][-1] in ".!?"
        gap = .40 if punctuation else .075
        if index in (2, 6, 10, 14, 15, 21, 22):
            gap += .20
        if index == len(entries) - 1:
            gap = .30
        assembled.extend([0] * int(entry["rate"] * gap))
        cursor += gap
    target = 15.2
    duration = len(assembled) / entries[0]["rate"]
    if not 14.2 <= duration <= 16.8:
        factor = target / duration
        resampled = array.array('h')
        for i in range(int(len(assembled) * factor)):
            source = i / factor
            left = int(source)
            frac = source - left
            right = min(left + 1, len(assembled) - 1)
            resampled.append(round(assembled[left] * (1 - frac) + assembled[right] * frac))
        assembled = resampled
        for entry in entries:
            entry["start"] *= factor
            entry["end"] *= factor
    path = OUT / "dialogue.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(entries[0]["rate"])
        writer.writeframes(assembled.tobytes())
    duration = len(assembled) / entries[0]["rate"]
    word_records = []
    visemes = []
    for index, entry in enumerate(entries):
        clean = re.sub(r"[^A-Za-z']", "", entry["token"])
        phones = authored_phones(clean.lower())
        word = {"index": index, "word": clean, "start": round(entry["start"], 5), "end": round(entry["end"], 5)}
        total = sum(weight for _, weight in phones)
        phone_time = entry["start"]
        word["phonemes"] = []
        for control, weight in phones:
            phone_duration = (entry["end"] - entry["start"]) * weight / total
            record = {"time": round(phone_time, 5), "duration": round(phone_duration, 5), "control": control}
            word["phonemes"].append(record.copy())
            visemes.append(record)
            phone_time += phone_duration
        word_records.append(word)
    alignment = {
        "transcript": TEXT,
        "audio": "dialogue.wav",
        "sample_rate": entries[0]["rate"],
        "channels": 1,
        "duration_seconds": round(duration, 6),
        "source": "Original text; locally synthesized with eSpeak NG 1.52 en-us, then silence-trimmed, envelope-normalized and assembled per word. No voice cloning.",
        "timing_method": "Each word's active synthesized waveform was measured before assembly; alignment is therefore exact to the delivered assembled WAV, not an estimated external transcript.",
        "viseme_standard": "MorphRig authored controls: MBP lip closure, FV labiodental, AA open vowel, EE wide vowel, OO rounded vowel/funnel, TH tongue-to-teeth, CH postalveolar consonant. Not a proprietary viseme standard.",
        "words": word_records,
        "visemes": visemes,
    }
    (OUT / "dialogue.txt").write_text(TEXT + "\n", encoding="utf-8")
    (OUT / "dialogue_alignment.json").write_text(json.dumps(alignment, indent=2) + "\n", encoding="utf-8")
    if not 12 <= duration <= 18:
        raise RuntimeError(f"Dialogue length outside required range: {duration}")
    print(json.dumps({"audio": str(path), "duration": duration, "words": len(words), "visemes": len(visemes)}))
    for file in WORK.iterdir():
        file.unlink()
    WORK.rmdir()


def normalize(samples, rate):
    if not samples:
        return array.array('h', [0] * int(rate * .1))
    peak = max(abs(value) for value in samples) or 1
    gain = min(2.5, 22000 / peak)
    result = array.array('h', [max(-32767, min(32767, int(value * gain))) for value in samples])
    fade_in = max(1, int(rate * .009))
    fade_out = max(1, int(rate * .016))
    for i in range(min(fade_in, len(result))):
        result[i] = int(result[i] * i / fade_in)
    for i in range(min(fade_out, len(result))):
        result[-1 - i] = int(result[-1 - i] * i / fade_out)
    return result


def authored_phones(word):
    tokens = []
    i = 0
    vowels = set("aeiouy")
    while i < len(word):
        trio = word[i:i + 3]
        pair = word[i:i + 2]
        char = word[i]
        if pair == "th":
            tokens.append(("Viseme_TH", 1.25)); i += 2
        elif pair in ("ch", "sh") or trio == "dge":
            tokens.append(("Viseme_CH", 1.15)); i += len(pair)
        elif char in "mbp":
            tokens.append(("Viseme_MBP", .95)); i += 1
        elif char in "fv":
            tokens.append(("Viseme_FV", 1.0)); i += 1
        elif char in vowels:
            control = "Viseme_EE" if char in "eiy" else "Viseme_OO" if char in "ou" else "Viseme_AA"
            tokens.append((control, 1.65)); i += 1
        else:
            i += 1
    return tokens or [("Viseme_AA", 1.0)]


if __name__ == "__main__":
    synth()
