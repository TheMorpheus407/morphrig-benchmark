"""Authoritative joint table and deformation-skeleton definition for the Operative.

Conventions (Blender scene space, metres):
  +Z up, character faces -Y, character's left is +X, ground plane z = 0, origin between the feet.
Bone local axes: Y runs head->tail, Z is aligned to the z_hint given here, X = Y x Z.
Right-side bones are exact X mirrors of the left ones (Blender symmetric convention:
mirrored Y/Z, X = -mirror(X)), so that equal local X rotations give symmetric flexion.
"""
import math
import numpy as np
from .util import V, norm, mirror_x, frame_from

HEIGHT = 1.80

# ---------------------------------------------------------------------------------- joints
J = {}
J['root'] = V(0, 0, 0)
J['pelvis'] = V(0, 0.006, 0.985)
J['spine_01'] = V(0, 0.010, 1.062)
J['spine_02'] = V(0, 0.016, 1.172)
J['spine_03'] = V(0, 0.022, 1.298)
J['spine_end'] = V(0, 0.022, 1.455)
J['neck_01'] = V(0, 0.018, 1.497)
J['head'] = V(0, 0.002, 1.590)
J['head_end'] = V(0, 0.002, 1.800)

# arm (left). A-pose: 47 deg below horizontal, 3 deg forward; elbow pre-bent 12 deg forward.
ARM_DOWN = math.radians(47.0)
J['clavicle_l'] = V(0.020, -0.034, 1.450)
J['upperarm_l'] = V(0.165, 0.012, 1.452)
_d_upper = norm(V(math.cos(ARM_DOWN), -0.05, -math.sin(ARM_DOWN)))
L_UPPER, L_LOWER = 0.283, 0.252
J['lowerarm_l'] = J['upperarm_l'] + L_UPPER * _d_upper
_d_lower = norm(_d_upper + 0.21 * V(0, -1, 0))
J['hand_l'] = J['lowerarm_l'] + L_LOWER * _d_lower
ARM_D_UPPER = _d_upper
ARM_D_LOWER = _d_lower

# hand frame (left): d = distal, t = thumb/radial side (forward in A pose), p = palmar normal
HAND_D = _d_lower
HAND_T = norm(V(0, -1, 0) - HAND_D * np.dot(V(0, -1, 0), HAND_D))
HAND_P = np.cross(HAND_D, HAND_T)


def hand_pt(d, t, p):
    return J['hand_l'] + d * HAND_D + t * HAND_T + p * HAND_P


def hand_dir(d, t, p):
    return norm(d * HAND_D + t * HAND_T + p * HAND_P)


# finger tables: name -> (mcp (d,t,p), direction (d,t,p), phalanx lengths, base radius, tip radius)
FINGERS = {
    'index':  ((0.0930, 0.0275, -0.0035), (1.0, 0.075, 0.03), (0.0400, 0.0245, 0.0215), 0.0086, 0.0070),
    'middle': ((0.0965, 0.0065, -0.0040), (1.0, 0.010, 0.03), (0.0440, 0.0275, 0.0225), 0.0089, 0.0072),
    'ring':   ((0.0905, -0.0135, -0.0035), (1.0, -0.055, 0.03), (0.0405, 0.0255, 0.0215), 0.0083, 0.0068),
    'pinky':  ((0.0800, -0.0320, -0.0020), (1.0, -0.150, 0.03), (0.0315, 0.0190, 0.0190), 0.0073, 0.0061),
}
THUMB = ((0.0220, 0.0250, 0.0090), (0.62, 0.66, 0.42), (0.0410, 0.0310, 0.0270), 0.0108, 0.0086)

for _name, (_mcp, _dir, _lens, _rb, _rt) in list(FINGERS.items()) + [('thumb', THUMB)]:
    _p = hand_pt(*_mcp)
    _dv = hand_dir(*_dir)
    for _i, _l in enumerate(_lens):
        J['%s_%02d_l' % (_name, _i + 1)] = _p.copy()
        _p = _p + _l * _dv
    J['%s_end_l' % _name] = _p.copy()

# leg (left)
J['thigh_l'] = V(0.092, 0.006, 0.955)
J['calf_l'] = V(0.097, -0.016, 0.518)
J['foot_l'] = V(0.102, 0.020, 0.098)
J['ball_l'] = V(0.105, -0.122, 0.028)
J['toe_end_l'] = V(0.107, -0.212, 0.028)

