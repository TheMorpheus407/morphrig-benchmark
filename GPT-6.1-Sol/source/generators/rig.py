"""Editable animator rig, IK/FK matching, foot pivots and facial bone controls."""
import bpy, math
from mathutils import Vector, Matrix, Euler, Quaternion

BONES=[]
def bone(name,head,tail,parent=None):BONES.append((name,tuple(head),tuple(tail),parent))
def define_bones():
 BONES.clear();bone('root',(0,0,0),(0,0,.12));bone('pelvis',(0,0,.94),(0,0,1.05),'root')
 for name,z0,z1,parent in [('spine_01',1.05,1.17,'pelvis'),('spine_02',1.17,1.30,'spine_01'),('chest',1.30,1.46,'spine_02'),('neck',1.46,1.52,'chest'),('head',1.52,1.73,'neck')]:bone(name,(0,0,z0),(0,0,z1),parent)
 bone('jaw',(0,-.015,1.614),(0,-.065,1.565),'head');bone('tongue',(0,-.070,1.574),(0,-.091,1.574),'jaw')
 for side,s in [('L',-1),('R',1)]:
  bone('clavicle.'+side,(s*.035,0,1.39),(s*.19,0,1.39),'chest')
  bone('upper_arm.'+side,(s*.19,0,1.39),(s*.34,0,1.15),'clavicle.'+side)
  bone('forearm.'+side,(s*.34,0,1.15),(s*.40,-.015,.94),'upper_arm.'+side)
  bone('hand.'+side,(s*.40,-.015,.94),(s*.42,-.035,.85),'forearm.'+side)
  bone('arm_twist.'+side,(s*.245,0,1.302),(s*.29,0,1.23),'upper_arm.'+side)
  bone('wrist_twist.'+side,(s*.374,-.008,1.031),(s*.399,-.015,.945),'forearm.'+side)
  bone('thigh.'+side,(s*.10,0,.94),(s*.11,-.025,.53),'pelvis')
  bone('shin.'+side,(s*.11,-.025,.53),(s*.11,0,.10),'thigh.'+side)
  bone('foot.'+side,(s*.11,0,.10),(s*.11,-.14,.04),'shin.'+side)
  bone('toe.'+side,(s*.11,-.14,.04),(s*.11,-.185,.04),'foot.'+side)
  for n,x,length in [('index',-.027,.068),('middle',-.009,.075),('ring',.010,.071),('pinky',.027,.055)]:
   base=Vector((s*(.414+x),-.020,.857));ps=[base,base+Vector((0,-.002,-length*.40)),base+Vector((0,-.004,-length*.74)),base+Vector((0,-.006,-length))]
   for j in range(3):bone(f'{n}_{j+1:02}.{side}',ps[j],ps[j+1],'hand.'+side if j==0 else f'{n}_{j:02}.{side}')
  ps=[(s*.382,-.019,.914),(s*.363,-.032,.891),(s*.354,-.039,.867),(s*.357,-.043,.851)]
  for j in range(3):bone(f'thumb_{j+1:02}.{side}',ps[j],ps[j+1],'hand.'+side if j==0 else f'thumb_{j:02}.{side}')
  for n,h,t in [
   ('eye',(s*.035,-.066,1.666),(s*.035,-.096,1.666)),
   ('brow',(s*.035,-.089,1.69),(s*.035,-.119,1.69)),
   ('lid_upper',(s*.035,-.066,1.666),(s*.035,-.093,1.676)),
   ('lid_lower',(s*.035,-.066,1.666),(s*.035,-.093,1.656)),
   ('lip_corner',(s*.031,-.088,1.5825),(s*.045,-.088,1.5825)),
   ('cheek',(s*.05,-.08,1.63),(s*.05,-.108,1.63))]:bone(n+'.'+side,h,t,'head')
 bone('lip_upper',(0,-.085,1.586),(0,-.11,1.586),'head');bone('lip_lower',(0,-.085,1.578),(0,-.11,1.578),'jaw')
 bone('cell',(.395,.031,1.01),(.395,.031,1.078),'forearm.R');bone('beacon',(-.125,.118,.96),(-.125,.118,1.042),'pelvis')
 bone('blade',(.442,.012,1.087),(.481,-.003,.825),'forearm.R')
 bone('cable_01',(.10,.095,1.37),(.13,.123,1.31),'chest');bone('cable_02',(.13,.123,1.31),(.134,.148,1.23),'cable_01');bone('cable_03',(.134,.148,1.23),(.076,.114,1.18),'cable_02')
 return BONES

