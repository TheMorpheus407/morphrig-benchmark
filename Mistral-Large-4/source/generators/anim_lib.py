"""MorphRig animation library - pose schema, rig driver and procedural pose generators.

Part of the MorphRig Operative production (SPEC.md section 8).  Used by
gen_03_animations.py to author the 96 required clips as Blender actions on the
deformation skeleton (Armature) plus a companion shape-key action per clip.

Authoring model (verified exact against rig_ops.apply_controls):
  The control rig's rest pose matches the deformation skeleton's rest pose bone
  for bone, and every FK control's parent is the control that drives the parent
  deform bone.  Therefore setting a control's WORLD matrix to the desired world
  matrix of its deform bone makes apply_controls() reproduce that matrix exactly
  on the deform bone (the rest chains telescope).  IK limbs are placed by
  authoring the ik target/pole controls and computing the fk_hand/fk_foot basis
  against the analytic IK solution (identical inputs to apply_controls, hence an
  identical result).  Prop bones (emitter/blade parented to forearm_R,
  cell_new/cell_spent/beacon parented to root) are direct-set AFTER apply,
  because apply_controls clears every deform bone basis at the start.

Conventions:
  * World units are meters, Z up.  The character faces -Y ("forward").
  * Yaw is in degrees about world +Z: positive yaw turns the facing direction
    toward +X (right).  Pitch positive = up.  dir_of(yaw, pitch) gives the
    unit direction (sin yaw cos p, -cos yaw cos p, sin p).
  * Gait clips are authored on a treadmill: the body stays in place and the
    stance feet move backward relative to the body at v_app, so a controller
    moving the capsule at v_app keeps the world feet planted.
"""
import bpy
import math
import copy
from mathutils import Vector, Matrix

import rig_ops
from morphrig_lib import lerp, lerp_v, smoothstep, cosine_ease, clamp, FPS, FWD, UP, RIGHT

TWO_PI = 2.0 * math.pi

# deform bones in hierarchy order (parents before children) - the keying order
DEFORM_BONES = [
    "root", "pelvis", "spine_01", "spine_02", "spine_03",
    "neck_01", "neck_02", "head", "jaw",
    "eye_L", "lid_upper_L", "lid_lower_L", "brow_L",
    "eye_R", "lid_upper_R", "lid_lower_R", "brow_R",
    "clavicle_L", "upper_arm_L", "upper_arm_twist_L", "forearm_L", "forearm_twist_L", "hand_L",
    "f_thumb_01_L", "f_thumb_02_L", "f_thumb_03_L",
    "f_index_01_L", "f_index_02_L", "f_index_03_L",
    "f_middle_01_L", "f_middle_02_L", "f_middle_03_L",
    "f_ring_01_L", "f_ring_02_L", "f_ring_03_L",
    "f_pinky_01_L", "f_pinky_02_L", "f_pinky_03_L",
    "clavicle_R", "upper_arm_R", "upper_arm_twist_R", "forearm_R", "forearm_twist_R", "hand_R",
    "f_thumb_01_R", "f_thumb_02_R", "f_thumb_03_R",
    "f_index_01_R", "f_index_02_R", "f_index_03_R",
    "f_middle_01_R", "f_middle_02_R", "f_middle_03_R",
    "f_ring_01_R", "f_ring_02_R", "f_ring_03_R",
    "f_pinky_01_R", "f_pinky_02_R", "f_pinky_03_R",
    "emitter", "blade", "cable_01", "cable_02",
    "thigh_L", "thigh_twist_L", "shin_L", "shin_twist_L", "foot_L", "toe_L",
    "thigh_R", "thigh_twist_R", "shin_R", "shin_twist_R", "foot_R", "toe_R",
    "cable_03", "cell_new", "cell_spent", "beacon",
]
SHAPE_KEYS = ["lip_close", "smile_L", "smile_R", "frown_L", "frown_R",
              "lip_width", "pucker", "cheek_L", "cheek_R", "tongue_out"]

# gait speed classes: n frames/cycle, stance fraction, stride E (m the foot
# travels relative to the body per step), swing foot lift, apparent (treadmill)
# speed, leg extension at mid-stance (fraction of full leg length), arm swing
# amplitude / elbow bend / forward lean, heel-rise angle at push-off.
# SPEC section 8 nominal reference speeds: 150 cm/s walk, 400 cm/s run,
# 650 cm/s sprint.  The stance foot moves backward relative to the body at
# exactly v_app, so E = v_app * stance * n / 30 (asserted in Rig.__init__).
# E is kept within the leg's reach: the pelvis vaults down at the stride
# extremes (drop ~7/11/11 cm for walk/run/sprint on this 0.85 m leg).
GAIT = {
    "walk":   dict(n=24, stance=0.60, E=0.72, lift=0.055, v_app=1.50,
                   d_mid=0.95, arm_amp=16.0, elbow=18.0, lean=2.0, heel=22.0,
                   shift=0.030, yaw_sway=1.4, arc=0.0),
    "run":    dict(n=18, stance=0.36, E=0.864, lift=0.10, v_app=4.00,
                   d_mid=0.93, arm_amp=28.0, elbow=32.0, lean=9.0, heel=26.0,
                   shift=0.022, yaw_sway=1.0, arc=0.035),
    "sprint": dict(n=12, stance=0.34, E=0.884, lift=0.13, v_app=6.50,
                   d_mid=0.92, arm_amp=34.0, elbow=40.0, lean=15.0, heel=28.0,
                   shift=0.016, yaw_sway=0.8, arc=0.05),
}
# direction name -> alpha (deg): u(alpha) = (sin a, -cos a, 0); body faces -Y
DIR_ALPHA = {"f": 0.0, "fr": 45.0, "r": 90.0, "br": 135.0,
             "b": 180.0, "bl": -135.0, "l": -90.0, "fl": -45.0}
