"""Semantic pose building on top of anim_lib: rig evaluation helpers, IK targets in root-relative metres, a base stance,
prop-follow tracks and simple analysis (foot skating, loop closure). All positions are root-relative character space
(+X forward, +Y left, +Z up) in metres."""
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix, Quaternion, Euler
import skeleton_def as S
import anim_lib as AL
from anim_lib import Pose, arm_fk, hand_pose, foot_ik, hand_ik, spine_pose, neck_head, DEG

SIDES = (('l', 1.0), ('r', -1.0))
CTX = {}


def bind(ctl, skel):
    CTX['ctl'] = ctl
    CTX['skel'] = skel


def evaluate(pose=None, reset=True):
    ctl = CTX['ctl']
    if reset:
        AL.reset_pose(ctl)
    if pose:
        AL.apply_pose(ctl, pose, update=False)
    ctl.update_tag()
    bpy.context.view_layer.update()
    return ctl.evaluated_get(bpy.context.evaluated_depsgraph_get())


def world_of(ev, bone):
    return ev.matrix_world @ ev.pose.bones[bone].matrix


def head_of(ev, bone):
    return ev.matrix_world @ ev.pose.bones[bone].head


def tail_of(ev, bone):
    return ev.matrix_world @ ev.pose.bones[bone].tail


REST_WRIST = {s: Vector(S.BONE_BY_NAME[f'hand_{s}'].head) for s, _ in SIDES}
REST_ANKLE_GROUND = {s: Vector((S.BONE_BY_NAME[f'foot_{s}'].head[0], S.BONE_BY_NAME[f'foot_{s}'].head[1], 0.0)) for s, _ in SIDES}
REST_HAND_DIR = Vector(S.HAND_DIR)


def rest_hand_dir(side):
    sy = 1.0 if side == 'l' else -1.0
    return Vector((S.HAND_DIR[0], sy * S.HAND_DIR[1], S.HAND_DIR[2]))


def euler_deg_from_matrix(m3):
    return tuple(math.degrees(a) for a in m3.to_euler('XYZ'))


def palm_normal(side):
    sy = 1.0 if side == 'l' else -1.0
    return Vector((S.PALM_NORMAL[0], sy * S.PALM_NORMAL[1], S.PALM_NORMAL[2]))


def hand_rot_for(side, direction, roll_deg=0.0, palm=None):
    """Euler XYZ degrees for ctl_hand_ik so the hand's finger axis points along `direction` (unit Vector). `palm` (Vector) makes the palm
    face that direction (roll chosen automatically); otherwise `roll_deg` rolls about the finger axis."""
    d = Vector(direction).normalized()
    q = rest_hand_dir(side).rotation_difference(d)
    if palm is not None:
        n = q @ palm_normal(side)
        u = Vector(palm)
        n_p = n - d * n.dot(d)
        u_p = u - d * u.dot(d)
        if n_p.length > 1e-6 and u_p.length > 1e-6:
            n_p.normalize()
            u_p.normalize()
            ang = math.atan2(d.dot(n_p.cross(u_p)), n_p.dot(u_p))
            roll_deg = math.degrees(ang) + roll_deg
    q_roll = Quaternion(d, roll_deg * DEG)
    q_tot = q_roll @ q
    return tuple(math.degrees(a) for a in q_tot.to_euler('XYZ'))


def arm_ik_pose(side, target, direction=None, roll=0.0, rot=None, palm=None):
    """IK hand at `target` (root-relative wrist position, metres). Orientation from finger direction or explicit rot."""
    off = Vector(target) - REST_WRIST[side]
    if rot is None:
        rot = hand_rot_for(side, direction if direction is not None else rest_hand_dir(side), roll, palm)
    return hand_ik(side, tuple(off), rot)


def arm_pole(side, elbow_hint):
    """Position the arm pole (world) at `elbow_hint`; returns loc offsets for ctl_pole_arm_side."""
    sy = 1.0 if side == 'l' else -1.0
    rest = Vector((S.ELBOW[0] - 0.32, sy * (S.ELBOW[1] + 0.06), S.ELBOW[2] + 0.02))
    p = Pose()
    p.loc(f'ctl_pole_arm_{side}', tuple(Vector(elbow_hint) - rest))
    return p


