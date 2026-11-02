"""MorphRig costume, cybernetics and props.

Everything the Operative wears or carries is generated here so the whole
character stays procedural and editable:

  undersuit        the torso / limbs are the suit shell
  armour           chest plate, pauldrons, collar, belt, thigh and knee
                   plates, boot cuffs
  cybernetics      right forearm vambrace with actuator, integrated wrist
                   emitter, retractable forearm blade
  props            removable power cell, deployable beacon / drone
  secondary        short hair section and a shoulder cable

Every plate is generated from the *same* surface function that produced the
body underneath it (torso_profile / arm_axis / leg_axis / boot sections), so
the armour hugs the character instead of floating in front of it.

Material slots are shared with the body build (8 slots total).
"""

import math
from mathutils import Vector

from mr_core import TAU, Tube, catmull_rom, parallel_transport_frames, clamp, lerp
from mr_face import _grid_surface, _stitch_border, _border_loop

M_SKIN, M_FACE, M_SUIT, M_ARMOR, M_METAL, M_OPTIC, M_ENERGY, M_ACCENT = range(8)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def grid_normals(grid):
    """Per-vertex normals of a quad grid (central differences)."""
    rows = len(grid)
    cols = len(grid[0])
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            du = Vector((0, 0, 0))
            dv = Vector((0, 0, 0))
            if c + 1 < cols:
                du = grid[r][c + 1] - grid[r][c]
            elif c > 0:
                du = grid[r][c] - grid[r][c - 1]
            if r + 1 < rows:
                dv = grid[r + 1][c] - grid[r][c]
            elif r > 0:
                dv = grid[r][c] - grid[r - 1][c]
            n = dv.cross(du)
            if n.length < 1e-9:
                n = Vector((0, 0, 1))
            row.append(n.normalized())
        out.append(row)
    return out


def shell(mb, grid_pts, thickness, mat, part, smooth=True, normals=None,
          u_scale=1.0, v_scale=1.0):
    """Solid panel from a grid of surface points.

    The panel is offset `thickness` along the local normal, so it sits on
    top of the surface with a visible edge.
    """
    rows = len(grid_pts)
    cols = len(grid_pts[0])
    if normals is None:
        normals = grid_normals(grid_pts)
    outer, inner = [], []
    for r in range(rows):
        ro, ri = [], []
        for c in range(cols):
            p = grid_pts[r][c]
            n = normals[r][c]
            ro.append(mb.add_verts([p + n * (thickness * 0.5)], part)[0])
            ri.append(mb.add_verts([p - n * (thickness * 0.5)], part)[0])
        outer.append(ro)
        inner.append(ri)
    for r in range(rows - 1):
        for c in range(cols - 1):
            u0 = c / float(cols - 1) * u_scale
            u1 = (c + 1) / float(cols - 1) * u_scale
            v0 = r / float(rows - 1) * v_scale
            v1 = (r + 1) / float(rows - 1) * v_scale
            a, b = outer[r][c], outer[r][c + 1]
            d, e = outer[r + 1][c + 1], outer[r + 1][c]
            idx = [a, b, d, e]
            nrm = (mb.verts[b] - mb.verts[a]).cross(mb.verts[d] - mb.verts[b])
            if nrm.dot(normals[r][c]) < 0.0:
                idx = idx[::-1]
            mb.add_quad(idx[0], idx[1], idx[2], idx[3],
                        [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], smooth, mat)
            a, b = inner[r][c], inner[r][c + 1]
            d, e = inner[r + 1][c + 1], inner[r + 1][c]
            idx = [a, b, d, e]
            nrm = (mb.verts[b] - mb.verts[a]).cross(mb.verts[d] - mb.verts[b])
            if nrm.dot(normals[r][c]) > 0.0:
                idx = idx[::-1]
            mb.add_quad(idx[0], idx[1], idx[2], idx[3],
                        [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], smooth, mat)
    _stitch_border(mb, outer, inner, _border_loop(rows, cols), mat, smooth)
    return outer


