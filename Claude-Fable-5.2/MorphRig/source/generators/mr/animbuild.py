"""Clip registry + helpers to build, bake, measure and preview clips."""
import os
import bpy
import numpy as np
from . import animkit, animio, bake, clips as clipdefs, gait, preview

REGISTRY = {}


def register(*ids):
    def deco(fn):
        for i in ids:
            REGISTRY[i] = fn
        return fn
    return deco


for _c in clipdefs.CLIPS:
    if _c['layer'] == 'locomotion':
        REGISTRY[_c['id']] = gait.build_gait_clip


def load_clip_modules():
    """Import the authoring modules (they register their builders)."""
    import importlib
    for m in ('anim_base', 'anim_move', 'anim_combat', 'anim_react', 'anim_social'):
        try:
            importlib.import_module('.' + m, __package__)
        except ModuleNotFoundError as e:
            if m not in str(e):
                raise


class Ctx:
    """Lets a clip builder evaluate what it has authored so far (measure, then author the contacts)."""

    def __init__(self, rig):
        self.rig = rig

    def sample(self, clip, frames, bones):
        """{frame: {bone: 4x4 armature-space matrix}} of control-rig bones for the clip's current keys."""
        sc = bpy.context.scene
        from . import rig as rigmod
        act, slot = animkit.write_action(clip, self.rig, name='TMP_sample')
        rigmod.reset_pose(self.rig)
        animio.assign(self.rig, act, slot)
        out = {}
        for f in frames:
            sc.frame_set(int(f))
            out[f] = {b: np.array(self.rig.pose.bones[b].matrix) for b in bones}
        self.rig.animation_data.action = None
        bpy.data.actions.remove(act)
        rigmod.reset_pose(self.rig)
        return out

    def pose(self, pose, bones):
        """Evaluate one Pose and return the matrices of the requested bones."""
        tmp = animkit.Clip('greet', frames=1)
        pose.apply(tmp, 0)
        return self.sample(tmp, [0], bones)[0]


def build_clip(cid, rig):
    from . import pose as _pose
    _pose.CLAMP_LOG['max'] = 0.0
    _pose.CLAMP_LOG['at'] = None
    import inspect
    clip = animkit.Clip(cid)
    fn = REGISTRY.get(cid)
    if fn is None:
        raise KeyError('no builder for ' + cid)
    if len(inspect.signature(fn).parameters) >= 2:
        fn(clip, Ctx(rig))
    else:
        fn(clip)
    if clip.loop:
        clip.close_loop()
    act, slot = animkit.write_action(clip, rig)
    return clip, act, slot


def bake_clip(clip, act, slot, rig, skel_ob, proxy_key=None, write=True):
    is_pose = clip.meta['form'] == 'pose'
    frames, tracks, morphs, world = bake.sample_clip(clip.id, clip.frames, rig, skel_ob, act, slot, is_pose)
    m = bake.metrics(clip.meta, frames, tracks, world, clip.notes)
    # IK reach error: ankle target vs solved ankle
    baked = None
    if write:
        baked = bake.write_baked(clip.id, skel_ob, proxy_key, frames, tracks, morphs)
    return dict(frames=frames, tracks=tracks, morphs=morphs, world=world, metrics=m, baked=baked)


worst_arm = [0.0, None]


def reach_error(rig, skel_ob, act, slot, n_frames):
    """Max distance between the IK ankle targets and the solved ankles over the clip (metres)."""
    sc = bpy.context.scene
    from . import rig as rigmod
    rigmod.reset_pose(rig)
    animio.assign(rig, act, slot)
    worst = 0.0
    worst_arm[0], worst_arm[1] = 0.0, None
    for f in range(0, n_frames + 1):
        sc.frame_set(f)
        for s in ('l', 'r'):
            if rig.pose.bones['foot_ik_' + s].get('leg_ik', 1.0) < 0.5:
                continue
            a = rig.pose.bones['MCH_ankle_tgt_' + s].matrix.translation
            b = skel_ob.pose.bones['foot_' + s].matrix.translation
            worst = max(worst, (a - b).length)
        for s in ('l', 'r'):
            if rig.pose.bones['hand_ik_' + s].get('arm_ik', 0.0) < 0.999:
                continue
            a = rig.pose.bones['hand_ik_' + s].matrix.translation
            b = skel_ob.pose.bones['hand_' + s].matrix.translation
            if (a - b).length > worst_arm[0]:
                worst_arm[0] = (a - b).length
                worst_arm[1] = (s, f)
    return worst


def preview_clip(cid, rig, act, slot, out_path, frames, views=('left', 'fl'), res=(300, 430), center=(0, -0.05, 0.92), height=2.0, cols=None):
    sc = bpy.context.scene
    from . import rig as rigmod
    rigmod.reset_pose(rig)
    animio.assign(rig, act, slot)
    preview.setup_workbench(sc, res=res)
    ps = []
    for v in views:
        for f in frames:
            sc.frame_set(int(f))
            rt = rig.pose.bones['root'].matrix.translation
            p = out_path + '_%s_%03d.png' % (v if isinstance(v, str) else 'v', int(f))
            preview.render_view(p, v, center=(center[0] + rt.x, center[1] + rt.y, center[2]), height=height)
            ps.append(p)
    preview.sheet(ps, out_path + '.png', cols=cols or len(frames))
    return out_path + '.png'
