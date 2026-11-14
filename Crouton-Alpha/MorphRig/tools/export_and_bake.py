"""Export Operative.blend -> FBX (mesh + one file per action). Blender 5.1.1 headless.
Usage: blender -b --factory-startup -P MorphRig/tools/export_and_bake.py -- /abs/Operative.blend /abs/export
Note: Blender 5 layered actions require NLA strips for FBX bake; this script creates a
temporary NLA track per clip, exports armature-only, then removes the track.
"""
import bpy, os, sys, json
args = sys.argv[sys.argv.index("--")+1:]
blend, outroot = args[0], args[1]
bpy.ops.wm.open_mainfile(filepath=blend)
os.makedirs(outroot, exist_ok=True)
os.makedirs(os.path.join(outroot,"animations"), exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for ob in bpy.data.objects:
    if ob.name != "Operative_Control":
        ob.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("Operative_Deform") or bpy.data.objects[0]
bpy.ops.export_scene.fbx(filepath=os.path.join(outroot,"Operative.fbx"),
    use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
    object_types={'ARMATURE','MESH'}, use_mesh_modifiers=True,
    add_leaf_bones=False, armature_nodetype='NULL', bake_anim=True, bake_anim_use_all_bones=True,
    bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
    bake_anim_simplify_factor=0.0, use_armature_deform_only=True,
    axis_forward='-Z', axis_up='Y', global_scale=1.0,
    embed_textures=False, bake_space_transform=True)
print("EXPORTED base", os.path.join(outroot,"Operative.fbx"))
arm = bpy.data.objects["Operative_Deform"]
manifest = json.load(open("/home/candidate/workspace/MorphRig/docs/animation_manifest.json"))
ad = arm.animation_data
ad.use_nla = True
for entry in manifest["animations"]:
    aid = entry["id"]
    act = bpy.data.actions.get(aid)
    if not act:
        print("MISSING ACTION", aid)
        continue
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_start = entry["frame_start"]
    bpy.context.scene.frame_end = entry["frame_end"]
    # temp NLA track with single strip (bake source)
    track = ad.nla_tracks.new()
    strip = track.strips.new("T", entry["frame_start"], act)
    strip.frame_start = entry["frame_start"]
    strip.frame_end = entry["frame_end"]
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    p = os.path.join(outroot,"animations", f"{aid}.fbx")
    bpy.ops.export_scene.fbx(filepath=p, use_selection=True, object_types={'ARMATURE'},
        bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=True, bake_anim_simplify_factor=0.0,
        use_armature_deform_only=True, use_mesh_modifiers=False,
        add_leaf_bones=False, axis_forward='-Z', axis_up='Y', global_scale=1.0,
        embed_textures=False, bake_space_transform=True)
    print("BAKED", aid, entry["frame_start"], entry["frame_end"])
    # cleanup temp track
    ad.nla_tracks.remove(track)
print("DONE")
