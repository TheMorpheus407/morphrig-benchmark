"""Fast creation / sampling of (slotted) actions - Blender 4.4+/5.x action API."""
import bpy
import numpy as np

INTERP = {'CONSTANT': 0, 'LINEAR': 1, 'BEZIER': 2}


def new_action(name, id_block, id_type='OBJECT'):
    """Create (replace) an action with one layer/strip/slot for id_block. Returns (action, slot, channelbag)."""
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    slot = act.slots.new(id_type=id_type, name=id_block.name)
    layer = act.layers.new('Layer')
    strip = layer.strips.new(type='KEYFRAME')
    cb = strip.channelbag(slot, ensure=True)
    act.use_fake_user = True
    return act, slot, cb


def channelbag(action, slot=None):
    for layer in action.layers:
        for strip in layer.strips:
            if slot is not None:
                cb = strip.channelbag(slot)
                if cb is not None:
                    return cb
            else:
                for cb in strip.channelbags:
                    return cb
    return None


def assign(id_block, action, slot=None):
    ad = id_block.animation_data or id_block.animation_data_create()
    ad.action = action
    if action is not None:
        if slot is None:
            slots = list(ad.action_suitable_slots)
            slot = slots[0] if slots else (action.slots[0] if len(action.slots) else None)
        if slot is not None:
            ad.action_slot = slot


def set_curve(cb, data_path, index, frames, values, group='', interp='LINEAR', compress=True, eps=1e-7):
    """Write one f-curve from sampled values. Constant curves collapse to a single key."""
    frames = np.asarray(frames, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if compress and len(values) > 1 and np.max(np.abs(values - values[0])) < eps:
        frames, values = frames[:1], values[:1]
    fc = cb.fcurves.new(data_path, index=index, group_name=group)
    n = len(frames)
    fc.keyframe_points.add(n)
    co = np.empty(n * 2, dtype=np.float64)
    co[0::2] = frames
    co[1::2] = values
    fc.keyframe_points.foreach_set('co', co)
    fc.keyframe_points.foreach_set('interpolation', np.full(n, INTERP[interp], dtype=np.int32))
    if interp == 'BEZIER':
        # eBezTriple_Handle: 0 FREE, 1 AUTO, 2 VECTOR, 3 ALIGNED, 4 AUTO_CLAMPED
        fc.keyframe_points.foreach_set('handle_left_type', np.full(n, 4, dtype=np.int32))
        fc.keyframe_points.foreach_set('handle_right_type', np.full(n, 4, dtype=np.int32))
        hl = co.copy()
        hr = co.copy()
        hl[0::2] -= 1.0
        hr[0::2] += 1.0
        fc.keyframe_points.foreach_set('handle_left', hl)
        fc.keyframe_points.foreach_set('handle_right', hr)
    fc.update()
    return fc


def reduce_keys(frames, values, tol):
    """Indices of the keys to keep so that linear interpolation between them stays within tol (max norm over the
    components) of every original sample. First and last keys are always kept (Ramer-Douglas-Peucker in time)."""
    frames = np.asarray(frames, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    n = len(frames)
    if n <= 2:
        return np.arange(n)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        t = (frames[a + 1:b] - frames[a]) / (frames[b] - frames[a])
        lin = values[a] + (values[b] - values[a]) * t[:, None]
        err = np.abs(values[a + 1:b] - lin).max(axis=1)
        k = int(np.argmax(err))
        if err[k] > tol:
            m = a + 1 + k
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return np.nonzero(keep)[0]


def bone_path(bone, prop):
    return 'pose.bones["%s"].%s' % (bone, prop)


def write_bone_tracks(cb, tracks, frames, compress=True):
    """tracks: {bone: {'rot': (n,4) wxyz quats, 'loc': (n,3), 'scale': (n,3)}}"""
    for bone, tr in tracks.items():
        q = tr.get('rot')
        if q is not None:
            q = np.asarray(q, dtype=np.float64)
            # keep quaternion continuity (shortest path between neighbours)
            for i in range(1, len(q)):
                if np.dot(q[i], q[i - 1]) < 0:
                    q[i] = -q[i]
            for k in range(4):
                set_curve(cb, bone_path(bone, 'rotation_quaternion'), k, frames, q[:, k], bone, compress=compress)
        loc = tr.get('loc')
        if loc is not None:
            loc = np.asarray(loc, dtype=np.float64)
            for k in range(3):
                set_curve(cb, bone_path(bone, 'location'), k, frames, loc[:, k], bone, compress=compress)
        sc = tr.get('scale')
        if sc is not None:
            sc = np.asarray(sc, dtype=np.float64)
            for k in range(3):
                set_curve(cb, bone_path(bone, 'scale'), k, frames, sc[:, k], bone, compress=compress)


def action_frame_range(action):
    lo, hi = action.frame_range
    return int(round(lo)), int(round(hi))
