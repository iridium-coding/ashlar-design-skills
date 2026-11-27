"""Line emission: phases, refusals, the player-block token, plan rows, previews and transit-check."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sitegen import make_heights, make_site
from terrain import blocks, route, transit
from terrain import transit_design as td
from terrain.emit import VerifyError
from terrain.live import decode
from terrain.site import Site, base_id, load_site, write_site

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills" / "terrain-shape" / "scripts" / "terrain.py"
ORIGIN, SIZE = (-40, -20), (280, 80)
Z0 = 20
DESIGN = "terrain/north-line.line.json"
ORDER = ["mass", "carve", "build", "track", "light"]


def _ground(x: int, z: int) -> int:
    """Rolling ground with a hill around x 50 and a valley around x 150."""
    hill = 12 * max(0.0, 1 - abs(x - 50) / 11)
    valley = -10 * max(0.0, 1 - abs(x - 150) / 9)
    return 64 + round(2 * math.sin(x / 7) + 2 * math.cos(z / 5) + hill + valley)


def _data(**extra) -> dict:
    data = {"element": "north-line", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [10, 65, Z0]}, "to": {"at": [190, 65, Z0]}, "heights": "heights.json"}
    data.update(extra)
    return data


def _project(tmp_path, built=None, **extra):
    """Heights, a rail design across the hill and the valley, its route and every section read."""
    project = tmp_path / "proj"
    project.mkdir(parents=True)
    nx, nz = SIZE
    ground = np.array([[_ground(ORIGIN[0] + i, ORIGIN[1] + j) for j in range(nz)] for i in range(nx)], float)
    make_heights(project / "heights.json", ORIGIN, ground)
    (project / "terrain").mkdir()
    (project / DESIGN).write_text(json.dumps(_data(**extra)), encoding="utf-8")
    design = td.load_line(project / DESIGN, project)
    transit.run_route(design, project)
    for s in _route(project).sections:
        x1, _, z1, x2, _, z2 = s.box
        heights = {(x, z): _ground(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
        make_site(project / f"site/north-line-{s.name}", s.box, ground=heights, cells=built or {}, world="world")
    return design, project


def _route(project):
    return route.load_route(project / "terrain/north-line.route.json")


def _edit(design, **changes):
    return td.parse_line({**design.source, **changes}, design.project)


def _rewrite_read(project, name, **changes):
    """Replace a section read by a copy with another box or world."""
    path = project / f"site/north-line-{name}"
    site = load_site(path)
    box = changes.get("box", site.box)
    columns = {(x, z): [(max(lo, box[1]), min(hi, box[4]), s) for lo, hi, s in runs if lo <= box[4] and hi >= box[1]]
               for (x, z), runs in site.columns.items() if box[0] <= x <= box[3] and box[2] <= z <= box[5]}
    shutil.rmtree(path)
    write_site(path, Site(box=box, world=changes.get("world", site.world), columns=columns))


def _write_projected_sites(project):
    """Every phase file's fills applied, in phase order, to each section read: the fresh reads of the build."""
    cells: dict = {}
    for path in sorted((project / "phases").glob("*.json"), key=lambda p: int(p.name.split("-")[0])):
        cells.update(decode(json.loads(path.read_text(encoding="utf-8"))["fills"]))
    dirs = []
    for read in sorted((project / "site").iterdir()):
        site = load_site(read)
        x1, y1, z1, x2, y2, z2 = site.box
        inside = {c: s for c, s in cells.items() if x1 <= c[0] <= x2 and y1 <= c[1] <= y2 and z1 <= c[2] <= z2}
        out = project / "built" / read.name
        write_site(out, blocks.apply_writes(site, [("build", blocks.cells_write(inside))]))
        dirs.append(out)
    return dirs


def _remove_one_rail(read, project):
    site = load_site(read)
    for x, z in _route(project).cells:
        rails = [lo for lo, _, state in site.columns.get((x, z), []) if base_id(state) == "minecraft:rail"]
        if rails:
            gone = blocks.cells_write({(x, rails[0], z): "minecraft:air"})
            write_site(read, blocks.apply_writes(site, [("x", gone)]))
            return
    raise AssertionError("no rail in the read")