def band(mb, points, normals, thickness, mat, part, closed=True):
    """Thick ribbon following a list of (point, normal) pairs."""
    n = len(points)
    outer, inner = [], []
    for p, nrm in zip(points, normals):
        outer.append(mb.add_verts([p + nrm * (thickness * 0.5)], part)[0])
        inner.append(mb.add_verts([p - nrm * (thickness * 0.5)], part)[0])
    lim = n if closed else n - 1
    for k in range(lim):
        k1 = (k + 1) % n
        a, b = outer[k], outer[k1]
        c, d = inner[k1], inner[k]
        idx = [a, b, c, d]
        nrm = (mb.verts[b] - mb.verts[a]).cross(mb.verts[c] - mb.verts[b])
        ref = normals[k]
        if nrm.dot(ref) < 0.0:
            idx = idx[::-1]
        mb.add_quad(idx[0], idx[1], idx[2], idx[3],
                    [(k / float(n), 0), ((k + 1) / float(n), 0),
                     ((k + 1) / float(n), 1), (k / float(n), 1)], True, mat)
        a, b = inner[k], inner[k1]
        c, d = outer[k1], outer[k]
        mb.add_quad(a, b, c, d,
                    [(k / float(n), 0), ((k + 1) / float(n), 0),
                     ((k + 1) / float(n), 1), (k / float(n), 1)], True, mat)
    if not closed:
        for (o0, i0), (o1, i1) in (((outer[0], inner[0]),
                                    (outer[1], inner[1])),
                                   ((outer[-1], inner[-1]),
                                    (outer[-2], inner[-2]))):
            mb.add_quad(o0, o1, i1, i0,
                        [(0, 0), (1, 0), (1, 1), (0, 1)], True, mat)
    return outer


def tube(mb, centers, radii, mat, part, sides=16, caps=True, up_hint=(0, 1, 0)):
    """Sweep a circular profile along a polyline."""
    frames = parallel_transport_frames(centers, Vector(up_hint))
    t = Tube(mb, "gear_tube")
    for i, c in enumerate(centers):
        tg, rt, upv = frames[i]
        r = radii[i]
        pts = [c + rt * (r * math.cos(TAU * j / sides)) +
               upv * (r * math.sin(TAU * j / sides)) for j in range(sides)]
        t.add_ring(pts, v=i / float(len(centers)), part=part)
        if i:
            t.bridge(i - 1, i, mat=mat)
    if caps:
        t.cap(0, center=centers[0], flip=True, mat=mat)
        t.cap(len(t.rings) - 1, center=centers[-1], flip=False, mat=mat)
    return t


def ellipse_surface(z, a, w, d, yo):
    """Point + outward normal on an ellipse centred on the Y axis."""
    p = Vector((w * math.cos(a), yo + d * math.sin(a), z))
    n = Vector((d * math.cos(a), w * math.sin(a), 0.0)).normalized()
    return p, n


def frame_angle(frames, i, world_dir):
    """Angle of `world_dir` inside the (right, up) plane of frame `i`."""
    tg, rt, upv = frames[i]
    d = Vector(world_dir)
    d = d - tg * d.dot(tg)
    if d.length < 1e-9:
        return 0.0
    d.normalize()
    return math.atan2(d.dot(upv), d.dot(rt))


def sleeve(mb, centers, radii, frames, i0, i1, ang_from, ang_to, mat, part,
           offset=0.009, flare=0.007, dome=0.0, thickness=0.007, cols=21,
           smooth=True, u_scale=1.0, v_scale=1.0):
    """A domed plate wrapped around a tapered tube segment."""
    grid = []
    nrows = max(i1 - i0, 1)
    for k in range(nrows + 1):
        i = i0 + k
        c = centers[i]
        r = radii[i]
        tg, rt, upv = frames[i]
        row = []
        for j in range(cols):
            f = j / float(cols - 1.0)
            a = math.radians(ang_from + (ang_to - ang_from) * f)
            d = (rt * math.cos(a) + upv * math.sin(a)).normalized()
            off = (offset + flare * ((k / float(nrows)) ** 2) +
                   dome * math.sin(math.pi * f))
            row.append(c + d * (r + off))
        grid.append(row)
    return shell(mb, grid, thickness, mat, part, smooth,
                 u_scale=u_scale, v_scale=v_scale)


