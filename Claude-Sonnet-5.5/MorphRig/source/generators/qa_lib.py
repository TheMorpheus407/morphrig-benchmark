"""QA helpers: contact sheets of a clip (time strips), foot-skating and loop-closure metrics. Runs inside Blender."""
import os
import subprocess
import math
import numpy as np
import bpy
import anim_lib as AL
import mr_viz


def hide_for_qa(keep=('Operative_Body', 'Operative_Head', 'Operative_Eyes', 'Operative_Mouth', 'Operative_Hand_R', 'Operative_CyberArm_L',
                      'Operative_Boots', 'Operative_Gear', 'Operative_Braid', 'Operative_Cable', 'Operative_Hair')):
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith('Operative_') and not o.name.startswith('Operative_Prop'):
            o.hide_render = o.name not in keep
    for n in ('Operative_Prop_PowerCell', 'Operative_Prop_Beacon'):
        if n in bpy.data.objects:
            bpy.data.objects[n].hide_render = False


def time_sheet(ctl, act, frames, out_png, view='left', target=(0, 0, 0.9), ortho=2.2, res=(200, 400), wire=False, tmp_dir=None, perspective=False, dist=4.0, color_type='MATERIAL', engine='BLENDER_WORKBENCH', shading='STUDIO'):
    """Render `frames` (clip frames) of the currently assigned action as one strip image."""
    AL.assign_action(ctl, act)
    tmp_dir = tmp_dir or os.path.dirname(out_png)
    tiles = []
    for i, f in enumerate(frames):
        bpy.context.scene.frame_set(f + 1)
        bpy.context.view_layer.update()
        p = os.path.join(tmp_dir, f'_ts_{i:03d}.png')
        mr_viz.render_views(p, views=(view,), target=target, ortho=ortho, res=res, wire=wire, perspective=perspective, dist=dist, color_type=color_type, engine=engine, shading=shading)
        tiles.append(p)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error']
    for t in tiles:
        cmd += ['-i', t]
    cmd += ['-filter_complex', f'hstack=inputs={len(tiles)}', out_png]
    subprocess.run(cmd, check=True)
    for t in tiles:
        os.remove(t)
    return out_png


def loop_error(ctl, skel, act, frames):
    """Max bone-head world distance between first and last frame (m)."""
    AL.assign_action(ctl, act)
    sc = bpy.context.scene
    res = []
    for f in (0, frames):
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        ev = skel.evaluated_get(bpy.context.evaluated_depsgraph_get())
        res.append({b.name: np.array(ev.matrix_world @ ev.pose.bones[b.name].head) for b in skel.data.bones})
    d = {n: float(np.linalg.norm(res[0][n] - res[1][n])) for n in res[0]}
    worst = max(d, key=d.get)
    return d[worst], worst


def skating(ctl, skel, act, frames, v_body, contacts, bones=('ball_l', 'ball_r')):
    """For each foot: stance-phase variation of (position + v*t) in the ground plane (cm). v_body = (vx, vy) m/s."""
    AL.assign_action(ctl, act)
    sc = bpy.context.scene
    pos = {b: [] for b in bones}
    for f in range(frames + 1):
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        ev = skel.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for b in bones:
            pos[b].append(np.array(ev.matrix_world @ ev.pose.bones[b].head))
    out = {}
    for c in contacts:
        b = 'ball_' + c['foot']
        a, l = c['plant_frame'], c['lift_frame']
        rng = list(range(a, l + 1)) if l > a else list(range(a, frames + 1)) + list(range(0, l + 1))
        # skip the roll transitions: use the middle 60 percent
        mid = rng[int(len(rng) * 0.2): int(len(rng) * 0.8) + 1]
        vals = []
        for i in mid:
            t = (i - a) / 30.0 if i >= a else (i + frames - a) / 30.0
            p = pos[b][i]
            vals.append([p[0] + v_body[0] * t, p[1] + v_body[1] * t])
        vals = np.array(vals)
        out[c['foot']] = float(np.abs(vals - vals.mean(axis=0)).max() * 100.0) if len(vals) else 0.0
    return out


BODY_OBJS = ('Operative_Body', 'Operative_Head', 'Operative_Hand_R', 'Operative_CyberArm_L', 'Operative_Boots', 'Operative_Gear')


def min_z_track(ctl, act, frames_list=None, objs=BODY_OBJS):
    """Minimum evaluated mesh z (m) per sampled frame of the assigned action; also the frame list."""
    AL.assign_action(ctl, act)
    sc = bpy.context.scene
    n = int(act['mr_frames'])
    frames_list = frames_list if frames_list is not None else list(range(0, n + 1))
    out = []
    for f in frames_list:
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        mz = 9.0
        for name in objs:
            ob = bpy.data.objects.get(name)
            if ob is None:
                continue
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            a = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get('co', a)
            a = a.reshape(-1, 3)
            mw = np.array(ob.matrix_world)
            z = a[:, 0] * mw[2, 0] + a[:, 1] * mw[2, 1] + a[:, 2] * mw[2, 2] + mw[2, 3]
            mz = min(mz, float(z.min()))
            ev.to_mesh_clear()
        out.append(mz)
    return frames_list, out
