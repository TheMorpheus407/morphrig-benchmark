#!/usr/bin/env python3
"""
Blender 5.1+ Editable CTRL Action Authoring & Exact Closed-Form DEF Skeleton Baker.

Authors all 96 entries in required_animations.csv at 30 FPS as:
  1) Editable animator control actions:
       - Armature action:  CTRL_<id>     (CTRL_* transforms, CTRL_Master IK/FK & prop switches, CTRL_Fingers curl/spread)
       - ShapeKey action:  SK_CTRL_<id>  (46 facial, viseme, preset & corrective shape keys)
  2) Baked export actions (for FBX & Unreal Engine 5.8):
       - Armature action:  <id>          (92 DEF bones exact world-preserving matrix_basis, continuous quaternions, pose_markers, custom morph curves on root)
       - ShapeKey action:  SK_<id>       (baked shape-key F-curves)

Supports rebaking (`bake_from_existing_ctrl_actions`) so any manual edit made to `CTRL_<id>` or `SK_CTRL_<id>`
in `source/Operative.blend` cleanly rebakes `<id>` and re-exports FBX without regenerating geometry.
"""

import math
from pathlib import Path
import bpy
from mathutils import Vector, Euler, Quaternion, Matrix

from motion_library import MotionLibrary, PoseSpec, ClipDefinition, FPS

MASTER_PROP_DEFAULTS = {
    "ik_fk_arm_l": 0.0,
    "ik_fk_arm_r": 0.0,
    "ik_fk_leg_l": 1.0,
    "ik_fk_leg_r": 1.0,
    "head_look_at": 0.0,
    "eye_look_at": 1.0,
    "cell_in_hand_l": 0.0,
    "beacon_in_hand_l": 0.0,
    "beacon_planted": 0.0,
}


def set_def_constraints_muted(arm_obj: bpy.types.Object, muted: bool) -> None:
    """Mutes or unmutes constraints on DEF bones (muted during baked DEF playback/FBX export; unmuted for live CTRL editing)."""
    for pb in arm_obj.pose.bones:
        if pb.bone.use_deform:
            for c in pb.constraints:
                c.mute = muted


def ensure_fcurve(datablock: bpy.types.ID, action: bpy.types.Action, data_path: str, index: int = 0):
    """Blender 5.1+ slotted Action F-Curve helper."""
    return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)


def write_curve_fast(datablock: bpy.types.ID, action: bpy.types.Action, data_path: str, index: int, frames: list[int], values: list[float], constant_interp: bool = False) -> None:
    fc = ensure_fcurve(datablock, action, data_path, index=index)
    fc.keyframe_points.clear()
    n = len(frames)
    fc.keyframe_points.add(n)
    flat = [0.0] * (2 * n)
    for i, (fr, val) in enumerate(zip(frames, values)):
        flat[2 * i] = float(fr)
        flat[2 * i + 1] = float(val)
    fc.keyframe_points.foreach_set("co", flat)
    interp = "CONSTANT" if constant_interp else "LINEAR"
    for kp in fc.keyframe_points:
        kp.interpolation = interp
    fc.update()


def reset_rig_pose(arm_obj: bpy.types.Object, lod0_obj: bpy.types.Object) -> None:
    for pb in arm_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    cm = arm_obj.pose.bones.get("CTRL_Master")
    if cm:
        for k, v in MASTER_PROP_DEFAULTS.items():
            cm[k] = v
    for S in ("L", "R"):
        cf = arm_obj.pose.bones.get(f"CTRL_Fingers_{S}")
        if cf:
            cf["curl"] = 0.0
            cf["spread"] = 0.0
    if lod0_obj and lod0_obj.data.shape_keys:
        for kb in lod0_obj.data.shape_keys.key_blocks:
            if kb.name != "Basis":
                kb.value = 0.0


