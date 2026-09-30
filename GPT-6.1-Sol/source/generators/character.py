"""Original parametric character geometry, surface library and fitted skin weights.
Run through build_character.py in the supplied Blender. No external model data.
"""
import bpy, math, json
from mathutils import Vector
from pathlib import Path

PALETTE = [
 ('Skin',(0.49,.245,.16,1),0.0,.46),
 ('Suit',(.052,.034,.086,1),0.05,.69),
 ('Armor',(.065,.09,.12,1),.72,.32),
 ('Silver',(.40,.48,.52,1),.85,.24),
 ('Accent',(.015,.72,.66,1),.28,.34),
 ('Hair',(.025,.018,.038,1),0,.51),
 ('Eyes',(.91,.88,.78,1),0,.20),
 ('Mouth',(.16,.024,.030,1),0,.46),
]

class MeshBuilder:
 def __init__(self):
  self.v=[];self.f=[];self.m=[];self.w=[]
 def vert(self,p,weights):
  self.v.append(tuple(p));self.w.append(dict(weights));return len(self.v)-1
 def face(self,idx,mat):self.f.append(tuple(idx));self.m.append(mat)
 def rings(self,centers,radii,weights,mat,segments=20,axis=None,cap=True):
  # Each section can supply an elliptical radius; axis constant for anatomical tubes.
  start=len(self.v); rings=[]
  if axis is None: axis=Vector(centers[-1])-Vector(centers[0])
  axis=Vector(axis).normalized();u=axis.cross(Vector((0,1,0)))
  if u.length<.01:u=axis.cross(Vector((1,0,0)))
  u.normalize();v=axis.cross(u).normalized()
  for i,(c,r) in enumerate(zip(centers,radii)):
   if isinstance(r,(int,float)):r=(r,r)
   ring=[]
   for k in range(segments):
    a=2*math.pi*k/segments
    ring.append(self.vert(Vector(c)+u*(r[0]*math.cos(a))+v*(r[1]*math.sin(a)),weights[i]))
   rings.append(ring)
  for j in range(len(rings)-1):
   for k in range(segments):self.face((rings[j][k],rings[j][(k+1)%segments],rings[j+1][(k+1)%segments],rings[j+1][k]),mat)
  if cap:
   self.face(tuple(reversed(rings[0])),mat);self.face(rings[-1],mat)
  return rings
 def ellipsoid(self,center,scale,weights,mat,seg=28,rows=16,rotation=None):
  rings=[]
  for j in range(rows+1):
   lat=-math.pi/2+math.pi*j/rows;r=max(.00002,math.cos(lat));ring=[]
   for k in range(seg):
    a=k*math.tau/seg;p=Vector((scale[0]*r*math.cos(a),scale[1]*r*math.sin(a),scale[2]*math.sin(lat)))
    if rotation:p=rotation@p
    ring.append(self.vert(Vector(center)+p,weights))
   rings.append(ring)
  for j in range(rows):
   for k in range(seg):self.face((rings[j][k],rings[j][(k+1)%seg],rings[j+1][(k+1)%seg],rings[j+1][k]),mat)
 def box(self,center,scale,weights,mat,bevel=.008,rotation=None):
  bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.scale=scale
  if rotation:o.rotation_euler=rotation
  bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  mod=o.modifiers.new('Manufactured edges','BEVEL');mod.width=bevel;mod.segments=3
  bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=mod.name)
  base=len(self.v)
  for v in o.data.vertices:self.vert(o.matrix_world@v.co,weights)
  for p in o.data.polygons:self.face([base+i for i in p.vertices],mat)
  bpy.data.objects.remove(o,do_unlink=True)
 def create(self,name,materials):
  used=sorted({i for face in self.f for i in face});mapping={i:j for j,i in enumerate(used)}
  self.v=[self.v[i] for i in used];self.w=[self.w[i] for i in used];self.f=[tuple(mapping[i] for i in face) for face in self.f]
  mesh=bpy.data.meshes.new(name);mesh.from_pydata(self.v,[],self.f);mesh.update()
  ob=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(ob)
  for m in materials:mesh.materials.append(m)
  for p,mat in zip(mesh.polygons,self.m):p.material_index=mat;p.use_smooth=True
  groups={}
  for i,ws in enumerate(self.w):
   total=sum(ws.values())
   for bone,w in ws.items():
    if bone not in groups:groups[bone]=ob.vertex_groups.new(name=bone)
    if w>1e-5:groups[bone].add([i],w/total,'REPLACE')
  return ob


