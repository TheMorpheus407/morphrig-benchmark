"""MorphRig animation authoring core (runs inside Blender).

A clip is authored as a list of semantic key poses (dict) at frames, plus optional
dense procedural tracks.  `realize()` converts a semantic pose into rig channel
values (bone location/rotation/custom properties) using the rig's rest matrices.
Channels are then written as keyframes on MR_Rig (see ClipWriter).

Semantic pose keys (all optional; missing keys fall back to the base pose):
  cog      (x, y, z) m offset of c_torso in root space
  cog_rot  (pitch, yaw, roll) deg (pitch + = lean forward, yaw + = turn left, roll + = lean right)
  hips     (pitch, yaw, roll) deg pelvis relative to c_torso
  spine    (pitch, yaw, roll) deg distributed over spine_01..03
  neck/head (pitch, yaw, roll) deg
  clav_l/clav_r (elevate, protract) deg
  arm_l/arm_r  {'fk': (flex, abd, twist), 'elbow': deg, 'wrist': (flex, dev, pron)} or
               {'ik': (x, y, z), 'hand_rot': 3x3 or None, 'pole': (x, y, z)}
  foot_l/foot_r {'pos': (x, y, z) ankle, 'yaw': deg, 'pitch': deg, 'roll': deg, 'toe': deg, 'heelroll': 0..1}
  knee_l/knee_r pole offset direction (x, y, z) (unit-ish, default = foot forward)
  hand_l/hand_r  finger shape name or dict
  face     {prop: value}, jaw (deg), tongue (t1, t2, t3 deg), look (yaw, pitch) deg
  blade    0 folded .. 1 extended
  cell     parent 0/1, beacon: {'parent': 0/1/2, 'pos': (x,y,z), 'yaw': deg}
  root     (x, y, z, yaw) root-motion
"""
import math
import numpy as np
import bpy
from mathutils import Matrix, Vector, Quaternion, Euler

DEG = math.pi / 180.0
FPS = 30

