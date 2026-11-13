#!/usr/bin/env python3
"""
Procedural Deformation Skeleton, Animator Control Rig, Part-Isolated Skinning,
Joint Corrective Shape Keys, and Hybrid Facial Rig Builder (Blender 5.1+).

Satisfies SPEC.md Sections 6 & 7:
  - Single-root ('root') connected/parented deformation skeleton (92 DEF bones), independent of 'pelvis'
  - Full animator control rig in organized Bone Collections with custom wire shapes:
    * Arms & Legs IK/FK with pose-matching operator, pole vectors, reverse-foot roll, heel/toe pivots
    * Hand master curl/spread + individual 30-phalanx finger controls
    * Torso, neck, head, stereo eye + head Look-At target, global scale, one-click pose reset
    * Controllable secondary motion chains (neural cable_01..03, hip strap_01..03)
    * Prop controls & constraint handoffs (emitter_bone_r, retractable blade_r, reload cell_bone, deploy beacon_bone)
  - Part-isolated analytical skinning (<= 8 bone influences/vertex, zero finger or lip cross-bleeding)
  - Hybrid facial rig: facial bones + bilateral/asymmetric shape keys + 13 visemes + 6 expression presets + joint correctives
"""

import json
import math
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler

ROOT_DIR = Path(__file__).resolve().parents[2]


EMBEDDED_UI_SCRIPT = '''import bpy
from mathutils import Matrix

class MORPHRIG_OT_reset_pose(bpy.types.Operator):
    bl_idname = "morphrig.reset_pose"
    bl_label = "Reset Operative Pose & Face"
    bl_description = "Reset all animator controls, custom rig properties, and facial shape keys to neutral rest pose"

    def execute(self, context):
        arm = bpy.data.objects.get("Armature")
        if arm and arm.pose:
            for pb in arm.pose.bones:
                pb.location = (0.0, 0.0, 0.0)
                pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                pb.rotation_euler = (0.0, 0.0, 0.0)
                pb.scale = (1.0, 1.0, 1.0)
            defaults = {
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
            ctrl_m = arm.pose.bones.get("CTRL_Master")
            if ctrl_m:
                for k, v in defaults.items():
                    if k in ctrl_m:
                        ctrl_m[k] = v
            for S in ("L", "R"):
                cf = arm.pose.bones.get(f"CTRL_Fingers_{S}")
                if cf:
                    cf["curl"] = 0.0
                    cf["spread"] = 0.0
        lod0 = bpy.data.objects.get("Operative_LOD0")
        if lod0 and lod0.data.shape_keys:
            for kb in lod0.data.shape_keys.key_blocks:
                if kb.name != "Basis":
                    kb.value = 0.0
        context.view_layer.update()
        return {"FINISHED"}


class MORPHRIG_OT_snap_ik_fk(bpy.types.Operator):
    bl_idname = "morphrig.snap_ik_fk"
    bl_label = "Snap IK <-> FK"
    bl_description = "Pose-match IK controls to FK chain or FK chain to evaluated IK deformation chain"

    limb: bpy.props.StringProperty(default="arm_l")
    to_ik: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        arm = bpy.data.objects.get("Armature")
        if not arm:
            return {"CANCELLED"}
        pb = arm.pose.bones
        ctrl_m = pb.get("CTRL_Master")
        side = self.limb[-1]  # 'l' or 'r'
        S = side.upper()
        if self.limb.startswith("arm"):
            prop_name = f"ik_fk_arm_{side}"
            def_u, def_l, def_h = pb[f"upperarm_{side}"], pb[f"lowerarm_{side}"], pb[f"hand_{side}"]
            fk_u, fk_l, fk_h = pb[f"CTRL_FK_UpperArm_{S}"], pb[f"CTRL_FK_LowerArm_{S}"], pb[f"CTRL_FK_Hand_{S}"]
            ik_c, pole_c = pb[f"CTRL_IK_Hand_{S}"], pb[f"CTRL_Pole_Arm_{S}"]
            if self.to_ik:
                ik_c.matrix = def_h.matrix.copy()
                context.view_layer.update()
                elbow_pos = def_l.head.copy()
                pole_c.matrix = Matrix.Translation(elbow_pos + def_l.z_axis * 0.35)
                ctrl_m[prop_name] = 1.0
            else:
                fk_u.matrix = def_u.matrix.copy()
                context.view_layer.update()
                fk_l.matrix = def_l.matrix.copy()
                context.view_layer.update()
                fk_h.matrix = def_h.matrix.copy()
                ctrl_m[prop_name] = 0.0
        else:
            prop_name = f"ik_fk_leg_{side}"
            def_u, def_l, def_f = pb[f"thigh_{side}"], pb[f"calf_{side}"], pb[f"foot_{side}"]
            fk_u, fk_l, fk_f = pb[f"CTRL_FK_Thigh_{S}"], pb[f"CTRL_FK_Calf_{S}"], pb[f"CTRL_FK_Foot_{S}"]
            ik_c, pole_c = pb[f"CTRL_IK_Foot_{S}"], pb[f"CTRL_Pole_Leg_{S}"]
            if self.to_ik:
                ik_c.location = (def_f.head.x - ik_c.bone.head_local.x, def_f.head.y - ik_c.bone.head_local.y, max(0.0, def_f.head.z - 0.095))
                context.view_layer.update()
                pole_c.matrix = Matrix.Translation(def_l.head + Vector((0.0, -0.45, 0.0)))
                ctrl_m[prop_name] = 1.0
            else:
                fk_u.matrix = def_u.matrix.copy()
                context.view_layer.update()
                fk_l.matrix = def_l.matrix.copy()
                context.view_layer.update()
                fk_f.matrix = def_f.matrix.copy()
                ctrl_m[prop_name] = 0.0
        context.view_layer.update()
        return {"FINISHED"}


class MORPHRIG_PT_panel(bpy.types.Panel):
    bl_label = "MorphRig Operative Controls"
    bl_idname = "MORPHRIG_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MorphRig"

    def draw(self, context):
        layout = self.layout
        layout.operator("morphrig.reset_pose", icon="ARMATURE_DATA")
        arm = bpy.data.objects.get("Armature")
        if arm and arm.pose and "CTRL_Master" in arm.pose.bones:
            cm = arm.pose.bones["CTRL_Master"]
            box = layout.box()
            box.label(text="IK / FK Blending & Pose Snap")
            for limb, lbl in [("arm_l", "Left Arm"), ("arm_r", "Right Arm"), ("leg_l", "Left Leg"), ("leg_r", "Right Leg")]:
                pname = f"ik_fk_{limb}"
                if pname in cm:
                    box.prop(cm, f'["{pname}"]', text=f"{lbl} IK")
                    row = box.row(align=True)
                    op1 = row.operator("morphrig.snap_ik_fk", text=f"{lbl}->IK")
                    op1.limb, op1.to_ik = limb, True
                    op2 = row.operator("morphrig.snap_ik_fk", text=f"{lbl}->FK")
                    op2.limb, op2.to_ik = limb, False
            fbox = layout.box()
            fbox.label(text="Hands, Gaze & Prop Handoffs")
            for S in ("L", "R"):
                cf = arm.pose.bones.get(f"CTRL_Fingers_{S}")
                if cf:
                    row = fbox.row(align=True)
                    row.prop(cf, '["curl"]', text=f"Curl {S}")
                    row.prop(cf, '["spread"]', text=f"Spread {S}")
            for p_key, p_lbl in [("head_look_at", "Head LookAt"), ("eye_look_at", "Eye LookAt"), ("cell_in_hand_l", "Cell->Hand L"), ("beacon_in_hand_l", "Beacon->Hand L"), ("beacon_planted", "Beacon->World")]:
                if p_key in cm:
                    fbox.prop(cm, f'["{p_key}"]', text=p_lbl)


classes = (MORPHRIG_OT_reset_pose, MORPHRIG_OT_snap_ik_fk, MORPHRIG_PT_panel)

def register():
    for c in classes:
        try:
            bpy.utils.register_class(c)
        except Exception:
            pass

if __name__ == "__main__":
    register()
'''


def create_widget_shapes() -> dict[str, bpy.types.Object]:
    """Creates clean wireframe custom shape objects hidden in a WGT_Shapes collection."""
    col = bpy.data.collections.get("WGT_Shapes")
    if not col:
        col = bpy.data.collections.new("WGT_Shapes")
        bpy.context.scene.collection.children.link(col)
        col.hide_viewport = True
        col.hide_render = True

    widgets = {}

    def make_wire(name: str, verts: list[tuple[float, float, float]], edges: list[tuple[int, int]]):
        m = bpy.data.meshes.new(name + "_Mesh")
        m.from_pydata(verts, edges, [])
        o = bpy.data.objects.new(name, m)
        col.objects.link(o)
        widgets[name] = o

    # Circle in XY plane
    c_verts = [(math.cos(2 * math.pi * i / 24), math.sin(2 * math.pi * i / 24), 0.0) for i in range(24)]
    c_edges = [(i, (i + 1) % 24) for i in range(24)]
    make_wire("WGT_Circle", c_verts, c_edges)

    # Box cube
    b_verts = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),  (0.5, -0.5, 0.5),  (0.5, 0.5, 0.5),  (-0.5, 0.5, 0.5),
    ]
    b_edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    make_wire("WGT_Box", b_verts, b_edges)

    # Diamond octahedron (for poles & look-at)
    d_verts = [(0,0,0.6),(0,0,-0.6),(0.6,0,0),(-0.6,0,0),(0,0.6,0),(0,-0.6,0)]
    d_edges = [(0,2),(0,3),(0,4),(0,5),(1,2),(1,3),(1,4),(1,5),(2,4),(4,3),(3,5),(5,2)]
    make_wire("WGT_Diamond", d_verts, d_edges)

    # Foot Ground Platform
    f_verts = [(-0.55, 0.75, 0.0), (0.55, 0.75, 0.0), (0.60, -1.85, 0.0), (-0.60, -1.85, 0.0)]
    f_edges = [(0,1),(1,2),(2,3),(3,0)]
    make_wire("WGT_Foot", f_verts, f_edges)

    return widgets


def get_finger_defs(side_sign: float) -> list[tuple[str, Vector, Vector, float]]:
    side_s = "l" if side_sign > 0 else "r"
    return [
        (f"thumb_{{0}}_{side_s}",  Vector((side_sign * 0.730, -0.032, 1.454)), Vector((side_sign * 0.82, -0.52, -0.24)).normalized(), 0.066),
        (f"index_{{0}}_{side_s}",  Vector((side_sign * 0.782, -0.030, 1.463)), Vector((side_sign * 0.995, -0.08, -0.04)).normalized(), 0.082),
        (f"middle_{{0}}_{side_s}", Vector((side_sign * 0.785, -0.009, 1.464)), Vector((side_sign * 0.999, -0.02, -0.03)).normalized(), 0.090),
        (f"ring_{{0}}_{side_s}",   Vector((side_sign * 0.782, +0.012, 1.463)), Vector((side_sign * 0.997, +0.04, -0.04)).normalized(), 0.084),
        (f"pinky_{{0}}_{side_s}",  Vector((side_sign * 0.776, +0.032, 1.461)), Vector((side_sign * 0.990, +0.11, -0.05)).normalized(), 0.068),
    ]


