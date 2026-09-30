"""MorphRig Operative costume: tactical vest + shoulder straps, high collar, belt with buckle /
pouches / hip charger / beacon clip, right shoulder pauldron (team-emblem plate), knee pads,
left forearm bracer, left ear comm plate, undercut hair cap and tied tail.

Most pieces are parametric patches: rays are cast from an inner axis/centre onto the body or
head SDF, offset by a clearance and solidified (outer skin, inner skin, rims).  The topology is a
clean grid; seams are marked on the rims and on the wrap line so Blender can unwrap islands.

Every builder returns a Mesh with m.bind describing the skinning:
  rigid:<bone>            all vertices to one bone
  transfer                weights copied from the nearest body-suit vertex (deforming cloth)
  blend:<b0>,<b1>         linear blend along the patch's v parameter (attrs['blend'])
  chain:<b0>,<b1>,..      smooth weights along a bone chain (attrs['chain_t'])
"""
import numpy as np
from mr_sdf import ray_exit, normalize, Union
from mr_meshkit import Mesh, make_consistent
from mr_params import J, H, nrm, v
import mr_body
import mr_head


# ----------------------------------------------------------------- patch machinery
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def cast(sdf, O, D, tmax=0.5):
    O = np.asarray(O, float).reshape(-1, 3)
    D = normalize(np.asarray(D, float).reshape(-1, 3))
    t = ray_exit(sdf, O, D, tmax=tmax, max_step=0.003)
    P = O + t[:, None] * D
    N = normalize(sdf.grad(P))
    return P, N


def solidify(P, N, thick, wrap_u=False, name="", pole_cap=False):
    """P, N: (nu, nv, 3) inner surface + outward normals. Returns a closed shell Mesh.
    pole_cap (wrapped patches only): close the last row with triangle fans instead of a rim."""
    nu, nv = P.shape[:2]
    m = Mesh()
    inner = m.add_verts(P.reshape(-1, 3))
    outer = m.add_verts((P + N * thick[..., None] if np.ndim(thick) else P + N * thick).reshape(-1, 3))
    iu = range(nu) if wrap_u else range(nu - 1)

    def vid(base, i, j):
        return base[(i % nu) * nv + j]
    for i in iu:
        for j in range(nv - 1):
            m.add_face((vid(outer, i, j), vid(outer, i + 1, j), vid(outer, i + 1, j + 1), vid(outer, i, j + 1)),
                       shell=1)
            m.add_face((vid(inner, i, j + 1), vid(inner, i + 1, j + 1), vid(inner, i + 1, j), vid(inner, i, j)),
                       shell=2)
    # rims along j = 0 and j = nv - 1
    for i in iu:
        m.add_face((vid(inner, i, 0), vid(inner, i + 1, 0), vid(outer, i + 1, 0), vid(outer, i, 0)), shell=3)
        if not pole_cap:
            m.add_face((vid(outer, i, nv - 1), vid(outer, i + 1, nv - 1), vid(inner, i + 1, nv - 1),
                        vid(inner, i, nv - 1)), shell=3)
    if pole_cap:
        ring_o = m.v[[vid(outer, i, nv - 1) for i in range(nu)]]
        ring_i = m.v[[vid(inner, i, nv - 1) for i in range(nu)]]
        co = m.add_verts([ring_o.mean(0) + (ring_o.mean(0) - ring_i.mean(0)) * 0.3])[0]
        ci = m.add_verts([ring_i.mean(0)])[0]
        for i in range(nu):
            m.add_face((vid(outer, i, nv - 1), vid(outer, i + 1, nv - 1), co), shell=1)
            m.add_face((vid(inner, i + 1, nv - 1), vid(inner, i, nv - 1), ci), shell=2)
    if not wrap_u:
        for j in range(nv - 1):
            m.add_face((vid(outer, 0, j), vid(outer, 0, j + 1), vid(inner, 0, j + 1), vid(inner, 0, j)), shell=3)
            m.add_face((vid(inner, nu - 1, j), vid(inner, nu - 1, j + 1), vid(outer, nu - 1, j + 1),
                        vid(outer, nu - 1, j)), shell=3)
    # orientation: outer faces must point along N
    fn = m.face_normals()
    k0 = 0
    c0 = m.v[list(m.f[k0])].mean(0)
    n0 = N.reshape(-1, 3)[0]
    if np.dot(fn[k0], n0) < 0:
        m.f = [f[::-1] for f in m.f]
    make_consistent(m, seed_face=0)
    # seams: outer/inner boundary loops (rim edges) and the wrap line
    for base in (inner, outer):
        row0 = [vid(base, i, 0) for i in range(nu)]
        row1 = [vid(base, i, nv - 1) for i in range(nu)]
        if wrap_u:
            m.mark_seam_loop(row0)
            if not pole_cap:
                m.mark_seam_loop(row1)
            m.mark_seam_path([vid(base, 0, j) for j in range(nv)])
        else:
            m.mark_seam_path(row0)
            m.mark_seam_path(row1)
            m.mark_seam_path([vid(base, 0, j) for j in range(nv)])
            m.mark_seam_path([vid(base, nu - 1, j) for j in range(nv)])
    extra = m.nv - 2 * nu * nv
    m.attrs["patch_v"] = np.concatenate([np.tile(np.linspace(0, 1, nv), nu)] * 2 + [np.ones(extra)])
    m.attrs["patch_u"] = np.concatenate([np.repeat(np.linspace(0, 1, nu), nv)] * 2 + [np.zeros(extra)])
    m.attrs["outer"] = np.concatenate([np.zeros(nu * nv), np.ones(nu * nv)] + [np.array([1.0, 0.0])[:extra]])
    m.part = name
    return m