# the character's rest ankle height (foot head z) and thigh-head offset below pelvis
ANKLE_Z = 0.075
THIGH_DROP = 0.030


# ------------------------------------------------------------------ math utils
def R_axis(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized())


def dir_of(yaw_deg, pitch_deg=0.0):
    """Unit direction for (yaw, pitch) in degrees: +yaw = right, +pitch = up."""
    y = math.radians(yaw_deg)
    p = math.radians(pitch_deg)
    return Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))


def most_down_perp(d):
    """The unit vector perpendicular to d that points as much downward as possible."""
    down = Vector((0.0, 0.0, -1.0))
    v = down - d * down.dot(d)
    if v.length < 1e-3:
        v = Vector((1.0, 0.0, 0.0)) - d * d.x
        if v.length < 1e-3:
            v = Vector((0.0, 1.0, 0.0))
    return v.normalized()


def mat_cols(c0, c1, c2):
    """4x4 matrix whose COLUMNS are c0, c1, c2 (rotation part, zero translation)."""
    return Matrix((c0, c1, c2)).transposed().to_4x4()


# ------------------------------------------------------------------ pose schema
def _leg():
    return {"mode": "ik", "ankle": None, "yaw": 0.0, "pitch": 0.0,
            "toe": 0.0, "pole": None}


def _arm():
    return {"mode": "fk_param", "w": (1.0, 0.0, 0.0),
            "swing": 0.0, "lift": 0.0, "yaw": 0.0, "elbow": 0.0, "wrist": 0.0,
            "curl": 0.0, "spread": 0.0,
            "hand": None, "forearm": None, "target": None, "pole": None,
            "hand_R": None}


def default_pose():
    return {
        "root": (0.0, 0.0, 0.0),          # ctrl_root local translation; +z = forward
        "scale": 1.0,                      # global_scale prop
        "w": (1.0, 0.0, 0.0),              # lean axis (world)
        "pelvis": {"z": 0.955, "yaw": 0.0, "lean": 0.0, "roll": 0.0, "shift": 0.0,
                   "x": 0.0, "y": 0.0},
        "chest": {"lean": 0.0, "yaw": 0.0},  # extra lean/yaw vs rigid pelvis follow
        "look": (0.0, 0.0),                # (yaw deg, pitch deg)
        "legs": {"L": _leg(), "R": _leg()},
        "arms": {"L": _arm(), "R": _arm()},
        "face": {},                        # control props
        "fingers": {"L": {}, "R": {}},     # {finger: curl deg (segment 01)}
        "def": {},                         # {deform bone: world Matrix}
    }


def P(base=None, **kw):
    """Deep copy of base (or a fresh default pose) with '__'-separated overrides."""
    out = copy.deepcopy(base if base is not None else default_pose())
    for k, v in kw.items():
        parts = k.split("__")
        d = out
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = v
    return out


def lerp_params(a, b, t):
    """Structural interpolation between two pose-param dicts."""
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for k in set(a.keys()) | set(b.keys()):
            if k in a and k in b:
                out[k] = lerp_params(a[k], b[k], t)
            elif k in a:
                out[k] = a[k]
            else:
                out[k] = b[k]
        return out
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        return rig_ops.lerp_matrices(a, b, t)
    if isinstance(a, bool) or isinstance(b, bool):
        return b if t >= 0.5 else a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * t
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b) \
            and all(isinstance(x, (int, float)) for x in a) \
            and all(isinstance(x, (int, float)) for x in b):
        return tuple(lerp_params(x, y, t) for x, y in zip(a, b))
    return b if t >= 0.5 else a


def eval_track(track, f):
    """Evaluate a PoseTrack [(frame, params), ...] at frame f (smoothstep segments)."""
    if f <= track[0][0]:
        return track[0][1]
    if f >= track[-1][0]:
        return track[-1][1]
    for i in range(len(track) - 1):
        f0, p0 = track[i]
        f1, p1 = track[i + 1]
        if f0 <= f <= f1:
            t = (f - f0) / float(f1 - f0)
            return lerp_params(p0, p1, smoothstep(t))
    return track[-1][1]


