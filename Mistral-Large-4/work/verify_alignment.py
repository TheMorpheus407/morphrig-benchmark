#!/usr/bin/env python3
"""Verify source/audio/dialogue_alignment.json against the delivered audio
and the espeak-ng synthesis event stream (work/dlg/events.txt), which is the
ground truth for every timing in the JSON. Nothing is hardcoded: word starts,
phoneme spans, clause slots and pauses are all recomputed from the raw event
stream and compared exactly. Also checks (against the WAV) that the pause
regions the event stream claims are silent, which validates the slot model.

Run inside nix-shell (ffprobe not needed): python3 work/verify_alignment.py
"""
import json
import math
import os
import re
import struct
import sys
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(TASK, "source", "audio")
EVENTS = os.path.join(TASK, "work", "dlg", "events.txt")
FPS = 30

fails = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


with open(os.path.join(A, "dialogue_alignment.json")) as f:
    al = json.load(f)

# ---------------------------------------------------------------- events ---
# parse the raw synthesis event stream (type text_pos length ms id)
events = []
audio_info = None
with open(EVENTS) as f:
    for line in f:
        parts = line.rstrip("\n").split(" ", 4)
        if not parts:
            continue
        if parts[0] == "AUDIO":
            audio_info = (int(parts[1]), int(parts[2]), float(parts[3]))
            continue
        if len(parts) < 5:
            continue
        events.append({"type": int(parts[0]), "text_pos": int(parts[1]),
                       "length": int(parts[2]), "ms": int(parts[3]),
                       "id": parts[4]})
rate, samples, dur = audio_info
total = samples / float(rate)
# full-stream spans: each event runs to the next event's position
for i, e in enumerate(events):
    e["start"] = e["ms"] / 1000.0
    e["end"] = (events[i + 1]["ms"] / 1000.0 if i + 1 < len(events)
                else dur)
word_ev = [e for e in events if e["type"] == 1]
end_ev = [e for e in events if e["type"] == 5]
ph_ev = [e for e in events if e["type"] == 7]
speech_ev = [e for e in ph_ev if not e["id"].startswith("_")]
pause_ev = [e for e in ph_ev if e["id"].startswith("_")]

# transcript -> word list + 1-based char positions (same as make_dialogue)
tr = al["transcript"]
toks = re.findall(r"[A-Za-z']+|[.,!?;:]", tr)
words_txt = []
i = 0
while i < len(toks):
    t = toks[i]
    if re.match(r"[A-Za-z']", t):
        punct = ""
        if i + 1 < len(toks) and re.match(r"[.,!?;:]", toks[i + 1]):
            punct = toks[i + 1]
            i += 1
        words_txt.append((t, punct))
    i += 1
word_pos, word_len = [], []
for m in re.finditer(r"[A-Za-z']+|[.,!?;:]", tr):
    t = m.group(0)
    if re.match(r"[A-Za-z']", t):
        word_pos.append(m.start() + 1)
        word_len.append(len(t))
n = len(words_txt)
pos_to_idx = {word_pos[k]: k for k in range(n)}
# WORD event -> word index (ground truth for word starts)
truth_word_start = {}
for e in word_ev:
    k = pos_to_idx.get(e["text_pos"])
    if k is None or word_len[k] != e["length"]:
        check(False, "WORD event (%d, len %d) matches a transcript word"
              % (e["text_pos"], e["length"]))
        sys.exit(1)
    truth_word_start[k] = e["ms"] / 1000.0
# clause slots: [first WORD event of the clause .. END event]
clause_ends = [e["ms"] / 1000.0 for e in end_ev]
clause_starts = [word_ev[0]["ms"] / 1000.0] + clause_ends[:-1]

print("== schema ==")
for k in ("asset", "fps", "sample_rate_hz", "channels", "bits_per_sample",
          "duration_seconds", "duration_frames", "speech_region",
          "transcript", "tts", "timing", "method", "phoneme_to_viseme",
          "viseme_to_jaw_open", "clauses", "words", "phonemes", "pauses",
          "visemes"):
    check(k in al, "field %s present" % k)