def leg_pole(side, foot_xy, yaw_deg=0.0, height=0.55, forward=0.38, out=0.03):
    sy = 1.0 if side == 'l' else -1.0
    rest = Vector((S.KNEE[0] + 0.36, sy * S.KNEE[1], S.KNEE[2]))
    yaw = yaw_deg * DEG
    f = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    pos = Vector((foot_xy[0], foot_xy[1], height)) + f * forward + Vector((0, sy * out, 0))
    p = Pose()
    p.loc(f'ctl_pole_leg_{side}', tuple(pos - rest))
    return p


def feet_pose(fl=None, fr=None, pelvis_xy=(0.0, 0.0), poles=True):
    """fl/fr dict(x,y,z,yaw,roll,pitch,bank) are ground-anchor OFFSETS from rest (metres, degrees)."""
    p = Pose()
    for s, f in (('l', fl or {}), ('r', fr or {})):
        p.update(foot_ik(s, (f.get('x', 0.0), f.get('y', 0.0), f.get('z', 0.0)), yaw=f.get('yaw', 0.0), roll=f.get('roll', 0.0),
                         pitch=f.get('pitch', 0.0), bank=f.get('bank', 0.0)))
        if poles:
            rx, ry = REST_ANKLE_GROUND[s].x, REST_ANKLE_GROUND[s].y
            p.update(leg_pole(s, (rx + f.get('x', 0.0), ry + f.get('y', 0.0)), f.get('yaw', 0.0), height=f.get('pole_h', 0.55), forward=f.get('pole_f', 0.38)))
    return p


def pelvis_pose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0):
    p = Pose()
    p.loc('ctl_pelvis', (x, y, z))
    p.rot('ctl_pelvis', (roll, pitch, yaw))
    return p


def base_stance(pelvis_drop=0.015, arms='relaxed', hands=0.25):
    p = Pose()
    p.update(pelvis_pose(z=-pelvis_drop))
    p.update(feet_pose())
    if arms == 'relaxed':
        p.update(arm_fk('l', flex=4, abd=-20, elbow=14))
        p.update(arm_fk('r', flex=4, abd=-20, elbow=14))
    p.update(hand_pose('l', curl=hands))
    p.update(hand_pose('r', curl=hands))
    return p


# ----------------------------------------------------------------------------- prop follow (cell in forearm slot, beacon in dock)

def prop_matrix(ev, which, state, hand_offset=None):
    """World matrix of the prop bone target. state: 'slot' | 'dock' | ('hand', side, Matrix offset) | ('world', Matrix)."""
    if which == 'cell':
        if state == 'slot':
            fa = world_of(ev, 'def_lowerarm_l')
            rest_fa = S.BONE_BY_NAME['lowerarm_l']
            slot = Matrix.Translation(Vector(S.SOCKETS['cell_slot'][1]))
            rest_bone = Matrix(skel_rest('lowerarm_l'))
            off = rest_bone.inverted() @ Matrix.Translation(Vector(S.BONE_BY_NAME['prop_cell'].head))
            return fa @ off
    return None


def skel_rest(name):
    return CTX['skel'].data.bones[name].matrix_local.copy()


def follow_offset(prop_bone, parent_bone):
    """Rest offset of the prop bone frame expressed in the parent bone frame (both rest matrices)."""
    return skel_rest(parent_bone).inverted() @ skel_rest(prop_bone)