def _cli(command, project, *args):
    return subprocess.run([sys.executable, str(LAUNCHER), command, str(project / DESIGN), *map(str, args)],
                          capture_output=True, text=True, check=False)


def _check(project, dirs):
    return _cli("transit-check", project, "--sites", *dirs, "--project", project)


# ------------------------------------------------------------------ emission
def test_line_preview_writes_reports_and_previews_but_no_phases(tmp_path):
    design, project = _project(tmp_path)
    result = transit.emit_line(design, project, first_phase=1, preview=True)
    assert result.previews and all(p.exists() for p in result.previews)
    assert (project / "terrain/north-line.line-report.json").exists()
    assert not (project / "phases").exists()
    assert not (project / "terrain/north-line.plan-rows.toon").exists()
    assert result.rows and result.report["check"]["ok"], result.report["check"]


def test_line_emit_orders_grading_then_infrastructure_with_contiguous_ids(tmp_path):
    design, project = _project(tmp_path)
    rows = transit.emit_line(design, project, first_phase=3).rows
    assert [r["id"] for r in rows] == list(range(3, 3 + len(rows)))
    for name in ("s01", "s02"):
        modes = [r["name"].split(f"-{name}-")[1].split("-")[0] for r in rows if f"-{name}-" in r["name"]]
        assert modes[0] == "mass" and {"build", "track", "light"} <= set(modes)
        assert modes == sorted(modes, key=ORDER.index)
    names = [r["name"] for r in rows]
    assert names.index("north-line-s01-light-1") < names.index("north-line-s02-mass-1")
    for r in rows:
        assert r["file"] == f"phases/{r['id']:02d}-{r['name']}.json" and (project / r["file"]).exists()
        assert r["via"] == "placer" and r["rollback"] == "backup"
        payload = json.loads((project / r["file"]).read_text(encoding="utf-8"))
        assert payload["world"] == "world" and payload["fills"]


def test_line_cli_prints_the_preview(tmp_path):
    _, project = _project(tmp_path)
    run = _cli("line", project, "--project", project, "--first-phase", "1", "--preview")
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert set(out) == {"preview", "phases", "bbox", "notes", "report", "previews"}
    assert out["preview"] is True and out["phases"] and len(out["bbox"]) == 6
    assert not (project / "phases").exists()


def test_standalone_writes_a_plan(tmp_path):
    design, project = _project(tmp_path)
    transit.emit_line(design, project, first_phase=1, standalone=True)
    plan = (project / "plan.toon").read_text(encoding="utf-8")
    assert plan.startswith("plan:\n") and "skill: system-transit" in plan and "approved: no" in plan
    assert "transit[1]{file}:" in plan


# ------------------------------------------------------------------ refusals
def test_line_refuses_missing_section_read(tmp_path):
    design, project = _project(tmp_path)
    shutil.rmtree(project / "site/north-line-s02")
    with pytest.raises(ValueError, match=r"s02.*site/north-line-s02"):
        transit.emit_line(design, project, first_phase=1)


def test_line_refuses_a_read_that_misses_the_section_box(tmp_path):
    design, project = _project(tmp_path)
    box = _route(project).sections[1].box
    short = (box[0], box[1] + 3, box[2], box[3], box[4], box[5])
    _rewrite_read(project, "s02", box=short)
    with pytest.raises(ValueError, match=r"s02.*site/north-line-s02") as err:
        transit.emit_line(design, project, first_phase=1)
    assert str(list(short)) in str(err.value) and str(list(box)) in str(err.value)


def test_line_refuses_a_read_of_another_world(tmp_path):
    design, project = _project(tmp_path)
    _rewrite_read(project, "s01", world="world_nether")
    with pytest.raises(ValueError, match=r"s01.*site/north-line-s01") as err:
        transit.emit_line(design, project, first_phase=1)
    assert "world_nether" in str(err.value) and "'world'" in str(err.value)


