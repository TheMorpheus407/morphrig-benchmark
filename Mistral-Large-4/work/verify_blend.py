"""Verify the saved source/Operative_rig.blend against the manifest:
192 actions (96 clips x body+face), frame ranges, pose markers, the
embedded rig_ops.py Text datablock synced from tools/rig_ops.py."""
import json
import os

import bpy

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

m = json.load(open(os.path.join(TASK, "docs", "animation_manifest.json"),
                   encoding="utf-8"))
acts = {a.name: a for a in bpy.data.actions}
print("actions in file: %d" % len(bpy.data.actions))
print("objects: %s" % sorted(o.name for o in bpy.data.objects))
print("armatures: %s" % [a.name for a in bpy.data.armatures])
print("texts: %s" % [t.name for t in bpy.data.texts])

bad = []
for c in m["clips"]:
    a = acts.get(c["id"])
    fa = acts.get(c["face_action"])
    if a is None or fa is None:
        bad.append((c["id"], "missing action"))
        continue
    if not (a.frame_start == 1 and a.frame_end == c["frame_end"]):
        bad.append((c["id"], "body range %s-%s want 1-%d"
                    % (a.frame_start, a.frame_end, c["frame_end"])))
    if not (fa.frame_start == 1 and fa.frame_end == c["frame_end"]):
        bad.append((c["id"], "face range %s-%s want 1-%d"
                    % (fa.frame_start, fa.frame_end, c["frame_end"])))
    got = sorted((mk.name, mk.frame) for mk in a.pose_markers)
    want = sorted((mk["name"], mk["frame"]) for mk in c["markers"])
    if got != want:
        bad.append((c["id"], "markers %s want %s" % (got, want)))


def n_fcurves(a):
    n = 0
    for layer in a.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                n += len(cb.fcurves)
    return n


for c in m["clips"]:
    if n_fcurves(acts[c["id"]]) == 0 or n_fcurves(acts[c["face_action"]]) == 0:
        bad.append((c["id"], "no keyframed fcurves"))
print("clips checked: %d, problems: %d" % (len(m["clips"]), len(bad)))
for b in bad[:20]:
    print("   BAD %s: %s" % b)

t = bpy.data.texts.get("rig_ops.py")
if t is None:
    print("rig_ops.py text block: MISSING")
else:
    src = open(os.path.join(TASK, "tools", "rig_ops.py"),
               encoding="utf-8").read()
    body = t.as_string()
    print("rig_ops.py text block: %d bytes, use_module=%s, matches tools/rig_ops.py: %s"
          % (len(body), t.use_module, body == src))

# spot-check one clip's fcurve count and a shape-key action
sp = m["clips"][0]
a = acts[sp["id"]]
print("spot %s: %d fcurves, frame_end=%d, markers=%d"
      % (sp["id"], n_fcurves(a), a.frame_end, len(a.pose_markers)))
print("VERIFY BLEND DONE, bad=%d" % len(bad))