def build_armature() -> bpy.types.Object:
    """Builds the unified Armature with 92 DEF bones (single root 'root') + full CTRL/MCH animator rig."""
    arm_data = bpy.data.armatures.new("Operative_Armature")
    arm_obj = bpy.data.objects.new("Armature", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)

    # Create organized Blender 5.1 Bone Collections
    col_names = [
        "DEF_Skeleton",
        "CTRL_Master",
        "CTRL_Torso",
        "CTRL_Arms",
        "CTRL_Legs",
        "CTRL_Fingers",
        "CTRL_Face",
        "CTRL_Secondary",
        "CTRL_Props",
        "MCH_Mechanism",
    ]
    bcols = {cname: arm_data.collections.new(cname) for cname in col_names}
    bcols["DEF_Skeleton"].is_visible = False
    bcols["MCH_Mechanism"].is_visible = False

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def add_bone(name: str, head: Vector, tail: Vector, parent_name: str | None, deform: bool, col_key: str, roll: float = 0.0, connect: bool = False):
        b = eb.new(name)
        b.head = head
        b.tail = tail
        b.roll = roll
        b.use_deform = deform
        if parent_name and parent_name in eb:
            b.parent = eb[parent_name]
            b.use_connect = connect
        bcols[col_key].assign(b)
        return b

    # =========================================================================
    # 1. DEFORMATION HIERARCHY (Strictly single root 'root', all parents DEF!)
    # =========================================================================
    add_bone("root",     Vector((0.0, 0.0, 0.0)),     Vector((0.0, -0.18, 0.0)),   None,       True, "DEF_Skeleton")
    add_bone("pelvis",   Vector((0.0, 0.005, 0.960)), Vector((0.0, 0.010, 1.060)), "root",     True, "DEF_Skeleton")
    add_bone("spine_01", Vector((0.0, 0.010, 1.060)), Vector((0.0, 0.014, 1.185)), "pelvis",   True, "DEF_Skeleton", connect=True)
    add_bone("spine_02", Vector((0.0, 0.014, 1.185)), Vector((0.0, 0.010, 1.320)), "spine_01", True, "DEF_Skeleton", connect=True)
    add_bone("spine_03", Vector((0.0, 0.010, 1.320)), Vector((0.0, 0.006, 1.465)), "spine_02", True, "DEF_Skeleton", connect=True)
    add_bone("neck_01",  Vector((0.0, 0.006, 1.465)), Vector((0.0, 0.000, 1.555)), "spine_03", True, "DEF_Skeleton", connect=True)
    add_bone("head",     Vector((0.0, 0.000, 1.555)), Vector((0.0, 0.000, 1.785)), "neck_01",  True, "DEF_Skeleton", connect=True)

    # Facial Deformation Bones (19 bones under head)
    add_bone("jaw",       Vector((0.0, -0.028, 1.612)), Vector((0.0, -0.094, 1.568)), "head",      True, "DEF_Skeleton")
    add_bone("tongue_01", Vector((0.0, -0.040, 1.596)), Vector((0.0, -0.065, 1.598)), "jaw",       True, "DEF_Skeleton")
    add_bone("tongue_02", Vector((0.0, -0.065, 1.598)), Vector((0.0, -0.087, 1.599)), "tongue_01", True, "DEF_Skeleton", connect=True)
    add_bone("lip_upper_mid", Vector((0.0, -0.098, 1.614)), Vector((0.0, -0.112, 1.614)), "head", True, "DEF_Skeleton")
    add_bone("lip_lower_mid", Vector((0.0, -0.098, 1.601)), Vector((0.0, -0.112, 1.601)), "jaw",  True, "DEF_Skeleton")

    for side_sign, sx in [(+1.0, "l"), (-1.0, "r")]:
        ec = Vector((side_sign * 0.032, -0.074, 1.675))
        add_bone(f"eye_{sx}",          ec, ec + Vector((0.0, -0.022, 0.0)),   "head", True, "DEF_Skeleton")
        add_bone(f"eyelid_upper_{sx}", ec, ec + Vector((0.0, -0.016, +0.007)), "head", True, "DEF_Skeleton")
        add_bone(f"eyelid_lower_{sx}", ec, ec + Vector((0.0, -0.016, -0.007)), "head", True, "DEF_Skeleton")
        add_bone(f"brow_inner_{sx}",   Vector((side_sign * 0.015, -0.092, 1.696)), Vector((side_sign * 0.015, -0.106, 1.696)), "head", True, "DEF_Skeleton")
        add_bone(f"brow_outer_{sx}",   Vector((side_sign * 0.044, -0.082, 1.696)), Vector((side_sign * 0.044, -0.096, 1.696)), "head", True, "DEF_Skeleton")
        add_bone(f"cheek_{sx}",        Vector((side_sign * 0.042, -0.084, 1.638)), Vector((side_sign * 0.042, -0.098, 1.638)), "head", True, "DEF_Skeleton")
        add_bone(f"lip_corner_{sx}",   Vector((side_sign * 0.024, -0.089, 1.608)), Vector((side_sign * 0.024, -0.102, 1.608)), "head", True, "DEF_Skeleton")

    # Secondary Motion Chains: Neural Cable (under head) + Hip Strap (under pelvis)
    add_bone("cable_01", Vector((0.0, 0.088, 1.665)), Vector((0.0, 0.130, 1.585)), "head",     True, "DEF_Skeleton")
    add_bone("cable_02", Vector((0.0, 0.130, 1.585)), Vector((0.0, 0.148, 1.495)), "cable_01", True, "DEF_Skeleton", connect=True)
    add_bone("cable_03", Vector((0.0, 0.148, 1.495)), Vector((0.0, 0.155, 1.405)), "cable_02", True, "DEF_Skeleton", connect=True)

    add_bone("strap_01", Vector((0.155, 0.045, 0.945)), Vector((0.168, 0.052, 0.855)), "pelvis",   True, "DEF_Skeleton")
    add_bone("strap_02", Vector((0.168, 0.052, 0.855)), Vector((0.174, 0.056, 0.765)), "strap_01", True, "DEF_Skeleton", connect=True)
    add_bone("strap_03", Vector((0.174, 0.056, 0.765)), Vector((0.176, 0.058, 0.680)), "strap_02", True, "DEF_Skeleton", connect=True)

    # Arms, Twists & 30 Finger Phalanges
    for side_sign, sx in [(+1.0, "l"), (-1.0, "r")]:
        c_head = Vector((side_sign * 0.035, 0.004, 1.450))
        u_head = Vector((side_sign * 0.168, 0.010, 1.472))
        l_head = Vector((side_sign * 0.445, 0.028, 1.468))
        h_head = Vector((side_sign * 0.705, 0.005, 1.464))
        h_tail = Vector((side_sign * 0.785, 0.002, 1.462))

        add_bone(f"clavicle_{sx}",       c_head, u_head, "spine_03",        True, "DEF_Skeleton")
        add_bone(f"upperarm_{sx}",       u_head, l_head, f"clavicle_{sx}",  True, "DEF_Skeleton", connect=True)
        add_bone(f"upperarm_twist_{sx}", u_head.lerp(l_head, 0.5), l_head, f"upperarm_{sx}", True, "DEF_Skeleton")
        add_bone(f"lowerarm_{sx}",       l_head, h_head, f"upperarm_{sx}",  True, "DEF_Skeleton", connect=True)
        add_bone(f"lowerarm_twist_{sx}", l_head.lerp(h_head, 0.5), h_head, f"lowerarm_{sx}", True, "DEF_Skeleton")
        add_bone(f"hand_{sx}",           h_head, h_tail, f"lowerarm_{sx}",  True, "DEF_Skeleton", connect=True)

        # 5 Fingers x 3 Phalanges (joint splits at t = 0.00 -> 0.45 -> 0.74 -> 1.00)
        for f_tmpl, f_base, f_dir, f_len in get_finger_defs(side_sign):
            p0 = f_base
            p1 = f_base + f_dir * (f_len * 0.45)
            p2 = f_base + f_dir * (f_len * 0.74)
            p3 = f_base + f_dir * f_len
            b1 = f_tmpl.format("01")
            b2 = f_tmpl.format("02")
            b3 = f_tmpl.format("03")
            add_bone(b1, p0, p1, f"hand_{sx}", True, "DEF_Skeleton")
            add_bone(b2, p1, p2, b1,           True, "DEF_Skeleton", connect=True)
            add_bone(b3, p2, p3, b2,           True, "DEF_Skeleton", connect=True)

    # Equipped Props & Weapon Anchor/Socket DEF Bones
    add_bone("emitter_bone_r", Vector((-0.620, -0.028, 1.502)), Vector((-0.735, -0.028, 1.502)), "lowerarm_twist_r", True, "DEF_Skeleton")
    add_bone("emitter_muzzle", Vector((-0.748, -0.028, 1.502)), Vector((-0.790, -0.028, 1.502)), "emitter_bone_r",   True, "DEF_Skeleton")
    add_bone("blade_r",        Vector((-0.480,  0.048, 1.468)), Vector((-0.755,  0.048, 1.468)), "lowerarm_r",       True, "DEF_Skeleton")
    add_bone("blade_tip",      Vector((-0.755,  0.048, 1.468)), Vector((-0.800,  0.048, 1.468)), "blade_r",          True, "DEF_Skeleton", connect=True)
    # cell_bone and beacon_bone sit under 'root' in DEF hierarchy so constraint switching never alters hierarchy!
    add_bone("cell_bone",      Vector((-0.655, -0.052, 1.502)), Vector((-0.618, -0.052, 1.502)), "root",             True, "DEF_Skeleton")
    add_bone("beacon_bone",    Vector((-0.105,  0.128, 0.935)), Vector((-0.105,  0.128, 0.985)), "root",             True, "DEF_Skeleton")

    # Legs, Twists, Feet & Balls/Toes
    for side_sign, sx in [(+1.0, "l"), (-1.0, "r")]:
        th_h = Vector((side_sign * 0.095,  0.005, 0.945))
        ca_h = Vector((side_sign * 0.098, -0.015, 0.515))
        ft_h = Vector((side_sign * 0.098,  0.020, 0.095))
        bl_h = Vector((side_sign * 0.098, -0.105, 0.028))
        bl_t = Vector((side_sign * 0.098, -0.195, 0.012))

        add_bone(f"thigh_{sx}",       th_h, ca_h, "pelvis",        True, "DEF_Skeleton")
        add_bone(f"thigh_twist_{sx}", th_h.lerp(ca_h, 0.5), ca_h, f"thigh_{sx}", True, "DEF_Skeleton")
        add_bone(f"calf_{sx}",        ca_h, ft_h, f"thigh_{sx}",   True, "DEF_Skeleton", connect=True)
        add_bone(f"calf_twist_{sx}",  ca_h.lerp(ft_h, 0.5), ft_h, f"calf_{sx}",  True, "DEF_Skeleton")
        add_bone(f"foot_{sx}",        ft_h, bl_h, f"calf_{sx}",    True, "DEF_Skeleton", connect=True)
        add_bone(f"ball_{sx}",        bl_h, bl_t, f"foot_{sx}",    True, "DEF_Skeleton", connect=True)

    # =========================================================================
    # 2. ANIMATOR CONTROL & MECHANISM RIG (use_deform = False)
    # =========================================================================
    add_bone("CTRL_Master",      Vector((0.0, 0.0, 0.0)),       Vector((0.0, -0.35, 0.0)),       None,            False, "CTRL_Master")
    add_bone("CTRL_Root",        Vector((0.0, 0.0, 0.0)),       Vector((0.0, -0.22, 0.0)),       "CTRL_Master",   False, "CTRL_Master")
    add_bone("CTRL_Pelvis",      Vector((0.0, 0.005, 0.960)),   Vector((0.0, 0.010, 1.060)),     "CTRL_Master",   False, "CTRL_Torso")
    add_bone("CTRL_Spine_01",    Vector((0.0, 0.010, 1.060)),   Vector((0.0, 0.014, 1.185)),     "CTRL_Pelvis",   False, "CTRL_Torso")
    add_bone("CTRL_Spine_02",    Vector((0.0, 0.014, 1.185)),   Vector((0.0, 0.010, 1.320)),     "CTRL_Spine_01", False, "CTRL_Torso")
    add_bone("CTRL_Spine_03",    Vector((0.0, 0.010, 1.320)),   Vector((0.0, 0.006, 1.465)),     "CTRL_Spine_02", False, "CTRL_Torso")
    add_bone("CTRL_Neck",        Vector((0.0, 0.006, 1.465)),   Vector((0.0, 0.000, 1.555)),     "CTRL_Spine_03", False, "CTRL_Torso")
    add_bone("CTRL_Head",        Vector((0.0, 0.000, 1.555)),   Vector((0.0, 0.000, 1.785)),     "CTRL_Neck",     False, "CTRL_Torso")

    # Look-At + Facial Bone Controls
    add_bone("CTRL_LookAt",      Vector((0.0, -0.80, 1.675)),   Vector((0.0, -0.88, 1.675)),     "CTRL_Master",   False, "CTRL_Face")
    add_bone("CTRL_Eye_L",       Vector((0.032, -0.80, 1.675)), Vector((0.032, -0.85, 1.675)),   "CTRL_LookAt",   False, "CTRL_Face")
    add_bone("CTRL_Eye_R",       Vector((-0.032, -0.80, 1.675)),Vector((-0.032, -0.85, 1.675)),  "CTRL_LookAt",   False, "CTRL_Face")
    add_bone("CTRL_Jaw",         Vector((0.0, -0.028, 1.612)),  Vector((0.0, -0.094, 1.568)),    "CTRL_Head",     False, "CTRL_Face")

    # Secondary Controls
    add_bone("CTRL_Cable_01", Vector((0.0, 0.088, 1.665)), Vector((0.0, 0.130, 1.585)), "CTRL_Head",     False, "CTRL_Secondary")
    add_bone("CTRL_Cable_02", Vector((0.0, 0.130, 1.585)), Vector((0.0, 0.148, 1.495)), "CTRL_Cable_01", False, "CTRL_Secondary")
    add_bone("CTRL_Cable_03", Vector((0.0, 0.148, 1.495)), Vector((0.0, 0.155, 1.405)), "CTRL_Cable_02", False, "CTRL_Secondary")

    add_bone("CTRL_Strap_01", Vector((0.155, 0.045, 0.945)), Vector((0.168, 0.052, 0.855)), "CTRL_Pelvis",   False, "CTRL_Secondary")
    add_bone("CTRL_Strap_02", Vector((0.168, 0.052, 0.855)), Vector((0.174, 0.056, 0.765)), "CTRL_Strap_01", False, "CTRL_Secondary")
    add_bone("CTRL_Strap_03", Vector((0.174, 0.056, 0.765)), Vector((0.176, 0.058, 0.680)), "CTRL_Strap_02", False, "CTRL_Secondary")

    # Arm FK + IK + MCH Chains
    for side_sign, sx, S in [(+1.0, "l", "L"), (-1.0, "r", "R")]:
        c_h = eb[f"clavicle_{sx}"].head.copy()
        u_h = eb[f"upperarm_{sx}"].head.copy()
        l_h = eb[f"lowerarm_{sx}"].head.copy()
        h_h = eb[f"hand_{sx}"].head.copy()
        h_t = eb[f"hand_{sx}"].tail.copy()

        add_bone(f"CTRL_Clavicle_{S}",    c_h, u_h, "CTRL_Spine_03",       False, "CTRL_Arms")
        add_bone(f"CTRL_FK_UpperArm_{S}", u_h, l_h, f"CTRL_Clavicle_{S}",  False, "CTRL_Arms")
        add_bone(f"CTRL_FK_LowerArm_{S}", l_h, h_h, f"CTRL_FK_UpperArm_{S}", False, "CTRL_Arms")
        add_bone(f"CTRL_FK_Hand_{S}",     h_h, h_t, f"CTRL_FK_LowerArm_{S}", False, "CTRL_Arms")

        add_bone(f"MCH_IK_UpperArm_{S}",  u_h, l_h, f"CTRL_Clavicle_{S}",  False, "MCH_Mechanism")
        add_bone(f"MCH_IK_LowerArm_{S}",  l_h, h_h, f"MCH_IK_UpperArm_{S}",False, "MCH_Mechanism", connect=True)
        add_bone(f"CTRL_IK_Hand_{S}",     h_h, h_t, "CTRL_Master",         False, "CTRL_Arms")
        add_bone(f"CTRL_Pole_Arm_{S}",    l_h + Vector((0.0, 0.45, 0.0)), l_h + Vector((0.0, 0.52, 0.0)), "CTRL_Master", False, "CTRL_Arms")

        # Master Finger Curl/Spread Widget + Driven MCH + Individual Finger Phalanx Controls
        add_bone(f"CTRL_Fingers_{S}", h_h + Vector((0.0, 0.0, 0.05)), h_h + Vector((0.0, 0.0, 0.09)), f"hand_{sx}", False, "CTRL_Fingers")
        for f_tmpl, _, _, _ in get_finger_defs(side_sign):
            for idx_p in ("01", "02", "03"):
                def_n = f_tmpl.format(idx_p)
                mch_n = f"MCH_{def_n}"
                ctrl_n = f"CTRL_{def_n}"
                par_n = f"hand_{sx}" if idx_p == "01" else f"CTRL_{f_tmpl.format('01' if idx_p=='02' else '02')}"
                add_bone(mch_n,  eb[def_n].head.copy(), eb[def_n].tail.copy(), par_n, False, "MCH_Mechanism")
                add_bone(ctrl_n, eb[def_n].head.copy(), eb[def_n].tail.copy(), mch_n, False, "CTRL_Fingers")

    # Leg FK + Reverse-Foot IK + MCH Chains
    for side_sign, sx, S in [(+1.0, "l", "L"), (-1.0, "r", "R")]:
        th_h = eb[f"thigh_{sx}"].head.copy()
        ca_h = eb[f"calf_{sx}"].head.copy()
        ft_h = eb[f"foot_{sx}"].head.copy()
        bl_h = eb[f"ball_{sx}"].head.copy()
        bl_t = eb[f"ball_{sx}"].tail.copy()

        add_bone(f"CTRL_FK_Thigh_{S}", th_h, ca_h, "CTRL_Pelvis",        False, "CTRL_Legs")
        add_bone(f"CTRL_FK_Calf_{S}",  ca_h, ft_h, f"CTRL_FK_Thigh_{S}", False, "CTRL_Legs")
        add_bone(f"CTRL_FK_Foot_{S}",  ft_h, bl_h, f"CTRL_FK_Calf_{S}",  False, "CTRL_Legs")
        add_bone(f"CTRL_FK_Ball_{S}",  bl_h, bl_t, f"CTRL_FK_Foot_{S}",  False, "CTRL_Legs")

        add_bone(f"MCH_IK_Thigh_{S}",  th_h, ca_h, "CTRL_Pelvis",        False, "MCH_Mechanism")
        add_bone(f"MCH_IK_Calf_{S}",   ca_h, ft_h, f"MCH_IK_Thigh_{S}",  False, "MCH_Mechanism", connect=True)

        # Ground-planted IK Foot Control + Reverse Foot Hierarchy (HeelPivot -> ToePivot -> BallRoll -> AnkleIK)
        foot_ground = Vector((side_sign * 0.098, -0.050, 0.000))
        heel_pt = Vector((side_sign * 0.098, +0.075, 0.000))
        toe_pt  = Vector((side_sign * 0.098, -0.202, 0.000))
        add_bone(f"CTRL_IK_Foot_{S}",   foot_ground, foot_ground + Vector((0.0, -0.10, 0.0)), "CTRL_Master", False, "CTRL_Legs")
        add_bone(f"CTRL_HeelPivot_{S}", heel_pt,     heel_pt + Vector((0.0, 0.0, 0.06)),      f"CTRL_IK_Foot_{S}",   False, "CTRL_Legs")
        add_bone(f"CTRL_ToePivot_{S}",  toe_pt,      toe_pt + Vector((0.0, 0.0, 0.06)),       f"CTRL_HeelPivot_{S}", False, "CTRL_Legs")
        add_bone(f"CTRL_FootRoll_{S}",  bl_h,        bl_h + Vector((0.0, 0.0, 0.08)),         f"CTRL_ToePivot_{S}",  False, "CTRL_Legs")
        add_bone(f"MCH_AnkleIK_{S}",    ft_h,        ft_h + Vector((0.0, 0.0, 0.06)),         f"CTRL_FootRoll_{S}",  False, "MCH_Mechanism")
        add_bone(f"MCH_IK_Foot_{S}",    ft_h,        bl_h,                                    f"CTRL_FootRoll_{S}",  False, "MCH_Mechanism")
        add_bone(f"MCH_IK_Ball_{S}",    bl_h,        bl_t,                                    f"CTRL_ToePivot_{S}",  False, "MCH_Mechanism")
        add_bone(f"CTRL_Pole_Leg_{S}",  ca_h + Vector((0.0, -0.52, 0.0)), ca_h + Vector((0.0, -0.58, 0.0)), "CTRL_Master", False, "CTRL_Legs")

    # Prop Controls & Socket Reference Targets
    add_bone("CTRL_Blade_R",      eb["blade_r"].head.copy(),     eb["blade_r"].tail.copy(),     "lowerarm_r",      False, "CTRL_Props")
    add_bone("MCH_Cell_Slot_R",   eb["cell_bone"].head.copy(),   eb["cell_bone"].tail.copy(),   "emitter_bone_r",  False, "MCH_Mechanism")
    add_bone("MCH_Cell_Hand_L",   Vector((0.770, -0.024, 1.448)),Vector((0.770, -0.060, 1.448)),"hand_l",          False, "MCH_Mechanism")
    add_bone("CTRL_Cell_Offset",  eb["cell_bone"].head.copy(),   eb["cell_bone"].tail.copy(),   "MCH_Cell_Slot_R", False, "CTRL_Props")

    add_bone("MCH_Beacon_Dock",   eb["beacon_bone"].head.copy(), eb["beacon_bone"].tail.copy(), "pelvis",          False, "MCH_Mechanism")
    add_bone("MCH_Beacon_Hand_L", Vector((0.768, -0.025, 1.430)),Vector((0.768, -0.025, 1.480)),"hand_l",          False, "MCH_Mechanism")
    add_bone("CTRL_Beacon_World", Vector((0.000, -0.450, 0.000)),Vector((0.000, -0.450, 0.050)),"CTRL_Master",     False, "CTRL_Props")

    bpy.ops.object.mode_set(mode="POSE")
    pb = arm_obj.pose.bones
    widgets = create_widget_shapes()

    # Custom properties on CTRL_Master
    cm = pb["CTRL_Master"]
    cm["ik_fk_arm_l"] = 0.0
    cm["ik_fk_arm_r"] = 0.0
    cm["ik_fk_leg_l"] = 1.0  # Planted IK legs ON by default for animator convenience!
    cm["ik_fk_leg_r"] = 1.0
    cm["head_look_at"] = 0.0
    cm["eye_look_at"] = 1.0
    cm["cell_in_hand_l"] = 0.0
    cm["beacon_in_hand_l"] = 0.0
    cm["beacon_planted"] = 0.0

    def add_copy_xform(pbone, target_bone: str, influence: float = 1.0, prop_driver: str | None = None):
        c = pbone.constraints.new("COPY_TRANSFORMS")
        c.target = arm_obj
        c.subtarget = target_bone
        c.influence = influence
        if prop_driver:
            drv = c.driver_add("influence").driver
            drv.type = "AVERAGE"
            var = drv.variables.new()
            var.name = "val"
            var.targets[0].id = arm_obj
            var.targets[0].data_path = f'pose.bones["CTRL_Master"]["{prop_driver}"]'
        return c

    # Wire Core & Torso DEF -> CTRL
    add_copy_xform(pb["root"],     "CTRL_Root")
    add_copy_xform(pb["pelvis"],   "CTRL_Pelvis")
    add_copy_xform(pb["spine_01"], "CTRL_Spine_01")
    add_copy_xform(pb["spine_02"], "CTRL_Spine_02")
    add_copy_xform(pb["spine_03"], "CTRL_Spine_03")
    add_copy_xform(pb["neck_01"],  "CTRL_Neck")
    add_copy_xform(pb["head"],     "CTRL_Head")
    add_copy_xform(pb["jaw"],      "CTRL_Jaw")

    # Head optional Look-At Damped Track + Eye stereo Look-At Damped Track
    dt_head = pb["head"].constraints.new("DAMPED_TRACK")
    dt_head.target = arm_obj
    dt_head.subtarget = "CTRL_LookAt"
    dt_head.track_axis = "TRACK_NEGATIVE_Y"
    drv_h = dt_head.driver_add("influence").driver
    drv_h.type = "AVERAGE"
    vh = drv_h.variables.new()
    vh.name = "v"
    vh.targets[0].id = arm_obj
    vh.targets[0].data_path = 'pose.bones["CTRL_Master"]["head_look_at"]'

    for sx, S in [("l", "L"), ("r", "R")]:
        dt_e = pb[f"eye_{sx}"].constraints.new("DAMPED_TRACK")
        dt_e.target = arm_obj
        dt_e.subtarget = f"CTRL_Eye_{S}"
        dt_e.track_axis = "TRACK_Y"
        drv_e = dt_e.driver_add("influence").driver
        drv_e.type = "AVERAGE"
        ve = drv_e.variables.new()
        ve.name = "v"
        ve.targets[0].id = arm_obj
        ve.targets[0].data_path = 'pose.bones["CTRL_Master"]["eye_look_at"]'

    # Secondary chains DEF -> CTRL
    for i in (1, 2, 3):
        add_copy_xform(pb[f"cable_0{i}"], f"CTRL_Cable_0{i}")
        add_copy_xform(pb[f"strap_0{i}"], f"CTRL_Strap_0{i}")

    # Arms IK Solver + FK/IK Blend + Twist Bones + Fingers
    for side_sign, sx, S in [(+1.0, "l", "L"), (-1.0, "r", "R")]:
        add_copy_xform(pb[f"clavicle_{sx}"], f"CTRL_Clavicle_{S}")

        ik = pb[f"MCH_IK_LowerArm_{S}"].constraints.new("IK")
        ik.target = arm_obj
        ik.subtarget = f"CTRL_IK_Hand_{S}"
        ik.pole_target = arm_obj
        ik.pole_subtarget = f"CTRL_Pole_Arm_{S}"
        ik.pole_angle = math.pi * 0.5 if side_sign > 0 else -math.pi * 0.5
        ik.chain_count = 2

        add_copy_xform(pb[f"upperarm_{sx}"], f"CTRL_FK_UpperArm_{S}", 1.0)
        add_copy_xform(pb[f"upperarm_{sx}"], f"MCH_IK_UpperArm_{S}",  0.0, f"ik_fk_arm_{sx}")
        add_copy_xform(pb[f"lowerarm_{sx}"], f"CTRL_FK_LowerArm_{S}", 1.0)
        add_copy_xform(pb[f"lowerarm_{sx}"], f"MCH_IK_LowerArm_{S}",  0.0, f"ik_fk_arm_{sx}")
        add_copy_xform(pb[f"hand_{sx}"],     f"CTRL_FK_Hand_{S}",     1.0)
        add_copy_xform(pb[f"hand_{sx}"],     f"CTRL_IK_Hand_{S}",     0.0, f"ik_fk_arm_{sx}")

        # Forearm Twist Bone copies 55% local Y-twist from hand
        ct_low = pb[f"lowerarm_twist_{sx}"].constraints.new("COPY_ROTATION")
        ct_low.target = arm_obj
        ct_low.subtarget = f"hand_{sx}"
        ct_low.target_space = "LOCAL"
        ct_low.owner_space = "LOCAL"
        ct_low.use_x = False
        ct_low.use_y = True
        ct_low.use_z = False
        ct_low.influence = 0.55

        # Finger controls + Master curl/spread custom properties + live MCH drivers
        cf = pb[f"CTRL_Fingers_{S}"]
        cf["curl"] = 0.0
        cf["spread"] = 0.0
        cf.custom_shape = widgets["WGT_Diamond"]
        cf.custom_shape_scale_xyz = (0.045, 0.045, 0.045)
        spread_map = {"thumb": -0.30, "index": -0.26, "middle": -0.07, "ring": +0.10, "pinky": +0.26}
        for f_tmpl, _, _, _ in get_finger_defs(side_sign):
            fname = f_tmpl.split("_")[0]
            for idx_p, curl_mul in [("01", 0.95), ("02", 1.25), ("03", 0.90)]:
                def_n = f_tmpl.format(idx_p)
                mch_pb = pb[f"MCH_{def_n}"]
                mch_pb.rotation_mode = "XYZ"
                # Local -X curls phalanx down into palm (-Z) for both L and R hands!
                c_scale = -0.55 * curl_mul if fname == "thumb" else -1.0 * curl_mul
                drv_cx = mch_pb.driver_add("rotation_euler", 0).driver
                drv_cx.type = "SCRIPTED"
                drv_cx.expression = f"curl * {c_scale:.4f}"
                vc = drv_cx.variables.new()
                vc.name = "curl"
                vc.targets[0].id = arm_obj
                vc.targets[0].data_path = f'pose.bones["CTRL_Fingers_{S}"]["curl"]'
                if idx_p == "01":
                    sp_scale = spread_map[fname] * (+1.0 if side_sign > 0 else -1.0)
                    drv_sz = mch_pb.driver_add("rotation_euler", 2).driver
                    drv_sz.type = "SCRIPTED"
                    drv_sz.expression = f"spread * {sp_scale:.4f}"
                    vs = drv_sz.variables.new()
                    vs.name = "spread"
                    vs.targets[0].id = arm_obj
                    vs.targets[0].data_path = f'pose.bones["CTRL_Fingers_{S}"]["spread"]'
                add_copy_xform(pb[def_n], f"CTRL_{def_n}")

    # Legs IK Solver + Reverse Foot + FK/IK Blend + Twist Bones
    for sx, S in [("l", "L"), ("r", "R")]:
        ik_l = pb[f"MCH_IK_Calf_{S}"].constraints.new("IK")
        ik_l.target = arm_obj
        ik_l.subtarget = f"MCH_AnkleIK_{S}"
        ik_l.pole_target = arm_obj
        ik_l.pole_subtarget = f"CTRL_Pole_Leg_{S}"
        ik_l.pole_angle = -math.pi * 0.5
        ik_l.chain_count = 2

        add_copy_xform(pb[f"thigh_{sx}"], f"CTRL_FK_Thigh_{S}", 1.0)
        add_copy_xform(pb[f"thigh_{sx}"], f"MCH_IK_Thigh_{S}",  1.0, f"ik_fk_leg_{sx}")
        add_copy_xform(pb[f"calf_{sx}"],  f"CTRL_FK_Calf_{S}",  1.0)
        add_copy_xform(pb[f"calf_{sx}"],  f"MCH_IK_Calf_{S}",   1.0, f"ik_fk_leg_{sx}")
        add_copy_xform(pb[f"foot_{sx}"],  f"CTRL_FK_Foot_{S}",  1.0)
        add_copy_xform(pb[f"foot_{sx}"],  f"MCH_IK_Foot_{S}",   1.0, f"ik_fk_leg_{sx}")
        add_copy_xform(pb[f"ball_{sx}"],  f"CTRL_FK_Ball_{S}",  1.0)
        add_copy_xform(pb[f"ball_{sx}"],  f"MCH_IK_Ball_{S}",   1.0, f"ik_fk_leg_{sx}")

    # Props: Retractable Blade, Reload Cell Handoff, Deploy Beacon Handoff
    add_copy_xform(pb["blade_r"],   "CTRL_Blade_R")
    add_copy_xform(pb["cell_bone"], "CTRL_Cell_Offset", 1.0)
    add_copy_xform(pb["cell_bone"], "MCH_Cell_Hand_L",  0.0, "cell_in_hand_l")

    add_copy_xform(pb["beacon_bone"], "MCH_Beacon_Dock",   1.0)
    add_copy_xform(pb["beacon_bone"], "MCH_Beacon_Hand_L", 0.0, "beacon_in_hand_l")
    add_copy_xform(pb["beacon_bone"], "CTRL_Beacon_World", 0.0, "beacon_planted")

    # Assign clean custom wireframe shapes to primary controls
    pb["CTRL_Master"].custom_shape = widgets["WGT_Circle"]
    pb["CTRL_Master"].custom_shape_scale_xyz = (0.42, 0.42, 0.42)
    pb["CTRL_Root"].custom_shape = widgets["WGT_Circle"]
    pb["CTRL_Root"].custom_shape_scale_xyz = (0.26, 0.26, 0.26)
    for sp_n in ("CTRL_Pelvis", "CTRL_Spine_01", "CTRL_Spine_02", "CTRL_Spine_03", "CTRL_Neck", "CTRL_Head"):
        pb[sp_n].custom_shape = widgets["WGT_Circle"]
        pb[sp_n].custom_shape_scale_xyz = (0.20, 0.20, 0.20)
    for S in ("L", "R"):
        pb[f"CTRL_IK_Hand_{S}"].custom_shape = widgets["WGT_Box"]
        pb[f"CTRL_IK_Hand_{S}"].custom_shape_scale_xyz = (0.10, 0.10, 0.10)
        pb[f"CTRL_IK_Foot_{S}"].custom_shape = widgets["WGT_Foot"]
        pb[f"CTRL_Pole_Arm_{S}"].custom_shape = widgets["WGT_Diamond"]
        pb[f"CTRL_Pole_Arm_{S}"].custom_shape_scale_xyz = (0.06, 0.06, 0.06)
        pb[f"CTRL_Pole_Leg_{S}"].custom_shape = widgets["WGT_Diamond"]
        pb[f"CTRL_Pole_Leg_{S}"].custom_shape_scale_xyz = (0.07, 0.07, 0.07)
    pb["CTRL_LookAt"].custom_shape = widgets["WGT_Diamond"]
    pb["CTRL_LookAt"].custom_shape_scale_xyz = (0.08, 0.08, 0.08)

    bpy.ops.object.mode_set(mode="OBJECT")

    # Embed and register the MorphRig Animator UI & Pose-Matching / Reset Operators in the .blend file
    txt = bpy.data.texts.get("morphrig_ui.py") or bpy.data.texts.new("morphrig_ui.py")
    txt.clear()
    txt.write(EMBEDDED_UI_SCRIPT)
    txt.use_module = True  # Auto-registers when opening Operative.blend!
    exec(compile(EMBEDDED_UI_SCRIPT, "morphrig_ui.py", "exec"), {"__name__": "__main__"})

    def_count = sum(1 for b in arm_data.bones if b.use_deform)
    print(f"[RigBuilder] Built Armature with {def_count} DEF bones and {len(arm_data.bones) - def_count} CTRL/MCH bones.")
    return arm_obj


