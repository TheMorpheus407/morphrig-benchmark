"""Bake evaluated editable control actions, preserving their source curves.

blender -b source/Operative.blend -P tools/rebake_action.py -- --clip reload
blender -b source/Operative.blend -P tools/rebake_action.py -- --all

Use --no-save for validation. The default saves the opened production blend.
"""
import bpy,json,argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def rebake(rig,id,manifest=None):
    items=manifest or json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations']
    item=next(m for m in items if m['id']==id)
    source=bpy.data.actions.get('EDIT__'+id)
    if not source:raise RuntimeError('Missing editable source EDIT__'+id)
    rig.animation_data_create();rig.animation_data.action=source
    if source.slots:rig.animation_data.action_slot=source.slots[0]
    for pb in rig.pose.bones:
        if pb.bone.use_deform:pb.rotation_mode='QUATERNION'
    muted=[(c,c.mute) for pb in rig.pose.bones for c in pb.constraints]
    names=[pb.name for pb in rig.pose.bones if pb.bone.use_deform]
    samples=[]
    # Evaluate source with the user's current live constraints and keyed controls.
    for frame in range(item['frame_start'],item['frame_end']+1):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        evaluated=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        samples.append((frame,{n:evaluated.pose.bones[n].matrix.copy() for n in names}))
    for c,_ in muted:c.mute=True
    old=bpy.data.actions.get(id)
    if old:bpy.data.actions.remove(old)
    baked=bpy.data.actions.new(id);baked.use_fake_user=True;baked['baked']=True;baked['sample_rate']=30;baked['source_action']='EDIT__'+id
    rig.animation_data.action=baked
    previous={}
    for frame,mats in samples:
        for name in names:
            pb=rig.pose.bones[name];matrix=mats[name]
            if pb.parent:
                parent=mats.get(pb.parent.name,pb.parent.matrix)
                rest_local=pb.parent.bone.matrix_local.inverted()@pb.bone.matrix_local
                basis=rest_local.inverted()@parent.inverted()@matrix
            else:basis=pb.bone.matrix_local.inverted()@matrix
            location,rotation,scale=basis.decompose()
            if name in previous and previous[name].dot(rotation)<0:rotation.negate()
            previous[name]=rotation.copy();pb.location=location;pb.rotation_quaternion=rotation;pb.scale=scale
            pb.keyframe_insert('location',frame=frame,group=name);pb.keyframe_insert('rotation_quaternion',frame=frame,group=name);pb.keyframe_insert('scale',frame=frame,group=name)
    for layer in baked.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:key.interpolation='LINEAR'
    for event in item['events']:
        marker=baked.pose_markers.new(event['name']);marker.frame=event['frame']
    for c,mute in muted:c.mute=mute
    rig.animation_data.action=source
    if source.slots:rig.animation_data.action_slot=source.slots[0]
    bpy.context.scene.frame_set(item['frame_start']);bpy.context.view_layer.update()
    print('REBAKED',id,len(samples),'samples',flush=True)
    return baked

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--clip',action='append');parser.add_argument('--all',action='store_true');parser.add_argument('--no-save',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations']
    ids=[m['id'] for m in manifest] if args.all else args.clip or []
    if not ids:parser.error('Specify --clip ID or --all')
    for id in ids:rebake(bpy.data.objects['Operative_Rig'],id,manifest)
    if not args.no_save:bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
