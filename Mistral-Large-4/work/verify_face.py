"""Post-build face verification: raycast source/Operative.blend and check that
specific rays hit the expected material slots at the expected depths."""
import bpy, os, json
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(TASK, "source", "Operative.blend")
bpy.ops.wm.open_mainfile(filepath=BLEND)

obj = bpy.data.objects["Operative"]
me = obj.data
deps = bpy.context.evaluated_depsgraph_get()
obj_eval = obj.evaluated_get(deps)
MAT_NAMES = ["Skin", "Suit", "Armor", "CyberMetal", "Emissive", "Hair", "Eye", "Mouth"]

def cast(origin, direction, label, expect_mat, note=""):
    origin = Vector(origin); direction = Vector(direction).normalized()
    res, loc, normal, idx = obj_eval.ray_cast(origin, direction)
    if not res:
        print(f"{label:34s} MISS  (expected mat {expect_mat} {MAT_NAMES[expect_mat]}) {note}")
        return None
    m = me.polygons[idx].material_index
    d = (loc - origin).length
    ok = "OK " if m == expect_mat else "FAIL"
    print(f"{label:34s} {ok} mat {m} ({MAT_NAMES[m]:9s}) hit y/x={loc.x:+.5f} {loc.y:+.5f} {loc.z:+.5f} d={d:.5f} (exp {expect_mat}) {note}")
    return m

print("== front rays (origin y=-1, dir +Y) ==")
cast((0.042, -1.0, 1.6450), (0, 1, 0), "eye front (slit center)", 6, "exp y=-0.1072")
cast((0.042, -1.0, 1.6385), (0, 1, 0), "lower lid band", 0, "exp y~-0.1069")
cast((0.042, -1.0, 1.6515), (0, 1, 0), "upper lid band", 0, "exp y~-0.1069")
cast((0.042, -1.0, 1.6575), (0, 1, 0), "eyeball top (lid covers)", 0, "exp lid, not eye")
cast((0.042, -1.0, 1.6330), (0, 1, 0), "cheek below lower lid", 0, "exp skin y~-0.1019")
cast((0.0509, -1.0, 1.6450), (0, 1, 0), "eye almond outer", 6, "exp y~-0.1035")
cast((0.056, -1.0, 1.6450), (0, 1, 0), "beyond eyeball edge", 0, "exp skin y~-0.0933")
cast((0.0465, -1.0, 1.6820), (0, 1, 0), "brow tube front", 0, "exp y~-0.1123")
cast((0.0, -1.0, 1.7100), (0, 1, 0), "visor band front", 4, "exp y~-0.1259")
cast((0.0, -1.0, 1.7126), (0, 1, 0), "visor front center", 4, "")
cast((0.0, -1.0, 1.7450), (0, 1, 0), "hair fringe front", 5, "exp y~-0.1167")
cast((0.0, -1.0, 1.6960), (0, 1, 0), "forehead skin (visor gap)", 0, "exp y~-0.1171")
print("== side/back rays ==")
cast((1.0, 0.032, 1.648), (-1, 0, 0), "R side: headset band first", 2, "exp x~0.080 before skull 0.071")
cast((0.0, 1.0, 1.66696), (0, -1, 0), "back: headset band", 2, "exp y~0.0795 before skull 0.0733")
cast((1.0, 0.005, 1.655), (-1, 0, 0), "R side: earpiece", 3, "exp x~0.094")
cast((1.0, -0.0573, 1.7012), (-1, 0, 0), "R side: visor end region", 4, "exp visor end ~x0.084")
print("VERIFY_FACE_DONE")