# ------------------------------------------------------------------ the Rig
class Rig:
    """Drives the control rig from pose params and bakes/keys the deform skeleton."""

    def __init__(self):
        self.A = rig_ops.arm()
        self.C = rig_ops.ctrl()
        self.M = rig_ops.mesh()
        self.sk = self.M.data.shape_keys
        self.pbs = {pb.name: pb for pb in self.A.pose.bones}
        self.cbs = {cb.name: cb for cb in self.C.pose.bones}
        self.rest = {}      # deform bone -> rest world matrix
        self.rl = {}        # deform bone -> rest matrix relative to parent
        self.blen = {}      # deform bone -> length
        self.ctrl_rl = {}   # control bone -> rest matrix relative to parent
        self.ctrl_rest = {} # control bone -> rest world matrix
        for pb in self.A.pose.bones:
            b = pb.bone
            self.rest[b.name] = b.matrix_local.copy()
            self.rl[b.name] = rig_ops.rest_local(b)
            self.blen[b.name] = b.length
        # control rest state (the blend is saved with controls at rest; reset anyway)
        rig_ops.reset_pose()
        for cb in self.C.pose.bones:
            b = cb.bone
            self.ctrl_rl[b.name] = rig_ops.rest_local(b)
            self.ctrl_rest[b.name] = b.matrix_local.copy()
        # emitter firing axis in forearm_R local space (for exact aim construction)
        self.FIRE_LOCAL = self.rl["emitter"].to_3x3() @ Vector((0.0, 0.0, -1.0))
        # IK chain segment lengths: head-of-bone to head-of-IK-child distances.
        # A bone's tail does not necessarily sit at the child bone's head (the
        # shin bone ends 0.03 above the ankle), and both the IK solver and
        # apply_controls work with head-to-head distances, so the reachability
        # math must use those, not bone lengths.
        def seg(a, b):
            return (self.rest[b].to_translation() - self.rest[a].to_translation()).length
        self.leg_len = seg("thigh_L", "shin_L") + seg("shin_L", "foot_L")
        self.arm_L1 = {s: seg(f"upper_arm_{s}", f"forearm_{s}") for s in ("L", "R")}
        self.arm_L2 = {s: seg(f"forearm_{s}", f"hand_{s}") for s in ("L", "R")}
        self.arm_len = {s: self.arm_L1[s] + self.arm_L2[s] for s in ("L", "R")}
        # gait pelvis height cap (mid-stance, foot under the hip)
        for s, g in GAIT.items():
            v = g["E"] / (g["stance"] * g["n"] / 30.0)
            assert abs(v - g["v_app"]) < 1e-9, \
                "gait %s: E/stance/n implies v_app=%.4f, table says %.4f" % (s, v, g["v_app"])
            g["z_hi"] = ANKLE_Z + THIGH_DROP + g["d_mid"] * self.leg_len
        # per-clip state
        self.ctrl_world = dict(self.ctrl_rest)
        self.def_m = {}
        self.prev = {}
        self.prev_euler = {}
        self.prev_shape = {}
        self.arm_m = {}
        # world offset added to the pelvis (and hence every limb target built
        # from it) for root-motion clips: the root CONTROL translates the root
        # bone + props, and this offset translates the body so the whole
        # character travels with the root.  Pp["root"] stays the root
        # control's LOCAL translation (local +Z = world -Y forward, +X right).
        self.root_off = Vector((0.0, 0.0, 0.0))
        self.act = None
        self.face_act = None
        self.markers = []
        self.clip_id = None
        self.n = 0

    # ---------------- state
    def reset(self):
        rig_ops.reset_pose()
        self.ctrl_world = dict(self.ctrl_rest)
        self.def_m = {}
        self.prev = {}
        self.prev_euler = {}
        self.prev_shape = {}
        self.arm_m = {}
        self.root_off = Vector((0.0, 0.0, 0.0))
        self.markers = []

    # ---------------- control setting
    def set_ctrl(self, name, M):
        """Set a control's WORLD matrix to M (exact on the driven deform bone)."""
        cb = self.cbs[name]
        b = cb.bone
        if b.parent is None:
            basis = b.matrix_local.inverted() @ M
        else:
            basis = self.ctrl_rl[name].inverted() @ self.ctrl_world[b.parent.name].inverted() @ M
        self._set_basis(cb, basis)
        self.ctrl_world[name] = M.copy()

    def set_ctrl_basis(self, name, basis):
        """Assign a control bone's local basis directly (fk_hand/fk_foot in IK mode)."""
        self._set_basis(self.cbs[name], basis)

    def set_target(self, name, pos):
        """Place a parentless-style control (ik target / pole / look) at world pos."""
        M = Matrix.Translation(Vector(pos))
        cb = self.cbs[name]
        b = cb.bone
        if b.parent is None:
            basis = b.matrix_local.inverted() @ M
        else:
            basis = self.ctrl_rl[name].inverted() @ self.ctrl_world[b.parent.name].inverted() @ M
        self._set_basis(cb, basis)
        self.ctrl_world[name] = M

    @staticmethod
    def _set_basis(pb, basis):
        loc = basis.to_translation()
        R = basis.to_3x3()
        sc = Vector((R.col[0].length, R.col[1].length, R.col[2].length))
        for i in range(3):
            if sc[i] > 1e-9:
                R.col[i] = R.col[i] / sc[i]
        pb.rotation_mode = 'XYZ'
        pb.location = loc
        pb.rotation_euler = R.to_euler('XYZ')
        pb.scale = sc

    def set_prop(self, name, value):
        self.C[name] = value

    # ---------------- bake
    def apply(self):
        rig_ops.apply_controls()
        self.def_m = {name: pb.matrix.copy() for name, pb in self.pbs.items()}

    def set_def(self, name, M):
        """Direct-set a deform bone (props) to world matrix M, after apply()."""
        pb = self.pbs[name]
        parent = pb.bone.parent.name
        basis = self.rl[name].inverted() @ self.def_m[parent].inverted() @ M
        self._set_basis(pb, basis)

    def post_pose(self, Pp):
        """Finger overrides + prop bone direct-sets.  MUST run after apply()."""
        for side, fingers in Pp["fingers"].items():
            for finger, deg in fingers.items():
                for i in (1, 2, 3):
                    pb = self.pbs[f"f_{finger}_0{i}_{side}"]
                    z = pb.rotation_euler[2]
                    pb.rotation_euler = (math.radians(deg) * (1.0 + 0.1 * (i - 1)), 0.0, z)
        for name, M in Pp["def"].items():
            self.set_def(name, M)
        bpy.context.view_layer.update()
        for name, pb in self.pbs.items():
            self.def_m[name] = pb.matrix.copy()

    # ---------------- keying
    def key(self, f, force=False):
        for name in DEFORM_BONES:
            pb = self.pbs[name]
            loc = tuple(pb.location)
            rot = tuple(pb.rotation_euler)
            sc = tuple(pb.scale)
            if name in self.prev_euler:
                pe = self.prev_euler[name]
                rot = tuple(_unwrap(rot[i], pe[i]) for i in range(3))
                if rot != tuple(pb.rotation_euler):
                    pb.rotation_euler = rot
            cur = (loc, rot, sc)
            if not force and self.prev.get(name) == cur:
                continue
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_euler", frame=f)
            pb.keyframe_insert("scale", frame=f)
            self.prev[name] = cur
            self.prev_euler[name] = rot
        for k in SHAPE_KEYS:
            kb = self.sk.key_blocks[k]
            v = kb.value
            if f == 1 or force or self.prev_shape.get(k) != v:
                kb.keyframe_insert("value", frame=f)
                self.prev_shape[k] = v

    # ---------------- clip lifecycle
    def begin_clip(self, clip_id, n):
        for a in list(bpy.data.actions):
            if a.name == clip_id or a.name == clip_id + "_face":
                bpy.data.actions.remove(a)
        self.act = bpy.data.actions.new(clip_id)
        self.face_act = bpy.data.actions.new(clip_id + "_face")
        if self.A.animation_data is None:
            self.A.animation_data_create()
        self.A.animation_data.action = self.act
        if self.sk.animation_data is None:
            self.sk.animation_data_create()
        self.sk.animation_data.action = self.face_act
        self.clip_id = clip_id
        self.n = n
        self.markers = []

    def end_clip(self, n, markers, loop=False):
        self.act.use_fake_user = True
        self.face_act.use_fake_user = True
        try:
            self.act.frame_start = 1
            self.act.frame_end = n
            self.face_act.frame_start = 1
            self.face_act.frame_end = n
        except Exception:
            pass
        for name, frame, note in markers:
            m = self.act.pose_markers.new(name=name)
            m.frame = frame
        # unassign so the next clip's authoring is not driven by these fcurves
        self.A.animation_data.action = None
        self.sk.animation_data.action = None
        self.act = None
        self.face_act = None

    def marker(self, name, frame, note=""):
        self.markers.append((name, frame, note))


