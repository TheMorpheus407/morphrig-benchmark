"""Original MorphRig Operative. Procedural mesh data, rig and editable materials.
Run: blender -b --factory-startup -P character.py
All lengths are metres. Z up, -Y forward; anatomical left is +X.
"""
import bpy, math, json, os, sys
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[2]
FACE_KEYS = ['blink.L','blink.R','squint.L','squint.R','brow_up.L','brow_up.R',
 'brow_down.L','brow_down.R','cheek.L','cheek.R','smile.L','smile.R','frown.L','frown.R',
 'jaw_open','lip_close','mouth_wide','pucker','funnel','viseme_AA','viseme_EE','viseme_OH',
 'viseme_OO','viseme_FV','viseme_MBP','viseme_L','viseme_TH','shoulder_raise.L','shoulder_raise.R',
 'hip_flex.L','hip_flex.R','wrist_flex.L','wrist_flex.R']
MAT_NAMES=['M_Skin','M_Weave','M_Ceramic','M_Alloy','M_TeamAccent','M_Hair','M_EyeWhite','M_Iris']

def skeleton_spec():
    b={}
    def add(n,h,t,p=None): b[n]={'head':h,'tail':t,'parent':p,'deform':True}
    add('root',(0,0,0),(0,0,.10))
    add('pelvis',(0,0,.94),(0,0,1.05),'root')
    add('spine_01',(0,0,1.05),(0,0,1.18),'pelvis')
    add('spine_02',(0,0,1.18),(0,0,1.32),'spine_01')
    add('chest',(0,0,1.32),(0,0,1.47),'spine_02')
    add('neck',(0,0,1.47),(0,0,1.58),'chest')
    add('head',(0,0,1.58),(0,0,1.80),'neck')
    add('jaw',(0,.018,1.652),(0,-.065,1.602),'head')
    add('tongue',(0,-.058,1.616),(0,-.097,1.616),'jaw')
    for side,s in [('L',1),('R',-1)]:
        add('clavicle.'+side,(0,0,1.445),(s*.20,0,1.46),'chest')
        add('upper_arm.'+side,(s*.20,0,1.46),(s*.38,-.018,1.26),'clavicle.'+side)
        add('forearm.'+side,(s*.38,-.018,1.26),(s*.53,-.018,1.08),'upper_arm.'+side)
        add('hand.'+side,(s*.53,-.018,1.08),(s*.59,-.024,1.015),'forearm.'+side)
        # Finger travel continues down the forearm axis. Finger separation is Y.
        for i,(finger,ln) in enumerate([('index',.081),('middle',.09),('ring',.083),('pinky',.064)]):
            start=Vector((s*(.576+(i==3)*-.008),-.052+i*.022,1.027+(i==3)*.005))
            d=Vector((s*.65,0,-.76))
            last='hand.'+side
            for j,fraction in enumerate([.44,.33,.23]):
                end=start+d*ln*fraction
                name=f'{finger}.{j+1:02d}.{side}'; add(name,tuple(start),tuple(end),last)
                last=name; start=end
        st=Vector((s*.55,-.058,1.06)); d=Vector((s*.15,-.8,-.58))
        last='hand.'+side
        for j,ln in enumerate([.026,.023,.020]):
            en=st+d*ln; n=f'thumb.{j+1:02d}.{side}';add(n,tuple(st),tuple(en),last);last=n;st=en
        add('thigh.'+side,(s*.09,0,.94),(s*.10,-.012,.52),'pelvis')
        add('shin.'+side,(s*.10,-.012,.52),(s*.105,0,.11),'thigh.'+side)
        add('foot.'+side,(s*.105,0,.11),(s*.105,-.13,.055),'shin.'+side)
        add('toe.'+side,(s*.105,-.13,.055),(s*.105,-.23,.045),'foot.'+side)
        add('eye.'+side,(s*.031,-.052,1.693),(s*.031,-.077,1.693),'head')
    add('emitter_muzzle',(-.517,-.082,1.102),(-.533,-.082,1.082),'forearm.R')
    add('blade_base',(-.449,.051,1.185),(-.48,.051,1.147),'forearm.R')
    add('blade_tip',(-.635,.051,.966),(-.65,.051,.95),'blade_base')
    add('cell',(-.434,-.066,1.217),(-.46,-.066,1.186),'forearm.R')
    add('beacon',(.16,.005,.99),(.16,.005,1.06),'pelvis')
    add('cable.01',(.09,.075,1.14),(.17,.075,1.025),'pelvis')
    add('cable.02',(.17,.075,1.025),(.155,.075,.91),'cable.01')
    return b

def write_contract():
    ROOT.joinpath('docs').mkdir(parents=True,exist_ok=True)
    data={'armature':'Operative_Rig','face_mesh':'Operative_LOD0','units':'metres','height_m':1.80,
       'source_axes':{'forward':'-Y','up':'+Z','anatomical_left':'+X'},'bones':skeleton_spec(),
       'bone_roll':'align_roll global +Y; local +Y follows bone','face_shape_keys':FACE_KEYS,
       'material_slots':MAT_NAMES,'props':{'emitter':'forearm.R','blade':'blade_base','cell':'cell','beacon':'beacon'},
       'controls':{'ik_targets':['CTRL_hand_ik.L','CTRL_hand_ik.R','CTRL_foot_ik.L','CTRL_foot_ik.R'],
       'pole_vectors':['CTRL_elbow_pole.L','CTRL_elbow_pole.R','CTRL_knee_pole.L','CTRL_knee_pole.R'],
       'ik_blends':'rig properties arm_ik.L/R, leg_ik.L/R, default zero (FK)',
       'fk':'deformation pose bones are directly keyable in FK mode'},
       'source':'source/generators/character.py','authoring':'Original generated mesh data; editable quad lofts and face feature loops'}
    data['unreal_import_name_mapping']={'rule':'FBX import replaces periods with underscores; verified in UE5.8.3 pilot import.','bones':{n:n.replace('.','_') for n in data['bones']},'morphs':{n:n.replace('.','_') for n in FACE_KEYS if n!='wrist_flex.R'}}
    data['reserved_zero_source_shapes']={'wrist_flex.R':'Zero authored source displacement on the rigid cybernetic forearm; intentionally omitted by the final Unreal importer. The source slider remains reserved for future authoring.'}
    data.update({'unreal_axes': {'forward': '+X', 'right': '+Y', 'up': '+Z', 'anatomical_left': '-Y', 'units': 'centimetres', 'source_to_unreal_position': '(X_UE,Y_UE,Z_UE)=(-100*Y_Blender,-100*X_Blender,100*Z_Blender)', 'bone_axis_note': 'Bone local axes follow imported reference transforms; world up is not the local Z axis of every bone. Root local Y follows its vertical bone.'}, 'export_import_contract': {'source_object_scale': [1, 1, 1], 'source_scene_unit_scale_m': 1, 'temporary_export_data_multiplier': 100, 'temporary_export_scene_unit_scale_m': 0.01, 'fbx_axis_forward': '-Y', 'fbx_axis_up': 'Z', 'fbx_global_scale': 1, 'unreal_convert_scene_unit': True, 'unreal_force_front_x_axis': True, 'unreal_mesh_import_uniform_scale': 1, 'unreal_animation_import_rotation_yaw_deg': -90, 'runtime_mesh_relative_yaw_deg': 0, 'unit_note': 'Mesh vertices, every shape target, rest bone coordinates and all bone location curves convert in memory for export; authoritative blend remains in metres.'}, 'unreal_morphs': {'target_count': 32, 'targets_with_deltas_per_lod': [32, 32, 32], 'source_key_count': 33, 'intentionally_nonempty_source_targets': 32, 'reserved_source_target': 'wrist_flex.R', 'reserved_source_target_imported': False, 'native_delta_evidence': 'docs/unreal_native_mesh_report.json', 'runtime_face_controls': 36, 'runtime_control_note': '32 morph controls plus independent left/right eye yaw and pitch.'}, 'unreal_imported_morph_target_count': 32, 'unreal_imported_bone_count': 64, 'unreal_imported_material_slots': 8})
    data['skinning']='Linear blend skinning in both Blender and Unreal; rigid cyber sleeve/forearm bones preserve mechanical joint volume.'
    ROOT.joinpath('docs/rig_contract.json').write_text(json.dumps(data,indent=2))
    sockets={'hand_left':'hand.L','hand_right':'hand.R','emitter_muzzle':'emitter_muzzle','blade_base':'blade_base','blade_tip':'blade_tip','power_cell':'cell','deployable_beacon':'beacon','fx_chest':'chest','fx_ground':'root'}
    data['sockets']=sockets
    ROOT.joinpath('docs/skeleton_and_sockets.json').write_text(json.dumps(data,indent=2))
    return data

