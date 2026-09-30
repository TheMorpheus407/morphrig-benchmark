"""Operative deformation skeleton: single source of truth (pure Python, no bpy).

Conventions (documented in docs/rig_usage.md and docs/skeleton_and_sockets.json):
  * Units: metres in the Blender source. The FBX export is baked to centimetres (see tools/export_and_bake.py).
  * Blender axes: Z up, the character faces +X, the character's LEFT side is +Y. Ground origin between the feet.
    Unreal receives (x, -y, z), so the character faces +X in Unreal and its left side is -Y there.
  * Bone frame: local Y runs head->tail; local Z is the 'flexion direction' hint given per bone; local X = Y x Z.
    For limbs and spine +X rotation is forward flexion. Right-side bones are exact X-mirrors of left-side bones.
  * Exactly one root ('root', at the ground origin). Pelvis is its child.
"""
import math

# ----------------------------------------------------------------------------- small vector helpers


def v(x, y, z):
    return (float(x), float(y), float(z))


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    l = length(a)
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 0.0, 0.0)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def rot_about(vec, axis, deg):
    """Rodrigues rotation of vec about unit axis by deg."""
    a = math.radians(deg)
    k = norm(axis)
    c, s = math.cos(a), math.sin(a)
    return add(add(mul(vec, c), mul(cross(k, vec), s)), mul(k, dot(k, vec) * (1 - c)))


def mirror(p):
    """Mirror across the sagittal plane (Y -> -Y)."""
    return (p[0], -p[1], p[2])


# ----------------------------------------------------------------------------- body landmarks (left side, metres)

HEIGHT = 1.80
F = (1.0, 0.0, 0.0)   # forward
L = (0.0, 1.0, 0.0)   # character left
U = (0.0, 0.0, 1.0)   # up

HIP_Y = 0.090
PELVIS_H = v(-0.005, 0.0, 0.965)
HIP = v(0.0, HIP_Y, 0.940)
KNEE = v(0.010, 0.096, 0.512)
ANKLE = v(-0.008, 0.100, 0.088)
BALL = v(0.128, 0.100, 0.030)
TOE_TIP = v(0.200, 0.100, 0.018)

SPINE = {
    'pelvis': (v(-0.005, 0, 0.965), v(-0.003, 0, 1.045)),
    'spine_01': (v(-0.003, 0, 1.045), v(0.0, 0, 1.175)),
    'spine_02': (v(0.0, 0, 1.175), v(0.0, 0, 1.315)),
    'spine_03': (v(0.0, 0, 1.315), v(0.005, 0, 1.490)),
    'neck_01': (v(0.005, 0, 1.490), v(0.010, 0, 1.545)),
    'neck_02': (v(0.010, 0, 1.545), v(0.012, 0, 1.600)),
    'head': (v(0.012, 0, 1.600), v(0.004, 0, 1.800)),
}

SHOULDER = v(-0.008, 0.185, 1.462)
CLAVICLE_H = v(0.020, 0.020, 1.462)
UPPERARM_LEN = 0.330
FOREARM_LEN = 0.265
UPPERARM_DIR = norm(v(0.02, math.sin(math.radians(32)), -math.cos(math.radians(32))))
FOREARM_DIR = norm(v(0.16, 0.50, -0.85))
ELBOW = add(SHOULDER, mul(UPPERARM_DIR, UPPERARM_LEN))
WRIST = add(ELBOW, mul(FOREARM_DIR, FOREARM_LEN))
HAND_DIR = norm(v(0.20, 0.47, -0.86))
PALM_LEN = 0.090

# palm frame: Y_h = HAND_DIR, N = palm normal (toward the body, -Y for the left hand), S = thumb side (forward)
_PN = norm(sub((0.0, -1.0, 0.0), mul(HAND_DIR, dot((0.0, -1.0, 0.0), HAND_DIR))))
_PS = norm(cross(_PN, HAND_DIR))  # right-handed: N x Y_h ; sign checked below
if dot(_PS, F) < 0:
    _PS = mul(_PS, -1.0)
PALM_NORMAL = _PN
PALM_SIDE = _PS

