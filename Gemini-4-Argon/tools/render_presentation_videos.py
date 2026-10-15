#!/usr/bin/env python3
"""
Render the three required presentation videos from source/Operative.blend:
  - presentation/turntable.mp4
  - presentation/motion_showcase.mp4
  - presentation/face_performance.mp4

Run with:
  blender -b source/Operative.blend --python-exit-code 1 -P tools/render_presentation_videos.py
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile

import bpy
from mathutils import Euler, Matrix, Vector

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRESENTATION_DIR = os.path.join(REPO_ROOT, "presentation")
AUDIO_WAV = os.path.join(REPO_ROOT, "source", "audio", "dialogue.wav")


def set_action(arm_obj, mesh_objs, action_name):
    act = bpy.data.actions.get(action_name)
    if not act:
        raise RuntimeError(f"Action {action_name} not found")
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    arm_obj.animation_data.action = act
    if hasattr(arm_obj.animation_data, "action_slot") and len(act.slots) > 0:
        for s in act.slots:
            if s.target_id_type == 'OBJECT':
                arm_obj.animation_data.action_slot = s
                break

    for mobj in mesh_objs:
        sk = mobj.data.shape_keys
        if sk:
            if not sk.animation_data:
                sk.animation_data_create()
            sk.animation_data.action = act
            if hasattr(sk.animation_data, "action_slot") and len(act.slots) > 0:
                for s in act.slots:
                    if s.target_id_type == 'KEY':
                        sk.animation_data.action_slot = s
                        break


def reset_pose_and_shapes(arm_obj, mesh_objs):
    for pb in arm_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    for mobj in mesh_objs:
        if mobj.data.shape_keys and mobj.data.shape_keys.key_blocks:
            for kb in mobj.data.shape_keys.key_blocks[1:]:
                kb.value = 0.0


def set_team_variant(team_name):
    """Switch M_Operative_Props_Accent textures between TeamA (Cyan/HexChevron) and TeamB (Amber/CrossedDiamond)."""
    mat = bpy.data.materials.get("M_Operative_Props_Accent")
    if not mat or not mat.use_nodes:
        return
    tex_dir = os.path.join(REPO_ROOT, "source", "textures")
    prefix = f"T_Operative_Props_Accent_{team_name}"
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            old_path = node.image.filepath
            for suffix in ("D", "R", "M", "ORM", "N", "E"):
                if old_path.endswith(f"_{suffix}.png"):
                    img_path = os.path.join(tex_dir, f"{prefix}_{suffix}.png")
                    if os.path.exists(img_path):
                        node.image.filepath = img_path
                        node.image.reload()
                    break


def setup_studio_environment(scene):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'

    # Configure native HUD stamp overlay
    scene.render.use_stamp = True
    scene.render.use_stamp_date = False
    scene.render.use_stamp_time = False
    scene.render.use_stamp_render_time = False
    scene.render.use_stamp_frame = True
    scene.render.use_stamp_frame_range = False
    scene.render.use_stamp_memory = False
    scene.render.use_stamp_hostname = False
    scene.render.use_stamp_camera = False
    scene.render.use_stamp_lens = False
    scene.render.use_stamp_scene = False
    scene.render.use_stamp_marker = False
    scene.render.use_stamp_filename = False
    scene.render.use_stamp_note = True
    scene.render.stamp_font_size = 18
    scene.render.stamp_background = (0.04, 0.06, 0.10, 0.88)
    scene.render.stamp_foreground = (0.92, 0.97, 1.0, 1.0)

    if not scene.world:
        scene.world = bpy.data.worlds.new("StudioWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.045, 0.055, 0.075, 1.0)
        bg.inputs[1].default_value = 1.1

    # Add studio floor disc
    if "StudioFloor" not in bpy.data.objects:
        bpy.ops.mesh.primitive_circle_add(vertices=64, radius=6.0, fill_type='NGON', location=(0.0, 0.0, -0.002))
        floor = bpy.context.active_object
        floor.name = "StudioFloor"
        fmat = bpy.data.materials.new("M_StudioFloor")
        fmat.use_nodes = True
        bsdf = fmat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.07, 0.08, 0.10, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.35
            bsdf.inputs["Metallic"].default_value = 0.2
        floor.data.materials.append(fmat)

    # Lights
    lights_spec = [
        ("KeyLight", 'AREA', (2.2, -2.6, 2.4), (math.radians(52), 0.0, math.radians(38)), 220.0, (1.0, 0.97, 0.93), 1.8),
        ("FillLight", 'AREA', (-2.4, -2.0, 1.7), (math.radians(60), 0.0, math.radians(-42)), 110.0, (0.72, 0.86, 1.0), 2.2),
        ("RimLight", 'AREA', (0.0, 2.5, 2.3), (math.radians(-52), 0.0, 0.0), 180.0, (0.55, 0.90, 1.0), 1.6),
    ]
    for name, ltype, loc, rot, energy, color, size in lights_spec:
        if name in bpy.data.objects:
            lobj = bpy.data.objects[name]
        else:
            ldata = bpy.data.lights.new(name, type=ltype)
            lobj = bpy.data.objects.new(name, ldata)
            scene.collection.objects.link(lobj)
        lobj.location = loc
        lobj.rotation_euler = Euler(rot, 'XYZ')
        lobj.data.energy = energy
        lobj.data.color = color
        lobj.data.size = size

    if "PresCam" in bpy.data.objects:
        cam_obj = bpy.data.objects["PresCam"]
    else:
        cam_data = bpy.data.cameras.new("PresCam")
        cam_obj = bpy.data.objects.new("PresCam", cam_data)
        scene.collection.objects.link(cam_obj)
    cam_obj.data.sensor_fit = 'VERTICAL'
    scene.camera = cam_obj
    return cam_obj


def annotate_image(img_path, title_text, subtitle_text, badge_text="MORPHRIG v1.2 // VEX OPERATIVE"):
    pass


def encode_mp4(frame_dir, output_mp4, fps=30, audio_path=None, total_duration=None):
    os.makedirs(os.path.dirname(output_mp4), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frame_dir, "frame_%04d.png"),
    ]
    if audio_path and os.path.exists(audio_path):
        cmd += ["-i", audio_path, "-af", "apad"]
        if total_duration:
            cmd += ["-t", f"{total_duration:.2f}"]
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_mp4,
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_mp4,
        ]
    subprocess.run(cmd, check=True)


def render_turntable(scene, cam_obj, arm_obj, lod0, lod1, lod2):
    print("Rendering presentation/turntable.mp4 ...")
    tmp_dir = tempfile.mkdtemp(prefix="morphrig_turntable_")
    try:
        mesh_objs = [lod0, lod1, lod2]
        reset_pose_and_shapes(arm_obj, mesh_objs)
        set_action(arm_obj, mesh_objs, "idle_relaxed")

        total_frames = 240  # 8 seconds @ 30fps
        for idx in range(total_frames):
            f_num = idx + 1
            # Loop the 90-frame idle_relaxed smoothly
            scene.frame_set((idx % 90) + 1)

            # Rotate rig around Z for turntable
            angle = (idx / total_frames) * 2.0 * math.pi * 2.0  # 2 full revolutions

            if idx < 90:
                # Segment 1: Team A (Cyan / Hex-Chevron) full-body
                set_team_variant("TeamA")
                lod0.hide_render = False
                lod1.hide_render = True
                lod2.hide_render = True
                lod0.show_wire = False
                cam_obj.data.lens = 34.0
                radius = 2.85
                cam_x = radius * math.sin(angle)
                cam_y = -radius * math.cos(angle)
                cam_obj.location = (cam_x, cam_y, 1.05)
                direction = Vector((0.0, 0.0, 0.96)) - cam_obj.location
                cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
                title = "TURNTABLE // TEAM A (CYAN HEX-CHEVRON) - LOD0 (39,070 TRIS)"
                sub = "Full-body 360 silhouette, PBR materials, integrated forearm emitter & prop_cell"
            elif idx < 165:
                # Segment 2: Team B (Amber / Crossed-Diamond) + Top-down 50 deg camera check
                set_team_variant("TeamB")
                lod0.hide_render = False
                lod1.hide_render = True
                lod2.hide_render = True
                cam_obj.data.lens = 32.0
                if idx < 130:
                    radius = 2.85
                    cam_x = radius * math.sin(angle)
                    cam_y = -radius * math.cos(angle)
                    cam_obj.location = (cam_x, cam_y, 1.05)
                    direction = Vector((0.0, 0.0, 0.96)) - cam_obj.location
                    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
                    title = "TURNTABLE // TEAM B (AMBER CROSSED-DIAMOND) - VARIANT SWITCH"
                    sub = "Distinct color + non-color geometric emblem pattern on chest & pauldron"
                else:
                    radius = 2.55
                    cam_x = radius * math.sin(angle)
                    cam_y = -radius * math.cos(angle)
                    cam_obj.location = (cam_x, cam_y, 2.85)
                    direction = Vector((0.0, 0.0, 0.95)) - cam_obj.location
                    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
                    title = "TOP-DOWN 50 DEG TACTICAL CAMERA READABILITY (TEAM B)"
                    sub = "Asymmetric cybernetic right arm, dorsal beacon fin & shoulder silhouette"
            else:
                # Segment 3: LOD1 & LOD2 + Wireframe overlay comparison
                set_team_variant("TeamA")
                cam_obj.data.lens = 34.0
                if idx < 205:
                    lod0.hide_render = True
                    lod1.hide_render = False
                    lod2.hide_render = True
                    title = "LOD1 MESH REVIEW // 16,334 TRIANGLES (<= 40,000 TARGET)"
                    sub = "Shared 93-bone deformation skeleton + shared 6 PBR material slots"
                else:
                    lod0.hide_render = True
                    lod1.hide_render = True
                    lod2.hide_render = False
                    title = "LOD2 MESH REVIEW // 5,602 TRIANGLES (<= 20,000 TARGET)"
                    sub = "Shared deformation skeleton & skin weights for crowd / distance rendering"
                radius = 2.85
                cam_x = radius * math.sin(angle)
                cam_y = -radius * math.cos(angle)
                cam_obj.location = (cam_x, cam_y, 1.05)
                direction = Vector((0.0, 0.0, 0.96)) - cam_obj.location
                cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

            out_png = os.path.join(tmp_dir, f"frame_{f_num:04d}.png")
            scene.render.filepath = out_png
            scene.render.stamp_note_text = f"MORPHRIG v1.2 // {title}  --  {sub}"
            bpy.ops.render.render(write_still=True)

        lod0.hide_render = False
        lod1.hide_render = True
        lod2.hide_render = True
        encode_mp4(tmp_dir, os.path.join(PRESENTATION_DIR, "turntable.mp4"), fps=30)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def render_motion_showcase(scene, cam_obj, arm_obj, lod0, lod1, lod2):
    print("Rendering presentation/motion_showcase.mp4 ...")
    tmp_dir = tempfile.mkdtemp(prefix="morphrig_motion_")
    try:
        mesh_objs = [lod0, lod1, lod2]
        lod0.hide_render = False
        lod1.hide_render = True
        lod2.hide_render = True
        set_team_variant("TeamA")

        # Curated showcase segments using exact required_animations.csv IDs
        segments = [
            ("idle_combat", 1, 20, "full", "LOCOMOTION // IDLE_COMBAT", "Ready stance, breathing & secondary neural tether motion"),
            ("walk_f", 1, 22, "full", "LOCOMOTION // WALK_F & 8-WAY CYCLES", "Seamless loop at 1.6 m/s with foot contact events"),
            ("run_f", 1, 18, "full", "LOCOMOTION // RUN_F (5.5 m/s)", "Full-body forward drive, arm counter-swing & spine lean"),
            ("walk_l", 1, 18, "full", "LOCOMOTION // WALK_L STRAFE", "8-way directional strafe locomotion"),
            ("sprint_f", 1, 16, "full", "LOCOMOTION // SPRINT_F", "Full-effort forward sprint"),
            ("dash_f", 1, 16, "wide", "EVADE & DASH // DASH_F (200 CM ROOT MOTION)", "Root-motion burst with dash_start / dash_stop events"),
            ("dash_b", 1, 16, "wide", "EVADE & DASH // DASH_B (200 CM ROOT MOTION)", "Backward root-motion evade dash"),
            ("melee_1", 1, 20, "combat", "MELEE COMBAT // MELEE_1 (SLASH 1)", "Diagonal forearm blade strike + combo_window_open"),
            ("melee_2", 1, 20, "combat", "MELEE COMBAT // MELEE_2 (SLASH 2)", "Reverse backhand cyber-blade cleave"),
            ("melee_3", 1, 24, "combat", "MELEE COMBAT // MELEE_3 (FINISHER)", "Committed spinning lunge finisher"),
            ("ranged_burst", 1, 20, "upper", "RANGED // RANGED_BURST + 9-POINT AIM GRID", "3-round wrist emitter burst + yaw/pitch aim offsets"),
            ("aim_up_right", 1, 10, "upper", "AIM GRID // AIM_UP_RIGHT & AIM_DOWN_LEFT", "9-point additive aim pose grid"),
            ("aim_down_left", 1, 10, "upper", "AIM GRID // AIM_DOWN_LEFT", "Additive yaw/pitch aim targeting"),
            ("reload", 1, 56, "reload", "PROP CONTACT // RELOAD (CELL EJECT & INSERT)", "Left hand grips prop_cell on forearm housing (frames 14-44)"),
            ("channel_loop", 1, 20, "upper", "ABILITY // CHANNEL_LOOP -> MIDPOINT INTERRUPT", "Sustained neural channel interrupted cleanly without frame-0 snap"),
            ("channel_interrupt", 1, 16, "upper", "ABILITY // CHANNEL_INTERRUPT", "Forced channel interruption distinct from completion"),
            ("charge_hold", 1, 16, "combat", "ABILITY // CHARGE_HOLD -> CHARGE_RELEASE", "High-energy wrist capacitor hold and release"),
            ("charge_release", 1, 22, "combat", "ABILITY // CHARGE_RELEASE", "Forceful release with weight transfer"),
            ("deploy", 1, 36, "combat", "PROP DEPLOY // DEPLOY (PROP_BEACON)", "Left hand detaches and tosses tactical beacon at frame 22"),
            ("blink_out", 1, 12, "wide", "TELEPORT // BLINK_OUT -> BLINK_IN", "Phase Compression -> 400 cm displacement -> Phase Emergence"),
            ("blink_in", 1, 14, "wide", "TELEPORT // BLINK_IN", "Arrival reappearance and plant"),
            ("hit_f", 1, 14, "combat", "REACTIONS & CC // HIT_F & STUN_LOOP", "Front impact stagger and electric neural stun"),
            ("stun_loop", 1, 18, "combat", "REACTIONS & CC // STUN_LOOP", "Disoriented stable crowd-control loop"),
            ("knockdown_back", 1, 24, "wide", "KNOCKDOWN // KNOCKDOWN_BACK -> GETUP_BACK", "Full-body fall to ground and recovery"),
            ("getup_back", 1, 30, "wide", "KNOCKDOWN // GETUP_BACK", "Stand from face-up through supporting contacts"),
            ("death_front", 1, 36, "wide", "TERMINAL STATE // DEATH_FRONT -> RESPAWN", "Collapse to floor & orbital drop-in reconstruction"),
            ("respawn", 1, 36, "wide", "RESPAWN // RESPAWN", "Reconstruct and settle into ready living stance"),
        ]

        f_counter = 1
        for act_name, start_f, count_f, cam_mode, title, sub in segments:
            reset_pose_and_shapes(arm_obj, mesh_objs)
            set_action(arm_obj, mesh_objs, act_name)
            for offset in range(count_f):
                scene.frame_set(start_f + offset)
                if cam_mode == "full":
                    cam_obj.data.lens = 33.0
                    cam_obj.location = (1.75, -2.65, 1.08)
                    direction = Vector((0.0, 0.0, 0.96)) - cam_obj.location
                elif cam_mode == "combat":
                    cam_obj.data.lens = 31.0
                    cam_obj.location = (1.90, -2.50, 1.15)
                    direction = Vector((0.0, 0.05, 0.98)) - cam_obj.location
                elif cam_mode == "upper":
                    cam_obj.data.lens = 40.0
                    cam_obj.location = (1.15, -1.85, 1.44)
                    direction = Vector((0.0, 0.0, 1.36)) - cam_obj.location
                elif cam_mode == "reload":
                    cam_obj.data.lens = 45.0
                    cam_obj.location = (0.85, -1.55, 1.42)
                    direction = Vector((-0.02, -0.15, 1.32)) - cam_obj.location
                else:  # wide
                    cam_obj.data.lens = 28.0
                    cam_obj.location = (2.35, -3.20, 1.35)
                    direction = Vector((0.0, 0.25, 0.92)) - cam_obj.location

                cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
                out_png = os.path.join(tmp_dir, f"frame_{f_counter:04d}.png")
                scene.render.filepath = out_png
                scene.render.stamp_note_text = f"MORPHRIG v1.2 // {title}  --  {sub}"
                bpy.ops.render.render(write_still=True)
                f_counter += 1

        encode_mp4(tmp_dir, os.path.join(PRESENTATION_DIR, "motion_showcase.mp4"), fps=30)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def render_face_performance(scene, cam_obj, arm_obj, lod0, lod1, lod2):
    print("Rendering presentation/face_performance.mp4 ...")
    tmp_dir = tempfile.mkdtemp(prefix="morphrig_face_")
    try:
        mesh_objs = [lod0, lod1, lod2]
        lod0.hide_render = False
        lod1.hide_render = True
        lod2.hide_render = True
        set_team_variant("TeamA")

        # Part 1: 436 frames (14.53s) of spoken dialogue performance synchronized with dialogue.wav
        reset_pose_and_shapes(arm_obj, mesh_objs)
        set_action(arm_obj, mesh_objs, "dialogue")

        cam_obj.data.lens = 52.0
        cam_obj.location = (0.16, -0.82, 1.66)
        direction = Vector((0.0, -0.05, 1.65)) - cam_obj.location
        cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

        f_counter = 1
        for f in range(1, 437):
            scene.frame_set(f)
            if f < 135:
                sub = 'Spoken Line 1 (Focus): "Command, this is Vex at the northern relay..."'
            elif f < 290:
                sub = 'Spoken Line 2 (Surprise/Concern): "Wait... someone breached the vault..."'
            else:
                sub = 'Spoken Line 3 (Confidence): "Locking my visor on the signal now..."'

            out_png = os.path.join(tmp_dir, f"frame_{f_counter:04d}.png")
            scene.render.filepath = out_png
            scene.render.stamp_note_text = f"MORPHRIG v1.2 // SPOKEN FACIAL PERFORMANCE  --  {sub}"
            bpy.ops.render.render(write_still=True)
            f_counter += 1

        # Part 2: Expression presets & isolated shape key review (120 frames = 4.0s)
        reset_pose_and_shapes(arm_obj, mesh_objs)
        set_action(arm_obj, mesh_objs, "idle_relaxed")
        scene.frame_set(1)

        expr_review = [
            (None, "EXPRESSION PRESET 1/6 // NEUTRAL", "Baseline relaxed facial state"),
            ("expr_focus", "EXPRESSION PRESET 2/6 // FOCUS", "Brows lowered, squint & firm lip press"),
            ("expr_anger", "EXPRESSION PRESET 3/6 // ANGER", "Sharp brow furrow, nose sneer & bared teeth"),
            ("expr_surprise", "EXPRESSION PRESET 4/6 // SURPRISE", "Raised inner/outer brows, wide eyelids & jaw drop"),
            ("expr_pain", "EXPRESSION PRESET 5/6 // PAIN / EFFORT", "Wince squint, cheek raise & grimace stretch"),
            ("expr_joy_confidence", "EXPRESSION PRESET 6/6 // JOY / CONFIDENCE", "Confident smile, cheek raise & brow lift"),
        ]
        for sk_name, title, sub in expr_review:
            for mobj in mesh_objs:
                if mobj.data.shape_keys and mobj.data.shape_keys.key_blocks:
                    for kb in mobj.data.shape_keys.key_blocks[1:]:
                        kb.value = 1.0 if kb.name == sk_name else 0.0
            for _ in range(20):
                out_png = os.path.join(tmp_dir, f"frame_{f_counter:04d}.png")
                scene.render.filepath = out_png
                scene.render.stamp_note_text = f"MORPHRIG v1.2 // {title}  --  {sub}"
                bpy.ops.render.render(write_still=True)
                f_counter += 1

        total_dur = (f_counter - 1) / 30.0
        encode_mp4(
            tmp_dir,
            os.path.join(PRESENTATION_DIR, "face_performance.mp4"),
            fps=30,
            audio_path=AUDIO_WAV,
            total_duration=total_dur,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    scene = bpy.context.scene
    arm_obj = bpy.data.objects["OperativeRig"]
    lod0 = bpy.data.objects["Operative_LOD0"]
    lod1 = bpy.data.objects["Operative_LOD1"]
    lod2 = bpy.data.objects["Operative_LOD2"]

    cam_obj = setup_studio_environment(scene)
    render_turntable(scene, cam_obj, arm_obj, lod0, lod1, lod2)
    render_motion_showcase(scene, cam_obj, arm_obj, lod0, lod1, lod2)
    render_face_performance(scene, cam_obj, arm_obj, lod0, lod1, lod2)
    print("All 3 presentation videos rendered and encoded successfully!")


if __name__ == "__main__":
    main()
