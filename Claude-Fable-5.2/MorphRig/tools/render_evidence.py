"""Renders the inspection images in docs/images from source/Operative.blend (Eevee, headless).

    blender -b source/Operative.blend -P tools/render_evidence.py [-- name ...]

Images: design_turnaround, face_presets, visemes, eye_look, deformation_poses, lods, team_variants, topdown_120px,
uv_layouts, clip_frames, dialogue_frames. Nothing in the .blend is saved.
"""
import math
import os
import subprocess
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(ROOT, 'source', 'generators'))
from mr import rig as rigmod, animio, materials, texraster                 # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'images')
os.makedirs(OUT, exist_ok=True)
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
want = lambda n: (not argv) or (n in argv)
sc = bpy.context.scene
rg = bpy.data.objects['RIG_Operative']
sk = bpy.data.objects['SKEL_Operative']
lods = [bpy.data.objects['Operative_LOD%d' % i] for i in range(3)]

# ---- neutral studio
for o in list(sc.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o)


def sun(name, direction, strength, color=(1, 1, 1), angle=0.25):
    d = bpy.data.lights.new(name, 'SUN')
    d.energy, d.color, d.angle = strength, color, angle
    o = bpy.data.objects.new(name, d)
    sc.collection.objects.link(o)
    o.rotation_euler = Vector(direction).normalized().to_track_quat('-Z', 'Y').to_euler()


