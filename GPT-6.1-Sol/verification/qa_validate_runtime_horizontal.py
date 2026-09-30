"""Review continuous planted-foot motion in the finalized packaged terrain CSVs.

Run from the delivery folder with python3 verification/qa_validate_runtime_horizontal.py.
The script does not launch the client or alter any production asset.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STANCE_THRESHOLD = .999
SUPPORT_DRIFT_CM = 1.0


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(row, side):
    return tuple(float(row[side+'_foot_'+axis]) for axis in 'xyz')


def sample(row, side):
    result = {
        't': float(row['t']),
        'foot_world_xyz_cm': point(row, side),
        'actor_world_xyz_cm': tuple(float(row['actor_'+a]) for a in 'xyz'),
        'controller_speed_cm_s': float(row['speed']),
        'stance_weight': float(row[side+'_stance_weight']),
        'surface_clearance_cm': float(row[side+'_boot_clearance_min_cm']),
    }
    for key in ('body_id', 'base_id', 'body_clip', 'base_clip', 'gait_phase', 'body_t'):
        if key in row:
            result[key] = row[key]
    return result


def measure_group(rows, side):
    positions = [point(row, side) for row in rows]
    diameter, ai, bi = max(
        (math.dist(a[:2], b[:2]), i, j)
        for i, a in enumerate(positions)
        for j, b in enumerate(positions)
    )
    adjacent, ji = max(
        ((math.dist(a[:2], b[:2]), i)
         for i, (a, b) in enumerate(zip(positions, positions[1:]))),
        default=(0.0, 0),
    )
    result = {
        'phase': rows[0]['phase'],
        'side': side,
        'sample_count': len(rows),
        'start_seconds': float(rows[0]['t']),
        'end_seconds': float(rows[-1]['t']),
        'duration_seconds': float(rows[-1]['t'])-float(rows[0]['t']),
        'horizontal_diameter_cm': diameter,
        'endpoint_horizontal_displacement_cm': math.dist(positions[0][:2], positions[-1][:2]),
        'maximum_adjacent_horizontal_displacement_cm': adjacent,
        'maximum_sample_interval_seconds': max(
            (float(b['t'])-float(a['t']) for a, b in zip(rows, rows[1:])), default=0.0),
        'minimum_stance_weight': min(float(r[side+'_stance_weight']) for r in rows),
        'surface_clearance_range_cm': [min(float(r[side+'_boot_clearance_min_cm']) for r in rows),
                                       max(float(r[side+'_boot_clearance_min_cm']) for r in rows)],
        'includes_controller_movement': any(float(r['speed']) >= 12 for r in rows),
        'includes_stationary_controller': any(float(r['speed']) < .5 for r in rows),
        'diameter_samples': [sample(rows[ai], side), sample(rows[bi], side)],
        'start_sample': sample(rows[0], side),
        'end_sample': sample(rows[-1], side),
        'pass': diameter <= SUPPORT_DRIFT_CM,
    }
    if len(rows) > 1:
        result['largest_adjacent_jump_samples'] = [sample(rows[ji], side), sample(rows[ji+1], side)]
    return result


def authored_support(row, side, entries):
    if float(row[side+'_stance_weight']) < STANCE_THRESHOLD:
        return False
    base = row.get('base_id', '')
    if base.startswith('idle_'):
        return True
    if not base.startswith(('walk_', 'run_', 'sprint_')) or 'gait_phase' not in row:
        return False
    entry = entries[base]
    letter = 'L' if side == 'left' else 'R'
    events = {e['name']: e['time'] for e in entry['events']}
    duration = entry['duration_seconds']
    contact = events['foot_contact.'+letter]/duration
    release = events['foot_release.'+letter]/duration
    relative = (float(row['gait_phase'])-contact) % 1
    support_length = (release-contact) % 1
    # Marker frames are quantized to the authored 30-Hz source. Exclude one
    # source frame at either end to separate interpolation and toe-off roll.
    margin = 1/(entry['sample_rate']*duration)
    return margin <= relative <= support_length-margin


def contact_crossed(previous, row, side, entries):
    """A skipped swing can land between CSV samples; that is a new contact."""
    base = row.get('base_id', '')
    if not base.startswith(('walk_', 'run_', 'sprint_')):
        return False
    if 'gait_phase' not in previous or 'gait_phase' not in row:
        return False
    letter = 'L' if side == 'left' else 'R'
    entry = entries[base]
    contact = next(e['time'] for e in entry['events']
                   if e['name'] == 'foot_contact.'+letter)/entry['duration_seconds']
    old_phase, new_phase = float(previous['gait_phase']) % 1, float(row['gait_phase']) % 1
    advance = (new_phase-old_phase) % 1
    until_contact = (contact-old_phase) % 1
    return 0 < until_contact <= advance


def support_groups(rows, side, predicate, new_contact=None):
    groups, current = [], []
    for row in rows:
        support = predicate(row, side)
        if current and (not support or row['phase'] != current[-1]['phase']
                        or (new_contact and new_contact(current[-1], row, side))):
            groups.append(measure_group(current, side))
            current = []
        if support:
            current.append(row)
    if current:
        groups.append(measure_group(current, side))
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', default='verification/qa_runtime_horizontal_validation.json')
    args = parser.parse_args()
    metadata_path = ROOT/'verification/terrain_validation.json'
    metadata = json.loads(metadata_path.read_text())
    manifest_path = ROOT/'docs/animation_manifest.json'
    entries = {e['id']: e for e in json.loads(manifest_path.read_text())['animations']}
    binary = ROOT/'build/Linux/MorphRig/Binaries/Linux/MorphRig'
    result = {
        'schema_version': 3,
        'method': 'Finalized world ankle support is classified by actual base clip, evaluated phase and authored contact/release events, together with full stance. A contact event crossed between CSV samples starts a new support segment, including a swing that was not sampled. Idle recovery uses full stance. Height-only groups remain separate diagnostics, and long frame intervals are retained.',
        'units': 'centimetres',
        'stance_threshold': STANCE_THRESHOLD,
        'contact_boundary_exclusion_authored_frames': 1,
        'support_drift_review_tolerance_cm': SUPPORT_DRIFT_CM,
        'criterion_note': 'One centimetre is the review precision for straight, flat-sole planted support. SPEC requires absence of visible large foot skating without assigning a numeric lateral limit. Raw diameters and adjacent jumps are retained.',
        'limitation': 'These are sampled straight terrain paths. Ankle-reference motion is appropriate for these flat-sole support intervals; the metric is not applied to heel/toe rolling or pivoting turns.',
        'evaluated_utc': datetime.datetime.now(datetime.UTC).isoformat(),
        'terrain_metadata_sha256': digest(metadata_path),
        'animation_manifest_sha256': digest(manifest_path),
        'terrain_metadata_binary_sha256': metadata.get('binary_sha256'),
        'delivered_binary_sha256': digest(binary),
        'runs': {},
    }
    for filename in ('terrain_contacts.csv', 'ramp_stop_contacts.csv'):
        path = ROOT/'verification'/filename
        rows = list(csv.DictReader(path.open()))
        assert rows, f'No finalized terrain samples: {path}'
        assert all(float(b['t']) > float(a['t']) for a, b in zip(rows, rows[1:])), f'Unordered samples: {path}'
        required = ['t', 'speed'] + ['actor_'+a for a in 'xyz']
        for side in ('left', 'right'):
            required += [side+'_foot_'+a for a in 'xyz']
            required += [side+'_stance_weight', side+'_boot_clearance_min_cm']
        assert all(math.isfinite(float(r[k])) for r in rows for k in required), f'Invalid numeric samples: {path}'
        height_groups = [g for side in ('left', 'right') for g in support_groups(
            rows, side, lambda r, s: float(r[s+'_stance_weight']) >= STANCE_THRESHOLD)]
        for group in height_groups:
            group.pop('pass')
        groups = [g for side in ('left', 'right') for g in support_groups(
            rows, side, lambda r, s: authored_support(r, s, entries),
            lambda prev, row, s: contact_crossed(prev, row, s, entries))]
        measurable = [g for g in groups if g['sample_count'] > 1]
        phase_fields_present = all('base_id' in r and 'gait_phase' in r for r in rows)
        if phase_fields_present:
            assert measurable, f'No consecutive authored support: {path}'
        run = {
            'rows': len(rows),
            'sha256': digest(path),
            'support_groups': groups,
            'height_only_diagnostic_groups': height_groups,
            'height_only_note': 'These groups can combine distinct contacts when the intervening swing falls between CSV samples, and can include touchdown/toe-off. Their diameters are raw diagnostics; they do not classify planted-support failures.',
            'height_only_maximum_horizontal_diameter_cm': max(g['horizontal_diameter_cm'] for g in height_groups),
            'authored_phase_fields_present': phase_fields_present,
            'consecutive_support_groups': len(measurable),
            'single_sample_support_groups': len(groups)-len(measurable),
            'maximum_horizontal_support_diameter_cm': max((g['horizontal_diameter_cm'] for g in measurable), default=None),
            'maximum_adjacent_support_displacement_cm': max((g['maximum_adjacent_horizontal_displacement_cm'] for g in measurable), default=None),
            'failures': [{'phase': g['phase'], 'side': g['side'], 'start_seconds': g['start_seconds'],
                          'end_seconds': g['end_seconds'], 'horizontal_diameter_cm': g['horizontal_diameter_cm']}
                         for g in measurable if not g['pass']],
        }
        run['coverage'] = {
            phase: {side: {
                'moving_support_groups': sum(g['includes_controller_movement'] for g in measurable if g['phase']==phase and g['side']==side),
                'stationary_support_groups': sum(g['includes_stationary_controller'] for g in measurable if g['phase']==phase and g['side']==side),
            } for side in ('left', 'right')} for phase in ('ramp', 'steps')
        }
        run['pass'] = phase_fields_present and not run['failures'] and all(
            side['moving_support_groups'] and side['stationary_support_groups']
            for phase in run['coverage'].values() for side in phase.values())
        result['runs'][filename] = run
    result['binary_identity_matches'] = result['delivered_binary_sha256'] == result['terrain_metadata_binary_sha256']
    result['summary'] = {'pass': result['binary_identity_matches'] and all(r['pass'] for r in result['runs'].values())}
    report = (ROOT/args.report).resolve()
    assert report.is_relative_to(ROOT), 'Reports must stay inside the delivery folder'
    report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({name: {'diameter_cm': run['maximum_horizontal_support_diameter_cm'],
                            'failures': len(run['failures'])}
                      for name, run in result['runs'].items()}))
    print(json.dumps(result['summary']))
    if not result['summary']['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
