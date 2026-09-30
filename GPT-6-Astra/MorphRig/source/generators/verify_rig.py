import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent))
import character,rig_tools
ROOT=character.ROOT
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'source/Character_Master.blend'))
rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];scene=bpy.context.scene
out=ROOT/'docs/rig_validation';out.mkdir(parents=True,exist_ok=True)
report={'morphs':{},'controls':{}}
cam=scene.camera;cam.location=(0,-1,1.685);cam.rotation_euler=(Vector((0,0,1.685))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=.28
scene.render.resolution_x=800;scene.render.resolution_y=800;scene.cycles.samples=24
for name,values in [('neutral',{}),('blink_left',{'blink.L':1}),('jaw_open',{'jaw_open':.8}),('AA',{'viseme_AA':1}),('MBP',{'viseme_MBP':1}),('asymmetric_joy',{'smile.L':.85,'brow_up.R':.5,'cheek.L':.3})]:
    rig_tools.reset_pose()
    for n,v in values.items():mesh.data.shape_keys.key_blocks[n].value=v
    rig.update_tag();bpy.context.view_layer.update();scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
    report['morphs'][name]={'values':values,'render':'docs/rig_validation/'+name+'.png'}
rig_tools.reset_pose();rig.update_tag();bpy.context.view_layer.update()
for side in ['L','R']:
    for limb in ['arm','leg']:
        rig_tools.reset_pose();report['controls']['match_'+limb+'_'+side]=rig_tools.match_switch(limb,side,True)
        rig_tools.match_switch(limb,side,False)
    rig_tools.reset_pose();p=rig.pose.bones['index.03.'+side];before=p.matrix.copy();rig['finger_curl.'+side]=1;rig.update_tag();bpy.context.view_layer.update();report['controls']['curl_'+side]={'tip_displacement_m':(p.tail-before@Vector((0,p.length,0))).length}
    rig_tools.reset_pose();rig_tools.match_switch('leg',side,True);p=rig.pose.bones['foot.'+side];before=p.head.copy();rig['foot_roll.'+side]=.5;rig.update_tag();bpy.context.view_layer.update();report['controls']['roll_'+side]={'ankle_displacement_m':(p.head-before).length}
rig_tools.reset_pose();before=rig.matrix_world.copy();rig['global_scale']=1.25;rig.update_tag();bpy.context.view_layer.update();report['controls']['global_scale']={'scale':list(rig.scale)};rig_tools.reset_pose()
dg=bpy.context.evaluated_depsgraph_get();ev=mesh.evaluated_get(dg);report['neutral_bounds_m']={'min':[min(v.co[i] for v in ev.data.vertices) for i in range(3)],'max':[max(v.co[i] for v in ev.data.vertices) for i in range(3)]}
report['deform_roots']=[b.name for b in rig.data.bones if b.use_deform and not b.parent]
report['loose_vertices']=len(set(range(len(mesh.data.vertices)))-set(i for p in mesh.data.polygons for i in p.vertices))
ROOT.joinpath('docs/rig_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
# Embed the exact editable utility source, ready for Run Script in Text Editor.
for filename in ['rig_tools.py','character.py']:
    text=bpy.data.texts.get(filename) or bpy.data.texts.new(filename);text.clear();text.write(Path(__file__).with_name(filename).read_text())
rig_tools.register();scene.camera.data.ortho_scale=2.23;cam.location=(2.7,-4.3,2.25);cam.rotation_euler=(Vector((0,0,.94))-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.resolution_x=1100;scene.render.resolution_y=1400
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'source/Character_Master.blend'))
