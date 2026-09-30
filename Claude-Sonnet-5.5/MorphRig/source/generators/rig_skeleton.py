"""Create the exportable deformation skeleton ('Operative_Skeleton') in Blender from skeleton_def."""
import bpy
from mathutils import Vector
import skeleton_def as S

SKELETON_NAME = 'Operative_Skeleton'

GROUP_COLLECTIONS = {
    'root': 'Root', 'spine': 'Deform Core', 'head': 'Deform Core', 'arm': 'Deform Core', 'leg': 'Deform Core', 'hand': 'Deform Core',
    'finger': 'Deform Fingers', 'twist': 'Twist and Helpers', 'corrective': 'Twist and Helpers', 'face': 'Deform Face',
    'secondary': 'Deform Secondary', 'prop': 'Deform Props',
}


def create_skeleton(name=SKELETON_NAME):
    data = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = data.edit_bones
    for b in S.BONES:
        e = eb.new(b.name)
        e.head = Vector(b.head)
        e.tail = Vector(b.tail)
        e.use_deform = b.deform
    for b in S.BONES:
        e = eb[b.name]
        if b.parent:
            e.parent = eb[b.parent]
    for b in S.BONES:
        e = eb[b.name]
        e.align_roll(Vector(S.bone_frame(b)[2]))
        if b.connect and b.parent:
            e.use_connect = True
    bpy.ops.object.mode_set(mode='OBJECT')
    # bone collections
    cols = {}
    for b in S.BONES:
        cname = GROUP_COLLECTIONS.get(b.group, 'Other')
        if cname not in cols:
            cols[cname] = data.collections.new(cname)
        cols[cname].assign(data.bones[b.name])
    data.display_type = 'OCTAHEDRAL'
    ob.show_in_front = True
    return ob
