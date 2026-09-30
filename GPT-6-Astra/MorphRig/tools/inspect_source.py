"""Blender-native independent structural and motion validation.

blender -b MorphRig/source/Operative.blend -P MorphRig/tools/inspect_source.py
"""
import bpy
import csv
import hashlib
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/validation'
OUT.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
rig=next((o for o in scene.objects if o.type=='ARMATURE' and o.name=='Operative_Rig'),None)
if not rig: rig=next(o for o in scene.objects if o.type=='ARMATURE')
rig.animation_data_create()

def activate(action):
    rig.animation_data.action=action
    for slot in action.slots:
        if slot.target_id_type=='OBJECT':
            rig.animation_data.action_slot=slot
            break
    for track in rig.animation_data.nla_tracks: track.mute=True

def pose(frame):
    scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    return {p.name:[round(v,7) for row in p.matrix for v in row] for p in rig.pose.bones if p.bone.use_deform}

meshes=[]
for obj in scene.objects:
    if obj.type!='MESH': continue
    obj.data.calc_loop_triangles()
    groups={g.index:g.name for g in obj.vertex_groups}
    deform_names={b.name for b in rig.data.bones if b.use_deform}
    influences=[sum(1 for g in v.groups if g.weight>1e-6 and groups.get(g.group) in deform_names) for v in obj.data.vertices]
    unweighted=sum(n==0 for n in influences)
    bad=[v.index for v in obj.data.vertices if any(not math.isfinite(x) for x in v.co)]
    meshes.append({'name':obj.name,'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),
        'materials':[m.name if m else None for m in obj.data.materials],
        'uv_layers':[u.name for u in obj.data.uv_layers],
        'max_bone_influences':max(influences,default=0),'unweighted_vertices':unweighted,
        'nonfinite_vertices':bad,'dimensions_m':list(obj.dimensions),
        'morphs':list(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else [],
        'hidden_render':obj.hide_render,'modifiers':[(m.name,m.type) for m in obj.modifiers],
        'armature_preserve_volume':{m.name:m.use_deform_preserve_volume for m in obj.modifiers if m.type=='ARMATURE'}})

required=list(csv.DictReader((ROOT.parent/'required_animations.csv').open()))
motion=[]
hashes={}
for row in required:
    name=row['id']
    action=bpy.data.actions.get(name)
    if not action:
        motion.append({'id':name,'present':False}); continue
    activate(action)
    first,last=action.frame_range
    snapshots=[pose(f) for f in (first,first+(last-first)*.25,first+(last-first)*.5,first+(last-first)*.75,last)]
    digest=hashlib.sha256(json.dumps(snapshots,sort_keys=True).encode()).hexdigest()
    hashes.setdefault(digest,[]).append(name)
    # Translation is from the actual evaluated root in Blender meters.
    scene.frame_set(round(first)); a=rig.pose.bones['root'].matrix.translation.copy()
    scene.frame_set(round(last)); b=rig.pose.bones['root'].matrix.translation.copy()
    err=max((abs(x-y) for bone,values in snapshots[0].items() for x,y in zip(values,snapshots[-1][bone])),default=0)
    duration=(last-first)/scene.render.fps
    motion.append({'id':name,'present':True,'frame_range':[first,last],'duration_seconds':duration,
        'five_pose_hash':digest,'distinct_sampled_poses':len({json.dumps(s,sort_keys=True) for s in snapshots}),
        'root_displacement_m':list(b-a),'root_distance_m':(b-a).length,'endpoint_matrix_max_error':err,
        'form':row['form'],'root_policy':row['root_movement']})

bones=[{'name':b.name,'parent':b.parent.name if b.parent else None,'deform':b.use_deform} for b in rig.data.bones]
report={'blend':str(Path(bpy.data.filepath).relative_to(ROOT)),
    'blender_version':bpy.app.version_string,'fps':scene.render.fps,'scene_unit_scale':scene.unit_settings.scale_length,
    'rig':rig.name,'armature_scale':list(rig.scale),'bones':bones,
    'deform_bone_count':sum(b['deform'] for b in bones),'root_bones':[b['name'] for b in bones if b['parent'] is None],
    'deform_rotation_modes':{p.name:p.rotation_mode for p in rig.pose.bones if p.bone.use_deform},
    'meshes':meshes,'actions':motion,
    'identical_five_pose_groups':[v for v in hashes.values() if len(v)>1],
    'missing_external_images':[i.name for i in bpy.data.images if i.source=='FILE' and not i.packed_file and i.filepath and not Path(bpy.path.abspath(i.filepath)).exists()],
    'linked_libraries':[l.filepath for l in bpy.data.libraries],
    'limits':'Structural checks do not establish visual deformation/contact quality. Five sampled poses detect obvious duplicated clips; each clip still requires playback review.'}
(OUT/'blender_source_audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('AUDIT',len(meshes),'meshes;',sum(x['present'] for x in motion),'of',len(required),'required actions;',report['deform_bone_count'],'deformation bones')
print('DUPLICATE GROUPS',report['identical_five_pose_groups'])
