"""Independent cross-check of dialogue_alignment.json: transcribe dialogue.wav with OpenAI Whisper (word timestamps) and compare the
recognised words and their times with the alignment that came out of the TTS duration predictor. Writes the result into the JSON
("verification") and prints a summary. Usage: python3 verify_dialogue.py [audio_dir]   (needs the `whisper` CLI and the small.en model)."""
import difflib
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

audio_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'audio'
align_path = audio_dir / 'dialogue_alignment.json'
info = json.loads(align_path.read_text(encoding='utf-8'))
norm = lambda s: re.sub(r"[^a-z']", '', s.lower())
with tempfile.TemporaryDirectory(prefix='mr_whisper_') as td:
    subprocess.run(['whisper', str(audio_dir / 'dialogue.wav'), '--model', 'small.en', '--model_dir', str(Path.home() / '.cache/whisper'), '--language', 'en',
                    '--device', 'cpu', '--fp16', 'False', '--word_timestamps', 'True', '--output_format', 'json', '--output_dir', td, '--verbose', 'False'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wh = json.loads((Path(td) / 'dialogue.json').read_text(encoding='utf-8'))
ww = [(norm(w['word']), w['start'], w['end']) for s in wh['segments'] for w in s['words']]
mine = [(norm(w['text']), w['start'], w['end']) for w in info['words']]
sm = difflib.SequenceMatcher(a=[m[0] for m in mine], b=[w[0] for w in ww], autojunk=False)
ds, de, matched = [], [], 0
for blk in sm.get_matching_blocks():
    for k in range(blk.size):
        a, b = mine[blk.a + k], ww[blk.b + k]
        ds.append(abs(a[1] - b[1]))
        de.append(abs(a[2] - b[2]))
        matched += 1
ds.sort()
de.sort()
p90 = lambda v: v[min(len(v) - 1, int(0.9 * len(v)))]
ver = {
    'method': 'OpenAI Whisper small.en, word timestamps (cross-attention DTW), compared with the TTS duration-predictor alignment',
    'whisper_transcript': wh['text'].strip(),
    'script_words': len(mine), 'whisper_words': len(ww), 'words_matched_by_text': matched,
    'word_start_abs_diff_ms': {'median': round(1000 * statistics.median(ds)), 'p90': round(1000 * p90(ds)), 'max': round(1000 * ds[-1])},
    'word_end_abs_diff_ms': {'median': round(1000 * statistics.median(de)), 'p90': round(1000 * p90(de)), 'max': round(1000 * de[-1])},
    'note': 'Whisper word times are approximate (tens of milliseconds). The TTS alignment is exact for the synthesised samples and is the one used for lip sync.',
}
info['verification'] = ver
align_path.write_text(json.dumps(info, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(ver, indent=1))
