"""The terrain copy carries no Chapman placement path and ships its licence and readme."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COPY = REPO / "skills" / "terrain-shape" / "tools" / "terrain"
GONE = ("emit_plan_toon", "place_terrain", "from voxel", "import voxel",
        "to_voxel_model", "write_terrain_fills", "TerrainLayers")


def test_copy_has_no_chapman_placement_paths():
    hits = [f"{p.relative_to(REPO)}: {word}" for p in COPY.rglob("*.py")
            for word in GONE if word in p.read_text(encoding="utf-8")]
    assert not hits, hits


def test_copy_has_license_and_readme():
    assert "MIT License" in (COPY / "LICENSE").read_text(encoding="utf-8")
    assert "ashlar_emit" in (COPY / "README.md").read_text(encoding="utf-8")
