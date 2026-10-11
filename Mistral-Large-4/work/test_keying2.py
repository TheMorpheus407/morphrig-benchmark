import bpy, sys
sys.path.insert(0, "tools")
import rig_ops

A = bpy.data.objects["Armature"]
M = bpy.data.objects["Operative"]
pb = A.pose.bones["pelvis"]

for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
rig_ops.reset_pose()

print("=== key with no action; inspect slotted API ===")
pb.location = (1, 0, 0)
pb.keyframe_insert("location", frame=1)
ad = A.animation_data
act = ad.action
print("action:", act.name, "slots:", [(s.name, s.identifier) for s in act.slots])
print("layers:", len(act.layers), "strips:", [len(l.strips) for l in act.layers])
for l in act.layers:
    for st in l.strips:
        print("  strip:", st.name, "frame_start", st.frame_start, "frame_end", st.frame_end, "channelbags:", len(st.channelbags))
        for cb in st.channelbags:
            print("    channelbag slot:", cb.slot.name if cb.slot else None, "fcurves:", len(cb.fcurves))
            for fc in cb.fcurves:
                print("      fc:", fc.data_path, fc.array_index, "keys:", [(kp.co.x, round(kp.co.y,3)) for kp in fc.keyframe_points])

pb.location = (2, 0, 0)
pb.keyframe_insert("location", frame=2)
for l in act.layers:
    for st in l.strips:
        for cb in st.channelbags:
            for fc in cb.fcurves:
                print("after 2nd key:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y,3)) for kp in fc.keyframe_points])

print("=== Q1: overwrite test ===")
bpy.context.scene.frame_set(1)
print("frame_set(1) -> location =", tuple(round(v, 3) for v in pb.location))
pb.location = (7, 7, 7)
bpy.context.view_layer.update()
print("manual set (7,7,7) + view_layer.update() ->", tuple(round(v, 3) for v in pb.location))

print("=== Q2: key at frame 5, scene.frame=1 ===")
pb.location = (5, 0, 0)
pb.keyframe_insert("location", frame=5)
for l in act.layers:
    for st in l.strips:
        for cb in st.channelbags:
            for fc in cb.fcurves:
                print("keys:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y,3)) for kp in fc.keyframe_points])
bpy.context.scene.frame_set(5)
print("frame_set(5) -> location =", tuple(round(v, 3) for v in pb.location))

print("=== Q2b: re-key frame 1 ===")
bpy.context.scene.frame_set(1)
pb.location = (9, 0, 0)
pb.keyframe_insert("location", frame=1)
for l in act.layers:
    for st in l.strips:
        for cb in st.channelbags:
            for fc in cb.fcurves:
                print("keys:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y,3)) for kp in fc.keyframe_points])

print("=== Q4: shape keys ===")
sk = M.data.shape_keys
sk.animation_data_create()
sk.animation_data.action = None
kb = sk.key_blocks["smile_L"]
kb.value = 0.3
kb.keyframe_insert("value", frame=1)
fca = sk.animation_data.action
print("sk action:", fca.name)
kb.value = 0.8
kb.keyframe_insert("value", frame=4)
for l in fca.layers:
    for st in l.strips:
        for cb in st.channelbags:
            for fc in cb.fcurves:
                print("sk fc:", fc.data_path, [(kp.co.x, round(kp.co.y,3)) for kp in fc.keyframe_points])
kb.value = 0.5
bpy.context.view_layer.update()
print("after manual set + update, kb.value =", round(kb.value, 3))

print("=== Q6: new action via bpy.data.actions.new + slot assignment ===")
act2 = bpy.data.actions.new("manual_act")
print("new action slots:", [(s.name, s.identifier) for s in act2.slots], "layers:", len(act2.layers))
print("has fcurves attr:", hasattr(act2, "fcurves"))
print("animation_data.action_slot:", ad.action_slot)
