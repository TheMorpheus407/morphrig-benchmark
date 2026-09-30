"""Render the face rig evidence sheets of Operative.blend: neutral + six expression presets + asymmetric examples, and the viseme shapes.
usage: blender -b source/Operative.blend -P source/generators/qa_face_sheets.py -- OUT_DIR
Writes OUT_DIR/face_expressions.png (10 tiles) and OUT_DIR/face_visemes.png (13 tiles)."""
import math
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mr_tools as MT
import mr_viz

out_dir = os.path.abspath(sys.argv[sys.argv.index('--') + 1])
os.makedirs(out_dir, exist_ok=True)
ctl = MT.ctl_obj()
if ctl.animation_data:
    ctl.animation_data.action = None          # manual poses must not be overwritten by the assigned idle clip's blink keys
for o in bpy.data.objects:
    if o.type == 'MESH':
        o.hide_render = o.name in ('Operative_Body', 'Operative_Gear', 'Operative_Boots', 'Operative_CyberArm_L', 'Operative_Cable', 'Operative_Prop_Beacon',
                                   'Operative_Prop_PowerCell', 'Operative_Hand_R') or o.name.startswith('WGT')
mr_viz.setup_world((0.32, 0.33, 0.36))
d = MT.data()


def render(tag):
    bpy.context.view_layer.update()
    p = os.path.join(out_dir, f'_fs_{tag}.png')
    mr_viz.render_views(p, views=('front',), target=(0.06, 0, 1.655), ortho=0.30, res=(300, 300), dist=3.0, engine='CYCLES', samples=24, perspective=False, light_energy=3.0)
    return p


def sheet(tiles, cols, name):
    rows = []
    for i in range(0, len(tiles), cols):
        chunk = tiles[i:i + cols]
        while len(chunk) < cols:
            chunk.append(chunk[-1])
        row = os.path.join(out_dir, f'_fsrow_{i}.png')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + sum([['-i', t] for t in chunk], []) + ['-filter_complex', f'hstack=inputs={cols}', row], check=True)
        rows.append(row)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + sum([['-i', r] for r in rows], []) + ['-filter_complex', f'vstack=inputs={len(rows)}', os.path.join(out_dir, name)], check=True)
    for r in rows:
        os.remove(r)


tiles = []
MT.reset_bones(ctl)
tiles.append(render('neutral'))
for name in ('joy_confidence', 'anger', 'concern_sadness', 'surprise', 'pain', 'focus'):
    MT.reset_bones(ctl)
    MT.apply_expression(ctl, name, 1.0)
    tiles.append(render(name))
# asymmetric examples built from single left/right channels
pb = ctl.pose.bones['ctl_face']
MT.reset_bones(ctl)                                        # left wink with a one-sided smile
ctl.pose.bones['ctl_lid_up_l'].rotation_euler = (math.radians(d['lid_close_up_deg']), 0, 0)
ctl.pose.bones['ctl_lid_lo_l'].rotation_euler = (math.radians(d['lid_close_lo_deg']), 0, 0)
pb['mouth_smile_l'] = 0.8; pb['cheek_raise_l'] = 0.6; pb['squint_l'] = 0.5; pb['dimple_l'] = 0.4
ctl.update_tag()
tiles.append(render('wink_left'))
MT.reset_bones(ctl)                                        # right smirk, left brow raised
pb['mouth_smile_r'] = 0.75; pb['dimple_r'] = 0.4; pb['brow_up_out_l'] = 0.9; pb['brow_up_in_l'] = 0.5; pb['brow_down_r'] = 0.5
ctl.update_tag()
tiles.append(render('smirk_right'))
MT.reset_bones(ctl)                                        # eyes look right, right lid half closed, left cheek puffed
for s, yaw in (('l', -22.0), ('r', -22.0)):
    ctl.pose.bones[f'ctl_eye_{s}'].rotation_euler = (math.radians(6.0), 0, math.radians(yaw))
ctl.pose.bones['ctl_lid_up_r'].rotation_euler = (math.radians(d['lid_close_up_deg'] * 0.55), 0, 0)
pb['cheek_puff_l'] = 0.8; pb['mouth_shift_r'] = 0.5; pb['nose_wrinkle_r'] = 0.5
ctl.update_tag()
tiles.append(render('gaze_puff'))
sheet(tiles, 5, 'face_expressions.png')
for t in tiles:
    os.remove(t)
tiles = []
for name in d['visemes']:
    if name == 'sil':
        continue
    MT.reset_bones(ctl)
    MT.apply_viseme(ctl, name, 1.0)
    tiles.append(render('vis_' + name))
sheet(tiles, 5, 'face_visemes.png')
for t in tiles:
    os.remove(t)
MT.reset_bones(ctl)
print('face sheets written to', out_dir)
