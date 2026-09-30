"""MorphRig's authored motion library; Blender 5.1, metres, -Y forward, 30 Hz.

All motion is constructed for this skeleton. No external animation data is used.
The analytic limb solver turns authored contact paths into editable FK curves.
EDIT__ actions retain the complete source sampling; identically named export actions
contain only evaluated deform transforms and are independent of rig constraints.
"""
import bpy, csv, json, math, os
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion, Euler
FPS=30
TAU=2*math.pi
DEPLOY_GRIP_OFFSET=Vector((.015,.089,.115))
DEPLOY_THUMB_TARGET=Vector((-.020,.008,.068))

def clamp(x,a=0,b=1): return max(a,min(b,x))
def smooth(x): x=clamp(x); return x*x*(3-2*x)
def pulse(t,a,b): return math.sin(math.pi*clamp((t-a)/(b-a))) if a<t<b else 0.
def vec(v): return Vector(v)
def lerp(a,b,t): return a+(b-a)*t

def mix(a,b,t):
    r={}; t=smooth(t)
    for k in a.keys()|b.keys():
        av=a.get(k,b.get(k)); bv=b.get(k,av)
        r[k]=tuple(lerp(x,y,t) for x,y in zip(av,bv)) if isinstance(av,(tuple,list)) else lerp(av,bv,t)
    return r

def timeline(t,keys):
    if t<=keys[0][0]: return keys[0][1].copy()
    for (a,p),(b,q) in zip(keys,keys[1:]):
        if t<=b: return mix(p,q,(t-a)/(b-a))
    return keys[-1][1].copy()

def pose(**kwargs):
    p=dict(pelvis=(0,0,0),pelvis_rot=(0,0,0),spine=(0,0,0),chest=(0,0,0),head=(0,0,0),
           footL=(.12,-.015,.11),footR=(-.12,.015,.11),handL=(.34,-.10,1.06),handR=(-.34,-.13,1.10),
           gripL=.16,gripR=.22,foot_pitchL=0.,foot_pitchR=0.,foot_yawL=0.,foot_yawR=0.,
           hand_rollL=0.,hand_rollR=0.,blinkL=0.,blinkR=0.,smile=0.,brow=0.,jaw=0.,squint=0.,gaze=(0,0),
           cell=0.,beacon=0.,secondary=0.,blade=1.,floor_hands=0.)
    p.update(kwargs); return p

READY=pose(pelvis=(0,0,-.025),footL=(.15,-.05,.11),footR=(-.15,.05,.11),handL=(.30,-.24,1.21),handR=(-.32,-.28,1.27),chest=(5,0,0),gripL=.35,gripR=.45)
AIM=pose(pelvis=(0,0,-.025),footL=(.15,-.05,.11),footR=(-.15,.05,.11),handL=(.23,-.26,1.24),handR=(-.16,-.60,1.40),chest=(3,0,-6),gripL=.30,gripR=.60)
CHANNEL=pose(pelvis=(0,0,-.075),footL=(.18,-.13,.11),footR=(-.18,.13,.11),handL=(.21,-.48,1.39),handR=(-.22,-.56,1.38),chest=(8,0,0),gripL=.08,gripR=.18)
CHARGE=pose(pelvis=(0,0,-.13),footL=(.19,-.05,.11),footR=(-.19,.08,.11),handL=(.22,-.26,1.28),handR=(-.25,-.20,1.22),chest=(12,0,0),head=(-8,0,0),gripL=.9,gripR=.9)
UPLINK=pose(pelvis=(0,0,-.018),handL=(.05,-.29,1.27),handR=(-.09,-.32,1.28),head=(15,0,-10),gripL=.15,gripR=.10)
STUN=pose(pelvis=(0,.03,-.10),spine=(9,-8,0),chest=(14,0,8),head=(18,8,-10),handL=(.33,-.10,1.12),handR=(-.24,-.17,1.45),footL=(.17,-.08,.11),footR=(-.17,.08,.11),gripL=.05,gripR=.06)
# Floor poses use explicit world contact targets and pelvis centres about 10 cm above the floor.
PRONE_FRONT=pose(pelvis=(0,.04,-.835),pelvis_rot=(88,0,0),spine=(0,0,0),chest=(-1,0,0),head=(17,0,23),footL=(.16,.77,.11),footR=(-.15,.78,.11),handL=(.37,-.52,.04),handR=(-.36,-.51,.048),gripL=.12,gripR=.2,foot_pitchL=0,foot_pitchR=0,foot_yawL=180,foot_yawR=180,blade=.035,floor_hands=1.)
PRONE_BACK=pose(pelvis=(0,-.02,-.845),pelvis_rot=(-88,0,0),spine=(0,0,0),chest=(0,0,0),head=(-14,0,-16),footL=(.19,-.75,.11),footR=(-.23,-.73,.11),handL=(.44,.43,.04),handR=(-.43,.36,.04),gripL=.12,gripR=.4,foot_pitchL=-20,foot_pitchR=-15,blade=.035,floor_hands=1.)
DEATH_FRONT=PRONE_FRONT.copy(); DEATH_FRONT.update(handL=(.46,-.39,.04),handR=(-.40,-.32,.055),head=(18,0,38),gripL=.02,gripR=.18)
DEATH_BACK=PRONE_BACK.copy(); DEATH_BACK.update(footL=(.25,-.54,.11),footR=(-.26,-.77,.11),handL=(.49,.29,.04),handR=(-.38,.42,.055),head=(-14,0,-29),gripL=.04,gripR=.22)
KNEEL=pose(pelvis=(0,-.02,-.42),chest=(12,0,0),head=(-6,0,0),footL=(.18,-.31,.11),footR=(-.17,.46,.11),handL=(.30,-.33,.65),handR=(-.26,-.22,.94),gripL=.1,gripR=.25)
SLEEP=pose(pelvis=(.03,.04,-.804),pelvis_rot=(67,34,0),spine=(12,0,0),chest=(13,0,0),head=(16,0,18),footL=(.22,.44,.139),footR=(-.04,.41,.129),handL=(.10,-.49,.159),handR=(-.09,-.48,.149),gripL=.2,gripR=.24,blinkL=1,blinkR=1,blade=.035)

DURATIONS={
'idle_relaxed':3.6,'idle_combat':2.8,'idle_wounded':3.4,'sprint_f':.6,'start_f':.7,'stop_f':.7,
'turn_l90':.8,'turn_r90':.8,'pivot_l180':.8,'pivot_r180':.8,'jump_start':.6,'jump_air':.8,'jump_land':.7,'fall':.9,'land_heavy':1.,
'dash_f':.5,'dash_b':.5,'dash_l':.5,'dash_r':.5,'blink_out':.4,'blink_in':.4,
'melee_1':.8,'melee_2':.9,'melee_3':1.1,'ranged_fire':.3,'ranged_burst':.6,'reload':2.3,
'cast_directional':.9,'cast_ground':1.2,'cast_self':.9,'channel_start':.6,'channel_loop':1.6,'channel_end':.6,'channel_interrupt':.4,
'charge_start':.8,'charge_hold':1.2,'charge_release':.8,'charge_cancel':.5,'deploy':1.8,'uplink_start':.8,'uplink_loop':1.6,'uplink_end':.7,'uplink_cancel':.5,
'hit_f':.4,'hit_b':.4,'hit_l':.4,'hit_r':.4,'stun_start':.7,'stun_loop':1.8,'stun_end':1.,'knockback':.8,'knockup_start':.6,'knockup_air':.8,
'knockdown_front':1.1,'knockdown_back':1.2,'prone_front':2.,'prone_back':2.,'getup_front':2.2,'getup_back':2.5,
'sleep_start':2.4,'sleep_loop':2.8,'sleep_end':2.6,'death_front':2.1,'death_back':2.4,'respawn':2.4,'greet':2.2,'victory':2.8,'defeat':2.5,'dialogue':15.}
DIRECTIONS={'f':(0,-1),'fl':(.707106781,-.707106781),'l':(1,0),'bl':(.707106781,.707106781),'b':(0,1),'br':(-.707106781,.707106781),'r':(-1,0),'fr':(-.707106781,-.707106781)}

