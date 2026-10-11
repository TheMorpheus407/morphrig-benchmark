"""Probe the prop mesh geometry: verts of the Operative mesh weighted to
each prop bone (blade, emitter, cells), in bone-local and forearm-local
space, to place grips on the actual meshes.

Run: blender -b --factory-startup --python work/probe_props.py
"""
import os
import sys

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(TASK, "source", "generators", "gen_03_animations.py")

import bpy
from mathutils import Vector, Matrix

src = open(GEN, encoding="utf-8").read()
head = src.split("# ==================================================================== bake")[0]
ns = {"__file__": GEN, "__name__": "probe_head"}
exec(compile(head, GEN, "exec"), ns)
rig = ns["rig"]

mesh_obj = bpy.data.objects["Operative"]
me = mesh_obj.data
vg_index = {g.name: g.index for g in mesh_obj.vertex_groups}


def verts_of(bone):
    gi = vg_index.get(bone)
    if gi is None:
        return []
    out = []
    for v in me.vertices:
        w = 0.0
        for g in v.groups:
            if g.group == gi:
                w = max(w, g.weight)
        if w > 0.5:
            out.append(v.co.copy())
    return out


def report(name, ref_rest):
    vs = verts_of(name)
    if not vs:
        print("== %s: NO VERTS >0.5" % name)
        return
    inv = ref_rest.inverted()
    pts = [inv @ v for v in vs]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    print("== %s: %d verts, %s-local bbox min=%s max=%s"
          % (name, len(vs), name,
             tuple(round(c, 4) for c in (min(xs), min(ys), min(zs))),
             tuple(round(c, 4) for c in (max(xs), max(ys), max(zs)))))
    return pts


for bone in ("blade", "emitter", "cell_new", "cell_spent", "beacon"):
    print("-- prop %s rest_world=%s blen=%.4f"
          % (bone, tuple(round(c, 4) for c in rig.rest[bone].to_translation()),
             rig.blen[bone]))
    report(bone, rig.rest[bone])

print("-- blade/emitter verts in FOREARM_R local space")
inv_fa = rig.rest["forearm_R"].inverted()
for bone in ("blade", "emitter"):
    vs = verts_of(bone)
    if not vs:
        continue
    pts = [inv_fa @ v for v in vs]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    print("   %-8s forearm-local bbox min=%s max=%s (verts=%d)"
          % (bone,
             tuple(round(c, 4) for c in (min(xs), min(ys), min(zs))),
             tuple(round(c, 4) for c in (max(xs), max(ys), max(zs))), len(vs)))

print("-- sockets (empties) rest positions")
for s in ("socket_blade_base", "socket_blade_tip", "socket_muzzle_flash",
          "socket_cell_emitter", "socket_cell_holster", "socket_weapon_r",
          "socket_hand_r", "socket_hand_l"):
    o = bpy.data.objects.get(s)
    if o is not None:
        print("   %-20s world=%s" % (s, tuple(round(c, 4) for c in
                                             o.matrix_world.to_translation())))
print("PROBE PROPS DONE")