check(al["fps"] == FPS, "fps == 30")
check(al["sample_rate_hz"] == 44100, "sample rate 44100")
check(al["channels"] == 1 and al["bits_per_sample"] == 16, "mono s16")
check(abs(al["duration_seconds"] - total) < 0.001,
      "json duration %.4f == event-stream audio %.4f"
      % (al["duration_seconds"], total))

print("== audio file ==")
w = wave.open(os.path.join(A, "dialogue.wav"))
nfr, wrate = w.getnframes(), w.getframerate()
wch, wsw = w.getnchannels(), w.getsampwidth()
wav_bytes = w.readframes(nfr)
w.close()
dur_wav = nfr / wrate
check(wrate == 44100 and wch == 1 and wsw == 2, "wav is 44100 Hz mono s16")
check(12.0 <= dur_wav <= 18.0, "duration %.3f s inside 12-18 s" % dur_wav)
check(abs(dur_wav - al["duration_seconds"]) < 0.01,
      "json duration %.4f matches wav %.4f" % (al["duration_seconds"], dur_wav))
check(al["duration_frames"] == int(round(dur_wav * FPS)),
      "duration_frames %d == round(dur*30)" % al["duration_frames"])
samples16 = struct.unpack("<%dh" % nfr, wav_bytes)


def rms(t0, t1):
    a, b = int(t0 * wrate), int(t1 * wrate)
    seg = samples16[a:b]
    if not seg:
        return 0.0
    return math.sqrt(sum(float(x) * x for x in seg) / len(seg))


peak = max(abs(s) for s in samples16[::7])  # subsampled peak, cheap

print("== words (vs WORD events) ==")
words = al["words"]
check(len(words) == n == 30, "30 words (got %d)" % len(words))
joined = " ".join(wd["word"] + wd["punct"] for wd in words)
check(joined == tr, "word+punct sequence reconstructs the transcript")
prev_slot_end = None
for k, wd in enumerate(words):
    check(wd["index"] == k, "word %d index field" % k)
    check((wd["word"], wd["punct"]) == words_txt[k],
          "word %d text %r%s" % (k, wd["word"], wd["punct"]))
    check(abs(wd["start"] - truth_word_start[k]) < 5e-4,
          "word %d (%s) start %.4f == WORD event %.4f"
          % (k, wd["word"], wd["start"], truth_word_start[k]))
    check(wd["end"] > wd["start"], "word %d (%s) has positive span"
          % (k, wd["word"]))
    check(abs(wd["slot_end"] - (truth_word_start[k + 1] if k + 1 < n
                               else clause_ends[-1])) < 5e-4,
          "word %d (%s) slot_end %.4f == next WORD/END position"
          % (k, wd["word"], wd["slot_end"]))
    if prev_slot_end is not None:
        check(wd["start"] >= prev_slot_end - 1e-6,
              "word %d (%s) slot starts at/after previous slot end"
              % (k, wd["word"]))
    prev_slot_end = wd["slot_end"]
    check(wd["start_frame"] == int(wd["start"] * FPS) + 1,
          "word %d start_frame convention" % k)
    check(1 <= wd["start_frame"] <= al["duration_frames"] and
          1 <= wd["end_frame"] <= al["duration_frames"],
          "word %d frames within 1..%d" % (k, al["duration_frames"]))
# word slots tile [0, clause_ends[-1]]
check(abs(words[0]["start"]) < 5e-4, "first word slot starts at 0")
check(abs(words[-1]["slot_end"] - clause_ends[-1]) < 5e-4,
      "last word slot ends at the final END event (%.3f)"
      % clause_ends[-1])

