"""Facial shape keys for Operative_Head, procedural region displacement fields (mirrored L/R), with drivers reading the
float properties of the control bone 'ctl_face'. Eyelids, jaw, eyes and tongue are bones (see build_rig)."""
import math
import numpy as np
import bpy
import skeleton_def as S

A = np.array
ZLINE = 1.6235


def _g(P, c, r, vec, amt=1.0):
    d = (P - A(c)) / A(r)
    w = np.exp(-np.sum(d * d, axis=1) * 1.5)
    return (w[:, None] * A(vec)[None, :]) * amt


def _mouth_falloff(P, r=(0.030, 0.046, 0.030)):
    d = (P - A((0.088, 0.0, ZLINE))) / A(r)
    return np.exp(-np.sum(d * d, axis=1) * 1.5)


def masks(P, info):
    up_ids, lo_ids, corners = set(), set(), set()
    for ru, rl in info['mouth']['rings']:
        corners.update([ru[0], ru[-1]])
        up_ids.update(ru[1:-1])
        lo_ids.update(rl[1:-1])
    upper = (P[:, 2] > ZLINE + 0.0004)
    lower = (P[:, 2] < ZLINE - 0.0004)
    up = np.zeros(len(P), dtype=bool)
    lo = np.zeros(len(P), dtype=bool)
    for i in up_ids:
        up[i] = True
    for i in lo_ids:
        lo[i] = True
    return (upper | up) & ~lo, (lower | lo) & ~up


def compute_keys(P, info):
    up, lo = masks(P, info)
    up = up.astype(float)
    lo = lo.astype(float)
    fm = _mouth_falloff(P)
    K = {}
    for s, sy in (('l', 1.0), ('r', -1.0)):
        K[f'brow_up_in_{s}'] = _g(P, (0.083, sy * 0.016, 1.708), (0.014, 0.016, 0.012), (0.0, -sy * 0.0006, 0.0075))
        K[f'brow_up_out_{s}'] = _g(P, (0.078, sy * 0.046, 1.708), (0.016, 0.020, 0.012), (0.0, sy * 0.0004, 0.0065))
        K[f'brow_down_{s}'] = _g(P, (0.082, sy * 0.030, 1.712), (0.018, 0.026, 0.013), (0.0025, 0.0, -0.0065))
        K[f'squint_{s}'] = (_g(P, (0.086, sy * 0.031, 1.6755), (0.020, 0.024, 0.008), (0, 0, 0.0050)) +
                            _g(P, (0.066, sy * 0.047, 1.660), (0.028, 0.028, 0.020), (0.002, 0, 0.0045)))
        K[f'eye_wide_{s}'] = _g(P, (0.089, sy * 0.031, 1.6965), (0.016, 0.022, 0.008), (0, 0, 0.0035)) + _g(P, (0.084, sy * 0.030, 1.708), (0.016, 0.024, 0.010), (0, 0, 0.0025))
        K[f'cheek_raise_{s}'] = _g(P, (0.064, sy * 0.048, 1.652), (0.028, 0.028, 0.022), (0.003, sy * 0.001, 0.006))
        K[f'cheek_puff_{s}'] = _g(P, (0.062, sy * 0.052, 1.640), (0.030, 0.028, 0.026), (0.003, sy * 0.009, 0.0))
        K[f'nose_wrinkle_{s}'] = _g(P, (0.102, sy * 0.011, 1.657), (0.012, 0.010, 0.010), (-0.002, 0, 0.0045)) + _g(P, (0.101, sy * 0.010, 1.634), (0.011, 0.012, 0.008), (0, 0, 0.003)) * up[:, None]
        K[f'nostril_flare_{s}'] = _g(P, (0.102, sy * 0.0160, 1.646), (0.010, 0.008, 0.007), (0, sy * 0.0045, 0.001))
        K[f'mouth_smile_{s}'] = (_g(P, (0.084, sy * 0.027, ZLINE), (0.018, 0.020, 0.014), (-0.003, sy * 0.005, 0.0075)) +
                                 _g(P, (0.070, sy * 0.040, 1.638), (0.024, 0.024, 0.018), (0.002, 0, 0.003)))
        K[f'mouth_frown_{s}'] = _g(P, (0.084, sy * 0.027, ZLINE), (0.018, 0.020, 0.014), (-0.001, -sy * 0.001, -0.0065))
        K[f'dimple_{s}'] = _g(P, (0.078, sy * 0.037, 1.622), (0.007, 0.007, 0.007), (-0.0022, 0, 0))
        K[f'mouth_shift_{s}'] = _g(P, (0.088, 0.0, ZLINE), (0.032, 0.045, 0.030), (0, sy * 0.007, 0))
        K[f'lip_corner_down_{s}'] = _g(P, (0.084, sy * 0.027, ZLINE - 0.002), (0.012, 0.012, 0.010), (0, 0, -0.005))
        K[f'lip_up_{s}'] = _g(P, (0.096, sy * 0.012, 1.6335), (0.010, 0.014, 0.007), (0, 0, 0.004)) * up[:, None]
        K[f'lip_down_{s}'] = _g(P, (0.096, sy * 0.012, 1.612), (0.010, 0.014, 0.007), (0, 0, -0.004)) * lo[:, None]
    # symmetric keys
    K['brow_pinch'] = sum(_g(P, (0.084, sy * 0.010, 1.705), (0.012, 0.012, 0.012), (0.001, -sy * 0.0055, -0.0035)) for sy in (1, -1))
    K['cheek_suck'] = sum(_g(P, (0.058, sy * 0.050, 1.635), (0.030, 0.030, 0.024), (0.0, -sy * 0.008, 0.0)) for sy in (1, -1))
    y = P[:, 1]
    K['mouth_wide'] = np.stack([-0.004 * fm, 0.20 * y * fm, 0 * fm], axis=1)
    K['mouth_narrow'] = np.stack([0.003 * fm, -0.20 * y * fm, 0 * fm], axis=1)
    K['mouth_pucker'] = np.stack([0.010 * fm, -0.28 * y * fm, -(P[:, 2] - ZLINE) * 0.10 * fm], axis=1)
    K['mouth_funnel'] = np.stack([0.006 * fm, -0.10 * y * fm, (0.003 * up - 0.003 * lo) * fm], axis=1)
    K['lip_press'] = np.stack([-0.0015 * fm * (up + lo), 0 * fm, -(P[:, 2] - ZLINE) * 0.30 * fm * (up + lo)], axis=1)
    K['lip_roll_up'] = _g(P, (0.096, 0.0, 1.630), (0.010, 0.026, 0.006), (-0.004, 0, -0.0015)) * up[:, None]
    K['lip_roll_down'] = _g(P, (0.096, 0.0, 1.6165), (0.010, 0.026, 0.006), (-0.004, 0, 0.0015)) * lo[:, None]
    K['lip_tuck_lower'] = _g(P, (0.094, 0.0, 1.617), (0.008, 0.024, 0.008), (-0.008, 0, 0.008)) * lo[:, None]
    K['chin_raise'] = _g(P, (0.086, 0.0, 1.600), (0.014, 0.020, 0.014), (0.002, 0, 0.005))
    K['jaw_open_corr'] = _g(P, (0.095, 0.0, 1.612), (0.010, 0.020, 0.010), (0.003, 0, 0)) + sum(_g(P, (0.084, sy * 0.027, ZLINE), (0.012, 0.012, 0.012), (0, -sy * 0.002, 0)) for sy in (1, -1))
    missing = [n for n in S.MORPH_TARGETS if n not in K]
    assert not missing, missing
    return K