def materials(root):
 result=[]
 for name,color,metal,rough in PALETTE:
  m=bpy.data.materials.new(name);m.use_nodes=True;n=m.node_tree.nodes;p=n.get('Principled BSDF')
  p.inputs['Base Color'].default_value=color;p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
  # Authored tile textures packed in source; UVs remain available for rebaking.
  im=bpy.data.images.new(name+'_BaseColor',width=256,height=256)
  pixels=[]
  for y in range(256):
   for x in range(256):
    weave=math.sin(x*math.pi)*math.sin(y*math.pi) # deterministic microvariation, plus visible woven grain
    grain=(math.sin(x*2.7+y*3.1)+math.sin(x*.51-y*.71))*.009
    if name=='Suit':grain+=((x%8<2)^(y%8<2))*.015
    pixels.extend([max(0,min(1,c+grain)) for c in color[:3]]+[1])
  im.pixels.foreach_set(pixels);im.filepath_raw=str(root/'source/textures'/f'{name}_BaseColor.png');im.file_format='PNG';im.save();im.pack();im.filepath='//textures/'+name+'_BaseColor.png'
  t=n.new('ShaderNodeTexImage');t.image=im;t.label='Editable original surface color';m.node_tree.links.new(t.outputs['Color'],p.inputs['Base Color'])
  if name in ['Skin','Suit']:
   normal=bpy.data.images.new(name+'_Normal',width=256,height=256);normal.colorspace_settings.name='Non-Color';pixels=[]
   for y in range(256):
    for x in range(256):
     amp=.12 if name=='Skin' else .29
     dx=amp*math.cos(x*math.pi/2)*math.sin(y*math.pi/2)
     dy=amp*math.sin(x*math.pi/2)*math.cos(y*math.pi/2)
     vec=Vector((-dx,-dy,1)).normalized();pixels.extend([.5+.5*vec.x,.5+.5*vec.y,.5+.5*vec.z,1])
   normal.pixels.foreach_set(pixels);normal.filepath_raw=str(root/'source/textures'/f'{name}_Normal.png');normal.file_format='PNG';normal.save();normal.pack();normal.filepath='//textures/'+name+'_Normal.png'
   sample=n.new('ShaderNodeTexImage');sample.image=normal;sample.label='Editable tangent surface normal'
   normalmap=n.new('ShaderNodeNormalMap');normalmap.inputs['Strength'].default_value=.55
   m.node_tree.links.new(sample.outputs['Color'],normalmap.inputs['Color']);m.node_tree.links.new(normalmap.outputs['Normal'],p.inputs['Normal'])
  if name=='Accent':p.inputs['Emission Color'].default_value=color;p.inputs['Emission Strength'].default_value=.28
  result.append(m)
 return result


