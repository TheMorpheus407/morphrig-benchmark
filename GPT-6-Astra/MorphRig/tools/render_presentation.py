"""Render the delivered Blender asset with a neutral inspection stage.

blender -b source/Operative.blend -P tools/render_presentation.py -- --mode turntable
Modes: turntable, motion, face, still. The source asset is never saved or changed.
"""
import argparse
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=['turntable','motion','face','still'],default='still')
parser.add_argument('--action',default='idle_relaxed')
parser.add_argument('--frame',type=int,default=1)
parser.add_argument('--view',choices=['front','side','back','top','face'],default='front')
parser.add_argument('--start',type=int,default=0)
parser.add_argument('--end',type=int)
parser.add_argument('--width',type=int,default=1920)
parser.add_argument('--height',type=int,default=1080)
parser.add_argument('--force',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
scene=bpy.context.scene
scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=args.width
scene.render.resolution_y=args.height
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=False
scene.render.fps=30
scene.render.image_settings.color_mode='RGB'
scene.world.color=(.12,.12,.12)
scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.19,.23,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.45
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
scene.view_settings.exposure=0

# Remove only staging objects, preserve all authored character geometry.
for obj in list(scene.objects):
    if obj.type in {'CAMERA','LIGHT'} or obj.name=='Studio_Floor':
        bpy.data.objects.remove(obj,do_unlink=True)
rig=bpy.data.objects.get('Operative_Rig') or next(o for o in scene.objects if o.type=='ARMATURE')
rig.animation_data_create()
for tr in rig.animation_data.nla_tracks: tr.mute=True
for o in scene.objects:
    if o.type=='MESH' and any(s in o.name.upper() for s in ('LOD1','LOD2')): o.hide_render=True

def point(obj,target): obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
def light(name,location,power,size):
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size
    o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=location;point(o,(0,0,1))
light('Inspection_Key',(2.8,-4.3,4.6),500,4)
light('Inspection_Fill',(-3,-1,2.4),350,3)
light('Inspection_Rim',(1.2,3,3.2),550,3)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.008))
ground=bpy.context.object;ground.name='Presentation_Stage'
mat=bpy.data.materials.new('Presentation_NeutralFloor');mat.diffuse_color=(.115,.13,.15,1);mat.use_nodes=True
mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.115,.13,.15,1)
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.82
ground.data.materials.append(mat)
camd=bpy.data.cameras.new('Inspection_Camera');cam=bpy.data.objects.new('Inspection_Camera',camd)
scene.collection.objects.link(cam);scene.camera=cam;camd.type='ORTHO';camd.ortho_scale=2.45;camd.lens=60;camd.clip_start=.01;camd.clip_end=300

def camera(view='front',angle=0,offset=(0,0,0)):
    ground.hide_render=(view=='face')
    offset=Vector(offset)
    target=Vector((0,0,.92))+offset
    aspect=scene.render.resolution_x/scene.render.resolution_y
    camd.ortho_scale=2.38*aspect
    if view=='face':
        target=Vector((0,-.025,1.67))+offset
        cam.location=Vector((.16,-2.3,1.71))+offset;camd.ortho_scale=.38*aspect
    elif view=='side': cam.location=Vector((4.7,-.08,1.40))+offset
    elif view=='back': cam.location=Vector((0,5,1.55))+offset
    elif view=='top': cam.location=Vector((2.4,-3.5,5.5))+offset;camd.ortho_scale=2.65*aspect
    else: cam.location=Vector((4.8*math.sin(angle),-4.8*math.cos(angle),1.80))+offset
    point(cam,target)

def assign_action(id,frame):
    action=bpy.data.actions.get(id)
    if action is None: raise RuntimeError('Missing required source action: '+id)
    rig.animation_data.action=action
    if action.slots:
        slots=[s for s in action.slots if s.target_id_type=='OBJECT']
        if slots:rig.animation_data.action_slot=slots[0]
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.data.shape_keys: continue
        key=obj.data.shape_keys
        fa=bpy.data.actions.get('FACE__'+id)
        if fa:
            key.animation_data_create();key.animation_data.action=fa
            if fa.slots:key.animation_data.action_slot=fa.slots[0]
    scene.frame_set(frame)
    bpy.context.view_layer.update()

motion_plan=[('idle_relaxed',2),('walk_f',2),('walk_l',2),('walk_b',2),('run_fr',2),('sprint_f',2),
    ('jump_start',.6),('jump_air',.6),('jump_land',.8),('dash_f',.5),('melee_1',1),('melee_2',1),('melee_3',1),
    ('ranged_burst',1),('reload',2.2),('cast_ground',1.2),('cast_self',1),
    ('channel_start',.6),('channel_loop',2),('channel_interrupt',.5),
    ('charge_start',.7),('charge_hold',1),('charge_release',.7),('deploy',1.7),
    ('uplink_start',.8),('uplink_loop',1.6),('uplink_cancel',.6),
    ('knockdown_back',1.4),('prone_back',1),('getup_back',2),
    ('death_front',2),('dead_front',1),('respawn',2),('greet',2),('victory',2)]

out=ROOT/'presentation/frames'/args.mode
out.mkdir(parents=True,exist_ok=True)
if args.mode=='still':
    assign_action(args.action,args.frame);camera(args.view)
    scene.render.filepath=str(ROOT/'docs/validation'/f'{args.action}_{args.frame}_{args.view}.png')
    bpy.ops.render.render(write_still=True)
else:
    plan=[]
    if args.mode=='turntable':
        plan=[('idle_relaxed',i/30) for i in range(240)]
    elif args.mode=='face':
        plan=[('dialogue',i/30) for i in range(420)]
    else:
        for clip,duration in motion_plan: plan.extend((clip,i/30) for i in range(round(duration*30)))
    cue=[]
    for i,(clip,time) in enumerate(plan):
        if i==0 or clip!=plan[i-1][0]:cue.append({'frame':i,'time':i/30,'clip':clip})
    (ROOT/'presentation'/f'{args.mode}_timeline.json').write_text(json.dumps({'fps':30,'frames':len(plan),'source':'source/Operative.blend','render':'Blender EEVEE, delivered real-time LOD0 mesh and materials','cues':cue},indent=2)+'\n')
    for i in range(args.start,min(args.end if args.end is not None else len(plan),len(plan))):
        path=out/f'{i:05d}.png'
        if path.exists() and not args.force:continue
        clip,time=plan[i];act=bpy.data.actions[clip];a,b=act.frame_range
        is_loop=clip.startswith(('idle','walk','run','sprint','prone')) or clip.endswith(('_loop','_hold')) or clip=='jump_air'
        f=a+((time*30)%(b-a) if is_loop and b>a else min(time*30,b-a))
        assign_action(clip,round(f))
        offset=rig.pose.bones['root'].matrix.translation if clip.startswith('dash') else (0,0,0)
        camera('face' if args.mode=='face' else 'front',i/len(plan)*2*math.pi if args.mode=='turntable' else .23,offset)
        scene.render.filepath=str(path)
        bpy.ops.render.render(write_still=True)
        if i%30==0:print('PRESENTATION_PROGRESS',args.mode,i,len(plan),flush=True)
