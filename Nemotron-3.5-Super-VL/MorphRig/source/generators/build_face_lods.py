#!/usr/bin/env python3
"""MORPHRIG - Facial shape keys, visemes, expression presets, LODs.
Loads source/Operative.blend, saves back."""
import bpy
import math
from mathutils import Vector

BLEND = "/home/candidate/workspace/MorphRig/source/Operative.blend"

bpy.ops.wm.open_mainfile(filepath=BLEND)

def link(obj, col_name):
    col = bpy.data.collections.get(col_name)
    if col is None:
        col = bpy.data.collections.new(col_name); bpy.context.scene.collection.children.link(col)
    col.objects.link(obj)
    for c in obj.users_collection:
        if c.name != col_name:
            c.objects.unlink(obj)

def make_active(obj):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)

def obj(name):
    return bpy.data.objects.get(name)

# ============ FACIAL SHAPE KEYS on Head ============
head = obj("Head")
make_active(head)
bpy.ops.object.mode_set(mode='OBJECT')
head.shape_key_clear()
kb = head.shape_key_add(name="Basis", from_mix=False)

def sk(name, relative=True):
    return head.shape_key_add(name=name, from_mix=False)

# Get basis vertices
import numpy as np
basis = np.array([v.co for v in head.data.vertices], dtype=float)

def apply_sk(skey, fn):
    arr = np.array([v.co for v in head.data.vertices], dtype=float)
    arr = fn(arr)
    for i, v in enumerate(head.data.vertices):
        v.co = arr[i]

# Helper masks
def mask_y_greater(arr, y):
    return arr[:,1] > y
def mask_y_less(arr, y):
    return arr[:,1] < y
def mask_x_less(arr, x):
    return arr[:,0] < x
def mask_x_greater(arr, x):
    return arr[:,0] > x
def mask_z_greater(arr, z):
    return arr[:,2] > z
def mask_z_less(arr, z):
    return arr[:,2] < z

# Blink L (close left eyelid): lower lid up / upper lid down around left eye
def blink_l(arr):
    a = arr.copy()
    m = (np.abs(a[:,0]-(-0.065))<0.05) & (np.abs(a[:,1]-0.13)<0.07) & (a[:,2]>1.58) & (a[:,2]<1.68)
    # upper lid moves down, lower lid moves up -> close eye vertically
    a[m,1] -= 0.012
    a[m,2] += 0.008
    return a
def set_sk(name, fn):
    kb = head.data.shape_keys.key_blocks.get(name)
    if kb is None:
        kb = head.shape_key_add(name=name, from_mix=False)
    arr = np.array([v.co for v in head.data.vertices], dtype=float)
    arr = fn(arr)
    for i, v in enumerate(head.data.vertices):
        kb.data[i].co = arr[i]

set_sk("blink_L", blink_l)

def blink_r(arr):
    a = arr.copy()
    m = (np.abs(a[:,0]-0.065)<0.05) & (np.abs(a[:,1]-0.13)<0.07) & (a[:,2]>1.58) & (a[:,2]<1.68)
    a[m,1] -= 0.012
    a[m,2] += 0.008
    return a
set_sk("blink_R", blink_r)

def squint(arr):
    a = arr.copy()
    for xc in (-0.065, 0.065):
        m = (np.abs(a[:,0]-xc)<0.06) & (np.abs(a[:,1]-0.13)<0.08) & (a[:,2]>1.58) & (a[:,2]<1.68)
        a[m,1] -= 0.018
        a[m,2] += 0.012
    # cheeks up
    m = (a[:,2]>1.54) & (a[:,2]<1.62) & (np.abs(a[:,0])>0.07) & (a[:,1]>0.09)
    a[m,1] += 0.01
    a[m,2] -= 0.006
    return a
set_sk("squint", squint)

def brow_raise(arr):
    a = arr.copy()
    for xc in (-0.06, 0.06):
        m = (np.abs(a[:,0]-xc)<0.05) & (a[:,2]>1.64) & (np.abs(a[:,1]-0.13)<0.06)
        a[m,2] += 0.015
    return a
