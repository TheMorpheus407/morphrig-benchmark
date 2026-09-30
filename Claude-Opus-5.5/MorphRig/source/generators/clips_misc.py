"""MorphRig idles (combat, wounded), social clips, aim-offset grid poses."""
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, DEG
import mr_poses as P
from mr_author import Prober, hand_rot, nrm
from clips_common import clip, expr, expr_jaw, breathing, blinks, sway_noise, tremble, face_mix
from clips_actions import aim_pose

A = P.ankle
C = P.COMBAT
RX = P.RELAXED


@clip("idle_combat")
def idle_combat(R):
    c = Clip("idle_combat", 90, loop=True, form="loop", layer="full_body", entry="any", exit="any",
             notes="ready stance, light bounce, guard adjustments, scanning glances")
    a = C
    b = merge(C, {"cog": (0.0, 0.012, -0.085), "cog_rot": (7.0, -15.0, 0.0), "look": (14, -2), "head": (-2, 6, 0),
                  "arm_l": {"fk": (50.0, -26.0, 25.0), "elbow": 104.0, "wrist": (0.0, 0.0, 22.0)}})
    d = merge(C, {"cog": (0.0, 0.016, -0.080), "cog_rot": (6.0, -13.0, 0.0), "look": (-12, -3), "head": (-2, -5, 0),
                  "arm_r": {"fk": (37.0, -27.0, -10.0), "elbow": 74.0, "wrist": (15.0, 0.0, 0.0)}})
    c.key(0, a).key(30, b).key(60, d).key(90, a)
    c.layers += [breathing(1.3, period=45), blinks([22, 70]), sway_noise(7, 0.6)]
    return c


@clip("idle_wounded")
def idle_wounded(R):
    c = Clip("idle_wounded", 120, loop=True, form="loop", layer="full_body", entry="any", exit="any",
             notes="injured but alert: favours the right leg, clutches the ribs, laboured breathing, a wince")
    W = P.WOUNDED
    wince = merge(W, {"face": face_mix(expr("pain", 0.85)), "jaw": 5.0, "spine": (13, 6, 7), "cog": (0.02, 0.04, -0.11)})
    look = merge(W, {"look": (16, 0), "head": (-2, 10, 0)})
    c.key(0, W).key(40, look).key(62, wince).key(80, W).key(120, W)
    c.layers += [breathing(2.2, period=30), blinks([18, 95]), sway_noise(9, 0.8)]
    return c


# ================================================================ social
@clip("greet")
def greet(R):
    c = Clip("greet", 54, form="one_shot", layer="full_body", entry="idle", exit="idle_relaxed",
             notes="two-finger salute from the brow with the organic hand, nod and half smile")
    up = merge(RX, {"arm_l": {"fk": (70.0, 46.0, -10.0), "elbow": 132.0, "wrist": (-10.0, 0.0, 20.0)},
                    "hand_l": {"base": "point", "curl": {"index": (0, 2, 2), "middle": (0, 2, 2), "ring": (85, 98, 55),
                                                           "pinky": (88, 96, 52)}},
                    "face": expr("joy", 0.5), "look": (0, 0), "head": (0, 0, 0)})
    out = merge(up, {"arm_l": {"fk": (80.0, 60.0, -20.0), "elbow": 90.0, "wrist": (-20.0, 0.0, 10.0)},
                     "head": (8, 0, 0), "face": expr("joy", 0.7), "jaw": 1.0})
    nod = merge(out, {"head": (12, 0, 0), "neck": (4, 0, 0)})
    c.key(0, RX).key(12, up).key(20, up).key(28, out).key(34, nod).key(42, merge(RX, {"face": expr("joy", 0.4)})).key(54, RX)
    c.markers += [(20, "greet_salute")]
    c.layers += [blinks([44])]
    return c


