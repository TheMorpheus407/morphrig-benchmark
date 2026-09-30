"""MorphRig teeth, gums and tongue (separate mesh MR_Mouth).

Upper teeth + upper gum follow the head, lower teeth + lower gum follow the jaw,
the tongue is skinned to tongue_01..03 (root blended to the jaw).
"""
import numpy as np
from mr_sdf import Ellipsoid, Union, Capsule, RoundBox, normalize
from mr_meshkit import Mesh, make_consistent
from mr_gear import box_mesh, sdf_blob, tube, merge
from mr_params import H, v

# (half width along arch, crown height, thickness) per tooth from the centre outward
UPPER = [(0.0043, 0.0102, 0.0068), (0.0034, 0.0088, 0.0060), (0.0038, 0.0096, 0.0072), (0.0035, 0.0078, 0.0080),
         (0.0034, 0.0072, 0.0085)]
LOWER = [(0.0027, 0.0090, 0.0058), (0.0029, 0.0088, 0.0060), (0.0034, 0.0094, 0.0068), (0.0034, 0.0078, 0.0076),
         (0.0035, 0.0074, 0.0082)]


def arch(x, front_y, depth_k=26.0):
    """Parabolic dental arch: y rises (goes back) with x^2."""
    return front_y + depth_k * x * x


def build_row(teeth, front_y, edge_z, upper=True, scale_x=1.0, k=26.0):
    """Teeth placed by arc length along the parabolic arch (both sides)."""
    xs = np.linspace(0, 0.04, 400)
    ys = front_y + k * xs * xs
    seg = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    arc = np.concatenate([[0], np.cumsum(seg)])
    parts = []
    acc = 0.0
    for i, (hw, h, th) in enumerate(teeth):
        cs = (acc + hw) * scale_x
        acc += 2 * hw + 0.0002
        cx = float(np.interp(cs, arc, xs))
        for sgn in (1.0, -1.0):
            px = sgn * cx
            py = front_y + k * px * px
            dy = 2 * k * px
            t = normalize(np.array([1.0, dy, 0.0]))
            back = normalize(np.array([-dy, 1.0, 0.0]))
            cz = edge_z + (h / 2 if upper else -h / 2)
            c = np.array([px, py, cz]) + back * th * 0.45
            R = np.stack([t, -back, np.array([0, 0, 1.0])], 1)
            tooth = box_mesh(c, np.array([hw * 0.96, th / 2, h / 2]), rot=R, bevel=min(hw, th / 2) * 0.55, n=3)
            make_consistent(tooth, outward_point=c)
            parts.append(tooth)
    return merge(parts)


def build_gum(front_y, z0, z1, upper=True, half_w=0.0205):
    xs = np.linspace(-half_w, half_w, 17)
    path = [np.array([x, arch(x, front_y) + 0.0032, 0.5 * (z0 + z1)]) for x in xs]
    radii = [(0.0034, abs(z1 - z0) / 2)] * len(xs)
    g = tube(path, radii, n=10, closed_ends=(True, True), ref=(0, 0, 1))
    return g


def build_tongue():
    tip = v(0, -0.0745, 1.5975)
    back = v(0, -0.030, 1.590)
    sdf = Union([
        Ellipsoid(0.5 * (tip + back) + v(0, 0, -0.001), (0.0215, 0.0250, 0.0072), axis=tip - back, hint=(0, 0, 1)),
        Ellipsoid(tip + v(0, 0.010, -0.0005), (0.0150, 0.0130, 0.0055)),
        Ellipsoid(back + v(0, 0.006, -0.004), (0.020, 0.012, 0.010)),
    ], k=0.006)
    m = sdf_blob(sdf, 0.5 * (tip + back) + v(0, 0, -0.001), n=8, stretch=(1.0, 2.2, 0.5), relax=4)
    return m


def build_mouth():
    """Returns Mesh with groups: teeth_upper, teeth_lower, gum_upper, gum_lower, tongue."""
    M = H["mouth"]
    ut = build_row(UPPER, front_y=M[1] + 0.0118, edge_z=M[2] - 0.0014, upper=True)
    lt = build_row(LOWER, front_y=M[1] + 0.0152, edge_z=M[2] + 0.0006, upper=False, scale_x=0.94)
    ug = build_gum(M[1] + 0.0120, M[2] + 0.0085, M[2] + 0.0150, upper=True)
    lg = build_gum(M[1] + 0.0155, M[2] - 0.0142, M[2] - 0.0078, upper=False, half_w=0.0195)
    tg = build_tongue()
    out = Mesh()
    for name, part in (("teeth_upper", ut), ("teeth_lower", lt), ("gum_upper", ug), ("gum_lower", lg),
                       ("tongue", tg)):
        off = out.append(part)
        g = out.group(name)
        g[off:off + part.nv] = True
    return out


def mouth_weights(m, bones):
    from mr_weights import chain_weights, normalize_weights, smoothstep
    n = m.nv
    W = {"head": np.zeros(n), "jaw": np.zeros(n)}
    W["head"][m.groups["teeth_upper"] | m.groups["gum_upper"]] = 1.0
    W["jaw"][m.groups["teeth_lower"] | m.groups["gum_lower"]] = 1.0
    tg = m.groups["tongue"]
    ch = [(nm, bones[nm][0], bones[nm][1]) for nm in ("tongue_01", "tongue_02", "tongue_03")]
    tw, s, S = chain_weights(m.v, ch, [0.008, 0.007])
    root = smoothstep((m.v[:, 1] - (-0.040)) / 0.012)     # back of the tongue -> jaw
    for nm, w in tw.items():
        W[nm] = np.where(tg, w * (1 - root), 0.0)
    W["jaw"] = np.where(tg, root, W["jaw"])
    return normalize_weights(W, n)
