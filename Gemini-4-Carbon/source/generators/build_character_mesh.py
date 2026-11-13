#!/usr/bin/env python3
"""
Procedural Cyberpunk Operative Character & Prop Geometry Generator (Blender 5.1+).
Authors original human-like Operative geometry from mathematical/anatomical surfaces:
  - Expressive human head with concentric orbital & perioral edge loops, zero-gap closed lips,
    watertight shadowed oral cavity bag, upper/lower dental arches, articulated tongue, eyeballs, ears, brows
  - Sleek cyberpunk undercut hair + occipital neural port + 3-segment braided cyber-cable (secondary motion)
  - Fitted hex-weave tactical undersuit & trousers (no coat/cape hiding legs)
  - Organic left arm & 5 articulated human fingers; visibly cybernetic right forearm & 5 mechanical fingers
  - Asymmetric tactical chest mantle, collar, left shoulder pauldron + dorsal team crest plate, belt + hip strap, knee/boot plates
  - Authored props: integrated wrist emitter, retractable forearm energy blade, removable power cell, deployable beacon/drone
  - Exact 1.800 m standing height (Z in [0.000, 1.800] m), facing -Y, +Z up, ground origin (0,0,0)
  - 6 PBR material slots (<= 8 limit) + genuine reduced-polygon LOD1 (<= 40k tris) and LOD2 (<= 20k tris)
"""

import math
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler

ROOT_DIR = Path(__file__).resolve().parents[2]
TEX_DIR = ROOT_DIR / "source" / "textures"

MATERIAL_NAMES = [
    "M_Skin_FaceBody",
    "M_Eyes_Mouth",
    "M_Hair",
    "M_Suit_Fabric",
    "M_CyberArmor",
    "M_Props_Tech",
]


