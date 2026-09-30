"""Check delivered files, imported coverage, audio and actual presentation media.

Run from this folder: python3 -B tools/validate_delivery.py
Source deformation and native state audits remain separate production checks.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(name, passed, details=None):
    checks.append({'name': name, 'status': 'pass' if passed else 'fail',
                   'details': details})


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


required_files = [
    'README.md', 'source/Operative.blend', 'source/audio/dialogue.wav',
    'source/audio/dialogue.txt', 'source/audio/dialogue_alignment.json',
    'export/Operative.fbx', 'export/Operative_LOD1.fbx',
    'export/Operative_LOD2.fbx', 'unreal/MorphRig.uproject',
    'build/Linux/MorphRig.sh', 'docs/rig_usage.md',
    'docs/skeleton_and_sockets.json', 'docs/animation_manifest.json',
    'docs/animation_state_contract.md', 'docs/material_and_lod_report.json',
    'docs/THIRD_PARTY_ASSETS.csv', 'docs/build_and_import_instructions.md',
    'docs/known_issues.md', 'docs/quality_review.md', 'docs/performance_report.md',
    'tools/export_and_bake.py', 'tools/build_linux.sh',
    'verification/terrain_validation.json',
    'verification/qa_runtime_surface_validation.json',
    'verification/qa_runtime_horizontal_validation.json',
    'verification/qa_presentation_review.json',
    'verification/performance_validation.json',
    'presentation/turntable.mp4', 'presentation/motion_showcase.mp4',
    'presentation/face_performance.mp4',
]
missing = [name for name in required_files
           if not (ROOT / name).is_file() or (ROOT / name).stat().st_size == 0]
check('required_deliverables_exist_and_are_nonempty', not missing, missing)
required = {row['id']: row for row in csv.DictReader(
    (ROOT / 'required_animations.csv').open())}
manifest = json.loads((ROOT / 'docs/animation_manifest.json').read_text())
entries = manifest['animations']
check('manifest_matches_closed_inventory',
      len(entries) == 96 and {entry['id'] for entry in entries} == set(required))
check('runtime_manifest_matches_delivered_contract',
      sha256(ROOT / 'docs/animation_manifest.json') ==
      sha256(ROOT / 'unreal/Content/Data/animation_manifest.json'))
check('retained_runtime_notices_are_packaged',
      (ROOT / 'build/Linux/Licenses/unreal/ROBOTO_License.txt').is_file() and
      (ROOT / 'build/Linux/Licenses/unreal/NOTICES.txt').is_file())
bad_exports = [entry['id'] for entry in entries
               if not (ROOT / entry['export_file']).is_file()]
check('all_named_baked_exports_exist', not bad_exports, bad_exports)
bad_assets = [entry['id'] for entry in entries if not (
    ROOT / 'unreal/Content' /
    (entry['unreal_asset'].removeprefix('/Game/') + '.uasset')).is_file()]
check('all_named_unreal_assets_exist', not bad_assets, bad_assets)
for entry in entries:
    row = required[entry['id']]
    correct = (entry['form'] == row['form'] and
               entry['root_motion_policy'] == row['root_movement'] and
               entry['sample_rate'] == 30 and entry['fps'] == 30 and
               entry['frame_count'] == entry['frame_end'] - entry['frame_start'] + 1 and
               abs(entry['duration'] - (entry['frame_count'] - 1) / 30) < 1e-6)
    check('inventory_timing_' + entry['id'], correct)

imported = json.loads((ROOT / 'verification/unreal_import_report.json').read_text())
check('actual_import_is_complete', imported.get('complete') is True and
      not imported.get('missing') and not imported.get('errors') and
      {entry['id'] for entry in imported['animations']} == set(required))
check('imported_scale_and_single_ground_root',
      imported['import_scale'] == 1 and imported['root_bones'] == ['root'] and
      abs(imported['native_asset_inspection']['height_cm'] - 180) < .05)
source = json.loads((ROOT / 'verification/asset_validation.json').read_text())
check('finished_source_matches_validated_asset',
      source['source_sha256'] == sha256(ROOT / 'source/Operative.blend') and
      source['summary'].get('fail', 0) == 0 and source['summary'].get('pass', 0) >= 926)
binary_sha256 = sha256(ROOT / 'build/Linux/MorphRig/Binaries/Linux/MorphRig')
terrain_path = ROOT / 'verification/terrain_validation.json'
surface_path = ROOT / 'verification/qa_runtime_surface_validation.json'
if terrain_path.is_file() and surface_path.is_file():
    terrain = json.loads(terrain_path.read_text())
    surfaces = json.loads(surface_path.read_text())
    check('final_packaged_terrain_and_independent_review_pass',
          terrain['summary'].get('pass') is True and
          surfaces['summary'].get('pass') is True)
    check('terrain_review_matches_final_binary_and_replays',
          terrain.get('binary_sha256') == binary_sha256 and
          surfaces.get('terrain_metadata_binary_sha256') == binary_sha256 and
          surfaces.get('terrain_metadata_sha256') == sha256(terrain_path) and
          all(run['sha256'] == sha256(ROOT / 'verification' / name)
              for name, run in surfaces['runs'].items()) and
          set(surfaces['runs']) == {'terrain_contacts.csv', 'ramp_stop_contacts.csv'})
horizontal_path = ROOT / 'verification/qa_runtime_horizontal_validation.json'
if horizontal_path.is_file():
    horizontal = json.loads(horizontal_path.read_text())
    check('final_packaged_horizontal_contacts_pass',
          horizontal.get('summary', {}).get('pass') is True,
          horizontal.get('summary'))
    check('horizontal_review_matches_final_binary_and_replays',
          horizontal.get('delivered_binary_sha256') == binary_sha256 and
          horizontal.get('terrain_metadata_binary_sha256') == binary_sha256 and
          horizontal.get('terrain_metadata_sha256') == sha256(terrain_path) and
          horizontal.get('animation_manifest_sha256') == sha256(
              ROOT / 'docs/animation_manifest.json') and
          all(run['sha256'] == sha256(ROOT / 'verification' / name)
              for name, run in horizontal['runs'].items()) and
          set(horizontal['runs']) == {'terrain_contacts.csv', 'ramp_stop_contacts.csv'})

alignment = json.loads((ROOT / 'source/audio/dialogue_alignment.json').read_text())
wav = ROOT / 'source/audio/dialogue.wav'
with wave.open(str(wav)) as voice:
    duration = voice.getnframes() / voice.getframerate()
    audio_format = {'sample_rate': voice.getframerate(),
                    'channels': voice.getnchannels(),
                    'sample_width_bytes': voice.getsampwidth(),
                    'duration_seconds': duration}
check('original_voice_duration_and_alignment_identity',
      12 <= duration <= 18 and
      abs(duration - alignment['duration_seconds']) < 1 / 22050 and
      sha256(wav) == alignment['wav_sha256'], audio_format)

media = {}
ffprobe = shutil.which('ffprobe')
check('media_probe_available', ffprobe is not None)
if ffprobe:
    for kind, filename, expected_duration, audio in (
            ('turntable', 'turntable.mp4', 15, False),
            ('motion', 'motion_showcase.mp4', 110, True),
            ('face', 'face_performance.mp4', duration, True)):
        path = ROOT / 'presentation' / filename
        if not path.is_file():
            continue
        result = subprocess.run([ffprobe, '-v', 'error', '-show_streams',
                                 '-show_format', '-of', 'json', str(path)],
                                check=True, text=True, capture_output=True)
        probe = json.loads(result.stdout)
        video = next(stream for stream in probe['streams']
                     if stream['codec_type'] == 'video')
        has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
        media[kind] = {'width': video['width'], 'height': video['height'],
                       'fps': video['avg_frame_rate'],
                       'duration': float(probe['format']['duration']),
                       'has_audio': has_audio, 'sha256': sha256(path)}
        correct = (video['width'] == 1920 and video['height'] == 1080 and
                   video['avg_frame_rate'] == '30/1' and
                   abs(media[kind]['duration'] - expected_duration) < .1 and
                   has_audio == audio)
        check('actual_presentation_media_' + kind, correct, media[kind])
        provenance = json.loads((ROOT / 'verification/presentation' /
                                 (kind + '_capture.json')).read_text())
        check('presentation_capture_identity_' + kind,
              provenance['sha256'] == media[kind]['sha256'] and
              provenance['client'] == 'build/Linux/MorphRig.sh' and
              provenance['source_sha256'] == source['source_sha256'] and
              provenance['manifest_sha256'] == sha256(
                  ROOT / 'docs/animation_manifest.json') and
              provenance['voice_sha256'] == alignment['wav_sha256'] and
              provenance['client_binary_sha256'] == binary_sha256)

visual_path = ROOT / 'verification/qa_presentation_review.json'
if visual_path.is_file():
    visual = json.loads(visual_path.read_text())
    check('independent_final_presentation_review_passes',
          visual['summary'].get('pass') is True and
          visual['summary'].get('pending_quality_work') == [] and
          all(item['pass'] is True for item in visual['findings']))
    check('visual_review_matches_delivered_source_binary_and_media',
          visual.get('binary_sha256') == binary_sha256 and
          visual.get('source_sha256') == source['source_sha256'] and
          visual.get('manifest_sha256') == sha256(
              ROOT / 'docs/animation_manifest.json') and
          visual.get('voice_sha256') == alignment['wav_sha256'] and
          set(visual['videos']) == set(media) and
          all(item['sha256'] == media[kind]['sha256']
              for kind, item in visual['videos'].items()))
    check('inspected_frames_captures_and_trace_match_review_record',
          all(item['capture_metadata_sha256'] == sha256(ROOT / item['capture_metadata'])
              and item['sheet_sha256'] == sha256(ROOT / item['sheet'])
              and all(frame['sha256'] == sha256(ROOT / frame['file'])
                      for frame in item['full_resolution_frames_inspected'])
              for item in visual['videos'].values()) and
          visual['recorded_sequence']['report_sha256'] == sha256(
              ROOT / visual['recorded_sequence']['report']))

for name in ('sequence', 'inventory'):
    path = ROOT / 'verification' / (name + '_validation.json')
    check('runtime_audit_exists_' + name, path.is_file())
    if path.is_file():
        report = json.loads(path.read_text())
        check('runtime_audit_passes_' + name, report['summary'].get('fail', 0) == 0,
              report['summary'])
movie_audit = ROOT / 'verification/presentation/motion_sequence_validation.json'
check('recorded_final_sequence_audit_exists', movie_audit.is_file())
if movie_audit.is_file():
    movie_report = json.loads(movie_audit.read_text())
    check('recorded_final_sequence_audit_passes',
          movie_report['summary'].get('fail', 0) == 0 and
          movie_report['summary'].get('pass', 0) == 10,
          movie_report['summary'])
    check('recorded_sequence_audit_matches_current_capture_trace',
          movie_report.get('trace_sha256') == sha256(
              ROOT / 'verification/presentation/motion_state_events.jsonl') and
          movie_report.get('manifest_sha256') == sha256(
              ROOT / 'docs/animation_manifest.json'))
perf_validation_path = ROOT / 'verification/performance_validation.json'
if perf_validation_path.is_file():
    perf_validation = json.loads(perf_validation_path.read_text())
    check('independent_performance_report_matches_final_binary',
          perf_validation.get('binary_sha256') == binary_sha256 and
          perf_validation.get('summary', {}).get('pass') is True)
for count in (1, 10):
    path = ROOT / 'verification' / f'performance_{count}_instances.json'
    check(f'warmed_performance_sample_exists_{count}', path.is_file())
    if path.is_file():
        perf = json.loads(path.read_text())
        check(f'actual_1080p_warmed_sample_{count}',
              perf['instances'] == count and perf['width'] == 1920 and
              perf['height'] == 1080 and perf['warmup_seconds'] >= 5 and
              perf['sample_seconds'] >= 30 and perf['frames'] > 100 and
              not perf['generated_frames'], perf)
        check(f'performance_sample_matches_final_binary_{count}',
              perf.get('client_binary_sha256') == binary_sha256)
        csv_path = ROOT / 'verification' / f'performance_{count}_instances.csv'
        frame_rows = list(csv.DictReader(csv_path.open()))
        frame_times = [float(row['frame_ms']) for row in frame_rows]
        csv_mean = sum(frame_times) / len(frame_times)
        check(f'actual_frame_log_agrees_with_summary_{count}',
              len(frame_rows) == perf['frames'] and
              all(math.isfinite(value) and value > 0 for value in frame_times) and
              sum(frame_times) / 1000 >= 30 and
              abs(csv_mean - perf['mean_ms']) < .00002 and
              perf.get('csv_sha256') == sha256(csv_path),
              {'frames': len(frame_rows), 'actual_sample_seconds': sum(frame_times) / 1000,
               'actual_mean_ms': csv_mean})
        check(f'neutral_showcase_mean_meets_60fps_target_{count}',
              csv_mean <= 1000 / 60, csv_mean)

report = {'schema_version': 1, 'checks': checks, 'presentation': media,
          'source_sha256': sha256(ROOT / 'source/Operative.blend'),
          'manifest_sha256': sha256(ROOT / 'docs/animation_manifest.json'),
          'client_binary_sha256': binary_sha256,
          'summary': {status: sum(item['status'] == status for item in checks)
                      for status in ('pass', 'fail')}}
(ROOT / 'verification/delivery_validation.json').write_text(
    json.dumps(report, indent=2) + '\n')
print(json.dumps(report['summary']))
for item in checks:
    if item['status'] == 'fail':
        print(item['name'], item['details'])
raise SystemExit(1 if report['summary']['fail'] else 0)
