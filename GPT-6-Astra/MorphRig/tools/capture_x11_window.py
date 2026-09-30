#!/usr/bin/env python3
"""Capture only the specified showcase X11 window for interactive QA."""
import argparse
import ctypes as C
import glob
import os
from pathlib import Path
from PIL import Image

p=argparse.ArgumentParser();p.add_argument('window',type=lambda s:int(s,0));p.add_argument('output',type=Path);args=p.parse_args()
lib=None
for name in ['libX11.so.6',*glob.glob('/nix/store/*libX11*/lib/libX11.so.6')]:
    try:lib=C.CDLL(name);break
    except OSError:continue
if lib is None:raise RuntimeError('libX11 is required')
class XImage(C.Structure):
    _fields_=[('width',C.c_int),('height',C.c_int),('xoffset',C.c_int),('format',C.c_int),('data',C.c_void_p),('byte_order',C.c_int),('bitmap_unit',C.c_int),('bitmap_bit_order',C.c_int),('bitmap_pad',C.c_int),('depth',C.c_int),('bytes_per_line',C.c_int),('bits_per_pixel',C.c_int)]
lib.XOpenDisplay.restype=C.c_void_p;lib.XOpenDisplay.argtypes=[C.c_char_p]
lib.XGetGeometry.argtypes=[C.c_void_p,C.c_ulong,*([C.POINTER(C.c_ulong)]+[C.POINTER(C.c_int)]*2+[C.POINTER(C.c_uint)]*4)]
lib.XGetImage.restype=C.POINTER(XImage);lib.XGetImage.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_ulong,C.c_int]
lib.XDestroyImage.argtypes=[C.POINTER(XImage)]
lib.XCloseDisplay.argtypes=[C.c_void_p]
display=lib.XOpenDisplay(os.environ.get('DISPLAY',':0').encode())
if not display:raise RuntimeError('No X11 display')
root=C.c_ulong();x=C.c_int();y=C.c_int();w=C.c_uint();h=C.c_uint();border=C.c_uint();depth=C.c_uint()
if not lib.XGetGeometry(display,args.window,C.byref(root),C.byref(x),C.byref(y),C.byref(w),C.byref(h),C.byref(border),C.byref(depth)):raise RuntimeError('Window geometry unavailable')
ptr=lib.XGetImage(display,args.window,0,0,w.value,h.value,0xFFFFFFFF,2)
if not ptr:raise RuntimeError('Window image unavailable')
im=ptr.contents
if im.bits_per_pixel!=32 or im.byte_order!=0:raise RuntimeError('Unsupported X11 pixel layout')
raw=C.string_at(im.data,im.bytes_per_line*im.height)
args.output.parent.mkdir(parents=True,exist_ok=True)
Image.frombytes('RGB',(im.width,im.height),raw,'raw','BGRX',im.bytes_per_line).save(args.output)
lib.XDestroyImage(ptr);lib.XCloseDisplay(display)
print(args.output)
