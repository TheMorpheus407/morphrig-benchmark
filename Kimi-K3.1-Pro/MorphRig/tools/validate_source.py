"""Reopen-and-evaluate validation for the delivered Blender production asset."""
from pathlib import Path
import json
import math
import bpy

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
manifest = json.loads((DOCS / "animation_manifest.json").read_text())
failures = []
rig = bpy.data.objects.get("Operative_DEF")
ctrl = bpy.data.objects.get("Operative_CTRL")
face = bpy.data.objects.get("Operative_Face")
if not rig or not ctrl or not face:
    raise RuntimeError("Required source objects are missing")
for bone in rig.pose.bones:
    for constraint in bone.constraints:
        constraint.influence = 0.0
ctrl.animation_data.action = None
for bone in ctrl.pose.bones:
    bone.matrix_basis.identity()
rig.animation_data.action = None
face.data.shape_keys.animation_data.action = None
for bone in rig.pose.bones:
    bone.matrix_basis.identity()
for key in face.data.shape_keys.key_blocks:
    key.value = 0.0
bpy.context.scene.frame_set(0)
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
z_values = []
for obj in (bpy.data.objects["Operative_Body_LOD0"], face, bpy.data.objects["Operative_Props"]):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    z_values.extend((obj.matrix_world @ vertex.co).z for vertex in mesh.vertices)
    evaluated.to_mesh_clear()
neutral_bounds = {"min_z_m": min(z_values), "max_z_m": max(z_values), "height_m": max(z_values) - min(z_values)}
if abs(neutral_bounds["min_z_m"]) > .00001 or abs(neutral_bounds["max_z_m"] - 1.80) > .00001:
    failures.append("Neutral source is not exactly ground-origin 1.80m: " + repr(neutral_bounds))
roots = [bone.name for bone in rig.data.bones if bone.parent is None]
if roots != ["root"]: failures.append("Deformation hierarchy roots: " + repr(roots))
if len(rig.data.bones) != 70: failures.append("Expected 70 deform bones")
for bone in rig.data.bones:
    ancestor = bone
    visited = set()
    while ancestor.parent:
        if ancestor.name in visited:
            failures.append("Bone parent cycle at " + bone.name)
            break
        visited.add(ancestor.name)
        ancestor = ancestor.parent
    if ancestor.name != "root": failures.append("Disconnected bone " + bone.name)
meshes = [bpy.data.objects[f"Operative_Body_LOD{i}"] for i in range(3)] + [face, bpy.data.objects["Operative_Props"]]
for obj in meshes:
    if not obj.data.uv_layers: failures.append(obj.name + ": missing UVs")
    for vertex in obj.data.vertices:
        if not all(math.isfinite(v) for v in vertex.co): failures.append(obj.name + ": nonfinite vertex")
        weights = [group.weight for group in vertex.groups]
        if not weights: failures.append(obj.name + ": unweighted vertex")
        if len(weights) > 8: failures.append(obj.name + ": more than eight influences")
        if abs(sum(weights) - 1) > .001: failures.append(obj.name + ": weights not normalized")
for image in bpy.data.images:
    if image.source == 'FILE' and image.packed_file is None:
        path = Path(bpy.path.abspath(image.filepath))
        if not path.exists(): failures.append("Missing image " + str(path))
    if max(image.size) > 4096: failures.append("Oversize image " + image.name)
if len(bpy.data.shape_keys if hasattr(bpy.data, 'shape_keys') else []) > 10000:
    failures.append("Unexpected shape-key datablock count")
records = []
scene = bpy.context.scene
for entry in manifest["entries"]:
    name = entry["id"]
    action = bpy.data.actions.get(name)
    source = bpy.data.actions.get("SOURCE_" + name)
    facial = bpy.data.actions.get(name + "_FACE")
    if not action or not source or not facial:
        failures.append(name + ": missing baked/source/facial action")
        continue
    if not action.use_fake_user or not source.use_fake_user or not facial.use_fake_user:
        failures.append(name + ": action is not retained")
    start, end = entry["frame_range"]
    if abs(action.frame_range[0] - start) > .01 or abs(action.frame_range[1] - end) > .01:
        failures.append(f"{name}: action range {list(action.frame_range)} != {[start, end]}")
    if len(json.loads(action["event_markers"])) != len(entry["events"]):
        failures.append(name + ": source event count mismatch")
    rig.animation_data.action = action
    face.data.shape_keys.animation_data.action = facial
    transforms = []
    for frame in {start, end}:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        transforms.append({bone.name: bone.matrix.copy() for bone in rig.pose.bones})
    if name in ("idle_relaxed", "idle_combat", "walk_f", "run_f"):
        if not .88 < transforms[0]["pelvis"].translation.z < 1.03 or not 1.48 < transforms[0]["head"].translation.z < 1.60:
            failures.append(name + ": baked standing pose has invalid pelvis/head height")
    if entry["loop"]:
        error = max(abs(transforms[0][bone][i][j] - transforms[1][bone][i][j]) for bone in transforms[0] for i in range(4) for j in range(4))
        if error > .0005: failures.append(f"{name}: baked loop error {error}")
    if name.startswith("dash_"):
        displacement = (transforms[1]["root"].translation - transforms[0]["root"].translation).length
        if abs(displacement - 2.0) > .001: failures.append(f"{name}: baked root displacement {displacement}")
    if name.startswith("death_"):
        dead_name = name.replace("death_", "dead_")
        rig.animation_data.action = bpy.data.actions[dead_name]
        face.data.shape_keys.animation_data.action = bpy.data.actions[dead_name + "_FACE"]
        scene.frame_set(0)
        bpy.context.view_layer.update()
        dead = {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
        error = max(abs(transforms[1][bone][i][j] - dead[bone][i][j]) for bone in dead for i in range(4) for j in range(4))
        if error > .0005: failures.append(f"{name}: baked death/dead error {error}")
        dead_face = {key.name: key.value for key in face.data.shape_keys.key_blocks}
        rig.animation_data.action = action
        face.data.shape_keys.animation_data.action = facial
        scene.frame_set(end)
        bpy.context.view_layer.update()
        for key in face.data.shape_keys.key_blocks:
            if abs(key.value - dead_face[key.name]) > .0005:
                failures.append(f"{name}: baked death/dead face mismatch {key.name}")
    records.append({"id": name, "range": [start, end], "action_retained": True})
result = {"status": "PASS" if not failures else "FAIL", "failures": failures, "actions": len(records), "deformation_bones": len(rig.data.bones), "facial_shapes": len(face.data.shape_keys.key_blocks) - 1, "source_action_count": len(bpy.data.actions), "mesh_objects_checked": len(meshes), "neutral_bounds": neutral_bounds}
(DOCS / "validation" / "source_asset_validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result), flush=True)
if failures:
    raise RuntimeError("Saved source validation failed")
