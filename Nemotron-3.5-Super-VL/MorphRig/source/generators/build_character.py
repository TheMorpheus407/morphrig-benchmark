#!/usr/bin/env python3
"""MORPHRIG - Build the Operative character (separate mesh parts, materials).
Run: blender -b --factory-startup -P build_character.py"""
import bpy
import bmesh
import math
from mathutils import Vector, Matrix, Euler

MORPH = "/home/candidate/workspace/MorphRig"
BLEND = f"{MORPH}/source/Operative.blend"

def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    if parent:
        parent.children.link(col)
    else:
        bpy.context.scene.collection.children.link(col)
    return col

COLS = {}
def ensure_col(name, parent=None):
    if name not in COLS:
        COLS[name] = new_collection(name, parent)
    return COLS[name]

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)
    for c in list(bpy.data.cameras):
        bpy.data.cameras.remove(c)
    for l in list(bpy.data.lights):
        bpy.data.lights.remove(l)
    for im in list(bpy.data.images):
        bpy.data.images.remove(im)
    for mt in list(bpy.data.materials):
        bpy.data.materials.remove(mt)
    for col in list(bpy.data.collections):
        if col.name not in ("Scene Collection",):
            bpy.data.collections.remove(col)

def active_obj():
    return bpy.context.view_layer.objects.active

def select(obj, state=True):
    obj.select_set(state)

def make_active(obj):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)

def link(obj, col_name="Character"):
    col = ensure_col(col_name)
    col.objects.link(obj)
    for c in obj.users_collection:
        if c.name != col_name:
            c.objects.unlink(obj)

def mat(name, base=(0.8,0.8,0.8), rough=0.45, metal=0.0, emissive=(0,0,0), emissive_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    links = m.node_tree.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*base, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if emissive_strength > 0:
        emi = nodes.new('ShaderNodeEmission')
        emi.inputs['Color'].default_value = (*emissive, 1.0)
        emi.inputs['Strength'].default_value = emissive_strength
        add = nodes.new('ShaderNodeAddShader')
        links.new(bsdf.outputs['BSDF'], add.inputs[0])
        links.new(emi.outputs['Emission'], add.inputs[1])
        links.new(add.outputs['Shader'], out.inputs['Surface'])
    else:
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m

def set_mat(obj, material):
    obj.data.materials.clear()
    obj.data.materials.append(material)

def smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True

def flat(obj):
    for p in obj.data.polygons:
        p.use_smooth = False

def apply_transform(obj):
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

def uv_smart(obj):
    make_active(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

def cyl(radius, depth, loc, rot=(0,0,0), name="Cyl", segments=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=loc, rotation=rot, vertices=segments)
    o = active_obj(); o.name = name
    return o

def sphere(radius, loc, rot=(0,0,0), name="Sph", segments=32, ring_count=16):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=loc, rotation=rot, segments=segments, ring_count=ring_count)
    o = active_obj(); o.name = name
    return o

def cube(size, loc, rot=(0,0,0), name="Cube"):
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc, rotation=rot)
    o = active_obj(); o.name = name
    return o

def cone(radius1, radius2, depth, loc, rot=(0,0,0), name="Cone", segments=16):
    bpy.ops.mesh.primitive_cone_add(radius1=radius1, radius2=radius2, depth=depth, location=loc, rotation=rot, vertices=segments)
    o = active_obj(); o.name = name
    return o

clear_scene()

# ---------------- Materials (<=8 total for character+props) ----------------
M_SKIN = mat("M_Skin", base=(0.88,0.74,0.64), rough=0.55, metal=0.0)
M_CYBER = mat("M_CyberMetal", base=(0.20,0.22,0.25), rough=0.35, metal=0.9)
M_GLOW = mat("M_GlowTeal", base=(0.0,0.1,0.1), rough=0.2, metal=0.1, emissive=(0.05,0.9,0.75), emissive_strength=6.0)
M_ARMOR = mat("M_Armor", base=(0.13,0.15,0.18), rough=0.3, metal=0.85)
M_CLOTH = mat("M_Cloth", base=(0.09,0.09,0.11), rough=0.85, metal=0.0)
M_TEAM_BLUE = mat("M_TeamBlue", base=(0.0,0.1,0.2), rough=0.2, metal=0.6, emissive=(0.04,0.5,0.9), emissive_strength=4.0)
M_TEAM_ORANGE = mat("M_TeamOrange", base=(0.1,0.05,0.0), rough=0.2, metal=0.6, emissive=(0.9,0.2,0.05), emissive_strength=4.0)
M_EYE = mat("M_Eye", base=(0.1,0.2,0.35), rough=0.1, metal=0.1)
M_HAIR = mat("M_Hair", base=(0.05,0.05,0.06), rough=0.6, metal=0.0)

