"""Print the bone orientations of the imported skeleton."""
import unreal

for clip in ("A_idle_combat", "A_dash_f"):
    seq = unreal.load_asset("/Game/MorphRig/Animations/%s" % clip)
    for bone in ("operative_rig", "root", "pelvis"):
        xform = unreal.AnimationLibrary.get_bone_pose_for_time(seq, bone, 0.0, False)
        t = xform.translation
        r = xform.rotation
        unreal.log("BONEPOSE %s %-13s loc=(%.2f, %.2f, %.2f) rot=%s" %
                   (clip, bone, t.x, t.y, t.z, str(r)))
