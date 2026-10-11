#!/usr/bin/env python3
"""
Build source/audio/dialogue.wav + source/audio/dialogue_alignment.json from
source/audio/dialogue.txt using espeak-ng (GPL-3.0-or-later, no voice cloning).

Run inside:  nix-shell -p espeak-ng --run 'python3 work/make_dialogue.py'

Method (documented in docs/rig_usage.md and in the alignment JSON itself):
  1. Synthesize the full transcript (with punctuation) as one continuous
     natural utterance with the espeak-ng CLI; pick a voice speed so the
     total lands ~13.5 s inside the SPEC-required 12-18 s window.
  2. Timing comes from the synthesizer itself: work/espeak_timing.c links
     libespeak-ng, re-synthesizes the identical text/voice/speed/pitch with
     phoneme events enabled (espeakINITIALIZE_PHONEME_EVENTS) and dumps the
     synthesis event stream — WORD / SENTENCE / END / PHONEME events with
     millisecond audio positions — plus the raw audio. The helper's audio is
     verified byte-identical to the CLI WAV, so event positions map 1:1
     onto the delivered dialogue.wav timeline (the delivered WAV is the CLI
     output resampled 22050 -> 44100 Hz; resampling preserves time).
  3. Word identity comes from WORD events (1-based character position +
     length in the transcript). The event stream arrives in audio order
     and every event's span runs to the NEXT event's position (of any
     type), so the stream tiles the whole utterance exactly: a word's
     slot starts at its WORD event, its last phoneme ends where the next
     event (a pause phoneme or the next word's WORD event) begins, and
     all inter-word / inter-clause silence is carried by pause phonemes
     ("_:" clause pause, "_!" word gap, "_" lead-in). This slot model was
     verified against the audio itself: the gaps between a word-final
     phoneme and the next word's first phoneme measure ~0 RMS, i.e. the
     word-final phoneme really ends at the next event's position. END
     events mark the clause slot ends. The phoneme name sequence is
     cross-checked against `espeak-ng -x` (string level).
  4. Map phonemes -> visemes and visemes -> jaw-open amounts (tables below;
     the jaw table matches tools/rig_ops.py VISEMES).
  5. Resample the full-line WAV 22050 -> 44100 Hz (ffmpeg, else fallback).
"""
import array
import json
import os
import re
import shutil
import subprocess
import sys
import wave

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(TASK, "source", "audio")
WORK = os.path.join(TASK, "work", "dlg")
os.makedirs(WORK, exist_ok=True)

FPS = 30
PITCH = 40
VOICE = "en-us"
ESPEAK_VERSION = "1.52.0.1"
TARGET_TOTAL = 13.5          # aim inside the 12-18 s window

# espeak-ng en phoneme mnemonics (for the -x cross-check). Multi-char first.
MULTI = ["tS", "dZ", "aI", "aU", "eI", "oU", "@U",
         "a:", "A:", "Q:", "E:", "I:", "O:", "U:", "u:", "i:", "o:",
         "@:", "3:", "8:", "2:"]
SINGLES = set("pbmfvdTtDdnNszSZlrjwhkg@AEIOUaeiou0238^VcqQxJyJ")
MODIFIERS = set("2,#-")      # silent, attach to preceding phoneme
SKIPMARKS = set("'_,! :")    # stress / pause / lengthen / separator: no unit

# Phoneme event names carry stress/modifier marks attached: leading "'" or
# "," (stress / linking), trailing "2" "#" "-" "," (silent modifiers). The
# base phoneme is the name with those marks stripped (a trailing ":" is part
# of long-vowel mnemonics and is kept). Pause phonemes are named "_", "_:"
# or "_!" (any name starting with "_").

