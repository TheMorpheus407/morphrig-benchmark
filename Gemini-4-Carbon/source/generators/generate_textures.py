#!/usr/bin/env python3
"""
Procedural 2048x2048 PBR Texture Set Generator for MORPHRIG Cyberpunk Operative.
Produces physically interpretable BaseColor, Normal (tangent-space), ORM (R=AO, G=Roughness, B=Metallic),
and Emissive/TeamMask maps for all 6 character/prop material slots, plus Team A (Vanguard Cyan + Diamond Crest)
and Team B (Syndicate Crimson-Amber + Chevron Crest) variants.

Outputs to:
  - source/textures/
  - export/textures/
"""

import math
import shutil
import struct
import zlib
from pathlib import Path
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_TEX_DIR = ROOT_DIR / "source" / "textures"
EXP_TEX_DIR = ROOT_DIR / "export" / "textures"

RES = 2048


def write_png_rgb(path: Path, rgb_uint8: np.ndarray) -> None:
    """Fast pure-Python zlib PNG writer for (H, W, 3) uint8 arrays."""
    h, w, c = rgb_uint8.shape
    assert c == 3
    # Prepend filter byte 0 per scanline
    raw = np.concatenate(
        [np.zeros((h, 1), dtype=np.uint8), rgb_uint8.reshape(h, w * 3)], axis=1
    ).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    compressed = zlib.compress(raw, level=4)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png_bytes)