def set_bind(m, bind):
    m.bind = bind
    return m


# ----------------------------------------------------------------- SDF helpers
_SDF = {}


def body():
    if "body" not in _SDF:
        _SDF["body"] = mr_body.body_sdf()
    return _SDF["body"]


def torso():
    if "torso" not in _SDF:
        _SDF["torso"] = mr_body.torso_sdf()
    return _SDF["torso"]


def headsdf():
    if "head" not in _SDF:
        _SDF["head"] = mr_head.head_sdf()
    return _SDF["head"]


def neck_body():
    if "nb" not in _SDF:
        _SDF["nb"] = Union([headsdf(), body()], k=0.01)
    return _SDF["nb"]


# ----------------------------------------------------------------- collar
def build_collar(nu=40, nv=6):
    """Stand-up collar hugging the neck base; front dips to cover the suit neckline."""
    phi = 2 * np.pi * np.arange(nu) / nu
    back = 0.5 * (1 - np.cos(phi))                      # 0 front (-Y), 1 back
    z0 = 1.432 + 0.030 * back
    z1 = 1.488 + 0.040 * back
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    for j in range(nv):
        t = j / (nv - 1)
        z = z0 + (z1 - z0) * t
        O = np.stack([np.zeros(nu), np.full(nu, 0.018), z], 1)
        D = np.stack([np.sin(phi), -np.cos(phi), np.zeros(nu)], 1)
        Ps, Ns = cast(neck_body(), O, D)
        r = np.linalg.norm(Ps[:, :2] - O[:, :2], axis=1)
        # keep the collar a tidy tube: never follow the shoulder slope outward
        rn = np.minimum(r, 0.074 + 0.012 * (1 - t) + 0.006 * np.abs(np.sin(phi)))
        rr = rn + 0.004 + 0.003 * (1 - t)
        P[:, j] = O + D * rr[:, None]
        Nh = D.copy()
        Nh[:, 2] = 0.12 * (1 - t)
        N[:, j] = normalize(Nh)
    m = solidify(P, N, 0.009, wrap_u=True, name="collar")
    blend = m.attrs["patch_v"]
    m.attrs["blend"] = blend
    return set_bind(m, "blend:spine_03,neck_01")


