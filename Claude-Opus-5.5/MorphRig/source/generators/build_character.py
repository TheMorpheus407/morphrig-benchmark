"""Stage A/B: build the MorphRig Operative meshes, export skeleton and skin weights.

Usage:
  blender -b --factory-startup -P build_character.py -- --out /abs/stageB.blend
"""
import sys
import os
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import bpy
import mr_blender as B
import mr_body
import mr_head
import mr_hand
import mr_gear
import mr_skeleton
import mr_skin
import mr_face
import mr_mouth
import mr_costume
import mr_uv
import mr_parts
import json
from mr_params import H, EYE_R, J


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def build_armature(bone_list, name="MR_Skeleton", coll=None):
    ad = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, ad)
    (coll or bpy.context.scene.collection).objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for b in bone_list:
        eb = ad.edit_bones.new(b["name"])
        eb.head = tuple(b["head"])
        eb.tail = tuple(b["tail"])
        eb.align_roll(tuple(b["zref"]))
        eb.use_deform = b["deform"]
        ebs[b["name"]] = eb
    for b in bone_list:
        if b["parent"]:
            ebs[b["name"]].parent = ebs[b["parent"]]
            ebs[b["name"]].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    ad.display_type = 'OCTAHEDRAL'
    ob.show_in_front = True
    return ob


def bind(obj, arm, weights):
    for bn, w in weights.items():
        idx = np.nonzero(w > 0)[0]
        if len(idx) == 0:
            continue
        vg = obj.vertex_groups.get(bn) or obj.vertex_groups.new(name=bn)
        # group by identical weight values for speed
        vals = w[idx]
        for val in np.unique(np.round(vals, 4)):
            sel = idx[np.round(vals, 4) == val]
            vg.add(sel.tolist(), float(val), 'REPLACE')
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_deform_preserve_volume = False
    obj.parent = arm


def eyeball_mesh(side):
    """Eyeball with a subtle cornea bulge; pole at the pupil (-Y) for planar iris UVs."""
    from mr_meshkit import Mesh, make_consistent
    segs, rings = 32, 20
    c = H["eye_" + side]
    verts = [c + np.array([0, -1.0, 0]) * (EYE_R + 0.0008)]
    for i in range(1, rings):
        th = np.pi * i / rings
        r = EYE_R
        if th < np.radians(32):
            r += 0.0008 * np.cos(th / np.radians(32) * np.pi / 2) ** 2
        for j in range(segs):
            ph = 2 * np.pi * j / segs
            d = np.array([np.sin(th) * np.cos(ph), -np.cos(th), np.sin(th) * np.sin(ph)])
            verts.append(c + d * r)
    verts.append(c + np.array([0, 1.0, 0]) * EYE_R)
    faces = []
    for j in range(segs):
        faces.append((0, 1 + j, 1 + (j + 1) % segs))
    for i in range(rings - 2):
        for j in range(segs):
            a = 1 + i * segs + j
            b = 1 + i * segs + (j + 1) % segs
            faces.append((a, a + segs, b + segs, b))
    last = len(verts) - 1
    base = 1 + (rings - 2) * segs
    for j in range(segs):
        faces.append((base + j, last, base + (j + 1) % segs))
    m = Mesh(np.array(verts), faces)
    make_consistent(m, outward_point=c)
    return m


