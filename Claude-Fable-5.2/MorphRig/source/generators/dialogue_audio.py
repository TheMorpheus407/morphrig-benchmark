"""Synthesises the Operative's spoken line and writes the audio, transcript and time alignment.

    python3 -I dialogue_audio.py <patched_voice.onnx> <output_dir> [--work <dir>]

* Speech synthesis: Piper TTS 1.4.2 (local, nix store) with the `en_US-ljspeech-high` voice. The voice model is a
  third-party asset (see docs/THIRD_PARTY_ASSETS.csv); it is not redistributed with this project.
* The voice has to be patched once so that it also returns the duration predictor output
  (`python -m piper.patch_voice_with_alignment`); this script expects the patched copy.
* Alignment: every phoneme start/end comes from the synthesiser's own per-phoneme sample counts, accumulated over
  the sentence segments and the authored pauses. Nothing is estimated by ear or by a second model.
* The line, its segmentation, the pauses and the tempo change between the tense first half and the relieved second
  half are authored here.

Outputs: dialogue.wav (48 kHz mono 16 bit), dialogue.txt, dialogue_alignment.json
"""
import glob
import json
import os
import re
import site
import subprocess
import sys
import wave

SEGMENTS = [
    # text, length_scale, pause_after_s, emotion
    ("Operative to all teams.", 0.85, 0.22, 'urgent'),
    ("The relay is failing, and the lane is wide open.", 0.83, 0.28, 'urgent'),
    ("Hold your positions.", 0.88, 0.32, 'urgent'),
    ("Give me thirty seconds.", 0.85, 0.18, 'urgent'),
    ("I'll stabilize the network myself.", 0.85, 0.95, 'urgent'),
    ("There.", 1.05, 0.30, 'relief'),
    ("Signal is back.", 0.97, 0.34, 'relief'),
    ("Push forward,", 0.95, 0.12, 'confident'),
    ("and thank you for trusting me.", 0.96, 0.05, 'warm'),
]
TEXT = ' '.join(s[0] for s in SEGMENTS)
FPS = 30
AUDIO_START_FRAME = 9            # the WAV starts at this clip frame (line_start marker)
TAIL_FRAMES = 18                 # clip frames after the audio ends (return to idle)
OUT_RATE = 48000

# IPA symbol (as emitted by the eSpeak NG phonemiser inside Piper) -> viseme control of the face rig
VISEME_OF = {
    'p': 'PP', 'b': 'PP', 'm': 'PP',
    'f': 'FF', 'v': 'FF',
    'θ': 'TH', 'ð': 'TH',
    't': 'DD', 'd': 'DD', 'n': 'DD', 'l': 'DD', 'ɾ': 'DD', 'ɫ': 'DD',
    'k': 'KK', 'ɡ': 'KK', 'g': 'KK', 'ŋ': 'KK', 'h': 'KK',
    'ʃ': 'CH', 'ʒ': 'CH',
    's': 'SS', 'z': 'SS',
    'ɹ': 'RR', 'r': 'RR', 'ɚ': 'RR', 'ɝ': 'RR',
    'w': 'OO', 'j': 'EE',
    'ɑ': 'AA', 'a': 'AA', 'æ': 'AA', 'ʌ': 'AA', 'ɐ': 'AA', 'ɒ': 'OH',
    'ɛ': 'EH', 'e': 'EH', 'ə': 'EH', 'ɜ': 'EH',
    'i': 'EE', 'ɪ': 'EE', 'ᵻ': 'EE',
    'ɔ': 'OH', 'o': 'OH',
    'u': 'OO', 'ʊ': 'OO',
}
# articulation strength of the mouth shape (reduced vowels and weak consonants read smaller)
STRENGTH = {'ə': 0.55, 'ɪ': 0.70, 'ᵻ': 0.6, 'ʊ': 0.80, 'h': 0.25, 'ŋ': 0.6, 'n': 0.7, 'd': 0.75, 't': 0.75, 'l': 0.8, 'ɐ': 0.7, 'ɜ': 0.8}
VOWELS = set('ɑaæʌɐɒɛeəɜiɪᵻɔouʊɚɝ')
MODIFIERS = {'ˈ': 'primary', 'ˌ': 'secondary', 'ː': 'long'}
SILENT = {'^', '$', ' ', '.', ',', '!', '?', ';', ':', '_'}