sun('key', (-0.5, 0.8, -0.75), 2.6, (1.0, 0.97, 0.94))
sun('fill', (0.9, 0.5, -0.3), 0.9, (0.85, 0.92, 1.0), 0.6)
sun('rim', (0.3, -0.9, -0.5), 1.8, (0.8, 0.9, 1.0))
w = sc.world or bpy.data.worlds.new('World')
sc.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get('Background')
bg.inputs[0].default_value = (0.20, 0.22, 0.26, 1)
bg.inputs[1].default_value = 0.9
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        pass
sc.view_settings.view_transform = 'AgX'
cam = bpy.data.objects.new('EvidenceCam', bpy.data.cameras.new('EvidenceCam'))
sc.collection.objects.link(cam)
sc.camera = cam
gm = bpy.data.meshes.new('EvidenceGround')
gm.from_pydata([(-8, -8, 0), (8, -8, 0), (8, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
ground = bpy.data.objects.new('EvidenceGround', gm)
sc.collection.objects.link(ground)
gmat = bpy.data.materials.new('EvidenceGround')
gmat.use_nodes = True
gmat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.22, 0.23, 0.25, 1)
gmat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.85
gm.materials.append(gmat)
rg.hide_render = True
sk.hide_render = True
for o in sc.objects:
    if o.name.startswith('WGT') or o.name == 'MorphProxy':
        o.hide_render = True


def shot(path, eye, target, lens=70, res=(520, 760), ortho=None):
    cam.location = eye
    cam.rotation_euler = (Vector(target) - Vector(eye)).normalized().to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        cam.data.ortho_scale = ortho
    cam.data.lens, cam.data.clip_start, cam.data.clip_end = lens, 0.02, 80
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def sheet(paths, out, cols=None, scale=None):
    cols = cols or len(paths)
    rows = int(math.ceil(len(paths) / float(cols)))
    args = ['ffmpeg', '-y', '-loglevel', 'error']
    for p in paths:
        args += ['-i', p]
    layout = '|'.join('%s_%s' % ('+'.join(['w0'] * c) if c else '0', '+'.join(['h0'] * r) if r else '0')
                      for r in range(rows) for c in range(cols))
    layout = '|'.join(layout.split('|')[:len(paths)])
    flt = ''.join('[%d:v]' % i for i in range(len(paths)))
    flt += ('xstack=inputs=%d:layout=%s:fill=black' % (len(paths), layout)) if len(paths) > 1 else 'null'
    if scale:
        flt += ',scale=iw*%d:ih*%d:flags=neighbor' % (scale, scale)
    subprocess.run(args + ['-filter_complex', flt, '-frames:v', '1', '-update', '1', out], check=True)
    for p in paths:
        if p != out:
            os.remove(p)


def show(i):
    for k, m in enumerate(lods):
        m.hide_render = (k != i)
        m.hide_viewport = (k != i)


def rest():
    if rg.animation_data:
        rg.animation_data.action = None
    rigmod.reset_pose(rg)
    bpy.context.view_layer.update()


def tmp(name):
    return os.path.join(OUT, '_' + name + '.png')


show(0)
rest()
if want('design_turnaround'):
    ps = [shot(tmp('t%d' % i), eye, (0, 0, 0.92), res=(560, 900)) for i, eye in enumerate(
        [(0.0, -5.4, 1.25), (3.9, -3.7, 1.35), (5.4, 0.0, 1.25), (0.0, 5.4, 1.35), (-3.9, -3.7, 1.35)])]
    sheet(ps, os.path.join(OUT, 'design_turnaround.png'))
    ps = [shot(tmp('c0'), (0.22, -1.25, 1.70), (0, -0.02, 1.665), lens=110, res=(700, 700)),
          shot(tmp('c1'), (0.95, -0.95, 1.72), (0, -0.02, 1.665), lens=110, res=(700, 700)),
          shot(tmp('c2'), (0.6, -2.0, 1.45), (0, 0, 1.25), lens=85, res=(700, 700)),
          shot(tmp('c3'), (-1.2, -1.3, 1.35), (-0.42, -0.02, 1.15), lens=110, res=(700, 700)),
          shot(tmp('c4'), (-0.5, 2.0, 1.75), (0, 0, 1.35), lens=85, res=(700, 700))]
    sheet(ps, os.path.join(OUT, 'design_closeups.png'))
face = rg.pose.bones['face']


def face_set(d):
    rest()
    for k, v in d.items():
        face[k] = float(v)
    rg.update_tag()
    bpy.context.view_layer.update()


FACE_EYE, FACE_TGT = (0.20, -1.2, 1.68), (0, -0.03, 1.655)
if want('face_presets'):
    sets = [('neutral', {}), ('joy', {'expr_joy': 1}), ('anger', {'expr_anger': 1}), ('concern', {'expr_concern': 1}),
            ('surprise', {'expr_surprise': 1}), ('pain', {'expr_pain': 1}), ('focus', {'expr_focus': 1}),
            ('wink_left_smirk_right', {'blink_l': 1, 'smile_r': 0.9, 'brow_outer_up_r': 0.8}),
            ('brow_left_frown_right', {'brow_inner_up_l': 1, 'brow_down_r': 0.9, 'frown_r': 0.8, 'squint_r': 0.6}),
            ('closed_lips', {'lip_press': 0.4, 'mouth_close': 0.3}), ('cheek_puff', {'cheek_puff_l': 1, 'cheek_puff_r': 1}),
            ('jaw_open_tongue', {'jaw_open': 1.0, 'tongue_out': 0.7, 'tongue_up': 0.5})]
    ps = []
    for name, d in sets:
        face_set(d)
        ps.append(shot(tmp('f_' + name), FACE_EYE, FACE_TGT, lens=125, res=(420, 460)))
    sheet(ps, os.path.join(OUT, 'face_presets.png'), cols=6)
if want('visemes'):
    ps = []
    for v in ('PP', 'FF', 'TH', 'DD', 'KK', 'CH', 'SS', 'RR', 'AA', 'EH', 'EE', 'OH', 'OO'):
        face_set({'vis_' + v: 1.0})
        ps.append(shot(tmp('v_' + v), (0.14, -0.95, 1.63), (0, -0.05, 1.615), lens=150, res=(360, 300)))
    sheet(ps, os.path.join(OUT, 'visemes.png'), cols=7)
if want('eye_look'):
    ps = []
    for name, tgt in (('up', (0, -1.0, 2.35)), ('down', (0, -1.0, 1.05)), ('left', (0.9, -1.0, 1.67)), ('right', (-0.9, -1.0, 1.67)),
                      ('cross', None), ('blink_l', None), ('blink_r', None)):
        rest()
        if tgt is not None:
            M = rg.pose.bones['look_target'].matrix.copy()
            M.translation = Vector(tgt)
            rg.pose.bones['look_target'].matrix = M
        elif name == 'cross':
            for s, dx in (('l', -0.10), ('r', 0.10)):
                rg.pose.bones['eye_target_' + s].location.x += dx * (1 if s == 'l' else 1)
            rg.pose.bones['look_target'].location = (0, 0.75, 0)
        else:
            face[name] = 1.0
        rg.update_tag()
        bpy.context.view_layer.update()
        ps.append(shot(tmp('e_' + name), (0.0, -1.0, 1.675), (0, -0.03, 1.668), lens=200, res=(420, 250)))
    sheet(ps, os.path.join(OUT, 'eye_look.png'), cols=4)
if want('deformation_poses'):
    ps = []
    names = [a.name for a in bpy.data.actions if a.name.startswith('DEMO_')]
    order = ['overhead_reach', 'deep_squat', 'crossed_arm_reach', 'torso_twist', 'kneeling', 'hand_support', 'closed_grip']
    for n in order:
        if 'DEMO_' + n not in names:
            continue
        rest()
        rg.pose.apply_pose_from_action(bpy.data.actions['DEMO_' + n], evaluation_time=0.0)
        bpy.context.view_layer.update()
        hz = rg.pose.bones['spine_03'].matrix.translation.z
        ps.append(shot(tmp('p_%s_f' % n), (1.6, -3.6, hz + 0.25), (0, 0, max(hz - 0.28, 0.45)), lens=60, res=(460, 600)))
        ps.append(shot(tmp('p_%s_b' % n), (-1.9, 3.4, hz + 0.3), (0, 0, max(hz - 0.28, 0.45)), lens=60, res=(460, 600)))
    sheet(ps, os.path.join(OUT, 'deformation_poses.png'), cols=len(ps) // 2)
if want('lods'):
    rest()
    ps = []
    for i in range(3):
        show(i)
        ps.append(shot(tmp('l%d' % i), (0.5, -5.2, 1.25), (0, 0, 0.92), res=(520, 800)))
        ps.append(shot(tmp('lf%d' % i), (0.6, -2.0, 1.45), (0, 0, 1.25), lens=85, res=(520, 800)))
    sheet(ps, os.path.join(OUT, 'lods.png'))
    show(0)
if want('team_variants'):
    rest()
    ps = []
    for team in ('A', 'B'):
        materials.set_team(lods[0], team)
        bpy.context.view_layer.update()
        ps.append(shot(tmp('tv_%s_f' % team), (0.6, -2.0, 1.45), (0, 0, 1.25), lens=85, res=(640, 640)))
        ps.append(shot(tmp('tv_%s_b' % team), (-0.5, 2.0, 1.75), (0, 0, 1.35), lens=85, res=(640, 640)))
    sheet(ps, os.path.join(OUT, 'team_variants.png'))
    # top-down game camera (55 degrees), the 1.8 m body covers about 120 px; enlarged 4x without filtering
    ps = []
    for team in ('A', 'B'):
        materials.set_team(lods[0], team)
        bpy.context.view_layer.update()
        d = Vector((0.0, -0.57, 0.82)).normalized()
        ps.append(shot(tmp('td_' + team), tuple(Vector((0, 0, 0.9)) + d * 12.0), (0, 0, 0.9), res=(200, 200), ortho=3.0))
    sheet(ps, os.path.join(OUT, 'topdown_120px.png'), scale=4)
    materials.set_team(lods[0], 'A')
if want('clip_frames'):
    ps = []
    for cid, f in (('idle_combat', 0), ('run_f', 5), ('ranged_fire', 3), ('melee_1', 10), ('reload', 31), ('deploy', 27), ('cast_ground', 18),
                   ('channel_loop', 10), ('charge_hold', 10), ('dash_f', 6), ('knockdown_back', 20), ('getup_front', 24), ('sleep_loop', 0),
                   ('death_back', 60), ('victory', 17), ('dialogue', 165)):
        if cid not in bpy.data.actions:
            continue
        rest()
        animio.assign(rg, bpy.data.actions[cid])
        sc.frame_set(f)
        bpy.context.view_layer.update()
        r = rg.pose.bones['root'].matrix.translation
        ps.append(shot(tmp('k_%s' % cid), (2.4 + r.x, -4.4 + r.y, 1.5), (r.x, r.y, 0.9), lens=60, res=(380, 470)))
    sheet(ps, os.path.join(OUT, 'clip_frames.png'), cols=8)
    rest()
if want('dialogue_frames') and 'dialogue' in bpy.data.actions:
    import json
    al = json.load(open(os.path.join(ROOT, 'source', 'audio', 'dialogue_alignment.json'), encoding='utf-8'))
    f0, fps = al['clip']['audio_start_frame'], al['clip']['fps']
    rest()
    animio.assign(rg, bpy.data.actions['dialogue'])
    # acting beats (bust view), pinned to words of the line
    beats = [('Operative', 0.5), ('relay', 0.6), ('wide', 0.6), ('Hold', 0.5), ('positions', 0.6), ('thirty', 0.3), ('stabilize', 0.5), ('myself', 1.6),
             ('There', 0.9), ('Signal', 0.5), ('Push', 0.6), ('thank', 0.6), ('trusting', 0.5), ('me', 0.9)]
    ps = []
    used = {}
    for word, frac in beats:
        hits = [w for w in al['words'] if w['word'] == word]
        w = hits[min(used.get(word, 0), len(hits) - 1)] if word != 'me' else hits[-1]
        f = int(round(f0 + (w['start'] + (w['end'] - w['start']) * frac) * fps))
        sc.frame_set(f)
        bpy.context.view_layer.update()
        ps.append(shot(tmp('d_%03d' % f), (0.35, -2.25, 1.50), (0.0, -0.05, 1.42), lens=70, res=(400, 400)))
    sheet(ps, os.path.join(OUT, 'dialogue_acting.png'), cols=7)
    # lip shapes at phoneme centres (face view)
    picks = [('Operative', 'p'), ('teams', 'i'), ('teams', 'm'), ('failing', 'f'), ('wide', 'w'), ('wide', 'a'), ('open', 'p'), ('Hold', 'ə'),
             ('positions', 'ʃ'), ('thirty', 'θ'), ('seconds', 's'), ('stabilize', 'b'), ('network', 'n'), ('myself', 'f'), ('There', 'ð'),
             ('back', 'a'), ('Push', 'ʊ'), ('forward', 'ɔ'), ('thank', 'θ'), ('you', 'u'), ('me', 'i')]
    ps = []
    for word, ph in picks:
        wi = [i for i, w in enumerate(al['words']) if w['word'] == word]
        wi = wi[-1] if word == 'me' else wi[0]
        cand = [p for p in al['phonemes'] if p['word'] == wi and p['phoneme'] == ph]
        if not cand:
            continue
        p0 = cand[0]
        f = int(round(f0 + 0.5 * (p0['start'] + p0['end']) * fps))
        sc.frame_set(f)
        bpy.context.view_layer.update()
        hm = rg.pose.bones['head'].matrix
        c = hm @ Vector((0.0, 0.035, 0.0)) if False else hm.translation + Vector((0.0, -0.06, 0.035))
        ps.append(shot(tmp('m_%03d_%s' % (f, p0['viseme'])), (c.x + 0.10, c.y - 0.80, c.z + 0.02), (c.x, c.y, c.z), lens=120, res=(300, 260)))
    sheet(ps, os.path.join(OUT, 'dialogue_lipsync.png'), cols=7)
    rest()
if want('uv_layouts'):
    import numpy as np
    ma = texraster.MeshArrays(lods[0].data)
    rng = np.random.RandomState(3)
    pal = rng.rand(len(ma.region_names), 3) * 0.7 + 0.25
    ps = []
    for mi, name in enumerate(ma.materials):
        r = texraster.Raster(ma, mi, 768)
        n = r.normal()
        col = pal[r.region()] * (0.55 + 0.45 * np.clip(n[:, 2] * 0.5 + 0.5, 0, 1))[:, None]
        p = tmp('uv_' + name)
        texraster.write_png(p, r.image(col, fill=0.06))
        ps.append(p)
    sheet(ps, os.path.join(OUT, 'uv_layouts.png'), cols=3)
print('EVIDENCE DONE', sorted(os.listdir(OUT)))
