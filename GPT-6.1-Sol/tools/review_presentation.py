"""Extract inspection frames from the three delivered realtime recordings.

Run after capture: python3 -B tools/review_presentation.py
Full-resolution frames and labelled contact sheets stay in verification.
Requires ffmpeg and Pillow; does not alter the recordings.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'verification/presentation'
PLANS = {
    'turntable': ('turntable.mp4', [
        (0, 'front'), (3.75, 'side'), (7.5, 'back'), (11.25, 'opposite side')]),
    'motion': ('motion_showcase.mp4', [
        (1.15, 'acceleration onset'), (1.35, 'first swing'),
        (1.65, 'start completion'),
        (4.3, 'moving fire'), (10.15, 'braking'), (10.45, 'stop settle'),
        (10.8, 'stopped recovery'), (17, 'channel'), (25, 'charge'),
        (29.45, 'reload grip'), (30.1, 'cell insertion'), (31.05, 'reload recovery'),
        (32.9, 'beacon deploy'), (44.8, 'held sleep'),
        (54.2, 'prone front'), (56, 'front getup'),
        (60.5, 'prone back'), (63, 'back getup'),
        (69.6, 'dead front'), (79.2, 'dead back'),
        (87, 'speech concern'), (93, 'speech confidence'),
        (103, 'half-rate melee'), (105.2, 'fast three-shot burst'),
        (106.8, 'airborne stasis'), (108.2, 'thaw'), (109.3, 'landing')]),
    'face': ('face_performance.mp4', [
        (.4065, 'rounded'), (1.4725, 'lip closure'), (3.4915, 'open vowel'),
        (4.2295, 'wide vowel'), (4.875, 'tongue'), (7.2165, 'pause'),
        (8.7, 'confidence shift'), (9.1595, 'consonant'),
        (10.438, 'labiodental'), (11.794, 'lip closure'),
        (12.6, 'final gesture'), (13.4, 'settle')]),
}


def main():
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is required for presentation review.')
    report = {}
    for kind, (filename, samples) in PLANS.items():
        video = ROOT / 'presentation' / filename
        sheet = Image.new('RGB', (4 * 480, ((len(samples) + 3) // 4) * 298), '#20212a')
        draw = ImageDraw.Draw(sheet)
        frames = []
        for index, (seconds, label) in enumerate(samples):
            path = DEST / f'review_final_{kind}_{index + 1:03d}.png'
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                            '-ss', str(seconds), '-i', str(video), '-frames:v', '1',
                            '-threads', '1', str(path)], check=True, cwd=ROOT)
            with Image.open(path) as frame:
                if frame.size != (1920, 1080):
                    raise ValueError(f'Unexpected frame dimensions: {path}')
                thumbnail = frame.convert('RGB').resize((480, 270), Image.Resampling.LANCZOS)
            x, y = (index % 4) * 480, (index // 4) * 298
            sheet.paste(thumbnail, (x, y))
            draw.text((x + 8, y + 276), f'{seconds:g}s | {label}', fill='white')
            frames.append({'seconds': seconds, 'label': label,
                           'file': str(path.relative_to(ROOT))})
        sheet_path = DEST / f'review_final_{kind}_sheet.png'
        sheet.save(sheet_path)
        report[kind] = {'video': str(video.relative_to(ROOT)),
                        'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                        'sheet': str(sheet_path.relative_to(ROOT)), 'frames': frames}
        print(f'Extracted {len(frames)} actual {kind} frames.', flush=True)
    (DEST / 'review_final_frames.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