# ---------------------------------------------------------------------------
# costume
# ---------------------------------------------------------------------------

def build_collar(mb, torso_profile):
    """Raised collar / neck seal that flares up towards the nape."""
    pts, nrm = [], []
    n = 37
    for i in range(n):
        a = TAU * i / float(n)
        back = (math.sin(a) + 1.0) * 0.5          # 1 at the nape, 0 at the throat
        z = 1.470 + 0.082 * (back ** 1.4)
        w, d, yo = torso_profile(min(z, 1.552))
        p, nv = ellipse_surface(z, a, w + 0.010, d + 0.010, yo)
        p = p + Vector((0.0, 0.018 * back, 0.014 * back))
        pts.append(p)
        nrm.append(nv)
    band(mb, pts, nrm, 0.009, M_ARMOR, "collar", closed=True)
    return pts


def build_chest_plate(mb, torso_profile):
    """Layered chest plate with a raised centre ridge and an optic core."""
    z0, z1 = 1.205, 1.392
    rows, cols = 11, 25
    grid = []
    for r in range(rows):
        v = r / float(rows - 1)
        z = z0 + (z1 - z0) * v
        w, d, yo = torso_profile(z)
        # outline: wide at the collar, tapering to a point at the sternum
        span = math.radians(26.0 + 30.0 * (v ** 0.75))
        row = []
        for c in range(cols):
            u = (c / float(cols - 1.0)) * 2.0 - 1.0
            a = 270.0 + math.degrees(span) * u
            p, n = ellipse_surface(z, math.radians(a), w, d, yo)
            # a rounded-off top and bottom edge
            edge = min(v, 1.0 - v) * 2.0
            shrink = math.sqrt(max(0.0, min(1.0, edge * 3.0)))
            a = 270.0 + math.degrees(span) * u * shrink
            p, n = ellipse_surface(z, math.radians(a), w, d, yo)
            dome = 0.013 * (1.0 - u * u) * (1.0 - (2.0 * v - 1.0) ** 2)
            row.append(p + n * (0.005 + dome))
        grid.append(row)
    shell(mb, grid, 0.011, M_ARMOR, "chest_plate")

    # glowing optic core set into the sternum
    core = []
    for r in range(5):
        v = r / 4.0
        z = 1.272 + 0.040 * v
        w, d, yo = torso_profile(z)
        row = []
        for c in range(9):
            u = (c / 8.0) * 2.0 - 1.0
            a = math.radians(270.0 + 15.0 * u)
            p, n = ellipse_surface(z, a, w, d, yo)
            row.append(p + n * 0.016)
        core.append(row)
    shell(mb, core, 0.005, M_ENERGY, "chest_plate")

    # accent trim running along the collarbone
    for side in (1, -1):
        pts, nrm = [], []
        for i in range(13):
            t = i / 12.0
            z = 1.360 - 0.020 * t
            w, d, yo = torso_profile(z)
            a = math.radians(270.0 + side * (20.0 + 34.0 * t))
            p, n = ellipse_surface(z, a, w, d, yo)
            pts.append(p + n * 0.012)
            nrm.append(n)
        band(mb, pts, nrm, 0.006, M_ACCENT, "chest_plate", closed=False)
    return grid


def build_pauldrons(mb, arms):
    """Hard shoulder caps that wrap the deltoid."""
    import mr_body
    out = []
    for side in (1, -1):
        part = "pauldron_%s" % ("r" if side > 0 else "l")
        centers, radii = mr_body.arm_axis(side)
        frames = parallel_transport_frames(centers)
        i0, i1 = 1, 7
        a0 = frame_angle(frames, i0, (side, 0, 0)) - math.degrees(118.0)
        a1 = frame_angle(frames, i1, (side, 0, 0)) + math.degrees(118.0)
        sleeve(mb, centers, radii, frames, i0, i1, a0, a1, M_ARMOR, part,
               offset=0.008, flare=0.010, dome=0.012, thickness=0.009, cols=25)
        # accent chevron across the outer face
        ac0 = frame_angle(frames, i0, (side, 0, 0)) - math.degrees(30.0)
        ac1 = frame_angle(frames, i1, (side, 0, 0)) + math.degrees(30.0)
        sleeve(mb, centers, radii, frames, i0 + 1, i1 - 1, ac0, ac1,
               M_ACCENT, part, offset=0.020, flare=0.010, thickness=0.004,
               cols=13)
        out.append(part)
    return out


