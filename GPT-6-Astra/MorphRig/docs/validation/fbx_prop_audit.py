"""Read-only binary FBX geometry/material/unit inventory for the authored prop."""
from pathlib import Path
import struct,zlib,json,sys
root=Path(__file__).resolve().parents[2]
p=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'export/Beacon.fbx'
f=p.open('rb');f.seek(23);version=struct.unpack('<I',f.read(4))[0];wide=version>=7500

def prop():
 t=f.read(1).decode();formats={'Y':'h','C':'?','I':'i','F':'f','D':'d','L':'q'}
 if t in formats:
  fmt='<'+formats[t];return struct.unpack(fmt,f.read(struct.calcsize(fmt)))[0]
 if t in ['S','R']:
  n=struct.unpack('<I',f.read(4))[0];v=f.read(n);return v.decode('utf8','replace') if t=='S' else len(v)
 if t in 'fdlibc':
  n,enc,size=struct.unpack('<III',f.read(12));v=f.read(size);v=zlib.decompress(v) if enc else v;fmt={'f':'f','d':'d','l':'q','i':'i','b':'?','c':'b'}[t];return list(struct.unpack('<'+fmt*n,v))
 raise RuntimeError(t)
def node():
 data=f.read(25 if wide else 13)
 if not data or not any(data):return None
 end,n,sz,nl=struct.unpack('<QQQB' if wide else '<IIIB',data);name=f.read(nl).decode();ps=[prop() for _ in range(n)];cs=[]
 while f.tell()<end:
  c=node()
  if c is None:break
  cs.append(c)
 f.seek(end);return {'name':name,'props':ps,'children':cs}
tree=[]
while True:
 x=node()
 if x is None:break
 tree.append(x)
def child(n,name):return next(x for x in n['children'] if x['name']==name)
gl=next(n for n in tree if n['name']=='GlobalSettings');props=child(gl,'Properties70')['children'];units={n['props'][0]:n['props'][-1] for n in props if 'UnitScaleFactor' in n['props'][0]}
objs=next(n for n in tree if n['name']=='Objects')['children'];out={'file':str(p.relative_to(root)),'fbx_version':version,'units':units,'materials':[n['props'][:2] for n in objs if n['name']=='Material'],'geometry':[],'models':[]}
for n in objs:
 if n['name']=='Geometry':
  vs=child(n,'Vertices')['props'][0];coords=[vs[i:i+3] for i in range(0,len(vs),3)];m=child(child(n,'LayerElementMaterial'),'Materials')['props'][0];out['geometry'].append({'vertices':len(coords),'bounds_min':[min(v[k] for v in coords) for k in range(3)],'bounds_max':[max(v[k] for v in coords) for k in range(3)],'polygon_material_histogram':{str(i):m.count(i) for i in set(m)}})
 if n['name']=='Model':out['models'].append({'name':n['props'][1],'properties':{x['props'][0]:x['props'][4:] for x in child(n,'Properties70')['children']}})
print(json.dumps(out,indent=2));(root/'docs/validation/beacon_fbx_audit.json').write_text(json.dumps(out,indent=2))
