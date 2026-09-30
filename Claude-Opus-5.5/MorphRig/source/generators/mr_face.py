"""MorphRig facial shape keys (procedural displacement fields on the head mesh).

All shapes are authored for the left side and mirrored for the right using the
mesh's mirror pairs.  Lid shapes rotate about the eyeball centre (arcs) so the
lid margin slides over the eye instead of cutting into it.  Lip shapes are driven
by the explicit lip-ring parameterisation (ring index, upper/lower, position
along the mouth) so the closed contact line stays closed unless a shape is meant
to open it.  Visemes are combinations of the base shapes plus specific terms.
"""
import numpy as np
from mr_params import H, EYE_R, nrm, v
from mr_face_list import SHAPES, VISEMES


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def gauss(P, c, sig):
    q = (P - np.asarray(c)) / np.asarray(sig)
    return np.exp(-0.5 * (q * q).sum(-1))


def rot_about(P, center, axis, ang):
    """Rotate points about an axis through center by per-point angles."""
    axis = nrm(axis)
    X = P - center
    c = np.cos(ang)[:, None]
    s = np.sin(ang)[:, None]
    cross = np.cross(np.tile(axis, (len(P), 1)), X)
    dot = (X @ axis)[:, None]
    return center + X * c + cross * s + np.outer(dot[:, 0], axis) * (1 - c)