def main():
    args = parse()
    t0 = time.time()
    B.clear_scene()
    sc = bpy.context.scene
    col_char = bpy.data.collections.new("MR_Character")
    col_rig = bpy.data.collections.new("MR_Rig")
    sc.collection.children.link(col_char)
    sc.collection.children.link(col_rig)
    # --- skeleton
    bl = mr_skeleton.build_bone_list()
    bones = {b["name"]: (b["head"], b["tail"]) for b in bl}
    arm = build_armature(bl, "MR_Skeleton", col_rig)
    # --- meshes
    suit, _ = mr_body.build_suit()
    head, _ = mr_head.build_head()
    mr_uv.head_seams(head)
    hl_local, _ = mr_hand.build_organic_hand()
    hand_l = mr_hand.place(hl_local, "l")
    parts = []
    parts.append(("MR_Suit", suit, mr_skin.suit_weights(suit, bones)))
    parts.append(("MR_Head", head, mr_skin.head_weights(head, bones)))
    parts.append(("MR_HandL", hand_l, mr_skin.hand_weights(hand_l, bones, "l")))
    for sd in ("l", "r"):
        bt = mr_gear.build_boot(sd)
        mr_uv.ring_seams(bt, bt.rings)
        parts.append((f"MR_Boot_{sd.upper()}", bt, mr_skin.boot_weights(bt, bones, sd)))
    cyber = mr_gear.build_cyber_arm() + mr_gear.build_cyber_hand() + [mr_gear.build_blade()]
    from mr_meshkit import Mesh
    cy = Mesh()
    cyw = {}
    for pc in cyber:
        mr_parts.tag(pc, pc.part)
        off = cy.append(pc)
        bone = pc.bind.split(":", 1)[1]
        w = np.zeros(cy.nv)
        w[off:off + pc.nv] = 1.0
        for k in cyw:
            cyw[k] = np.concatenate([cyw[k], np.zeros(cy.nv - len(cyw[k]))])
        cyw[bone] = cyw.get(bone, np.zeros(cy.nv)) + w
    for k in cyw:
        cyw[k] = np.concatenate([cyw[k], np.zeros(cy.nv - len(cyw[k]))])
    parts.append(("MR_CyberArm", cy, cyw))
    a = mr_gear.cyber_anchor_points()
    cell = mr_gear.build_power_cell(a["cell_slot"], a["cell_axis"], a["cell_up"])
    beacon = mr_gear.build_beacon(mr_skeleton.BEACON_HOLSTER, np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    parts.append(("MR_PropCell", cell, {"prop_cell": np.ones(cell.nv)}))
    parts.append(("MR_PropBeacon", beacon, {"prop_beacon": np.ones(beacon.nv)}))
    for sd in ("l", "r"):
        eb = eyeball_mesh(sd)
        parts.append((f"MR_Eye_{sd.upper()}", eb, {f"eye_{sd}": np.ones(eb.nv)}))
    mouth = mr_mouth.build_mouth()
    mouth.face_attrs["part"] = [mr_parts.pid(next(g for g in ("teeth_upper", "teeth_lower", "gum_upper", "gum_lower",
                                                              "tongue") if mouth.groups[g][list(f)].all()))
                                for f in mouth.f]
    parts.append(("MR_Mouth", mouth, mr_mouth.mouth_weights(mouth, bones)))
    # costume (vest, collar, belt gear, pauldron, knee pads, bracer, comm, hair)
    suit_w = parts[0][2]
    costume = mr_costume.assemble(mr_costume.build_all(), bones, suit.v, suit_w)
    gear_m, gear_w, gear_mats = costume["gear"]
    hair_m, hair_w, hair_mats = costume["hair"]
    tail_m, tail_w, tail_mats = costume["tail"]
    parts.append(("MR_Gear", gear_m, gear_w))
    parts.append(("MR_Hair", hair_m, hair_w))
    parts.append(("MR_HairTail", tail_m, tail_w))
    mats = {
        "MR_Suit": B.preview_material("M_Suit", (0.07, 0.075, 0.09), rough=0.7),
        "MR_Head": B.preview_material("M_Skin", (0.55, 0.38, 0.30), rough=0.45, sss=0.1),
        "MR_HandL": B.preview_material("M_Skin", (0.55, 0.38, 0.30), rough=0.45, sss=0.1),
        "gear": B.preview_material("M_Gear", (0.20, 0.21, 0.23), rough=0.35, metallic=0.6),
        "prop": B.preview_material("M_Props", (0.0, 0.6, 0.8), rough=0.3),
        "eye": B.preview_material("M_Eye", (0.8, 0.8, 0.78), rough=0.1),
        "MR_Mouth": B.preview_material("M_Mouth", (0.85, 0.80, 0.74), rough=0.3),
        "armor": B.preview_material("M_Armor", (0.62, 0.62, 0.60), rough=0.4),
        "hair": B.preview_material("M_Hair", (0.05, 0.035, 0.03), rough=0.55),
    }
    mats["suit"] = mats["MR_Suit"]
    mats["cyber"] = mats["gear"]
    multi = {"MR_Gear": [mats[k] for k in gear_mats], "MR_Hair": [mats[k] for k in hair_mats],
             "MR_HairTail": [mats[k] for k in tail_mats]}
    single = {"MR_Suit": "suit", "MR_Head": "head", "MR_HandL": "hand_l", "MR_Boot_L": "boot", "MR_Boot_R": "boot",
              "MR_PropCell": "power_cell", "MR_PropBeacon": "beacon", "MR_Eye_L": "eye", "MR_Eye_R": "eye"}
    # head regions from the generator's vertex groups (mouth interior, lips, lid margins)
    g = head.groups
    inner = g["mouth_bag"].copy()
    for k in range(1, 6):
        inner |= g[f"mouth_in{k}"]
    lips = g["lip_L0"] | g["lip_L1"] | g["lip_L2"] | g["lip_L3"]
    lipb = lips | g["lip_L4"]
    lids = g["lid_A_l"] | g["lid_B_l"] | g["lid_A_r"] | g["lid_B_r"]
    hp = []
    for f in head.f:
        fl = list(f)
        if inner[fl].all():
            hp.append(mr_parts.pid("mouth_inner"))
        elif lips[fl].all():
            hp.append(mr_parts.pid("lips"))
        elif lipb[fl].all():
            hp.append(mr_parts.pid("lip_border"))
        elif lids[fl].all():
            hp.append(mr_parts.pid("lid_margin"))
        else:
            hp.append(mr_parts.pid("head"))
    head.face_attrs["part"] = hp
    suit_regions = ["suit_torso", "suit_arm_l", "suit_arm_r", "suit_leg_l", "suit_leg_r"]
    suit.face_attrs["part"] = [mr_parts.pid(suit_regions[int(x or 0)]) for x in suit.face_attrs["part"]]
    for name, m, w in parts:
        if name in single and "part" not in m.face_attrs:
            mr_parts.tag(m, single[name])
    for name, m, w in parts:
        used = np.zeros(m.nv, bool)
        for f in m.f:
            used[list(f)] = True
        assert used.all(), f"{name}: {int((~used).sum())} loose vertices"
        mat = mats.get(name) or (mats["prop"] if "Prop" in name else mats["eye"] if "Eye" in name else mats["gear"])
        obj = B.to_object(name, m, collection=col_char, materials=multi.get(name, [mat]), groups=False)
        bind(obj, arm, w)
        if name == "MR_Head":
            deltas = mr_face.build_shapes(m, m.sym_pairs)
            mr_face.apply_shape_keys(obj, deltas)
            print("SHAPEKEYS", len(deltas))
        print("PART", name, "verts", m.nv, "tris", m.tri_count(), "bones", len(w))
    # final material slots + UV layout per texture set
    objs = {name: bpy.data.objects[name] for name, _, _ in parts}
    mr_uv.assign_materials(objs, {"MR_Gear": gear_mats, "MR_Hair": hair_mats, "MR_HairTail": tail_mats})
    groups = mr_uv.layout(objs)
    print("UV sets", {k: [o.name for o, _ in v] for k, v in groups.items()})
    sc["mr_part_names"] = json.dumps(mr_parts.NAMES)
    sc["mr_build_seconds"] = time.time() - t0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("SAVED", args.out, "in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
