#!/usr/bin/env python3
"""Exercise final packaged inspection controls with actual local input."""
import json
import os
import argparse
from pathlib import Path
import subprocess
import time

from qa_input import ShowcaseInput, XDOTOOL

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--mouse',action='store_true',help='Also test Normals via X11 mouse; requires a display that routes XWayland synthetic clicks correctly.')
args=parser.parse_args()
OUT = ROOT / 'docs/validation/runtime_final_controls'
OUT.mkdir(parents=True, exist_ok=True)
events = []
env = dict(os.environ, SDL_VIDEODRIVER='x11')
with (OUT / 'stdout.log').open('w') as stdout:
    client = subprocess.Popen(
        ['bash', str(ROOT / 'tools/run_showcase.sh'), '-MorphSeconds=120',
         f'-MorphEvidenceDir={OUT}'], stdout=stdout, stderr=subprocess.STDOUT, env=env)
    window = None
    for _ in range(40):
        time.sleep(.5)
        if client.poll() is not None:
            raise RuntimeError(f'Client exited before inspection: {client.returncode}')
        candidates = subprocess.run(['pgrep', '-x', 'MorphRig'], capture_output=True, text=True).stdout.split()
        for pid in candidates:
            command = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
            if str(ROOT / 'build/Linux') not in command:
                continue
            found = subprocess.run([XDOTOOL, 'search', '--onlyvisible', '--pid', pid], capture_output=True, text=True).stdout.split()
            if found:
                window = found[-1]
                break
        if window:
            break
    if not window:
        raise RuntimeError('Packaged showcase X11 window was not found')
    subprocess.run([XDOTOOL, 'windowmove', '--sync', window, '2300', '2300'], check=True)
    time.sleep(3)
    with ShowcaseInput(window) as q:
        def shot(name):
            time.sleep(.6)
            q.capture(OUT / f'{name}.png')
            events.append({'image': f'{name}.png', 'time_unix': time.time()})
        shot('textured')
        if args.mouse:
            q.click(210, 348)
            shot('normals')
            q.click(210, 348)
        q.key(24)
        shot('skeleton')
        q.key(24)
        q.key(47)
        shot('front')
        q.key(47)
        shot('side')
        q.key(47)
        shot('top_down_team_a')
        q.key(20)
        shot('top_down_team_b')
        q.key(47)
        q.key(47)
        for lod in range(3):
            q.key(38)
            shot(f'forced_lod{lod}')
        q.key(38)
        q.key(49)
        shot('ten_team_b')
        q.key(20)
        shot('ten_team_a')
        q.key(49)
        q.key(1)
    code = client.wait(timeout=20)
    trace = OUT / 'state_event_trace.log'
    result = {'scope': 'Actual packaged inspection through focus-verified native keyboard events. Images require visual review.',
              'mouse_attempted':args.mouse,
              'normals_note':'Optional XWayland mouse routing is environment-dependent. Normals was observed working on September 26; it is not recaptured by the default keyboard-only run.',
              'client_exit_code': code, 'trace_saved': trace.exists() and trace.stat().st_size > 0,
              'screenshots': events}
    (OUT / 'input_record.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if code or not result['trace_saved']:
        raise SystemExit(1)