def gait(id,t,duration):
    sprint=id=='sprint_f'; running=id.startswith('run_') or sprint
    direction=DIRECTIONS[id.split('_')[-1]]; dx,dy=direction
    speed=6.5 if sprint else 4. if running else 1.5
    stance=.21 if sprint else .28 if running else .57
    # Strafe gaits shorten contact and use distinct staggered foot lanes.
    if abs(dx)>.8: stance*=.78
    p=pose(pelvis=(.015*math.sin(TAU*t),0,-.085 + (.024 if running else .013)*math.cos(4*math.pi*t)),
           chest=(18 if sprint else 10 if running else 3,0,3*math.sin(TAU*t)),spine=(2,0,-3*math.sin(TAU*t)))
    for side,phase in [('L',t%1),('R',(t+.5)%1)]:
        s=1 if side=='L' else -1
        half=speed*duration*stance*.5
        if phase<stance:
            along=half-speed*duration*phase
            z=.11
            q=phase/stance
            pitch=lerp(-7,0,q/.12) if q<.12 else lerp(0,13,(q-.8)/.2) if q>.8 else 0.
        else:
            q=(phase-stance)/(1-stance)
            along=lerp(-half,half,smooth(q)); z=.11+(.22 if sprint else .16 if running else .075)*math.sin(math.pi*q)
            pitch=-17*math.sin(math.pi*q)
        p['foot'+side]=(s*.145+dx*along,dy*along+s*.065*abs(dx),z)
        p['foot_pitch'+side]=pitch
        swing=math.sin(TAU*(t+(0 if side=='L' else .5)))
        p['hand'+side]=(s*(.31+.025*abs(dx)), -.12+dy*(.16 if running else .10)*swing,
                        (1.34 if sprint else 1.25 if running else 1.05)+(.09 if running else .035)*swing)
        p['grip'+side]=.72 if sprint else .48 if running else .2
    p['head']=(-7 if sprint else -3,0,-2*math.sin(TAU*t))
    return p