MATS = [M_SKIN, M_CYBER, M_GLOW, M_ARMOR, M_CLOTH, M_TEAM_BLUE, M_TEAM_ORANGE, M_EYE, M_HAIR]

# ===== Helper: place object =====
def place(obj, loc, rot=(0,0,0), scale=(1,1,1)):
    obj.location = Vector(loc)
    obj.rotation_euler = Euler(rot)
    obj.scale = Vector(scale)
    apply_transform(obj)

# ===== BODY PARTS (organic, skinned) =====
# Head
head = sphere(0.125, (0, 0, 1.60), name="Head")
head.scale = (1.0, 0.88, 1.05)
apply_transform(head)
bm = bmesh.new(); bm.from_mesh(head.data)
for v in bm.verts:
    if v.co.z < 1.55:
        v.co.z -= 0.02
        v.co.y += 0.01
    if v.co.z < 1.52 and abs(v.co.x) < 0.09 and abs(v.co.y) < 0.09:
        v.co *= 0.85
        v.co.z = 1.52
bm.to_mesh(head.data); bm.free()
smooth(head)
set_mat(head, M_SKIN)
link(head)

# Eyes
eye_l = sphere(0.045, (-0.065, 0.13, 1.625), name="Eye_L"); smooth(eye_l); set_mat(eye_l, M_EYE); link(eye_l)
eye_r = sphere(0.045, (0.065, 0.13, 1.625), name="Eye_R"); smooth(eye_r); set_mat(eye_r, M_EYE); link(eye_r)
pupil_l = sphere(0.022, (-0.065, 0.144, 1.625), name="Pupil_L"); smooth(pupil_l); set_mat(pupil_l, M_EYE); link(pupil_l)
pupil_r = sphere(0.022, (0.065, 0.144, 1.625), name="Pupil_R"); smooth(pupil_r); set_mat(pupil_r, M_EYE); link(pupil_r)

# Torso
torso = cube(1.0, (0, 0, 1.22), name="Torso")
torso.scale = (0.34, 0.26, 0.55)
apply_transform(torso)
bm = bmesh.new(); bm.from_mesh(torso.data)
for v in bm.verts:
    t = (v.co.z - 0.95) / 0.4
    if t > 0:
        sxy = 1.0 - 0.35 * min(t, 1.0)
        v.co.x *= sxy; v.co.y *= sxy
for v in bm.verts:
    if v.co.z > 1.4:
        v.co.z += 0.03; v.co.y += 0.02
bm.to_mesh(torso.data); bm.free()
smooth(torso); set_mat(torso, M_SKIN); link(torso)

neck = cyl(0.062, 0.18, (0, 0.04, 1.50), rot=(math.radians(-10), 0, 0), name="Neck")
apply_transform(neck); smooth(neck); set_mat(neck, M_SKIN); link(neck)

clav_l = cyl(0.035, 0.22, (-0.21, 0.02, 1.42), rot=(0, math.radians(12), math.radians(8)), name="Clav_L")
apply_transform(clav_l); smooth(clav_l); set_mat(clav_l, M_SKIN); link(clav_l)
clav_r = cyl(0.035, 0.22, (0.21, 0.02, 1.42), rot=(0, math.radians(-12), math.radians(-8)), name="Clav_R")
apply_transform(clav_r); smooth(clav_r); set_mat(clav_r, M_SKIN); link(clav_r)