def build_belt(mb, torso_profile):
    """Utility belt with a hip pouch and a front buckle."""
    grid = []
    n = 49
    for r in range(3):
        z = 1.012 + 0.026 * r
        w, d, yo = torso_profile(z)
        row = []
        for c in range(n):
            a = TAU * c / float(n)
            p, nv = ellipse_surface(z, a, w, d, yo)
            row.append(p + nv * 0.008)
        grid.append(row)
    shell(mb, grid, 0.014, M_ARMOR, "belt")

    # hip pouch on the right side
    pouch = []
    for r in range(5):
        v = r / 4.0
        z = 0.925 + 0.095 * v
        w, d, yo = torso_profile(z)
        row = []
        for c in range(9):
            u = (c / 8.0) * 2.0 - 1.0
            a = math.radians(18.0 + u * 34.0)
            p, nv = ellipse_surface(z, a, w, d, yo)
            bulge = 0.024 * (1.0 - u * u) * (0.35 + 0.65 * math.sin(math.pi * v))
            row.append(p + nv * (0.006 + bulge))
        pouch.append(row)
    shell(mb, pouch, 0.014, M_ARMOR, "belt")

    # front buckle
    buckle = []
    for r in range(3):
        v = r / 2.0
        z = 1.012 + 0.026 * v
        w, d, yo = torso_profile(z)
        row = []
        for c in range(7):
            u = (c / 6.0) * 2.0 - 1.0
            a = math.radians(270.0 + u * 13.0)
            p, nv = ellipse_surface(z, a, w, d, yo)
            row.append(p + nv * (0.020 + 0.004 * (1.0 - u * u)))
        buckle.append(row)
    shell(mb, buckle, 0.010, M_METAL, "belt")
    return grid


def build_limb_plates(mb, legs):
    """Knee guards and thigh plates that follow the leg axis."""
    import mr_body
    for side in (1, -1):
        part = "legplate_%s" % ("r" if side > 0 else "l")
        centers, radii = mr_body.leg_axis(side)
        frames = parallel_transport_frames(centers)
        # knee guard (front of the leg)
        f0 = frame_angle(frames, 7, (0, -1, 0)) - math.degrees(56.0)
        f1 = frame_angle(frames, 13, (0, -1, 0)) + math.degrees(56.0)
        sleeve(mb, centers, radii, frames, 6, 13, f0, f1, M_ARMOR, part,
               offset=0.007, flare=0.008, dome=0.010, thickness=0.008, cols=19)
        # small pad on the outer thigh
        t0 = frame_angle(frames, 2, (side, 0, 0)) - math.degrees(30.0)
        t1 = frame_angle(frames, 5, (side, 0, 0)) + math.degrees(30.0)
        sleeve(mb, centers, radii, frames, 2, 5, t0, t1, M_ARMOR, part,
               offset=0.007, flare=0.005, dome=0.010, thickness=0.008, cols=13)


def build_boot_cuffs(mb):
    """Armoured cuff at the top of each boot."""
    import mr_body
    for side in (1, -1):
        part = "bootcuff_%s" % ("r" if side > 0 else "l")
        ax = 0.100 * side
        grid = []
        rows = ((0.014, 0.051, 0.046), (0.032, 0.057, 0.052),
                (0.050, 0.062, 0.057))
        for (y, hw, hh) in rows:
            row = []
            for c in range(29):
                a = TAU * c / 28.0
                row.append(Vector((ax + hw * math.cos(a), y,
                                   0.120 + hh * math.sin(a))))
            grid.append(row)
        shell(mb, grid, 0.009, M_ARMOR, part)
        # accent strip
        acc = []
        for (y, hw, hh) in ((0.020, 0.055, 0.050), (0.046, 0.061, 0.056)):
            row = []
            for c in range(29):
                a = TAU * c / 28.0
                row.append(Vector((ax + hw * math.cos(a), y,
                                   0.120 + hh * math.sin(a))))
            acc.append(row)
        shell(mb, acc, 0.004, M_ACCENT, part)