FACE_KEYS=['blink.L','blink.R','squint.L','squint.R','brow_raise.L','brow_raise.R','brow_lower.L','brow_lower.R','cheek.L','cheek.R','jaw','lip_close','smile.L','smile.R','frown.L','frown.R','width','pucker','funnel','tongue','eye_yaw.L','eye_yaw.R','eye_pitch.L','eye_pitch.R','viseme_closure','viseme_labiodental','viseme_open','viseme_wide','viseme_round','viseme_tongue','viseme_consonant']

def newbone(eb,name,h,t,parent=None,deform=False):
 b=eb.new(name);b.head=h;b.tail=t;b.use_deform=deform
 if parent:b.parent=eb[parent]
 return b

def create_rig(mesh):
 arm=bpy.data.armatures.new('Operative_Deformation_And_Controls');ob=bpy.data.objects.new('Operative_Rig',arm);bpy.context.collection.objects.link(ob)
 ob.show_in_front=True;arm.display_type='BBONE'
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.mode_set(mode='EDIT');eb=arm.edit_bones
 define_bones()
 for name,h,t,parent in BONES:newbone(eb,name,h,t,parent,True)
 newbone(eb,'CTRL_global',(0,0,0),(0,0,.24));newbone(eb,'CTRL_root',(0,0,0),(0,0,.12),'CTRL_global')
 for name in ['pelvis','spine_01','spine_02','chest','neck','head']:
  d=next(b for b in BONES if b[0]==name);parent='CTRL_root' if name=='pelvis' else 'CTRL_'+d[3]
  newbone(eb,'CTRL_'+name,d[1],d[2],parent)
 newbone(eb,'CTRL_settings',(0,.45,.85),(0,.45,1.03),'CTRL_global')
 newbone(eb,'CTRL_face',(0,-.25,1.7),(0,-.25,1.78),'CTRL_head')
 newbone(eb,'CTRL_look',(0,-.75,1.666),(0,-.75,1.76),'CTRL_global')
 for side,s in [('L',-1),('R',1)]:
  for part in ['clavicle','upper_arm','forearm','hand','thigh','shin','foot','toe']:
   d=next(b for b in BONES if b[0]==part+'.'+side)
   parent=('CTRL_chest' if part=='clavicle' else 'CTRL_pelvis' if part=='thigh' else 'FK_'+d[3])
   newbone(eb,'FK_'+part+'.'+side,d[1],d[2],parent)
  for typ,part in [('hand','hand'),('foot','foot')]:
   d=next(b for b in BONES if b[0]==part+'.'+side);newbone(eb,f'IK_{typ}.{side}',d[1],d[2],'CTRL_global')
  for name,p in [('elbow',(s*.42,-.33,1.16)),('knee',(s*.11,-.55,.53))]:newbone(eb,f'POLE_{name}.{side}',p,Vector(p)+Vector((0,0,.09)),'CTRL_global')
  for name,p in [('heel',(s*.11,.055,.025)),('toe',(s*.11,-.185,.025))]:newbone(eb,f'PIVOT_{name}.{side}',p,Vector(p)+Vector((0,0,.06)),'IK_foot.'+side if name=='heel' else 'PIVOT_heel.'+side)
  d=next(b for b in BONES if b[0]=='foot.'+side);newbone(eb,'MCH_ankle.'+side,d[1],d[2],'PIVOT_toe.'+side)
  for n in ['thumb','index','middle','ring','pinky']:
   for j in range(1,4):
    d=next(b for b in BONES if b[0]==f'{n}_{j:02}.{side}');newbone(eb,'CTRL_'+d[0],d[1],d[2],'FK_hand.'+side if j==1 else f'CTRL_{n}_{j-1:02}.{side}')
 for name in ['cell','beacon','blade','cable_01','cable_02','cable_03']:
  d=next(b for b in BONES if b[0]==name);newbone(eb,'CTRL_'+name,d[1],d[2],'CTRL_global')
 bpy.ops.object.mode_set(mode='POSE');pb=ob.pose.bones
 for p in pb:p.rotation_mode='QUATERNION'
 settings=pb['CTRL_settings'];face=pb['CTRL_face']
 for side in ['L','R']:
  for limb in ['arm','leg']:
   settings[f'ik_{limb}.{side}']=1.;settings.id_properties_ui(f'ik_{limb}.{side}').update(min=0,max=1,description='1 IK, 0 FK; use Match/Switch operators')
  settings['curl.'+side]=0.;settings['spread.'+side]=0.;settings['foot_roll.'+side]=0.;settings['heel.'+side]=0.;settings['toe.'+side]=0.
 for k in FACE_KEYS:
  face[k]=0.;face.id_properties_ui(k).update(min=-1 if 'eye_' in k else 0,max=1,description='Independent anatomical facial control; baked to deformation skeleton')
 for name in ['root','pelvis','spine_01','spine_02','chest','neck','head']:
  c=pb[name].constraints.new('COPY_TRANSFORMS');c.name='Animator control';c.target=ob;c.subtarget='CTRL_'+name
 for side,s in [('L',-1),('R',1)]:
  for part in ['clavicle','upper_arm','forearm','hand','thigh','shin','foot','toe']:
   c=pb[part+'.'+side].constraints.new('COPY_ROTATION');c.name='FK animator';c.target=ob;c.subtarget='FK_'+part+'.'+side;c.target_space='WORLD';c.owner_space='WORLD'
  for part,limb,target,pole in [('forearm','arm','hand','elbow'),('shin','leg','foot','knee')]:
   c=pb[part+'.'+side].constraints.new('IK');c.name='Two-bone '+limb+' IK';c.target=ob;c.subtarget=('MCH_ankle.' if target=='foot' else 'IK_hand.')+side;c.pole_target=ob;c.pole_subtarget='POLE_'+pole+'.'+side;c.chain_count=2;c.use_stretch=False
   # Pole angle calibrated against rest matrices after initial evaluation below.
   c.pole_angle=0
   dr=c.driver_add('influence').driver;v=dr.variables.new();v.name='ik';v.type='SINGLE_PROP';v.targets[0].id=ob;v.targets[0].data_path=f'pose.bones["CTRL_settings"]["ik_{limb}.{side}"]';dr.expression='ik'
  for part in ['hand','foot']:
   c=pb[part+'.'+side].constraints.new('COPY_ROTATION');c.name='IK end orientation';c.target=ob;c.subtarget=('MCH_ankle.' if part=='foot' else 'IK_hand.')+side
   dr=c.driver_add('influence').driver;v=dr.variables.new();v.name='ik';v.targets[0].id=ob;v.targets[0].data_path=f'pose.bones["CTRL_settings"]["ik_{"arm" if part=="hand" else "leg"}.{side}"]';dr.expression='ik'
  for n in ['thumb','index','middle','ring','pinky']:
   for j in range(1,4):
    name=f'{n}_{j:02}.{side}';c=pb[name].constraints.new('COPY_ROTATION');c.target=ob;c.subtarget='CTRL_'+name;c.owner_space='LOCAL';c.target_space='LOCAL';c.mix_mode='AFTER'
 for n in ['cell','beacon','blade','cable_01','cable_02','cable_03']:
  c=pb[n].constraints.new('COPY_TRANSFORMS');c.target=ob;c.subtarget='CTRL_'+n
 for side in ['L','R']:
  c=pb['arm_twist.'+side].constraints.new('COPY_ROTATION');c.target=ob;c.subtarget='upper_arm.'+side;c.target_space='LOCAL';c.owner_space='LOCAL';c.influence=.5
  c=pb['wrist_twist.'+side].constraints.new('COPY_ROTATION');c.target=ob;c.subtarget='hand.'+side;c.target_space='LOCAL';c.owner_space='LOCAL';c.influence=.45
 bpy.ops.object.mode_set(mode='OBJECT')
 deform=arm.collections.new('Deformation (exported)');controls=arm.collections.new('Animator controls');fk=arm.collections.new('FK limbs');facecol=arm.collections.new('Face and secondary')
 for b in arm.bones:
  (deform if b.use_deform else fk if b.name.startswith('FK_') else facecol if 'face' in b.name or 'cable' in b.name else controls).assign(b)
  b.color.palette='THEME04' if b.name.startswith('IK_') else 'THEME03' if b.name.startswith('POLE') else 'THEME09' if not b.use_deform else 'DEFAULT'
 deform.is_visible=False;fk.is_visible=False
 mod=mesh.modifiers.new('Volume preserving skin','ARMATURE');mod.object=ob;mod.use_deform_preserve_volume=True;mesh.parent=ob
 # Calibrate IK pole angles by actual rest-joint error, maintaining matching bind pose.
 for side in ['L','R']:
  for part,joint in [('forearm','forearm'),('shin','shin')]:
   c=pb[part+'.'+side].constraints.get('Two-bone '+('arm' if part=='forearm' else 'leg')+' IK')
   expected=ob.data.bones[joint+'.'+side].head_local;best=(1e9,0)
   for i in range(72):
    a=-math.pi+i*math.tau/72;c.pole_angle=a;ob.update_tag();bpy.context.view_layer.update();error=(pb[joint+'.'+side].head-expected).length
    if error<best[0]:best=(error,a)
   c.pole_angle=best[1]
 ob.update_tag();bpy.context.view_layer.update();return ob