class FaceField:
    def __init__(self, m):
        self.m = m
        self.P = m.v.copy()
        self.n = len(self.P)
        g = m.groups
        z = np.zeros(self.n, bool)
        self.g = lambda name: g.get(name, z)
        self.M = H["mouth"].copy()
        self.W = H["mouth_half_width"]
        self.eye = H["eye_l"].copy()
        # lip ring bookkeeping
        self.ring = np.full(self.n, -1)
        for k in range(6):
            self.ring[self.g(f"lip_L{k}")] = k
        for k in range(1, 6):
            self.ring[self.g(f"mouth_in{k}")] = 10 + k
        self.up = np.zeros(self.n, bool)
        self.lo = np.zeros(self.n, bool)
        for k in range(6):
            self.up |= self.g(f"lip_L{k}_up")
            self.lo |= self.g(f"lip_L{k}_lo")
        for k in range(1, 6):
            self.up |= self.g(f"mouth_in{k}_up")
            self.lo |= self.g(f"mouth_in{k}_lo")
        self.corner = self.g("mouth_corner")
        self.bag = self.g("mouth_bag")
        rel = self.P - self.M
        self.rel = rel
        # position along the mouth, -1 right corner .. +1 left corner
        self.s = np.clip(rel[:, 0] / self.W, -1.6, 1.6)
        self.front = (self.P[:, 1] < 0.02)

    def mirror(self, D, pairs):
        """Mirror a left-side delta field to the right side."""
        out = np.zeros_like(D)
        ok = pairs >= 0
        idx = np.nonzero(ok)[0]
        out[idx] = D[pairs[idx]] * np.array([-1.0, 1.0, 1.0])
        return out

    # ------------------------------------------------------------ regions
    def mouth_region(self, rx=0.045, rz=0.032, ry=0.035):
        return gauss(self.P, self.M + v(0, 0.008, 0), (rx, ry, rz)) * self.front

    def left_corner_w(self, sig=(0.016, 0.02, 0.013)):
        c = self.M + v(self.W, 0.017, -0.001)
        return gauss(self.P, c, sig)

    def lips_side_w(self, side=1.0):
        return smoothstep((side * self.s + 0.15) / 1.15) ** 1.4

    # ------------------------------------------------------------ shapes (left)
    def browInnerUp(self):
        c = v(0.016, -0.086, 1.700)
        w = gauss(self.P, c, (0.013, 0.02, 0.016)) * self.front
        w *= smoothstep((self.P[:, 2] - 1.680) / 0.012)       # keep the upper lid margin
        D = np.zeros_like(self.P)
        D[:, 2] = 0.0085 * w
        D[:, 1] = -0.0012 * w
        D[:, 0] = 0.0008 * w
        return D

    def browOuterUp(self):
        c = v(0.043, -0.074, 1.701)
        w = gauss(self.P, c, (0.015, 0.02, 0.015)) * self.front
        w *= smoothstep((self.P[:, 2] - 1.682) / 0.012)
        D = np.zeros_like(self.P)
        D[:, 2] = 0.0072 * w
        return D

    def browDown(self):
        c = v(0.024, -0.083, 1.697)
        w = gauss(self.P, c, (0.022, 0.02, 0.013)) * self.front
        w *= smoothstep((self.P[:, 2] - 1.676) / 0.010)
        inner = gauss(self.P, v(0.012, -0.088, 1.694), (0.010, 0.02, 0.010))
        D = np.zeros_like(self.P)
        D[:, 2] = -0.0062 * w
        D[:, 1] = -0.0020 * w
        D[:, 0] = -0.0030 * inner
        # upper lid crease compresses slightly
        crease = self.g("lid_E_up_l") | self.g("lid_F_up_l")
        D[crease, 2] -= 0.0012
        return D

    def eyeSquint(self):
        """Lower lid rises along the eyeball (rotation), cheek pushes up underneath."""
        D = np.zeros_like(self.P)
        C = self.eye
        lat = v(-1.0, 0, 0)          # rotation axis so +angle lifts the front-lower points
        wmap = {"A": 1.0, "B": 1.0, "C": 0.95, "D": 0.8, "E": 0.45, "F": 0.15}
        for ring, wv in wmap.items():
            idx = np.nonzero(self.g(f"lid_{ring}_lo_l"))[0]
            if len(idx) == 0:
                continue
            ang = np.radians(9.0) * wv * np.ones(len(idx))
            newp = rot_about(self.P[idx], C, np.array([1.0, 0, 0]), -ang)
            D[idx] = newp - self.P[idx]
        cheek = gauss(self.P, v(0.036, -0.068, 1.652), (0.018, 0.02, 0.012)) * self.front
        cheek *= ~(self.g("lid_A_lo_l") | self.g("lid_B_lo_l") | self.g("lid_C_lo_l"))
        D[:, 2] += 0.0022 * cheek
        D[:, 1] -= 0.0010 * cheek
        # crow's feet compression at the outer corner
        oc = gauss(self.P, v(0.050, -0.060, 1.672), (0.008, 0.02, 0.010))
        D[:, 0] -= 0.0012 * oc
        return D

    def cheekRaise(self):
        c = v(0.037, -0.070, 1.640)
        w = gauss(self.P, c, (0.019, 0.022, 0.016)) * self.front
        lids = np.zeros(self.n, bool)
        for r in "ABCD":
            lids |= self.g(f"lid_{r}_lo_l") | self.g(f"lid_{r}_up_l")
        w[lids] = 0
        D = np.zeros_like(self.P)
        D[:, 2] = 0.0052 * w
        D[:, 1] = -0.0026 * w
        return D

    def cheekPuff(self):
        wl = gauss(self.P, v(0.040, -0.058, 1.612), (0.018, 0.02, 0.018)) * self.front
        D = np.zeros_like(self.P)
        D[:, 0] = 0.0055 * wl
        D[:, 1] = -0.0030 * wl
        # mirrored part added by caller as symmetric shape
        lips = self.ring >= 0
        D[lips & ~self.bag, 1] -= 0.0012 * smoothstep(1 - np.abs(self.s[lips & ~self.bag]))
        return D

    def noseSneer(self):
        c = v(0.016, -0.093, 1.636)
        w = gauss(self.P, c, (0.010, 0.02, 0.011)) * self.front
        D = np.zeros_like(self.P)
        D[:, 2] = 0.0032 * w
        D[:, 1] = -0.0006 * w
        # upper lip lateral part follows a little
        ul = self.up & (self.ring >= 2) & (self.ring <= 5)
        D[ul, 2] += 0.0012 * self.lips_side_w()[ul] * (1 - np.abs(self.s[ul] - 0.4))
        return D

    def mouthSmile(self):
        D = np.zeros_like(self.P)
        wc = self.left_corner_w((0.020, 0.024, 0.016))
        side = self.lips_side_w()
        lip = self.ring >= 0
        w = np.where(lip, side * np.maximum(wc, 0.35 * side), wc)
        w *= self.front | self.bag
        D[:, 0] += 0.0058 * w
        D[:, 1] += 0.0060 * w
        D[:, 2] += 0.0078 * w
        # nasolabial bulge lateral/above the corner
        nl = gauss(self.P, self.M + v(0.034, 0.004, 0.012), (0.012, 0.02, 0.016)) * self.front
        D[:, 1] -= 0.0030 * nl
        D[:, 2] += 0.0024 * nl
        return D

    def mouthFrown(self):
        D = np.zeros_like(self.P)
        wc = self.left_corner_w((0.016, 0.02, 0.018))
        side = self.lips_side_w()
        lip = self.ring >= 0
        w = np.where(lip, side * wc, wc) * (self.front | self.bag)
        D[:, 2] -= 0.0065 * w
        D[:, 0] += 0.0012 * w
        chin = gauss(self.P, self.M + v(0.022, 0.006, -0.024), (0.014, 0.02, 0.012)) * self.front
        D[:, 1] -= 0.0012 * chin
        return D

    def mouthStretch(self):
        D = np.zeros_like(self.P)
        wc = self.left_corner_w((0.022, 0.024, 0.015))
        side = self.lips_side_w()
        lip = self.ring >= 0
        w = np.where(lip, side * np.maximum(wc, 0.4 * side), wc) * (self.front | self.bag)
        D[:, 0] += 0.0055 * w
        D[:, 1] += 0.0020 * w
        D[:, 2] -= 0.0010 * w
        # vermilion thins
        th = lip & ~self.bag & (self.ring >= 1) & (self.ring <= 3)
        D[th & self.up, 2] -= 0.0010 * side[th & self.up]
        D[th & self.lo, 2] += 0.0010 * side[th & self.lo]
        return D

    def mouthPucker(self):
        D = np.zeros_like(self.P)
        wm = self.mouth_region(0.034, 0.026, 0.03)
        lip = self.ring >= 0
        # compress toward the centre laterally, push forward
        D[:, 0] = -0.38 * self.rel[:, 0] * wm
        D[:, 1] = -0.0060 * wm
        # lips thicken forward at the contact line, keep closed
        D[lip & ~self.bag, 1] -= 0.0020 * (1 - np.abs(self.s[lip & ~self.bag]) ** 2)
        return D

    def mouthFunnel(self):
        D = np.zeros_like(self.P)
        wm = self.mouth_region(0.034, 0.028, 0.03)
        lip = self.ring >= 0
        D[:, 0] = -0.22 * self.rel[:, 0] * wm
        D[:, 1] = -0.0050 * wm
        # open an O: upper lip up, lower lip down, strongest at the centre and inner rings
        prof = np.clip(1 - np.abs(self.s) ** 2, 0, 1)
        kfac = np.where(self.ring == 0, 1.0, np.where(self.ring == 1, 0.85, np.where(self.ring == 2, 0.6,
                        np.where(self.ring == 3, 0.35, np.where(self.ring >= 10, 0.9, 0.12)))))
        D[self.up, 2] += 0.0034 * (prof * kfac)[self.up]
        D[self.lo, 2] -= 0.0036 * (prof * kfac)[self.lo]
        # inner surfaces flare outward (visible funnel)
        inn = self.ring >= 10
        D[inn & self.up, 1] -= 0.0015
        D[inn & self.lo, 1] -= 0.0015
        return D

    def mouthPress(self):
        D = np.zeros_like(self.P)
        lip = (self.ring >= 0) & (self.ring <= 3)
        prof = np.clip(1 - np.abs(self.s) ** 3, 0, 1)
        D[lip & self.up, 2] -= 0.0012 * prof[lip & self.up]
        D[lip & self.lo, 2] += 0.0012 * prof[lip & self.lo]
        D[lip, 1] += 0.0010 * prof[lip]
        return D

    def mouthRoll(self, upper=True):
        D = np.zeros_like(self.P)
        sel = self.up if upper else self.lo
        sgn = 1.0 if upper else -1.0
        prof = np.clip(1 - np.abs(self.s) ** 2.5, 0, 1)
        for k, (dz, dy) in enumerate([(0.0, 0.0030), (-0.0020, 0.0038), (-0.0038, 0.0030), (-0.0030, 0.0018),
                                      (-0.0010, 0.0006), (0.0, 0.0)]):
            idx = sel & (self.ring == k)
            D[idx, 2] += sgn * dz * prof[idx]
            D[idx, 1] += dy * prof[idx]
        for k in range(1, 4):
            idx = sel & (self.ring == 10 + k)
            D[idx, 1] += 0.0025 * prof[idx]
        return D

    def mouthUpperUp(self):
        D = np.zeros_like(self.P)
        side = self.lips_side_w()
        prof = side * np.clip(1.2 - np.abs(self.s - 0.45), 0, 1)
        kf = {0: 1.0, 1: 1.0, 2: 0.95, 3: 0.85, 4: 0.6, 5: 0.3, 11: 0.9, 12: 0.6}
        for k, f in kf.items():
            idx = self.up & (self.ring == k)
            D[idx, 2] += 0.0042 * f * prof[idx]
            D[idx, 1] -= 0.0008 * f * prof[idx]
        skin = gauss(self.P, self.M + v(0.014, 0.0, 0.017), (0.012, 0.02, 0.008)) * self.front * (self.ring < 0)
        D[:, 2] += 0.0020 * skin
        return D

    def mouthLowerDown(self):
        D = np.zeros_like(self.P)
        side = self.lips_side_w()
        prof = side * np.clip(1.2 - np.abs(self.s - 0.4), 0, 1)
        kf = {0: 1.0, 1: 1.0, 2: 0.95, 3: 0.85, 4: 0.6, 5: 0.3, 11: 0.9, 12: 0.6}
        for k, f in kf.items():
            idx = self.lo & (self.ring == k)
            D[idx, 2] -= 0.0045 * f * prof[idx]
            D[idx, 1] -= 0.0010 * f * prof[idx]
        skin = gauss(self.P, self.M + v(0.012, 0.004, -0.02), (0.012, 0.02, 0.009)) * self.front * (self.ring < 0)
        D[:, 2] -= 0.0018 * skin
        return D

    def mouthClose(self):
        """Corrective for an open jaw: brings the lips together (upper down, lower up)."""
        D = np.zeros_like(self.P)
        prof = np.clip(1 - np.abs(self.s) ** 2.5, 0, 1)
        kf = {0: 1.0, 1: 1.0, 2: 0.9, 3: 0.7, 4: 0.4, 5: 0.15, 11: 0.8, 12: 0.5}
        for k, f in kf.items():
            iu = self.up & (self.ring == k)
            il = self.lo & (self.ring == k)
            D[iu, 2] -= 0.0030 * f * prof[iu]
            D[il, 2] += 0.0068 * f * prof[il]
            D[il, 1] -= 0.0020 * f * prof[il]
        return D

    def mouthShift(self, direction=1.0):
        D = np.zeros_like(self.P)
        wm = self.mouth_region(0.036, 0.03, 0.03)
        D[:, 0] = 0.0060 * direction * wm
        D[:, 1] = 0.0012 * np.abs(self.rel[:, 0]) / 0.03 * wm * 0
        return D


