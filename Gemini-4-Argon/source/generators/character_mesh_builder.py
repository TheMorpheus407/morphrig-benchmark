#!/usr/bin/env python3
"""
Procedural Character Geometry, UV, and Shape-Key Builder for MorphRig Operative ("Vex").

Builds the original adult human-like cyberpunk Operative from procedural parametric surfaces
at exact 1.800 m standing height (Z = 0.000 m soles to Z = 1.800 m crown, facing -Y in Blender):
  - Expressive human face with eye sockets, upper/lower eyelids, eyeballs, nose, lips,
    inner oral cavity, upper/lower dental arches, articulated tongue, ears, jaw, and neck.
  - Fitted cyberpunk tactical suit and articulated joint topology (shoulders, elbows, wrists,
    hips, knees, ankles, toes).
  - Organic left forearm and 5-finger articulated hand.
  - Cybernetic right forearm and 5-finger mechanical hand with integrated wrist emitter
    and retractable forearm blade.
  - Hard composite chest armor, shoulder pauldrons with team-accent badges, collar, knee guards.
  - Secondary-motion neural occipital tether cable and tactical hip data-strap.
  - Removable hex-core power cell and deployable tri-fin micro-beacon/drone props.
  - True multi-resolution LOD0, LOD1, and LOD2 meshes with clean UVs, 6 PBR material slots,
    and 38 facial + corrective Shape Keys (Morph Targets).
"""

import math
from typing import Dict, List, Tuple
import bpy
import bmesh
from mathutils import Vector, Matrix


MATERIAL_NAMES = [
    "M_Operative_Skin",          # Slot 0
    "M_Operative_Eyes",          # Slot 1
    "M_Operative_Suit",          # Slot 2
    "M_Operative_Armor",         # Slot 3
    "M_Operative_CyberArm",      # Slot 4
    "M_Operative_Props_Accent",  # Slot 5
]


class MeshAccumulator:
    """Accumulates vertices, faces, UVs, material indices, and anatomical part tags."""

    def __init__(self):
        self.verts: List[Vector] = []
        self.faces: List[Tuple[int, ...]] = []
        self.face_uvs: List[List[Tuple[float, float]]] = []
        self.face_mats: List[int] = []
        self.vert_tags: List[str] = []

    def add_vert(self, co: Vector, tag: str = "body") -> int:
        idx = len(self.verts)
        self.verts.append(Vector(co))
        self.vert_tags.append(tag)
        return idx

    def add_quad(
        self,
        i0: int,
        i1: int,
        i2: int,
        i3: int,
        uv0: Tuple[float, float],
        uv1: Tuple[float, float],
        uv2: Tuple[float, float],
        uv3: Tuple[float, float],
        mat_idx: int,
        flip: bool = False,
    ):
        if flip:
            self.faces.append((i0, i3, i2, i1))
            self.face_uvs.append([uv0, uv3, uv2, uv1])
        else:
            self.faces.append((i0, i1, i2, i3))
            self.face_uvs.append([uv0, uv1, uv2, uv3])
        self.face_mats.append(mat_idx)

    def add_tri(
        self,
        i0: int,
        i1: int,
        i2: int,
        uv0: Tuple[float, float],
        uv1: Tuple[float, float],
        uv2: Tuple[float, float],
        mat_idx: int,
        flip: bool = False,
    ):
        if flip:
            self.faces.append((i0, i2, i1))
            self.face_uvs.append([uv0, uv2, uv1])
        else:
            self.faces.append((i0, i1, i2))
            self.face_uvs.append([uv0, uv1, uv2])
        self.face_mats.append(mat_idx)

    def add_lofted_tube(
        self,
        rings: List[List[Vector]],
        mat_idx: int,
        tag: str,
        uv_box: Tuple[float, float, float, float] = (0.05, 0.05, 0.95, 0.95),
        closed_u: bool = True,
        cap_start: bool = False,
        cap_end: bool = False,
        flip_normals: bool = False,
        ring_tags: List[str] = None,
        ring_mats: List[int] = None,
    ) -> List[List[int]]:
        """Loft a sequence of cross-section rings into quads with clean UV mapping."""
        u0, v0, u1, v1 = uv_box
        n_rings = len(rings)
        n_seg = len(rings[0])
        ring_indices: List[List[int]] = []

        for r_idx, ring in enumerate(rings):
            t_tag = ring_tags[r_idx] if ring_tags else tag
            row = [self.add_vert(pt, t_tag) for pt in ring]
            ring_indices.append(row)

        for r_idx in range(n_rings - 1):
            va = v0 + (v1 - v0) * (r_idx / float(max(1, n_rings - 1)))
            vb = v0 + (v1 - v0) * ((r_idx + 1) / float(max(1, n_rings - 1)))
            m_idx = ring_mats[r_idx] if ring_mats else mat_idx
            limit = n_seg if closed_u else (n_seg - 1)
            for s_idx in range(limit):
                s_next = (s_idx + 1) % n_seg
                ua = u0 + (u1 - u0) * (s_idx / float(n_seg if closed_u else max(1, n_seg - 1)))
                ub = u0 + (u1 - u0) * ((s_idx + 1) / float(n_seg if closed_u else max(1, n_seg - 1)))
                self.add_quad(
                    ring_indices[r_idx][s_idx],
                    ring_indices[r_idx][s_next],
                    ring_indices[r_idx + 1][s_next],
                    ring_indices[r_idx + 1][s_idx],
                    (ua, va),
                    (ub, va),
                    (ub, vb),
                    (ua, vb),
                    m_idx,
                    flip=flip_normals,
                )

        if cap_start and closed_u:
            center = sum(rings[0], Vector((0.0, 0.0, 0.0))) / float(n_seg)
            c_idx = self.add_vert(center, ring_tags[0] if ring_tags else tag)
            uc, vc = 0.5 * (u0 + u1), v0
            m_idx = ring_mats[0] if ring_mats else mat_idx
            for s_idx in range(n_seg):
                s_next = (s_idx + 1) % n_seg
                ua = u0 + (u1 - u0) * (s_idx / float(n_seg))
                ub = u0 + (u1 - u0) * ((s_idx + 1) / float(n_seg))
                self.add_tri(
                    c_idx,
                    ring_indices[0][s_next],
                    ring_indices[0][s_idx],
                    (uc, vc),
                    (ub, vc),
                    (ua, vc),
                    m_idx,
                    flip=flip_normals,
                )

        if cap_end and closed_u:
            center = sum(rings[-1], Vector((0.0, 0.0, 0.0))) / float(n_seg)
            c_idx = self.add_vert(center, ring_tags[-1] if ring_tags else tag)
            uc, vc = 0.5 * (u0 + u1), v1
            m_idx = ring_mats[-1] if ring_mats else mat_idx
            for s_idx in range(n_seg):
                s_next = (s_idx + 1) % n_seg
                ua = u0 + (u1 - u0) * (s_idx / float(n_seg))
                ub = u0 + (u1 - u0) * ((s_idx + 1) / float(n_seg))
                self.add_tri(
                    c_idx,
                    ring_indices[-1][s_idx],
                    ring_indices[-1][s_next],
                    (uc, vc),
                    (ua, vc),
                    (ub, vc),
                    m_idx,
                    flip=flip_normals,
                )

        return ring_indices


def make_ellipse_ring(
    center: Vector,
    rx: float,
    ry: float,
    n_seg: int,
    rot_matrix: Matrix = None,
    squareness: float = 0.0,
) -> List[Vector]:
    pts = []
    for i in range(n_seg):
        ang = 2.0 * math.pi * (i / float(n_seg))
        ca = math.cos(ang)
        sa = math.sin(ang)
        if squareness > 0.0:
            ca = math.copysign(abs(ca) ** (1.0 - 0.5 * squareness), ca)
            sa = math.copysign(abs(sa) ** (1.0 - 0.5 * squareness), sa)
        local = Vector((ca * rx, sa * ry, 0.0))
        if rot_matrix is not None:
            local = rot_matrix @ local
        pts.append(center + local)
    return pts


def subdivide_rings(rings: List[List[Vector]], steps: int) -> List[List[Vector]]:
    if steps <= 1:
        return rings
    out: List[List[Vector]] = []
    for i in range(len(rings) - 1):
        r0 = rings[i]
        r1 = rings[i + 1]
        for s in range(steps):
            alpha = s / float(steps)
            # Smooth hermite blend with subtle curvature preservation
            row = [r0[j].lerp(r1[j], alpha) for j in range(len(r0))]
            out.append(row)
    out.append(rings[-1])
    return out


