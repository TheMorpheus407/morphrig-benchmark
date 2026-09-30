"""Editable animator tools. Run this text in Blender to install the MorphRig panel."""
import bpy, math
from mathutils import Vector, Matrix

EXPRESSION_PRESETS={
 'neutral':{},
 'joy_confidence':{'smile.L':.85,'smile.R':.65,'cheek.L':.4,'cheek.R':.4,'brow_up.L':.2},
 'anger':{'brow_down.L':.9,'brow_down.R':.9,'squint.L':.35,'squint.R':.35,'lip_close':.65},
 'concern_sadness':{'brow_up.L':.6,'brow_up.R':.45,'frown.L':.65,'frown.R':.8},
 'surprise':{'brow_up.L':1,'brow_up.R':1,'jaw_open':.7,'funnel':.4},
 'pain':{'blink.L':.85,'squint.R':.8,'brow_down.L':.7,'frown.L':.6,'jaw_open':.3},
 'focus':{'squint.L':.4,'squint.R':.4,'brow_down.L':.4,'brow_down.R':.3,'lip_close':.4}}

def get_rig(): return bpy.data.objects['Operative_Rig']

def reset_pose(rig=None, detach_action=True):
    rig=rig or get_rig()
    if detach_action and rig.animation_data:rig.animation_data.action=None
    for key in list(rig.keys()):
        if isinstance(rig[key],(int,float)):rig[key]=1.0 if key=='global_scale' else 0.0
    for pb in rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
    for ob in bpy.data.objects:
        if ob.type=='MESH' and ob.data.shape_keys and ob.name.startswith('Operative_LOD'):
            if detach_action and ob.data.shape_keys.animation_data:ob.data.shape_keys.animation_data.action=None
            for key in ob.data.shape_keys.key_blocks:
                if key.name!='Basis':key.value=0
    rig.update_tag();bpy.context.view_layer.update()

def expression(name, mesh=None):
    obs=[mesh] if mesh else [o for o in bpy.data.objects if o.name.startswith('Operative_LOD')]
    for ob in obs:
        if not ob or not ob.data.shape_keys:continue
        for key in ob.data.shape_keys.key_blocks:
            if key.name!='Basis' and not key.name.startswith(('shoulder_','hip_','wrist_')):key.value=EXPRESSION_PRESETS[name].get(key.name,0)
    bpy.context.view_layer.update()

def match_switch(limb='arm',side='L',to_ik=True,rig=None):
    """Keep world pose when switching; calibrate the pole plane against captured FK.
    Operates at current frame. Set keys afterward if the switch should be animated.
    """
    rig=rig or get_rig();rig.update_tag();bpy.context.view_layer.update();p=rig.pose.bones
    first,second,end=('upper_arm','forearm','hand') if limb=='arm' else ('thigh','shin','foot')
    names=[x+'.'+side for x in [first,second,end]];matrices={n:p[n].matrix.copy() for n in names}
    prop=limb+'_ik.'+side
    if not to_ik:
        rig[prop]=0.;rig.update_tag();bpy.context.view_layer.update()
        for n in names:p[n].matrix=matrices[n];rig.update_tag();bpy.context.view_layer.update()
        return
    if limb=='leg':
        for key in ['foot_roll','heel_pivot','toe_pivot']:rig[key+'.'+side]=0
        rig.update_tag();bpy.context.view_layer.update()
    target='CTRL_'+('hand_ik' if limb=='arm' else 'foot_ik')+'.'+side
    pole='CTRL_'+('elbow_pole' if limb=='arm' else 'knee_pole')+'.'+side
    a=matrices[names[0]].translation;b=matrices[names[1]].translation;c=matrices[names[2]].translation
    direction=(c-a).normalized();projected=a+direction*(b-a).dot(direction);normal=b-projected
    if normal.length<.0001:normal=Vector((0,1 if limb=='arm' else -1,0))
    normal.normalize();pole_pos=b+normal*.4
    p[target].matrix=matrices[names[2]]
    pm=p[pole].matrix.copy();pm.translation=pole_pos;p[pole].matrix=pm
    rig[prop]=1.;rig.update_tag();bpy.context.view_layer.update();con=p[names[1]].constraints['Animator '+limb+' IK']
    # Blender's pole-angle definition depends on rest roll. Measured minimization
    # avoids hardcoded mirrored offsets and preserves arbitrary posed planes.
    best=(1e9,0.)
    for i in range(73):
        angle=-math.pi+i*2*math.pi/72;con.pole_angle=angle;rig.update_tag();bpy.context.view_layer.update()
        error=(p[names[1]].head-b).length
        if error<best[0]:best=(error,angle)
    center=best[1]
    for i in range(41):
        angle=center+(i-20)*math.pi/720;con.pole_angle=angle;rig.update_tag();bpy.context.view_layer.update();error=(p[names[1]].head-b).length
        if error<best[0]:best=(error,angle)
    con.pole_angle=best[1];rig.update_tag();bpy.context.view_layer.update()
    return {'joint_error_m':best[0],'end_error_m':(p[names[2]].head-c).length}

