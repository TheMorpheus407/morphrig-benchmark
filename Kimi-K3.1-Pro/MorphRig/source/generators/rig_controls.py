"""Run this text in Blender to register the Operative animator panel.
The same source is embedded in Operative.blend as START_HERE_Rig_Controls.py.
"""
import bpy
import math
from mathutils import Vector

FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def control_rig():
    return bpy.data.objects.get("Operative_CTRL")


class MORPHRIG_OT_reset_pose(bpy.types.Operator):
    bl_idname = "operative.reset_pose"
    bl_label = "Reset Operative Pose"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = control_rig()
        if not rig:
            return {'CANCELLED'}
        rig.animation_data.action = None
        deform = bpy.data.objects.get("Operative_DEF")
        if deform and deform.animation_data:
            deform.animation_data.action = None
        face = bpy.data.objects.get("Operative_Face")
        if face and face.data.shape_keys and face.data.shape_keys.animation_data:
            face.data.shape_keys.animation_data.action = None
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        rig.scale = (1, 1, 1)
        for s in ("L", "R"):
            rig[f"ik_arm_{s}"] = 0.0
            rig[f"ik_leg_{s}"] = 0.0
            rig[f"foot_roll_{s}"] = 0.0
            hand = rig.pose.bones[f"hand.{s}"]
            for finger in FINGERS:
                hand[f"curl_{finger}"] = .12
            hand["spread"] = 0.0
        face = bpy.data.objects.get("Operative_Face")
        if face and face.data.shape_keys:
            for key in face.data.shape_keys.key_blocks:
                key.value = 0.0
        context.view_layer.update()
        return {'FINISHED'}


class MORPHRIG_OT_match_ik(bpy.types.Operator):
    bl_idname = "operative.match_ik"
    bl_label = "Match FK to IK"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = control_rig()
        context.view_layer.update()
        for s in ("L", "R"):
            for kind, end in (("arm", "hand"), ("leg", "foot")):
                target = rig.pose.bones[f"CTRL_{end}.{s}"]
                source = rig.pose.bones[f"{end}.{s}"]
                target.matrix = source.matrix
                joint = rig.pose.bones["forearm." + s if kind == "arm" else "shin." + s]
                sign = 1 if s == "L" else -1
                offset = Vector((sign * .18, .12, .02)) if kind == "arm" else Vector((0, -.35, .02))
                pole = rig.pose.bones["CTRL_elbow." + s if kind == "arm" else "CTRL_knee." + s]
                pole.matrix.translation = joint.tail + offset
            rig[f"ik_{kind}_{s}"] = 1.0
        context.view_layer.update()
        return {'FINISHED'}


class MORPHRIG_OT_match_fk(bpy.types.Operator):
    bl_idname = "operative.match_fk"
    bl_label = "Match IK to FK"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = control_rig()
        context.view_layer.update()
        matrices = {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
        for s in ("L", "R"):
            for kind, chain in (("arm", ("upperarm", "forearm", "hand")), ("leg", ("thigh", "shin", "foot"))):
                rig[f"ik_{kind}_{s}"] = 0.0
                context.view_layer.update()
                for name in chain:
                    rig.pose.bones[f"{name}.{s}"].matrix = matrices[f"{name}.{s}"]
                    context.view_layer.update()
        return {'FINISHED'}


class MORPHRIG_OT_fingers(bpy.types.Operator):
    bl_idname = "operative.apply_fingers"
    bl_label = "Apply Curl / Spread"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = control_rig()
        for s in ("L", "R"):
            hand = rig.pose.bones[f"hand.{s}"]
            for finger_index, finger in enumerate(FINGERS):
                curl = hand[f"curl_{finger}"]
                for joint in range(3):
                    bone = rig.pose.bones[f"{finger}_{joint + 1:02d}.{s}"]
                    bone.rotation_mode = 'XYZ'
                    bone.rotation_euler.x = math.radians((62, 74, 55)[joint] * curl)
                    if finger != "thumb" and joint == 0:
                        bone.rotation_euler.z = math.radians((finger_index - 2) * 6 * hand["spread"])
        context.view_layer.update()
        return {'FINISHED'}


class MORPHRIG_OT_foot_roll(bpy.types.Operator):
    bl_idname = "operative.apply_foot_roll"
    bl_label = "Apply Heel / Toe Roll"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from mathutils import Matrix
        rig = control_rig()
        if any(rig[f"ik_leg_{s}"] < .5 for s in ("L", "R")):
            bpy.ops.operative.match_ik()
        context.view_layer.update()
        for s in ("L", "R"):
            foot = rig.pose.bones[f"CTRL_foot.{s}"]
            degrees = rig[f"foot_roll_{s}"]
            pivot_name = f"CTRL_toe_pivot.{s}" if degrees >= 0 else f"CTRL_heel.{s}"
            pivot = rig.pose.bones[pivot_name].head
            matrix = foot.matrix.copy()
            foot.matrix = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(degrees), 4, 'X') @ Matrix.Translation(-pivot) @ matrix
        context.view_layer.update()
        return {'FINISHED'}