class MeshBuilder:
    def __init__(self,detail):
        self.v=[];self.f=[];self.mi=[];self.weights=[];self.tags=[];self.uv=[];self.detail=detail
    def vert(self,p,w,tag='',uv=(0,0)):
        self.v.append(tuple(p));self.weights.append(w);self.tags.append(tag);self.uv.append(uv);return len(self.v)-1
    def face(self,ids,mat): self.f.append(ids);self.mi.append(mat)
    def loft(self,name,centers,radii,mat,weights,segments=16,caps=True,frame=None):
        seg=max(8,int(segments*self.detail));rows=[]
        for k,(c,r,w) in enumerate(zip(centers,radii,weights)):
            c=Vector(c)
            if frame: a,b=map(Vector,frame)
            else:
                direction=Vector(centers[min(k+1,len(centers)-1)])-Vector(centers[max(k-1,0)])
                direction.normalize();a=direction.cross(Vector((0,1,0))).normalized();b=direction.cross(a).normalized()
            row=[]
            for j in range(seg):
                th=2*math.pi*j/seg;p=c+a*math.cos(th)*r[0]+b*math.sin(th)*r[1]
                row.append(self.vert(p,w,name,(j/seg,k/max(1,len(centers)-1))))
            rows.append(row)
        for k in range(len(rows)-1):
            for j in range(seg):self.face((rows[k][j],rows[k][(j+1)%seg],rows[k+1][(j+1)%seg],rows[k+1][j]),mat)
        if caps:self.face(tuple(reversed(rows[0])),mat);self.face(tuple(rows[-1]),mat)
        return rows
    def ellipsoid(self,name,center,scale,mat,w,seg=24,rings=14):
        rr=max(5,int(rings*self.detail));ss=max(10,int(seg*self.detail));rows=[]
        for k in range(rr+1):
            th=math.pi*(.001+(k/rr)*.998);z=math.cos(th);r=math.sin(th)
            row=[]
            for j in range(ss):
                ph=2*math.pi*j/ss
                row.append(self.vert((center[0]+scale[0]*r*math.cos(ph),center[1]+scale[1]*r*math.sin(ph),center[2]+scale[2]*z),w,name,(j/ss,k/rr)))
            rows.append(row)
        for k in range(rr):
            for j in range(ss):self.face((rows[k][j],rows[k+1][j],rows[k+1][(j+1)%ss],rows[k][(j+1)%ss]),mat)
        self.face(tuple(rows[0]),mat);self.face(tuple(reversed(rows[-1])),mat)
    def box(self,name,center,scale,mat,w,bevel=.005):
        # An authored bevelled cube with explicit flat face normals after mesh split.
        bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=name
        o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        mod=o.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=max(1,round(3*self.detail))
        bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=mod.name)
        offset=len(self.v)
        for v in o.data.vertices:self.vert(o.matrix_world@v.co,w,name)
        for p in o.data.polygons:self.face(tuple(offset+i for i in p.vertices),mat)
        bpy.data.objects.remove(o,do_unlink=True)
    def tube(self,name,points,radius,mat,weights,segments=10):
        return self.loft(name,points,[(radius,radius)]*len(points),mat,weights,segments)
    def panel(self,name,outline,depth,mat,w):
        # Front vertices describe a tailored polygon. Positive Y is interior.
        n=len(outline);vs=list(outline)+[(x,y+depth,z) for x,y,z in outline]
        fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(o)
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        md=o.modifiers.new('Edge chamfer','BEVEL');md.width=.004;md.segments=2 if self.detail>.7 else 1;bpy.ops.object.modifier_apply(modifier=md.name)
        off=len(self.v)
        for v in o.data.vertices:self.vert(v.co,w,name)
        for p in o.data.polygons:self.face(tuple(off+i for i in p.vertices),mat)
        bpy.data.objects.remove(o,do_unlink=True)

def smoothstep(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)));return t*t*(3-2*t)
def gauss(x,s):return math.exp(-(x/s)**2)

