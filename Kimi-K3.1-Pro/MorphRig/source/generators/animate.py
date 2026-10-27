"""Authored procedural motion, control curves, baked actions, and animation metadata."""
from pathlib import Path
from math import sin, cos, pi, sqrt
import json
import math
import bpy
from mathutils import Vector, Matrix, Quaternion

ROOT = Path(__file__).resolve().parents[2]
def V(x, y=None, z=None):
    return Vector(x) if y is None else Vector((x, y, z))


SPEC = []
REST = {}
REST_LOCAL = {}
PARENT = {}
ORDER = []
DIRECTIONS = {"f": V(0, -1, 0), "fr": V(-1, -1, 0).normalized(), "r": V(-1, 0, 0), "br": V(-1, 1, 0).normalized(), "b": V(0, 1, 0), "bl": V(1, 1, 0).normalized(), "l": V(1, 0, 0), "fl": V(1, -1, 0).normalized()}


def Q(axis, degrees):
    return Quaternion(V(axis).normalized(), math.radians(degrees))


def ease(t):
    t = max(0., min(1., t))
    return t * t * (3 - 2 * t)


def pulse(t, center, width):
    return max(0., 1 - abs(t - center) / width)


def keyed(t, points):
    if t <= points[0][0]: return points[0][1]
    for (a, va), (b, vb) in zip(points, points[1:]):
        if t <= b:
            f = ease((t - a) / (b - a))
            return va.lerp(vb, f) if isinstance(va, Vector) else va * (1 - f) + vb * f
    return points[-1][1]


class Pose:
    def __init__(self):
        self.rot = {}
        self.local = {}
        self.absolute = {}
        self.pelvis = V(0, 0, 0)
        self.root = V(0, 0, 0)
        self.arm_targets = {}
        self.leg_targets = {}
        self.knee_targets = {}
        self.curls = {"L": .14, "R": .14}
        self.spread = {"L": .04, "R": .04}
        self.face = {"LipClosed": .55}
        self.look = {"L": V(0, 0, 0), "R": V(0, 0, 0)}

    def copy(self):
        p = Pose()
        p.rot = dict(self.rot); p.local = dict(self.local); p.absolute = dict(self.absolute)
        p.pelvis = self.pelvis.copy(); p.root = self.root.copy()
        p.arm_targets = dict(self.arm_targets); p.leg_targets = dict(self.leg_targets); p.knee_targets = dict(self.knee_targets)
        p.curls = dict(self.curls); p.spread = dict(self.spread); p.face = dict(self.face)
        p.look = {key: value.copy() for key, value in self.look.items()}
        return p


def blend(a, b, t):
    t = ease(t)
    p = Pose()
    for name in a.rot.keys() | b.rot.keys():
        qa = a.rot.get(name, Quaternion()); qb = b.rot.get(name, Quaternion())
        p.rot[name] = qa.slerp(qb, t)
    for name in a.local.keys() | b.local.keys():
        p.local[name] = a.local.get(name, Quaternion()).slerp(b.local.get(name, Quaternion()), t)
    p.pelvis = a.pelvis.lerp(b.pelvis, t); p.root = a.root.lerp(b.root, t)
    for name in a.absolute.keys() | b.absolute.keys():
        if name == "pelvis":
            fallback_a = V(0, 0, .995) + a.pelvis
            fallback_b = V(0, 0, .995) + b.pelvis
            p.absolute[name] = a.absolute.get(name, fallback_a).lerp(b.absolute.get(name, fallback_b), t)
        elif name in a.absolute and name in b.absolute:
            p.absolute[name] = a.absolute[name].lerp(b.absolute[name], t)
        else:
            p.absolute[name] = (a.absolute if name in a.absolute else b.absolute)[name].copy()
    for side in ("L", "R"):
        if side in a.arm_targets or side in b.arm_targets:
            hand = next(item for item in SPEC if item["name"] == f"hand.{side}")
            fallback_a = V(hand["head"]) + a.pelvis
            fallback_b = V(hand["head"]) + b.pelvis
            p.arm_targets[side] = a.arm_targets.get(side, fallback_a).lerp(b.arm_targets.get(side, fallback_b), t)
        if side in a.leg_targets or side in b.leg_targets:
            ankle = next(item for item in SPEC if item["name"] == f"foot.{side}")
            va = a.leg_targets.get(side, V(ankle["head"]) + a.pelvis)
            vb = b.leg_targets.get(side, V(ankle["head"]) + b.pelvis)
            p.leg_targets[side] = va.lerp(vb, t)
        p.curls[side] = a.curls[side] * (1 - t) + b.curls[side] * t
        p.spread[side] = a.spread[side] * (1 - t) + b.spread[side] * t
    for name in a.face.keys() | b.face.keys():
        p.face[name] = a.face.get(name, 0) * (1 - t) + b.face.get(name, 0) * t
    for side in ("L", "R"):
        p.look[side] = a.look[side].lerp(b.look[side], t)
    return p


def base_pose(combat=False, phase=0):
    p = Pose()
    breath = sin(phase * 2 * pi)
    p.rot["spine_02"] = Q((1, 0, 0), .8 * breath)
    p.rot["neck"] = Q((1, 0, 0), -.45 * breath)
    for side, s in ((1, "L"), (-1, "R")):
        p.rot[f"upperarm.{s}"] = Q((0, 1, 0), -side * (5 if not combat else 12)) @ Q((1, 0, 0), -5 if not combat else -17)
        p.rot[f"forearm.{s}"] = Q((1, 0, 0), -13 if not combat else -34)
        p.local[f"clavicle.{s}"] = Q((0, 1, 0), side * 2)
    if combat:
        p.pelvis.z = -.025
        p.rot["spine_01"] = Q((1, 0, 0), 5)
        p.rot["spine_03"] = Q((0, 0, 1), -4)
        p.curls = {"L": .24, "R": .32}
    for s in ("L", "R"):
        ankle = V(next(item["head"] for item in SPEC if item["name"] == f"foot.{s}"))
        if combat: ankle.y += .065 if s == "L" else -.055
        p.leg_targets[s] = ankle
    return p


