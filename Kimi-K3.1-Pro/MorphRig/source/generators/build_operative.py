"""Reproducible source build; run with Blender --background --factory-startup -P this_file."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from character import build

if __name__ == "__main__":
    asset = build()
    if "--model-only" not in sys.argv:
        from animate import build_animation_inventory
        build_animation_inventory(asset)
    print("OPERATIVE_SOURCE_READY", str(ROOT / "source" / "Operative.blend"), flush=True)
