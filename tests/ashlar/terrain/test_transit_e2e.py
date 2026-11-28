"""Whole lines offline: route, section reads, line emission, every phase applied, then the line's checks
and every quality row of its plan (surface_match, seam, transit) run by the launcher's own commands."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from sitegen import make_heights, make_site
from terrain import blocks, route, transit, transit_checks
from terrain import transit_design as td
from terrain.live import decode
from terrain.site import (
    ATTACHED,
    LEAVES,
    PLANTS,
    base_id,
    liquid_kind,
    load_site,
    write_site,
)

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


# ------------------------------------------------------------------ build and verify, as the plan's rows do
REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills" / "terrain-shape" / "scripts" / "terrain.py"
_NO_COLLISION = ("rail", "torch", "lantern", "_carpet", "_button", "_pressure_plate", "_sign", "_banner")


def _cli():
    """The launcher's ``main``, run in this process: the same rules as ``terrain.py <command>``."""
    spec = importlib.util.spec_from_file_location("terrain_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _blocks_motion(state: str) -> bool:
    """What the server's SOLID_OR_LIQUID_NO_LEAVES height counts: a block with collision or a liquid, not leaves."""
    block = base_id(state)
    if block in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
        return False
    if liquid_kind(state) is not None:
        return True
    return not (block in LEAVES or block in PLANTS or block in ATTACHED or block.endswith(_NO_COLLISION))


def _measured_heights(site, path: Path) -> Path:
    """The F2 heights file ``ashlar_place.py heights`` would read over the site's columns after the build."""
    x1, _, z1, x2, _, z2 = site.box
    nx, nz = x2 - x1 + 1, z2 - z1 + 1
    surface = np.full((nx, nz), np.nan)
    for (x, z), runs in site.columns.items():
        for _, hi, state in reversed(runs):
            if _blocks_motion(state):
                surface[x - x1, z - z1] = hi
                break
    make_heights(path, (x1, z1), surface)
    return path


_LINES = {
    "rail": {"from": {"at": [10, 65, Z0], "stop": "terminus"}, "to": {"at": [190, 65, Z0], "stop": "terminus"}},
    "road": {"from": {"at": [10, 65, Z0]}, "to": {"at": [190, 65, Z0]}},
    "ice": {"from": {"at": [10, 65, Z0]}, "to": {"at": [190, 65, Z0]}},
}


@pytest.mark.parametrize("mode", list(_LINES))
def test_every_quality_row_passes_on_the_built_line(tmp_path, mode):
    project = _terrain_project(tmp_path)
    data = {**json.loads((project / DESIGN).read_text(encoding="utf-8")), "mode": mode, **_LINES[mode]}
    (project / DESIGN).write_text(json.dumps(data), encoding="utf-8")
    design = td.load_line(project / DESIGN, project)
    transit.run_route(design, project)
    r = route.load_route(project / "terrain/north-line.route.json")
    sites = _write_reads(project, r)
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["check"]["ok"], result.report["check"]
    built = _apply_phases(sites, project)
    dirs = {}
    for name, site in built.items():
        dirs[name] = project / "verify" / f"north-line-{name}"
        write_site(dirs[name], site)
    main = _cli()

    assert result.quality["surface_match"]
    for row in result.quality["surface_match"]:
        name = row["file"].rsplit("-", 1)[1].split(".")[0]
        heights = _measured_heights(built[name], project / "verify" / f"{name}.heights.json")
        status = main(["compare", str(project / row["file"]), str(heights), "--tolerance", str(row["tolerance"]),
                       "--min-ratio", str(row["min_ratio"])])
        assert status == 0, (row["file"], status)

    assert result.quality["seam"]
    steps = {"x": (1, 0), "-x": (-1, 0), "z": (0, 1), "-z": (0, -1)}
    for row in result.quality["seam"]:
        dx, dz = steps[row["outward"]]
        points = [row["from"], row["to"], [row["from"][0] + dx, row["from"][1] + dz],
                  [row["to"][0] + dx, row["to"][1] + dz]]
        name = next(n for n, s in built.items()
                    if all(s.box[0] <= x <= s.box[3] and s.box[2] <= z <= s.box[5] for x, z in points))
        status = main(["seam", "--site", str(dirs[name]), "--from", *map(str, row["from"]), "--to",
                       *map(str, row["to"]), f"--outward={row['outward']}", "--max-step", str(row["max_step"])])
        assert status == 0, row

    assert main(["transit-check", str(project / DESIGN), "--sites", *map(str, dirs.values()),
                 "--project", str(project)]) == 0
