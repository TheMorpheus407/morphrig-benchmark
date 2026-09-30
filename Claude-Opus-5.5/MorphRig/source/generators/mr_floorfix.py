"""MorphRig automatic floor-contact correction on the deformed mesh.

Iteratively: evaluate every frame of the clip, find the deepest body vertex below the
floor, classify it (foot / leg / hand / arm / body) and insert a corrective key on the
responsible control (foot IK, hand IK, FK shoulder, or the centre of gravity).  The
corrective keys become part of the clip's editable key set.
"""
import numpy as np
import bpy
import mr_clip
from mr_qa import BODY_MESHES

TARGET = 0.003
TOL = -0.006


def _rest_coords(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def scan(frames, obs, rest):
    sc = bpy.context.scene
    worst = (1e9, None, -1, -1)
    per_frame = np.zeros(frames + 1)
    for f in range(frames + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        fmin = 1e9
        for o in obs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            z = co[2::3]
            i = int(np.argmin(z))
            if z[i] < fmin:
                fmin = float(z[i])
            if z[i] < worst[0]:
                worst = (float(z[i]), o.name, f, i)
        per_frame[f] = fmin
    return worst, per_frame


def classify(obj, vi, rest):
    if obj.startswith("MR_Boot_"):
        return "foot_" + obj[-1].lower()
    if obj == "MR_HandL":
        return "arm_l"
    if obj == "MR_CyberArm":
        return "arm_r"
    if obj in ("MR_Suit", "MR_Gear"):
        p = rest[obj][vi]
        if p[2] < 0.84:
            return "leg_" + ("l" if p[0] > 0 else "r")
        if p[0] > 0.20:
            return "arm_l"
        if p[0] < -0.20:
            return "arm_r"
    return "cog"


def _eval_channels_at(clip, keyed, f):
    frames = np.array([f])
    ser = mr_clip.evaluate_channels(clip, keyed, frames)
    return {k: v[0].copy() for k, v in ser.items()}


def correct(R, ch, kind, d, rig):
    rest = R.m.rest
    if kind.startswith("foot_"):
        s = kind[-1]
        ch[f"c_foot_ik_{s}.loc"] = ch[f"c_foot_ik_{s}.loc"] + np.array([0, 0, d * 1.15])
    elif kind.startswith("arm_"):
        s = kind[-1]
        if ch[f"c_hand_ik_{s}[ik_fk]"][0] > 0.5:
            Rr = rest[f"c_hand_ik_{s}"][:3, :3]
            ch[f"c_hand_ik_{s}.loc"] = ch[f"c_hand_ik_{s}.loc"] + Rr.T @ np.array([0, 0, d * 1.2])
        else:
            # lift the FK arm: raise the shoulder (flexion toward the body's up) by an angle ~ d / 0.55 m
            ang = min(0.6, d / 0.5 * 1.2)
            best = None
            base = ch[f"c_upperarm_fk_{s}.rot"].copy()
            for axis in (0, 2):
                for sg in (-1.0, 1.0):
                    cand = base.copy()
                    cand[axis] += sg * 0.15
                    h = _hand_height(rig, ch, s, cand)
                    if best is None or h > best[0]:
                        best = (h, axis, sg)
            ch[f"c_upperarm_fk_{s}.rot"] = base + np.eye(3)[best[1]] * best[2] * ang
    else:
        # centre of gravity up (c_torso local +Y == world +Z)
        ch["c_torso.loc"] = ch["c_torso.loc"] + np.array([0, d * 1.1, 0])
    return ch


def _hand_height(rig, ch, s, rot):
    pbs = rig.pose.bones
    saved = rig.animation_data.action
    rig.animation_data.action = None
    for name, val in ch.items():
        if name.endswith(".loc"):
            pbs[name[:-4]].location = tuple(val)
        elif name.endswith(".rot"):
            pbs[name[:-4]].rotation_euler = tuple(val)
        elif name.endswith(".quat"):
            pbs[name[:-5]].rotation_quaternion = tuple(val)
        elif "[" in name:
            b, p = name.split("[", 1)
            pbs[b][p[:-1]] = float(val[0])
    pbs[f"c_upperarm_fk_{s}"].rotation_euler = tuple(rot)
    bpy.context.view_layer.update()
    h = float(np.array(pbs[f"hand_{s}"].matrix)[2, 3])
    rig.animation_data.action = saved
    if saved and saved.slots:
        rig.animation_data.action_slot = saved.slots[0]
    return h


def _lowest(obs):
    dg = bpy.context.evaluated_depsgraph_get()
    worst = (1e9, None, -1)
    for o in obs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        z = co[2::3]
        i = int(np.argmin(z))
        if z[i] < worst[0]:
            worst = (float(z[i]), o.name, i)
    return worst


def floor_fix(rig, R, clip, keyed, max_iter=45, log=None):
    from mr_contactfix import apply_channels
    obs = [bpy.data.objects[n] for n in BODY_MESHES if n in bpy.data.objects]
    for o in obs:
        o.hide_viewport = False
    rest = {o.name: _rest_coords(o) for o in obs}
    fixes = 0
    act = None
    # pass 1: authored key poses (fixing a held pose once is cleaner than many inserted keys)
    if rig.animation_data:
        rig.animation_data.action = None
    for i, (f, ch, itp) in enumerate(keyed):
        ch2 = {k: np.asarray(v, float).copy() for k, v in ch.items()}
        changed = False
        for _ in range(6):
            apply_channels(rig, ch2)
            z, obj, vi = _lowest(obs)
            if z >= TOL:
                break
            ch2 = correct(R, ch2, classify(obj, vi, rest), TARGET - z, rig)
            changed = True
        if changed:
            keyed[i] = (f, ch2, itp)
            fixes += 1
            if log is not None:
                log.append(("key", f, obj, round(z * 100, 2)))
    if clip.loop and keyed and keyed[-1][0] == clip.frames:
        keyed[-1] = (keyed[-1][0], {k: v.copy() for k, v in keyed[0][1].items()}, keyed[-1][2])
    for it in range(max_iter):
        act, _ = mr_clip.write_keyed(rig, clip, keyed)
        mr_clip.assign_action(rig, act)
        (z, obj, f, vi), per = scan(clip.frames, obs, rest)
        if z >= TOL:
            break
        kind = classify(obj, vi, rest)
        d = TARGET - z
        ch = _eval_channels_at(clip, keyed, f)
        ch = correct(R, ch, kind, d, rig)
        # replace or insert key at f
        keyed = [k for k in keyed if abs(k[0] - f) > 0.5]
        keyed.append((float(f), ch, "BEZIER"))
        keyed.sort(key=lambda k: k[0])
        if clip.loop and f == 0:
            keyed = [k for k in keyed if k[0] != clip.frames] + [(float(clip.frames), ch, "BEZIER")]
        fixes += 1
        if log is not None:
            log.append((it, f, obj, kind, round(z * 100, 2)))
    for o in obs:
        o.hide_viewport = True
    return keyed, act, fixes
