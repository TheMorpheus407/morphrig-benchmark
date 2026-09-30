#!/usr/bin/env python3
"""Validate the concrete handoff inventory. Does not claim artistic acceptance."""
from __future__ import annotations
import argparse
import csv
import json
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit():
    results=[]
    def check(name, ok, detail=''):
        results.append({'check':name,'pass':bool(ok),'detail':detail})
    required=['README.md','source/Operative.blend','source/audio/dialogue.wav',
      'source/audio/dialogue.txt','source/audio/dialogue_alignment.json',
      'export/Operative.fbx','unreal/MorphRig.uproject',
      'docs/rig_usage.md','docs/skeleton_and_sockets.json',
      'docs/animation_manifest.json','docs/animation_state_contract.md',
      'docs/material_and_lod_report.json','docs/THIRD_PARTY_ASSETS.csv',
      'docs/build_and_import_instructions.md','docs/known_issues.md',
      'tools/export_and_bake.py','tools/build_linux.sh',
      'presentation/turntable.mp4','presentation/motion_showcase.mp4',
      'presentation/face_performance.mp4']
    for rel in required:
        p=ROOT/rel
        check('file:'+rel,p.is_file() and p.stat().st_size>0,p.stat().st_size if p.is_file() else 'missing')
    ids={x['id']:x for x in csv.DictReader((ROOT.parent/'required_animations.csv').open())}
    check('task inventory contains 96 distinct entries',len(ids)==96,len(ids))
    manifest=ROOT/'docs/animation_manifest.json'
    if manifest.exists():
        m=json.loads(manifest.read_text())
        clips=m if isinstance(m,list) else m.get('animations',m.get('clips',m.get('entries',m)))
        if isinstance(clips,dict):
            clips=[dict(v,id=k) for k,v in clips.items() if isinstance(v,dict)]
        keyed={v.get('id',v.get('name')):v for v in clips}
        check('manifest covers exact required IDs',set(keyed)==set(ids),{'missing':sorted(set(ids)-set(keyed)),'extra':sorted(set(keyed)-set(ids))})
        for id,c in keyed.items():
            export=c.get('exported_file',c.get('export_file',c.get('export',None)))
            if isinstance(export,dict): export=export.get('file')
            if export:
                p=ROOT/export
                check('export:'+id,p.is_file() and p.stat().st_size>1024,export)
    audio=ROOT/'source/audio/dialogue.wav'
    if audio.exists():
        with wave.open(str(audio)) as w:
            duration=w.getnframes()/w.getframerate()
            check('spoken performance duration in 12–18 s',12<=duration<=18,duration)
            check('speech PCM format',w.getnchannels()==1 and w.getsampwidth()==2,{'channels':w.getnchannels(),'bits':8*w.getsampwidth(),'sample_rate':w.getframerate()})
        alignment=json.loads((ROOT/'source/audio/dialogue_alignment.json').read_text())
        check('alignment duration matches actual WAV',abs(alignment['duration']-duration)<1/22050,alignment['duration'])
        ph=alignment['phonemes']
        check('phoneme event times monotonic',all(a['start']<=b['start'] for a,b in zip(ph,ph[1:])),len(ph))
        check('speech has all seven mapped visemes',len({p['viseme'] for p in ph}-{'neutral'})==7,sorted({p['viseme'] for p in ph}))
    for name in ('turntable','motion_showcase','face_performance'):
        path=ROOT/'presentation'/f'{name}.mp4'
        if path.exists():
            p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True)
            d=json.loads(p.stdout) if p.returncode==0 else {}
            check('playable video:'+name,any(s.get('codec_type')=='video' for s in d.get('streams',[])),d.get('format',{}).get('duration'))
            if name=='face_performance':
                check('face performance includes audio',any(s.get('codec_type')=='audio' for s in d.get('streams',[])))
    binaries=[p for p in (ROOT/'build/Linux').rglob('*') if p.is_file() and p.name=='MorphRig' and 'Binaries' in p.parts] if (ROOT/'build/Linux').exists() else []
    check('standalone Linux executable present',len(binaries)>0,[str(p.relative_to(ROOT)) for p in binaries])
    return {'scope':'File, metadata and media validation; visual quality requires separate inspection.',
        'passed':sum(r['pass'] for r in results),'total':len(results),'checks':results}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--strict',action='store_true')
    args=parser.parse_args()
    result=audit()
    out=ROOT/'docs/validation/delivery_audit.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(f"{result['passed']}/{result['total']} checks passed; {out.relative_to(ROOT)}")
    for r in result['checks']:
        if not r['pass']: print('FAIL',r['check'],r['detail'])
    if args.strict and result['passed']!=result['total']: raise SystemExit(1)

if __name__=='__main__': main()