def motion(id,t,duration):
    """Pose at normalized phase. Contact targets and acting beats are authored here."""
    s=math.sin(TAU*t); c=math.cos(TAU*t)
    if id.startswith(('walk_','run_')) or id=='sprint_f': return gait(id,t,duration)
    if id.startswith('aim_'):
        _,pitch_name,yaw_name=id.split('_'); pitch={'down':-35,'level':0,'up':35}[pitch_name]; yaw={'left':-60,'center':0,'right':60}[yaw_name]
        a=math.radians(yaw); e=math.radians(pitch)
        # Positive engine yaw means character-right; -Y source forward.
        direction=Vector((-math.sin(a)*math.cos(e),-math.cos(a)*math.cos(e),math.sin(e)))
        p=AIM.copy(); origin=Vector((-.18,0,1.40)); p['handR']=tuple(origin+direction*.59)
        p['chest']=(3-pitch*.20,0,-yaw*.38); p['head']=(-pitch*.30,0,-yaw*.40); return p
    if id=='idle_relaxed': return pose(pelvis=(.009*s,0,.003*(1-c)),chest=(1.1*s,0,.7*s),head=(-1+1.8*s,0,3*s),handL=(.34,-.1,1.06+.008*s),handR=(-.34,-.13,1.1+.008*s),secondary=2*s)
    if id=='idle_combat':
        p=READY.copy(); p['pelvis']=(.008*s,0,-.025+.005*(1-c)); p['chest']=(5+1.5*s,0,1.5*s); p['head']=(-3,0,4*s);return p
    if id=='idle_wounded': return pose(pelvis=(.015,.03,-.10+.004*s),chest=(17+2*s,0,-7),head=(-7,0,9),handL=(.08,-.25,1.15),handR=(-.31,-.12,.99),footL=(.14,-.10,.11),footR=(-.14,.10,.11),brow=-.5,squint=.3)
    if id=='start_f': return timeline(t,[(0,READY),(.3,pose(pelvis=(0,.06,-.13),chest=(15,0,0),handL=(.31,-.28,1.28),handR=(-.31,.03,1.11))), (1,gait('run_f',.15,.7))])
    if id=='stop_f': return timeline(t,[(0,gait('run_f',.35,.7)),(.4,pose(pelvis=(0,.10,-.14),chest=(-9,0,0),footL=(.16,-.33,.11),footR=(-.16,.12,.11),handL=(.36,-.18,1.17),handR=(-.33,-.28,1.28))), (1,READY)])
    if id.startswith(('turn_','pivot_')):
        sign=1 if '_l' in id else -1; degrees=180 if 'pivot' in id else 90; yaw=sign*degrees*smooth(t)
        p=READY.copy(); p['pelvis']=(0,0,-.025-.045*math.sin(math.pi*t));p['pelvis_rot']=(0,0,yaw);p['chest']=(5,0,sign*18*math.sin(math.pi*t));p['head']=(0,0,sign*15*math.sin(math.pi*t))
        for side in ('L','R'):
            phase=clamp((t-(0 if (side=='L')==(sign>0) else .42))/.58); a=math.radians(sign*degrees*smooth(phase)); v=Vector(READY['foot'+side]); v=Matrix.Rotation(a,3,'Z')@v;v.z+=.095*math.sin(math.pi*phase);p['foot'+side]=tuple(v);p['foot_yaw'+side]=sign*degrees*smooth(phase)
            h=Matrix.Rotation(math.radians(yaw),3,'Z')@Vector(READY['hand'+side]);p['hand'+side]=tuple(h)
        return p
    if id=='jump_start': return timeline(t,[(0,READY),(.40,pose(pelvis=(0,.01,-.24),chest=(22,0,0),handL=(.31,.13,.97),handR=(-.31,.13,.97))), (1,pose(pelvis=(0,0,.05),handL=(.27,-.23,1.70),handR=(-.27,-.23,1.68),footL=(.12,.04,.16),footR=(-.12,.04,.16),foot_pitchL=30,foot_pitchR=30))])
    if id=='jump_air': return pose(pelvis=(0,0,.035+.01*s),footL=(.13,.10,.34),footR=(-.13,.21,.29),handL=(.38,-.17,1.57+.02*s),handR=(-.37,-.20,1.55-.02*s),chest=(6,0,0),foot_pitchL=15,foot_pitchR=20)
    if id in ('jump_land','land_heavy'):
        heavy=id=='land_heavy'; crouch=pose(pelvis=(0,0,-(.33 if heavy else .20)),chest=(35 if heavy else 18,0,0),footL=(.18,-.06,.11),footR=(-.18,.04,.11),handL=(.38,-.35,.66 if heavy else 1.01),handR=(-.37,-.26,.86 if heavy else 1.01))
        return timeline(t,[(0,READY),(.23,crouch),(.48,crouch),(1,READY)])
    if id=='fall': return pose(pelvis=(0,0,.015*s),chest=(-9,0,0),head=(16,0,4*s),footL=(.16,.1,.17+.01*s),footR=(-.19,.14,.21-.01*s),handL=(.59,-.05,1.62+.03*s),handR=(-.56,-.07,1.65-.03*s),gripL=.02,gripR=.02)
    if id.startswith('dash_'):
        dx,dy=DIRECTIONS[id[-1]];w=math.sin(math.pi*t);p=READY.copy();p['pelvis']=(0,0,-.05-.12*w);p['chest']=(18*(-dy)*w,15*(-dx)*w,0);p['footL']=(.17+dx*.24*w,dy*.24*w,.11);p['footR']=(-.17-dx*.21*w,-dy*.21*w,.11);p['handL']=(.37,-.10+dy*.15*w,1.22);p['handR']=(-.34,-.19-dy*.14*w,1.21);return p
    if id in ('blink_out','blink_in'):
        q=t if id=='blink_out' else 1-t
        return mix(READY,pose(pelvis=(0,0,-.19),chest=(21,0,0),head=(-10,0,0),handL=(.06,-.3,1.3),handR=(-.06,-.28,1.34),gripL=.9,gripR=.9),q)
    if id.startswith('melee_'):
        n=int(id[-1]);wind=[(.38,-.19,1.54),(-.49,.18,1.42),(-.28,.05,1.85)][n-1];follow=[(-.50,-.38,.99),(.37,-.30,1.15),(-.18,-.58,.75)][n-1]
        prep=READY.copy();prep.update(handR=wind,chest=(2,0,[-32,32,-10][n-1]),handL=(.22,-.26,1.31),pelvis=(0,.025,-.085),gripR=.95)
        strike=READY.copy();strike.update(handR=follow,chest=([16,10,31][n-1],0,[33,-32,9][n-1]),pelvis=(0,-.06,-.12),footL=(.18,-.23,.11),footR=(-.18,.16,.11),gripR=.95)
        return timeline(t,[(0,READY),(.28,prep),(.47,strike),(.68,strike),(1,READY)])
    if id in ('ranged_fire','ranged_burst'):
        p=AIM.copy(); times=[.28] if id=='ranged_fire' else [.18,.45,.72]; recoil=sum(pulse(t,a,a+.18) for a in times)
        p['handR']=(-.16,-.60+.09*recoil,1.40+.045*recoil);p['chest']=(-4*recoil,0,-6);p['head']=(2*recoil,0,0);p['squint']=.2+.25*recoil;return p
    if id=='reload':
        hold=READY.copy();hold.update(handR=(-.05,-.34,1.24),handL=(.07,-.32,1.27),head=(19,0,-6),gripL=.75,gripR=.35)
        pull=hold.copy();pull.update(handL=(.15,-.46,1.23),cell=1.)
        seat=hold.copy();seat.update(cell=1.)
        return timeline(t,[(0,READY),(.18,hold),(.30,hold),(.43,pull),(.57,pull),(.73,seat),(.82,hold),(1,READY)])
    if id=='cast_directional':
        wind=READY.copy();wind.update(handR=(-.31,.06,1.45),handL=(.16,-.22,1.27),chest=(3,0,-22))
        release=AIM.copy();release.update(handR=(-.12,-.62,1.43),gripR=.05,chest=(10,0,12),smile=.15)
        return timeline(t,[(0,READY),(.34,wind),(.55,release),(.7,release),(1,READY)])
    if id=='cast_ground':
        low=KNEEL.copy();low.update(handR=(-.22,-.47,.26),head=(25,0,-12),handL=(.23,-.19,.99),gripR=0.)
        return timeline(t,[(0,READY),(.35,KNEEL),(.55,low),(.70,low),(1,READY)])
    if id=='cast_self':
        gather=READY.copy();gather.update(handL=(.07,-.22,1.30),handR=(-.07,-.23,1.3),chest=(11,0,0),gripL=.6,gripR=.6)
        release=READY.copy();release.update(handL=(.54,-.19,1.51),handR=(-.54,-.19,1.51),chest=(-7,0,0),head=(-8,0,0),gripL=0,gripR=0)
        return timeline(t,[(0,READY),(.33,gather),(.57,release),(.74,release),(1,READY)])
    if id.startswith('channel_'):
        if id=='channel_start':return mix(READY,CHANNEL,t)
        if id=='channel_loop':
            p=CHANNEL.copy();p['chest']=(8+1*s,0,0);p['head']=(-4,0,2*s);p['handR']=(-.22,-.56,1.38+.005*s);return p
        if id=='channel_end':return mix(CHANNEL,READY,t)
        shock=READY.copy();shock.update(chest=(-17,0,12),handL=(.36,-.24,1.5),handR=(-.38,-.25,1.55),head=(14,0,-9))
        return timeline(t,[(0,CHANNEL),(.35,shock),(1,READY)])
    if id.startswith('charge_'):
        if id=='charge_start':return mix(READY,CHARGE,t)
        if id=='charge_hold':
            p=CHARGE.copy();p['pelvis']=(.004*s,0,-.13+.008*s);p['chest']=(12+2*s,0,0);p['secondary']=4*s;return p
        if id=='charge_cancel':return mix(CHARGE,READY,t)
        release=CHANNEL.copy();release.update(handL=(.23,-.58,1.40),handR=(-.18,-.62,1.40),chest=(20,0,0),pelvis=(0,-.05,-.12),gripL=.0,gripR=.0)
        return timeline(t,[(0,CHARGE),(.32,release),(.49,release),(1,READY)])
    if id=='deploy':
        grab=READY.copy();grab.update(handL=(.18,.07,1.08),head=(15,0,12),gripL=.9)
        low=pose(pelvis=(0,.05,-.54),pelvis_rot=(60,0,0),spine=(12,0,0),chest=(12,0,0),head=(-25,0,12),footL=(.18,-.20,.11),footR=(-.17,.73,.11),handL=(.32,-.585,.1155),handR=(-.29,-.45,.155),gripL=.9,gripR=.08,beacon=1.,blade=.035)
        release=low.copy();release.update(gripL=.12,beacon=2.)
        leave=READY.copy();leave.update(beacon=2.)
        return timeline(t,[(0,READY),(.17,grab),(.25,grab),(.56,low),(.64,low),(.74,release),(1,leave)])
    if id.startswith('uplink_'):
        if id=='uplink_start':return mix(READY,UPLINK,t)
        if id=='uplink_loop':
            p=UPLINK.copy();p['handL']=(.05+.018*s,-.29,1.27+.007*c);p['head']=(15,0,-10+2*s);p['gripL']=.12+.06*(1-c);return p
        if id=='uplink_cancel':
            away=UPLINK.copy();away.update(handL=(.26,-.29,1.29),head=(0,0,20));return timeline(t,[(0,UPLINK),(.4,away),(1,READY)])
        cue=UPLINK.copy();cue.update(handL=(.17,-.20,1.51),head=(-3,0,0),smile=.5);return timeline(t,[(0,UPLINK),(.45,cue),(1,READY)])
    if id.startswith('hit_'):
        dx,dy=DIRECTIONS[id[-1]];w=pulse(t,0,.85);return pose(chest=(-dy*-14*w,dx*-14*w,dx*8*w),spine=(-dy*-6*w,dx*-5*w,0),head=(-dy*12*w,dx*10*w,0),handL=(.34,-.1,1.06),handR=(-.34,-.13,1.10))
    if id.startswith('stun_'):
        if id=='stun_start':return timeline(t,[(0,READY),(.25,pose(chest=(-18,0,12),head=(-18,5,9),handL=(.39,-.1,1.40),handR=(-.36,-.21,1.52))),(1,STUN)])
        if id=='stun_end':return timeline(t,[(0,STUN),(.6,pose(handR=(-.16,-.19,1.51),head=(7,0,-8))),(1,READY)])
        p=STUN.copy();p['chest']=(14+2*s,3*s,8+3*s);p['head']=(18+4*s,8,-10+5*s);return p
    if id=='knockback':return timeline(t,[(0,READY),(.25,pose(pelvis=(0,.08,-.13),chest=(-23,0,0),head=(-14,0,0),footL=(.17,-.19,.11),footR=(-.17,.18,.11),handL=(.46,-.17,1.44),handR=(-.42,-.19,1.44))),(.7,STUN),(1,READY)])
    if id=='knockup_start':return timeline(t,[(0,READY),(.2,pose(chest=(22,0,0),pelvis=(0,0,-.15))),(1,pose(chest=(-22,0,0),head=(-17,0,0),footL=(.17,.15,.31),footR=(-.19,.27,.26),handL=(.55,.10,1.61),handR=(-.52,.08,1.68)))])
    if id=='knockup_air':return pose(chest=(-22+4*s,0,8*s),head=(-17,0,7*s),footL=(.17,.15,.31+.025*s),footR=(-.19,.27,.26-.025*s),handL=(.55,.10,1.61+.03*s),handR=(-.52,.08,1.68-.03*s),gripL=.1,gripR=.1)
    if id.startswith(('knockdown_','death_')):
        front=id.endswith('front');fatal=id.startswith('death_');final=(DEATH_FRONT if front else DEATH_BACK) if fatal else (PRONE_FRONT if front else PRONE_BACK)
        if front:
            catch=pose(pelvis=(0,-.08,-.35),pelvis_rot=(48,0,0),chest=(12,0,0),head=(-12,0,0),handL=(.31,-.68,.22),handR=(-.31,-.65,.24),footL=(.16,.24,.11),footR=(-.16,.20,.11),gripL=.02,gripR=.03)
            settle=final.copy();settle['pelvis']=(0,.04,-.75);settle['chest']=(-8,0,0)
            if fatal:
                recoil=pose(pelvis=(0,.07,-.075),chest=(-21,0,-15),head=(-16,0,9),handL=(.07,-.22,1.35),handR=(-.28,-.23,1.11),footL=(.17,-.15,.11),footR=(-.19,.08,.11))
                catch['handL']=(.36,-.54,.13);catch['handR']=(-.27,-.58,.20);catch['pelvis_rot']=(62,0,-9);catch['floor_hands']=1.;catch['blade']=.035
                return timeline(t,[(0,READY),(.17,recoil),(.33,recoil),(.58,catch),(.78,final),(1,final)])
            return timeline(t,[(0,READY),(.16,pose(chest=(-14,0,0),head=(-12,0,0),handL=(.24,-.2,1.2),handR=(-.21,-.21,1.2))),(.45,catch),(.67,settle),(.84,final),(1,final)])
        slump=pose(pelvis=(0,.06,-.46),pelvis_rot=(-38,0,0),chest=(24,0,0),head=(17,0,-12),footL=(.21,-.28,.11),footR=(-.17,-.34,.11),handL=(.43,.30,.31),handR=(-.41,.26,.37))
        if fatal:
            impact=pose(pelvis=(.03,0,-.11),chest=(29,-10,-15),head=(28,0,-12),handL=(.23,-.38,1.18),handR=(-.43,-.25,1.41),footL=(.21,-.13,.11),footR=(-.17,.12,.11))
            slump['pelvis_rot']=(-52,-8,12);slump['handL']=(.44,.30,.22);slump['handR']=(-.32,.42,.23)
            return timeline(t,[(0,READY),(.15,impact),(.29,impact),(.56,slump),(.81,final),(1,final)])
        return timeline(t,[(0,READY),(.17,pose(chest=(18,0,-6),head=(22,0,8))),(.45,slump),(.72,final),(1,final)])
    if id in ('dead_front','dead_back'):return (DEATH_FRONT if id.endswith('front') else DEATH_BACK).copy()
    if id.startswith('prone_'):
        p=(PRONE_FRONT if id.endswith('front') else PRONE_BACK).copy();x,y,z=p['pelvis'];p['pelvis']=(x,y,z+.003*(1-c));return p
    if id in ('getup_front','getup_back'):
        if id.endswith('front'):
            support=pose(pelvis=(0,.05,-.58),pelvis_rot=(60,0,0),spine=(12,0,0),chest=(12,0,0),head=(-25,0,0),handL=(.28,-.44,.035),handR=(-.28,-.44,.055),footL=(.18,.73,.11),footR=(-.18,.73,.11),gripL=.02,gripR=.02,blade=.035,floor_hands=1.)
            return timeline(t,[(0,PRONE_FRONT),(.25,support),(.38,support),(.64,KNEEL),(.80,pose(pelvis=(0,0,-.22),chest=(25,0,0),footL=(.17,-.24,.11),footR=(-.17,.16,.11))),(1,READY)])
        sit=pose(pelvis=(0,.05,-.72),pelvis_rot=(-60,0,0),chest=(12,0,0),head=(12,0,0),footL=(.21,-.45,.11),footR=(-.20,-.40,.11),handL=(.33,.47,.04),handR=(-.33,.47,.055),gripL=.01,gripR=.01,blade=.035,floor_hands=1.)
        return timeline(t,[(0,PRONE_BACK),(.30,sit),(.40,sit),(.67,KNEEL),(.82,pose(pelvis=(0,0,-.20),chest=(20,0,0),footL=(.17,-.18,.11),footR=(-.17,.12,.11))),(1,READY)])
    if id.startswith('sleep_'):
        if id=='sleep_start':return timeline(t,[(0,READY),(.35,KNEEL),(.65,mix(KNEEL,SLEEP,.65)),(1,SLEEP)])
        if id=='sleep_end':return timeline(t,[(0,SLEEP),(.2,mix(SLEEP,PRONE_FRONT,.25)),(.54,KNEEL),(1,READY)])
        p=SLEEP.copy();p['chest']=(13+1.5*s,0,0);return p
    if id=='respawn':
        start=KNEEL.copy();start.update(handL=(.06,-.25,.94),handR=(-.07,-.26,.95),head=(24,0,0),blinkL=1,blinkR=1)
        activate=READY.copy();activate.update(handL=(.47,-.10,1.45),handR=(-.47,-.10,1.45),chest=(-6,0,0),head=(-9,0,0),gripL=0,gripR=0)
        return timeline(t,[(0,start),(.25,start),(.65,activate),(1,READY)])
    if id=='greet':
        wave=pose(handL=(.45,-.17,1.69),handR=(-.34,-.14,1.10),gripL=.01,smile=.65,head=(-2,0,12),hand_rollL=24*math.sin(6*math.pi*t))
        return timeline(t,[(0,pose()),(.23,wave),(.7,wave),(1,pose(smile=.25))])
    if id=='victory':
        salute=pose(pelvis=(.025,0,.005),chest=(-6,0,5),handL=(.31,-.11,1.91),handR=(-.22,-.22,1.36),gripL=.95,gripR=.65,smile=.95,head=(-10,0,7))
        return timeline(t,[(0,READY),(.25,pose(pelvis=(0,0,-.08),handL=(.28,-.21,1.31),handR=(-.30,-.2,1.26))),(.50,salute),(.75,salute),(1,pose(smile=.6))])
    if id=='defeat':
        slump=pose(pelvis=(0,.02,-.07),chest=(15,0,0),head=(28,0,-8),handL=(.26,-.03,.99),handR=(-.28,-.06,.97),brow=-.65,smile=-.65,gripL=.03,gripR=.02)
        return timeline(t,[(0,READY),(.4,slump),(.75,slump),(1,mix(slump,pose(),.4))])
    if id=='dialogue':
        p=pose(pelvis=(.01*math.sin(3*math.pi*t),0,.003*s),head=(2*math.sin(5*math.pi*t),0,9*math.sin(3*math.pi*t)),brow=-.25 if t<.42 else .2,smile=.0 if t<.42 else .45)
        beat=pulse(t,.10,.31);assure=pulse(t,.44,.65);point=pulse(t,.73,.94)
        p['handL']=(.34-.18*beat,-.10-.24*beat,1.06+.30*beat+.20*assure)
        p['handR']=(-.34+.19*assure,-.13-.22*assure-.24*point,1.1+.21*assure+.27*point)
        p['gripR']=.20+.45*point;p['chest']=(2*beat-2*assure,0,3*math.sin(2*math.pi*t));return p
    raise ValueError('Unauthored motion '+id)


