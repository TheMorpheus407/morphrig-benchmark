"""MorphRig animation infrastructure.

Provides:
  * `Rig`    - rest matrices, hierarchy order and parent lookup
  * `Pose`   - a hierarchical pose builder that resolves to Blender bone
                bases (and to facial shape key values)
  * `bake`   - turns a pose function into a real Blender action with
                keyframes on the deformation skeleton, shape key curves and
                timeline markers

Authoring conventions
---------------------
* Blender units are metres, the character faces -Y and up is +Z.
* Rotations are given as (world axis, degrees) and are applied to the bone's
  rest orientation, so a pose reads the same way it would in a DCC tool.
* Translations are world-space offsets applied to the bone head.
"""

import math

from mathutils import Vector, Matrix, Quaternion

TAU = math.pi * 2.0
D2R = math.pi / 180.0
FPS = 30


# ---------------------------------------------------------------------------
# rig access
# ---------------------------------------------------------------------------

class Rig:
    """Rest data of the deformation skeleton."""

    def __init__(self, arm_obj):
        self.arm = arm_obj
        self.rest = {}
        self.parent = {}
        self.order = []
        for b in arm_obj.data.bones:
            self.rest[b.name] = b.matrix_local.copy()
            self.parent[b.name] = b.parent.name if b.parent else None
        # parents before children
        done = set()
        remaining = list(self.rest.keys())
        while remaining:
            progressed = False
            for name in list(remaining):
                p = self.parent[name]
                if p is None or p in done:
                    self.order.append(name)
                    done.add(name)
                    remaining.remove(name)
                    progressed = True
            if not progressed:
                raise RuntimeError("cycle in bone hierarchy")
        self.deform = [b.name for b in arm_obj.data.bones if b.use_deform]
        self.armature = arm_obj.data

    def chain(self, name):
        """(parent world matrix, parent rest, bone rest) for the given bone."""
        bone = self.rest[name]
        p = self.parent[name]
        if p is None:
            return None, None, bone
        return p, self.rest[p], bone


# ---------------------------------------------------------------------------
# pose builder
# ---------------------------------------------------------------------------

def _rot_matrix(rots):
    """Combine [(axis, degrees)] into a 3x3 matrix (applied in order)."""
    m = Matrix.Identity(3)
    for axis, ang in rots:
        m = Quaternion(Vector(axis).normalized(),
                       ang * D2R).to_matrix() @ m
    return m


class Pose:
    """A hierarchical pose.

    Authoring is order independent: every bone stores its *intent* (which
    rotations, translation and scale) and the world matrices are rebuilt from
    the hierarchy whenever they are needed.  Re-posing the pelvis after the
    arms therefore still rotates the arms with the torso.

    `bone(name, *rots)` rotates the bone about world axes, pivoting on the
    bone head; `bone(name, local=...)` rotates inside the bone's own frame.
    """

    def __init__(self, rig):
        self.rig = rig
        self.specs = {}
        self.shape = {}
        self.scl = {}
        self._cache = None

    # -- authoring ----------------------------------------------------------
    def bone(self, name, *rots, **kw):
        """Pose a bone.

        `rots` are (world axis, degrees) pairs.  The bone's orientation
        changes by that world-space rotation while its head stays put.
        Keyword arguments: `trans` (world offset of the bone head), `scale`
        (local scale), `local` (rotations inside the bone's own rest frame
        instead of world axes).
        """
        if name not in self.rig.rest:
            raise KeyError("unknown bone %r" % name)
        self.specs[name] = {
            "rots": tuple(rots),
            "local": kw.get("local"),
            "trans": tuple(kw.get("trans", (0.0, 0.0, 0.0))),
            "scale": kw.get("scale"),
        }
        self._cache = None
        return self

    def bone_local(self, name, *rots, **kw):
        """Pose a bone with rotations inside its own rest frame."""
        return self.bone(name, local=rots, **kw)

    def face(self, **kwargs):
        """Set facial shape key values (0..1, negative allowed)."""
        for k, v in kwargs.items():
            self.shape[k] = float(v)
        return self

    def blade(self, amount):
        """Extend / retract the forearm blade by scaling its bone."""
        return self.bone("blade_r", scale=(1.0, amount, 1.0))

    # -- resolution ---------------------------------------------------------
    def _build(self):
        """Rebuild world + basis matrices from the authored intent."""
        if self._cache is not None:
            return self._cache
        rig = self.rig
        eff = {}
        world = {}
        basis = {}
        for name in rig.order:
            pname, prest, brest = rig.chain(name)
            if pname is None:
                chain = brest.copy()
            else:
                chain = eff[pname] @ prest.inverted() @ brest
            spec = self.specs.get(name)
            if spec is None:
                eff[name] = chain
                continue
            if spec["local"] is not None:
                # rotation inside the bone's own frame
                B = _rot_matrix(spec["local"]).to_4x4()
                if spec["scale"] is not None:
                    B = B @ Matrix.Diagonal(Vector((spec["scale"][0],
                                                    spec["scale"][1],
                                                    spec["scale"][2], 1.0)))
                M = chain @ B
            else:
                # rotation about world axes, pivoting on the bone head
                rot = chain.to_3x3()
                if spec["rots"]:
                    rot = _rot_matrix(spec["rots"]) @ rot
                M = Matrix.Translation(chain.translation) @ rot.to_4x4()
                if spec["scale"] is not None:
                    M = M @ Matrix.Diagonal(Vector((spec["scale"][0],
                                                    spec["scale"][1],
                                                    spec["scale"][2], 1.0)))
            trans = spec["trans"]
            if any(abs(c) > 1e-12 for c in trans):
                M.translation = M.translation + Vector(trans)
            eff[name] = M
            world[name] = M
            basis[name] = chain.inverted() @ M
        self._cache = (world, basis)
        return self._cache

    @property
    def world(self):
        """World (armature space) matrix of every authored bone."""
        return self._build()[0]

    def resolve(self):
        """Return (basis dict, shape dict) ready for keyframing."""
        world, basis = self._build()
        return basis, dict(self.shape)