def apply_pose_spec(
    arm_obj: bpy.types.Object,
    lod0_obj: bpy.types.Object,
    spec: PoseSpec,
    rest_r3: dict[str, Matrix],
) -> None:
    reset_rig_pose(arm_obj, lod0_obj)
    pb = arm_obj.pose.bones
    cm = pb["CTRL_Master"]
    for k, v in MASTER_PROP_DEFAULTS.items():
        cm[k] = float(spec.props.get(k, v))

    pb["CTRL_Fingers_L"]["curl"] = float(spec.finger_curl_l)
    pb["CTRL_Fingers_R"]["curl"] = float(spec.finger_curl_r)
    pb["CTRL_Fingers_L"]["spread"] = float(spec.finger_spread_l)
    pb["CTRL_Fingers_R"]["spread"] = float(spec.finger_spread_r)

    for bn, loc in spec.loc.items():
        if bn in pb:
            pb[bn].location = rest_r3[bn].inverted() @ Vector(loc)

    for bn, rot in spec.rot.items():
        if bn in pb:
            r3 = rest_r3[bn]
            pb[bn].rotation_mode = "QUATERNION"
            pb[bn].rotation_quaternion = (r3.inverted() @ Euler(rot, "XYZ").to_matrix() @ r3).to_quaternion()

    if lod0_obj and lod0_obj.data.shape_keys:
        kbs = lod0_obj.data.shape_keys.key_blocks
        for sk_name, val in spec.shapes.items():
            if sk_name in kbs:
                kbs[sk_name].value = float(val)


def ensure_root_morph_props(arm_obj: bpy.types.Object, sk_names: list[str]) -> None:
    """Ensures root DEF bone carries float custom properties matching all 46 shape-key names for FBX custom-attribute curve export."""
    root_pb = arm_obj.pose.bones["root"]
    for skn in sk_names:
        if skn not in root_pb:
            root_pb[skn] = 0.0