class MORPHRIG_OT_bake_range(bpy.types.Operator):
    bl_idname = "operative.bake_range"
    bl_label = "Bake Current Range"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = context.scene.get("operative_clip", "idle_relaxed")
        ctrl = control_rig()
        deform = bpy.data.objects["Operative_DEF"]
        action = bpy.data.actions.get(clip) or bpy.data.actions.new(clip)
        action.use_fake_user = True
        deform.animation_data_create()
        deform.animation_data.action = action
        influences = {bone.name: [c.influence for c in bone.constraints] for bone in deform.pose.bones}
        for bone in deform.pose.bones:
            for constraint in bone.constraints:
                constraint.influence = 0.0
        for frame in range(context.scene.frame_start, context.scene.frame_end + 1):
            context.scene.frame_set(frame)
            context.view_layer.update()
            matrices = {bone.name: bone.matrix.copy() for bone in ctrl.pose.bones}
            for bone in deform.data.bones:
                relative = matrices[bone.parent.name].inverted() @ matrices[bone.name] if bone.parent else matrices[bone.name]
                rest = bone.parent.matrix_local.inverted() @ bone.matrix_local if bone.parent else bone.matrix_local
                deform.pose.bones[bone.name].matrix_basis = rest.inverted() @ relative
                deform.pose.bones[bone.name].keyframe_insert("location", frame=frame, group=bone.name)
                deform.pose.bones[bone.name].keyframe_insert("rotation_quaternion", frame=frame, group=bone.name)
                deform.pose.bones[bone.name].keyframe_insert("scale", frame=frame, group=bone.name)
        for bone in deform.pose.bones:
            for constraint, influence in zip(bone.constraints, influences[bone.name]):
                constraint.influence = influence
        action["rebaked_from"] = "Evaluated Operative_CTRL range; editable source action retained"
        self.report({'INFO'}, f"Baked {clip}: {context.scene.frame_start}–{context.scene.frame_end}; save the .blend to retain changes")
        return {'FINISHED'}


class MORPHRIG_OT_select_clip(bpy.types.Operator):
    bl_idname = "operative.select_clip"
    bl_label = "Select / Play Clip"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import json
        clip = context.scene.get("operative_clip", "idle_relaxed")
        source = bpy.data.actions.get("SOURCE_" + clip)
        baked = bpy.data.actions.get(clip)
        facial = bpy.data.actions.get(clip + "_FACE")
        if not source or not baked or not facial:
            self.report({'ERROR'}, "Required source, baked and face actions are missing")
            return {'CANCELLED'}
        rig = control_rig()
        rig.animation_data.action = source
        deform = bpy.data.objects["Operative_DEF"]
        deform.animation_data.action = baked
        for bone in deform.pose.bones:
            for constraint in bone.constraints:
                constraint.influence = 1.0
        bpy.data.objects["Operative_Face"].data.shape_keys.animation_data.action = facial
        context.scene.timeline_markers.clear()
        for event in json.loads(baked["event_markers"]):
            context.scene.timeline_markers.new(event["name"], frame=event["frame"])
        context.scene.frame_start = int(baked.frame_range[0])
        context.scene.frame_end = int(baked.frame_range[1])
        context.scene.frame_set(context.scene.frame_start)
        return {'FINISHED'}