def world_rotate(rig,name,angles):
    if name not in rig.pose.bones:return
    pb=rig.pose.bones[name];q=Euler(tuple(math.radians(a) for a in angles),'XYZ').to_quaternion();rest=pb.bone.matrix_local.to_quaternion()
    pb.rotation_mode='QUATERNION';pb.rotation_quaternion=rest.inverted()@q@rest

def set_world_matrix(pb,matrix,parent_matrix=None):
    if pb.parent:
        pm=parent_matrix if parent_matrix is not None else pb.parent.matrix
        local_rest=pb.parent.bone.matrix_local.inverted()@pb.bone.matrix_local
        pb.matrix_basis=local_rest.inverted()@pm.inverted()@matrix
    else:pb.matrix_basis=pb.bone.matrix_local.inverted()@matrix
    return matrix

def orient_bone(pb,head,tail,parent_matrix=None):
    rest=pb.bone.matrix_local.to_quaternion();rest_dir=pb.bone.tail_local-pb.bone.head_local;direction=tail-head
    if direction.length<1e-7:return
    q=rest_dir.normalized().rotation_difference(direction.normalized())@rest
    return set_world_matrix(pb,Matrix.Translation(head)@q.to_matrix().to_4x4(),parent_matrix)

def limb(rig,upper,lower,target,pole,min_joint_z=None):
    """Stable analytic two-bone solve, bend plane defined by an explicit world pole."""
    a=rig.pose.bones[upper];b=rig.pose.bones[lower];start=a.head.copy();target=Vector(target);pole=Vector(pole)
    l1=a.bone.length;l2=b.bone.length;delta=target-start;distance=clamp(delta.length,abs(l1-l2)+.0001,l1+l2-.000001);axis=delta.normalized()
    projection=pole-start;normal=projection-axis*projection.dot(axis)
    if normal.length<1e-5:normal=Vector((0,-1,0))
    normal.normalize();d=(l1*l1-l2*l2+distance*distance)/(2*distance);h=math.sqrt(max(0,l1*l1-d*d));center=start+axis*d
    if min_joint_z is not None and center.z+normal.z*h<min_joint_z and h>1e-6:
        up=Vector((0,0,1))-axis*axis.z;vertical_capacity=up.length
        if vertical_capacity>1e-5:
            up.normalize();side=axis.cross(up).normalized();fraction=clamp((min_joint_z-center.z)/(h*vertical_capacity),-1,1)
            orient=1 if normal.dot(side)>0 else -1
            if abs(normal.dot(side))<.02:orient=1 if side.x*(1 if upper.endswith('.L') else -1)>0 else -1
            normal=up*fraction+side*(orient*math.sqrt(max(0,1-fraction*fraction)))
    joint=center+normal*h;end=start+axis*distance
    am=orient_bone(a,start,joint);bm=orient_bone(b,joint,end,am)
    bpy.context.view_layer.update()
    return end