# phoneme mnemonic -> viseme (documented mapping; see docs/rig_usage.md)
VISEME = {
    "p": "MBP", "b": "MBP", "m": "MBP",
    "f": "FV", "v": "FV",
    "T": "TH", "D": "TH",
    "k": "KG", "g": "KG", "N": "KG", "c": "KG", "q": "KG", "x": "KG",
    "s": "SZ", "z": "SZ", "S": "SZ", "Z": "SZ", "tS": "SZ", "dZ": "SZ",
    "l": "L", "r": "R",
    "w": "UW", "j": "IH", "h": "IH", "y": "IH", "J": "IH",
    "t": "REST", "d": "REST", "n": "REST",
    "i": "EE", "eI": "EE", "i:": "EE", "I:": "EE",
    "I": "IH", "@": "IH", "3": "IH", "3:": "IH", "2": "IH",
    "^": "IH", "e": "IH", "8": "IH", "8:": "IH", "2:": "IH",
    "a": "AW", "A": "AW", "0": "AW", "aU": "AW", "aI": "AW",
    "a:": "AW", "A:": "AW", "E": "AW", "E:": "AW", "V": "AW",
    "O": "OH", "o": "OH", "O:": "OH", "o:": "OH", "Q": "OH", "O@": "OH",
    "oU": "OO", "u": "OO", "U": "OO", "u:": "OO", "U:": "OO", "@U": "OO",
    "U@": "OO",
}

# viseme -> jaw_open amount (0..1 of the rig's full 65-degree jaw range).
# Matches tools/rig_ops.py VISEMES so the alignment and the rig agree.
JAW = {"REST": 0.0, "MBP": 0.08, "FV": 0.18, "TH": 0.3, "KG": 0.15,
       "SZ": 0.15, "L": 0.45, "R": 0.3, "IH": 0.25, "EE": 0.2,
       "AW": 0.95, "OH": 0.5, "OO": 0.3, "UW": 0.35}


def log(msg):
    print(msg, flush=True)


