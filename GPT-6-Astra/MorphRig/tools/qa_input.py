"""Temporary local input device for packaged UI validation; never a game dependency."""
import fcntl
import glob
import shutil
import os
from pathlib import Path
import struct
import subprocess
import time

XDOTOOL=os.environ.get('MORPH_XDOTOOL') or shutil.which('xdotool') or next(iter(glob.glob('/nix/store/*-xdotool-*/bin/xdotool')), None)
if not XDOTOOL: raise RuntimeError('xdotool is needed for this optional local QA helper')

class ShowcaseInput:
    def __init__(self,window):
        self.window=str(window);self.fd=None;self.held=set()
    def xdo(self,*args):subprocess.run([XDOTOOL,*map(str,args)],check=True)
    def read_xdo(self,*args):return subprocess.check_output([XDOTOOL,*map(str,args)],text=True).strip()
    def require_focus(self):
        active=self.read_xdo('getactivewindow');focus=self.read_xdo('getwindowfocus')
        if active!=self.window or focus!=self.window:
            raise RuntimeError(f'Input withheld: expected showcase window {self.window}, active={active}, focus={focus}')
    def activate(self):
        self.xdo('windowactivate','--sync',self.window);time.sleep(.15);self.require_focus()
    def __enter__(self):
        self.activate()
        self.fd=os.open('/dev/uinput',os.O_WRONLY|os.O_NONBLOCK)
        fcntl.ioctl(self.fd,0x40045564,1)
        for code in [*range(1,249),272,273,274]:fcntl.ioctl(self.fd,0x40045565,code)
        fcntl.ioctl(self.fd,0x40045564,2)
        for code in (0,1,8):fcntl.ioctl(self.fd,0x40045566,code)
        os.write(self.fd,struct.pack('80sHHHHI',b'MorphRig temporary validation input',3,0x1234,0x5678,1,0)+bytes(64*4*4))
        fcntl.ioctl(self.fd,0x5501);time.sleep(.7);self.require_focus();return self
    def event(self,typ,code,value):os.write(self.fd,struct.pack('llHHi',0,0,typ,code,value))
    def sync(self):self.event(0,0,0)
    def down(self,code):self.require_focus();self.held.add(code);self.event(1,code,1);self.sync()
    def up(self,code):self.event(1,code,0);self.sync();self.held.discard(code)
    def key(self,code,hold=.08):self.down(code);time.sleep(hold);self.up(code)
    def move(self,x,y):
        self.require_focus()
        self.xdo('mousemove','--window',self.window,x,y);time.sleep(.2)
        self.require_focus()
    def click(self,x,y):
        # Keep warp and click within XWayland's pointer coordinate space.
        # A native uinput click can instead follow KWin's stale native cursor.
        self.move(x,y);self.require_focus();self.xdo('click','1')
    def capture(self,path):subprocess.run(['python3',str(Path(__file__).with_name('capture_x11_window.py')),self.window,str(path)],check=True)
    def __exit__(self,*args):
        if self.fd is not None:
            for code in list(self.held):self.up(code)
            fcntl.ioctl(self.fd,0x5502);os.close(self.fd);self.fd=None