def matrix_at(ob,name,position,rotation=None):
 b=ob.data.bones[name];q=b.matrix_local.to_quaternion()
 if rotation is not None:q=Euler(rotation,'XYZ').to_quaternion()@q
 return Matrix.Translation(Vector(position))@q.to_matrix().to_4x4()

def world_euler_delta(pb,rot):
 # Map global XYZ rotation onto rest-bone local basis.
 q=pb.bone.matrix_local.to_quaternion();pb.rotation_quaternion=q.inverted()@Euler(rot,'XYZ').to_quaternion()@q


def apply_face(ob,values):
 pb=ob.pose.bones;f=pb['CTRL_face']
 for k in FACE_KEYS:f[k]=float(values.get(k,0))

 ob.update_tag();bpy.context.view_layer.update()


def reset(ob):
 for p in ob.pose.bones:p.location=(0,0,0);p.rotation_quaternion=(1,0,0,0);p.scale=(1,1,1)
 for k in FACE_KEYS:ob.pose.bones['CTRL_face'][k]=0.
 for k in ob.pose.bones['CTRL_settings'].keys():ob.pose.bones['CTRL_settings'][k]=1. if k.startswith('ik_') else 0.
 for side in ['L','R']:
  for k in ['arm','leg']:ob.pose.bones['CTRL_settings'][f'ik_{k}.{side}']=1.
 ob.update_tag();bpy.context.view_layer.update()