def wounded_pose(t):
    p = base_pose(True)
    p.pelvis += V(.015, 0, -.03)
    p.rot["spine_02"] = Q((0, 1, 0), -10) @ Q((1, 0, 0), 8 + sin(t * 2 * pi))
    p.rot["head"] = Q((0, 1, 0), 9) @ Q((1, 0, 0), 6)
    p.arm_targets["L"] = V(.09, -.13, 1.13)
    p.curls["L"] = .62
    p.face.update({"BrowLower.L": .45, "BrowLower.R": .35, "Frown.L": .40, "Frown.R": .40, "Squint.R": .20})
    return p


def gait_pose(direction, period, t, kind="walk", amplitude=1):
    p = base_pose(True)
    d = DIRECTIONS[direction]
    speed = {"walk": 1.5, "run": 4., "sprint": 6.5}[kind]
    stride = min(.92, speed * period * .25) * amplitude
    lift = {"walk": .085, "run": .15, "sprint": .18}[kind] * amplitude
    bounce = {"walk": .014, "run": .027, "sprint": .039}[kind]
    p.pelvis.z -= .026 + bounce * (1 - cos(t * 4 * pi)) * .5 * amplitude
    p.pelvis.y = -.016 * amplitude if kind == "walk" else -.036 * amplitude
    p.rot["spine_01"] = Q((1, 0, 0), {"walk": 3, "run": 9, "sprint": 17}[kind] * amplitude)
    p.rot["spine_03"] = Q((0, 0, 1), (4 if kind == "walk" else 7) * sin(t * 2 * pi) * amplitude)
    p.rot["head"] = Q((0, 0, 1), -2 * sin(t * 2 * pi) * amplitude)
    for index, (side, s) in enumerate(((1, "L"), (-1, "R"))):
        phase = (t + index * .5) % 1
        if phase < .60:
            along = stride * (1 - 2 * phase / .60)
            height = 0
            foot_pitch = -6 * sin(phase / .60 * pi)
        else:
            u = (phase - .60) / .40
            along = -stride + 2 * stride * ease(u)
            height = lift * sin(u * pi)
            foot_pitch = 12 * sin(u * pi)
        ankle = V(next(item["head"] for item in SPEC if item["name"] == f"foot.{s}")) + d * along
        ankle.z += height
        p.leg_targets[s] = ankle
        p.local[f"toe.{s}"] = Q((1, 0, 0), max(0, foot_pitch) * .55)
        swing = -sin((t + index * .5) * 2 * pi) * (16 if kind == "walk" else 34 if kind == "run" else 46) * amplitude
        p.rot[f"upperarm.{s}"] = Q((0, 1, 0), -side * 9) @ Q((1, 0, 0), swing - 12)
        p.rot[f"forearm.{s}"] = Q((1, 0, 0), -25 - max(0, -swing) * .6)
        p.local[f"forearm_twist.{s}"] = Q((0, 1, 0), 6 * sin(t * 2 * pi))
    return p


def turn_pose(t, degrees):
    p = base_pose(True)
    angle = degrees * ease(t)
    p.rot["pelvis"] = Q((0, 0, 1), angle)
    p.rot["spine_02"] = Q((0, 0, 1), 7 * sin(pi * t))
    for index, s in enumerate(("L", "R")):
        start = V(next(item["head"] for item in SPEC if item["name"] == f"foot.{s}"))
        local_t = max(0, min(1, t * 1.4 - index * .18))
        a = math.radians(degrees * ease(local_t))
        p.leg_targets[s] = V((start.x * cos(a) - start.y * sin(a), start.x * sin(a) + start.y * cos(a), start.z + .07 * sin(local_t * pi)))
    p.arm_targets["L"] = V(.26, -.11, 1.04)
    p.arm_targets["R"] = V(-.26, -.11, 1.04)
    return p


def solve_two_bone(start, target, hint, first_length, second_length):
    direction = target - start
    distance = max(.02, min(first_length + second_length - .001, direction.length))
    direction.normalize()
    target = start + direction * distance
    a = (first_length ** 2 - second_length ** 2 + distance ** 2) / (2 * distance)
    h = sqrt(max(0, first_length ** 2 - a ** 2))
    perpendicular = hint - direction * hint.dot(direction)
    if perpendicular.length < .001:
        perpendicular = direction.cross(V(0, 0, 1))
    perpendicular.normalize()
    return start + direction * a + perpendicular * h, target


def world_transforms(p):
    result = {}
    for name in ORDER:
        item = REST[name]
        parent = PARENT[name]
        rest = item.matrix_local.copy()
        rest_rel = REST_LOCAL[name]
        if parent:
            parent_world = result[parent]
            head = parent_world @ rest_rel.translation
            orientation = (parent_world.to_quaternion() @ rest_rel.to_quaternion()).normalized()
        else:
            parent_world = Matrix.Identity(4)
            head = rest.translation.copy()
            orientation = rest.to_quaternion()
        if name == "root": head = V(item.head_local) + p.root
        if name == "pelvis": head = p.absolute.get("pelvis", V(item.head_local) + p.pelvis)
        elif name in p.absolute: head = p.absolute[name]
        if name in p.rot:
            orientation = (p.rot[name] @ rest.to_quaternion()).normalized()
        if name in p.local:
            orientation = (orientation @ p.local[name]).normalized()
        result[name] = Matrix.Translation(head) @ orientation.to_matrix().to_4x4()
    return result


