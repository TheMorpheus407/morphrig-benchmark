import bpy
bpy.ops.wm.open_mainfile(filepath="source/Operative_rig.blend")
me = bpy.data.objects["Operative"]
sk = me.data.shape_keys
sk.animation_data_create()
act = bpy.data.actions.new("sktest")
sk.animation_data.action = act
for name in ("smile_L", "lip_close", "pucker"):
    kb = sk.key_blocks[name]
    kb.value = 0.0
    kb.keyframe_insert("value", frame=1)
    kb.value = 1.0
    kb.keyframe_insert("value", frame=10)
bpy.ops.export_scene.fbx(filepath="work/shapekey_test.fbx", use_selection=False,
                         object_types={'MESH', 'ARMATURE'},
                         add_leaf_bones=False, bake_anim=True,
                         bake_anim_use_all_actions=False, bake_anim_step=1,
                         bake_anim_simplify_factor=0.0)
print("FBX_TEST_DONE")
