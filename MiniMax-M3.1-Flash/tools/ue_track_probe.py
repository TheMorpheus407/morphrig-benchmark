"""Probe how the root bone animation is stored in the imported sequence."""
import unreal

seq = unreal.load_asset("/Game/MorphRig/Animations/A_dash_f")
unreal.log("TRACKS %s" % ", ".join(sorted(str(n) for n in unreal.AnimationLibrary.get_animation_track_names(seq))))
try:
    data = unreal.AnimationLibrary.get_raw_track_data(seq, "root")
    unreal.log("RAWTRACK root type=%s" % type(data))
    unreal.log("RAWTRACK %s" % str(data)[:400])
except Exception as exc:  # noqa: BLE001
    unreal.log("RAWTRACK error %s" % exc)

for t in (0.0, 0.1, 0.2, 0.35, 0.4667):
    track = unreal.AnimationLibrary.extract_root_track_transform(seq, t)
    loc = track.translation
    unreal.log("EXTRACT t=%.3f loc=(%.2f, %.2f, %.2f)" % (t, loc.x, loc.y, loc.z))

# the reference pose of the root bone
mesh = unreal.load_asset("/Game/MorphRig/Meshes/SK_Operative")
skel = mesh.get_editor_property("skeleton")
names = [skel.get_reference_skeleton().get_bone_name(i)
         for i in range(skel.get_reference_skeleton().get_num_bones())]
unreal.log("BONES first5=%s total=%d" % (names[:5], len(names)))
