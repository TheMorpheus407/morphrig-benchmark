"""Independent, replayable asset checks; never saves or changes the source file.

blender -b source/Operative.blend --python-exit-code 1 -P tools/validate_asset.py -- --render

Checks actual mesh data, evaluated rig controls, all required authored/baked
actions, loops, roots, held poses, gait support, hand reach and face response.
All lengths are metres. Rendered QA frames use the delivered LOD0 geometry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/generators"))
import rig


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="verification/asset_validation.json")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--geometry-only", action="store_true")
    parser.add_argument("--contacts-only", action="store_true")
    parser.add_argument("--linear-skinning", action="store_true",
                        help="Inspect the exported linear skinning basis used by Unreal; never saves the change")
    parser.add_argument("--ground-only", action="store_true",
                        help="Check actual linear-skinned floor clearance at every authored frame")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


REPORT = {"schema_version": 1, "blender_version": bpy.app.version_string,
          "source": str(Path(bpy.data.filepath).relative_to(ROOT)),
          "units": "metres", "checks": [], "geometry": {}, "rig": {},
          "face_controls": {}, "actions": {}, "renders": []}
FLOOR_PRESSURE_TOLERANCE_M = .01


def check(name, ok, details, warning=False):
    REPORT["checks"].append({"name": name, "status": "pass" if ok else "warning" if warning else "fail",
                             "details": details})


def evaluate_mesh(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    return [ob.matrix_world @ v.co for v in ob.evaluated_get(deps).data.vertices]


def evaluated_bones(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    result = {}
    for bone in ob.data.bones:
        if not bone.use_deform:
            continue
        matrix = ev.matrix_world @ ev.pose.bones[bone.name].matrix.copy()
        # Retained export data is in centimetres at object scale .01. Joint
        # translations are already metres; normalize rest basis units so
        # animated scale factors compare to the source's metre skeleton.
        rest_scale = (ev.matrix_world @ bone.matrix_local).to_scale()
        for column in range(3):
            if abs(rest_scale[column]) > 1e-8:
                for row in range(3):
                    matrix[row][column] /= rest_scale[column]
        result[bone.name] = matrix
    return result


def pose_delta(a, b):
    distances = {name: (a[name].translation - b[name].translation).length for name in a if name in b}
    angles = {name: math.degrees(a[name].to_quaternion().rotation_difference(b[name].to_quaternion()).angle)
              for name in a if name in b}
    scales = {name: (a[name].to_scale() - b[name].to_scale()).length for name in a if name in b}
    for name in angles:
        angles[name] = min(angles[name], 360 - angles[name])
    return {"max_position_delta_m": max(distances.values(), default=0),
            "position_bone": max(distances, key=distances.get, default=None),
            "max_rotation_delta_degrees": max(angles.values(), default=0),
            "rotation_bone": max(angles, key=angles.get, default=None),
            "max_scale_delta": max(scales.values(), default=0)}


def topology(ob):
    mesh = ob.data
    mesh.calc_loop_triangles()
    deform = {b.name for b in bpy.data.objects["Operative_Rig"].data.bones if b.use_deform}
    groups = {g.index: g.name for g in ob.vertex_groups}
    influences, unweighted, nondeform, unnormalized = [], [], [], []
    for v in mesh.vertices:
        weights = [g.weight for g in v.groups if g.weight > 1e-5 and groups[g.group] in deform]
        influences.append(len(weights))
        if not weights:
            unweighted.append(v.index)
        if any(g.weight > 1e-5 and groups[g.group] not in deform for g in v.groups):
            nondeform.append(v.index)
        if weights and abs(sum(weights) - 1) > 1e-4:
            unnormalized.append(v.index)
    used = {i for p in mesh.polygons for i in p.vertices}
    edge_faces = Counter()
    for p in mesh.polygons:
        for edge in p.edge_keys:
            edge_faces[tuple(sorted(edge))] += 1
    loose = [v.index for v in mesh.vertices if v.index not in used]
    finite = all(math.isfinite(c) for v in mesh.vertices for c in v.co)
    zero_area = [t.index for t in mesh.loop_triangles
                 if (mesh.vertices[t.vertices[1]].co-mesh.vertices[t.vertices[0]].co).cross(
                     mesh.vertices[t.vertices[2]].co-mesh.vertices[t.vertices[0]].co).length < 1e-12]
    parent = list(range(len(mesh.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in mesh.edges:
        a, b = map(find, e.vertices)
        parent[b] = a
    components = defaultdict(list)
    for v in mesh.vertices:
        components[find(v.index)].append(v.index)
    boundary_by_component = Counter()
    for (a, b), n in edge_faces.items():
        if n != 2:
            boundary_by_component[find(a)] += 1
    volumes = Counter()
    for t in mesh.loop_triangles:
        a, b, c = [mesh.vertices[i].co for i in t.vertices]
        volumes[find(t.vertices[0])] += a.dot(b.cross(c)) / 6
    inverted_closed = [{"vertices": len(components[k]), "signed_volume_m3": vol}
                       for k, vol in volumes.items() if boundary_by_component[k] == 0 and vol < -1e-10]
    uv = mesh.uv_layers.active
    uv_finite = bool(uv) and len(uv.data) == len(mesh.loops) and all(
        math.isfinite(c) for item in uv.data for c in item.uv)
    return {"vertices": len(mesh.vertices), "triangles": len(mesh.loop_triangles),
            "material_slots": len(mesh.materials), "influence_histogram": dict(Counter(influences)),
            "max_deformation_influences": max(influences, default=0),
            "unweighted_vertices": len(unweighted), "unnormalized_vertices": len(unnormalized),
            "nondeformation_weight_vertices": len(nondeform), "orphan_vertices": len(loose),
            "nonfinite_vertices": not finite, "zero_area_triangles": len(zero_area),
            "boundary_edges": sum(n == 1 for n in edge_faces.values()),
            "nonmanifold_edges": sum(n > 2 for n in edge_faces.values()),
            "connected_surface_components": len(components),
            "inverted_closed_components": inverted_closed, "uv_finite_complete": uv_finite,
            "object_scale": list(ob.scale), "object_rotation": list(ob.rotation_euler)}


def check_geometry(source, lod0):
    source.animation_data_create()
    source.animation_data.action = None
    rig.reset(source)
    reset_types = {k:type(source.pose.bones["CTRL_face"][k]).__name__ for k in rig.FACE_KEYS}
    check("script_reset_preserves_float_animation_properties", all(v == "float" for v in reset_types.values()), reset_types)
    # Restore float properties for independent source/bake comparison even
    # if an older reset implementation corrupted their animation types.
    rig.apply_face(source, {})
    for i, limit in enumerate((80000, 40000, 20000)):
        name = "Operative_LOD" + str(i)
        ob = bpy.data.objects.get(name)
        if not ob:
            check(name + "_present", False, "LOD mesh missing")
            continue
        stats = topology(ob)
        REPORT["geometry"][name] = stats
        check(name + "_triangle_budget", stats["triangles"] <= limit, {"actual": stats["triangles"], "maximum": limit})
        check(name + "_skin", stats["max_deformation_influences"] <= 8 and stats["unweighted_vertices"] == 0
              and stats["unnormalized_vertices"] == 0 and stats["nondeformation_weight_vertices"] == 0,
              {k: stats[k] for k in ("max_deformation_influences", "unweighted_vertices", "unnormalized_vertices", "nondeformation_weight_vertices")})
        check(name + "_surface_integrity", not stats["nonfinite_vertices"] and stats["orphan_vertices"] == 0
              and stats["nonmanifold_edges"] == 0 and not stats["inverted_closed_components"],
              {k: stats[k] for k in ("orphan_vertices", "nonfinite_vertices", "nonmanifold_edges", "inverted_closed_components")})
        check(name + "_UV_and_material_budget", stats["uv_finite_complete"] and stats["material_slots"] <= 8,
              {"uv_complete": stats["uv_finite_complete"], "material_slots": stats["material_slots"]})
    counts = [REPORT["geometry"].get("Operative_LOD"+str(i), {}).get("triangles", 0) for i in range(3)]
    check("genuine_LOD_reduction", counts[0] > counts[1] > counts[2] > 0, counts)
    coords = evaluate_mesh(lod0)
    low = [min(v[i] for v in coords) for i in range(3)]
    high = [max(v[i] for v in coords) for i in range(3)]
    REPORT["geometry"]["neutral_bounds_m"] = {"min": low, "max": high, "height": high[2]-low[2]}
    raw = [lod0.matrix_world @ v.co for v in lod0.data.vertices]
    REPORT["geometry"]["raw_bounds_m"] = {"min": [min(v[i] for v in raw) for i in range(3)],
                                             "max": [max(v[i] for v in raw) for i in range(3)]}
    check("standing_real_world_scale", abs((high[2]-low[2])-1.8) < .015 and abs(low[2]) < .01,
          REPORT["geometry"]["neutral_bounds_m"])
    uv = lod0.data.uv_layers.active
    REPORT["geometry"]["uv_bounds"] = {"min": [min(v.uv[i] for v in uv.data) for i in range(2)],
                                          "max": [max(v.uv[i] for v in uv.data) for i in range(2)]} if uv else None
    check("UVs_inside_editable_unit_tile", bool(uv) and all(-1e-6 <= c <= 1+1e-6 for v in uv.data for c in v.uv), REPORT["geometry"]["uv_bounds"])
    textures = []
    for im in bpy.data.images:
        if im.type not in {"IMAGE", "UV_TEST"} or im.name in {"Render Result", "Viewer Node"}:
            continue
        path = Path(bpy.path.abspath(im.filepath)) if im.filepath else None
        textures.append({"name": im.name, "size": list(im.size), "packed": bool(im.packed_file),
                         "file_exists": bool(path and path.exists()),
                         "RGBA8_with_mips_estimate_bytes": round(im.size[0]*im.size[1]*4*4/3)})
    REPORT["geometry"]["textures"] = textures
    check("available_bounded_textures", bool(textures) and all(max(t["size"]) <= 4096
          and (t["packed"] or t["file_exists"]) for t in textures), textures)
    shape_keys = lod0.data.shape_keys
    corrections = {}
    if shape_keys:
        basis = shape_keys.key_blocks[0]
        for key in shape_keys.key_blocks:
            if not key.name.startswith("correct_"):
                continue
            part, side = key.name.removeprefix("correct_").rsplit("_", 1)
            bone = {"shoulder": "upper_arm", "hip": "thigh", "wrist": "hand"}.get(part, part)+"."+side
            group = lod0.vertex_groups.get(bone)
            moved = [i for i, (v, b) in enumerate(zip(key.data, basis.data)) if (v.co-b.co).length > 1e-6]
            unrelated = [i for i in moved if group and not any(g.group == group.index and g.weight > 1e-5 for g in lod0.data.vertices[i].groups)]
            corrections[key.name] = {"affected_vertices": len(moved), "unrelated_vertices": len(unrelated),
                                     "maximum_delta_m": max(((key.data[i].co-basis.data[i].co).length for i in moved), default=0)}
            check("corrective_locality_"+key.name, not unrelated and bool(moved), corrections[key.name])
    REPORT["geometry"]["corrective_targets"] = corrections


def check_rig(source, mesh):
    bones = [b for b in source.data.bones if b.use_deform]
    roots = [b.name for b in bones if not b.parent or not b.parent.use_deform]
    groups = {g.name for g in mesh.vertex_groups if any(v.groups and any(
        x.group == g.index and x.weight > 1e-5 for x in v.groups) for v in mesh.data.vertices)}
    REPORT["rig"] = {"deformation_bones": len(bones), "roots": roots,
                     "unused_deformation_bones": [b.name for b in bones if b.name not in groups]}
    check("single_root_independent_of_pelvis", roots == ["root"] and source.data.bones["pelvis"].parent.name == "root", REPORT["rig"])
    source.animation_data.action = None
    rig.reset(source)
    rig.apply_pose(source, {})
    first = evaluated_bones(source)
    rig.apply_pose(source, {"root": (0, -2, 0)})
    last = evaluated_bones(source)
    displacement = last["root"].translation-first["root"].translation
    check("root_control_drives_export_root", (displacement-Vector((0, -2, 0))).length < 1e-4,
          {"requested_m": [0, -2, 0], "evaluated_m": list(displacement)})
    tracked = ("pelvis", "spine_01", "spine_02", "chest", "neck", "head", "hand.L", "hand.R", "foot.L", "foot.R")
    residual = {n:(last[n].translation-first[n].translation-Vector((0,-2,0))).length for n in tracked}
    check("root_translation_moves_connected_body_once", max(residual.values()) < .001, residual)
    rig.reset(source)
    for name in rig.FACE_KEYS:
        rig.apply_face(source, {})
        neutral = evaluate_mesh(mesh)
        rig.apply_face(source, {name: .3 if name.startswith("eye_") else 1})
        posed = evaluate_mesh(mesh)
        deltas = [(a-b).length for a, b in zip(neutral, posed)]
        result = {"affected_vertices_above_1um": sum(d > 1e-6 for d in deltas), "maximum_displacement_m": max(deltas, default=0)}
        REPORT["face_controls"][name] = result
        check("face_control_" + name, result["affected_vertices_above_1um"] > 0, result)
    check_blink_coverage(source, mesh)
    rig.reset(source)


def eye_visible_samples(mesh):
    """Ray-cast a 7-by-5 pupil/iris patch from directly in front of each eye.

    Geometry and material visibility are used, rather than driver values or
    assumed lid angles. Skin should occlude the patch in a complete blink.
    """
    deps = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(deps)
    vertices = [ev.matrix_world @ v.co for v in ev.data.vertices]
    polys = [list(p.vertices) for p in ev.data.polygons]
    tree = BVHTree.FromPolygons(vertices, polys, all_triangles=False)
    visible = {}
    material_names = [m.name for m in mesh.data.materials]
    for side, sign in (("L", -1), ("R", 1)):
        hits = Counter()
        for ix in range(7):
            for iz in range(5):
                origin = Vector((sign*.035+(ix-3)*.002, -.5, 1.666+(iz-2)*.002))
                point, normal, polygon, distance = tree.ray_cast(origin, Vector((0,1,0)), 1.)
                if polygon is not None:
                    hits[material_names[ev.data.polygons[polygon].material_index]] += 1
                else:
                    hits["miss"] += 1
        visible[side] = {"eye_surface_samples": sum(hits[n] for n in ("Eyes", "Accent", "Hair")),
                         "material_hit_counts": dict(hits), "total_samples": 35}
    return visible


def check_blink_coverage(source, mesh):
    source.animation_data.action = None
    rig.reset(source)
    neutral = eye_visible_samples(mesh)
    rig.apply_face(source, {"blink.L": 1})
    left = eye_visible_samples(mesh)
    rig.apply_face(source, {"blink.L": 1, "blink.R": 1})
    both = eye_visible_samples(mesh)
    REPORT["rig"]["blink_visibility"] = {"neutral": neutral, "left_only": left, "both": both}
    check("bilateral_blink_occludes_iris", all(both[s]["eye_surface_samples"] == 0 for s in ("L", "R")), both)
    check("independent_left_blink", left["L"]["eye_surface_samples"] == 0 and left["R"]["eye_surface_samples"] >= neutral["R"]["eye_surface_samples"]*.9, left)
    rig.reset(source)
    first = evaluated_bones(source)["lip_lower"].translation
    rig.apply_face(source, {"jaw": 1, "viseme_open": 1})
    last = evaluated_bones(source)["lip_lower"].translation
    check("jaw_opens_lip_downwards", last.z < first.z-.012, {"lower_lip_start_m": list(first), "lower_lip_open_m": list(last)})
    rig.reset(source)


def check_animator_controls(source, mesh):
    """Exercise the delivered panel operators and their evaluated deformation.

    Operators are loaded from the embedded production text with Python's
    normal property annotations, exactly as running that text in Blender.
    """
    text = bpy.data.texts.get("Operative_Animator_Panel.py")
    if not text:
        check("embedded_animator_panel", False, "Embedded panel source missing")
        return
    exec(compile(text.as_string(), "Operative_Animator_Panel.py", "exec", dont_inherit=True), {})
    source.animation_data.action = None
    results = {}
    for side in ("L", "R"):
        for limb, parts, pose in (("arm", ("upper_arm", "forearm", "hand"), QA_POSES["overhead_reach"]),
                                  ("leg", ("thigh", "shin", "foot"), QA_POSES["deep_squat"])):
            rig.reset(source)
            rig.apply_pose(source, pose)
            before = evaluated_bones(source)
            names = [p+"."+side for p in parts]
            if limb == "arm":
                names += [f"{finger}_{joint:02}.{side}" for finger in ("thumb", "index", "middle", "ring", "pinky") for joint in range(1,4)]
            reference = {n:before[n] for n in names}
            bpy.ops.morphrig.switch(side=side, limb=limb)
            after = evaluated_bones(source)
            fk = pose_delta(reference, after)
            check("match_IK_to_FK_"+limb+"."+side, fk["max_position_delta_m"] < .001 and fk["max_rotation_delta_degrees"] < .5, fk)
            bpy.ops.morphrig.switch(side=side, limb=limb)
            after = evaluated_bones(source)
            ik = pose_delta(reference, after)
            check("match_FK_to_IK_"+limb+"."+side, ik["max_position_delta_m"] < .001 and ik["max_rotation_delta_degrees"] < .5, ik)
            results[limb+"."+side] = {"IK_to_FK": fk, "FK_to_IK": ik}
    REPORT["rig"]["switch_matching"] = results
    rig.reset(source)
    neutral = evaluate_mesh(mesh)
    source.pose.bones["CTRL_global"].scale = (2,2,2)
    source.update_tag()
    bpy.context.view_layer.update()
    scaled = evaluate_mesh(mesh)
    max_error = max((b-2*a).length for a,b in zip(neutral,scaled))
    check("global_control_uniform_scale", max_error < .001, {"scale": 2, "maximum_mesh_error_m": max_error})
    bpy.ops.morphrig.reset()
    reset = evaluate_mesh(mesh)
    max_error = max((b-a).length for a,b in zip(neutral,reset))
    check("panel_reset_rest_pose", max_error < 1e-5, {"maximum_mesh_error_m": max_error})
    reset_types = {k:type(source.pose.bones["CTRL_face"][k]).__name__ for k in rig.FACE_KEYS}
    check("panel_reset_preserves_float_animation_properties", all(v == "float" for v in reset_types.values()), reset_types)
    rig.apply_face(source, {})
    rig.reset(source)
    check_hand_pivot_look_controls(source)


def check_hand_pivot_look_controls(source):
    """Prove the required controls move their intended joints and pivot points."""
    source.animation_data.action = None
    pb = source.pose.bones
    settings = pb["CTRL_settings"]
    measurements = {}
    for side in ("L", "R"):
        rig.reset(source)
        initial = evaluated_bones(source)
        settings["curl."+side] = .8
        source.update_tag()
        bpy.context.view_layer.update()
        curled = evaluated_bones(source)
        fingers = [f"{finger}_{joint:02}.{side}" for finger in ("thumb", "index", "middle", "ring", "pinky") for joint in range(1,4)]
        other = "R" if side == "L" else "L"
        rotations = {n: pose_delta({n:initial[n]}, {n:curled[n]})["max_rotation_delta_degrees"] for n in fingers}
        opposite = pose_delta({n:m for n,m in initial.items() if n.endswith("."+other)}, curled)
        check("hand_curl_articulates_five_fingers_"+side, min(rotations.values()) > 20 and opposite["max_position_delta_m"] < 1e-4,
              {"finger_rotations_degrees":rotations,"opposite_side_error":opposite})
        rig.reset(source)
        initial = evaluated_bones(source)
        rig.world_euler_delta(pb["CTRL_index_02."+side], (-.40,0,0))
        source.update_tag()
        bpy.context.view_layer.update()
        adjusted = evaluated_bones(source)
        selected = pose_delta({"index_02."+side:initial["index_02."+side]}, adjusted)
        unrelated = pose_delta({n:initial[n] for n in fingers if not n.startswith("index_")}, adjusted)
        check("individual_finger_adjustment_"+side, selected["max_rotation_delta_degrees"] > 15 and unrelated["max_position_delta_m"] < 1e-4 and unrelated["max_rotation_delta_degrees"] < .05,
              {"selected_index_joint":selected,"other_fingers":unrelated})
        rig.reset(source)
        initial = evaluated_bones(source)
        settings["spread."+side] = 1.
        source.update_tag()
        bpy.context.view_layer.update()
        spread = evaluated_bones(source)
        changed = [n for n in fingers if pose_delta({n:initial[n]},spread)["max_rotation_delta_degrees"] > .5]
        check("finger_spread_control_"+side, len(changed) >= 6, {"moved_finger_joints":changed})
        # Use the lift direction for each ground pivot. Rotating a heel the
        # opposite way would push the ankle below the floor and demand a leg
        # longer than its neutral maximum reach.
        for key, pivot, angle in (("heel","heel",-.30),("toe","toe",.30),("foot_roll","heel",-.30),("foot_roll","toe",.30)):
            rig.reset(source)
            initial = evaluated_bones(source)
            center = (source.matrix_world @ pb["PIVOT_"+pivot+"."+side].matrix).translation.copy()
            settings[key+"."+side] = angle
            source.update_tag()
            bpy.context.view_layer.update()
            rotated = evaluated_bones(source)
            now = (source.matrix_world @ pb["PIVOT_"+pivot+"."+side].matrix).translation
            from mathutils import Quaternion
            expected = center+Quaternion(Vector((1,0,0)),angle) @ (initial["foot."+side].translation-center)
            detail = {"angle_radians":angle,"pivot_center_shift_m":(now-center).length,
                      "ankle_pivot_error_m":(rotated["foot."+side].translation-expected).length,
                      "ankle_motion_m":(rotated["foot."+side].translation-initial["foot."+side].translation).length}
            name = key+"_"+pivot+"_"+side
            measurements[name] = detail
            check("ground_pivot_"+name, detail["pivot_center_shift_m"] < 1e-4 and detail["ankle_pivot_error_m"] < .001 and detail["ankle_motion_m"] > .01, detail)
    for kind, names in (("eye",("eye.L","eye.R")),("head",("head",))):
        rig.reset(source)
        target = Vector((.18,-.70,1.76))
        pb["CTRL_look"].matrix = rig.matrix_at(source,"CTRL_look",target)
        settings[kind+"_look_at"] = 1.
        source.update_tag()
        bpy.context.view_layer.update()
        posed = evaluated_bones(source)
        errors = {}
        for name in names:
            local_forward = source.data.bones[name].matrix_local.to_3x3().inverted() @ Vector((0,-1,0))
            direction = (posed[name].to_3x3() @ local_forward).normalized()
            desired = (target-posed[name].translation).normalized()
            errors[name] = math.degrees(direction.angle(desired))
        check(kind+"_look_target_tracks_forward", max(errors.values()) < 1, {"target_m":list(target),"forward_error_degrees":errors})
        measurements[kind+"_look_at"] = errors
    REPORT["rig"]["hand_pivot_look_controls"] = measurements
    rig.reset(source)


def sample_action(ob, name, frame):
    ob.animation_data_create()
    if ob.animation_data.action != bpy.data.actions[name]:
        ob.animation_data.action = bpy.data.actions[name]
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return evaluated_bones(ob)


def check_actions(source, render=False):
    required = list(csv.DictReader((ROOT/"required_animations.csv").open()))
    manifest_path = ROOT/"docs/animation_manifest.json"
    manifest = json.loads(manifest_path.read_text())["animations"] if manifest_path.exists() else []
    entries = {e["id"]: e for e in manifest}
    missing = [r["id"] for r in required if r["id"] not in bpy.data.actions]
    missing_baked = [r["id"] for r in required if "BAKED_"+r["id"] not in bpy.data.actions]
    check("all_96_required_source_actions", not missing, {"required": len(required), "missing": missing})
    check("all_96_required_baked_actions", not missing_baked, {"required": len(required), "missing": missing_baked})
    check("manifest_one_to_one", len(manifest) == len(required) and set(entries) == {r["id"] for r in required},
          {"manifest_entries": len(manifest), "required_entries": len(required)})
    export_arm = bpy.data.objects.get("Operative_Export_Skeleton")
    end_states = {}
    fingerprints = defaultdict(list)
    for row in required:
        name = row["id"]
        if name not in bpy.data.actions:
            continue
        entry = entries.get(name, {})
        start = int(entry.get("frame_start", 1))
        end = int(entry.get("frame_end", bpy.data.actions[name].frame_range[1]))
        first = sample_action(source, name, start)
        last = sample_action(source, name, end)
        result = {"frames": end-start+1, "duration_seconds": (end-start)/30,
                  "endpoint_difference": pose_delta(first, last),
                  "root_displacement_m": list(last["root"].translation-first["root"].translation)}
        end_states[name] = (first, last)
        REPORT["actions"][name] = result
        if row["form"] == "loop":
            d = result["endpoint_difference"]
            check("loop_"+name, d["max_position_delta_m"] < .001 and d["max_rotation_delta_degrees"] < .5
                  and d["max_scale_delta"] < .001, d)
        if row["form"] == "pose":
            d = result["endpoint_difference"]
            check("held_pose_"+name, d["max_position_delta_m"] < 1e-5 and d["max_rotation_delta_degrees"] < .01, d)
        if row["root_movement"] == "root_motion":
            actual = Vector(result["root_displacement_m"])
            expected = Vector({"dash_f":(0,-2,0), "dash_b":(0,2,0),
                               "dash_l":(-2,0,0), "dash_r":(2,0,0)}[name])
            documented = Vector(entry.get("nominal_root_displacement_m", (0,0,0)))
            check("dash_distance_"+name, (actual-expected).length < .01 and (documented-expected).length < .01,
                  {"actual_m": list(actual), "required_source_direction_m": list(expected),
                   "documented_m":list(documented)})
        elif name.startswith("blink_"):
            check("blink_has_no_baked_teleport_"+name, Vector(result["root_displacement_m"]).length < 1e-5, result["root_displacement_m"])
        if entry:
            check("export_exists_"+name, (ROOT/entry["export_file"]).exists(), entry["export_file"])
            events = entry.get("events", [])
            check("event_frames_"+name, all(start <= ev["frame"] <= end and abs((ev["frame"]-start)/30-ev["time"]) < 1e-6 for ev in events), events)
        if row["form"] != "pose":
            low, high = map(float, row["duration_seconds"].replace("–", "-").split("-"))
            check("duration_range_"+name, low <= result["duration_seconds"] <= high, {"actual_s": result["duration_seconds"], "required_range_s": [low, high]})
        motion_samples = []
        target_errors = {part+"."+side: 0. for part in ("hand", "foot") for side in ("L", "R")}
        for i in range(17):
            sampled = sample_action(source, name, round(start+(end-start)*i/16))
            motion_samples.append(sampled)
            ev = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
            for part in ("hand", "foot"):
                for side in ("L", "R"):
                    target_name = ("MCH_ankle."+side if part == "foot" and "MCH_ankle."+side in ev.pose.bones else "IK_"+part+"."+side)
                    target = ev.matrix_world @ ev.pose.bones[target_name].matrix.translation
                    key = part+"."+side
                    target_errors[key] = max(target_errors[key], (sampled[key].translation-target).length)
        result["sampled_IK_target_errors_m"] = target_errors
        check("sampled_motion_contact_reach_"+name, max(target_errors.values()) < .015, target_errors)
        if row["root_movement"] == "in_place":
            drift = max((p["root"].translation-first["root"].translation).length for p in motion_samples)
            check("in_place_root_stable_"+name, drift < .0001, {"maximum_root_translation_m":drift})
        signature = hashlib.sha256(json.dumps([[round(c, 5) for n in sorted(p) for row in p[n] for c in row] for p in motion_samples]).encode()).hexdigest()
        fingerprints[signature].append(name)
        result["evaluated_motion_sha256"] = signature
        if row["form"] != "pose":
            changed = [pose_delta(first, p) for p in motion_samples]
            check("nonempty_motion_"+name, any(d["max_position_delta_m"] > .002 or d["max_rotation_delta_degrees"] > 1 for d in changed),
                  {"maximum_pose_position_change_m": max(d["max_position_delta_m"] for d in changed),
                   "maximum_pose_rotation_change_degrees": max(d["max_rotation_delta_degrees"] for d in changed)})
        if export_arm and "BAKED_"+name in bpy.data.actions:
            errors = []
            for f in range(start, end+1):
                authored = sample_action(source, name, f)
                baked = sample_action(export_arm, "BAKED_"+name, f)
                errors.append(pose_delta(authored, baked))
            result["bake_comparison"] = {"frames_checked": len(errors), "max_position_error_m": max(d["max_position_delta_m"] for d in errors),
                                          "max_rotation_error_degrees": max(d["max_rotation_delta_degrees"] for d in errors),
                                          "max_scale_error": max(d["max_scale_delta"] for d in errors)}
            c = result["bake_comparison"]
            check("bake_matches_controls_"+name, c["max_position_error_m"] < .0001 and c["max_rotation_error_degrees"] < .05 and c["max_scale_error"] < .0001, c)
        if name.startswith(("walk_", "run_", "sprint_")):
            gait_contacts(source, name, start, end, entry, result)
    for direction in ("front", "back"):
        death, dead = "death_"+direction, "dead_"+direction
        if death in end_states and dead in end_states:
            d = pose_delta(end_states[death][1], end_states[dead][0])
            check("death_held_endpoint_"+direction, d["max_position_delta_m"] < .001 and d["max_rotation_delta_degrees"] < .5, d)
    duplicates = [names for names in fingerprints.values() if len(names) > 1]
    check("distinct_evaluated_required_motion", not duplicates, {"duplicate_groups": duplicates})
    check_dialogue(source, entries, render)
    check_prop_contacts(source, bpy.data.objects["Operative_LOD0"], entries, render)
    source.animation_data.action = None
    if export_arm:
        export_arm.animation_data.action = None
    rig.reset(source)


def check_dialogue(source, entries, render=False):
    """Check the saved face performance against timestamps from the actual WAV."""
    import wave
    alignment_path = ROOT/"source/audio/dialogue_alignment.json"
    wav_path = ROOT/"source/audio/dialogue.wav"
    if not alignment_path.exists() or not wav_path.exists() or "dialogue" not in entries:
        check("dialogue_audio_and_alignment", False, "Missing WAV, alignment or action")
        return
    data = json.loads(alignment_path.read_text())
    with wave.open(str(wav_path)) as sound:
        duration = sound.getnframes()/sound.getframerate()
        audio = {"duration_seconds":duration,"sample_rate":sound.getframerate(),
                 "channels":sound.getnchannels(),"sample_width_bytes":sound.getsampwidth()}
    audio["sha256"] = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    entry = entries["dialogue"]
    authored_duration = (entry["frame_end"]-entry["frame_start"])/30
    check("dialogue_actual_WAV_duration_and_identity", 12 <= duration <= 18 and abs(duration-authored_duration) < 1/30 and audio["sha256"] == data.get("wav_sha256"), audio)
    phonemes = data.get("phonemes",[])
    kinds = {"closure","labiodental","open","wide","round","tongue","consonant"}
    check("dialogue_timed_seven_viseme_classes", kinds <= {p["viseme"] for p in phonemes} and all(0 <= p["start"] <= p["end"] <= duration+1e-6 for p in phonemes),
          {"phoneme_count":len(phonemes),"viseme_counts":dict(Counter(p["viseme"] for p in phonemes))})
    samples = []
    for phoneme in phonemes:
        if phoneme["viseme"] not in kinds:
            continue
        center = (phoneme["start"]+phoneme["end"])/2
        frame = round(center*30)+entry["frame_start"]
        sample_action(source,"dialogue",frame)
        value = float(source.pose.bones["CTRL_face"]["viseme_"+phoneme["viseme"]])
        samples.append({"phoneme":phoneme["phoneme"],"viseme":phoneme["viseme"],
                        "interval_s":[phoneme["start"],phoneme["end"]],"sample_frame":frame,
                        "authored_viseme_value":value})
    check("dialogue_saved_visemes_follow_audio_phoneme_centers", bool(samples) and all(p["authored_viseme_value"] > .12 for p in samples),
          {"sampled_phonemes":len(samples),"weak_samples":[p for p in samples if p["authored_viseme_value"] <= .12],
           "minimum_center_activation":min((p["authored_viseme_value"] for p in samples),default=0)})
    early = sample_action(source,"dialogue",round(.45*30)+1)
    early_face = {k:float(source.pose.bones["CTRL_face"][k]) for k in rig.FACE_KEYS}
    late = sample_action(source,"dialogue",round(9.1*30)+1)
    late_face = {k:float(source.pose.bones["CTRL_face"][k]) for k in rig.FACE_KEYS}
    emotion = {"early_frown_L":early_face["frown.L"],"late_smile_L":late_face["smile.L"],
               "brow_raise_change":abs(late_face["brow_raise.L"]-early_face["brow_raise.L"]),
               "gaze_yaw_change_rad":abs(late_face["eye_yaw.L"]-early_face["eye_yaw.L"]),
               "hand_gesture_displacement_m":(late["hand.L"].translation-early["hand.L"].translation).length}
    check("dialogue_gaze_emotion_and_gesture", emotion["early_frown_L"] > .15 and emotion["late_smile_L"] > .15
          and emotion["gaze_yaw_change_rad"] > .05 and emotion["hand_gesture_displacement_m"] > .04, emotion)
    REPORT["dialogue"] = {"audio":audio,"phoneme_center_samples":samples,"performance_shift":emotion}
    if render:
        for label, seconds in (("concern",.45),("wrist",2.65),("crossing",6.80),
                               ("breath",7.60),("confidence",9.10),("together",10.95)):
            sample_action(source,"dialogue",round(seconds*30)+1)
            render_frame(source,"qa_dialogue_face_"+label,face=True)
            render_frame(source,"qa_dialogue_body_"+label)


def check_prop_contacts(source, mesh, entries, render=False):
    """Measure skinned hand/prop surfaces throughout declared held intervals."""
    groups = {g.index:g.name for g in mesh.vertex_groups}
    hand_names = {"hand.L"} | {f"{finger}_{joint:02}.L" for finger in ("thumb", "index", "middle", "ring", "pinky") for joint in range(1,4)}
    hand_indices = [v.index for v in mesh.data.vertices if any(groups[g.group] in hand_names and g.weight > .1 for g in v.groups)]
    REPORT["prop_contacts"] = {}
    for name, prop, first_marker, last_marker in (("reload", "cell", "cell_left_grasp", "cell_attach_emitter"),
                                                 ("deploy", "beacon", "beacon_left_grasp", "beacon_contact")):
        if name not in entries or name not in bpy.data.actions:
            continue
        entry = entries[name]
        events = {ev["name"]:ev for ev in entry["events"]}
        if first_marker not in events or last_marker not in events:
            continue
        prop_indices = [v.index for v in mesh.data.vertices if any(groups[g.group] == prop and g.weight > .99 for g in v.groups)]
        distances = []
        for frame in range(events[first_marker]["frame"], events[last_marker]["frame"]+1):
            sample_action(source, name, frame)
            coords = evaluate_mesh(mesh)
            tree = KDTree(len(hand_indices))
            for i in hand_indices:
                tree.insert(coords[i], i)
            tree.balance()
            closest = min(tree.find(coords[i])[2] for i in prop_indices)
            distances.append({"frame":frame, "nearest_hand_prop_vertex_distance_m":closest,
                              "prop_minimum_z_m":min(coords[i].z for i in prop_indices)})
        result = {"interval_frames": [distances[0]["frame"], distances[-1]["frame"]],
                  "sampled_frames":len(distances),
                  "maximum_nearest_surface_vertex_distance_m": max(d["nearest_hand_prop_vertex_distance_m"] for d in distances),
                  "worst_contact_frame": max(distances, key=lambda d:d["nearest_hand_prop_vertex_distance_m"])["frame"],
                  "marker_samples": [d for d in distances if d["frame"] in {e["frame"] for e in entry["events"]}]}
        REPORT["prop_contacts"][name] = result
        check("held_prop_surface_contact_"+name, result["maximum_nearest_surface_vertex_distance_m"] < .02, result)
        if name == "deploy":
            for frame_name, frame in (("placement",events["beacon_contact"]["frame"]), ("final",entry["frame_end"])):
                sample_action(source,name,frame)
                coords = evaluate_mesh(mesh)
                minimum = min(coords[i].z for i in prop_indices)
                check("deployed_beacon_floor_contact_"+frame_name, -.005 <= minimum <= .012, {"frame":frame,"base_z_m":minimum})
        if name == "reload":
            rest = source.data.bones["forearm.R"].matrix_local.inverted() @ source.data.bones["cell"].matrix_local
            mounted = []
            for frame in (entry["frame_start"], events["cell_attach_emitter"]["frame"], entry["frame_end"]):
                bones = sample_action(source,name,frame)
                expected = bones["forearm.R"] @ rest
                delta = pose_delta({"cell": expected}, {"cell": bones["cell"]})
                mounted.append({"frame": frame, **delta})
            result["mounted_cell_alignment"] = mounted
            check("reload_cell_mounted_alignment", all(d["max_position_delta_m"] < .012 and d["max_rotation_delta_degrees"] < 5 for d in mounted), mounted)
        if render:
            marker_names = (("cell_left_grasp", "cell_detach", "cell_hand_transfer", "cell_align", "cell_insert", "left_release") if name == "reload"
                            else ("beacon_left_grasp", "beacon_detach", "beacon_contact", "beacon_release"))
            for marker in marker_names:
                if marker not in events:
                    continue
                frame = events[marker]["frame"]
                sample_action(source, name, frame)
                bone = evaluated_bones(source)[prop].translation
                render_frame(source,"qa_contact_"+name+"_"+marker, target=bone+Vector((0,0,.04)), ortho=.70 if name == "reload" else .75)


def gait_contacts(source, name, start, end, entry, result):
    """Measure evaluated ankle support after adding declared controller travel.

    Excludes the lift/touchdown boundary itself, where the foot rolls. No IK
    target values are substituted for the actual evaluated export foot bone.
    """
    import motions
    duration = (end-start)/30
    suffix = name.split("_")[-1]
    dx, dy = motions.DIRECTIONS[suffix]
    speed = entry.get("nominal_speed_cm_s", entry.get("speed_cm_s", 0))/100
    stance = .62 if name.startswith("walk_") else .32 if name.startswith("sprint_") else .37
    samples = {"L": [], "R": []}
    reach = {"L": [], "R": []}
    for f in range(start, end+1):
        bones = sample_action(source, name, f)
        u = (f-start)/(end-start)
        t = (f-start)/30
        for side, shift in (("L", 0.), ("R", .5)):
            phase = (u+shift)%1
            actual = bones["foot."+side].translation
            target = source.matrix_world @ source.pose.bones["IK_foot."+side].matrix.translation
            reach[side].append((actual-target).length)
            if .03 <= phase <= stance-.03:
                world = actual+Vector((dx*speed*t, dy*speed*t, 0))
                samples[side].append((f, world))
    contacts = {}
    for side in ("L", "R"):
        # R stance crosses the loop seam for walking; compare consecutive
        # support samples only, avoiding a discontinuous cycle wrap.
        steps = [(b-a).length for (fa,a),(fb,b) in zip(samples[side],samples[side][1:]) if fb-fa == 1]
        heights = [v.z for _,v in samples[side]]
        contacts[side] = {"support_samples": len(samples[side]), "maximum_world_support_speed_m_s": max(steps, default=0)*30,
                          "maximum_IK_reach_error_m": max(reach[side], default=0),
                          "ankle_support_height_range_m": [min(heights, default=0), max(heights, default=0)]}
    result["gait_contacts"] = contacts
    check("planted_gait_"+name, all(c["maximum_world_support_speed_m_s"] < .12 and c["maximum_IK_reach_error_m"] < .015 for c in contacts.values()), contacts)


def check_motion_floor_clearance(source, mesh, entries, render=False):
    """Inspect every required frame on a flat floor using runtime linear skinning.

    This measures the actual surface, including head, palms and equipped props,
    rather than inferring clearance from ankle targets or pelvis height.
    """
    armature_modifiers = [m for m in mesh.modifiers if m.type == "ARMATURE"]
    preserve = [m.use_deform_preserve_volume for m in armature_modifiers]
    for modifier in armature_modifiers:
        modifier.use_deform_preserve_volume = False
    groups = {g.index:g.name for g in mesh.vertex_groups}
    results = {}
    # Representative support and floor poses, kept stable across corrections
    # so their visible before/after behavior can be compared. Every frame is
    # still measured, and any new failure also receives a worst-frame render.
    review_frames = {"jump_start":9,"jump_land":9,"land_heavy":12,"deploy":25,
                     "knockdown_front":45,"knockdown_back":58,
                     "prone_front":16,"prone_back":46,
                     "getup_front":1,"getup_back":1,
                     "death_front":61,"death_back":69,
                     "dead_front":1,"dead_back":1}
    try:
        for name, entry in entries.items():
            if name not in bpy.data.actions:
                continue
            samples = []
            penetrating_groups = Counter()
            for frame in range(entry["frame_start"],entry["frame_end"]+1):
                sample_action(source,name,frame)
                coords = evaluate_mesh(mesh)
                low = min(range(len(coords)), key=lambda i:coords[i].z)
                samples.append({"frame":frame,"minimum_surface_z_m":coords[low].z,
                                "lowest_vertex_index":low})
                for i,co in enumerate(coords):
                    if co.z < -FLOOR_PRESSURE_TOLERANCE_M:
                        weights = mesh.data.vertices[i].groups
                        if weights:
                            group = max(weights,key=lambda g:g.weight)
                            penetrating_groups[groups[group.group]] += 1
            worst = min(samples,key=lambda s:s["minimum_surface_z_m"])
            detail = {"frames_checked":len(samples),"worst_frame":worst["frame"],
                      "minimum_surface_z_m":worst["minimum_surface_z_m"],
                      "lowest_vertex_index":worst["lowest_vertex_index"],
                      "penetrating_vertex_frame_groups":dict(penetrating_groups)}
            results[name] = detail
            detail["maximum_allowed_contact_pressure_depth_m"] = FLOOR_PRESSURE_TOLERANCE_M
            check("linear_surface_floor_clearance_"+name, worst["minimum_surface_z_m"] >= -FLOOR_PRESSURE_TOLERANCE_M, detail)
            if worst["minimum_surface_z_m"] < -FLOOR_PRESSURE_TOLERANCE_M:
                print("FLOOR_CLEARANCE_ISSUE",name,json.dumps(detail),flush=True)
            if render and (name in review_frames or worst["minimum_surface_z_m"] < -FLOOR_PRESSURE_TOLERANCE_M):
                frame = worst["frame"] if worst["minimum_surface_z_m"] < -FLOOR_PRESSURE_TOLERANCE_M else review_frames[name]
                detail["review_render_frame"] = frame
                sample_action(source,name,frame)
                render_frame(source,"qa_floor_"+name)
    finally:
        for modifier, value in zip(armature_modifiers,preserve):
            modifier.use_deform_preserve_volume = value
        source.animation_data.action = None
        rig.reset(source)
    REPORT["linear_floor_clearance"] = results


QA_POSES = {
    "neutral": {},
    "overhead_reach": {"hands": {"L": (-.20,-.05,1.86), "R": (.20,-.05,1.86)}},
    "deep_squat": {"pelvis": (0,.04,.60), "hands": {"L": (-.22,-.24,1.00), "R": (.22,-.24,1.00)}, "torso": (.20,0,0)},
    "crossed_arm": {"hands": {"L": (.18,-.19,1.33), "R": (-.18,-.20,1.29)}},
    "torso_twist": {"torso": (0,0,1.05), "hands": {"L": (-.34,-.18,1.30), "R": (.18,.28,1.25)}},
    "kneeling": {"pelvis": (0,0,.60), "feet": {"L": (-.11,-.27,.10), "R": (.11,.35,.10)}, "hands": {"L": (-.26,-.10,.83), "R": (.32,-.12,.9)}},
    "hand_support": {"blade": 0, "pelvis": (0,.10,.255), "torso": (1.1,0,0), "hands": {"L": (-.25,-.29,.045), "R": (.25,-.29,.045)}, "hand_rot": {"L": (math.pi/2,0,0), "R": (math.pi/2,0,0)}},
    "closed_grip": {"hands": {"L": (-.18,-.26,1.24), "R": (.18,-.26,1.24)}, "curls": {"L": [.6,.9,.9,.9,.9], "R": [.6,.9,.9,.9,.9]}},
}


def check_poses(source, mesh, render=False):
    source.animation_data.action = None
    metrics = {}
    for name, pose in QA_POSES.items():
        rig.reset(source)
        if "QA_"+name in bpy.data.actions:
            sample_action(source, "QA_"+name, 1)
        else:
            source.animation_data.action = None
            rig.apply_pose(source, pose)
        coords = evaluate_mesh(mesh)
        errors = {}
        bones = evaluated_bones(source)
        for part in ("hand", "foot"):
            for side in ("L", "R"):
                target = source.matrix_world @ source.pose.bones["IK_"+part+"."+side].matrix.translation
                errors[part+"."+side] = (bones[part+"."+side].translation-target).length
        metrics[name] = {"IK_target_errors_m": errors, "minimum_surface_z_m": min(v.z for v in coords),
                         "maximum_surface_z_m": max(v.z for v in coords)}
        penetrating = Counter()
        for index, co in enumerate(coords):
            if co.z < -.015:
                weights = mesh.data.vertices[index].groups
                if weights:
                    g = max(weights, key=lambda g:g.weight)
                    penetrating[mesh.vertex_groups[g.group].name] += 1
        metrics[name]["floor_penetrating_vertex_groups"] = dict(penetrating)
        check("demanding_pose_reach_"+name, max(errors.values()) < .015, metrics[name])
        check("demanding_pose_ground_clearance_"+name, metrics[name]["minimum_surface_z_m"] > -.015, metrics[name]["minimum_surface_z_m"])
        if name == "deep_squat":
            knees = {side: list(bones["shin."+side].translation) for side in ("L", "R")}
            metrics[name]["knee_centers_m"] = knees
            check("squat_knees_follow_anatomical_side", knees["L"][0] < -.025 and knees["R"][0] > .025 and max(k[1] for k in knees.values()) < 0, knees)
        if render:
            render_frame(source, "qa_"+name, face=False)
    REPORT["rig"]["demanding_pose_metrics"] = metrics
    if render:
        import motions
        faces = {"neutral": {}, **{k:v for k,v in motions.expression_presets.items() if k != "neutral"},
                 "blink_left": {"blink.L": 1}, "blink_both": {"blink.L": 1, "blink.R": 1},
                 "mouth_closed": {"lip_close": 1}, "mouth_open": {"jaw": .85, "viseme_open": .8},
                 "pucker": {"pucker": 1}}
        faces.update({key:{key:1} for key in rig.FACE_KEYS if key.startswith("viseme_")})
        for name, face in faces.items():
            source.animation_data.action = None
            rig.reset(source)
            rig.apply_face(source, face)
            render_frame(source, "qa_face_"+name, face=True)
    rig.reset(source)


def render_frame(source, name, face=False, target=None, ortho=None):
    scene = bpy.context.scene
    camera = scene.camera
    target = Vector(target) if target is not None else Vector((0,-.025,1.65)) if face else Vector((0,0,.98))
    camera.location = target+Vector((1,-2,.6)) if ortho is not None else (0,-2.0,1.67) if face else (2.4,-4,1.9)
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho if ortho is not None else .33 if face else 2.34
    scene.render.resolution_x = 600 if face else 512
    scene.render.resolution_y = 600 if face else 640
    scene.render.resolution_percentage = 100
    scene.cycles.samples = 16
    if REPORT.get("skinning_basis") == "linear":
        name = name.replace("qa_", "qa_lbs_", 1)
    scene.render.filepath = str(ROOT/"verification"/(name+".png"))
    bpy.ops.render.render(write_still=True)
    REPORT["renders"].append(str(Path(scene.render.filepath).relative_to(ROOT)))


def main():
    args = parse_args()
    started = time.monotonic()
    source = bpy.data.objects["Operative_Rig"]
    mesh = bpy.data.objects["Operative_LOD0"]
    source_path = Path(bpy.data.filepath)
    source_stamp = source_path.stat().st_mtime_ns
    REPORT["source_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    REPORT["validated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    REPORT["skinning_basis"] = "linear" if args.linear_skinning else "delivered"
    if args.linear_skinning:
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name.startswith("Operative_LOD"):
                for modifier in ob.modifiers:
                    if modifier.type == "ARMATURE":
                        modifier.use_deform_preserve_volume = False
        bpy.context.view_layer.update()
    if args.contacts_only or args.ground_only:
        entries = {e["id"]:e for e in json.loads((ROOT/"docs/animation_manifest.json").read_text())["animations"]}
        if args.ground_only:
            check_motion_floor_clearance(source,mesh,entries,args.render)
        else:
            check_prop_contacts(source, mesh, entries, args.render)
        check("source_unchanged_during_validation", source_path.stat().st_mtime_ns == source_stamp,
              {"source_mtime_ns_at_start":source_stamp,"source_mtime_ns_at_end":source_path.stat().st_mtime_ns})
        REPORT["elapsed_seconds"] = round(time.monotonic()-started,3)
        REPORT["summary"] = dict(Counter(c["status"] for c in REPORT["checks"]))
        report_path = ROOT/args.report
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(REPORT,indent=2)+"\n")
        print("ASSET_CONTACT_VALIDATION", json.dumps(REPORT["summary"]), flush=True)
        return
    check_geometry(source, mesh)
    check_rig(source, mesh)
    check_animator_controls(source, mesh)
    if not args.geometry_only:
        check_actions(source, args.render)
        entries = {e["id"]:e for e in json.loads((ROOT/"docs/animation_manifest.json").read_text())["animations"]}
        check_motion_floor_clearance(source,mesh,entries,args.render)
    check_poses(source, mesh, args.render)
    check("source_unchanged_during_validation", source_path.stat().st_mtime_ns == source_stamp,
          {"source_mtime_ns_at_start": source_stamp, "source_mtime_ns_at_end": source_path.stat().st_mtime_ns})
    REPORT["elapsed_seconds"] = round(time.monotonic()-started, 3)
    REPORT["summary"] = dict(Counter(c["status"] for c in REPORT["checks"]))
    path = ROOT/args.report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REPORT, indent=2)+"\n")
    print("ASSET_VALIDATION", json.dumps(REPORT["summary"]), str(path), flush=True)
    # No save operation: production .blend and actions remain unchanged.


if __name__ == "__main__":
    main()
    if REPORT["summary"].get("fail", 0):
        raise RuntimeError(f"Asset validation found {REPORT['summary']['fail']} failures; see the written report.")
