"""Audit actual standalone state/event traces against the closed inventory.

Usage: python3 -B tools/validate_runtime.py TRACE.jsonl [--sequence|--inventory]
Use a single-run trace: append-only client logs can contain repeated sessions.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('trace', type=Path)
parser.add_argument('--sequence', action='store_true')
parser.add_argument('--inventory', action='store_true')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
rows = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
checks = []


def check(name, passed, details=None):
    checks.append({'name': name, 'status': 'pass' if passed else 'fail', 'details': details})


marker_pattern = re.compile(r'^marker ([^/]+)/([^ ]+) clip_t=([\d.]+) token=(\d+) cycle=(\d+)')
seen = set()
duplicates = []
events = []
for row in rows:
    match = marker_pattern.match(row['action'])
    if not match:
        continue
    clip, marker, clip_time, token, cycle = match.groups()
    key = (row['actor'], clip, marker, token, cycle)
    if key in seen:
        duplicates.append(row)
    seen.add(key)
    events.append((row, clip, marker))
check('trace_has_rows', bool(rows), len(rows))
check('marker_executes_once_per_actor_track_cycle', not duplicates, duplicates)
manifest = {e['id']: e for e in json.loads((ROOT / 'docs/animation_manifest.json').read_text())['animations']}
unknown = [(clip, marker) for row, clip, marker in events
           if clip not in manifest or marker not in {m['name'] for m in manifest[clip]['events']}]
check('markers_belong_to_authored_manifest', not unknown, unknown)
actions = [r['action'] for r in rows]
entered = {a.split()[1] for a in actions if a.startswith('enter ')}
if args.inventory:
    required = {r['id'] for r in csv.DictReader((ROOT / 'required_animations.csv').open())}
    check('every_required_asset_played', required <= entered, sorted(required - entered))
    check('inventory_finished', 'inventory_complete' in actions)
if args.sequence:
    required = {'ranged_fire', 'ranged_burst', 'hit_l', 'cast_directional',
                'dash_f', 'blink_out', 'blink_in', 'channel_start', 'channel_loop',
                'channel_interrupt', 'channel_end', 'charge_start', 'charge_hold',
                'charge_release', 'charge_cancel', 'reload', 'deploy',
                'uplink_start', 'uplink_cancel', 'stun_start', 'stun_loop',
                'stun_end', 'sleep_start', 'sleep_loop', 'sleep_end',
                'knockup_start', 'knockdown_front', 'prone_front', 'getup_front',
                'knockdown_back', 'prone_back', 'getup_back', 'cast_ground',
                'death_front', 'dead_front', 'death_back', 'dead_back',
                'jump_start', 'respawn', 'dialogue', 'melee_1'}
    check('major_combined_states_played', required <= entered, sorted(required - entered))
    check('sequence_finished', 'deterministic_sequence_complete' in actions)
    check('representative_half_rate_and_fast_rate',
          any(abs(r['rate']-.5) < .001 for r in rows) and any(abs(r['rate']-1.5) < .001 for r in rows))
    teleport = [r for r in rows if r['action'] == 'blink_actor_event']
    check('one_blink_actor_event', len(teleport) == 1, len(teleport))
    hidden = [r for r in rows if r['action'] == 'blink_mesh_disappear']
    visible = [r for r in rows if r['action'] == 'blink_mesh_reappear']
    check('blink_disappears_and_reappears_once',
          len(hidden) == len(visible) == 1 and hidden[0]['t'] < visible[0]['t'],
          {'disappearances': len(hidden), 'reappearances': len(visible)})
    frozen = [r for r in rows if r['action'] == 'status stasis' and r['state'] == 'stasis']
    thawed = [r for r in rows if r['action'] == 'status stasis' and r['state'] != 'stasis']
    if len(frozen) == len(thawed) == 1:
        hold = [thawed[0][k]-frozen[0][k] for k in ('x', 'y', 'z')]
        before = [r for r in rows if r['t'] < frozen[0]['t'] and
                  r['action'].startswith('enter jump_start ')]
        airborne = bool(before) and frozen[0]['z']-before[-1]['z'] > 5
        check('airborne_stasis_holds_capsule_position',
              airborne and max(abs(d) for d in hold) < .01 and
              thawed[0]['t']-frozen[0]['t'] >= 1,
              {'delta_cm': hold, 'airborne': airborne,
               'hold_seconds': thawed[0]['t']-frozen[0]['t']})
    else:
        check('airborne_stasis_holds_capsule_position', False,
              {'freeze_entries': len(frozen), 'thaw_entries': len(thawed)})
    dash_enter = next((r for r in rows if r['action'].startswith('enter dash_f ')), None)
    dash_end = next((r for r in rows if r['action'] == 'complete dash_f'), None)
    if dash_enter and dash_end:
        delta = [dash_end[k]-dash_enter[k] for k in ('x', 'y', 'z')]
        check('forward_dash_capsule_travels_two_meters',
              abs(delta[0]-200) < 2 and abs(delta[1]) < 1 and abs(delta[2]) < 2, delta)
    else:
        check('forward_dash_capsule_travels_two_meters', False, 'No dash start/end trace.')
report = {'source': str(args.trace),
          'trace_sha256': hashlib.sha256(args.trace.read_bytes()).hexdigest(),
          'manifest_sha256': hashlib.sha256(
              (ROOT / 'docs/animation_manifest.json').read_bytes()).hexdigest(),
          'rows': len(rows), 'markers': len(events),
          'entered_clips': sorted(entered), 'checks': checks,
          'summary': {status: sum(c['status'] == status for c in checks) for status in ('pass', 'fail')}}
out = args.output or ROOT / 'verification/runtime_trace_validation.json'
if not out.resolve().is_relative_to(ROOT):
    raise ValueError('Output must stay inside task folder.')
out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report['summary']))
if report['summary']['fail']:
    for item in checks:
        if item['status'] == 'fail':
            print(item['name'], item['details'])
    raise SystemExit(1)