def build_torso_and_neck(acc: MeshAccumulator, radial_seg: int, height_sub: int):
    """
    Build pelvis, abdomen, ribcage/chest, collar, and lower neck.
    Total height spans Z = 0.88 m (crotch/pelvis base) to Z = 1.56 m (upper neck).
    """
    # (z, center_y, rx, ry, squareness, mat_idx, tag)
    profile = [
        (0.87, 0.005, 0.125, 0.095, 0.1, 2, "pelvis"),
        (0.92, 0.002, 0.162, 0.115, 0.15, 2, "pelvis"),
        (0.98, 0.000, 0.168, 0.118, 0.20, 3, "pelvis"),    # Tactical utility belt
        (1.02, -0.002, 0.145, 0.102, 0.10, 2, "spine_01"),
        (1.08, -0.004, 0.132, 0.096, 0.10, 2, "spine_01"),  # Waist taper
        (1.15, -0.005, 0.146, 0.108, 0.15, 2, "spine_02"),
        (1.22, -0.008, 0.164, 0.124, 0.25, 3, "spine_02"),  # Lower chest rig armor
        (1.29, -0.012, 0.178, 0.134, 0.30, 3, "spine_03"),  # Pectoral chest armor
        (1.36, -0.008, 0.186, 0.126, 0.30, 3, "spine_03"),  # Upper chest / shoulder line
        (1.42, 0.000, 0.148, 0.104, 0.20, 3, "spine_03"),   # Collar base
        (1.46, 0.004, 0.072, 0.068, 0.05, 0, "neck_01"),    # Base of organic neck
        (1.51, 0.002, 0.058, 0.056, 0.00, 0, "neck_02"),
        (1.56, -0.002, 0.060, 0.058, 0.00, 0, "neck_02"),
    ]

    rings = []
    tags = []
    mats = []
    for idx in range(len(profile) - 1):
        p0 = profile[idx]
        p1 = profile[idx + 1]
        for s in range(height_sub):
            t = s / float(height_sub)
            z = p0[0] + (p1[0] - p0[0]) * t
            cy = p0[1] + (p1[1] - p0[1]) * t
            rx = p0[2] + (p1[2] - p0[2]) * t
            ry = p0[3] + (p1[3] - p0[3]) * t
            sq = p0[4] + (p1[4] - p0[4]) * t
            ring = make_ellipse_ring(Vector((0.0, cy, z)), rx, ry, radial_seg, squareness=sq)
            # Sculpt anatomical thoracic sternum groove and spinal channel
            for v_i, pt in enumerate(ring):
                ang = 2.0 * math.pi * (v_i / float(radial_seg))
                # Front is -Y (ang ~ 3*pi/2), Back is +Y (ang ~ pi/2)
                if 1.18 <= z <= 1.38:
                    # Pectoral / breastplate definition in front (-Y)
                    frontness = max(0.0, -math.sin(ang))
                    sternum = math.exp(-((pt.x / 0.035) ** 2)) * frontness
                    pt.y -= 0.014 * frontness * (1.0 - 0.6 * sternum)
                if 1.00 <= z <= 1.40:
                    # Spine groove on back (+Y)
                    backness = max(0.0, math.sin(ang))
                    spine_ch = math.exp(-((pt.x / 0.025) ** 2)) * backness
                    pt.y -= 0.008 * spine_ch
            rings.append(ring)
            mats.append(p0[5])
            tags.append(p0[6])

    p_last = profile[-1]
    rings.append(make_ellipse_ring(Vector((0.0, p_last[1], p_last[0])), p_last[2], p_last[3], radial_seg))
    mats.append(p_last[5])
    tags.append(p_last[6])

    acc.add_lofted_tube(
        rings,
        mat_idx=2,
        tag="spine_02",
        uv_box=(0.05, 0.28, 0.95, 0.95),
        closed_u=True,
        cap_start=True,
        cap_end=False,
        ring_tags=tags,
        ring_mats=mats,
    )

    # High cyberpunk armored collar (around back and sides of neck, open in front -Y)
    collar_seg = max(12, radial_seg // 2)
    collar_rings = []
    for r_i, (z, rad_scale, flare) in enumerate([(1.41, 1.0, 0.0), (1.46, 1.08, 0.012), (1.52, 1.14, 0.022), (1.54, 1.10, 0.018)]):
        row = []
        for s_i in range(collar_seg):
            # Span angle from -0.22*pi to +1.22*pi (covering right, back +Y, and left)
            ang = -0.20 * math.pi + 1.40 * math.pi * (s_i / float(collar_seg - 1))
            rx = (0.105 + flare) * math.cos(ang)
            ry = (0.095 + flare) * math.sin(ang) + 0.01
            row.append(Vector((rx, ry, z)))
        collar_rings.append(row)
    acc.add_lofted_tube(
        collar_rings,
        mat_idx=3,
        tag="spine_03",
        uv_box=(0.10, 0.10, 0.90, 0.45),
        closed_u=False,
    )

    # Dorsal team-accent beacon fin on upper back (reads clearly from 45-60 deg top-down camera!)
    fin_rings = []
    for z, w, y0, y1 in [(1.20, 0.022, 0.11, 0.155), (1.29, 0.026, 0.12, 0.175), (1.38, 0.022, 0.11, 0.160)]:
        fin_rings.append([
            Vector((-w, y0, z)),
            Vector((w, y0, z)),
            Vector((w * 0.6, y1, z)),
            Vector((-w * 0.6, y1, z)),
        ])
    acc.add_lofted_tube(
        fin_rings,
        mat_idx=5,  # M_Operative_Props_Accent
        tag="spine_03",
        uv_box=(0.20, 0.20, 0.80, 0.80),
        closed_u=True,
        cap_start=True,
        cap_end=True,
    )


def build_head_and_face(acc: MeshAccumulator, radial_seg: int, height_sub: int):
    """
    Build an expressive human head with sculpted facial anatomy:
      - Jawline, chin, cheeks, nasolabial contours, nose bridge & tip, brow ridge, forehead, cranium
      - Watertight stitched dual-ring mouth slit (mouth_slit_lower & mouth_slit_upper at Z = 1.598)
        connected to an internal oral cavity pocket so closed lips have zero gap and open-mouth
        speech parts into a smooth, natural mouth opening with zero holes!
      - Upper & lower dental arches (white enamel teeth) and articulated 3-segment tongue inside mouth
      - Recessed orbital eye sockets with visible spherical eyeballs (eye_l, eye_r) and upper/lower eyelids
      - Eyebrow strips seated cleanly on the brow ridge
    Standing crown reaches exact Z = 1.800 m!
    """
    n_u = max(24, radial_seg)
    base_levels = [
        (1.545, 0.056, 0.058, 0.004, "neck_02"),
        (1.568, 0.066, 0.078, -0.008, "head_chin"),
        (1.586, 0.074, 0.088, -0.012, "lip_lower"),
        (1.598, 0.077, 0.090, -0.014, "mouth_slit_lower"),
        (1.598, 0.077, 0.090, -0.014, "mouth_slit_upper"),
        (1.610, 0.079, 0.091, -0.014, "lip_upper"),
        (1.630, 0.083, 0.094, -0.012, "nose_base"),
        (1.652, 0.087, 0.096, -0.010, "cheek_mid"),
        (1.674, 0.089, 0.097, -0.010, "eye_lower"),
        (1.686, 0.090, 0.097, -0.010, "eye_center"),
        (1.698, 0.090, 0.098, -0.011, "eye_upper"),
        (1.716, 0.089, 0.099, -0.012, "brow_ridge"),
        (1.745, 0.086, 0.098, -0.008, "forehead"),
        (1.775, 0.074, 0.086, 0.000, "cranium"),
        (1.794, 0.046, 0.052, 0.004, "cranium"),
        (1.800, 0.014, 0.016, 0.006, "cranium"),
    ]

    levels = []
    for i in range(len(base_levels) - 1):
        b0 = base_levels[i]
        b1 = base_levels[i + 1]
        if b0[4] == "mouth_slit_lower" and b1[4] == "mouth_slit_upper":
            levels.append(b0)
            continue
        steps = height_sub if b0[4] not in ("lip_lower", "mouth_slit_lower", "mouth_slit_upper", "eye_lower", "eye_center") else 1
        for s in range(steps):
            t = s / float(steps)
            levels.append((
                b0[0] + (b1[0] - b0[0]) * t,
                b0[1] + (b1[1] - b0[1]) * t,
                b0[2] + (b1[2] - b0[2]) * t,
                b0[3] + (b1[3] - b0[3]) * t,
                b0[4] if t < 0.5 else b1[4],
            ))
    levels.append(base_levels[-1])

    ring_indices: List[List[int]] = []
    ring_uvs: List[List[Tuple[float, float]]] = []
    slit_lower_r_idx = -1
    slit_upper_r_idx = -1

    for r_idx, (z, rx, ry, cy, region) in enumerate(levels):
        if region == "mouth_slit_lower":
            slit_lower_r_idx = r_idx
        elif region == "mouth_slit_upper":
            slit_upper_r_idx = r_idx

        row_idx = []
        row_uv = []
        # Map Z height directly to UV V in [0.30, 0.94] so lips (Z=1.598) sit at exact V=0.45!
        v_coord = 0.30 + 0.64 * ((z - 1.545) / (1.800 - 1.545))
        for s_idx in range(n_u):
            u_norm = s_idx / float(n_u)
            ang = 0.5 * math.pi + 2.0 * math.pi * u_norm
            ca = math.cos(ang)
            sa = math.sin(ang)

            x = ca * rx
            y = cy + sa * ry
            pz = z
            v_tag = "head"

            if sa < -0.10:
                front_w = math.sin(min(1.0, (-sa - 0.10) / 0.90) * 0.5 * math.pi)
                abs_x = abs(x)

                # Smooth chin prominence
                if 1.555 <= z < 1.585:
                    chin_w = math.exp(-((abs_x / 0.034) ** 2)) * math.sin(((z - 1.555) / 0.030) * math.pi)
                    y -= 0.005 * chin_w * front_w
                    if abs_x < 0.042:
                        v_tag = "jaw"

                # Sculpted lips around mouth slit (Z ~ 1.582 .. 1.614, |X| < 0.034)
                if 1.582 <= z <= 1.614 and abs_x < 0.034:
                    mouth_w = math.cos(min(1.0, abs_x / 0.034) * 0.5 * math.pi) ** 1.3
                    if region == "mouth_slit_lower":
                        y -= 0.007 * mouth_w
                        if abs_x < 0.010:
                            v_tag = "lip_lower_mid"
                        elif abs_x < 0.022:
                            v_tag = "lip_lower_l" if x > 0 else "lip_lower_r"
                        else:
                            v_tag = "lip_corner_l" if x > 0 else "lip_corner_r"
                    elif region == "mouth_slit_upper":
                        y -= 0.007 * mouth_w
                        if abs_x < 0.010:
                            v_tag = "lip_upper_mid"
                        elif abs_x < 0.022:
                            v_tag = "lip_upper_l" if x > 0 else "lip_upper_r"
                        else:
                            v_tag = "lip_corner_l" if x > 0 else "lip_corner_r"
                    elif region == "lip_lower":
                        y -= 0.008 * mouth_w
                        if abs_x < 0.012:
                            v_tag = "lip_lower_mid"
                        else:
                            v_tag = "lip_lower_l" if x > 0 else "lip_lower_r"
                    elif region == "lip_upper":
                        y -= 0.009 * mouth_w
                        if abs_x < 0.012:
                            v_tag = "lip_upper_mid"
                        else:
                            v_tag = "lip_upper_l" if x > 0 else "lip_upper_r"

                # Nose bridge, tip, and nostrils
                if 1.620 <= z <= 1.702 and abs_x < 0.024:
                    nose_x_w = math.cos((abs_x / 0.024) * 0.5 * math.pi) ** 1.6
                    nose_z_t = (1.702 - z) / 0.082
                    nose_profile = math.sin(min(1.0, max(0.0, nose_z_t)) * math.pi * 0.85)
                    y -= 0.022 * nose_x_w * nose_profile
                    if z < 1.640 and abs_x > 0.008:
                        v_tag = "nostril_l" if x > 0 else "nostril_r"

                # Cheekbones
                if 1.630 <= z <= 1.675 and 0.024 <= abs_x <= 0.074:
                    cheek_w = math.exp(-(((abs_x - 0.046) / 0.020) ** 2)) * math.sin(((z - 1.630) / 0.045) * math.pi)
                    y -= 0.006 * cheek_w
                    v_tag = "cheek_l" if x > 0 else "cheek_r"

                # Recessed orbital eye sockets around X = +/-0.032, Z = 1.686
                eye_dx = abs_x - 0.032
                eye_dz = z - 1.686
                eye_dist_norm = math.sqrt((eye_dx / 0.021) ** 2 + (eye_dz / 0.016) ** 2)
                if eye_dist_norm < 1.0:
                    socket_depth = (math.cos(eye_dist_norm * 0.5 * math.pi) ** 1.5)
                    y += 0.022 * socket_depth
                    if eye_dz >= 0.0:
                        v_tag = "eyelid_upper_l" if x > 0 else "eyelid_upper_r"
                    else:
                        v_tag = "eyelid_lower_l" if x > 0 else "eyelid_lower_r"

                # Brow ridge
                if 1.705 <= z <= 1.728 and abs_x < 0.064:
                    brow_w = math.cos((abs_x / 0.064) * 0.5 * math.pi) * math.sin(((z - 1.705) / 0.023) * math.pi)
                    y -= 0.008 * brow_w
                    if abs_x < 0.022:
                        v_tag = "brow_inner_l" if x > 0 else "brow_inner_r"
                    elif abs_x < 0.042:
                        v_tag = "brow_mid_l" if x > 0 else "brow_mid_r"
                    else:
                        v_tag = "brow_outer_l" if x > 0 else "brow_outer_r"

            # Ears on lateral sides
            if abs(sa) < 0.22 and 1.645 <= z <= 1.700:
                ear_flare = math.sin(((z - 1.645) / 0.055) * math.pi) * (1.0 - abs(sa) / 0.22)
                x += math.copysign(0.013 * ear_flare, x)
                y += 0.005 * ear_flare

            idx = acc.add_vert(Vector((x, y, pz)), v_tag)
            row_idx.append(idx)
            u_coord = 0.08 + 0.84 * u_norm
            row_uv.append((u_coord, v_coord))

        ring_indices.append(row_idx)
        ring_uvs.append(row_uv)

    # Connect rings, leaving the 4 front lip segments (|x| < 0.032) between slit_lower and slit_upper open
    # and stitched to the internal oral cavity pocket!
    mouth_open_s_indices = []
    for r_idx in range(len(ring_indices) - 1):
        is_slit_pair = (r_idx == slit_lower_r_idx and (r_idx + 1) == slit_upper_r_idx)
        for s_idx in range(n_u):
            s_next = (s_idx + 1) % n_u
            if is_slit_pair:
                v0 = acc.verts[ring_indices[r_idx][s_idx]]
                v1 = acc.verts[ring_indices[r_idx][s_next]]
                if v0.y < -0.075 and v1.y < -0.075 and abs(v0.x) < 0.032 and abs(v1.x) < 0.032:
                    mouth_open_s_indices.append((s_idx, s_next))
                    continue
            # Assign dark hair material (mat_idx=2) to scalp/crown & back undercut so there is zero bald strip
            z_face = levels[r_idx][0]
            v_curr = acc.verts[ring_indices[r_idx][s_idx]]
            is_scalp_hair = (z_face >= 1.744) or (z_face >= 1.665 and v_curr.y > -0.015)
            face_mat = 2 if is_scalp_hair else 0
            acc.add_quad(
                ring_indices[r_idx][s_idx],
                ring_indices[r_idx][s_next],
                ring_indices[r_idx + 1][s_next],
                ring_indices[r_idx + 1][s_idx],
                ring_uvs[r_idx][s_idx],
                ring_uvs[r_idx][s_next],
                ring_uvs[r_idx + 1][s_next],
                ring_uvs[r_idx + 1][s_idx],
                mat_idx=face_mat,
            )

    # Stitch an internal oral cavity pocket directly to the upper and lower lip slit vertices
    if mouth_open_s_indices and slit_lower_r_idx >= 0:
        inner_lower_map = {}
        inner_upper_map = {}
        ordered_s = [mouth_open_s_indices[0][0]] + [pair[1] for pair in mouth_open_s_indices]
        for s_i in ordered_s:
            v_low = acc.verts[ring_indices[slit_lower_r_idx][s_i]]
            v_up = acc.verts[ring_indices[slit_upper_r_idx][s_i]]
            inner_lower_map[s_i] = acc.add_vert(Vector((v_low.x * 0.85, v_low.y + 0.026, v_low.z - 0.004)), "lip_lower_mid")
            inner_upper_map[s_i] = acc.add_vert(Vector((v_up.x * 0.85, v_up.y + 0.026, v_up.z + 0.004)), "head")

        for s_idx, s_next in mouth_open_s_indices:
            # Lower lip inner mucosa wall
            acc.add_quad(
                ring_indices[slit_lower_r_idx][s_idx],
                ring_indices[slit_lower_r_idx][s_next],
                inner_lower_map[s_next],
                inner_lower_map[s_idx],
                (0.15, 0.12), (0.35, 0.12), (0.35, 0.05), (0.15, 0.05),
                mat_idx=0,
            )
            # Upper lip inner mucosa wall
            acc.add_quad(
                inner_upper_map[s_idx],
                inner_upper_map[s_next],
                ring_indices[slit_upper_r_idx][s_next],
                ring_indices[slit_upper_r_idx][s_idx],
                (0.15, 0.05), (0.35, 0.05), (0.35, 0.12), (0.15, 0.12),
                mat_idx=0,
            )
            # Back throat wall connecting inner_lower to inner_upper (dark shadowed interior)
            acc.add_quad(
                inner_lower_map[s_idx],
                inner_lower_map[s_next],
                inner_upper_map[s_next],
                inner_upper_map[s_idx],
                (0.15, 0.05), (0.35, 0.05), (0.35, 0.15), (0.15, 0.15),
                mat_idx=2,
            )
        s_first = ordered_s[0]
        s_last = ordered_s[-1]
        acc.add_tri(
            ring_indices[slit_lower_r_idx][s_first],
            inner_lower_map[s_first],
            inner_upper_map[s_first],
            (0.15, 0.10), (0.20, 0.05), (0.20, 0.15),
            mat_idx=0,
        )
        acc.add_tri(
            ring_indices[slit_upper_r_idx][s_last],
            inner_upper_map[s_last],
            inner_lower_map[s_last],
            (0.35, 0.10), (0.30, 0.15), (0.30, 0.05),
            mat_idx=0,
        )

    # Cap the crown at Z = 1.800 m with hair material (mat_idx=2)
    crown_idx = acc.add_vert(Vector((0.0, 0.006, 1.800)), "head")
    for s_idx in range(n_u):
        s_next = (s_idx + 1) % n_u
        acc.add_tri(
            crown_idx,
            ring_indices[-1][s_idx],
            ring_indices[-1][s_next],
            (0.5, 0.98),
            ring_uvs[-1][s_idx],
            ring_uvs[-1][s_next],
            mat_idx=2,
        )

    # Build visible spherical eyeballs (eye_l at +X, eye_r at -X) seated in the orbital sockets!
    eye_rings_n = max(8, radial_seg // 3)
    eye_seg_n = max(12, radial_seg // 2)
    for side_sign, eye_tag in [(1.0, "eye_l"), (-1.0, "eye_r")]:
        eye_center = Vector((side_sign * 0.032, -0.095, 1.686))
        eye_rad = 0.0135
        e_rings = []
        for r_i in range(eye_rings_n + 1):
            phi = math.pi * (r_i / float(eye_rings_n))
            cy_e = -math.cos(phi) * eye_rad
            r_ring = max(0.0008, math.sin(phi) * eye_rad)
            row = []
            for s_i in range(eye_seg_n):
                theta = 2.0 * math.pi * (s_i / float(eye_seg_n))
                px = math.cos(theta) * r_ring
                pz = math.sin(theta) * r_ring
                row.append(eye_center + Vector((px, cy_e, pz)))
            e_rings.append(row)

        e_indices = [[acc.add_vert(pt, eye_tag) for pt in row] for row in e_rings]
        for r_i in range(eye_rings_n):
            rad_a = 0.46 * (r_i / float(eye_rings_n))
            rad_b = 0.46 * ((r_i + 1) / float(eye_rings_n))
            for s_i in range(eye_seg_n):
                s_next = (s_i + 1) % eye_seg_n
                ta = 2.0 * math.pi * (s_i / float(eye_seg_n))
                tb = 2.0 * math.pi * ((s_i + 1) / float(eye_seg_n))
                uva = (0.5 + rad_a * math.cos(ta), 0.5 + rad_a * math.sin(ta))
                uvb = (0.5 + rad_a * math.cos(tb), 0.5 + rad_a * math.sin(tb))
                uvc = (0.5 + rad_b * math.cos(tb), 0.5 + rad_b * math.sin(tb))
                uvd = (0.5 + rad_b * math.cos(ta), 0.5 + rad_b * math.sin(ta))
                acc.add_quad(
                    e_indices[r_i][s_i],
                    e_indices[r_i][s_next],
                    e_indices[r_i + 1][s_next],
                    e_indices[r_i + 1][s_i],
                    uva,
                    uvb,
                    uvc,
                    uvd,
                    mat_idx=1,  # M_Operative_Eyes
                )

        # Upper and lower eyelid hoods framing the exposed iris/cornea cleanly
        for lid_is_upper in (True, False):
            lid_tag = f"eyelid_{'upper' if lid_is_upper else 'lower'}_{'l' if side_sign > 0 else 'r'}"
            z_sign = 1.0 if lid_is_upper else -1.0
            lid_rings = []
            for ang_elev, r_mult in [(0.34, 1.06), (0.64, 1.12), (1.02, 1.08)]:
                row = []
                for s_i in range(10):
                    u_t = (s_i / 9.0) * 2.0 - 1.0
                    lx = u_t * eye_rad * 1.18
                    lz = z_sign * math.sin(ang_elev) * eye_rad * r_mult * math.cos(u_t * 0.72)
                    ly = -math.cos(ang_elev) * eye_rad * r_mult * math.cos(u_t * 0.55)
                    row.append(eye_center + Vector((lx, ly, lz)))
                lid_rings.append(row)
            acc.add_lofted_tube(
                lid_rings,
                mat_idx=0,
                tag=lid_tag,
                uv_box=(0.40, 0.72, 0.60, 0.76),
                closed_u=False,
                flip_normals=not lid_is_upper,
            )

        # High-contrast sculpted eyebrow strip seated proudly in front of the brow ridge
        brow_rings = []
        for z_off in (-0.0035, 0.0035):
            row = []
            for s_i in range(8):
                u_t = s_i / 7.0
                bx = side_sign * (0.012 + 0.040 * u_t)
                bz = 1.712 + 0.006 * math.sin(u_t * math.pi) + z_off
                by = -0.1165 + 0.015 * (u_t ** 1.6)
                row.append(Vector((bx, by, bz)))
            brow_rings.append(row)
        acc.add_lofted_tube(
            brow_rings,
            mat_idx=2,  # Dark slate eyebrow pigment
            tag=f"brow_mid_{'l' if side_sign > 0 else 'r'}",
            uv_box=(0.2, 0.2, 0.4, 0.3),
            closed_u=False,
            flip_normals=(side_sign < 0),
        )

    # Upper & Lower Dental Arches (Teeth) inside oral cavity (Y ~ -0.098 .. -0.088)
    for is_upper in (True, False):
        t_tag = "head" if is_upper else "jaw"
        z_base = 1.603 if is_upper else 1.593
        z_tip = 1.5982 if is_upper else 1.5978
        arch_rings = []
        for z_curr, _ in [(z_base, 0.004), (z_tip, 0.002)]:
            row = []
            for s_i in range(10):
                ang = -0.35 * math.pi + 0.70 * math.pi * (s_i / 9.0)
                tx = math.sin(ang) * 0.018
                ty = -0.080 - math.cos(ang) * 0.017
                row.append(Vector((tx, ty, z_curr)))
            arch_rings.append(row)
        acc.add_lofted_tube(
            arch_rings,
            mat_idx=0,
            tag=t_tag,
            uv_box=(0.60, 0.04, 0.92, 0.16),
            closed_u=False,
            flip_normals=is_upper,
        )

    # Articulated Tongue (tongue_01 base -> tongue_02 tip) safely inside oral cavity
    tongue_rings = []
    tongue_tags = []
    for y_t, z_t, rx_t, rz_t, t_tag in [
        (-0.068, 1.592, 0.011, 0.0035, "tongue_01"),
        (-0.078, 1.593, 0.011, 0.0035, "tongue_01"),
        (-0.086, 1.594, 0.009, 0.0030, "tongue_02"),
        (-0.093, 1.595, 0.005, 0.0018, "tongue_02"),
    ]:
        rot = Matrix.Rotation(0.5 * math.pi, 3, "X")
        tongue_rings.append(make_ellipse_ring(Vector((0.0, y_t, z_t)), rx_t, rz_t, 10, rot_matrix=rot))
        tongue_tags.append(t_tag)
    acc.add_lofted_tube(
        tongue_rings,
        mat_idx=0,
        tag="tongue_02",
        uv_box=(0.10, 0.04, 0.42, 0.18),
        closed_u=True,
        cap_end=True,
        ring_tags=tongue_tags,
    )

    # Stylized sculpted short cyberpunk hair / undercut crown cap seated cleanly outside cranium
    hair_rings = []
    for z_h, rx_h, ry_h, cy_h in [
        (1.700, 0.095, 0.104, 0.004),
        (1.745, 0.093, 0.106, -0.002),
        (1.782, 0.080, 0.094, -0.004),
        (1.800, 0.034, 0.042, 0.000),
    ]:
        row = []
        for s_i in range(16):
            ang = -0.15 * math.pi + 1.30 * math.pi * (s_i / 15.0)
            row.append(Vector((math.cos(ang) * rx_h, cy_h + math.sin(ang) * ry_h, z_h)))
        hair_rings.append(row)
    acc.add_lofted_tube(
        hair_rings,
        mat_idx=2,
        tag="head",
        uv_box=(0.10, 0.70, 0.90, 0.95),
        closed_u=False,
    )


def build_legs_and_boots(acc: MeshAccumulator, radial_seg: int, height_sub: int):
    """
    Build left and right legs with dense joint topology at hips, knees, ankles, and toe balls.
    Planted flat on ground Z = 0.000 m.
    """
    leg_seg = max(14, (radial_seg * 2) // 3)
    for side_sign, side_s in [(1.0, "l"), (-1.0, "r")]:
        hip_x = side_sign * 0.098
        # (z, y_off, rx, ry, mat_idx, tag)
        leg_profile = [
            (0.90, 0.004, 0.088, 0.092, 2, f"thigh_{side_s}"),
            (0.84, 0.002, 0.086, 0.090, 2, f"thigh_{side_s}"),
            (0.74, 0.000, 0.078, 0.082, 2, f"thigh_twist_01_{side_s}"),
            (0.62, 0.002, 0.066, 0.068, 2, f"thigh_twist_01_{side_s}"),
            # Intentional 5-loop knee deformation zone
            (0.54, -0.002, 0.060, 0.062, 3, f"thigh_twist_01_{side_s}"),
            (0.51, -0.006, 0.059, 0.063, 3, f"calf_{side_s}"),  # Knee center
            (0.48, -0.003, 0.057, 0.060, 3, f"calf_{side_s}"),
            (0.38, 0.008, 0.062, 0.066, 2, f"calf_{side_s}"),   # Calf muscle gastrocnemius
            (0.26, 0.004, 0.050, 0.054, 3, f"calf_twist_01_{side_s}"),  # Shin armor boot top
            (0.15, 0.002, 0.044, 0.048, 3, f"calf_twist_01_{side_s}"),
            (0.10, 0.004, 0.042, 0.046, 3, f"foot_{side_s}"),   # Ankle joint loop
            (0.07, 0.006, 0.044, 0.050, 3, f"foot_{side_s}"),
        ]

        rings = []
        tags = []
        mats = []
        for idx in range(len(leg_profile) - 1):
            p0 = leg_profile[idx]
            p1 = leg_profile[idx + 1]
            for s in range(height_sub):
                t = s / float(height_sub)
                z = p0[0] + (p1[0] - p0[0]) * t
                cy = p0[1] + (p1[1] - p0[1]) * t
                rx = p0[2] + (p1[2] - p0[2]) * t
                ry = p0[3] + (p1[3] - p0[3]) * t
                rings.append(make_ellipse_ring(Vector((hip_x, cy, z)), rx, ry, leg_seg, squareness=0.15))
                mats.append(p0[4])
                tags.append(p0[5])
        p_last = leg_profile[-1]
        rings.append(make_ellipse_ring(Vector((hip_x, p_last[1], p_last[0])), p_last[2], p_last[3], leg_seg, squareness=0.15))
        mats.append(p_last[4])
        tags.append(p_last[5])

        acc.add_lofted_tube(
            rings,
            mat_idx=2,
            tag=f"thigh_{side_s}",
            uv_box=(0.05, 0.05, 0.95, 0.95),
            closed_u=True,
            cap_start=True,
            cap_end=False,
            ring_tags=tags,
            ring_mats=mats,
        )

        # Combat Boot & Articulated Toe Box (planted flat at Z = 0.000 m, heel at Y=+0.055, toe at Y=-0.165)
        boot_rings = []
        boot_tags = []
        for y_b, z_top, width_x, b_tag in [
            (0.055, 0.072, 0.042, f"foot_{side_s}"),
            (0.015, 0.078, 0.046, f"foot_{side_s}"),
            (-0.045, 0.064, 0.048, f"foot_{side_s}"),
            (-0.095, 0.048, 0.050, f"ball_{side_s}"),   # Metatarsal ball joint loop
            (-0.135, 0.038, 0.046, f"ball_{side_s}"),
            (-0.168, 0.026, 0.034, f"ball_{side_s}"),
        ]:
            row = []
            for s_i in range(leg_seg):
                ang = 2.0 * math.pi * (s_i / float(leg_seg))
                bx = hip_x + math.cos(ang) * width_x
                sz = math.sin(ang)
                if sz < 0.0:
                    bz = 0.000
                else:
                    bz = sz * z_top
                row.append(Vector((bx, y_b, bz)))
            boot_rings.append(row)
            boot_tags.append(b_tag)

        acc.add_lofted_tube(
            boot_rings,
            mat_idx=3,
            tag=f"foot_{side_s}",
            uv_box=(0.10, 0.10, 0.90, 0.90),
            closed_u=True,
            cap_start=True,
            cap_end=True,
            ring_tags=boot_tags,
        )


def build_arms_hands_and_cyberware(acc: MeshAccumulator, radial_seg: int, height_sub: int):
    """
    Build both arms in a clean A/T-relaxed neutral stance (along +/-X axis at Z ~ 1.37 m):
      - Left arm (+X): tactical sleeve upper arm, organic skin forearm & 5-finger articulated hand.
      - Right arm (-X): tactical shoulder + visibly cybernetic mechanical forearm, 5-finger
        articulated cyber-hand, integrated dorsal wrist emitter, and retractable forearm blade.
      - Shoulder armor pauldrons with Team Accent crest badges on both shoulders.
    """
    arm_seg = max(12, radial_seg // 2)
    rot_yz = Matrix.Rotation(0.5 * math.pi, 3, "Y")

    for side_sign, side_s in [(1.0, "l"), (-1.0, "r")]:
        is_cyber = side_s == "r"
        forearm_mat = 4 if is_cyber else 0  # M_Operative_CyberArm on right, M_Operative_Skin on left
        hand_mat = 4 if is_cyber else 0

        arm_profile = [
            (0.165, 0.000, 1.375, 0.056, 0.058, 2, f"clavicle_{side_s}"),
            (0.205, 0.002, 1.370, 0.054, 0.056, 2, f"upperarm_{side_s}"),
            (0.275, 0.006, 1.365, 0.048, 0.050, 2, f"upperarm_{side_s}"),
            (0.355, 0.012, 1.360, 0.044, 0.046, 2, f"upperarm_twist_01_{side_s}"),
            # 5-loop elbow joint region around |X| = 0.435
            (0.415, 0.016, 1.356, 0.041, 0.043, 2, f"upperarm_twist_01_{side_s}"),
            (0.435, 0.018, 1.355, 0.040, 0.042, forearm_mat, f"lowerarm_{side_s}"),
            (0.455, 0.015, 1.354, 0.043, 0.045, forearm_mat, f"lowerarm_{side_s}"),
            (0.525, 0.008, 1.352, 0.042, 0.044, forearm_mat, f"lowerarm_{side_s}"),
            (0.605, 0.000, 1.350, 0.036, 0.038, forearm_mat, f"lowerarm_twist_01_{side_s}"),
            # Wrist joint loops at |X| = 0.680 .. 0.700
            (0.675, -0.004, 1.349, 0.030, 0.024, forearm_mat, f"lowerarm_twist_01_{side_s}"),
            (0.695, -0.005, 1.348, 0.031, 0.022, hand_mat, f"hand_{side_s}"),
            # Palm (|X| = 0.700 .. 0.775)
            (0.735, -0.005, 1.348, 0.042, 0.016, hand_mat, f"hand_{side_s}"),
            (0.775, -0.005, 1.348, 0.044, 0.014, hand_mat, f"hand_{side_s}"),
        ]

        rings = []
        tags = []
        mats = []
        for idx in range(len(arm_profile) - 1):
            p0 = arm_profile[idx]
            p1 = arm_profile[idx + 1]
            for s in range(height_sub):
                t = s / float(height_sub)
                ax = side_sign * (p0[0] + (p1[0] - p0[0]) * t)
                ay = p0[1] + (p1[1] - p0[1]) * t
                az = p0[2] + (p1[2] - p0[2]) * t
                ry = p0[3] + (p1[3] - p0[3]) * t
                rz = p0[4] + (p1[4] - p0[4]) * t
                sq = 0.35 if (is_cyber and p0[0] >= 0.43) else 0.08
                ring = make_ellipse_ring(Vector((ax, ay, az)), rz, ry, arm_seg, rot_matrix=rot_yz, squareness=sq)
                rings.append(ring)
                mats.append(p0[5])
                tags.append(p0[6])
        p_last = arm_profile[-1]
        rings.append(
            make_ellipse_ring(
                Vector((side_sign * p_last[0], p_last[1], p_last[2])),
                p_last[4],
                p_last[3],
                arm_seg,
                rot_matrix=rot_yz,
                squareness=0.25,
            )
        )
        mats.append(p_last[5])
        tags.append(p_last[6])

        acc.add_lofted_tube(
            rings,
            mat_idx=forearm_mat,
            tag=f"lowerarm_{side_s}",
            uv_box=(0.08, 0.30, 0.92, 0.92),
            closed_u=True,
            cap_start=True,
            cap_end=True,
            flip_normals=(side_sign < 0),
            ring_tags=tags,
            ring_mats=mats,
        )

        # Five individually articulated fingers per hand (thumb, index, middle, ring, pinky)
        finger_specs = [
            ("thumb",  0.725, -0.036, 1.338, 0.78, -0.62, 0.068, 0.0095),
            ("index",  0.775, -0.034, 1.350, 0.99, -0.10, 0.082, 0.0082),
            ("middle", 0.778, -0.012, 1.351, 1.00,  0.00, 0.088, 0.0085),
            ("ring",   0.775,  0.010, 1.350, 0.99,  0.08, 0.080, 0.0080),
            ("pinky",  0.770,  0.030, 1.347, 0.98,  0.16, 0.068, 0.0072),
        ]
        f_seg = max(8, arm_seg // 2)
        for fname, fx0, fy0, fz0, dx, dy, flen, frad in finger_specs:
            f_rings = []
            f_tags = []
            for step_i in range(7):
                frac = step_i / 6.0
                if frac < 0.34:
                    p_num = "01"
                elif frac < 0.67:
                    p_num = "02"
                else:
                    p_num = "03"
                px = side_sign * (fx0 + dx * flen * frac)
                py = fy0 + dy * flen * frac
                pz = fz0 - 0.003 * (frac ** 2)
                r_curr = frad * (1.0 - 0.28 * frac)
                f_rings.append(
                    make_ellipse_ring(
                        Vector((px, py, pz)),
                        r_curr * 0.9,
                        r_curr,
                        f_seg,
                        rot_matrix=rot_yz,
                        squareness=0.3 if is_cyber else 0.05,
                    )
                )
                f_tags.append(f"{fname}_{p_num}_{side_s}")

            acc.add_lofted_tube(
                f_rings,
                mat_idx=hand_mat,
                tag=f"{fname}_01_{side_s}",
                uv_box=(0.15, 0.35, 0.85, 0.75),
                closed_u=True,
                cap_start=True,
                cap_end=True,
                flip_normals=(side_sign < 0),
                ring_tags=f_tags,
            )

        # Shoulder Armor Pauldron + Team-Accent Holographic Badge on each shoulder
        pauldron_rings = []
        for s_step, (x_off, z_off, w_y, arch_z) in enumerate([
            (0.145, 1.405, 0.068, 0.015),
            (0.185, 1.412, 0.078, 0.022),
            (0.235, 1.395, 0.072, 0.018),
            (0.265, 1.368, 0.056, 0.010),
        ]):
            row = []
            for u_i in range(8):
                ang = -0.45 * math.pi + 0.90 * math.pi * (u_i / 7.0)
                py = math.sin(ang) * w_y
                pz = z_off + math.cos(ang) * arch_z
                row.append(Vector((side_sign * x_off, py, pz)))
            pauldron_rings.append(row)
        acc.add_lofted_tube(
            pauldron_rings,
            mat_idx=3,  # M_Operative_Armor
            tag=f"clavicle_{side_s}",
            uv_box=(0.10, 0.10, 0.90, 0.90),
            closed_u=False,
            flip_normals=(side_sign < 0),
        )

        # Team-Accent Crest Patch on outer shoulder (uses M_Operative_Props_Accent UV 0..1)
        crest_rings = []
        for v_i, x_c in enumerate([0.195, 0.245]):
            z_c = 1.418 if v_i == 0 else 1.398
            crest_rings.append([
                Vector((side_sign * x_c, -0.042, z_c)),
                Vector((side_sign * x_c,  0.042, z_c)),
            ])
        acc.add_lofted_tube(
            crest_rings,
            mat_idx=5,  # M_Operative_Props_Accent (shows full Hex/Diamond icon!)
            tag=f"clavicle_{side_s}",
            uv_box=(0.02, 0.02, 0.98, 0.98),
            closed_u=False,
            flip_normals=(side_sign > 0),
        )

    # === RIGHT CYBERNETIC ARM INTEGRATED WEAPONS & PROPS ===
    emitter_rings = []
    emitter_tags = []
    for x_e, rx_e, rz_e, e_tag in [
        (-0.515, 0.022, 0.016, "emitter_mount_r"),
        (-0.575, 0.028, 0.020, "emitter_mount_r"),
        (-0.655, 0.026, 0.019, "emitter_mount_r"),
        (-0.705, 0.018, 0.014, "emitter_muzzle_r"),
        (-0.725, 0.014, 0.011, "emitter_muzzle_r"),
    ]:
        emitter_rings.append(
            make_ellipse_ring(Vector((x_e, -0.006, 1.388)), rz_e, rx_e, 10, rot_matrix=rot_yz, squareness=0.45)
        )
        emitter_tags.append(e_tag)
    acc.add_lofted_tube(
        emitter_rings,
        mat_idx=4,
        tag="emitter_mount_r",
        uv_box=(0.15, 0.02, 0.85, 0.25),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        flip_normals=True,
        ring_tags=emitter_tags,
    )

    blade_housing_rings = []
    for x_b in (-0.45, -0.55, -0.66):
        blade_housing_rings.append(
            make_ellipse_ring(Vector((x_b, 0.044, 1.348)), 0.010, 0.014, 8, rot_matrix=rot_yz, squareness=0.5)
        )
    acc.add_lofted_tube(
        blade_housing_rings,
        mat_idx=4,
        tag="blade_mount_r",
        uv_box=(0.20, 0.40, 0.80, 0.70),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        flip_normals=True,
    )

    blade_rings = []
    for x_bl, w_y, thick_z in [
        (-0.50, 0.018, 0.005),
        (-0.62, 0.024, 0.005),
        (-0.74, 0.022, 0.004),
        (-0.84, 0.012, 0.002),
        (-0.89, 0.002, 0.001),
    ]:
        blade_rings.append([
            Vector((x_bl, 0.040, 1.348 - thick_z)),
            Vector((x_bl, 0.040 + w_y, 1.348)),
            Vector((x_bl, 0.040, 1.348 + thick_z)),
            Vector((x_bl, 0.036, 1.348)),
        ])
    acc.add_lofted_tube(
        blade_rings,
        mat_idx=4,
        tag="blade_extend_r",
        uv_box=(0.10, 0.01, 0.90, 0.16),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        flip_normals=True,
    )


def build_secondary_and_props(acc: MeshAccumulator):
    tether_rings = []
    tether_tags = []
    for z_t, y_t, rad_t, t_tag in [
        (1.64, 0.088, 0.014, "neural_tether_01"),
        (1.56, 0.115, 0.013, "neural_tether_01"),
        (1.48, 0.132, 0.012, "neural_tether_02"),
        (1.40, 0.142, 0.011, "neural_tether_02"),
        (1.32, 0.146, 0.010, "neural_tether_03"),
        (1.25, 0.142, 0.007, "neural_tether_03"),
    ]:
        tether_rings.append(make_ellipse_ring(Vector((0.0, y_t, z_t)), rad_t, rad_t, 8))
        tether_tags.append(t_tag)
    acc.add_lofted_tube(
        tether_rings,
        mat_idx=3,
        tag="neural_tether_01",
        uv_box=(0.10, 0.10, 0.40, 0.90),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        ring_tags=tether_tags,
    )

    strap_rings = []
    strap_tags = []
    for z_s, x_s, s_tag in [
        (0.98, 0.166, "belt_strap_01"),
        (0.90, 0.174, "belt_strap_01"),
        (0.82, 0.178, "belt_strap_02"),
        (0.73, 0.175, "belt_strap_02"),
    ]:
        strap_rings.append([
            Vector((x_s, -0.024, z_s)),
            Vector((x_s + 0.006, -0.024, z_s)),
            Vector((x_s + 0.006,  0.024, z_s)),
            Vector((x_s,  0.024, z_s)),
        ])
        strap_tags.append(s_tag)
    acc.add_lofted_tube(
        strap_rings,
        mat_idx=5,
        tag="belt_strap_01",
        uv_box=(0.05, 0.02, 0.95, 0.18),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        ring_tags=strap_tags,
    )

    rot_yz = Matrix.Rotation(0.5 * math.pi, 3, "Y")
    cell_rings = []
    for x_c, rad_c in [(-0.555, 0.012), (-0.565, 0.015), (-0.615, 0.015), (-0.625, 0.012)]:
        cell_rings.append(make_ellipse_ring(Vector((x_c, -0.028, 1.402)), rad_c, rad_c, 6, rot_matrix=rot_yz))
    acc.add_lofted_tube(
        cell_rings,
        mat_idx=5,
        tag="prop_cell",
        uv_box=(0.10, 0.02, 0.90, 0.15),
        closed_u=True,
        cap_start=True,
        cap_end=True,
        flip_normals=True,
    )

    beacon_rings = []
    for z_b, rad_b in [(0.835, 0.016), (0.850, 0.036), (0.868, 0.042), (0.885, 0.024), (0.896, 0.008)]:
        beacon_rings.append(make_ellipse_ring(Vector((-0.178, -0.020, z_b)), rad_b, rad_b, 9))
    acc.add_lofted_tube(
        beacon_rings,
        mat_idx=5,
        tag="prop_beacon",
        uv_box=(0.10, 0.10, 0.90, 0.90),
        closed_u=True,
        cap_start=True,
        cap_end=True,
    )


def create_materials(tex_dir) -> List[bpy.types.Material]:
    """Create the 6 PBR materials in Blender wired to source/textures/*.png."""
    mats = []
    tex_map = {
        "M_Operative_Skin": "T_Operative_Skin",
        "M_Operative_Eyes": "T_Operative_Eyes",
        "M_Operative_Suit": "T_Operative_Suit",
        "M_Operative_Armor": "T_Operative_Armor",
        "M_Operative_CyberArm": "T_Operative_CyberArm",
        "M_Operative_Props_Accent": "T_Operative_Props_Accent_TeamA",
    }

    for mat_name in MATERIAL_NAMES:
        mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        out_node = nodes.new(type="ShaderNodeOutputMaterial")
        out_node.location = (400, 0)
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (80, 0)
        links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

        prefix = tex_map[mat_name]

        def load_img_node(suffix: str, non_color: bool, loc_y: float):
            img_path = tex_dir / f"{prefix}_{suffix}.png"
            img = bpy.data.images.load(str(img_path), check_existing=True)
            if non_color:
                img.colorspace_settings.name = "Non-Color"
            tnode = nodes.new(type="ShaderNodeTexImage")
            tnode.image = img
            tnode.location = (-360, loc_y)
            return tnode

        d_node = load_img_node("D", False, 260)
        r_node = load_img_node("R", True, 60)
        m_node = load_img_node("M", True, -120)
        n_node = load_img_node("N", True, -300)
        e_node = load_img_node("E", False, -480)

        links.new(d_node.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(r_node.outputs["Color"], bsdf.inputs["Roughness"])
        links.new(m_node.outputs["Color"], bsdf.inputs["Metallic"])

        norm_map = nodes.new(type="ShaderNodeNormalMap")
        norm_map.location = (-120, -300)
        links.new(n_node.outputs["Color"], norm_map.inputs["Color"])
        links.new(norm_map.outputs["Normal"], bsdf.inputs["Normal"])

        if "Emission Color" in bsdf.inputs:
            links.new(e_node.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.5

        mats.append(mat)

    for suffix in ("D", "E"):
        tb_path = tex_dir / f"T_Operative_Props_Accent_TeamB_{suffix}.png"
        if tb_path.exists():
            tb_img = bpy.data.images.load(str(tb_path), check_existing=True)
            tb_img.use_fake_user = True

    return mats


def add_facial_and_corrective_shape_keys(obj: bpy.types.Object, vert_tags: List[str]):
    """
    Author 38 Morph Targets (Shape Keys) on the character mesh using smooth spatial falloffs
    and initialize every non-Basis Shape Key to value = 0.0!
    """
    mesh = obj.data
    n_verts = len(mesh.vertices)
    basis_coords = [Vector(v.co) for v in mesh.vertices]

    basis_sk = obj.shape_key_add(name="Basis", from_mix=False)

    def create_key(name: str, delta_fn):
        sk = obj.shape_key_add(name=name, from_mix=False)
        sk.value = 0.0  # CRITICAL: Blender 5.1 defaults new shape keys to 1.0 unless explicitly zeroed!
        for i in range(n_verts):
            co = basis_coords[i]
            tag = vert_tags[i]
            d = delta_fn(i, co, tag)
            if d is not None:
                sk.data[i].co = co + d

    lower_mouth_tags = {"jaw", "head_chin", "lip_lower", "lip_lower_mid", "lip_lower_l", "lip_lower_r"}
    upper_mouth_tags = {"lip_upper", "lip_upper_mid", "lip_upper_l", "lip_upper_r"}

    def mouth_lower_weight(co: Vector, tag: str) -> float:
        if tag not in lower_mouth_tags or co.y > -0.03:
            return 0.0
        wx = math.exp(-((co.x / 0.032) ** 2))
        wz = math.exp(-(((co.z - 1.592) / 0.022) ** 2))
        return wx * wz

    def mouth_upper_weight(co: Vector, tag: str) -> float:
        if tag not in upper_mouth_tags or co.y > -0.03:
            return 0.0
        wx = math.exp(-((co.x / 0.032) ** 2))
        wz = math.exp(-(((co.z - 1.602) / 0.016) ** 2))
        return wx * wz

    def corner_weight(co: Vector, side_sign: float) -> float:
        if co.y > -0.04:
            return 0.0
        dx = co.x - side_sign * 0.024
        dz = co.z - 1.598
        return math.exp(-(dx * dx / 0.00035 + dz * dz / 0.00025))

    def brow_weight(co: Vector, side_sign: float) -> float:
        if co.y > -0.05 or co.x * side_sign < 0.0:
            return 0.0
        dx = co.x - side_sign * 0.030
        dz = co.z - 1.714
        return math.exp(-(dx * dx / 0.0008 + dz * dz / 0.00022))

    def cheek_weight(co: Vector, side_sign: float) -> float:
        if co.y > -0.04 or co.x * side_sign < 0.0:
            return 0.0
        dx = co.x - side_sign * 0.045
        dz = co.z - 1.652
        return math.exp(-(dx * dx / 0.0007 + dz * dz / 0.0005))

    # 1. Independent Blinks, Squints, Brows, Cheeks, Smile, Frown
    for side_s, sign_x in [("l", 1.0), ("r", -1.0)]:
        create_key(
            f"blink_{side_s}",
            lambda i, co, tag, s=side_s: (
                Vector((0.0, -0.0055, -0.0105)) if tag == f"eyelid_upper_{s}"
                else (Vector((0.0, -0.0045, 0.0055)) if tag == f"eyelid_lower_{s}" else None)
            ),
        )
        create_key(
            f"squint_{side_s}",
            lambda i, co, tag, s=side_s, sx=sign_x: (
                Vector((0.0, -0.0035, 0.0050)) if tag == f"eyelid_lower_{s}"
                else (Vector((0.0, -0.0030, -0.0035)) if tag == f"eyelid_upper_{s}"
                else (Vector((0.0, -0.002, 0.003)) * cheek_weight(co, sx) if cheek_weight(co, sx) > 0.05 else None))
            ),
        )
        create_key(
            f"brow_raise_{side_s}",
            lambda i, co, tag, sx=sign_x: (
                Vector((0.0, -0.001, 0.009)) * brow_weight(co, sx) if brow_weight(co, sx) > 0.02 else None
            ),
        )
        create_key(
            f"brow_lower_{side_s}",
            lambda i, co, tag, sx=sign_x: (
                Vector((-0.003 * sx, -0.002, -0.008)) * brow_weight(co, sx) if brow_weight(co, sx) > 0.02 else None
            ),
        )
        create_key(
            f"cheek_raise_{side_s}",
            lambda i, co, tag, sx=sign_x: (
                Vector((0.0, -0.003, 0.005)) * cheek_weight(co, sx) if cheek_weight(co, sx) > 0.02 else None
            ),
        )
        create_key(
            f"smile_{side_s}",
            lambda i, co, tag, sx=sign_x: (
                Vector((0.006 * sx, 0.002, 0.007)) * corner_weight(co, sx) if corner_weight(co, sx) > 0.02 else None
            ),
        )
        create_key(
            f"frown_{side_s}",
            lambda i, co, tag, sx=sign_x: (
                Vector((0.002 * sx, 0.001, -0.007)) * corner_weight(co, sx) if corner_weight(co, sx) > 0.02 else None
            ),
        )

    create_key(
        "cheek_puff",
        lambda i, co, tag: (
            Vector((math.copysign(0.007, co.x), -0.005, 0.0)) * max(cheek_weight(co, 1.0), cheek_weight(co, -1.0))
            if max(cheek_weight(co, 1.0), cheek_weight(co, -1.0)) > 0.02 else None
        ),
    )

    # Jaw & Mouth Core Controls with smooth spatial falloffs
    create_key(
        "jaw_open",
        lambda i, co, tag: (
            Vector((0.0, 0.003, -0.015)) * mouth_lower_weight(co, tag)
            if mouth_lower_weight(co, tag) > 0.01
            else (Vector((0.0, 0.002, -0.010)) if tag in ("jaw", "tongue_01", "tongue_02") and co.y < -0.04 else None)
        ),
    )
    create_key(
        "jaw_left",
        lambda i, co, tag: Vector((0.006, 0.0, 0.0)) * mouth_lower_weight(co, tag) if mouth_lower_weight(co, tag) > 0.01 else None,
    )
    create_key(
        "jaw_right",
        lambda i, co, tag: Vector((-0.006, 0.0, 0.0)) * mouth_lower_weight(co, tag) if mouth_lower_weight(co, tag) > 0.01 else None,
    )
    create_key(
        "lip_close",
        lambda i, co, tag: (
            Vector((0.0, -0.002, -0.004)) * mouth_upper_weight(co, tag) if mouth_upper_weight(co, tag) > 0.02
            else (Vector((0.0, -0.002, 0.004)) * mouth_lower_weight(co, tag) if mouth_lower_weight(co, tag) > 0.02 else None)
        ),
    )
    create_key(
        "mouth_wide",
        lambda i, co, tag: (
            Vector((math.copysign(0.006, co.x), 0.001, 0.0)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
            if max(corner_weight(co, 1.0), corner_weight(co, -1.0)) > 0.02 else None
        ),
    )
    create_key(
        "mouth_narrow",
        lambda i, co, tag: (
            Vector((-0.30 * co.x, -0.002, 0.0)) * max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag))
            if max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag)) > 0.02 else None
        ),
    )
    create_key(
        "mouth_pucker",
        lambda i, co, tag: (
            Vector((-0.36 * co.x, -0.006, 0.0)) * max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag))
            if max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag)) > 0.02 else None
        ),
    )
    create_key(
        "mouth_funnel",
        lambda i, co, tag: (
            Vector((-0.24 * co.x, -0.006, 0.003 * mouth_upper_weight(co, tag) - 0.005 * mouth_lower_weight(co, tag)))
            if max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag)) > 0.02 else None
        ),
    )
    create_key(
        "tongue_up",
        lambda i, co, tag: Vector((0.0, -0.002, 0.006)) if tag == "tongue_02" else None,
    )
    create_key(
        "tongue_out",
        lambda i, co, tag: Vector((0.0, -0.012, 0.001)) if tag.startswith("tongue_") else None,
    )

    # 6 Required Expression Presets (§7)
    create_key(
        "expr_joy_confidence",
        lambda i, co, tag: (
            Vector((math.copysign(0.006, co.x), 0.001, 0.007)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
            + Vector((0.0, -0.002, 0.004)) * max(cheek_weight(co, 1.0), cheek_weight(co, -1.0))
            + Vector((0.0, 0.0, 0.003)) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
        ),
    )
    create_key(
        "expr_anger",
        lambda i, co, tag: (
            Vector((-math.copysign(0.003, co.x), -0.002, -0.008)) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
            + Vector((0.0, 0.001, -0.005)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
        ),
    )
    create_key(
        "expr_concern_sadness",
        lambda i, co, tag: (
            Vector((0.0, -0.001, 0.006 * (1.0 - min(1.0, abs(co.x) / 0.035)))) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
            + Vector((0.0, 0.001, -0.006)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
        ),
    )
    create_key(
        "expr_surprise",
        lambda i, co, tag: (
            Vector((0.0, -0.001, 0.009)) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
            + Vector((-0.18 * co.x, 0.002, -0.011)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "expr_pain",
        lambda i, co, tag: (
            Vector((0.0, -0.003, -0.006)) if tag.startswith("eyelid_upper")
            else (Vector((0.0, -0.003, 0.005)) if tag.startswith("eyelid_lower")
            else (
                Vector((-math.copysign(0.003, co.x), -0.002, -0.006)) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
                + Vector((math.copysign(0.004, co.x), 0.001, -0.004)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
            ))
        ),
    )
    create_key(
        "expr_focus",
        lambda i, co, tag: (
            Vector((0.0, -0.002, -0.005)) * max(brow_weight(co, 1.0), brow_weight(co, -1.0))
            + (Vector((0.0, -0.002, 0.0025)) if tag.startswith("eyelid_lower") else Vector((0.0, 0.0, 0.0)))
        ),
    )

    # 11 Speech Visemes (§7)
    create_key("viseme_SIL", lambda i, co, tag: None)
    create_key(
        "viseme_MBP",
        lambda i, co, tag: (
            Vector((0.0, -0.002, -0.004)) * mouth_upper_weight(co, tag)
            + Vector((0.0, -0.002, 0.004)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "viseme_FV",
        lambda i, co, tag: (
            Vector((0.0, 0.004, 0.003)) * mouth_lower_weight(co, tag)
            + Vector((0.0, -0.001, 0.002)) * mouth_upper_weight(co, tag)
        ),
    )
    create_key(
        "viseme_TH",
        lambda i, co, tag: (
            Vector((0.0, -0.010, 0.002)) if tag == "tongue_02"
            else Vector((0.0, 0.001, -0.006)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "viseme_TDNL",
        lambda i, co, tag: (
            Vector((0.0, -0.004, 0.006)) if tag == "tongue_02"
            else Vector((0.0, 0.001, -0.007)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "viseme_SZ",
        lambda i, co, tag: (
            Vector((math.copysign(0.003, co.x), 0.0, -0.003)) * max(mouth_upper_weight(co, tag), mouth_lower_weight(co, tag))
        ),
    )
    create_key(
        "viseme_KG",
        lambda i, co, tag: (
            Vector((0.0, 0.002, 0.005)) if tag == "tongue_01"
            else Vector((0.0, 0.001, -0.007)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "viseme_AA",
        lambda i, co, tag: (
            Vector((0.0, 0.003, -0.014)) * mouth_lower_weight(co, tag)
            + Vector((0.0, 0.0, 0.002)) * mouth_upper_weight(co, tag)
        ),
    )
    create_key(
        "viseme_EE",
        lambda i, co, tag: (
            Vector((math.copysign(0.005, co.x), 0.001, 0.0)) * max(corner_weight(co, 1.0), corner_weight(co, -1.0))
            + Vector((0.0, 0.001, -0.006)) * mouth_lower_weight(co, tag)
        ),
    )
    create_key(
        "viseme_OH",
        lambda i, co, tag: (
            Vector((-0.24 * co.x, -0.005, -0.011)) * mouth_lower_weight(co, tag)
            + Vector((-0.20 * co.x, -0.004, 0.002)) * mouth_upper_weight(co, tag)
        ),
    )
    create_key(
        "viseme_OO",
        lambda i, co, tag: (
            Vector((-0.35 * co.x, -0.007, -0.004)) * mouth_lower_weight(co, tag)
            + Vector((-0.35 * co.x, -0.007, 0.001)) * mouth_upper_weight(co, tag)
        ),
    )

    # 6 Joint Volume-Preservation Corrective Shape Keys (§6)
    create_key(
        "corr_shoulder_up_l",
        lambda i, co, tag: Vector((-0.004, 0.0, 0.010)) if tag in ("clavicle_l", "upperarm_l") and co.z > 1.38 else None,
    )
    create_key(
        "corr_shoulder_up_r",
        lambda i, co, tag: Vector((0.004, 0.0, 0.010)) if tag in ("clavicle_r", "upperarm_r") and co.z > 1.38 else None,
    )
    create_key(
        "corr_knee_bend_l",
        lambda i, co, tag: Vector((0.0, -0.008, 0.0)) if tag == "calf_l" and co.z > 0.46 and co.y < 0.0 else None,
    )
    create_key(
        "corr_knee_bend_r",
        lambda i, co, tag: Vector((0.0, -0.008, 0.0)) if tag == "calf_r" and co.z > 0.46 and co.y < 0.0 else None,
    )
    create_key(
        "corr_hip_bend_l",
        lambda i, co, tag: Vector((0.0, -0.006, 0.005)) if tag == "thigh_l" and co.z > 0.84 else None,
    )
    create_key(
        "corr_hip_bend_r",
        lambda i, co, tag: Vector((0.0, -0.006, 0.005)) if tag == "thigh_r" and co.z > 0.84 else None,
    )


def build_operative_lod_mesh(
    name: str,
    radial_seg: int,
    height_sub: int,
    materials: List[bpy.types.Material],
    with_shape_keys: bool = True,
) -> Tuple[bpy.types.Object, List[str]]:
    acc = MeshAccumulator()
    build_torso_and_neck(acc, radial_seg=radial_seg, height_sub=height_sub)
    build_head_and_face(acc, radial_seg=radial_seg, height_sub=height_sub)
    build_legs_and_boots(acc, radial_seg=radial_seg, height_sub=height_sub)
    build_arms_hands_and_cyberware(acc, radial_seg=radial_seg, height_sub=height_sub)
    build_secondary_and_props(acc)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in acc.verts], [], acc.faces)
    mesh.update()

    for mat in materials:
        mesh.materials.append(mat)

    for poly_idx, poly in enumerate(mesh.polygons):
        poly.material_index = acc.face_mats[poly_idx]
        poly.use_smooth = True

    uv_layer = mesh.uv_layers.new(name="UVMap")
    mesh.uv_layers.active = uv_layer
    for poly_idx, poly in enumerate(mesh.polygons):
        uvs = acc.face_uvs[poly_idx]
        for loop_i, loop_idx in enumerate(poly.loop_indices):
            uv_layer.data[loop_idx].uv = uvs[loop_i]

    # Ensure consistent outward normals via bmesh selectively or validate
    mesh.validate(verbose=False)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    if with_shape_keys:
        add_facial_and_corrective_shape_keys(obj, acc.vert_tags)

    return obj, acc.vert_tags
