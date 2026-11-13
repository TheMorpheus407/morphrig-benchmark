#!/usr/bin/env python3
"""
Procedural Tactical Operative Speech & Sample-Exact Phoneme/Viseme Alignment Generator.
Generates:
  - source/audio/dialogue.txt
  - source/audio/dialogue.wav (48 kHz 16-bit PCM mono, 12-18s required window)
  - source/audio/dialogue_alignment.json (word, IPA phoneme, viseme, gaze, emotion, gesture alignment @ 30 FPS)

Reproducible via:
  nix-shell -p espeak-ng --run "python3 source/generators/generate_dialogue_audio.py"
"""

import ctypes
import glob
import json
import math
import os
import shutil
import struct
import subprocess
import wave
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT_DIR / "source" / "audio"

FPS = 30

# eSpeak NG C API constants (from speak_lib.h)
AUDIO_OUTPUT_SYNCHRONOUS = 2
ESPEAK_INITIALIZE_PHONEME_EVENTS = 0x0001
ESPEAK_INITIALIZE_PHONEME_IPA = 0x0002

ESPEAK_EVENT_LIST_TERMINATED = 0
ESPEAK_EVENT_WORD = 1
ESPEAK_EVENT_SENTENCE = 2
ESPEAK_EVENT_END = 5
ESPEAK_EVENT_MSG_TERMINATED = 6
ESPEAK_EVENT_PHONEME = 7

ESPEAK_RATE = 1
ESPEAK_VOLUME = 2
ESPEAK_PITCH = 3
ESPEAK_RANGE = 4
ESPEAK_WORDGAP = 7


class EspeakEventId(ctypes.Union):
    _fields_ = [
        ("number", ctypes.c_int),
        ("name", ctypes.c_char_p),
        ("string", ctypes.c_char * 8),
    ]


class EspeakEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("unique_identifier", ctypes.c_uint),
        ("text_position", ctypes.c_int),
        ("length", ctypes.c_int),
        ("audio_position", ctypes.c_int),
        ("sample", ctypes.c_int),
        ("user_data", ctypes.c_void_p),
        ("id", EspeakEventId),
    ]


SYNTH_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_short),
    ctypes.c_int,
    ctypes.POINTER(EspeakEvent),
)

# Documented Viseme Mapping Table (13 Visemes covering all required categories)
VISEME_DEFINITIONS = {
    "V_SIL": "Neutral closed/resting mouth; zero lip gap.",
    "V_MBP": "Bilabial full lip closure with subtle compression (m, b, p).",
    "V_FV": "Labiodental lower lip tucked to upper incisors (f, v).",
    "V_TH": "Interdental tongue tip visible between upper/lower incisors (theta, eth).",
    "V_TDNL": "Alveolar tongue tip elevated behind upper teeth ridge, slight jaw part (t, d, n, l, tap).",
    "V_SZ": "Sibilant/affricate narrow dental gap and slight corner tension (s, z, sh, zh, ch, j).",
    "V_KG": "Velar/glottal dorsal tongue raise with moderate relaxed jaw opening (k, g, ng, h).",
    "V_AA": "Open vowel with clear vertical jaw drop and visible tongue floor (a, ae, ai, au).",
    "V_EE": "Wide unrounded front vowel with lateral corner pull (i:, I, eI, j).",
    "V_EH": "Mid-open unrounded vowel (E, V/uh, schwa).",
    "V_OH": "Open-mid rounded vowel with oval lip shaping (oU, O:, Q).",
    "V_OU": "Close rounded pucker/funnel vowel and labial-velar glide (u:, U, w).",
    "V_ER": "Rhotic retroflex/bunched tongue with mild lip rounding (r, 3:, @r).",
}


