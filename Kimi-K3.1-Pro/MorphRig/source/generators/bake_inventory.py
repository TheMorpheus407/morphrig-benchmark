"""Bake the complete inventory into an existing generated Operative.blend."""
from pathlib import Path
import sys
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from character import skeleton_spec
from animate import build_animation_inventory

controls = bpy.data.texts.get("START_HERE_Rig_Controls.py") or bpy.data.texts.new("START_HERE_Rig_Controls.py")
controls.clear()
controls.write((HERE / "rig_controls.py").read_text())
controls.use_module = True

asset = {
    "ctrl": bpy.data.objects["Operative_CTRL"], "rig": bpy.data.objects["Operative_DEF"],
    "face": bpy.data.objects["Operative_Face"], "bones": skeleton_spec(),
}
build_animation_inventory(asset)