def apply_pose(ob,p,t=0):
 pb=ob.pose.bones;pelvis=Vector(p.get('pelvis',(0,0,.94)));pelrot=p.get('pelvis_rot',(0,0,0));pq=Euler(pelrot,'XYZ').to_quaternion();torso=p.get('torso',(0,0,0));tq=pq@Euler(torso,'XYZ').to_quaternion();cq=tq@Euler(p.get('chest',(0,0,0)),'XYZ').to_quaternion();hq=cq@Euler(p.get('head',(0,0,0)),'XYZ').to_quaternion()
 root_delta=Vector(p.get('root',(0,0,0)));pelvis+=root_delta
 pb['CTRL_root'].matrix=matrix_at(ob,'CTRL_root',root_delta)
 ob.update_tag();bpy.context.view_layer.update()
 pb['CTRL_pelvis'].matrix=Matrix.Translation(pelvis)@pq.to_matrix().to_4x4()@ob.data.bones['CTRL_pelvis'].matrix_local.to_quaternion().to_matrix().to_4x4()
 ob.update_tag();bpy.context.view_layer.update()
 pos=pelvis+pq@Vector((0,0,.11))
 for name,z,rot in [('spine_01',.12,tq),('spine_02',.13,tq),('chest',.16,cq),('neck',.06,cq),('head',0,hq)]:
  b=ob.data.bones['CTRL_'+name];pb['CTRL_'+name].matrix=Matrix.Translation(pos)@rot.to_matrix().to_4x4()@b.matrix_local.to_quaternion().to_matrix().to_4x4();pos+=rot@Vector((0,0,z));ob.update_tag();bpy.context.view_layer.update()
 for side,s in [('L',-1),('R',1)]:
  wrist=p.get('hands',{}).get(side,(s*.40,-.015,.94));ankle=p.get('feet',{}).get(side,(s*.11,0,.10))
  pb['IK_hand.'+side].matrix=matrix_at(ob,'IK_hand.'+side,Vector(wrist)+root_delta,p.get('hand_rot',{}).get(side,(0,0,0)))
  fr=list(p.get('foot_rot',{}).get(side,(0,0,0)));settings=pb['CTRL_settings']
  # Foot-roll chain rotates around actual heel and toe ground pivots.
  pb['IK_foot.'+side].matrix=matrix_at(ob,'IK_foot.'+side,Vector(ankle)+root_delta,fr)
  for pole,default in [('elbow',(s*.47,-.31,1.15)),('knee',(s*.11,-.55,.53))]:
   target=p.get('poles',{}).get(pole+'.'+side,default);pb['POLE_'+pole+'.'+side].matrix=matrix_at(ob,'POLE_'+pole+'.'+side,Vector(target)+root_delta)
  settings['spread.'+side]=float(p.get('spreads',{}).get(side,0))
  curls=p.get('curls',{}).get(side,[.06]*5)
  for i,n in enumerate(['thumb','index','middle','ring','pinky']):
   for j in range(1,4):
    pp=pb[f'CTRL_{n}_{j:02}.{side}'];world_euler_delta(pp,(-float(curls[i])*(.70 if n=='thumb' else 1.13),0,0))
    # Global finger spread is provided by the deform-bone control driver.
  world_euler_delta(pb['FK_toe.'+side],(0,0,0))
 ob.update_tag();bpy.context.view_layer.update()
 # Rigid prop controls follow evaluated attachment transform unless explicitly manipulated.
 for name,parent in [('cell','forearm.R'),('beacon','pelvis'),('blade','forearm.R')]:
  if name in p and isinstance(p[name],(dict,list,tuple)):
   target=p[name];position=target.get('position') if isinstance(target,dict) else target
   rot=target.get('rotation',(0,0,0)) if isinstance(target,dict) else (0,0,0)
   pb['CTRL_'+name].matrix=matrix_at(ob,'CTRL_'+name,Vector(position)+root_delta,rot)
  else:
   rest=ob.data.bones[parent].matrix_local.inverted()@ob.data.bones[name].matrix_local;pb['CTRL_'+name].matrix=pb[parent].matrix@rest
  if name=='blade':pb['CTRL_blade'].scale=(1,1,1) if p.get('blade',0)>0 else (1,.20,1)
 for i,n in enumerate(['cable_01','cable_02','cable_03']):
  parent='chest' if i==0 else ['cable_01','cable_02'][i-1]
  rest=ob.data.bones[parent].matrix_local.inverted()@ob.data.bones[n].matrix_local
  secondary=p.get('secondary',(0,0,0));wiggle=Euler(tuple(float(a)*(.72**i) for a in secondary),'XYZ').to_matrix().to_4x4()
  pb['CTRL_'+n].matrix=pb[parent].matrix@rest@wiggle;ob.update_tag();bpy.context.view_layer.update()
 apply_face(ob,p.get('face',{}));ob.update_tag();bpy.context.view_layer.update()