def section_body(b):
 # Fitted soft underlayer; deliberate section rings at ribcage, waist, hip, bend joints.
 heights=[.87,.91,.96,1.01,1.06,1.12,1.18,1.24,1.30,1.35,1.39,1.42]
 widths=[.128,.148,.15,.133,.122,.131,.15,.173,.183,.188,.18,.12]
 depths=[.10,.10,.101,.089,.085,.094,.101,.105,.105,.098,.084,.06]
 ws=[]
 for z in heights:
  if z<1.04:ws.append({'pelvis':1})
  elif z<1.14:ws.append({'spine_01':1-(z-1.04)/.10,'spine_02':(z-1.04)/.10})
  elif z<1.28:ws.append({'spine_02':1-(z-1.14)/.14,'chest':(z-1.14)/.14})
  else:ws.append({'chest':1})
 b.rings([(0,0,z) for z in heights],list(zip(widths,depths)),ws,1,48,axis=(0,0,1))
 # neck, shoulders and organic arms have multi-ring smooth deforming transitions.
 b.rings([(0,0,1.425),(0,0,1.46),(0,0,1.50),(0,0,1.535)],[(.065,.059),(.057,.055),(.055,.052),(.058,.053)],[{'chest':1},{'neck':1},{'neck':.6,'head':.4},{'head':1}],0,32)
 for side,s in [('L',-1),('R',1)]:
  hip=Vector((s*.10,0,.94));knee=Vector((s*.11,-.025,.53));ankle=Vector((s*.11,0,.10))
  thigh=f'thigh.{side}';shin=f'shin.{side}';foot=f'foot.{side}'
  centers=[];radii=[];weights=[]
  for t,r in [(0,.092),(.12,.094),(.35,.084),(.63,.071),(.83,.06),(.92,.058),(1,.056)]:
   centers.append(hip.lerp(knee,t));radii.append((r,r*.9));weights.append({thigh:1} if t<.75 else {thigh:1-(t-.75)*2,shin:(t-.75)*2})
  for t,r in [(.06,.055),(.14,.054),(.26,.06),(.48,.055),(.73,.043),(.89,.034),(1,.032)]:
   centers.append(knee.lerp(ankle,t));radii.append((r,r*.90));weights.append({thigh:max(0,.5-t*2.8),shin:min(1,.5+t*2.8)})
  b.rings(centers,radii,weights,1,28,axis=(0,0,1))
  # boot wraps ankle and foot in soft cuff with sole/toe blocks.
  b.rings([(s*.11,0,.085),(s*.11,0,.13),(s*.11,0,.18)],[(.047,.04),(.042,.04),(.039,.036)],[{foot:1},{shin:.45,foot:.55},{shin:1}],2,24)
  b.box((s*.11,-.064,.058),(.099,.217,.106),{foot:1},2,.022)
  b.box((s*.11,-.068,.014),(.103,.22,.028),{foot:1},3,.009)
  b.box((s*.11,-.149,.039),(.098,.07,.071),{f'toe.{side}':.7,foot:.3},2,.015)
  b.box((s*.11,-.175,.065),(.065,.022,.016),{f'toe.{side}':1},4,.004)
  # Human deltoids stay organic and visible, flex clothing doesn't hide bend.
  shoulder=Vector((s*.19,0,1.39));elbow=Vector((s*.34,0,1.15));wrist=Vector((s*.40,-.015,.94))
  arm=f'upper_arm.{side}';fore=f'forearm.{side}';hand=f'hand.{side}'
  centers=[];radii=[];weights=[]
  for t,r in [(0,.067),(.12,.071),(.28,.064),(.50,.057),(.76,.047),(.91,.041),(1,.039)]:
   centers.append(shoulder.lerp(elbow,t));radii.append((r,r*.91));weights.append({arm:1} if t<.75 else {arm:1-(t-.75)*2,fore:(t-.75)*2})
  for t,r in [(.10,.041),(.24,.047),(.48,.043),(.72,.034),(.91,.027),(1,.026)]:
   centers.append(elbow.lerp(wrist,t));radii.append((r,r*.9));weights.append({arm:max(0,.5-t*2.4),fore:min(1,.5+t*2.4)})
  b.rings(centers,radii,weights,0 if side=='L' else 1,28,axis=wrist-shoulder)
  # Short tailored sleeve hem on right only; left organic limb visible.
  if side=='R':
   b.ellipsoid((.198,0,1.361),(.073,.066,.088),{arm:.85,'clavicle.R':.15},1,24,14)
  # Palm and individually jointed fingers, flattened anatomical palm.
  palm_center=Vector((s*.413,-.018,.893))
  b.ellipsoid(palm_center,(.038,.018,.054),{hand:1},0 if side=='L' else 2,24,16)
  # Fingers follow downwards palm. Four fingers evenly across X, thumb oblique inward.
  for n,x,length in [('index',-.027,.068),('middle',-.009,.075),('ring',.010,.071),('pinky',.027,.055)]:
   base=Vector((s*(.414+x),-.020,.857));points=[base,base+Vector((0,-.002,-length*.40)),base+Vector((0,-.004,-length*.74)),base+Vector((0,-.006,-length))]
   cs=[];rs=[];wts=[]
   for j in range(3):
    for t in [0,.16,.65,.90]:
     cs.append(points[j].lerp(points[j+1],t));rs.append((.0083 if n!='pinky' else .0067)*(1-j*.13)*(1-.06*t));ws={f'{n}_{j+1:02}.{side}':1}
     if t>.65 and j<2:ws={f'{n}_{j+1:02}.{side}':1-(t-.65),f'{n}_{j+2:02}.{side}':t-.65}
     wts.append(ws)
   cs.append(points[-1]);rs.append(.0038);wts.append({f'{n}_03.{side}':1})
   b.rings(cs,rs,wts,0 if side=='L' else 3,12,axis=(0,0,-1))
  thumbpoints=[Vector((s*.382,-.019,.914)),Vector((s*.363,-.032,.891)),Vector((s*.354,-.039,.867)),Vector((s*.357,-.043,.851))]
  cs=[];rs=[];wts=[]
  for j in range(3):
   for t in [0,.22,.72,.92]:
    cs.append(thumbpoints[j].lerp(thumbpoints[j+1],t));rs.append(.011*(1-j*.17));wts.append({f'thumb_{j+1:02}.{side}':1})
  cs.append(thumbpoints[-1]);rs.append(.005);wts.append({f'thumb_03.{side}':1})
  b.rings(cs,rs,wts,0 if side=='L' else 3,12,axis=thumbpoints[-1]-thumbpoints[0])