def materials():
    colors=[(.47,.255,.175,1),(.018,.035,.055,1),(.40,.51,.55,1),(.045,.065,.08,1),(.01,.68,.67,1),(.014,.009,.017,1),(.82,.87,.85,1),(.35,.18,.045,1)]
    rough=[.5,.7,.3,.32,.27,.4,.15,.22];metal=[0,0,.4,.82,.5,0,0,.05]
    mats=[]
    texdir=ROOT/'source/textures';texdir.mkdir(parents=True,exist_ok=True)
    import numpy as np
    rng=np.random.default_rng(913)
    yy,xx=np.mgrid[0:512,0:512]
    for i,n in enumerate(MAT_NAMES):
        m=bpy.data.materials.get(n) or bpy.data.materials.new(n);m.use_nodes=True
        m.diffuse_color=colors[i];bs=m.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Roughness'].default_value=rough[i];bs.inputs['Metallic'].default_value=metal[i]
        if i==0:bs.inputs['Subsurface Weight'].default_value=.06
        if i==4:bs.inputs['Emission Color'].default_value=colors[i];bs.inputs['Emission Strength'].default_value=.35
        noise=rng.random((512,512))*.012-.006
        if i==1:noise+=((xx%6<2)^(yy%6<2))*.018
        if i in [2,3]:noise+=(np.sin(xx*.16)+np.cos(yy*.08))*.003
        pixels=np.empty((512,512,4),dtype=np.float32);pixels[:,:,:3]=np.clip(np.array(colors[i][:3])[None,None,:]+noise[:,:,None],0,1);pixels[:,:,3]=1
        image=bpy.data.images.new(n+'_BaseColor',512,512,alpha=True);image.pixels.foreach_set(pixels.ravel());image.filepath_raw=str(texdir/(n+'_BaseColor.png'));image.file_format='PNG';image.save();image.pack()
        node=m.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;node.label='Original editable color / micro-weave';m.node_tree.links.new(node.outputs['Color'],bs.inputs['Base Color'])
        # Tangent-space microdetail is physically subtle, and survives via supplied map.
        normal=np.ones((512,512,4),dtype=np.float32);normal[:,:,0:2]=.5
        if i==1:normal[:,:,0]=.5+.018*np.sin(xx*math.pi/3);normal[:,:,1]=.5+.018*np.sin(yy*math.pi/3)
        else:normal[:,:,0]=.5+noise*.1;normal[:,:,1]=.5-noise*.1
        im=bpy.data.images.new(n+'_Normal',512,512,alpha=True);im.colorspace_settings.name='Non-Color';im.pixels.foreach_set(normal.ravel());im.filepath_raw=str(texdir/(n+'_Normal.png'));im.file_format='PNG';im.save();im.pack()
        nt=m.node_tree.nodes.new('ShaderNodeTexImage');nt.image=im;nm=m.node_tree.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.35;m.node_tree.links.new(nt.outputs['Color'],nm.inputs['Color']);m.node_tree.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
        mats.append(m)
    return mats

def segment_weights(z,side=''):
    levels=[(.94,'pelvis'),(1.10,'spine_01'),(1.25,'spine_02'),(1.40,'chest'),(1.51,'neck'),(1.59,'head')]
    for i in range(len(levels)-1):
        z0,n0=levels[i];z1,n1=levels[i+1]
        if z0<=z<=z1:
            t=(z-z0)/(z1-z0);return {n0:1-t,n1:t}
    return {levels[0 if z<.94 else -1][1]:1}

def fit_power_cell_clearance(m):
    # Compact tapered cartridge end clears the organic wrist in every reload frame.
    # Preserve the socket end and luminous inset; all positions remain editable.
    ids=[i for i,t in enumerate(m.tags) if t.startswith('power_cell')]
    cell=skeleton_spec()['cell'];head=Vector(cell['head']);axis=(Vector(cell['tail'])-head).normalized()
    maximum=max((Vector(m.v[i])-head).dot(axis) for i in ids)
    start=.012;end=.0215
    for i in ids:
        p=Vector(m.v[i]);y=(p-head).dot(axis)
        if y>start:p+=axis*((start+(y-start)*(end-start)/(maximum-start))-y)
        m.v[i]=tuple(p)