def reset(rig):
    for pb in rig.pose.bones:
        pb.location=(0,0,0)
        if pb.bone.use_deform:pb.rotation_mode='QUATERNION'
        pb.rotation_quaternion=(1,0,0,0);pb.rotation_euler=(0,0,0);pb.scale=(1,1,1)


def deploy_prop(t):
    keys=[(.24,Vector((.16,.005,.965))),(.36,Vector((.23,-.15,.87))),(.52,Vector((.30,-.58,.13))),(.60,Vector((.30,-.65,.0005)))]
    if t<=keys[0][0]:return keys[0][1].copy()
    for (a,p),(b,q) in zip(keys,keys[1:]):
        if t<=b:return p.lerp(q,smooth((t-a)/(b-a)))
    return keys[-1][1].copy()

def finger_quaternion(side,name,j,amount):
    sign=-1 if side=='L' else 1
    if name=='thumb':return Euler((sign*.50*amount if j==1 else 0.,0.,sign*([.45,.80,.65][j-1])*amount),'XYZ').to_quaternion()
    return Quaternion((0,0,1),sign*([.9,1.2,.9][j-1])*amount)


def apply_pose(rig,p,id,t):
    reset(rig)
    root=Vector((0,0,0))
    if id.startswith('dash_'):
        dx,dy=DIRECTIONS[id[-1]];root=Vector((dx*2*smooth(t),dy*2*smooth(t),0));rig.pose.bones['root'].location=rig.pose.bones['root'].bone.matrix_local.to_quaternion().inverted()@root
    for side in ('L','R'):
        # Heel/toe roll rotates the ankle around its planted sole pivot.
        pitch=math.radians(p['foot_pitch'+side]);yaw=math.radians(p['foot_yaw'+side]);x,y,z=p['foot'+side]
        pivot=.23 if pitch>=0 else -.045
        dy=pivot*math.cos(pitch)-.11*math.sin(pitch)-pivot
        dz=pivot*math.sin(pitch)+.11*math.cos(pitch)-.11
        p['foot'+side]=(x-dy*math.sin(yaw),y+dy*math.cos(yaw),z+dz)
    if id.startswith(('walk_','run_')) or id=='sprint_f':
        px,py,pz=p['pelvis']
        for side in ('L','R'):
            sign=1 if side=='L' else -1;fx,fy,fz=p['foot'+side]
            reach=rig.pose.bones['thigh.'+side].bone.length+rig.pose.bones['shin.'+side].bone.length-.005
            horizontal=(fx-sign*.09-px)**2+(fy-py)**2
            if horizontal<reach*reach:pz=min(pz,fz+math.sqrt(reach*reach-horizontal)-.94)
        p['pelvis']=(px,py,pz)
    pelvis=rig.pose.bones['pelvis'];rest=pelvis.bone.matrix_local.to_quaternion();pelvis.location=rest.inverted()@Vector(p['pelvis'])
    world_rotate(rig,'pelvis',p['pelvis_rot']);world_rotate(rig,'spine_01',tuple(v*.6 for v in p['spine']));world_rotate(rig,'spine_02',tuple(v*.4 for v in p['spine']));world_rotate(rig,'chest',p['chest']);world_rotate(rig,'neck',tuple(v*.35 for v in p['head']));world_rotate(rig,'head',tuple(v*.65 for v in p['head']))
    bpy.context.view_layer.update()
    for side in ('R','L'):
        sign=1 if side=='L' else -1;target=Vector(p['foot'+side])+root
        # The pole follows body yaw, while world feet retain explicit contacts.
        pole=Vector((sign*.15,-1.0,.50));pole=Matrix.Rotation(math.radians(p['pelvis_rot'][2]),3,'Z')@pole+root
        target=limb(rig,'thigh.'+side,'shin.'+side,target,pole,min_joint_z=.075)
        foot=rig.pose.bones.get('foot.'+side)
        if foot:
            restq=foot.bone.matrix_local.to_quaternion();q=Euler((math.radians(p['foot_pitch'+side]),0,math.radians(p['foot_yaw'+side]))).to_quaternion();set_world_matrix(foot,Matrix.Translation(target)@(q@restq).to_matrix().to_4x4())
        bpy.context.view_layer.update()
        target=Vector(p['hand'+side])+root
        if id.startswith('aim_') and side=='R':
            _,pn,yn=id.split('_');a=math.radians({'left':-60,'center':0,'right':60}[yn]);e=math.radians({'down':-35,'level':0,'up':35}[pn])
            direction=Vector((-math.sin(a)*math.cos(e),-math.cos(a)*math.cos(e),math.sin(e)))
            shoulder=rig.pose.bones['upper_arm.R'].head.copy()
            reach=rig.pose.bones['upper_arm.R'].bone.length+rig.pose.bones['forearm.R'].bone.length-.000001
            target=shoulder+direction*reach
        if id=='deploy' and side=='L':
            contact=deploy_prop(t)+DEPLOY_GRIP_OFFSET
            weight=smooth(t/.17)*(1-smooth((t-.64)/.12))
            target=target.lerp(contact,weight)
            target.z+=.18*math.sin(math.pi*clamp(t/.17))
            target.z+=.12*smooth((t-.60)/.10)*(1-smooth((t-.84)/.14))
        if id=='reload' and side=='L':
            socket=rig.pose.bones['cell'].head.copy()
            pull=.14*smooth((t-.30)/.13)*(1-smooth((t-.57)/.16))
            contact=socket+Vector((.03+pull,-.035-pull*.35,.02))
            w=smooth(t/.18)*(1-smooth((t-.82)/.18))
            target=target.lerp(contact,w)
        pole=Vector((sign*.80,.13,1.0))+root
        pole=pole.lerp(Vector((sign*.72,-.16,.18))+root,p['floor_hands'])
        end=limb(rig,'upper_arm.'+side,'forearm.'+side,target,pole)
        bpy.context.view_layer.update()
        if p['floor_hands']>0:
            fore=rig.pose.bones['forearm.'+side];y=(fore.tail-fore.head).normalized();z=Vector((0,0,1));z=(z-y*z.dot(y)).normalized();x=y.cross(z).normalized()
            q=Matrix((x,y,z)).transposed().to_quaternion();q=fore.matrix.to_quaternion().slerp(q,p['floor_hands'])
            set_world_matrix(fore,Matrix.Translation(fore.head)@q.to_matrix().to_4x4());bpy.context.view_layer.update()
        # Keep wrists aligned with forearms. A gentle palm roll supports waving.
        world_rotate(rig,'hand.'+side,(0,p['hand_roll'+side],0))
        if id=='deploy' and side=='L':
            hand=rig.pose.bones['hand.L'];bpy.context.view_layer.update()
            q=Matrix(((0,0,1),(-1,0,0),(0,-1,0))).to_quaternion()
            weight=smooth(t/.17)*(1-smooth((t-.64)/.16));q=hand.matrix.to_quaternion().slerp(q,weight)
            set_world_matrix(hand,Matrix.Translation(hand.head)@q.to_matrix().to_4x4())
        if p['floor_hands']>0:
            hand=rig.pose.bones['hand.'+side];bpy.context.view_layer.update()
            flat=Matrix(((0,0,sign),(0,-1,0),(sign,0,0))).to_quaternion()
            q=hand.matrix.to_quaternion().slerp(flat,p['floor_hands'])
            set_world_matrix(hand,Matrix.Translation(hand.head)@q.to_matrix().to_4x4())
        for name in ('thumb','index','middle','ring','pinky'):
            for j in (1,2,3):
                bn=f'{name}_{j:02d}.{side}'
                if bn not in rig.pose.bones:bn=f'{name}.{j:02d}.{side}'
                if bn in rig.pose.bones:rig.pose.bones[bn].rotation_quaternion=finger_quaternion(side,name,j,p['grip'+side])
        if id=='deploy' and side=='L':
            bpy.context.view_layer.update()
            thumbs=[rig.pose.bones[f'thumb.{j:02d}.L'] for j in (1,2,3)]
            original=[b.rotation_quaternion.copy() for b in thumbs]
            hand=rig.pose.bones['hand.L'];grip_q=Matrix(((0,0,1),(-1,0,0),(0,-1,0))).to_quaternion()
            delta=hand.matrix.to_quaternion()@grip_q.inverted()
            tip=hand.head+delta@(DEPLOY_THUMB_TARGET-DEPLOY_GRIP_OFFSET)
            pole=hand.head+delta@(Vector((-.075,.065,.105))-DEPLOY_GRIP_OFFSET)
            end=limb(rig,'thumb.01.L','thumb.02.L',tip+delta@Vector((0,thumbs[2].bone.length,0)),pole)
            orient_bone(thumbs[2],end,tip);bpy.context.view_layer.update()
            weight=smooth((t-.08)/.08)*(1-smooth((t-.64)/.12))
            for b,q in zip(thumbs,original):
                b.rotation_quaternion=q.slerp(b.rotation_quaternion,weight);b.location=(0,0,0)
    if 'blade_base' in rig.pose.bones:rig.pose.bones['blade_base'].scale=(p['blade'],)*3
    if 'secondary_01' in rig.pose.bones:world_rotate(rig,'secondary_01',(p['secondary']+3*math.sin(TAU*t),0,0))
    if 'cable.01' in rig.pose.bones:world_rotate(rig,'cable.01',(p['secondary']+3*math.sin(TAU*t),0,0))
    if 'cable.02' in rig.pose.bones:world_rotate(rig,'cable.02',(p['secondary']*.5+2*math.sin(TAU*t-.5),0,0))
    if id=='dialogue':
        world_rotate(rig,'eye.L',(1.8*math.sin(5*math.pi*t),0,5*math.sin(3*math.pi*t)))
        world_rotate(rig,'eye.R',(1.8*math.sin(5*math.pi*t),0,4.8*math.sin(3*math.pi*t)))
    bpy.context.view_layer.update()
    # Manipulated props carry evaluated transform curves, independent from runtime reattachment.
    if 'cell' in rig.pose.bones and id=='reload' and .29<=t<=.76:
        h=rig.pose.bones['hand.L'];m=rig.pose.bones['cell'].matrix.copy();m.translation=h.head+Vector((-.03,.035,-.02));set_world_matrix(rig.pose.bones['cell'],m)
    if 'beacon' in rig.pose.bones and id=='deploy' and t>=.24:
        # The hand and upright beacon share one continuous trajectory through release.
        rest=rig.pose.bones['beacon'].bone.matrix_local.to_quaternion()
        set_world_matrix(rig.pose.bones['beacon'],Matrix.Translation(deploy_prop(t))@rest.to_matrix().to_4x4())
    bpy.context.view_layer.update()


