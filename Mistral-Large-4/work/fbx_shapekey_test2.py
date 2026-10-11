import bpy
bpy.ops.wm.open_mainfile(filepath="source/Operative_rig.blend")
# no shape-key animation at all: does the static export still carry morphs?
bpy.ops.export_scene.fbx(filepath="work/shapekey_static.fbx", use_selection=False,
                         object_types={'MESH', 'ARMATURE'},
                         add_leaf_bones=False, bake_anim=False)
print("FBX_TEST2_DONE")