def seg_dist_t(p: Vector, a: Vector, b: Vector) -> tuple[float, float]:
    """Returns (perpendicular/capsule distance to segment AB, clamped parameter t in [0,1])."""
    ab = b - a
    len_sq = ab.length_squared
    if len_sq < 1e-10:
        return (p - a).length, 0.0
    t = max(0.0, min(1.0, (p - a).dot(ab) / len_sq))
    proj = a + ab * t
    return (p - proj).length, t


def assign_skin_weights(obj_lod0: bpy.types.Object, arm_obj: bpy.types.Object, part_names: dict[int, str]) -> None:
    """
    Assigns clean, smooth, part-isolated skin weights to Operative_LOD0 (<= 8 influences/vertex, normalized).
    """
    mesh = obj_lod0.data
    bones = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm_obj.data.bones if b.use_deform}

    # Create vertex groups for all 92 DEF bones in deterministic order
    vgroups = {}
    for b in arm_obj.data.bones:
        if b.use_deform:
            vgroups[b.name] = obj_lod0.vertex_groups.get(b.name) or obj_lod0.vertex_groups.new(name=b.name)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    part_layer = bm.verts.layers.int.get("part_id")
    sub_layer = bm.verts.layers.int.get("sub_id")
    vert_parts = [(part_names.get(v[part_layer], "TORSO_SUIT"), v[sub_layer], v.co.copy()) for v in bm.verts]
    bm.free()

    def sstep(e0: float, e1: float, x: float) -> float:
        t = max(0.0, min(1.0, (x - e0) / max(1e-8, e1 - e0)))
        return t * t * (3.0 - 2.0 * t)

    def add_w(wdict: dict[str, float], bname: str, w: float):
        if w > 1e-4:
            wdict[bname] = wdict.get(bname, 0.0) + w

    for v_idx, (pname, sub_id, co) in enumerate(vert_parts):
        w: dict[str, float] = {}

        if pname == "PROP_EMITTER_R":
            add_w(w, "emitter_bone_r", 1.0)
        elif pname == "PROP_BLADE_R":
            add_w(w, "blade_r", 1.0)
        elif pname == "PROP_CELL":
            add_w(w, "cell_bone", 1.0)
        elif pname == "PROP_BEACON":
            add_w(w, "beacon_bone", 1.0)
        elif pname == "BELT":
            add_w(w, "pelvis", 1.0)
        elif pname == "CHEST_ARMOR":
            t_sp = sstep(1.24, 1.38, co.z)
            add_w(w, "spine_02", 0.25 * (1.0 - t_sp))
            add_w(w, "spine_03", 0.75 + 0.25 * t_sp)
        elif pname == "COLLAR_ARMOR":
            add_w(w, "spine_03", 0.72)
            add_w(w, "neck_01", 0.28)
        elif pname == "PAULDRON_L":
            t_lat = sstep(0.14, 0.27, co.x)
            add_w(w, "spine_03", 0.20 * (1.0 - t_lat))
            add_w(w, "clavicle_l", 0.80 + 0.05 * t_lat)
            add_w(w, "upperarm_l", 0.15 * t_lat)
        elif pname in ("KNEE_GUARD_L", "KNEE_GUARD_R"):
            sx = "l" if pname.endswith("_L") else "r"
            t_up = sstep(0.49, 0.54, co.z)
            add_w(w, f"calf_{sx}", 1.0 - 0.20 * t_up)
            add_w(w, f"thigh_{sx}", 0.20 * t_up)
        elif pname == "EYEBALL_L":
            add_w(w, "eye_l", 1.0)
        elif pname == "EYEBALL_R":
            add_w(w, "eye_r", 1.0)
        elif pname == "TEETH_UPPER":
            add_w(w, "head", 1.0)
        elif pname == "TEETH_LOWER":
            add_w(w, "jaw", 1.0)
        elif pname == "TONGUE":
            # Smoothly blend jaw -> tongue_01 -> tongue_02 along Y (-0.038 to -0.087)
            ty = sstep(-0.040, -0.085, co.y) if co.y < -0.085 else max(0.0, min(1.0, (-0.038 - co.y) / 0.049))
            add_w(w, "jaw", max(0.0, 1.0 - ty * 2.5))
            add_w(w, "tongue_01", math.sin(min(1.0, ty * 1.1) * math.pi) * 0.85 + (0.25 if ty < 0.5 else 0.0))
            add_w(w, "tongue_02", sstep(0.42, 0.85, ty))
        elif pname == "HAIR":
            t_nape = 1.0 - sstep(1.50, 1.58, co.z)
            add_w(w, "head", 1.0 - 0.35 * t_nape)
            add_w(w, "neck_01", 0.35 * t_nape)
        elif pname == "CABLE":
            tc = max(0.0, min(1.0, (1.665 - co.z) / 0.260))
            if tc < 0.33:
                u = tc / 0.33
                add_w(w, "head", 0.25 * (1.0 - u))
                add_w(w, "cable_01", 0.75 + 0.25 * u * (1.0 - u))
                add_w(w, "cable_02", 0.30 * u)
            elif tc < 0.67:
                u = (tc - 0.33) / 0.34
                add_w(w, "cable_01", 0.35 * (1.0 - u))
                add_w(w, "cable_02", 0.65 * (1.0 - 0.4 * u) + 0.35 * u * (1.0 - u))
                add_w(w, "cable_03", 0.45 * u)
            else:
                u = (tc - 0.67) / 0.33
                add_w(w, "cable_02", 0.35 * (1.0 - u))
                add_w(w, "cable_03", 0.65 + 0.35 * u)
        elif pname == "STRAP":
            ts = max(0.0, min(1.0, (0.945 - co.z) / 0.265))
            if ts < 0.34:
                u = ts / 0.34
                add_w(w, "pelvis", 0.25 * (1.0 - u))
                add_w(w, "strap_01", 0.75 * (1.0 - 0.3 * u) + 0.25 * u)
                add_w(w, "strap_02", 0.30 * u)
            elif ts < 0.67:
                u = (ts - 0.34) / 0.33
                add_w(w, "strap_01", 0.35 * (1.0 - u))
                add_w(w, "strap_02", 0.65 * (1.0 - 0.35 * u) + 0.30 * u * (1.0 - u))
                add_w(w, "strap_03", 0.45 * u)
            else:
                u = (ts - 0.67) / 0.33
                add_w(w, "strap_02", 0.35 * (1.0 - u))
                add_w(w, "strap_03", 0.65 + 0.35 * u)
        elif pname.startswith("EYELID_"):
            # EYELID_UPPER_L / EYELID_LOWER_R etc.
            parts = pname.split("_")
            kind = parts[1].lower()
            sx = parts[2].lower()
            lid_w = 0.90 if sub_id == 2 else 0.45
            add_w(w, f"eyelid_{kind}_{sx}", lid_w)
            add_w(w, "head", 1.0 - lid_w)
        elif pname in ("BROW_L", "BROW_R"):
            sx = "l" if pname.endswith("_L") else "r"
            ax = abs(co.x)
            t_out = sstep(0.018, 0.044, ax)
            add_w(w, f"brow_inner_{sx}", 0.75 * (1.0 - t_out))
            add_w(w, f"brow_outer_{sx}", 0.75 * t_out)
            add_w(w, "head", 0.25)
        elif pname in ("LIP_UPPER", "LIP_LOWER", "ORAL_BAG"):
            is_corner = sub_id == 99
            is_lower = (pname == "LIP_LOWER") or (pname == "ORAL_BAG" and sub_id == 2)
            cor_l = math.exp(-(((co.x - 0.024) / 0.011) ** 2))
            cor_r = math.exp(-(((co.x + 0.024) / 0.011) ** 2))
            mid_f = math.exp(-((co.x / 0.018) ** 2))
            if is_corner:
                add_w(w, "lip_corner_l" if co.x > 0 else "lip_corner_r", 0.55)
                add_w(w, "jaw", 0.22)
                add_w(w, "head", 0.23)
            elif is_lower:
                lip_bone_w = (0.45 * mid_f if pname == "LIP_LOWER" else 0.0)
                add_w(w, "lip_lower_mid", lip_bone_w)
                add_w(w, "lip_corner_l", 0.25 * cor_l)
                add_w(w, "lip_corner_r", 0.25 * cor_r)
                add_w(w, "jaw", max(0.25, 1.0 - lip_bone_w - 0.25 * (cor_l + cor_r)))
            else:
                lip_bone_w = (0.45 * mid_f if pname == "LIP_UPPER" else 0.0)
                add_w(w, "lip_upper_mid", lip_bone_w)
                add_w(w, "lip_corner_l", 0.25 * cor_l)
                add_w(w, "lip_corner_r", 0.25 * cor_r)
                add_w(w, "head", max(0.25, 1.0 - lip_bone_w - 0.25 * (cor_l + cor_r)))
        elif pname == "HEAD_SKIN":
            # Continuous, branch-free smooth neck_01 -> spine_03 -> head + jaw/chin + cheek + brow weights!
            t_sp = 1.0 - sstep(1.455, 1.495, co.z)
            t_hd = sstep(1.515, 1.568, co.z)
            neck_w_val = (1.0 - t_sp) * (1.0 - t_hd)
            jaw_zone = sstep(0.035, 0.068, -co.y) * sstep(1.555, 1.572, co.z)
            jaw_z = 1.0 - sstep(1.575, 1.606, co.z)
            jaw_w = 0.88 * jaw_zone * jaw_z * math.exp(-((co.x / 0.052) ** 2))
            sx = "l" if co.x >= 0 else "r"
            ax = abs(co.x)
            cheek_w = 0.35 * math.exp(-(((ax - 0.042) / 0.020) ** 2 + ((co.z - 1.638) / 0.020) ** 2)) * sstep(0.05, 0.08, -co.y)
            bi_w = 0.42 * math.exp(-(((ax - 0.015) / 0.014) ** 2 + ((co.z - 1.696) / 0.014) ** 2)) * sstep(0.06, 0.085, -co.y)
            bo_w = 0.42 * math.exp(-(((ax - 0.044) / 0.016) ** 2 + ((co.z - 1.696) / 0.014) ** 2)) * sstep(0.05, 0.080, -co.y)
            rem = max(0.0, t_hd * (1.0 - jaw_w - cheek_w - bi_w - bo_w))
            add_w(w, "spine_03", t_sp)
            add_w(w, "neck_01", neck_w_val)
            add_w(w, "jaw", jaw_w)
            add_w(w, f"cheek_{sx}", cheek_w)
            add_w(w, f"brow_inner_{sx}", bi_w)
            add_w(w, f"brow_outer_{sx}", bo_w)
            add_w(w, "head", rem)
        elif pname.startswith("FINGER_"):
            # Strictly isolated per-finger weights! FINGER_<NAME>_<L/R>
            _, fn, st = pname.split("_")
            sx = st.lower()
            prefix = f"{fn.lower()}"
            b1, b2, b3 = f"{prefix}_01_{sx}", f"{prefix}_02_{sx}", f"{prefix}_03_{sx}"
            d1, t1 = seg_dist_t(co, *bones[b1])
            d2, t2 = seg_dist_t(co, *bones[b2])
            d3, t3 = seg_dist_t(co, *bones[b3])
            # Smooth inverse-distance + axial joint transition
            for bn, d in [(b1, d1), (b2, d2), (b3, d3)]:
                add_w(w, bn, 1.0 / ((d + 0.004) ** 3))
            if t1 < 0.25 and d1 < 0.016:
                add_w(w, f"hand_{sx}", (0.25 - t1) * 18000.0)
        elif pname in ("ARM_UPPER_L", "ARM_UPPER_R", "FOREARM_ORGANIC_L", "FOREARM_CYBER_R"):
            sx = "l" if pname.endswith("_L") else "r"
            ax = abs(co.x)
            if ax < 0.215:
                u = sstep(0.155, 0.215, ax)
                add_w(w, f"clavicle_{sx}", 0.55 * (1.0 - u))
                add_w(w, f"upperarm_{sx}", 0.45 + 0.55 * u)
            elif ax < 0.415:
                u = sstep(0.270, 0.400, ax)
                add_w(w, f"upperarm_{sx}", 1.0 - 0.55 * u)
                add_w(w, f"upperarm_twist_{sx}", 0.55 * u)
            elif ax < 0.480:
                # 5-ring elbow joint blend!
                u = sstep(0.415, 0.480, ax)
                add_w(w, f"upperarm_twist_{sx}", 0.65 * (1.0 - u))
                add_w(w, f"upperarm_{sx}", 0.35 * (1.0 - u))
                add_w(w, f"lowerarm_{sx}", u)
            elif ax < 0.680:
                u = sstep(0.540, 0.675, ax)
                add_w(w, f"lowerarm_{sx}", 1.0 - 0.65 * u)
                add_w(w, f"lowerarm_twist_{sx}", 0.65 * u)
            else:
                # Wrist & palm!
                u = sstep(0.685, 0.725, ax)
                add_w(w, f"lowerarm_twist_{sx}", 0.75 * (1.0 - u))
                add_w(w, f"lowerarm_{sx}", 0.25 * (1.0 - u))
                add_w(w, f"hand_{sx}", u)
        elif pname in ("LEG_L", "LEG_R", "BOOT_L", "BOOT_R"):
            sx = "l" if pname.endswith("_L") else "r"
            z = co.z
            if z > 0.895:
                u = sstep(0.895, 0.965, z)
                add_w(w, "pelvis", 0.55 * u)
                add_w(w, f"thigh_{sx}", 1.0 - 0.55 * u)
            elif z > 0.555:
                u = 1.0 - sstep(0.560, 0.760, z)
                add_w(w, f"thigh_{sx}", 1.0 - 0.50 * u)
                add_w(w, f"thigh_twist_{sx}", 0.50 * u)
            elif z > 0.470:
                # 5-ring knee bend transition!
                u = 1.0 - sstep(0.470, 0.555, z)
                add_w(w, f"thigh_twist_{sx}", 0.60 * (1.0 - u))
                add_w(w, f"thigh_{sx}", 0.40 * (1.0 - u))
                add_w(w, f"calf_{sx}", u)
            elif z > 0.130:
                u = 1.0 - sstep(0.140, 0.340, z)
                add_w(w, f"calf_{sx}", 1.0 - 0.45 * u)
                add_w(w, f"calf_twist_{sx}", 0.45 * u)
            else:
                # Ankle -> Foot -> Ball/Toe blend!
                u_ankle = 1.0 - sstep(0.075, 0.130, z)
                u_ball = sstep(-0.085, -0.135, co.y) if co.y < -0.135 else max(0.0, min(1.0, (-0.085 - co.y) / 0.055))
                foot_total = u_ankle
                add_w(w, f"calf_twist_{sx}", 0.65 * (1.0 - foot_total))
                add_w(w, f"calf_{sx}", 0.35 * (1.0 - foot_total))
                add_w(w, f"foot_{sx}", foot_total * (1.0 - u_ball))
                add_w(w, f"ball_{sx}", foot_total * u_ball)
        else:
            # TORSO_SUIT smooth spine + clavicle/deltoid + hip distribution
            z = co.z
            ax = abs(co.x)
            sx = "l" if co.x >= 0 else "r"
            if z < 1.04:
                u = sstep(0.95, 1.04, z)
                hip_leg = sstep(0.07, 0.15, ax) * (1.0 - sstep(0.885, 0.945, z))
                add_w(w, f"thigh_{sx}", 0.45 * hip_leg)
                add_w(w, "pelvis", (1.0 - 0.45 * hip_leg) * (1.0 - 0.45 * u))
                add_w(w, "spine_01", (1.0 - 0.45 * hip_leg) * 0.45 * u)
            elif z < 1.185:
                u = sstep(1.04, 1.185, z)
                add_w(w, "spine_01", 1.0 - 0.65 * u)
                add_w(w, "spine_02", 0.65 * u)
            elif z < 1.335:
                u = sstep(1.185, 1.335, z)
                add_w(w, "spine_02", 1.0 - 0.70 * u)
                add_w(w, "spine_03", 0.70 * u)
            else:
                clav_w = sstep(0.085, 0.175, ax) * sstep(1.37, 1.44, z)
                neck_w = (1.0 - sstep(0.04, 0.09, ax)) * sstep(1.450, 1.485, z)
                rem = max(0.05, 1.0 - 0.65 * clav_w - 0.75 * neck_w)
                add_w(w, f"clavicle_{sx}", 0.65 * clav_w)
                add_w(w, "neck_01", 0.75 * neck_w)
                add_w(w, "spine_03", rem)

        # Keep top <= 8 weights and normalize to exact sum 1.0
        sorted_items = sorted(w.items(), key=lambda kv: kv[1], reverse=True)[:8]
        w_sum = sum(val for _, val in sorted_items)
        if w_sum < 1e-8:
            vgroups["pelvis"].add([v_idx], 1.0, "REPLACE")
        else:
            for bn, val in sorted_items:
                vgroups[bn].add([v_idx], val / w_sum, "REPLACE")

    arm_mod = obj_lod0.modifiers.new(name="Armature", type="ARMATURE")
    arm_mod.object = arm_obj
    arm_mod.use_deform_preserve_volume = True
    print("[SkinBuilder] Assigned normalized <=8-influence part-isolated skin weights to Operative_LOD0.")


