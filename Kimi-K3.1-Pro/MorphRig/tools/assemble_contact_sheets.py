#!/usr/bin/env python3
"""Assemble fixed-order inspection sheets from the rendered source checks."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation"
BODY = ["idle_relaxed", "walk_l", "run_fr", "jump_air", "melee_3", "reload", "deploy", "aim_up_left", "victory", "getup_back", "knockdown_front", "prone_back"]
FACE = ["joy", "anger", "concern", "surprise", "pain", "focus", "left_blink", "open_vowel", "rounded_vowel"]


def assemble(names, prefix, columns, tile, destination):
    command = ["ffmpeg", "-y", "-v", "error"]
    for name in names:
        command += ["-i", str(OUT / f"{prefix}_{name}.png")]
    filters = []
    for index in range(len(names)):
        filters.append(f"[{index}:v]scale={tile}:{tile}:force_original_aspect_ratio=decrease,pad={tile}:{tile}:(ow-iw)/2:(oh-ih)/2:color=0x202830[v{index}]")
    layout = "|".join(f"{(i % columns) * tile}_{(i // columns) * tile}" for i in range(len(names)))
    filters.append("".join(f"[v{i}]" for i in range(len(names))) + f"xstack=inputs={len(names)}:layout={layout}[sheet]")
    command += ["-filter_complex", ";".join(filters), "-map", "[sheet]", "-frames:v", "1", str(OUT / destination)]
    subprocess.run(command, check=True)


assemble(BODY, "pose", 4, 320, "motion_contact_sheet.png")
assemble(FACE, "face", 3, 320, "face_contact_sheet.png")
print("Inspection sheets assembled")
