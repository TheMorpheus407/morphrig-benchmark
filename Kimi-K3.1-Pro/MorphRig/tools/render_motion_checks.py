"""Render representative authored motion/contact/deformation checks from the saved source."""
from pathlib import Path
import bpy
import json
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation"
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 20
scene.cycles.use_denoising = True
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_percentage = 100
rig = bpy.data.objects["Operative_DEF"]
face = bpy.data.objects["Operative_Face"]
ctrl = bpy.data.objects["Operative_CTRL"]
ctrl.animation_data.action = None
for bone in rig.pose.bones:
    for constraint in bone.constraints:
        constraint.influence = 0.0
camera_data = bpy.data.cameras.new("MotionInspection")
camera = bpy.data.objects.new("MotionInspection", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera


def camera_at(location, target, ortho=None, lens=70):
    camera.location = location
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        camera.data.type = 'ORTHO'; camera.data.ortho_scale = ortho
    else:
        camera.data.type = 'PERSP'; camera.data.lens = lens


checks = [
    ("idle_relaxed", 0), ("walk_l", 8), ("run_fr", 6), ("jump_air", 5),
    ("melee_3", 18), ("reload", 30), ("deploy", 30), ("aim_up_left", 0),
    ("victory", 36), ("getup_back", 58), ("knockdown_front", 66), ("prone_back", 0),
]
for name, frame in checks:
    rig.animation_data.action = bpy.data.actions[name]
    face.data.shape_keys.animation_data.action = bpy.data.actions[name + "_FACE"]
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    floor = name.startswith(("knockdown", "prone"))
    camera_at((1.35, -3.9, 2.0), (0, .10, .30 if floor else .94), 1.6 if floor else 2.08)
    scene.render.resolution_x, scene.render.resolution_y = (640, 720 if floor else 800)
    scene.render.filepath = str(OUT / ("pose_" + name + ".png"))
    bpy.ops.render.render(write_still=True)

rig.animation_data.action = None
face.data.shape_keys.animation_data.action = None
for bone in rig.pose.bones:
    bone.matrix_basis.identity()
for bone in ctrl.pose.bones:
    bone.matrix_basis.identity()
for bone in rig.pose.bones:
    for constraint in bone.constraints:
        constraint.influence = 1.0
scene.frame_set(0)
bpy.context.view_layer.update()
presets = {
    "joy": {"Smile.L": .85, "Smile.R": .85, "Cheek.L": .55, "Cheek.R": .55, "Squint.L": .20, "Squint.R": .20},
    "anger": {"BrowLower.L": .9, "BrowLower.R": .9, "Squint.L": .45, "Squint.R": .45, "Frown.L": .65, "Frown.R": .65},
    "concern": {"BrowRaise.L": .32, "BrowRaise.R": .42, "Frown.L": .65, "Frown.R": .45},
    "surprise": {"BrowRaise.L": 1, "BrowRaise.R": 1, "JawOpen": .55, "Viseme_OO": .4},
    "pain": {"Blink.L": .62, "Squint.R": .85, "BrowLower.L": .55, "BrowLower.R": .65, "Frown.L": .6, "Frown.R": .7, "JawOpen": .25},
    "focus": {"Squint.L": .32, "Squint.R": .24, "BrowLower.L": .18, "BrowLower.R": .26, "LipClosed": .85},
    "left_blink": {"Blink.L": 1.0},
    "open_vowel": {"JawOpen": .75, "Viseme_AA": .65},
    "rounded_vowel": {"Viseme_OO": .85, "JawOpen": .22},
}
for name, values in presets.items():
    for key in face.data.shape_keys.key_blocks:
        key.value = 0.0
    for name_key, value in values.items():
        face.data.shape_keys.key_blocks[name_key].value = value
    bpy.context.view_layer.update()
    camera_at((.10, -.62, 1.70), (0, -.01, 1.665), lens=70)
    scene.render.resolution_x = scene.render.resolution_y = 640
    scene.render.filepath = str(OUT / ("face_" + name + ".png"))
    bpy.ops.render.render(write_still=True)
(OUT / "inspection_sheet_order.json").write_text(json.dumps({"body": [entry[0] for entry in checks], "face": list(presets)}, indent=2) + "\n")
print("MOTION_AND_FACE_INSPECTION_RENDERED", flush=True)
