#!/usr/bin/env python3
"""MorphRig asset pipeline: rebuild the Blender source, bake every clip and export for Unreal.

    python3 MorphRig/tools/export_and_bake.py                 # full rebuild (about 1 h on the reference host)
    python3 MorphRig/tools/export_and_bake.py --from anims    # re-bake clips on the existing rig, then export
    python3 MorphRig/tools/export_and_bake.py --from export   # export only (Operative.blend must exist)
    python3 MorphRig/tools/export_and_bake.py --only walk_f,dialogue --from anims

Stages (each one is a headless Blender run of a script in source/generators/):
  character  build_character.py  meshes, skeleton, skin weights, shape keys, costume, UVs
  textures   build_textures.py   geometry-map bakes + procedural PBR textures -> source/textures/*.png
  lods       build_lods.py       LOD1 / LOD2 (decimated, weights + shape keys transferred)
  rig        build_rig.py        control rig (IK/FK, pose matching, foot roll, face drivers, props)
  anims      build_anims.py      author all clips on the rig, floor / contact fixes, tail simulation,
                                 bake to the export skeleton, motion QA -> docs/qa/motion_qa.json
  save       (in anims)          the result is saved as source/Operative.blend (relative texture paths)
  export     export_fbx.py       export/Operative*.fbx, export/animations/*.fbx + face_curves.json,
                                 export/props/SM_Beacon.fbx, export/textures (copy of the PNGs)
Intermediate .blend files go to MorphRig/build/intermediate (not needed to use the asset).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "source", "generators")
MID = os.path.join(ROOT, "build", "intermediate")
BLENDER = os.environ.get("BLENDER", "blender")
STAGES = ["character", "textures", "lods", "rig", "anims", "export"]


def run(script, *args):
    cmd = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(GEN, script), "--", *args]
    print(">>", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=os.path.dirname(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = os.path.join(MID, script.replace(".py", ".log"))
    with open(log, "w") as fh:
        fh.write(proc.stdout)
    if proc.returncode != 0 or "Traceback" in proc.stdout:
        print(proc.stdout[-4000:])
        sys.exit(f"stage {script} failed (log: {log})")
    print(f"   done in {time.time() - t0:.0f}s (log: {log})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="character", choices=STAGES)
    ap.add_argument("--to", dest="stop", default="export", choices=STAGES)
    ap.add_argument("--only", default="", help="comma separated clip ids for the anims/export stages")
    args = ap.parse_args()
    os.makedirs(MID, exist_ok=True)
    tex = os.path.join(ROOT, "source", "textures")
    blend = os.path.join(ROOT, "source", "Operative.blend")
    todo = STAGES[STAGES.index(args.start):STAGES.index(args.stop) + 1]
    b = lambda n: os.path.join(MID, n)
    if "character" in todo:
        run("build_character.py", "--out", b("stageB.blend"))
    if "textures" in todo:
        run("build_textures.py", "--in", b("stageB.blend"), "--out", b("stageB_tex.blend"), "--tex-dir", tex)
    if "lods" in todo:
        run("build_lods.py", "--in", b("stageB_tex.blend"), "--out", b("stageB_lod.blend"))
    if "rig" in todo:
        run("build_rig.py", "--in", b("stageB_lod.blend"), "--out", b("stageC.blend"))
    if "anims" in todo:
        qa = os.path.join(ROOT, "docs", "qa")
        os.makedirs(qa, exist_ok=True)
        extra = ["--only", args.only] if args.only else []
        # a partial rebuild replaces only the listed clips inside the existing production file
        src = blend if (args.only and os.path.exists(blend) and "rig" not in todo) else b("stageC.blend")
        run("build_anims.py", "--in", src, "--out", blend, "--qa-json",
            os.path.join(qa, "motion_qa.json"), *extra)
    if "export" in todo:
        extra = ["--only", args.only] if args.only else []
        run("export_fbx.py", "--in", blend, "--outdir", os.path.join(ROOT, "export"), *extra)
        dst = os.path.join(ROOT, "export", "textures")
        os.makedirs(dst, exist_ok=True)
        for f in sorted(os.listdir(tex)):
            if f.endswith(".png"):
                shutil.copy2(os.path.join(tex, f), os.path.join(dst, f))
    print("pipeline finished:", ", ".join(todo))


if __name__ == "__main__":
    main()
