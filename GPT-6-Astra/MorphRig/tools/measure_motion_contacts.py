"""Measure evaluated chain continuity and support contacts, independent of generator."""
import bpy
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rig=bpy.data.objects['Operative_Rig'];scene=bpy.context.scene
mesh=bpy.data.objects['Operative_LOD0']
manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations']
groups={g.index:g.name for g in mesh.vertex_groups}
foot_indices={side:[v.index for v in mesh.data.vertices if sum(g.weight for g in v.groups if groups[g.group] in ('foot.'+side,'toe.'+side))>.9] for side in ('L','R')}
joints=[(a+'.'+s,b+'.'+s) for s in ('L','R') for a,b in [('thigh','shin'),('shin','foot'),('upper_arm','forearm'),('forearm','hand')]]
rows=[]
for entry in manifest:
    name=entry['id'];a=bpy.data.actions[name];rig.animation_data.action=a
    if a.slots:rig.animation_data.action_slot=a.slots[0]
    maximum={f'{a}->{b}':{'distance_m':0.,'frame':0} for a,b in joints}
    supports=[]
    for frame in range(entry['frame_start'],entry['frame_end']+1):
        scene.frame_set(frame);bpy.context.view_layer.update()
        for parent,child in joints:
            p=rig.pose.bones[parent];c=rig.pose.bones[child]
            delta=(p.tail-c.head).length
            key=f'{parent}->{child}'
            if delta>maximum[key]['distance_m']:maximum[key]={'distance_m':delta,'frame':frame}
        if name.startswith(('walk_','run_','idle_')) and frame in (1,round(entry['frame_end']/2)):
            ev=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            supports.append({'frame':frame,**{side:min((ev.matrix_world@ev.data.vertices[i].co).z for i in foot_indices[side]) for side in ('L','R')}})
    rows.append({'id':name,'max_joint_gap_m':max(v['distance_m'] for v in maximum.values()),'joints':maximum,'sampled_sole_z':supports})
out={'method':'Evaluate actual armature pose every source frame; compare parent bone tail and child bone head for all eight limb connections. Foot samples use evaluated skinned mesh vertices assigned to foot/toe bones.','clips':rows,'worst_joint_gap_m':max(r['max_joint_gap_m'] for r in rows)}
(ROOT/'docs/validation/motion_contacts.json').write_text(json.dumps(out,indent=2)+'\n')
print('WORST_CHAIN_GAP_METERS',out['worst_joint_gap_m'])
for r in rows:
    if r['max_joint_gap_m']>.005:print('CHAIN_GAP',r['id'],r['max_joint_gap_m'])