# ---------------------------------------------------------------------------
# cybernetics
# ---------------------------------------------------------------------------

def build_cyber_arm(mb, arm_axis):
    """Segmented cybernetic vambrace over the right forearm."""
    part = "cyber_arm"
    centers, radii = arm_axis(1)
    frames = parallel_transport_frames(centers)
    start = 8
    seg_pts = centers[start:]
    seg_rad = [radii[i] + 0.007 for i in range(start, len(centers))]
    # three overlapping plates with gaps
    t = Tube(mb, "cyber")
    for i, c in enumerate(seg_pts):
        tg, rt, upv = frames[start + i]
        r = seg_rad[i]
        n = 20
        pts = []
        for j in range(n):
            a = TAU * j / n
            pts.append(c + rt * (r * math.cos(a)) + upv * (r * math.sin(a)))
        t.add_ring(pts, v=i / float(len(seg_pts)), part=part)
        if i:
            t.bridge(i - 1, i, mat=M_METAL)
    t.cap(len(t.rings) - 1, center=seg_pts[-1], flip=False, mat=M_METAL)
    # ribs between the plates
    for i in (3, 8, 13):
        if i >= len(seg_pts):
            continue
        c = seg_pts[i]
        tg, rt, upv = frames[start + i]
        r = seg_rad[i] * 0.99
        pts, nrm = [], []
        for j in range(21):
            a = TAU * j / 20.0
            n = (rt * math.cos(a) + upv * math.sin(a)).normalized()
            pts.append(c + n * r)
            nrm.append(n)
        band(mb, pts, nrm, 0.010, M_OPTIC, part, closed=True)
    # vent slots on the outer face
    for i in (5, 10):
        c = seg_pts[i]
        tg, rt, upv = frames[start + i]
        for k in range(3):
            off = (k - 1) * 0.016
            ctr = c + tg * off
            pts, nrm = [], []
            for j in range(7):
                a = math.radians(-26.0 + 52.0 * j / 6.0)
                d = (rt * math.cos(a) + upv * math.sin(a)).normalized()
                pts.append(ctr + d * (seg_rad[i] + 0.003))
                nrm.append(d)
            band(mb, pts, nrm, 0.005, M_OPTIC, part, closed=False)


def build_emitter(mb, arm_axis):
    """Integrated wrist emitter on the right forearm."""
    part = "emitter"
    centers, radii = arm_axis(1)
    frames = parallel_transport_frames(centers)
    w = centers[-1]
    d = (centers[-1] - centers[-4]).normalized()     # towards the hand
    tg, rt, upv = frames[-1]
    side = Vector((1.0, 0.0, 0.0))
    side = (side - d * side.dot(d)).normalized()
    up = d.cross(side).normalized()
    base = w + up * 0.021 + side * 0.013
    # barrel
    barrel = []
    for i in range(7):
        t = i / 6.0
        barrel.append(base + d * (0.006 + 0.086 * t))
    radii2 = [0.0195 - 0.0035 * (i / 6.0) for i in range(7)]
    tube(mb, barrel, radii2, M_METAL, part, sides=18, caps=True)
    # muzzle ring
    tip = barrel[-1]
    pts, nrm = [], []
    for j in range(19):
        a = TAU * j / 18.0
        n = (side * math.cos(a) + up * math.sin(a)).normalized()
        pts.append(tip + n * 0.0145)
        nrm.append(n)
    band(mb, pts, nrm, 0.008, M_OPTIC, part, closed=True)
    # emitter glow
    pts, nrm = [], []
    for j in range(19):
        a = TAU * j / 18.0
        n = (side * math.cos(a) + up * math.sin(a)).normalized()
        pts.append(tip + d * 0.001 + n * 0.0098)
        nrm.append(n)
    band(mb, pts, nrm, 0.004, M_ENERGY, part, closed=True)
    # charge cells on the side of the vambrace
    for k in range(2):
        c = base + d * (0.020 + 0.036 * k) - up * 0.014
        cell = []
        for i in range(5):
            cell.append(c + side * (0.0 + 0.006 * i))
        tube(mb, cell, [0.0065] * 5, M_OPTIC, part, sides=10, caps=True)
    return base, d, side, up