def compute_prop_tracks(act_frames, states):
    """states: callable(frame) -> dict(cell=('slot'|'dock'|('hand', side, offset_matrix)|('world', matrix)|None), beacon=...).
    Steps through the currently assigned action frame by frame and returns channel arrays for ctl_cell / ctl_beacon
    (location and Euler degrees, relative to their rest transforms)."""
    ctl = CTX['ctl']
    sc = bpy.context.scene
    out = {}
    cell_rest = skel_rest('prop_cell')
    beac_rest = skel_rest('prop_beacon')
    rest_off_cell = follow_offset('prop_cell', 'lowerarm_l')
    rest_off_beac = follow_offset('prop_beacon', 'pelvis')
    tracks = {('ctl_cell', 'loc'): [], ('ctl_cell', 'rot'): [], ('ctl_beacon', 'loc'): [], ('ctl_beacon', 'rot'): []}
    for f in range(act_frames + 1):
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        ev = ctl.evaluated_get(bpy.context.evaluated_depsgraph_get())
        st = states(f)
        for which, bone, rest, rest_off, parent in (('cell', 'ctl_cell', cell_rest, rest_off_cell, 'def_lowerarm_l'), ('beacon', 'ctl_beacon', beac_rest, rest_off_beac, 'def_pelvis')):
            s = st.get(which)
            if s == 'slot' or s == 'dock':
                M = world_of(ev, parent) @ rest_off
            elif isinstance(s, tuple) and s[0] == 'hand':
                M = world_of(ev, f'def_hand_{s[1]}') @ s[2]
            elif isinstance(s, tuple) and s[0] == 'world':
                M = s[1]
            else:
                M = rest
            # basis relative to the bone rest (bone parent is ctl_root, identity at rest and moving with root motion)
            rootM = world_of(ev, 'ctl_root')
            rest_root = Matrix.Identity(4)
            Bm = (rootM @ rest).inverted() @ M
            # ctl bone local basis = rest^-1 * root^-1 * M   (bone matrix_local rest)
            Bm = rest.inverted() @ rootM.inverted() @ M
            loc = Bm.to_translation()
            eul = Bm.to_euler('XYZ')
            tracks[(bone, 'loc')].append(tuple(loc))
            tracks[(bone, 'rot')].append(tuple(math.degrees(a) for a in eul))
    return tracks


def add_prop_keys(clip, states, step=1):
    """Compute prop follow tracks from the written action (action must be assigned) and merge them into clip.keys."""
    tr = compute_prop_tracks(clip.frames, states)
    for (bone, kind), arr in tr.items():
        arr = np.array(arr)
        for i in range(3):
            d = clip.keys.setdefault((bone, kind, i), {})
            for f in range(0, clip.frames + 1, step):
                d[f] = float(arr[f, i])
            d[clip.frames] = float(arr[clip.frames, i])


def finalize_clip(clip, ctl, skel, states=None):
    """Write the action, add prop follow keys (cell in slot, beacon in dock unless overridden), rewrite the action."""
    if states is None:
        states = lambda f: {'cell': 'slot', 'beacon': 'dock'}
    act = AL.write_action(ctl, clip)
    AL.assign_action(ctl, act)
    add_prop_keys(clip, states)
    act = AL.write_action(ctl, clip)
    return act


# ----------------------------------------------------------------------------- analysis helpers

def foot_world_track(clip, ctl, skel, bones=('ball_l', 'ball_r', 'foot_l', 'foot_r')):
    sc = bpy.context.scene
    out = {b: [] for b in bones}
    for f in range(clip.frames + 1):
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        ev = skel.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for b in bones:
            out[b].append(tuple(ev.matrix_world @ ev.pose.bones[b].head))
    return {b: np.array(v) for b, v in out.items()}


# ----------------------------------------------------------------------------- matrix based hand targets and prop grips

def hand_ik_from_world(side, M):
    """Pose channels (ctl_hand_ik) that put the hand bone at world matrix M (root-relative armature space, identity root)."""
    R_rest = skel_rest(f'hand_{side}').to_3x3()
    R_ctrl = M.to_3x3() @ R_rest.inverted()
    loc = M.translation - REST_WRIST[side]
    return hand_ik(side, tuple(loc), tuple(math.degrees(a) for a in R_ctrl.to_euler('XYZ')))


CELL_AXIS_MESH = None


def _mesh_axis(prop):
    import cyber_arm as CA
    return Vector(CA.FA).normalized() if prop == 'cell' else Vector((0.0, 0.0, 1.0))


def grip_matrix(prop, side):
    """Rigid offset G so that prop_bone_world = hand_world @ G. Cell: axis across the palm, held 5 cm along the fingers and 2 cm off the
    palm. Beacon: base towards the palm side, body 6 cm along the fingers, top pointing towards the palm."""
    R_rest = skel_rest('prop_cell' if prop == 'cell' else 'prop_beacon').to_3x3()
    a_mesh = _mesh_axis(prop)
    if prop == 'cell':
        Rf = a_mesh.rotation_difference(Vector((1.0, 0.0, 0.0))).to_matrix()
        g = Vector((0.0, 0.052, 0.024))
    else:
        Rf = Quaternion(Vector((1.0, 0.0, 0.0)), math.pi).to_matrix() @ a_mesh.rotation_difference(Vector((0.0, 0.0, 1.0))).to_matrix()
        g = Vector((0.0, 0.062, 0.050))
    G = Matrix.Translation(g) @ (Rf @ R_rest).to_4x4()
    return G


