#!/usr/bin/env python3
"""Checks the delivered MorphRig folder against the numbers and the layout of the specification.

usage: python3 tools/verify_delivery.py [--blender]

Standard library only. One line per check (PASS / FAIL), exit code 1 when any check fails.
--blender additionally opens source/Operative.blend headless (needs `blender` on the PATH) and checks for missing files,
libraries and absolute private paths inside the file.
"""
import csv
import json
import os
import re
import struct
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def P(*a):
    return os.path.join(ROOT, *a)


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok)))
    print(('PASS  ' if ok else 'FAIL  ') + name + (' : ' + str(detail) if detail != '' else ''))


def load(*a):
    with open(P(*a), encoding='utf-8') as fh:
        return json.load(fh)


def png_size(path):
    with open(path, 'rb') as fh:
        head = fh.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


# ---------------------------------------------------------------- layout
LAYOUT = ['README.md', 'source/Operative.blend', 'source/textures', 'source/audio/dialogue.wav', 'source/audio/dialogue.txt',
          'source/audio/dialogue_alignment.json', 'source/generators', 'export/Operative.fbx', 'export/animations', 'export/textures',
          'unreal/MorphRig.uproject', 'unreal/Content', 'unreal/Source', 'unreal/Config', 'build/Linux',
          'docs/rig_usage.md', 'docs/skeleton_and_sockets.json', 'docs/animation_manifest.json', 'docs/animation_state_contract.md',
          'docs/material_and_lod_report.json', 'docs/THIRD_PARTY_ASSETS.csv', 'docs/build_and_import_instructions.md', 'docs/known_issues.md',
          'tools/export_and_bake.py', 'tools/build_linux.sh', 'presentation/turntable.mp4', 'presentation/motion_showcase.mp4',
          'presentation/face_performance.mp4']
missing = [p for p in LAYOUT if not os.path.exists(P(p))]
check('layout: every listed deliverable exists', not missing, ', '.join(missing) if missing else '%d entries' % len(LAYOUT))

# ---------------------------------------------------------------- inventory and manifest
rows = list(csv.DictReader(open(P('source', 'generators', 'required_animations.csv'), encoding='utf-8')))
man = load('docs', 'animation_manifest.json')
clips = {c['id']: c for c in man['clips']}
check('inventory: 96 entries, 85 motion and 11 static', len(rows) == 96 and len(clips) == 96 and sum(1 for c in clips.values() if c['static_pose']) == 11,
      '%d rows, %d clips, %d static' % (len(rows), len(clips), sum(1 for c in clips.values() if c['static_pose'])))
bad = []
for r in rows:
    c = clips.get(r['id'])
    if c is None:
        bad.append(r['id'] + ' missing')
        continue
    if c['form'] != r['form'] or c['root_motion'] != r['root_movement']:
        bad.append(r['id'] + ' form/root')
    if r['duration_seconds'] != 'pose':
        lo, hi = [float(x) for x in re.split(r'[-\u2013]', r['duration_seconds'])]
        if not lo - 1e-6 <= c['duration_s'] <= hi + 1e-6:
            bad.append('%s duration %.3f not in %s' % (r['id'], c['duration_s'], r['duration_seconds']))
    if c['loop'] != (r['form'] == 'loop'):
        bad.append(r['id'] + ' loop flag')
    if c['sample_rate'] != 30 or abs(c['duration_s'] - c['frames'] / 30.0) > 1e-6:
        bad.append(r['id'] + ' sample rate or duration')
    if not c['events']:
        bad.append(r['id'] + ' no events')
check('manifest: form, root policy, duration range, loop flag, 30 fps and events match the inventory', not bad, '; '.join(bad[:6]))
fbx_bad = []
for cid, c in clips.items():
    p = P(c['export_file'])
    if not os.path.isfile(p):
        fbx_bad.append(cid)
        continue
    with open(p, 'rb') as fh:
        if not fh.read(20).startswith(b'Kaydara FBX Binary'):
            fbx_bad.append(cid + ' (not a binary FBX)')
