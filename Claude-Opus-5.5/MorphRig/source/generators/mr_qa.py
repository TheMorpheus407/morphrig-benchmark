"""MorphRig motion QA on baked skeleton data (foot sliding, ground penetration, loop seams)."""
import numpy as np
from mr_params import J

_SOLE = None


def _sole_points(baked):
    """Heel / ball / toe-tip ground points expressed in foot / ball bone space (from rest)."""
    global _SOLE
    if _SOLE is not None:
        return _SOLE
    import bpy
    skel = bpy.data.objects["MR_Skeleton"]
    out = {}
    for s in "lr":
        foot_rest = np.array(skel.data.bones[f"foot_{s}"].matrix_local)
        ball_rest = np.array(skel.data.bones[f"ball_{s}"].matrix_local)
        heel = np.append(J[f"heel_{s}"], 1.0)
        ball = J[f"ball_{s}"].copy()
        ball[2] = 0.0
        ball = np.append(ball, 1.0)
        toe = J[f"toe_end_{s}"].copy()
        toe[2] = 0.0
        toe = np.append(toe, 1.0)
        out[s] = {"heel": ("foot", np.linalg.inv(foot_rest) @ heel),
                  "ball": ("foot", np.linalg.inv(foot_rest) @ ball),
                  "toe": ("ball", np.linalg.inv(ball_rest) @ toe)}
    _SOLE = out
    return out


def sole_world(baked, s):
    sp = _sole_points(baked)[s]
    res = {}
    for k, (b, p) in sp.items():
        W = baked["world"][f"{b}_{s}"]
        res[k] = np.einsum("fij,j->fi", W, p)[:, :3]
    return res


def check_clip(clip, baked):
    nf = clip.frames + 1
    q = {}
    # loop seam
    if clip.loop:
        worst = 0.0
        for n in baked["bones"]:
            dl = np.linalg.norm(baked["loc"][n][0] - baked["loc"][n][-1])
            d = abs(float(np.dot(baked["rot"][n][0], baked["rot"][n][-1])))
            ang = 2 * np.degrees(np.arccos(min(1.0, d)))
            worst = max(worst, dl * 100.0, ang)
        q["loop_seam"] = round(worst, 3)
    # sole points: penetration and sliding during contacts
    travel = np.zeros(3)
    t = np.arange(nf) / 30.0
    offs = np.zeros((nf, 3))
    if clip.root == "in_place" and clip.speed > 0 and "travel_dir" in clip.extra:
        tdir = np.asarray(clip.extra["travel_dir"], float)
        if "speed_curve_cms" in clip.extra:
            sp = np.asarray(clip.extra["speed_curve_cms"], float) / 100.0
            xs = np.concatenate([[0.0], np.cumsum(0.5 * (sp[1:] + sp[:-1]) / 30.0)])
            offs = xs[:, None] * tdir[None, :]
        else:
            offs = t[:, None] * (tdir * clip.speed / 100.0)[None, :]
    minz = 1e9
    slide = {}
    for s in "lr":
        pts = sole_world(baked, s)
        for k, P in pts.items():
            if float(P[:, 2].min()) < minz:
                minz = float(P[:, 2].min())
                q["min_sole_at"] = f"{s}:{k}@{int(np.argmin(P[:, 2]))}"
        # every sole point separately: horizontal drift while it is grounded (travel compensated)
        worst = 0.0
        for k, Pk in pts.items():
            W = Pk + offs
            for (f0, f1) in clip.contacts.get(s, []):
                seg = W[f0:f1 + 1]
                on = seg[:, 2] < 0.010
                if on.sum() >= 2:
                    hs = seg[on][:, :2]
                    worst = max(worst, float(np.linalg.norm(hs - hs.mean(0), axis=1).max()))
        slide[s] = round(worst * 100.0, 2)
    q["min_sole_z_cm"] = round(minz * 100.0, 2)
    q["foot_slide_cm"] = slide
    # pelvis travel for in-place clips (drift start->end)
    pel = baked["world"]["pelvis"][:, :3, 3]
    q["pelvis_drift_cm"] = round(float(np.linalg.norm(pel[-1, :2] - pel[0, :2])) * 100.0, 2)
    root = baked["world"]["root"][:, :3, 3]
    q["root_travel_cm"] = round(float(np.linalg.norm(root[-1, :2] - root[0, :2])) * 100.0, 2)
    return q


BODY_MESHES = ("MR_Suit", "MR_Head", "MR_Boot_L", "MR_Boot_R", "MR_HandL", "MR_CyberArm", "MR_Gear", "MR_Hair")