def _unwrap(v, prev):
    """Unwrap an euler component to within pi of the previous keyed value."""
    while v - prev > math.pi:
        v -= TWO_PI
    while v - prev < -math.pi:
        v += TWO_PI
    return v


# ------------------------------------------------------------------ body math
def body_matrices(rig, Pp):
    """Root/pelvis/chest/spine03 world matrices + shoulders from pose params."""
    rx, ry, rz = Pp["root"]
    M_root = rig.rest["root"] @ Matrix.Translation((rx, ry, rz))
    pel = Pp["pelvis"]
    w = Vector(Pp["w"]).normalized()
    pos = Vector((pel.get("x", 0.0), pel.get("y", 0.0), pel["z"])) + w * pel["shift"] + rig.root_off
    R_pel = (Matrix.Rotation(math.radians(pel["yaw"]), 4, 'Z')
             @ R_axis(w, pel["lean"])
             @ Matrix.Rotation(math.radians(pel["roll"]), 4, 'Y'))
    M_pel = Matrix.Translation(pos) @ R_pel @ rig.rest["pelvis"].to_3x3().to_4x4()
    M_chest_rigid = M_pel @ rig.rl["spine_01"] @ rig.rl["spine_02"]
    chest = Pp["chest"]
    R_extra = R_axis(w, chest["lean"]) @ Matrix.Rotation(math.radians(chest["yaw"]), 4, 'Z')
    M_chest = (Matrix.Translation(M_chest_rigid.to_translation())
               @ R_extra @ M_chest_rigid.to_3x3().to_4x4())
    M_spine03 = M_chest @ rig.rl["spine_03"]
    shoulders = {}
    for side in ("L", "R"):
        M_clav = M_spine03 @ rig.rl[f"clavicle_{side}"]
        shoulders[side] = (M_clav @ rig.rl[f"upper_arm_{side}"]).to_translation()
    return M_root, M_pel, M_chest, M_spine03, shoulders


