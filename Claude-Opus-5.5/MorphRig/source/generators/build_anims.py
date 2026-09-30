"""Stage C2: author all clips on MR_Rig, bake them to MR_Skeleton, run motion QA.

Usage:
  blender -b --factory-startup -P build_anims.py -- --in stageC.blend --out Operative.blend [--only id,id]
"""
import sys
import os
import json
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import bpy
import mr_anim
import mr_clip
import mr_qa
import mr_floorfix
import mr_contactfix
import mr_secondary
import mr_face_list
import clips_all


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--qa-json", default="")
    ap.add_argument("--bakes-dir", default="")
    return ap.parse_args(argv)


def set_meshes_enabled(on):
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith("MR_"):
            o.hide_viewport = not on


def main():
    args = parse()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.inp))
    sc = bpy.context.scene
    sc.render.fps = 30
    rig = bpy.data.objects["MR_Rig"]
    skel = bpy.data.objects["MR_Skeleton"]
    R = mr_anim.Realizer(rig)
    only = [x for x in args.only.split(",") if x]
    # held pose clips copy the last frame of their source clip: rebuild them together
    for src, dep in (("death_front", "dead_front"), ("death_back", "dead_back")):
        if src in only and dep not in only:
            only.append(dep)
    clips = clips_all.build_all(R, only)
    set_meshes_enabled(False)
    report = {}
    t0 = time.time()
    final_keys = {}
    # clips whose pose is copied from another clip's last frame are processed after it
    clips.sort(key=lambda c: 1 if c.extra.get("pose_from") else 0)
    for clip in clips:
        keyed = mr_clip.prepare_keys(R, clip)
        fixlog = []
        src = clip.extra.get("pose_from")
        if src and src in final_keys:
            last = final_keys[src]
            keyed = [(0.0, last, "LINEAR"), (float(clip.frames), last, "LINEAR")]
            clip.extra["no_floor_fix"] = True
        if not clip.extra.get("no_floor_fix"):
            keyed, act, nfix = mr_floorfix.floor_fix(rig, R, clip, keyed, log=fixlog)
        if not (src and src in final_keys) and not clip.extra.get("no_contact_fix"):
            keyed, ncf = mr_contactfix.contact_fix(rig, R, clip, keyed, log=fixlog)
            if ncf and not clip.extra.get("no_floor_fix"):
                keyed, act, nfix = mr_floorfix.floor_fix(rig, R, clip, keyed, log=fixlog)
        if src and src in final_keys:
            # exact copy of the source clip's final frame, secondary motion included
            clip.layers = []
            clip.dense = False
        elif clip.extra.get("no_tail_sim"):
            pass
        else:
            # secondary motion (hair tail) simulated against the final body motion, then baked
            act, _ = mr_clip.write_keyed(rig, clip, keyed)
            mr_clip.assign_action(rig, act)
            sim = mr_secondary.simulate_tail(rig, clip.frames, loop=clip.loop or clip.form == "pose")
            clip.layers.append(mr_secondary.tail_layer(sim))
        act, series = mr_clip.write_keyed(rig, clip, keyed)
        mr_clip.assign_action(rig, act)
        # channel values at the final frame as played (pose clips copy them to connect exactly)
        final_keys[clip.id] = {k: np.asarray(v[-1], float).copy() for k, v in series.items()}
        sc.frame_start, sc.frame_end = 0, clip.frames
        baked = mr_clip.bake_skeleton(skel, rig, 0, clip.frames, props=mr_face_list.FACE_PROPS)
        bact = mr_clip.write_baked_action(skel, baked, f"SK_{clip.id}")
        for f, nm in clip.markers:
            m = bact.pose_markers.new(nm)
            m.frame = f
        bact["mr_clip"] = clip.id
        qa = mr_qa.check_clip(clip, baked)
        qa.update(mr_qa.mesh_floor_check(clip.frames, step=1))
        qa.update(mr_qa.body_clearance(clip.frames, step=2))
        qa["fixes"] = len(fixlog)
        qa["fix_log"] = [list(map(str, x)) for x in fixlog][:40]
        report[clip.id] = qa
        if args.bakes_dir:
            os.makedirs(args.bakes_dir, exist_ok=True)
            np.savez_compressed(os.path.join(args.bakes_dir, clip.id + ".npz"),
                                **{f"loc__{n}": baked["loc"][n] for n in baked["bones"]},
                                **{f"rot__{n}": baked["rot"][n] for n in baked["bones"]},
                                **{f"scl__{n}": baked["scl"][n] for n in baked["bones"]},
                                **{f"prop__{p}": baked["props"][p] for p in baked["props"]})
        meta = dict(id=clip.id, frames=clip.frames, loop=clip.loop, form=clip.form, root=clip.root,
                    speed_cms=clip.speed, layer=clip.layer, entry=clip.entry, exit=clip.exit,
                    markers=clip.markers, notes=clip.notes, extra=clip.extra)
        act["mr_meta"] = json.dumps(meta)
        bact["mr_meta"] = json.dumps(meta)
        print("CLIP", clip.id, clip.frames, "QA", json.dumps(qa))
    # leave the rig on the first clip, skeleton constraints active
    set_meshes_enabled(True)
    if clips:
        mr_clip.assign_action(rig, bpy.data.actions[f"RIG_{clips[0].id}"])
    if args.qa_json:
        if only and os.path.exists(args.qa_json):
            # partial rebuild: keep the QA entries of the clips that were not rebuilt
            with open(args.qa_json) as fh:
                prev = json.load(fh)
            prev.update(report)
            report = prev
        with open(args.qa_json, "w") as fh:
            json.dump(report, fh, indent=1)
    # texture paths relative to the saved file (the asset must open from any location)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    for img in bpy.data.images:
        if img.filepath and img.source == 'FILE':
            img.filepath = bpy.path.relpath(bpy.path.abspath(img.filepath), start=out_dir)
    sc.frame_set(0)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out), relative_remap=False)
    print("SAVED", args.out, "clips", len(clips), "time", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