# ----------------------------------------------------------------- vest
def build_vest(nu=48, nv=16):
    """Sleeveless tactical vest: torso band from the belt line to the chest, arm holes cut as
    rim boundaries; the shoulder straps are separate bands."""
    phi = 2 * np.pi * np.arange(nu) / nu
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    # arm holes: pull the side columns down below the arm pits (height depends on angle)
    side = np.abs(np.sin(phi))
    top = 1.395 - 0.13 * smoothstep((side - 0.80) / 0.17)
    for i in range(nu):
        zt = top[i]
        zc = np.linspace(1.035, zt, nv)
        O = np.stack([np.zeros(nv), np.full(nv, 0.025), zc], 1)
        D = np.tile([np.sin(phi[i]), -np.cos(phi[i]), 0.0], (nv, 1))
        Ps, Ns = cast(torso(), O, D)
        P[i] = Ps + Ns * 0.006
        N[i] = Ns
    m = solidify(P, N, 0.007, wrap_u=True, name="vest")
    return set_bind(m, "transfer")


def build_strap(side, nu=22, nv=4, width=0.046):
    """Shoulder strap over the trapezius joining the vest front and back."""
    sg = 1.0 if side == "l" else -1.0
    x0 = 0.095 * sg
    ts = np.linspace(0.0, 1.0, nu)
    # path in the sagittal plane at x0: front vest top -> over the shoulder -> back vest top
    ang = np.pi * ts                                      # 0 front, pi back
    c = np.array([x0, 0.030, 1.36])
    D = np.stack([np.zeros(nu), -np.cos(ang), np.sin(ang) * 1.0], 1)
    D[:, 2] = np.sin(ang) + 0.0
    D = normalize(D)
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    for j in range(nv):
        off = (j / (nv - 1) - 0.5) * width
        O = c + np.array([off * sg * 0.0 + off, 0.0, 0.0])
        Ps, Ns = cast(body(), np.tile(O, (nu, 1)), D)
        P[:, j] = Ps + Ns * 0.010
        N[:, j] = Ns
    m = solidify(P, N, 0.006, wrap_u=False, name="strap_" + side)
    return set_bind(m, "transfer")


# ----------------------------------------------------------------- belt
def build_belt(nu=48, nv=5):
    phi = 2 * np.pi * np.arange(nu) / nu
    zs = np.linspace(0.952, 1.002, nv)
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    for j, z in enumerate(zs):
        O = np.stack([np.zeros(nu), np.full(nu, 0.02), np.full(nu, z)], 1)
        Dd = np.stack([np.sin(phi), -np.cos(phi), np.zeros(nu)], 1)
        Ps, Ns = cast(body(), O, Dd)
        P[:, j] = Ps + Ns * 0.004
        Nh = Ns.copy()
        N[:, j] = normalize(Nh)
    # smooth the band vertically (keeps it a straight strap instead of following bumps)
    P[:, :, :2] = P[:, :, :2].mean(1, keepdims=True) * 0.6 + P[:, :, :2] * 0.4
    m = solidify(P, N, 0.007, wrap_u=True, name="belt")
    return set_bind(m, "rigid:pelvis")


def _rbox(center, half, R, bevel):
    from mr_gear import box_mesh
    return box_mesh(center, half, rot=R, bevel=bevel, n=3)


BELT_Z = 0.972
CHARGER_ANGLE = 35.0            # degrees from the front toward the character's left (+X)


def belt_anchor(angle_deg, z=BELT_Z):
    """Point on the belt's outer surface at an azimuth (0 = front, + = toward the left) and its normal."""
    a = np.radians(angle_deg)
    d = v(np.sin(a), -np.cos(a), 0.0)
    P, N = cast(body(), v(0.0, 0.02, z)[None, :], d[None, :])
    n = N[0].copy()
    n[2] = 0.0
    n = nrm(n)
    return P[0] + n * 0.011, n       # belt offset 4 mm + thickness 7 mm


def charger_frame():
    """(outer face centre, outward normal) of the hip charger pad; the reload clip seats the cell here."""
    p, n = belt_anchor(CHARGER_ANGLE, 0.958)
    return p + n * 0.016, n