def synth(path, text, speed):
    r = subprocess.run(["espeak-ng", "-v", VOICE, "-s", str(speed),
                        "-p", str(PITCH), "-w", path, text],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("espeak-ng failed (%d): %s" % (r.returncode, r.stderr))
    return path


def load_wav(path):
    w = wave.open(path)
    assert w.getframerate() == 22050 and w.getnchannels() == 1 \
        and w.getsampwidth() == 2, "unexpected wav format in %s" % path
    raw = w.readframes(w.getnframes())
    rate = w.getframerate()
    w.close()
    a = array.array("h")
    a.frombytes(raw)
    return a, rate


def envelope(a, rate, hop_s=0.010, win_s=0.020):
    hop = int(hop_s * rate)
    win = int(win_s * rate)
    env = []
    for s in range(0, max(1, len(a) - win), hop):
        acc = 0
        for v in a[s:s + win]:
            acc += v * v
        env.append((acc / win) ** 0.5)
    return env, hop_s


def speech_region(a, rate, hop_s=0.010, win_s=0.020, rel_thr=0.05):
    """Energy-measured speech region (onset_s, offset_s) of a mono signal."""
    env, hop_s = envelope(a, rate, hop_s, win_s)
    if not env:
        return 0.0, 0.0
    peak = max(env)
    if peak <= 0:
        return 0.0, 0.0
    thr = rel_thr * peak
    sustain = 3  # 30 ms
    onset = None
    for i in range(len(env)):
        if env[i] > thr and all(env[j] > thr * 0.5
                               for j in range(i, min(len(env), i + sustain))):
            onset = i * hop_s
            break
    offset = None
    for i in range(len(env) - 1, -1, -1):
        if env[i] > thr and all(env[j] > thr * 0.5
                               for j in range(max(0, i - sustain + 1), i + 1)):
            offset = (i + 1) * hop_s
            break
    if onset is None or offset is None or offset <= onset:
        return 0.0, 0.0
    return onset, offset


def full_line_mnemonics(transcript):
    """espeak-ng -x on the full transcript -> list of clauses, each a list of
    per-word mnemonic strings (words space-separated per clause)."""
    r = subprocess.run(["espeak-ng", "-v", VOICE, "-x", "-q", transcript],
                       capture_output=True, text=True)
    clauses = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line:
            clauses.append(line.split(" "))
    return clauses


def tokenize(mnem):
    """Split an espeak -x mnemonic string into phoneme units.
    Returns list of (start_char, end_char, base_phoneme)."""
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
            if c in SINGLES:
                tok = c
            else:
                log("  WARN: unknown mnemonic char %r in %r (skipped)" % (c, mnem))
                i += 1
                continue
        units.append((i, i + len(tok), tok))
        i += len(tok)
    return units


def build_timing_helper():
    """Compile work/espeak_timing.c against the nix espeak-ng (headers + lib)
    if the binary is missing or stale. Returns the binary path or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "espeak_timing.c")
    binp = os.path.join(here, "espeak_timing")
    espeak = shutil.which("espeak-ng")
    if not espeak:
        log("ERROR: espeak-ng not on PATH. Run inside: "
            "nix-shell -p espeak-ng --run 'python3 work/make_dialogue.py'")
        return None
    prefix = os.path.dirname(os.path.dirname(espeak))
    inc = os.path.join(prefix, "include")
    lib = os.path.join(prefix, "lib")
    if not os.path.exists(os.path.join(inc, "espeak-ng", "speak_lib.h")) \
            or not os.path.exists(os.path.join(lib, "libespeak-ng.so")):
        log("ERROR: espeak-ng headers/library not found under %s" % prefix)
        return None
    if not os.path.exists(binp) \
            or os.path.getmtime(src) > os.path.getmtime(binp):
        gcc = shutil.which("gcc") or shutil.which("cc")
        if not gcc:
            log("ERROR: gcc/cc not found (needed to build the timing helper)")
            return None
        r = subprocess.run([gcc, "-O2", "-I" + inc, "-o", binp, src,
                            "-L" + lib, "-lespeak-ng",
                            "-Wl,-rpath," + lib],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log("ERROR: building espeak_timing failed:\n%s" % r.stderr)
            return None
        log("built work/espeak_timing (libespeak-ng synthesis-event dumper)")
    return binp


def run_timing_helper(binp, text_path, speed):
    """Run the timing helper; returns (events, audio_info).
    events: list of dicts {type, text_pos, length, ms, id} in stream order
    (type: 1=WORD 2=SENTENCE 5=END 7=PHONEME 8=SAMPLERATE).
    audio_info: (rate, samples, duration_s)."""
    ev = os.path.join(WORK, "events.txt")
    raw = os.path.join(WORK, "api_audio.raw")
    r = subprocess.run([binp, text_path, str(speed), str(PITCH), ev, raw, VOICE],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("ERROR: espeak_timing failed: %s" % r.stderr)
        return None, None
    log("  " + r.stderr.strip())
    events = []
    audio = None
    with open(ev) as f:
        for line in f:
            parts = line.rstrip("\n").split(" ", 4)
            if not parts:
                continue
            if parts[0] == "AUDIO":
                audio = (int(parts[1]), int(parts[2]), float(parts[3]))
                continue
            if len(parts) < 5:
                continue
            events.append({"type": int(parts[0]), "text_pos": int(parts[1]),
                           "length": int(parts[2]), "ms": int(parts[3]),
                           "id": parts[4]})
    return events, audio


def base_phoneme(name):
    """Strip stress/linking marks (leading ' and ,) and silent modifiers
    (trailing 2 # - ,) from a phoneme event name. Keeps long-vowel ':'."""
    n = name
    while n and n[0] in "',":
        n = n[1:]
    while len(n) > 1 and n[-1] in "2#-,":
        n = n[:-1]
    return n


def main():
    txt_path = os.path.join(AUDIO, "dialogue.txt")
    with open(txt_path) as f:
        transcript = f.read().strip()
    toks = re.findall(r"[A-Za-z']+|[.,!?;:]", transcript)
    words = []          # (word, punct)
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z']", t):
            punct = ""
            if i + 1 < len(toks) and re.match(r"[.,!?;:]", toks[i + 1]):
                punct = toks[i + 1]
                i += 1
            words.append((t, punct))
        i += 1
    # 1-based char offsets + lengths of each word in the transcript
    word_pos = []
    word_len = []
    for m in re.finditer(r"[A-Za-z']+|[.,!?;:]", transcript):
        t = m.group(0)
        if re.match(r"[A-Za-z']", t):
            word_pos.append(m.start() + 1)   # 1-based
            word_len.append(len(t))
    n = len(words)
    log("transcript: %d words" % n)

    # --- full-line synthesis, speed chosen for ~TARGET_TOTAL seconds
    full150 = synth(os.path.join(WORK, "full150.wav"), transcript, 150)
    w = wave.open(full150)
    d150 = w.getnframes() / w.getframerate()
    w.close()
    speed = int(round(150 * d150 / TARGET_TOTAL))
    speed = max(120, min(180, speed))
    full_wav = os.path.join(WORK, "full.wav")
    synth(full_wav, transcript, speed)
    full_a, full_rate = load_wav(full_wav)
    total = len(full_a) / full_rate
    onset_t, offset_t = speech_region(full_a, full_rate)
    log("full line @%d wpm = %.3f s, energy speech region [%.3f, %.3f]"
        % (speed, total, onset_t, offset_t))
    if not (12.0 <= total <= 18.0):
        log("ERROR: total duration %.3f outside 12-18 s window!" % total)
        return 1

    # --- exact timing from the synthesizer's own event stream
    binp = build_timing_helper()
    if binp is None:
        return 1
    events, audio = run_timing_helper(binp, txt_path, speed)
    if events is None:
        return 1
    a_rate, a_samples, a_dur = audio
    # the helper's audio must be identical to the CLI WAV so that event
    # positions map 1:1 onto the delivered file's timeline
    raw_path = os.path.join(WORK, "api_audio.raw")
    api_a = array.array("h")
    with open(raw_path, "rb") as f:
        api_a.frombytes(f.read())
    if len(api_a) != len(full_a) or api_a.tobytes() != full_a.tobytes():
        log("ERROR: libespeak-ng audio differs from the CLI WAV "
            "(%d vs %d samples) — event positions would not map onto the "
            "delivered dialogue.wav" % (len(api_a), len(full_a)))
        return 1
    log("timing helper audio is byte-identical to the CLI WAV "
        "(%d samples @ %d Hz)" % (a_samples, a_rate))

    ph_ev = [e for e in events if e["type"] == 7]     # PHONEME events
    word_ev = [e for e in events if e["type"] == 1]   # WORD events
    sent_ev = [e for e in events if e["type"] == 2]   # SENTENCE events
    end_ev = [e for e in events if e["type"] == 5]    # END events
    log("events: %d phoneme, %d word, %d sentence, %d end"
        % (len(ph_ev), len(word_ev), len(sent_ev), len(end_ev)))

    # Event spans (canonical timing model): the event stream is in audio
    # order; every event's span runs to the NEXT event's position (any
    # type: phoneme, WORD, SENTENCE, END), and the final event runs to the
    # end of the audio. This tiles [0, total] exactly. A word's slot starts
    # at its WORD event; its final phoneme ends at the next event's
    # position; inter-word / inter-clause silence shows up as pause
    # phoneme spans. (Verified against the audio: those gaps are silent.)
    total_ms = total * 1000.0
    for i, e in enumerate(events):
        e["start"] = e["ms"] / 1000.0
        e["end"] = (events[i + 1]["ms"] / 1000.0 if i + 1 < len(events)
                    else total)
    if any(events[i + 1]["ms"] < events[i]["ms"]
           for i in range(len(events) - 1)):
        log("ERROR: event stream is not in audio order")
        return 1
    speech_ph = [e for e in ph_ev if not e["id"].startswith("_")]
    log("speech phonemes: %d (pause phonemes: %d), speech region "
        "[%.3f, %.3f] s (event-based)"
        % (len(speech_ph), len(ph_ev) - len(speech_ph),
           speech_ph[0]["start"], speech_ph[-1]["end"]))

    # --- word identity from WORD events (1-based char pos + length)
    pos_to_word = {word_pos[k]: k for k in range(n)}
    word_of_event = {}
    word_event_of = {}
    used = set()
    for e in word_ev:
        k = pos_to_word.get(e["text_pos"])
        if k is None or word_len[k] != e["length"] or k in used:
            log("ERROR: WORD event (%d, len %d) does not match any "
                "transcript word" % (e["text_pos"], e["length"]))
            return 1
        used.add(k)
        word_of_event[e["text_pos"]] = k
        word_event_of[k] = e
    if len(used) != n:
        log("ERROR: %d/%d words matched by WORD events" % (len(used), n))
        return 1

    # --- group phonemes into words (phoneme events carry the word's
    # 1-based char position)
    word_phon_idx = [[] for _ in range(n)]
    for e in speech_ph:
        k = word_of_event.get(e["text_pos"])
        if k is None:
            log("ERROR: phoneme %r at text pos %d matches no word"
                % (e["id"], e["text_pos"]))
            return 1
        word_phon_idx[k].append(e)
    if any(not w for w in word_phon_idx):
        log("ERROR: some word has no phonemes")
        return 1

    # --- word boundaries: the word's slot starts at its WORD event (the
    # synthesizer's own word-start marker); the word's speech ends where
    # its last phoneme ends (the next event's position — a pause phoneme
    # or the next word's WORD event). Word slots therefore tile the whole
    # utterance: [WORD_k, WORD_{k+1}) with the last word ending at the
    # final END event.
    word_bounds = []
    for k in range(n):
        a = word_event_of[k]["ms"] / 1000.0
        b = word_phon_idx[k][-1]["end"]
        if b <= a:
            b = a + 0.001
        word_bounds.append((a, b))
    word_slot_end = []
    for k in range(n):
        if k + 1 < n:
            word_slot_end.append(word_event_of[k + 1]["ms"] / 1000.0)
        else:
            word_slot_end.append(end_ev[-1]["ms"] / 1000.0)

    # --- clause boundaries from END events; clause 1 starts at the first
    # speech phoneme
    if len(end_ev) < 2:
        log("ERROR: expected >= 2 END events, got %d" % len(end_ev))
        return 1
    clause_ends = [e["ms"] / 1000.0 for e in end_ev]
    # clause slots: [WORD event of the clause's first word .. END event];
    # the first clause starts at the first WORD event (audio position 0)
    clause_starts = [word_ev[0]["ms"] / 1000.0] + clause_ends[:-1]
    nclauses = len(end_ev)
    word_clause = []
    for k in range(n):
        a = word_bounds[k][0]
        ci = None
        for c in range(nclauses):
            if clause_starts[c] - 1e-6 <= a < clause_ends[c] - 1e-6 \
                    or (c == nclauses - 1 and a >= clause_starts[c] - 1e-6):
                ci = c
                break
        if ci is None:
            log("ERROR: word %d (%s) at %.3f outside all clause slots"
                % (k, words[k][0], a))
            return 1
        word_clause.append(ci)
    # sentence index per clause (SENTENCE events mark sentence starts)
    sent_starts = [e["ms"] / 1000.0 for e in sent_ev]
    clause_sent = []
    for c in range(nclauses):
        s = 0
        for si, ss in enumerate(sent_starts):
            if ss <= clause_starts[c] + 1e-6:
                s = si
        clause_sent.append(s)
    log("clauses: %d, sentences: %d" % (nclauses, len(sent_starts)))
    for c in range(nclauses):
        cw = [k for k in range(n) if word_clause[k] == c]
        log("  clause %d [%.3f, %.3f] sentence %d: %s"
            % (c, clause_starts[c], clause_ends[c], clause_sent[c],
               " ".join(words[k][0] for k in cw)))

    # --- cross-check the phoneme name sequence against espeak-ng -x
    clauses_x = full_line_mnemonics(transcript)
    if len(clauses_x) != nclauses:
        log("ERROR: -x gave %d clauses, events give %d"
            % (len(clauses_x), nclauses))
        return 1
    for c in range(nclauses):
        mnem = " ".join(clauses_x[c])
        units = tokenize(mnem)
        x_str = "".join(u[2] for u in units)
        cw = [k for k in range(n) if word_clause[k] == c]
        ev_str = "".join(base_phoneme(e["id"])
                         for k in cw for e in word_phon_idx[k])
        if x_str != ev_str:
            log("ERROR: clause %d phoneme sequence mismatch:\n  -x:     %r\n"
                "  events: %r" % (c, x_str, ev_str))
            return 1
    log("phoneme sequence cross-check vs espeak-ng -x: OK "
        "(%d speech phonemes)" % len(speech_ph))

    # --- resample full-line audio to 44100 Hz
    out_wav = os.path.join(AUDIO, "dialogue.wav")
    mono22 = os.path.join(WORK, "dialogue_22k.wav")
    w = wave.open(mono22, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    w.writeframes(full_a.tobytes())
    w.close()
    ffmpeg = shutil.which("ffmpeg") or "/home/morpheus/.nix-profile/bin/ffmpeg"
    if ffmpeg and os.path.exists(ffmpeg):
        r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", mono22,
                            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
                            out_wav], capture_output=True, text=True)
        if r.returncode != 0:
            log("ffmpeg failed: %s" % r.stderr)
            return 1
        log("resampled with ffmpeg -> 44100 Hz mono s16")
    else:
        up = array.array("h", bytes(4 * (2 * len(full_a))))
        for i in range(len(full_a)):
            v0 = full_a[i]
            v1 = full_a[i + 1] if i + 1 < len(full_a) else full_a[i]
            up[2 * i] = v0
            up[2 * i + 1] = (v0 + v1) // 2
        w = wave.open(out_wav, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(up.tobytes())
        w.close()
        log("resampled with linear-interp fallback -> 44100 Hz")

    # --- alignment JSON
    def fstart(x):
        return int(x * FPS) + 1

    def fend(x):
        return max(int(x * FPS) + 1, 1)

    words_json = []
    for k in range(n):
        a, b = word_bounds[k]
        words_json.append({
            "index": k, "word": words[k][0], "punct": words[k][1],
            "clause": word_clause[k],
            "start": round(a, 4), "end": round(b, 4),
            "slot_end": round(word_slot_end[k], 4),
            "start_frame": fstart(a), "end_frame": fend(b - 1e-4),
            "phonemes": [base_phoneme(e["id"]) for e in word_phon_idx[k]],
        })

    phonemes_json = []
    for k in range(n):
        for e in word_phon_idx[k]:
            base = base_phoneme(e["id"])
            vis = VISEME.get(base)
            if vis is None:
                log("  WARN: phoneme %r not in viseme map -> REST" % base)
                vis = "REST"
            phonemes_json.append({
                "word_index": k, "phoneme": base, "viseme": vis,
                "jaw": JAW[vis],
                "start": round(e["start"], 4), "end": round(e["end"], 4),
                "start_frame": fstart(e["start"]),
                "end_frame": fend(e["end"] - 1e-4),
            })

    visemes_json = []
    for ph in phonemes_json:
        if visemes_json and visemes_json[-1]["viseme"] == ph["viseme"] \
                and abs(visemes_json[-1]["end"] - ph["start"]) < 1e-4:
            visemes_json[-1]["end"] = ph["end"]
            visemes_json[-1]["end_frame"] = fend(ph["end"] - 1e-4)
            visemes_json[-1]["jaw"] = max(visemes_json[-1]["jaw"], ph["jaw"])
        else:
            visemes_json.append({
                "viseme": ph["viseme"], "jaw": ph["jaw"],
                "start": ph["start"], "end": ph["end"],
                "start_frame": fstart(ph["start"]),
                "end_frame": fend(ph["end"] - 1e-4),
            })

    pauses_json = []
    for e in ph_ev:
        if not e["id"].startswith("_"):
            continue
        kind = {"_:": "clause", "_!": "word", "_": "lead"}.get(e["id"], "other")
        pauses_json.append({
            "name": e["id"], "kind": kind,
            "start": round(e["start"], 4), "end": round(e["end"], 4),
            "start_frame": fstart(e["start"]),
            "end_frame": fend(e["end"] - 1e-4),
        })

    clauses_json = []
    for c in range(nclauses):
        cw = [k for k in range(n) if word_clause[k] == c]
        speech_c = [e for k in cw for e in word_phon_idx[k]]
        pause_start = speech_c[-1]["end"] if speech_c else clause_starts[c]
        clauses_json.append({
            "index": c, "sentence": clause_sent[c],
            "start": round(clause_starts[c], 4),
            "end": round(clause_ends[c], 4),
            "speech_start": round(speech_c[0]["start"], 4) if speech_c
                            else round(clause_starts[c], 4),
            "speech_end": round(pause_start, 4),
            "pause_start": round(pause_start, 4),
            "pause_end": round(clause_ends[c], 4),
            "words": [words[k][0] for k in cw],
        })

    align = {
        "asset": "dialogue",
        "fps": FPS,
        "sample_rate_hz": 44100,
        "channels": 1,
        "bits_per_sample": 16,
        "duration_seconds": round(total, 4),
        "duration_frames": int(round(total * FPS)),
        "speech_region": [round(speech_ph[0]["start"], 4),
                          round(speech_ph[-1]["end"], 4)],
        "transcript": transcript,
        "tts": {"engine": "espeak-ng", "version": ESPEAK_VERSION,
                "voice": VOICE, "speed_wpm": speed, "pitch": PITCH,
                "license": "GPL-3.0-or-later",
                "note": "synthetic voice, no voice cloning"},
        "timing": {
            "source": "espeak-ng libespeak-ng synthesis events "
                      "(espeakINITIALIZE_PHONEME_EVENTS) via work/espeak_timing.c",
            "internal_sample_rate_hz": a_rate,
            "positions": "milliseconds in the generated audio; 1 ms exact",
            "audio_verified_identical_to_cli": True,
        },
        "method": (
            "Audio is one continuous espeak-ng synthesis of the full "
            "transcript (natural prosody, punctuation pauses included; "
            "energy-measured speech region [%.3f, %.3f] s). Word, phoneme "
            "and clause timings are taken directly from the synthesizer's "
            "own event stream: work/espeak_timing.c links libespeak-ng, "
            "re-synthesizes the identical text/voice/speed/pitch with "
            "phoneme events enabled and dumps WORD/SENTENCE/END/PHONEME "
            "events with millisecond audio positions; the helper's "
            "generated audio is verified byte-identical to the CLI WAV, so "
            "event positions map 1:1 onto this file's timeline (the "
            "delivered WAV is the CLI output resampled 22050->44100 Hz; "
            "resampling preserves time). The event stream arrives in audio "
            "order and every event's span runs to the next event's "
            "position (any type), so it tiles the whole utterance: word "
            "slots are [WORD event, next WORD event), a word's speech ends "
            "where its last phoneme ends, and all inter-word / inter-clause "
            "silence is carried by pause phonemes ('_:' clause pause, "
            "'_!' word gap, '_' lead-in); this slot model was verified "
            "against the audio (the gaps measure ~0 RMS). Word identity "
            "comes from WORD events (1-based character position + length); "
            "clause slots run from the clause's first WORD event to its END "
            "event. The phoneme name sequence is cross-checked against "
            "espeak-ng -x. Phonemes map to visemes via phoneme_to_viseme; "
            "viseme_to_jaw_open matches tools/rig_ops.py VISEMES. Frame "
            "numbers are 1-based at 30 fps; frame f covers "
            "[(f-1)/30, f/30) seconds. Event positions are exact (1 ms); "
            "no envelope estimation is used."
            % (onset_t, offset_t)),
        "phoneme_to_viseme": VISEME,
        "viseme_to_jaw_open": JAW,
        "clauses": clauses_json,
        "words": words_json,
        "phonemes": phonemes_json,
        "pauses": pauses_json,
        "visemes": visemes_json,
    }
    with open(os.path.join(AUDIO, "dialogue_alignment.json"), "w") as f:
        json.dump(align, f, indent=2)
    log("wrote dialogue_alignment.json (%d words, %d phonemes, %d visemes, "
        "%d clauses)" % (len(words_json), len(phonemes_json),
                         len(visemes_json), nclauses))
    log("DIALOGUE_DONE total=%.3fs speed=%d" % (total, speed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
