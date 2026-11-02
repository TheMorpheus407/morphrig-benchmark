"""Build the complete MorphRig Operative inside Blender.

    blender -b --factory-startup -P source/generators/build_character.py -- \
        --out source/Operative.blend [--preview /tmp/preview] [--clay]

Produces one armature, one skinned character mesh with facial morphs and
a fully wired control rig.
"""

import os
import sys
import math
import time
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy

import mr_core
import mr_body
import mr_face
import mr_rig
import mr_skin

MAT_NAMES = ["M_Skin", "M_Face", "M_Suit", "M_Armor",
             "M_Metal", "M_Optic", "M_Energy", "M_Accent"]

# material index shortcuts used by the generators
M_SKIN, M_FACE, M_SUIT, M_ARMOR, M_METAL, M_OPTIC, M_ENERGY, M_ACCENT = range(8)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def build_geometry(with_gear=True):
    mb = mr_core.MeshBuilder()
    torso, ang, rows = mr_body.build_torso(mb)
    head, h_ang, h_rows, mouth = mr_body.build_head(mb, torso, ang, rows)
    arms = {}
    for side in (1, -1):
        arms[side] = mr_body.build_arm(mb, torso, rows, side)
    legs = mr_body.build_legs(mb, torso, rows)
    boots = []
    for side in (1, -1):
        boots.append(mr_body.build_boot(mb, side))
    fingers = []
    hands = {}
    for side in (1, -1):
        arm = arms[side]
        palm, wc, fwd, right, up = mr_body.build_hand(mb, arm, side)
        hands[side] = dict(palm=palm, wrist=wc, fwd=fwd, right=right, up=up)
        fingers.append((side, mr_body.build_fingers(mb, palm, side, wc, fwd,
                                                    right, up)))
    eye_l, eye_r = mr_body.build_face_details(
        mb, head, mouth,
        (M_FACE, M_OPTIC, M_OPTIC, M_FACE, M_OPTIC))
    mb.uv_rect["head"] = mr_face.FACE_ATLAS["skin"]
    # the neck shares the face texture, it samples the plain skin band
    mb.uv_rect["neck"] = (0.00, 0.00, 0.48, 0.86)

    gear = None
    if with_gear:
        import mr_gear
        gear = mr_gear.build_gear(mb, arms, legs, head, eyes=(eye_l, eye_r),
                                  hands=hands)
        mr_gear.assign_part_materials(mb)
    mr_core.cleanup_faces(mb)
    obj = mb.to_object("Operative_Body")
    layout = face_layout(mb, head, mouth, None)
    return mb, obj, dict(torso=torso, head=head, arms=arms, legs=legs,
                          boots=boots, fingers=fingers, gear=gear,
                          hands=hands, eye_l=eye_l, eye_r=eye_r, rows=rows,
                          layout=layout)