# signs for mirrored local axes: (bone_base, axis) -> (left sign, right sign)
MIRROR_SIGN = {"Y": (1, -1), "Z": (1, -1), "X": (1, 1)}


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def axis_angle(axis, a):
    axis = np.asarray(axis, float)
    axis = axis / max(np.linalg.norm(axis), 1e-12)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def to_M4(R=None, t=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if t is not None:
        M[:3, 3] = t
    return M


def mat_to_quat(R):
    q = Matrix([list(R[0]), list(R[1]), list(R[2])]).to_quaternion()
    return np.array([q.w, q.x, q.y, q.z])


def world_turn(yaw_deg, pitch_deg=0.0, roll_deg=0.0):
    """Rotation in the character frame: yaw about +Z (left turn positive), pitch about the
    character's lateral axis (+ = nose down / lean forward), roll about forward axis (+ = lean right)."""
    # character forward = -Y, left = +X.  Lean forward (pitch +) rotates +Z toward -Y: about +X axis.
    return rot_z(yaw_deg * DEG) @ rot_x(pitch_deg * DEG) @ rot_y(roll_deg * DEG)


class RigModel:
    """Rest data of MR_Rig for converting world targets to bone bases."""

    def __init__(self, rig):
        self.rig = rig
        self.rest = {}
        self.parent = {}
        for b in rig.data.bones:
            self.rest[b.name] = np.array(b.matrix_local)
            self.parent[b.name] = b.parent.name if b.parent else None
        self.rotmode = {pb.name: pb.rotation_mode for pb in rig.pose.bones}

    def rest_local(self, name):
        p = self.parent[name]
        if p is None:
            return self.rest[name]
        return np.linalg.inv(self.rest[p]) @ self.rest[name]

    def basis_from_world(self, name, M_world, parent_world=None):
        """basis such that parent_world @ rest_local @ basis = M_world."""
        p = self.parent[name]
        if parent_world is None:
            parent_world = np.eye(4) if p is None else self.rest[p]
        return np.linalg.inv(parent_world @ self.rest_local(name)) @ M_world


# ---------------------------------------------------------------- hand shapes
HAND_SHAPES = {
    # per finger (mcp, pip, dip) curl deg, thumb (cmc, mcp, ip) flexion toward the pad,
    # thumb_add = CMC adduction toward the index side (negative = abduction), spread deg
    "relaxed": dict(curl={"index": (14, 22, 12), "middle": (18, 28, 16), "ring": (22, 32, 18), "pinky": (26, 36, 20)},
                    thumb=(8, 10, 12), thumb_add=10, spread=2),
    "open": dict(curl={"index": (2, 4, 2), "middle": (2, 4, 2), "ring": (3, 5, 3), "pinky": (4, 6, 3)},
                 thumb=(-4, 0, 0), thumb_add=0, spread=10),
    "spread": dict(curl={"index": (-4, 2, 2), "middle": (-4, 2, 2), "ring": (-4, 2, 2), "pinky": (-4, 2, 2)},
                   thumb=(-12, -6, 0), thumb_add=-20, spread=18),
    "fist": dict(curl={"index": (82, 95, 55), "middle": (86, 98, 55), "ring": (88, 98, 55), "pinky": (90, 96, 52)},
                 thumb=(-2, 35, 32), thumb_add=50, spread=-2),
    "loose_fist": dict(curl={"index": (55, 70, 40), "middle": (60, 75, 42), "ring": (64, 78, 42),
                             "pinky": (68, 80, 44)}, thumb=(5, 22, 18), thumb_add=32, spread=0),
    "point": dict(curl={"index": (0, 2, 2), "middle": (80, 95, 55), "ring": (85, 98, 55), "pinky": (88, 96, 52)},
                  thumb=(0, 30, 25), thumb_add=45, spread=0),
    "grip_cell": dict(curl={"index": (48, 58, 30), "middle": (52, 60, 32), "ring": (56, 62, 32),
                            "pinky": (60, 64, 34)}, thumb=(24, 20, 18), thumb_add=0, spread=-1),
    "grip_beacon": dict(curl={"index": (26, 34, 18), "middle": (28, 36, 18), "ring": (30, 36, 18),
                              "pinky": (32, 36, 18)}, thumb=(18, 14, 10), thumb_add=5, spread=8),
    "knife": dict(curl={"index": (6, 8, 4), "middle": (6, 8, 4), "ring": (7, 9, 4), "pinky": (8, 10, 4)},
                  thumb=(6, 4, 2), thumb_add=25, spread=-4),
    "claw": dict(curl={"index": (20, 60, 40), "middle": (20, 62, 40), "ring": (22, 62, 40), "pinky": (24, 60, 40)},
                 thumb=(10, 30, 30), thumb_add=0, spread=12),
    "type": dict(curl={"index": (20, 30, 18), "middle": (28, 40, 22), "ring": (34, 46, 24), "pinky": (40, 50, 26)},
                 thumb=(14, 18, 16), thumb_add=10, spread=4),
    "wave": dict(curl={"index": (4, 6, 4), "middle": (4, 6, 4), "ring": (5, 7, 4), "pinky": (6, 8, 4)},
                 thumb=(-6, 0, 2), thumb_add=-10, spread=12),
    "thumbs_up": dict(curl={"index": (88, 98, 55), "middle": (90, 98, 55), "ring": (90, 98, 55),
                            "pinky": (90, 96, 52)}, thumb=(-10, -5, 0), thumb_add=-30, spread=0),
}

FINGERS = ["index", "middle", "ring", "pinky"]
SPREAD_W = {"index": 1.0, "middle": 0.25, "ring": -0.55, "pinky": -1.0}


def finger_channels(side, shape, extra_curl=0.0):
    """Local euler rotations for finger bones. Curl is -X (toward the palm)."""
    if isinstance(shape, str):
        sh = HAND_SHAPES[shape]
    else:
        base = HAND_SHAPES[shape.get("base", "relaxed")]
        sh = dict(base)
        sh.update({k: v for k, v in shape.items() if k != "base"})
    ch = {}
    sgn = 1 if side == "l" else -1
    for f in FINGERS:
        c = sh["curl"][f]
        for k in range(3):
            ang = -(c[k] + extra_curl) * DEG
            spread = 0.0
            if k == 0:
                spread = sh.get("spread", 0) * SPREAD_W[f] * DEG * sgn
            ch[f"{f}_0{k + 1}_{side}.rot"] = np.array([ang, 0.0, spread])
    # thumb (cmc, mcp, ip) flexion toward the pad (-X), plus CMC adduction toward the index side (+Z)
    t = sh["thumb"]
    add = sh.get("thumb_add", 0.0)
    ch[f"thumb_01_{side}.rot"] = np.array([-t[0] * DEG, 0.0, add * DEG * sgn])
    ch[f"thumb_02_{side}.rot"] = np.array([-t[1] * DEG, 0.0, 0.0])
    ch[f"thumb_03_{side}.rot"] = np.array([-t[2] * DEG, 0.0, 0.0])
    return ch


# ---------------------------------------------------------------- realize
class Realizer:
    """Converts semantic poses into rig channel values."""

    def __init__(self, rig):
        self.m = RigModel(rig)
        self.rig = rig
        R = self.m.rest
        self.ankle_rest = {s: R[f"c_foot_ik_{s}"][:3, 3].copy() for s in "lr"}
        self.foot_rest_R = {s: R[f"c_foot_ik_{s}"][:3, :3].copy() for s in "lr"}
        self.hand_rest = {s: R[f"c_hand_ik_{s}"].copy() for s in "lr"}
        self.torso_rest = R["c_torso"].copy()
        self.look_rest = R["c_look"][:3, 3].copy()

    # -- helpers producing channels ------------------------------------------
    def euler_bone(self, ch, bone, pitch=0.0, yaw=0.0, roll=0.0):
        """Spine-like bones: X = pitch (bend forward), Y = yaw (turn left), Z = roll (lean right)."""
        ch[bone + ".rot"] = np.array([pitch * DEG, yaw * DEG, roll * DEG])

    def foot(self, ch, side, pos=None, yaw=0.0, pitch=0.0, roll=0.0, toe=0.0, heelroll=0.0, root=None):
        """IK foot: ankle world position + orientation relative to rest (deg)."""
        rest = self.m.rest[f"c_foot_ik_{side}"]
        p = self.ankle_rest[side] if pos is None else np.asarray(pos, float)
        fd = rest[:3, 1].copy()
        fd[2] = 0
        fd /= np.linalg.norm(fd)
        lat = np.cross(fd, np.array([0, 0, 1.0]))
        # pitch + = toes up (rotation about the foot's right-pointing lateral axis)
        Rw = rot_z(yaw * DEG) @ axis_angle(lat, pitch * DEG) @ axis_angle(fd, roll * DEG) @ rest[:3, :3]
        M = to_M4(Rw, p)
        B = np.linalg.inv(rest) @ M      # parent = root (identity in root space)
        ch[f"c_foot_ik_{side}.loc"] = B[:3, 3]
        ch[f"c_foot_ik_{side}.quat"] = mat_to_quat(B[:3, :3])
        ch[f"c_foot_ik_{side}[roll]"] = np.array([heelroll])
        ch[f"c_ball_ik_{side}.rot"] = np.array([toe * DEG, 0, 0])
        ch[f"c_foot_ik_{side}[ik_fk]"] = np.array([1.0])

    def knee_pole(self, ch, side, offset):
        """Pole relative to the foot control (in foot-control local space)."""
        ch[f"c_knee_pole_{side}.loc"] = np.asarray(offset, float)

    def hand_ik(self, ch, side, pos, R_world=None, pole=None, blend=1.0):
        rest = self.hand_rest[side]
        Rw = rest[:3, :3] if R_world is None else np.asarray(R_world, float)
        M = to_M4(Rw, np.asarray(pos, float))
        B = np.linalg.inv(rest) @ M
        ch[f"c_hand_ik_{side}.loc"] = B[:3, 3]
        ch[f"c_hand_ik_{side}.quat"] = mat_to_quat(B[:3, :3])
        ch[f"c_hand_ik_{side}[ik_fk]"] = np.array([blend])
        if pole is not None:
            pr = self.m.rest[f"c_elbow_pole_{side}"]
            ch[f"c_elbow_pole_{side}.loc"] = (np.linalg.inv(pr) @ to_M4(pr[:3, :3], np.asarray(pole, float)))[:3, 3]

    def arm_fk(self, ch, side, flex=0.0, abd=0.0, twist=0.0, elbow=0.0, wflex=0.0, wdev=0.0, pron=0.0):
        s = 1 if side == "l" else -1
        ch[f"c_upperarm_fk_{side}.rot"] = np.array([flex * DEG, twist * DEG * s, abd * DEG * s])
        ch[f"c_lowerarm_fk_{side}.rot"] = np.array([elbow * DEG, pron * 0.0, 0.0])
        ch[f"c_hand_fk_{side}.rot"] = np.array([-wflex * DEG, pron * DEG * s, wdev * DEG * s])
        ch[f"c_hand_ik_{side}[ik_fk]"] = np.array([0.0])

    def clav(self, ch, side, elevate=0.0, protract=0.0):
        s = 1 if side == "l" else -1
        ch[f"clavicle_{side}.rot"] = np.array([elevate * DEG, 0.0, -protract * DEG * s])

    def hand_shape(self, ch, side, shape):
        ch.update(finger_channels(side, shape))

    def look(self, ch, yaw=0.0, pitch=0.0, dist=1.5):
        """c_look lives in head space: yaw + = look to the character's left, pitch + = up."""
        # c_look local axes: Y = -Y world (forward), Z = up, X = Y x Z = -X world.
        x = -math.tan(yaw * DEG) * dist
        z = math.tan(pitch * DEG) * dist
        ch["c_look.loc"] = np.array([x, 0.0, z])

    def face(self, ch, props):
        from mr_face_list import FACE_PROPS
        for k in FACE_PROPS:
            ch[f"c_face[{k}]"] = np.array([float(props.get(k, 0.0))])
        for k in props:
            if k not in FACE_PROPS:
                raise KeyError(f"unknown face control {k}")

    def realize(self, P):
        """Semantic pose dict -> channel dict."""
        ch = {}
        cog = P.get("cog", (0, 0, 0))
        crot = P.get("cog_rot", (0, 0, 0))
        # c_torso: world target = rest translated by cog, rotated by cog_rot
        R = world_turn(crot[1], crot[0], crot[2])
        rest = self.torso_rest
        M = to_M4(R @ rest[:3, :3], rest[:3, 3] + np.asarray(cog, float))
        B = np.linalg.inv(rest) @ M
        ch["c_torso.loc"] = B[:3, 3]
        ch["c_torso.quat"] = mat_to_quat(B[:3, :3])
        hp = P.get("hips", (0, 0, 0))
        # pelvis bone: Y up, Z forward -> X = pitch forward, Y = yaw left, Z = roll right
        q = Euler((hp[0] * DEG, hp[1] * DEG, hp[2] * DEG), 'XYZ').to_quaternion()
        ch["pelvis.quat"] = np.array([q.w, q.x, q.y, q.z])
        sp = P.get("spine", (0, 0, 0))
        dist = P.get("spine_dist", (0.30, 0.33, 0.37))
        for b, w in zip(("spine_01", "spine_02", "spine_03"), dist):
            self.euler_bone(ch, b, sp[0] * w, sp[1] * w, sp[2] * w)
        nk = P.get("neck", (0, 0, 0))
        self.euler_bone(ch, "neck_01", nk[0] * 0.55, nk[1] * 0.5, nk[2] * 0.5)
        self.euler_bone(ch, "neck_02", nk[0] * 0.45, nk[1] * 0.5, nk[2] * 0.5)
        hd = P.get("head", (0, 0, 0))
        self.euler_bone(ch, "head", hd[0], hd[1], hd[2])
        for s in "lr":
            c = P.get("clav_" + s, (0, 0))
            self.clav(ch, s, c[0], c[1])
            a = P.get("arm_" + s, {"fk": (0, 0, 0), "elbow": 0})
            if "ik" in a:
                self.hand_ik(ch, s, a["ik"], a.get("hand_rot"), a.get("pole"), a.get("blend", 1.0))
                if a.get("pole") is None:
                    ch[f"c_elbow_pole_{s}.loc"] = np.zeros(3)
                # keep FK channels at a neutral bent pose so switching is sane
                self.arm_fk(ch, s, *a.get("fk_hint", (10, 0, 0)), elbow=a.get("elbow_hint", 30))
                ch[f"c_hand_ik_{s}[ik_fk]"] = np.array([a.get("blend", 1.0)])
            else:
                fk = a.get("fk", (0, 0, 0))
                w = a.get("wrist", (0, 0, 0))
                self.arm_fk(ch, s, fk[0], fk[1], fk[2], a.get("elbow", 0.0), w[0], w[1], w[2])
                # IK control is snapped to the evaluated FK hand by the writer (pose matching)
                ch[f"c_hand_ik_{s}.loc"] = np.zeros(3)
                ch[f"c_hand_ik_{s}.quat"] = np.array([1.0, 0, 0, 0])
                ch[f"c_elbow_pole_{s}.loc"] = np.zeros(3)
                ch.setdefault("@snap", []).append(s)
            f = P.get("foot_" + s) or {}
            self.foot(ch, s, f.get("pos"), f.get("yaw", 0.0), f.get("pitch", 0.0), f.get("roll", 0.0),
                      f.get("toe", 0.0), f.get("heelroll", 0.0))
            lg = P.get("leg_" + s)
            sg = 1 if s == "l" else -1
            if lg is not None and P.get("foot_" + s) and not lg.get("override", True):
                lg = None
            if lg is not None:
                fk = lg.get("fk", (0, 0, 0))
                ak = lg.get("ankle", (0, 0))
                ch[f"c_thigh_fk_{s}.rot"] = np.array([fk[0] * DEG, fk[2] * DEG * sg, fk[1] * DEG * sg])
                ch[f"c_calf_fk_{s}.rot"] = np.array([-lg.get("knee", 0.0) * DEG, 0.0, 0.0])
                ch[f"c_foot_fk_{s}.rot"] = np.array([ak[0] * DEG, 0.0, ak[1] * DEG * sg])
                ch[f"c_ball_fk_{s}.rot"] = np.array([lg.get("toe", 0.0) * DEG, 0.0, 0.0])
                ch.setdefault("@snap_leg", []).append(s)
            else:
                for part in ("thigh", "calf", "foot", "ball"):
                    ch[f"c_{part}_fk_{s}.rot"] = np.zeros(3)
            kp = P.get("knee_" + s)
            if kp is not None:
                self.knee_pole(ch, s, kp)
            else:
                ch[f"c_knee_pole_{s}.loc"] = np.zeros(3)
            self.hand_shape(ch, s, P.get("hand_" + s, "relaxed"))
            ch[f"c_fingers_{s}.rot"] = np.zeros(3)
        fp = dict(P.get("face", {}))
        self.face(ch, fp)
        ch["jaw.rot"] = np.array([P.get("jaw", 0.0) * DEG, 0.0, P.get("jaw_side", 0.0) * DEG])
        tg = P.get("tongue", (0, 0, 0))
        for k in range(3):
            ch[f"tongue_0{k + 1}.rot"] = np.array([tg[k] * DEG, 0.0, 0.0])
        lk = P.get("look", (0, 0))
        self.look(ch, lk[0], lk[1])
        # blade: rotate about the forearm lateral axis from folded (0) to extended (1)
        bl = P.get("blade", 0.0)
        ch["blade_r.rot"] = np.array([0.0, 0.0, -bl * 180.0 * DEG])
        ch["prop_cell[parent]"] = np.array([float(P.get("cell", 0))])
        bc = P.get("beacon", {"parent": 0})
        ch["prop_beacon[parent]"] = np.array([float(bc.get("parent", 0))])
        if bc.get("parent", 0) == 2 and "pos" in bc:
            rest_b = self.m.rest["prop_beacon"]
            yaw = bc.get("yaw", 0.0) * DEG
            Y = rot_z(yaw) @ np.array([0, -1.0, 0])
            Z = np.array([0, 0, 1.0])
            X = np.cross(Y, Z)
            Mw = to_M4(np.stack([X, Y, Z], 1), np.asarray(bc["pos"], float))
            Bb = np.linalg.inv(rest_b) @ Mw
            ch["prop_beacon.loc"] = Bb[:3, 3]
            ch["prop_beacon.rot"] = np.array(Matrix([list(Bb[0][:3]), list(Bb[1][:3]), list(Bb[2][:3])]).to_euler('XYZ'))
        else:
            ch["prop_beacon.loc"] = np.zeros(3)
            ch["prop_beacon.rot"] = np.zeros(3)
        ch["prop_cell.loc"] = np.asarray(P.get("cell_offset", (0, 0, 0)), float)
        ch["prop_cell.rot"] = np.zeros(3)
        rt = P.get("root", (0, 0, 0, 0))
        ch["root.loc"] = self._root_loc(rt)
        q = Quaternion((0, 0, 1), rt[3] * DEG)
        # root bone: Y = -Y world, Z = up; its local rotation about local Z == world Z
        ch["root.quat"] = np.array([q.w, q.x, q.y, q.z])
        for k in range(1, 5):
            ch[f"hair_tail_{k:02d}.rot"] = np.asarray(P.get(f"tail_{k}", (0, 0, 0)), float) * DEG
        return ch

    def _root_loc(self, rt):
        # root rest: head at origin, Y axis = -Y world, Z = +Z, X = Y x Z = -X world
        return np.array([-rt[0], -rt[1], rt[2]])


def merge(base, *over):
    """Deep-merge semantic poses (dicts for arms/feet are merged key-wise)."""
    out = {}
    for d in (base,) + over:
        for k, v in d.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("face",):
                nv = dict(out[k])
                nv.update(v)
                out[k] = nv
            elif k == "face" and isinstance(out.get(k), dict):
                nv = dict(out[k])
                nv.update(v)
                out[k] = nv
            else:
                out[k] = v
    return out
