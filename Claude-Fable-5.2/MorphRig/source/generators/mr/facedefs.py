"""Facial rig vocabulary: morph targets, animator controls, viseme and expression presets.

Controls are 0..1 channels. A control can drive a morph target of the same name, face bones, or both.
Visemes and expressions are documented linear combinations of controls (no proprietary standard assumed).
Final channel value = clamp(direct control + sum(viseme_i * w) + sum(expression_j * w)).
"""

# ---- morph targets (Blender shape keys == Unreal morph targets, identical names)
MORPHS = [
    'brow_inner_up_l', 'brow_inner_up_r', 'brow_outer_up_l', 'brow_outer_up_r', 'brow_down_l', 'brow_down_r',
    'squint_l', 'squint_r', 'cheek_raise_l', 'cheek_raise_r', 'cheek_puff_l', 'cheek_puff_r',
    'nose_sneer_l', 'nose_sneer_r',
    'smile_l', 'smile_r', 'frown_l', 'frown_r', 'mouth_wide_l', 'mouth_wide_r',
    'upper_lip_up_l', 'upper_lip_up_r', 'lower_lip_down_l', 'lower_lip_down_r',
    'pucker', 'funnel', 'lip_press', 'mouth_close', 'lip_roll_upper', 'lip_roll_lower', 'labiodental', 'chin_raise',
]

# ---- bone driven controls: control -> list of (bone, kind, axis, amount)   kind 'rot' (degrees, bone local) / 'loc' (metres)
BONE_CONTROLS = {
    'jaw_open': [('jaw', 'rot', 'X', 21.0)],
    'jaw_left': [('jaw', 'rot', 'Z', 5.0)],
    'jaw_right': [('jaw', 'rot', 'Z', -5.0)],
    'jaw_forward': [('jaw', 'loc', 'Y', 0.0035)],
    'blink_l': [('lid_upper_l', 'rot', 'X', -40.5), ('lid_lower_l', 'rot', 'X', 11.0)],
    'blink_r': [('lid_upper_r', 'rot', 'X', -40.5), ('lid_lower_r', 'rot', 'X', 11.0)],
    'eye_wide_l': [('lid_upper_l', 'rot', 'X', 9.0), ('lid_lower_l', 'rot', 'X', -3.0)],
    'eye_wide_r': [('lid_upper_r', 'rot', 'X', 9.0), ('lid_lower_r', 'rot', 'X', -3.0)],
    'squint_l': [('lid_lower_l', 'rot', 'X', 10.0), ('lid_upper_l', 'rot', 'X', -6.0)],
    'squint_r': [('lid_lower_r', 'rot', 'X', 10.0), ('lid_upper_r', 'rot', 'X', -6.0)],
    'tongue_up': [('tongue_01', 'rot', 'X', 10.0), ('tongue_02', 'rot', 'X', 32.0)],
    'tongue_out': [('tongue_01', 'loc', 'Y', 0.011)],
}

CONTROLS = MORPHS + [c for c in BONE_CONTROLS if c not in MORPHS]

# eyes are aimed by a look-at target; lids follow the eyeball pitch by these factors
EYE_LOOK = dict(max_yaw_deg=32.0, max_pitch_up_deg=22.0, max_pitch_down_deg=28.0, lid_upper_follow=0.62, lid_lower_follow=0.32)


def _lr(d):
    """expand keys ending with '*' to _l/_r"""
    out = {}
    for k, v in d.items():
        if k.endswith('*'):
            out[k[:-1] + '_l'] = v
            out[k[:-1] + '_r'] = v
        else:
            out[k] = v
    return out


# ---- visemes: name -> (phoneme classes, {control: weight})
VISEMES = {
    'sil': ('silence / rest', {}),
    'PP': ('lip closure: p b m', _lr({'jaw_open': 0.05, 'lip_press': 0.75, 'mouth_close': 0.20, 'lip_roll_upper': 0.25, 'lip_roll_lower': 0.25})),
    'FF': ('labiodental: f v', _lr({'jaw_open': 0.10, 'labiodental': 1.0, 'upper_lip_up*': 0.18})),
    'TH': ('tongue to teeth: th dh', _lr({'jaw_open': 0.17, 'tongue_out': 0.90, 'tongue_up': 0.22, 'mouth_wide*': 0.10})),
    'DD': ('alveolar: t d n l', _lr({'jaw_open': 0.19, 'tongue_up': 0.95, 'mouth_wide*': 0.14})),
    'KK': ('velar: k g ng', _lr({'jaw_open': 0.25, 'mouth_wide*': 0.10})),
    'CH': ('post-alveolar: ch j sh zh', _lr({'jaw_open': 0.14, 'funnel': 0.70, 'pucker': 0.22})),
    'SS': ('sibilant: s z', _lr({'jaw_open': 0.07, 'mouth_wide*': 0.42, 'upper_lip_up*': 0.12, 'lower_lip_down*': 0.16})),
    'RR': ('r-coloured: r er', _lr({'jaw_open': 0.18, 'pucker': 0.42, 'funnel': 0.28})),
    'AA': ('open vowel: aa ah ay(start)', _lr({'jaw_open': 0.64, 'mouth_wide*': 0.12, 'lower_lip_down*': 0.20})),
    'EH': ('mid vowel: eh ae uh schwa', _lr({'jaw_open': 0.38, 'mouth_wide*': 0.28})),
    'EE': ('wide vowel: iy ih y', _lr({'jaw_open': 0.15, 'mouth_wide*': 0.62, 'smile*': 0.14, 'upper_lip_up*': 0.10})),
    'OH': ('rounded vowel: ow ao', _lr({'jaw_open': 0.42, 'funnel': 0.75, 'pucker': 0.15})),
    'OO': ('tight rounded vowel: uw w', _lr({'jaw_open': 0.14, 'pucker': 0.85, 'funnel': 0.20})),
}

# ---- expression presets
EXPRESSIONS = {
    'neutral': {},
    'joy': _lr({'smile*': 0.78, 'cheek_raise*': 0.60, 'squint*': 0.22, 'brow_outer_up*': 0.18, 'jaw_open': 0.04}),
    'anger': _lr({'brow_down*': 0.92, 'nose_sneer*': 0.55, 'squint*': 0.38, 'lip_press': 0.45, 'frown*': 0.30,
                  'upper_lip_up*': 0.18, 'jaw_forward': 0.5}),
    'concern': _lr({'brow_inner_up*': 0.95, 'frown*': 0.52, 'chin_raise': 0.42, 'blink*': 0.14, 'mouth_close': 0.1}),
    'surprise': _lr({'brow_inner_up*': 0.78, 'brow_outer_up*': 0.92, 'eye_wide*': 1.0, 'jaw_open': 0.36, 'funnel': 0.18}),
    'pain': _lr({'brow_down*': 0.72, 'brow_inner_up*': 0.50, 'squint*': 0.85, 'cheek_raise*': 0.72, 'nose_sneer*': 0.70,
                 'upper_lip_up*': 0.50, 'mouth_wide*': 0.48, 'jaw_open': 0.20, 'blink*': 0.35}),
    'focus': _lr({'brow_down*': 0.36, 'squint*': 0.30, 'lip_press': 0.24, 'blink*': 0.08}),
}
