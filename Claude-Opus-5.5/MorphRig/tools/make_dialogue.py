#!/usr/bin/env python3
"""Synthesize the Operative's dialogue line with local Piper TTS and write WAV + alignment.

Run inside:  nix-shell -p piper-tts espeak-ng --run "python3 MorphRig/tools/make_dialogue.py --voice DIR"

* Voice: en_US-john-medium (Piper voices, MIT repo; dataset LibriVox public domain; see
  docs/THIRD_PARTY_ASSETS.csv).  The ONNX model is patched locally (same method as
  piper/patch_voice_with_alignment.py) so the duration predictor's ceil() output is exposed
  and every phoneme gets an exact sample count.
* Output: source/audio/dialogue.wav (22.05 kHz mono 16-bit), dialogue.txt and
  dialogue_alignment.json (sentences, words, phonemes with start/end seconds).
"""
import argparse
import json
import os
import re
import shutil
import site
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LINES = [
    # (text, pause after in seconds, tone tag used by the performance generator)
    ("East lane is mine.", 0.22, "confident"),
    ("Give me ninety seconds, and this whole network stabilizes.", 0.52, "confident"),
    ("Hold on.", 0.30, "concern"),
    ("Something is rewriting the grid from the inside.", 0.48, "concern"),
    ("No.", 0.24, "anger"),
    ("Not on my watch.", 0.40, "anger"),
    ("Hold the line.", 0.22, "resolve"),
    ("I'm patching the node myself.", 0.50, "resolve"),
]
LEAD_IN = 0.35


def bootstrap_piper():
    """Import piper's own site-packages (the nix wrapper lists them)."""
    exe = shutil.which("piper")
    if exe is None:
        sys.exit("piper not on PATH (use: nix-shell -p piper-tts espeak-ng)")
    exe = os.path.realpath(exe)
    wrapped = os.path.join(os.path.dirname(exe), ".piper-wrapped")
    txt = open(wrapped).read()
    m = re.search(r"\[('/nix/store/[^\]]+)\]", txt)
    for p in re.findall(r"'([^']+)'", m.group(0)):
        site.addsitedir(p)


def patch_model(src, dst):
    import onnx
    model = onnx.load(src)
    names = set()
    for node in model.graph.node:
        if node.op_type == "Ceil":
            names.update(node.output)
    assert len(names) == 1, names
    name = next(iter(names))
    if not any(o.name == name for o in model.graph.output):
        vi = onnx.helper.ValueInfoProto()
        vi.name = name
        model.graph.output.append(vi)
    onnx.save(model, dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="dir with en_US-john-medium.onnx(.json)")
    ap.add_argument("--out", default=os.path.join(ROOT, "source", "audio"))
    ap.add_argument("--length-scale", type=float, default=0.98)
    args = ap.parse_args()
    bootstrap_piper()
    import numpy as np
    from piper import PiperVoice, SynthesisConfig
    src = os.path.join(args.voice, "en_US-john-medium.onnx")
    patched = os.path.join(args.voice, "en_US-john-medium.aligned.onnx")
    if not os.path.exists(patched):
        patch_model(src, patched)
        shutil.copy(src + ".json", patched + ".json")
    voice = PiperVoice.load(patched, config_path=patched + ".json")
    sr = voice.config.sample_rate
    cfg = SynthesisConfig(length_scale=args.length_scale, noise_scale=0.55, noise_w_scale=0.7)
    pcm = [np.zeros(int(LEAD_IN * sr), np.float32)]
    t = LEAD_IN
    out = {"sample_rate": sr, "fps": 30, "voice": "en_US-john-medium", "length_scale": args.length_scale,
           "sentences": [], "words": [], "phonemes": []}
    for text, pause, tone in LINES:
        chunks = list(voice.synthesize(text, syn_config=cfg, include_alignments=True))
        s_start = t
        for ch in chunks:
            audio = ch.audio_float_array.astype(np.float32)
            al = ch.phoneme_alignments
            assert al, "alignment missing (model not patched?)"
            cur = t
            word = []
            w_start = None
            for pa in al:
                dur = pa.num_samples / sr
                ph = pa.phoneme
                if ph in ("^", "$", "_"):
                    cur += dur
                    continue
                if ph == " ":
                    if word:
                        out["words"].append({"ipa": "".join(word), "start": round(w_start, 4), "end": round(cur, 4)})
                    word, w_start = [], None
                    cur += dur
                    continue
                if w_start is None:
                    w_start = cur
                out["phonemes"].append({"p": ph, "start": round(cur, 4), "end": round(cur + dur, 4)})
                if ph not in ",.!?;:—-":
                    word.append(ph)
                cur += dur
            if word:
                out["words"].append({"ipa": "".join(word), "start": round(w_start, 4), "end": round(cur, 4)})
            pcm.append(audio)
            t += len(audio) / sr
        out["sentences"].append({"text": text, "tone": tone, "start": round(s_start, 4), "end": round(t, 4)})
        pcm.append(np.zeros(int(pause * sr), np.float32))
        t += pause
    audio = np.concatenate(pcm)
    peak = float(np.max(np.abs(audio)))
    audio = audio / max(peak, 1e-6) * 0.89
    # attach orthographic words to the IPA words sentence by sentence (espeak may join words,
    # e.g. "from the" -> one phonetic word); joined words get the combined text
    ortho = []
    for (text, _, _), sent in zip(LINES, out["sentences"]):
        ow = re.findall(r"[A-Za-z']+", text)
        iw = [w for w in out["words"] if w["start"] >= sent["start"] - 1e-3 and w["end"] <= sent["end"] + 1e-3]
        ortho += ow
        groups = [[o] for o in ow]

        def cost(gr):
            return sum(abs(len(re.sub("[ˈˌː]", "", w["ipa"])) - 0.85 * len("".join(g))) for w, g in zip(iw, gr))
        while len(groups) > len(iw):
            # merge the adjacent pair that best explains the phonetic word lengths
            best = None
            for i in range(len(groups) - 1):
                cand = groups[:i] + [groups[i] + groups[i + 1]] + groups[i + 2:]
                c = cost(cand)
                if best is None or c < best[0]:
                    best = (c, cand)
            groups = best[1]
        for w, g in zip(iw, groups):
            w["text"] = " ".join(g)
    out["duration"] = round(len(audio) / sr, 4)
    os.makedirs(args.out, exist_ok=True)
    with wave.open(os.path.join(args.out, "dialogue.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    with open(os.path.join(args.out, "dialogue.txt"), "w") as fh:
        fh.write(" ".join(l[0] for l in LINES) + "\n")
    with open(os.path.join(args.out, "dialogue_alignment.json"), "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("DIALOGUE", out["duration"], "s,", len(out["words"]), "words,", len(out["phonemes"]), "phonemes,",
          "text attached:", sum(1 for w in out["words"] if "text" in w))


if __name__ == "__main__":
    main()