def create_pbr_materials() -> list[bpy.types.Material]:
    """Create the 6 Principled BSDF materials wired to source/textures/*.png (relative paths)."""
    tex_map = {
        "M_Skin_FaceBody": ("Skin_BaseColor.png", "Skin_Normal.png", "Skin_ORM.png", None),
        "M_Eyes_Mouth": ("EyesMouth_BaseColor.png", "EyesMouth_Normal.png", "EyesMouth_ORM.png", None),
        "M_Hair": ("Hair_BaseColor.png", "Hair_Normal.png", "Hair_ORM.png", None),
        "M_Suit_Fabric": ("SuitFabric_BaseColor.png", "SuitFabric_Normal.png", "SuitFabric_ORM.png", None),
        "M_CyberArmor": ("CyberArmor_BaseColor.png", "CyberArmor_Normal.png", "CyberArmor_ORM.png", "CyberArmor_Emissive.png"),
        "M_Props_Tech": ("PropsTech_BaseColor.png", "PropsTech_Normal.png", "PropsTech_ORM.png", "PropsTech_Emissive.png"),
    }
    mats = []
    for m_name in MATERIAL_NAMES:
        mat = bpy.data.materials.get(m_name) or bpy.data.materials.new(name=m_name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()

        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        out_node.location = (500, 0)
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (180, 0)
        nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

        bc_f, nm_f, orm_f, em_f = tex_map[m_name]

        def load_img(fname: str, non_color: bool = False):
            fpath = TEX_DIR / fname
            img = bpy.data.images.load(str(fpath), check_existing=True)
            if non_color:
                img.colorspace_settings.name = "Non-Color"
            return img

        if (TEX_DIR / bc_f).exists():
            n_bc = nt.nodes.new("ShaderNodeTexImage")
            n_bc.image = load_img(bc_f, non_color=False)
            n_bc.location = (-380, 260)
            nt.links.new(n_bc.outputs["Color"], bsdf.inputs["Base Color"])

        if (TEX_DIR / orm_f).exists():
            n_orm = nt.nodes.new("ShaderNodeTexImage")
            n_orm.image = load_img(orm_f, non_color=True)
            n_orm.location = (-620, -20)
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            sep.location = (-260, -20)
            nt.links.new(n_orm.outputs["Color"], sep.inputs["Color"])
            nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
            nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

        if (TEX_DIR / nm_f).exists():
            n_nm = nt.nodes.new("ShaderNodeTexImage")
            n_nm.image = load_img(nm_f, non_color=True)
            n_nm.location = (-620, -300)
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.location = (-240, -300)
            nt.links.new(n_nm.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

        if em_f and (TEX_DIR / em_f).exists():
            n_em = nt.nodes.new("ShaderNodeTexImage")
            n_em.image = load_img(em_f, non_color=False)
            n_em.location = (-380, -560)
            if "Emission Color" in bsdf.inputs:
                nt.links.new(n_em.outputs["Color"], bsdf.inputs["Emission Color"])
                bsdf.inputs["Emission Strength"].default_value = 1.6
        mats.append(mat)
    return mats


class MeshPartBuilder:
    """Accumulates clean quad/tri sub-meshes with explicit material index, UVs, and semantic part tags."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv_layer = self.bm.loops.layers.uv.new("UVMap")
        self.part_layer = self.bm.verts.layers.int.new("part_id")
        self.sub_layer = self.bm.verts.layers.int.new("sub_id")
        self.part_names: dict[int, str] = {}
        self._next_part = 1

    def register_part(self, name: str) -> int:
        for pid, pname in self.part_names.items():
            if pname == name:
                return pid
        pid = self._next_part
        self._next_part += 1
        self.part_names[pid] = name
        return pid

    def add_grid(
        self,
        rings: list[list[Vector]],
        uvs: list[list[tuple[float, float]]],
        mat_idx: int,
        part_name: str,
        closed_u: bool = True,
        cap_start: bool = False,
        cap_end: bool = False,
        sub_ids: list[list[int]] | None = None,
        smooth: bool = True,
    ) -> list[list[bmesh.types.BMVert]]:
        pid = self.register_part(part_name)
        n_v = len(rings)
        n_u = len(rings[0])
        bm_rings: list[list[bmesh.types.BMVert]] = []
        for iv in range(n_v):
            row = []
            for iu in range(n_u):
                v = self.bm.verts.new(rings[iv][iu])
                v[self.part_layer] = pid
                v[self.sub_layer] = sub_ids[iv][iu] if sub_ids else 0
                row.append(v)
            bm_rings.append(row)

        u_limit = n_u if closed_u else (n_u - 1)
        for iv in range(n_v - 1):
            for iu in range(u_limit):
                iu_next = (iu + 1) % n_u
                v00 = bm_rings[iv][iu]
                v10 = bm_rings[iv][iu_next]
                v11 = bm_rings[iv + 1][iu_next]
                v01 = bm_rings[iv + 1][iu]
                if (v00.co - v10.co).length < 1e-7 and (v01.co - v11.co).length < 1e-7:
                    continue
                try:
                    f = self.bm.faces.new((v00, v10, v11, v01))
                except ValueError:
                    continue
                f.material_index = mat_idx
                f.smooth = smooth
                uv00 = uvs[iv][iu]
                uv10 = uvs[iv][iu if not closed_u and iu + 1 == n_u else iu_next]
                uv11 = uvs[iv + 1][iu if not closed_u and iu + 1 == n_u else iu_next]
                uv01 = uvs[iv + 1][iu]
                for loop, uv_val in zip(f.loops, (uv00, uv10, uv11, uv01)):
                    loop[self.uv_layer].uv = uv_val

        if cap_start and closed_u:
            center_co = sum((v.co for v in bm_rings[0]), Vector()) / n_u
            vc = self.bm.verts.new(center_co)
            vc[self.part_layer] = pid
            vc[self.sub_layer] = sub_ids[0][0] if sub_ids else 0
            c_uv = (
                sum(uvs[0][i][0] for i in range(n_u)) / n_u,
                sum(uvs[0][i][1] for i in range(n_u)) / n_u,
            )
            for iu in range(n_u):
                iu_next = (iu + 1) % n_u
                try:
                    f = self.bm.faces.new((bm_rings[0][iu_next], bm_rings[0][iu], vc))
                    f.material_index = mat_idx
                    f.smooth = smooth
                    f.loops[0][self.uv_layer].uv = uvs[0][iu_next]
                    f.loops[1][self.uv_layer].uv = uvs[0][iu]
                    f.loops[2][self.uv_layer].uv = c_uv
                except ValueError:
                    pass

        if cap_end and closed_u:
            center_co = sum((v.co for v in bm_rings[-1]), Vector()) / n_u
            vc = self.bm.verts.new(center_co)
            vc[self.part_layer] = pid
            vc[self.sub_layer] = sub_ids[-1][0] if sub_ids else 0
            c_uv = (
                sum(uvs[-1][i][0] for i in range(n_u)) / n_u,
                sum(uvs[-1][i][1] for i in range(n_u)) / n_u,
            )
            for iu in range(n_u):
                iu_next = (iu + 1) % n_u
                try:
                    f = self.bm.faces.new((bm_rings[-1][iu], bm_rings[-1][iu_next], vc))
                    f.material_index = mat_idx
                    f.smooth = smooth
                    f.loops[0][self.uv_layer].uv = uvs[-1][iu]
                    f.loops[1][self.uv_layer].uv = uvs[-1][iu_next]
                    f.loops[2][self.uv_layer].uv = c_uv
                except ValueError:
                    pass

        return bm_rings


def gauss(x: float, mu: float, sig: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sig) ** 2)


def gauss2(x: float, y: float, mx: float, my: float, sx: float, sy: float) -> float:
    return math.exp(-0.5 * (((x - mx) / sx) ** 2 + ((y - my) / sy) ** 2))


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / max(1e-8, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def eval_head_surface(theta: float, v: float) -> Vector:
    """
    Parametric sculpted adult human head + neck surface.
    theta in [-pi, pi]: 0 is straight front (-Y), +pi/2 is Left (+X), -pi/2 is Right (-X), +-pi is back (+Y).
    v in [0, 1]: 0 is neck base (Z=1.455), 1 is cranial crown (Z=1.792).
    """
    s_th = math.sin(theta)  # +1 left (+X), -1 right (-X)
    c_th = -math.cos(theta) # -1 front (-Y), +1 back (+Y)
    frontness = max(0.0, math.cos(theta))

    # Base vertical profile Z(v)
    z = 1.455 + 0.337 * v
    # Crown dome curve near v -> 1
    if v > 0.80:
        t_top = (v - 0.80) / 0.20
        dome_scale = math.sqrt(max(0.0004, 1.0 - t_top * t_top * 0.996))
        z = 1.724 + 0.068 * math.sin(t_top * math.pi * 0.5)
    else:
        dome_scale = 1.0

    # Neck to cranium base radii rx (width), ry (depth), center y0
    neck_t = smoothstep(0.26, 0.40, v)  # 0 in neck, 1 in head
    jaw_chin_t = smoothstep(0.32, 0.58, v)

    rx_neck = 0.048 - 0.003 * math.sin(v * math.pi * 2.0) + 0.015 * (1.0 - smoothstep(0.0, 0.14, v))
    ry_neck = 0.052 + 0.010 * (1.0 - smoothstep(0.0, 0.14, v))
    y0_neck = 0.008 - 0.006 * v

    # Cranium oval widths (sleek sculpted human proportions)
    rx_head = (0.062 + 0.012 * smoothstep(0.46, 0.68, v) - 0.004 * smoothstep(0.75, 0.92, v)) * dome_scale
    ry_head = (0.085 + 0.014 * smoothstep(0.45, 0.72, v)) * dome_scale
    y0_head = -0.004 + 0.012 * smoothstep(0.55, 0.85, v)

    rx = rx_neck * (1.0 - neck_t) + rx_head * neck_t
    ry = ry_neck * (1.0 - neck_t) + ry_head * neck_t
    y0 = y0_neck * (1.0 - neck_t) + y0_head * neck_t

    # Taper lower face into a clean V-oval jawline from cheekbones (v=0.58) down to chin (v=0.33)
    chin_narrow = (1.0 - jaw_chin_t) * neck_t * (0.45 + 0.55 * (frontness**1.2))
    rx *= 1.0 - 0.34 * chin_narrow

    x = rx * s_th
    y = y0 + ry * c_th

    # Sculpted facial landmarks on the front hemisphere (theta in [-1.45, 1.45])
    if abs(theta) < 1.45 and 0.28 < v < 0.88:
        # Chin prominence (Z ~ 1.568, v ~ 0.34)
        chin = gauss2(theta, v, 0.0, 0.345, 0.20, 0.036)
        y -= 0.013 * chin
        z -= 0.004 * chin

        # Clean mandibular jaw definition (subtle, athletic, non-boxy)
        jaw_ang = (gauss2(theta, v, 0.78, 0.42, 0.20, 0.042) + gauss2(theta, v, -0.78, 0.42, 0.20, 0.042))
        x += math.copysign(0.0035 * jaw_ang, x)

        # Cheekbones / zygomatic arch (v ~ 0.57, theta ~ +-0.56)
        cheek = gauss2(abs(theta), v, 0.56, 0.575, 0.24, 0.055)
        x += math.copysign(0.0075 * cheek, x)
        y -= 0.0080 * cheek

        # Recessed eye sockets (around x=+-0.032 -> abs(theta)~0.47, Z=1.675 -> v~0.653)
        orb = gauss2(abs(theta), v, 0.47, 0.653, 0.16, 0.040)
        y += 0.0135 * orb

        # Supraorbital brow ridge (v ~ 0.715)
        brow = gauss2(abs(theta), v, 0.42, 0.712, 0.28, 0.026)
        y -= 0.0080 * brow

        # Nose bridge, dorsum, tip (v ~ 0.545 -> Z ~ 1.638), and alar nostrils
        nose_dorsum = gauss(theta, 0.0, 0.088) * smoothstep(0.52, 0.56, v) * (1.0 - smoothstep(0.66, 0.73, v))
        nose_tip = gauss2(theta, v, 0.0, 0.542, 0.095, 0.026)
        nostril_w = gauss2(abs(theta), v, 0.18, 0.528, 0.070, 0.018)
        y -= 0.016 * nose_dorsum + 0.023 * nose_tip + 0.007 * nostril_w
        x += math.copysign(0.0035 * nostril_w, x)

        # Muzzle / perioral barrel support (v ~ 0.453 -> Z ~ 1.608)
        muzzle = gauss2(theta, v, 0.0, 0.453, 0.28, 0.046)
        y -= 0.0090 * muzzle

        # Mentolabial crease under lower lip (v ~ 0.395)
        mento = gauss2(theta, v, 0.0, 0.395, 0.22, 0.018)
        y += 0.0050 * mento

    return Vector((x, y, z))


def build_head_and_face(builder: MeshPartBuilder) -> None:
    """
    Constructs sculpted head/neck mesh with carved concentric eye-socket eyelid rings
    and concentric perioral lip + watertight shadowed oral cavity bag!
    """
    n_u = 72
    n_v = 58
    thetas = [-math.pi + (2.0 * math.pi * iu / n_u) for iu in range(n_u)]
    vs = [iv / (n_v - 1) for iv in range(n_v)]

    # Eye & mouth opening windows in grid index space so we stitch concentric quad loops seamlessly!
    # Mouth window: centered at theta=0 (iu = n_u//2 = 36), v ~ 0.453 (iv ~ 26)
    m_u0, m_u1 = 31, 41   # 10 columns wide -> perimeter has 2*(10 + 6) = 32 edges!
    m_v0, m_v1 = 23, 29   # 6 rows tall

    # Right Eye window (theta < 0, -X): iu in [28, 34] centered right at x=-0.032!
    re_u0, re_u1 = 28, 34
    re_v0, re_v1 = 35, 40
    # Left Eye window (theta > 0, +X): iu in [38, 44] centered right at x=+0.032!
    le_u0, le_u1 = 38, 44
    le_v0, le_v1 = 35, 40

    def in_hole(iu: int, iv: int) -> bool:
        if m_u0 <= iu < m_u1 and m_v0 <= iv < m_v1:
            return True
        if re_u0 <= iu < re_u1 and re_v0 <= iv < re_v1:
            return True
        if le_u0 <= iu < le_u1 and le_v0 <= iv < le_v1:
            return True
        return False

    pid_head = builder.register_part("HEAD_SKIN")
    bm_grid: list[list[bmesh.types.BMVert]] = []
    uv_grid: list[list[tuple[float, float]]] = []

    for iv, v in enumerate(vs):
        row_v = []
        row_uv = []
        for iu, th in enumerate(thetas):
            co = eval_head_surface(th, v)
            # Map face front UV cleanly into U in [0.04, 0.60], V in [0.26, 0.96] (matching generate_skin!)
            u_coord = 0.32 + (th / math.pi) * 0.28
            v_coord = 0.26 + v * 0.70
            bv = builder.bm.verts.new(co)
            bv[builder.part_layer] = pid_head
            bv[builder.sub_layer] = 0
            row_v.append(bv)
            row_uv.append((u_coord, v_coord))
        bm_grid.append(row_v)
        uv_grid.append(row_uv)

    # Create all head faces outside the 3 anatomical feature windows
    for iv in range(n_v - 1):
        for iu in range(n_u):
            if in_hole(iu, iv):
                continue
            iu_next = (iu + 1) % n_u
            v00 = bm_grid[iv][iu]
            v10 = bm_grid[iv][iu_next]
            v11 = bm_grid[iv + 1][iu_next]
            v01 = bm_grid[iv + 1][iu]
            f = builder.bm.faces.new((v00, v10, v11, v01))
            f.material_index = 0  # M_Skin_FaceBody
            f.smooth = True
            uv10 = (0.60, uv_grid[iv][0][1]) if iu + 1 == n_u else uv_grid[iv][iu_next]
            uv11 = (0.60, uv_grid[iv + 1][0][1]) if iu + 1 == n_u else uv_grid[iv + 1][iu_next]
            for loop, uv_val in zip(f.loops, (uv_grid[iv][iu], uv10, uv11, uv_grid[iv + 1][iu])):
                loop[builder.uv_layer].uv = uv_val

    # Close crown apex cleanly
    crown_center = Vector((0.0, 0.008, 1.792))
    vc_top = builder.bm.verts.new(crown_center)
    vc_top[builder.part_layer] = pid_head
    for iu in range(n_u):
        iu_next = (iu + 1) % n_u
        f = builder.bm.faces.new((bm_grid[-1][iu], bm_grid[-1][iu_next], vc_top))
        f.material_index = 0
        f.smooth = True
        f.loops[0][builder.uv_layer].uv = uv_grid[-1][iu]
        f.loops[1][builder.uv_layer].uv = uv_grid[-1][iu_next]
        f.loops[2][builder.uv_layer].uv = (0.32, 0.97)

    def extract_window_loop(u0: int, u1: int, v0: int, v1: int):
        """Returns ordered counter-clockwise perimeter (BMVert, uv) around a rectangular grid hole."""
        loop_v = []
        loop_uv = []
        # Bottom edge: u0 -> u1 at v0
        for u in range(u0, u1):
            loop_v.append(bm_grid[v0][u])
            loop_uv.append(uv_grid[v0][u])
        # Right edge: v0 -> v1 at u1
        for v in range(v0, v1):
            loop_v.append(bm_grid[v][u1])
            loop_uv.append(uv_grid[v][u1])
        # Top edge: u1 -> u0 at v1
        for u in range(u1, u0, -1):
            loop_v.append(bm_grid[v1][u])
            loop_uv.append(uv_grid[v1][u])
        # Left edge: v1 -> v0 at u0
        for v in range(v1, v0, -1):
            loop_v.append(bm_grid[v][u0])
            loop_uv.append(uv_grid[v][u0])
        return loop_v, loop_uv

    # --- STITCH CONCENTRIC EYELID LOOPS (Left & Right) ---
    for side_sign, (eu0, eu1, ev0, ev1), part_ul, part_ll in [
        (-1.0, (re_u0, re_u1, re_v0, re_v1), "EYELID_UPPER_R", "EYELID_LOWER_R"),
        (+1.0, (le_u0, le_u1, le_v0, le_v1), "EYELID_UPPER_L", "EYELID_LOWER_L"),
    ]:
        outer_v, outer_uv = extract_window_loop(eu0, eu1, ev0, ev1)
        n_p = len(outer_v)  # 22 vertices
        eye_center = Vector((side_sign * 0.032, -0.074, 1.675))
        eye_r = 0.0121

        pid_ul = builder.register_part(part_ul)
        pid_ll = builder.register_part(part_ll)

        # Build smooth monotonic almond palpebral rim target points matching outer_v order
        # extract_window_loop order (22 verts): 0..5 bottom (left->right), 6..10 right (bot->top), 11..16 top (right->left), 17..21 left (top->bot)
        rim_pts = []
        rim_inner_pts = []
        rim_is_upper = []
        rim_uvs = []
        for idx, bv_out in enumerate(outer_v):
            # Smooth monotonic angle starting at bottom-left corner (-0.75*pi) wrapping CCW by 2*pi
            ang = -math.pi * 0.78 + (2.0 * math.pi * idx / n_p)
            tilt = 0.0014 * (math.cos(ang) * side_sign)
            px = eye_center.x + 0.0132 * math.cos(ang)
            pz = eye_center.z + 0.0048 * math.sin(ang) + tilt
            dx = px - eye_center.x
            dz = pz - eye_center.z
            dy = -math.sqrt(max(0.00001, (eye_r + 0.0008) ** 2 - dx * dx - dz * dz))
            p_rim = Vector((px, eye_center.y + dy, pz))
            dy_in = -math.sqrt(max(0.00001, (eye_r - 0.0001) ** 2 - (dx * 0.96) ** 2 - (dz * 0.94) ** 2))
            p_in = Vector((eye_center.x + dx * 0.96, eye_center.y + dy_in + 0.0018, eye_center.z + dz * 0.94))
            rim_pts.append(p_rim)
            rim_inner_pts.append(p_in)
            rim_is_upper.append(8 < idx < 19)
            u_c = 0.405 if side_sign > 0 else 0.235
            rim_uvs.append((u_c + 0.032 * math.cos(ang), 0.665 + 0.018 * math.sin(ang)))

        # Interpolate 3 concentric eyelid rings + inner thickness fold
        ring_factors = [0.38, 0.74, 1.00]
        prev_v = outer_v
        prev_uv = outer_uv
        for rf in ring_factors:
            cur_v = []
            cur_uv = []
            for i in range(n_p):
                co = outer_v[i].co.lerp(rim_pts[i], rf)
                # Push eyelid crease slightly forward at rf=0.74 for crisp upper lid fold
                if rf < 0.95:
                    co.y -= 0.0012 * math.sin(rf * math.pi)
                bv = builder.bm.verts.new(co)
                bv[builder.part_layer] = pid_ul if rim_is_upper[i] else pid_ll
                bv[builder.sub_layer] = 2 if rf > 0.9 else 1
                cur_v.append(bv)
                cur_uv.append(
                    (
                        outer_uv[i][0] * (1.0 - rf) + rim_uvs[i][0] * rf,
                        outer_uv[i][1] * (1.0 - rf) + rim_uvs[i][1] * rf,
                    )
                )
            for i in range(n_p):
                inext = (i + 1) % n_p
                f = builder.bm.faces.new((prev_v[i], prev_v[inext], cur_v[inext], cur_v[i]))
                f.material_index = 0
                f.smooth = True
                for lp, uvv in zip(f.loops, (prev_uv[i], prev_uv[inext], cur_uv[inext], cur_uv[i])):
                    lp[builder.uv_layer].uv = uvv
            prev_v, prev_uv = cur_v, cur_uv

        # Inner conjunctival rim wrapping onto eyeball -> zero visible gap around eyes!
        in_v = []
        for i in range(n_p):
            bv = builder.bm.verts.new(rim_inner_pts[i])
            bv[builder.part_layer] = pid_ul if rim_is_upper[i] else pid_ll
            bv[builder.sub_layer] = 2
            in_v.append(bv)
        for i in range(n_p):
            inext = (i + 1) % n_p
            f = builder.bm.faces.new((prev_v[i], prev_v[inext], in_v[inext], in_v[i]))
            f.material_index = 0
            f.smooth = True
            for lp, uvv in zip(f.loops, (prev_uv[i], prev_uv[inext], prev_uv[inext], prev_uv[i])):
                lp[builder.uv_layer].uv = uvv

    # --- STITCH CONCENTRIC PERIORAL LIPS (ZERO-GAP CLOSED COMMISSURE) + ORAL CAVITY BAG ---
    m_outer_v, m_outer_uv = extract_window_loop(m_u0, m_u1, m_v0, m_v1)
    n_m = len(m_outer_v)  # 32 vertices!
    mouth_center = Vector((0.0, -0.098, 1.6075))
    pid_ulip = builder.register_part("LIP_UPPER")
    pid_llip = builder.register_part("LIP_LOWER")
    pid_oral = builder.register_part("ORAL_BAG")

    # Classify each perimeter index cleanly into upper half vs lower half vs exact corners
    lip_vermilion = []
    lip_crest = []
    lip_contact = []
    lip_mucosa = []
    lip_is_upper = []
    lip_uv_verm = []
    lip_uv_contact = []

    for i, bv_out in enumerate(m_outer_v):
        rel = bv_out.co - mouth_center
        # Notice: extract_window_loop goes bottom (u0->u1, rel.z<0), right (v0->v1), top (u1->u0, rel.z>0), left (v1->v0)
        ang = math.atan2(rel.z, rel.x)
        is_up = i >= (n_m // 2 - 2) and i < (n_m - 3)
        # Better: strictly classify by index along the rectangle!
        # Bottom edge: 0..9 (10), Right edge: 10..15 (6), Top edge: 16..25 (10), Left edge: 26..31 (6)
        # Mid-right corner is index 13, mid-left corner is index 29!
        is_corner = i in (13, 29)
        is_upper = 13 < i < 29
        lip_is_upper.append((is_upper, is_corner))

        # Parameterize horizontal coordinate sx in [-1, 1] along mouth width (+-24mm)
        sx = math.cos(ang)
        sz = math.sin(ang)
        mx = 0.0245 * sx

        # Cupid's bow on upper vermilion border, full curve on lower vermilion border
        cupid = 0.0020 * math.cos(sx * math.pi * 2.0) * (1.0 - sx * sx) if is_upper else 0.0
        if is_corner:
            vz = mouth_center.z + 0.0012
            cz = vz
            contact_z = vz
        elif is_upper:
            vz = mouth_center.z + 0.0085 * abs(sz) + cupid
            cz = mouth_center.z + 0.0042 * abs(sz) + 0.5 * cupid
            contact_z = mouth_center.z + 0.0012 * (sx * sx)
        else:
            vz = mouth_center.z - 0.0092 * abs(sz)
            cz = mouth_center.z - 0.0046 * abs(sz)
            # EXACT SAME Z & Y AS UPPER CONTACT ROW -> 0.000mm gap when mouth is closed!
            contact_z = mouth_center.z + 0.0012 * (sx * sx)

        curve_y = 0.0065 * (sx * sx)
        p_verm = Vector((mx * 1.04, -0.0975 + curve_y, vz))
        p_crest = Vector((mx * 0.98, -0.1025 + curve_y, cz))
        p_cont = Vector((mx * 0.92, -0.0990 + curve_y, contact_z))
        p_muc = Vector((mx * 0.88, -0.0890 + curve_y, contact_z + (0.0025 if is_upper else -0.0025 if not is_corner else 0.0)))

        lip_vermilion.append(p_verm)
        lip_crest.append(p_crest)
        lip_contact.append(p_cont)
        lip_mucosa.append(p_muc)
        lip_uv_verm.append((0.32 + sx * 0.065, 0.445 + sz * 0.028))
        lip_uv_contact.append((0.32 + sx * 0.055, 0.445 + sz * 0.006))

    def make_lip_ring(pts, uvs, sub_code):
        ring = []
        for idx_p, p in enumerate(pts):
            is_up, is_cor = lip_is_upper[idx_p]
            bv = builder.bm.verts.new(p)
            if is_cor:
                bv[builder.part_layer] = pid_ulip
                bv[builder.sub_layer] = 99  # Corner tag (shared 50/50 jaw + corner bone)
            else:
                bv[builder.part_layer] = pid_ulip if is_up else pid_llip
                bv[builder.sub_layer] = sub_code
            ring.append(bv)
        return ring, uvs

    # Outer nasolabial blend ring -> Vermilion border -> Lip fullness crest -> Zero-gap contact line
    mid_pts = [m_outer_v[i].co.lerp(lip_vermilion[i], 0.55) for i in range(n_m)]
    mid_uvs = [
        (
            m_outer_uv[i][0] * 0.45 + lip_uv_verm[i][0] * 0.55,
            m_outer_uv[i][1] * 0.45 + lip_uv_verm[i][1] * 0.55,
        )
        for i in range(n_m)
    ]

    lip_stages = [
        (mid_pts, mid_uvs, 1, 0),
        (lip_vermilion, lip_uv_verm, 2, 0),
        (lip_crest, lip_uv_verm, 3, 0),
        (lip_contact, lip_uv_contact, 4, 0),
    ]

    prev_lv, prev_luv = m_outer_v, m_outer_uv
    for pts, uvs, scode, mat_id in lip_stages:
        cur_lv, cur_luv = make_lip_ring(pts, uvs, scode)
        for i in range(n_m):
            inext = (i + 1) % n_m
            f = builder.bm.faces.new((prev_lv[i], prev_lv[inext], cur_lv[inext], cur_lv[i]))
            f.material_index = mat_id
            f.smooth = True
            for lp, uvv in zip(f.loops, (prev_luv[i], prev_luv[inext], cur_luv[inext], cur_luv[i])):
                lp[builder.uv_layer].uv = uvv
        prev_lv, prev_luv = cur_lv, cur_luv

    # Inner Oral Cavity Bag (3 rings extending backward into dark shadowed Q4 UV [0.55..0.95, 0.05..0.45] + closed throat cap!)
    oral_depths = [
        (lip_mucosa, 0.15),
        ([Vector((lip_mucosa[i].x * 1.12, -0.065, 1.608 + (0.016 if lip_is_upper[i][0] else -0.018 if not lip_is_upper[i][1] else 0.0))) for i in range(n_m)], 0.25),
        ([Vector((lip_mucosa[i].x * 0.85, -0.028, 1.608 + (0.013 if lip_is_upper[i][0] else -0.014 if not lip_is_upper[i][1] else 0.0))) for i in range(n_m)], 0.38),
    ]
    for pts, v_off in oral_depths:
        cur_lv = []
        cur_luv = []
        for i, p in enumerate(pts):
            is_up, is_cor = lip_is_upper[i]
            bv = builder.bm.verts.new(p)
            bv[builder.part_layer] = pid_oral
            bv[builder.sub_layer] = 1 if is_up else (99 if is_cor else 2)
            cur_lv.append(bv)
            cur_luv.append((0.75 + 0.15 * math.cos(2 * math.pi * i / n_m), v_off))
        for i in range(n_m):
            inext = (i + 1) % n_m
            f = builder.bm.faces.new((prev_lv[i], prev_lv[inext], cur_lv[inext], cur_lv[i]))
            f.material_index = 1  # M_Eyes_Mouth (Q4 shadowed oral wall)
            f.smooth = True
            for lp, uvv in zip(f.loops, (prev_luv[i], prev_luv[inext], cur_luv[inext], cur_luv[i])):
                lp[builder.uv_layer].uv = uvv
        prev_lv, prev_luv = cur_lv, cur_luv

    # Cap back of oral cavity bag -> 100% watertight, zero holes through head during speech!
    oral_back = builder.bm.verts.new(Vector((0.0, -0.020, 1.608)))
    oral_back[builder.part_layer] = pid_oral
    oral_back[builder.sub_layer] = 1
    for i in range(n_m):
        inext = (i + 1) % n_m
        f = builder.bm.faces.new((prev_lv[i], prev_lv[inext], oral_back))
        f.material_index = 1
        f.smooth = True
        f.loops[0][builder.uv_layer].uv = prev_luv[i]
        f.loops[1][builder.uv_layer].uv = prev_luv[inext]
        f.loops[2][builder.uv_layer].uv = (0.75, 0.25)


def build_eyes_teeth_tongue_ears_hair(builder: MeshPartBuilder) -> None:
    """Adds spherical eyeballs, upper/lower dental arches, articulated tongue, ears, brows, hair, and neural cable."""
    # 1. Eyeballs (M_Eyes_Mouth Q1: centered at U=0.25, V=0.75, facing -Y)
    for side_sign, pname in [(-1.0, "EYEBALL_R"), (+1.0, "EYEBALL_L")]:
        center = Vector((side_sign * 0.032, -0.074, 1.675))
        r_eye = 0.0120
        n_seg, n_ring = 28, 16
        rings, uvs = [], []
        for ir in range(n_ring):
            # phi = 0 at front pole (-Y), pi at back pole (+Y)
            phi = math.pi * (0.04 + 0.92 * ir / (n_ring - 1))
            sp, cp = math.sin(phi), math.cos(phi)
            # Cornea bulge near phi < 0.42
            cornea = 0.0007 * max(0.0, 1.0 - (phi / 0.42) ** 2)
            row, ruv = [], []
            for iseg in range(n_seg):
                az = 2.0 * math.pi * iseg / n_seg
                px = center.x + r_eye * sp * math.cos(az)
                pz = center.z + r_eye * sp * math.sin(az)
                py = center.y - (r_eye + cornea) * cp
                row.append(Vector((px, py, pz)))
                # Map front hemisphere directly onto Q1 iris/sclera atlas (0.25, 0.75)
                rad_uv = min(0.24, 0.24 * (phi / (math.pi * 0.52)))
                ruv.append((0.25 + rad_uv * math.cos(az), 0.75 + rad_uv * math.sin(az)))
            rings.append(row)
            uvs.append(ruv)
        builder.add_grid(rings, uvs, mat_idx=1, part_name=pname, closed_u=True, cap_start=True, cap_end=True)

    # 2. Upper & Lower Dental Arches (M_Eyes_Mouth Q2: U in [0.52, 0.98], V in [0.52, 0.98])
    for is_upper, pname, z_base, dir_sign in [
        (True, "TEETH_UPPER", 1.617, -1.0),
        (False, "TEETH_LOWER", 1.598, +1.0),
    ]:
        n_arch = 24
        # Cross section around the horseshoe arch (4 profile stations: labial gum -> labial crown -> incisal edge -> lingual gum)
        prof_offsets = [
            (0.000, 0.000, 0.95),   # Gum base (V=0.95 -> pink gum line in Q2!)
            (-0.0015, 0.0045 * dir_sign, 0.72),
            (-0.0008, 0.0085 * dir_sign, 0.54),  # Incisal/occlusal crown edge (Z~1.6085 upper, Z~1.6065 lower)
            (0.0038, 0.0010 * dir_sign, 0.88),   # Lingual side
        ]
        rings, uvs = [], []
        for iu_a in range(n_arch):
            t = -1.0 + 2.0 * iu_a / (n_arch - 1)  # -1 right molar to +1 left molar
            ax = 0.022 * math.sin(t * math.pi * 0.48)
            ay = -0.090 + 0.028 * (1.0 - math.cos(t * math.pi * 0.48))
            out_n = Vector((math.sin(t * math.pi * 0.48), -math.cos(t * math.pi * 0.48), 0.0)).normalized()
            # Subtle individual tooth scalloping
            scallop = 0.0005 * abs(math.cos(t * 8.0 * math.pi))
            row, ruv = [], []
            for r_off, z_off, tv in prof_offsets:
                p = Vector((ax, ay, z_base + z_off + scallop * dir_sign)) - out_n * (-r_off)
                row.append(p)
                ruv.append((0.52 + 0.46 * (iu_a / (n_arch - 1)), tv))
            rings.append(row)
            uvs.append(ruv)
        builder.add_grid(rings, uvs, mat_idx=1, part_name=pname, closed_u=True)

    # 3. Articulated 3D Tongue (M_Eyes_Mouth Q3: U in [0.04, 0.46], V in [0.04, 0.46])
    t_rings, t_uvs = [], []
    n_tlen, n_tseg = 12, 16
    for il in range(n_tlen):
        tl = il / (n_tlen - 1)  # 0 = tongue root (Y=-0.038), 1 = tongue tip (Y=-0.087)
        ty = -0.038 - 0.049 * tl
        tz = 1.596 + 0.004 * math.sin(tl * math.pi)
        tw = 0.017 * math.sqrt(max(0.04, 1.0 - 0.82 * (tl**2.2)))
        th = 0.0065 * math.sqrt(max(0.06, 1.0 - 0.78 * (tl**2.0)))
        row, ruv = [], []
        for iseg in range(n_tseg):
            ang = 2.0 * math.pi * iseg / n_tseg
            groove = -0.0012 * max(0.0, math.sin(ang)) * math.exp(-((math.cos(ang) / 0.25) ** 2))
            row.append(Vector((tw * math.cos(ang), ty, tz + th * math.sin(ang) + groove)))
            ruv.append((0.25 + 0.20 * math.cos(ang), 0.06 + 0.38 * tl))
        t_rings.append(row)
        t_uvs.append(ruv)
    builder.add_grid(t_rings, t_uvs, mat_idx=1, part_name="TONGUE", closed_u=True, cap_start=True, cap_end=True)

    # 4. Sculpted Human Ears (M_Skin_FaceBody)
    for side_sign in (-1.0, +1.0):
        e_rings, e_uvs = [], []
        for iv in range(10):
            tv = iv / 9.0  # 0 lobe (Z=1.640) -> 1 helix top (Z=1.692)
            ez = 1.640 + 0.052 * tv
            ey_c = -0.006 + 0.008 * math.sin(tv * math.pi)
            ex_c = side_sign * (0.067 + 0.012 * math.sin(tv * math.pi * 0.85))
            w_y = 0.014 * math.sin(0.2 + tv * math.pi * 0.75)
            w_x = 0.0055
            row, ruv = [], []
            for iu in range(12):
                ang = 2.0 * math.pi * iu / 12.0
                concha = -0.003 * max(0.0, -side_sign * math.cos(ang))
                p = Vector((ex_c + (w_x + concha) * math.cos(ang), ey_c + w_y * math.sin(ang), ez))
                row.append(p)
                ruv.append((0.08 + 0.06 * tv, 0.55 + 0.06 * math.sin(ang)))
            e_rings.append(row)
            e_uvs.append(ruv)
        builder.add_grid(e_rings, e_uvs, mat_idx=0, part_name="HEAD_SKIN", closed_u=True, cap_start=True, cap_end=True)

    # 5. Sculpted 3D Eyebrow Strips (M_Hair)
    for side_sign, b_part in [(-1.0, "BROW_R"), (+1.0, "BROW_L")]:
        b_rings, b_uvs = [], []
        for il in range(9):
            t = il / 8.0  # 0 inner brow -> 1 outer arch/tail
            bx = side_sign * (0.012 + 0.040 * t)
            arch = math.sin(t * math.pi * 0.82)
            bz = 1.694 + 0.0065 * arch - 0.003 * (t**2)
            # Conform right onto supraorbital ridge
            th_est = math.atan2(bx, 0.092)
            surf = eval_head_surface(th_est, (bz - 1.455) / 0.337)
            thick = 0.0034 * (1.0 - 0.55 * (t**1.8))
            row, ruv = [], []
            for iseg in range(8):
                ang = 2.0 * math.pi * iseg / 8.0
                row.append(Vector((bx, surf.y - 0.0022 - 0.0018 * math.cos(ang), bz + thick * math.sin(ang))))
                ruv.append((0.15 + 0.7 * (iseg / 8.0), 0.1 + 0.8 * t))
            b_rings.append(row)
            b_uvs.append(ruv)
        builder.add_grid(b_rings, b_uvs, mat_idx=2, part_name=b_part, closed_u=True, cap_start=True, cap_end=True)

    # 6. Layered Cyberpunk Undercut Hair Cap + Swept Crest Locks (M_Hair) — Crown max Z = 1.800 m EXACT!
    h_rings, h_uvs = [], []
    n_hu, n_hv = 44, 18
    for iv in range(n_hv):
        tv = iv / (n_hv - 1)  # 0 hairline/nape -> 1 top swept crown
        row, ruv = [], []
        for iu in range(n_hu):
            th = -math.pi + 2.0 * math.pi * iu / n_hu
            # Asymmetric cyberpunk side-part hairline (higher over left temple, subtle swept fringe on right forehead, clean undercut around ears!)
            front_w = max(0.0, math.cos(th))
            side_w = abs(math.sin(th))
            asym_part = 0.045 * math.sin(th - 0.3) * front_w
            v_start = 0.36 + 0.45 * (front_w**1.4) + 0.24 * (side_w**2.2) + asym_part
            v_head = v_start + (0.995 - v_start) * tv
            surf = eval_head_surface(th, min(0.995, v_head))
            strand_wave = 0.0024 * math.sin(th * 12.0 + tv * 5.0) * math.sin(tv * math.pi)
            undercut_loft = 0.003 + 0.011 * smoothstep(0.28, 0.85, tv) * (0.55 + 0.45 * math.sin(th + 0.8)) + strand_wave
            nrm = Vector((surf.x, surf.y, max(0.02, surf.z - 1.66))).normalized()
            p = surf + nrm * undercut_loft
            p.z = min(1.800, p.z)
            # Diagonal UV shear so hair strands flow diagonally back-and-across like swept locks!
            ruv.append((((iu / n_hu) + 0.22 * tv) % 1.0, tv))
            row.append(p)
        h_rings.append(row)
        h_uvs.append(ruv)
    builder.add_grid(h_rings, h_uvs, mat_idx=2, part_name="HAIR", closed_u=True, cap_end=True)

    # Ensure exact crown point hits 1.800 m cleanly
    crest_rings, crest_uvs = [], []
    for il in range(10):
        t = il / 9.0
        cy = -0.065 + 0.155 * t
        cz = 1.786 + 0.014 * math.sin(t * math.pi * 0.72)  # Peaks cleanly at Z = 1.800 m!
        cx = 0.010 * math.sin(t * math.pi)
        r_lock = 0.018 * math.sin(0.15 + t * math.pi * 0.82)
        row, ruv = [], []
        for iseg in range(10):
            ang = 2.0 * math.pi * iseg / 10.0
            p = Vector((cx + r_lock * 1.3 * math.cos(ang), cy, min(1.800, cz + r_lock * 0.55 * math.sin(ang))))
            row.append(p)
            ruv.append((iseg / 10.0, t))
        crest_rings.append(row)
        crest_uvs.append(ruv)
    builder.add_grid(crest_rings, crest_uvs, mat_idx=2, part_name="HAIR", closed_u=True, cap_start=True, cap_end=True)

    # 7. Occipital Neural Port + Secondary-Motion Braided Cyber-Cable (cable_01..03)
    c_rings, c_uvs = [], []
    n_clen = 18
    for il in range(n_clen):
        t = il / (n_clen - 1)  # 0 at occipital port (0, 0.088, 1.665) -> 1 at cable tip (0, 0.155, 1.405)
        cy = 0.088 + 0.067 * math.sin(t * math.pi * 0.55)
        cz = 1.665 - 0.260 * t
        r_cab = 0.013 * (1.0 - 0.45 * t) + (0.005 if il < 2 else 0.0)
        braid = 0.0018 * math.sin(t * 28.0 * math.pi)
        row, ruv = [], []
        for iseg in range(12):
            ang = 2.0 * math.pi * iseg / 12.0
            row.append(Vector(((r_cab + braid) * math.cos(ang), cy + (r_cab + braid) * math.sin(ang), cz)))
            # Use glowing conduit strip on last tip band, cyber chassis elsewhere
            if t > 0.84:
                ruv.append((0.70 + 0.20 * (iseg / 12.0), 0.06 + 0.10 * (t - 0.84) / 0.16))
            else:
                ruv.append((0.10 + 0.45 * (iseg / 12.0), 0.05 + 0.25 * t))
        c_rings.append(row)
        c_uvs.append(ruv)
    builder.add_grid(c_rings, c_uvs, mat_idx=4, part_name="CABLE", closed_u=True, cap_start=True, cap_end=True)


def build_torso_and_legs(builder: MeshPartBuilder) -> None:
    """Builds anatomical fitted-suit torso, pelvis, thighs, 5-loop knees, calves, and planted combat boots."""
    # 1. Torso & Pelvis (Z from 0.885 m pelvis base to 1.482 m neck collar socket)
    # Profile slices: (z, rx_half_width, ry_half_depth, y_center, is_flex_rib)
    torso_profile = [
        (0.848, 0.068, 0.082, 0.010, False),  # Seamless groin saddle base
        (0.885, 0.148, 0.102, 0.010, False),  # Full hip wrap overlapping thigh sockets -> zero gap!
        (0.925, 0.162, 0.110, 0.012, False),  # Hip / glute fullness
        (0.965, 0.162, 0.108, 0.010, False),  # Iliac crest
        (1.020, 0.142, 0.095, 0.008, True),   # Lower waist flex
        (1.080, 0.132, 0.090, 0.010, True),   # Narrow athletic waist
        (1.145, 0.142, 0.098, 0.010, True),   # Lower ribcage
        (1.215, 0.156, 0.108, 0.008, False),  # Mid ribcage
        (1.285, 0.170, 0.118, 0.002, False),  # Pectoral / bust fullness
        (1.345, 0.178, 0.114, 0.004, False),  # Upper chest / lat flare
        (1.405, 0.188, 0.102, 0.008, False),  # Deltoid-pectoral bridge
        (1.452, 0.145, 0.082, 0.008, False),  # Trapezius / clavicle slope
        (1.472, 0.072, 0.068, 0.006, True),   # High collar gasket (wraps neck cleanly -> zero neck seam!)
        (1.485, 0.052, 0.054, 0.005, True),   # Tucked inside neck!
    ]
    # Subdivide vertical slices smoothly via Catmull-Rom / dense linear-cosine interpolation for 34 clean deformation rings
    t_rings, t_uvs = [], []
    n_tu = 44
    dense_torso = []
    for idx in range(len(torso_profile) - 1):
        p0, p1 = torso_profile[idx], torso_profile[idx + 1]
        steps = 3
        for s in range(steps):
            ft = smoothstep(0.0, 1.0, s / steps)
            dense_torso.append(
                (
                    p0[0] + (p1[0] - p0[0]) * (s / steps),
                    p0[1] + (p1[1] - p0[1]) * ft,
                    p0[2] + (p1[2] - p0[2]) * ft,
                    p0[3] + (p1[3] - p0[3]) * ft,
                    p0[4],
                )
            )
    dense_torso.append(torso_profile[-1])

    for iv, (z, rx, ry, yc, is_flex) in enumerate(dense_torso):
        tv = iv / (len(dense_torso) - 1)
        row, ruv = [], []
        for iu in range(n_tu):
            ang = 2.0 * math.pi * iu / n_tu
            ca, sa = math.cos(ang), math.sin(ang)
            # Superellipse chest/back muscle contour (spinal furrow on back +Y, pectoral contour on front -Y)
            spinal_groove = -0.007 * max(0.0, sa) * math.exp(-((ca / 0.18) ** 2)) * smoothstep(0.95, 1.15, z) * (1.0 - smoothstep(1.40, 1.47, z))
            pec_contour = -0.008 * max(0.0, -sa) * math.exp(-(((abs(ca) - 0.45) / 0.25) ** 2)) * gauss(z, 1.30, 0.055)
            px = rx * ca
            py = yc + (ry + spinal_groove) * sa + pec_contour
            row.append(Vector((px, py, z)))
            v_uv = (0.04 + 0.22 * tv) if is_flex else (0.30 + 0.68 * tv)
            ruv.append((iu / n_tu, v_uv))
        t_rings.append(row)
        t_uvs.append(ruv)
    builder.add_grid(t_rings, t_uvs, mat_idx=3, part_name="TORSO_SUIT", closed_u=True, cap_start=True, cap_end=True)

    # 2. Left & Right Legs + Tactical Combat Boots (Z = 0.000 m planted sole!)
    for side_sign, leg_part, boot_part in [
        (-1.0, "LEG_R", "BOOT_R"),
        (+1.0, "LEG_L", "BOOT_L"),
    ]:
        # Leg slices from thigh hip socket (Z=0.960) down to ankle (Z=0.095) with 5 dense knee rings around Z=0.515!
        leg_stations = [
            (0.965, 0.088, 0.092, side_sign * 0.094, 0.008, False),
            (0.900, 0.094, 0.096, side_sign * 0.096, 0.006, False),
            (0.810, 0.088, 0.090, side_sign * 0.097, 0.002, False),
            (0.710, 0.078, 0.082, side_sign * 0.097, -0.004, False),
            (0.610, 0.068, 0.072, side_sign * 0.098, -0.010, False),
            # 5 Intentional Knee Deformation Loops around Z = 0.515 m!
            (0.555, 0.061, 0.065, side_sign * 0.098, -0.013, True),
            (0.535, 0.059, 0.064, side_sign * 0.098, -0.015, True),
            (0.515, 0.058, 0.065, side_sign * 0.098, -0.016, True),
            (0.495, 0.057, 0.063, side_sign * 0.098, -0.014, True),
            (0.475, 0.058, 0.063, side_sign * 0.098, -0.010, True),
            # Gastrocnemius calf muscle swell -> tapered Achilles/ankle
            (0.410, 0.064, 0.070, side_sign * 0.098, 0.004, False),
            (0.340, 0.062, 0.068, side_sign * 0.098, 0.012, False),
            (0.255, 0.052, 0.056, side_sign * 0.098, 0.016, False),
            (0.175, 0.045, 0.049, side_sign * 0.098, 0.018, True),
            # 3 Ankle Bend Loops around Z = 0.095 m!
            (0.115, 0.043, 0.047, side_sign * 0.098, 0.020, True),
            (0.095, 0.044, 0.049, side_sign * 0.098, 0.020, True),
            (0.075, 0.046, 0.054, side_sign * 0.098, 0.018, True),
        ]
        l_rings, l_uvs = [], []
        n_lu = 28
        for iv, (z, rx, ry, xc, yc, is_flex) in enumerate(leg_stations):
            tv = iv / (len(leg_stations) - 1)
            row, ruv = [], []
            for iu in range(n_lu):
                ang = 2.0 * math.pi * iu / n_lu
                row.append(Vector((xc + rx * math.cos(ang), yc + ry * math.sin(ang), z)))
                v_uv = (0.04 + 0.22 * (iv % 4) / 3.0) if is_flex else (0.32 + 0.64 * tv)
                ruv.append((iu / n_lu, v_uv))
            l_rings.append(row)
            l_uvs.append(ruv)
        builder.add_grid(l_rings, l_uvs, mat_idx=3, part_name=leg_part, closed_u=True, cap_start=True)

        # Tactical Combat Boot (M_CyberArmor, flat ground contact Z = 0.000 m, heel Y=+0.075, toe Y=-0.205!)
        # Boot loft from cuff (Z=0.185) down through ankle, instep/ball, to flat sole at Z=0.000 m!
        boot_slices = [
            # (z, rx, y_front, y_back, uv_v)
            (0.185, 0.051, -0.036, 0.072, 0.90),
            (0.135, 0.049, -0.042, 0.073, 0.78),
            (0.090, 0.050, -0.075, 0.076, 0.66),
            (0.052, 0.052, -0.155, 0.078, 0.54),
            (0.026, 0.054, -0.198, 0.078, 0.44),
            (0.008, 0.055, -0.205, 0.077, 0.38),
            (0.000, 0.053, -0.202, 0.075, 0.36),  # EXACT Z = 0.000 m flat planted sole!
        ]
        b_rings, b_uvs = [], []
        xc = side_sign * 0.098
        for z, rx, yf, yb, uvv in boot_slices:
            yc = 0.5 * (yf + yb)
            ry = 0.5 * (yb - yf)
            row, ruv = [], []
            for iu in range(n_lu):
                ang = 2.0 * math.pi * iu / n_lu
                ca, sa = math.cos(ang), math.sin(ang)
                # Slightly squared-off tactical boot toe & sole profile
                sq = 1.0 + 0.10 * (ca * ca * sa * sa)
                row.append(Vector((xc + rx * ca * sq, yc + ry * sa * sq, z)))
                ruv.append((0.04 + 0.54 * (iu / n_lu), uvv))
            b_rings.append(row)
            b_uvs.append(ruv)
        builder.add_grid(b_rings, b_uvs, mat_idx=4, part_name=boot_part, closed_u=True, cap_start=True, cap_end=True)


def build_arms_and_hands(builder: MeshPartBuilder) -> None:
    """
    Left Arm (+X): Tactical shoulder sleeve -> bare ORGANIC human elbow, forearm, wrist, palm & 5 articulated fingers.
    Right Arm (-X): Tactical shoulder -> visibly CYBERNETIC prosthetic forearm, mechanical wrist & 5 articulated fingers.
    """
    for side_sign in (+1.0, -1.0):
        is_cyber = side_sign < 0.0
        # Arm centerline along X from shoulder (0.162) -> elbow (0.445, Y=0.028, Z=1.468) -> wrist (0.705, Y=0.005, Z=1.464)
        arm_stations = [
            # (x_abs, y_c, z_c, ry, rz)
            (0.155, 0.008, 1.468, 0.062, 0.066),
            (0.205, 0.012, 1.472, 0.056, 0.058),  # Deltoid fullness
            (0.275, 0.018, 1.471, 0.048, 0.050),  # Bicep/tricep
            (0.335, 0.022, 1.470, 0.046, 0.047),  # Sleeve cuff / Cyber-collar boundary!
        ]
        # Upper arm sleeve segment (M_Suit_Fabric)
        n_au = 24
        s_rings, s_uvs = [], []
        for ix, (xa, yc, zc, ry, rz) in enumerate(arm_stations):
            row, ruv = [], []
            for iu in range(n_au):
                ang = 2.0 * math.pi * iu / n_au
                row.append(Vector((side_sign * xa, yc + ry * math.cos(ang), zc + rz * math.sin(ang))))
                ruv.append((iu / n_au, 0.35 + 0.45 * (ix / 3.0)))
            s_rings.append(row)
            s_uvs.append(ruv)
        # Rolled cuff / machined bicep cyber-collar lip
        cuff_x = 0.340
        row_cuff, ruv_cuff = [], []
        for iu in range(n_au):
            ang = 2.0 * math.pi * iu / n_au
            row_cuff.append(Vector((side_sign * cuff_x, 0.022 + 0.050 * math.cos(ang), 1.470 + 0.051 * math.sin(ang))))
            ruv_cuff.append((iu / n_au, 0.85))
        s_rings.append(row_cuff)
        s_uvs.append(ruv_cuff)
        builder.add_grid(
            s_rings,
            s_uvs,
            mat_idx=4 if is_cyber else 3,
            part_name="ARM_UPPER_R" if is_cyber else "ARM_UPPER_L",
            closed_u=True,
            cap_start=True,
            cap_end=True,
        )

        # Lower Bicep -> 5-Ring Elbow Joint (X=0.445) -> Forearm -> 3-Ring Wrist (X=0.705) -> Palm (X=0.782)!
        forearm_stations = [
            (0.338, 0.022, 1.470, 0.044, 0.045),
            (0.390, 0.025, 1.469, 0.042, 0.043),
            # 5 Intentional Elbow Deformation Loops around X = 0.445!
            (0.422, 0.027, 1.468, 0.041, 0.041),
            (0.436, 0.028, 1.468, 0.040, 0.040),
            (0.445, 0.029, 1.468, 0.041, 0.039),  # Olecranon elbow center
            (0.456, 0.027, 1.468, 0.042, 0.041),
            (0.472, 0.025, 1.467, 0.045, 0.043),
            # Forearm muscle belly / segmented cyber-chassis taper to wrist
            (0.515, 0.021, 1.467, 0.046, 0.042),
            (0.565, 0.016, 1.466, 0.041, 0.037),
            (0.625, 0.011, 1.465, 0.035, 0.031),
            (0.675, 0.007, 1.464, 0.031, 0.025),
            # 3 Wrist Deformation Loops around X = 0.705!
            (0.695, 0.006, 1.464, 0.030, 0.022),
            (0.705, 0.005, 1.464, 0.031, 0.021),
            (0.716, 0.004, 1.464, 0.034, 0.020),
            # Sculpted Palm (flattened dorsal-palmar thickness rz=0.015, wide metacarpal span ry=0.043)
            (0.748, 0.003, 1.463, 0.042, 0.016),
            (0.782, 0.002, 1.462, 0.043, 0.014),
        ]
        f_rings, f_uvs = [], []
        for ix, (xa, yc, zc, ry, rz) in enumerate(forearm_stations):
            tx = ix / (len(forearm_stations) - 1)
            row, ruv = [], []
            for iu in range(n_au):
                ang = 2.0 * math.pi * iu / n_au
                ca, sa = math.cos(ang), math.sin(ang)
                if is_cyber:
                    # Faceted chamfered cybernetic alloy plates + recessed actuator groove at elbow/wrist!
                    is_joint = (0.415 < xa < 0.475) or (0.688 < xa < 0.720)
                    facet = 1.0 + (0.06 * math.cos(ang * 4.0) if not is_joint else -0.07)
                    py = yc + ry * ca * facet
                    pz = zc + rz * sa * facet
                    # Map dorsal/ventral alloy plates vs glowing circuit conduit seam vs dark actuator joints
                    if abs(sa) > 0.92 and not is_joint:
                        uv_pt = (0.72 + 0.22 * tx, 0.06 + 0.12 * (0.5 + 0.5 * ca))  # Glowing circuit seam!
                    elif is_joint:
                        uv_pt = (0.08 + 0.48 * (iu / n_au), 0.06 + 0.24 * tx)       # Dark carbon actuator
                    else:
                        uv_pt = (0.06 + 0.52 * (iu / n_au), 0.40 + 0.54 * tx)       # Brushed alloy plate
                else:
                    # Smooth organic human muscle & tendon contour
                    muscle = 0.0025 * math.cos(ang * 2.0) * gauss(xa, 0.51, 0.05)
                    py = yc + (ry + muscle) * ca
                    pz = zc + rz * sa
                    uv_pt = (0.66 + 0.32 * (iu / n_au), 0.04 + 0.92 * tx)
                row.append(Vector((side_sign * xa, py, pz)))
                ruv.append(uv_pt)
            f_rings.append(row)
            f_uvs.append(ruv)
        builder.add_grid(
            f_rings,
            f_uvs,
            mat_idx=4 if is_cyber else 0,
            part_name="FOREARM_CYBER_R" if is_cyber else "FOREARM_ORGANIC_L",
            closed_u=True,
            cap_start=True,
            cap_end=True,
        )

        # --- 5 INDIVIDUALLY ARTICULATED FINGERS PER HAND (3 Phalanges + 3 Knuckle Bend Loops each!) ---
        # Finger definitions matching build_rig_and_skin.py joint landmarks!
        # Thumb starts on anterior palm (-Y) at X=0.730; Index..Pinky start along distal metacarpal arch at X=0.782
        finger_specs = [
            # (name_idx, base_x, base_y, base_z, dir_vec, length_total, radius_base)
            ("THUMB",  0.730, -0.032, 1.454, Vector((side_sign * 0.82, -0.52, -0.24)).normalized(), 0.066, 0.0105),
            ("INDEX",  0.782, -0.030, 1.463, Vector((side_sign * 0.995, -0.08, -0.04)).normalized(), 0.082, 0.0088),
            ("MIDDLE", 0.785, -0.009, 1.464, Vector((side_sign * 0.999, -0.02, -0.03)).normalized(), 0.090, 0.0092),
            ("RING",   0.782, +0.012, 1.463, Vector((side_sign * 0.997, +0.04, -0.04)).normalized(), 0.084, 0.0086),
            ("PINKY",  0.776, +0.032, 1.461, Vector((side_sign * 0.990, +0.11, -0.05)).normalized(), 0.068, 0.0076),
        ]
        side_tag = "R" if is_cyber else "L"
        for fname, bx, by, bz, fdir, flen, r0 in finger_specs:
            p_base = Vector((side_sign * bx, by, bz))
            # Build orthonormal frame along finger axis
            up_ref = Vector((0.0, 0.0, 1.0))
            lat = fdir.cross(up_ref).normalized()
            dors = lat.cross(fdir).normalized()

            # 15 rings per finger with dense 3-ring clusters at MCP (t=0.04), PIP (t=0.45), and DIP (t=0.74)!
            t_samples = [0.0, 0.04, 0.12, 0.28, 0.41, 0.45, 0.49, 0.62, 0.70, 0.74, 0.78, 0.88, 0.95, 1.00]
            fg_rings, fg_uvs = [], []
            n_fu = 12
            for ts in t_samples:
                taper = (1.0 - 0.28 * ts) * (math.sqrt(max(0.08, 1.0 - ((ts - 0.88) / 0.12) ** 2)) if ts > 0.88 else 1.0)
                knuckle_swell = 1.0 + 0.06 * (gauss(ts, 0.45, 0.035) + gauss(ts, 0.74, 0.03))
                rad = r0 * taper * knuckle_swell
                c_pt = p_base + fdir * (flen * ts)
                is_knuckle = abs(ts - 0.45) < 0.045 or abs(ts - 0.74) < 0.045 or ts < 0.06
                row, ruv = [], []
                for iu in range(n_fu):
                    ang = 2.0 * math.pi * iu / n_fu
                    ca, sa = math.cos(ang), math.sin(ang)
                    p = c_pt + lat * (rad * ca) + dors * (rad * 0.90 * sa)
                    row.append(p)
                    if is_cyber:
                        uv_pt = (0.10 + 0.45 * (iu / n_fu), (0.08 + 0.20 * ts) if is_knuckle else (0.42 + 0.48 * ts))
                    else:
                        uv_pt = (0.68 + 0.28 * (iu / n_fu), 0.05 + 0.20 * ts)
                    ruv.append(uv_pt)
                fg_rings.append(row)
                fg_uvs.append(ruv)
            builder.add_grid(
                fg_rings,
                fg_uvs,
                mat_idx=4 if is_cyber else 0,
                part_name=f"FINGER_{fname}_{side_tag}",
                closed_u=True,
                cap_start=True,
                cap_end=True,
            )


def add_beveled_shell(
    builder: MeshPartBuilder,
    rings_inner: list[list[Vector]],
    thickness: float,
    uv_rect: tuple[float, float, float, float],
    mat_idx: int,
    part_name: str,
) -> None:
    """Extrudes a curved quad surface patch outward by `thickness` into a solid closed armor plate!"""
    pid = builder.register_part(part_name)
    nv = len(rings_inner)
    nu = len(rings_inner[0])
    u0, u1, v0, v1 = uv_rect

    # Compute smooth outward normals per grid vertex
    rings_outer = []
    for iv in range(nv):
        row_o = []
        for iu in range(nu):
            p = rings_inner[iv][iu]
            pu = rings_inner[iv][min(nu - 1, iu + 1)] - rings_inner[iv][max(0, iu - 1)]
            pv = rings_inner[min(nv - 1, iv + 1)][iu] - rings_inner[max(0, iv - 1)][iu]
            nrm = pu.cross(pv)
            if nrm.length < 1e-7:
                nrm = Vector((p.x, p.y, 0.0))
            nrm.normalize()
            # Ensure outward away from body spine (0, 0.01, p.z)
            radial = p - Vector((0.0, 0.01, p.z))
            if nrm.dot(radial) < 0.0:
                nrm = -nrm
            # Bevel taper near edges
            edge_u = min(iu, nu - 1 - iu) / max(1.0, (nu - 1) * 0.25)
            edge_v = min(iv, nv - 1 - iv) / max(1.0, (nv - 1) * 0.25)
            bevel = 0.35 + 0.65 * min(1.0, min(edge_u, edge_v))
            row_o.append(p + nrm * (thickness * bevel))
        rings_outer.append(row_o)

    bm_in, bm_out = [], []
    for iv in range(nv):
        ri, ro = [], []
        for iu in range(nu):
            vi = builder.bm.verts.new(rings_inner[iv][iu])
            vo = builder.bm.verts.new(rings_outer[iv][iu])
            vi[builder.part_layer] = pid
            vo[builder.part_layer] = pid
            ri.append(vi)
            ro.append(vo)
        bm_in.append(ri)
        bm_out.append(ro)

    def uv_at(iu: int, iv: int):
        return (u0 + (u1 - u0) * (iu / max(1, nu - 1)), v0 + (v1 - v0) * (iv / max(1, nv - 1)))

    # Outer & inner faces
    for iv in range(nv - 1):
        for iu in range(nu - 1):
            fo = builder.bm.faces.new((bm_out[iv][iu], bm_out[iv][iu + 1], bm_out[iv + 1][iu + 1], bm_out[iv + 1][iu]))
            fi = builder.bm.faces.new((bm_in[iv][iu], bm_in[iv + 1][iu], bm_in[iv + 1][iu + 1], bm_in[iv][iu + 1]))
            for f in (fo, fi):
                f.material_index = mat_idx
                f.smooth = True
            for lp, (cu, cv) in zip(fo.loops, ((iu, iv), (iu + 1, iv), (iu + 1, iv + 1), (iu, iv + 1))):
                lp[builder.uv_layer].uv = uv_at(cu, cv)
            for lp in fi.loops:
                lp[builder.uv_layer].uv = (0.15, 0.15)

    # Perimeter rim quads (mapped to accent trim/conduit strip for crisp cyberpunk silhouette!)
    rim_uv = ((0.66, 0.06), (0.94, 0.06), (0.94, 0.18), (0.66, 0.18))
    for iu in range(nu - 1):
        f1 = builder.bm.faces.new((bm_in[0][iu], bm_in[0][iu + 1], bm_out[0][iu + 1], bm_out[0][iu]))
        f2 = builder.bm.faces.new((bm_out[-1][iu], bm_out[-1][iu + 1], bm_in[-1][iu + 1], bm_in[-1][iu]))
        for f in (f1, f2):
            f.material_index = mat_idx
            f.smooth = False
            for lp, ruv in zip(f.loops, rim_uv):
                lp[builder.uv_layer].uv = ruv
    for iv in range(nv - 1):
        f1 = builder.bm.faces.new((bm_out[iv][0], bm_out[iv + 1][0], bm_in[iv + 1][0], bm_in[iv][0]))
        f2 = builder.bm.faces.new((bm_in[iv][-1], bm_in[iv + 1][-1], bm_out[iv + 1][-1], bm_out[iv][-1]))
        for f in (f1, f2):
            f.material_index = mat_idx
            f.smooth = False
            for lp, ruv in zip(f.loops, rim_uv):
                lp[builder.uv_layer].uv = ruv


def build_armor_and_props(builder: MeshPartBuilder) -> None:
    """
    Builds hard-surface tactical armor plates, secondary-motion hip strap,
    and all 4 authored props: Wrist Emitter, Retractable Forearm Blade, Removable Power Cell, Deployable Beacon.
    """
    # 1. Tactical Chest Mantle + Dorsal Team Crest Plate (M_CyberArmor)
    # Front plate (Z in [1.24, 1.44])
    front_grid = []
    for iv in range(9):
        tv = iv / 8.0
        z = 1.245 + 0.195 * tv
        rx = 0.145 + 0.036 * tv
        ry = 0.120 - 0.014 * tv
        row = []
        for iu in range(13):
            ang = -math.pi * 0.86 + (math.pi * 0.72) * (iu / 12.0)  # Front arc around -Y
            v_cut = -0.018 * (1.0 - abs(iu / 6.0 - 1.0)) * (1.0 - tv)
            row.append(Vector((rx * math.cos(ang), 0.004 + ry * math.sin(ang), z + v_cut)))
        front_grid.append(row)
    add_beveled_shell(builder, front_grid, 0.014, (0.06, 0.58, 0.42, 0.94), mat_idx=4, part_name="CHEST_ARMOR")

    # Back Dorsal Mantle mapped to Team Crest UV [0.64..0.96, 0.64..0.96] -> readable from 45-60 deg top-down gameplay view!
    back_grid = []
    for iv in range(9):
        tv = iv / 8.0
        z = 1.255 + 0.190 * tv
        rx = 0.138 + 0.038 * tv
        ry = 0.116 - 0.012 * tv
        row = []
        for iu in range(11):
            ang = math.pi * 0.22 + (math.pi * 0.56) * (iu / 10.0)  # Back arc around +Y
            row.append(Vector((rx * math.cos(ang), 0.008 + ry * math.sin(ang), z)))
        back_grid.append(row)
    add_beveled_shell(builder, back_grid, 0.015, (0.64, 0.96, 0.64, 0.96), mat_idx=4, part_name="CHEST_ARMOR")

    # Sculpted High Tactical Collar Guard (Z in [1.445, 1.520], open in front so jaw/throat stay clear!)
    col_grid = []
    for iv in range(6):
        tv = iv / 5.0
        z = 1.445 + 0.072 * tv
        rad = 0.088 + 0.016 * tv
        row = []
        for iu in range(15):
            ang = -math.pi * 0.20 + (math.pi * 1.40) * (iu / 14.0)  # Wraps left -> back -> right
            row.append(Vector((rad * math.cos(ang), 0.010 + rad * 0.95 * math.sin(ang), z)))
        col_grid.append(row)
    add_beveled_shell(builder, col_grid, 0.010, (0.08, 0.56, 0.50, 0.88), mat_idx=4, part_name="COLLAR_ARMOR")

    # 2. Asymmetric Left Shoulder Pauldron with Team Crest Emblem (+X = Left shoulder, UV [0.64..0.96, 0.64..0.96]!)
    paul_grid = []
    for iv in range(8):
        tv = iv / 7.0  # Medial clavicle -> lateral deltoid cap
        xa = 0.135 + 0.145 * tv
        zc = 1.515 - 0.048 * (tv**1.5)
        ry = 0.082 - 0.012 * tv
        row = []
        for iu in range(11):
            ang = -math.pi * 0.48 + (math.pi * 0.96) * (iu / 10.0)  # Wraps front-to-back over top of deltoid
            row.append(Vector((xa + 0.012 * math.cos(ang), 0.010 + ry * math.sin(ang), zc + 0.032 * math.cos(ang))))
        paul_grid.append(row)
    add_beveled_shell(builder, paul_grid, 0.013, (0.64, 0.96, 0.64, 0.96), mat_idx=4, part_name="PAULDRON_L")

    # 3. Tactical Utility Belt (pelvis Z in [0.935, 0.988]) + Secondary-Motion Hip Data-Strap (strap_01..03)
    belt_rings, belt_uvs = [], []
    for iv in range(6):
        tv = iv / 5.0
        z = 0.935 + 0.052 * tv
        bev = 0.008 * math.sin(tv * math.pi)
        row, ruv = [], []
        for iu in range(32):
            ang = 2.0 * math.pi * iu / 32.0
            buckle = 0.008 if abs(ang + math.pi * 0.5) < 0.25 else 0.0
            px = (0.165 + bev + buckle) * math.cos(ang)
            py = 0.010 + (0.114 + bev + buckle) * math.sin(ang)
            row.append(Vector((px, py, z)))
            ruv.append((0.06 + 0.52 * (iu / 32.0), (0.08 if tv in (0.0, 1.0) else 0.48 + 0.30 * tv)))
        belt_rings.append(row)
        belt_uvs.append(ruv)
    builder.add_grid(belt_rings, belt_uvs, mat_idx=4, part_name="BELT", closed_u=True, cap_start=True, cap_end=True)

    # Secondary-Motion Hip Data-Strap at Left-Rear Hip (X=+0.155..0.176, Y=+0.045..0.058, Z=0.945..0.680)
    st_rings, st_uvs = [], []
    for il in range(14):
        t = il / 13.0
        sx = 0.155 + 0.021 * math.sin(t * math.pi * 0.5)
        sy = 0.045 + 0.013 * t
        sz = 0.945 - 0.265 * t
        w_s = 0.022 * (1.0 - 0.25 * t)
        th_s = 0.0045
        row, ruv = [], []
        for iu in range(8):
            ang = 2.0 * math.pi * iu / 8.0
            row.append(Vector((sx + th_s * math.cos(ang), sy + w_s * math.sin(ang), sz)))
            ruv.append((0.68 + 0.24 * (iu / 8.0), (0.08 + 0.10 * t) if t > 0.78 else (0.30 + 0.25 * t)))
        st_rings.append(row)
        st_uvs.append(ruv)
    builder.add_grid(st_rings, st_uvs, mat_idx=4, part_name="STRAP", closed_u=True, cap_start=True, cap_end=True)

    # 4. Contoured Knee/Shin Armor Guards (weighted to calf_l/r)
    for side_sign, kp in [(-1.0, "KNEE_GUARD_R"), (+1.0, "KNEE_GUARD_L")]:
        kg_grid = []
        xc = side_sign * 0.098
        for iv in range(7):
            tv = iv / 6.0
            z = 0.355 + 0.175 * tv
            rx = 0.058 + 0.008 * math.sin(tv * math.pi)
            ry = 0.068 + 0.008 * math.sin(tv * math.pi)
            row = []
            for iu in range(9):
                ang = -math.pi * 0.80 + (math.pi * 0.60) * (iu / 8.0)  # Front shin/patella shield
                row.append(Vector((xc + rx * math.cos(ang), -0.012 + ry * math.sin(ang), z)))
            kg_grid.append(row)
        add_beveled_shell(builder, kg_grid, 0.010, (0.08, 0.54, 0.42, 0.86), mat_idx=4, part_name=kp)

    # =========================================================================
    # 5. AUTHORED CHARACTER PROPS (M_Props_Tech, mat_idx = 5)
    # =========================================================================

    # PROP A: Integrated Right Wrist Emitter (on dorsal/anterior right cybernetic wrist)
    # Q1 UV: U in [0.04, 0.46], V in [0.54, 0.96]; muzzle lens at (0.25, 0.75)
    em_rings, em_uvs = [], []
    em_stations = [
        (-0.595, 0.022, 0.018),
        (-0.620, 0.028, 0.022),
        (-0.685, 0.028, 0.022),
        (-0.725, 0.025, 0.019),
        (-0.745, 0.020, 0.016),
        (-0.748, 0.014, 0.014),  # Focusing muzzle aperture at (-0.748, -0.028, 1.502)!
    ]
    for ix, (ex, ry, rz) in enumerate(em_stations):
        tx = ix / (len(em_stations) - 1)
        row, ruv = [], []
        for iu in range(16):
            ang = 2.0 * math.pi * iu / 16.0
            # Hexagonal-chamfered tactical barrel housing
            hex_f = 1.0 + 0.06 * math.cos(ang * 6.0)
            row.append(Vector((ex, -0.028 + ry * hex_f * math.cos(ang), 1.502 + rz * hex_f * math.sin(ang))))
            if ix == len(em_stations) - 1:
                ruv.append((0.25 + 0.06 * math.cos(ang), 0.75 + 0.06 * math.sin(ang)))
            else:
                ruv.append((0.05 + 0.40 * (iu / 16.0), 0.54 + 0.40 * tx))
        em_rings.append(row)
        em_uvs.append(ruv)
    builder.add_grid(em_rings, em_uvs, mat_idx=5, part_name="PROP_EMITTER_R", closed_u=True, cap_start=True, cap_end=True)

    # PROP B: Retractable Right Forearm Energy Blade (mounted along ulnar/posterior right forearm +Y)
    # Q2 UV: U in [0.54, 0.96], V in [0.54, 0.96]; glowing plasma cutting edge at V > 0.84!
    # Rail housing (weighted to FOREARM_CYBER_R) + Sliding Blade (weighted to PROP_BLADE_R / blade_r bone!)
    rail_rings, rail_uvs = [], []
    for ix in range(6):
        tx = ix / 5.0
        rx_pos = -0.455 - 0.235 * tx
        row, ruv = [], []
        for iu in range(10):
            ang = 2.0 * math.pi * iu / 10.0
            row.append(Vector((rx_pos, 0.044 + 0.011 * math.cos(ang), 1.468 + 0.014 * math.sin(ang))))
            ruv.append((0.55 + 0.38 * tx, 0.56 + 0.18 * (iu / 10.0)))
        rail_rings.append(row)
        rail_uvs.append(ruv)
    builder.add_grid(rail_rings, rail_uvs, mat_idx=5, part_name="FOREARM_CYBER_R", closed_u=True, cap_start=True, cap_end=True)

    # Sliding Energy Blade (in neutral stowed pose sits compactly along [-0.480 .. -0.715]; extends to -0.96 in melee!)
    bl_rings, bl_uvs = [], []
    bl_stations = [
        (-0.480, 0.008, 0.014),
        (-0.560, 0.010, 0.020),
        (-0.650, 0.011, 0.022),
        (-0.715, 0.008, 0.015),
        (-0.755, 0.002, 0.003),  # Sharp diamond blade tip!
    ]
    for ix, (bx, b_thick, b_height) in enumerate(bl_stations):
        tx = ix / (len(bl_stations) - 1)
        # 6-point diamond blade cross-section: sharp plasma cutting edge at +Y/+Z outer edge (V=0.92), spine at inner edge (V=0.62)
        prof = [
            (0.052 + b_height, 0.000, 0.93),          # Sharp glowing outer plasma edge!
            (0.050 + b_height * 0.45, +b_thick, 0.85),
            (0.046, +b_thick * 0.8, 0.62),            # Metallic spine
            (0.044, 0.000, 0.58),
            (0.046, -b_thick * 0.8, 0.62),
            (0.050 + b_height * 0.45, -b_thick, 0.85),
        ]
        row, ruv = [], []
        for py_o, pz_o, uvv in prof:
            row.append(Vector((bx, py_o, 1.468 + pz_o)))
            ruv.append((0.55 + 0.40 * tx, uvv))
        bl_rings.append(row)
        bl_uvs.append(ruv)
    builder.add_grid(bl_rings, bl_uvs, mat_idx=5, part_name="PROP_BLADE_R", closed_u=True, cap_start=True, cap_end=True)

    # PROP C: Removable Power Cell (seated in Wrist Emitter side breech at (-0.655, -0.052, 1.502), weighted to cell_bone!)
    # Q3 UV: U in [0.06, 0.44], V in [0.06, 0.44]; glowing core window at V in [0.20, 0.32]!
    pc_rings, pc_uvs = [], []
    pc_stations = [
        (-0.618, 0.012, 0.08),
        (-0.625, 0.015, 0.14),  # Knurled grip cap (grasped by left fingers in reload!)
        (-0.642, 0.015, 0.22),  # Glowing plasma charge core window!
        (-0.672, 0.015, 0.30),  # Glowing plasma charge core window!
        (-0.688, 0.014, 0.40),
        (-0.694, 0.010, 0.44),
    ]
    for cx, cr, uvv in pc_stations:
        row, ruv = [], []
        for iu in range(14):
            ang = 2.0 * math.pi * iu / 14.0
            row.append(Vector((cx, -0.052 + cr * math.cos(ang), 1.502 + cr * math.sin(ang))))
            ruv.append((0.10 + 0.30 * (iu / 14.0), uvv))
        pc_rings.append(row)
        pc_uvs.append(ruv)
    builder.add_grid(pc_rings, pc_uvs, mat_idx=5, part_name="PROP_CELL", closed_u=True, cap_start=True, cap_end=True)

    # PROP D: Deployable Tactical Beacon / Micro-Drone (docked on rear-right belt at (-0.105, 0.122, 0.958), weighted to beacon_bone!)
    # Q4 UV: U in [0.54, 0.96], V in [0.04, 0.46]; optical pulse ring at V in [0.21, 0.28]!
    # Built upright in local puck orientation centered at (-0.105, 0.128, 0.958), diameter ~10.4 cm, height ~5.2 cm
    bc_center = Vector((-0.105, 0.128, 0.935))
    bc_stations = [
        (0.000, 0.048, 0.08),  # Flat base pad (plants cleanly on floor Z=0 during deploy!)
        (0.012, 0.054, 0.16),  # Tri-fin stabilizer ring
        (0.024, 0.048, 0.24),  # Glowing optical sensor ring!
        (0.038, 0.038, 0.36),  # Upper chamfered dome
        (0.050, 0.016, 0.44),  # Top emitter cap
    ]
    bc_rings, bc_uvs = [], []
    for dz, br, uvv in bc_stations:
        row, ruv = [], []
        for iu in range(18):
            ang = 2.0 * math.pi * iu / 18.0
            # 3 tactical stabilizer fins every 120 degrees on lower ring
            fin = 0.014 * max(0.0, math.cos(ang * 3.0)) if 0.005 < dz < 0.020 else 0.0
            row.append(Vector((bc_center.x + (br + fin) * math.cos(ang), bc_center.y + (br + fin) * math.sin(ang), bc_center.z + dz)))
            ruv.append((0.55 + 0.40 * (iu / 18.0), uvv))
        bc_rings.append(row)
        bc_uvs.append(ruv)
    builder.add_grid(bc_rings, bc_uvs, mat_idx=5, part_name="PROP_BEACON", closed_u=True, cap_start=True, cap_end=True)


def build_operative_meshes() -> tuple[bpy.types.Object, dict[int, str]]:
    """Builds Operative_LOD0 and returns (lod0_obj, part_id_to_name_map)."""
    mats = create_pbr_materials()
    builder = MeshPartBuilder()

    build_head_and_face(builder)
    build_eyes_teeth_tongue_ears_hair(builder)
    build_torso_and_legs(builder)
    build_arms_and_hands(builder)
    build_armor_and_props(builder)

    # Ensure consistent outward face normals & zero degenerate geometry
    bmesh.ops.recalc_face_normals(builder.bm, faces=builder.bm.faces[:])

    mesh_lod0 = bpy.data.meshes.new("Operative_LOD0_Mesh")
    builder.bm.to_mesh(mesh_lod0)
    builder.bm.free()

    for m in mats:
        mesh_lod0.materials.append(m)

    obj_lod0 = bpy.data.objects.new("Operative_LOD0", mesh_lod0)
    bpy.context.scene.collection.objects.link(obj_lod0)

    # Verify exact standing height Z in [0.000, 1.800] m
    zs = [v.co.z for v in mesh_lod0.vertices]
    z_min, z_max = min(zs), max(zs)
    tri_count = sum(len(p.vertices) - 2 for p in mesh_lod0.polygons)
    print(f"[MeshBuilder] Operative_LOD0: {len(mesh_lod0.vertices)} verts, {tri_count} tris, Z=[{z_min:.4f}, {z_max:.4f}] m")

    return obj_lod0, builder.part_names


def generate_lods(obj_lod0: bpy.types.Object) -> tuple[bpy.types.Object, bpy.types.Object]:
    """
    Creates genuine reduced-resolution LOD1 (<= 40,000 tris, ~50% of LOD0) and LOD2 (<= 20,000 tris, ~25% of LOD0)
    preserving UVs, all 6 materials, symmetry, skin weights, and silhouette!
    Call AFTER skin weights are assigned to Operative_LOD0 so LOD1 & LOD2 inherit clean normalized skinning!
    """
    lods = []
    # Temporarily create a clean duplicate without shape keys so DECIMATE can collapse cleanly while preserving Vertex Groups & UVs
    for lod_idx, ratio, max_tris in [(1, 0.52, 40000), (2, 0.26, 20000)]:
        dup_mesh = obj_lod0.data.copy()
        dup_mesh.name = f"Operative_LOD{lod_idx}_Mesh"
        dup_obj = obj_lod0.copy()
        dup_obj.name = f"Operative_LOD{lod_idx}"
        dup_obj.data = dup_mesh
        bpy.context.scene.collection.objects.link(dup_obj)

        # Remove shape keys on the decimation copy so Blender allows applying Decimate modifier
        if dup_obj.data.shape_keys:
            dup_obj.shape_key_clear()

        # Remove non-deform temporary modifiers before applying Decimate, then restore Armature modifier
        arm_target = None
        for mod in list(dup_obj.modifiers):
            if mod.type == "ARMATURE":
                arm_target = mod.object
            dup_obj.modifiers.remove(mod)

        dec = dup_obj.modifiers.new(name="DecimateLOD", type="DECIMATE")
        dec.decimate_type = "COLLAPSE"
        dec.ratio = ratio
        dec.use_collapse_triangulate = False

        bpy.context.view_layer.objects.active = dup_obj
        bpy.ops.object.modifier_apply(modifier=dec.name)

        # Cap bone weights <= 8 and normalize after decimation (all vertex groups are DEF bones)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=8)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)

        if arm_target is not None:
            arm_mod = dup_obj.modifiers.new(name="Armature", type="ARMATURE")
            arm_mod.object = arm_target
            arm_mod.use_deform_preserve_volume = True

        tri_count = sum(len(p.vertices) - 2 for p in dup_obj.data.polygons)
        assert tri_count <= max_tris, f"LOD{lod_idx} exceeded {max_tris} tris ({tri_count})"
        print(f"[MeshBuilder] Operative_LOD{lod_idx}: {len(dup_obj.data.vertices)} verts, {tri_count} tris (<= {max_tris})")
        lods.append(dup_obj)

    return lods[0], lods[1]


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    build_operative_meshes()
