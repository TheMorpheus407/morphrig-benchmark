"""Deformation test poses (stored in Operative.blend as one-frame actions DEMO_<name> on the control rig)."""
from .anim_base import stand, ready, kneel, foot_at, fix_reach
from .pose import Pose, floor_pass, solve_cog_height
from . import animkit

ORDER = ['overhead_reach', 'deep_squat', 'crossed_arm_reach', 'torso_twist', 'kneeling', 'hand_support', 'closed_grip']


def build_poses():
    S = stand()
    S.face = {}
    R = ready()
    R.face = {}
    out = {}
    # 1 - both arms straight up, on the toes
    p = S.mod(cog=(0.0, 0.004, 0.040), spine=(-5.0, 0.0, 0.0), head=(-16.0, 0.0, 0.0), clav_l=(20.0, 0.0), clav_r=(20.0, 0.0),
              arm_l=dict(upper=(0.42, 0.04, 0.91), fore=(0.34, 0.02, 0.94), hand=(0.0, 0.0, 0.0)),
              arm_r=dict(upper=(0.42, 0.04, 0.91), fore=(0.34, 0.02, 0.94), hand=(0.0, 0.0, 0.0)))
    p.foot_l.update(roll=1.30)
    p.foot_r.update(roll=1.30)
    p.fing_l.update(curl=0.04, thumb=0.0, spread=0.45)
    p.fing_r.update(curl=0.04, thumb=0.0, spread=0.45)
    p.look = (0.0, 1.0, 3.6)
    out['overhead_reach'] = p
    # 2 - deep squat, heels down, arms forward for balance
    p = S.mod(cog=(0.0, -0.085, -0.56), cog_rot=(30.0, 0.0, 0.0), hips=(-6.0, 0.0, 0.0), spine=(16.0, 0.0, 0.0), head=(-34.0, 0.0, 0.0),
              clav_l=(4.0, 14.0), clav_r=(4.0, 14.0),
              arm_l=dict(upper=(0.22, 0.94, -0.10), fore=(0.02, 0.99, 0.12), hand=(0.0, 0.0, 30.0)),
              arm_r=dict(upper=(0.22, 0.94, -0.10), fore=(0.02, 0.99, 0.12), hand=(0.0, 0.0, 30.0)))
    p.foot_l.update(pos=(0.185, 0.0, 0.0), yaw=24.0, knee=(0.50, 1.0, 0.25))
    p.foot_r.update(pos=(-0.185, 0.0, 0.0), yaw=-24.0, knee=(-0.50, 1.0, 0.25))
    p.fing_l.update(curl=0.10, spread=0.3)
    p.fing_r.update(curl=0.10, spread=0.3)
    out['deep_squat'] = p
    # 3 - arms crossed in front of the chest, each hand reaching past the opposite shoulder
    p = S.mod(spine=(5.0, 0.0, 0.0), head=(4.0, 0.0, 0.0), clav_l=(6.0, 26.0), clav_r=(6.0, 26.0))
    p.arm_l.update(ik=True, pos=p.chest_point((-0.27, 0.27, 0.10)), fingers=(-0.92, 0.36, 0.14), palm=(0.2, -0.3, -0.93), elbow=(0.25, 0.45, -0.86))
    p.arm_r.update(ik=True, pos=p.chest_point((0.29, 0.33, 0.02)), fingers=(0.94, 0.30, 0.12), palm=(-0.2, -0.3, -0.93), elbow=(-0.25, 0.45, -0.86))
    p.fing_l.update(curl=0.08, spread=0.3)
    p.fing_r.update(curl=0.08, spread=0.3)
    out['crossed_arm_reach'] = p
    # 4 - strong torso twist with the arms out
    p = S.mod(hips=(0.0, -10.0, 0.0), spine=(2.0, 64.0, 0.0), head=(0.0, 26.0, 0.0),
              arm_l=dict(upper=(0.97, -0.05, 0.10), fore=(0.98, 0.14, 0.06), hand=(0.0, 0.0, 60.0)),
              arm_r=dict(upper=(0.97, -0.05, 0.10), fore=(0.98, 0.14, 0.06), hand=(0.0, 0.0, 60.0)))
    p.fing_l.update(curl=0.05, spread=0.5)
    p.fing_r.update(curl=0.05, spread=0.5)
    p.look = (3.0, 1.5, 1.6)
    out['torso_twist'] = p
    # 5 - kneeling on the right knee, hands resting
    p = kneel(R, knee='r', lean=10.0, back=0.34)
    p.arm_l = dict(S.arm_l, upper=(0.22, 0.62, -0.75), fore=(-0.25, 0.80, -0.55), hand=(10.0, 0.0, 40.0))
    p.arm_r = dict(S.arm_r, upper=(0.20, 0.05, -0.98), bend=24.0, hand=(4.0, 0.0, 10.0))
    p.fing_l.update(curl=0.30, thumb=0.2)
    p.fing_r.update(curl=0.30, thumb=0.2)
    p.look = (0.0, 4.0, 1.2)
    out['kneeling'] = p
    # 6 - weight on both hands (low three-point crouch)
    wl, wr = (0.20, 0.44, 0.045), (-0.22, 0.42, 0.050)
    p = kneel(R, knee='r', lean=58.0, wrist=wr, wrist_side='r', back=0.32)
    p.arm_r.update(ik=True, pos=wr, fingers=(-0.05, 1.0, 0.0), palm=(0.0, 0.0, -1.0), elbow=(-0.9, -0.3, 0.3))
    p.arm_l.update(ik=True, pos=wl, fingers=(0.05, 1.0, 0.0), palm=(0.0, 0.0, -1.0), elbow=(0.9, -0.3, 0.3))
    p.fing_l.update(curl=0.0, thumb=0.0, spread=0.9)
    p.fing_r.update(curl=0.0, thumb=0.0, spread=0.9)
    p.head = (-38.0, 0.0, 0.0)
    p.look = (0.0, 4.0, 0.8)
    out['hand_support'] = p
    # 7 - closed grip: the left hand holds the spare power cell (same grip as in the reload clip), the mechanical hand is a fist
    p = R.mod(spine=(8.0, 4.0, 0.0), head=(8.0, 14.0, 0.0),
              arm_l=dict(upper=(0.30, 0.62, -0.72), fore=(-0.30, 0.52, 0.80), hand=(-4.0, 0.0, 24.0)),
              arm_r=dict(upper=(0.38, 0.40, -0.83), fore=(-0.22, 0.60, 0.77), hand=(-6.0, 0.0, 30.0)))
    p.fing_l.update(curl=0.52, index=0.52, middle=0.52, ring=0.64, pinky=0.70, thumb=0.42, spread=0.15, fist=0.0)
    p.fing_r.update(curl=1.0, thumb=0.85, spread=0.0, fist=1.0)
    p.look = (0.25, 0.6, 1.25)
    out['closed_grip'] = p
    solve_cog_height(list(out.values()), limit=0.99)
    floor_pass(list(out.values()))
    return out


def install(rig):
    """Write the DEMO_<name> actions; returns {name: action}."""
    acts = {}
    for name, pose in build_poses().items():
        tmp = animkit.Clip('greet', frames=1)
        pose.apply(tmp, 0)
        if name == 'closed_grip':
            from .anim_combat import CELL_IN_HAND_L
            tmp.hold_grip('prop_cell_spare', 'hand_l', 0, CELL_IN_HAND_L)
            tmp.prop_hold('prop_cell_spare', 'hand_l', 0, 1)
        act, slot = animkit.write_action(tmp, rig, name='DEMO_' + name)
        act.use_fake_user = True
        acts[name] = (act, slot)
    return acts