def build_body(m):
    # Tailored torso: denser horizontal rings at pelvis, waist and shoulder bend.
    profile=[(.87,.085,.061),(.90,.13,.080),(.935,.169,.092),(.965,.175,.092),(.99,.164,.086),(1.025,.146,.081),(1.07,.125,.073),(1.115,.115,.067),(1.16,.118,.073),(1.20,.127,.084),(1.25,.144,.089),(1.30,.155,.086),(1.34,.165,.081),(1.38,.173,.071),(1.42,.165,.065),(1.455,.139,.058),(1.48,.091,.046),(1.493,.061,.041)]
    m.loft('suit_torso',[(0,0,z) for z,x,y in profile],[(x,y) for z,x,y in profile],1,[segment_weights(z) for z,x,y in profile],32,frame=((1,0,0),(0,1,0)))
    # Bare neck remains visibly organic.
    m.loft('neck',[(0,0,1.47),(0,0,1.49),(0,.003,1.535),(0,.006,1.58),(0,.008,1.604)],[(.052,.039),(.047,.035),(.037,.033),(.034,.029),(.032,.027)],0,[{'chest':.7,'neck':.3},{'neck':1},{'neck':1},{'neck':.5,'head':.5},{'head':1}],24,frame=((1,0,0),(0,1,0)))
    sk=skeleton_spec()
    for side,s in [('L',1),('R',-1)]:
        # Continuous leg through hip, knee and ankle, deliberate knee compression rings.
        zs=[.955,.925,.88,.81,.71,.61,.555,.53,.505,.475,.42,.32,.23,.15,.105]
        rx=[.087,.09,.086,.082,.073,.06,.054,.054,.052,.053,.057,.054,.042,.035,.034]
        ry=[.078,.081,.084,.08,.07,.057,.05,.046,.045,.052,.057,.048,.04,.033,.033]
        centers=[];weights=[]
        for z in zs:
            x=s*(.09+(.955-z)*.02);y=-.012*gauss(z-.52,.15)
            centers.append((x,y,z));t=smoothstep(.47,.59,z)
            w={'thigh.'+side:t,'shin.'+side:1-t}
            if z>.87:w={'pelvis':smoothstep(.87,.99,z)*.38,'thigh.'+side:1-smoothstep(.87,.99,z)*.38}
            weights.append(w)
        m.loft('suit_leg.'+side,centers,list(zip(rx,ry)),1,weights,24,frame=((1,0,0),(0,1,0)))
        # Shoe profile: rounded toe, sole rests exactly on ground.
        ys=[.055,.045,.015,-.05,-.125,-.19,-.245,-.258]
        m.loft('boot.'+side,[(s*.105,y,.064 if y<-.03 else .079) for y in ys],[(.036,.06),(.044,.073),(.048,.079),(.055,.064),(.057,.054),(.053,.049),(.040,.038),(.025,.023)],3,[{'foot.'+side:1} if y>-.13 else {'foot.'+side:.35,'toe.'+side:.65} for y in ys],20,frame=((1,0,0),(0,0,1)))
        # Authored side stripe, kneecap and shin shell leave bending knee visible.
        m.ellipsoid('knee_guard.'+side,(s*.104,-.059,.53),(.049,.023,.051),2,{'shin.'+side:.65,'thigh.'+side:.35},20,10)
        m.ellipsoid('shin_plate.'+side,(s*.106,-.049,.339),(.038,.019,.126),2,{'shin.'+side:1},20,12)
        m.box('shin_accent.'+side,(s*.107,-.068,.353),(.012,.006,.106),4,{'shin.'+side:1},.003)
        m.ellipsoid('thigh_panel.'+side,(s*.139,-.042,.79),(.058,.033,.105),2,{'thigh.'+side:1},18,12)
        # Sleeve to just above elbow, followed by skin on L, machine on R.
        shoulder=Vector(sk['upper_arm.'+side]['head']);elbow=Vector(sk['forearm.'+side]['head']);wrist=Vector(sk['hand.'+side]['head'])
        pts=[];rads=[];ws=[]
        for t,r in [(0,.067),(.12,.075),(.26,.069),(.5,.058),(.75,.051),(.91,.045),(1,.043)]:
            pts.append(tuple(shoulder.lerp(elbow,t)));rads.append((r,r*.86));ws.append({'upper_arm.'+side:1} if t<.75 or side=='R' else {'upper_arm.'+side:1-(t-.75)*2,'forearm.'+side:(t-.75)*2})
        m.loft('sleeve.'+side,pts,rads,1,ws,24)
        pts=[];rads=[];ws=[]
        for t,r in [(0,.042),(.09,.043),(.2,.046),(.4,.047),(.63,.040),(.82,.033),(.94,.029),(1,.028)]:
            pts.append(tuple(elbow.lerp(wrist,t)));rads.append((r,r*.86))
            if side=='R':ws.append({'forearm.R':1})
            elif t>=.82:
                # The palm's first ring shares the wrist position and 70% hand
                # weighting. Match that endpoint and blend through the distal
                # forearm so extreme hand rotations cannot open a wrist seam.
                hand_weight=.70*smoothstep(.75,1,t)
                ws.append({'forearm.'+side:1-hand_weight,'hand.'+side:hand_weight})
            else:ws.append({'upper_arm.'+side:max(0,.4-t*3),'forearm.'+side:1-max(0,.4-t*3)})
        m.loft(('organic_forearm.' if side=='L' else 'cyber_armature.')+side,pts,rads,0 if side=='L' else 3,ws,24)
        # Open pauldron cuffs let the flexible sleeve pass through cleanly.
        armor_shift=(elbow-shoulder).normalized()*.055
        m.loft('shoulder_shell.'+side,[tuple(shoulder.lerp(elbow,t)+armor_shift) for t in [-.10,0,.22,.31]],[(.086,.080),(.085,.079),(.081,.077),(.077,.072)],2,[{'upper_arm.'+side:1}]*4,12,caps=False)
        m.ellipsoid('shoulder_inlay.'+side,Vector((s*.221,-.073,1.458))+armor_shift,(.023,.006,.009),4,{'upper_arm.'+side:1},20,8)
        hand0=Vector(sk['hand.'+side]['head']);hand1=Vector(sk['hand.'+side]['tail'])
        handpts=[hand0,hand0.lerp(hand1,.25),hand0.lerp(hand1,.7),hand1]
        m.loft('palm.'+side,[tuple(x) for x in handpts],[(.027,.025),(.030,.032),(.025,.043),(.018,.04)],0 if side=='L' else 3,[{'forearm.'+side:.3,'hand.'+side:.7},{'hand.'+side:1},{'hand.'+side:1},{'hand.'+side:1}],20)
        for finger in ['thumb','index','middle','ring','pinky']:
            pts=[];rr=[];ww=[]
            for j in range(1,4):
                bn=f'{finger}.{j:02d}.{side}';h=Vector(sk[bn]['head']);t=Vector(sk[bn]['tail']);rad=(.011 if finger=='thumb' else .0095)*[1,.83,.65][j-1]
                if j==1:pts.append(tuple(h));rr.append((rad,rad*.87));ww.append({'hand.'+side:.24,bn:.76})
                pts.append(tuple(h.lerp(t,.38)));rr.append((rad,rad*.87));ww.append({bn:1})
                pts.append(tuple(t));rr.append((rad*.86,rad*.76));ww.append({bn:1} if j==3 else {bn:.5,f'{finger}.{j+1:02d}.{side}':.5})
            pts.append(tuple(t+(t-h).normalized()*.003));rr.append((.002,.002));ww.append({bn:1})
            m.loft('finger_'+finger+'.'+side,pts,rr,0 if side=='L' else 3,ww,12)
        # Elbow tubing and plated cybernetic forearm express the asymmetry.
        if side=='R':
            m.loft('forearm_shell', [tuple(elbow.lerp(wrist,t)+Vector((0,-.015,0))) for t in [.18,.24,.68,.83]],[(.045,.036),(.047,.039),(.037,.033),(.029,.027)],2,[{'forearm.R':1}]*4,12)
            for t in [.25,.42,.59]:
                c=elbow.lerp(wrist,t)+Vector((0,-.05,0));m.box('emitter_vent',c,(.035,.009,.012),3,{'forearm.R':1},.002)
            m.ellipsoid('emitter_core',(-.514,-.071,1.107),(.019,.012,.024),4,{'forearm.R':1},20,12)
            # Bevelled cell fits the visible forearm socket; its own bone drives removal.
            m.box('power_cell',(-.438,-.066,1.207),(.028,.035,.060),3,{'cell':1},.006)
            m.box('power_cell_window',(-.438,-.085,1.207),(.015,.004,.039),4,{'cell':1},.002)
            fit_power_cell_clearance(m)
    # Small chest armor panels, central readable team stripe and graphic glyph.
    for s in [-1,1]:
        m.panel('chest_plate',[(s*.022,-.092,1.405),(s*.080,-.092,1.439),(s*.151,-.065,1.412),(s*.149,-.073,1.355),(s*.095,-.100,1.308),(s*.026,-.106,1.340)],.017,2,{'chest':1})
        m.panel('chest_recess',[(s*.041,-.111,1.364),(s*.079,-.113,1.381),(s*.116,-.097,1.370),(s*.081,-.117,1.345)],.005,3,{'chest':1})
    m.box('sternum_stripe',(0,-.096,1.363),(.014,.012,.091),4,{'chest':1},.004)
    for x in [-.04,0,.04]:m.box('belt_segment',(x,-.083,1.016),(.033,.023,.027),3,{'pelvis':1},.004)
    m.box('belt_buckle',(0,-.1,1.016),(.025,.006,.017),4,{'pelvis':1},.002)
    # Blade is a closed original double-edged wedge with light spine.
    base=Vector((-.449,.051,1.185));tip=Vector((-.635,.051,.966));wide=Vector((.02,0,-.016))
    ids=[m.vert(base+wide,{'blade_base':1},'blade'),m.vert(base-wide,{'blade_base':1},'blade'),m.vert(base+Vector((0,-.01,0)),{'blade_base':1},'blade'),m.vert(base+Vector((0,.01,0)),{'blade_base':1},'blade'),m.vert(tip,{'blade_tip':1},'blade')]
    for face in [(0,2,4),(2,1,4),(1,3,4),(3,0,4),(0,3,1,2)]:m.face(tuple(ids[j] for j in face),2)
    m.tube('blade_luminous_spine',[base+Vector((0,-.011,0)),tip],.0028,4,[{'blade_base':1},{'blade_tip':1}],8)
    # Belt beacon and controllable soft cable.
    m.box('beacon_body',(.16,.005,1.026),(.067,.04,.073),3,{'beacon':1},.012)
    m.ellipsoid('beacon_lens',(.16,-.02,1.034),(.02,.008,.02),4,{'beacon':1},16,10)
    pts=[(.09,.077,1.14),(.143,.086,1.08),(.174,.085,1.017),(.177,.075,.955),(.155,.075,.91)]
    m.tube('secondary_cable',pts,.006,4,[{'cable.01':1},{'cable.01':1},{'cable.01':.5,'cable.02':.5},{'cable.02':1},{'cable.02':1}],10)

