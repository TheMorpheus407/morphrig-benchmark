#!/usr/bin/env python3
"""
Procedural generator for the Operative's spoken performance audio (dialogue.wav),
transcript (dialogue.txt), and phoneme/viseme/emotion/gaze/gesture alignment
(dialogue_alignment.json).

Uses espeak-ng for deterministic local speech synthesis and phoneme extraction,
followed by slight acoustic warmth/formant shaping and exact 30 FPS curve alignment.
"""

import json
import math
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path


SEGMENTS = [
    {
        "id": "seg_01",
        "start_sec": 0.35,
        "target_end_sec": 2.55,
        "text": "Command, Operative Vex on the northern lane.",
        "emotion": "focus",
        "pitch": 46,
        "speed": 148,
        "gaze": {"yaw_deg": 0.0, "pitch_deg": 0.0, "target": "camera_center"},
        "gesture": "comms_ear_tap_and_scan",
    },
    {
        "id": "seg_02",
        "start_sec": 2.75,
        "target_end_sec": 5.10,
        "text": "Relay nodes one through four are holding steady.",
        "emotion": "focus",
        "pitch": 44,
        "speed": 145,
        "gaze": {"yaw_deg": -18.0, "pitch_deg": -8.0, "target": "wrist_console"},
        "gesture": "inspect_wrist_emitter_holo",
    },
    {
        "id": "seg_03",
        "start_sec": 5.35,
        "target_end_sec": 7.65,
        "text": "Wait, voltage spike on the primary conduit!",
        "emotion": "surprise",
        "pitch": 58,
        "speed": 160,
        "gaze": {"yaw_deg": 28.0, "pitch_deg": 6.0, "target": "lane_horizon_right"},
        "gesture": "alert_recoil_and_point_conduit",
    },
    {
        "id": "seg_04",
        "start_sec": 7.80,
        "target_end_sec": 10.20,
        "text": "If that barrier drops, the whole sector goes dark.",
        "emotion": "concern_sadness",
        "pitch": 50,
        "speed": 152,
        "gaze": {"yaw_deg": -12.0, "pitch_deg": 4.0, "target": "command_uplink"},
        "gesture": "urgent_two_hand_stabilize",
    },
    {
        "id": "seg_05",
        "start_sec": 10.45,
        "target_end_sec": 12.60,
        "text": "Rerouting auxiliary power through my wrist emitter now.",
        "emotion": "focus",
        "pitch": 48,
        "speed": 155,
        "gaze": {"yaw_deg": -15.0, "pitch_deg": -12.0, "target": "wrist_emitter_cell"},
        "gesture": "lock_power_cell_and_channel",
    },
    {
        "id": "seg_06",
        "start_sec": 12.80,
        "target_end_sec": 14.35,
        "text": "Network stabilized. This lane stays ours.",
        "emotion": "joy_confidence",
        "pitch": 42,
        "speed": 140,
        "gaze": {"yaw_deg": 0.0, "pitch_deg": 2.0, "target": "camera_center"},
        "gesture": "confident_fist_clench_and_nod",
    },
]

TOTAL_DURATION_SEC = 14.50
FPS = 30
TOTAL_FRAMES = int(round(TOTAL_DURATION_SEC * FPS))  # 435 frames
SAMPLE_RATE = 44100


VISEME_DOC = {
    "viseme_SIL": "Neutral closed/rest lips (silence/pause)",
    "viseme_MBP": "Bilabial full lip closure with slight compression (M, B, P)",
    "viseme_FV": "Labiodental lower lip tucked against upper teeth (F, V)",
    "viseme_TH": "Dental tongue tip visible between slightly parted teeth (TH)",
    "viseme_TDNL": "Alveolar tongue elevated to upper tooth ridge, moderate jaw (T, D, N, L)",
    "viseme_SZ": "Sibilant/affricate narrow tooth gap with slightly spread corners (S, Z, SH, ZH, CH, JH)",
    "viseme_KG": "Velar dorsal tongue lift with relaxed lips and slight jaw drop (K, G, NG, R, Y, H)",
    "viseme_AA": "Open vowel with clear vertical jaw drop and relaxed corners (AA, AE, AH, AY, AW)",
    "viseme_EE": "Wide unrounded vowel with horizontal corner pull and moderate jaw (EE, IH, EY, EH)",
    "viseme_OH": "Rounded mid-open vowel with oval lip shaping and jaw drop (OH, AO, OW, OY)",
    "viseme_OO": "Tight rounded vowel with forward lip pucker and small aperture (OO, UW, UH, W)",
}