# face
EYE_R = 0.0126
J['eye_l'] = V(0.0320, -0.0760, 1.6720)
J['jaw'] = V(0, 0.012, 1.650)
J['jaw_end'] = V(0, -0.088, 1.562)
J['tongue_01'] = V(0, -0.032, 1.5960)
J['tongue_02'] = V(0, -0.064, 1.5955)
J['tongue_end'] = V(0, -0.093, 1.5945)

# secondary cable (braided data-cable tail from the occipital port)
J['cable_01'] = V(0, 0.0905, 1.668)
J['cable_02'] = V(0, 0.1080, 1.622)
J['cable_03'] = V(0, 0.1180, 1.574)
J['cable_04'] = V(0, 0.1240, 1.524)
J['cable_end'] = V(0, 0.1280, 1.476)

FWD = V(0, -1, 0)
UP = V(0, 0, 1)
BACK = V(0, 1, 0)

# ---------------------------------------------------------------------------------- bones
# (name, parent, head, tail, z_hint, flags)   flags: 'D' deform, 'T' twist, 'H' helper, 'P' prop, 'F' face, 'S' secondary
BONES = []


def _b(name, parent, head, tail, zhint, flags='D'):
    BONES.append(dict(name=name, parent=parent, head=np.array(head, float), tail=np.array(tail, float),
                      zhint=np.array(zhint, float), flags=flags))


def _along(a, b, f):
    return a + (b - a) * f


# root rest matrix is the identity (Y towards +Y, Z up) so that the Unreal root bone is unrotated
_b('root', None, J['root'], J['root'] + V(0, 0.20, 0), UP)
_b('pelvis', 'root', J['pelvis'], J['spine_01'], FWD)
_b('spine_01', 'pelvis', J['spine_01'], J['spine_02'], FWD)
_b('spine_02', 'spine_01', J['spine_02'], J['spine_03'], FWD)
_b('spine_03', 'spine_02', J['spine_03'], J['spine_end'], FWD)
_b('neck_01', 'spine_03', J['neck_01'], J['head'], FWD)
_b('head', 'neck_01', J['head'], J['head_end'], FWD)

# left chain definitions, mirrored below
_SIDE = []


def _s(name, parent, head, tail, zhint, flags='D'):
    _SIDE.append((name, parent, np.array(head, float), np.array(tail, float), np.array(zhint, float), flags))


_s('clavicle_l', 'spine_03', J['clavicle_l'], J['upperarm_l'], FWD)
_s('upperarm_l', 'clavicle_l', J['upperarm_l'], J['lowerarm_l'], FWD)
_s('upperarm_twist_l', 'upperarm_l', J['upperarm_l'], _along(J['upperarm_l'], J['lowerarm_l'], 0.40), FWD, 'DT')
_s('shoulder_helper_l', 'clavicle_l', J['upperarm_l'], _along(J['upperarm_l'], J['lowerarm_l'], 0.25), FWD, 'DH')
_s('lowerarm_l', 'upperarm_l', J['lowerarm_l'], J['hand_l'], FWD)
_s('elbow_helper_l', 'upperarm_l', J['lowerarm_l'], _along(J['lowerarm_l'], J['hand_l'], 0.22), FWD, 'DH')
_s('lowerarm_twist_l', 'lowerarm_l', _along(J['lowerarm_l'], J['hand_l'], 0.55), J['hand_l'], FWD, 'DT')
_s('hand_l', 'lowerarm_l', J['hand_l'], hand_pt(0.070, 0.004, 0.0), HAND_T)
for _name in ['thumb', 'index', 'middle', 'ring', 'pinky']:
    _zh = HAND_P if _name != 'thumb' else hand_dir(0.25, -0.75, 0.62)
    _par = 'hand_l'
    for _i in range(3):
        _n = '%s_%02d_l' % (_name, _i + 1)
        _nx = '%s_%02d_l' % (_name, _i + 2) if _i < 2 else '%s_end_l' % _name
        _s(_n, _par, J[_n], J[_nx], _zh)
        _par = _n
