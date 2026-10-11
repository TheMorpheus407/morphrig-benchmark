import bpy, json
A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]
defbones = [pb.name for pb in A.pose.bones]
ctrlbones = [cb.name for cb in C.pose.bones]
print("DEFORM (%d):" % len(defbones))
print(json.dumps(defbones, indent=0))
print("CTRL (%d):" % len(ctrlbones))
print(json.dumps(ctrlbones, indent=0))
print("shape keys:", [kb.name for kb in M.data.shape_keys.key_blocks])
print("custom props on ctrl obj:", sorted(C.keys()))