def arm(side, cyber):
    s = 1 if side == 'L' else -1
    ua = cyl(0.075, 0.34, (s*0.30, 0.0, 1.32), rot=(0, 0, math.radians(s*15)), name=f"UpperArm_{side}")
    apply_transform(ua); smooth(ua)
    fa = cyl(0.068, 0.32, (s*0.52, 0.0, 1.08), rot=(0, 0, math.radians(s*15)), name=f"LowerArm_{side}")
    apply_transform(fa); smooth(fa)
    hand = sphere(0.055, (s*0.66, 0.0, 0.90), name=f"Hand_{side}")
    hand.scale = (1.0, 0.9, 1.0); apply_transform(hand); smooth(hand)
    m = M_CYBER if cyber else M_SKIN
    set_mat(ua, m); set_mat(fa, m); set_mat(hand, m)
    link(ua); link(fa); link(hand)
    return ua, fa, hand

ua_l, fa_l, hand_l = arm('L', cyber=False)
ua_r, fa_r, hand_r = arm('R', cyber=True)

# Fingers as separate cylinders (each weighted to its finger bone)
def hand_fingers(side, hand_obj):
    s = 1 if side == 'L' else -1
    hloc = hand_obj.location
    finger_dir = s
    offsets = [(0.00,0.025,0.015),(0.00,0.005,0.000),(0.00,-0.012,-0.005),(0.00,-0.028,-0.012),(0.00,-0.042,-0.018)]
    lengths = [0.05,0.062,0.058,0.052,0.044]
    segs_all = []
    for i,(ox,oy,oz) in enumerate(offsets):
        base = Vector((hloc.x + ox*finger_dir, hloc.y + oy, hloc.z + oz))
        segs = []
        for j in range(3):
            L = lengths[i]/3.0
            mid = Vector((base.x + finger_dir*(j+0.5)*L, base.y, base.z))
            ph = cyl(0.014, L, mid, rot=(0, math.radians(90 if side=='L' else -90), 0), name=f"Finger{side}_{i}_p{j+1}")
            apply_transform(ph); smooth(ph)
            m = M_CYBER if side=='R' else M_SKIN
            set_mat(ph, m); link(ph)
            segs.append(ph)
        segs_all.append(segs)
    return segs_all

fingers_l = hand_fingers('L', hand_l)
fingers_r = hand_fingers('R', hand_r)

def leg(side):
    s = 1 if side == 'L' else -1
    thigh = cyl(0.10, 0.42, (s*0.11, 0.0, 0.82), name=f"Thigh_{side}")
    apply_transform(thigh); smooth(thigh); set_mat(thigh, M_SKIN); link(thigh)
    shin = cyl(0.085, 0.44, (s*0.11, 0.0, 0.40), name=f"Shin_{side}")
    apply_transform(shin); smooth(shin); set_mat(shin, M_SKIN); link(shin)
    foot = cyl(0.09, 0.14, (s*0.11, 0.10, 0.10), rot=(math.radians(-10), 0, 0), name=f"Foot_{side}")
    apply_transform(foot); smooth(foot); set_mat(foot, M_SKIN); link(foot)
    toe = cube(1.0, (s*0.11, 0.18, 0.03), name=f"Toe_{side}")
    toe.scale = (0.5, 0.62, 0.22); apply_transform(toe); smooth(toe); set_mat(toe, M_SKIN); link(toe)
    return thigh, shin, foot, toe

thigh_l, shin_l, foot_l, toe_l = leg('L')
thigh_r, shin_r, foot_r, toe_r = leg('R')
# feet at ground
for o in (foot_l, foot_r, toe_l, toe_r):
    o.location.z = 0.06
    apply_transform(o)

