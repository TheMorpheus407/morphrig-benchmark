"""MorphRig authoring helpers: pose probing, IK targets for props, aiming, step planning."""
import math
import numpy as np
import bpy
from mathutils import Matrix

from mr_anim import DEG, rot_z, axis_angle, to_M4, merge
from mr_params import J, H, FOOT_DIR_L, nrm, v
from mr_poses import ANKLE
import mr_skeleton


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def smoother(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


class Prober:
    """Apply a semantic pose directly to MR_Rig and read evaluated bone matrices."""

    def __init__(self, realizer):
        self.R = realizer
        self.rig = realizer.rig
        self.skel = bpy.data.objects["MR_Skeleton"]
        self._saved = None

    def apply(self, pose):
        ch = self.R.realize(pose)
        pbs = self.rig.pose.bones
        if self.rig.animation_data:
            self._saved = self.rig.animation_data.action
            self.rig.animation_data.action = None
        import mr_clip
        ch = mr_clip.snap_ik_to_fk(self.R, ch) if any(k.startswith("@") for k in ch) else ch
        for name, val in ch.items():
            if name.startswith("@"):
                continue
            if name.endswith(".loc"):
                pbs[name[:-4]].location = tuple(val)
            elif name.endswith(".rot"):
                pbs[name[:-4]].rotation_euler = tuple(val)
            elif name.endswith(".quat"):
                pbs[name[:-5]].rotation_quaternion = tuple(val)
            else:
                b, p = name.split("[", 1)
                pbs[b][p[:-1]] = float(val[0])
        bpy.context.view_layer.update()

    def world(self, pose, bones):
        self.apply(pose)
        return {b: np.array(self.skel.pose.bones[b].matrix) for b in bones}

    def rig_world(self, pose, bones):
        self.apply(pose)
        return {b: np.array(self.rig.pose.bones[b].matrix) for b in bones}


# ---------------------------------------------------------------- prop grips
_GRIPS = {}


def grip(prop):
    """Prop matrix expressed in hand_l bone space (as used by the rig Child Of constraints)."""
    if prop in _GRIPS:
        return _GRIPS[prop]
    rig = bpy.data.objects["MR_Rig"]
    pb = rig.pose.bones["prop_cell" if prop == "cell" else "prop_beacon"]
    con = pb.constraints["in_hand"]
    rest = np.array(pb.bone.matrix_local)
    inv = np.array(con.inverse_matrix)
    G = inv @ rest          # inverse = G @ rest^-1  ->  G = inverse @ rest
    _GRIPS[prop] = G
    return G


def hand_for_prop(prop_world, prop):
    """World matrix for the left hand so that the held prop sits exactly at prop_world."""
    return prop_world @ np.linalg.inv(grip(prop))


# ---------------------------------------------------------------- arm helpers
UPPER = float(np.linalg.norm(J["lowerarm_l"] - J["upperarm_l"]))
FORE = float(np.linalg.norm(J["hand_l"] - J["lowerarm_l"]))


def hand_rot(fingers_dir, back_dir):
    """Hand bone world rotation: Y along the fingers, Z = back of the hand."""
    y = nrm(fingers_dir)
    z = nrm(back_dir - np.dot(back_dir, y) * y)
    x = np.cross(y, z)
    return np.stack([x, y, z], 1)


def elbow_pole(shoulder, hand, out_dir, dist=0.4):
    mid = 0.5 * (np.asarray(shoulder) + np.asarray(hand))
    return mid + nrm(out_dir) * dist


def aim_arm(shoulder_world, aim_dir, side="r", upper_bias=(0, 0, -0.30), lateral=0.18):
    """Right-arm IK solution pointing the forearm exactly along aim_dir.

    Returns (hand_pos, elbow_pos, pole_pos)."""
    d = nrm(aim_dir)
    sgn = -1.0 if side == "r" else 1.0
    lat = nrm(np.cross(np.array([0, 0, 1.0]), d)) * -sgn   # outward side of the arm
    u = nrm(d + np.asarray(upper_bias) + lat * lateral)
    elbow = shoulder_world + u * UPPER
    hand = elbow + d * FORE
    pole = elbow + nrm(np.cross(d, np.cross(u, d)) * -1 + lat * 0.5 - d * 0.2) * 0.35
    # pole pointing away from the bend: the elbow points out/back/down
    bend_out = nrm((elbow - (shoulder_world + hand) * 0.5))
    pole = elbow + bend_out * 0.4
    return hand, elbow, pole


# ---------------------------------------------------------------- step planner
class Steps:
    """World-space foot plants for one-shot clips (in root space for in-place clips).

    plants[side] = list of (frame_down, frame_up, (x, y), yaw_deg)  with frame_up None for the last.
    Swing between plants uses a smooth arc with lift; heel/toe roll optional.
    """

    def __init__(self, nframes):
        self.n = nframes
        self.plants = {"l": [], "r": []}

    def plant(self, side, f_down, f_up, xy, yaw, lift=0.07, roll_out=0.35, roll_in=-0.25):
        self.plants[side].append(dict(down=f_down, up=f_up, xy=np.asarray(xy, float), yaw=yaw, lift=lift,
                                      roll_out=roll_out, roll_in=roll_in))
        return self

    def foot_at(self, side, f):
        P = self.plants[side]
        z = ANKLE[side][2]
        for i, p in enumerate(P):
            up = p["up"] if p["up"] is not None else self.n + 999
            if p["down"] <= f <= up:
                roll = 0.0
                # heel-off before lift
                if p["up"] is not None and p["roll_out"]:
                    t0 = up - 4
                    if f > t0:
                        roll = p["roll_out"] * smooth((f - t0) / 4.0)
                if i > 0 and p["roll_in"] and f < p["down"] + 3:
                    roll = p["roll_in"] * (1 - smooth((f - p["down"]) / 3.0))
                return dict(pos=(p["xy"][0], p["xy"][1], z), yaw=p["yaw"], heelroll=roll)
            if i + 1 < len(P) and up < f < P[i + 1]["down"]:
                q = P[i + 1]
                u = (f - up) / float(q["down"] - up)
                us = smoother(u)
                xy = (1 - us) * p["xy"] + us * q["xy"]
                yaw = (1 - us) * p["yaw"] + us * q["yaw"]
                h = q["lift"] * math.sin(math.pi * u) ** 1.2
                roll = p["roll_out"] * (1 - smooth(u / 0.35)) + q["roll_in"] * smooth((u - 0.7) / 0.3)
                pitch = -10.0 * math.sin(math.pi * min(1.0, u / 0.8))
                return dict(pos=(xy[0], xy[1], z + h), yaw=yaw, heelroll=roll, pitch=pitch)
        # before the first plant / after the last
        p = P[0] if f < P[0]["down"] else P[-1]
        return dict(pos=(p["xy"][0], p["xy"][1], z), yaw=p["yaw"], heelroll=0.0)


def stance_xy(side, dx=0.0, dy=0.0):
    a = ANKLE[side]
    return (a[0] + dx, a[1] + dy)


def rotate_xy(xy, yaw_deg, center=(0.0, 0.0)):
    c = np.asarray(center, float)
    R = rot_z(yaw_deg * DEG)[:2, :2]
    return tuple(c + R @ (np.asarray(xy, float) - c))


# ---------------------------------------------------------------- floor contact
FLOOR_MESHES = ("MR_Suit", "MR_Head", "MR_Boot_L", "MR_Boot_R", "MR_HandL", "MR_CyberArm")


_REST_Z = {}


def _rest_z(ob):
    if ob.name not in _REST_Z:
        co = np.empty(len(ob.data.vertices) * 3)
        ob.data.vertices.foreach_get("co", co)
        _REST_Z[ob.name] = co.reshape(-1, 3)[:, 2].copy()
    return _REST_Z[ob.name]


def mesh_min_z(prober, pose, meshes=FLOOR_MESHES, upper_only=False, apply=True):
    """Lowest deformed vertex (world z) of the given meshes for a pose.
    upper_only: only suit vertices whose rest height is above the crotch (torso + arms)."""
    if apply:
        prober.apply(pose)
    lo = 1e9
    per = {}
    for name in meshes:
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        was_hidden = ob.hide_viewport
        if was_hidden:
            ob.hide_viewport = False
            bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        ev.to_mesh_clear()
        if was_hidden:
            ob.hide_viewport = True
        if upper_only and name == "MR_Suit":
            co = co[_rest_z(ob) > 0.86]
        z = float(co[:, 2].min())
        per[name] = z
        lo = min(lo, z)
    return lo, per


def settle(prober, pose, target=0.004, meshes=("MR_Suit", "MR_Head"), iters=4, upper_only=False):
    """Shift the COG vertically so the lowest body point rests on the floor (z = target)."""
    p = dict(pose)
    for _ in range(iters):
        z, _ = mesh_min_z(prober, p, meshes, upper_only=upper_only)
        dz = target - z
        if abs(dz) < 0.0015:
            break
        c = list(p.get("cog", (0, 0, 0)))
        c[2] += dz
        p["cog"] = tuple(c)
    return p


def leg_min_z(prober, pose, side, apply=True):
    """Lowest point of one leg: suit leg surface (rest z < crotch) on that side + its boot."""
    if apply:
        prober.apply(pose)
    dg = bpy.context.evaluated_depsgraph_get()
    lo = 1e9
    for name in ("MR_Suit", "MR_Boot_" + side.upper()):
        ob = bpy.data.objects[name]
        was_hidden = ob.hide_viewport
        if was_hidden:
            ob.hide_viewport = False
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        ev.to_mesh_clear()
        if was_hidden:
            ob.hide_viewport = True
        if name == "MR_Suit":
            rest = np.empty(len(ob.data.vertices) * 3)
            ob.data.vertices.foreach_get("co", rest)
            rest = rest.reshape(-1, 3)
            sel = (rest[:, 2] < 0.84) & ((rest[:, 0] > 0) if side == "l" else (rest[:, 0] < 0))
            co = co[sel]
        lo = min(lo, float(co[:, 2].min()))
    return lo


def settle_legs(prober, pose, sides="lr", target=0.004, sign=1.0, iters=9):
    """Adjust FK hip flexion of lying/sitting legs until each whole leg touches the floor.

    sign=+1: more flexion lifts the leg (face-up / sitting); -1 for face-down."""
    p = dict(pose)
    for s in sides:
        lg = dict(p["leg_" + s])
        fk = list(lg.get("fk", (0, 0, 0)))
        lo_a, hi_a = fk[0] - 40.0, fk[0] + 40.0
        for _ in range(iters):
            mid = 0.5 * (lo_a + hi_a)
            fk[0] = mid
            lg["fk"] = tuple(fk)
            p["leg_" + s] = dict(lg)
            z = leg_min_z(prober, p, s)
            if (z - target) * sign > 0:
                hi_a = mid
            else:
                lo_a = mid
        fk[0] = 0.5 * (lo_a + hi_a)
        lg["fk"] = tuple(fk)
        p["leg_" + s] = lg
    return p


def settle_lying(prober, pose, face_up=True, target=0.004):
    p = settle(prober, pose, target, ("MR_Suit", "MR_Head"), upper_only=True)
    p = settle_legs(prober, p, "lr", target, sign=1.0 if face_up else -1.0)
    p = settle(prober, p, target, ("MR_Suit", "MR_Head"), upper_only=True)
    return p


def hip_world(prober, pose, side):
    W = prober.world(pose, ["thigh_" + side])
    return W["thigh_" + side][:3, 3]


def settle_sitting(prober, pose, target=0.004):
    p = settle(prober, pose, target, ("MR_Suit",), upper_only=True)
    p = settle_legs(prober, p, "lr", target, sign=1.0)
    p = settle(prober, p, target, ("MR_Suit",), upper_only=True)
    return p
