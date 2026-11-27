"""One whole rail line offline: route, section reads, line emission, every phase applied, line checks."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from sitegen import make_heights, make_site
from terrain import blocks, route, transit, transit_checks
from terrain import transit_design as td
from terrain.live import decode
from terrain.site import base_id, load_site

ORIGIN, SIZE = (-40, -20), (280, 80)
Z0 = 20
DESIGN = "terrain/north-line.line.json"


def _ground(x: int, z: int) -> int:
    """Rolling ground with a tall hill around x 60 (a tunnel) and a deep valley around x 140 (a bridge)."""
    hill = 30 * max(0.0, 1 - abs(x - 60) / 22)
    valley = -34 * max(0.0, 1 - abs(x - 140) / 14)
    return 64 + round(2 * math.sin(x / 7) + 2 * math.cos(z / 5) + hill + valley)


def _terrain_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "terrain").mkdir(parents=True)
    nx, nz = SIZE
    heights = np.array([[_ground(ORIGIN[0] + i, ORIGIN[1] + j) for j in range(nz)] for i in range(nx)], float)
    make_heights(project / "heights.json", ORIGIN, heights)
    data = {"element": "north-line", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [10, 65, Z0], "stop": "terminus"}, "to": {"at": [190, 65, Z0], "stop": "terminus"},
            "heights": "heights.json"}
    (project / DESIGN).write_text(json.dumps(data), encoding="utf-8")
    return project


def _write_reads(project: Path, r: route.Route) -> dict:
    """A read of every section box from the same ground, as the player's survey would give."""
    sites = {}
    for s in r.sections:
        x1, _, z1, x2, _, z2 = s.box
        columns = {(x, z): _ground(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
        path = project / f"site/north-line-{s.name}"
        make_site(path, s.box, ground=columns, cells={}, world="world")
        sites[s.name] = load_site(path)
    return sites


def _apply_phases(sites: dict, project: Path):
    """Every phase file's fills, in phase order, written into each section's site."""
    files = sorted((project / "phases").glob("*.json"), key=lambda p: int(p.name.split("-")[0]))
    assert files
    cells: dict = {}
    for path in files:
        cells.update(decode(json.loads(path.read_text(encoding="utf-8"))["fills"]))
    built = {}
    for name, site in sites.items():
        x1, y1, z1, x2, y2, z2 = site.box
        inside = {c: s for c, s in cells.items() if x1 <= c[0] <= x2 and y1 <= c[1] <= y2 and z1 <= c[2] <= z2}
        built[name] = blocks.apply_writes(site, [("build", blocks.cells_write(inside))])
    return built


def _remove_one_rail(built: dict, r: route.Route) -> dict:
    for s in r.sections:
        for x, z in r.cells[s.start:s.end + 1]:
            for lo, _, state in built[s.name].columns.get((x, z), []):
                if base_id(state) == "minecraft:rail":
                    gone = blocks.cells_write({(x, lo, z): "minecraft:air"})
                    return {**built, s.name: blocks.apply_writes(built[s.name], [("x", gone)])}
    raise AssertionError("no rail in the built line")


def test_rail_line_end_to_end(tmp_path):
    project = _terrain_project(tmp_path)
    design = td.load_line(project / DESIGN, project)
    assert design.source["from"]["stop"] == "terminus"
    transit.run_route(design, project)
    r = route.load_route(project / "terrain/north-line.route.json")
    assert {"bridge", "tunnel"} <= set(r.kinds), sorted(set(r.kinds))
    sites = _write_reads(project, r)

    result = transit.emit_line(design, project, first_phase=1)
    assert result.rows and result.report["check"]["ok"], result.report["check"]
    built = _apply_phases(sites, project)

    report = transit_checks.check_line(design, r, built)
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]
    assert any(c["name"] == "continuity" and c["ok"] for c in report["checks"])

    broken = transit_checks.check_line(design, r, _remove_one_rail(built, r))
    assert any(c["name"] == "continuity" and not c["ok"] for c in broken["checks"])