def hip_pos(rig, side, M_pel):
    return (M_pel @ rig.rl[f"thigh_{side}"]).to_translation()


# ------------------------------------------------------------------ limbs
def build_leg(rig, side, leg, M_pel):
    th, sh, ft = f"thigh_{side}", f"shin_{side}", f"foot_{side}"
    R_foot = (Matrix.Rotation(math.radians(leg["yaw"]), 4, 'Z')
              @ Matrix.Rotation(math.radians(leg["pitch"]), 4, 'X')
              @ rig.rest[ft].to_3x3().to_4x4())
    rig.set_prop(f"toe_curl_{side}", leg["toe"])
    rig.set_prop(f"foot_roll_{side}", 0.0)
    rig.set_prop(f"roll_pivot_{side}", 0)
    if leg["mode"] == "fk":
        rig.set_prop(f"ik_fk_leg_{side}", 0.0)
        M_thigh = M_pel @ rig.rl[th]
        rig.set_ctrl(f"fk_{th}", M_thigh)
        M_shin = M_thigh @ rig.rl[sh]
        rig.set_ctrl(f"fk_{sh}", M_shin)
        if leg["ankle"] is not None:
            M_foot = Matrix.Translation(Vector(leg["ankle"])) @ R_foot
        else:
            M_foot = Matrix.Translation((M_shin @ rig.rl[ft]).to_translation()) @ R_foot
        rig.set_ctrl(f"fk_{ft}", M_foot)
        return
    rig.set_prop(f"ik_fk_leg_{side}", 1.0)
    A0 = (M_pel @ rig.rl[th]).to_translation()
    K0 = A0 + (rig.rest[sh].to_translation() - rig.rest[th].to_translation())
    F0 = A0 + (rig.rest[ft].to_translation() - rig.rest[th].to_translation())
    ankle = Vector(leg["ankle"])
    pole = Vector(leg["pole"])
    K_new, F_new = rig_ops.solve_2bone_ik(A0, K0, F0, ankle, pole)
    M_ik_shin = rig_ops.dir_pose_matrix(rig.rest[sh], F_new - K_new, K_new)
    basis = rig.rl[ft].inverted() @ M_ik_shin.inverted() @ R_foot
    rig.set_ctrl_basis(f"fk_{ft}", basis)
    rig.set_target(f"ik_foot_{side}", ankle)
    rig.set_target(f"pole_knee_{side}", pole)


