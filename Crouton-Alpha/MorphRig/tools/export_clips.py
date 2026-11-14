"""Export base + 96 single-strip mesh+anim FBXs (Blender 5 NLA bake)."""
import bpy, os, sys, json
args = sys.argv[sys.argv.index("--")+1:]
blend, outroot = args[0], args[1]
bpy.ops.wm.open_mainfile(filepath=blend)
os.makedirs(outroot, exist_ok=True)
os.makedirs(os.path.join(outroot,"animations"), exist_ok=True)
arm = bpy.data.objects["Operative_Deform"]
manifest = json.load(open("/home/candidate/workspace/MorphRig/docs/animation_manifest.json"))
ad = arm.animation_data
ad.use_nla = True
def export_clip(e):
    aid = e["id"]
    act = bpy.data.actions.get(aid)
    if not act: return False
    arm.animation_data.action = act
    if act.slots: arm.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_start = e["frame_start"]; bpy.context.scene.frame_end = e["frame_end"]
    track = ad.nla_tracks.new()
    strip = track.strips.new("T", e["frame_start"], act)
    strip.frame_start = e["frame_start"]; strip.frame_end = e["frame_end"]
    bpy.ops.object.select_all(action='DESELECT')
    for ob in bpy.data.objects:
        if ob.name in ("Operative_Deform","Operative_Body"): ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    p = os.path.join(outroot,"animations", f"{aid}.fbx")
    bpy.ops.export_scene.fbx(filepath=p, use_selection=True, object_types={'ARMATURE','MESH'},
        use_mesh_modifiers=True, add_leaf_bones=False,
        bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=True,
        bake_anim_simplify_factor=0.0, use_armature_deform_only=True, axis_forward='-Z', axis_up='Y', global_scale=1.0,
        embed_textures=False, bake_space_transform=True)
    print("BAKED", aid)
    ad.nla_tracks.remove(track)
    return True
# base: idle_combat strip with full mesh (for skeleton+mesh+materials)
if True:
    e = [x for x in manifest["animations"] if x["id"]=="idle_combat"][0]
    act = bpy.data.actions["idle_combat"]
    arm.animation_data.action = act
    if act.slots: arm.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_start = 1; bpy.context.scene.frame_end = e["frame_end"]
    track = ad.nla_tracks.new()
    strip = track.strips.new("T", 1, act); strip.frame_start=1; strip.frame_end=e["frame_end"]
    bpy.ops.object.select_all(action='DESELECT')
    for ob in bpy.data.objects:
        if ob.name!="Operative_Control" and ob.name not in ("Operative_LOD1","Operative_LOD2"): ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=os.path.join(outroot,"Operative.fbx"), use_selection=True,
        object_types={'ARMATURE','MESH'}, use_mesh_modifiers=True, add_leaf_bones=False,
        bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=True,
        bake_anim_simplify_factor=0.0, use_armature_deform_only=True, axis_forward='-Z', axis_up='Y', global_scale=1.0,
        embed_textures=True, bake_space_transform=True)
    print("BAKED base Operative.fbx")
    ad.nla_tracks.remove(track)
for e in manifest["animations"]:
    export_clip(e)
print("DONE")