def build_blade(mb, arm_axis):
    """Retractable forearm blade (bound to the blade_r bone).

    The mesh runs along the blade_r bone's own axis starting at the bone
    head, so scaling that bone's Y axis extends and retracts the blade.
    """
    part = "blade_r"
    centers, radii = arm_axis(1)
    frames = parallel_transport_frames(centers)
    d = (centers[-1] - centers[-5]).normalized()      # towards the hand
    tg, rt, upv = frames[-5]
    side = Vector((1.0, 0.0, 0.0))
    side = (side - d * side.dot(d)).normalized()
    up = d.cross(side).normalized()
    base = centers[-5] + up * 0.026 - side * 0.012
    rows, cols = 9, 5
    gp, gn = [], []
    for r in range(rows):
        v = r / float(rows - 1)
        c = base + d * (0.250 * v)
        wdt = 0.017 * (1.0 - 0.75 * v * v)
        rowp, rown = [], []
        for c2 in range(cols):
            u = (c2 / float(cols - 1.0)) * 2.0 - 1.0
            p = c + side * (u * wdt) + up * (0.002 * (1.0 - abs(u)))
            rowp.append(p)
            rown.append(side * (1.0 if u >= 0 else -1.0))
        gp.append(rowp)
        gn.append(rown)
    shell(mb, gp, 0.007, M_METAL, part)
    # glowing edge
    gp, gn = [], []
    for r in range(rows):
        v = r / float(rows - 1)
        c = base + d * (0.250 * v)
        wdt = 0.017 * (1.0 - 0.75 * v * v)
        rowp, rown = [], []
        for c2 in range(cols):
            u = (c2 / float(cols - 1.0)) * 2.0 - 1.0
            p = c + side * (u * wdt) + up * (0.006 * (1.0 - abs(u)))
            rowp.append(p)
            rown.append(up)
        gp.append(rowp)
        gn.append(rown)
    shell(mb, gp, 0.003, M_ENERGY, part)
    # housing
    house = [base - d * (0.034 * i) for i in range(4)]
    tube(mb, house, [0.019, 0.022, 0.021, 0.015], M_METAL, part, sides=14)


def build_power_cell(mb, center=None):
    """Removable emitter power cell (rides in the right hand)."""
    part = "cell_r"
    c = Vector(center) if center is not None else Vector((0, 0, 0))
    body = [c + Vector((0, 0, -0.026 + 0.013 * i)) for i in range(5)]
    tube(mb, body, [0.021, 0.023, 0.023, 0.023, 0.021], M_METAL, part,
         sides=16, caps=True)
    band_pts, band_n = [], []
    for j in range(17):
        a = TAU * j / 16.0
        n = Vector((math.cos(a), math.sin(a), 0.0))
        band_pts.append(c + Vector((0, 0, 0.0)) + n * 0.0235)
        band_n.append(n)
    band(mb, band_pts, band_n, 0.008, M_ENERGY, part, closed=True)
    return c


def build_beacon(mb, center=None):
    """Small deployable beacon drone."""
    part = "beacon"
    org = Vector(center) if center is not None else Vector((0, 0, 0))
    body = [org + Vector((0, 0, -0.018 + 0.012 * i)) for i in range(4)]
    tube(mb, body, [0.030, 0.038, 0.036, 0.024], M_METAL, part, sides=16,
         caps=True)
    # rotor rings
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = org + Vector((sx * 0.036, sy * 0.036, 0.022))
            pts, nrm = [], []
            for j in range(17):
                a = TAU * j / 16.0
                n = Vector((math.cos(a), math.sin(a), 0.0))
                pts.append(c + n * 0.020)
                nrm.append(n)
            band(mb, pts, nrm, 0.005, M_OPTIC, part, closed=True)
    # lens
    lens = [org + Vector((0.0, -0.036 + 0.008 * i, 0.0)) for i in range(3)]
    tube(mb, lens, [0.014, 0.016, 0.012], M_OPTIC, part, sides=14)
    glow = [org + Vector((0.0, -0.042, 0.0)), org + Vector((0.0, -0.046, 0.0))]
    tube(mb, glow, [0.009, 0.006], M_ENERGY, part, sides=12)
    return part


