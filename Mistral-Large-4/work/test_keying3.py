import bpy, sys
sys.path.insert(0, "tools")
import rig_ops

A = bpy.data.objects["Armature"]
pb = A.pose.bones["pelvis"]
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
rig_ops.reset_pose()

pb.location = (1, 0, 0)
pb.keyframe_insert("location", frame=1)
ad = A.animation_data
act = ad.action
print("ACTION attrs:", [a for a in dir(act) if not a.startswith("_")][:40])
slot = act.slots[0]
print("SLOT attrs:", [a for a in dir(slot) if not a.startswith("_")])
print("slot repr:", slot, "identifier:", slot.identifier, "target_id_type:", slot.target_id_type)
print("layers:", len(act.layers))
l0 = act.layers[0]
print("LAYER attrs:", [a for a in dir(l0) if not a.startswith("_")])
st = l0.strips[0]
print("STRIP attrs:", [a for a in dir(st) if not a.startswith("_")])
print("strip frame_start/end:", st.frame_start, st.frame_end, "type:", st.type)
cb = st.channelbags[0]
print("CHANNELBAG attrs:", [a for a in dir(cb) if not a.startswith("_")])
print("cb slot:", cb.slot.identifier if cb.slot else None)
for fc in cb.fcurves:
    print("  fc:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
print("ad.action_slot:", ad.action_slot.identifier if ad.action_slot else None)
print("ad.action:", ad.action.name)

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
    for s in l.strips:
        for c in s.channelbags:
            for fc in c.fcurves:
                print("keys:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
bpy.context.scene.frame_set(5)
print("frame_set(5) -> location =", tuple(round(v, 3) for v in pb.location))

print("=== Q2b: re-key frame 1 ===")
bpy.context.scene.frame_set(1)
pb.location = (9, 0, 0)
pb.keyframe_insert("location", frame=1)
for l in act.layers:
    for s in l.strips:
        for c in s.channelbags:
            for fc in c.fcurves:
                print("keys:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
