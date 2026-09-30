"""MorphRig automatic hand / forearm vs body contact correction (companion of mr_floorfix).

Deformed-mesh test: left hand + left forearm sleeve and the cyber forearm/hand against the
torso, hips/thighs (suit faces dominated by those bones) and the head.  A tester vertex is
'inside' when it lies under an obstacle face (see mr_qa.body_clearance).

Pass 1 corrects the authored key poses in place, pass 2 inserts corrective keys at the worst
remaining in-between frames.  Every correction evaluates a few candidate moves on the rig
(IK: move hand target / elbow pole along the push direction; FK: nudge shoulder and elbow)
and keeps the one with the smallest combined body + floor penetration.  Corrected keys stay
ordinary editable keys of the clip.
"""
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import mr_clip
import mr_qa

TOL = 0.003          # tolerated penetration (m)
MARGIN = 0.004       # clearance aimed for after a fix
NAMES = ("MR_Suit", "MR_Head", "MR_HandL", "MR_CyberArm", "MR_Gear")


class Checker:
    def __init__(self):
        self.st = mr_qa._clearance_setup()
        self.obs = {n: bpy.data.objects[n] for n in NAMES if n in bpy.data.objects}

    def show(self, on):
        for o in self.obs.values():
            o.hide_viewport = not on

    def coords(self):
        dg = bpy.context.evaluated_depsgraph_get()
        co = {}
        for n, o in self.obs.items():
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            a = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", a)
            ev.to_mesh_clear()
            co[n] = a.reshape(-1, 3)
        return co

    def measure(self, co=None, sides="lr"):
        """side -> dict(depth, push (unit world vector), n, floor)"""
        co = co or self.coords()
        S = co["MR_Suit"]
        trees = [BVHTree.FromPolygons([Vector(p) for p in S], self.st["obst_polys"]),
                 BVHTree.FromPolygons([Vector(p) for p in co["MR_Head"]], self.st["head_polys"])]
        tl = [co["MR_HandL"], S[self.st["sleeve_l"]]]
        if "MR_Gear" in co and self.st["gear_polys"]:
            trees.append(BVHTree.FromPolygons([Vector(p) for p in co["MR_Gear"]], self.st["gear_polys"]))
            if self.st["bracer"].any():
                tl.append(co["MR_Gear"][self.st["bracer"]])
        testers = {"l": np.concatenate(tl), "r": co["MR_CyberArm"][self.st["cyb_sel"]]}
        out = {}
        for s in sides:
            P = testers[s]
            depth, push, n = 0.0, np.zeros(3), 0
            for p in P:
                pv = Vector(p)
                for tree in trees:
                    loc, nr, idx, dist = tree.find_nearest(pv, 0.06)
                    if loc is None:
                        continue
                    sd = (pv - loc).dot(nr)
                    if sd < -0.0015 and -sd > 0.9 * dist:
                        depth = max(depth, dist)
                        push += np.array(nr) * dist
                        n += 1
            nn = np.linalg.norm(push)
            out[s] = dict(depth=depth, push=push / nn if nn > 1e-9 else np.zeros(3), n=n,
                          floor=max(0.0, -float(P[:, 2].min())))
        return out


def apply_channels(rig, ch):
    pbs = rig.pose.bones
    for name, val in ch.items():
        if name.startswith("@"):
            continue
        if name.endswith(".loc"):
            pbs[name[:-4]].location = tuple(val)
        elif name.endswith(".rot"):
            pbs[name[:-4]].rotation_euler = tuple(val)
        elif name.endswith(".quat"):
            pbs[name[:-5]].rotation_quaternion = tuple(val)
        elif "[" in name:
            b, p = name.split("[", 1)
            pbs[b][p[:-1]] = float(val[0])
    bpy.context.view_layer.update()


def _cost(m):
    return m["depth"] * 10.0 + m["floor"] * 10.0


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _candidates(R, ch, s, m):
    """Candidate channel dicts that move side s out of the body."""
    d = m["depth"] + MARGIN
    push = m["push"]
    out = []

    def cp(src):
        return {k: v.copy() for k, v in src.items()}
    if ch[f"c_hand_ik_{s}[ik_fk]"][0] > 0.5:
        Rr = R.m.rest[f"c_hand_ik_{s}"][:3, :3]
        Rp = R.m.rest[f"c_elbow_pole_{s}"][:3, :3]
        horiz = push.copy()
        horiz[2] = 0.0
        hn = np.linalg.norm(horiz)
        dirs = [push, push + np.array([0, 0, 0.5])]
        if hn > 0.2:
            dirs.append(horiz / hn)
        for dv in dirs:
            dv = dv / max(np.linalg.norm(dv), 1e-9)
            for scale in (1.0, 1.6, 2.4):
                c = cp(ch)
                c[f"c_hand_ik_{s}.loc"] = c[f"c_hand_ik_{s}.loc"] + Rr.T @ (dv * d * scale)
                out.append(c)
                c2 = cp(c)
                c2[f"c_elbow_pole_{s}.loc"] = c2[f"c_elbow_pole_{s}.loc"] + Rp.T @ (dv * 0.15)
                out.append(c2)
        # tilt the hand (about its local X / Z) so fingertips lift off the surface
        ang = float(np.clip(d / 0.12, 0.05, 0.4))
        for ax in (np.array([1.0, 0, 0]), np.array([0, 0, 1.0])):
            for sg in (-1.0, 1.0):
                q = np.concatenate([[np.cos(sg * ang / 2)], np.sin(sg * ang / 2) * ax])
                c = cp(ch)
                c[f"c_hand_ik_{s}.quat"] = _quat_mul(c[f"c_hand_ik_{s}.quat"], q)
                out.append(c)
    else:
        ang = float(np.clip(d / 0.35, 0.02, 0.45))
        for mult in (1.0, 2.0):
            a = ang * mult
            for axis in (0, 1, 2):
                for sg in (-1.0, 1.0):
                    c = cp(ch)
                    c[f"c_upperarm_fk_{s}.rot"] = c[f"c_upperarm_fk_{s}.rot"] + np.eye(3)[axis] * sg * a
                    out.append(c)
            for sg in (-1.0, 1.0):
                c = cp(ch)
                c[f"c_lowerarm_fk_{s}.rot"] = c[f"c_lowerarm_fk_{s}.rot"] + np.array([sg * a * 1.2, 0, 0])
                out.append(c)
            for axis in (0, 2):
                for sg in (-1.0, 1.0):
                    c = cp(ch)
                    c[f"c_hand_fk_{s}.rot"] = c[f"c_hand_fk_{s}.rot"] + np.eye(3)[axis] * sg * a * 2.0
                    out.append(c)
    return out


