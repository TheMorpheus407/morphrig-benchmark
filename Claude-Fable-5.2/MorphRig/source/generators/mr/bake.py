"""Baking of control-rig actions onto the deformation skeleton, with QA measurements."""
import math
import bpy
import numpy as np
from mathutils import Matrix
from . import animio, facedefs, skel, clips as clipdefs
from .animkit import m_to_q


def face_control_values(face_pb):
    """Final 0..1 value of every face control from the 'face' bone properties (same formula as the drivers)."""
    out = {}
    for ctl in facedefs.CONTROLS:
        v = float(face_pb.get(ctl, 0.0))
        for vis, (_, wmap) in facedefs.VISEMES.items():
            if ctl in wmap:
                v += wmap[ctl] * float(face_pb.get('vis_' + vis, 0.0))
        for ex, wmap in facedefs.EXPRESSIONS.items():
            if ctl in wmap:
                v += wmap[ctl] * float(face_pb.get('expr_' + ex, 0.0))
        out[ctl] = min(1.0, max(0.0, v))
    return out


def sample_clip(clip_id, n_frames, rig, skel_ob, action, slot, is_pose=False):
    """Evaluate the rig for frames 0..n and return per-bone local tracks of the deformation skeleton."""
    sc = bpy.context.scene
    from . import rig as rigmod
    rigmod.reset_pose(rig)          # channels without keys must not inherit values from the previous clip
    animio.assign(rig, action, slot)
    bones = [pb.name for pb in skel_ob.pose.bones]
    parents = {pb.name: (pb.parent.name if pb.parent else None) for pb in skel_ob.pose.bones}
    rest = {pb.name: np.array(pb.bone.matrix_local) for pb in skel_ob.pose.bones}
    rest_inv = {k: np.linalg.inv(v) for k, v in rest.items()}
    frames = [0, 1] if is_pose else list(range(0, n_frames + 1))
    tracks = {b: {'rot': np.zeros((len(frames), 4)), 'loc': np.zeros((len(frames), 3))} for b in bones}
    world = {b: np.zeros((len(frames), 4, 4)) for b in bones}
    morphs = {m: np.zeros(len(frames)) for m in facedefs.MORPHS}
    face_pb = rig.pose.bones['face']
    for fi, f in enumerate(frames):
        sc.frame_set(0 if is_pose else f)
        mats = {pb.name: np.array(pb.matrix) for pb in skel_ob.pose.bones}
        for b in bones:
            M = mats[b]
            world[b][fi] = M
            p = parents[b]
            if p is None:
                L = rest_inv[b] @ M
            else:
                L = np.linalg.inv(mats[p] @ rest_inv[p] @ rest[b]) @ M
            tracks[b]['loc'][fi] = L[:3, 3]
            R = L[:3, :3]
            # remove scale (root scale is not used by any required clip)
            R = R / np.linalg.norm(R, axis=0, keepdims=True)
            tracks[b]['rot'][fi] = m_to_q(R)
        vals = face_control_values(face_pb)
        for m in facedefs.MORPHS:
            morphs[m][fi] = vals[m]
    return frames, tracks, morphs, world


def write_baked(clip_id, skel_ob, proxy_key, frames, tracks, morphs):
    act, slot, cb = animio.new_action('BAKED_' + clip_id, skel_ob, 'OBJECT')
    animio.write_bone_tracks(cb, tracks, frames)
    kact = None
    if proxy_key is not None:
        used = {m: v for m, v in morphs.items() if np.max(np.abs(v)) > 1e-5}
        if used:
            kact, kslot, kcb = animio.new_action('BAKED_' + clip_id + '.morph', proxy_key, 'KEY')
            for m, v in used.items():
                animio.set_curve(kcb, 'key_blocks["%s"].value' % m, 0, frames, v, 'morph')
    return act, slot, kact


# ------------------------------------------------------------------------------------ QA metrics
FOOT_POINTS = {'heel': (0.0, 0.046, -0.098), 'ball': (0.003, -0.142, -0.098), 'toe': (0.005, -0.234, -0.098)}