set_sk("brow_raise_L", brow_raise)  # both for simplicity; L variant mirrored below
set_sk("brow_raise_R", brow_raise)

def brow_lower(arr):
    a = arr.copy()
    for xc in (-0.06, 0.06):
        m = (np.abs(a[:,0]-xc)<0.05) & (a[:,2]>1.64) & (np.abs(a[:,1]-0.13)<0.06)
        a[m,2] -= 0.012
        a[m,1] += 0.008
    return a
set_sk("brow_lower", brow_lower)

def jaw_open(arr):
    a = arr.copy()
    m = a[:,2] < 1.55
    m &= (np.abs(a[:,1])<0.14)
    a[m,2] -= 0.05
    a[m,1] += 0.02
    return a
set_sk("jaw_open", jaw_open)

def smile(arr):
    a = arr.copy()
    # mouth corners up and out, cheeks up
    m = (np.abs(a[:,0]-0.045)<0.03) & (a[:,2]>1.52) & (a[:,2]<1.58) & (a[:,1]>0.05)
    a[m,0] += 0.015
    a[m,2] += 0.012
    m = (np.abs(a[:,0]+0.045)<0.03) & (a[:,2]>1.52) & (a[:,2]<1.58) & (a[:,1]>0.05)
    a[m,0] -= 0.015
    a[m,2] += 0.012
    m = (np.abs(a[:,0])>0.07) & (a[:,2]>1.55) & (a[:,2]<1.62) & (a[:,1]>0.08)
    a[m,1] += 0.008
    a[m,2] -= 0.005
    return a
set_sk("smile", smile)

def frown(arr):
    a = arr.copy()
    m = (np.abs(a[:,0]-0.045)<0.03) & (a[:,2]>1.50) & (a[:,2]<1.58) & (a[:,1]>0.05)
    a[m,0] += 0.008
    a[m,2] -= 0.012
    m = (np.abs(a[:,0]+0.045)<0.03) & (a[:,2]>1.50) & (a[:,2]<1.58) & (a[:,1]>0.05)
    a[m,0] -= 0.008
    a[m,2] -= 0.012
    # brow lower
    for xc in (-0.06, 0.06):
        m = (np.abs(a[:,0]-xc)<0.05) & (a[:,2]>1.64) & (np.abs(a[:,1]-0.13)<0.06)
        a[m,2] -= 0.01
    return a
set_sk("frown", frown)

def lip_pucker(arr):
    a = arr.copy()
    m = (np.abs(a[:,0])<0.05) & (a[:,2]>1.53) & (a[:,2]<1.58) & (np.abs(a[:,1])<0.12)
    a[m,1] += 0.025  # push lips forward (+y)
    a[m,2] += 0.005
    return a
set_sk("lip_pucker", lip_pucker)

def lip_funnel(arr):
    a = arr.copy()
    m = (np.abs(a[:,0])<0.05) & (a[:,2]>1.53) & (a[:,2]<1.58)
    a[m,1] += 0.018
    a[m,2] -= 0.01
    return a
set_sk("lip_funnel", lip_funnel)

def lip_width(arr):
    a = arr.copy()
    m = (a[:,2]>1.52) & (a[:,2]<1.59) & (np.abs(a[:,1])<0.13)
    a[np.abs(a[:,0])>0.03, 0] *= 1.15
    return a
set_sk("lip_width", lip_width)

def jaw_thrust(arr):
    a = arr.copy()
    m = a[:,2] < 1.55
    m &= (np.abs(a[:,1])<0.14)
    a[m,1] += 0.02
    return a
set_sk("jaw_thrust", jaw_thrust)

def cheek_puff(arr):
    a = arr.copy()
    m = (np.abs(a[:,0])>0.08) & (a[:,2]>1.54) & (a[:,2]<1.61) & (a[:,1]>0.07)
    a[m,1] += 0.015
    return a
set_sk("cheek_puff_L", cheek_puff)
set_sk("cheek_puff_R", cheek_puff)

def tongue_up(arr):
    a = arr.copy()
    m = (a[:,2]>1.48) & (a[:,2]<1.56) & (np.abs(a[:,1])<0.10) & (np.abs(a[:,0])<0.04)
    a[m,2] += 0.015
    return a