def face_values(p,id,t,duration,alignment):
    v={'blink.L':p['blinkL'],'blink.R':p['blinkR'],'squint.L':p['squint'],'squint.R':p['squint']*.85,'jaw_open':p['jaw'],
       'smile.L':max(0,p['smile']),'smile.R':max(0,p['smile'])*.9,'frown.L':max(0,-p['smile']),'frown.R':max(0,-p['smile']),
       'brow_up.L':max(0,p['brow']),'brow_up.R':max(0,p['brow'])*.7,'brow_down.L':max(0,-p['brow']),'brow_down.R':max(0,-p['brow'])*.8,
       'cheek.L':max(0,p['smile'])*.4,'cheek.R':max(0,p['smile'])*.35}
    for side in ('L','R'):
        v['shoulder_raise.'+side]=clamp((p['hand'+side][2]-1.45)/.40)
        v['hip_flex.'+side]=clamp(-p['pelvis'][2]/.40)
        v['wrist_flex.'+side]=clamp(abs(p['hand_roll'+side])/35.)
    if id=='dialogue':
        sec=t*duration
        for a in (1.1,4.2,7.8,11.6,14.2):
            blink=pulse(sec,a,a+.17);v['blink.L']=max(v['blink.L'],blink);v['blink.R']=max(v['blink.R'],pulse(sec,a+.015,a+.185))
        mapping={'lip_close':'viseme_MBP','labiodental':'viseme_FV','open_vowel':'viseme_AA','wide_vowel':'viseme_EE','rounded_vowel':'viseme_OH','tongue_teeth':'viseme_TH','consonant':'viseme_L'}
        for event in alignment.get('visemes',[]):
            start=event['start'];end=event['end'];name=event.get('name',event.get('viseme','consonant'))
            if start-.045<=sec<=end+.055:
                w=min(smooth((sec-start+.045)/.055),smooth((end+.055-sec)/.075))*event.get('value',1.)
                key=mapping.get(name,name)
                phoneme=next((x['phoneme'].lower().strip("'") for x in alignment.get('phonemes',[]) if abs(x['start']-start)<.001 and x.get('viseme')==name),'')
                if name=='rounded_vowel' and phoneme in ('u','u:','U'.lower()):key='viseme_OO'
                if name=='tongue_teeth' and phoneme=='l':key='viseme_L'
                if key=='viseme_MBP' and start<=sec<=end:w=1.
                v[key]=max(v.get(key,0),w)
        # Visemes already contain their jaw/width/pucker/closure deformation.
        closure=v.get('viseme_MBP',0)
        for key in tuple(v):
            if key.startswith('viseme_') and key!='viseme_MBP':v[key]*=(1-closure)**2
        total=sum(value for key,value in v.items() if key.startswith('viseme_'))
        if total>1:
            for key in tuple(v):
                if key.startswith('viseme_'):v[key]/=total
        v['jaw_open']=0.;v['lip_close']=0.;v['mouth_wide']=0.;v['pucker']=0.
    return v


