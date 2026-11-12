#!/usr/bin/env python3
"""MORPHRIG export: Operative.fbx (bind pose) + Operative_AllAnims.fbx (all 96 actions as takes, constraint-free skeleton)."""
import bpy, os
BLEND = "/home/candidate/workspace/MorphRig/source/Operative.blend"
EXP = "/home/candidate/workspace/MorphRig/export"
bpy.ops.wm.open_mainfile(filepath=BLEND)
arm = bpy.data.objects["Operative_Armature"]
ob_head = bpy.data.objects.get("Head")
char_objs = [o for o in bpy.data.objects if o.type=='MESH' and o.users_collection and any(c.name=="Character" for c in o.users_collection)
             and "_LOD" not in o.name]

# constraint-free export armature
ead = arm.data.copy()
earm = arm.copy(); earm.data = ead; earm.name = "Operative_Armature_Export"
bpy.context.scene.collection.objects.link(earm)
for pb in earm.pose.bones:
    while pb.constraints: pb.constraints.remove(pb.constraints[0])
for c in list(earm.constraints): earm.constraints.remove(c)

FBX_KW = dict(use_selection=True, object_types={'ARMATURE','MESH'},
              use_mesh_modifiers=False, use_subsurf=False,
              use_armature_deform_only=False, add_leaf_bones=False,
              primary_bone_axis='Y', secondary_bone_axis='X',
              bake_anim_use_all_actions=True,
              bake_anim_use_all_bones=True, bake_anim_simplify_factor=0.0)
os.makedirs(f"{EXP}/animations", exist_ok=True)

def sel(objs):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]

def mesh_mod_target(target):
    for o in char_objs:
        for m in o.modifiers:
            if m.type=='ARMATURE': m.object = target

# 1) Bind pose (mesh skins to authoring armature, no anim)
mesh_mod_target(arm)
sel(char_objs + [arm])
for t in (arm, ob_head):
    if t.animation_data: t.animation_data.action = None
bpy.ops.export_scene.fbx(filepath=f"{EXP}/Operative.fbx", **FBX_KW, bake_anim=False)
print("Exported Operative.fbx")

# 2) All animations (mesh skins to constraint-free earm, all actions as takes)
mesh_mod_target(earm)
sel(char_objs + [earm])
for t in (earm, ob_head):
    if t.animation_data is None: t.animation_data_create()
    t.animation_data.action = None  # exporter uses all-actions
bpy.ops.export_scene.fbx(filepath=f"{EXP}/animations/Operative_AllAnims.fbx", **FBX_KW, bake_anim=True)
print("Exported Operative_AllAnims.fbx with", len(bpy.data.actions), "actions")

# restore authoring targets
mesh_mod_target(arm)
bpy.ops.wm.save_mainfile(filepath=BLEND)
print("Done")