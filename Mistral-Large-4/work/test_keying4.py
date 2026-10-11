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
cb = act.layers[0].strips[0].channelbags[0]
print("CB attrs:", [a for a in dir(cb) if not a.startswith("_")])
print("cb slot:", cb.slot.identifier if cb.slot else None, "name_display:", cb.slot.name_display if cb.slot else None)
for fc in cb.fcurves:
    print("  fc:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
print("ad.action_slot:", ad.action_slot.identifier if ad.action_slot else None)
print("action frame_range:", act.frame_range, "is_layered:", act.is_action_layered)

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

print("=== Q3: create action manually, assign, key into it ===")
act2 = bpy.data.actions.new("manual_act")
print("new action: slots:", [s.identifier for s in act2.slots], "layers:", len(act2.layers))
if len(act2.layers) == 0:
    print("  no layers! need to create layer/strip/channelbag manually")
    print("  Action attrs for creation:", [a for a in dir(act2) if "layer" in a.lower() or "strip" in a.lower() or "channel" in a.lower() or "slot" in a.lower()])
# try assigning
ad.action = act2
print("ad.action:", ad.action.name, "ad.action_slot:", ad.action_slot.identifier if ad.action_slot else None)
pb.location = (3, 1, 4)
pb.keyframe_insert("location", frame=1)
print("after key into manual action:")
for l in act2.layers:
    for s in l.strips:
        for c in s.channelbags:
            for fc in c.fcurves:
                print("  keys:", fc.data_path, fc.array_index, [(kp.co.x, round(kp.co.y, 3)) for kp in fc.keyframe_points])