def face(b):
 # Parametric skull with feature relief and actual mouth opening. Front is -Y.
 zs=[1.50,1.516,1.53,1.542,1.553,1.564,1.575,1.583,1.59,1.597,1.604,1.611,1.618,1.625,1.632,1.64,1.648,1.658,1.668,1.677,1.687,1.7,1.714,1.73,1.748,1.765,1.78,1.792,1.80]
 widths=[.033,.043,.051,.058,.064,.07,.075,.08,.084,.087,.09,.091,.092,.092,.092,.092,.093,.094,.094,.093,.092,.09,.086,.08,.071,.061,.047,.032,.0001]
 depths=[.043,.050,.057,.063,.070,.077,.084,.087,.09,.091,.092,.092,.093,.094,.095,.097,.1,.102,.104,.106,.107,.108,.107,.103,.097,.088,.072,.051,.0001]
 seg=96;rings=[]
 def gauss(x,z,cx,cz,wx,wz):return math.exp(-((x-cx)/wx)**2-((z-cz)/wz)**2)
 for z,w,d in zip(zs,widths,depths):
  ring=[]
  for k in range(seg):
   a=(k/seg)*math.tau;x=w*math.sin(a);y=-d*math.cos(a)+.009
   front=max(0,math.cos(a))**9
   # Bridge/tip, chin, muzzle, cheekbone, eye orbit anatomy.
   relief=.026*gauss(x,z,0,1.642,.015,.041)+.024*gauss(x,z,0,1.626,.022,.013)
   relief+=.010*(gauss(x,z,.046,1.633,.027,.017)+gauss(x,z,-.046,1.633,.027,.017))
   relief+=.006*gauss(x,z,0,1.554,.042,.020)
   relief-=.019*(gauss(x,z,.035,1.666,.025,.014)+gauss(x,z,-.035,1.666,.025,.014))
   y-=relief*front
   jaw=max(0,min(1,(1.61-z)/.067)) if math.cos(a)>.1 else max(0,min(.6,(1.59-z)/.09))
   jaw=max(jaw,max(0,min(1,(1.593-z)/.018))*gauss(x,z,0,1.573,.060,.052)*front)
   side='L' if x<0 else 'R'
   cheek=.45*gauss(x,z,(-1 if x<0 else 1)*.05,1.638,.026,.025)*front
   brow=.48*gauss(x,z,(-1 if x<0 else 1)*.035,1.694,.026,.013)*front
   head=max(.01,1-jaw*.9-cheek-brow)
   ring.append(b.vert((x,y,z),{'head':head,'jaw':jaw*.9,f'cheek.{side}':cheek,f'brow.{side}':brow}))
  rings.append(ring)
 # Remove four central front strips between mouth border levels (physical oral aperture).
 mi0=zs.index(1.575);mi1=zs.index(1.59)
 for j in range(len(zs)-1):
  for k in range(seg):
   signed=k if k<seg//2 else k-seg
   if mi0<=j<mi1 and -4<=signed<4:continue
   b.face((rings[j][k],rings[j][(k+1)%seg],rings[j+1][(k+1)%seg],rings[j+1][k]),0)
 b.face(tuple(reversed(rings[0])),0)
 # Lips: concentric quad ring around an elliptical oral opening, carefully supported.
 loops=[]
 for r in range(5):
  outer=r/4;loop=[]
  for k in range(48):
   a=k*math.tau/48;x=(.030+outer*.009)*math.cos(a);z=1.5825+(outer*.0115)*math.sin(a)
   y=-.089-.007*math.sin(math.pi*outer)-.001*(1-outer)
   # upper cupid bow and closed center create real seal at neutral.
   if math.sin(a)>0:z+=.0015*math.exp(-(x/.008)**2)*outer*(1-outer)
   bone='lip_upper' if math.sin(a)>=0 else 'lip_lower';headweight=outer*.9
   side='L' if x<0 else 'R';corner=max(0,(abs(math.cos(a))-.65)/.35)*(1-outer*.7)
   ws={bone:(1-headweight)*(1-corner),('head' if math.sin(a)>=0 else 'jaw'):headweight,f'lip_corner.{side}':(1-headweight)*corner}
   loop.append(b.vert((x,y,z),ws))
  loops.append(loop)
 for j in range(4):
  for k in range(48):b.face((loops[j+1][k],loops[j+1][(k+1)%48],loops[j][(k+1)%48],loops[j][k]),0)
 # Inner sealed mouth cavity prevents view through skull; teeth/tongue real geometries.
 oral=[]
 for depth in [-.069,-.044,-.018]:
  ring=[]
  for k in range(48):
   a=k*math.tau/48;jaw=(1-math.sin(a))*.5
   ring.append(b.vert((.034*math.cos(a),depth,1.582+.019*math.sin(a)),{'jaw':jaw,'head':1-jaw}))
  oral.append(ring)
 for j in range(2):
  for k in range(48):b.face((oral[j][k],oral[j][(k+1)%48],oral[j+1][(k+1)%48],oral[j+1][k]),7)
 b.face(tuple(reversed(oral[-1])),7)
 b.box((0,-.074,1.585),(.047,.009,.008),{'head':1},6,.003)
 b.box((0,-.067,1.583),(.044,.009,.007),{'jaw':1},6,.003)
 b.ellipsoid((0,-.062,1.578),(.018,.015,.004),{'tongue':1},7,24,10)
 # eyeballs, irises, pupils, corneal dark border. Eyelid curved arc strips.
 for side,s in [('L',-1),('R',1)]:
  eye=f'eye.{side}';cx=s*.035;cy=-.066;cz=1.666
  b.ellipsoid((cx,cy,cz),(.022,.018,.017),{eye:1},6,40,24)
  b.ellipsoid((cx,cy-.0175,cz),(.0095,.0024,.010),{eye:1},4,32,16)
  b.ellipsoid((cx,cy-.0194,cz),(.0046,.001,.0055),{eye:1},5,24,12)
  b.ellipsoid((cx-s*.003,cy-.0192,cz+.003),(.0019,.0007,.002),{eye:1},6,16,8)
  for upper in [True,False]:
   arc=[]
   for band in range(4):
    frac=band/3;row=[]
    for k in range(33):
     a=math.pi*k/32;x=cx+.024*math.cos(a);z=cz+(1 if upper else -1)*(.010+.005*frac)*math.sin(a)
     y=cy-.016*math.sin(a)-.0055+frac*.001
     bone=f'lid_{"upper" if upper else "lower"}.{side}'
     row.append(b.vert((x,y,z),{bone:1-frac*.7,'head':frac*.7}))
    arc.append(row)
   for j in range(3):
    for k in range(32):b.face((arc[j+1][k],arc[j+1][k+1],arc[j][k+1],arc[j][k]) if upper else (arc[j][k],arc[j][k+1],arc[j+1][k+1],arc[j+1][k]),0)
  # Strong intentional brows, independent brow deform bones.
  points=[]
  for k in range(10):
   t=k/9;points.append((cx+(t-.5)*.047,-.089,1.688+.004*math.sin(t*math.pi)))
  b.rings(points,[.0026]*10,[{f'brow.{side}':1}]*10,5,8,axis=(1,0,0))
 # Nose nostril wings emphasize human anatomy, subtle ear pinnae and canal.
 for s in [-1,1]:
  b.ellipsoid((s*.012,-.107,1.625),(.011,.008,.007),{'head':1},0,20,12)
  b.ellipsoid((s*.009,-.113,1.621),(.004,.002,.002),{'head':1},7,16,10)
  b.ellipsoid((s*.095,.01,1.645),(.014,.019,.032),{'head':1},0,28,20)
  b.ellipsoid((s*.106,-.002,1.644),(.005,.010,.018),{'head':1},7,20,14)


