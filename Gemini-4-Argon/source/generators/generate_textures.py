#!/usr/bin/env python3
"""
Procedural PBR Texture Generator for MorphRig Cyberpunk Operative ("Vex").
Generates physically interpretable BaseColor (_D), Roughness (_R), Metallic (_M),
Tangent-Space Normal (_N), Emissive (_E), and UE-packed OcclusionRoughnessMetallic (_ORM)
textures for all 6 character material slots, including Team A and Team B accent variants
with distinct geometric crest icons and border patterns (not color alone).

All textures are deterministic, <= 4096x4096 (2048x2048 and 1024x1024), and written to
both source/textures/ and export/textures/ (hardlinked/synced to avoid disk bloat).
"""

import json
import math
import os
import shutil
import struct
import zlib
from pathlib import Path

try:
    import numpy as np
except ImportError:
    raise RuntimeError("Run with Blender python or system python with numpy available.")


def write_png_rgb_or_rgba(path: Path, arr: "np.ndarray"):
    """Fast deterministic PNG writer using numpy + zlib (no Pillow dependency needed)."""
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    h, w, c = arr.shape
    if c == 3:
        color_type = 2  # RGB
    elif c == 4:
        color_type = 6  # RGBA
    else:
        raise ValueError(f"Unsupported channel count {c}")

    # Prepend filter byte 0 to each scanline
    filter_col = np.zeros((h, 1), dtype=np.uint8)
    scanlines = np.hstack([filter_col, arr.reshape(h, w * c)])
    raw_bytes = scanlines.tobytes()
    compressed = zlib.compress(raw_bytes, level=6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    png_data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png_data)


def height_to_normal(height_map: "np.ndarray", strength: float = 3.0) -> "np.ndarray":
    """Convert a float [0,1] height map into an RGB [0..255] tangent-space normal map."""
    dy, dx = np.gradient(height_map.astype(np.float32))
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz + 1e-8)
    nx /= norm
    ny /= norm
    nz /= norm
    rgb = np.stack(
        [
            (nx * 0.5 + 0.5) * 255.0,
            (ny * 0.5 + 0.5) * 255.0,
            (nz * 0.5 + 0.5) * 255.0,
        ],
        axis=-1,
    )
    return np.clip(rgb, 0, 255).astype(np.uint8)


def save_material_set(
    out_dirs,
    prefix: str,
    base_color: "np.ndarray",
    roughness: "np.ndarray",
    metallic: "np.ndarray",
    ao: "np.ndarray",
    normal: "np.ndarray",
    emissive: "np.ndarray",
):
    h, w, _ = base_color.shape
    r_rgb = np.repeat(np.clip(roughness * 255.0, 0, 255).astype(np.uint8)[..., None], 3, axis=-1)
    m_rgb = np.repeat(np.clip(metallic * 255.0, 0, 255).astype(np.uint8)[..., None], 3, axis=-1)
    orm_rgb = np.stack(
        [
            np.clip(ao * 255.0, 0, 255).astype(np.uint8),
            np.clip(roughness * 255.0, 0, 255).astype(np.uint8),
            np.clip(metallic * 255.0, 0, 255).astype(np.uint8),
        ],
        axis=-1,
    )

    files = {
        f"{prefix}_D.png": base_color,
        f"{prefix}_R.png": r_rgb,
        f"{prefix}_M.png": m_rgb,
        f"{prefix}_ORM.png": orm_rgb,
        f"{prefix}_N.png": normal,
        f"{prefix}_E.png": emissive,
    }
    primary_dir = out_dirs[0]
    for fname, img in files.items():
        src_p = primary_dir / fname
        write_png_rgb_or_rgba(src_p, img)
        for extra_dir in out_dirs[1:]:
            dst_p = extra_dir / fname
            if dst_p.exists():
                dst_p.unlink()
            try:
                os.link(src_p, dst_p)
            except OSError:
                shutil.copy2(src_p, dst_p)
    return list(files.keys()), (w, h)