def add_shape_keys(head_obj, info):
    me = head_obj.data
    n = len(me.vertices)
    P = np.empty(n * 3)
    me.vertices.foreach_get('co', P)
    P = P.reshape(-1, 3)
    K = compute_keys(P, info)
    head_obj.shape_key_add(name='Basis', from_mix=False)
    for name in S.MORPH_TARGETS:
        sk = head_obj.shape_key_add(name=name, from_mix=False)
        sk.slider_min, sk.slider_max = 0.0, 1.0
        sk.data.foreach_set('co', (P + K[name]).ravel())
    return K


def add_face_props_and_drivers(ctl, head_obj):
    """Custom float props on ctl_face for every morph plus helper viseme sliders; drivers on the shape-key values."""
    pb = ctl.pose.bones['ctl_face']
    for name in S.MORPH_TARGETS:
        pb[name] = 0.0
        ui = pb.id_properties_ui(name)
        ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, default=0.0)
    for v in S.VISEMES:
        key = 'viseme_' + v
        pb[key] = 0.0
        ui = pb.id_properties_ui(key)
        ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, default=0.0, description='Helper: use the MorphRig panel button to apply this viseme mapping')
    keyblocks = head_obj.data.shape_keys.key_blocks
    for name in S.MORPH_TARGETS:
        fc = keyblocks[name].driver_add('value')
        d = fc.driver
        d.type = 'SUM'
        var = d.variables.new()
        var.name = 'v'
        var.type = 'SINGLE_PROP'
        var.targets[0].id = ctl
        var.targets[0].data_path = f'pose.bones["ctl_face"]["{name}"]'
