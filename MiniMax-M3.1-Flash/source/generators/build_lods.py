"""Generate LOD1 / LOD2 from the LOD0 body and write the LOD report.

    blender -b --factory-startup -P source/generators/build_lods.py

LOD1 and LOD2 are decimated copies of the LOD0 body.  The facial morph
targets live on LOD0 only - Blender cannot decimate a mesh that carries
shape keys - so the lower LODs keep the bones, the skin weights and the
eight material slots but no face morphs.
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

TARGETS = [
    ("LOD1", 0.62),
    ("LOD2", 0.34),
]

LIMITS = {"LOD0": 80000, "LOD1": 40000, "LOD2": 20000}


def tri_count(ob):
    me = ob.data
    return sum(len(p.vertices) - 2 for p in me.polygons)


def strip_shape_keys(ob):
    if ob.data.shape_keys is None:
        return
    if ob.data.shape_keys.animation_data:
        ob.data.shape_keys.animation_data_clear()
    ob.shape_key_clear()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = os.path.join(ROOT, "source", "Operative.blend")
    out = blend
    if "--blend" in argv:
        blend = argv[argv.index("--blend") + 1]
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    report_path = os.path.join(ROOT, "docs", "material_and_lod_report.json")

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    body = bpy.data.objects.get("Operative_Body")
    arm = bpy.data.objects.get("Operative_Rig")
    if body is None:
        raise SystemExit("Operative_Body missing")

    report = {"character": "Operative", "unit": "metre",
              "forward": "-Y", "up": "+Z", "lods": []}

    mats = [s.material.name if s.material else None
            for s in body.material_slots]
    base = {
        "object": body.name,
        "vertices": len(body.data.vertices),
        "polygons": len(body.data.polygons),
        "triangles": tri_count(body),
        "material_slots": mats,
        "material_slot_count": len(mats),
        "deform_bones": len([b for b in arm.data.bones if b.use_deform]),
        "shape_keys": (len(body.data.shape_keys.key_blocks)
                       if body.data.shape_keys else 0),
    }
    report["lods"].append(dict(base, lod="LOD0", limit=LIMITS["LOD0"],
                               within_limit=base["triangles"] <= LIMITS["LOD0"],
                               reduction=1.0))

    for lod, ratio in TARGETS:
        name = "Operative_Body_%s" % lod
        if name in bpy.data.objects:
            old = bpy.data.objects[name]
            bpy.data.objects.remove(old, do_unlink=True)
        dup = body.copy()
        dup.data = body.data.copy()
        dup.name = name
        dup.data.name = "%s_Mesh" % name
        bpy.context.scene.collection.objects.link(dup)
        strip_shape_keys(dup)
        # the armature modifier points at the shared rig, keep it
        mod = dup.modifiers.new("Decimate", 'DECIMATE')
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = dup
        dup.select_set(True)
        bpy.ops.object.modifier_apply(modifier="Decimate")
        dup.select_set(False)
        tris = tri_count(dup)
        report["lods"].append({
            "lod": lod,
            "object": dup.name,
            "vertices": len(dup.data.vertices),
            "polygons": len(dup.data.polygons),
            "triangles": tris,
            "material_slots": [s.material.name if s.material else None
                               for s in dup.material_slots],
            "material_slot_count": len(dup.material_slots),
            "deform_bones": len([b for b in arm.data.bones if b.use_deform]),
            "shape_keys": 0,
            "limit": LIMITS[lod],
            "within_limit": tris <= LIMITS[lod],
            "reduction": round(tris / float(base["triangles"]), 4),
        })
        print("LOD_BUILT %-5s tris=%6d limit=%6d ok=%s"
              % (lod, tris, LIMITS[lod], tris <= LIMITS[lod]))

    # texture memory
    tex = []
    for img in bpy.data.images:
        if img.source != 'FILE':
            continue
        w, h = img.size
        tex.append({"file": os.path.basename(img.filepath),
                    "size": "%dx%d" % (w, h),
                    "bytes_with_mips": w * h * 4 * 4 // 3})
    report["textures"] = sorted(tex, key=lambda t: t["file"])
    report["texture_bytes_total"] = sum(t["bytes_with_mips"] for t in tex)
    report["texture_count"] = len(tex)
    report["max_texture_size"] = max([2048] + [
        int(t["size"].split("x")[0]) for t in tex])

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2)
    print("LOD_REPORT %s" % report_path)
    print("LOD_DONE")


main()
