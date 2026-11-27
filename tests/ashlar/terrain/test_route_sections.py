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
