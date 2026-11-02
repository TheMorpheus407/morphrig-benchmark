"""Render the three MORPHRIG presentation videos.

    blender -b --factory-startup -P source/generators/render_videos.py -- \
        --outdir presentation [--only turntable|motion|face] [--samples N]

Produces
    presentation/turntable.mp4         the Operative seen from all sides
    presentation/motion_showcase.mp4   a sequence of the delivered clips
    presentation/face_performance.mp4  the spoken performance, close up

Cycles on the CPU renders the delivered asset, so the videos show exactly
what was built.  The frames are written as PNG and encoded with ffmpeg.
"""

import math
import os
import subprocess
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FPS = 30

# the sequence shown in the motion showcase: clip, number of frames
SHOWCASE = [
    ("idle_combat", 45),
    ("walk_f", 45),
    ("run_f", 45),
    ("dash_f", 15),
    ("melee_1", 27),
    ("cast_directional", 27),
    ("aim_level_center", 30),
    ("charge_start", 21),
    ("channel_loop", 30),
    ("hit_f", 15),
    ("death_front", 45),
    ("respawn", 45),
]


# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------

def build_scene(samples, res):
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    scn.cycles.device = 'CPU'
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 4
    scn.render.resolution_x = res[0]
    scn.render.resolution_y = res[1]
    scn.render.film_transparent = False
    scn.render.image_settings.file_format = 'PNG'
    # AgX rolls the highlights off, so the bright suit does not clip
    for transform in ('AgX', 'Filmic', 'Standard'):
        try:
            scn.view_settings.view_transform = transform
            break
        except Exception:
            continue
    try:
        scn.view_settings.look = 'None'
    except Exception:
        pass
    scn.view_settings.exposure = 0.0
    scn.view_settings.gamma = 1.0
    scn.render.fps = FPS

    # dark studio world with a soft gradient
    world = bpy.data.worlds.new("Studio")
    scn.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.020, 0.024, 0.032, 1.0)
    bg.inputs[1].default_value = 1.0

    # three point rig
    for name, loc, energy, size, color in (
            ("Key", (2.2, -2.6, 2.8), 380.0, 2.2, (1.0, 0.93, 0.86)),
            ("Fill", (-2.6, -1.6, 1.4), 120.0, 3.0, (0.55, 0.68, 1.0)),
            ("Rim", (0.6, 2.8, 2.4), 260.0, 1.6, (0.40, 0.80, 1.0)),
            ("Bounce", (0.0, -1.2, 0.2), 45.0, 4.0, (1.0, 0.62, 0.30))):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = Vector((0.0, 0.0, 1.0)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        scn.collection.objects.link(ob)

    # floor
    bpy.ops.mesh.primitive_plane_add(size=24.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.name = "Floor"
    mat = bpy.data.materials.new("FloorMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.035, 0.040, 0.052, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.0
    floor.data.materials.append(mat)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    scn.collection.objects.link(cam)
    scn.camera = cam
    return cam, floor


def place_camera(cam, location, target):
    cam.location = location
    d = Vector(target) - Vector(location)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def set_clip(rig, mesh, clip):
    """Bind the body action and the face action of a clip."""
    rig.animation_data.action = bpy.data.actions.get("ACT_%s" % clip)
    sk = mesh.data.shape_keys
    if sk and sk.animation_data:
        sk.animation_data.action = bpy.data.actions.get("ACT_%s_face" % clip)


def render_frames(cam, rig, mesh, seq_dir, name, res, samples, frames):
    """Render a list of (clip, local_frame) pairs to PNG frames.

    Frames that already exist are skipped, so an interrupted run resumes.
    """
    os.makedirs(seq_dir, exist_ok=True)
    scn = bpy.context.scene
    scn.render.resolution_x = res[0]
    scn.render.resolution_y = res[1]
    scn.cycles.samples = samples

    t0 = time.time()
    done = 0
    for index, (clip, local_frame) in enumerate(frames):
        path = os.path.join(seq_dir, "f%05d.png" % index)
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            done += 1
            continue
        set_clip(rig, mesh, clip)
        scn.frame_set(local_frame)
        scn.render.filepath = os.path.join(seq_dir, "f%05d" % index)
        bpy.ops.render.render(write_still=True)
        if index % 20 == 0:
            print("RENDER %s %d/%d %.1fs" % (name, index, len(frames),
                                             time.time() - t0), flush=True)
    print("RENDER_DONE %s %d frames %.1fs" % (name, len(frames),
                                               time.time() - t0), flush=True)
    return seq_dir


def encode(seq_dir, outfile, fps, audio=None):
    """Encode the PNG frames into an H.264 mp4."""
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
           "-i", os.path.join(seq_dir, "f%05d.png")]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-preset", "medium"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [outfile]
    subprocess.run(cmd, check=True)
    size = os.path.getsize(outfile) / 1048576.0
    print("VIDEO %s %.1f MB" % (outfile, size), flush=True)


# ---------------------------------------------------------------------------
# the three videos
# ---------------------------------------------------------------------------

def make_turntable(outdir, rig, mesh, samples):
    scn = bpy.context.scene
    total = 180
    frames = [("idle_combat", 1 + (index % 30)) for index in range(total)]

    # the camera makes the turn so the lights stay put
    dist = 3.9
    height = 0.98

    seq_dir = os.path.join(outdir, "_frames_turntable")
    scn.render.resolution_x = 1080
    scn.render.resolution_y = 1920
    scn.cycles.samples = samples

    t0 = time.time()
    for index in range(total):
        path = os.path.join(seq_dir, "f%05d.png" % index)
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            continue
        angle = 2.0 * math.pi * index / total
        set_clip(rig, mesh, "idle_combat")
        scn.frame_set(1 + (index % 30))
        place_camera(cam, (dist * math.sin(angle),
                           -dist * math.cos(angle), height),
                     (0.0, 0.0, 0.92))
        os.makedirs(seq_dir, exist_ok=True)
        scn.render.filepath = os.path.join(seq_dir, "f%05d" % index)
        bpy.ops.render.render(write_still=True)
        if index % 20 == 0:
            print("RENDER turntable %d/%d %.1fs" % (index, total,
                                                    time.time() - t0), flush=True)
    print("RENDER_DONE turntable %d frames %.1fs" % (total, time.time() - t0),
          flush=True)
    encode(seq_dir, os.path.join(outdir, "turntable.mp4"), FPS)
    return seq_dir


def make_motion(outdir, rig, mesh, samples):
    scn = bpy.context.scene
    frames = []
    for clip, count in SHOWCASE:
        for local in range(1, count + 1):
            frames.append((clip, local))

    seq_dir = os.path.join(outdir, "_frames_motion")
    scn.render.resolution_x = 1280
    scn.render.resolution_y = 720
    scn.cycles.samples = samples

    t0 = time.time()
    for index, (clip, local) in enumerate(frames):
        path = os.path.join(seq_dir, "f%05d.png" % index)
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            continue
        set_clip(rig, mesh, clip)
        scn.frame_set(local)
        # follow the character so the root motion dash stays in frame
        target = mesh.matrix_world @ Vector((0.0, 0.0, 0.98))
        place_camera(cam, (target.x + 3.05, target.y - 4.25, target.z + 0.62),
                     (target.x, target.y, target.z - 0.06))
        os.makedirs(seq_dir, exist_ok=True)
        scn.render.filepath = os.path.join(seq_dir, "f%05d" % index)
        bpy.ops.render.render(write_still=True)
        if index % 20 == 0:
            print("RENDER motion %d/%d %.1fs" % (index, len(frames),
                                                 time.time() - t0), flush=True)
    print("RENDER_DONE motion %d frames %.1fs" % (len(frames), time.time() - t0),
          flush=True)
    encode(seq_dir, os.path.join(outdir, "motion_showcase.mp4"), FPS)
    return seq_dir


def make_face(outdir, rig, mesh, samples):
    scn = bpy.context.scene
    # the dialogue is 12.53 s long, the video ends with the voice
    total = 376
    seq_dir = os.path.join(outdir, "_frames_face")
    scn.render.resolution_x = 1080
    scn.render.resolution_y = 1080
    scn.cycles.samples = samples

    t0 = time.time()
    for index in range(total):
        path = os.path.join(seq_dir, "f%05d.png" % index)
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            continue
        set_clip(rig, mesh, "dialogue")
        scn.frame_set(1 + index)
        head = mesh.matrix_world @ Vector((0.0, -0.02, 1.655))
        # a slow push in and a slight drift keep the face alive
        drift = 0.16 * math.sin(index / total * math.pi)
        place_camera(cam, (head.x + 0.09 + drift * 0.35, head.y - 0.46,
                           head.z + 0.02 - drift * 0.22),
                     (head.x, head.y + 0.02, head.z))
        os.makedirs(seq_dir, exist_ok=True)
        scn.render.filepath = os.path.join(seq_dir, "f%05d" % index)
        bpy.ops.render.render(write_still=True)
        if index % 20 == 0:
            print("RENDER face %d/%d %.1fs" % (index, total, time.time() - t0),
                  flush=True)
    print("RENDER_DONE face %d frames %.1fs" % (total, time.time() - t0),
          flush=True)

    audio = os.path.join(ROOT, "source", "audio", "dialogue.wav")
    encode(seq_dir, os.path.join(outdir, "face_performance.mp4"), FPS,
           audio=audio if os.path.exists(audio) else None)
    return seq_dir


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(flag, default=None):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    outdir = os.path.abspath(arg("--outdir", os.path.join(ROOT, "presentation")))
    only = arg("--only")
    samples = int(arg("--samples", 24))
    os.makedirs(outdir, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "source", "Operative.blend"))
    rig = bpy.data.objects.get("Operative_Rig")
    mesh = bpy.data.objects.get("Operative_Body")
    if rig is None or mesh is None:
        raise SystemExit("rig or body missing")

    # The LOD bodies are alternatives of the same character, they must not be
    # rendered on top of LOD0.
    for name in ("Operative_Body_LOD1", "Operative_Body_LOD2"):
        other = bpy.data.objects.get(name)
        if other is not None:
            other.hide_render = True
            other.hide_viewport = True

    global cam
    cam, _floor = build_scene(samples, (720, 1080))
    scn = bpy.context.scene
    scn.frame_start = 1
    scn.frame_end = 600

    if only in (None, "turntable"):
        make_turntable(outdir, rig, mesh, samples)
    if only in (None, "motion"):
        make_motion(outdir, rig, mesh, samples)
    if only in (None, "face"):
        make_face(outdir, rig, mesh, samples)

    print("VIDEOS_DONE")


if __name__ == "__main__":
    main()