def build_facial_and_corrective_shapekeys(obj_lod0: bpy.types.Object, arm_obj: bpy.types.Object, part_names: dict[int, str]) -> None:
    """
    Authors full facial shape keys (bilateral & asymmetric controls, 13 visemes, 6 expression presets)
    and driven joint-corrective shape keys onto Operative_LOD0!
    """
    mesh = obj_lod0.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    part_layer = bm.verts.layers.int.get("part_id")
    sub_layer = bm.verts.layers.int.get("sub_id")
    v_meta = [(part_names.get(v[part_layer], ""), v[sub_layer], v.co.copy()) for v in bm.verts]
    bm.free()

    basis = obj_lod0.shape_key_add(name="Basis", from_mix=False)
    n_verts = len(v_meta)

    def add_sk(name: str, delta_fn) -> bpy.types.ShapeKey:
        sk = obj_lod0.shape_key_add(name=name, from_mix=False)
        for idx, (pname, sub_id, co) in enumerate(v_meta):
            d = delta_fn(pname, sub_id, co)
            if d is not None:
                sk.data[idx].co = co + d
        return sk

    # --- 1. BILATERAL / ASYMMETRIC FACIAL CONTROLS ---
    for side_sign, sx in [(+1.0, "l"), (-1.0, "r")]:
        S_tag = "L" if side_sign > 0 else "R"
        ec = Vector((side_sign * 0.032, -0.074, 1.675))

        # Spherical eyelid closure (upper lid sweeps down +X rot, lower lid sweeps up -X rot to meet cleanly over cornea!)
        def make_blink(s_sign=side_sign, tag=S_tag, center=ec):
            def fn(pname, sub_id, co):
                corner_taper = math.cos(min(1.0, abs(co.x - center.x) / 0.0155) * math.pi * 0.42)
                if pname == f"EYELID_UPPER_{tag}":
                    w = (1.0 if sub_id == 2 else 0.48) * corner_taper
                    rel = co - center
                    rot = Matrix.Rotation(+0.64 * w, 3, "X")
                    return (center + rot @ rel) - co + Vector((0.0, -0.0008 * w, 0.0))
                if pname == f"EYELID_LOWER_{tag}":
                    w = (1.0 if sub_id == 2 else 0.45) * corner_taper
                    rel = co - center
                    rot = Matrix.Rotation(-0.24 * w, 3, "X")
                    return (center + rot @ rel) - co + Vector((0.0, -0.0006 * w, 0.0))
                return None
            return fn

        add_sk(f"blink_{sx}", make_blink())

        def make_squint(s_sign=side_sign, tag=S_tag, center=ec):
            def fn(pname, sub_id, co):
                if pname == f"EYELID_LOWER_{tag}":
                    w = 1.0 if sub_id == 2 else 0.55
                    return Vector((0.0, -0.0006 * w, 0.0026 * w))
                if pname == f"EYELID_UPPER_{tag}":
                    w = 1.0 if sub_id == 2 else 0.45
                    return Vector((0.0, -0.0004 * w, -0.0014 * w))
                if pname == "HEAD_SKIN" and co.x * s_sign > 0.005 and co.y < -0.055:
                    g = math.exp(-(((co.x - s_sign * 0.036) / 0.018) ** 2 + ((co.z - 1.662) / 0.014) ** 2))
                    if g > 0.02:
                        return Vector((-s_sign * 0.0012 * g, -0.0010 * g, 0.0022 * g))
                return None
            return fn

        add_sk(f"squint_{sx}", make_squint())

        def make_brow_up(s_sign=side_sign, tag=S_tag):
            def fn(pname, sub_id, co):
                if pname == f"BROW_{tag}":
                    return Vector((0.0, -0.0008, 0.0065))
                if pname == "HEAD_SKIN" and co.x * s_sign >= -0.004 and co.y < -0.055:
                    g = math.exp(-(((co.x - s_sign * 0.028) / 0.024) ** 2 + ((co.z - 1.700) / 0.020) ** 2))
                    if g > 0.02:
                        return Vector((0.0, -0.0006 * g, 0.0062 * g))
                return None
            return fn

        add_sk(f"brow_up_{sx}", make_brow_up())

        def make_brow_down(s_sign=side_sign, tag=S_tag):
            def fn(pname, sub_id, co):
                if pname == f"BROW_{tag}":
                    inner_f = max(0.2, 1.0 - abs(co.x) / 0.055)
                    return Vector((-s_sign * 0.0038 * inner_f, -0.0014 * inner_f, -0.0058 * inner_f))
                if pname == "HEAD_SKIN" and co.x * s_sign >= -0.004 and co.y < -0.055:
                    g = math.exp(-(((co.x - s_sign * 0.024) / 0.022) ** 2 + ((co.z - 1.696) / 0.018) ** 2))
                    if g > 0.02:
                        return Vector((-s_sign * 0.0032 * g, -0.0012 * g, -0.0054 * g))
                return None
            return fn

        add_sk(f"brow_down_{sx}", make_brow_down())

        def make_cheek_raise(s_sign=side_sign):
            def fn(pname, sub_id, co):
                if pname == "HEAD_SKIN" and co.x * s_sign > 0.004 and co.y < -0.045:
                    g = math.exp(-(((co.x - s_sign * 0.038) / 0.024) ** 2 + ((co.z - 1.638) / 0.024) ** 2))
                    if g > 0.02:
                        return Vector((s_sign * 0.0022 * g, -0.0028 * g, 0.0045 * g))
                return None
            return fn

        add_sk(f"cheek_raise_{sx}", make_cheek_raise())

        def make_smile(s_sign=side_sign):
            def fn(pname, sub_id, co):
                if pname in ("LIP_UPPER", "LIP_LOWER", "HEAD_SKIN", "ORAL_BAG") and co.y < -0.055:
                    if co.x * s_sign < -0.004:
                        return None
                    side_w = max(0.0, min(1.0, (co.x * s_sign + 0.004) / 0.018))
                    g = math.exp(-(((co.x - s_sign * 0.024) / 0.020) ** 2 + ((co.z - 1.608) / 0.020) ** 2)) * side_w
                    if g > 0.01:
                        return Vector((s_sign * 0.0058 * g, +0.0038 * g, +0.0068 * g))
                return None
            return fn

        add_sk(f"smile_{sx}", make_smile())

        def make_frown(s_sign=side_sign):
            def fn(pname, sub_id, co):
                if pname in ("LIP_UPPER", "LIP_LOWER", "HEAD_SKIN", "ORAL_BAG") and co.y < -0.055:
                    if co.x * s_sign < -0.004:
                        return None
                    side_w = max(0.0, min(1.0, (co.x * s_sign + 0.004) / 0.018))
                    g = math.exp(-(((co.x - s_sign * 0.024) / 0.020) ** 2 + ((co.z - 1.606) / 0.020) ** 2)) * side_w
                    if g > 0.01:
                        return Vector((s_sign * 0.0018 * g, +0.0018 * g, -0.0065 * g))
                return None
            return fn

        add_sk(f"frown_{sx}", make_frown())

    # Symmetric / Oral Controls: jaw_open, lip_close, mouth_wide, mouth_pucker, mouth_funnel, tongue_up, tongue_out
    jaw_pivot = Vector((0.0, -0.028, 1.612))

    def jaw_delta(pname: str, sub_id: int, co: Vector, angle_rad: float = 0.24):
        rot = Matrix.Rotation(angle_rad, 3, "X")
        if pname in ("TEETH_LOWER", "TONGUE"):
            return (jaw_pivot + rot @ (co - jaw_pivot)) - co
        if pname == "LIP_LOWER" or (pname == "ORAL_BAG" and sub_id == 2):
            # Smooth oval corner taper so mouth opens into a natural curved oval rather than a sharp rectangle
            oval_w = 0.38 + 0.62 * math.cos(min(1.0, abs(co.x) / 0.026) * math.pi * 0.5)
            rot_o = Matrix.Rotation(angle_rad * oval_w, 3, "X")
            inward_x = -co.x * 0.12 * (angle_rad / 0.24)
            return (jaw_pivot + rot_o @ (co - jaw_pivot)) - co + Vector((inward_x, 0.0, 0.0))
        if sub_id == 99 and pname in ("LIP_UPPER", "ORAL_BAG"):
            rot_half = Matrix.Rotation(angle_rad * 0.35, 3, "X")
            return (jaw_pivot + rot_half @ (co - jaw_pivot)) - co + Vector((-co.x * 0.10 * (angle_rad / 0.24), 0.0, 0.0))
        if pname == "HEAD_SKIN" and co.y < -0.030 and co.z < 1.608:
            w = max(0.0, min(1.0, (1.606 - co.z) / 0.028)) * max(0.0, min(1.0, (-0.030 - co.y) / 0.040))
            if w > 0.01:
                return ((jaw_pivot + rot @ (co - jaw_pivot)) - co) * w
        return None

    add_sk("jaw_open", lambda p, s, c: jaw_delta(p, s, c, 0.24))

    def lip_close_fn(pname, sub_id, co):
        if pname == "LIP_UPPER" and sub_id != 99:
            f = (sub_id / 4.0) * math.exp(-((co.x / 0.024) ** 2))
            return Vector((0.0, -0.0010 * f, -0.0038 * f))
        if pname == "LIP_LOWER" and sub_id != 99:
            f = (sub_id / 4.0) * math.exp(-((co.x / 0.024) ** 2))
            return Vector((0.0, -0.0010 * f, +0.0048 * f))
        return None

    add_sk("lip_close", lip_close_fn)

    def mouth_wide_fn(pname, sub_id, co):
        if pname in ("LIP_UPPER", "LIP_LOWER", "HEAD_SKIN", "ORAL_BAG") and co.y < -0.060:
            g = math.exp(-(((co.z - 1.608) / 0.018) ** 2)) * min(1.0, abs(co.x) / 0.016)
            if g > 0.01:
                return Vector((math.copysign(0.0062 * g, co.x), +0.0022 * g, 0.0))
        return None

    add_sk("mouth_wide", mouth_wide_fn)

    def pucker_fn(pname, sub_id, co, funnel_open: float = 0.0):
        if pname in ("LIP_UPPER", "LIP_LOWER", "HEAD_SKIN", "ORAL_BAG") and co.y < -0.065:
            g = math.exp(-(((co.z - 1.608) / 0.020) ** 2 + (co.x / 0.032) ** 2))
            if g > 0.01:
                dx = -co.x * 0.42 * g
                dy = -0.0058 * g
                dz = 0.0
                if funnel_open > 0.0 and pname in ("LIP_UPPER", "LIP_LOWER") and sub_id != 99:
                    dz = (+0.0042 if pname == "LIP_UPPER" else -0.0048) * funnel_open * (sub_id / 4.0)
                return Vector((dx, dy, dz))
        return None

    add_sk("mouth_pucker", lambda p, s, c: pucker_fn(p, s, c, 0.0))
    add_sk("mouth_funnel", lambda p, s, c: pucker_fn(p, s, c, 1.0))

    add_sk("tongue_up", lambda p, s, c: Vector((0.0, -0.003 * max(0.0, (-0.045 - c.y) / 0.042), 0.0105 * max(0.0, (-0.045 - c.y) / 0.042))) if p == "TONGUE" else None)
    add_sk("tongue_out", lambda p, s, c: Vector((0.0, -0.011 * max(0.0, (-0.045 - c.y) / 0.042), 0.0045 * max(0.0, (-0.045 - c.y) / 0.042))) if p == "TONGUE" else None)

    # --- 2. 13 EXPLICIT VISEME SHAPE KEYS (Matching dialogue_alignment.json) ---
    kb = obj_lod0.data.shape_keys.key_blocks

    def mix_shapes(new_name: str, recipe: dict[str, float]):
        sk = obj_lod0.shape_key_add(name=new_name, from_mix=False)
        for idx in range(n_verts):
            acc = Vector((0.0, 0.0, 0.0))
            b_co = basis.data[idx].co
            for src_n, weight in recipe.items():
                acc += (kb[src_n].data[idx].co - b_co) * weight
            sk.data[idx].co = b_co + acc

    mix_shapes("V_SIL",  {})
    mix_shapes("V_MBP",  {"lip_close": 0.90, "mouth_pucker": 0.18})
    # Labiodental V_FV: slight jaw part + lower lip tucked back/up toward upper incisors, upper lip lifted slightly!
    def v_fv_fn(pname, sub_id, co):
        jd = jaw_delta(pname, sub_id, co, 0.055) or Vector()
        if pname == "LIP_LOWER" and sub_id != 99:
            f = (sub_id / 4.0) * math.exp(-((co.x / 0.022) ** 2))
            jd += Vector((0.0, +0.0055 * f, +0.0038 * f))
        elif pname == "LIP_UPPER" and sub_id != 99:
            f = (sub_id / 4.0) * math.exp(-((co.x / 0.022) ** 2))
            jd += Vector((0.0, -0.0005 * f, +0.0028 * f))
        return jd if jd.length_squared > 1e-10 else None
    add_sk("V_FV", v_fv_fn)

    mix_shapes("V_TH",   {"jaw_open": 0.36, "tongue_out": 0.95, "mouth_wide": 0.20})
    mix_shapes("V_TDNL", {"jaw_open": 0.34, "tongue_up": 0.92, "mouth_wide": 0.22})
    mix_shapes("V_SZ",   {"jaw_open": 0.18, "mouth_wide": 0.55, "tongue_up": 0.45})
    mix_shapes("V_KG",   {"jaw_open": 0.45, "mouth_wide": 0.15})
    mix_shapes("V_AA",   {"jaw_open": 0.92, "mouth_wide": 0.18})
    mix_shapes("V_EE",   {"jaw_open": 0.34, "mouth_wide": 0.85, "smile_l": 0.28, "smile_r": 0.28})
    mix_shapes("V_EH",   {"jaw_open": 0.56, "mouth_wide": 0.42})
    mix_shapes("V_OH",   {"jaw_open": 0.72, "mouth_funnel": 0.82})
    mix_shapes("V_OU",   {"jaw_open": 0.26, "mouth_pucker": 0.92, "mouth_funnel": 0.35})
    mix_shapes("V_ER",   {"jaw_open": 0.38, "mouth_funnel": 0.55, "tongue_up": 0.55})

    # --- 3. SIX REQUIRED NAMED EXPRESSION PRESET SHAPE KEYS ---
    mix_shapes("expr_joy_confidence", {
        "smile_l": 0.85, "smile_r": 0.72, "cheek_raise_l": 0.70, "cheek_raise_r": 0.60,
        "squint_l": 0.32, "squint_r": 0.28, "brow_up_l": 0.22,
    })
    mix_shapes("expr_anger", {
        "brow_down_l": 0.95, "brow_down_r": 0.95, "squint_l": 0.68, "squint_r": 0.68,
        "frown_l": 0.45, "frown_r": 0.45, "jaw_open": 0.14, "mouth_funnel": 0.22,
    })
    mix_shapes("expr_concern_sadness", {
        "brow_up_l": 0.55, "brow_up_r": 0.55, "frown_l": 0.68, "frown_r": 0.68,
        "squint_l": 0.25, "squint_r": 0.25,
    })
    mix_shapes("expr_surprise", {
        "brow_up_l": 0.95, "brow_up_r": 0.95, "jaw_open": 0.62, "mouth_funnel": 0.45,
    })
    mix_shapes("expr_pain", {
        "blink_l": 0.72, "blink_r": 0.78, "squint_l": 0.85, "squint_r": 0.85,
        "brow_down_l": 0.85, "brow_down_r": 0.85, "mouth_wide": 0.65, "frown_l": 0.50, "frown_r": 0.50, "jaw_open": 0.28,
    })
    mix_shapes("expr_focus", {
        "brow_down_l": 0.52, "brow_down_r": 0.52, "squint_l": 0.42, "squint_r": 0.42, "lip_close": 0.35,
    })

    # --- 4. JOINT VOLUME-PRESERVATION CORRECTIVE SHAPE KEYS ---
    for side_sign, sx in [(+1.0, "l"), (-1.0, "r")]:
        S_tag = "L" if side_sign > 0 else "R"
        # Shoulder overhead volume preservation (lifts armpit/deltoid crease so shoulder never collapses!)
        def make_sh_corr(s_sign=side_sign, tag=S_tag):
            def fn(pname, sub_id, co):
                if pname in (f"ARM_UPPER_{tag}", "TORSO_SUIT") and co.x * s_sign > 0.08:
                    g = math.exp(-(((co.x - s_sign * 0.175) / 0.055) ** 2 + ((co.z - 1.445) / 0.055) ** 2))
                    if g > 0.02:
                        return Vector((-s_sign * 0.008 * g, 0.0, +0.016 * g))
                return None
            return fn
        sk_sh = add_sk(f"corr_shoulder_up_{sx}", make_sh_corr())

        # Elbow bend volume preservation
        def make_el_corr(s_sign=side_sign, tag=S_tag):
            def fn(pname, sub_id, co):
                if pname in (f"FOREARM_ORGANIC_{tag}", f"FOREARM_CYBER_{tag}"):
                    g = math.exp(-(((co.x - s_sign * 0.445) / 0.035) ** 2))
                    if g > 0.02:
                        return Vector((0.0, +0.008 * g if co.y > 0.028 else -0.004 * g, 0.0))
                return None
            return fn
        add_sk(f"corr_elbow_bend_{sx}", make_el_corr())

        # Knee deep-squat patella preservation
        def make_kn_corr(s_sign=side_sign, tag=S_tag):
            def fn(pname, sub_id, co):
                if pname == f"LEG_{tag}":
                    g = math.exp(-(((co.z - 0.515) / 0.045) ** 2))
                    if g > 0.02 and co.y < -0.015:
                        return Vector((0.0, -0.010 * g, +0.004 * g))
                return None
            return fn
        add_sk(f"corr_knee_bend_{sx}", make_kn_corr())

    print(f"[FacialRig] Authored {len(mesh.shape_keys.key_blocks) - 1} facial, viseme, preset & corrective shape keys.")