FINGERS = {
    #            mcp offset along S, spread deg, (prox, mid, dist) lengths
    'index': (0.031, +6.0, (0.040, 0.024, 0.020)),
    'middle': (0.011, 0.0, (0.043, 0.026, 0.021)),
    'ring': (-0.010, -5.0, (0.040, 0.025, 0.020)),
    'pinky': (-0.030, -11.0, (0.032, 0.019, 0.017)),
}
FINGER_CURL_DEG = 7.0   # relaxed rest curl per joint (about the palm-side axis)
THUMB_LENS = (0.046, 0.036, 0.029)


def _finger_chain(name, side_sign=1.0):
    """Return list of (bone, head, tail) for one hand's finger bones in left-hand space (unmirrored)."""
    out = []
    wrist = WRIST
    mcp_center = add(wrist, mul(HAND_DIR, PALM_LEN))
    for fname, (s_off, spread, lens) in FINGERS.items():
        mcp = add(mcp_center, mul(PALM_SIDE, s_off))
        meta_head = add(add(wrist, mul(HAND_DIR, 0.012)), mul(PALM_SIDE, s_off * 0.45))
        d = rot_about(HAND_DIR, PALM_NORMAL, -spread)     # fan out in the palm plane
        curl_axis = cross(d, PALM_NORMAL)                  # rotates d toward the palm normal
        out.append((f'{fname}_metacarpal', meta_head, mcp))
        head = mcp
        for i, ln in enumerate(lens):
            d = rot_about(d, curl_axis, -FINGER_CURL_DEG) if i > 0 else rot_about(d, curl_axis, -FINGER_CURL_DEG * 0.5)
            tail = add(head, mul(d, ln))
            out.append((f'{fname}_{i + 1:02d}', head, tail))
            head = tail
    # thumb
    t_head = add(add(add(wrist, mul(HAND_DIR, 0.014)), mul(PALM_SIDE, 0.022)), mul(PALM_NORMAL, 0.006))
    d = rot_about(HAND_DIR, PALM_NORMAL, -38.0)
    d = rot_about(d, cross(d, PALM_NORMAL), -14.0)
    head = t_head
    for i, ln in enumerate(THUMB_LENS):
        tail = add(head, mul(d, ln))
        out.append((f'thumb_{i + 1:02d}', head, tail))
        head = tail
        d = rot_about(d, cross(d, PALM_NORMAL), -9.0)
    return out


# ----------------------------------------------------------------------------- bone table construction


class Bone:
    __slots__ = ('name', 'parent', 'head', 'tail', 'z_hint', 'deform', 'group', 'connect', 'note')

    def __init__(self, name, parent, head, tail, z_hint, deform=True, group='body', connect=False, note=''):
        self.name, self.parent, self.head, self.tail = name, parent, head, tail
        self.z_hint, self.deform, self.group, self.connect, self.note = z_hint, deform, group, connect, note


def _side(name, s):
    return f'{name}_{s}'


