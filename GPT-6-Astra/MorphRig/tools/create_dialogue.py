#!/usr/bin/env python3
"""Create original speech and sample-accurate synthesis events using local eSpeak NG.

Run inside nix-shell -p espeak-ng: python3 MorphRig/tools/create_dialogue.py
No pretrained neural voice or downloaded speech is used.
"""
from __future__ import annotations
import ctypes as C
import ctypes.util
import json
import re
from pathlib import Path
import shutil
import wave

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = ("Hold this lane. I can stabilize the network, but I need a clear signal. "
              "There... the relay is responding. Keep your eyes on the crossing. "
              "We have a path now. Move with me.")

class EventID(C.Union):
    _fields_ = [('number', C.c_int), ('name', C.c_char_p), ('string', C.c_char * 8)]

class Event(C.Structure):
    _fields_ = [('type', C.c_int), ('unique_identifier', C.c_uint),
                ('text_position', C.c_int), ('length', C.c_int),
                ('audio_position', C.c_int), ('sample', C.c_int),
                ('user_data', C.c_void_p), ('id', EventID)]

def viseme(p):
    p = re.sub(r"[0-9#]", "", p.lstrip("',"))
    if p in ('m','b','p'): return 'lip_close'
    if p in ('f','v'): return 'labiodental'
    if p in ('T','D','l'): return 'tongue_teeth'
    if p in ('w','u:','U','oU','o:','O:','O','3:','@U'): return 'rounded_vowel'
    if p in ('i:','I','i','e','eI','E','j'): return 'wide_vowel'
    if any(x in p for x in ('a','A','V','@')): return 'open_vowel'
    if p.startswith('_') or not p: return 'neutral'
    return 'consonant'

def main():
    executable = shutil.which('espeak-ng')
    if executable:
        library = Path(executable).resolve().parents[1] / 'lib/libespeak-ng.so'
    else:
        library = C.util.find_library('espeak-ng')
    if not library:
        raise SystemExit('Run through nix-shell -p espeak-ng or install eSpeak NG.')
    lib = C.CDLL(str(library))
    lib.espeak_Initialize.argtypes = [C.c_int,C.c_int,C.c_char_p,C.c_int]
    sr = lib.espeak_Initialize(2, 20, None, 1)
    assert sr > 0
    lib.espeak_SetVoiceByName.argtypes=[C.c_char_p]
    assert lib.espeak_SetVoiceByName(b'en-us+f3') == 0
    lib.espeak_SetParameter(1, 140, 0)
    lib.espeak_SetParameter(2, 95, 0)
    lib.espeak_SetParameter(3, 47, 0)
    samples = bytearray()
    events = []
    CALLBACK = C.CFUNCTYPE(C.c_int, C.POINTER(C.c_short), C.c_int, C.POINTER(Event))
    @CALLBACK
    def callback(wav, n, es):
        if wav and n:
            samples.extend(C.string_at(wav, n*2))
        i = 0
        while es and es[i].type:
            e = es[i]
            if e.type in (1,7):
                events.append({'kind':e.type,'start':e.audio_position/1000,
                    'position':e.text_position, 'length':e.length,
                    'phoneme':bytes(e.id.string).decode('utf8','replace') if e.type==7 else ''})
            i+=1
        return 0
    lib.espeak_SetSynthCallback(callback)
    lib.espeak_Synth.argtypes = [C.c_void_p,C.c_size_t,C.c_uint,C.c_int,C.c_uint,C.c_uint,C.POINTER(C.c_uint),C.c_void_p]
    payload = TRANSCRIPT.encode() + b'\0'
    uid = C.c_uint()
    assert lib.espeak_Synth(payload,len(payload),0,1,0,1,C.byref(uid),None)==0
    lib.espeak_Synchronize()
    lib.espeak_Terminate()
    # Small leading and trailing rests make facial preparation and settling explicit.
    lead, tail = .3, .45
    pcm = b'\0\0' * round(sr*lead) + bytes(samples) + b'\0\0' * round(sr*tail)
    duration = len(pcm)/(2*sr)
    out = ROOT / 'source/audio'
    out.mkdir(parents=True,exist_ok=True)
    with wave.open(str(out/'dialogue.wav'),'wb') as w:
        w.setparams((1,2,sr,0,'NONE','not compressed'))
        w.writeframes(pcm)
    words, phonemes = [], []
    for e in events:
        t = round(e['start']+lead,4)
        if e['kind']==1:
            words.append({'text':TRANSCRIPT[e['position']-1:e['position']-1+e['length']], 'start':t})
        else:
            phonemes.append({'phoneme':e['phoneme'],'start':t,'viseme':viseme(e['phoneme'])})
    for seq in (words,phonemes):
        for i,e in enumerate(seq):
            e['end'] = seq[i+1]['start'] if i+1 < len(seq) else round(duration-tail,4)
    mapping = {p['phoneme']:p['viseme'] for p in phonemes}
    alignment = {'schema_version':1, 'transcript':TRANSCRIPT, 'duration':duration,
        'sample_rate':sr, 'channels':1, 'sample_width_bits':16,
        'voice':'eSpeak NG built-in en-us+f3 (formant synthesis)',
        'alignment_method':'Native eSpeak NG phoneme and word events from the same PCM synthesis callback; 0.300 s leading rest added to both audio and events.',
        'words':words,'phonemes':phonemes,
        'visemes':[{'name':p['viseme'],'start':p['start'],'end':p['end'],'value':1.0} for p in phonemes if p['viseme']!='neutral'],
        'viseme_mapping':mapping,
        'emotional_beats':[{'start':0,'end':6.6,'expression':'concern','gaze':'front then crossing left','gesture':'left palm caution'},
                           {'start':6.6,'end':10.3,'expression':'focus','gaze':'wrist emitter then camera','gesture':'relay recognition'},
                           {'start':10.3,'end':duration,'expression':'joy_confidence','gaze':'front','gesture':'open invitation then settle'}]}
    (out/'dialogue.txt').write_text(TRANSCRIPT+'\n')
    (out/'dialogue_alignment.json').write_text(json.dumps(alignment,indent=2)+'\n')
    print(json.dumps({'duration':duration,'phonemes':len(phonemes),'words':len(words),'sample_rate':sr,'phoneme_map':mapping},indent=2))
    assert 12 <= duration <= 18, f'Adjust rate: {duration:.3f} seconds'

if __name__=='__main__': main()
