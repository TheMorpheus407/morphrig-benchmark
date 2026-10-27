"""Analytic source-pose validation; runs in Blender without modifying the saved asset."""
from pathlib import Path
import sys
import json
import math
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source" / "generators"))
import animate
from character import skeleton_spec

spec = skeleton_spec()
animate.SPEC = spec
animate.REST = {item["name"]: bpy.data.objects["Operative_DEF"].data.bones[item["name"]] for item in spec}
animate.PARENT = {item["name"]: item["parent"] for item in spec}
animate.ORDER = [item["name"] for item in spec]
animate.REST_LOCAL = {name: (animate.REST[animate.PARENT[name]].matrix_local.inverted() @ animate.REST[name].matrix_local if animate.PARENT[name] else animate.REST[name].matrix_local.copy()) for name in animate.ORDER}
alignment = json.loads((ROOT / "source" / "audio" / "dialogue_alignment.json").read_text())
inventory = json.loads((ROOT / "source" / "animation_inventory.json").read_text())
failures = []
records = []
for entry in inventory:
    name, frames = entry["id"], entry["frame_range"][1]
    samples = []
    for index in range(5):
        t = index / 4
        if entry["loop"] and index == 4: t = 0
        p = animate.apply_contacts(animate.sample_pose(name, t, frames, alignment))
        world = animate.world_transforms(p)
        if not all(math.isfinite(value) for matrix in world.values() for row in matrix for value in row):
            failures.append(name + ": nonfinite transform")
        if name in ("idle_relaxed", "idle_combat", "walk_f", "run_f") and index == 0:
            if not .88 < world["pelvis"].translation.z < 1.03 or not 1.48 < world["head"].translation.z < 1.60:
                failures.append(name + ": invalid standing rest-space pelvis/head height")
        if entry["root_motion_policy"] == "in_place" and p.root.length > 1e-6:
            failures.append(name + ": in-place root has translation")
        if name.startswith("dash_") and index == 4:
            if abs(p.root.length - 2) > 1e-5:
                failures.append(name + ": dash is not 2m")
            if p.root.normalized().dot(animate.DIRECTIONS[name.split("_")[1]]) < .999:
                failures.append(name + ": dash direction disagrees with anatomical convention")
        if name.startswith(("walk_", "run_")) and index == 0:
            direction = name.split("_")[1]
            foot_x = p.leg_targets["L"].x
            if "l" in direction and foot_x <= .112:
                failures.append(name + ": left gait target is on the wrong side")
            if "r" in direction and foot_x >= .112:
                failures.append(name + ": right gait target is on the wrong side")
        if name in ("turn_l90", "pivot_l180") and index == 2 and p.rot["pelvis"].z <= 0:
            failures.append(name + ": left turn has the wrong sign")
        if name in ("turn_r90", "pivot_r180") and index == 2 and p.rot["pelvis"].z >= 0:
            failures.append(name + ": right turn has the wrong sign")
        samples.append((p, world))
    if name in ("getup_front", "getup_back"):
        support = animate.apply_contacts(animate.sample_pose(name, 58 / 90, 90, alignment))
        support_world = animate.world_transforms(support)
        wrist_height = support_world["hand.R"].translation.z
        if abs(wrist_height - .105) > .012:
            failures.append(f"{name}: planted support wrist is {wrist_height:.4f}m, expected 0.105m")
    if entry["loop"]:
        error = max(abs(samples[0][1][bone][i][j] - samples[-1][1][bone][i][j]) for bone in animate.ORDER for i in range(4) for j in range(4))
        if error > 1e-5: failures.append(f"{name}: loop endpoint matrix error {error}")
    if name.startswith("death_"):
        dead = animate.apply_contacts(animate.sample_pose("dead_" + name.split("_")[1], 0, 0, alignment))
        dead_world = animate.world_transforms(dead)
        error = max(abs(samples[-1][1][bone][i][j] - dead_world[bone][i][j]) for bone in animate.ORDER for i in range(4) for j in range(4))
        if error > 1e-5: failures.append(f"{name}: death/dead skeletal error {error}")
        face_error = {key: [samples[-1][0].face.get(key, 0), dead.face.get(key, 0)] for key in samples[-1][0].face.keys() | dead.face.keys() if abs(samples[-1][0].face.get(key, 0) - dead.face.get(key, 0)) > 1e-6}
        if face_error: failures.append(name + ": death/dead facial mismatch " + repr(face_error))
    contact = None
    if name in ("reload", "deploy"):
        fraction = 34 / 60 if name == "reload" else 30 / 48
        support = animate.apply_contacts(animate.sample_pose(name, fraction, entry["frame_range"][1], alignment))
        support_world = animate.world_transforms(support)
        prop_name = "cell" if name == "reload" else "beacon"
        contact = {
            "wrist_to_prop_m": (support_world["hand.L"].translation - support_world[prop_name].translation).length,
            "finger_to_prop_m": (support_world["middle_03.L"].translation - support_world[prop_name].translation).length,
        }
        if contact["wrist_to_prop_m"] > (.08 if name == "reload" else .16):
            failures.append(f"{name}: wrist loses prop contact by {contact['wrist_to_prop_m']:.4f}m")
        if name == "deploy":
            if contact["finger_to_prop_m"] > .08:
                failures.append(f"deploy: fingers do not reach beacon by {contact['finger_to_prop_m']:.4f}m")
            props = bpy.data.objects["Operative_Props"]
            group = props.vertex_groups["beacon"]
            floor_offset = min(vertex.co.z for vertex in props.data.vertices if any(link.group == group.index and link.weight > 0 for link in vertex.groups)) - bpy.data.objects["Operative_DEF"].data.bones["beacon"].head_local.z
            contact["floor_height_m"] = support_world["beacon"].translation.z + floor_offset
            if abs(contact["floor_height_m"]) > .002:
                failures.append(f"deploy: lowest beacon geometry is {contact['floor_height_m']:.5f}m from the floor")
            release_distance = (samples[-1][1]["beacon"].translation - support_world["beacon"].translation).length
            contact["release_return_distance_m"] = release_distance
            if release_distance > .002:
                failures.append(f"deploy: released beacon moves {release_distance:.4f}m away from floor contact")
    records.append({"id": name, "evaluated_samples": 5, "root_policy_ok": not (entry["root_motion_policy"] == "in_place" and any(p.root.length > 1e-6 for p, _ in samples)), "support_contact": contact})
result = {"status": "PASS" if not failures else "FAIL", "entries": len(records), "failures": failures, "samples": records}
(ROOT / "docs" / "validation" / "analytic_motion.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "entries": len(records), "failures": failures}), flush=True)
if failures: raise RuntimeError("Analytic motion validation failed")