PANEL_SCRIPT=r'''import bpy, math
from mathutils import Vector, Quaternion
class MORPHRIG_OT_reset(bpy.types.Operator):
 bl_idname='morphrig.reset';bl_label='Reset to neutral pose'
 def execute(self,context):
  ob=bpy.data.objects.get('Operative_Rig')
  if ob.animation_data:ob.animation_data.action=None
  for p in ob.pose.bones:p.location=(0,0,0);p.rotation_quaternion=(1,0,0,0);p.scale=(1,1,1)
  for k in ob.pose.bones['CTRL_face'].keys():ob.pose.bones['CTRL_face'][k]=0.
  for k in ob.pose.bones['CTRL_settings'].keys():ob.pose.bones['CTRL_settings'][k]=1. if k.startswith('ik_') else 0.
  ob.update_tag();context.view_layer.update();return {'FINISHED'}
class MORPHRIG_OT_switch(bpy.types.Operator):
 bl_idname='morphrig.switch';bl_label='Match and switch IK/FK'
 side:bpy.props.EnumProperty(items=[('L','Left',''),('R','Right','')]);limb:bpy.props.EnumProperty(items=[('arm','Arm',''),('leg','Leg','')])
 def execute(self,context):
  ob=bpy.data.objects.get('Operative_Rig');pb=ob.pose.bones;s=self.side;settings=pb['CTRL_settings'];prop='ik_'+self.limb+'.'+s
  parts=['upper_arm','forearm','hand'] if self.limb=='arm' else ['thigh','shin','foot'];mats=[pb[n+'.'+s].matrix.copy() for n in parts]
  if settings[prop]>.5:
   for n,m in zip(parts,mats):
    pb['FK_'+n+'.'+s].matrix=m;context.view_layer.update()
   settings[prop]=0.
  else:
   if self.limb=='leg':
    for k in ['foot_roll','heel','toe']:settings[k+'.'+s]=0.
   pb['IK_'+parts[-1]+'.'+s].matrix=mats[-1]
   start=mats[0].translation;end=mats[-1].translation;joint=mats[1].translation;axis=(end-start).normalized()
   projection=start+axis*((joint-start).dot(axis));desired=(joint-projection).normalized()
   if desired.length<.001:desired=Vector((0,-1,0))
   pole='POLE_'+('elbow' if self.limb=='arm' else 'knee')+'.'+s
   settings[prop]=1.
   def evaluate(angle):
    direction=Quaternion(axis,angle)@desired
    matrix=pb[pole].matrix.copy();matrix.translation=projection+direction*.40;pb[pole].matrix=matrix
    ob.update_tag();context.view_layer.update()
    return (pb[parts[1]+'.'+s].head-joint).length
   step=math.tau/72
   best=min((evaluate(-math.pi+i*step),-math.pi+i*step) for i in range(72))[1]
   lo,hi=best-step,best+step
   for iteration in range(20):
    a=lo+(hi-lo)/3;b=hi-(hi-lo)/3
    if evaluate(a)<evaluate(b):hi=b
    else:lo=a
   evaluate((lo+hi)/2)


  ob.update_tag();context.view_layer.update();return {'FINISHED'}
class MORPHRIG_PT_tools(bpy.types.Panel):
 bl_label='Operative animator';bl_idname='MORPHRIG_PT_tools';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Operative'
 def draw(self,context):
  layout=self.layout;ob=bpy.data.objects.get('Operative_Rig')
  if not ob:return
  layout.operator('morphrig.reset')
  for side in ['L','R']:
   row=layout.row()
   for limb in ['arm','leg']:
    op=row.operator('morphrig.switch',text=side+' '+limb+' IK/FK');op.side=side;op.limb=limb
  layout.label(text='Foot roll, heel / toe and hand controls:')
  s=ob.pose.bones['CTRL_settings']
  for side in ['L','R']:
   for name in ['curl','spread','foot_roll','heel','toe']:layout.prop(s,'["'+name+'.'+side+'"]',text=name+' '+side)
  layout.label(text='Independent face / viseme controls:')
  f=ob.pose.bones['CTRL_face']
  for k in f.keys():layout.prop(f,'["'+k+'"]',text=k)
for c in [MORPHRIG_OT_reset,MORPHRIG_OT_switch,MORPHRIG_PT_tools]:
 try:bpy.utils.register_class(c)
 except ValueError:pass
'''

