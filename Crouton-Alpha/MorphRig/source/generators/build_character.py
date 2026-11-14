import bpy, bmesh, math, random, os, json, mathutils
from mathutils import Vector, Quaternion, Matrix

random.seed(7)

# ---------- clean scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
for c in list(bpy.data.collections):
    if c.name != "Collection":
        try: bpy.data.collections.remove(c)
        except: pass
# remove default
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE'
# 30 fps
scene.render.fps = 30
scene.render.fps_base = 1.0

# ---------- materials ----------
def mat(name, base, rough=0.7, metal=0.0, emissive=None, emissive_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emissive:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emissive_strength
    return m

M_SKIN  = mat("MAT_Skin", (0.72,0.48,0.36), 0.65)
M_CLOTH = mat("MAT_Clothing", (0.08,0.16,0.22), 0.85)
M_ARMOR = mat("MAT_Armor", (0.16,0.18,0.22), 0.45, 0.6)
M_CYBER = mat("MAT_Cyber", (0.35,0.38,0.42), 0.3, 0.9)
M_EMIT  = mat("MAT_EmissiveAccent", (0.05,0.05,0.08), 0.4, 0.2, emissive=(0.0,0.9,1.0), emissive_strength=2.5)
M_EYE   = mat("MAT_Eye", (0.1,0.35,0.55), 0.15)
M_MOUTH = mat("MAT_MouthInterior", (0.15,0.03,0.03), 0.8)
M_HAIR  = mat("MAT_Hair", (0.12,0.08,0.05), 0.8)

MATS = [M_SKIN, M_CLOTH, M_ARMOR, M_CYBER, M_EMIT, M_EYE, M_MOUTH, M_HAIR]

def prim(kind, name, loc, scale, mat, rotation=(0,0,0), segments=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=loc, rotation=rotation) if kind=='sphere' else \
    bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=1.0, depth=1.0, location=loc, rotation=rotation) if kind=='cyl' else \
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rotation)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    if mat:
        ob.data.materials.append(mat)
    return ob

parts = []
# x+ = character left (L), forward = -Y
# torso & pelvis
parts.append(prim('sphere','torso',(0,0,1.24),(0.205,0.120,0.30),M_CLOTH,segments=32,rings=24))
parts.append(prim('sphere','pelvis',(0,0,0.99),(0.195,0.120,0.16),M_CLOTH,segments=32,rings=20))
parts.append(prim('sphere','chest_skin',(0,0,1.38),(0.17,0.105,0.13),M_SKIN,segments=32,rings=20))
# neck (skin)
parts.append(prim('cyl','neck',(0,0,1.56),(0.045,0.045,0.07),M_SKIN,segments=20))
# head skin
head = prim('sphere','head',(0,0,1.68),(0.086,0.092,0.102),M_SKIN,segments=48,rings=32)
parts.append(head)
# hair cap (back/top)
parts.append(prim('sphere','hair',(0,0.030,1.72),(0.090,0.092,0.100),M_HAIR,segments=32,rings=24))
# hair tail secondary motion element (short, back of neck)
parts.append(prim('sphere','hair_tail',(0,0.075,1.57),(0.045,0.03,0.09),M_HAIR,segments=20,rings=12))
# limbs
for side, sx in (('L',1),('R',-1)):
    x = sx
    parts.append(prim('cyl',f'upperarm_{side}',(x*0.205,0,1.37),(0.046,0.046,0.16),M_SKIN,segments=20))
    parts.append(prim('cyl',f'forearm_{side}',(x*0.215,0,1.13),(0.040,0.040,0.15),M_SKIN,segments=20))
    parts.append(prim('sphere',f'hand_{side}',(x*0.22,-0.005,0.96),(0.037,0.026,0.070),M_SKIN,segments=20,rings=14))
    parts.append(prim('cyl',f'thigh_{side}',(x*0.080,0,0.72),(0.080,0.080,0.27),M_CLOTH,segments=20))
    parts.append(prim('cyl',f'shin_{side}',(x*0.080,0,0.32),(0.062,0.062,0.26),M_CLOTH,segments=20))
    parts.append(prim('sphere',f'foot_{side}',(x*0.080,-0.045,0.045),(0.052,0.125,0.045),M_ARMOR,segments=20,rings=14))
    # fingers: 4 fingers down, thumb angled
    for i in range(4):
        px = x*(0.22 + (i-1.5)*0.013); py = -0.008 - 0.003*i
        z = 0.915
        for ph, (r, h) in enumerate([(0.009,0.024),(0.008,0.020),(0.007,0.016)]):
            parts.append(prim('cyl',f'finger_{side}_{i}_{ph}',(px,py,z),(r,r,h),M_SKIN,segments=10))
            z -= 0.040
    # thumb
    parts.append(prim('cyl',f'thumb_{side}_0',(x*0.192,-0.025,0.95),(0.009,0.009,0.02),M_SKIN,rotation=(0.5,0,x*0.4),segments=10))
    parts.append(prim('cyl',f'thumb_{side}_1',(x*0.182,-0.038,0.93),(0.008,0.008,0.017),M_SKIN,rotation=(0.5,0,x*0.4),segments=10))
    parts.append(prim('cyl',f'thumb_{side}_2',(x*0.176,-0.048,0.915),(0.007,0.007,0.014),M_SKIN,rotation=(0.5,0,x*0.4),segments=10))