# ---------------------------------------------------------------------------
# convenience pose helpers
# ---------------------------------------------------------------------------

def side_of(s):
    return 1 if s == "r" else -1


def stance(p, combat=False, weight=0.0):
    """Neutral standing pose; `combat` adds a ready stance."""
    for s in ("r", "l"):
        sd = side_of(s)
        if combat:
            p.bone("thigh_%s" % s, ((1, 0, 0), -7.0), ((0, 1, 0), -4.0 * sd))
            p.bone("calf_%s" % s, ((1, 0, 0), 9.0))
            p.bone("foot_%s" % s, ((1, 0, 0), -2.0))
            p.bone("upperarm_%s" % s, ((1, 0, 0), -18.0),
                   ((0, 1, 0), -14.0 * sd))
            p.bone("lowerarm_%s" % s, ((1, 0, 0), -38.0))
            p.bone("hand_%s" % s, ((1, 0, 0), -10.0))
        else:
            p.bone("thigh_%s" % s, ((1, 0, 0), -4.0), ((0, 1, 0), -2.0 * sd))
            p.bone("calf_%s" % s, ((1, 0, 0), 5.0))
            p.bone("foot_%s" % s, ((1, 0, 0), -1.0))
            p.bone("upperarm_%s" % s, ((1, 0, 0), -5.0),
                   ((0, 1, 0), -6.0 * sd))
            p.bone("lowerarm_%s" % s, ((1, 0, 0), -14.0))
            p.bone("hand_%s" % s, ((1, 0, 0), -4.0))
    if weight:
        p.bone("pelvis", trans=(0.0, 0.0, -weight))
    return p


def breathe(p, t, amount=1.0, phase=0.0):
    """Chest / spine breathing cycle (t is the normalised clip time)."""
    a = math.sin(TAU * t + phase)
    b = math.sin(TAU * t + phase + 0.9)
    p.bone("spine_02", ((1, 0, 0), -1.6 * amount * b))
    p.bone("spine_03", ((1, 0, 0), -2.0 * amount * a))
    p.bone("chest", ((1, 0, 0), -2.4 * amount * a))
    p.bone("neck_01", ((1, 0, 0), 1.2 * amount * a))
    return p


def look_at(p, yaw=0.0, pitch=0.0, eye=1.0, eye_yaw=0.0, eye_pitch=0.0):
    """Aim the head and (optionally) the eyes.

    yaw is positive to the character's right, pitch positive is down.
    """
    p.bone("head", ((0, 0, 1), yaw), ((1, 0, 0), pitch))
    if eye:
        p.bone("eye_l", ((0, 0, 1), eye_yaw), ((1, 0, 0), eye_pitch))
        p.bone("eye_r", ((0, 0, 1), eye_yaw), ((1, 0, 0), eye_pitch))
    return p


def blink(p, amount=1.0):
    """Close the eyelids by `amount` (0 open, 1 closed)."""
    a = 52.0 * amount
    b = 25.0 * amount
    p.bone("eyelid_upper_l", ((1, 0, 0), a))
    p.bone("eyelid_upper_r", ((1, 0, 0), a))
    p.bone("eyelid_lower_l", ((1, 0, 0), -b))
    p.bone("eyelid_lower_r", ((1, 0, 0), -b))
    return p