WORD_PHONEME_VISEMES = {
    "command": [("k", "viseme_KG"), ("ə", "viseme_AA"), ("m", "viseme_MBP"), ("æ", "viseme_AA"), ("n", "viseme_TDNL"), ("d", "viseme_TDNL")],
    "operative": [("ɑ", "viseme_OH"), ("p", "viseme_MBP"), ("ɚ", "viseme_KG"), ("ə", "viseme_AA"), ("t", "viseme_TDNL"), ("ɪ", "viseme_EE"), ("v", "viseme_FV")],
    "vex": [("v", "viseme_FV"), ("ɛ", "viseme_EE"), ("k", "viseme_KG"), ("s", "viseme_SZ")],
    "on": [("ɑ", "viseme_OH"), ("n", "viseme_TDNL")],
    "the": [("ð", "viseme_TH"), ("ə", "viseme_EE")],
    "northern": [("n", "viseme_TDNL"), ("ɔ", "viseme_OH"), ("ɹ", "viseme_KG"), ("ð", "viseme_TH"), ("ɚ", "viseme_KG"), ("n", "viseme_TDNL")],
    "lane": [("l", "viseme_TDNL"), ("eɪ", "viseme_EE"), ("n", "viseme_TDNL")],
    "relay": [("ɹ", "viseme_OO"), ("i", "viseme_EE"), ("l", "viseme_TDNL"), ("eɪ", "viseme_EE")],
    "nodes": [("n", "viseme_TDNL"), ("oʊ", "viseme_OH"), ("d", "viseme_TDNL"), ("z", "viseme_SZ")],
    "one": [("w", "viseme_OO"), ("ʌ", "viseme_AA"), ("n", "viseme_TDNL")],
    "through": [("θ", "viseme_TH"), ("ɹ", "viseme_OO"), ("u", "viseme_OO")],
    "four": [("f", "viseme_FV"), ("ɔ", "viseme_OH"), ("ɹ", "viseme_KG")],
    "are": [("ɑ", "viseme_AA"), ("ɹ", "viseme_KG")],
    "holding": [("h", "viseme_KG"), ("oʊ", "viseme_OH"), ("l", "viseme_TDNL"), ("d", "viseme_TDNL"), ("ɪ", "viseme_EE"), ("ŋ", "viseme_KG")],
    "steady": [("s", "viseme_SZ"), ("t", "viseme_TDNL"), ("ɛ", "viseme_EE"), ("d", "viseme_TDNL"), ("i", "viseme_EE")],
    "wait": [("w", "viseme_OO"), ("eɪ", "viseme_EE"), ("t", "viseme_TDNL")],
    "voltage": [("v", "viseme_FV"), ("oʊ", "viseme_OH"), ("l", "viseme_TDNL"), ("t", "viseme_TDNL"), ("ɪ", "viseme_EE"), ("dʒ", "viseme_SZ")],
    "spike": [("s", "viseme_SZ"), ("p", "viseme_MBP"), ("aɪ", "viseme_AA"), ("k", "viseme_KG")],
    "primary": [("p", "viseme_MBP"), ("ɹ", "viseme_OO"), ("aɪ", "viseme_AA"), ("m", "viseme_MBP"), ("ɛ", "viseme_EE"), ("ɹ", "viseme_KG"), ("i", "viseme_EE")],
    "conduit": [("k", "viseme_KG"), ("ɑ", "viseme_OH"), ("n", "viseme_TDNL"), ("d", "viseme_TDNL"), ("u", "viseme_OO"), ("ɪ", "viseme_EE"), ("t", "viseme_TDNL")],
    "if": [("ɪ", "viseme_EE"), ("f", "viseme_FV")],
    "that": [("ð", "viseme_TH"), ("æ", "viseme_AA"), ("t", "viseme_TDNL")],
    "barrier": [("b", "viseme_MBP"), ("æ", "viseme_AA"), ("ɹ", "viseme_KG"), ("i", "viseme_EE"), ("ɚ", "viseme_KG")],
    "drops": [("d", "viseme_TDNL"), ("ɹ", "viseme_OO"), ("ɑ", "viseme_OH"), ("p", "viseme_MBP"), ("s", "viseme_SZ")],
    "whole": [("h", "viseme_KG"), ("oʊ", "viseme_OH"), ("l", "viseme_TDNL")],
    "sector": [("s", "viseme_SZ"), ("ɛ", "viseme_EE"), ("k", "viseme_KG"), ("t", "viseme_TDNL"), ("ɚ", "viseme_KG")],
    "goes": [("g", "viseme_KG"), ("oʊ", "viseme_OH"), ("z", "viseme_SZ")],
    "dark": [("d", "viseme_TDNL"), ("ɑ", "viseme_AA"), ("ɹ", "viseme_KG"), ("k", "viseme_KG")],
    "rerouting": [("ɹ", "viseme_OO"), ("i", "viseme_EE"), ("ɹ", "viseme_OO"), ("aʊ", "viseme_AA"), ("t", "viseme_TDNL"), ("ɪ", "viseme_EE"), ("ŋ", "viseme_KG")],
    "auxiliary": [("ɔ", "viseme_OH"), ("g", "viseme_KG"), ("z", "viseme_SZ"), ("ɪ", "viseme_EE"), ("l", "viseme_TDNL"), ("j", "viseme_EE"), ("ɚ", "viseme_KG"), ("i", "viseme_EE")],
    "power": [("p", "viseme_MBP"), ("aʊ", "viseme_AA"), ("oʊ", "viseme_OH"), ("ɚ", "viseme_KG")],
    "my": [("m", "viseme_MBP"), ("aɪ", "viseme_AA")],
    "wrist": [("ɹ", "viseme_OO"), ("ɪ", "viseme_EE"), ("s", "viseme_SZ"), ("t", "viseme_TDNL")],
    "emitter": [("ɪ", "viseme_EE"), ("m", "viseme_MBP"), ("ɪ", "viseme_EE"), ("t", "viseme_TDNL"), ("ɚ", "viseme_KG")],
    "now": [("n", "viseme_TDNL"), ("aʊ", "viseme_AA"), ("oʊ", "viseme_OO")],
    "network": [("n", "viseme_TDNL"), ("ɛ", "viseme_EE"), ("t", "viseme_TDNL"), ("w", "viseme_OO"), ("ɚ", "viseme_KG"), ("k", "viseme_KG")],
    "stabilized": [("s", "viseme_SZ"), ("t", "viseme_TDNL"), ("eɪ", "viseme_EE"), ("b", "viseme_MBP"), ("ə", "viseme_AA"), ("l", "viseme_TDNL"), ("aɪ", "viseme_AA"), ("z", "viseme_SZ"), ("d", "viseme_TDNL")],
    "this": [("ð", "viseme_TH"), ("ɪ", "viseme_EE"), ("s", "viseme_SZ")],
    "stays": [("s", "viseme_SZ"), ("t", "viseme_TDNL"), ("eɪ", "viseme_EE"), ("z", "viseme_SZ")],
    "ours": [("aʊ", "viseme_AA"), ("oʊ", "viseme_OH"), ("ɚ", "viseme_KG"), ("z", "viseme_SZ")],
}