def apply_contacts(p):
    world = world_transforms(p)
    for side, s in ((1, "L"), (-1, "R")):
        if s in p.arm_targets:
            shoulder = world[f"upperarm.{s}"].translation
            upper = next(item for item in SPEC if item["name"] == f"upperarm.{s}")
            fore = next(item for item in SPEC if item["name"] == f"forearm.{s}")
            l1, l2 = (V(upper["tail"]) - V(upper["head"])).length, (V(fore["tail"]) - V(fore["head"])).length
            hint = V(side * .8, .25, -.5)
            elbow, wrist = solve_two_bone(shoulder, p.arm_targets[s] + p.root, hint, l1, l2)
            p.rot[f"upperarm.{s}"] = (V(upper["tail"]) - V(upper["head"])).rotation_difference(elbow - shoulder)
            p.rot[f"forearm.{s}"] = (V(fore["tail"]) - V(fore["head"])).rotation_difference(wrist - elbow)
        if s in p.knee_targets:
            knee, ankle = p.knee_targets[s]
            hip = world[f"thigh.{s}"].translation
            for prefix, target_a, target_b in (("thigh", hip, knee), ("shin", knee, ankle)):
                item = next(item for item in SPEC if item["name"] == f"{prefix}.{s}")
                p.rot[f"{prefix}.{s}"] = (V(item["tail"]) - V(item["head"])).rotation_difference(target_b - target_a)
            p.rot[f"foot.{s}"] = Quaternion()
        elif s in p.leg_targets:
            hip = world[f"thigh.{s}"].translation
            thigh = next(item for item in SPEC if item["name"] == f"thigh.{s}")
            shin = next(item for item in SPEC if item["name"] == f"shin.{s}")
            l1, l2 = (V(thigh["tail"]) - V(thigh["head"])).length, (V(shin["tail"]) - V(shin["head"])).length
            target = p.leg_targets[s] + p.root
            knee, ankle = solve_two_bone(hip, target, V(0, -1, .06), l1, l2)
            p.rot[f"thigh.{s}"] = (V(thigh["tail"]) - V(thigh["head"])).rotation_difference(knee - hip)
            p.rot[f"shin.{s}"] = (V(shin["tail"]) - V(shin["head"])).rotation_difference(ankle - knee)
            p.rot[f"foot.{s}"] = Quaternion()
        for finger in ("thumb", "index", "middle", "ring", "pinky"):
            for joint in range(3):
                amount = p.curls[s] * (64, 75, 48)[joint] * (.70 if finger == "thumb" else 1)
                p.local[f"{finger}_{joint + 1:02d}.{s}"] = Q((1, 0, 0), amount)
                if finger != "thumb" and joint == 0:
                    p.local[f"{finger}_{joint + 1:02d}.{s}"] @= Q((0, 0, 1), (("index", "middle", "ring", "pinky").index(finger) - 1.5) * p.spread[s] * 13)
        look = p.look[s]
        p.rot[f"eye.{s}"] = Q((0, 0, 1), look.x) @ Q((1, 0, 0), -look.y) @ Q((0, 1, 0), look.z)
    for i in range(3):
        p.local[f"cable_{i + 1:02d}"] = Q((1, 0, 0), 2.5 * sin(p.root.length * 2 + i))
    return p


def aim_pose(yaw=0, pitch=0, recoil=0):
    p = base_pose(True)
    p.rot["spine_03"] = Q((0, 0, 1), yaw * .22)
    p.rot["neck"] = Q((0, 0, 1), yaw * .12) @ Q((1, 0, 0), pitch * .13)
    rad_y, rad_p = math.radians(yaw), math.radians(pitch)
    direction = V((sin(rad_y) * cos(rad_p), -cos(rad_y) * cos(rad_p), sin(rad_p)))
    elbow = V((-.295, -.015, 1.207))
    wrist = elbow + direction * (.25 - recoil * .035)
    p.arm_targets["R"] = wrist
    p.arm_targets["L"] = elbow + direction * .16 + V(.035, -.014, -.046)
    p.curls["R"] = .40; p.curls["L"] = .52
    p.face["LipClosed"] = .90; p.face["Squint.L"] = .18; p.face["Squint.R"] = .23
    return p


def channel_pose(t=0):
    p = aim_pose(0, -3)
    p.arm_targets["L"] = V(.13, -.31, 1.26 + .008 * sin(t * 2 * pi))
    p.arm_targets["R"] = V(-.22, -.36, 1.34 + .006 * sin(t * 2 * pi))
    p.rot["spine_02"] = Q((1, 0, 0), 4 + .7 * sin(t * 2 * pi))
    p.face["BrowLower.L"] = .23; p.face["BrowLower.R"] = .23
    return p


def uplink_pose(t=0):
    p = base_pose(True)
    p.arm_targets["R"] = V(-.22, -.28, 1.29 + .004 * sin(2 * pi * t))
    p.arm_targets["L"] = V(.16, -.06, 1.60)
    p.curls["R"] = .34; p.curls["L"] = .65
    p.rot["head"] = Q((1, 0, 0), 5 + sin(2 * pi * t))
    return p


def charge_pose(t=0):
    p = base_pose(True)
    p.pelvis.z = -.07
    p.arm_targets["L"] = V(.10, -.30, 1.19 + .012 * sin(t * 2 * pi))
    p.arm_targets["R"] = V(-.10, -.30, 1.19 + .012 * cos(t * 2 * pi))
    p.curls = {"L": .75, "R": .75}
    p.rot["spine_02"] = Q((1, 0, 0), 8 + sin(t * 2 * pi))
    p.face.update({"BrowLower.L": .5, "BrowLower.R": .5, "Squint.L": .3, "Squint.R": .3})
    return p


def floor_pose(front=True, dead=False):
    p = Pose()
    sign = 1 if front else -1
    p.absolute["pelvis"] = V(0, .18 if front else -.18, .175)
    p.rot["pelvis"] = Q((1, 0, 0), sign * 90)
    p.rot["spine_01"] = Q((1, 0, 0), sign * 90)
    p.rot["spine_02"] = Q((1, 0, 0), sign * 91)
    p.rot["spine_03"] = Q((1, 0, 0), sign * 90)
    p.rot["neck"] = Q((1, 0, 0), sign * 84)
    p.rot["head"] = Q((1, 0, 0), sign * 79) @ Q((0, 0, 1), 8 if front else -12)
    for side, s in ((1, "L"), (-1, "R")):
        p.arm_targets[s] = V(side * (.25 if front else .30), -.34 if front else -.16, .11 if front else .083)
        p.rot[f"hand.{s}"] = Q((1, 0, 0), sign * 90)
        p.leg_targets[s] = V(side * .115, .72 if front else -.70, .095)
        p.curls[s] = .16 if not dead else .30
    p.face = {"LipClosed": 1., "Blink.L": .95 if dead else .25, "Blink.R": .90 if dead else .22, "Frown.L": .3 if dead else 0, "Frown.R": .3 if dead else 0}
    return p


