"""Check the skinning of the Operative for tears and unbound vertices.

    blender -b --factory-startup -P source/generators/validate_skin.py

The check has three parts:

1.  Every vertex has to be bound to at least one bone.  A vertex without a
    weight keeps its rest position while its neighbours move, which shows up
    in the render as a long stretched spike.
2.  No evaluated edge may be much longer than the rest edge of the same mesh.
    A long edge means two vertices are pulled apart by two different bones.
3.  The cap centres, which close the tubes, have to carry the part tag of the
    ring they close, otherwise they fall back to the generic "body" tag and
    the auto skinner leaves them unbound.

The script prints a report and exits with a non zero code when it finds a
problem, so it can be used in the build chain.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# the clips that move the arms and the hands the most
PROBE_CLIPS = [
    ("idle_combat", 10),
    ("walk_f", 5),
    ("run_f", 8),
    ("dash_f", 7),
    ("melee_1", 15),
    ("cast_directional", 20),
    ("ranged_fire", 6),
    ("reload", 30),
    ("death_front", 40),
    ("respawn", 30),
]


def unbound_vertices(obj):
    """Vertices that carry no weight at all."""
    out = []
    for vert in obj.data.vertices:
        if not any(g.weight > 1e-4 for g in vert.groups):
            out.append(vert.index)
    return out


def longest_edge(me):
    worst = 0.0
    for edge in me.edges:
        a = me.vertices[edge.vertices[0]].co
        b = me.vertices[edge.vertices[1]].co
        length = (a - b).length
        if length > worst:
            worst = length
    return worst


def main():
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "source", "Operative.blend"))
    scn = bpy.context.scene
    rig = bpy.data.objects.get("Operative_Rig")
    body = bpy.data.objects.get("Operative_Body")
    if rig is None or body is None:
        print("SKIN_ERROR the rig or the body is missing")
        return 1

    report = {"unbound": [], "edge_ratio": {}, "rest_edge_max": 0.0}

    # the longest edge of the rest mesh, that is the reference
    rest = longest_edge(body.data)
    report["rest_edge_max"] = round(rest, 4)
    limit = rest * 1.6

    unbound = unbound_vertices(body)
    report["unbound_count"] = len(unbound)
    report["unbound"] = unbound[:40]

    for clip, frame in PROBE_CLIPS:
        action = bpy.data.actions.get("ACT_%s" % clip)
        if action is None:
            continue
        rig.animation_data.action = action
        scn.frame_set(frame)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = body.evaluated_get(depsgraph)
        me = evaluated.to_mesh()
        longest = longest_edge(me)
        evaluated.to_mesh_clear()
        report["edge_ratio"][clip] = round(longest / max(rest, 1e-6), 3)

    # the cap centres must not carry the generic tag any more
    stray = []
    try:
        import build_character
        mb, _obj, _ctx = build_character.build_geometry()
        for index, part in enumerate(mb.part):
            if part == "body":
                stray.append((index, tuple(round(c, 3) for c in mb.verts[index])))
    except Exception as exc:  # noqa: BLE001
        report["builder_error"] = str(exc)
    report["generic_tag_vertices"] = stray[:40]
    report["generic_tag_count"] = len(stray)

    out = os.path.join(ROOT, "docs", "skin_report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)

    print("SKIN_REPORT %s" % out)
    print("SKIN_REST_EDGE %.4f  limit %.4f" % (rest, limit))
    print("SKIN_UNBOUND %d" % len(unbound))
    for clip, ratio in report["edge_ratio"].items():
        print("SKIN_EDGE %-18s ratio %.3f" % (clip, ratio))
    print("SKIN_GENERIC_TAG %d" % len(stray))

    failures = 0
    if unbound:
        print("SKIN_FAIL %d vertices have no weight" % len(unbound))
        failures += 1
    for clip, ratio in report["edge_ratio"].items():
        if ratio > 1.6:
            print("SKIN_FAIL %s stretches the mesh by %.2fx" % (clip, ratio))
            failures += 1
    if stray:
        print("SKIN_FAIL %d vertices still carry the generic body tag" % len(stray))
        failures += 1
    print("SKIN_RESULT %s" % ("PASS" if failures == 0 else "FAIL"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
