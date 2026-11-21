"""Test setup: put the terrain copy and the voxel toolkit on sys.path.

``skills/terrain-shape/tools`` holds the ``terrain`` package (Chapman's toolkit,
minus his placer and harness output). ``skills/design-monument/tools`` holds
``voxel``, which the copy never imports on the Ashlar path.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for tools in (REPO / "skills" / "design-monument" / "tools",
              REPO / "skills" / "terrain-shape" / "tools"):
    sys.path.insert(0, str(tools))