def events(id,duration):
    e=[]
    def add(name,t):e.append({'name':name,'time':round(t*duration,6),'frame':round(t*duration*FPS)+1})
    if id.startswith(('walk_','run_')) or id=='sprint_f':add('foot_contact_L',0);add('foot_contact_R',.5)
    if id.startswith('melee_'):add('blade_extend',.12);add('melee_window_open',.36);add('melee_contact',.43);add('melee_window_close',.52);add('recovery',.68);add('blade_retract',.88)
    if id=='ranged_fire':add('muzzle_fire',.28)
    if id=='ranged_burst':
        for i,t in enumerate((.18,.45,.72)):add('muzzle_fire_'+str(i+1),t)
    if id=='reload':add('cell_grip',.29);add('cell_extract',.38);add('cell_insert',.73);add('cell_release',.77);add('reload_complete',.88)
    if id=='deploy':add('beacon_grip',.24);add('beacon_release',.64);add('beacon_activate',.72)
    if id.startswith('cast_'):add('cast_release',.55)
    if id.startswith(('channel_','charge_','uplink_')):add(id,0);add(id+'_complete',1)
    if id=='jump_start':add('takeoff',.87)
    if id in ('jump_land','land_heavy'):add('foot_contact_L',.08);add('foot_contact_R',.10)
    if id=='blink_out':add('blink_teleport',.94)
    if id=='blink_in':add('blink_visible',.06);add('foot_contact_L',.70);add('foot_contact_R',.70)
    if id.startswith('death_'):add('death_ground_contact',.69);add('death_settled',.84)
    if id.startswith('knockdown_'):add('body_ground_contact',.70)
    if id.startswith('getup_'):add('support_hand_contact',.22);add('support_hand_release',.38 if id.endswith('front') else .40);add('standing',.95)
    return e


def action_curves(action):
    try:return action.fcurves
    except AttributeError:
        curves=[]
        for layer in action.layers:
            for strip in layer.strips:
                if strip.type=='KEYFRAME':
                    for bag in strip.channelbags:curves.extend(bag.fcurves)
        return curves


