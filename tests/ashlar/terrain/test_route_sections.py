from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from sitegen import make_heights
from terrain import route
from terrain import transit_design as td

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills" / "terrain-shape" / "scripts" / "terrain.py"


def _design_data(length, **extra):
    data = {"element": "north-line", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, None, 10]}, "to": {"at": [length - 1, None, 10]}, "heights": "heights.json"}
    data.update(extra)
    return data


def _write_heights(project, length, top_bump=None):
    nx, nz = length + 60, 41
    top = np.full((nx, nz), 64.0)
    if top_bump is not None:
        x, z, y = top_bump
        top[x + 30, z + 20] = y
    project.mkdir(parents=True, exist_ok=True)
    make_heights(project / "heights.json", (-30, -20), np.full((nx, nz), 64.0), top=top)


def _planned(tmp_path, *, length, top_bump=None):
    _write_heights(tmp_path, length, top_bump)
    design = td.parse_line(_design_data(length), tmp_path)
    grid = route.load_grid(design.heights)
    return route.plan_route(design, grid)


def _project_with_heights(tmp_path):
    project = tmp_path / "proj"
    _write_heights(project, 150)
    (project / "terrain").mkdir()
    (project / "terrain" / "north-line.line.json").write_text(json.dumps(_design_data(150)), encoding="utf-8")
    return project


def test_sections_split_every_length_cells_and_cover_the_corridor(tmp_path):
    r = _planned(tmp_path, length=250)
    assert [s.name for s in r.sections] == ["s01", "s02", "s03"]
    assert [(s.start, s.end) for s in r.sections] == [(0, 95), (96, 191), (192, 249)]
    for s in r.sections:
        x1, _, z1, x2, _, z2 = s.box
        assert all(x1 + 8 <= x <= x2 - 8 and z1 + 8 <= z <= z2 - 8 for x, z in r.cells[s.start:s.end + 1])


def test_section_box_reaches_below_ground_and_above_the_tallest_top(tmp_path):
    r = _planned(tmp_path, length=120, top_bump=(60, 4, 90))
    box = r.sections[0].box
    assert box[1] <= 64 - 6 and box[4] >= 92


def test_route_json_round_trips(tmp_path):
    r = _planned(tmp_path, length=120)
    route.write_route(r, tmp_path / "r.json")
    assert route.load_route(tmp_path / "r.json") == r
    assert len(r.design_hash) == 12


def test_design_hash_ignores_style_but_not_limits(tmp_path):
    a = td.parse_line(_design_data(100), tmp_path)
    b = td.parse_line(_design_data(100, style="wood"), tmp_path)
    c = td.parse_line(_design_data(100, limits={"max_cut": 3}), tmp_path)
    assert route.design_hash(a) == route.design_hash(b) != route.design_hash(c)


def test_design_hash_covers_heights_tunnels_sections_and_dimension(tmp_path):
    _write_heights(tmp_path, 100)
    base = route.design_hash(td.parse_line(_design_data(100), tmp_path))
    for extra in ({"tunnels": {"width": 4}}, {"sections": {"length": 50}}, {"heights": "other.json"},
                  {"dimension": "nether", "from": {"at": [0, 65, 10]}, "to": {"at": [99, 65, 10]}}):
        assert route.design_hash(td.parse_line(_design_data(100, **extra), tmp_path)) != base, extra
    _write_heights(tmp_path, 100, top_bump=(10, 0, 90))           # the same file, new content
    assert route.design_hash(td.parse_line(_design_data(100), tmp_path)) != base


def test_route_command_writes_route_report_previews_and_reads(tmp_path):
    project = _project_with_heights(tmp_path)
    out = subprocess.run([sys.executable, str(LAUNCHER), "route", str(project / "terrain/north-line.line.json"),
                          "--project", str(project)], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert (project / "terrain/north-line.route.json").exists()
    assert (project / "terrain/north-line.route-report.json").exists()
    assert (project / "terrain/previews/north-line-profile.png").exists()
    assert (project / "terrain/previews/north-line-route.png").exists()
    assert data["report"]["reads"][0]["out"] == "site/north-line-s01"
    assert data["report"]["length"] == 150


def test_section_floor_reaches_the_lowest_ground_under_the_box(tmp_path):
    from sitegen import make_site
    from terrain import corridor

    length = 40
    nx, nz = length + 60, 41
    ground = np.full((nx, nz), 64.0)
    ground[:, 36:39] = 50.0                     # a trench at z 16-18, under the box margin only
    make_heights(tmp_path / "heights.json", (-30, -20), ground)
    design = td.parse_line(_design_data(length, **{"from": {"at": [0, 63, 10]},
                                                   "to": {"at": [length - 1, 63, 10]}}), tmp_path)
    r = route.plan_route(design, route.load_grid(design.heights))
    section = r.sections[0]
    assert all(g == 64 for g in r.ground) and section.box[1] <= 50 - 6
    x1, _, z1, x2, _, z2 = section.box
    columns = {(x, z): int(ground[x + 30, z + 20]) if -20 <= z <= 20 else 64
               for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
    site = make_site(tmp_path / "site", section.box, ground=columns, world="world")
    _, mass, _ = corridor.graded_site(design, r, section, site)      # no "read lower to find the ground"
    assert mass is not None


def test_a_line_classed_from_its_reads_reads_deep_enough_for_tube_piers(tmp_path):
    for world, floor in (("world", -64), ("world_nether", 0)):    # the Nether has no blocks below y 0
        data = {"element": "deep-line", "seed": 1, "world": world, "mode": "rail", "route": "straight",
                "from": {"at": [0, 20, 0]}, "to": {"at": [30, 20, 0]}}
        design = td.parse_line(data, tmp_path)
        r = route.plan_route(design, None)
        assert r.sections[0].box[1] == max(20 - 1 - (route.TUBE_REACH + 2), floor), world


def _straight_route(length, z):
    cells = [(100 + i, z) for i in range(length)]
    return route.Route("north-line", "rail", "world", "overworld", "h", cells, [65.0] * length, ["grade"] * length,
                       [64.0] * length, [64.0] * length, [], [])


def test_the_route_map_keeps_a_thin_route_visible_when_it_shrinks_a_large_grid(tmp_path):
    from PIL import Image
    from terrain import transit_preview

    grid = route.grid_from_heights(make_heights(None, (0, 0), np.full((2400, 300), 64.0)))
    design = td.parse_line(_design_data(2000), tmp_path)
    grey = transit_preview.KIND_COLOURS["grade"]
    for z in range(150, 154):
        path = transit_preview.route_map(design, grid, _straight_route(2000, z), tmp_path / f"map-{z}.png")
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert (pixels == grey).all(axis=2).sum() > 100, z


def test_cross_sections_replace_the_stale_ones(tmp_path):
    from terrain import transit_preview

    folder = tmp_path / "previews"
    folder.mkdir()
    for name in ("north-line-xs-09.png", "north-line-line-xs-01.png", "other-xs-01.png"):
        (folder / name).write_bytes(b"old")
    written = transit_preview.cross_sections(_straight_route(30, 10), folder, element="north-line")
    names = sorted(p.name for p in folder.iterdir())
    assert "north-line-xs-09.png" not in names and {p.name for p in written} <= set(names)
    assert "north-line-line-xs-01.png" in names and "other-xs-01.png" in names