def costume(b):
 # Split manufactured breast plate, asymmetric shoulder, belt and thigh plate.
 b.box((-.072,-.105,1.285),(.123,.022,.175),{'chest':1},2,.015,rotation=(0,-.10,-.10))
 b.box((.07,-.105,1.302),(.123,.024,.16),{'chest':1},2,.015,rotation=(0,.10,.10))
 b.box((0,-.117,1.275),(.025,.014,.091),{'chest':1},4,.006)
 for x in [-.082,.080]:b.box((x,-.121,1.345),(.066,.008,.017),{'chest':1},3,.004)
 b.box((.192,-.005,1.425),(.118,.122,.055),{'clavicle.R':.4,'upper_arm.R':.6},2,.015,rotation=(0,.3,0))
 b.box((.196,-.068,1.428),(.07,.012,.024),{'upper_arm.R':1},4,.004)
 b.rings([(0,0,.936),(0,0,.973)],[(.159,.112),(.154,.11)],[{'pelvis':1}]*2,2,48,axis=(0,0,1))
 b.box((0,-.112,.955),(.077,.025,.044),{'pelvis':1},3,.009)
 b.box((0,-.127,.955),(.042,.011,.024),{'pelvis':1},4,.004)
 b.box((-.145,-.007,.91),(.052,.079,.108),{'pelvis':1},2,.008)
 b.box((.113,-.077,.779),(.111,.022,.135),{'thigh.R':1},2,.013,rotation=(0,-.02,-.10))
 b.box((.12,-.093,.821),(.054,.008,.022),{'thigh.R':1},4,.003)
 for side,s in [('L',-1),('R',1)]:
  b.box((s*.11,-.075,.542),(.103,.033,.082),{f'shin.{side}':.5,f'thigh.{side}':.5},2,.014)
  b.box((s*.11,-.060,.35),(.063,.022,.166),{f'shin.{side}':1},2,.01)
  b.box((s*.13,-.074,.383),(.013,.008,.106),{f'shin.{side}':1},4,.003)
 # Right cybernetic forearm shell segmented across elbow/wrist. Original attached blade.
 elbow=Vector((.34,0,1.15));wrist=Vector((.40,-.015,.94));axis=wrist-elbow
 for t0,t1,r in [(.16,.42,.053),(.48,.71,.046),(.77,.93,.037)]:
  b.rings([elbow.lerp(wrist,t0),elbow.lerp(wrist,t1)],[(r,r*.86)]*2,[{'forearm.R':1}]*2,2,24,axis=axis)
 for t in [.31,.55,.80]:
  c=elbow.lerp(wrist,t);c.y-=.044
  b.box(c,(.041,.010,.025),{'forearm.R':1},3,.004,rotation=(0,-.27,0))
 b.box((.407,-.012,1.042),(.027,.046,.159),{'forearm.R':1},3,.007,rotation=(0,-.27,0))
 b.box((.372,-.057,1.015),(.050,.042,.122),{'forearm.R':1},2,.006,rotation=(0,-.27,0))
 b.ellipsoid((.39,-.08,.966),(.018,.009,.018),{'forearm.R':1},4,28,14)
 # blade tapered custom mesh on outer ulna; retracts along deformation bone.
 base=Vector((.442,.012,1.087));tip=Vector((.481,-.003,.825));idx=[]
 for p in [base+Vector((-.012,-.011,0)),base+Vector((.015,-.006,0)),base+Vector((.008,.013,0)),tip+Vector((0,-.003,0)),tip+Vector((0,.003,0))]:idx.append(b.vert(p,{'blade':1}))
 for f in [(0,1,3),(1,2,4,3),(2,0,3,4),(0,2,1)]:b.face([idx[i] for i in f],3)
 # Power cell and deployable beacon are skinned single rigid props with own bones.
 b.box((.395,.031,1.01),(.033,.037,.068),{'cell':1},2,.006)
 b.box((.395,.052,1.01),(.018,.009,.048),{'cell':1},4,.003)
 b.box((-.125,.118,.96),(.067,.047,.082),{'beacon':1},2,.008)
 b.box((-.125,.147,.964),(.042,.013,.043),{'beacon':1},4,.006)
 # Small flexible back cable with three weighted segments.
 path=[(.10,.095,1.37),(.13,.123,1.31),(.134,.148,1.23),(.104,.139,1.18),(.076,.114,1.18)]
 b.rings(path,[.006]*5,[{'cable_01':1},{'cable_01':.5,'cable_02':.5},{'cable_02':1},{'cable_03':1},{'cable_03':1}],3,12,axis=(0,0,-1))
 # Hair: short swept sculpted cap; face remains fully visible at inspection.
 rows=[]
 for j in range(13):
  t=j/12;ring=[]
  for k in range(64):
   a=k*math.tau/64;zbase=1.684+.038*max(0,math.cos(a))+.014*math.sin(a)
   z=zbase+(1.803-zbase)*t
   lat=(z-1.656)/.151;r=math.sqrt(max(.00001,1-lat*lat))
   x=.096*r*math.sin(a);y=.011-.111*r*math.cos(a)
   x+=.008*math.sin(t*math.pi);z+=.006*math.sin(a*3+t*5)*math.sin(math.pi*t)**2
   ring.append(b.vert((x,y,z),{'head':1}))
  rows.append(ring)
 for j in range(12):
  for k in range(64):b.face((rows[j][k],rows[j][(k+1)%64],rows[j+1][(k+1)%64],rows[j+1][k]),5)
 b.face(rows[-1],5)
 # Swept short hair panels intersect the fitted cap intentionally.
 for k in range(7):
  x=-.054+k*.017
  path=[(x,-.072,1.744),(x+.010,-.049,1.775),(x+.014,-.016,1.801),(x+.010,.020,1.796)]
  b.rings(path,[(.007,.003),(.008,.005),(.007,.004),(.001,.001)],[{'head':1}]*4,5,10,axis=(0,1,0))
 # Small original non-verbal chest signature, built as two aligned bars.
 b.box((-.071,-.12,1.293),(.038,.006,.008),{'chest':1},4,.002)
 b.box((-.082,-.12,1.278),(.016,.006,.008),{'chest':1},4,.002)


def uv_unwrap(ob):
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
 bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False) if hasattr(bpy.ops.mesh,'normals_make_consistent') else None
 bpy.ops.uv.smart_project(angle_limit=math.radians(63),island_margin=.008,area_weight=.3);bpy.ops.object.mode_set(mode='OBJECT')


def create_character(root):
 mats=materials(root);b=MeshBuilder();section_body(b);face(b);costume(b);b.v=[(x,y,min(1.80,z)) for x,y,z in b.v];ob=b.create('Operative_LOD0',mats)
 uv_unwrap(ob)
 return ob,mats