def create_animations(rig, face_obj=None, project_root=None, only_ids=None):
    root=Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    csv_path=root/'source/required_animations.csv'
    if not csv_path.exists():csv_path=root.parent/'required_animations.csv'
    rows=list(csv.DictReader(csv_path.open()))
    if only_ids:rows=[r for r in rows if r['id'] in only_ids]
    ap=root/'source/audio/dialogue_alignment.json';alignment=json.loads(ap.read_text()) if ap.exists() else {}
    if alignment.get('duration'):DURATIONS['dialogue']=math.ceil(alignment['duration']*FPS)/FPS + 2/FPS
    face_obj=face_obj or bpy.data.objects.get('Operative_LOD0')
    shapes=face_obj.data.shape_keys if face_obj and face_obj.type=='MESH' else None
    scene=bpy.context.scene;scene.render.fps=FPS;rig.animation_data_create()
    # Analytic solves record FK result; animator can match into live IK controls later.
    constraints=[(c,c.mute) for pb in rig.pose.bones for c in pb.constraints]
    for c,_ in constraints:c.mute=True
    manifest=[];face_export={};checks={};source_mats={}
    if only_ids:
        manifest=[m for m in json.loads((root/'docs/animation_manifest.json').read_text())['animations'] if m['id'] not in only_ids]
        face_export=json.loads((root/'docs/facial_animation_curves.json').read_text())['clips']
        checks=json.loads((root/'docs/animation_validation.json').read_text())['clips']
    for idx,row in enumerate(rows):
        id=row['id'];static=row['form']=='pose';duration=0 if static else DURATIONS.get(id,.8 if id.startswith('walk_') else .7)
        intervals=1 if static else round(duration*FPS);duration=intervals/FPS
        if id in bpy.data.actions:bpy.data.actions.remove(bpy.data.actions[id])
        if 'EDIT__'+id in bpy.data.actions:bpy.data.actions.remove(bpy.data.actions['EDIT__'+id])
        action=bpy.data.actions.new('EDIT__'+id);action.use_fake_user=True;rig.animation_data.action=action
        action['authorship']='Procedurally authored contact paths and acting poses; see animations.py';action['clip_id']=id
        face_action=None
        if shapes:
            shapes.animation_data_create()
            if 'FACE__'+id in bpy.data.actions:bpy.data.actions.remove(bpy.data.actions['FACE__'+id])
            face_action=bpy.data.actions.new('FACE__'+id);face_action.use_fake_user=True;shapes.animation_data.action=face_action
        face_samples=[];positions=[]
        for i in range(intervals+1):
            frame=i+1;t=0 if static else i/intervals;scene.frame_set(frame)
            p=motion(id,t,duration);apply_pose(rig,p,id,t)
            for pb in rig.pose.bones:
                if pb.name.startswith(('CTRL','ctrl','MCH','mch')):continue
                pb.keyframe_insert('location',frame=frame,group=pb.name);pb.keyframe_insert('rotation_quaternion',frame=frame,group=pb.name);pb.keyframe_insert('scale',frame=frame,group=pb.name)
            values=face_values(p,id,t,duration,alignment)
            if shapes:
                for key in shapes.key_blocks:
                    if key.name=='Basis':continue
                    key.value=values.get(key.name,0.);key.keyframe_insert('value',frame=frame,group='Facial articulation')
            face_samples.append({'time':i/FPS,'values':{k:round(v,4) for k,v in values.items() if v>.0001}})
            positions.append(tuple(rig.pose.bones['root'].matrix.translation))
            if i in (0,intervals):source_mats[(id,i)]=[list(pb.matrix) for pb in rig.pose.bones if pb.bone.use_deform]
        for fc in action_curves(action):
            for kp in fc.keyframe_points:kp.interpolation='LINEAR'
        if face_action:
            for fc in action_curves(face_action):
                for kp in fc.keyframe_points:kp.interpolation='LINEAR'
        baked=action.copy();baked.name=id;baked.use_fake_user=True;baked['baked']=True;baked['sample_rate']=FPS
        marks=events(id,duration)
        for mark in marks:
            marker=baked.pose_markers.new(mark['name']);marker.frame=mark['frame']
        layer='additive_upper' if row['form']=='additive' else 'upper_body' if id.startswith('aim_') or id in ('ranged_fire','ranged_burst','cast_directional') else 'full_body'
        nominal=650 if id=='sprint_f' else 400 if id.startswith('run_') else 150 if id.startswith('walk_') else 0
        entry='living';exit='living'
        if id.startswith('death_'):exit='dead_'+id.rsplit('_',1)[1]
        if id.startswith('getup_'):entry='prone_'+id.rsplit('_',1)[1]
        if id.endswith(('_loop','_hold')):entry=exit=id
        if id.endswith('_start') and id.split('_')[0] in ('channel','uplink','charge','stun','sleep'):exit=id.split('_')[0]+('_hold' if id.startswith('charge') else '_loop')
        entry={'id':id,'source_action':'EDIT__'+id,'baked_action':id,'face_action':'FACE__'+id,'exported_file':'export/animations/'+id+'.fbx','exported_take':'Scene','unreal_asset':'/Game/Operative/Animations/'+id,'frame_start':1,'frame_end':intervals+1,'frame_count':intervals+1,'sample_rate':FPS,'duration':duration,'static_pose':static,'loop':row['form']=='loop','form':row['form'],'root_motion_policy':row['root_movement'],'layer':layer,'nominal_speed_cm_s':nominal,'events':marks,'entry_state':entry,'exit_state':exit,'required_behavior':row['required_behavior']}
        if id.startswith('aim_'):
            entry['aim_yaw_degrees']={'left':-60,'center':0,'right':60}[id.rsplit('_',1)[1]];entry['aim_pitch_degrees']={'down':-35,'level':0,'up':35}[id.split('_')[1]]
        if id.startswith('dash_'):entry['root_displacement_m']=[round(v,6) for v in positions[-1]]
        manifest.append(entry);face_export[id]=face_samples
        disp=(Vector(positions[-1])-Vector(positions[0])).length
        checks[id]={'sample_count':intervals+1,'duration_seconds':duration,'root_displacement_m':round(disp,7),'authored':True}
        print(f'ANIMATION {idx+1:02d}/96 {id}: {intervals+1} frames',flush=True)
    # Restore animator rig behavior, with IK/FK switches still FK at their defaults.
    for c,mute in constraints:c.mute=mute
    rig.animation_data.action=bpy.data.actions['idle_relaxed'];scene.frame_start=1;scene.frame_end=109;scene.frame_set(1)
    if shapes:shapes.animation_data.action=bpy.data.actions['FACE__idle_relaxed']
    (root/'docs').mkdir(parents=True,exist_ok=True)
    (root/'docs/animation_manifest.json').write_text(json.dumps({'schema_version':1,'authoring':'Original procedural motion authored for the Operative','sample_rate':FPS,'units':'meters','source_forward':'-Y','source_up':'+Z','aim_sign_convention':'Yaw negative character left; pitch positive up; radians converted at application boundary','endpoint_policy':'Loops include duplicate last sample. Runtime uses [start,end). Static poses have identical frames 1 and 2.','animations':manifest},indent=2))
    (root/'docs/facial_animation_curves.json').write_text(json.dumps({'sample_rate':FPS,'clips':face_export},separators=(',',':')))
    (root/'docs/animation_validation.json').write_text(json.dumps({'inventory_count':len(manifest),'motion_count':sum(not a['static_pose'] for a in manifest),'static_count':sum(a['static_pose'] for a in manifest),'clips':checks},indent=2))
    return manifest

if __name__=='__main__':
    create_animations(bpy.data.objects['Operative_Rig'])


def create_deformation_tests(rig,face_obj=None,project_root=None):
    """Supplemental editable rig stress poses, separate from the finite inventory."""
    root=Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    tests={
      'overhead_reach':pose(handL=(.22,-.04,1.95),handR=(-.22,-.04,1.95),chest=(-5,0,0),gripL=0,gripR=0),
      'deep_squat':pose(pelvis=(0,.12,-.54),spine=(18,0,0),chest=(17,0,0),footL=(.21,-.23,.11),footR=(-.21,-.23,.11),handL=(.24,-.55,.96),handR=(-.24,-.55,.96)),
      'crossed_arm_reach':pose(handL=(-.23,-.24,1.46),handR=(.22,-.22,1.37),chest=(2,0,9),gripL=.2,gripR=.2),
      'large_torso_twist':pose(pelvis_rot=(0,0,0),spine=(0,0,38),chest=(0,0,35),head=(0,0,10),handL=(.28,.10,1.39),handR=(.24,-.35,1.26)),
      'kneeling':KNEEL.copy(),
      'planted_hand_support':pose(pelvis=(0,.05,-.58),pelvis_rot=(60,0,0),spine=(12,0,0),chest=(12,0,0),head=(-25,0,0),handL=(.28,-.44,.030),handR=(-.28,-.44,.055),footL=(.18,.73,.11),footR=(-.18,.73,.11),gripL=0,gripR=0,blade=.035,floor_hands=1.),
      'closed_grip':pose(handL=(.09,-.29,1.24),handR=(-.09,-.31,1.27),gripL=1,gripR=1,head=(14,0,0))}
    constraints=[(c,c.mute) for pb in rig.pose.bones for c in pb.constraints]
    for c,_ in constraints:c.mute=True
    for name,p in tests.items():
        id='TEST__'+name
        if id in bpy.data.actions:bpy.data.actions.remove(bpy.data.actions[id])
        a=bpy.data.actions.new(id);a.use_fake_user=True;rig.animation_data.action=a;apply_pose(rig,p,id,0)
        for f in (1,31):
            for pb in rig.pose.bones:
                if pb.bone.use_deform:
                    pb.keyframe_insert('location',frame=f,group=pb.name);pb.keyframe_insert('rotation_quaternion',frame=f,group=pb.name);pb.keyframe_insert('scale',frame=f,group=pb.name)
    for c,m in constraints:c.mute=m
    (root/'docs/deformation_test_poses.json').write_text(json.dumps({'source':'source/Operative.blend','frame':1,'actions':['TEST__'+name for name in tests]},indent=2))
    rig.animation_data.action=bpy.data.actions['idle_relaxed'];bpy.context.scene.frame_set(1)
