"""The terrain copy carries no Chapman placement path and ships its licence and readme."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COPY = REPO / "skills" / "terrain-shape" / "tools" / "terrain"
GONE = ("emit_plan_toon", "place_terrain", "from voxel", "import voxel",
        "to_voxel_model", "write_terrain_fills", "TerrainLayers")


def test_copy_has_no_chapman_placement_paths():
    hits = []
    for path in COPY.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if path == COPY / "forms.py":
            # Form authoring shares the design-monument grid and palette.
            source = source.replace("\nfrom voxel import Palette, VoxelModel\n", "\n", 1)
        elif path == COPY / "trees.py":
            # Tree previews share the palette, grid and offline PNG renderer.
            source = source.replace("\nfrom voxel import Palette, VoxelModel, render_views\n", "\n", 1)
        hits.extend(f"{path.relative_to(REPO)}: {word}" for word in GONE if word in source)
    assert not hits, hits


def test_copy_has_license_and_readme():
    assert "MIT License" in (COPY / "LICENSE").read_text(encoding="utf-8")
    assert "ashlar_emit" in (COPY / "README.md").read_text(encoding="utf-8")