# ---------------------------------------------------------------------------
# secondary motion
# ---------------------------------------------------------------------------

def build_hair(mb, head_profile):
    """Short swept hair section (secondary motion element).

    The hair follows the skull profile, is parted at the front and sweeps
    down to the nape at the back.
    """
    part = "hair_01"
    a0, a1 = 315.0, 585.0          # 270 deg is the face centre
    cols = 49
    rows = 9
    grid = []
    for r in range(rows):
        v = r / float(rows - 1.0)
        row = []
        for c in range(cols):
            f = c / float(cols - 1.0)
            a = math.radians(a0 + (a1 - a0) * f)
            back = (math.sin(a) + 1.0) * 0.5
            # ragged hair line
            rag = 0.010 * math.sin(a * 9.0) + 0.006 * math.sin(a * 21.0 + 1.1)
            z_top = 1.793
            z_bot = 1.648 - 0.066 * back + rag
            z = lerp(z_top, z_bot, v)
            w, d, yo = head_profile(min(z, 1.793))
            grow = 1.0 + 0.028 * (1.0 - v) + 0.010 * back
            p = Vector((w * grow * math.cos(a), yo + d * grow * math.sin(a), z))
            row.append(p)
        grid.append(row)
    shell(mb, grid, 0.007, M_SUIT, part)

    # fringe: a short sweep across the forehead
    fringe = []
    for r in range(3):
        v = r / 2.0
        row = []
        for c in range(15):
            u = (c / 14.0) * 2.0 - 1.0
            a = math.radians(270.0 + u * 52.0)
            z = 1.748 - 0.034 * (1.0 - abs(u)) + 0.014 * v
            w, d, yo = head_profile(min(z, 1.793))
            grow = 1.0 + 0.034 + 0.020 * v
            p = Vector((w * grow * math.cos(a), yo + d * grow * math.sin(a), z))
            row.append(p)
        fringe.append(row)
    shell(mb, fringe, 0.006, M_SUIT, part)
    return grid


def build_backpack(mb, torso_profile):
    """Small back pack plus the shoulder cable."""
    grid = []
    for r in range(9):
        v = r / 8.0
        z = 1.170 + 0.215 * v
        w, d, yo = torso_profile(z)
        row = []
        for c in range(13):
            u = (c / 12.0) * 2.0 - 1.0
            a = math.radians(90.0 + u * 54.0)
            p, n = ellipse_surface(z, a, w, d, yo)
            bulge = 0.030 * (1.0 - u * u) * math.sin(math.pi * v)
            row.append(p + n * bulge)
        grid.append(row)
    shell(mb, grid, 0.014, M_ARMOR, "back_pack")

    # cable from the pack over the left shoulder
    pts = [Vector((0.0, 0.112, 1.330)), Vector((-0.055, 0.135, 1.318)),
           Vector((-0.115, 0.120, 1.270)), Vector((-0.160, 0.070, 1.222)),
           Vector((-0.176, 0.010, 1.196))]
    centers = catmull_rom(pts, 18)
    t = Tube(mb, "cable")
    first = 3
    for i, c in enumerate(centers):
        if i < first:
            continue
        k = i - first
        nxt = centers[min(i + 1, len(centers) - 1)]
        prv = centers[i - 1]
        d = (nxt - prv).normalized()
        r = 0.0062 - 0.0022 * (k / float(max(len(centers) - first - 1, 1)))
        upv = Vector((0, 0, 1)).cross(d)
        if upv.length < 1e-6:
            upv = Vector((1, 0, 0))
        upv.normalize()
        ctr = [c + upv * (r * math.cos(TAU * j / 8.0)) +
               d.cross(upv) * (r * math.sin(TAU * j / 8.0))
               for j in range(8)]
        seg = (k * 3) // max(len(centers) - first - 1, 1)
        part = "cable_%02d" % (1 + min(seg, 2))
        t.add_ring(ctr, v=k / float(len(centers)), part=part)
        if len(t.rings) > 1:
            t.bridge(len(t.rings) - 2, len(t.rings) - 1, mat=M_OPTIC)
        else:
            t.cap(0, center=c, flip=True, mat=M_OPTIC)
    t.cap(len(t.rings) - 1, center=centers[-1], flip=False, mat=M_OPTIC)
    # cable connector on the arm
    conn = [Vector((-0.176, 0.010, 1.196)), Vector((-0.180, -0.006, 1.186))]
    tube(mb, conn, [0.010, 0.008], M_METAL, "cable_03", sides=10)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_gear(mb, arms, legs, head, eyes=None, torso_profile=None,
               hands=None):
    import mr_body
    if torso_profile is None:
        torso_profile = mr_body.torso_profile
    arm_axis = mr_body.arm_axis
    head_profile = mr_body.head_profile

    build_hair(mb, head_profile)
    build_collar(mb, torso_profile)
    build_chest_plate(mb, torso_profile)
    build_pauldrons(mb, arms)
    build_belt(mb, torso_profile)
    build_limb_plates(mb, legs)
    build_boot_cuffs(mb)
    build_backpack(mb, torso_profile)
    build_cyber_arm(mb, arm_axis)
    build_emitter(mb, arm_axis)
    build_blade(mb, arm_axis)
    centers, _ = arm_axis(1)
    wrist = centers[-1]
    if hands and 1 in hands:
        wrist = hands[1]["wrist"]
    hand_c = wrist + mr_body.HAND_DIR * 0.085
    build_power_cell(mb, hand_c)
    build_beacon(mb, hand_c + Vector((0.0, -0.02, -0.07)))
    return True