def build_arm(rig, side, arm, M_spine03, shoulder):
    M_clav = M_spine03 @ rig.rl[f"clavicle_{side}"]
    rig.set_ctrl(f"fk_clavicle_{side}", M_clav)
    s = 1.0 if side == "L" else -1.0
    rig.set_prop(f"curl_{side}", arm["curl"])
    rig.set_prop(f"spread_{side}", arm["spread"])
    ua, fa, ha = (f"upper_arm_{side}", f"forearm_{side}", f"hand_{side}")
    mode = arm["mode"]
    if mode == "ik":
        rig.set_prop(f"ik_fk_arm_{side}", 1.0)
        E0 = shoulder + (rig.rest[fa].to_translation() - rig.rest[ua].to_translation())
        W0 = shoulder + (rig.rest[ha].to_translation() - rig.rest[ua].to_translation())
        target = Vector(arm["target"])
        pole = Vector(arm["pole"])
        R_hand = arm["hand_R"]
        E_new, T_new = rig_ops.solve_2bone_ik(shoulder, E0, W0, target, pole)
        M_ik_fore = rig_ops.dir_pose_matrix(rig.rest[fa], T_new - E_new, E_new)
        basis = rig.rl[ha].inverted() @ M_ik_fore.inverted() @ R_hand
        rig.set_ctrl_basis(f"fk_hand_{side}", basis)
        rig.set_target(f"ik_hand_{side}", target)
        rig.set_target(f"pole_elbow_{side}", pole)
        rig.arm_m[side] = {"clav": M_clav, "ua": None, "fa": M_ik_fore,
                           "hand": Matrix.Translation(T_new) @ R_hand}
        return
    rig.set_prop(f"ik_fk_arm_{side}", 0.0)
    if arm["forearm"] is not None:
        # exact forearm placement (emitter aiming): build the chain back from it
        M_fa = arm["forearm"]
        elbow = M_fa.to_translation()
        M_ua = rig_ops.dir_pose_matrix(rig.rest[ua], elbow - shoulder, shoulder)
        if arm["hand"] is not None and not isinstance(arm["hand"], (tuple, list)):
            # optional independent hand pose while the forearm stays pinned
            # (used by reload: the R hand catches the ejected cell)
            M_h = arm["hand"]
        else:
            M_h = M_fa @ rig.rl[ha]
    elif arm["hand"] is not None:
        h = arm["hand"]
        if isinstance(h, (tuple, list)) and len(h) == 3 and isinstance(h[0], str):
            # reference: ("ref_forearm", (x, y, z)) -> point on the R forearm frame
            ref = rig.arm_m["R"]["fa"] @ Vector(h[1])
            M_h = Matrix.Translation(ref) @ rig.arm_m["R"]["fa"].to_3x3().to_4x4()
        else:
            M_h = h
        wrist = M_h.to_translation()
        E0 = shoulder + (rig.rest[fa].to_translation() - rig.rest[ua].to_translation())
        W0 = shoulder + (rig.rest[ha].to_translation() - rig.rest[ua].to_translation())
        pole = Vector(arm["pole"]) if arm["pole"] is not None else \
            shoulder + Vector((0.0, -0.25, -0.35))
        E_new, T_new = rig_ops.solve_2bone_ik(shoulder, E0, W0, wrist, pole)
        M_ua = rig_ops.dir_pose_matrix(rig.rest[ua], E_new - shoulder, shoulder)
        M_fa = rig_ops.dir_pose_matrix(rig.rest[fa], T_new - E_new, E_new)
    else:
        # parametric FK: swing/lift/yaw about the shoulder, elbow/wrist bends
        w = Vector(arm["w"]).normalized()
        R_swing = (R_axis(w, arm["swing"])
                   @ Matrix.Rotation(math.radians(arm["lift"] * s), 4, 'Y')
                   @ Matrix.Rotation(math.radians(arm["yaw"]), 4, 'Z'))
        M_ua = Matrix.Translation(shoulder) @ R_swing @ rig.rest[ua].to_3x3().to_4x4()
        M_fa = (M_ua @ rig.rl[fa]) @ Matrix.Rotation(math.radians(arm["elbow"]), 4, 'X')
        M_h = (M_fa @ rig.rl[ha]) @ Matrix.Rotation(math.radians(arm["wrist"]), 4, 'X')
    rig.set_ctrl(f"fk_{ua}", M_ua)
    rig.set_ctrl(f"fk_{fa}", M_fa)
    rig.set_ctrl(f"fk_hand_{side}", M_h)
    rig.arm_m[side] = {"clav": M_clav, "ua": M_ua, "fa": M_fa, "hand": M_h}


def apply_pose(rig, Pp):
    """Set all controls/props for pose params Pp (does not bake)."""
    M_root, M_pel, M_chest, M_spine03, shoulders = body_matrices(rig, Pp)
    rig.set_ctrl("ctrl_root", M_root)
    rig.set_ctrl("ctrl_pelvis", M_pel)
    rig.set_ctrl("ctrl_chest", M_chest)
    rig.set_prop("look_auto", False)
    rig.set_prop("look_yaw", Pp["look"][0])
    rig.set_prop("look_pitch", Pp["look"][1])
    rig.set_prop("global_scale", Pp["scale"])
    for side in ("L", "R"):
        build_leg(rig, side, Pp["legs"][side], M_pel)
    for side in ("R", "L"):  # R first: the L arm may reference the R forearm
        build_arm(rig, side, Pp["arms"][side], M_spine03, shoulders[side])
    for k, v in Pp["face"].items():
        rig.set_prop(k, v)


# ------------------------------------------------------------------ aim construction
def aim_forearm_matrix(rig, yaw_deg, pitch_deg):
    """Forearm world rotation that makes the wrist emitter fire along (yaw, pitch).

    The emitter fires along FIRE_LOCAL, a fixed axis in forearm-local space that
    is almost but not exactly perpendicular to the forearm bone axis (+Y).
    Build the orthonormal firing frame (FIRE_LOCAL, bone axis projected perp to
    it, their cross product) and map it onto (d, most_down_perp(d), d x v): the
    result is a proper rotation sending FIRE_LOCAL exactly onto the aim
    direction, with the forearm axis as downward as the mounting allows.
    """
    d = dir_of(yaw_deg, pitch_deg)
    v = most_down_perp(d)
    e1 = rig.FIRE_LOCAL.normalized()
    y = Vector((0.0, 1.0, 0.0))
    e2 = (y - e1 * y.dot(e1)).normalized()
    e3 = e1.cross(e2)
    A = mat_cols(e1, e2, e3)
    B = mat_cols(d, v, d.cross(v))
    return B @ A.inverted()


def aim_arm_params(rig, side, shoulder, yaw_deg, pitch_deg, elbow_dir, curl=0.0, spread=0.0):
    """Arm params (mode 'fk') placing the wrist emitter on the aim line.

    elbow_dir: unit-ish direction from the shoulder to the elbow (the elbow is
    placed at shoulder + L1 * normalize(elbow_dir), so the chain closes exactly).
    """
    R = aim_forearm_matrix(rig, yaw_deg, pitch_deg)
    ed = Vector(elbow_dir).normalized()
    elbow = shoulder + ed * rig.arm_L1[side]
    M_fa = Matrix.Translation(elbow) @ R
    return {
        "mode": "fk", "forearm": M_fa, "curl": curl, "spread": spread,
        "w": (1.0, 0.0, 0.0), "swing": 0.0, "lift": 0.0, "yaw": 0.0,
        "elbow": 0.0, "wrist": 0.0, "hand": None, "target": None,
        "pole": None, "hand_R": None,
    }


