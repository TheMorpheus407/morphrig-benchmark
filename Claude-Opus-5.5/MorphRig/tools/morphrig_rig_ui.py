"""MorphRig rig tools (Blender 5.x). 3D View > Sidebar (N) > MorphRig.

Embedded in source/Operative.blend as the text block 'morphrig_rig_ui.py' (registered on file load
when Python auto-run is trusted; otherwise open the text block and press Run Script, or install
this file as an add-on).

  Reset Pose            all MR_Rig controls to rest, face props / prop switches to default
  Snap FK -> IK / IK -> FK  pose matching for each arm and leg before switching the ik_fk blend
  Bake Active Action    sample the active RIG_<clip> action onto MR_Skeleton as SK_<clip>
                        (frame range of the action, one key per frame, markers copied)
"""
bl_info = {"name": "MorphRig rig tools", "blender": (5, 0, 0), "category": "Rigging"}

import bpy
from mathutils import Matrix

RIG = "MR_Rig"
SKEL = "MR_Skeleton"
ARM = {"upper": "upperarm", "lower": "lowerarm", "hand": "hand"}


def rig():
    return bpy.data.objects.get(RIG)


def _set_world(pb, M):
    pb.matrix = M
    bpy.context.view_layer.update()


class MR_OT_reset_pose(bpy.types.Operator):
    bl_idname = "morphrig.reset_pose"
    bl_label = "Reset Pose"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        r = rig()
        if r.animation_data:
            r.animation_data.action = None
        for pb in r.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)
            for k in list(pb.keys()):
                if isinstance(pb[k], float):
                    pb[k] = 1.0 if k == "ik_fk" and pb.name.startswith("c_foot_ik") else 0.0
        for s in "lr":
            r.pose.bones[f"c_hand_ik_{s}"]["ik_fk"] = 0.0
        context.view_layer.update()
        return {'FINISHED'}


class MR_OT_snap(bpy.types.Operator):
    """Pose matching: make one chain match the other so switching ik_fk does not pop"""
    bl_idname = "morphrig.snap"
    bl_label = "Snap"
    bl_options = {'REGISTER', 'UNDO'}
    limb: bpy.props.StringProperty()      # arm_l, arm_r, leg_l, leg_r
    to_ik: bpy.props.BoolProperty()       # True: IK controls follow the current (FK) pose

    def execute(self, context):
        r = rig()
        pbs = r.pose.bones
        kind, s = self.limb.split("_")
        if kind == "arm":
            chain = [("c_upperarm_fk_", "upperarm_"), ("c_lowerarm_fk_", "lowerarm_"), ("c_hand_fk_", "hand_")]
            if self.to_ik:
                H = pbs["hand_" + s].matrix.copy()
                el = pbs["lowerarm_" + s].matrix.translation
                sh = pbs["upperarm_" + s].matrix.translation
                _set_world(pbs["c_hand_ik_" + s], H)
                mid = (sh + H.translation) * 0.5
                pole = el + (el - mid).normalized() * 0.4
                P = pbs["c_elbow_pole_" + s].matrix.copy()
                P.translation = pole
                _set_world(pbs["c_elbow_pole_" + s], P)
                pbs["c_hand_ik_" + s]["ik_fk"] = 1.0
            else:
                mats = [pbs[d + s].matrix.copy() for _, d in chain]
                for (c, _), M in zip(chain, mats):
                    _set_world(pbs[c + s], M)
                pbs["c_hand_ik_" + s]["ik_fk"] = 0.0
        else:
            chain = [("c_thigh_fk_", "thigh_"), ("c_calf_fk_", "calf_"), ("c_foot_fk_", "foot_"), ("c_ball_fk_", "ball_")]
            if self.to_ik:
                bones = r.data.bones
                rel = bones["c_foot_ik_" + s].matrix_local.inverted() @ bones["mch_ankle_ik_" + s].matrix_local
                Fw = pbs["foot_" + s].matrix.copy()
                pbs["c_foot_ik_" + s]["roll"] = 0.0
                _set_world(pbs["c_foot_ik_" + s], Fw @ rel.inverted())
                pbs["c_ball_ik_" + s].rotation_euler = pbs["c_ball_fk_" + s].rotation_euler.copy()
                pbs["c_foot_ik_" + s]["ik_fk"] = 1.0
            else:
                mats = [pbs[d + s].matrix.copy() for _, d in chain]
                for (c, _), M in zip(chain, mats):
                    _set_world(pbs[c + s], M)
                pbs["c_foot_ik_" + s]["ik_fk"] = 0.0
        context.view_layer.update()
        return {'FINISHED'}


class MR_OT_bake(bpy.types.Operator):
    """Bake the active RIG_<clip> action of MR_Rig onto MR_Skeleton (SK_<clip>)"""
    bl_idname = "morphrig.bake"
    bl_label = "Bake Active Action"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        r, sk = rig(), bpy.data.objects.get(SKEL)
        act = r.animation_data.action if r.animation_data else None
        if act is None:
            self.report({'ERROR'}, "MR_Rig has no active action")
            return {'CANCELLED'}
        cid = act.name[4:] if act.name.startswith("RIG_") else act.name
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        name = "SK_" + cid
        old = bpy.data.actions.get(name)
        if old:
            bpy.data.actions.remove(old)
        sc = context.scene
        frames = []
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            frames.append({pb.name: sk.convert_space(pose_bone=pb, matrix=pb.matrix, from_space='POSE',
                                                     to_space='LOCAL') for pb in sk.pose.bones})
        new = bpy.data.actions.new(name)
        new.use_fake_user = True
        if sk.animation_data is None:
            sk.animation_data_create()
        prev = sk.animation_data.action
        sk.animation_data.action = new
        for i, f in enumerate(range(f0, f1 + 1)):
            for pb in sk.pose.bones:
                pb.rotation_mode = 'QUATERNION'
                pb.matrix_basis = frames[i][pb.name]
                pb.keyframe_insert("location", frame=f)
                pb.keyframe_insert("rotation_quaternion", frame=f)
                pb.keyframe_insert("scale", frame=f)
        for m in act.pose_markers:
            nm = new.pose_markers.new(m.name)
            nm.frame = m.frame
        for k in ("mr_meta", "mr_clip"):
            if k in act:
                new[k] = act[k]
        sk.animation_data.action = prev
        self.report({'INFO'}, f"baked {name} ({f1 - f0 + 1} frames)")
        return {'FINISHED'}


class MR_PT_panel(bpy.types.Panel):
    bl_label = "MorphRig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "MorphRig"

    def draw(self, context):
        L = self.layout
        L.operator("morphrig.reset_pose", icon='ARMATURE_DATA')
        for limb in ("arm_l", "arm_r", "leg_l", "leg_r"):
            row = L.row(align=True)
            row.label(text=limb)
            op = row.operator("morphrig.snap", text="FK = pose")
            op.limb, op.to_ik = limb, False
            op = row.operator("morphrig.snap", text="IK = pose")
            op.limb, op.to_ik = limb, True
        L.operator("morphrig.bake", icon='ACTION')
        r = rig()
        if r and "c_face" in r.pose.bones:
            L.label(text="Face: select c_face, edit custom props")


CLASSES = (MR_OT_reset_pose, MR_OT_snap, MR_OT_bake, MR_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