set_sk("tongue_up", tongue_up)

# ============ VISEME SHAPE KEYS ============
def viseme_closed(arr):  # M B P - lips closed
    a = arr.copy()
    m = (a[:,2]>1.53) & (a[:,2]<1.585) & (np.abs(a[:,1])<0.12)
    a[m,2] -= 0.015
    a[m,1] += 0.005
    return a
set_sk("viseme_closed", viseme_closed)

def viseme_lipteeth(arr):  # F V
    a = arr.copy()
    m = (np.abs(a[:,0])<0.05) & (a[:,2]>1.53) & (a[:,2]<1.585)
    a[m,1] += 0.012
    a[m,2] -= 0.008
    # upper lip down to teeth
    m = (np.abs(a[:,0])<0.05) & (a[:,2]>1.55) & (a[:,2]<1.575)
    a[m,2] -= 0.01
    return a
set_sk("viseme_lipteeth", viseme_lipteeth)

def viseme_open_a(arr):  # open vowel A
    a = arr.copy()
    m = (a[:,2]<1.56) & (np.abs(a[:,1])<0.14)
    a[m,2] -= 0.06
    a[m,1] += 0.02
    return a
set_sk("viseme_open_a", viseme_open_a)

def viseme_wide_e(arr):  # wide vowel E/I
    a = arr.copy()
    m = (a[:,2]>1.52) & (a[:,2]<1.59) & (np.abs(a[:,1])<0.13)
    a[np.abs(a[:,0])>0.02,0] *= 1.25
    a[m,2] -= 0.02
    return a
set_sk("viseme_wide_e", viseme_wide_e)

def viseme_rounded_o(arr):  # rounded vowel O/U
    a = arr.copy()
    m = (np.abs(a[:,0])<0.06) & (a[:,2]>1.53) & (a[:,2]<1.585)
    a[m,1] += 0.028
    a[m,2] -= 0.005
    return a
set_sk("viseme_rounded_o", viseme_rounded_o)

def viseme_tongue_teeth(arr):  # T D N
    a = arr.copy()
    m = (a[:,2]>1.50) & (a[:,2]<1.57) & (np.abs(a[:,0])<0.04) & (np.abs(a[:,1])<0.11)
    a[m,1] += 0.015
    a[m,2] += 0.01
    return a
set_sk("viseme_tongue_teeth", viseme_tongue_teeth)

# zero all shape keys
for kb in head.data.shape_keys.key_blocks:
    kb.value = 0.0

# ============ LODs ============
lodcol = bpy.data.collections.new("LODs")
bpy.context.scene.collection.children.link(lodcol)

def decimate_copy(src, ratio, suffix):
    # duplicate object + data
    o = src.copy()
    o.data = src.data.copy()
    o.name = src.name + suffix
    o.animation_data_clear()
    link(o, "LODs")
    mod = o.modifiers.new(name="Decimate", type='DECIMATE')
    mod.ratio = ratio
    # apply decimate
    bpy.context.view_layer.objects.active = o
    for oo in bpy.context.view_layer.objects:
        oo.select_set(oo == o)
    bpy.ops.object.modifier_apply(modifier="Decimate")
    return o

# LOD0 = originals (keep). LOD1 ratio 0.5, LOD2 ratio 0.25 on character body parts
lod1_objs, lod2_objs = [], []
for src in bpy.data.objects:
    if src.type != 'MESH': continue
    if src.name.startswith(("Eye","Pupil")): continue
    if src.data.shape_keys: continue
    if src.users_collection and any(c.name=="Props" for c in src.users_collection):
        continue  # props keep full detail (small)
    o1 = decimate_copy(src, 0.5, "_LOD1")
    o2 = decimate_copy(src, 0.25, "_LOD2")
    lod1_objs.append(o1); lod2_objs.append(o2)

print("Shape keys:", len(head.data.shape_keys.key_blocks))
print("LOD1 objects:", len(lod1_objs), "LOD2 objects:", len(lod2_objs))
bpy.ops.wm.save_mainfile(filepath=BLEND)
print("Saved", BLEND)