check('export: 96 baked clip FBX files exist', not fbx_bad, ', '.join(fbx_bad[:6]))
ue_bad = [cid for cid, c in clips.items() if not os.path.isfile(P('unreal', 'Content', c['unreal_asset'].replace('/Game/', '', 1) + '.uasset'))]
check('unreal: every manifest asset path exists as a .uasset in unreal/Content', not ue_bad, ', '.join(ue_bad[:6]))
dash = [c for c in clips.values() if c['id'].startswith('dash_')]
check('dashes: root motion of 200 cm (horizontal)', all(abs((c['root_motion_cm']['x'] ** 2 + c['root_motion_cm']['y'] ** 2) ** 0.5 - 200.0) < 1.0 for c in dash),
      ', '.join('%s %.1f' % (c['id'], (c['root_motion_cm']['x'] ** 2 + c['root_motion_cm']['y'] ** 2) ** 0.5) for c in dash))
speeds = {c['id']: c['nominal_speed_cm_s'] for c in clips.values()}
check('speeds: walk 150, run 400, sprint 650 cm/s', (speeds['walk_f'], speeds['run_f'], speeds['sprint_f']) == (150, 400, 650),
      'walk_f %s run_f %s sprint_f %s' % (speeds['walk_f'], speeds['run_f'], speeds['sprint_f']))

# ---------------------------------------------------------------- dialogue
with wave.open(P('source', 'audio', 'dialogue.wav')) as w:
    dur = w.getnframes() / float(w.getframerate())
check('dialogue: WAV lasts 12 to 18 s', 12.0 <= dur <= 18.0, '%.2f s' % dur)
al = load('source', 'audio', 'dialogue_alignment.json')
words = al['words']
mono = all(words[i]['start'] < words[i]['end'] <= words[i + 1]['end'] for i in range(len(words) - 1)) and words[-1]['end'] <= dur + 0.05
check('dialogue: alignment lists %d words with increasing times inside the audio' % len(words), mono and len(words) > 10)
txt = open(P('source', 'audio', 'dialogue.txt'), encoding='utf-8').read().strip()
check('dialogue: transcript equals the alignment transcript', ' '.join(txt.split()) == ' '.join(al['transcript'].split()))
check('dialogue: clip length follows the audio', abs(clips['dialogue']['duration_s'] - dur) < 0.2, '%.2f s clip, %.2f s audio' % (clips['dialogue']['duration_s'], dur))

# ---------------------------------------------------------------- geometry, materials, textures, skeleton
rep = load('docs', 'material_and_lod_report.json')
lods = rep['lods']
check('LODs within budget', all(lods[k]['triangles'] <= lods[k]['budget_triangles'] for k in ('LOD0', 'LOD1', 'LOD2')),
      ', '.join('%s %d/%d' % (k, lods[k]['triangles'], lods[k]['budget_triangles']) for k in ('LOD0', 'LOD1', 'LOD2')))
check('at most 8 material slots for character and props', rep['material_slots']['total_unique_slots'] <= 8, rep['material_slots']['total_unique_slots'])
pngs = sorted(f for f in os.listdir(P('source', 'textures')) if f.endswith('.png'))
big = [f for f in pngs if max(png_size(P('source', 'textures', f)) or (0, 0)) > 4096]
check('textures: %d PNG files, none above 4096' % len(pngs), pngs and not big, ', '.join(big))
sk = load('docs', 'skeleton_and_sockets.json')
roots = [b['name'] for b in sk['bones'] if b['parent'] is None]
check('skeleton: exactly one root', roots == ['root'] and sk['bone_count'] == len(sk['bones']), '%d bones, roots %s' % (len(sk['bones']), roots))
names = {b['name'] for b in sk['bones']}
check('skeleton: every parent exists', all(b['parent'] in names for b in sk['bones'] if b['parent'] is not None))
need = ['hand_grip_l', 'hand_grip_r', 'emitter_muzzle', 'blade_base', 'blade_tip']
sock = {s['name'] for s in sk['sockets']}
check('sockets: hands, muzzle, blade base and tip, effect anchors', all(n in sock for n in need) and sum(1 for n in sock if n.startswith('fx_')) >= 2, '%d sockets' % len(sock))
check('skin: at most 8 influences per vertex, height 180 cm', rep['skeleton']['max_influences_per_vertex'] <= 8 and abs(rep['height_cm'] - 180.0) < 0.5 and rep['height_cm_with_hair'] < 181.5,
      '%d influences, %.2f cm to the skull, %.1f cm with the hair' % (rep['skeleton']['max_influences_per_vertex'], rep['height_cm'], rep['height_cm_with_hair']))