def mesh_floor_check(frames, step=3):
    """Evaluate deformed body meshes at sampled frames: lowest point and where."""
    import bpy
    sc = bpy.context.scene
    obs = [bpy.data.objects[n] for n in BODY_MESHES if n in bpy.data.objects]
    for o in obs:
        o.hide_viewport = False
    worst = (1e9, "", -1)
    for f in range(0, frames + 1, step):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for o in obs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            z = float(co[2::3].min())
            if z < worst[0]:
                worst = (z, o.name, f)
    for o in obs:
        o.hide_viewport = True
    return {"min_body_z_cm": round(worst[0] * 100, 2), "min_body_at": f"{worst[1]}@{worst[2]}"}


# ---------------------------------------------------------------- hand / forearm vs body
OBSTACLE_BONES = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "neck_02", "clavicle_l", "clavicle_r",
                  "thigh_l", "thigh_r", "thigh_twist_01_l", "thigh_twist_01_r")


def _dominant_groups(obj):
    names = [g.name for g in obj.vertex_groups]
    out = []
    for vx in obj.data.vertices:
        best = max(vx.groups, key=lambda g: g.weight, default=None)
        out.append(names[best.group] if best is not None else "")
    return np.array(out)


_CLEAR = None


def _clearance_setup():
    global _CLEAR
    if _CLEAR is not None:
        return _CLEAR
    import bpy
    suit = bpy.data.objects["MR_Suit"]
    head = bpy.data.objects["MR_Head"]
    cyb = bpy.data.objects["MR_CyberArm"]
    ds = _dominant_groups(suit)
    obst_v = np.isin(ds, OBSTACLE_BONES)
    obst_polys = [list(p.vertices) for p in suit.data.polygons if obst_v[list(p.vertices)].all()]
    head_polys = [list(p.vertices) for p in head.data.polygons]
    dc = _dominant_groups(cyb)
    cyb_sel = np.array([not d.startswith("upperarm") for d in dc])
    sleeve_l = np.isin(ds, ("lowerarm_l", "lowerarm_twist_01_l"))
    gear = bpy.data.objects.get("MR_Gear")
    gear_polys, bracer = [], np.zeros(0, bool)
    if gear is not None:
        dg = _dominant_groups(gear)
        gv = np.isin(dg, OBSTACLE_BONES)
        gear_polys = [list(p.vertices) for p in gear.data.polygons if gv[list(p.vertices)].all()]
        bracer = np.isin(dg, ("lowerarm_l", "lowerarm_twist_01_l"))
    _CLEAR = dict(obst_polys=obst_polys, head_polys=head_polys, cyb_sel=cyb_sel, sleeve_l=sleeve_l,
                  gear_polys=gear_polys, bracer=bracer)
    return _CLEAR


def body_clearance(frames, step=2, radius=0.05):
    """Signed distance of hand / forearm vertices to torso, hips/thighs and head surfaces.

    A tester vertex counts as inside when it lies under an obstacle face (the offset to the
    nearest surface point is along the face normal, pointing inward).  Returns the deepest
    penetration in cm (0 when none) and where it happened."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    sc = bpy.context.scene
    st = _clearance_setup()
    names = ("MR_Suit", "MR_Head", "MR_HandL", "MR_CyberArm") + (("MR_Gear",) if st["gear_polys"] else ())
    obs = {n: bpy.data.objects[n] for n in names}
    for o in obs.values():
        o.hide_viewport = False
    worst = (0.0, "", -1)
    n_bad = 0
    for f in range(0, frames + 1, step):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        co = {}
        for n, o in obs.items():
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            a = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", a)
            ev.to_mesh_clear()
            co[n] = a.reshape(-1, 3)
        S = co["MR_Suit"]
        bv = [("body", BVHTree.FromPolygons([Vector(p) for p in S], st["obst_polys"])),
              ("head", BVHTree.FromPolygons([Vector(p) for p in co["MR_Head"]], st["head_polys"]))]
        if "MR_Gear" in co:
            bv.append(("gear", BVHTree.FromPolygons([Vector(p) for p in co["MR_Gear"]], st["gear_polys"])))
        testers = [("hand_l", co["MR_HandL"]), ("forearm_l", S[st["sleeve_l"]]),
                   ("cyber_r", co["MR_CyberArm"][st["cyb_sel"]])]
        if "MR_Gear" in co and st["bracer"].any():
            testers.append(("bracer_l", co["MR_Gear"][st["bracer"]]))
        bad_frame = False
        for tn, P in testers:
            for p in P:
                pv = Vector(p)
                for on, tree in bv:
                    loc, nr, idx, dist = tree.find_nearest(pv, radius)
                    if loc is None:
                        continue
                    sd = (pv - loc).dot(nr)
                    if sd < -0.002 and -sd > 0.9 * dist:
                        bad_frame = True
                        if -dist < worst[0]:
                            worst = (-dist, f"{tn}->{on}", f)
        n_bad += int(bad_frame)
    for o in obs.values():
        o.hide_viewport = True
    return {"body_clear_cm": round(worst[0] * 100, 2), "body_clear_at": f"{worst[1]}@{worst[2]}",
            "body_clear_bad_samples": n_bad}