def build_belt_gear():
    """Buckle (front), two pouches (right back hip), hip charger pad (front-left, used by reload),
    beacon clip plate (back, behind the beacon)."""
    out = []
    bp, bn = belt_anchor(0.0)
    bk = _rbox(bp + bn * 0.004, v(0.030, 0.006, 0.022), np.eye(3), 0.004)
    bk.part = "buckle"
    out.append(set_bind(bk, "rigid:pelvis"))
    # pouches on the right hip, toward the back (clear of the hanging arm)
    for ang, w in ((-126.0, 0.030), (-152.0, 0.029)):
        p, n = belt_anchor(ang, 0.962)
        R = np.stack([np.cross(v(0, 0, 1), n), n, v(0, 0, 1)], 1)
        pm = _rbox(p + n * 0.013, v(w, 0.013, 0.036), R, 0.007)
        pm.part = "pouch"
        out.append(set_bind(pm, "rigid:pelvis"))
    # hip charger pad (front-left): a round-cornered plate
    p, n = belt_anchor(CHARGER_ANGLE, 0.958)
    R = np.stack([np.cross(v(0, 0, 1), n), n, v(0, 0, 1)], 1)
    pad = _rbox(p + n * 0.008, v(0.026, 0.008, 0.036), R, 0.005)
    pad.part = "charger"
    out.append(set_bind(pad, "rigid:pelvis"))
    # beacon clip plate behind the beacon holster
    clp = _rbox(v(0.0, 0.112, 0.968), v(0.030, 0.004, 0.030), np.eye(3), 0.003)
    clp.part = "beacon_clip"
    out.append(set_bind(clp, "rigid:pelvis"))
    return out


# ----------------------------------------------------------------- pauldron (right shoulder)
PAULDRON_PLATES = (
    # (offset, thickness, front/back half-angle, b range deg (0 = shoulder top, + = down the arm))
    (0.007, 0.011, 70.0, (-20.0, 38.0)),
    (0.006, 0.009, 62.0, (32.0, 66.0)),
)


def build_pauldron(nu=16, nv=12):
    S = J["upperarm_r"]
    E = J["lowerarm_r"]
    ax = nrm(E - S)                                 # down the arm (out and down in the A pose)
    up = nrm(v(0, 0, 1) - np.dot(v(0, 0, 1), ax) * ax)
    fwd = nrm(np.cross(ax, up))
    if fwd[1] > 0:
        fwd = -fwd
    centre = S + ax * 0.02
    out = []
    for li, (off, th, ha, (b0, b1)) in enumerate(PAULDRON_PLATES):
        us = np.linspace(-1, 1, nu)
        bs = np.radians(np.linspace(b0, b1, nv))
        P = np.zeros((nu, nv, 3))
        N = np.zeros((nu, nv, 3))
        for i, uu in enumerate(us):
            a = np.radians(ha) * uu * (1.0 - 0.15 * li)
            # rotate 'up' toward the arm axis by b, then around the arm axis by a
            base = up[None, :] * np.cos(bs)[:, None] + ax[None, :] * np.sin(bs)[:, None]
            dirs = base * np.cos(a) + fwd[None, :] * np.sin(a)
            Ps, Ns = cast(body(), np.tile(centre, (nv, 1)), dirs)
            P[i] = Ps + Ns * off
            N[i] = Ns
        # round the plate corners: shrink the outer columns toward the centre line
        m = solidify(P, N, th, wrap_u=False, name=f"pauldron_{li}")
        out.append(set_bind(m, "rigid:upperarm_r"))
    return out