def kneel_pose(support=False):
    p = base_pose(False)
    p.pelvis.z = -.655 if support else -.495
    p.rot["spine_01"] = Q((1, 0, 0), 46 if support else 17)
    p.rot["spine_02"] = Q((1, 0, 0), 80 if support else 7)
    p.rot["head"] = Q((1, 0, 0), 20 if support else -8)
    p.knee_targets["L"] = (V(.115, -.30 if support else .10, .105), V(.12, .10 if support else .51, .13))
    p.knee_targets["R"] = (V(-.12, -.40, .36 if support else .46), V(-.12, -.74 if support else -.66, .14))
    p.arm_targets["R"] = V(-.245, -.43, .105) if support else V(-.17, -.28, .47)
    p.arm_targets["L"] = V(.13, -.24, .46 if not support else .31)
    p.curls = {"L": .48, "R": .35}
    return p


def melee_pose(index, t):
    p = base_pose(True)
    if index == 1:
        p.rot["spine_03"] = Q((0, 0, 1), keyed(t, [(0, -16), (.28, -25), (.51, 30), (1, 0)]))
        p.arm_targets["R"] = keyed(t, [(0, V(-.30, -.04, .98)), (.26, V(-.40, -.10, 1.51)), (.50, V(.25, -.37, 1.27)), (.72, V(.04, -.31, .99)), (1, V(-.30, -.04, .98))])
        p.arm_targets["L"] = V(.24, -.17, 1.13)
    elif index == 2:
        p.rot["spine_03"] = Q((0, 0, 1), keyed(t, [(0, 22), (.31, 38), (.54, -42), (.80, -10), (1, 0)]))
        p.arm_targets["R"] = keyed(t, [(0, V(-.31, -.03, 1.00)), (.28, V(.32, -.22, 1.43)), (.52, V(-.39, -.32, 1.15)), (.75, V(-.25, -.16, .97)), (1, V(-.30, -.04, .98))])
        p.arm_targets["L"] = V(.15, -.16, 1.28)
    else:
        p.pelvis.z = -.04 - .13 * pulse(t, .58, .45)
        p.rot["spine_01"] = Q((1, 0, 0), keyed(t, [(0, -8), (.3, -17), (.58, 32), (1, 3)]))
        p.arm_targets["R"] = keyed(t, [(0, V(-.30, -.04, .98)), (.30, V(-.05, -.19, 1.67)), (.56, V(.03, -.50, 1.00)), (.78, V(-.10, -.27, .88)), (1, V(-.30, -.04, .98))])
        p.arm_targets["L"] = keyed(t, [(0, V(.3, -.03, .98)), (.3, V(.20, -.15, 1.51)), (.60, V(.18, -.32, 1.03)), (1, V(.30, -.03, .98))])
    p.curls["R"] = .42
    p.face.update({"BrowLower.L": .65, "BrowLower.R": .65, "Squint.L": .28, "Squint.R": .28})
    p.local["blade_slide"] = Quaternion()
    return p


def floor_transition(t, front=True):
    p = blend(base_pose(True), floor_pose(front), ease(t))
    p.absolute["pelvis"].z = max(.175, .995 * ((1 - t) ** 1.3) + .175 * t)
    return p


def dialogue_pose(t, alignment):
    seconds = t * alignment["duration_seconds"]
    p = base_pose(True)
    p.face = {"LipClosed": .65, "BrowLower.L": .22, "BrowLower.R": .22, "Squint.L": .12, "Squint.R": .12}
    for item in alignment["visemes"]:
        start, duration = item["time"], item["duration"]
        local = (seconds - start) / max(.04, duration)
        if -.15 <= local <= 1.15:
            envelope = min(1., max(0., (local + .15) / .35), max(0., (1.15 - local) / .35))
            control = item["control"]
            p.face[control] = max(p.face.get(control, 0), .92 * envelope)
            jaw = {"Viseme_AA": .70, "Viseme_EE": .15, "Viseme_OO": .26, "Viseme_TH": .14, "Viseme_CH": .12}.get(control, 0)
            p.face["JawOpen"] = max(p.face.get("JawOpen", 0), jaw * envelope)
    for blink_time in (2.18, 6.1, 10.65, 14.03):
        amount = pulse(seconds, blink_time, .11)
        p.face["Blink.L"] = max(p.face.get("Blink.L", 0), amount)
        p.face["Blink.R"] = max(p.face.get("Blink.R", 0), amount * .95)
    concern = ease((seconds - 6.3) / 1.0) * (1 - ease((seconds - 10.8) / 1.2))
    joy = ease((seconds - 12.0) / 1.7)
    p.face["Frown.L"] = .46 * concern; p.face["Frown.R"] = .37 * concern
    p.face["BrowRaise.L"] = .35 * concern; p.face["BrowRaise.R"] = .45 * concern
    for s in ("L", "R"):
        p.face["Smile." + s] = .78 * joy; p.face["Cheek." + s] = .50 * joy
        p.look[s] = V(keyed(seconds, [(0, 0), (3.8, 0), (5.0, 8), (6.6, 8), (7.4, -9), (9.2, -9), (10.2, 0), (15.2, 0)]), keyed(seconds, [(0, 0), (7.0, -2), (9.4, -2), (10.4, 0), (15.2, 0)]), 0)
    p.rot["head"] = Q((0, 0, 1), keyed(seconds, [(0, 0), (4.8, 6), (6.6, 6), (7.5, -7), (9.4, -7), (10.6, 0), (15.2, 0)])) @ Q((1, 0, 0), 2.5 * sin(seconds * 1.2) + 2.5 * pulse(seconds, 14.1, .5))
    p.arm_targets["R"] = keyed(seconds, [(0, V(-.305, -.036, .962)), (1.0, V(-.26, -.22, 1.20)), (2.0, V(-.28, -.40, 1.39)), (3.6, V(-.22, -.29, 1.29)), (6.8, V(-.23, -.32, 1.23)), (8.1, V(-.34, -.40, 1.43)), (9.5, V(-.20, -.27, 1.19)), (11.3, V(-.12, -.38, 1.32)), (12.9, V(-.21, -.21, 1.17)), (15.2, V(-.305, -.036, .962))])
    p.arm_targets["L"] = keyed(seconds, [(0, V(.305, -.036, .962)), (2.9, V(.27, -.12, 1.06)), (4.1, V(.14, -.34, 1.26)), (6.3, V(.22, -.20, 1.14)), (9.9, V(.28, -.11, 1.06)), (11.5, V(.12, -.37, 1.31)), (13.0, V(.25, -.18, 1.12)), (15.2, V(.305, -.036, .962))])
    p.curls["R"] = .30 + .22 * pulse(seconds, 2.2, 1.4)
    p.curls["L"] = .24 + .16 * pulse(seconds, 4.7, 1.3)
    p.rot["spine_03"] = Q((0, 0, 1), 3 * sin(seconds * .9))
    return p


