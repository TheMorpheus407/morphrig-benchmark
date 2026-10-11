"""Empirical: what angular extent does sphere_cap_bm actually produce for given
(segs, rings, half_angle)? Measure max angle-from-+Z of cap verts and the rim."""
import bpy, bmesh, math, sys, os
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "source", "generators"))
from morphrig_lib import sphere_cap_bm

for rings, half in ((12, 40), (18, 45), (9, 40), (18, 40), (27, 40), (20, 45)):
    bm = bmesh.new()
    cv, cf = sphere_cap_bm(bm, 1.0, half, segs=20, rings=rings, mat_index=0)
    zs = sorted({round(v.co.z, 6) for v in cv})
    angs = sorted({round(math.degrees(math.acos(max(-1, min(1, v.co.z)))), 3)
                   for v in cv if abs(v.co.x) > 1e-9 or abs(v.co.y) > 1e-9})
    rim = [e for e in bm.edges if e.is_boundary]
    rim_angs = sorted({round(math.degrees(math.acos(max(-1, min(1, v.co.z)))), 3)
                       for e in rim for v in e.verts})
    print(f"rings={rings:3d} half={half:3d}: verts={len(cv):4d} faces={len(cf):4d} "
          f"distinct z={len(zs)} angles={angs} rim_angles={rim_angs}")
    bm.free()
print("CAP_TEST_DONE")