# ----------------------------------------------------------------- knee pads
def build_kneepad(side, nu=12, nv=12):
    K = J["calf_" + side]
    Hh = J["thigh_" + side]
    A = J["foot_" + side]
    down = nrm(A - K)
    fwd = nrm(v(0, -1, 0) - np.dot(v(0, -1, 0), down) * down)
    lat = nrm(np.cross(down, fwd))
    centre = K + down * 0.012 + fwd * -0.01
    us = np.linspace(-1, 1, nu)
    vs = np.linspace(-1, 1, nv)
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    for i, uu in enumerate(us):
        a = np.radians(52.0) * uu
        b = np.radians(42.0) * vs + np.radians(8.0)
        dirs = (fwd[None, :] * np.cos(a) * np.cos(b)[:, None] + lat[None, :] * np.sin(a)
                + down[None, :] * np.sin(b)[:, None] * np.cos(a))
        Ps, Ns = cast(body(), np.tile(centre, (nv, 1)), dirs)
        P[i] = Ps + Ns * 0.006
        N[i] = Ns
    m = solidify(P, N, 0.009, wrap_u=False, name="kneepad_" + side)
    # upper third follows the thigh a little so deep knee bends do not open a gap
    m.attrs["blend"] = 1.0 - smoothstep((m.attrs["patch_v"] - 0.0) / 0.45) * 0.0
    return set_bind(m, f"knee:{side}")


# ----------------------------------------------------------------- bracer (left forearm)
def build_bracer(nu=28, nv=10):
    E = J["lowerarm_l"]
    W = J["hand_l"]
    ax = nrm(W - E)
    ref = nrm(np.cross(ax, v(0, -1, 0)))
    ref2 = np.cross(ax, ref)
    phi = 2 * np.pi * np.arange(nu) / nu
    ss = np.linspace(0.38, 0.90, nv)
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    L = np.linalg.norm(W - E)
    for j, s in enumerate(ss):
        O = np.tile(E + ax * s * L, (nu, 1))
        D = np.cos(phi)[:, None] * ref[None, :] + np.sin(phi)[:, None] * ref2[None, :]
        Ps, Ns = cast(body(), O, D)
        flare = 0.004 * smoothstep((s - 0.78) / 0.12)
        P[:, j] = Ps + Ns * (0.004 + flare)
        N[:, j] = Ns
    m = solidify(P, N, 0.006, wrap_u=True, name="bracer")
    return set_bind(m, "transfer")


# ----------------------------------------------------------------- ear comm plate (left)
def build_comm():
    from mr_gear import cylinder
    # find the ear surface point on the head SDF, left side
    O = v(0.0, 0.012, 1.640)
    Ps, Ns = cast(headsdf(), O[None, :], v(1.0, 0.08, 0.0)[None, :])
    p, n = Ps[0], Ns[0]
    disc = cylinder(p + n * 0.004, p + n * 0.013, 0.019, n=20)
    rim = cylinder(p + n * 0.011, p + n * 0.016, 0.011, n=16)
    fin = cylinder(p + n * 0.010 + v(0, 0.010, 0.012), p + n * 0.010 + v(0, 0.026, 0.040), 0.0035, n=8, r1=0.002)
    out = []
    for mm, nm in ((disc, "comm_disc"), (rim, "comm_rim"), (fin, "comm_fin")):
        mm.part = nm
        out.append(set_bind(mm, "rigid:head"))
    return out


# ----------------------------------------------------------------- hair
HAIR_C = v(0.0, 0.012, 1.655)


def _hairline_el(a):
    """Hairline elevation (deg) from HAIR_C for azimuth a (0 = front, +pi/2 = left)."""
    front = np.clip(-np.cos(a) * -1.0, 0, 1)            # cos(a)=1 at the front
    front = np.clip(np.cos(a), 0, 1)
    side = np.abs(np.sin(a))
    back = np.clip(-np.cos(a), 0, 1)
    # forehead 33 deg, temples ~20, above the ears 10, nape -34
    el = 33.0 * front ** 1.3 + 10.0 * side * (1 - back) - 34.0 * back ** 1.5
    return np.maximum(el, -34.0)


def _top_weight(a, el):
    """1 inside the long top section of the undercut (a wide strip over the crown)."""
    D = np.stack([np.cos(el) * np.sin(a), -np.cos(el) * np.cos(a), np.sin(el)], -1)
    lat = np.abs(D[..., 0])
    back = np.clip(-np.cos(a), 0, 1)
    edge = 0.60 - 0.10 * back                              # part line; narrower toward the back
    return smoothstep((edge - lat) / 0.05) * smoothstep((np.degrees(el) - 8.0 + 30.0 * back) / 8.0)