# ---------------------------------------------------------------- hygiene
PRIVATE = re.compile('/ho' + 'me/[a-z]+/|/t' + 'mp/claude')          # built from pieces so this file does not match itself
leaks = []
skip_dirs = {'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache', 'build', 'voice', '.git'}
text_ext = ('.md', '.json', '.py', '.sh', '.csv', '.txt', '.cpp', '.h', '.cs', '.ini', '.uproject')
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in skip_dirs and not os.path.islink(os.path.join(base, d))]
    for f in files:
        if f.endswith(text_ext):
            path = os.path.join(base, f)
            try:
                s = open(path, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            if PRIVATE.search(s):
                leaks.append(os.path.relpath(path, ROOT))
check('hygiene: no absolute private-machine paths in text files', not leaks, ', '.join(leaks[:6]))
junk = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ('Binaries', 'Intermediate', 'Saved', 'DerivedDataCache') and not os.path.islink(os.path.join(base, d))]
    junk += [os.path.relpath(os.path.join(base, d), ROOT) for d in dirs if d in ('__pycache__', '_work', '_pilot', 'capture')]
    junk += [os.path.relpath(os.path.join(base, f), ROOT) for f in files if f.endswith(('.pyc', '.blend1', '.tmp'))]
check('hygiene: no cache folders or temporary files in the tree', not junk, ', '.join(junk[:6]))

# ---------------------------------------------------------------- videos
def probe(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,avg_frame_rate:format=duration', '-of', 'json', path],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    except (OSError, subprocess.CalledProcessError):
        return None


for name in ('turntable', 'motion_showcase', 'face_performance'):
    path = P('presentation', name + '.mp4')
    info = probe(path) if os.path.isfile(path) else None
    if info is None:
        check('video %s.mp4 readable (ffprobe)' % name, False)
        continue
    vs = [s for s in info['streams'] if s['codec_type'] == 'video']
    au = [s for s in info['streams'] if s['codec_type'] == 'audio']
    ok = bool(vs) and float(info['format']['duration']) > 5.0 and (bool(au) if name == 'face_performance' else True)
    check('video %s.mp4' % name, ok, '%sx%s, %s fps, %.1f s%s' % (vs[0]['width'], vs[0]['height'], vs[0]['avg_frame_rate'], float(info['format']['duration']), ', audio' if au else ''))

# ---------------------------------------------------------------- optional Blender check
if '--blender' in sys.argv:
    code = ("import bpy,os;print('MR_MISSING',[i.filepath for i in bpy.data.images if i.filepath and not os.path.exists(bpy.path.abspath(i.filepath))]);"
            "print('MR_LIBS',[l.filepath for l in bpy.data.libraries]);print('MR_ACTIONS',len([a for a in bpy.data.actions if a.name.startswith('A_')]))")
    out = subprocess.run(['blender', '-b', P('source', 'Operative.blend'), '--python-expr', code], capture_output=True, text=True).stdout
    miss = re.search(r'MR_MISSING (\[.*\])', out)
    libs = re.search(r'MR_LIBS (\[.*\])', out)
    acts = re.search(r'MR_ACTIONS (\d+)', out)
    check('blend: no missing texture files', miss is not None and miss.group(1) == '[]', miss.group(1) if miss else 'Blender did not run')
    check('blend: no linked libraries', libs is not None and libs.group(1) == '[]')
    check('blend: 96 clip actions plus 7 pose tests (A_*)', acts is not None and int(acts.group(1)) == 103, acts.group(1) if acts else '')

failed = [n for n, ok in RESULTS if not ok]
print('\n%d checks, %d failed' % (len(RESULTS), len(failed)))
sys.exit(1 if failed else 0)