# armor: chest plate, shoulder pads
parts.append(prim('sphere','chest_plate',(0,-0.055,1.38),(0.16,0.05,0.12),M_ARMOR,segments=24,rings=16))
for side, sx in (('L',1),('R',-1)):
    parts.append(prim('sphere',f'shoulder_pad_{side}',(sx*0.205,0,1.505),(0.075,0.075,0.045),M_ARMOR,segments=24,rings=16))
    parts.append(prim('sphere',f'elbow_pad_{side}',(sx*0.228,0.02,1.25),(0.045,0.045,0.04),M_ARMOR,segments=16,rings=10))
    parts.append(prim('sphere',f'knee_pad_{side}',(sx*0.085,-0.045,0.53),(0.06,0.04,0.06),M_ARMOR,segments=16,rings=10))
    # emissive trim
    parts.append(prim('sphere',f'trim_{side}',(sx*0.175,-0.075,1.30),(0.02,0.015,0.06),M_EMIT,segments=12,rings=8))
    # backpack/cable anchor accent
    parts.append(prim('sphere',f'pack_{side}',(sx*0.09,0.09,1.30),(0.07,0.045,0.13),M_ARMOR,segments=16,rings=10))

# cybernetic left forearm shell (L = +X)
parts.append(prim('cyl','cyber_forearm_L',(0.215,0,1.13),(0.046,0.046,0.14),M_CYBER,segments=20))
parts.append(prim('sphere','cyber_hand_L',(0.22,-0.005,0.96),(0.039,0.028,0.072),M_CYBER,segments=20,rings=14))
parts.append(prim('sphere','cyber_trim_L',(0.215,-0.032,1.13),(0.042,0.02,0.05),M_EMIT,segments=14,rings=8))
# cable secondary motion (curve converted to mesh strip? use thin cylinder chain)
cable = prim('cyl','cable',(0.12,0.09,1.28),(0.008,0.008,0.14),M_CYBER,rotation=(0.3,0,0),segments=8)
parts.append(cable)

# eyeballs
eyes = []
for side, sx in (('L',1),('R',-1)):
    e = prim('sphere',f'eye_{side}',(sx*0.033,-0.078,1.70),(0.015,0.015,0.015),M_EYE,segments=20,rings=14)
    eyes.append(e)
# teeth + tongue + mouth interior
teeth = prim('sphere','teeth',(0,-0.074,1.615),(0.033,0.014,0.018),M_EYE,segments=16,rings=10)
tongue = prim('sphere','tongue',(0,-0.068,1.598),(0.027,0.018,0.011),M_MOUTH,segments=16,rings=10)
mouth_in = prim('sphere','mouth_interior',(0,-0.02,1.63),(0.04,0.05,0.035),M_MOUTH,segments=16,rings=10)

# ---------- join body parts ----------
bpy.ops.object.select_all(action='DESELECT')
for ob in parts: ob.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
body = bpy.context.active_object
body.name = "Operative_Body"
# ensure material order -> slots 8 max
# (join preserves all materials; we have exactly 8)

