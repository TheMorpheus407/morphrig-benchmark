"""Independently review actual imported boot surfaces in packaged replays.

Run from this folder with python3 verification/qa_validate_runtime_surfaces.py.
Uses finalized-bone CSVs produced by the delivered client. Never launches it.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESSURE_CM = 1.0
STANDING_GAP_CM = 1.0


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    bindings_path = ROOT/'unreal/Content/Data/boot_surface_bindings.json'
    bindings = json.loads(bindings_path.read_text())
    out = {
        'schema_version': 2,
        'method': 'Independent review of finalized imported LOD0 boot/toe vertex skinning in both packaged terrain replays; every captured row is inspected regardless of IK weight.',
        'units': 'centimetres',
        'contact_pressure_tolerance_cm': PRESSURE_CM,
        'planted_surface_gap_tolerance_cm': STANDING_GAP_CM,
        'acceptance_note': 'Raw depths are retained. Height weight1 can include a safety-raised swing foot. Planted support is identified by the separate stance weight.',
        'boot_bindings_sha256': digest(bindings_path),
        'imported_boot_vertex_samples': len(bindings['vertices']),
        'binding_weight_max_sum_error': max(abs(sum(v['weights'])-1) for v in bindings['vertices']),
        'evaluated_utc': datetime.datetime.now(datetime.UTC).isoformat(),
        'runs': {},
    }
    metadata_path = ROOT/'verification/terrain_validation.json'
    if metadata_path.exists():
        out['terrain_metadata_binary_sha256'] = json.loads(metadata_path.read_text()).get('binary_sha256')
        out['terrain_metadata_sha256'] = digest(metadata_path)
    binary = ROOT/'build/Linux/MorphRig/Binaries/Linux/MorphRig'
    out['delivered_binary_sha256'] = digest(binary)
    out['binary_identity_matches'] = out['delivered_binary_sha256'] == out.get('terrain_metadata_binary_sha256')
    for name in ['terrain_contacts.csv', 'ramp_stop_contacts.csv']:
        path = ROOT/'verification'/name
        rows = list(csv.DictReader(path.open()))
        assert rows, f'No terrain rows: {path}'
        assert all(math.isfinite(float(value)) for row in rows for key, value in row.items()
                   if key not in {'phase', 'body_id', 'base_id'}), f'Non-finite values: {path}'
        run = {'rows': len(rows), 'sha256': digest(path), 'phases': {}}
        for phase in ['ramp', 'steps']:
            rr = [x for x in rows if x['phase'] == phase]
            assert rr, f'Missing {phase}: {path}'
            phase_result = {}
            for side in ['left', 'right']:
                clearance = side+'_boot_clearance_min_cm'
                worst = min(rr, key=lambda x: float(x[clearance]))
                height_support = [x for x in rr if float(x[side+'_ik_weight']) >= .999]
                stance_key = side+'_stance_weight'
                stance_support = [x for x in rr if stance_key in x and float(x[stance_key]) >= .999]
                planted_gap = max([float(x[clearance]) for x in stance_support], default=None)
                phase_result[side] = {
                    'minimum_surface_clearance_cm': float(worst[clearance]),
                    'worst_time_seconds': float(worst['t']),
                    'inside_tread_vertex_count': sum(int(x[side+'_boot_inside_step_vertices']) for x in rr),
                    'maximum_solid_penetration_cm': max(float(x[side+'_boot_step_penetration_max_cm']) for x in rr),
                    'fully_height_weighted_samples': len(height_support),
                    'maximum_fully_height_weighted_surface_gap_cm': max([float(x[clearance]) for x in height_support], default=None),
                    'fully_stance_weighted_samples': len(stance_support),
                    'maximum_planted_surface_gap_cm': planted_gap,
                    'minimum_planted_surface_clearance_cm': min([float(x[clearance]) for x in stance_support], default=None),
                }
                phase_result[side]['pass'] = (
                    phase_result[side]['minimum_surface_clearance_cm'] >= -PRESSURE_CM
                    and phase_result[side]['maximum_solid_penetration_cm'] <= PRESSURE_CM
                    and planted_gap is not None and planted_gap <= STANDING_GAP_CM
                )
            run['phases'][phase] = phase_result
        run['pass'] = all(side['pass'] for phase in run['phases'].values() for side in phase.values())
        out['runs'][name] = run
    out['summary'] = {'pass': out['binary_identity_matches']
                      and out['binding_weight_max_sum_error'] < 1e-5
                      and all(x['pass'] for x in out['runs'].values())}
    report = ROOT/'verification/qa_runtime_surface_validation.json'
    report.write_text(json.dumps(out, indent=2)+'\n')
    print(json.dumps(out['summary']))
    if not out['summary']['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