def support_hand_params(rig, grip_M, curl=0.15):
    """Left-hand params gripping at world matrix grip_M (pose near the R wrist)."""
    return {
        "mode": "fk", "hand": grip_M, "curl": curl, "spread": 0.0,
        "w": (1.0, 0.0, 0.0), "swing": 0.0, "lift": 0.0, "yaw": 0.0,
        "elbow": 0.0, "wrist": 0.0, "forearm": None, "target": None,
        "pole": None, "hand_R": None,
    }


# ------------------------------------------------------------------ stances
def stance_legs(rig, M_pel, alpha=0.0, spread=0.06, mode="ik"):
    """Planted-stance leg params for both legs (feet spread `spread` beyond hips)."""
    u = dir_of(alpha, 0.0)
    right = Vector((M_pel.to_3x3() @ RIGHT))
    right.z = 0.0
    if right.length < 1e-6:
        right = RIGHT.copy()
    right.normalize()
    legs = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        hip = hip_pos(rig, side, M_pel)
        ankle = Vector((hip.x, hip.y, ANKLE_Z)) + right * (sgn * spread)
        pole = hip + u * 0.30 + Vector((0.0, 0.0, -0.25))
        legs[side] = {"mode": mode, "ankle": tuple(ankle), "yaw": alpha,
                      "pitch": 0.0, "toe": 0.0, "pole": tuple(pole)}
    return legs


def combat_pose(rig, pelvis_z=0.905, spread=0.075, lean=0.0, yaw=0.0, alpha=0.0):
    """Combat-ready standing pose params (IK legs, relaxed FK arms)."""
    Pp = P(pelvis__z=pelvis_z, pelvis__lean=lean, pelvis__yaw=yaw)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=alpha, spread=spread)
    for side in ("L", "R"):
        Pp["arms"][side] = {
            "mode": "fk_param", "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 6.0, "yaw": 0.0, "elbow": 16.0, "wrist": -8.0,
            "curl": 0.18, "spread": 0.05,
            "hand": None, "forearm": None, "target": None, "pole": None,
            "hand_R": None,
        }
    return Pp


def relaxed_pose(rig, pelvis_z=0.930, spread=0.0):
    """Relaxed standing pose (feet under hips, arms hanging)."""
    Pp = P(pelvis__z=pelvis_z)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=spread)
    for side in ("L", "R"):
        Pp["arms"][side] = {
            "mode": "fk_param", "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 3.0, "yaw": 0.0, "elbow": 12.0, "wrist": -5.0,
            "curl": 0.1, "spread": 0.0,
            "hand": None, "forearm": None, "target": None, "pole": None,
            "hand_R": None,
        }
    return Pp