# ---------- armature ----------
arm_data = bpy.data.armatures.new("Operative_DeformArmature")
arm = bpy.data.objects.new("Operative_Deform", arm_data)
scene.collection.objects.link(arm)
arm.show_in_front = False
# build bone list
B = []
def bone(name, head, tail, parent=None):
    B.append((name, Vector(head), Vector(tail), parent))

bone("root",(0,0,0),(0,0,0.02))
bone("pelvis",(0,0,0.90),(0,0,1.08),"root")
bone("spine_01",(0,0,1.05),(0,0,1.25),"pelvis")
bone("spine_02",(0,0,1.22),(0,0,1.42),"spine_01")
bone("spine_03",(0,0,1.40),(0,0,1.56),"spine_02")
bone("neck_01",(0,0,1.54),(0,0,1.63),"spine_03")
bone("head",(0,0,1.61),(0,0,1.80),"neck_01")
bone("jaw",(0,-0.01,1.62),(0,-0.03,1.56),"head")
bone("eye_L",(0.033,-0.078,1.70),(0.033,-0.10,1.70),"head")
bone("eye_R",(-0.033,-0.078,1.70),(-0.033,-0.10,1.70),"head")
for side, sx in (('L',1),('R',-1)):
    bone(f"clavicle_{side}",(sx*0.03,0,1.50),(sx*0.20,0,1.50),"spine_03")
    bone(f"upperarm_{side}",(sx*0.20,0,1.50),(sx*0.215,0,1.26),f"clavicle_{side}")
    bone(f"upperarm_twist_{side}",(sx*0.21,0,1.44),(sx*0.225,0,1.33),f"upperarm_{side}")
    bone(f"lowerarm_{side}",(sx*0.215,0,1.26),(sx*0.225,0,1.03),f"upperarm_{side}")
    bone(f"forearm_twist_{side}",(sx*0.22,0,1.20),(sx*0.225,0,1.09),f"lowerarm_{side}")
    bone(f"hand_{side}",(sx*0.225,0,1.03),(sx*0.22,-0.01,0.93),f"lowerarm_{side}")
    # fingers
    fnames = ["index","middle","ring","pinky"]
    for i, fn in enumerate(fnames):
        px = sx*(0.22 + (i-1.5)*0.013); 
        # note mesh fingers at similar; bones hang down
        p0=(px,-0.008-0.003*i,0.915); p1=(px,-0.008-0.003*i,0.875); p2=(px,-0.008-0.003*i,0.845); p3=(px,-0.008-0.003*i,0.82)
        bone(f"{fn}_01_{side}",p0,p1,f"hand_{side}")
        bone(f"{fn}_02_{side}",p1,p2,f"{fn}_01_{side}")
        bone(f"{fn}_03_{side}",p2,p3,f"{fn}_02_{side}")
    # thumb
    bone(f"thumb_01_{side}",(sx*0.24,0,0.97),(sx*0.22,-0.02,0.95),f"hand_{side}")
    bone(f"thumb_02_{side}",(sx*0.22,-0.02,0.95),(sx*0.21,-0.035,0.93),f"thumb_01_{side}")
    bone(f"thumb_03_{side}",(sx*0.21,-0.035,0.93),(sx*0.205,-0.045,0.915),f"thumb_02_{side}")
    bone(f"thigh_{side}",(sx*0.080,0,0.99),(sx*0.085,0,0.54),"pelvis")
    bone(f"thigh_twist_{side}",(sx*0.082,0,0.86),(sx*0.084,0,0.68),f"thigh_{side}")
    bone(f"calf_{side}",(sx*0.085,0,0.54),(sx*0.085,0,0.10),f"thigh_{side}")
    bone(f"calf_twist_{side}",(sx*0.085,0,0.42),(sx*0.085,0,0.22),f"calf_{side}")
    bone(f"foot_{side}",(sx*0.085,0,0.10),(sx*0.085,-0.09,0.05),f"calf_{side}")
    bone(f"ball_{side}",(sx*0.085,-0.09,0.05),(sx*0.085,-0.16,0.035),f"foot_{side}")

bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bone_objs = {}
for name, h, t, parent in B:
    b = arm_data.edit_bones.new(name)
    b.head = h; b.tail = t
    bone_objs[name] = b
for name, h, t, parent in B:
    if parent:
        bone_objs[name].parent = bone_objs[parent]
        bone_objs[name].use_connect = False
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
# set deform
for b in arm_data.bones: b.use_deform = True
bpy.ops.object.mode_set(mode='OBJECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body

# parenting eyes/teeth/tongue/mouth to bones
def parent_to_bone(obj, bone_name, keep_offset=True):
    obj.parent = arm
    obj.parent_type = 'BONE'
    obj.parent_bone = bone_name
    # keep world transform via matrix_parent_inverse
    # compute inverse: parent bone matrix at rest
    # use simple: set matrix_parent_inverse to identity inverse of current
    obj.matrix_parent_inverse = obj.matrix_world.inverted()

for e, bn in [(eyes[0],"eye_L"),(eyes[1],"eye_R")]:
    parent_to_bone(e, bn)
parent_to_bone(teeth, "jaw")
parent_to_bone(tongue, "jaw")
parent_to_bone(mouth_in, "head")

# ---------- vertex groups by bone distance ----------
mesh = body.data
# precompute bone segment endpoints in world (armature at origin identity)
bones_world = [(name, h, t) for name,h,t,_ in B]
# group creation
vg = {}
for name,_,_ in bones_world:
    g = body.vertex_groups.new(name=name)
    vg[name] = g

import mathutils
def seg_dist(p, a, b):
    ab = b-a; L2 = ab.length_squared
    if L2 < 1e-9: return (p-a).length
    t = max(0.0, min(1.0, (p-a).dot(ab)/L2))
    return (p-(a+ab*t)).length

# radius falloff per bone type
def radius_for(name):
    if 'finger' in name or 'thumb' in name or 'index' in name or 'middle' in name or 'ring' in name or 'pinky' in name: return 0.035
    if name.startswith('eye') or name=='jaw': return 0.07
    if name in ('head',): return 0.16
    if name.startswith('spine') or name in ('pelvis','neck_01'): return 0.20
    if name.startswith('clavicle') or name.startswith('upperarm'): return 0.11
    if name.startswith('lowerarm') or name.startswith('forearm'): return 0.10
    if name.startswith('thigh') or name.startswith('calf'): return 0.14
    if name.startswith('foot') or name.startswith('ball'): return 0.10
    if name.startswith('hand'): return 0.08
    return 0.15

# For each vertex, find deform bones sorted
# Build lists: only bones whose rest position might influence: check y,z range skip root
deform_bones = [(n,h,t) for n,h,t in bones_world if n!='root']
for v in mesh.vertices:
    p = v.co
    cand = []
    for name,h,t in deform_bones:
        d = seg_dist(p,h,t)
        r = radius_for(name)
        if d < r:
            w = (1 - (d/r)**2)**2
            if w>0.002: cand.append((w,name))
    cand.sort(reverse=True)
    cand = cand[:4]
    tot = sum(w for w,_ in cand) or 1.0
    for w,name in cand:
        vg[name].add([v.index], w/tot, 'REPLACE')
    if not cand:
        # nearest bone
        best = min(deform_bones, key=lambda nb: seg_dist(p,nb[1],nb[2]))
        vg[best[0]].add([v.index],1.0,'REPLACE')

# head deformation bones already, hair vertices near head will bind to head ok

# ---------- shape keys on head/body ----------
# Work on body mesh shape keys
body.shape_key_add(from_mix=False)
basis = body.data.shape_keys.key_blocks[0]
# helper: apply displacement function f(p) -> offset
def make_key(name, func, strength=1.0):
    sk = body.shape_key_add(name=name, from_mix=False)
    # copy basis coords
    for v in mesh.vertices:
        off = func(v.co.copy())
        sk.data[v.index].co = v.co + off
    sk.value = 0.0
    return sk

# mouth region: centre ~ (0,-0.07,1.63), lips radius 0.035
def mouth_mask(p):
    c = Vector((0,-0.065,1.632))
    d=(p-c).length
    return max(0.0, 1-d/0.045)

def face_mask(p, centre, radius):
    c=Vector(centre); d=(p-c).length
    return max(0.0, 1-d/radius)

# eyes / lids centres
EL=(0.033,-0.07,1.70); ER=(-0.033,-0.07,1.70); MOU=(0,-0.065,1.632)

make_key("Blink_L", lambda p: Vector((0,0.006,0))*face_mask(p,EL,0.028))
make_key("Blink_R", lambda p: Vector((0,0.006,0))*face_mask(p,ER,0.028))
make_key("Squint", lambda p: Vector((0,0.004,0))*(face_mask(p,EL,0.03)+face_mask(p,ER,0.03))*0.7)
make_key("BrowRaise", lambda p: Vector((0,-0.002,0.012))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)))
make_key("BrowLower", lambda p: Vector((0,-0.002,-0.010))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)))
make_key("CheekRaise", lambda p: Vector((0,-0.003,0.008))*(face_mask(p,(0.045,-0.06,1.68),0.04)+face_mask(p,(-0.045,-0.06,1.68),0.04)))
# jaw open: lower face moves down/back
def jawfunc(p):
    m = face_mask(p,(0,-0.05,1.615),0.05)
    return Vector((0,-0.008,-0.028))*m