def test_line_refuses_a_stale_route(tmp_path):
    design, project = _project(tmp_path)
    edited = _edit(design, to={"at": [190, 65, 20], "stop": "terminus"})
    with pytest.raises(ValueError, match="stale"):
        transit.emit_line(edited, project, first_phase=1)


def test_line_refuses_a_missing_route(tmp_path):
    design, project = _project(tmp_path)
    (project / "terrain/north-line.route.json").unlink()
    with pytest.raises(ValueError, match="run terrain.py route first"):
        transit.emit_line(design, project, first_phase=1)


def test_failed_projected_checks_refuse_emission_but_not_the_preview(tmp_path):
    design, project = _project(tmp_path, lights={"min": 15})     # no lamp layout lights every cell to 15
    with pytest.raises(VerifyError, match="light"):
        transit.emit_line(design, project, first_phase=1)
    assert not (project / "phases").exists()
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    failed = [c for c in report["check"]["checks"] if not c["ok"]]
    assert [c["name"] for c in failed] == ["light"] and failed[0]["cells"]
    assert all(s["light_spacing"] == 1 for s in report["sections"])     # the densest layout was kept


def test_lamp_spacing_halves_until_each_section_is_lit(tmp_path):
    design, project = _project(tmp_path, lights={"spacing": 64})
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert report["check"]["ok"], report["check"]
    spacings = [s["light_spacing"] for s in report["sections"]]
    assert all(s < 64 and 64 % s == 0 for s in spacings), spacings


# ------------------------------------------------------------------ player blocks
def test_line_requires_the_token_for_player_blocks(tmp_path):
    design, project = _project(tmp_path, built={(40, 66, 20): "minecraft:oak_fence"})
    with pytest.raises(VerifyError, match="player block"):
        transit.emit_line(design, project, first_phase=1)
    assert not (project / "phases").exists()
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert report["built"]["count"] == 1
    item = report["built"]["items"][0]
    assert item["cell"] == [40, 66, 20] and item["block"] == "minecraft:oak_fence" and "chainage 30" in item["why"]
    assert transit.emit_line(design, project, first_phase=1, approve_built=report["built"]["token"]).rows


def test_design_edit_changes_built_token(tmp_path):
    design, project = _project(tmp_path, built={(40, 66, 20): "minecraft:oak_fence", (60, 66, 20): "minecraft:chest"})
    old = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]
    assert old["count"] == 2 and old["loses_data"] == 1
    edited, project = _project(tmp_path / "b", built={(40, 66, 20): "minecraft:oak_fence"})
    new = transit.emit_line(edited, project, first_phase=1, preview=True).report["built"]["token"]
    assert new != old["token"]
    with pytest.raises(VerifyError):
        transit.emit_line(edited, project, first_phase=1, approve_built=old["token"])


def test_a_line_without_player_blocks_needs_no_token(tmp_path):
    design, project = _project(tmp_path)
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["built"] == {"token": None, "count": 0, "by_block": {}, "loses_data": 0, "items": []}


# ------------------------------------------------------------------ plan rows and report
def test_plan_rows_carry_transit_surface_match_and_outer_seams(tmp_path):
    design, project = _project(tmp_path)
    result = transit.emit_line(design, project, first_phase=1)
    text = (project / "terrain/north-line.plan-rows.toon").read_text(encoding="utf-8")
    assert "transit[1]{file}:" in text and "surface_match[" in text and "seam[" in text
    assert "terrain/north-line.line.json" in text
    assert [row["file"] for row in result.quality["surface_match"]] == [
        "terrain/north-line-s01.surface.json", "terrain/north-line-s02.surface.json"]
    seams = result.quality["seam"]
    assert seams and {row["outward"] for row in seams} == {"z", "-z"}     # along the line, never across it
    assert not any((row["from"][1] - Z0) * (row["to"][1] - Z0) < 0 for row in seams)
    report = json.loads((project / "terrain/north-line.line-report.json").read_text(encoding="utf-8"))
    assert report["boxes"] == [list(s.box) for s in _route(project).sections]
    assert [s["name"] for s in report["sections"]] == ["s01", "s02"]
    assert {"check", "built", "displaced_water", "unsupported_tube"} <= set(report)