def author_ctrl_actions(
    arm_obj: bpy.types.Object,
    lod0_obj: bpy.types.Object,
    ml: MotionLibrary,
) -> None:
    """Authors all 96 editable CTRL_<id> and SK_CTRL_<id> actions from MotionLibrary."""
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    sk_id = lod0_obj.data.shape_keys
    if not sk_id.animation_data:
        sk_id.animation_data_create()

    rest_r3 = {b.name: b.matrix_local.to_3x3() for b in arm_obj.data.bones}
    all_sk_names = [kb.name for kb in sk_id.key_blocks if kb.name != "Basis"]
    ensure_root_morph_props(arm_obj, all_sk_names)

    for clip in ml.catalog:
        cid = clip.clip_id
        n_frames = max(1, clip.frames)
        frame_list = list(range(0, n_frames + 1))

        # Evaluate PoseSpecs across [0 .. n_frames]
        specs: list[PoseSpec] = []
        for fr in frame_list:
            if clip.form == "pose":
                specs.append(ml.evaluate(cid, 0))
            elif clip.form == "loop" and fr == n_frames:
                # Guarantee exact mathematical loop closure: frame N == frame 0!
                specs.append(specs[0])
            else:
                specs.append(ml.evaluate(cid, fr))

        # Create / clear CTRL_<id> on Armature
        ctrl_act_name = f"CTRL_{cid}"
        old_c = bpy.data.actions.get(ctrl_act_name)
        if old_c:
            bpy.data.actions.remove(old_c)
        ctrl_act = bpy.data.actions.new(name=ctrl_act_name)
        ctrl_act.use_fake_user = True
        ctrl_act.use_frame_range = True
        ctrl_act.frame_start = 0.0
        ctrl_act.frame_end = float(n_frames)
        arm_obj.animation_data.action = ctrl_act

        # Collect animated CTRL channels
        loc_bones = sorted({bn for sp in specs for bn in sp.loc.keys()})
        rot_bones = sorted({bn for sp in specs for bn in sp.rot.keys()})

        for bn in loc_bones:
            r3_inv = rest_r3[bn].inverted()
            xs, ys, zs = [], [], []
            for sp in specs:
                v = r3_inv @ Vector(sp.loc.get(bn, (0.0, 0.0, 0.0)))
                xs.append(v.x)
                ys.append(v.y)
                zs.append(v.z)
            dpath = f'pose.bones["{bn}"].location'
            write_curve_fast(arm_obj, ctrl_act, dpath, 0, frame_list, xs)
            write_curve_fast(arm_obj, ctrl_act, dpath, 1, frame_list, ys)
            write_curve_fast(arm_obj, ctrl_act, dpath, 2, frame_list, zs)

        for bn in rot_bones:
            r3 = rest_r3[bn]
            r3_inv = r3.inverted()
            qw, qx, qy, qz = [], [], [], []
            prev_q = None
            for sp in specs:
                rot_xyz = sp.rot.get(bn, (0.0, 0.0, 0.0))
                q = (r3_inv @ Euler(rot_xyz, "XYZ").to_matrix() @ r3).to_quaternion()
                if prev_q is not None and q.dot(prev_q) < 0.0:
                    q = -q
                prev_q = q
                qw.append(q.w)
                qx.append(q.x)
                qy.append(q.y)
                qz.append(q.z)
            dpath = f'pose.bones["{bn}"].rotation_quaternion'
            write_curve_fast(arm_obj, ctrl_act, dpath, 0, frame_list, qw)
            write_curve_fast(arm_obj, ctrl_act, dpath, 1, frame_list, qx)
            write_curve_fast(arm_obj, ctrl_act, dpath, 2, frame_list, qy)
            write_curve_fast(arm_obj, ctrl_act, dpath, 3, frame_list, qz)

        # Master custom properties + Finger curl/spread
        for pk, pdef in MASTER_PROP_DEFAULTS.items():
            vals = [float(sp.props.get(pk, pdef)) for sp in specs]
            write_curve_fast(arm_obj, ctrl_act, f'pose.bones["CTRL_Master"]["{pk}"]', 0, frame_list, vals)

        write_curve_fast(arm_obj, ctrl_act, 'pose.bones["CTRL_Fingers_L"]["curl"]',   0, frame_list, [sp.finger_curl_l for sp in specs])
        write_curve_fast(arm_obj, ctrl_act, 'pose.bones["CTRL_Fingers_R"]["curl"]',   0, frame_list, [sp.finger_curl_r for sp in specs])
        write_curve_fast(arm_obj, ctrl_act, 'pose.bones["CTRL_Fingers_L"]["spread"]', 0, frame_list, [sp.finger_spread_l for sp in specs])
        write_curve_fast(arm_obj, ctrl_act, 'pose.bones["CTRL_Fingers_R"]["spread"]', 0, frame_list, [sp.finger_spread_r for sp in specs])

        for m_fr, m_name in clip.markers:
            pm = ctrl_act.pose_markers.new(name=m_name)
            pm.frame = int(m_fr)

        # Create / clear SK_CTRL_<id> on ShapeKeys
        sk_ctrl_name = f"SK_CTRL_{cid}"
        old_sk = bpy.data.actions.get(sk_ctrl_name)
        if old_sk:
            bpy.data.actions.remove(old_sk)
        sk_ctrl_act = bpy.data.actions.new(name=sk_ctrl_name)
        sk_ctrl_act.use_fake_user = True
        sk_id.animation_data.action = sk_ctrl_act

        active_sks = sorted({skn for sp in specs for skn, v in sp.shapes.items() if abs(v) > 1e-5})
        for skn in active_sks:
            vals = [float(sp.shapes.get(skn, 0.0)) for sp in specs]
            write_curve_fast(sk_id, sk_ctrl_act, f'key_blocks["{skn}"].value', 0, frame_list, vals)

    print(f"[AnimBuilder] Authored {len(ml.catalog)} editable CTRL_<id> and SK_CTRL_<id> actions.")