make_key("JawOpen", jawfunc)
make_key("LipClosure", lambda p: Vector((0,-0.004,0))*mouth_mask(p)*0.6)
def smile(p):
    m=mouth_mask(p)
    # corners up/out
    sx = 0.02 if p.x>0 else -0.02
    return Vector((sx*m*0.5, -0.002*m, 0.008*m))
make_key("Smile", smile)
make_key("Frown", lambda p: Vector((0,-0.002,-0.010))*mouth_mask(p))
make_key("Pucker", lambda p: Vector((0,-0.010,0))*mouth_mask(p))
make_key("Viseme_A", lambda p: Vector((0,-0.006,-0.022))*mouth_mask(p))
make_key("Viseme_I", lambda p: Vector((0.012*(1 if p.x>0 else -1),-0.002,0))*mouth_mask(p)* (1 if abs(p.x)>0.015 else 0.3))
make_key("Viseme_U", lambda p: Vector((0,-0.010,0.002))*mouth_mask(p))
make_key("Viseme_O", lambda p: Vector((0,-0.008,-0.006))*mouth_mask(p))
make_key("Viseme_M", lambda p: Vector((0,-0.003,0))*mouth_mask(p)*0.8)
make_key("Viseme_F", lambda p: Vector((0,-0.002,-0.008))*face_mask(p,(0,-0.06,1.625),0.035))
make_key("Viseme_L", lambda p: Vector((0,-0.003,0.006))*mouth_mask(p))
# presets as shape keys (composite)
make_key("Preset_Joy", lambda p: smile(p)*1.2 + Vector((0,0,0.008))*(face_mask(p,(0.045,-0.06,1.68),0.04)+face_mask(p,(-0.045,-0.06,1.68),0.04))*0.6 + Vector((0,-0.002,0.010))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03))*0.5)
make_key("Preset_Anger", lambda p: Vector((0,-0.002,-0.012))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)) + Vector((0,0.002,-0.008))*mouth_mask(p) + Vector((0,0.006,0))*(face_mask(p,EL,0.028)+face_mask(p,ER,0.028)))
make_key("Preset_Sadness", lambda p: Vector((0,-0.002,0.008))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)) + Vector((0,-0.002,-0.008))*mouth_mask(p))
make_key("Preset_Surprise", lambda p: Vector((0,-0.002,0.014))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)) + jawfunc(p)*0.7)
make_key("Preset_Pain", lambda p: Vector((0,0.002,-0.010))*(face_mask(p,EL,0.028)+face_mask(p,ER,0.028)) + Vector((0,-0.002,-0.010))*mouth_mask(p))
make_key("Preset_Focus", lambda p: Vector((0,-0.002,-0.006))*(face_mask(p,(0.033,-0.06,1.735),0.03)+face_mask(p,(-0.033,-0.06,1.735),0.03)) + Vector((0,0.006,0))*(face_mask(p,EL,0.028)+face_mask(p,ER,0.028))*0.8)

