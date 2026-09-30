"""Record the delivered standalone client, preserving actual realtime visuals.

Usage: python3 -B tools/capture_presentation.py [turntable|motion|face|all]
Requires the active XWayland DISPLAY and Nix ffmpeg-full/xdotool/xwininfo.
The original dialogue WAV is muxed at the client's traced speech onset;
desktop-wide audio is never captured. All outputs stay in this folder.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / 'verification/presentation'
TEMP.mkdir(parents=True, exist_ok=True)


def run(args, **kw):
    return subprocess.run(args, check=True, cwd=ROOT, **kw)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def dependencies():
    lines = run(['nix-shell', '-p', 'ffmpeg-full', 'xdotool', 'xwininfo',
                 '--run', 'command -v ffmpeg ffprobe xdotool xwininfo'],
                capture_output=True, text=True).stdout.splitlines()
    if len(lines) != 4:
        raise RuntimeError('Capture dependencies did not resolve.')
    return dict(zip(('ffmpeg', 'ffprobe', 'xdotool', 'xwininfo'), lines))


def trace_paths():
    return list((ROOT / 'unreal/Saved').rglob('state_events.jsonl')) + list(
        (ROOT / 'build/Linux').rglob('state_events.jsonl'))


def new_trace_rows(baselines):
    rows = []
    for path in trace_paths():
        with path.open() as stream:
            stream.seek(baselines.get(str(path), 0))
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def capture(kind, dep):
    duration = {'turntable': 15.0, 'motion': 110.0, 'face': 407 / 30}[kind]
    delay = 8.0
    options = {'turntable': ['-MorphTurntable', '-MorphClip=idle_relaxed', '-MorphNoHUD', '-MorphView=1'],
               'motion': ['-MorphSequence'],
               'face': ['-MorphClip=dialogue', '-MorphNoHUD', '-MorphView=3']}[kind]
    options += [f'-MorphStartDelay={delay}',
                f'-MorphExitSeconds={delay + duration + 1}', '-ForceRes']
    raw = TEMP / f'{kind}.mkv'
    silent = TEMP / f'{kind}_silent.mp4'
    final = ROOT / 'presentation' / {
        'turntable': 'turntable.mp4', 'motion': 'motion_showcase.mp4',
        'face': 'face_performance.mp4'}[kind]
    final.parent.mkdir(exist_ok=True)
    baselines = {str(p): p.stat().st_size for p in trace_paths()}
    log_path = ROOT / f'verification/logs/capture_{kind}_client.log'
    options.append(f'-abslog={log_path}')
    launch_wall = time.time()
    env = dict(os.environ, SDL_VIDEODRIVER='x11')
    with (TEMP / f'{kind}_launch.log').open('w') as client_log, (
            TEMP / f'{kind}_ffmpeg.log').open('w') as record_log:
        client = subprocess.Popen([str(ROOT / 'tools/build_linux.sh'), 'run',
                                   *options], cwd=ROOT, env=env,
                                  stdout=client_log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        recorder = None
        try:
            window = None
            until = time.monotonic() + 180
            while window is None and time.monotonic() < until:
                result = subprocess.run([dep['xdotool'], 'search', '--onlyvisible',
                                         '--name', 'MorphRig'],
                                        capture_output=True, text=True)
                for candidate in result.stdout.split():
                    pid = subprocess.run([dep['xdotool'], 'getwindowpid', candidate],
                                         capture_output=True, text=True).stdout.strip()
                    try:
                        command = Path(f'/proc/{pid}/cmdline').read_bytes()
                    except OSError:
                        continue
                    if str(ROOT / 'build/Linux').encode() in command:
                        window = candidate
                        break
                if client.poll() is not None:
                    raise RuntimeError(f'Client exited before capture: {client.returncode}')
                time.sleep(.05)
            if window is None:
                raise RuntimeError('Packaged MorphRig window not found.')
            geometry = run([dep['xwininfo'], '-id', window],
                           capture_output=True, text=True).stdout
            recorder = subprocess.Popen([
                dep['ffmpeg'], '-hide_banner', '-loglevel', 'warning', '-y',
                '-f', 'x11grab', '-window_id', window, '-framerate', '30',
                '-draw_mouse', '0', '-i', os.environ['DISPLAY'], '-copyts',
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough', str(raw)],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=record_log,
                stderr=subprocess.STDOUT)
            print(f'Recording {kind}: packaged window {window}', flush=True)
            client.wait(timeout=duration + 240)
        finally:
            if recorder is not None and recorder.poll() is None:
                recorder.send_signal(signal.SIGINT)
                recorder.wait(timeout=30)
            if client.poll() is None:
                os.killpg(client.pid, signal.SIGTERM)
                client.wait(timeout=30)
    if client.returncode != 0:
        raise RuntimeError(f'Client failed during {kind}: {client.returncode}')
    rows = new_trace_rows(baselines)
    start = next((r for r in rows if r['action'].startswith('presentation_start')), None)
    if start is None or 'epoch' not in start:
        raise RuntimeError('Client did not supply presentation_start epoch for exact sync.')
    probe = json.loads(run([dep['ffprobe'], '-v', 'error', '-show_streams',
                           '-show_format', '-of', 'json', str(raw)],
                          capture_output=True, text=True).stdout)
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    if (stream['width'], stream['height']) != (1920, 1080):
        raise RuntimeError(f'Expected native 1920x1080 capture, got {stream["width"]}x{stream["height"]}.')
    first_frame = float(stream['start_time'])
    offset = float(start['epoch']) - first_frame
    if offset < 0:
        raise RuntimeError('Capture began after presentation onset; increase start delay.')
    run([dep['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw),
         '-ss', str(offset), '-t', str(duration), '-map', '0:v:0',
         '-vf', 'setpts=PTS-STARTPTS,fps=30', '-c:v', 'libx264',
         '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
         '-movflags', '+faststart', str(silent)])
    audio_offset = None
    if kind == 'turntable':
        silent.replace(final)
    else:
        onset = next(r for r in rows if r['action'].startswith('enter dialogue '))
        audio_offset = max(0, float(onset['epoch']) - float(start['epoch']))
        wav = ROOT / 'source/audio/dialogue.wav'
        run([dep['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-y',
             '-i', str(silent), '-i', str(wav), '-filter_complex',
             f'[1:a]adelay={round(audio_offset * 1000)}:all=1,apad[a]',
             '-map', '0:v:0', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac',
             '-b:a', '192k', '-t', str(duration), '-movflags', '+faststart', str(final)])
        silent.unlink()
    metadata = {'kind': kind, 'client': 'build/Linux/MorphRig.sh',
                'source': 'standalone realtime project; same delivered mesh and LODs',
                'launch_epoch': launch_wall, 'presentation_start': start,
                'first_capture_frame_epoch': first_frame, 'trim_seconds': offset,
                'speech_offset_seconds': audio_offset, 'fps': 30,
                'width': 1920, 'height': 1080, 'duration': duration,
                'window_geometry': geometry, 'command_options': options,
                'audio': ('silent turntable' if kind == 'turntable' else
                          'original delivered dialogue.wav, muxed at traced live onset'),
                'output': str(final.relative_to(ROOT)),
                'sha256': sha256(final),
                'source_sha256': sha256(ROOT / 'source/Operative.blend'),
                'manifest_sha256': sha256(ROOT / 'docs/animation_manifest.json'),
                'voice_sha256': sha256(ROOT / 'source/audio/dialogue.wav'),
                'client_binary_sha256': sha256(
                    ROOT / 'build/Linux/MorphRig/Binaries/Linux/MorphRig')}
    (TEMP / f'{kind}_capture.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (TEMP / f'{kind}_state_events.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in rows))
    print(f'Completed {final.relative_to(ROOT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('turntable', 'motion', 'face', 'all'), default='all', nargs='?')
    args = parser.parse_args()
    dep = dependencies()
    for kind in (('turntable', 'motion', 'face') if args.kind == 'all' else (args.kind,)):
        capture(kind, dep)