PART_MATERIAL = {
    "torso": M_SUIT,
    "arm_r": M_SUIT, "arm_l": M_SUIT,
    "leg_r": M_SUIT, "leg_l": M_SUIT,
    "boot_r": M_SUIT, "boot_l": M_SUIT,
    "head": M_FACE,
    "neck": M_FACE,
    "hand_r": M_SKIN, "hand_l": M_SKIN,
    "eye_r": M_FACE, "eye_l": M_FACE,
    "iris_r": M_OPTIC, "iris_l": M_OPTIC,
    "pupil_r": M_OPTIC, "pupil_l": M_OPTIC,
    "lid_up_r": M_FACE, "lid_up_l": M_FACE,
    "lid_lo_r": M_FACE, "lid_lo_l": M_FACE,
    "brow_r": M_OPTIC, "brow_l": M_OPTIC,
    "mouth_cav": M_OPTIC,
    "teeth_up": M_FACE, "teeth_lo": M_FACE,
    "tongue": M_SKIN,
    "chest_plate": M_ARMOR,
    "collar": M_ARMOR,
    "belt": M_ARMOR,
    "back_pack": M_ARMOR,
    "pauldron_r": M_ARMOR, "pauldron_l": M_ARMOR,
    "legplate_r": M_ARMOR, "legplate_l": M_ARMOR,
    "bootcuff_r": M_ARMOR, "bootcuff_l": M_ARMOR,
    "cyber_arm": M_METAL,
    "emitter": M_METAL,
    "blade_r": M_METAL,
    "cell_r": M_METAL,
    "beacon": M_METAL,
    "hair_01": M_OPTIC,
    "cable_01": M_OPTIC, "cable_02": M_OPTIC, "cable_03": M_METAL,
}


def assign_part_materials(mb):
    """Set the material index of every face from its owning part.

    The team accent is always authored explicitly (pauldron chevrons, boot
    cuff strips) and shares the part name of the armour it sits on, so it
    must not be overwritten by the part lookup.
    """
    changed = 0
    for i, face in enumerate(mb.faces):
        if mb.face_mat[i] == M_ACCENT:
            continue
        part = mb.part[face[0]]
        mat = PART_MATERIAL.get(part)
        if mat is not None and mat != mb.face_mat[i]:
            mb.face_mat[i] = mat
            changed += 1
    return changed