# ---------- props ----------
props = []
# wrist emitter on right forearm (R=-X) front
em = prim('cyl','Emitter',( -0.215,-0.045,1.08),(0.022,0.022,0.05),M_CYBER,rotation=(math.pi/2,0,0),segments=16)
em.parent = arm; em.parent_type='BONE'; em.parent_bone='lowerarm_R'; em.matrix_parent_inverse = em.matrix_world.inverted()
props.append(em)
em_tip = prim('sphere','Muzzle',(-0.215,-0.08,1.08),(0.012,0.012,0.012),M_EMIT,segments=12,rings=8)
em_tip.parent = arm; em_tip.parent_type='BONE'; em_tip.parent_bone='lowerarm_R'; em_tip.matrix_parent_inverse = em_tip.matrix_world.inverted()
props.append(em_tip)
# forearm blade on left forearm
blade = prim('cube','Blade',(0.215,-0.055,1.05),(0.012,0.09,0.008),M_CYBER,segments=1)
blade.parent = arm; blade.parent_type='BONE'; blade.parent_bone='lowerarm_L'; blade.matrix_parent_inverse = blade.matrix_world.inverted()
props.append(blade)
# power cell (separate, initially in left hand area)
cell = prim('cube','PowerCell',(0.29,-0.02,0.90),(0.015,0.015,0.035),M_EMIT,segments=1)
props.append(cell)
# beacon/drone
beacon = prim('sphere','Beacon',(0.4,-0.3,0.02),(0.05,0.05,0.05),M_ARMOR,segments=16,rings=10)
props.append(beacon)
beacon_light = prim('sphere','BeaconLight',(0.4,-0.3,0.06),(0.02,0.02,0.02),M_EMIT,segments=10,rings=6)
props.append(beacon_light)

# ---------- control rig (separate armature) ----------
cdata = bpy.data.armatures.new("Operative_ControlArmature")
carm = bpy.data.objects.new("Operative_Control", cdata)
scene.collection.objects.link(carm)
bpy.context.view_layer.objects.active = carm
carm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
cb = {}
def cbone(name, h, t, parent=None):
    b = cdata.edit_bones.new(name); b.head=Vector(h); b.tail=Vector(t); cb[name]=b
    if parent: b.parent=cb[parent]
    return b
cbone("ctrl_root",(0,0,0),(0,0,0.1))
cbone("ctrl_pelvis",(0,0,0.9),(0,0,1.05),"ctrl_root")
cbone("ctrl_spine",(0,0,1.05),(0,0,1.3),"ctrl_pelvis")
cbone("ctrl_chest",(0,0,1.3),(0,0,1.5),"ctrl_spine")
cbone("ctrl_neck",(0,0,1.5),(0,0,1.6),"ctrl_chest")
cbone("ctrl_head",(0,0,1.6),(0,0,1.78),"ctrl_neck")
for side,sx in (('L',1),('R',-1)):
    cbone(f"ctrl_hand_ik_{side}",(sx*0.29,0,1.0),(sx*0.29,-0.05,0.95),"ctrl_chest")
    cbone(f"ctrl_foot_ik_{side}",(sx*0.10,-0.05,0.07),(sx*0.10,-0.15,0.04),"ctrl_pelvis")
    cbone(f"pole_elbow_{side}",(sx*0.35,0.1,1.25),(sx*0.35,0.18,1.25),"ctrl_root")
    cbone(f"pole_knee_{side}",(sx*0.10,-0.12,0.52),(sx*0.10,-0.20,0.52),"ctrl_root")
    cbone(f"ctrl_ankle_roll_{side}",(sx*0.10,0,0.07),(sx*0.10,-0.04,0.04),f"ctrl_foot_ik_{side}")
    cbone(f"ctrl_toe_{side}",(sx*0.10,-0.12,0.04),(sx*0.10,-0.18,0.03),f"ctrl_foot_ik_{side}")
bpy.ops.object.mode_set(mode='OBJECT')
for b in cdata.bones: b.use_deform=False

# save initial
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Operative.blend")
out = os.path.abspath(out)
os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out)
print("triangles approx", sum(len(p.data.polygons) for p in [body]))
result={"saved":out,"materials":len(body.data.materials),"bones":len(arm_data.bones)}