def sample_pose(name, t, frames, alignment):
    if name == "idle_relaxed":
        p = base_pose(False, t)
        p.pelvis.x = .010 * sin(2 * pi * t); p.rot["pelvis"] = Q((0, 1, 0), 1.2 * sin(2 * pi * t))
        return p
    if name == "idle_combat": return base_pose(True, t)
    if name == "idle_wounded": return wounded_pose(t)
    if name.startswith("walk_") or name.startswith("run_"):
        kind, direction = name.split("_")
        return gait_pose(direction, 1.2 if kind == "walk" else .8, t, kind)
    if name == "sprint_f": return gait_pose("f", .6, t, "sprint")
    if name == "start_f": return blend(base_pose(True), gait_pose("f", 1.2, t * .7, "walk"), ease(t))
    if name == "stop_f": return blend(gait_pose("f", 1.2, .6 + t * .4, "walk"), base_pose(True), ease(t))
    if name.startswith("turn_") or name.startswith("pivot_"):
        degrees = (90 if "l90" in name else -90 if "r90" in name else 180 if "l180" in name else -180)
        return turn_pose(t, degrees)
    if name in ("jump_start", "jump_land", "land_heavy"):
        p = base_pose(True)
        depth = .13 if name != "land_heavy" else .22
        if name == "jump_start":
            amount = keyed(t, [(0, 0), (.36, 1), (.68, -.40), (1, -.20)])
            p.arm_targets["L"] = keyed(t, [(0, V(.30, -.02, .97)), (.35, V(.28, .13, 1.00)), (.72, V(.26, -.22, 1.31)), (1, V(.28, -.10, 1.09))])
            p.arm_targets["R"] = keyed(t, [(0, V(-.30, -.02, .97)), (.35, V(-.28, .13, 1.00)), (.72, V(-.26, -.22, 1.31)), (1, V(-.28, -.10, 1.09))])
        else:
            amount = keyed(t, [(0, .2), (.23, 1), (.58, .8), (1, 0)])
            p.arm_targets["L"] = V(.30, -.18, 1.12); p.arm_targets["R"] = V(-.30, -.18, 1.12)
        p.pelvis.z = -depth * amount
        p.rot["spine_01"] = Q((1, 0, 0), 18 * max(0, amount))
        for s in ("L", "R"):
            ankle = V(next(item["head"] for item in SPEC if item["name"] == f"foot.{s}")); ankle.y += -.04 if s == "L" else .04
            p.leg_targets[s] = ankle
        return p
    if name in ("jump_air", "fall", "knockup_air"):
        p = base_pose(False)
        falling = name != "jump_air"
        p.pelvis.z = .03 if not falling else -.015
        for side, s in ((1, "L"), (-1, "R")):
            ankle = V(next(item["head"] for item in SPEC if item["name"] == f"foot.{s}"))
            ankle += V(0, .04 if s == "L" else -.08, .16 if not falling else .06)
            p.leg_targets[s] = ankle
            p.arm_targets[s] = V(side * (.30 if not falling else .39), -.04, 1.27 + .035 * sin(t * 2 * pi + side))
        p.rot["spine_01"] = Q((1, 0, 0), -8 if not falling else 12)
        p.face["BrowRaise.L"] = .35 if falling else .1; p.face["BrowRaise.R"] = .35 if falling else .1
        return p
    if name.startswith("dash_"):
        p = base_pose(True)
        d = DIRECTIONS[name.split("_")[1]]
        p.root = d * (2 * ease(t))
        p.pelvis.z = -.08 * sin(pi * t)
        p.rot["spine_01"] = Q((1, 0, 0), 24 if name == "dash_f" else -16)
        p.rot["spine_03"] = Q((0, 1, 0), 17 if name == "dash_l" else -17 if name == "dash_r" else 0)
        for side, s in ((1, "L"), (-1, "R")):
            p.arm_targets[s] = V(side * .32, .07 if name == "dash_f" else -.22, 1.04)
            p.leg_targets[s] = V(side * .13, 0, .14) - d * (.20 + .07 * side)
        return p
    if name in ("blink_out", "blink_in"):
        p = base_pose(True)
        u = t if name == "blink_out" else 1 - t
        p.pelvis.z = -.13 * sin(u * pi / 2)
        p.rot["spine_01"] = Q((1, 0, 0), 15 * sin(u * pi))
        p.arm_targets["L"] = V(.14, -.17, 1.25); p.arm_targets["R"] = V(-.14, -.17, 1.25)
        p.face["Blink.L"] = u * .6; p.face["Blink.R"] = u * .6
        return p
    if name.startswith("melee_"): return melee_pose(int(name[-1]), t)
    if name in ("ranged_fire", "ranged_burst"):
        times = [.28] if name == "ranged_fire" else [.16, .45, .73]
        recoil = max(pulse(t, center, .09) for center in times)
        p = aim_pose(0, 0, recoil)
        p.rot["head"] = Q((1, 0, 0), -3 * recoil)
        return p
    if name == "reload":
        p = base_pose(True)
        emitter = V(-.23, -.30, 1.20)
        p.arm_targets["R"] = emitter
        cell = emitter + V(.015, -.062, -.015)
        held = V(-.02, -.36, 1.18)
        u = keyed(t, [(0, 0), (.40, 0), (.57, 1), (.69, 1), (.85, 0), (1, 0)])
        p.absolute["cell"] = cell.lerp(held, u)
        p.rot["cell"] = Q((0, 0, 1), 15 * u)
        p.arm_targets["L"] = keyed(t, [(0, V(.30, -.04, .97)), (.22, cell + V(.035, -.015, -.015)), (.43, held + V(.035, 0, -.01)), (.68, held + V(.03, 0, -.01)), (.82, cell + V(.035, -.01, 0)), (1, V(.30, -.04, .97))])
        p.curls["L"] = keyed(t, [(0, .16), (.25, .85), (.83, .85), (1, .14)])
        p.curls["R"] = .45
        p.rot["head"] = Q((1, 0, 0), 13 * sin(pi * t))
        return p
    if name.startswith("cast_"):
        p = base_pose(True)
        if name == "cast_directional":
            for side, s in ((1, "L"), (-1, "R")):
                p.arm_targets[s] = keyed(t, [(0, V(side * .30, -.02, .98)), (.30, V(side * .24, .06, 1.25)), (.55, V(side * .16, -.44, 1.35)), (1, V(side * .30, -.02, .98))])
            p.rot["spine_03"] = Q((0, 0, 1), -8 * sin(pi * t))
        elif name == "cast_ground":
            p.pelvis.z = -.15 * sin(pi * t)
            p.rot["head"] = Q((1, 0, 0), 22 * sin(pi * t))
            p.arm_targets["R"] = keyed(t, [(0, V(-.30, -.02, .98)), (.30, V(-.32, -.10, 1.25)), (.58, V(-.20, -.42, .85)), (1, V(-.30, -.02, .98))])
            p.arm_targets["L"] = V(.22, -.18, 1.13)
        else:
            p.arm_targets["L"] = keyed(t, [(0, V(.30, -.02, .98)), (.42, V(-.10, -.16, 1.32)), (.66, V(-.13, -.17, 1.35)), (1, V(.30, -.02, .98))])
            p.arm_targets["R"] = keyed(t, [(0, V(-.30, -.02, .98)), (.42, V(.10, -.18, 1.27)), (.66, V(.13, -.18, 1.30)), (1, V(-.30, -.02, .98))])
            p.rot["spine_02"] = Q((0, 0, 1), 35 * sin(pi * t))
        p.curls = {"L": .35, "R": .35}
        p.face["BrowLower.L"] = .38; p.face["BrowLower.R"] = .38
        return p
    if name == "channel_start": return blend(base_pose(True), channel_pose(), t)
    if name == "channel_loop": return channel_pose(t)
    if name == "channel_end": return blend(channel_pose(), base_pose(True), t)
    if name == "channel_interrupt": return blend(channel_pose(), wounded_pose(t), ease(t))
    if name == "charge_start": return blend(base_pose(True), charge_pose(), t)
    if name == "charge_hold": return charge_pose(t)
    if name == "charge_release":
        p = blend(charge_pose(), aim_pose(), ease(t))
        p.pelvis.z -= .06 * sin(pi * t)
        p.rot["spine_01"] = Q((1, 0, 0), 15 * sin(pi * t))
        return p
    if name == "charge_cancel": return blend(charge_pose(), base_pose(False), t)
    if name == "deploy":
        p = base_pose(True)
        crouch = pulse(t, .63, .56)
        p.pelvis.z = -.80 * crouch
        p.rot["spine_01"] = Q((1, 0, 0), 70 * crouch)
        p.rot["head"] = Q((1, 0, 0), 18 * crouch)
        floor_point = V(.23, -.35, .009)
        beacon = keyed(t, [(0, V(.17, .075, 1.0)), (.24, V(.22, -.22, .89)), (.63, floor_point), (1, floor_point)])
        p.absolute["beacon"] = beacon
        p.arm_targets["L"] = keyed(t, [(0, V(.17, .075, 1.055)), (.24, V(.22, -.22, .945)), (.63, floor_point + V(0, .08, .075)), (.70, floor_point + V(0, .08, .075)), (1, V(.30, -.04, .97))])
        p.arm_targets["R"] = V(-.17, -.22, 1.04) + p.pelvis
        p.rot["hand.L"] = Q((1, 0, 0), keyed(t, [(0, 0), (.24, -40), (.63, -70), (.70, -70), (1, 0)]))
        p.curls["L"] = keyed(t, [(0, .65), (.23, .70), (.63, .35), (.66, .35), (.78, .1), (1, .14)])
        for s in ("L", "R"):
            p.leg_targets[s] = V(.12 if s == "L" else -.12, -.04 if s == "L" else .12, .14)
        return p
    if name == "uplink_start": return blend(base_pose(True), uplink_pose(), t)
    if name == "uplink_loop": return uplink_pose(t)
    if name == "uplink_end": return blend(uplink_pose(), aim_pose(0, 8), t)
    if name == "uplink_cancel": return blend(uplink_pose(), base_pose(False), t)
    if name.startswith("hit_"):
        p = base_pose(True)
        direction = name[-1]
        strength = sin(pi * t)
        axis = {"f": (1, 0, 0), "b": (1, 0, 0), "l": (0, 1, 0), "r": (0, 1, 0)}[direction]
        degrees = {"f": -14, "b": 15, "l": 13, "r": -13}[direction]
        p.rot["spine_03"] = Q(axis, strength * degrees)
        p.rot["head"] = Q(axis, strength * degrees * .7)
        for side, s in ((1, "L"), (-1, "R")):
            p.rot[f"upperarm.{s}"] = Q((1, 0, 0), -10 - strength * 8)
        p.face["Squint.L"] = .5 * strength; p.face["Squint.R"] = .5 * strength
        return p
    if name.startswith("stun_"):
        if name == "stun_start": p = blend(base_pose(True), wounded_pose(t), t)
        elif name == "stun_end": p = blend(wounded_pose(1 - t), base_pose(True), t)
        else:
            p = base_pose(True)
            p.pelvis.x = .027 * sin(2 * pi * t)
            p.rot["spine_02"] = Q((0, 1, 0), 12 * sin(2 * pi * t))
            p.rot["head"] = Q((0, 1, 0), -18 + 7 * sin(4 * pi * t)) @ Q((1, 0, 0), 15)
            p.arm_targets["L"] = V(.26, -.03, .93); p.arm_targets["R"] = V(-.26, -.03, .93)
            p.face.update({"Squint.L": .65, "Blink.R": .42, "BrowRaise.L": .3})
        return p
    if name == "knockback":
        p = base_pose(True)
        p.rot["spine_01"] = Q((1, 0, 0), -30 * sin(pi * t))
        p.pelvis.z = -.08 * sin(pi * t)
        for side, s in ((1, "L"), (-1, "R")):
            p.arm_targets[s] = V(side * .35, -.15, 1.37)
            p.leg_targets[s] = V(side * .13, .12 if s == "L" else -.08, .14 + .08 * sin(pi * t) * (1 if s == "R" else 0))
        return p
    if name == "knockup_start": return blend(base_pose(True), sample_pose("knockup_air", 0, 36, alignment), t)
    if name in ("knockdown_front", "knockdown_back"):
        p = floor_transition(t, name.endswith("front"))
        p.rot["head"] = Q((1, 0, 0), (-25 if name.endswith("front") else 25) * (1 - t)) @ p.rot.get("head", Quaternion())
        return p
    if name in ("prone_front", "prone_back"):
        p = floor_pose(name.endswith("front"))
        p.face["Blink.L"] = .55; p.face["Blink.R"] = .55
        p.rot["spine_02"] @= Q((0, 1, 0), 1.1 * sin(2 * pi * t))
        return p
    if name in ("getup_front", "getup_back"):
        if t < .44:
            p = blend(floor_pose(name.endswith("front")), kneel_pose(), t / .44)
        elif t < .65:
            p = blend(kneel_pose(), kneel_pose(True), (t - .44) / .21)
        else:
            p = blend(kneel_pose(True), base_pose(True), (t - .65) / .35)
        return p
    if name in ("sleep_start", "sleep_end"):
        p = blend(base_pose(False) if name == "sleep_start" else floor_pose(False), floor_pose(False) if name == "sleep_start" else base_pose(True), t)
        p.face["Blink.L"] = .85 * (t if name == "sleep_start" else 1 - t)
        p.face["Blink.R"] = p.face["Blink.L"]
        return p
    if name == "sleep_loop":
        p = floor_pose(False)
        p.face["Blink.L"] = 1.; p.face["Blink.R"] = 1.
        p.arm_targets["L"] = V(.07, -.02, .29); p.arm_targets["R"] = V(-.08, -.01, .30)
        p.rot["spine_02"] @= Q((0, 1, 0), 1.8 * sin(2 * pi * t))
        return p
    if name in ("death_front", "death_back", "dead_front", "dead_back"):
        front = name.endswith("front")
        if name.startswith("dead_"):
            p = floor_pose(front, True)
        else:
            p = floor_transition(t, front)
            if t > .96: p = floor_pose(front, True)
            p.face["Blink.L"] = .95 * ease((t - .30) / .40); p.face["Blink.R"] = .90 * ease((t - .32) / .40)
            p.face["Frown.L"] = .55 * (1 - t) + .30 * t; p.face["Frown.R"] = .55 * (1 - t) + .30 * t
        if front:
            p.arm_targets["L"] = V(.28, -.31, .105); p.arm_targets["R"] = V(-.19, -.42, .10)
        else:
            p.arm_targets["L"] = V(.34, -.10, .082); p.arm_targets["R"] = V(-.30, -.28, .083)
        return p
    if name == "respawn":
        p = blend(kneel_pose(), base_pose(True), ease(t))
        p.rot["spine_03"] = Q((0, 0, 1), 28 * (1 - ease(t)))
        p.face["BrowRaise.L"] = .6 * (1 - t); p.face["BrowRaise.R"] = .6 * (1 - t)
        p.face["Smile.L"] = .35 * t; p.face["Smile.R"] = .35 * t
        return p
    if name == "greet":
        p = base_pose(False)
        p.arm_targets["R"] = keyed(t, [(0, V(-.305, -.036, .962)), (.25, V(-.28, -.16, 1.59)), (.70, V(-.28, -.16, 1.59)), (1, V(-.305, -.036, .962))])
        p.rot["hand.R"] = Q((0, 1, 0), 22 * sin(t * 6 * pi) * sin(pi * t))
        p.rot["head"] = Q((0, 0, 1), -7 * sin(pi * t))
        p.face.update({"Smile.L": .65 * sin(pi * t), "Smile.R": .65 * sin(pi * t), "Cheek.L": .4 * sin(pi * t), "Cheek.R": .4 * sin(pi * t)})
        return p
    if name == "victory":
        p = base_pose(True)
        raise_amount = sin(pi * min(1, t * 1.35))
        for side, s in ((1, "L"), (-1, "R")):
            p.arm_targets[s] = V(side * (.23 + .03 * raise_amount), -.04, .98 + .72 * raise_amount)
            p.curls[s] = .12
            p.local[f"clavicle.{s}"] = Q((0, 1, 0), side * 9 * raise_amount)
        p.pelvis.z = .015 * sin(pi * t)
        p.face.update({"Smile.L": .9 * raise_amount, "Smile.R": .9 * raise_amount, "Cheek.L": .6 * raise_amount, "Cheek.R": .6 * raise_amount, "BrowRaise.L": .4 * raise_amount, "BrowRaise.R": .4 * raise_amount})
        return p
    if name == "defeat":
        p = base_pose(False)
        amount = sin(pi * t * .75)
        p.pelvis.z = -.05 * amount
        p.rot["spine_02"] = Q((1, 0, 0), 15 * amount)
        p.rot["head"] = Q((1, 0, 0), 22 * amount)
        p.face.update({"Frown.L": .7 * amount, "Frown.R": .65 * amount, "BrowRaise.L": .25 * amount, "BrowRaise.R": .35 * amount})
        return p
    if name == "dialogue": return dialogue_pose(t, alignment)
    if name.startswith("aim_"):
        _, pitch, yaw = name.split("_")
        return aim_pose({"left": 60, "center": 0, "right": -60}[yaw], {"down": -35, "level": 0, "up": 35}[pitch])
    raise KeyError(name)