HEAD_PROFILE=[(1.576,.004,-.015,.018),(1.59,.035,-.05,.032),(1.605,.047,-.060,.043),(1.623,.060,-.068,.054),(1.650,.070,-.070,.070),(1.68,.075,-.065,.079),(1.70,.074,-.064,.080),(1.725,.071,-.064,.076),(1.75,.062,-.055,.068),(1.78,.045,-.035,.045),(1.796,.016,-.007,.023),(1.8,.002,.010,.014)]
def head_profile(z):
    for a,b in zip(HEAD_PROFILE,HEAD_PROFILE[1:]):
        if a[0]<=z<=b[0]:
            t=(z-a[0])/(b[0]-a[0]);return tuple(a[i]*(1-t)+b[i]*t for i in [1,2,3])
    return HEAD_PROFILE[0 if z<1.576 else -1][1:]
def face_surface(x,z):
    # Shared surface evaluation keeps orbital and lip patches on the skull.
    width,front,back=head_profile(z);arc=math.sqrt(max(0,1-(x/max(width,.001))**2))
    y=.008+(front-.008)*arc
    y-=.007*gauss(z-1.665,.022)*gauss(abs(x)-.04,.023)*arc
    y+=.006*gauss(z-1.693,.014)*gauss(abs(x)-.031,.020)*arc
    y-=.012*gauss(z-1.675,.032)*gauss(x,.010)*arc
    y-=.027*gauss(z-1.652,.011)*gauss(x,.015)*arc
    y-=.009*gauss(z-1.624,.016)*gauss(x,.032)*arc
    return y

def build_head(m):
    # Skull horizontal quad loops, with openings behind independent lid and lip loops.
    seg=max(40,int(88*m.detail));nz=max(26,int(64*m.detail));rows=[]
    for k in range(nz+1):
        v=k/nz;z=1.576+.224*v
        wid,front,back=head_profile(z)
        row=[]
        for j in range(seg):
            a=2*math.pi*j/seg;x=wid*math.sin(a)
            y=(back-.008)*math.cos(a)+.008
            if math.cos(a)<0:
                y=face_surface(x,z)
            row.append(m.vert((x,y,z),{'head':1},'face',(j/seg,v)))
        rows.append(row)
    holes={'L':[],'R':[],'mouth':[]}
    for k in range(nz):
        for j in range(seg):
            ids=(rows[k][j],rows[k][(j+1)%seg],rows[k+1][(j+1)%seg],rows[k+1][j]);p=sum((Vector(m.v[i]) for i in ids),Vector())/4
            hole=None
            for side,s in [('L',1),('R',-1)]:
                if ((p.x-s*.031)/.029)**2+((p.z-1.693)/.019)**2<1 and p.y<-.028:hole=side
            if (p.x/.034)**2+((p.z-1.623)/.011)**2<1 and p.y<-.04:hole='mouth'
            if hole:holes[hole].append(ids)
            else:m.face(ids,0)
    m.face(tuple(reversed(rows[0])),0);m.face(tuple(rows[-1]),0)
    def boundary(polys,center):
        edges={}
        for ids in polys:
            for i,a in enumerate(ids):
                b=ids[(i+1)%len(ids)];e=tuple(sorted((a,b)));edges[e]=edges.get(e,0)+1
        ids=set(v for e,c in edges.items() if c==1 for v in e)
        return sorted(ids,key=lambda i:math.atan2((m.v[i][2]-center[1]),(m.v[i][0]-center[0])))
    # Eye globes, irises and dark pupils are nested authored ellipsoids.
    for side,s in [('L',1),('R',-1)]:
        center=(s*.031,-.052,1.693)
        m.ellipsoid('eyeball.'+side,center,(.018,.018,.017),6,{'eye.'+side:1},32,20)
        m.ellipsoid('iris.'+side,(s*.031,-.0701,1.693),(.0071,.0012,.0071),7,{'eye.'+side:1},28,14)
        m.ellipsoid('pupil.'+side,(s*.031,-.0712,1.693),(.0030,.0005,.0038),5,{'eye.'+side:1},20,12)
        # Concentric eyelid annuli: boundary follows eye curvature exactly.
        outer=boundary(holes[side],(s*.031,1.693));nr=6 if m.detail>.7 else 4;ss=len(outer);rr=[]
        for k in range(nr):
            t=k/(nr-1);row=[]
            for j,oi in enumerate(outer):
                if k==nr-1:row.append(oi);continue
                op=Vector(m.v[oi]);a=math.atan2((op.z-1.693)/.019,(op.x-s*.031)/.029)
                dx=math.cos(a)*.0175*(1-t)+(op.x-s*.031)*t;dz=math.sin(a)*.0064*(1-t)+(op.z-1.693)*t
                z=1.693+dz+dx*s*.065;x=s*.031+dx
                depth=-.052-math.sqrt(max(.000003,.018**2-dx*dx-(dz*1.06)**2))
                y=min(depth-.0022,face_surface(x,z))-.0005*math.sin(t*math.pi)
                row.append(m.vert((x,y,z),{'head':1},'lid.'+side+':'+str(t),(j/ss,t)))
            rr.append(row)
        for k in range(nr-1):
            for j in range(ss):m.face((rr[k][j],rr[k][(j+1)%ss],rr[k+1][(j+1)%ss],rr[k+1][j]),0)
        # Sculpted brow ridge and hair eyebrow, intentionally asymmetric notch.
        pts=[]
        for j in range(8):
            x=s*(.011+j*.006);z=1.713+.004*math.sin(j/7*math.pi)-j*.0003
            pts.append((x,face_surface(x,z)-.003,z))
        m.loft('brow.'+side,pts,[(.0022,.0032)]*8,5,[{'head':1}]*8,8)
        # Ears, helix rim and inset inner ear.
        m.ellipsoid('ear.'+side,(s*.072,.003,1.673),(.014,.016,.030),0,{'head':1},20,14)
        m.ellipsoid('ear_inner.'+side,(s*.081,-.005,1.674),(.005,.010,.019),0,{'head':1},16,10)
        m.box('ear_commlink.'+side,(s*.08,.009,1.656),(.009,.018,.024),3,{'head':1},.004)
    # Closed lip silhouette with concentric lip/skin rings and a deep closed oral cavity.
    outer=boundary(holes['mouth'],(0,1.623));nr=6;ss=len(outer);rr=[]
    for k in range(nr):
        t=k/(nr-1);row=[]
        for j,oi in enumerate(outer):
            if k==nr-1:row.append(oi);continue
            op=Vector(m.v[oi]);a=math.atan2((op.z-1.623)/.011,op.x/.034)
            x=math.cos(a)*.027*(1-t)+op.x*t
            z=(1.623+math.sin(a)*.00015)*(1-t)+op.z*t
            if math.sin(a)>0:z-=.0007*gauss(x,.007)*math.sin(t*math.pi)
            y=face_surface(x,z)-.004*math.sin(t*math.pi)-.001*(1-t)
            row.append(m.vert((x,y,z),{'head':1},'lip',(j/ss,t)))
        rr.append(row)
    for k in range(nr-1):
        for j in range(ss):m.face((rr[k][j],rr[k][(j+1)%ss],rr[k+1][(j+1)%ss],rr[k+1][j]),0)
    # Relax the stitched boundary bands while preserving aperture rings. This
    # removes pole shading on the rectilinear skull grid without detached patches.
    feature=set(v for polys in holes.values() for poly in polys for v in poly)
    adj={}
    for f in m.f:
        for j,a in enumerate(f):
            b=f[(j+1)%len(f)];adj.setdefault(a,set()).add(b);adj.setdefault(b,set()).add(a)
    for _ in range(2):feature.update(n for i in list(feature) for n in adj.get(i,[]) if m.tags[n]=='face')
    feature.update(i for i,tg in enumerate(m.tags) if (tg.startswith('lid.') and not tg.endswith(':0.0')) or (tg=='lip' and m.uv[i][1]>.05))
    for _ in range(6):
        new={}
        for i in feature:
            ns=adj.get(i,[])
            if ns:
                p=Vector(m.v[i]);avg=sum((Vector(m.v[n]) for n in ns),Vector())/len(ns)
                new[i]=tuple(p.lerp(avg,.30))
        for i,p in new.items():m.v[i]=p
    m.ellipsoid('oral_cavity',(0,-.021,1.618),(.029,.037,.027),5,{'jaw':.5,'head':.5},28,18)
    # Small discrete teeth are a genuine inside-mouth mesh, upper and lower arcs.
    for lower in [False,True]:
        for i in range(8):
            x=(i-3.5)*.0057;y=-.061+.008*(abs(x)/.022)**2
            m.box('teeth_lower' if lower else 'teeth_upper',(x,y,1.614 if lower else 1.625),(.0053,.005,.008),6,{'jaw':1} if lower else {'head':1},.0013)
    m.ellipsoid('tongue',(0,-.044,1.610),(.018,.018,.0045),0,{'tongue':1},22,10)
    # Cropped swept hair cap leaves face and brows exposed.
    ss=max(30,int(64*m.detail));nn=max(12,int(26*m.detail));rows=[]
    for k in range(nn+1):
        t=k/nn;row=[]
        for j in range(ss):
            a=j/ss*2*math.pi
            low=1.693 if math.cos(a)>.1 else 1.741+.008*math.sin(a)
            z=low+(1.800-low)*t;wid,front,back=head_profile(z)
            ridge=.0012*math.sin(a*16+t*3)**2
            x=(wid+.002+ridge)*math.sin(a);y=.008+((back-.008+.002+ridge) if math.cos(a)>=0 else (.008-front+.002+ridge))*math.cos(a)
            row.append(m.vert((x,y,z),{'head':1},'hair',(j/ss,t)))
        rows.append(row)
    for k in range(nn):
        for j in range(ss):m.face((rows[k][j],rows[k][(j+1)%ss],rows[k+1][(j+1)%ss],rows[k+1][j]),5)
    m.face(tuple(rows[-1]),5)