_s('thigh_l', 'pelvis', J['thigh_l'], J['calf_l'], FWD)
_s('thigh_twist_l', 'thigh_l', J['thigh_l'], _along(J['thigh_l'], J['calf_l'], 0.40), FWD, 'DT')
_s('hip_helper_l', 'pelvis', J['thigh_l'], _along(J['thigh_l'], J['calf_l'], 0.22), FWD, 'DH')
_s('calf_l', 'thigh_l', J['calf_l'], J['foot_l'], FWD)
_s('knee_helper_l', 'thigh_l', J['calf_l'], _along(J['calf_l'], J['foot_l'], 0.20), FWD, 'DH')
_s('foot_l', 'calf_l', J['foot_l'], J['ball_l'], UP)
_s('ball_l', 'foot_l', J['ball_l'], J['toe_end_l'], UP)
_s('eye_l', 'head', J['eye_l'], J['eye_l'] + V(0, -0.030, 0), UP, 'DF')
_s('lid_upper_l', 'head', J['eye_l'], J['eye_l'] + V(0, -0.022, 0.006), UP, 'DF')
_s('lid_lower_l', 'head', J['eye_l'], J['eye_l'] + V(0, -0.022, -0.006), UP, 'DF')


def mirror_name(n):
    if n.endswith('_l'):
        return n[:-2] + '_r'
    if n.endswith('_r'):
        return n[:-2] + '_l'
    return n


for (_n, _p, _h, _t, _z, _f) in _SIDE:
    _b(_n, _p, _h, _t, _z, _f)
for (_n, _p, _h, _t, _z, _f) in _SIDE:
    _b(mirror_name(_n), mirror_name(_p), mirror_x(_h), mirror_x(_t), mirror_x(_z), _f)
    J[mirror_name(_n)] = mirror_x(_h)

_b('jaw', 'head', J['jaw'], J['jaw_end'], V(0, 0, -1), 'DF')
_b('tongue_01', 'jaw', J['tongue_01'], J['tongue_02'], UP, 'DF')
_b('tongue_02', 'tongue_01', J['tongue_02'], J['tongue_end'], UP, 'DF')
_b('cable_01', 'head', J['cable_01'], J['cable_02'], BACK, 'DS')
_b('cable_02', 'cable_01', J['cable_02'], J['cable_03'], BACK, 'DS')
_b('cable_03', 'cable_02', J['cable_03'], J['cable_04'], BACK, 'DS')
_b('cable_04', 'cable_03', J['cable_04'], J['cable_end'], BACK, 'DS')

for _k in list(J.keys()):
    if _k.endswith('_l') and mirror_name(_k) not in J:
        J[mirror_name(_k)] = mirror_x(J[_k])

BONE_BY_NAME = {b['name']: b for b in BONES}


def add_bone(name, parent, head, tail, zhint, flags='D'):
    """Used by prop/accessory generators to register extra bones (blade, cell, beacon ...)."""
    if name in BONE_BY_NAME:
        return
    _b(name, parent, head, tail, zhint, flags)
    BONE_BY_NAME[name] = BONES[-1]
    J[name] = np.array(head, float)


def bone_frame(name):
    b = BONE_BY_NAME[name]
    return frame_from(b['tail'] - b['head'], b['zhint'])


def bone_matrix(name):
    """4x4 armature-space rest matrix (columns X,Y,Z,head)."""
    b = BONE_BY_NAME[name]
    m = np.eye(4)
    m[:3, :3] = bone_frame(name)
    m[:3, 3] = b['head']
    return m


def children_of(name):
    return [b['name'] for b in BONES if b['parent'] == name]


# ---------------------------------------------------------------------------------- prop bones
def _arm_frame(side='l'):
    """(origin elbow, distal dir, dorsal/outer dir, radial/front dir) of the forearm."""
    e, w = J['lowerarm_l'], J['hand_l']
    d = norm(w - e)
    fr = frame_from(d, FWD)
    dorsal = -fr[:, 0]
    radial = fr[:, 2]
    if side == 'r':
        return mirror_x(e), mirror_x(d), mirror_x(dorsal), mirror_x(radial)
    return e, d, dorsal, radial


