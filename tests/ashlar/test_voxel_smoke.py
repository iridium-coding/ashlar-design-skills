"""Smoke test for the vendored voxel toolkit plus the placer's plan command."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("PIL")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills" / "design-monument" / "tools"))
PLACER = REPO / "skills" / "exec-ashlar" / "scripts" / "ashlar_place.py"


def test_tiny_model_renders_and_plans(tmp_path):
    from voxel import Palette, VoxelModel, render_views, write_fills_json

    palette = Palette.building()
    model = VoxelModel(nx=6, ny=4, nz=5, palette=palette)
    model.box((0, 0, 0), (5, 0, 4), palette.code("stone"))
    model.box((1, 1, 1), (4, 3, 3), palette.code("oak_planks"))
    paths = render_views(model, str(tmp_path / "tiny"))
    assert len(paths) == 3 and all(Path(p).stat().st_size > 0 for p in paths)
    fills = tmp_path / "tiny_fills.json"
    summary = write_fills_json(model, str(fills), origin=(100, 64, 100))
    assert summary["fills"] >= 2
    proc = subprocess.run([sys.executable, str(PLACER), "plan", str(fills)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["cells"] == summary["solid_voxels"]