def add_shape_keys(obj,tags):
    obj.shape_key_add(name='Basis');verts=obj.data.vertices
    def delta(n,p,tag):
        x,y,z=p;d=Vector((0,0,0));face=tag in ['face','lip','oral_cavity','teeth_lower','tongue'] or tag.startswith(('lid.','brow.','eyeball.','iris.','pupil.'))
        if not face:return d
        frontal=y<-.02
        if n.startswith(('blink.','squint.')):
            side=n.split('.')[-1];s=1 if side=='L' else -1
            if tag.startswith('lid.'+side):
                a=(x-s*.031)/.033;fall=max(0,1-a*a);center=1.693+(x-s*.031)*s*.065
                amount=(1 if n.startswith('blink') else .45)*(1-float(tag.split(':')[-1]))
                d.z=(center-z)*amount
                nz=z+d.z;target_y=-.052-math.sqrt(max(.000003,.018**2-(x-s*.031)**2-((nz-1.693)*1.06)**2))-.004
                d.y=(min(y,target_y)-y)*(1 if n.startswith('blink') else .5)
            if tag in ['eyeball.'+side,'iris.'+side,'pupil.'+side]:
                # Protected recession prevents globe/iris intersections during
                # both full closure and partial squint after linear export.
                d.y=.010 if n.startswith('blink') else .004
        if n.startswith(('brow_up.','brow_down.','cheek.','smile.','frown.')) and frontal:
            side=n.split('.')[-1];s=1 if side=='L' else -1
            lateral=gauss(x-s*.03,.026)
            if n.startswith('brow') and tag!='lip':d.z=(.011 if n.startswith('brow_up') else -.007)*lateral*gauss(z-1.717,.021)
            if n.startswith('cheek'):d.z=.006*lateral*gauss(z-1.666,.022);d.y=-.003*lateral*gauss(z-1.666,.022)
            if n.startswith(('smile','frown')):
                strength=gauss(x-s*.025,.014)*gauss(z-1.623,.020)
                d.z=(.010 if n.startswith('smile') else -.008)*strength;d.x=s*.004*strength
        if n in ['jaw_open','viseme_AA','viseme_OH','viseme_OO','viseme_EE','viseme_L','viseme_TH']:
            amount={'jaw_open':1,'viseme_AA':.85,'viseme_OH':.7,'viseme_OO':.38,'viseme_EE':.3,'viseme_L':.45,'viseme_TH':.35}[n]
            lower=(1-smoothstep(1.613,1.629,z))*gauss(x,.065) if frontal else 0
            if tag=='lip':lower=(1 if z<1.623 else 0)*math.sqrt(max(0,1-(x/.029)**2))
            if tag in ['teeth_lower','tongue']:lower=1
            d.z-=.027*lower*amount;d.y+=.006*lower*amount
        if n in ['mouth_wide','viseme_EE'] and frontal:
            st=gauss(z-1.624,.018)*gauss(x,.04);d.x+=x*.30*st
        if n in ['pucker','funnel','viseme_OH','viseme_OO'] and frontal:
            st=gauss(z-1.623,.017)*gauss(x,.04);power={'pucker':1,'funnel':.65,'viseme_OH':.5,'viseme_OO':1}[n]
            d.x-=x*.36*st*power;d.y-=.010*st*power
            if n=='funnel':d.z+=(z-1.623)*.25*st
        if n in ['lip_close','viseme_MBP'] and tag=='lip':
            st=gauss(z-1.623,.007);d.z+=(1.623-z)*st*.9
        if n=='viseme_FV' and tag=='lip' and z<1.623:d.z+=.008*gauss(x,.03);d.y+=.004
        if n in ['viseme_L','viseme_TH'] and tag=='tongue':d.z+=.012;d.y-=.008 if n=='viseme_TH' else .003
        return d
    for name in FACE_KEYS:
        key=obj.shape_key_add(name=name,from_mix=False);key.value=0.0
        for i,v in enumerate(verts):key.data[i].co=v.co+delta(name,v.co,tags[i])
        key.slider_min=0;key.slider_max=1
    # Full shoulder/hip/wrist correctives use weighted affected rings, never armouring over failure.
    for side,s in [('L',1),('R',-1)]:
        for i,v in enumerate(verts):
            p=v.co;tag=tags[i]
            if tag=='sleeve.'+side:
                a=gauss(p.x-s*.25,.07)*gauss(p.z-1.43,.08)
                obj.data.shape_keys.key_blocks['shoulder_raise.'+side].data[i].co+=Vector((s*.009*a,0,.012*a))
            if tag=='suit_leg.'+side:
                a=gauss(p.z-.90,.09);obj.data.shape_keys.key_blocks['hip_flex.'+side].data[i].co+=Vector((s*.006*a,.007*a,0))
            if tag=='organic_forearm.'+side:
                a=gauss(p.x-s*.52,.028);obj.data.shape_keys.key_blocks['wrist_flex.'+side].data[i].co+=Vector((0,-.004*a,0))

