"""Render the delivered FBX in Blender without changing it."""
from pathlib import Path
import json
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.fbx(filepath=str(ROOT / "export" / "Operative_LOD0.fbx"), use_anim=False)
bpy.context.view_layer.update()
rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
head = rig.matrix_world @ rig.pose.bones["head"].matrix.translation
eyes = [(rig.matrix_world @ rig.pose.bones[name].matrix.translation) for name in ("eye.L", "eye.R")]
eye = sum(eyes, Vector()) / 2
forward = (eye - head).normalized()
camera_data = bpy.data.cameras.new("FBXReview")
camera = bpy.data.objects.new("FBXReview", camera_data)
bpy.context.scene.collection.objects.link(camera)
asset_height = max((obj.matrix_world @ Vector(corner)).z for obj in bpy.context.scene.objects if obj.type == "MESH" for corner in obj.bound_box) - min((obj.matrix_world @ Vector(corner)).z for obj in bpy.context.scene.objects if obj.type == "MESH" for corner in obj.bound_box)
camera.location = eye + forward * (asset_height * .29) + Vector((0, 0, asset_height * .01))
camera.rotation_euler = (eye - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 60
scene = bpy.context.scene
scene.camera = camera
for location, power, size in [((1, -2, 3), 600, 3), ((-2, -1, 2), 350, 2), ((0, 2, 2.6), 500, 2)]:
    data = bpy.data.lights.new("FBXReviewLight", "AREA")
    data.energy = power
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new("FBXReviewLight", data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, 1)) - obj.location).to_track_quat("-Z", "Y").to_euler()
scene.render.engine = "CYCLES"
scene.cycles.samples = 20
scene.cycles.use_denoising = True
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.render.filepath = str(ROOT / "docs" / "validation" / "fbx_face_review.png")
points = [obj.matrix_world @ Vector(corner) for obj in scene.objects if obj.type == "MESH" for corner in obj.bound_box]
report = {
    "file": "export/Operative_LOD0.fbx",
    "mesh_objects": len([obj for obj in scene.objects if obj.type == "MESH"]),
    "deformation_bones": len(rig.data.bones),
    "height_source_units": max(point.z for point in points) - min(point.z for point in points),
    "eye_head_delta": list(eye - head),
    "camera_location": list(camera.location),
    "camera_forward": list(eye - camera.location),
}
(ROOT / "docs" / "validation" / "fbx_render_review.json").write_text(json.dumps(report, indent=2) + "\n")
bpy.ops.render.render(write_still=True)
print(json.dumps(report, indent=2), flush=True)