def fbm_noise(res: int, freqs=(4, 8, 16, 32, 64), seed=42) -> np.ndarray:
    """Tileable multi-octave value/spectral noise in [0, 1]."""
    rng = np.random.default_rng(seed)
    spectrum = np.zeros((res, res // 2 + 1), dtype=np.complex128)
    ky = np.fft.fftfreq(res) * res
    kx = np.fft.rfftfreq(res) * res
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX**2 + KY**2)

    amp_total = np.zeros_like(K)
    for i, f in enumerate(freqs):
        weight = 0.5**i
        band = weight * np.exp(-0.5 * ((K - f) / max(1.5, f * 0.45)) ** 2)
        amp_total += band

    phase = rng.uniform(0, 2 * np.pi, size=spectrum.shape)
    mag = rng.normal(1.0, 0.25, size=spectrum.shape) * amp_total
    spectrum = mag * (np.cos(phase) + 1j * np.sin(phase))
    spectrum[0, 0] = 0.0
    field = np.fft.irfft2(spectrum, s=(res, res))
    fmin, fmax = field.min(), field.max()
    return (field - fmin) / max(1e-8, (fmax - fmin))


def height_to_normal(height: np.ndarray, strength: float = 2.5) -> np.ndarray:
    """Convert [0,1] heightfield to tangent-space RGB uint8 normal map (+X right, +Y up/OpenGL)."""
    dy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    dx = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    nx = -dx * strength
    ny = dy * strength
    nz = np.ones_like(height)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len
    rgb = np.stack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def pack_orm(ao: np.ndarray, rough: np.ndarray, metal: np.ndarray) -> np.ndarray:
    rgb = np.stack([ao, rough, metal], axis=-1)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def to_u8(rgb: np.ndarray) -> np.ndarray:
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def uv_grid(res: int):
    # v=0 at bottom, v=1 at top (image row 0 is v=1)
    u = np.linspace(0.0, 1.0, res, endpoint=False)
    v = np.linspace(1.0, 0.0, res, endpoint=False)
    return np.meshgrid(u, v)


def save_set(prefix: str, base: np.ndarray, norm: np.ndarray, orm: np.ndarray, emis: np.ndarray | None = None):
    write_png_rgb(SRC_TEX_DIR / f"{prefix}_BaseColor.png", base)
    write_png_rgb(SRC_TEX_DIR / f"{prefix}_Normal.png", norm)
    write_png_rgb(SRC_TEX_DIR / f"{prefix}_ORM.png", orm)
    if emis is not None:
        write_png_rgb(SRC_TEX_DIR / f"{prefix}_Emissive.png", emis)


def generate_skin(U: np.ndarray, V: np.ndarray):
    pores = fbm_noise(RES, freqs=(24, 64, 140, 280), seed=101)
    mottle = fbm_noise(RES, freqs=(3, 7, 15), seed=102)

    # Warm olive-tan realistic human skin tone with subsurface warmth zones
    # Head face UV occupies U in [0.0, 0.65], V in [0.25, 1.0]; Organic Left Arm/Hand occupies U in [0.65, 1.0] or V in [0.0, 0.25]
    base_r = 0.73 + 0.04 * (mottle - 0.5) - 0.02 * (pores - 0.5)
    base_g = 0.55 + 0.03 * (mottle - 0.5) - 0.02 * (pores - 0.5)
    base_b = 0.44 + 0.025 * (mottle - 0.5) - 0.015 * (pores - 0.5)

    # Cheek & nasal subsurface warmth zone (centered around face UV U=0.32, V=0.60)
    cheek_l = np.exp(-(((U - 0.21) / 0.08) ** 2 + ((V - 0.58) / 0.07) ** 2))
    cheek_r = np.exp(-(((U - 0.43) / 0.08) ** 2 + ((V - 0.58) / 0.07) ** 2))
    nose_warm = np.exp(-(((U - 0.32) / 0.04) ** 2 + ((V - 0.60) / 0.06) ** 2))
    warmth = np.clip(cheek_l + cheek_r + 0.8 * nose_warm, 0.0, 1.0)
    base_r += 0.065 * warmth
    base_g -= 0.018 * warmth
    base_b -= 0.015 * warmth

    # Natural vermilion lip zone (UV around U=0.32, V=0.445)
    lip_mask = np.exp(-(((U - 0.32) / 0.075) ** 2 + ((V - 0.445) / 0.032) ** 2))
    base_r = base_r * (1.0 - 0.7 * lip_mask) + 0.62 * (0.7 * lip_mask)
    base_g = base_g * (1.0 - 0.7 * lip_mask) + 0.31 * (0.7 * lip_mask)
    base_b = base_b * (1.0 - 0.7 * lip_mask) + 0.30 * (0.7 * lip_mask)

    # Subtle orbital eyelid shadow
    eye_l_sh = np.exp(-(((U - 0.235) / 0.048) ** 2 + ((V - 0.665) / 0.028) ** 2))
    eye_r_sh = np.exp(-(((U - 0.405) / 0.048) ** 2 + ((V - 0.665) / 0.028) ** 2))
    lid_sh = np.clip(eye_l_sh + eye_r_sh, 0.0, 1.0)
    base_r -= 0.08 * lid_sh
    base_g -= 0.07 * lid_sh
    base_b -= 0.05 * lid_sh

    # Subtle cyberpunk dermal gold/platinum circuit inlay along outer cheekbones/temples
    trace_l = (
        (np.abs((U - 0.14) - 0.25 * (V - 0.62)) < 0.0028)
        & (V > 0.56)
        & (V < 0.70)
    )
    trace_r = (
        (np.abs((U - 0.50) + 0.25 * (V - 0.62)) < 0.0028)
        & (V > 0.56)
        & (V < 0.70)
    )
    dermal_trace = (trace_l | trace_r).astype(np.float64)
    base_r = base_r * (1.0 - dermal_trace) + 0.78 * dermal_trace
    base_g = base_g * (1.0 - dermal_trace) + 0.68 * dermal_trace
    base_b = base_b * (1.0 - dermal_trace) + 0.52 * dermal_trace

    height = 0.5 + 0.35 * (pores - 0.5) - 0.25 * dermal_trace + 0.15 * lip_mask * np.sin(U * 420.0)
    norm = height_to_normal(height, strength=1.8)
    ao = np.clip(0.92 - 0.12 * lid_sh + 0.06 * (pores - 0.5), 0.5, 1.0)
    rough = np.clip(0.46 - 0.14 * lip_mask - 0.22 * dermal_trace + 0.08 * (pores - 0.5), 0.18, 0.68)
    metal = np.clip(dermal_trace * 0.85, 0.0, 1.0)

    save_set(
        "Skin",
        to_u8(np.stack([base_r, base_g, base_b], axis=-1)),
        norm,
        pack_orm(ao, rough, metal),
    )


def generate_eyes_mouth(U: np.ndarray, V: np.ndarray):
    """
    Quadrant UV Atlas:
      Q1 Top-Left     U in [0.0, 0.5], V in [0.5, 1.0]: Eyeball (Pupil + Cyber-Teal/Amber Iris + Sclera)
      Q2 Top-Right    U in [0.5, 1.0], V in [0.5, 1.0]: Teeth enamel + interdental grooves
      Q3 Bottom-Left  U in [0.0, 0.5], V in [0.0, 0.5]: Tongue & Gums
      Q4 Bottom-Right U in [0.5, 1.0], V in [0.0, 0.5]: Inner Oral Cavity wall (dark warm shadow)
    """
    noise_fine = fbm_noise(RES, freqs=(16, 48, 128), seed=202)
    r = np.zeros_like(U)
    g = np.zeros_like(U)
    b = np.zeros_like(U)
    ao = np.ones_like(U) * 0.92
    rough = np.ones_like(U) * 0.25
    metal = np.zeros_like(U)
    height = np.ones_like(U) * 0.5

    # Q1: Eyeball centered at (0.25, 0.75)
    q1 = (U < 0.5) & (V >= 0.5)
    dx = (U - 0.25) / 0.25
    dy = (V - 0.75) / 0.25
    rad = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    fibers = 0.5 + 0.5 * np.sin(ang * 44.0 + noise_fine * 3.0)

    # Sclera default
    ey_r = 0.90 - 0.08 * np.clip((rad - 0.45) * 1.1, 0.0, 1.0) + 0.03 * (noise_fine - 0.5)
    ey_g = 0.88 - 0.13 * np.clip((rad - 0.45) * 1.1, 0.0, 1.0)
    ey_b = 0.87 - 0.14 * np.clip((rad - 0.45) * 1.1, 0.0, 1.0)

    # Iris (rad in [0.16, 0.43]) + Limbal ring
    iris_m = np.clip(1.0 - np.abs(rad - 0.295) / 0.145, 0.0, 1.0) > 0.0
    limbal = np.exp(-(((rad - 0.42) / 0.025) ** 2))
    collarette = np.exp(-(((rad - 0.23) / 0.035) ** 2))
    ir_r = 0.10 + 0.18 * fibers + 0.42 * collarette
    ir_g = 0.46 + 0.26 * fibers + 0.18 * collarette
    ir_b = 0.58 + 0.22 * fibers - 0.08 * collarette
    iris_blend = np.clip((0.44 - rad) / 0.03, 0.0, 1.0)
    ey_r = ey_r * (1.0 - iris_blend) + ir_r * iris_blend * (1.0 - 0.75 * limbal)
    ey_g = ey_g * (1.0 - iris_blend) + ir_g * iris_blend * (1.0 - 0.75 * limbal)
    ey_b = ey_b * (1.0 - iris_blend) + ir_b * iris_blend * (1.0 - 0.75 * limbal)

    # Pupil (rad < 0.165)
    pupil_blend = np.clip((0.175 - rad) / 0.02, 0.0, 1.0)
    ey_r *= 1.0 - 0.96 * pupil_blend
    ey_g *= 1.0 - 0.96 * pupil_blend
    ey_b *= 1.0 - 0.95 * pupil_blend

    r = np.where(q1, ey_r, r)
    g = np.where(q1, ey_g, g)
    b = np.where(q1, ey_b, b)
    rough = np.where(q1, 0.05, rough)
    ao = np.where(q1, np.clip(1.0 - 0.25 * np.clip(rad - 0.7, 0.0, 1.0), 0.7, 1.0), ao)
    height = np.where(q1, 0.5 + 0.15 * fibers * iris_blend, height)

    # Q2: Teeth (U >= 0.5, V >= 0.5)
    q2 = (U >= 0.5) & (V >= 0.5)
    tu = (U - 0.5) / 0.5
    tv = (V - 0.5) / 0.5
    tooth_groove = np.exp(-((np.sin(tu * 8.0 * np.pi) / 0.14) ** 2))
    gum_line = np.clip((tv - 0.72) / 0.18, 0.0, 1.0)
    tr = (0.90 - 0.12 * tooth_groove) * (1.0 - gum_line) + 0.68 * gum_line
    tg = (0.88 - 0.15 * tooth_groove) * (1.0 - gum_line) + 0.34 * gum_line
    tb = (0.81 - 0.18 * tooth_groove) * (1.0 - gum_line) + 0.34 * gum_line
    r = np.where(q2, tr, r)
    g = np.where(q2, tg, g)
    b = np.where(q2, tb, b)
    rough = np.where(q2, 0.14 + 0.18 * gum_line, rough)
    ao = np.where(q2, 0.95 - 0.35 * tooth_groove, ao)
    height = np.where(q2, 0.55 - 0.35 * tooth_groove, height)

    # Q3: Tongue & Gums (U < 0.5, V < 0.5)
    q3 = (U < 0.5) & (V < 0.5)
    gu = U / 0.5
    med_groove = np.exp(-(((gu - 0.5) / 0.05) ** 2))
    r = np.where(q3, 0.66 - 0.08 * med_groove + 0.05 * (noise_fine - 0.5), r)
    g = np.where(q3, 0.31 - 0.05 * med_groove + 0.03 * (noise_fine - 0.5), g)
    b = np.where(q3, 0.33 - 0.04 * med_groove + 0.03 * (noise_fine - 0.5), b)
    rough = np.where(q3, 0.24 + 0.08 * noise_fine, rough)
    ao = np.where(q3, 0.86 - 0.20 * med_groove, ao)
    height = np.where(q3, 0.5 + 0.25 * noise_fine - 0.25 * med_groove, height)

    # Q4: Inner Oral Cavity (U >= 0.5, V < 0.5) - naturally shadowed warm interior
    q4 = (U >= 0.5) & (V < 0.5)
    r = np.where(q4, 0.18 + 0.03 * noise_fine, r)
    g = np.where(q4, 0.07 + 0.02 * noise_fine, g)
    b = np.where(q4, 0.08 + 0.02 * noise_fine, b)
    rough = np.where(q4, 0.82, rough)
    ao = np.where(q4, 0.32, ao)

    save_set(
        "EyesMouth",
        to_u8(np.stack([r, g, b], axis=-1)),
        height_to_normal(height, strength=2.2),
        pack_orm(ao, rough, metal),
    )


def generate_hair(U: np.ndarray, V: np.ndarray):
    # Directional anisotropic strand noise along V
    rng = np.random.default_rng(303)
    strands_1 = np.sin(U * 380.0 * np.pi + rng.uniform(0, 6.28)) * 0.5 + 0.5
    strands_2 = np.sin(U * 890.0 * np.pi + 1.7) * 0.5 + 0.5
    clump = fbm_noise(RES, freqs=(8, 24, 64), seed=304)
    strands = 0.50 * strands_1 + 0.35 * strands_2 + 0.15 * clump

    # Deep charcoal-indigo cyberpunk hair with subtle cool-silver tip sheen near V->1
    tip = np.clip((V - 0.55) / 0.45, 0.0, 1.0)
    r = 0.09 + 0.07 * strands + 0.10 * tip * strands
    g = 0.10 + 0.08 * strands + 0.14 * tip * strands
    b = 0.14 + 0.10 * strands + 0.20 * tip * strands

    height = 0.25 + 0.65 * strands
    ao = np.clip(0.62 + 0.34 * strands, 0.4, 1.0)
    rough = np.clip(0.48 - 0.14 * strands, 0.28, 0.65)
    metal = np.full_like(U, 0.04)

    save_set(
        "Hair",
        to_u8(np.stack([r, g, b], axis=-1)),
        height_to_normal(height, strength=3.2),
        pack_orm(ao, rough, metal),
    )


def generate_suit_fabric(U: np.ndarray, V: np.ndarray):
    # Tactical hex-ripstop carbon fabric with contrast flex panels and seam stitching
    micro = fbm_noise(RES, freqs=(12, 36, 96), seed=404)
    # Hexagonal weave pattern
    hx = U * 140.0
    hy = V * 140.0 * 1.1547
    hex_w = 0.5 + 0.25 * np.cos(hx * 2 * np.pi) + 0.25 * np.cos((0.5 * hx + 0.866 * hy) * 2 * np.pi)

    # Ribbed flex joint zone for V in [0.0, 0.28]
    flex_zone = (V < 0.28).astype(np.float64)
    ribs = 0.5 + 0.5 * np.sin(V * 220.0 * np.pi)

    # Contrast slate panel vs deep charcoal undersuit
    panel = ((U > 0.52) & (V >= 0.28)).astype(np.float64)
    seam = ((np.abs(U - 0.52) < 0.004) | (np.abs(V - 0.28) < 0.004)).astype(np.float64)

    base_val = (
        0.13 * (1.0 - panel)
        + 0.22 * panel
        + 0.03 * (hex_w - 0.5) * (1.0 - flex_zone)
        + 0.04 * (ribs - 0.5) * flex_zone
        + 0.02 * (micro - 0.5)
        - 0.05 * seam
    )
    r = base_val * 0.95
    g = base_val * 1.00
    b = base_val * 1.10

    height = (
        0.5
        + 0.22 * hex_w * (1.0 - flex_zone)
        + 0.35 * ribs * flex_zone
        - 0.35 * seam
        + 0.08 * micro
    )
    ao = np.clip(0.88 - 0.28 * seam - 0.12 * (1.0 - ribs) * flex_zone, 0.45, 1.0)
    rough = np.clip(0.68 - 0.14 * panel + 0.08 * hex_w, 0.42, 0.84)
    metal = np.clip(0.06 + 0.08 * panel, 0.0, 0.25)

    save_set(
        "SuitFabric",
        to_u8(np.stack([r, g, b], axis=-1)),
        height_to_normal(height, strength=2.6),
        pack_orm(ao, rough, metal),
    )


def build_crest_mask(U: np.ndarray, V: np.ndarray, variant: str) -> np.ndarray:
    """
    Non-color geometric emblem mask in UV emblem region U in [0.68, 0.92], V in [0.68, 0.92]
    so Team A (Diamond Hollow Crest) and Team B (Double-Chevron Crest) remain distinguishable
    by shape/pattern even in monochrome!
    """
    cx = (U - 0.80) / 0.10
    cy = (V - 0.80) / 0.10
    in_box = (np.abs(cx) < 1.0) & (np.abs(cy) < 1.0)
    if variant == "A":
        # Crisp Diamond Ring + Center Crossbar
        d = np.abs(cx) + np.abs(cy)
        ring = (d > 0.52) & (d < 0.78)
        core = d < 0.24
        return (in_box & (ring | core)).astype(np.float64)
    else:
        # Crisp Double Upward Chevron Bars (distinct silhouette/iconography from Team A)
        chev1 = (np.abs(cy - (0.35 - 0.75 * np.abs(cx))) < 0.13) & (np.abs(cx) < 0.82)
        chev2 = (np.abs(cy - (-0.18 - 0.75 * np.abs(cx))) < 0.13) & (np.abs(cx) < 0.82)
        return (in_box & (chev1 | chev2)).astype(np.float64)


def generate_cyber_armor(U: np.ndarray, V: np.ndarray):
    """
    UV Layout Regions for M_CyberArmor:
      - U in [0.00, 0.62], V in [0.35, 1.00]: Brushed Gunmetal/Titanium Armor Plates (chest, pauldron, boots, cyber-arm outer shell)
      - U in [0.62, 1.00], V in [0.58, 1.00]: Team Crest & High-Contrast Trim Accent Zone (crest centered at 0.80, 0.80)
      - U in [0.00, 0.62], V in [0.00, 0.35]: Dark Carbon-Alloy Cybernetic Forearm Inner Chassis & Finger Joints
      - U in [0.62, 1.00], V in [0.00, 0.58]: Glowing Circuit Seam / Tactical Accent Trim Strip (V in [0.0, 0.22] = emissive conduit)
    """
    brush = fbm_noise(RES, freqs=(6, 28, 110), seed=505)
    # Brushed metal fine horizontal micro-grooves
    micro_brush = 0.5 + 0.5 * np.sin(V * 620.0 * np.pi + brush * 2.0)

    plate_zone = (U < 0.62) & (V >= 0.35)
    chassis_zone = (U < 0.62) & (V < 0.35)
    trim_zone = (U >= 0.62) & (V >= 0.22)
    conduit_zone = (U >= 0.62) & (V < 0.22)

    # Panel bevel grooves inside plate_zone
    grid_x = np.abs(((U * 8.0) % 1.0) - 0.5)
    grid_y = np.abs(((V * 8.0) % 1.0) - 0.5)
    panel_groove = ((grid_x > 0.475) | (grid_y > 0.475)).astype(np.float64) * plate_zone

    height = (
        0.55 * plate_zone
        + 0.35 * chassis_zone
        + 0.60 * trim_zone
        + 0.30 * conduit_zone
        - 0.32 * panel_groove
        + 0.06 * micro_brush
    )
    norm = height_to_normal(height, strength=3.0)
    ao = np.clip(0.92 - 0.38 * panel_groove - 0.10 * chassis_zone, 0.42, 1.0)
    rough = np.clip(
        0.30 * plate_zone
        + 0.48 * chassis_zone
        + 0.26 * trim_zone
        + 0.20 * conduit_zone
        + 0.08 * (brush - 0.5)
        + 0.20 * panel_groove,
        0.16,
        0.72,
    )
    metal = np.clip(
        0.86 * plate_zone + 0.45 * chassis_zone + 0.72 * trim_zone + 0.20 * conduit_zone,
        0.0,
        1.0,
    )
    orm_u8 = pack_orm(ao, rough, metal)

    # Generate Team A (Vanguard Cyan #00D8FF + Diamond Crest) and Team B (Syndicate Crimson-Amber #FF4A1C + Double-Chevron Crest)
    teams = {
        "CyberArmor": ((0.05, 0.78, 0.96), "A"),       # Default = Team A
        "CyberArmor_TeamB": ((0.96, 0.26, 0.10), "B"), # Variant = Team B
    }
    for prefix, (accent_rgb, var_code) in teams.items():
        crest = build_crest_mask(U, V, var_code)
        # Base armor silver-titanium + dark carbon chassis + team trim/crest
        r = (
            (0.34 + 0.05 * micro_brush) * plate_zone
            + (0.14 + 0.03 * brush) * chassis_zone
            + (0.20 * (1.0 - crest) + accent_rgb[0] * crest) * trim_zone
            + accent_rgb[0] * conduit_zone
        ) * (1.0 - 0.45 * panel_groove)
        g = (
            (0.37 + 0.05 * micro_brush) * plate_zone
            + (0.15 + 0.03 * brush) * chassis_zone
            + (0.22 * (1.0 - crest) + accent_rgb[1] * crest) * trim_zone
            + accent_rgb[1] * conduit_zone
        ) * (1.0 - 0.45 * panel_groove)
        b = (
            (0.42 + 0.05 * micro_brush) * plate_zone
            + (0.17 + 0.03 * brush) * chassis_zone
            + (0.25 * (1.0 - crest) + accent_rgb[2] * crest) * trim_zone
            + accent_rgb[2] * conduit_zone
        ) * (1.0 - 0.45 * panel_groove)

        # Emissive strictly in conduit strip + crisp crest outline (moderate, readable, never blowing out geometry!)
        emis_strength = 0.85 * conduit_zone + 0.55 * crest
        emis = np.stack(
            [
                accent_rgb[0] * emis_strength,
                accent_rgb[1] * emis_strength,
                accent_rgb[2] * emis_strength,
            ],
            axis=-1,
        )
        if prefix == "CyberArmor":
            save_set(prefix, to_u8(np.stack([r, g, b], axis=-1)), norm, orm_u8, to_u8(emis))
        else:
            write_png_rgb(SRC_TEX_DIR / f"{prefix}_BaseColor.png", to_u8(np.stack([r, g, b], axis=-1)))
            write_png_rgb(SRC_TEX_DIR / f"{prefix}_Emissive.png", to_u8(emis))

    # Also write an explicit channel-packed TeamMask texture (R=Trim/Conduit, G=TeamA Diamond Crest, B=TeamB Chevron Crest)
    crest_a = build_crest_mask(U, V, "A")
    crest_b = build_crest_mask(U, V, "B")
    mask_rgb = np.stack([conduit_zone.astype(np.float64), crest_a, crest_b], axis=-1)
    write_png_rgb(SRC_TEX_DIR / "CyberArmor_TeamMask.png", to_u8(mask_rgb))


def generate_props_tech(U: np.ndarray, V: np.ndarray):
    """
    UV Quadrant Atlas for M_Props_Tech:
      Q1 Top-Left     U < 0.5, V >= 0.5 : Integrated Wrist Emitter housing & muzzle lens
      Q2 Top-Right    U >= 0.5, V >= 0.5: Forearm Blade spine + crystalline energy cutting edge (V > 0.82 = glowing blade edge)
      Q3 Bottom-Left  U < 0.5, V < 0.5  : Removable Power Cell canister (knurled grip + glowing charge core window V in [0.18, 0.34])
      Q4 Bottom-Right U >= 0.5, V < 0.5 : Deployable Beacon / Micro-Drone chassis + optical ring (V in [0.18, 0.30])
    """
    fine = fbm_noise(RES, freqs=(16, 64, 160), seed=606)
    knurl = 0.5 + 0.5 * np.sin((U + V) * 260.0 * np.pi) * np.sin((U - V) * 260.0 * np.pi)

    q1 = (U < 0.5) & (V >= 0.5)
    q2 = (U >= 0.5) & (V >= 0.5)
    q3 = (U < 0.5) & (V < 0.5)
    q4 = (U >= 0.5) & (V < 0.5)

    muzzle_lens = q1 & (((U - 0.25) ** 2 + (V - 0.75) ** 2) < 0.008)
    blade_edge = q2 & (V > 0.82)
    cell_core = q3 & (V > 0.18) & (V < 0.34) & (U > 0.08) & (U < 0.42)
    cell_grip = q3 & (~cell_core)
    beacon_ring = q4 & (V > 0.20) & (V < 0.29)

    glow_mask = (muzzle_lens | blade_edge | cell_core | beacon_ring).astype(np.float64)

    base_metal = 0.24 + 0.06 * fine
    r = base_metal * (1.0 - glow_mask) + 0.12 * glow_mask
    g = (base_metal + 0.02) * (1.0 - glow_mask) + 0.88 * glow_mask
    b = (base_metal + 0.05) * (1.0 - glow_mask) + 1.00 * glow_mask

    height = (
        0.5
        + 0.30 * knurl * cell_grip.astype(np.float64)
        + 0.20 * blade_edge.astype(np.float64)
        - 0.20 * cell_core.astype(np.float64)
        + 0.08 * fine
    )
    ao = np.clip(0.90 - 0.18 * cell_grip.astype(np.float64) * (1.0 - knurl), 0.5, 1.0)
    rough = np.clip(0.32 * (1.0 - glow_mask) + 0.12 * glow_mask + 0.18 * cell_grip.astype(np.float64), 0.10, 0.65)
    metal = np.clip(0.84 * (1.0 - glow_mask) + 0.15 * glow_mask, 0.0, 1.0)

    emis = np.stack([0.10 * glow_mask, 0.85 * glow_mask, 1.00 * glow_mask], axis=-1)
    save_set(
        "PropsTech",
        to_u8(np.stack([r, g, b], axis=-1)),
        height_to_normal(height, strength=2.8),
        pack_orm(ao, rough, metal),
        to_u8(emis),
    )

    # Team B emissive & basecolor for PropsTech
    r_b = base_metal * (1.0 - glow_mask) + 1.00 * glow_mask
    g_b = (base_metal + 0.02) * (1.0 - glow_mask) + 0.32 * glow_mask
    b_b = (base_metal + 0.05) * (1.0 - glow_mask) + 0.10 * glow_mask
    emis_b = np.stack([1.00 * glow_mask, 0.30 * glow_mask, 0.08 * glow_mask], axis=-1)
    write_png_rgb(SRC_TEX_DIR / "PropsTech_TeamB_BaseColor.png", to_u8(np.stack([r_b, g_b, b_b], axis=-1)))
    write_png_rgb(SRC_TEX_DIR / "PropsTech_TeamB_Emissive.png", to_u8(emis_b))


def main() -> None:
    SRC_TEX_DIR.mkdir(parents=True, exist_ok=True)
    EXP_TEX_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating {RES}x{RES} PBR texture sets in {SRC_TEX_DIR}...")
    U, V = uv_grid(RES)
    generate_skin(U, V)
    generate_eyes_mouth(U, V)
    generate_hair(U, V)
    generate_suit_fabric(U, V)
    generate_cyber_armor(U, V)
    generate_props_tech(U, V)

    for png in sorted(SRC_TEX_DIR.glob("*.png")):
        shutil.copy2(png, EXP_TEX_DIR / png.name)

    files = list(SRC_TEX_DIR.glob("*.png"))
    total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    print(f"Generated {len(files)} texture maps ({total_mb:.2f} MiB compressed PNG on disk) and synced to export/textures/.")


if __name__ == "__main__":
    main()