def bake_ctrl_to_def_actions(
    arm_obj: bpy.types.Object,
    lod0_obj: bpy.types.Object,
    ml: MotionLibrary,
    target_clips: list[str] | None = None,
) -> dict[str, dict]:
    """
    Evaluates live CTRL_<id> + SK_CTRL_<id> through all Blender rig constraints frame-by-frame
    and bakes exact world-preserving <id> DEF actions + SK_<id> shape-key actions.
    Returns per-clip baked telemetry (root displacement, active morph curves, markers) for manifest generation.
    """
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0

    set_def_constraints_muted(arm_obj, False)
    sk_id = lod0_obj.data.shape_keys
    all_sk_names = [kb.name for kb in sk_id.key_blocks if kb.name != "Basis"]
    ensure_root_morph_props(arm_obj, all_sk_names)

    def_bones = [b.name for b in arm_obj.data.bones if b.use_deform]
    rest_mat = {bn: arm_obj.data.bones[bn].matrix_local.copy() for bn in def_bones}
    rest_inv = {bn: rest_mat[bn].inverted() for bn in def_bones}
    def_parent = {
        bn: (arm_obj.data.bones[bn].parent.name if (arm_obj.data.bones[bn].parent and arm_obj.data.bones[bn].parent.use_deform) else None)
        for bn in def_bones
    }
    # Precompute R_p_inv @ R_b for fast closed-form child basis evaluation
    parent_rel = {
        bn: (rest_inv[def_parent[bn]] @ rest_mat[bn]) if def_parent[bn] else rest_mat[bn]
        for bn in def_bones
    }

    telemetry: dict[str, dict] = {}
    clips_to_bake = [c for c in ml.catalog if (target_clips is None or c.clip_id in target_clips)]

    for clip in clips_to_bake:
        cid = clip.clip_id
        n_frames = max(1, clip.frames)
        frame_list = list(range(0, n_frames + 1))

        ctrl_act = bpy.data.actions.get(f"CTRL_{cid}")
        sk_ctrl_act = bpy.data.actions.get(f"SK_CTRL_{cid}")
        assert ctrl_act is not None, f"Missing CTRL_{cid} action!"

        reset_rig_pose(arm_obj, lod0_obj)
        arm_obj.animation_data.action = ctrl_act
        if sk_ctrl_act:
            sk_id.animation_data.action = sk_ctrl_act

        # Sample evaluated DEF world/armature matrices & shape-key values across [0 .. n_frames]
        loc_samples = {bn: ([], [], []) for bn in def_bones}
        rot_samples = {bn: ([], [], [], []) for bn in def_bones}
        prev_quat: dict[str, Quaternion] = {}
        sk_samples: dict[str, list[float]] = {skn: [] for skn in all_sk_names}

        root_start = None
        root_end = None

        for fr in frame_list:
            scene.frame_set(fr)
            bpy.context.view_layer.update()

            pb = arm_obj.pose.bones
            eval_world = {bn: pb[bn].matrix.copy() for bn in def_bones}

            if fr == 0:
                root_start = eval_world["root"].translation.copy()
            if fr == n_frames:
                root_end = eval_world["root"].translation.copy()

            for bn in def_bones:
                par_n = def_parent[bn]
                mw = eval_world[bn]
                if par_n is None:
                    mb = rest_inv[bn] @ mw
                else:
                    mb = (eval_world[par_n] @ parent_rel[bn]).inverted() @ mw

                loc_v = mb.to_translation()
                q = mb.to_quaternion()
                if bn in prev_quat and q.dot(prev_quat[bn]) < 0.0:
                    q = -q
                prev_quat[bn] = q

                lx, ly, lz = loc_samples[bn]
                lx.append(loc_v.x)
                ly.append(loc_v.y)
                lz.append(loc_v.z)

                qw, qx, qy, qz = rot_samples[bn]
                qw.append(q.w)
                qx.append(q.x)
                qy.append(q.y)
                qz.append(q.z)

            for skn in all_sk_names:
                sk_samples[skn].append(float(sk_id.key_blocks[skn].value))

        # Create baked DEF action `<id>`
        old_def = bpy.data.actions.get(cid)
        if old_def:
            bpy.data.actions.remove(old_def)
        baked_act = bpy.data.actions.new(name=cid)
        baked_act.use_fake_user = True
        baked_act.use_frame_range = True
        baked_act.frame_start = 0.0
        baked_act.frame_end = float(n_frames)
        arm_obj.animation_data.action = baked_act

        for bn in def_bones:
            pb[bn].rotation_mode = "QUATERNION"
            lx, ly, lz = loc_samples[bn]
            dpath_l = f'pose.bones["{bn}"].location'
            write_curve_fast(arm_obj, baked_act, dpath_l, 0, frame_list, lx)
            write_curve_fast(arm_obj, baked_act, dpath_l, 1, frame_list, ly)
            write_curve_fast(arm_obj, baked_act, dpath_l, 2, frame_list, lz)

            qw, qx, qy, qz = rot_samples[bn]
            dpath_r = f'pose.bones["{bn}"].rotation_quaternion'
            write_curve_fast(arm_obj, baked_act, dpath_r, 0, frame_list, qw)
            write_curve_fast(arm_obj, baked_act, dpath_r, 1, frame_list, qx)
            write_curve_fast(arm_obj, baked_act, dpath_r, 2, frame_list, qy)
            write_curve_fast(arm_obj, baked_act, dpath_r, 3, frame_list, qz)

        # Copy pose markers from CTRL_<id> (or clip definition)
        for pm_src in ctrl_act.pose_markers:
            pm = baked_act.pose_markers.new(name=pm_src.name)
            pm.frame = pm_src.frame

        # Bake active morph curves onto BOTH SK_<id> AND root custom properties on `<id>` (for FBX export)
        sk_baked_name = f"SK_{cid}"
        old_skb = bpy.data.actions.get(sk_baked_name)
        if old_skb:
            bpy.data.actions.remove(old_skb)
        sk_baked_act = bpy.data.actions.new(name=sk_baked_name)
        sk_baked_act.use_fake_user = True
        sk_id.animation_data.action = sk_baked_act

        active_morph_dict = {}
        for skn, vals in sk_samples.items():
            if max(abs(v) for v in vals) > 1e-4:
                write_curve_fast(sk_id, sk_baked_act, f'key_blocks["{skn}"].value', 0, frame_list, vals)
                write_curve_fast(arm_obj, baked_act, f'pose.bones["root"]["{skn}"]', 0, frame_list, vals)
                active_morph_dict[skn] = [round(v, 4) for v in vals]

        disp = (root_end - root_start) if (root_start and root_end) else Vector((0.0, 0.0, 0.0))
        telemetry[cid] = {
            "root_displacement_m": [round(disp.x, 4), round(disp.y, 4), round(disp.z, 4)],
            "root_displacement_length_m": round(disp.length, 4),
            "active_morph_curves": active_morph_dict,
            "markers": [{"frame": pm.frame, "time_sec": round(pm.frame / float(FPS), 4), "name": pm.name} for pm in baked_act.pose_markers],
        }

    # Restore clean neutral bind rest state with unmuted live CTRL constraints
    arm_obj.animation_data.action = None
    sk_id.animation_data.action = None
    reset_rig_pose(arm_obj, lod0_obj)
    set_def_constraints_muted(arm_obj, False)
    scene.frame_set(0)
    bpy.context.view_layer.update()

    print(f"[AnimBuilder] Baked {len(clips_to_bake)} exact DEF export actions (<id> + SK_<id>).")
    return telemetry