# ===== CLOTHING / ARMOR (hard, separate) =====
chest_armor = cube(1.0, (0, 0.16, 1.30), name="ChestArmor")
chest_armor.scale = (0.40, 0.11, 0.43); apply_transform(chest_armor); flat(chest_armor)
set_mat(chest_armor, M_ARMOR); link(chest_armor)
paul_l = sphere(0.075, (-0.35, 0.02, 1.42), name="Paul_L")
paul_l.scale = (1.0,0.6,0.75); apply_transform(paul_l); flat(paul_l); set_mat(paul_l, M_ARMOR); link(paul_l)
paul_r = sphere(0.075, (0.35, 0.02, 1.42), name="Paul_R")
paul_r.scale = (1.0,0.6,0.75); apply_transform(paul_r); flat(paul_r); set_mat(paul_r, M_ARMOR); link(paul_r)
thigh_arm_l = cube(1.0, (-0.11, -0.02, 0.72), name="ThighArmor_L")
thigh_arm_l.scale = (0.13,0.10,0.20); apply_transform(thigh_arm_l); flat(thigh_arm_l); set_mat(thigh_arm_l, M_ARMOR); link(thigh_arm_l)
thigh_arm_r = cube(1.0, (0.11, -0.02, 0.72), name="ThighArmor_R")
thigh_arm_r.scale = (0.13,0.10,0.20); apply_transform(thigh_arm_r); flat(thigh_arm_r); set_mat(thigh_arm_r, M_ARMOR); link(thigh_arm_r)
undershirt = cube(1.0, (0, 0, 1.20), name="Undershirt")
undershirt.scale = (0.37,0.29,0.56); apply_transform(undershirt); smooth(undershirt); set_mat(undershirt, M_CLOTH); link(undershirt)
pants = cube(1.0, (0, 0, 0.70), name="Pants")
pants.scale = (0.20,0.18,0.55); apply_transform(pants); smooth(pants); set_mat(pants, M_CLOTH); link(pants)
hair = sphere(0.13, (0, -0.05, 1.70), name="Hair")
hair.scale = (1.0,0.85,0.7); apply_transform(hair); smooth(hair); set_mat(hair, M_HAIR); link(hair)

# ===== PROPS =====
emitter = cyl(0.05, 0.09, (-0.66, 0.0, 0.90), name="WristEmitter")
emitter.scale = (1.0,1.0,0.7); apply_transform(emitter); flat(emitter); set_mat(emitter, M_CYBER); link(emitter, "Props")
emitter_glow = sphere(0.03, (-0.66, 0.05, 0.90), name="EmitterGlow")
apply_transform(emitter_glow); set_mat(emitter_glow, M_GLOW); link(emitter_glow, "Props")
blade_base = cyl(0.04, 0.10, (0.66, -0.04, 1.02), name="BladeBase")
apply_transform(blade_base); flat(blade_base); set_mat(blade_base, M_CYBER); link(blade_base, "Props")
blade = cone(0.018, 0.0, 0.30, (0.66, -0.06, 0.90), rot=(math.radians(-20), 0, 0), name="Blade")
apply_transform(blade); flat(blade); set_mat(blade, M_CYBER); link(blade, "Props")
cell = cyl(0.05, 0.10, (0.22, -0.12, 0.92), name="PowerCell")
apply_transform(cell); flat(cell); set_mat(cell, M_CYBER); link(cell, "Props")
cell_glow = sphere(0.025, (0.22, -0.16, 0.97), name="CellGlow")
apply_transform(cell_glow); set_mat(cell_glow, M_GLOW); link(cell_glow, "Props")
beacon = sphere(0.05, (0.0, 0.25, 1.15), name="Beacon")
apply_transform(beacon); smooth(beacon); set_mat(beacon, M_CYBER); link(beacon, "Props")
beacon_ant = cyl(0.008, 0.06, (0.0, 0.30, 1.20), name="BeaconAntenna")
apply_transform(beacon_ant); flat(beacon_ant); set_mat(beacon_ant, M_CYBER); link(beacon_ant, "Props")

# UVs
all_mesh = [head, torso, neck, clav_l, clav_r, ua_l, fa_l, hand_l, ua_r, fa_r, hand_r,
            thigh_l, shin_l, foot_l, toe_l, thigh_r, shin_r, foot_r, toe_r,
            chest_armor, paul_l, paul_r, thigh_arm_l, thigh_arm_r, undershirt, pants, hair,
            eye_l, eye_r, pupil_l, pupil_r] + [p for f in fingers_l+fingers_r for p in f]
for o in all_mesh:
    try: uv_smart(o)
    except Exception as e: print("UV fail", o.name, e)
for o in [emitter, emitter_glow, blade_base, blade, cell, cell_glow, beacon, beacon_ant]:
    try: uv_smart(o)
    except Exception as e: print("UV fail prop", o.name, e)

# Character height check
print("Character built. Parts:", len(all_mesh))
bpy.ops.wm.save_mainfile(filepath=BLEND)
print("Saved", BLEND)