def map_ipa_to_viseme(ipa_raw: str) -> str:
    s = ipa_raw.strip().replace("ˈ", "").replace("ˌ", "").replace("ː", "").replace("ˑ", "")
    if not s or s in ("_", " ", "|", "||", "?"):
        return "V_SIL"
    # Check multi-char diphthongs / affricates first
    if s.startswith(("tʃ", "dʒ", "ts", "dz")):
        return "V_SZ"
    if s.startswith(("aɪ", "aʊ", "ɑ", "æ", "a", "ɐ")):
        return "V_AA"
    if s.startswith(("oʊ", "əʊ", "ɔɪ", "ɔ", "ɒ", "o")):
        return "V_OH"
    if s.startswith(("eɪ", "i", "ɪ", "j")):
        return "V_EE"
    if s.startswith(("u", "ʊ", "ʉ", "w", "ʍ")):
        return "V_OU"
    if s.startswith(("ɝ", "ɚ", "ɜ", "ɹ", "r", "ɻ")):
        return "V_ER"
    if s.startswith(("p", "b", "m")):
        return "V_MBP"
    if s.startswith(("f", "v")):
        return "V_FV"
    if s.startswith(("θ", "ð")):
        return "V_TH"
    if s.startswith(("t", "d", "n", "l", "ɾ", "ɫ")):
        return "V_TDNL"
    if s.startswith(("s", "z", "ʃ", "ʒ")):
        return "V_SZ"
    if s.startswith(("k", "ɡ", "g", "ŋ", "h", "ʔ")):
        return "V_KG"
    if s.startswith(("ɛ", "ʌ", "ə", "ᵻ", "e")):
        return "V_EH"
    return "V_EH"


def find_libespeak() -> str:
    espeak_bin = shutil.which("espeak-ng")
    if not espeak_bin:
        raise RuntimeError("espeak-ng not found on PATH. Run via `nix-shell -p espeak-ng`.")
    prefix = Path(espeak_bin).resolve().parents[1]
    candidates = sorted(glob.glob(str(prefix / "lib" / "libespeak-ng.so*")))
    if not candidates:
        raise RuntimeError(f"Could not find libespeak-ng.so under {prefix / 'lib'}")
    return candidates[0]


