"""Facial performance helpers: blink, gaze, jaw, viseme mapping and the six expression presets, as anim_lib Poses.

Bone conventions (local axes of the face bones, see skeleton_def): eyes: rot = (pitch up +, 0, yaw left +) degrees;
upper lid closes with negative X rotation, lower lid closes with positive X rotation; jaw opens with negative X rotation."""
import skeleton_def as S
from anim_lib import Pose, lerp_pose

LID_CLOSE_UP = -36.0
LID_CLOSE_LO = 15.0
LID_OPEN_UP = 8.0
JAW_MAX = 24.0


def morphs(**kw):
    p = Pose()
    for k, v in kw.items():
        assert k in S.MORPH_TARGETS, k
        p.prop('ctl_face', k, v)
    return p


def morph_dict(d):
    p = Pose()
    for k, v in d.items():
        assert k in S.MORPH_TARGETS, k
        p.prop('ctl_face', k, v)
    return p


def lids(side, upper_deg=0.0, lower_deg=0.0):
    p = Pose()
    p.rot(f'ctl_lid_up_{side}', (upper_deg, 0, 0))
    p.rot(f'ctl_lid_lo_{side}', (lower_deg, 0, 0))
    return p


def blink(side, amount):
    return lids(side, LID_CLOSE_UP * amount, LID_CLOSE_LO * amount)


def blink_both(amount):
    return blink('l', amount).merged(blink('r', amount))


def gaze(yaw=0.0, pitch=0.0, vergence=0.0):
    """Both eyes look yaw degrees to the character's left and pitch degrees up (independent vergence adds convergence)."""
    p = Pose()
    p.rot('ctl_eye_l', (pitch, 0, yaw - vergence))
    p.rot('ctl_eye_r', (pitch, 0, yaw + vergence))
    return p


def gaze_eye(side, yaw, pitch):
    p = Pose()
    p.rot(f'ctl_eye_{side}', (pitch, 0, yaw))
    return p


def jaw(open01=0.0, side=0.0, forward=0.0):
    p = Pose()
    p.rot('ctl_jaw', (-JAW_MAX * open01, 0, side * 6.0))
    p.loc('ctl_jaw', (0, 0, forward * 0.004))
    return p


def tongue(up01=0.0, curl=0.0):
    p = Pose()
    p.rot('ctl_tongue_01', (-18.0 * up01, 0, 0))
    p.rot('ctl_tongue_02', (-22.0 * up01 - 14.0 * curl, 0, 0))
    p.rot('ctl_tongue_03', (-16.0 * up01 - 24.0 * curl, 0, 0))
    return p


EXPRESSIONS = {
    'neutral': dict(),
    'joy_confidence': dict(morphs=dict(mouth_smile_l=0.78, mouth_smile_r=0.78, cheek_raise_l=0.55, cheek_raise_r=0.55, squint_l=0.28, squint_r=0.28,
                                       brow_up_out_l=0.22, brow_up_out_r=0.22, dimple_l=0.35, dimple_r=0.35, nostril_flare_l=0.1, nostril_flare_r=0.1),
                           jaw=0.07, lid_up=2.0),
    'anger': dict(morphs=dict(brow_down_l=0.95, brow_down_r=0.95, brow_pinch=0.75, nose_wrinkle_l=0.45, nose_wrinkle_r=0.45, nostril_flare_l=0.55,
                              nostril_flare_r=0.55, mouth_frown_l=0.35, mouth_frown_r=0.35, mouth_narrow=0.3, lip_up_l=0.35, lip_up_r=0.35, squint_l=0.3, squint_r=0.3),
                  jaw=0.04, lid_up=-6.0),
    'concern_sadness': dict(morphs=dict(brow_up_in_l=0.9, brow_up_in_r=0.9, brow_down_l=0.15, brow_down_r=0.15, mouth_frown_l=0.6, mouth_frown_r=0.6,
                                        lip_corner_down_l=0.55, lip_corner_down_r=0.55, chin_raise=0.55, lip_roll_down=0.25, cheek_raise_l=0.1, cheek_raise_r=0.1),
                            jaw=0.02, lid_up=-4.0),
    'surprise': dict(morphs=dict(brow_up_in_l=0.9, brow_up_in_r=0.9, brow_up_out_l=0.9, brow_up_out_r=0.9, eye_wide_l=0.95, eye_wide_r=0.95,
                                 mouth_funnel=0.25, nostril_flare_l=0.25, nostril_flare_r=0.25, jaw_open_corr=0.5),
                     jaw=0.5, lid_up=9.0),
    'pain': dict(morphs=dict(brow_up_in_l=0.7, brow_up_in_r=0.7, brow_pinch=0.85, squint_l=0.85, squint_r=0.85, cheek_raise_l=0.55, cheek_raise_r=0.55,
                             mouth_wide=0.55, lip_up_l=0.65, lip_up_r=0.65, mouth_frown_l=0.5, mouth_frown_r=0.5, nose_wrinkle_l=0.65, nose_wrinkle_r=0.65),
                 jaw=0.22, lid_up=-12.0),
    'focus': dict(morphs=dict(brow_down_l=0.38, brow_down_r=0.38, squint_l=0.25, squint_r=0.25, lip_press=0.35, mouth_narrow=0.15),
                  jaw=0.0, lid_up=-3.0),
}


def expression(name, w=1.0, keep_channels=True):
    """Pose for a preset scaled by weight w (all morph channels present so presets can be cross-faded)."""
    e = EXPRESSIONS[name]
    vals = {m: 0.0 for m in S.MORPH_TARGETS} if keep_channels else {}
    for k, v in e.get('morphs', {}).items():
        vals[k] = v * w
    p = morph_dict(vals)
    p.update(jaw(e.get('jaw', 0.0) * w))
    lu = e.get('lid_up', 0.0) * w
    for s in ('l', 'r'):
        p.rot(f'ctl_lid_up_{s}', (lu, 0, 0))
    return p


def viseme(name, w=1.0):
    """Pose for a viseme: jaw opening, morph weights and tongue lift according to skeleton_def.VISEMES."""
    v = S.VISEMES[name]
    p = morph_dict({m: 0.0 for m in S.MORPH_TARGETS})
    for m, val in v['morphs'].items():
        p.prop('ctl_face', m, val * w)
    p.update(jaw(v['jaw_open'] * w))
    p.update(tongue(v.get('tongue', 0.0) * w))
    # corrective for open mouths
    p.prop('ctl_face', 'jaw_open_corr', min(1.0, v['jaw_open'] * w * 1.1))
    return p