def build_hair(nu=22, nv=34):
    """Undercut top section: a strip from the forehead over the crown to the tail base, full
    thickness in the middle, feathered to ~1 mm at the part lines.  The shaved sides/nape are
    painted into the head skin texture (see textures), not modelled."""
    us = np.linspace(-1.0, 1.0, nu)
    vs = np.linspace(0.0, 1.0, nv)
    th = np.radians(34.0 + (158.0 - 34.0) * vs)          # pitch from the front, over the top, to the back
    P = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    T = np.zeros((nu, nv))
    for i, uu in enumerate(us):
        halfw = np.radians(35.0 - 7.0 * smoothstep((vs - 0.55) / 0.45))   # narrower toward the back
        ph = halfw * uu
        D = np.stack([np.sin(ph), -np.cos(ph) * np.cos(th), np.cos(ph) * np.sin(th)], 1)
        Ps, Ns = cast(headsdf(), np.tile(HAIR_C, (nv, 1)), D)
        edge = np.sqrt(np.clip(1.0 - np.abs(uu) ** 3, 0.0, 1.0))
        front = smoothstep(vs / 0.10)                              # feathered hairline
        quiff = 0.010 * np.exp(-((vs - 0.12) / 0.10) ** 2)         # raised front
        crown = 0.011 + 0.006 * smoothstep((vs - 0.35) / 0.3)
        taper = 1.0 - 0.65 * smoothstep((vs - 0.78) / 0.22)          # thins into the tail base
        T[i] = 0.0012 + (crown + quiff) * edge * front * taper
        P[i] = Ps + Ns * 0.0004
        # swept-back volume: lean the growth direction backward on the top
        N[i] = normalize(Ns + (edge * front)[:, None] * v(0, 0.22, 0.12))
    m = solidify(P, N, T, wrap_u=False, name="hair")
    return set_bind(m, "rigid:head")


def build_tail(nr=12):
    """Tied tail following hair_tail_01..04 (secondary-motion chain)."""
    from mr_gear import tube
    pts = np.array([v(0, 0.090, 1.730), v(0, 0.117, 1.708), v(0, 0.133, 1.670), v(0, 0.139, 1.630),
                    v(0, 0.137, 1.592)])
    from mr_body import _polyline_eval
    total = _polyline_eval(list(pts), np.array([0.0]))[1]
    ss = np.linspace(0, total, 17)
    P, _ = _polyline_eval(list(pts), ss)
    s = ss / total
    rad = 0.0150 * (1 - s) ** 0.6 + 0.0025
    radii = [(r * 1.05, r * 0.85) for r in rad]
    m = tube(P, radii, n=nr, closed_ends=(True, True), ref=(1, 0, 0))
    d = np.linalg.norm(m.v[:, None, :] - P[None, :, :], axis=2)
    m.attrs["chain_t"] = s[np.argmin(d, axis=1)]
    m.part = "hair_tail"
    band = tube([P[0] * 0.6 + P[1] * 0.4 - v(0, 0.0, 0.0), P[1] * 0.5 + P[2] * 0.5],
                [0.0185, 0.0175], n=nr, ref=(1, 0, 0))
    band.part = "hair_band"
    return [set_bind(m, "chain:head,hair_tail_01,hair_tail_02,hair_tail_03,hair_tail_04"),
            set_bind(band, "rigid:hair_tail_01")]


def build_all():
    pieces = [build_collar(), build_vest(), build_strap("l"), build_strap("r"), build_belt()]
    pieces += build_belt_gear()
    pieces += build_pauldron()
    pieces += [build_kneepad("l"), build_kneepad("r"), build_bracer()]
    pieces += build_comm()
    pieces += [build_hair()]
    pieces += build_tail()
    return pieces


# ----------------------------------------------------------------- skinning
MATERIAL_OF = {"collar": "suit", "vest": "suit", "strap": "suit", "belt": "suit", "bracer": "suit",
               "pauldron": "armor", "kneepad": "armor", "gear": "armor", "comm": "cyber",
               "hair": "hair", "hair_tail": "hair", "hair_band": "armor"}


