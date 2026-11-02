"""Probe the root bone track of the imported dash clips."""
import unreal

ANIM_DIR = "/Game/MorphRig/Animations"


def fmt(xform):
    loc = xform.translation
    return "(%.2f, %.2f, %.2f)" % (loc.x, loc.y, loc.z)


for name in ("dash_f", "dash_b", "dash_l", "dash_r", "walk_f"):
    seq = unreal.load_asset("%s/A_%s" % (ANIM_DIR, name))
    if seq is None:
        unreal.log("ROOTTACK %s missing" % name)
        continue
    length = float(seq.get_editor_property("sequence_length"))
    for t in (0.0, length * 0.25, length * 0.5, length * 0.75, length):
        raw = unreal.AnimationLibrary.get_bone_pose_for_time(seq, "root", t, False)
        extracted = unreal.AnimationLibrary.get_bone_pose_for_time(seq, "root", t, True)
        track = unreal.AnimationLibrary.extract_root_track_transform(seq, t)
        unreal.log("ROOTTACK %s t=%.3f raw=%s extract=%s track=%s" %
                   (name, t, fmt(raw), fmt(extracted), fmt(track)))