def make_mesh(detail,name,mats,rig):
    m=MeshBuilder(detail);build_body(m);build_head(m)
    used=sorted(set(i for f in m.f for i in f));remap={old:new for new,old in enumerate(used)}
    m.v=[m.v[i] for i in used];m.weights=[m.weights[i] for i in used];m.tags=[m.tags[i] for i in used];m.uv=[m.uv[i] for i in used];m.f=[tuple(remap[i] for i in f) for f in m.f]
    mesh=bpy.data.meshes.new(name+'_EditableMesh');mesh.from_pydata(m.v,[],m.f);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o)
    for mat in mats:mesh.materials.append(mat)
    for p,mi in zip(mesh.polygons,m.mi):
        p.material_index=mi;p.use_smooth=not any(t in m.tags[p.vertices[0]] for t in ['chest_plate','chest_recess','blade','segment','buckle','stripe','window','body','vent','cell','commlink'])
    for name_b in skeleton_spec():o.vertex_groups.new(name=name_b)
    for idx,w in enumerate(m.weights):
        total=sum(w.values())
        for bn,weight in w.items():
            if weight>0:o.vertex_groups[bn].add([idx],weight/total,'REPLACE')
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.uv.smart_project(angle_limit=1.15,island_margin=.007,area_weight=.1,correct_aspect=True,scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    add_shape_keys(o,m.tags)
    mod=o.modifiers.new('Native-compatible linear skin','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=False;o.parent=rig
    o['authoring']='Original quad lofts / explicit facial loops; source/generators/character.py';o['lod_detail']=detail
    return o

def create_rig():
    spec=skeleton_spec();arm=bpy.data.armatures.new('Operative_Deformation');rig=bpy.data.objects.new('Operative_Rig',arm);bpy.context.collection.objects.link(rig);bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for n,d in spec.items():
        b=arm.edit_bones.new(n);b.head=d['head'];b.tail=d['tail'];b.align_roll(Vector((0,1,0)));b.use_deform=True
        if d['parent']:b.parent=arm.edit_bones[d['parent']]
    bpy.ops.object.mode_set(mode='OBJECT');rig.show_in_front=True;rig.data.display_type='OCTAHEDRAL'
    for p in rig.pose.bones:p.rotation_mode='XYZ'
    # Controls form a separate nondeforming branch under stable root.
    bpy.ops.object.mode_set(mode='EDIT')
    for side,s in [('L',1),('R',-1)]:
        for typ,pos in [('hand_ik',spec['hand.'+side]['head']),('foot_ik',spec['foot.'+side]['head']),('elbow_pole',(s*.36,.35,1.22)),('knee_pole',(s*.10,-.5,.55)),('heel',(s*.105,.055,.035)),('toe_pivot',(s*.105,-.23,.035))]:
            b=arm.edit_bones.new('CTRL_'+typ+'.'+side);b.head=pos;b.tail=Vector(pos)+Vector((0,0,.07));b.use_deform=False;b.parent=arm.edit_bones['root']
    for side in ['L','R']:
        arm.edit_bones['CTRL_toe_pivot.'+side].parent=arm.edit_bones['CTRL_heel.'+side]
        arm.edit_bones['CTRL_foot_ik.'+side].parent=arm.edit_bones['CTRL_toe_pivot.'+side]
        for typ,source in [('foot_ik','foot'),('hand_ik','hand')]:
            cb=arm.edit_bones['CTRL_'+typ+'.'+side];cb.head=spec[source+'.'+side]['head'];cb.tail=spec[source+'.'+side]['tail'];cb.align_roll(Vector((0,1,0)))
        for finger in ['thumb','index','middle','ring','pinky']:
            for j in [1,2,3]:
                n=f'{finger}.{j:02d}.{side}';b=arm.edit_bones.new('CTRL_'+n);b.head=spec[n]['head'];b.tail=spec[n]['tail'];b.align_roll(Vector((0,1,0)));b.use_deform=False;b.parent=arm.edit_bones['root']
    for n,pos in [('look',(0,-.7,1.69))]:
        b=arm.edit_bones.new('CTRL_'+n);b.head=pos;b.tail=Vector(pos)+Vector((0,0,.1));b.use_deform=False
        b.parent=arm.edit_bones['root']
    bpy.ops.object.mode_set(mode='POSE')
    for side in ['L','R']:
        for limb,chain,target,pole in [('arm','forearm','hand_ik','elbow_pole'),('leg','shin','foot_ik','knee_pole')]:
            prop=limb+'_ik.'+side;rig[prop]=0.0;rig.id_properties_ui(prop).update(min=0,max=1,description='0 FK / 1 IK; use rig_tools.match_switch before changing')
            con=rig.pose.bones[chain+'.'+side].constraints.new('IK');con.name='Animator '+limb+' IK';con.target=rig;con.subtarget='CTRL_'+target+'.'+side;con.pole_target=rig;con.pole_subtarget='CTRL_'+pole+'.'+side;con.chain_count=2;con.use_stretch=False;con.pole_angle=math.pi/2 if side=='L' else -math.pi/2
            drv=con.driver_add('influence').driver;v=drv.variables.new();v.name='blend';v.targets[0].id=rig;v.targets[0].data_path='["'+prop+'"]';drv.expression='blend'
        for prop in ['foot_roll','heel_pivot','toe_pivot','finger_curl','finger_spread']:
            rig[prop+'.'+side]=0.0;rig.id_properties_ui(prop+'.'+side).update(min=-1,max=1)
        # Physical hierarchy pivots the ankle target around heel / ball positions.
        for ctrlname,extra,expression in [('heel','heel_pivot','min(0,roll)*0.65+extra*0.4'),('toe_pivot','toe_pivot','max(0,roll)*0.65+extra*0.5')]:
            ctrl=rig.pose.bones['CTRL_'+ctrlname+'.'+side];ctrl.rotation_mode='XYZ';drv=ctrl.driver_add('rotation_euler',0).driver
            for vn,prop in [('roll','foot_roll'),('extra',extra)]:
                v=drv.variables.new();v.name=vn;v.targets[0].id=rig;v.targets[0].data_path='["'+prop+'.'+side+'"]'
            drv.expression=expression
        for limb,end,target in [('arm','hand','hand_ik'),('leg','foot','foot_ik')]:
            c=rig.pose.bones[end+'.'+side].constraints.new('COPY_ROTATION');c.name='IK orientation';c.target=rig;c.subtarget='CTRL_'+target+'.'+side;c.target_space='WORLD';c.owner_space='WORLD'
            drv=c.driver_add('influence').driver;v=drv.variables.new();v.name='ik';v.targets[0].id=rig;v.targets[0].data_path='["'+limb+'_ik.'+side+'"]';drv.expression='ik'
        for fi,finger in enumerate(['thumb','index','middle','ring','pinky']):
            for j in [1,2,3]:
                n=f'{finger}.{j:02d}.{side}';ctrl=rig.pose.bones['CTRL_'+n];ctrl.rotation_mode='XYZ'
                c=rig.pose.bones[n].constraints.new('COPY_ROTATION');c.name='Additive hand controls';c.target=rig;c.subtarget=ctrl.name;c.owner_space='LOCAL';c.target_space='LOCAL';c.mix_mode='ADD'
                for axis,prop,factor in [(2,'finger_curl',(-1 if side=='L' else 1)*[.9,1.2,.9][j-1]),(0,'finger_spread',(fi-2)*.14 if j==1 else 0)]:
                    drv=ctrl.driver_add('rotation_euler',axis).driver;v=drv.variables.new();v.name='amount';v.targets[0].id=rig;v.targets[0].data_path='["'+prop+'.'+side+'"]';drv.expression=f'amount*{factor}'
    rig['global_scale']=1.0;rig.id_properties_ui('global_scale').update(min=.01,max=10,description='Uniform scale of complete character including IK targets')
    for axis in range(3):
        drv=rig.driver_add('scale',axis).driver;v=drv.variables.new();v.name='size';v.targets[0].id=rig;v.targets[0].data_path='["global_scale"]';drv.expression='size'
    rig['look_at']=0.0
    for side in ['L','R']:
        c=rig.pose.bones['eye.'+side].constraints.new('DAMPED_TRACK');c.target=rig;c.subtarget='CTRL_look';c.track_axis='TRACK_Y';drv=c.driver_add('influence').driver;v=drv.variables.new();v.name='look';v.targets[0].id=rig;v.targets[0].data_path='["look_at"]';drv.expression='look'
    bpy.ops.object.mode_set(mode='OBJECT')
    # Separate control/deform collections, visible animator convention.
    dc=arm.collections.new('Deformation / FK');cc=arm.collections.new('Animator IK and poles')
    for b in arm.bones:
        (cc if b.name.startswith('CTRL_') else dc).assign(b)
        if b.name.startswith('CTRL_'):b.color.palette='THEME04'
        else:b.color.palette='THEME03' if b.name.endswith('.L') else 'THEME01' if b.name.endswith('.R') else 'THEME09'
    return rig

def setup_scene(rig):
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.;scene.render.fps=30
    scene.world.color=(.06,.06,.06);scene.render.engine='CYCLES';scene.cycles.samples=48
    scene.view_settings.view_transform='AgX';scene.render.resolution_x=1100;scene.render.resolution_y=1400;scene.render.resolution_percentage=100
    # Neutral studio for author inspection; hidden from export selection.
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.004));floor=bpy.context.object;floor.name='Studio_Floor'
    mat=bpy.data.materials.new('Studio_Slate');mat.diffuse_color=(.035,.045,.055,1);floor.data.materials.append(mat)
    for name,loc,power,size,col in [('Key',(2,-3,4),400,3,(.76,.87,1)),('Fill',(-2,-1.5,2),240,2,(1,.69,.48)),('Rim',(1,2,3),600,2,(.2,.7,1))]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size;data.color=col;o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('Inspection');cam=bpy.data.objects.new('Inspection',data);scene.collection.objects.link(cam);cam.location=(2.7,-4.3,2.25);cam.rotation_euler=(Vector((0,0,.94))-cam.location).to_track_quat('-Z','Y').to_euler();data.type='ORTHO';data.ortho_scale=2.23;scene.camera=cam
    rig.select_set(True);bpy.context.view_layer.objects.active=rig