# ------------------------------------------------------------------ gait
def gait_frame(rig, speed, alpha, f, face=None, pelvis_over=None, arm_over=None):
    """Pose params for frame f (1..n) of an 8-direction gait loop (seamless)."""
    g = GAIT[speed]
    n = g["n"]
    phi = TWO_PI * (f - 1) / n
    u = dir_of(alpha, 0.0)
    w = UP.cross(u)
    phi_mid = math.pi * g["stance"]
    s2pi = TWO_PI * g["stance"]
    heel_rise = 0.14 * math.sin(math.radians(g["heel"]))
    # ---- per-leg phase data.  The ankle target is hip.xy + u*along, so its
    # horizontal distance to the hip is exactly |along| regardless of the
    # pelvis height; that lets the pelvis height ride the reachability
    # ceiling below without circularity.
    legs_data = {}
    for side, off in (("L", 0.0), ("R", math.pi)):
        ph = (phi + off) % TWO_PI
        if ph < s2pi:  # stance: foot planted, travels backward at v_app
            t = ph / s2pi
            along = g["E"] / 2 - g["E"] * t
            hr = clamp((t - 0.75) / 0.25, 0.0, 1.0)
            heel = g["heel"] * smoothstep(hr)
            legs_data[side] = (along, ANKLE_Z + 0.14 * math.sin(math.radians(heel)),
                               heel, 0.7 * smoothstep(hr))
        else:          # swing: foot lifts and travels forward
            t = (ph - s2pi) / (TWO_PI * (1.0 - g["stance"]))
            along = -g["E"] / 2 + g["E"] * cosine_ease(t)
            # carry the toe-off heel rise over smoothly (no pop at lift-off)
            az = ANKLE_Z + g["lift"] * math.sin(math.pi * t) + heel_rise * (1.0 - t) ** 2
            legs_data[side] = (along, az, g["heel"] * (1.0 - t) - 72.0 * t * (1.0 - t), 0.0)
    shift = -g["shift"] * math.cos(phi - phi_mid)
    yaw = g["yaw_sway"] * math.sin(2.0 * phi)
    lean = g["lean"] + 1.5 * math.sin(phi)
    R_pel = Matrix.Rotation(math.radians(yaw), 4, 'Z') @ R_axis(w, lean)
    # ---- pelvis height: the highest safe value rides the tightest leg's
    # reachability ceiling.  Each leg's hip sits at pz + (R_pel @ thigh_off).z;
    # with a sideways lean the lateral thigh offset (+-0.105) rotates into z,
    # so the two hips differ in height by up to ~2*0.105*sin(lean) -- the
    # ceiling must use each leg's actual hip height, or the IK clamps.
    L = rig.leg_len
    pz = g["z_hi"]
    for side in ("L", "R"):
        along, az, _, _ = legs_data[side]
        hzoff = (R_pel @ rig.rl["thigh_%s" % side].to_translation()).z
        pz = min(pz, az + g["d_mid"] * math.sqrt(max(0.04, L * L - along * along)) - hzoff)
    if g["stance"] < 0.5:
        # flight phases: both feet off the ground
        if s2pi <= phi < math.pi:
            tf = (phi - s2pi) / (math.pi - s2pi)
        elif s2pi + math.pi <= phi < TWO_PI:
            tf = (phi - s2pi - math.pi) / (math.pi - s2pi)
        else:
            tf = None
        if tf is not None:
            pz += g["arc"] * math.sin(math.pi * tf)
    shift = -g["shift"] * math.cos(phi - phi_mid)
    yaw = g["yaw_sway"] * math.sin(2.0 * phi)
    lean = g["lean"] + 1.5 * math.sin(phi)
    Pp = P(pelvis__z=pz, pelvis__shift=shift, pelvis__yaw=yaw, pelvis__lean=lean, w=tuple(w))
    if pelvis_over:
        for k, v in pelvis_over.items():
            Pp["pelvis"][k] = v
    M_root, M_pel, M_chest, M_spine03, shoulders = body_matrices(rig, Pp)
    # ---- legs
    for side in ("L", "R"):
        along, az, pitch, toe = legs_data[side]
        hip = hip_pos(rig, side, M_pel)
        pole = hip + u * 0.30 + Vector((0.0, 0.0, -0.25))
        ankle = Vector((hip.x, hip.y, az)) + u * along
        Pp["legs"][side] = {"mode": "ik", "ankle": tuple(ankle), "yaw": alpha,
                            "pitch": pitch, "toe": toe, "pole": tuple(pole)}
    # ---- arms: contralateral swing
    amp_scale = 0.35 + 0.65 * abs(math.cos(math.radians(alpha)))
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        swing = sgn * g["arm_amp"] * amp_scale * math.cos(phi)
        Pp["arms"][side] = {
            "mode": "fk_param", "w": tuple(w), "swing": swing,
            "lift": 6.0, "yaw": 0.0, "elbow": g["elbow"] + 3.0 * math.sin(2.0 * phi),
            "wrist": -8.0, "curl": 0.15, "spread": 0.05,
            "hand": None, "forearm": None, "target": None, "pole": None,
            "hand_R": None,
        }
    if arm_over:
        for side in ("L", "R"):
            for k, v in arm_over.get(side, {}).items():
                Pp["arms"][side][k] = v
    # ---- chest counter-rotation, head look
    Pp["chest"] = {"lean": 1.0 + 0.8 * math.sin(phi), "yaw": -0.5 * yaw}
    Pp["look"] = (4.0 * math.sin(phi), 2.0 * math.sin(2.0 * phi))
    if face:
        Pp["face"] = face
    return Pp


def gait_markers(speed, alpha):
    """Foot contact/lift markers for one gait cycle (frames 1..n)."""
    g = GAIT[speed]
    n = g["n"]
    s2pi = TWO_PI * g["stance"]
    out = []
    for side, off, name in (("L", 0.0, "L"), ("R", math.pi, "R")):
        # stance spans ph in [0, s2pi): contact at ph=0, lift at ph=s2pi;
        # phi = 2*pi*(f-1)/n, so ph maps to f = 1 + round(ph/2pi * n) (mod n)
        f_contact = 1 + int(round((off % TWO_PI) / TWO_PI * n)) % n
        f_lift = 1 + int(round(((off + s2pi) % TWO_PI) / TWO_PI * n)) % n
        out.append((f"foot_{name}_contact", f_contact, "stance begins (heel strike)"))
        out.append((f"foot_{name}_lift", f_lift, "toe-off"))
    return out


# ------------------------------------------------------------------ shared pose helpers
def blink_bump(f, center, half=3.0):
    """A ~6-frame blink bump (0..1) centered at frame `center`."""
    d = abs(f - center)
    if d >= half:
        return 0.0
    return math.cos(math.pi * d / (2.0 * half)) ** 2


def breathing(f, n, amp_z=0.008, amp_shift=0.015, amp_lean=1.0, period=None):
    """Slow breathing oscillation for idle loops. Returns (dz, shift, lean_deg)."""
    per = period if period else n
    ph = TWO_PI * (f - 1) / per
    return amp_z * math.sin(ph), amp_shift * math.sin(ph), amp_lean * math.sin(ph)