def build_bones():
    bones = []

    def B(*a, **k):
        bones.append(Bone(*a, **k))

    B('root', None, v(0, 0, 0), v(0, 0.10, 0), U, group='root', note='single stable root, identity-oriented: local axes = character axes; carries root motion')
    for n, p in (('pelvis', 'root'), ('spine_01', 'pelvis'), ('spine_02', 'spine_01'), ('spine_03', 'spine_02'),
                 ('neck_01', 'spine_03'), ('neck_02', 'neck_01'), ('head', 'neck_02')):
        h, t = SPINE[n]
        B(n, p, h, t, F, group='spine' if n.startswith(('pelvis', 'spine')) else 'head', connect=(n != 'pelvis'))

    # ---- face bones
    head_h = SPINE['head'][0]
    eye_c = v(0.0715, 0.031, 1.6855)
    B('jaw', 'head', v(-0.020, 0.0, 1.635), v(0.065, 0.0, 1.578), F, group='face', note='jaw pivot near the ear line')
    B('tongue_01', 'jaw', v(0.008, 0, 1.612), v(0.032, 0, 1.610), U, group='face')
    B('tongue_02', 'tongue_01', v(0.032, 0, 1.610), v(0.054, 0, 1.610), U, group='face', connect=True)
    B('tongue_03', 'tongue_02', v(0.054, 0, 1.610), v(0.072, 0, 1.610), U, group='face', connect=True)
    for s, sy in (('l', 1.0), ('r', -1.0)):
        ec = v(eye_c[0], sy * eye_c[1], eye_c[2])
        B(_side('eye', s), 'head', ec, add(ec, v(0.020, 0, 0)), U, group='face', note='eyeball pivot = eyeball centre')
        B(_side('lid_up', s), 'head', ec, add(ec, v(0.018, 0, 0)), U, group='face', note='upper lid, pivots about the eyeball centre')
        B(_side('lid_lo', s), 'head', ec, add(ec, v(0.018, 0, 0)), U, group='face', note='lower lid, pivots about the eyeball centre')

    # ---- braid (secondary motion), hangs from the back of the head
    hair_pts = [v(-0.084, 0, 1.700), v(-0.098, 0, 1.652), v(-0.104, 0, 1.604), v(-0.106, 0, 1.556), v(-0.106, 0, 1.508), v(-0.106, 0, 1.460)]
    prev = 'head'
    for i in range(5):
        n = f'hair_{i + 1:02d}'
        B(n, prev, hair_pts[i], hair_pts[i + 1], F, group='secondary', connect=i > 0, note='braid chain (secondary motion)')
        prev = n

    # ---- arms, legs, hands (left side authored, right mirrored)
    def limb_side(s, sy):
        def m(p):
            return (p[0], sy * p[1], p[2])

        def mh(vec):  # mirror a direction hint
            return (vec[0], sy * vec[1], vec[2])
        B(_side('clavicle', s), 'spine_03', m(CLAVICLE_H), m(SHOULDER), F, group='arm')
        B(_side('upperarm', s), _side('clavicle', s), m(SHOULDER), m(ELBOW), F, group='arm', connect=True)
        B(_side('lowerarm', s), _side('upperarm', s), m(ELBOW), m(WRIST), F, group='arm', connect=True)
        B(_side('hand', s), _side('lowerarm', s), m(WRIST), m(add(WRIST, mul(HAND_DIR, PALM_LEN))), mh(PALM_NORMAL), group='hand', connect=True)
        # twist bones (fractions along the segment)
        for seg, a, b_, parent in (('upperarm', SHOULDER, ELBOW, 'upperarm'), ('lowerarm', ELBOW, WRIST, 'lowerarm')):
            for i, (f0, f1) in enumerate(((0.10, 0.50), (0.50, 0.90))):
                B(f'{seg}_twist_{i + 1:02d}_{s}', f'{parent}_{s}', m(lerp(a, b_, f0)), m(lerp(a, b_, f1)), F, group='twist',
                  note='twist distribution bone')
        # half-angle correctives
        B(_side('shoulder_half', s), _side('clavicle', s), m(add(SHOULDER, v(0, 0, 0.02))), m(add(SHOULDER, v(0, 0.045, 0.02))), F, group='corrective',
          note='half-angle corrective at the shoulder')
        B(_side('elbow_half', s), _side('upperarm', s), m(ELBOW), m(add(ELBOW, mul(FOREARM_DIR, 0.05))), F, group='corrective',
          note='half-angle corrective at the elbow')
        B(_side('wrist_half', s), _side('lowerarm', s), m(WRIST), m(add(WRIST, mul(HAND_DIR, 0.04))), mh(PALM_NORMAL), group='corrective',
          note='half-angle corrective at the wrist')
        # fingers
        for name, head, tail in _finger_chain('x'):
            base = name.rsplit('_', 1)[0]
            idx = name.split('_')[-1]
            if name.endswith('metacarpal'):
                parent = _side('hand', s)
            elif name.startswith('thumb'):
                parent = _side('hand', s) if idx == '01' else _side(f'thumb_{int(idx) - 1:02d}', s)
            else:
                parent = _side(f'{base}_metacarpal', s) if idx == '01' else _side(f'{base}_{int(idx) - 1:02d}', s)
            B(_side(name, s), parent, m(head), m(tail), mh(PALM_NORMAL), group='finger', connect=(idx != '01' and not name.endswith('metacarpal')) or name.startswith('thumb') and idx != '01')
        # legs
        B(_side('thigh', s), 'pelvis', m(HIP), m(KNEE), F, group='leg')
        B(_side('calf', s), _side('thigh', s), m(KNEE), m(ANKLE), F, group='leg', connect=True)
        B(_side('foot', s), _side('calf', s), m(ANKLE), m(BALL), U, group='leg', connect=True)
        B(_side('ball', s), _side('foot', s), m(BALL), m(TOE_TIP), U, group='leg', connect=True)
        for seg, a, b_ in (('thigh', HIP, KNEE), ('calf', KNEE, ANKLE)):
            for i, (f0, f1) in enumerate(((0.10, 0.50), (0.50, 0.90))):
                B(f'{seg}_twist_{i + 1:02d}_{s}', _side(seg, s), m(lerp(a, b_, f0)), m(lerp(a, b_, f1)), F, group='twist', note='twist distribution bone')
        B(_side('hip_half', s), 'pelvis', m(HIP), m(add(HIP, v(0, 0, -0.05))), F, group='corrective', note='half-angle corrective at the hip')
        B(_side('knee_half', s), _side('thigh', s), m(KNEE), m(add(KNEE, mul(norm(sub(ANKLE, KNEE)), 0.05))), F, group='corrective',
          note='half-angle corrective at the knee')

    limb_side('l', 1.0)
    limb_side('r', -1.0)

    # ---- cyber forearm parts (left side only) and props
    lw = WRIST
    fdir = FOREARM_DIR
    # outward/dorsal offset direction for the blade slot: away from the body, perpendicular to the forearm
    slot_dir = norm(sub(v(0.0, 1.0, 0.0), mul(fdir, dot(v(0.0, 1.0, 0.0), fdir))))
    blade_head = add(add(ELBOW, mul(fdir, 0.024)), mul(slot_dir, 0.046))
    B('blade', 'lowerarm_l', blade_head, add(blade_head, mul(fdir, 0.06)), F, group='prop', note='retractable forearm blade; extend by translating along local Y')
    cab = [add(ELBOW, v(-0.045, 0.0, -0.02))]
    for i in range(5):
        cab.append(add(cab[-1], v(-0.012, -0.012, -0.055)))
    prev = 'lowerarm_l'
    for i in range(5):
        B(f'cable_{i + 1:02d}', prev, cab[i], cab[i + 1], F, group='secondary', connect=i > 0, note='cable chain (secondary motion)')
        prev = f'cable_{i + 1:02d}'
    B('prop_cell', 'root', v(0.11, 0.44, 1.08), v(0.11, 0.44, 1.16), U, group='prop', note='power cell prop bone (character-space); keys follow the forearm slot, hand or pouch')
    B('prop_beacon', 'root', v(-0.10, -0.15, 0.93), v(-0.10, -0.15, 1.00), U, group='prop', note='beacon/drone prop bone (character-space); keys follow the dock, the right hand or the floor')
    return bones