def piper_setup():
    cands = sorted(glob.glob('/nix/store/*-piper-tts-1.4.2/bin/.piper-wrapped'))
    if not cands:
        raise SystemExit('piper-tts 1.4.2 not found in /nix/store (nix-shell -p piper-tts)')
    src = open(cands[0]).read()
    m = re.search(r"site\.addsitedir\(p, k\), \[(.*?)\]", src, re.S)
    for p in re.findall(r"'([^']+)'", m.group(1)):
        site.addsitedir(p)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    model, outdir = args[0], args[1]
    work = outdir
    if '--work' in sys.argv:
        work = sys.argv[sys.argv.index('--work') + 1]
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    piper_setup()
    import numpy as np
    import onnxruntime
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    voice = PiperVoice.load(model)
    sr = voice.config.sample_rate
    audio = []
    n_total = 0
    phon = []            # dict(ipa, start, end, seg, word(None), stress, long)
    segs = []
    words = []
    for si, (text, ls, pause, emotion) in enumerate(SEGMENTS):
        onnxruntime.set_seed(4200 + si)
        np.random.seed(4200 + si)
        cfg = SynthesisConfig(length_scale=ls, noise_scale=0.45, noise_w_scale=0.5, normalize_audio=False)
        chunks = list(voice.synthesize(text, cfg, include_alignments=True))
        assert len(chunks) == 1, 'segment was split: ' + text
        ch = chunks[0]
        a = ch.audio_float_array.astype(np.float64)
        al = ch.phoneme_alignments
        assert al is not None and sum(p.num_samples for p in al) == len(a), 'the voice returned no usable alignment'
        # level the segments (bounded) so the quiet ones stay intelligible
        rms = float(np.sqrt(np.mean(a * a)) + 1e-9)
        a = a * min(2.2, max(0.6, 0.075 / rms))
        seg_start = n_total
        # words of this segment (transcript order); eSpeak separates words with ' '
        seg_words = [w for w in re.findall(r"[A-Za-z']+", text)]
        wi = 0
        cur = None
        pos = n_total
        stress = None
        for p in al:
            s0, s1 = pos, pos + int(p.num_samples)
            pos = s1
            sym = p.phoneme
            if sym in MODIFIERS:
                if sym == 'ː' and phon and phon[-1]['seg'] == si and phon[-1]['end_s'] == s0:
                    phon[-1]['end_s'] = s1               # length mark extends the vowel before it
                    phon[-1]['long'] = True
                else:
                    stress = MODIFIERS[sym]              # stress mark: its samples belong to the next phoneme
                    pending = s0 if cur is None or True else s0
                    phon.append(dict(ipa=None, start_s=s0, end_s=s1, seg=si, stress_mark=stress))
                continue
            if sym in SILENT:
                if sym == ' ' and cur is not None:
                    cur = None
                    wi += 1
                stress = None
                continue
            if cur is None:
                assert wi < len(seg_words), ('more phoneme words than text words', text)
                cur = dict(word=seg_words[wi], start_s=s0, end_s=s1, seg=si)
                words.append(cur)
            # absorb a directly preceding stress mark
            start = s0
            st = None
            if phon and phon[-1].get('ipa') is None and phon[-1]['seg'] == si and phon[-1]['end_s'] == s0:
                mk = phon.pop()
                start = mk['start_s']
                st = mk['stress_mark']
                if cur['start_s'] == s0:
                    cur['start_s'] = start
            phon.append(dict(ipa=sym, start_s=start, end_s=s1, seg=si, word=len(words) - 1, stress=st, long=False))
            cur['end_s'] = s1
        phon = [p for p in phon if p.get('ipa') is not None]
        assert wi + (1 if cur is not None else 0) == len(seg_words), ('word count mismatch', text, wi, len(seg_words))
        audio.append(a)
        n_total += len(a)
        segs.append(dict(index=si, text=text, emotion=emotion, start_s=seg_start, end_s=n_total, length_scale=ls, pause_after=pause))
        gap = int(round(pause * sr))
        audio.append(np.zeros(gap))
        n_total += gap
    a = np.concatenate(audio)
    # short fades at the very start / end, peak normalisation to -1.5 dBFS
    fade = int(0.01 * sr)
    a[:fade] *= np.linspace(0.0, 1.0, fade)
    a[-fade:] *= np.linspace(1.0, 0.0, fade)
    a = a / float(np.max(np.abs(a))) * 10 ** (-1.5 / 20)
    raw = os.path.join(work, 'dialogue_22k.wav')
    with wave.open(raw, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767.0).astype('<i2').tobytes())
    wav = os.path.join(outdir, 'dialogue.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw, '-af', 'highpass=f=70,aresample=%d:resampler=soxr' % OUT_RATE,
                    '-ac', '1', '-c:a', 'pcm_s16le', wav], check=True)
    with wave.open(wav, 'rb') as w:
        duration = w.getnframes() / float(w.getframerate())
    T = lambda s: round(s / float(sr), 4)
    frames = AUDIO_START_FRAME + int(-(-duration * FPS // 1)) + TAIL_FRAMES
    shift_seg = next(s for s in segs if s['emotion'] == 'relief')
    doc = dict(
        schema='morphrig.dialogue_alignment/1',
        audio='dialogue.wav', sample_rate=OUT_RATE, duration=round(duration, 4), text=TEXT,
        clip=dict(id='dialogue', fps=FPS, frames=frames, audio_start_frame=AUDIO_START_FRAME, audio_start_time=round(AUDIO_START_FRAME / FPS, 4),
                  note='audio time 0 corresponds to clip frame audio_start_frame (the line_start marker); '
                       'clip frame = audio_start_frame + time * fps'),
        markers=dict(line_start=0.0, emotion_shift=T(shift_seg['start_s']), line_end=T(segs[-1]['end_s'])),
        method='Phoneme boundaries are the per-phoneme sample counts returned by the synthesiser (Piper VITS duration predictor, '
               'hop 256 at 22.05 kHz), accumulated over the authored segments and pauses. Stress marks are merged into the '
               'following phoneme and length marks into the preceding vowel.',
        synthesis=dict(tool='Piper TTS 1.4.2 (local)', voice='en_US-ljspeech-high', phonemizer='eSpeak NG (bundled with Piper)',
                       noise_scale=0.45, noise_w_scale=0.5, seeds='4200 + segment index'),
        segments=[dict(index=s['index'], text=s['text'], emotion=s['emotion'], start=T(s['start_s']), end=T(s['end_s']),
                       length_scale=s['length_scale'], pause_after=s['pause_after']) for s in segs],
        words=[dict(word=w['word'], start=T(w['start_s']), end=T(w['end_s']), segment=w['seg']) for w in words],
        phonemes=[dict(phoneme=p['ipa'], viseme=VISEME_OF.get(p['ipa'], 'sil'), start=T(p['start_s']), end=T(p['end_s']), word=p['word'],
                       stress=p['stress'], long=p['long'], strength=STRENGTH.get(p['ipa'], 1.0), vowel=p['ipa'] in VOWELS) for p in phon],
        viseme_map={k: v for k, v in sorted(VISEME_OF.items())},
    )
    unknown = sorted({p['ipa'] for p in phon if p['ipa'] not in VISEME_OF})
    if unknown:
        raise SystemExit('phonemes without a viseme: %s' % unknown)
    with open(os.path.join(outdir, 'dialogue_alignment.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    with open(os.path.join(outdir, 'dialogue.txt'), 'w', encoding='utf-8') as f:
        f.write(TEXT + '\n')
    print('duration %.3f s, clip frames %d, words %d, phonemes %d' % (duration, frames, len(words), len(phon)))
    print(' '.join('%s[%.2f]' % (w['word'], w['start_s'] / sr) for w in words))


if __name__ == '__main__':
    main()