def face_layout(mb, head, mouth, info):
    """UV rectangles for the painted facial features (lips, brows, sockets).

    The head skin occupies u 0.00..0.48 of the face atlas, so the painted
    patches are scaled into that band.

    The uv seam of the head sits at the front centre, right between the
    lips, so the mouth is split over the two ends of the skin band.  Both
    halves are painted separately, otherwise the lips would be clipped by
    the edge of the atlas.
    """
    from mathutils import Vector
    import mr_face
    out = {}
    scale = mr_face.SKIN_U_SCALE

    def rect_for(point, half_u, half_v, key):
        u, v = mr_body.head_uv_at(mb, head, point)
        su = u * scale
        sv = v
        out[key] = (max(su - half_u, 0.0), max(sv - half_v, 0.0),
                    min(su + half_u, scale),
                    min(sv + half_v, mr_face.SKIN_V_MAX))

    # the carved mouth slit, in the signed u around the seam and in v
    signed = []
    vs = set()
    for vi in mouth:
        u, v = mr_body.head_uv_at(mb, head, mb.verts[vi])
        signed.append(u if u < 0.5 else u - 1.0)
        vs.add(round(v, 6))
    vs = sorted(vs)
    v_low, v_high = vs[0], vs[-1]
    u_lo, u_hi = min(signed), max(signed)

    # the two halves of the mouth: the right one sits at the left edge of
    # the skin band, the left one at the right edge
    x_split = (0.0 - u_lo) / max(u_hi - u_lo, 1e-6)
    for tag, x0, x1, u0, u1 in (
            ("r", x_split, 1.0, 0.0, u_hi * scale),
            ("l", 0.0, x_split, scale + u_lo * scale, scale)):
        for part, v0, v1 in (("upper", v_high, v_high + 0.012),
                             ("lower", v_low - 0.020, v_low)):
            out["lip_%s_%s" % (part, tag)] = (u0, v0, u1, v1)
            out["lipshape_%s_%s" % (part, tag)] = (x0, x1)

    # brows and eye sockets
    for side in (1, -1):
        sfx = "r" if side > 0 else "l"
        samples = mr_body.brow_samples(mb, head, side, count=5)
        mid = samples[len(samples) // 2][0]
        rect_for(mid, 0.020, 0.016, "brow_%s" % sfx)
        surf, nrm, c = mr_body.socket_frame(mb, head, side)
        rect_for(surf, 0.020, 0.028, "socket_%s" % sfx)
    for k, v in sorted(out.items()):
        print("  LAYOUT %-18s %s" % (k, tuple(round(q, 4) for q in v)))
    return out


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------

def build_rig(mb, obj, info):
    specs = mr_rig.build_bone_specs(info["eye_l"], info["eye_r"])
    arm_obj, _ = mr_rig.create_armature(specs)
    arm_obj.name = "Operative_Rig"
    arm_obj.data.name = "Operative_Rig"
    mr_rig.build_constraints(arm_obj, specs)

    ctx = {}
    for side in (1, -1):
        ctx.setdefault("arm_pts", {})[side] = mr_body.arm_axis(side)[0]
        ctx.setdefault("leg_pts", {})[side] = mr_body.leg_axis(side)[0]
    stats = mr_skin.build_weights(mb, obj, ctx)

    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm_obj
    obj.parent = arm_obj
    obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()
    return arm_obj, specs, stats


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------

def clay_materials():
    cols = [(0.60, 0.50, 0.45, 1), (0.68, 0.58, 0.52, 1), (0.13, 0.14, 0.17, 1),
            (0.26, 0.28, 0.33, 1), (0.52, 0.55, 0.58, 1), (0.03, 0.04, 0.05, 1),
            (0.95, 0.55, 0.15, 1), (0.90, 0.35, 0.08, 1)]
    out = []
    for i, c in enumerate(cols):
        m = bpy.data.materials.new(MAT_NAMES[i])
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = c
        b.inputs["Roughness"].default_value = 0.55
        b.inputs["Metallic"].default_value = 0.2
        out.append(m)
    return out


def real_materials(texture_dir, layout=None):
    import mr_materials
    return mr_materials.build_all(texture_dir, layout=layout)


def assign_materials(obj, mats, mb=None):
    """Attach the material slots and (re)apply the per-face material indices.

    `material_index` is clamped by Blender to the number of slots, so the
    indices have to be written again once the slots exist.
    """
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)
    if mb is not None:
        for pi, poly in enumerate(obj.data.polygons):
            if pi < len(mb.face_mat):
                poly.material_index = mb.face_mat[pi]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(flag, default=None):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    out = arg("--out")
    preview = arg("--preview")
    clay = "--clay" in argv
    t0 = time.time()

    reset_scene()
    mb, obj, info = build_geometry(with_gear="--nogear" not in argv)
    arm_obj, specs, stats = build_rig(mb, obj, info)

    tex_dir = os.path.abspath(
        arg("--textures", os.path.join(HERE, "..", "textures")))
    mats = clay_materials() if clay else real_materials(
        tex_dir,
        info.get("layout"))
    assign_materials(obj, mats, mb)

    keys = mr_skin.build_shape_keys(obj, mb)

    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print("CHAR_STATS verts=%d faces=%d tris=%d bones=%d shapes=%d" %
          (len(me.vertices), len(me.polygons), tris,
           len([s for s in specs if s.deform]), len(keys)))
    print("CHAR_SKIN %s" % stats)
    zs = [v.co.z for v in me.vertices]
    xs = [v.co.x for v in me.vertices]
    print("CHAR_BBOX x=%.3f..%.3f z=%.3f..%.3f" % (min(xs), max(xs),
                                                   min(zs), max(zs)))
    from collections import defaultdict
    bb = defaultdict(lambda: [1e9, -1e9])
    for i, part in enumerate(mb.part):
        b = bb[part]
        x = mb.verts[i].x
        b[0] = min(b[0], x); b[1] = max(b[1], x)
    for k in sorted(bb):
        if abs(bb[k][1]) > 0.001 or abs(bb[k][0]) > 0.001:
            print("  PART_X %-16s %+.4f .. %+.4f" % (k, bb[k][0], bb[k][1]))
    import collections
    acc = collections.defaultdict(lambda: [1e9, -1e9, 1e9, -1e9, 1e9, -1e9])
    for i, part in enumerate(mb.part):
        v = mb.verts[i]
        a = acc[part]
        a[0] = min(a[0], v.x); a[1] = max(a[1], v.x)
        a[2] = min(a[2], v.y); a[3] = max(a[3], v.y)
        a[4] = min(a[4], v.z); a[5] = max(a[5], v.z)
    for k in ("mouth_cav", "teeth_up", "teeth_lo", "tongue", "head", "torso"):
        a = acc.get(k)
        if a:
            print("  PART_BB %-10s x %+.4f..%+.4f y %+.4f..%+.4f z %+.4f..%+.4f"
                  % (k, a[0], a[1], a[2], a[3], a[4], a[5]))

    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
        print("CHAR_SAVED", out)

    hide = arg("--hide")
    if hide:
        hide_set = set(hide.split(","))
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        kill = [f for f in bm.faces if mb.part[f.verts[0].index] in hide_set]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(obj.data)
        bm.free()
        print("CHAR_HIDE", hide)
    if preview:
        import build_preview_lib
        build_preview_lib.render_views(preview, obj)

    print("CHAR_DONE %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