@clip("victory")
def victory(R):
    c = Clip("victory", 80, form="one_shot", layer="full_body", entry="any", exit="idle_combat",
             notes="cyber fist pump, glowing grin, then a confident arms-crossed stance")
    pump = merge(C, {"cog": (0.0, 0.0, -0.02), "cog_rot": (-4.0, -6.0, 0.0), "spine": (-10, 6, 0), "neck": (-10, 0, 0),
                     "arm_r": {"fk": (150.0, 20.0, 0.0), "elbow": 40.0, "wrist": (0.0, 0.0, 0.0)}, "hand_r": "fist",
                     "arm_l": {"fk": (20.0, -20.0, 0.0), "elbow": 90.0}, "hand_l": "fist",
                     "face": expr("joy", 1.0), "jaw": 8.0, "look": (0, 12)})
    pump2 = merge(pump, {"arm_r": {"fk": (160.0, 24.0, 0.0), "elbow": 20.0}, "cog": (0.0, 0.0, -0.01)})
    cross = merge(RX, {"arm_l": {"fk": (40.0, -20.0, 60.0), "elbow": 118.0, "wrist": (0.0, 0.0, 20.0)},
                       "arm_r": {"fk": (44.0, -18.0, 60.0), "elbow": 112.0, "wrist": (0.0, 0.0, 20.0)},
                       "hand_l": "loose_fist", "hand_r": "loose_fist", "spine": (-4, 0, 0), "head": (-6, -8, 0),
                       "face": face_mix(expr("joy", 0.6), {"mouthSmile_L": 0.9}), "look": (-10, 0)})
    c.key(0, C).key(10, pump).key(16, merge(pump, {"arm_r": {"fk": (140.0, 20.0, 0.0), "elbow": 60.0}}))
    c.key(22, pump2).key(40, merge(C, {"face": expr("joy", 0.8)})).key(56, cross).key(80, cross)
    c.markers += [(10, "victory_pump"), (22, "victory_pump")]
    c.layers += [blinks([48])]
    return c


@clip("defeat")
def defeat(R):
    c = Clip("defeat", 80, form="one_shot", layer="full_body", entry="any", exit="idle_relaxed",
             notes="nonfatal disappointment: shoulders drop, head shake, hands on hips, exhale")
    slump = merge(RX, {"cog": (0.0, 0.02, -0.04), "cog_rot": (8.0, 0.0, 0.0), "spine": (14, 0, 0), "neck": (16, 0, 0),
                       "head": (12, 0, 0), "clav_l": (-8, 6), "clav_r": (-8, 6), "face": expr("concern", 0.9),
                       "jaw": 2.0, "look": (0, -30)})
    shake_a = merge(slump, {"head": (12, 14, 0)})
    shake_b = merge(slump, {"head": (12, -14, 0)})
    hips = merge(RX, {"arm_l": {"fk": (-8.0, 10.0, 60.0), "elbow": 104.0, "wrist": (20.0, 0.0, 0.0)},
                      "arm_r": {"fk": (-8.0, 10.0, 60.0), "elbow": 104.0, "wrist": (20.0, 0.0, 0.0)},
                      "spine": (6, 0, 0), "head": (2, 0, 0), "face": expr("concern", 0.6), "look": (-6, -10)})
    c.key(0, RX).key(14, slump).key(26, shake_a).key(34, shake_b).key(42, slump).key(60, hips).key(80, hips)
    c.markers += [(14, "defeat_exhale")]
    c.layers += [breathing(1.5, period=40), blinks([52])]
    return c


# ================================================================ aim grid (static poses)
AIM_YAW = {"left": 60.0, "center": 0.0, "right": -60.0}
AIM_PITCH = {"down": -35.0, "level": 0.0, "up": 35.0}


def _aim_clip(pk, yk):
    cid = f"aim_{pk}_{yk}"
    c = Clip(cid, 1, form="pose", layer="upper_body", entry="aim_offset", exit="aim_offset",
             notes=f"aim sample yaw {AIM_YAW[yk]:+.0f} deg (+ = left), pitch {AIM_PITCH[pk]:+.0f} deg (+ = up); "
                   "forearm/emitter exactly along the aim ray; legs identical to idle_combat")
    return c


for _pk in AIM_PITCH:
    for _yk in AIM_YAW:
        def _mk(R, pk=_pk, yk=_yk):
            c = _aim_clip(pk, yk)
            pose = aim_pose(R, AIM_YAW[yk], AIM_PITCH[pk])
            c.key(0, pose).key(1, pose)
            c.extra["aim_yaw_deg"] = AIM_YAW[yk]
            c.extra["aim_pitch_deg"] = AIM_PITCH[pk]
            c.extra["no_floor_fix"] = True
            return c
        clip(f"aim_{_pk}_{_yk}")(_mk)
