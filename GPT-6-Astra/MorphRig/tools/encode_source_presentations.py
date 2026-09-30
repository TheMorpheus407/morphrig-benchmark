"""Encode already-rendered final-source frames and validate concrete media streams."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['both','turntable','face'],default='both');args=p.parse_args()
reports=[]
for mode,output,frames in [('turntable','turntable',240),('face','face_performance',420)]:
 if args.mode not in ('both',mode):continue
 folder=ROOT/'presentation/frames'/mode
 for i in range(frames):
  path=folder/f'{i:05d}.png'
  if not path.is_file():raise RuntimeError(f'Missing rendered frame {path}')
  if path.stat().st_mtime<(ROOT/'source/Operative.blend').stat().st_mtime:raise RuntimeError(f'Render predates current source: {path}')
 temporary=ROOT/'presentation'/f'{output}.encoding.mp4';dest=ROOT/'presentation'/f'{output}.mp4'
 command=['ffmpeg','-y','-hide_banner','-v','warning','-framerate','30','-start_number','0','-i',str(folder/'%05d.png')]
 if mode=='face':command+=['-i',str(ROOT/'source/audio/dialogue.wav')]
 command+=['-frames:v',str(frames),'-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart']
 if mode=='face':command+=['-c:a','aac','-b:a','128k','-af','apad','-t','14']
 else:command+=['-an']
 subprocess.run(command+[str(temporary)],check=True);temporary.replace(dest)
 data=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(dest)]))
 video=next(s for s in data['streams'] if s['codec_type']=='video');audio=[s for s in data['streams'] if s['codec_type']=='audio']
 report={'file':str(dest.relative_to(ROOT)),'encoding':'libx264 CRF18, slow, yuv420p; face audio AAC128k with silence pad to 14s','width':video['width'],'height':video['height'],'fps':video['r_frame_rate'],'frames':int(video['nb_read_frames']),'video_duration_s':float(video['duration']),'audio_streams':len(audio),'source_sha256':hashlib.sha256((ROOT/'source/Operative.blend').read_bytes()).hexdigest()}
 report['passed']=video['codec_name']=='h264' and report['width']==1920 and report['height']==1080 and report['fps']=='30/1' and report['frames']==frames and abs(report['video_duration_s']-frames/30)<.001 and (bool(audio) if mode=='face' else not audio)
 assert report['passed'],report
 if audio:report['audio_duration_s']=float(audio[0]['duration']);report['audio_codec']=audio[0]['codec_name']
 reports.append(report);print(json.dumps(report),flush=True)
(ROOT/'docs/validation/source_media_final.json').write_text(json.dumps(reports,indent=2))