# ------------------------------------------------------------------ transit-check
def test_transit_check_cli_passes_on_the_projected_line_and_fails_on_a_gap(tmp_path):
    design, project = _project(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    dirs = _write_projected_sites(project)              # applies every phase file's fills to the section reads
    run = _check(project, dirs)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["ok"] is True
    _remove_one_rail(dirs[0], project)
    run = _check(project, dirs)
    assert run.returncode == 1
    assert any(c["name"] == "continuity" and not c["ok"] for c in json.loads(run.stdout)["checks"])


def test_transit_check_refuses_a_section_without_a_read_and_a_read_without_a_section(tmp_path):
    design, project = _project(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    dirs = _write_projected_sites(project)
    run = _check(project, dirs[:1])
    assert run.returncode == 1 and "s02" in run.stderr
    stray = project / "built/stray"
    make_site(stray, (300, 60, 300, 305, 70, 305), world="world")
    run = _check(project, [*dirs, stray])
    assert run.returncode == 1 and "built/stray" in run.stderr


# ------------------------------------------------------------------ underground and Nether lines
NETHERRACK = "minecraft:netherrack"


def _nether(tmp_path, cells=None):
    """A straight Nether rail line through netherrack with an open cave across part of it."""
    project = tmp_path / "deep"
    (project / "terrain").mkdir(parents=True)
    data = {"element": "deep-line", "seed": 2, "world": "world_nether", "dimension": "nether", "mode": "rail",
            "route": "straight", "from": {"at": [10, 70, Z0]}, "to": {"at": [69, 70, Z0]}}
    (project / "terrain/deep-line.line.json").write_text(json.dumps(data), encoding="utf-8")
    design = td.load_line(project / "terrain/deep-line.line.json", project)
    transit.run_route(design, project)
    section = route.load_route(project / "terrain/deep-line.route.json").sections[0]
    x1, y1, z1, x2, y2, z2 = section.box
    cave = {(x, y, z): "minecraft:air" for x in range(30, 46) for y in range(69, 77) for z in range(14, 27)}
    cave.update(cells or {})
    columns = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            states = [cave.get((x, y, z), NETHERRACK) for y in range(y1, y2 + 1)]
            states[-1] = "minecraft:air"
            runs, start = [], 0
            for i in range(1, len(states) + 1):
                if i == len(states) or states[i] != states[start]:
                    runs.append((y1 + start, y1 + i - 1, states[start]))
                    start = i
            columns[(x, z)] = runs
    write_site(project / "site/deep-line-s01", Site(box=section.box, world="world_nether", columns=columns))
    return design, project


def test_nether_line_classes_tunnel_and_tube_from_the_read(tmp_path):
    design, project = _nether(tmp_path)
    result = transit.emit_line(design, project, first_phase=1)
    kinds = result.report["sections"][0]["kinds"]
    assert kinds.get("tube", 0) > 0 and kinds.get("tunnel", 0) > 0, kinds
    assert result.report["check"]["ok"], result.report["check"]
    assert result.report["built"]["count"] == 0        # netherrack is Nether ground, not a player block


def test_a_player_block_is_listed_once_under_the_layer_that_first_changes_it(tmp_path):
    # The wall cell at chainage 4 is lined (build), then holds a lamp (light).
    design, project = _nether(tmp_path, cells={(14, 70, 22): "minecraft:oak_fence"})
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert [(i["cell"], i["block"], i["action"]) for i in report["built"]["items"]] == [
        ([14, 70, 22], "minecraft:oak_fence", "build")]


def test_netherrack_is_a_player_block_on_an_overworld_line(tmp_path):
    design, project = _project(tmp_path, built={(40, 66, 20): NETHERRACK})
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert [i["block"] for i in report["built"]["items"]] == [NETHERRACK]