def build(output_dir=None):
    if output_dir:
        global ROOT
        ROOT=Path(output_dir)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    write_contract();mats=materials();rig=create_rig();meshes=[]
    for detail,n in [(1.,0),(.62,1),(.38,2)]:
        obj=make_mesh(detail,'Operative_LOD'+str(n),mats,rig);meshes.append(obj)
        if n:obj.hide_render=True;obj.hide_set(True)
    setup_scene(rig)
    report={'lods':[],'material_slots':len(mats),'deformation_bones':sum(b.use_deform for b in rig.data.bones),'max_influences':0,'textures':{'count':16,'resolution':[512,512],'format':'RGBA8 PNG','uncompressed_mipmapped_bytes':16*512*512*4*4//3},'height_m':1.80,'units':'metres; identity mesh/armature transforms','team_variants':{'A':{'accent':[.01,.68,.67],'icon':'square (runtime cube silhouette)'},'B':{'accent':[1,.20,.035],'icon':'circle (runtime sphere silhouette)'}}}
    for o in meshes:
        tris=sum(len(p.vertices)-2 for p in o.data.polygons);report['lods'].append({'name':o.name,'triangles':tris,'vertices':len(o.data.vertices),'materials':len(o.data.materials),'shape_keys':len(o.data.shape_keys.key_blocks)-1})
        report['max_influences']=max(report['max_influences'],max(len(v.groups) for v in o.data.vertices))
    report['materials']=[{'slot':i,'name':n,'roughness':r,'metalness':mt,'basecolor_texture':'source/textures/'+n+'_BaseColor.png','normal_texture':'source/textures/'+n+'_Normal.png'} for i,(n,r,mt) in enumerate(zip(MAT_NAMES,[.5,.7,.3,.32,.27,.4,.15,.22],[0,0,.4,.82,.5,0,0,.05]))]
    report['unreal_import']={'deform_bones':64,'nonempty_morph_targets':32,'source_shape_keys':33,'omitted_zero_delta_shape':'wrist_flex.R','name_sanitization':'period -> underscore'}
    report['actual_neutral_bounds_m']={'min':[min(v.co[i] for v in meshes[0].data.vertices) for i in range(3)],'max':[max(v.co[i] for v in meshes[0].data.vertices) for i in range(3)]}
    for fn in ['rig_tools.py','character.py']:
        text=bpy.data.texts.get(fn) or bpy.data.texts.new(fn);text.clear();text.write(Path(__file__).with_name(fn).read_text())
    ROOT.joinpath('docs/material_and_lod_report.json').write_text(json.dumps(report,indent=2))
    for image in bpy.data.images:
        if image.filepath:image.filepath='//textures/'+Path(image.filepath).name
    path=ROOT/'source/Character_Master.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
    print('CHARACTER_READY',path,json.dumps(report))
    return rig,meshes[0]

if __name__=='__main__':
    rig,face=build()
    bpy.context.scene.render.filepath=str(ROOT/'docs/character_inspection.png');bpy.ops.render.render(write_still=True)
