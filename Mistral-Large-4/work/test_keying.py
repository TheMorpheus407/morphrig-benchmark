import bpy, sys
sys.path.insert(0, "tools")
import rig_ops

A = bpy.data.objects["Armature"]
M = bpy.data.objects["Operative"]
pb = A.pose.bones["pelvis"]

for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
rig_ops.reset_pose()

print("=== Q3: keyframe_insert with no action assigned ===")
pb.location = (1, 0, 0)
pb.keyframe_insert("location", frame=1)
ad = A.animation_data
print("animation_data:", ad is not None, "action:", ad.action.name if ad and ad.action else None)
act = ad.action
pb.location = (2, 0, 0)
pb.keyframe_insert("location", frame=2)
fc = act.fcurves.find('pose.bones["pelvis"].location', index=0)
print("fcurve keys:", [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])

print("=== Q1: does view_layer.update() overwrite manual values (action assigned)? ===")
bpy.context.scene.frame_set(1)
print("frame_set(1) -> location =", tuple(round(v, 3) for v in pb.location))
pb.location = (7, 7, 7)
bpy.context.view_layer.update()
print("manual set (7,7,7) + view_layer.update() ->", tuple(round(v, 3) for v in pb.location))

print("=== Q2: key at frame 5 while scene.frame=1, action assigned ===")
pb.location = (5, 0, 0)
pb.keyframe_insert("location", frame=5)
fc = act.fcurves.find('pose.bones["pelvis"].location', index=0)
print("fcurve keys:", [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
bpy.context.scene.frame_set(5)
print("frame_set(5) -> location =", tuple(round(v, 3) for v in pb.location))

print("=== Q2b: re-key same frame overwrites? ===")
bpy.context.scene.frame_set(1)
pb.location = (9, 0, 0)
pb.keyframe_insert("location", frame=1)
fc = act.fcurves.find('pose.bones["pelvis"].location', index=0)
print("fcurve keys:", [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])

print("=== Q4: shape keys with action ===")
sk = M.data.shape_keys
sk.animation_data_create()
sk.animation_data.action = None
kb = sk.key_blocks["smile_L"]
kb.value = 0.3
kb.keyframe_insert("value", frame=1)
print("sk action:", sk.animation_data.action.name if sk.animation_data.action else None)
fca = sk.animation_data.action
kb.value = 0.8
kb.keyframe_insert("value", frame=4)
fc = fca.fcurves.find('key_blocks["smile_L"].value')
print("sk fcurve keys:", [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
kb.value = 0.5
bpy.context.view_layer.update()
print("after manual set + update, kb.value =", round(kb.value, 3))

print("=== Q5: euler unwrap sanity - rotation_mode of pose bones ===")
print("pelvis rotation_mode:", pb.rotation_mode)
modes = set(p.rotation_mode for p in A.pose.bones)
print("all deform rotation modes:", modes)