print("== phonemes (vs full event-stream spans) ==")
phs = al["phonemes"]
check(len(phs) == len(speech_ev) == 107,
      "107 speech phonemes (got %d, events %d)" % (len(phs), len(speech_ev)))
ok_span = ok_mono = ok_word = True
for i, (pj, ev) in enumerate(zip(phs, speech_ev)):
    if abs(pj["start"] - ev["start"]) > 5e-4 or \
            abs(pj["end"] - ev["end"]) > 5e-4:
        ok_span = False
        print("    phoneme %d %r: json [%.4f, %.4f] events [%.4f, %.4f]"
              % (i, pj["phoneme"], pj["start"], pj["end"],
                 ev["start"], ev["end"]))
    if i and phs[i]["start"] < phs[i - 1]["end"] - 1e-9:
        ok_mono = False
check(ok_span, "every phoneme span == [event pos, next event pos)")
check(ok_mono, "phoneme spans monotonic without overlap")
# phonemes tile each word's speech exactly: they start inside the word's
# slot (at/after the WORD event) and end exactly at the word's speech end
by_word = {}
for pj in phs:
    by_word.setdefault(pj["word_index"], []).append(pj)
for k, wd in enumerate(words):
    pl = by_word.get(k, [])
    if not pl or not (wd["start"] - 1e-6 <= pl[0]["start"]) or \
            abs(pl[-1]["end"] - wd["end"]) > 5e-4:
        ok_word = False
        print("    word %d (%s): phonemes [%.4f, %.4f] vs word slot "
              "[%.4f, ...] end %.4f"
              % (k, wd["word"], pl[0]["start"] if pl else -1,
                 pl[-1]["end"] if pl else -1, wd["start"], wd["end"]))
    for a, b in zip(pl, pl[1:]):
        if abs(a["end"] - b["start"]) > 1e-9:
            ok_word = False
check(ok_word, "phonemes tile each word's speech exactly, contiguously")


def base_phoneme(name):
    """Same rule as make_dialogue.base_phoneme: strip leading stress/linking
    marks (' and ,) and trailing silent modifiers (2 # - ,), never eating
    the last remaining character (a trailing ':' is part of long vowels)."""
    n = name
    while n and n[0] in "',":
        n = n[1:]
    while len(n) > 1 and n[-1] in "2#-,":
        n = n[:-1]
    return n


check([pj["phoneme"] for pj in phs] ==
      [base_phoneme(e["id"]) for e in speech_ev],
      "phoneme name sequence matches the event stream")
visemes_ok = all(ph["viseme"] in al["viseme_to_jaw_open"] for ph in phs)
check(visemes_ok, "every phoneme viseme is in viseme_to_jaw_open")
jaw_ok = all(abs(ph["jaw"] - al["viseme_to_jaw_open"][ph["viseme"]]) < 1e-9
             for ph in phs)
check(jaw_ok, "phoneme jaw values match the viseme table")
# phoneme -> viseme mapping is the documented table
map_ok = all(ph["viseme"] == al["phoneme_to_viseme"].get(ph["phoneme"], "REST")
             for ph in phs)
check(map_ok, "phoneme visemes follow phoneme_to_viseme")

print("== pauses (vs pause phoneme events) ==")
pauses = al["pauses"]
check(len(pauses) == len(pause_ev),
      "%d pause spans (got %d)" % (len(pause_ev), len(pauses)))
ok_pause = True
for pj, ev in zip(pauses, pause_ev):
    if pj["name"] != ev["id"] or abs(pj["start"] - ev["start"]) > 5e-4 \
            or abs(pj["end"] - ev["end"]) > 5e-4:
        ok_pause = False
check(ok_pause, "pause spans match the pause phoneme events")
# the claimed pauses must be silent in the delivered audio (slot model)
quiet = True
for pj in pauses:
    if rms(pj["start"], pj["end"]) > 0.02 * peak:
        quiet = False
        print("    pause %s [%.3f, %.3f] rms %.1f > 2%% of peak %.1f"
              % (pj["name"], pj["start"], pj["end"],
                 rms(pj["start"], pj["end"]), peak))