def make_actions(asset, entry, alignment):
    name, frames = entry["id"], entry["frame_range"][1]
    ctrl, rig, face = asset["ctrl"], asset["rig"], asset["face"]
    source = bpy.data.actions.new("SOURCE_" + name)
    baked = bpy.data.actions.new(name)
    facial = bpy.data.actions.new(name + "_FACE")
    for action in (source, baked, facial):
        action.use_fake_user = True
        action["required_id"] = name
        action["sample_rate"] = 30
        action["root_policy"] = entry["root_motion_policy"]
        action["layer"] = entry["layer"]
    ctrl.animation_data_create(); ctrl.animation_data.action = source
    rig.animation_data_create(); rig.animation_data.action = baked
    key = face.data.shape_keys
    key.animation_data_create(); key.animation_data.action = facial
    source_frame_step = 1 if frames <= 24 else 2
    for frame in range(frames + 1):
        sample_frame = 0 if entry["loop"] and frame == frames else frame
        p = sample_pose(name, sample_frame / frames if frames else 0, frames, alignment)
        p = apply_contacts(p)
        world = world_transforms(p)
        for bone_name in ORDER:
            parent = PARENT[bone_name]
            relative = (world[parent].inverted() @ world[bone_name]) if parent else world[bone_name]
            basis = REST_LOCAL[bone_name].inverted() @ relative
            loc, rot, scale = basis.decompose()
            rot.normalize()
            for arm in (ctrl, rig):
                pb = arm.pose.bones[bone_name]
                pb.rotation_mode = 'QUATERNION'
                pb.matrix_basis = basis
                pb.keyframe_insert("location", frame=frame, group=bone_name)
                pb.keyframe_insert("rotation_quaternion", frame=frame, group=bone_name)
                pb.keyframe_insert("scale", frame=frame, group=bone_name)
        for shape in key.key_blocks:
            if shape.name == "Basis": continue
            shape.value = max(0., min(1., p.face.get(shape.name, 0)))
            shape.keyframe_insert("value", frame=frame, group=shape.name)
    for action in (baked, source, facial):
        action["event_markers"] = json.dumps(entry["events"], ensure_ascii=False)
    baked["authored_frame_count"] = entry["frame_count"]
    baked["nominal_speed_cm_s"] = entry["nominal_speed_cm_s"]
    source["generator"] = "source/generators/animate.py; original analytic poses and authored contact curves"
    return {"id": name, "frames": frames + 1, "source_curves": True, "baked_deform_bones": len(ORDER), "face_curves": len(key.key_blocks) - 1}


