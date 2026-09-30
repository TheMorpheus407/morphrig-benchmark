#!/usr/bin/env python3
"""Author the original MorphRig speech WAV and native phoneme alignment.

Run through the prepared dependency: nix-shell -p espeak-ng --run
'python3 source/generators/speech.py'. No voice model, cloud service or
identifiable person's voice is used. eSpeak's synchronous audio callback
provides phoneme/word offsets from the SAME synthesis that writes the WAV.
"""
from __future__ import annotations

import argparse
import ctypes as C
import ctypes.util
import hashlib
import json
import math
import shutil
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = ("Hold this lane with me. The relay is unstable, but I can rebuild the link. "
        "Keep your eyes on the crossing. Breathe. We have a signal again. "
        "Now move together, and keep the network alive.")


class EventID(C.Union):
    _fields_ = [("number", C.c_int), ("name", C.c_char_p), ("string", C.c_char * 8)]


class Event(C.Structure):
    _fields_ = [("type", C.c_int), ("unique_identifier", C.c_uint),
                ("text_position", C.c_int), ("length", C.c_int),
                ("audio_position", C.c_int), ("sample", C.c_int),
                ("user_data", C.c_void_p), ("id", EventID)]


def find_library():
    """Resolve the active tool, not a historical private machine path."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if exe:
        install = Path(exe).resolve().parents[1]
        for candidate in (install / "lib/libespeak-ng.so", install / "lib/libespeak.so"):
            if candidate.exists():
                return str(candidate), str(install / "share")
    lib = C.util.find_library("espeak-ng") or C.util.find_library("espeak")
    if lib:
        return lib, None
    raise RuntimeError("Run: nix-shell -p espeak-ng --run 'python3 source/generators/speech.py'")


def classify(phoneme):
    """Public, anatomical seven-class mapping for eSpeak mnemonics."""
    p = phoneme.strip("' ,").replace("_", "")
    if p in ("", ":", "pau", "sil"):
        return "silence"
    if p in ("p", "b", "m"):
        return "closure"
    if p in ("f", "v"):
        return "labiodental"
    if p in ("T", "D", "l", "n", "t", "d", "L", "N"):
        return "tongue"
    if p in ("w", "u", "u:", "U", "U@", "o", "o:", "oU", "O", "O:", "O@", "O2", "aU", "OI", "0"):
        return "round"
    if p in ("i", "i:", "I", "I#", "I@", "e", "e:", "E", "E:", "eI", "aI", "j", "e@"):
        return "wide"
    if p in ("a", "a:", "A", "A:", "V", "@", "@:", "@L", "3", "3:", "{", "&", "a#", "@2"):
        return "open"
    return "consonant"


def synthesize(rate=154):
    library, data = find_library()
    lib = C.CDLL(library)
    callback_type = C.CFUNCTYPE(C.c_int, C.POINTER(C.c_short), C.c_int, C.POINTER(Event))
    lib.espeak_Initialize.argtypes = [C.c_int, C.c_int, C.c_char_p, C.c_int]
    lib.espeak_Initialize.restype = C.c_int
    lib.espeak_SetSynthCallback.argtypes = [callback_type]
    lib.espeak_SetVoiceByName.argtypes = [C.c_char_p]
    lib.espeak_SetParameter.argtypes = [C.c_int, C.c_int, C.c_int]
    lib.espeak_Synth.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, C.c_int,
                                C.c_uint, C.c_uint, C.POINTER(C.c_uint), C.c_void_p]
    lib.espeak_Info.argtypes = [C.POINTER(C.c_char_p)]
    lib.espeak_Info.restype = C.c_char_p
    sample_rate = lib.espeak_Initialize(2, 20, data.encode() if data else None, 1 | 0x8000)
    if sample_rate <= 0:
        raise RuntimeError("eSpeak initialization failed")
    chunks, events = [], []

    @callback_type
    def callback(samples, count, queue):
        if samples and count:
            chunks.append(C.string_at(samples, count * 2))
        i = 0
        while queue[i].type:
            event = queue[i]
            record = {"type": event.type, "start": event.audio_position / 1000,
                      "text_position": event.text_position, "length": event.length}
            if event.type == 7:
                record["phoneme"] = bytes(event.id.string).decode("utf-8", "replace").rstrip("\0")
            events.append(record)
            i += 1
        return 0

    lib.espeak_SetSynthCallback(callback)
    if lib.espeak_SetVoiceByName(b"en-us"):
        raise RuntimeError("Built-in generic English voice unavailable")
    lib.espeak_SetParameter(1, rate, 0)   # espeakRATE
    lib.espeak_SetParameter(2, 90, 0)     # amplitude
    lib.espeak_SetParameter(3, 44, 0)     # pitch, generic synthetic voice
    lib.espeak_SetParameter(4, 56, 0)     # pitch range
    identifier = C.c_uint()
    encoded = TEXT.encode() + b"\0"
    error = lib.espeak_Synth(encoded, len(encoded), 0, 1, 0, 1 | 0x1000,
                             C.byref(identifier), None)
    if error:
        raise RuntimeError(f"eSpeak synthesis failed: {error}")
    lib.espeak_Synchronize()
    version = lib.espeak_Info(None).decode()
    lib.espeak_Terminate()
    return sample_rate, b"".join(chunks), events, version


def build(output=None):
    output = Path(output) if output else ROOT / "source/audio"
    output.mkdir(parents=True, exist_ok=True)
    rate = 154
    sr, pcm, raw, version = synthesize(rate)
    seconds = len(pcm) / (2 * sr)
    if not 12 <= seconds <= 17.6:
        # Retiming is a fresh synthesis with a shared callback, never a
        # timing guess against independently produced audio.
        rate = int(round(rate * seconds / 15.8))
        sr, pcm, raw, version = synthesize(rate)
        seconds = len(pcm) / (2 * sr)
    lead = 0.20
    total = math.ceil((lead + seconds + 0.16) * 30) / 30
    if not 12 <= total <= 18:
        raise RuntimeError(f"Dialogue length outside required interval: {total:.3f}s")
    lead_samples = round(lead * sr)
    lead = lead_samples / sr
    tail_samples = round(total * sr) - lead_samples - len(pcm) // 2
    pcm = b"\0\0" * lead_samples + pcm + b"\0\0" * max(0, tail_samples)
    wav = output / "dialogue.wav"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sr)
        writer.writeframes(pcm)
    actual_duration = len(pcm) / (2 * sr)
    phonemes = [e for e in raw if e["type"] == 7]
    # Remove repeated native events at the same time, keeping all successive
    # real phonemes, including closure and short consonants.
    spans = []
    for i, p in enumerate(phonemes):
        start = p["start"] + lead
        end = (phonemes[i + 1]["start"] if i + 1 < len(phonemes) else seconds) + lead
        if end <= start:
            continue
        spans.append({"phoneme": p["phoneme"], "viseme": classify(p["phoneme"]),
                      "start": round(start, 6), "end": round(min(end, actual_duration), 6),
                      "text_position": p["text_position"]})
    word_events = [e for e in raw if e["type"] == 1]
    words = []
    for i, e in enumerate(word_events):
        start = e["start"] + lead
        end = (word_events[i + 1]["start"] if i + 1 < len(word_events) else seconds) + lead
        position = max(0, e["text_position"] - 1)
        words.append({"word": TEXT[position:position + e["length"]],
                      "start": round(start, 6), "end": round(end, 6),
                      "text_position": e["text_position"]})
    def at_word(word, default):
        found = [w["start"] for w in words if w["word"].strip(",.!?").lower() == word]
        return found[0] if found else default
    alignment = {"schema_version": 1, "audio": "source/audio/dialogue.wav",
                 "transcript": TEXT, "duration_seconds": actual_duration,
                 "sample_rate": sr, "channels": 1, "sample_width_bytes": 2,
                 "authored_fps": 30, "frame_count": round(total * 30) + 1,
                 "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                 "synthesis": {"engine": "eSpeak NG", "version": version,
                               "voice": "en-us (generic built-in synthetic voice)",
                               "rate_wpm": rate, "phoneme_alphabet": "eSpeak mnemonics",
                               "alignment_method": "native espeakEVENT_WORD and espeakEVENT_PHONEME audio-position callbacks during the exact WAV synthesis",
                               "license": "GPL-3.0-or-later tool; generated original text/audio authored for this assignment"},
                 "words": words, "phonemes": spans,
                 "performance_cues": [
                     {"time": 0.0, "event": "concern_scan_left", "description": "Concerned brow and leftward gaze; palm invites support."},
                     {"time": at_word("relay", 2.5), "event": "look_wrist", "description": "Inspect cybernetic wrist while explaining relay instability."},
                     {"time": at_word("crossing", 7.2), "event": "point_crossing", "description": "Organic hand indicates crossing to the left."},
                     {"time": at_word("breathe", 8.0), "event": "breath_release", "description": "Slow chest release, soften concern; deliberately re-center eyes."},
                     {"time": at_word("signal", 10.0), "event": "confidence_shift", "description": "Brows release, cheeks lift into asymmetric confident smile."},
                     {"time": at_word("together", 12.4), "event": "forward_gesture", "description": "Invite collective forward movement with open hand."},
                     {"time": total - 0.15, "event": "settle", "description": "Mouth closes, eyes and hands settle into combat-ready stance."}],
                 "viseme_controls": ["closure", "labiodental", "open", "wide", "round", "tongue", "consonant"]}
    (output / "dialogue.txt").write_text(TEXT + "\n", encoding="utf-8")
    (output / "dialogue_alignment.json").write_text(json.dumps(alignment, indent=2) + "\n")
    print(json.dumps({"duration": actual_duration, "frames": alignment["frame_count"],
                      "sample_rate": sr, "words": len(words), "phonemes": len(spans),
                      "sha256": alignment["wav_sha256"], "rate_wpm": rate}, indent=2))
    return alignment


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    build(arguments.output)