def prop_world_matrix(prop, pos, axis=None, roll_deg=0.0):
    """World matrix of a prop bone that puts the prop's mesh axis along `axis` (world) with the mesh centre/base at `pos`."""
    R_rest = skel_rest('prop_cell' if prop == 'cell' else 'prop_beacon').to_3x3()
    a_mesh = _mesh_axis(prop)
    if axis is None:
        Rn = Matrix.Identity(3)
    else:
        u = Vector(axis).normalized()
        q = a_mesh.rotation_difference(u)
        if roll_deg:
            q = Quaternion(u, math.radians(roll_deg)) @ q
        Rn = q.to_matrix()
    return Matrix.Translation(Vector(pos)) @ (Rn @ R_rest).to_4x4()


def slot_matrix(ev):
    """Prop bone matrix of the cell seated in the forearm slot (follows def_lowerarm_l)."""
    return world_of(ev, 'def_lowerarm_l') @ follow_offset('prop_cell', 'lowerarm_l')


def dock_matrix(ev):
    return world_of(ev, 'def_pelvis') @ follow_offset('prop_beacon', 'pelvis')


def compute_prop_tracks2(frames, states):
    """states(f, ev) -> dict(cell=..., beacon=...) where each is 'slot'|'dock'|('hand', side)|('world', Matrix)."""
    ctl = CTX['ctl']
    sc = bpy.context.scene
    cell_rest = skel_rest('prop_cell')
    beac_rest = skel_rest('prop_beacon')
    tracks = {('ctl_cell', 'loc'): [], ('ctl_cell', 'rot'): [], ('ctl_beacon', 'loc'): [], ('ctl_beacon', 'rot'): []}
    Gc = {s: grip_matrix('cell', s) for s in ('l', 'r')}
    Gb = {s: grip_matrix('beacon', s) for s in ('l', 'r')}
    for f in range(frames + 1):
        sc.frame_set(f + 1)
        bpy.context.view_layer.update()
        ev = ctl.evaluated_get(bpy.context.evaluated_depsgraph_get())
        st = states(f, ev)
        rootM = world_of(ev, 'ctl_root')
        for which, bone, rest in (('cell', 'ctl_cell', cell_rest), ('beacon', 'ctl_beacon', beac_rest)):
            s = st.get(which)
            if s == 'slot':
                M = slot_matrix(ev)
            elif s == 'dock':
                M = dock_matrix(ev)
            elif isinstance(s, tuple) and s[0] == 'hand':
                H = world_of(ev, f'def_hand_{s[1]}')
                M = H @ (Gc[s[1]] if which == 'cell' else Gb[s[1]])
            elif isinstance(s, tuple) and s[0] == 'world':
                M = s[1]
            else:
                M = rest
            Bm = rest.inverted() @ rootM.inverted() @ M
            tracks[(bone, 'loc')].append(tuple(Bm.to_translation()))
            tracks[(bone, 'rot')].append(tuple(math.degrees(a) for a in Bm.to_euler('XYZ')))
    return tracks


def add_prop_keys2(clip, states):
    tr = compute_prop_tracks2(clip.frames, states)
    for (bone, kind), arr in tr.items():
        arr = np.array(arr)
        for i in range(3):
            d = clip.keys.setdefault((bone, kind, i), {})
            for f in range(0, clip.frames + 1):
                d[f] = float(arr[f, i])


def finalize_clip(clip, ctl, skel, states=None):
    """Write the action, add prop follow keys, rewrite the action. states may be f(frame) or f(frame, ev)."""
    if states is None:
        st2 = lambda f, ev: {'cell': 'slot', 'beacon': 'dock'}
    else:
        import inspect
        n = len(inspect.signature(states).parameters)
        st2 = states if n >= 2 else (lambda f, ev, _s=states: _s(f))
    act = AL.write_action(ctl, clip)
    AL.assign_action(ctl, act)
    add_prop_keys2(clip, st2)
    act = AL.write_action(ctl, clip)
    return act