_e, _d, _dor, _rad = _arm_frame('l')
# forearm blade (left): slides along its own Y axis; rest = retracted
BLADE_TRAVEL = 0.205
_blade_head = _e + _d * 0.060 + _dor * 0.047
_b('blade_l', 'lowerarm_l', _blade_head, _blade_head + _d * 0.30, _dor, 'DP')
J['blade_l'] = _blade_head
_e, _d, _dor, _rad = _arm_frame('r')
# emitter power cell (right forearm): local Y = eject direction (dorsal)
_cell_head = _e + _d * 0.105 + _dor * 0.050
_b('prop_cell', 'lowerarm_r', _cell_head, _cell_head + _dor * 0.06, _d, 'DP')
J['prop_cell'] = _cell_head
EMITTER_MUZZLE = _e + _d * 0.262 + _dor * 0.047
EMITTER_DIR = _d.copy()
CELL_SLOT_DIR = _dor.copy()
# spare cell on the belt (left hip) and the deployable beacon (back of the belt, right side)
_spare = V(0.150, -0.045, 1.035)
_b('prop_cell_spare', 'pelvis', _spare, _spare + V(0, 0, 0.06), V(1, 0, 0), 'DP')
J['prop_cell_spare'] = _spare
# rear (empty) belt cradle; finalised by cyber.build_belt_props once the belt surface is known
REAR_CRADLE = dict(head=_spare + V(-0.012, 0.036, 0.0), tail=_spare + V(-0.012, 0.036, 0.06), zhint=V(1.0, 0.0, 0.0))
_beacon = V(-0.075, 0.128, 1.040)
_b('prop_beacon', 'pelvis', _beacon, _beacon + V(0, 0, 0.06), V(0, 1, 0), 'DP')
J['prop_beacon'] = _beacon
BONE_BY_NAME.update({b['name']: b for b in BONES})

# ---------------------------------------------------------------------------------- sockets
# name -> (bone, armature-space position, forward axis, up axis)  [forward = +X of the Unreal socket, up = +Z]
SOCKETS = {}


def socket(name, bone, pos, fwd, up):
    SOCKETS[name] = dict(name=name, bone=bone, pos=np.array(pos, float), fwd=norm(np.array(fwd, float)), up=norm(np.array(up, float)))


def _palm(side):
    p = hand_pt(0.062, 0.004, 0.016)
    f = HAND_D
    u = HAND_T
    if side == 'r':
        return mirror_x(p), mirror_x(f), mirror_x(u)
    return p, f, u


def rebuild_sockets():
    SOCKETS.clear()
    for s in ('l', 'r'):
        p, f, u = _palm(s)
        socket('hand_%s_socket' % s, 'hand_' + s, p, f, u)
    e, d, dor, rad = _arm_frame('r')
    socket('emitter_muzzle', 'lowerarm_r', EMITTER_MUZZLE, EMITTER_DIR, dor)
    socket('cell_slot', 'lowerarm_r', J['prop_cell'], CELL_SLOT_DIR, EMITTER_DIR)
    e, d, dor, rad = _arm_frame('l')
    socket('blade_base', 'blade_l', J['blade_l'] + d * 0.06, d, dor)
    socket('blade_tip', 'blade_l', J['blade_l'] + d * 0.30, d, dor)
    socket('fx_chest', 'spine_03', V(0, -0.115, 1.36), FWD, UP)
    socket('fx_back', 'spine_03', V(0, 0.125, 1.38), BACK, UP)
    socket('fx_head', 'head', V(0, 0.0, 1.83), FWD, UP)
    socket('fx_root', 'root', V(0, 0, 0), FWD, UP)
    socket('beacon_mount', 'pelvis', J['prop_beacon'], BACK, UP)
    socket('cell_pouch', 'pelvis', J['prop_cell_spare'], V(1, 0, 0), UP)
    socket('cell_cradle_rear', 'pelvis', REAR_CRADLE['head'], REAR_CRADLE['zhint'], UP)
    socket('foot_l_socket', 'foot_l', V(J['foot_l'][0], J['foot_l'][1] - 0.06, 0.0), FWD, UP)
    socket('foot_r_socket', 'foot_r', V(J['foot_r'][0], J['foot_r'][1] - 0.06, 0.0), FWD, UP)


rebuild_sockets()


def to_unreal_pos(p):
    """Blender armature space (m) -> Unreal component space (cm): (x, -y, z) * 100."""
    return [float(p[0]) * 100.0, float(-p[1]) * 100.0, float(p[2]) * 100.0]


def rear_cradle_matrix():
    """Rest matrix (armature space, prop-bone axis convention) of a cell parked in the rear belt cradle."""
    m = np.eye(4)
    m[:3, :3] = frame_from(REAR_CRADLE['tail'] - REAR_CRADLE['head'], REAR_CRADLE['zhint'])
    m[:3, 3] = REAR_CRADLE['head']
    return m


def place_bone(name, head, tail, zhint=None):
    """Re-position a registered bone (used by prop generators once their mounts are known)."""
    b = BONE_BY_NAME[name]
    b['head'] = np.array(head, float)
    b['tail'] = np.array(tail, float)
    if zhint is not None:
        b['zhint'] = np.array(zhint, float)
    J[name] = b['head'].copy()
    rebuild_sockets()
