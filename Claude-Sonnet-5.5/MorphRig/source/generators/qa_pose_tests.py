"""Render the skinning demonstration poses (front, left, back, three-quarter) of Operative.blend into one sheet.
usage: blender -b source/Operative.blend -P source/generators/qa_pose_tests.py -- OUT.png [--hq]   (--hq renders with Cycles)"""
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anim_lib as AL
import mr_viz

args = sys.argv[sys.argv.index('--') + 1:]
out = os.path.abspath(args[0])
engine = 'CYCLES' if '--hq' in args else 'BLENDER_WORKBENCH'
ctl = bpy.data.objects['Operative_Control']
for o in bpy.data.objects:
    if o.type == 'MESH':
        o.hide_render = o.name.startswith('WGT')
names = ['overhead_reach', 'deep_squat', 'crossed_arm_reach', 'torso_twist', 'kneeling', 'planted_hand', 'closed_grip']
mr_viz.setup_world((0.30, 0.31, 0.34))
tmp = os.path.dirname(out)
rows = []
for n in names:
    AL.assign_action(ctl, bpy.data.actions['A_pt_' + n])
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    tiles = []
    for view in ('front', 'left', 'back', 'q_front_left'):
        p = os.path.join(tmp, f'_pt_{n}_{view}.png')
        mr_viz.render_views(p, views=(view,), target=(0.0, 0, 1.0), ortho=2.6, res=(300, 420), dist=6.0, color_type='TEXTURE' if engine != 'CYCLES' else 'MATERIAL',
                            engine=engine, samples=24, perspective=(view == 'q_front_left'), light_energy=3.0)
        tiles.append(p)
    row = os.path.join(tmp, f'_ptrow_{n}.png')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + sum([['-i', t] for t in tiles], []) + ['-filter_complex', 'hstack=inputs=4', row], check=True)
    rows.append(row)
    for t in tiles:
        os.remove(t)
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + sum([['-i', r] for r in rows], []) + ['-filter_complex', f'vstack=inputs={len(rows)}', out], check=True)
for r in rows:
    os.remove(r)
print('pose test sheet written', out)