def fix_pose(rig, R, chk, ch, max_steps=10):
    """Correct a channel dict in place until both arms are clear (or no candidate helps)."""
    apply_channels(rig, ch)
    m = chk.measure()
    changed = False
    for _ in range(max_steps):
        bad = [s for s in "lr" if m[s]["depth"] > TOL]
        if not bad:
            break
        s = max(bad, key=lambda k: m[k]["depth"])
        best = None
        for c in _candidates(R, ch, s, m[s]):
            apply_channels(rig, c)
            mc = chk.measure()
            cost = _cost(mc[s]) + 0.5 * _cost(mc["r" if s == "l" else "l"])
            if best is None or cost < best[0]:
                best = (cost, c, mc)
        cur = _cost(m[s]) + 0.5 * _cost(m["r" if s == "l" else "l"])
        if best is None or best[0] >= cur - 1e-5:
            break
        c = best[1]
        if c[f"c_hand_ik_{s}[ik_fk]"][0] <= 0.5:
            # FK arm moved: re-match the IK control to it so IK/FK blends stay consistent
            c["@snap"] = [s]
            c = mr_clip.snap_ik_to_fk(R, c)
        ch.clear()
        ch.update(c)
        m = best[2]
        changed = True
    apply_channels(rig, ch)
    return changed, m


def scan(rig, clip, chk, step=1):
    sc = bpy.context.scene
    worst = (0.0, -1, None)
    for f in range(0, clip.frames + 1, step):
        sc.frame_set(f)
        m = chk.measure()
        for s in "lr":
            if m[s]["depth"] > worst[0]:
                worst = (m[s]["depth"], f, s)
    return worst


def contact_fix(rig, R, clip, keyed, max_iter=24, log=None):
    chk = Checker()
    chk.show(True)
    saved = rig.animation_data.action if rig.animation_data else None
    if rig.animation_data:
        rig.animation_data.action = None
    fixes = 0
    # pass 1: authored key poses
    for i, (f, ch, it) in enumerate(keyed):
        ch2 = {k: np.asarray(v, float).copy() for k, v in ch.items()}
        changed, m = fix_pose(rig, R, chk, ch2)
        if changed:
            keyed[i] = (f, ch2, it)
            fixes += 1
            if log is not None:
                log.append(("key", f, round(max(m["l"]["depth"], m["r"]["depth"]) * 100, 2)))
    if clip.loop and keyed and keyed[-1][0] == clip.frames:
        keyed[-1] = (keyed[-1][0], {k: v.copy() for k, v in keyed[0][1].items()}, keyed[-1][2])
    # pass 2: in-between frames
    act = None
    for it in range(max_iter):
        act, _ = mr_clip.write_keyed(rig, clip, keyed)
        mr_clip.assign_action(rig, act)
        depth, f, s = scan(rig, clip, chk)
        if depth <= TOL or f < 0:
            break
        # correct the pose as played (keys + procedural layers), then move only the correction
        # into a new key made of the un-layered channels (layers are re-applied on write)
        frames = np.arange(0, clip.frames + 1)
        ser = mr_clip.evaluate_channels(clip, keyed, frames)
        lay = {k: v.copy() for k, v in ser.items()}
        for layer in clip.layers:
            layer(frames, lay)
        base_lay = {k: lay[k][f].copy() for k in lay}
        ch_l = {k: v.copy() for k, v in base_lay.items()}
        rig.animation_data.action = None
        changed, m = fix_pose(rig, R, chk, ch_l)
        ch = {}
        for k, v in ser.items():
            if k.endswith(".quat") or "[" in k:
                ch[k] = ch_l[k].copy() if not np.allclose(ch_l[k], base_lay[k]) else v[f].copy()
            else:
                ch[k] = v[f] + (ch_l[k] - base_lay[k])
        if not changed:
            if log is not None:
                log.append(("stuck", f, round(depth * 100, 2)))
            break
        keyed = [k for k in keyed if abs(k[0] - f) > 0.5]
        keyed.append((float(f), ch, "BEZIER"))
        keyed.sort(key=lambda k: k[0])
        if clip.loop and f in (0, clip.frames):
            keyed = [k for k in keyed if k[0] not in (0.0, float(clip.frames))]
            keyed = [(0.0, ch, "BEZIER")] + keyed + [(float(clip.frames), {k: v.copy() for k, v in ch.items()}, "BEZIER")]
        fixes += 1
        if log is not None:
            log.append(("frame", f, s, round(depth * 100, 2)))
    chk.show(False)
    if saved is not None and act is None:
        rig.animation_data.action = saved
    return keyed, fixes