def read_wav_samples(path: str):
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if sampwidth == 2:
        fmt = f"<{n_frames * n_channels}h"
        ints = struct.unpack(fmt, raw)
        samples = [s / 32768.0 for s in ints[::n_channels]]
    else:
        raise RuntimeError(f"Unsupported sample width: {sampwidth}")
    return samples, framerate


def resample_linear(samples, src_rate, dst_rate):
    if src_rate == dst_rate:
        return list(samples)
    ratio = src_rate / float(dst_rate)
    out_len = int(len(samples) / ratio)
    out = [0.0] * out_len
    for i in range(out_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(samples):
            out[i] = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        else:
            out[i] = samples[idx]
    return out


def enhance_voice_segment(samples, rate):
    """Apply subtle vocal warmth, de-harshing low-pass + chest resonance so TTS sounds clean."""
    if not samples:
        return samples
    out = [0.0] * len(samples)
    # 1-pole lowpass around 4.8 kHz to smooth harsh buzz + subtle sub-harmonic warmth
    rc = 1.0 / (2.0 * math.pi * 4800.0)
    dt = 1.0 / rate
    alpha = dt / (rc + dt)
    prev = 0.0
    for i, s in enumerate(samples):
        lp = prev + alpha * (s - prev)
        prev = lp
        # Soft saturation for vocal presence
        shaped = math.tanh(lp * 1.35) * 0.78
        out[i] = shaped
    # Fade in/out 15ms to avoid clicks
    fade_n = min(int(0.015 * rate), len(out) // 4)
    for i in range(fade_n):
        w = i / float(max(1, fade_n))
        out[i] *= w
        out[-1 - i] *= w
    return out


def synthesize_segments():
    master_len = int(TOTAL_DURATION_SEC * SAMPLE_RATE)
    master_audio = [0.0] * master_len

    segment_records = []
    word_records = []
    phoneme_records = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for seg in SEGMENTS:
            wav_tmp = os.path.join(tmpdir, f"{seg['id']}.wav")
            cmd = [
                "nix-shell",
                "-p",
                "espeak-ng",
                "--run",
                (
                    f"espeak-ng -v en-us+f3 -p {seg['pitch']} -s {seg['speed']} "
                    f"-w {wav_tmp} {json.dumps(seg['text'])}"
                ),
            ]
            subprocess.run(cmd, check=True)
            ipa_cmd = [
                "nix-shell",
                "-p",
                "espeak-ng",
                "--run",
                f"espeak-ng -v en-us -q --ipa {json.dumps(seg['text'])}",
            ]
            ipa_out = subprocess.check_output(ipa_cmd, text=True).strip()

            raw_samples, src_rate = read_wav_samples(wav_tmp)
            # Trim leading/trailing silence from raw_samples
            thresh = 0.012
            start_idx = 0
            while start_idx < len(raw_samples) and abs(raw_samples[start_idx]) < thresh:
                start_idx += 1
            end_idx = len(raw_samples) - 1
            while end_idx > start_idx and abs(raw_samples[end_idx]) < thresh:
                end_idx -= 1
            trimmed = raw_samples[max(0, start_idx - int(0.02 * src_rate)) : min(len(raw_samples), end_idx + int(0.04 * src_rate))]

            resampled = resample_linear(trimmed, src_rate, SAMPLE_RATE)
            enhanced = enhance_voice_segment(resampled, SAMPLE_RATE)

            seg_start = seg["start_sec"]
            actual_dur = len(enhanced) / float(SAMPLE_RATE)
            max_dur = seg["target_end_sec"] - seg_start
            if actual_dur > max_dur and max_dur > 0.2:
                # Time-fit slightly if needed
                target_samples = int(max_dur * SAMPLE_RATE)
                enhanced = resample_linear(enhanced, len(enhanced), target_samples)
                actual_dur = len(enhanced) / float(SAMPLE_RATE)

            seg_end = round(seg_start + actual_dur, 4)
            write_start = int(seg_start * SAMPLE_RATE)
            for i, s in enumerate(enhanced):
                if write_start + i < master_len:
                    master_audio[write_start + i] += s

            # Split words and distribute word & phoneme timings proportional to phoneme length + energy
            raw_words = [w.strip(".,!?;:—-") for w in seg["text"].split() if w.strip(".,!?;:—-")]
            word_weights = []
            for w in raw_words:
                clean_w = w.lower()
                ph_list = WORD_PHONEME_VISEMES.get(clean_w, [("ə", "viseme_AA")])
                word_weights.append(max(2, len(ph_list)) + (1.2 if w.endswith((",", ".", "!")) else 0.0))

            total_weight = sum(word_weights)
            cursor = seg_start
            for w_idx, w in enumerate(raw_words):
                clean_w = w.lower()
                w_dur = actual_dur * (word_weights[w_idx] / total_weight)
                w_start = cursor
                w_end = cursor + w_dur * 0.92  # small inter-word articulation gap
                cursor += w_dur

                word_records.append(
                    {
                        "word": w,
                        "segment_id": seg["id"],
                        "start_sec": round(w_start, 4),
                        "end_sec": round(w_end, 4),
                        "emotion": seg["emotion"],
                    }
                )

                ph_list = WORD_PHONEME_VISEMES.get(clean_w, [("ə", "viseme_AA")])
                ph_dur = (w_end - w_start) / float(len(ph_list))
                for p_idx, (ipa_sym, viseme_name) in enumerate(ph_list):
                    p_start = w_start + p_idx * ph_dur
                    p_end = p_start + ph_dur
                    phoneme_records.append(
                        {
                            "phoneme": ipa_sym,
                            "viseme": viseme_name,
                            "word": w,
                            "segment_id": seg["id"],
                            "start_sec": round(p_start, 4),
                            "end_sec": round(p_end, 4),
                        }
                    )

            segment_records.append(
                {
                    "id": seg["id"],
                    "text": seg["text"],
                    "ipa": ipa_out,
                    "start_sec": round(seg_start, 4),
                    "end_sec": round(seg_end, 4),
                    "emotion": seg["emotion"],
                    "gaze": seg["gaze"],
                    "gesture": seg["gesture"],
                }
            )

    # Add a very subtle high-tech comms ambient bed (-44 dB) so the WAV feels alive and grounded
    for i in range(master_len):
        t = i / float(SAMPLE_RATE)
        hum = 0.0025 * math.sin(2.0 * math.pi * 110.0 * t) + 0.0012 * math.sin(2.0 * math.pi * 220.0 * t)
        master_audio[i] = max(-0.98, min(0.98, master_audio[i] + hum))

    return master_audio, segment_records, word_records, phoneme_records


def build_frame_curves(segment_records, phoneme_records):
    """Build 30 FPS per-frame curves for visemes, jaw, tongue, emotions, gaze, blinks, and gestures."""
    frames = []
    blink_times = [0.20, 2.58, 5.18, 7.68, 10.28, 12.68, 14.20]

    for f in range(TOTAL_FRAMES + 1):
        t = round(f / float(FPS), 4)
        viseme_weights = {k: 0.0 for k in VISEME_DOC}
        active_viseme = "viseme_SIL"

        for ph in phoneme_records:
            # Smooth triangular/trapezoidal co-articulation kernel around each phoneme window
            mid = 0.5 * (ph["start_sec"] + ph["end_sec"])
            half_w = max(0.045, 0.65 * (ph["end_sec"] - ph["start_sec"]))
            dist = abs(t - mid)
            if dist < half_w:
                val = 0.5 * (1.0 + math.cos(math.pi * dist / half_w))
                vname = ph["viseme"]
                viseme_weights[vname] = max(viseme_weights[vname], round(val, 4))

        total_active = sum(v for k, v in viseme_weights.items() if k != "viseme_SIL")
        if total_active < 0.05:
            viseme_weights["viseme_SIL"] = 1.0
            active_viseme = "viseme_SIL"
        else:
            viseme_weights["viseme_SIL"] = round(max(0.0, 1.0 - total_active), 4)
            active_viseme = max(
                (k for k in viseme_weights if k != "viseme_SIL"),
                key=lambda k: viseme_weights[k],
            )

        # Compute jaw opening & tongue placement from active visemes (not mere jaw flapping!)
        jaw_open = (
            0.75 * viseme_weights["viseme_AA"]
            + 0.55 * viseme_weights["viseme_OH"]
            + 0.35 * viseme_weights["viseme_EE"]
            + 0.28 * viseme_weights["viseme_TDNL"]
            + 0.25 * viseme_weights["viseme_KG"]
            + 0.22 * viseme_weights["viseme_TH"]
            + 0.18 * viseme_weights["viseme_OO"]
            + 0.12 * viseme_weights["viseme_SZ"]
            + 0.08 * viseme_weights["viseme_FV"]
            + 0.00 * viseme_weights["viseme_MBP"]
        )
        jaw_open = round(min(1.0, max(0.0, jaw_open)), 4)

        tongue_up = round(
            min(1.0, 0.85 * viseme_weights["viseme_TDNL"] + 0.5 * viseme_weights["viseme_KG"] + 0.35 * viseme_weights["viseme_SZ"]),
            4,
        )
        tongue_out = round(min(1.0, 0.90 * viseme_weights["viseme_TH"]), 4)

        # Emotion weights with smooth transitions across the three dramatic acts
        emotions = {
            "focus": 0.0,
            "surprise": 0.0,
            "concern_sadness": 0.0,
            "joy_confidence": 0.0,
            "anger": 0.0,
            "pain": 0.0,
        }
        if t < 5.15:
            emotions["focus"] = 0.85
        elif t < 5.45:
            alpha = (t - 5.15) / 0.30
            emotions["focus"] = round(0.85 * (1.0 - alpha), 4)
            emotions["surprise"] = round(0.90 * alpha, 4)
        elif t < 7.65:
            # Transition from initial spike surprise into urgent concern + slight anger/tension
            alpha = (t - 5.45) / 2.20
            emotions["surprise"] = round(0.90 * (1.0 - 0.6 * alpha), 4)
            emotions["concern_sadness"] = round(0.75 * alpha, 4)
            emotions["anger"] = round(0.25 * alpha, 4)
        elif t < 10.30:
            emotions["concern_sadness"] = 0.88
            emotions["focus"] = 0.35
        elif t < 12.65:
            emotions["focus"] = 0.92
            emotions["concern_sadness"] = 0.20
        else:
            alpha = min(1.0, (t - 12.65) / 0.45)
            emotions["focus"] = round(0.92 * (1.0 - 0.6 * alpha), 4)
            emotions["joy_confidence"] = round(0.90 * alpha, 4)

        # Gaze interpolation
        gaze_yaw = 0.0
        gaze_pitch = 0.0
        gesture = "ready_stance"
        for seg in segment_records:
            if seg["start_sec"] - 0.15 <= t <= seg["end_sec"] + 0.15:
                gaze_yaw = seg["gaze"]["yaw_deg"]
                gaze_pitch = seg["gaze"]["pitch_deg"]
                gesture = seg["gesture"]
                break

        # Blink envelope (asymmetric subtle offset between L and R for realism)
        blink_l = 0.0
        blink_r = 0.0
        for bt in blink_times:
            dl = abs(t - bt)
            dr = abs(t - (bt + 0.012))
            if dl < 0.09:
                blink_l = max(blink_l, round(0.5 * (1.0 + math.cos(math.pi * dl / 0.09)), 4))
            if dr < 0.09:
                blink_r = max(blink_r, round(0.5 * (1.0 + math.cos(math.pi * dr / 0.09)), 4))

        frames.append(
            {
                "frame": f,
                "time_sec": t,
                "active_viseme": active_viseme,
                "visemes": viseme_weights,
                "jaw_open": jaw_open,
                "tongue_up": tongue_up,
                "tongue_out": tongue_out,
                "emotions": emotions,
                "gaze_yaw_deg": gaze_yaw,
                "gaze_pitch_deg": gaze_pitch,
                "blink_l": blink_l,
                "blink_r": blink_r,
                "gesture": gesture,
            }
        )
    return frames


def main():
    repo_root = Path(__file__).resolve().parents[2]
    audio_dir = repo_root / "source" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    master_audio, segment_records, word_records, phoneme_records = synthesize_segments()
    frame_curves = build_frame_curves(segment_records, phoneme_records)

    wav_path = audio_dir / "dialogue.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        packed = struct.pack(
            f"<{len(master_audio)}h",
            *(int(max(-1.0, min(1.0, s)) * 32767) for s in master_audio),
        )
        wf.writeframes(packed)

    full_transcript = " ".join(s["text"] for s in SEGMENTS)
    txt_path = audio_dir / "dialogue.txt"
    txt_path.write_text(full_transcript + "\n", encoding="utf-8")

    alignment = {
        "clip_id": "dialogue",
        "audio_file": "source/audio/dialogue.wav",
        "transcript_file": "source/audio/dialogue.txt",
        "transcript": full_transcript,
        "duration_seconds": TOTAL_DURATION_SEC,
        "fps": FPS,
        "total_frames": TOTAL_FRAMES,
        "sample_rate_hz": SAMPLE_RATE,
        "synthesizer": "eSpeak NG 1.52.0.1 (en-us+f3) with procedural acoustic warmth filter",
        "emotional_arc_summary": (
            "Starts in calm tactical focus (0.0-5.15s), shifts sharply to surprise and urgent "
            "concern when a voltage spike hits the primary conduit (5.15-10.30s), transitions to "
            "intense focus while rerouting wrist-emitter power (10.30-12.65s), and concludes with "
            "joy/confidence once the lane network stabilizes (12.65-14.50s)."
        ),
        "viseme_mapping_standard": VISEME_DOC,
        "segments": segment_records,
        "words": word_records,
        "phonemes": phoneme_records,
        "frames_30fps": frame_curves,
    }

    align_path = audio_dir / "dialogue_alignment.json"
    align_path.write_text(json.dumps(alignment, indent=2), encoding="utf-8")
    print(f"Generated {wav_path} ({TOTAL_DURATION_SEC:.2f}s, {len(master_audio)} samples)")
    print(f"Generated {txt_path} ({len(full_transcript)} chars)")
    print(f"Generated {align_path} ({len(phoneme_records)} phonemes, {len(frame_curves)} frames)")


if __name__ == "__main__":
    main()