if rms(0.0, speech_ev[0]["start"]) > 0.02 * peak:
    quiet = False
if rms(speech_ev[-1]["end"], dur_wav) > 0.02 * peak:
    quiet = False
check(quiet, "all pause regions + lead-in/tail are silent in the WAV "
      "(validates the slot model against the audio)")

print("== clauses (vs END events) ==")
cls = al["clauses"]
check(len(cls) == len(end_ev) == 6, "6 clauses (got %d)" % len(cls))
for c in cls:
    check(abs(c["start"] - clause_starts[c["index"]]) < 5e-4,
          "clause %d start %.4f == slot start %.4f"
          % (c["index"], c["start"], clause_starts[c["index"]]))
    check(abs(c["end"] - clause_ends[c["index"]]) < 5e-4,
          "clause %d end %.4f == END event %.4f"
          % (c["index"], c["end"], clause_ends[c["index"]]))
    cw = [wd for wd in words if wd["clause"] == c["index"]]
    check([wd["word"] for wd in cw] == c["words"],
          "clause %d word list matches" % c["index"])
    sp = [e for wd in cw for e in by_word.get(wd["index"], [])]
    check(abs(c["speech_start"] - sp[0]["start"]) < 5e-4 and
          abs(c["speech_end"] - sp[-1]["end"]) < 5e-4,
          "clause %d speech region [%.3f, %.3f]"
          % (c["index"], c["speech_start"], c["speech_end"]))
    check(abs(c["pause_start"] - c["speech_end"]) < 1e-9 and
          abs(c["pause_end"] - c["end"]) < 5e-4,
          "clause %d pause runs speech_end..slot end" % c["index"])
counts = [sum(1 for wd in words if wd["clause"] == c) for c in range(6)]
check(counts == [3, 4, 6, 8, 5, 4],
      "clause word counts 3/4/6/8/5/4 (got %s)" % counts)

print("== visemes (merged) ==")
vs = al["visemes"]
merged = []
for ph in phs:
    if merged and merged[-1]["viseme"] == ph["viseme"] \
            and abs(merged[-1]["end"] - ph["start"]) < 1e-4:
        merged[-1]["end"] = ph["end"]
        merged[-1]["jaw"] = max(merged[-1]["jaw"], ph["jaw"])
    else:
        merged.append({"viseme": ph["viseme"], "jaw": ph["jaw"],
                       "start": ph["start"], "end": ph["end"]})
check(len(vs) == len(merged),
      "%d merged visemes (recomputed %d)" % (len(vs), len(merged)))
ok_v = len(vs) == len(merged) and all(
    v["viseme"] == m["viseme"] and abs(v["start"] - m["start"]) < 5e-4
    and abs(v["end"] - m["end"]) < 5e-4 and abs(v["jaw"] - m["jaw"]) < 1e-9
    for v, m in zip(vs, merged))
check(ok_v, "merged viseme spans/jaws match a recomputation from phonemes")
ok = all(vs[i]["end"] <= vs[i + 1]["start"] + 1e-6
         for i in range(len(vs) - 1))
check(ok, "merged visemes monotonic")

print("== speech region ==")
sr = al["speech_region"]
check(abs(sr[0] - speech_ev[0]["start"]) < 5e-4 and
      abs(sr[1] - speech_ev[-1]["end"]) < 5e-4,
      "speech region [%.3f, %.3f] == first/last speech phoneme span"
      % (sr[0], sr[1]))
check(vs[0]["start"] >= sr[0] - 1e-6 and vs[-1]["end"] <= sr[1] + 1e-6,
      "visemes within the speech region")

print()
if fails:
    print("FAILED %d checks:" % len(fails))
    for m in fails:
        print("  - " + m)
    sys.exit(1)
print("ALL ALIGNMENT CHECKS PASSED")