def bake_secondary(start,end,rig=None,strength=.15):
    """Deterministic spring driven from pelvis changes, fixed30Hz integration."""
    rig=rig or get_rig();scene=bpy.context.scene;state=0.;velocity=0.;previous=None
    for f in range(start,end+1):
        scene.frame_set(f);pelvis=rig.pose.bones['pelvis'].matrix.translation.copy()
        impulse=0 if previous is None else (pelvis-previous).y*12;previous=pelvis
        velocity+=(impulse-state*22-velocity*6)/30;state+=velocity/30
        for i,n in enumerate(['cable.01','cable.02']):
            pb=rig.pose.bones[n];pb.rotation_euler.x=max(-.4,min(.4,state*strength*(i+1)));pb.keyframe_insert('rotation_euler',frame=f,group='Secondary cable')

class MORPHRIG_OT_reset(bpy.types.Operator):
    bl_idname='morphrig.reset_pose';bl_label='Reset character pose';bl_options={'UNDO'}
    def execute(self,context):reset_pose();return {'FINISHED'}
class MORPHRIG_OT_match(bpy.types.Operator):
    bl_idname='morphrig.match_switch';bl_label='Match IK/FK';bl_options={'UNDO'}
    limb:bpy.props.StringProperty(default='arm');side:bpy.props.StringProperty(default='L');to_ik:bpy.props.BoolProperty(default=True)
    def execute(self,context):match_switch(self.limb,self.side,self.to_ik);return {'FINISHED'}
class MORPHRIG_PT_controls(bpy.types.Panel):
    bl_label='MorphRig Animator';bl_idname='MORPHRIG_PT_controls';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='MorphRig'
    def draw(self,context):
        r=bpy.data.objects.get('Operative_Rig');l=self.layout
        if not r:return
        l.operator('morphrig.reset_pose');l.prop(r,'["global_scale"]',text='Global scale')
        for side in ['L','R']:
            box=l.box();box.label(text='Left' if side=='L' else 'Right')
            for limb in ['arm','leg']:
                row=box.row()
                for target in [True,False]:
                    op=row.operator('morphrig.match_switch',text=limb+' → '+('IK' if target else 'FK'));op.side=side;op.limb=limb;op.to_ik=target
            for prop in ['finger_curl','finger_spread','foot_roll','heel_pivot','toe_pivot']:box.prop(r,'["'+prop+'.'+side+'"]',text=prop.replace('_',' ').title())
        l.prop(r,'["look_at"]',text='Look target blend')
        ob=bpy.data.objects.get('Operative_LOD0')
        if ob:
            box=l.box();box.label(text='Face / corrective sliders')
            for key in ob.data.shape_keys.key_blocks:
                if key.name!='Basis':box.prop(key,'value',text=key.name)

def register():
    for cls in [MORPHRIG_OT_reset,MORPHRIG_OT_match,MORPHRIG_PT_controls]:
        try:bpy.utils.register_class(cls)
        except ValueError:pass

if __name__=='__main__':register()