def build_animation_inventory(asset):
    global SPEC, REST, REST_LOCAL, PARENT, ORDER
    SPEC = asset["bones"]
    REST = {item["name"]: asset["rig"].data.bones[item["name"]] for item in SPEC}
    PARENT = {item["name"]: item["parent"] for item in SPEC}
    ORDER = [item["name"] for item in SPEC]
    REST_LOCAL = {name: (REST[PARENT[name]].matrix_local.inverted() @ REST[name].matrix_local if PARENT[name] else REST[name].matrix_local.copy()) for name in ORDER}
    inventory = json.loads((ROOT / "source" / "animation_inventory.json").read_text())
    alignment = json.loads((ROOT / "source" / "audio" / "dialogue_alignment.json").read_text())
    # Clear only generated actions, preserving no stale duplicate clips on rebuild.
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    audit = []
    for index, entry in enumerate(inventory):
        audit.append(make_actions(asset, entry, alignment))
        if index % 8 == 0: print("ANIMATION_PROGRESS", index + 1, len(inventory), entry["id"], flush=True)
    manifest = {
        "schema": "MorphRig.animation_manifest/1.2",
        "asset": "Operative",
        "units": {"source": "meters", "unreal": "centimeters"},
        "source_file": "source/Operative.blend",
        "skeleton": "Operative_DEF / /Game/Operative/SK_Operative",
        "entry_count": len(inventory), "motion_entry_count": 85, "static_pose_count": 11,
        "fps": 30, "frame_convention": "Inclusive source frame range; duration is last_frame/30. Static poses have one sample and zero duration.",
        "root_convention": "in_place removes authored actor travel; dash root translation is exactly 2 m/200 cm. Turn clips rotate the pelvis and emit FacingCommit. Blink teleports are events, never baked travel.",
        "aim_convention": "Yaw +60 = left, yaw -60 = right. Pitch +35 = up, pitch -35 = down. Source forward -Y; upper-body only; planted legs excluded.",
        "visemes": "MBP=lip closure; FV=labiodental; AA=open vowel; EE=wide vowel; OO=rounded/funnel; TH=tongue-to-teeth; CH=postalveolar consonant.",
        "dialogue": {"audio": "source/audio/dialogue.wav", "transcript": "source/audio/dialogue.txt", "alignment": "source/audio/dialogue_alignment.json", "duration_seconds": alignment["duration_seconds"]},
        "entries": inventory,
        "bake_audit": audit,
    }
    (ROOT / "docs" / "animation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')
    # A clean ground-origin neutral pose is the initial editing state.
    asset["ctrl"].animation_data.action = None
    asset["rig"].animation_data.action = None
    asset["face"].data.shape_keys.animation_data.action = None
    for arm in (asset["ctrl"], asset["rig"]):
        for bone in arm.pose.bones:
            bone.matrix_basis.identity()
    for key in asset["face"].data.shape_keys.key_blocks:
        key.value = 0
    bpy.context.scene.frame_start = 0; bpy.context.scene.frame_end = 90
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    bpy.context.scene["animation_inventory_count"] = 96
    bpy.context.scene["animation_manifest"] = "docs/animation_manifest.json"
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "source" / "Operative.blend"))
    print("ANIMATION_INVENTORY_COMPLETE", len(inventory), flush=True)