def install_panel():
 t=bpy.data.texts.new('Operative_Animator_Panel.py');t.write(PANEL_SCRIPT);t.use_module=True;exec(PANEL_SCRIPT,{})


def add_face_drivers(ob):
 """Single editable slider source, evaluated live in Blender and baked on export."""
 pb=ob.pose.bones
 def drive(bone,path,index,expression,variables):
  d=pb[bone].driver_add(path,index).driver
  for var,key in variables.items():
   v=d.variables.new();v.name=var;v.type='SINGLE_PROP';v.targets[0].id=ob;v.targets[0].data_path='pose.bones["CTRL_face"]["'+key+'"]'
  d.expression=expression
 def vector_driver(bone,path,world_vector,expression,variables):
  local=pb[bone].bone.matrix_local.to_3x3().inverted()@Vector(world_vector)
  for i,c in enumerate(local):
   if abs(c)>1e-8:drive(bone,path,i,f'({expression})*({c:.9f})',variables)
 for name in ['jaw','tongue','eye.L','eye.R','lid_upper.L','lid_upper.R','lid_lower.L','lid_lower.R']:pb[name].rotation_mode='XYZ'
 visvars={'jaw':'jaw','vo':'viseme_open','vw':'viseme_wide','vr':'viseme_round','vl':'viseme_labiodental','vt':'viseme_tongue','vc':'viseme_consonant','closure':'viseme_closure'}
 effective_jaw='max(jaw,.70*vo,.30*vw,.30*vr,.12*vl,.22*vt,.12*vc)*(1-closure)'
 vector_driver('jaw','rotation_euler',(.36,0,0),effective_jaw,visvars)
 vector_driver('tongue','rotation_euler',(-.23,0,0),'max(tongue,vt)',{'tongue':'tongue','vt':'viseme_tongue'})
 vector_driver('tongue','location',(0,-.006,.008),'max(tongue,vt)',{'tongue':'tongue','vt':'viseme_tongue'})
 for side,s in [('L',-1),('R',1)]:
  vector_driver('lid_upper.'+side,'rotation_euler',(.80,0,0),'min(1,blink+.45*squint)-pitch*.30',{'blink':'blink.'+side,'squint':'squint.'+side,'pitch':'eye_pitch.'+side})
  vector_driver('lid_lower.'+side,'rotation_euler',(-.35,0,0),'min(1,blink+.45*squint)+pitch*.30',{'blink':'blink.'+side,'squint':'squint.'+side,'pitch':'eye_pitch.'+side})
  # Eye X pitch and Z yaw are orthogonal in authored forward-facing eye basis.
  local=pb['eye.'+side].bone.matrix_local.to_3x3().inverted()
  pitch=local@Vector((-1,0,0));yaw=local@Vector((0,0,1))
  for i in range(3):drive('eye.'+side,'rotation_euler',i,f'pitch*{pitch[i]:.9f}+yaw*{yaw[i]:.9f}',{'pitch':'eye_pitch.'+side,'yaw':'eye_yaw.'+side})
  vector_driver('brow.'+side,'location',(0,0,1),'.009*raise_b-.006*lower_b',{'raise_b':'brow_raise.'+side,'lower_b':'brow_lower.'+side})
  local=pb['cheek.'+side].bone.matrix_local.to_3x3().inverted()@Vector((0,-.003,.005))
  for i in range(3):drive('cheek.'+side,'location',i,f'cheek*{local[i]:.9f}',{'cheek':'cheek.'+side})
  local=pb['lip_corner.'+side].bone.matrix_local.to_3x3().inverted()
  for i in range(3):drive('lip_corner.'+side,'location',i,f'{local[i][0]:.9f}*({s}*(.006*max(width,.85*vw,.15*vc)-.006*max(pucker,.85*vr)))+{local[i][1]:.9f}*(-.006*max(pucker,.85*vr))+{local[i][2]:.9f}*(.007*smile-.006*frown)',{'width':'width','pucker':'pucker','smile':'smile.'+side,'frown':'frown.'+side,'vr':'viseme_round','vw':'viseme_wide','vc':'viseme_consonant'})
 for name,low in [('lip_upper',False),('lip_lower',True)]:
  local=pb[name].bone.matrix_local.to_3x3().inverted()
  for i in range(3):
   zexpr='.0003*max(close,closure)+.024*('+effective_jaw+')*max(close,closure)+.003*vl' if low else '-.0003*max(close,closure)+.001*('+effective_jaw+')'
   drive(name,'location',i,f'{local[i][1]:.9f}*(-.008*(max(pucker,.85*vr)+.6*funnel))+{local[i][2]:.9f}*({zexpr})',dict(visvars,close='lip_close',pucker='pucker',funnel='funnel'))
  # Bone local X corresponds sideways for lip; width is a live scale channel.
  drive(name,'scale',0,'max(.72,1-.30*max(pucker,.85*vr)+.14*max(width,.85*vw,.15*vc))',{'pucker':'pucker','width':'width','vr':'viseme_round','vw':'viseme_wide','vc':'viseme_consonant'})
 pb['CTRL_face']['lip_close']=0.;ob.update_tag();bpy.context.view_layer.update()