def brows(p, up_l=0.0, up_r=0.0, down_l=0.0, down_r=0.0):
    p.bone("brow_l", ((1, 0, 0), -8.0 * up_l + 9.0 * down_l))
    p.bone("brow_r", ((1, 0, 0), -8.0 * up_r + 9.0 * down_r))
    return p


def squint(p, amount=0.0):
    """Squint: the lower lid rises and the cheek under the eye pushes up.

    `amount` is 0 (open) to 1 (a hard squint).  The lids are driven on their
    own bones so left and right can be split by the caller, the skin
    response is the `squint` shape key.
    """
    a = max(0.0, min(1.0, amount))
    p.bone("eyelid_lower_l", ((1, 0, 0), -9.0 * a))
    p.bone("eyelid_lower_r", ((1, 0, 0), -9.0 * a))
    p.face(squint=a * 0.85, cheek_raise_l=a * 0.45, cheek_raise_r=a * 0.45)
    return p


def jaw(p, amount=0.0, side=0.0):
    """Open the jaw (0..1) with a slight sideways shift."""
    p.bone("jaw", ((1, 0, 0), -12.0 * amount), ((0, 0, 1), 4.0 * side))
    return p


def finger_curl(p, s, curl=0.0, spread=0.0, thumb=0.0):
    """Curl / spread the fingers of one hand.

    The curl is a rotation inside each phalanx's own frame, so it
    accumulates correctly down the chain.
    """
    segs = (0.42, 0.33, 0.25)
    for fname in ("index", "middle", "ring", "pinky"):
        total = curl
        if fname == "index":
            total = curl
        for i, frac in enumerate(segs):
            amt = total * frac * 78.0
            if fname == "thumb":
                amt = thumb * frac * 70.0
            p.bone_local("finger_%s_%02d_%s" % (fname, i + 1, s),
                         ((1, 0, 0), amt))
    if spread:
        for fname in ("index", "middle", "ring", "pinky"):
            amt = spread * 14.0
            p.bone_local("finger_%s_01_%s" % (fname, s), ((0, 0, 1), amt))
    return p


def arm(p, s, pitch=0.0, yaw=0.0, roll=0.0, elbow=0.0, wrist=0.0,
        wrist_roll=0.0):
    """Pose one arm.

    pitch  + swings the arm forward
    yaw    + swings the arm away from the body
    elbow  + bends the elbow (hand travels forward)
    """
    sd = side_of(s)
    p.bone("upperarm_%s" % s, ((1, 0, 0), -pitch),
           ((0, 1, 0), -yaw * sd), ((0, 0, 1), roll))
    p.bone("lowerarm_%s" % s, ((1, 0, 0), -elbow))
    p.bone("hand_%s" % s, ((1, 0, 0), -wrist), ((0, 0, 1), wrist_roll))
    return p


def arm_world(p, s, pitch=0.0, yaw=0.0, roll=0.0, elbow=0.0, wrist=0.0,
              wrist_roll=0.0):
    """Arm pose that ignores the parent's rotation (world aligned)."""
    sd = side_of(s)
    p.bone("clavicle_%s" % s, ((1, 0, 0), -pitch * 0.25),
           ((0, 1, 0), -yaw * sd * 0.35))
    p.bone("upperarm_%s" % s, ((1, 0, 0), -pitch * 0.75),
           ((0, 1, 0), -yaw * sd * 0.65), ((0, 0, 1), roll))
    p.bone("lowerarm_%s" % s, ((1, 0, 0), -elbow))
    p.bone("hand_%s" % s, ((1, 0, 0), -wrist), ((0, 0, 1), wrist_roll))
    return p


def leg(p, s, hip=0.0, hip_yaw=0.0, knee=0.0, ankle=0.0, toe=0.0,
        heel=0.0):
    """Pose one leg.

    hip  + swings the leg forward
    knee + bends the knee (heel towards the back)
    """
    sd = side_of(s)
    p.bone("thigh_%s" % s, ((1, 0, 0), -hip), ((0, 1, 0), -hip_yaw * sd))
    p.bone("calf_%s" % s, ((1, 0, 0), knee))
    p.bone("foot_%s" % s, ((1, 0, 0), -ankle))
    p.bone("ball_%s" % s, ((1, 0, 0), -toe))
    p.bone("heel_%s" % s, ((1, 0, 0), heel))
    return p


def pelvis_shift(p, side=0.0, forward=0.0, up=0.0, rot=0.0):
    p.bone("pelvis", ((0, 0, 1), rot), trans=(side, forward, up))
    return p


