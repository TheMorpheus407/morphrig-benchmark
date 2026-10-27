"""Export the authored beacon subset without a skeleton or replacement geometry."""
from pathlib import Path
import hashlib
import json
import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
source = bpy.data.objects["Operative_Props"]
group = source.vertex_groups.get("beacon")
if group is None:
    raise RuntimeError("The authored beacon vertex group is missing")
bpy.context.view_layer.update()
center = Vector(next(item["source_world_m"] for item in json.loads((ROOT / "docs" / "skeleton_and_sockets.json").read_text())["sockets"] if item["name"] == "beacon"))
obj = source.copy()
obj.data = source.data.copy()
obj.name = "ST_Beacon_Source"
bpy.context.scene.collection.objects.link(obj)
obj.parent = None
obj.matrix_world = Matrix.Identity(4)
for modifier in list(obj.modifiers):
    obj.modifiers.remove(modifier)
for vertex in obj.data.vertices:
    vertex.co = source.matrix_world @ vertex.co - center
mesh = bmesh.new()
mesh.from_mesh(obj.data)
mesh.verts.ensure_lookup_table()
unrelated = [vertex for vertex in mesh.verts if all(link.group != group.index for link in obj.data.vertices[vertex.index].groups)]
if unrelated:
    bmesh.ops.delete(mesh, geom=unrelated, context="VERTS")
if not mesh.verts or not mesh.faces:
    raise RuntimeError("Beacon export has no geometry")
mesh.to_mesh(obj.data)
mesh.free()
if not obj.data.uv_layers:
    raise RuntimeError("Beacon UVs were not retained")
obj.scale = (100.0, 100.0, 100.0)
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
output = ROOT / "export" / "Beacon.fbx"
bpy.ops.export_scene.fbx(
    filepath=str(output), use_selection=True, object_types={"MESH"},
    use_mesh_modifiers=True, use_tspace=True, use_triangles=True,
    axis_forward="-Z", axis_up="Y", global_scale=1.0,
    apply_unit_scale=False, apply_scale_options="FBX_SCALE_UNITS",
    bake_space_transform=False, path_mode="RELATIVE", embed_textures=True,
    bake_anim=False,
)
points = [vertex.co for vertex in obj.data.vertices]
report = {
    "source": "source/Operative.blend / Operative_Props[beacon]",
    "file": "export/Beacon.fbx",
    "vertices": len(obj.data.vertices),
    "triangles": sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons),
    "uv_layers": len(obj.data.uv_layers),
    "materials": [material.name for material in obj.data.materials],
    "bounds_cm": [[min(point[i] for point in points) * 100, max(point[i] for point in points) * 100] for i in range(3)],
    "socket_source_m": list(center),
    "object_scale": 100,
    "fbx_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
}
(ROOT / "docs" / "validation" / "beacon_export.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
