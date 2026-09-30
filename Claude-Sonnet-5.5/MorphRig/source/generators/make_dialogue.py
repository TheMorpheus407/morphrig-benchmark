"""Original spoken performance for the Operative: script -> local TTS -> WAV, transcript and alignment JSON.

Run inside the piper-tts environment:
    tools/piper_py.sh source/generators/make_dialogue.py [--out source/audio] [--seed N]

Engine: piper-tts 1.4.2 (VITS voices, eSpeak NG phonemizer). The voice is en_US-ljspeech-high (trained from scratch on the public-domain LJ Speech
dataset, see source/audio/voice/MODEL_CARD_en_US-ljspeech-high.txt). The ONNX voice is patched to expose the duration
predictor output, which gives the exact number of samples of every phoneme, so the alignment comes from the synthesis itself and is
not estimated afterwards. verify_dialogue.py cross-checks the result with an independent speech recogniser.

Outputs (in --out): dialogue.wav (mono 16-bit), dialogue.txt (transcript), dialogue_alignment.json.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VOICE_NAME = 'en_US-ljspeech-high'
LEAD_IN = 0.50       # seconds of silence before the first word (breath in, look up)
TAIL = 0.90          # seconds after the last word (hold the last expression)
FPS = 30

# text, pause after (s), length_scale (>1 slower). The line is about holding a lane and stabilizing a network (SPEC section 9).
# Emotional arc: worry (the network is collapsing) -> resolve (I can hold the lane) -> warmth (I will be right behind you).
SCRIPT = [
    ('Listen.', 0.60, 1.08),
    ('The network is collapsing, and every lane into the district is going dark.', 0.70, 1.02),
    ('But I can hold the north lane, if you stabilize the relay.', 0.50, 0.95),
    ('Keep the signal alive, and trust the beacon.', 0.50, 1.00),
    ("I'll be right behind you.", 0.0, 1.05),
]
NOISE_SCALE = 0.50
NOISE_W = 0.55

# ----------------------------------------------------------------------------- IPA (eSpeak NG, en-us) -> viseme
# (viseme, weight): the weight scales the viseme target so reduced vowels open the mouth less. Viseme names and the way they map to
# face controls are defined in skeleton_def.VISEMES.
IPA_VISEME = {
    'p': ('PP', 1.0), 'b': ('PP', 1.0), 'm': ('PP', 1.0),
    'f': ('FF', 1.0), 'v': ('FF', 1.0),
    'θ': ('TH', 1.0), 'ð': ('TH', 0.9),
    't': ('DD', 1.0), 'd': ('DD', 1.0), 'n': ('DD', 0.9), 'l': ('DD', 1.0), 'ɫ': ('DD', 1.0), 'ɾ': ('DD', 0.8), 'ʔ': ('DD', 0.3),
    'k': ('KK', 1.0), 'ɡ': ('KK', 1.0), 'g': ('KK', 1.0), 'ŋ': ('KK', 0.9), 'x': ('KK', 0.8),
    'ʃ': ('CH', 1.0), 'ʒ': ('CH', 1.0), 'tʃ': ('CH', 1.0), 'dʒ': ('CH', 1.0), 'ʧ': ('CH', 1.0), 'ʤ': ('CH', 1.0),
    's': ('SS', 1.0), 'z': ('SS', 1.0),
    'ɹ': ('RR', 1.0), 'r': ('RR', 1.0), 'ɻ': ('RR', 1.0), 'ɚ': ('RR', 0.9), 'ɝ': ('RR', 1.0),
    'w': ('OO', 0.85), 'j': ('EE', 0.6), 'h': ('IH', 0.4),
    'ɑ': ('AA', 1.0), 'ɒ': ('AA', 0.8), 'ɐ': ('AA', 0.5), 'a': ('AA', 0.8), 'æ': ('AA', 0.75), 'ʌ': ('AA', 0.55),
    'ɔ': ('OH', 0.95), 'o': ('OH', 1.0),
    'ə': ('IH', 0.55), 'ɜ': ('IH', 0.7), 'ᵻ': ('IH', 0.6), 'ɪ': ('IH', 1.0),
    'ɛ': ('EE', 0.8), 'e': ('EE', 0.85), 'i': ('EE', 1.0),
    'ʊ': ('OO', 0.7), 'u': ('OO', 1.0),
}
STRESS = {'ˈ': 2, 'ˌ': 1}
PUNCT = set(',.;:!?—…-')
IGNORED = {'ʲ', '̃', '̩', '̯', '͡'}


def strip_marks(sym):
    return ''.join(ch for ch in sym if unicodedata.category(ch) not in ('Mn',) and ch not in IGNORED)


def build_phoneme_track(align, sr, t0):
    """align: list of (symbol, samples) for one sentence. Returns (phonemes, words_ipa) with absolute times (s)."""
    pos = 0
    events = []          # (sym, start_sample, end_sample)
    for sym, n in align:
        events.append((sym, pos, pos + n))
        pos += n
    phs = []
    word_idx = 0
    pending_stress = 0
    pending_start = None
    for sym, a, b in events:
        if sym in ('^', '$'):
            continue
        if sym == ' ':
            word_idx += 1
            continue
        if sym in STRESS:
            pending_stress = STRESS[sym]
            pending_start = a
            continue
        if sym == 'ː':
            if phs:
                phs[-1]['end'] = t0 + b / sr
                phs[-1]['long'] = True
            continue
        base = strip_marks(sym)
        if base == '':
            if phs:
                phs[-1]['end'] = t0 + b / sr
            continue
        if base in PUNCT or all(ch in PUNCT for ch in base):
            phs.append(dict(ipa=base, start=t0 + a / sr, end=t0 + b / sr, viseme='sil', weight=1.0, word=None, kind='pause', stress=0))
            continue
        vis, w = IPA_VISEME.get(base, (None, None))
        if vis is None:
            print(f'warning: no viseme for IPA symbol {base!r}, using IH', file=sys.stderr)
            vis, w = 'IH', 0.4
        start = a if pending_start is None else pending_start
        phs.append(dict(ipa=base, start=t0 + start / sr, end=t0 + b / sr, viseme=vis, weight=w, word=word_idx, kind='phoneme', stress=pending_stress))
        pending_stress = 0
        pending_start = None
    # diphthongs that eSpeak writes as two symbols and that read as one mouth shape
    merged = []
    i = 0
    while i < len(phs):
        p = phs[i]
        q = phs[i + 1] if i + 1 < len(phs) else None
        if q and p['kind'] == q['kind'] == 'phoneme' and p['word'] == q['word']:
            pair = p['ipa'] + q['ipa']
            if pair in ('əʊ', 'oʊ'):
                merged.append(dict(p, ipa=pair, end=q['end'], viseme='OH', weight=0.95))
                i += 2
                continue
            if pair == 'eɪ':
                merged.append(dict(p, ipa=pair, end=q['end'], viseme='EE', weight=0.9))
                i += 2
                continue
        merged.append(p)
        i += 1
    return merged


def run(out_dir):
    from piper import PiperVoice, SynthesisConfig
    import piper.patch_voice_with_alignment as pv
    voice_dir = HERE.parent / 'audio' / 'voice'
    src_model = voice_dir / f'{VOICE_NAME}.onnx'
    src_cfg = voice_dir / f'{VOICE_NAME}.onnx.json'
    if not src_model.exists():
        raise SystemExit(f'voice model missing: {src_model} (download instructions are in docs/build_and_import_instructions.md)')
    tmp = Path(tempfile.mkdtemp(prefix='mr_tts_'))
    try:
        patched = tmp / f'{VOICE_NAME}_aligned.onnx'
        argv0 = sys.argv
        sys.argv = ['patch_voice_with_alignment', str(src_model), '--output', str(patched)]
        pv.main()
        sys.argv = argv0
        shutil.copy(src_cfg, tmp / f'{VOICE_NAME}_aligned.onnx.json')
        voice = PiperVoice.load(patched, config_path=tmp / f'{VOICE_NAME}_aligned.onnx.json')
        sr = voice.config.sample_rate

        audio = [np.zeros(int(round(LEAD_IN * sr)), dtype=np.float32)]
        cursor = len(audio[0])
        sentences, words, phonemes, pauses = [], [], [], []
        for si, (text, pause_after, length_scale) in enumerate(SCRIPT):
            cfg = SynthesisConfig(length_scale=length_scale, noise_scale=NOISE_SCALE, noise_w_scale=NOISE_W)
            chunks = list(voice.synthesize(text, cfg, include_alignments=True))
            if len(chunks) != 1 or chunks[0].phoneme_alignments is None:
                raise SystemExit(f'sentence {si}: expected one aligned chunk, got {len(chunks)}')
            ch = chunks[0]
            wav = np.asarray(ch.audio_float_array, dtype=np.float32)
            align = [(a.phoneme, int(a.num_samples)) for a in ch.phoneme_alignments]
            if sum(n for _, n in align) != len(wav):
                raise SystemExit(f'sentence {si}: alignment covers {sum(n for _, n in align)} samples but audio has {len(wav)}')
            t0 = cursor / sr
            phs = build_phoneme_track(align, sr, t0)
            text_words = text.split()
            n_words = 1 + max(p['word'] for p in phs if p['word'] is not None)
            if n_words != len(text_words):
                raise SystemExit(f'sentence {si}: {n_words} phonetic words but {len(text_words)} text words')
            base_word = len(words)
            for wi, tw in enumerate(text_words):
                wp = [p for p in phs if p['word'] == wi]
                words.append(dict(index=base_word + wi, text=tw.strip(',.'), start=wp[0]['start'], end=wp[-1]['end'], sentence=si,
                                  ipa=''.join(p['ipa'] for p in wp), stress=any(p['stress'] == 2 for p in wp)))
            for p in phs:
                if p['word'] is not None:
                    p['word'] = base_word + p['word']
                phonemes.append(p)
            sp = [p for p in phs if p['kind'] == 'phoneme']
            sentences.append(dict(index=si, text=text, start=sp[0]['start'], end=sp[-1]['end']))
            audio.append(wav)
            cursor += len(wav)
            if pause_after > 0:
                n = int(round(pause_after * sr))
                audio.append(np.zeros(n, dtype=np.float32))
                pauses.append(dict(start=cursor / sr, end=(cursor + n) / sr, kind='sentence'))
                cursor += n
        tail = np.zeros(int(round(TAIL * sr)), dtype=np.float32)
        audio.append(tail)
        cursor += len(tail)
        sig = np.concatenate(audio)
        peak = float(np.abs(sig).max())
        sig = sig * (0.89 / peak)
        fade = int(0.008 * sr)
        sig[:fade] *= np.linspace(0, 1, fade)
        sig[-fade:] *= np.linspace(1, 0, fade)
        pcm = (np.clip(sig, -1, 1) * 32767.0).astype(np.int16)

        out_dir.mkdir(parents=True, exist_ok=True)
        wav_path = out_dir / 'dialogue.wav'
        with wave.open(str(wav_path), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        (out_dir / 'dialogue.txt').write_text('\n'.join(s[0] for s in SCRIPT) + '\n', encoding='utf-8')

        duration = len(pcm) / sr
        frames = int(round(duration * FPS))
        # merged viseme timeline (run-length)
        vis_line = []
        for p in phonemes:
            if vis_line and vis_line[-1]['viseme'] == p['viseme'] and abs(vis_line[-1]['end'] - p['start']) < 1e-4 and p['viseme'] == 'sil':
                vis_line[-1]['end'] = p['end']
            else:
                vis_line.append(dict(viseme=p['viseme'], start=p['start'], end=p['end'], weight=p['weight'], ipa=p['ipa']))
        for lst in (words, phonemes, sentences, pauses, vis_line):
            for d in lst:
                for k in ('start', 'end'):
                    if k in d:
                        d[k] = round(float(d[k]), 4)
        info = {
            'format': 'morphrig-dialogue-alignment/1',
            'audio': {'file': 'dialogue.wav', 'sample_rate': sr, 'channels': 1, 'sample_width_bytes': 2, 'duration_s': round(duration, 4),
                      'samples': int(len(pcm))},
            'clip': {'id': 'dialogue', 'fps': FPS, 'frames': frames, 'duration_s': round(frames / FPS, 4), 'lead_in_s': LEAD_IN, 'tail_s': TAIL},
            'transcript': ' '.join(s[0] for s in SCRIPT),
            'tts': {'engine': 'piper-tts 1.4.2 (VITS) with eSpeak NG phonemizer', 'voice': VOICE_NAME,
                    'voice_license': 'public domain dataset (LJ Speech), see source/audio/voice/MODEL_CARD_en_US-ljspeech-high.txt',
                    'params': {'noise_scale': NOISE_SCALE, 'noise_w_scale': NOISE_W, 'length_scale_per_sentence': [s[2] for s in SCRIPT]},
                    'alignment_source': 'duration predictor output of the voice model (phoneme widths, 256-sample hops), exact for the rendered audio',
                    'note': 'Synthesis uses random noise, so re-running produces a slightly different take. Keep the shipped WAV and JSON together.'},
            'viseme_set': 'skeleton_def.VISEMES (14 shapes, documented in docs/rig_usage.md)',
            'sentences': sentences, 'words': words, 'pauses': pauses, 'phonemes': phonemes, 'visemes': vis_line,
        }
        (out_dir / 'dialogue_alignment.json').write_text(json.dumps(info, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'wrote {wav_path} ({duration:.2f} s, {frames} frames at {FPS} fps), {len(words)} words, {len(phonemes)} phoneme events')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(HERE.parent / 'audio'))
    args = ap.parse_args()
    run(Path(args.out))