BONES = build_bones()
BONE_BY_NAME = {b.name: b for b in BONES}


def children(name):
    return [b for b in BONES if b.parent == name]


def validate():
    names = [b.name for b in BONES]
    assert len(names) == len(set(names)), 'duplicate bone names'
    roots = [b.name for b in BONES if b.parent is None]
    assert roots == ['root'], f'expected exactly one root, got {roots}'
    seen = set()
    for b in BONES:
        if b.parent is not None:
            assert b.parent in seen, f'{b.name}: parent {b.parent} must precede it'
        seen.add(b.name)
        assert length(sub(b.tail, b.head)) > 1e-4, f'{b.name}: zero length'
    return True


# ----------------------------------------------------------------------------- sockets
# name: (parent bone, position in the Blender rest pose (metres), forward direction hint, up direction hint, purpose)
def _sockets():
    fdir = norm(FOREARM_DIR)
    hd = norm(HAND_DIR)
    pn = norm(PALM_NORMAL)
    dorsal = mul(pn, -1.0)
    slot_dir = norm(sub(v(0.0, 1.0, 0.0), mul(fdir, dot(v(0.0, 1.0, 0.0), fdir))))
    front = norm(sub(v(1.0, 0.0, 0.0), mul(fdir, fdir[0])))
    e_c = add(add(WRIST, mul(hd, 0.036)), mul(dorsal, 0.034))
    blade_base = add(add(ELBOW, mul(fdir, 0.024)), mul(slot_dir, 0.046))
    palm_c = add(WRIST, mul(hd, 0.058))
    sk = {}
    sk['hand_grip_l'] = ('hand_l', palm_c, hd, dorsal, 'left palm grip point (fingers along forward)')
    sk['hand_grip_r'] = ('hand_r', mirror(palm_c), (hd[0], -hd[1], hd[2]), (dorsal[0], -dorsal[1], dorsal[2]), 'right palm grip point')
    sk['emitter_muzzle'] = ('hand_l', add(e_c, mul(hd, 0.096)), hd, dorsal, 'wrist emitter muzzle (fire along forward)')
    sk['blade_base'] = ('blade', blade_base, fdir, slot_dir, 'forearm blade base (sheath rear)')
    sk['blade_tip'] = ('blade', add(blade_base, mul(fdir, 0.258)), fdir, slot_dir, 'blade tip (retracted position, moves with the blade bone)')
    sk['cell_slot'] = ('lowerarm_l', add(add(ELBOW, mul(fdir, 0.150)), mul(front, 0.044)), fdir, front, 'power cell slot on the cybernetic forearm')
    sk['cell_pouch'] = ('pelvis', v(0.055, -0.150, 0.985), v(0, 0, 1), v(1, 0, 0), 'spare power cell pouch (right hip)')
    sk['beacon_dock'] = ('pelvis', v(-0.100, -0.150, 0.925), v(0, 0, 1), v(1, 0, 0), 'beacon dock cup (right hip, rear)')
    sk['prop_cell'] = ('prop_cell', (0.11, 0.44, 1.08), v(1, 0, 0), v(0, 0, 1), 'centre of the power cell prop (mesh is Z-up authored: axes = character axes at rest)')
    sk['prop_beacon'] = ('prop_beacon', (-0.10, -0.15, 0.93), v(1, 0, 0), v(0, 0, 1), 'base centre of the beacon prop (mesh is Z-up authored)')
    sk['fx_chest'] = ('spine_03', v(0.115, 0.0, 1.345), v(1, 0, 0), v(0, 0, 1), 'chest effect anchor')
    sk['fx_back'] = ('spine_03', v(-0.125, 0.0, 1.355), v(-1, 0, 0), v(0, 0, 1), 'back effect anchor')
    sk['fx_head_top'] = ('head', v(0.0, 0.0, 1.84), v(0, 0, 1), v(1, 0, 0), 'effect anchor above the head')
    sk['fx_mouth'] = ('jaw', v(0.090, 0.0, 1.6235), v(1, 0, 0), v(0, 0, 1), 'mouth centre')
    sk['fx_foot_l'] = ('foot_l', v(0.02, 0.10, 0.0), v(1, 0, 0), v(0, 0, 1), 'left foot ground anchor')
    sk['fx_foot_r'] = ('foot_r', v(0.02, -0.10, 0.0), v(1, 0, 0), v(0, 0, 1), 'right foot ground anchor')
    sk['cam_face'] = ('head', v(0.62, 0.0, 1.69), v(-1, 0, 0), v(0, 0, 1), 'close-up camera anchor in front of the face (looks back at the face)')
    sk['eye_l'] = ('eye_l', v(0.0715, 0.031, 1.6855), v(1, 0, 0), v(0, 0, 1), 'left eye centre')
    sk['eye_r'] = ('eye_r', v(0.0715, -0.031, 1.6855), v(1, 0, 0), v(0, 0, 1), 'right eye centre')
    sk['floor_l'] = ('foot_l', v(0.02, 0.10, 0.0), v(1, 0, 0), v(0, 0, 1), 'ground contact reference under the left ankle')
    sk['floor_r'] = ('foot_r', v(0.02, -0.10, 0.0), v(1, 0, 0), v(0, 0, 1), 'ground contact reference under the right ankle')
    return sk