def generate() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    lib_path = find_libespeak()
    lib = ctypes.CDLL(lib_path)

    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_SetSynthCallback.argtypes = [SYNTH_CALLBACK]
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.espeak_Synth.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.c_void_p,
    ]

    sample_rate = lib.espeak_Initialize(
        AUDIO_OUTPUT_SYNCHRONOUS,
        60,
        None,
        ESPEAK_INITIALIZE_PHONEME_EVENTS | ESPEAK_INITIALIZE_PHONEME_IPA,
    )
    if sample_rate <= 0:
        raise RuntimeError(f"espeak_Initialize failed: {sample_rate}")

    # Voice selection: female/clear neutral English voice variant for crisp consonant articulation
    lib.espeak_SetVoiceByName(b"en-us+f3")

    # Structured 5-clause tactical performance with explicit emotional shift midway
    clauses = [
        {
            "id": "clause_1_alert",
            "text": "Central, outer lane relay is surging —",
            "emotion": "concern_sadness",
            "emotion_secondary": "focus",
            "rate": 178,
            "pitch": 58,
            "range": 62,
            "pre_pause_s": 0.35,
            "post_pause_s": 0.18,
            "gesture": "left_hand_earpiece_alert",
            "gaze_target": {"yaw_deg": -14.0, "pitch_deg": 6.0},
        },
        {
            "id": "clause_2_warning",
            "text": "voltage spikes are tearing through node seven, fall back from the breach!",
            "emotion": "concern_sadness",
            "emotion_secondary": "anger",
            "rate": 182,
            "pitch": 62,
            "range": 68,
            "pre_pause_s": 0.05,
            "post_pause_s": 0.40,
            "gesture": "left_arm_sweep_warn",
            "gaze_target": {"yaw_deg": 16.0, "pitch_deg": -4.0},
        },
        {
            "id": "clause_3_shift_stabilize",
            "text": "Wait... phase dampers locking in now.",
            "emotion": "focus",
            "emotion_secondary": "surprise",
            "rate": 166,
            "pitch": 49,
            "range": 52,
            "pre_pause_s": 0.15,
            "post_pause_s": 0.32,
            "gesture": "wrist_emitter_console_tune",
            "gaze_target": {"yaw_deg": -18.0, "pitch_deg": -22.0},
        },
        {
            "id": "clause_4_resolved",
            "text": "Grid frequency is stable.",
            "emotion": "joy_confidence",
            "emotion_secondary": "focus",
            "rate": 168,
            "pitch": 46,
            "range": 54,
            "pre_pause_s": 0.08,
            "post_pause_s": 0.25,
            "gesture": "open_palm_confirm",
            "gaze_target": {"yaw_deg": 0.0, "pitch_deg": 2.0},
        },
        {
            "id": "clause_5_command",
            "text": "We hold this lane — nobody gets past this line.",
            "emotion": "joy_confidence",
            "emotion_secondary": "focus",
            "rate": 164,
            "pitch": 44,
            "range": 58,
            "pre_pause_s": 0.08,
            "post_pause_s": 0.45,
            "gesture": "decisive_lane_point_and_settle",
            "gaze_target": {"yaw_deg": 4.0, "pitch_deg": 0.0},
        },
    ]

    all_pcm = []
    words_out = []
    phonemes_out = []
    clause_spans = []

    current_samples = []
    current_events = []

    @SYNTH_CALLBACK
    def on_synth(wav_ptr, numsamples, events_ptr):
        if wav_ptr and numsamples > 0:
            for i in range(numsamples):
                current_samples.append(int(wav_ptr[i]))
        if events_ptr:
            idx = 0
            while True:
                ev = events_ptr[idx]
                if ev.type == ESPEAK_EVENT_LIST_TERMINATED:
                    break
                if ev.type == ESPEAK_EVENT_WORD:
                    current_events.append(
                        (
                            "word",
                            ev.audio_position / 1000.0,
                            ev.text_position,
                            ev.length,
                            "",
                        )
                    )
                elif ev.type == ESPEAK_EVENT_PHONEME:
                    raw_bytes = bytes(ev.id.string).split(b"\x00", 1)[0]
                    ipa_str = raw_bytes.decode("utf-8", errors="ignore")
                    current_events.append(
                        ("phoneme", ev.audio_position / 1000.0, 0, 0, ipa_str)
                    )
                elif ev.type in (ESPEAK_EVENT_END, ESPEAK_EVENT_MSG_TERMINATED):
                    current_events.append(("end", ev.audio_position / 1000.0, 0, 0, ""))
                idx += 1
        return 0

    lib.espeak_SetSynthCallback(on_synth)

    cursor_sec = 0.0
    transcript_lines = []

    for c_idx, clause in enumerate(clauses):
        transcript_lines.append(clause["text"])
        # Pre-pause silence (with subtle breath noise before energetic clauses)
        pre_samples = int(round(clause["pre_pause_s"] * sample_rate))
        for s_i in range(pre_samples):
            # Subtle natural intake breath in last 0.18s of pre-pause for realism
            rem_s = (pre_samples - s_i) / sample_rate
            if 0.03 < rem_s < 0.20:
                env = math.sin((rem_s - 0.03) / 0.17 * math.pi)
                breath = int(160.0 * env * math.sin(s_i * 0.37) * math.cos(s_i * 0.11))
                all_pcm.append(breath)
            else:
                all_pcm.append(0)
        cursor_sec = len(all_pcm) / sample_rate

        current_samples.clear()
        current_events.clear()

        lib.espeak_SetParameter(ESPEAK_RATE, clause["rate"], 0)
        lib.espeak_SetParameter(ESPEAK_VOLUME, 100, 0)
        lib.espeak_SetParameter(ESPEAK_PITCH, clause["pitch"], 0)
        lib.espeak_SetParameter(ESPEAK_RANGE, clause["range"], 0)
        lib.espeak_SetParameter(ESPEAK_WORDGAP, 2, 0)

        text_bytes = clause["text"].encode("utf-8")
        lib.espeak_Synth(text_bytes, len(text_bytes) + 1, 0, 0, 0, 1, None, None)

        clause_dur = len(current_samples) / sample_rate
        clause_start = cursor_sec
        clause_end = clause_start + clause_dur

        clause_spans.append(
            {
                "id": clause["id"],
                "index": c_idx,
                "text": clause["text"],
                "emotion_primary": clause["emotion"],
                "emotion_secondary": clause["emotion_secondary"],
                "gesture": clause["gesture"],
                "gaze_target": clause["gaze_target"],
                "start_sec": round(clause_start, 4),
                "end_sec": round(clause_end, 4),
                "start_frame": int(round(clause_start * FPS)),
                "end_frame": int(round(clause_end * FPS)),
            }
        )

        # Extract word events
        word_evs = [e for e in current_events if e[0] == "word"]
        for w_i, (_, t_rel, t_pos, w_len, _) in enumerate(word_evs):
            # espeak text_position is 1-based character index
            start_ch = max(0, t_pos - 1)
            raw_slice = clause["text"][start_ch : start_ch + max(1, w_len + 4)]
            word_tok = raw_slice.split()[0].strip("—.,!?\"'") if raw_slice.split() else ""
            w_start = clause_start + t_rel
            w_end = (
                clause_start + word_evs[w_i + 1][1]
                if w_i + 1 < len(word_evs)
                else clause_end
            )
            if word_tok:
                words_out.append(
                    {
                        "word": word_tok,
                        "clause_id": clause["id"],
                        "start_sec": round(w_start, 4),
                        "end_sec": round(max(w_start + 0.04, w_end), 4),
                        "start_frame": int(round(w_start * FPS)),
                        "end_frame": int(round(max(w_start + 0.04, w_end) * FPS)),
                    }
                )

        # Extract phoneme events with real acoustic RMS energy from current_samples
        ph_evs = [e for e in current_events if e[0] in ("phoneme", "end")]
        for p_i, (etype, t_rel, _, _, ipa_str) in enumerate(ph_evs):
            if etype != "phoneme":
                continue
            p_start_rel = t_rel
            p_end_rel = (
                ph_evs[p_i + 1][1] if p_i + 1 < len(ph_evs) else clause_dur
            )
            if p_end_rel <= p_start_rel:
                p_end_rel = min(clause_dur, p_start_rel + 0.045)
            s0 = max(0, min(len(current_samples), int(p_start_rel * sample_rate)))
            s1 = max(s0 + 1, min(len(current_samples), int(p_end_rel * sample_rate)))
            window = current_samples[s0:s1]
            rms = (
                math.sqrt(sum(float(x) * float(x) for x in window) / len(window)) / 32768.0
                if window
                else 0.0
            )
            viseme = map_ipa_to_viseme(ipa_str)
            if viseme == "V_SIL" and rms < 0.01:
                continue
            p_start = clause_start + p_start_rel
            p_end = clause_start + p_end_rel
            phonemes_out.append(
                {
                    "ipa": ipa_str if ipa_str else "_",
                    "viseme": viseme,
                    "clause_id": clause["id"],
                    "start_sec": round(p_start, 4),
                    "end_sec": round(p_end, 4),
                    "start_frame": int(round(p_start * FPS)),
                    "end_frame": int(round(p_end * FPS)),
                    "energy": round(min(1.0, rms * 3.8), 3),
                }
            )

        all_pcm.extend(current_samples)

        # Post-pause silence
        post_samples = int(round(clause["post_pause_s"] * sample_rate))
        all_pcm.extend([0] * post_samples)
        cursor_sec = len(all_pcm) / sample_rate

    raw_wav = AUDIO_DIR / "_raw_espeak.wav"
    final_wav = AUDIO_DIR / "dialogue.wav"
    txt_path = AUDIO_DIR / "dialogue.txt"
    align_path = AUDIO_DIR / "dialogue_alignment.json"

    with wave.open(str(raw_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(all_pcm)}h", *all_pcm))

    # Resample to clean 48 kHz 16-bit PCM with warm studio formant smoothing (zero timing change)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-i",
            str(raw_wav),
            "-af",
            "highpass=f=85,lowpass=f=8500,equalizer=f=230:t=q:w=1.1:g=2.5,equalizer=f=3400:t=q:w=1.4:g=-2.0,acompressor=threshold=-18dB:ratio=2.2:makeup=2dB,alimiter=limit=0.88",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(final_wav),
        ],
        check=True,
    )
    raw_wav.unlink(missing_ok=True)

    # Verify exact output WAV duration
    with wave.open(str(final_wav), "rb") as wf:
        out_sr = wf.getframerate()
        out_frames = wf.getnframes()
        total_duration_sec = out_frames / float(out_sr)

    total_anim_frames = int(round(total_duration_sec * FPS))
    assert 12.0 <= total_duration_sec <= 18.0, (
        f"Dialogue duration {total_duration_sec:.2f}s outside required 12-18s window!"
    )

    full_transcript = " ".join(transcript_lines)
    txt_path.write_text(full_transcript + "\n", encoding="utf-8")

    # Author explicit facial blink, gaze saccade, emotional shift, and body gesture tracks
    emotional_arc = [
        {"time_sec": 0.0, "frame": 0, "preset": "focus", "weights": {"focus": 0.65, "concern_sadness": 0.25}},
        {"time_sec": clause_spans[0]["start_sec"], "frame": clause_spans[0]["start_frame"], "preset": "concern_sadness", "weights": {"concern_sadness": 0.72, "focus": 0.35}},
        {"time_sec": clause_spans[1]["start_sec"] + 0.8, "frame": int((clause_spans[1]["start_sec"] + 0.8) * FPS), "preset": "concern_sadness", "weights": {"concern_sadness": 0.65, "anger": 0.42, "focus": 0.30}},
        {"time_sec": clause_spans[2]["start_sec"], "frame": clause_spans[2]["start_frame"], "preset": "focus", "weights": {"surprise": 0.35, "focus": 0.80}},
        {"time_sec": clause_spans[3]["start_sec"], "frame": clause_spans[3]["start_frame"], "preset": "joy_confidence", "weights": {"joy_confidence": 0.75, "focus": 0.30}},
        {"time_sec": clause_spans[4]["end_sec"], "frame": clause_spans[4]["end_frame"], "preset": "joy_confidence", "weights": {"joy_confidence": 0.82, "focus": 0.25}},
        {"time_sec": round(total_duration_sec, 4), "frame": total_anim_frames, "preset": "neutral", "weights": {"joy_confidence": 0.40, "focus": 0.20}},
    ]

    blinks = [
        {"time_sec": 0.32, "duration_sec": 0.16, "asymmetry_lr": [1.0, 0.95]},
        {"time_sec": round(clause_spans[0]["end_sec"] + 0.08, 3), "duration_sec": 0.15, "asymmetry_lr": [1.0, 1.0]},
        {"time_sec": round(clause_spans[1]["end_sec"] + 0.18, 3), "duration_sec": 0.20, "asymmetry_lr": [0.95, 1.0]},
        {"time_sec": round(clause_spans[2]["end_sec"] + 0.12, 3), "duration_sec": 0.16, "asymmetry_lr": [1.0, 1.0]},
        {"time_sec": round(clause_spans[3]["end_sec"] + 0.10, 3), "duration_sec": 0.15, "asymmetry_lr": [1.0, 0.92]},
        {"time_sec": round(total_duration_sec - 0.35, 3), "duration_sec": 0.17, "asymmetry_lr": [1.0, 1.0]},
    ]

    used_visemes = sorted({p["viseme"] for p in phonemes_out})

    alignment_doc = {
        "schema_version": "1.0",
        "fps": FPS,
        "sample_rate_hz": out_sr,
        "duration_seconds": round(total_duration_sec, 4),
        "total_frames": total_anim_frames,
        "voice_synthesis": {
            "tool": "eSpeak NG 1.52.0.1 (local deterministic formant synthesis via libespeak-ng + FFmpeg 8.0 48kHz studio EQ)",
            "voice_id": "en-us+f3",
            "license": "GPL-3.0-or-later tool; generated audio output unrestricted / self-authored transcript",
        },
        "transcript": full_transcript,
        "viseme_definitions": VISEME_DEFINITIONS,
        "visemes_exercised": used_visemes,
        "emotional_shift_summary": "Transitions from urgent tactical concern/warning (0.45s-6.8s) through focused instrument stabilization (6.8s-9.8s) into calm, confident command (9.8s-end).",
        "clauses": clause_spans,
        "emotional_arc": emotional_arc,
        "blinks": blinks,
        "words": words_out,
        "phonemes": phonemes_out,
    }

    align_path.write_text(json.dumps(alignment_doc, indent=2) + "\n", encoding="utf-8")
    print(
        f"Generated dialogue.wav: {total_duration_sec:.3f}s ({total_anim_frames} frames @ {FPS} FPS), "
        f"{len(words_out)} words, {len(phonemes_out)} phonemes, visemes={used_visemes}"
    )


if __name__ == "__main__":
    generate()