class MORPHRIG_OT_expression(bpy.types.Operator):
    bl_idname = "operative.expression"
    bl_label = "Expression Preset"
    preset: bpy.props.StringProperty(default="neutral")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        face = bpy.data.objects.get("Operative_Face")
        if not face or not face.data.shape_keys:
            return {'CANCELLED'}
        for key in face.data.shape_keys.key_blocks:
            key.value = 0.0
        presets = {
            "joy": {"Smile.L": .85, "Smile.R": .85, "Cheek.L": .55, "Cheek.R": .55, "BrowRaise.L": .16, "BrowRaise.R": .16, "Squint.L": .20, "Squint.R": .20},
            "anger": {"BrowLower.L": .90, "BrowLower.R": .90, "Squint.L": .45, "Squint.R": .45, "Frown.L": .65, "Frown.R": .65, "MouthWidth": .16},
            "concern": {"BrowRaise.L": .32, "BrowRaise.R": .42, "BrowLower.L": .20, "BrowLower.R": .08, "Frown.L": .65, "Frown.R": .45},
            "surprise": {"BrowRaise.L": 1, "BrowRaise.R": 1, "JawOpen": .55, "Viseme_OO": .4},
            "pain": {"Blink.L": .62, "Squint.R": .85, "BrowLower.L": .55, "BrowLower.R": .65, "Frown.L": .6, "Frown.R": .7, "JawOpen": .25},
            "focus": {"Squint.L": .32, "Squint.R": .24, "BrowLower.L": .18, "BrowLower.R": .26, "LipClosed": .85},
        }
        for key, value in presets.get(self.preset, {}).items():
            face.data.shape_keys.key_blocks[key].value = value
        return {'FINISHED'}


class MORPHRIG_PT_controls(bpy.types.Panel):
    bl_label = "MorphRig / Operative"
    bl_idname = "MORPHRIG_PT_controls"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "MorphRig"

    def draw(self, context):
        layout = self.layout
        rig = control_rig()
        if not rig:
            layout.label(text="Open Operative.blend")
            return
        layout.operator("operative.reset_pose", icon='ARMATURE_DATA')
        layout.prop(context.scene, '["operative_clip"]', text="Clip ID")
        layout.operator("operative.select_clip")
        layout.operator("operative.bake_range")
        layout.prop(rig, '["Team"]', text="Team (0 cyan / 1 amber)")
        for s in ("L", "R"):
            box = layout.box(); box.label(text=f"{s} arm / leg")
            for kind in ("arm", "leg"):
                box.prop(rig, f'["ik_{kind}_{s}"]', text=f"{kind} IK")
            box.prop(rig, f'["foot_roll_{s}"]', text="Foot roll")
            hand = rig.pose.bones[f"hand.{s}"]
            for finger in FINGERS:
                box.prop(hand, f'["curl_{finger}"]', text=finger)
            box.prop(hand, '["spread"]', text="Spread")
        row = layout.row(align=True)
        row.operator("operative.match_ik"); row.operator("operative.match_fk")
        layout.operator("operative.apply_fingers")
        layout.operator("operative.apply_foot_roll")
        layout.prop(rig, '["look_at_weight"]', text="Look at")
        box = layout.box(); box.label(text="Facial presets")
        for preset in ("neutral", "joy", "anger", "concern", "surprise", "pain", "focus"):
            op = box.operator("operative.expression", text=preset.title()); op.preset = preset
        face = bpy.data.objects.get("Operative_Face")
        if face and face.data.shape_keys:
            box = layout.box(); box.label(text="Independent face / visemes")
            for key in face.data.shape_keys.key_blocks:
                if key.name != "Basis": box.prop(key, "value", text=key.name, slider=True)
        layout.label(text="Source: SOURCE_<clip>; export: <clip>")
        layout.label(text="30 fps; meters; forward -Y; root at ground")


CLASSES = (MORPHRIG_OT_reset_pose, MORPHRIG_OT_match_ik, MORPHRIG_OT_match_fk, MORPHRIG_OT_fingers, MORPHRIG_OT_foot_roll, MORPHRIG_OT_select_clip, MORPHRIG_OT_bake_range, MORPHRIG_OT_expression, MORPHRIG_PT_controls)


def register():
    for cls in CLASSES:
        existing = getattr(bpy.types, cls.__name__, None)
        if existing:
            bpy.utils.unregister_class(existing)
        bpy.utils.register_class(cls)


if __name__ == "__main__":
    register()