def export_skeleton_and_sockets_doc(arm_obj: bpy.types.Object, out_path: Path) -> None:
    """Writes docs/skeleton_and_sockets.json documenting all 92 exported DEF bones, hierarchy, axes, units & sockets."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bones_doc = []
    for b in arm_obj.data.bones:
        if not b.use_deform:
            continue
        bones_doc.append({
            "name": b.name,
            "parent": b.parent.name if (b.parent and b.parent.use_deform) else None,
            "head_m": [round(b.head_local.x, 5), round(b.head_local.y, 5), round(b.head_local.z, 5)],
            "tail_m": [round(b.tail_local.x, 5), round(b.tail_local.y, 5), round(b.tail_local.z, 5)],
            "length_m": round(b.length, 5),
        })

    sockets = [
        {"socket_name": "socket_hand_r",         "parent_bone": "hand_r",          "local_offset_cm": [0.0, 0.0, 0.0],    "purpose": "Right cybernetic hand grip / weapon attachment"},
        {"socket_name": "socket_hand_l",         "parent_bone": "hand_l",          "local_offset_cm": [0.0, 0.0, 0.0],    "purpose": "Left organic hand grip (reload power cell & deploy beacon contact)"},
        {"socket_name": "socket_emitter_muzzle", "parent_bone": "emitter_muzzle",  "local_offset_cm": [0.0, 0.0, 0.0],    "purpose": "Wrist emitter ranged projectile & beam origin"},
        {"socket_name": "socket_blade_base",     "parent_bone": "blade_r",         "local_offset_cm": [0.0, 0.0, 0.0],    "purpose": "Retractable forearm blade base trail anchor"},
        {"socket_name": "socket_blade_tip",      "parent_bone": "blade_tip",       "local_offset_cm": [0.0, 0.0, 0.0],    "purpose": "Retractable forearm blade tip slash arc anchor"},
        {"socket_name": "socket_cell_slot",      "parent_bone": "emitter_bone_r",  "local_offset_cm": [-3.5, -2.4, 0.0],  "purpose": "Wrist emitter power-cell breech housing"},
        {"socket_name": "socket_beacon_dock",    "parent_bone": "pelvis",          "local_offset_cm": [-10.5, 12.3, -2.5],"purpose": "Rear-right belt tactical beacon dock"},
        {"socket_name": "socket_chest_fx",       "parent_bone": "spine_03",        "local_offset_cm": [0.0, -12.0, 4.0],  "purpose": "Self-cast / shield / hit VFX anchor"},
        {"socket_name": "socket_head_fx",        "parent_bone": "head",            "local_offset_cm": [0.0, 0.0, 26.0],   "purpose": "Overhead status indicator (stun/sleep/silence/team icon)"},
        {"socket_name": "socket_root_fx",        "parent_bone": "root",            "local_offset_cm": [0.0, 0.0, 2.0],    "purpose": "Ground ring, blink/respawn/cast_ground VFX anchor"},
    ]

    doc = {
        "asset_name": "Operative",
        "standing_height_m": 1.800,
        "standing_height_unreal_cm": 180.0,
        "source_units": "Blender Metric (1.0 unit = 1.0 meter); exported to FBX -> Unreal Engine centimeters (180.0 cm, uniform import scale 1.0)",
        "coordinate_convention": {
            "blender": {"up": "+Z", "forward": "-Y", "left": "+X", "right": "-X", "ground_origin": [0.0, 0.0, 0.0]},
            "unreal": {"up": "+Z", "mesh_forward": "+Y / Character Facing X via standard +90/-90 deg Mesh Yaw", "units": "cm"},
        },
        "root_bone": "root",
        "pelvis_independent_of_root": True,
        "deformation_bone_count": len(bones_doc),
        "max_influences_per_vertex": 8,
        "bones": bones_doc,
        "sockets": sockets,
    }
    out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"[RigBuilder] Wrote {out_path}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_character_mesh import build_operative_meshes, generate_lods

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

    lod0, part_names = build_operative_meshes()
    arm = build_armature()
    assign_skin_weights(lod0, arm, part_names)
    lod1, lod2 = generate_lods(lod0)
    build_facial_and_corrective_shapekeys(lod0, arm, part_names)
    export_skeleton_and_sockets_doc(arm, ROOT_DIR / "docs" / "skeleton_and_sockets.json")