SOCKETS = _sockets()

# ----------------------------------------------------------------------------- morph targets (shape keys)

MORPH_TARGETS = [
    # brows
    'brow_up_in_l', 'brow_up_in_r', 'brow_up_out_l', 'brow_up_out_r', 'brow_down_l', 'brow_down_r', 'brow_pinch',
    # eyes / cheeks / nose
    'squint_l', 'squint_r', 'eye_wide_l', 'eye_wide_r', 'cheek_raise_l', 'cheek_raise_r', 'cheek_puff_l', 'cheek_puff_r',
    'cheek_suck', 'nose_wrinkle_l', 'nose_wrinkle_r', 'nostril_flare_l', 'nostril_flare_r',
    # mouth corners and width
    'mouth_smile_l', 'mouth_smile_r', 'mouth_frown_l', 'mouth_frown_r', 'mouth_wide', 'mouth_narrow', 'dimple_l', 'dimple_r',
    'mouth_shift_l', 'mouth_shift_r',
    # lips
    'mouth_pucker', 'mouth_funnel', 'lip_press', 'lip_up_l', 'lip_up_r', 'lip_down_l', 'lip_down_r', 'lip_roll_up', 'lip_roll_down',
    'lip_tuck_lower', 'chin_raise', 'jaw_open_corr', 'lip_corner_down_l', 'lip_corner_down_r',
]