def generate_skin_textures(size: int = 1024):
    """
    M_Operative_Skin:
    UV Quadrants:
      - Top-Left & Top-Right (V: 0.25..1.0): Face, neck, ears, organic left forearm & hand
        Warm olive-tan human complexion, subtle cheek/nose blush, brow/lip tone variation,
        cybernetic sub-dermal temple seam lines, fine skin pore micro-normal.
      - Bottom-Left (U: 0.0..0.5, V: 0.0..0.25): Inner mouth cavity & articulated tongue
      - Bottom-Right (U: 0.5..1.0, V: 0.0..0.25): Upper & lower teeth enamel
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    # Deterministic procedural pore noise
    pore1 = np.sin(x * 380.0) * np.cos(y * 380.0)
    pore2 = np.sin((x + y) * 620.0) * np.sin((x - y) * 540.0)
    pores = 0.5 + 0.25 * pore1 + 0.25 * pore2

    base = np.zeros((size, size, 3), dtype=np.float32)
    # Default warm human skin tone (sRGB ~ [208, 158, 134])
    base[..., 0] = 206.0 + 10.0 * (pores - 0.5)
    base[..., 1] = 156.0 + 8.0 * (pores - 0.5)
    base[..., 2] = 132.0 + 6.0 * (pores - 0.5)

    # Subtle subsurface blush around mid-cheek region (in image space y = 1 - V; cheeks are at V ~ 0.62 => y ~ 0.38)
    blush = np.exp(-((x - 0.5) ** 2 / 0.05 + (y - 0.38) ** 2 / 0.015))
    base[..., 0] += 18.0 * blush
    base[..., 1] -= 6.0 * blush
    base[..., 2] -= 4.0 * blush

    # Lip vermilion rose tint (lips are around V ~ 0.45 => image y = 1 - 0.45 = 0.55, U ~ 0.44..0.56)
    lip_mask = np.exp(-((x - 0.5) ** 2 / 0.0035 + (y - 0.55) ** 2 / 0.0012))
    base[..., 0] = base[..., 0] * (1.0 - 0.55 * lip_mask) + 176.0 * (0.55 * lip_mask)
    base[..., 1] = base[..., 1] * (1.0 - 0.55 * lip_mask) + 88.0 * (0.55 * lip_mask)
    base[..., 2] = base[..., 2] * (1.0 - 0.55 * lip_mask) + 92.0 * (0.55 * lip_mask)

    # Subtle brow & upper-lash shadow (brows are at V ~ 0.76 => image y = 0.24)
    brow_mask = np.exp(-((y - 0.24) ** 2 / 0.0005)) * ((x > 0.36) & (x < 0.64)).astype(np.float32)
    base *= 1.0 - 0.22 * brow_mask[..., None]

    # Bottom-left UV quadrant (y > 0.78, x < 0.5 in image space => V < 0.22): Inner mouth & tongue
    mouth_mask = (y > 0.78) & (x < 0.50)
    base[mouth_mask, 0] = 148.0 + 12.0 * pores[mouth_mask]
    base[mouth_mask, 1] = 64.0 + 6.0 * pores[mouth_mask]
    base[mouth_mask, 2] = 72.0 + 6.0 * pores[mouth_mask]

    # Bottom-right UV quadrant (y > 0.78, x >= 0.50): Teeth enamel
    teeth_mask = (y > 0.78) & (x >= 0.50)
    tooth_grooves = np.abs(np.sin(x * 96.0 * math.pi))
    base[teeth_mask, 0] = 232.0 + 12.0 * tooth_grooves[teeth_mask]
    base[teeth_mask, 1] = 226.0 + 12.0 * tooth_grooves[teeth_mask]
    base[teeth_mask, 2] = 212.0 + 10.0 * tooth_grooves[teeth_mask]

    # Cyberpunk temple neural seam lines on face (subtle metallic trace)
    seam_l = np.exp(-((np.abs(x - 0.24) * 180.0) ** 2)) * ((y > 0.35) & (y < 0.68)).astype(np.float32)
    seam_r = np.exp(-((np.abs(x - 0.76) * 180.0) ** 2)) * ((y > 0.35) & (y < 0.68)).astype(np.float32)
    seam = np.clip(seam_l + seam_r, 0.0, 1.0)
    base[..., 0] = base[..., 0] * (1.0 - seam) + 55.0 * seam
    base[..., 1] = base[..., 1] * (1.0 - seam) + 185.0 * seam
    base[..., 2] = base[..., 2] * (1.0 - seam) + 210.0 * seam

    roughness = np.full((size, size), 0.46, dtype=np.float32) - 0.08 * lip_mask + 0.05 * (pores - 0.5)
    roughness[mouth_mask] = 0.24
    roughness[teeth_mask] = 0.16
    metallic = np.clip(seam * 0.85, 0.0, 1.0).astype(np.float32)
    ao = np.full((size, size), 0.94, dtype=np.float32) - 0.15 * seam
    ao[mouth_mask] = 0.72

    height = 0.5 + 0.12 * (pores - 0.5) - 0.35 * seam
    height[teeth_mask] = 0.5 + 0.25 * tooth_grooves[teeth_mask]
    normal = height_to_normal(height, strength=2.2)

    emissive = np.zeros((size, size, 3), dtype=np.uint8)
    emissive[..., 0] = np.clip(seam * 20.0, 0, 255).astype(np.uint8)
    emissive[..., 1] = np.clip(seam * 180.0, 0, 255).astype(np.uint8)
    emissive[..., 2] = np.clip(seam * 230.0, 0, 255).astype(np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def generate_eye_textures(size: int = 1024):
    """
    M_Operative_Eyes:
    Radial eyeball map centered at (0.5, 0.5):
      - r < 0.13: Deep black pupil
      - 0.13 <= r < 0.32: Cyber-amber/teal radial iris fibers with limbal ring & HUD reticle ring
      - r >= 0.32: Clean sclera with subtle peripheral capillaries
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    dx = x - 0.5
    dy = y - 0.5
    r = np.sqrt(dx * dx + dy * dy)
    theta = np.arctan2(dy, dx)

    base = np.full((size, size, 3), 238.0, dtype=np.float32)
    # Sclera subtle veins
    veins = np.clip(np.sin(theta * 18.0 + r * 25.0) * np.cos(theta * 11.0), 0.0, 1.0) * np.clip((r - 0.34) * 2.2, 0.0, 1.0)
    base[..., 0] -= 8.0 * veins
    base[..., 1] -= 26.0 * veins
    base[..., 2] -= 24.0 * veins

    # Iris (0.12 .. 0.31)
    iris_mask = (r >= 0.11) & (r <= 0.31)
    fibers = 0.5 + 0.5 * np.sin(theta * 48.0 + np.sin(r * 60.0) * 2.0)
    radial_grad = np.clip((r - 0.11) / 0.20, 0.0, 1.0)
    iris_r = 35.0 + 75.0 * fibers + 40.0 * (1.0 - radial_grad)
    iris_g = 155.0 + 75.0 * fibers
    iris_b = 195.0 + 50.0 * fibers
    # Limbal dark outer ring
    limbal = np.exp(-((r - 0.30) ** 2) / 0.00035)
    iris_r *= 1.0 - 0.72 * limbal
    iris_g *= 1.0 - 0.72 * limbal
    iris_b *= 1.0 - 0.72 * limbal

    base[iris_mask, 0] = iris_r[iris_mask]
    base[iris_mask, 1] = iris_g[iris_mask]
    base[iris_mask, 2] = iris_b[iris_mask]

    # Pupil (r < 0.115)
    pupil_mask = r < 0.115
    base[pupil_mask] = 10.0

    # Cybernetic gold ring at r == 0.21
    ring = np.exp(-((r - 0.21) ** 2) / 0.00008)
    base[..., 0] = np.clip(base[..., 0] + 220.0 * ring, 0, 255)
    base[..., 1] = np.clip(base[..., 1] + 185.0 * ring, 0, 255)
    base[..., 2] = np.clip(base[..., 2] + 60.0 * ring, 0, 255)

    roughness = np.full((size, size), 0.08, dtype=np.float32)  # wet cornea gloss
    metallic = np.clip(ring * 0.6, 0.0, 1.0).astype(np.float32)
    ao = np.clip(1.0 - 0.25 * np.clip((r - 0.38) * 1.5, 0.0, 1.0), 0.7, 1.0).astype(np.float32)
    height = 0.5 + 0.15 * fibers * iris_mask.astype(np.float32)
    normal = height_to_normal(height, strength=1.5)

    emissive = np.zeros((size, size, 3), dtype=np.uint8)
    emissive[..., 0] = np.clip(ring * 190.0 + iris_mask.astype(np.float32) * 15.0, 0, 255).astype(np.uint8)
    emissive[..., 1] = np.clip(ring * 150.0 + iris_mask.astype(np.float32) * 55.0, 0, 255).astype(np.uint8)
    emissive[..., 2] = np.clip(ring * 40.0 + iris_mask.astype(np.float32) * 75.0, 0, 255).astype(np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def generate_suit_textures(size: int = 1024):
    """
    M_Operative_Suit:
    Tactical dark graphite/slate cyberpunk bodysuit with micro-hex ripstop weave,
    reinforced seam piping, and flex-ribbed joint panels.
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    weave_x = np.sin(x * 240.0 * math.pi)
    weave_y = np.sin(y * 240.0 * math.pi)
    weave = 0.5 + 0.25 * weave_x * weave_y + 0.25 * np.cos((x + y) * 180.0 * math.pi)

    # Diagonal tactical ribs in alternate bands
    ribs = 0.5 + 0.5 * np.sin((x * 28.0 + y * 28.0) * math.pi)
    panel_seams = np.exp(-((np.sin(x * 8.0 * math.pi)) ** 2) * 90.0) + np.exp(-((np.sin(y * 8.0 * math.pi)) ** 2) * 90.0)
    panel_seams = np.clip(panel_seams, 0.0, 1.0)

    base = np.zeros((size, size, 3), dtype=np.float32)
    val = 38.0 + 14.0 * weave + 8.0 * ribs - 16.0 * panel_seams
    base[..., 0] = val * 0.92
    base[..., 1] = val * 0.98
    base[..., 2] = val * 1.12  # cool dark slate-blue tint

    roughness = np.clip(0.58 + 0.14 * weave - 0.12 * panel_seams, 0.25, 0.85).astype(np.float32)
    metallic = np.clip(0.12 + 0.25 * panel_seams, 0.0, 1.0).astype(np.float32)
    ao = np.clip(0.95 - 0.30 * panel_seams, 0.5, 1.0).astype(np.float32)
    height = 0.5 + 0.18 * weave + 0.15 * ribs - 0.35 * panel_seams
    normal = height_to_normal(height, strength=3.2)
    emissive = np.zeros((size, size, 3), dtype=np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def generate_armor_textures(size: int = 1024):
    """
    M_Operative_Armor:
    Hard composite carbon-titanium armor plates (chest rig, shoulder pauldrons,
    knee/shin guards, high collar, boot plating) with beveled panel grooves,
    wear edge highlights, and subtle status indicator slits.
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    hex_u = np.sin(x * 160.0 * math.pi) * np.sin((y * 160.0 + 0.5) * math.pi)
    grid_x = np.abs(((x * 6.0) % 1.0) - 0.5) * 2.0
    grid_y = np.abs(((y * 6.0) % 1.0) - 0.5) * 2.0
    groove = ((grid_x > 0.92) | (grid_y > 0.92)).astype(np.float32)
    bevel_edge = (((grid_x > 0.86) & (grid_x <= 0.92)) | ((grid_y > 0.86) & (grid_y <= 0.92))).astype(np.float32)

    base = np.zeros((size, size, 3), dtype=np.float32)
    base[..., 0] = 64.0 + 8.0 * hex_u + 34.0 * bevel_edge - 36.0 * groove
    base[..., 1] = 70.0 + 8.0 * hex_u + 38.0 * bevel_edge - 38.0 * groove
    base[..., 2] = 82.0 + 10.0 * hex_u + 44.0 * bevel_edge - 42.0 * groove

    roughness = np.clip(0.32 + 0.08 * hex_u - 0.10 * bevel_edge + 0.25 * groove, 0.15, 0.85).astype(np.float32)
    metallic = np.clip(0.78 + 0.15 * bevel_edge - 0.40 * groove, 0.1, 0.98).astype(np.float32)
    ao = np.clip(0.96 - 0.45 * groove, 0.4, 1.0).astype(np.float32)
    height = 0.5 + 0.08 * hex_u + 0.18 * bevel_edge - 0.45 * groove
    normal = height_to_normal(height, strength=4.0)
    emissive = np.zeros((size, size, 3), dtype=np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def generate_cyberarm_textures(size: int = 1024):
    """
    M_Operative_CyberArm:
    Right cybernetic forearm, articulated mechanical fingers, integrated wrist emitter,
    and retractable forearm energy-blade. Gunmetal titanium housing, anodized bronze
    actuator rings, glowing fiber-optic conduit traces, and high-energy plasma edge along V > 0.80.
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    seg_x = np.abs(((x * 10.0) % 1.0) - 0.5) * 2.0
    seg_y = np.abs(((y * 10.0) % 1.0) - 0.5) * 2.0
    seam = ((seg_x > 0.90) | (seg_y > 0.90)).astype(np.float32)

    #Glowing circuit trace channels
    trace = (
        (np.abs(((x * 10.0) % 1.0) - 0.5) < 0.035)
        & (((y * 20.0) % 1.0) > 0.15)
    ).astype(np.float32)

    # Energy blade edge band (top band of UV: y < 0.18 in image coordinates)
    blade_edge = np.clip((0.18 - y) / 0.18, 0.0, 1.0)
    # Copper/bronze actuator band (0.72 < y < 0.84)
    actuator_band = ((y > 0.72) & (y < 0.84)).astype(np.float32)

    base = np.zeros((size, size, 3), dtype=np.float32)
    base[..., 0] = 88.0 - 45.0 * seam + 95.0 * actuator_band + 150.0 * blade_edge
    base[..., 1] = 96.0 - 48.0 * seam + 52.0 * actuator_band + 235.0 * blade_edge + 180.0 * trace
    base[..., 2] = 110.0 - 52.0 * seam + 12.0 * actuator_band + 255.0 * blade_edge + 220.0 * trace

    roughness = np.clip(0.24 + 0.28 * seam - 0.14 * blade_edge, 0.08, 0.75).astype(np.float32)
    metallic = np.clip(0.88 - 0.35 * seam - 0.30 * trace, 0.2, 0.98).astype(np.float32)
    ao = np.clip(0.96 - 0.45 * seam, 0.45, 1.0).astype(np.float32)
    height = 0.5 - 0.45 * seam - 0.20 * trace + 0.20 * actuator_band
    normal = height_to_normal(height, strength=4.2)

    emissive = np.zeros((size, size, 3), dtype=np.uint8)
    em_glow = np.clip(trace * 0.85 + blade_edge * 1.0, 0.0, 1.0)
    emissive[..., 0] = np.clip(em_glow * 40.0, 0, 255).astype(np.uint8)
    emissive[..., 1] = np.clip(em_glow * 225.0, 0, 255).astype(np.uint8)
    emissive[..., 2] = np.clip(em_glow * 255.0, 0, 255).astype(np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def generate_props_accent_textures(size: int = 1024, team: str = "TeamA"):
    """
    M_Operative_Props_Accent:
    Shared material for team-accent trim strips, shoulder crest badge, removable power cell,
    and deployable beacon/drone prop.
    - TeamA: Electric Cyan (#00E5FF) + Hexagonal Triple-Chevron Icon + Continuous Double-Line Outline
    - TeamB: Solar Amber/Crimson (#FF5500) + Crossed-Diamond Strike Icon + Segmented Notch Outline
    Distinguishable by icon geometry and border pattern even in monochrome!
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    dx = (x - 0.5) * 2.0
    dy = (y - 0.5) * 2.0
    r = np.sqrt(dx * dx + dy * dy)

    if team == "TeamA":
        accent_rgb = np.array([0.0, 229.0, 255.0], dtype=np.float32)
        # Hexagonal distance metric + triple chevron stripes inside badge
        hex_d = np.maximum(np.abs(dx), 0.5 * np.abs(dx) + 0.8660254 * np.abs(dy))
        outer_border = ((hex_d > 0.72) & (hex_d < 0.80)) | ((hex_d > 0.84) & (hex_d < 0.89))
        chevron = (
            (hex_d < 0.62)
            & (np.abs((dy + 0.45 * np.abs(dx)) * 5.0 % 1.0 - 0.5) < 0.24)
        )
        pattern_mask = (outer_border | chevron).astype(np.float32)
    else:
        accent_rgb = np.array([255.0, 88.0, 16.0], dtype=np.float32)
        # Diamond / Manhattan metric + crossed X-strike + dashed perimeter notches
        dia_d = np.abs(dx) + np.abs(dy)
        angle = np.arctan2(dy, dx)
        dashed_ring = (dia_d > 0.72) & (dia_d < 0.86) & (np.sin(angle * 16.0) > -0.1)
        x_strike = (dia_d < 0.62) & ((np.abs(dx - dy) < 0.11) | (np.abs(dx + dy) < 0.11))
        center_core = r < 0.22
        pattern_mask = (dashed_ring | x_strike | center_core).astype(np.float32)

    # Also add horizontal energy cell core bands near top/bottom for the power cell & beacon
    cell_bands = ((y < 0.16) | (y > 0.84)) & (np.sin(x * 24.0 * math.pi) > -0.25)
    active = np.clip(pattern_mask + cell_bands.astype(np.float32), 0.0, 1.0)

    base = np.zeros((size, size, 3), dtype=np.float32)
    for c in range(3):
        base[..., c] = 36.0 * (1.0 - active) + accent_rgb[c] * active

    roughness = (0.38 * (1.0 - active) + 0.14 * active).astype(np.float32)
    metallic = (0.72 * (1.0 - active) + 0.35 * active).astype(np.float32)
    ao = np.full((size, size), 0.94, dtype=np.float32)
    height = 0.5 + 0.30 * active
    normal = height_to_normal(height, strength=3.5)

    emissive = np.zeros((size, size, 3), dtype=np.uint8)
    for c in range(3):
        emissive[..., c] = np.clip(active * accent_rgb[c], 0, 255).astype(np.uint8)

    return np.clip(base, 0, 255).astype(np.uint8), roughness, metallic, ao, normal, emissive


def main():
    repo_root = Path(__file__).resolve().parents[2]
    src_tex = repo_root / "source" / "textures"
    exp_tex = repo_root / "export" / "textures"
    src_tex.mkdir(parents=True, exist_ok=True)
    exp_tex.mkdir(parents=True, exist_ok=True)
    out_dirs = [src_tex, exp_tex]

    manifest = {}
    generators = [
        ("T_Operative_Skin", generate_skin_textures(1024)),
        ("T_Operative_Eyes", generate_eye_textures(1024)),
        ("T_Operative_Suit", generate_suit_textures(1024)),
        ("T_Operative_Armor", generate_armor_textures(1024)),
        ("T_Operative_CyberArm", generate_cyberarm_textures(1024)),
        ("T_Operative_Props_Accent_TeamA", generate_props_accent_textures(1024, "TeamA")),
        ("T_Operative_Props_Accent_TeamB", generate_props_accent_textures(1024, "TeamB")),
    ]

    for prefix, data in generators:
        fnames, dims = save_material_set(out_dirs, prefix, *data)
        manifest[prefix] = {"resolution": list(dims), "files": fnames}
        print(f"Generated {prefix}: {len(fnames)} maps at {dims[0]}x{dims[1]}")

    (src_tex / "texture_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