def build_shapes(m, pairs):
    """Return ordered dict name -> delta (n,3)."""
    F = FaceField(m)
    out = {}

    def lr(name, D):
        out[name + "_L"] = D
        out[name + "_R"] = F.mirror(D, pairs)

    lr("browInnerUp", F.browInnerUp())
    lr("browOuterUp", F.browOuterUp())
    lr("browDown", F.browDown())
    lr("eyeSquint", F.eyeSquint())
    lr("cheekRaise", F.cheekRaise())
    cp = F.cheekPuff()
    out["cheekPuff"] = cp + F.mirror(cp, pairs)
    lr("noseSneer", F.noseSneer())
    lr("mouthSmile", F.mouthSmile())
    lr("mouthFrown", F.mouthFrown())
    lr("mouthStretch", F.mouthStretch())
    out["mouthPucker"] = F.mouthPucker()
    out["mouthFunnel"] = F.mouthFunnel()
    out["mouthPress"] = F.mouthPress()
    out["mouthRollUpper"] = F.mouthRoll(True)
    out["mouthRollLower"] = F.mouthRoll(False)
    lr("mouthUpperUp", F.mouthUpperUp())
    lr("mouthLowerDown", F.mouthLowerDown())
    out["mouthClose"] = F.mouthClose()
    out["mouthLeft"] = F.mouthShift(1.0)
    out["mouthRight"] = F.mouthShift(-1.0)

    def combo(weights, extra=None):
        D = np.zeros_like(F.P)
        for k, w in weights.items():
            D += out[k] * w
        if extra is not None:
            D += extra
        return D

    both = lambda n, w: {n + "_L": w, n + "_R": w}
    # visemes (jaw opening is the jaw bone; see mr_face_list.VISEME_JAW_DEG)
    fv = np.zeros_like(F.P)
    prof = np.clip(1 - np.abs(F.s) ** 2.2, 0, 1)
    for k, (dz, dy) in enumerate([(0.0030, 0.0050), (0.0034, 0.0052), (0.0030, 0.0040), (0.0020, 0.0022),
                                  (0.0008, 0.0008)]):
        idx = F.lo & (F.ring == k)
        fv[idx, 2] += dz * prof[idx]
        fv[idx, 1] += dy * prof[idx]
    out["V_MBP"] = combo({"mouthPress": 1.0, "mouthRollUpper": 0.15, "mouthRollLower": 0.25, "mouthClose": 0.25})
    out["V_FV"] = combo({**both("mouthUpperUp", 0.25)}, fv)
    out["V_TH"] = combo({"mouthFunnel": 0.1, **both("mouthStretch", 0.1)})
    out["V_LNT"] = combo({**both("mouthStretch", 0.12), "mouthFunnel": 0.05})
    out["V_SS"] = combo({**both("mouthStretch", 0.35), **both("mouthUpperUp", 0.25), **both("mouthLowerDown", 0.3)})
    out["V_CH"] = combo({"mouthFunnel": 0.55, "mouthPucker": 0.25, **both("mouthUpperUp", 0.15)})
    out["V_KG"] = combo({**both("mouthStretch", 0.15), **both("mouthLowerDown", 0.1)})
    out["V_R"] = combo({"mouthPucker": 0.35, "mouthFunnel": 0.3})
    out["V_AA"] = combo({**both("mouthStretch", 0.1), **both("mouthUpperUp", 0.12), **both("mouthLowerDown", 0.25)})
    out["V_EH"] = combo({**both("mouthStretch", 0.3), **both("mouthLowerDown", 0.15)})
    out["V_EE"] = combo({**both("mouthStretch", 0.55), **both("mouthSmile", 0.15), **both("mouthUpperUp", 0.12)})
    out["V_IH"] = combo({**both("mouthStretch", 0.35), **both("mouthLowerDown", 0.1)})
    out["V_OH"] = combo({"mouthFunnel": 0.65, "mouthPucker": 0.25})
    out["V_OO"] = combo({"mouthPucker": 0.9, "mouthFunnel": 0.35})
    for k in list(out):
        assert k in SHAPES or k in VISEMES, k
    return out


def apply_shape_keys(obj, deltas):
    import bpy
    me = obj.data
    if me.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    base = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", base)
    base = base.reshape(-1, 3)
    for name, D in deltas.items():
        kb = obj.shape_key_add(name=name, from_mix=False)
        kb.data.foreach_set("co", (base + D).ravel())
        kb.slider_min = 0.0
        kb.slider_max = 1.0
        kb.value = 0.0          # neutral until driven by the rig's face controls
    return obj
