#!/usr/bin/env python3
"""Summarize actual warmed packaged-client frame samples (never capture playback)."""
import argparse
import csv
import json
import statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def percentile(values,p):
    values=sorted(values)
    k=(len(values)-1)*p;i=int(k)
    return values[i]+(values[min(i+1,len(values)-1)]-values[i])*(k-i)

def summarize(path):
    rows=list(csv.DictReader(path.open()))
    warm=[r for r in rows if float(r['elapsed_s'])>=10 and r.get('warmed_up','1')=='1']
    frames=[float(r['frame_ms']) for r in warm]
    if not frames:raise ValueError(f'No warmed-up frame samples in {path}')
    return {'csv':str(path.relative_to(ROOT)),'warmup_seconds':10,'samples':len(frames),
        'first_elapsed_s':float(warm[0]['elapsed_s']),'last_elapsed_s':float(warm[-1]['elapsed_s']),
        'instances':sorted({int(r['instances']) for r in warm}),
        'resolution':sorted({r['resolution'] for r in warm}),
        'rendered_lods':sorted({int(r['rendered_lod']) for r in warm if r.get('rendered_lod') is not None}),
        'mean_ms':statistics.mean(frames),'median_ms':statistics.median(frames),
        'p95_ms':percentile(frames,.95),'p99_ms':percentile(frames,.99),'maximum_ms':max(frames),
        'effective_fps':1000/statistics.mean(frames),
        'fraction_frames_within_16_667ms':sum(t<=1000/60 for t in frames)/len(frames)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('csv',nargs='+',type=Path)
    args=parser.parse_args()
    data={'method':'Packaged Unreal client wall-clock frame deltas. Discard first 10 seconds; average FPS=1000/mean frame_ms. No movie capture fixed timestep or generated frames.',
        'hardware':{'cpu':'AMD Ryzen 9 9950X, 16 cores / 32 threads','ram_gib':91,'gpu':'NVIDIA RTX 5090, 32 GiB','driver':'595.71.05','os':'NixOS x86-64'},
        'settings':{'resolution':'1920x1080','rhi':'Vulkan SM6','antialiasing':'TAA','resolution_percent':100,'vsync':False,'fps_cap':0,'ui_visible':True,'lod':'automatic','run_seconds':45,'warmup_seconds':10,'lumen':False,'nanite':False,'virtual_shadow_maps':False},
        'comparison_note':'The ten-actor view uses a wider camera and automatic lower LODs. This is the delivered instance-toggle behavior, not a controlled same-LOD scaling benchmark. Hero rendered LOD is recorded for each run.',
        'hardware_evidence':['docs/validation/cpu.json','docs/validation/memory.txt','docs/validation/gpu.txt','docs/validation/kernel.txt'],
        'settings_evidence':['docs/validation/performance/DefaultEngine.ini','docs/validation/performance/DefaultGameUserSettings.ini','docs/validation/performance/gpu_before.txt','docs/validation/performance/gpu_after.txt'],
        'runs':[summarize(p.resolve()) for p in args.csv]}
    out=ROOT/'docs/performance_report.json';out.write_text(json.dumps(data,indent=2)+'\n')
    lines=['# Measured packaged-client performance','','The standalone Linux client runs for 45 seconds per view; the first 10 seconds are discarded. These are actual wall-clock frame deltas, without screenshot capture, a fixed time step or generated frames. This project’s render, import and build workers are idle during measurement. Other desktop processes are recorded in the GPU snapshots.','','Host: AMD Ryzen 9 9950X (16 cores / 32 threads), 91 GiB RAM, NVIDIA RTX 5090 (32 GiB), driver 595.71.05, NixOS x86-64.','','Settings: windowed 1920×1080, Vulkan SM6, native 100% resolution, TAA, visible UI, automatic LOD, VSync off and no FPS cap. Default showcase lighting; Lumen, Nanite and virtual shadow maps disabled. Full renderer and scalability settings are retained in the [configuration snapshots](validation/performance/).','','| Instances | Resolution | Samples | Mean ms | p95 ms | p99 ms | Effective FPS |','|---|---|---:|---:|---:|---:|---:|']
    for r in data['runs']:
        lines.append(f"| {r['instances'][0]} | {', '.join(r['resolution'])} | {r['samples']} | {r['mean_ms']:.3f} | {r['p95_ms']:.3f} | {r['p99_ms']:.3f} | {r['effective_fps']:.1f} |")
    lines+=['','The ten-actor view uses a wider camera and automatic lower LODs. The comparison includes the effects of screen coverage and LOD selection. These results measure the delivered views rather than a controlled same-LOD scaling benchmark.']
    for r in data['runs']:
        lines.append(f"\n{r['instances'][0]} actor(s): hero rendered LOD {r['rendered_lods']}; {r['fraction_frames_within_16_667ms']*100:.3f}% of warmed frames meet the 16.67 ms / 60 FPS target; slowest recorded frame {r['maximum_ms']:.3f} ms. [Raw CSV]({Path(r['csv']).relative_to('docs')}).")
    lines+=['','[Machine-readable report](performance_report.json) includes all percentiles and evidence paths. Results apply to this reference host and recorded configuration.']
    (ROOT/'docs/performance_report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(data,indent=2))

if __name__=='__main__':main()