def piece_material(m):
    part = getattr(m, "part", "") or "gear"
    for k in sorted(MATERIAL_OF, key=len, reverse=True):
        if part.startswith(k):
            return MATERIAL_OF[k]
    return "armor"


def piece_weights(m, bones, suit_v, suit_w):
    """Weights dict for one costume piece according to m.bind."""
    from mr_weights import normalize_weights
    kind, _, arg = m.bind.partition(":")
    n = m.nv
    if kind == "rigid":
        return {arg: np.ones(n)}
    if kind == "blend":
        b0, b1 = arg.split(",")
        t = np.clip(m.attrs["blend"], 0, 1)
        return normalize_weights({b0: 1 - t, b1: t}, n)
    if kind == "chain":
        names = arg.split(",")[1:]
        t = np.clip(m.attrs["chain_t"], 0, 1) * len(names) - 0.5
        W = {nm: np.zeros(n) for nm in names}
        k0 = np.clip(np.floor(t).astype(int), 0, len(names) - 1)
        k1 = np.clip(k0 + 1, 0, len(names) - 1)
        f = np.clip(t - np.floor(t), 0, 1)
        f[t < 0] = 0.0
        for i in range(n):
            W[names[k0[i]]][i] += 1 - f[i]
            W[names[k1[i]]][i] += f[i]
        return normalize_weights(W, n)
    if kind == "knee":
        s = arg
        K = J["calf_" + s]
        up = nrm(J["thigh_" + s] - K)
        h = (m.v - K) @ up
        wt = 0.5 * smoothstep(h / 0.05)
        return normalize_weights({f"calf_{s}": 1 - wt, f"thigh_{s}": wt}, n)
    if kind == "transfer":
        # inverse-distance blend of the 6 nearest suit vertices
        d2 = ((m.v[:, None, :] - suit_v[None, :, :]) ** 2).sum(-1)
        idx = np.argsort(d2, axis=1)[:, :6]
        dd = np.sqrt(np.take_along_axis(d2, idx, 1)) + 1e-4
        wi = 1.0 / dd ** 2
        wi /= wi.sum(1, keepdims=True)
        W = {}
        for bn, w in suit_w.items():
            vals = (w[idx] * wi).sum(1)
            if vals.max() > 1e-4:
                W[bn] = vals
        return normalize_weights(W, n)
    raise ValueError(m.bind)


def assemble(pieces, bones, suit_v, suit_w):
    """Merge pieces into objects: 'gear' (suit/armor/cyber materials) and 'hair'.
    Returns {obj_key: (Mesh, weights, material_names)} with face attr 'mat' indices."""
    groups = {"gear": [], "hair": [], "tail": []}
    for m in pieces:
        mat = piece_material(m)
        part = getattr(m, "part", "") or ""
        key = "tail" if part.startswith("hair_") else ("hair" if mat == "hair" else "gear")
        groups[key].append((m, mat))
    out = {}
    for key, items in groups.items():
        mats = []
        M = Mesh()
        W = {}
        for m, mat in items:
            if mat not in mats:
                mats.append(mat)
            import mr_parts
            mr_parts.tag(m, getattr(m, "part", "") or "gear")
            off = M.nv
            M.append(m)
            nf_new = len(m.f)
            fa = list(M.face_attrs.get("mat", []))
            fa = fa + [0] * (len(M.f) - len(fa))
            fa[len(M.f) - nf_new:] = [mats.index(mat)] * nf_new
            M.face_attrs["mat"] = fa
            w = piece_weights(m, bones, suit_v, suit_w)
            for bn, vals in w.items():
                arr = W.setdefault(bn, np.zeros(0))
                if len(arr) < M.nv:
                    arr = np.concatenate([arr, np.zeros(M.nv - len(arr))])
                arr[off:off + m.nv] = vals
                W[bn] = arr
        for bn in W:
            if len(W[bn]) < M.nv:
                W[bn] = np.concatenate([W[bn], np.zeros(M.nv - len(W[bn]))])
        out[key] = (M, W, mats)
    return out