# ----------------------------------------------------------------------------- viseme map (documented mapping, not a proprietary standard)
# jaw_open in 0..1 (bone 'jaw' rotation up to ~24 deg), 'morphs' are shape key weights.
VISEMES = {
    'sil': {'jaw_open': 0.0, 'morphs': {}},
    'PP': {'jaw_open': 0.05, 'morphs': {'lip_press': 1.0, 'mouth_narrow': 0.2}, 'phonemes': 'p b m'},
    'FF': {'jaw_open': 0.10, 'morphs': {'lip_tuck_lower': 1.0, 'mouth_wide': 0.15}, 'phonemes': 'f v'},
    'TH': {'jaw_open': 0.22, 'morphs': {'lip_up_l': 0.2, 'lip_up_r': 0.2, 'mouth_wide': 0.15}, 'tongue': 0.8, 'phonemes': 'th dh'},
    'DD': {'jaw_open': 0.20, 'morphs': {'mouth_wide': 0.25}, 'tongue': 0.6, 'phonemes': 't d n l'},
    'KK': {'jaw_open': 0.28, 'morphs': {'mouth_wide': 0.20}, 'tongue': 0.3, 'phonemes': 'k g ng'},
    'CH': {'jaw_open': 0.15, 'morphs': {'mouth_pucker': 0.5, 'mouth_funnel': 0.45}, 'phonemes': 'ch jh sh zh'},
    'SS': {'jaw_open': 0.10, 'morphs': {'mouth_wide': 0.45, 'lip_up_l': 0.15, 'lip_up_r': 0.15}, 'tongue': 0.4, 'phonemes': 's z'},
    'RR': {'jaw_open': 0.20, 'morphs': {'mouth_pucker': 0.35, 'mouth_narrow': 0.25}, 'phonemes': 'r er'},
    'AA': {'jaw_open': 0.85, 'morphs': {'lip_down_l': 0.30, 'lip_down_r': 0.30, 'mouth_wide': 0.10}, 'phonemes': 'aa ah ao'},
    'EE': {'jaw_open': 0.35, 'morphs': {'mouth_wide': 0.75, 'mouth_smile_l': 0.20, 'mouth_smile_r': 0.20}, 'phonemes': 'iy ih ey eh ae'},
    'IH': {'jaw_open': 0.40, 'morphs': {'mouth_wide': 0.40}, 'phonemes': 'ih ah ax'},
    'OH': {'jaw_open': 0.55, 'morphs': {'mouth_funnel': 0.75, 'mouth_narrow': 0.35}, 'phonemes': 'ow oy'},
    'OO': {'jaw_open': 0.25, 'morphs': {'mouth_pucker': 1.0, 'mouth_narrow': 0.5}, 'phonemes': 'uw uh w'},
}

# ----------------------------------------------------------------------------- team accent
TEAM_ACCENTS = {
    'A': {'name': 'Cyan / circle icon', 'color_srgb': (0.05, 0.85, 1.0)},
    'B': {'name': 'Magenta / diamond icon', 'color_srgb': (1.0, 0.10, 0.62)},
}


def bone_frame(b):
    """Return (X, Y, Z) unit axes of the bone in rest pose (world/character space)."""
    y = norm(sub(b.tail, b.head))
    z = sub(b.z_hint, mul(y, dot(b.z_hint, y)))
    if length(z) < 1e-6:
        z = cross(y, (1.0, 0.0, 0.0)) if abs(y[0]) < 0.9 else cross(y, (0.0, 1.0, 0.0))
    z = norm(z)
    x = norm(cross(y, z))
    return x, y, z


if __name__ == '__main__':
    import json
    import sys
    validate()
    print('bones:', len(BONES), 'deform bones:', sum(1 for b in BONES if b.deform), 'morph targets:', len(MORPH_TARGETS))
    print('wrist L', tuple(round(c, 3) for c in WRIST), 'elbow L', tuple(round(c, 3) for c in ELBOW))
    if len(sys.argv) > 2 and sys.argv[1] == '--json':
        json.dump([{'name': b.name, 'parent': b.parent, 'head': b.head, 'tail': b.tail, 'group': b.group} for b in BONES], open(sys.argv[2], 'w'), indent=1)