# ---------------------------------------------------------------------------
# baking
# ---------------------------------------------------------------------------

def _new_action(owner, name):
    """Create a fresh action on `owner` (armature object or shape keys)."""
    if owner.animation_data is None:
        owner.animation_data_create()
    act = bpy_actions_new(owner, name)
    owner.animation_data.action = act
    return act


def bpy_actions_new(owner, name):
    import bpy
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    return act


def reset_pose(arm_obj):
    """Return every deform bone to its rest transform."""
    for pb in arm_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def bake(rig, arm_obj, mesh_obj, clip, scene, fcurve_step=1):
    """Bake a clip into a Blender action.

    Every bone the clip ever touches is keyed on every frame, so the baked
    action fully determines the pose and does not inherit leftovers from a
    previously baked clip.  Bones the clip never touches keep their rest
    transform.

    Returns a dict describing the baked clip (frame range, markers, ...).
    """
    import bpy
    name = clip["name"]
    frames = clip["frames"]
    fn = clip["fn"]

    # --- evaluate the whole clip first so we know which channels to write
    poses = []
    authored = set()
    shape_keys = set()
    for f in range(1, frames + 1):
        t = (f - 1) / float(frames)
        pose = fn(t, rig)
        poses.append(pose)
        authored.update(pose.specs.keys())
        shape_keys.update(pose.shape.keys())

    reset_pose(arm_obj)
    arm_act = _new_action(arm_obj, "ACT_%s" % name)
    sk_act = None
    sk = None
    if mesh_obj is not None and mesh_obj.data.shape_keys is not None:
        sk = mesh_obj.data.shape_keys
        for block in sk.key_blocks:
            block.value = 0.0
        sk_act = _new_action(sk, "ACT_%s_face" % name)

    ident = Matrix.Identity(4)

    # resolve every pose once, the closing frame reuses one of them
    resolved = [pose.resolve() for pose in poses]

    def write_frame(index, f):
        basis, shapes = resolved[index]
        for bname in authored:
            mat = basis.get(bname, ident)
            pb = arm_obj.pose.bones[bname]
            loc, rot, sc = mat.decompose()
            pb.location = loc
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = rot
            pb.scale = sc
            if fcurve_step == 1 or f % fcurve_step == 0:
                pb.keyframe_insert("location", frame=f)
                pb.keyframe_insert("rotation_quaternion", frame=f)
                pb.keyframe_insert("scale", frame=f)
        if sk_act is not None:
            for key in shape_keys:
                val = shapes.get(key, 0.0)
                kb = sk.key_blocks.get(key)
                if kb is None:
                    continue
                kb.value = val
                if fcurve_step == 1 or f % fcurve_step == 0:
                    kb.keyframe_insert("value", frame=f)

    for idx in range(len(poses)):
        write_frame(idx, idx + 1)

    # A closing key makes the clip exactly as long as its authored duration
    # once it is imported: Unreal derives the length of a sequence from the
    # number of keys, so N + 1 keys give N / frame rate.  A looping clip
    # closes with the pose of its first frame, which makes the loop seamless,
    # a one shot closes with its last pose, which holds the end for a frame.
    write_frame(0 if clip.get("loop", False) else len(poses) - 1, frames + 1)

    # timeline markers (Blender 5.x calls them pose markers)
    for mname, mframe in clip.get("markers", []):
        mk = arm_act.pose_markers.new(mname)
        mk.frame = int(mframe)

    # make the action cyclic friendly and set the interpolation
    _set_interpolation(arm_act, clip.get("interp", "BEZIER"))
    if sk_act is not None:
        _set_interpolation(sk_act, clip.get("interp", "BEZIER"))

    return dict(name=name, action=arm_act.name, face_action=(
        sk_act.name if sk_act else None),
        frames=frames, start=1, end=frames + 1,
        duration=round(frames / float(FPS), 4), loop=clip.get("loop", False),
        form=clip.get("form", "one_shot"),
        markers=list(clip.get("markers", [])),
        root_motion=clip.get("root_motion", "in_place"),
        speed=clip.get("speed", 0.0),
        bones_baked=len(authored),
        face_keys_baked=len(shape_keys),
        closing_key=True)


def _set_interpolation(action, mode):
    """Set the key interpolation of every curve in a slotted action."""
    if action is None:
        return
    try:
        layers = action.layers
    except AttributeError:
        return
    for layer in layers:
        for strip in layer.strips:
            bags = getattr(strip, "channelbags", None)
            if bags is None:
                continue
            for bag in bags:
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = mode
                    fc.update()


def action_fcurves(action):
    """All fcurves of a (slotted) action."""
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out