def add_limb_control_drivers(ob):
 pb=ob.pose.bones
 def drive(bone,path,index,expression,variables):
  d=pb[bone].driver_add(path,index).driver
  for var,key in variables.items():
   v=d.variables.new();v.name=var;v.targets[0].id=ob;v.targets[0].data_path='pose.bones["CTRL_settings"]["'+key+'"]'
  d.expression=expression
 for side in ['L','R']:
  for name,expr in [('heel','min(0,roll)+heel'),('toe','max(0,roll)+toe')]:
   bone='PIVOT_'+name+'.'+side;pb[bone].rotation_mode='XYZ'
   local=pb[bone].bone.matrix_local.to_3x3().inverted()@Vector((1,0,0))
   for i,c in enumerate(local):drive(bone,'rotation_euler',i,f'({expr})*{c:.9f}',{'roll':'foot_roll.'+side,'heel':'heel.'+side,'toe':'toe.'+side})
  for i,n in enumerate(['thumb','index','middle','ring','pinky']):
   for j in range(1,4):
    bone=f'{n}_{j:02}.{side}';pb[bone].rotation_mode='XYZ';local=pb[bone].bone.matrix_local.to_3x3().inverted();x=local@Vector((1,0,0));z=local@Vector((0,0,1))
    for a in range(3):drive(bone,'rotation_euler',a,f'-curl*{.7 if n=="thumb" else 1.13}*{x[a]:.9f}+spread*{(i-2)*.04 if j==1 else 0}*{z[a]:.9f}',{'curl':'curl.'+side,'spread':'spread.'+side})
 ob.update_tag();bpy.context.view_layer.update()


def add_look_controls(ob):
 pb=ob.pose.bones;s=pb['CTRL_settings'];s['eye_look_at']=0.;s['head_look_at']=0.
 for name,axis,key in [('eye.L','TRACK_Y','eye_look_at'),('eye.R','TRACK_Y','eye_look_at'),('CTRL_head','TRACK_Z','head_look_at')]:
  c=pb[name].constraints.new('DAMPED_TRACK');c.name='Look-at target (optional)';c.target=ob;c.subtarget='CTRL_look';c.track_axis=axis
  d=c.driver_add('influence').driver;v=d.variables.new();v.name='weight';v.targets[0].id=ob;v.targets[0].data_path='pose.bones["CTRL_settings"]["'+key+'"]';d.expression='min(1,max(0,weight))'
 ob.update_tag();bpy.context.view_layer.update()