def foot_points(world, side, fi):
    """World positions of heel / ball / toe sole points for a frame (uses foot and ball bone matrices)."""
    sx = 1.0 if side == 'l' else -1.0
    Mf = world['foot_' + side][fi]
    Mb = world['ball_' + side][fi]
    rf = np.array(skel.bone_matrix('foot_' + side))
    rb = np.array(skel.bone_matrix('ball_' + side))
    ank = skel.J['foot_' + side]
    out = {}
    for name, off in FOOT_POINTS.items():
        p_rest = ank + np.array([off[0] * sx, off[1], off[2]])
        M, r = (Mb, rb) if name == 'toe' else (Mf, rf)
        local = np.linalg.inv(r) @ np.append(p_rest, 1.0)
        out[name] = (M @ local)[:3]
    return out


BODY_RADII = {'pelvis': 0.095, 'spine_02': 0.095, 'spine_03': 0.105, 'head': 0.075, 'hand_l': 0.018, 'hand_r': 0.020,
               'lowerarm_l': 0.035, 'lowerarm_r': 0.040, 'calf_l': 0.050, 'calf_r': 0.050, 'upperarm_l': 0.045, 'upperarm_r': 0.045,
               'foot_l': 0.045, 'foot_r': 0.045}


def metrics(clip_meta, frames, tracks, world, notes=None):
    """QA numbers for a baked clip. Ground speed: nominal speed for locomotion loops, the authored speed profile
    for start/stop clips (notes['speed_profile'], m/s along the facing), zero otherwise."""
    notes = notes or {}
    n = len(frames)
    res = {}
    if clip_meta['form'] == 'loop':
        worst = 0.0
        for b, tr in tracks.items():
            dq = min(np.abs(tr['rot'][0] - tr['rot'][-1]).max(), np.abs(tr['rot'][0] + tr['rot'][-1]).max())
            worst = max(worst, dq, np.abs(tr['loc'][0] - tr['loc'][-1]).max())
        res['loop_error'] = float(worst)
    res['root_displacement_cm'] = [round(float(v) * 100, 3) for v in (world['root'][-1][:3, 3] - world['root'][0][:3, 3]) * np.array([1, -1, 1])]
    v_nom = clip_meta.get('nominal_speed', 0.0) / 100.0 if clip_meta['layer'] == 'locomotion' else 0.0
    ang = math.radians(clip_meta.get('travel_dir_deg', 0.0))
    prof = notes.get('speed_profile')
    slide_max, pen_min, slide_at, pen_at = 0.0, 1.0, None, None
    planted_n = {}
    for side in ('l', 'r'):
        pts = [foot_points(world, side, fi) for fi in range(n)]
        cnt = 0
        for fi in range(n - 1):
            v = v_nom
            if prof is not None:
                v = 0.5 * (prof[min(fi, len(prof) - 1)] + prof[min(fi + 1, len(prof) - 1)])
            ground_v = -np.array([math.sin(ang), -math.cos(ang), 0.0]) * v
            root_v = (world['root'][fi + 1][:3, 3] - world['root'][fi][:3, 3]) * clipdefs.FPS
            lowest = min(pts[fi], key=lambda k: pts[fi][k][2])
            z0, z1 = pts[fi][lowest][2], pts[fi + 1][lowest][2]
            if z0 < pen_min:
                pen_min, pen_at = z0, (side, lowest, frames[fi])
            if z0 < 0.004 and z1 < 0.004:
                vel = (pts[fi + 1][lowest] - pts[fi][lowest]) * clipdefs.FPS
                rel = vel - ground_v
                sp = float(np.linalg.norm(rel[:2]))
                if sp > slide_max:
                    slide_max, slide_at = sp, (side, lowest, frames[fi])
                cnt += 1
        planted_n[side] = cnt
    res['slide_max_cm_s'] = round(slide_max * 100, 2)
    res['slide_at'] = slide_at
    res['min_sole_height_cm'] = round(pen_min * 100, 2)
    res['min_sole_at'] = pen_at
    res['planted'] = planted_n
    # body clearance: lowest point of a few joints minus an approximate body radius (negative = sunk into the floor)
    worst, where = 1.0, None
    for bone, rad in BODY_RADII.items():
        if bone not in world:
            continue
        z = world[bone][:, 2, 3] - rad
        k = int(np.argmin(z))
        if z[k] < worst:
            worst, where = float(z[k]), (bone, frames[k])
    res['body_clear_cm'] = round(worst * 100, 1)
    res['body_clear_at'] = where
    return res


def world_root_vel(world, fi):
    return np.zeros(3)
