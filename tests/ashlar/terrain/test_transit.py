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
from terrain import blocks, portals, route, transit, transit_checks
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


def _project(tmp_path, built=None, ground=_ground, **extra):
    """Heights, a rail design across the hill and the valley, its route and every section read."""
    project = tmp_path / "proj"
    project.mkdir(parents=True)
    nx, nz = SIZE
    heights = np.array([[ground(ORIGIN[0] + i, ORIGIN[1] + j) for j in range(nz)] for i in range(nx)], float)
    make_heights(project / "heights.json", ORIGIN, heights)
    (project / "terrain").mkdir()
    (project / DESIGN).write_text(json.dumps(_data(**extra)), encoding="utf-8")
    design = td.load_line(project / DESIGN, project)
    transit.run_route(design, project)
    for s in _route(project).sections:
        x1, _, z1, x2, _, z2 = s.box
        columns = {(x, z): ground(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
        make_site(project / f"site/north-line-{s.name}", s.box, ground=columns, cells=built or {}, world="world")
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


def _put(read, cells):
    """Overwrite cells of a (built) read in place."""
    site = load_site(read)
    write_site(read, blocks.apply_writes(site, [("x", blocks.cells_write(cells))]))


def _cli(command, project, *args, design=DESIGN):
    return subprocess.run([sys.executable, str(LAUNCHER), command, str(project / design), *map(str, args)],
                          capture_output=True, text=True, check=False)


def _check(project, dirs, design=DESIGN):
    return _cli("transit-check", project, "--sites", *dirs, "--project", project, design=design)


def _failed(run):
    return {c["name"] for c in json.loads(run.stdout)["checks"] if not c["ok"]}


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


def test_a_platform_lamp_and_a_line_lamp_on_one_cell_make_one_column(tmp_path):
    """The terminus platform's lamp column and the line's own meet on a cell: one column, a supported lantern."""
    design, project = _project(tmp_path, lights={"spacing": 6}, ground=lambda x, z: 64,
                               **{"from": {"at": [10, 65, Z0], "stop": "terminus"},
                                  "to": {"at": [190, 65, Z0], "stop": "terminus"}})
    result = transit.emit_line(design, project, first_phase=1, preview=True)
    assert result.report["check"]["ok"], result.report["check"]


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
    sections = _route(project).sections
    assert [r["box"] for r in report["reads"]] == [list(s.box) for s in sections]
    assert [r["out"] for r in report["reads"]] == ["site/north-line-s01", "site/north-line-s02"]
    written = [list(transit._union([(*r["from"], *r["to"]) for r in result.rows if f"-{s.name}-" in r["name"]]))
               for s in sections]
    assert report["boxes"] == written and written != [list(s.box) for s in sections]
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


# ------------------------------------------------------------------ fix round 1
NETHER_DESIGN = "terrain/deep-line.line.json"
LAVA = "minecraft:lava[level=0]"


def _knoll(x: int, z: int) -> int:
    """A flat plain at 64 with a knoll two blocks high on the line."""
    return 66 if 45 <= x <= 55 and 15 <= z <= 25 else 64


def _gentle(x: int, z: int) -> int:
    """A plain that rolls by a block."""
    return 64 + round(math.sin(x / 7) + math.cos(z / 5))


def test_transit_check_on_a_nether_build_fails_on_a_blocked_bore_and_on_lava_beside_it(tmp_path):
    design, project = _nether(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    built = _write_projected_sites(project)
    run = _check(project, built, design=NETHER_DESIGN)
    assert run.returncode == 0, run.stdout + run.stderr
    x, z = 20, Z0                                   # a tunnel cell: the cave spans x 30-45
    _put(built[0], {(x, 71, z): NETHERRACK})         # the bore blocked again
    run = _check(project, built, design=NETHER_DESIGN)
    assert run.returncode == 1 and "clearance" in _failed(run)
    _put(built[0], {(x, 71, z): "minecraft:air", (x, 71, z + 2): LAVA})     # lava in the wall beside the bore
    run = _check(project, built, design=NETHER_DESIGN)
    assert run.returncode == 1 and _failed(run) == {"seal"}


def test_transit_check_uses_the_kinds_the_build_used(tmp_path, monkeypatch):
    design, project = _nether(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    built = _write_projected_sites(project)
    report = json.loads((project / "terrain/deep-line.line-report.json").read_text(encoding="utf-8"))
    planned = route.load_route(project / "terrain/deep-line.route.json")
    assert set(planned.kinds) == {"tunnel"} and {"tube", "tunnel"} <= set(report["kinds"])
    checked = {}
    real = transit_checks.check_line

    def spy(design, line_route, sites, **kw):
        checked["kinds"] = list(line_route.kinds)
        return real(design, line_route, sites, **kw)

    monkeypatch.setattr(transit_checks, "check_line", spy)
    assert transit.check_reads(design, project, built)["ok"]
    assert checked["kinds"] == report["kinds"]


def test_transit_check_needs_the_line_report_of_a_nether_line(tmp_path):
    design, project = _nether(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    built = _write_projected_sites(project)
    path = project / "terrain/deep-line.line-report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**report, "route": "0" * 12}), encoding="utf-8")
    with pytest.raises(ValueError, match="run terrain.py line again"):
        transit.check_reads(design, project, built)
    path.unlink()
    with pytest.raises(ValueError, match="run terrain.py line first"):
        transit.check_reads(design, project, built)


@pytest.mark.parametrize("ground", [pytest.param(_knoll, id="flat-plain-with-a-knoll"),
                                    pytest.param(_gentle, id="plain-rolling-by-a-block")])
def test_corridor_grading_on_flat_and_gently_rolling_ground_is_emitted(tmp_path, ground):
    design, project = _project(tmp_path, ground=ground)
    result = transit.emit_line(design, project, first_phase=1)
    assert any("-s01-mass-" in r["name"] for r in result.rows)
    gate = (project / "terrain/north-line-s01.verify.txt").read_text(encoding="utf-8")
    assert "no_ziggurat: not checked: corridor grading" in gate


def test_a_section_with_nothing_to_grade_has_no_surface_match_row(tmp_path):
    design, project = _project(tmp_path, ground=_knoll)       # s02 runs at grade over flat ground
    result = transit.emit_line(design, project, first_phase=1)
    s02 = result.report["sections"][1]
    assert s02["cut_columns"] == s02["fill_columns"] == 0
    assert not any("-s02-mass-" in r["name"] for r in result.rows)
    assert [r["file"] for r in result.quality["surface_match"]] == ["terrain/north-line-s01.surface.json"]
    assert "surface_match[1]{" in (project / "terrain/north-line.plan-rows.toon").read_text(encoding="utf-8")


def test_preview_and_standalone_together_are_refused(tmp_path):
    design, project = _project(tmp_path)
    with pytest.raises(ValueError, match="standalone"):
        transit.emit_line(design, project, first_phase=1, preview=True, standalone=True)
    run = _cli("line", project, "--project", project, "--first-phase", "1", "--preview", "--standalone")
    assert run.returncode != 0 and "--standalone" in run.stderr
    assert not (project / "terrain/north-line.line-report.json").exists()


def test_the_design_is_copied_where_the_transit_row_points(tmp_path):
    design, project = _project(tmp_path)
    (project / DESIGN).unlink()
    notes = transit.emit_line(design, project, first_phase=1).notes
    assert json.loads((project / DESIGN).read_text(encoding="utf-8")) == design.source
    assert any("copied" in n and DESIGN in n for n in notes)
    assert not any("copied" in n for n in transit.emit_line(design, project, first_phase=1).notes)


# ------------------------------------------------------------------ final fix wave: sections, structures, stops
def _section_reads(project, element, r, ground, cells=None):
    """A read of every section box: `ground` gives each column's grass level, `cells` overrides cells."""
    for s in r.sections:
        x1, _, z1, x2, _, z2 = s.box
        columns = {(x, z): ground(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
        make_site(project / f"site/{element}-{s.name}", s.box, ground=columns, cells=cells or {}, world="world")


def _line_project(tmp_path, data, ground, *, cells=None, surface=None):
    """The design `data` with its route and every section read; heights from `ground` unless it has none."""
    project = tmp_path / "line"
    (project / "terrain").mkdir(parents=True)
    element = data["element"]
    if "heights" in data:
        nx, nz = SIZE
        g = np.array([[ground(ORIGIN[0] + i, ORIGIN[1] + j) for j in range(nz)] for i in range(nx)], float)
        s = None if surface is None else np.array(
            [[surface(ORIGIN[0] + i, ORIGIN[1] + j) for j in range(nz)] for i in range(nx)], float)
        make_heights(project / data["heights"], ORIGIN, g, surface=s)
    path = project / f"terrain/{element}.line.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    design = td.load_line(path, project)
    transit.run_route(design, project)
    r = route.load_route(project / f"terrain/{element}.route.json")
    _section_reads(project, element, r, ground, cells)
    return design, project, r


def _built_sections(project, element, r):
    """Every phase applied, in phase order, to each section read: what fresh reads of the build would hold."""
    cells: dict = {}
    for path in sorted((project / "phases").glob("*.json"), key=lambda p: int(p.name.split("-")[0])):
        cells.update(decode(json.loads(path.read_text(encoding="utf-8"))["fills"]))
    built = {}
    for s in r.sections:
        site = load_site(project / f"site/{element}-{s.name}")
        x1, y1, z1, x2, y2, z2 = site.box
        inside = {c: v for c, v in cells.items() if x1 <= c[0] <= x2 and y1 <= c[1] <= y2 and z1 <= c[2] <= z2}
        built[s.name] = blocks.apply_writes(site, [("build", blocks.cells_write(inside))])
    return built


def _failing(report):
    return [(c["name"], c["detail"], c["cells"][:3]) for c in report["checks"] if not c["ok"]]


@pytest.mark.parametrize("corner", [pytest.param(20, id="first-cell"), pytest.param(21, id="second-cell")])
def test_a_tunnel_corner_at_a_section_start_keeps_every_rail(tmp_path, corner):
    data = {"element": "deep", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 40, 0]}, "via": [[corner, 0]], "to": {"at": [corner, 40, 39 - corner]},
            "sections": {"length": 20}}
    design, project, r = _line_project(tmp_path, data, lambda x, z: 90)
    assert r.corners == [corner] and r.sections[1].start == 20
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["check"]["ok"], _failing(result.report["check"])
    post = transit_checks.check_line(design, r, _built_sections(project, "deep", r))
    assert post["ok"], _failing(post)


def _lake(x, z):
    return 6 <= x <= 30 and -12 <= z <= 14


def test_a_bridge_corner_at_a_section_start_keeps_every_rail(tmp_path):
    data = {"element": "span", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 65, 0]}, "via": [[20, 0]], "to": {"at": [20, 65, 19]}, "heights": "heights.json",
            "bridges": {"piers_in_water": True}, "sections": {"length": 20}}
    water = {(x, y, z): "minecraft:water[level=0]" for x in range(-30, 70) for z in range(-30, 50)
             if _lake(x, z) for y in (61, 62)}
    design, project, r = _line_project(tmp_path, data, lambda x, z: 60 if _lake(x, z) else 64, cells=water,
                                       surface=lambda x, z: 62 if _lake(x, z) else 64)
    assert r.corners == [20] and r.sections[1].start == 20 and r.kinds[18:23] == ["bridge"] * 5
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["check"]["ok"], _failing(result.report["check"])
    post = transit_checks.check_line(design, r, _built_sections(project, "span", r))
    assert post["ok"], _failing(post)


def test_overworld_lamp_spacing_holds_across_section_boundaries(tmp_path):
    data = {"element": "plain", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 65, 0]}, "to": {"at": [99, 65, 0]}, "heights": "heights.json",
            "sections": {"length": 25}}
    design, project, _ = _line_project(tmp_path, data, lambda x, z: 64)
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert report["check"]["ok"], _failing(report["check"])
    assert [s["light_spacing"] for s in report["sections"]] == [design.lights.spacing] * 4


def _ditches(x, z):
    """Flat ground with two ditches the line dips into (the embankment beside it falls away)."""
    return 59 if 44 <= x <= 48 else 60 if 92 <= x <= 96 else 64


def test_lamp_posts_beside_an_embankment_reach_the_ground(tmp_path):
    data = {"element": "dip", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [10, 65, Z0], "stop": "terminus"}, "to": {"at": [140, 65, Z0], "stop": "terminus"},
            "heights": "heights.json"}
    design, project, r = _line_project(tmp_path, data, _ditches)
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["check"]["ok"], _failing(result.report["check"])
    built = _built_sections(project, "dip", r)
    posts, lamps = set(design.palette["lamp_post"]), set(design.palette["lamp"])
    seen = 0
    for s in r.sections:
        site = built[s.name]
        for (x, z), runs in site.columns.items():
            for lo, _, state in runs:
                if base_id(state) in lamps:
                    y = lo - 1
                    while base_id(site.block(x, y, z)) in posts:
                        y -= 1
                    seen += 1
                    assert base_id(site.block(x, y, z)) not in ("minecraft:air", "minecraft:cave_air"), (x, y, z)
    assert seen
    assert transit_checks.check_line(design, r, built)["ok"]


def test_a_tube_read_reaches_the_ground_its_piers_stand_on(tmp_path):
    data = {"element": "hall", "seed": 1, "world": "world_nether", "mode": "rail", "route": "straight",
            "from": {"at": [0, 60, 0]}, "to": {"at": [60, 60, 0]}}
    project = tmp_path / "hall"
    (project / "terrain").mkdir(parents=True)
    (project / "terrain/hall.line.json").write_text(json.dumps(data), encoding="utf-8")
    design = td.load_line(project / "terrain/hall.line.json", project)
    transit.run_route(design, project)
    r = route.load_route(project / "terrain/hall.route.json")
    for s in r.sections:              # open air down to a floor 12 below the line, read exactly the box
        make_site(project / f"site/hall-{s.name}", s.box, ground=48, world="world_nether")
    result = transit.emit_line(design, project, first_phase=1, preview=True)
    assert result.report["sections"][0]["kinds"] == {"tube": 61}
    assert result.report["unsupported_tube"] == 0 and result.report["sections"][0]["piers"] > 0


def test_a_rail_tunnel_over_a_cave_beds_on_lining_rather_than_gravel(tmp_path):
    data = {"element": "deep", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 40, 0]}, "to": {"at": [40, 40, 0]}}
    cave = {(x, y, z): "minecraft:cave_air" for x in range(15, 25) for y in (36, 37, 38) for z in range(-3, 4)}
    design, project, r = _line_project(tmp_path, data, lambda x, z: 90, cells=cave)
    result = transit.emit_line(design, project, first_phase=1)
    assert result.report["check"]["ok"], _failing(result.report["check"])
    built = _built_sections(project, "deep", r)["s01"]
    lining = set(design.palette["lining"])
    for x in range(15, 25):
        for z in (-1, 0, 1):
            below = base_id(built.block(x, 39, z))
            assert below in lining or below == "minecraft:redstone_block", (x, z, below)


def test_a_form_refusal_is_reported_in_a_preview_and_refuses_a_write_after_the_report(tmp_path):
    data = {"element": "walk", "seed": 1, "world": "world", "mode": "path", "route": "straight",
            "from": {"at": [0, 65, 0]}, "to": {"at": [30, 65, 0]}, "heights": "heights.json",
            "palette": {"surface": "minecraft:gravel"}}
    hollow = {(x, 63, z): "minecraft:air" for x in range(10, 20) for z in range(-3, 4)}
    design, project, _ = _line_project(tmp_path, data, lambda x, z: 64, cells=hollow)
    result = transit.emit_line(design, project, first_phase=1, preview=True)
    refused = result.report["refused"]
    assert refused and refused[0]["section"] == "s01" and "gravity" in refused[0]["error"]
    assert any("gravity" in n for n in result.notes)
    report_path = project / "terrain/walk.line-report.json"
    report_path.unlink()
    with pytest.raises(VerifyError, match="gravity"):
        transit.emit_line(design, project, first_phase=1)
    assert report_path.exists() and not (project / "phases").exists()


def _landing(tmp_path):
    """A built Nether landing with a doorway facing south at (13, 71, 9), read as a whole."""
    pair = portals.parse_portal({"element": "hub", "overworld": {"world": "world", "at": [80, 70, 40]},
                                 "nether": {"world": "world_nether", "at": [10, 70, 5]}, "size": [4, 5],
                                 "doorways": [[13, 71, 9, "south"]]}, tmp_path)
    big = make_site(tmp_path / "big", (-30, 30, -30, 60, 100, 80), ground=95, world="world_nether")
    return blocks.apply_writes(big, portals.portal_layers(pair, "nether", big))


def _crop(site, box):
    cols = {(x, z): [(max(lo, box[1]), min(hi, box[4]), s) for lo, hi, s in runs if lo <= box[4] and hi >= box[1]]
            for (x, z), runs in site.columns.items() if box[0] <= x <= box[3] and box[2] <= z <= box[5]}
    return Site(box=box, world=site.world, columns=cols)


@pytest.mark.parametrize("mode", ["rail", "path"])
def test_a_spoke_ending_at_a_landing_doorway_clears_it_and_touches_no_landing_block(tmp_path, mode):
    landed = _landing(tmp_path)
    project = tmp_path / "spoke"
    (project / "terrain").mkdir(parents=True)
    data = {"element": "spoke", "seed": 1, "world": "world_nether", "mode": mode, "route": "straight",
            "from": {"at": [13, 71, 45]}, "to": {"at": [13, 71, 11], "stop": "open"}}
    if mode == "path":
        data["width"] = 1
    (project / "terrain/spoke.line.json").write_text(json.dumps(data), encoding="utf-8")
    design = td.load_line(project / "terrain/spoke.line.json", project)
    transit.run_route(design, project)
    for s in route.load_route(project / "terrain/spoke.route.json").sections:
        write_site(project / f"site/spoke-{s.name}", _crop(landed, s.box))
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    assert report["check"]["ok"], _failing(report["check"])
    assert report["built"]["count"] == 0, report["built"]["items"]


def _pit(x, z):
    """Ground 64 with a pit 20 deep over x 78..114, z -20..30."""
    return 44 if 78 <= x <= 114 and -20 <= z <= 30 else 64


def test_a_cliff_past_the_outside_of_a_corner_on_a_valley_floor_is_left_alone(tmp_path):
    # The line drops to the pit floor and turns there; the pit wall stands 19 blocks past the corner,
    # straight ahead of the incoming leg (bridge_corner.py).
    data = {"element": "pit", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 65, 0]}, "via": [[96, 0]], "to": {"at": [96, 65, 50]}, "heights": "heights.json"}
    design, project, r = _line_project(tmp_path, data, _pit)
    result = transit.emit_line(design, project, first_phase=1)         # no edge_match refusal
    assert result.report["check"]["ok"], _failing(result.report["check"])
    built = _built_sections(project, "pit", r)
    for z in (-1, 0, 1):
        assert built["s02"].block(115, 64, z) == "minecraft:grass_block[snowy=false]", z



# ------------------------------------------------------------------ player blocks the line affects in place
def test_a_player_block_buried_under_the_line_is_listed_for_the_token(tmp_path):
    slab = "minecraft:oak_slab[type=bottom,waterlogged=false]"
    design, project = _project(tmp_path, ground=lambda x, z: 64, built={(186, 64, Z0 - 2): slab},
                               to={"at": [190, 65, Z0], "stop": "terminus"})
    built = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]
    assert [(i["cell"], i["block"], i["action"]) for i in built["items"]] == [([186, 64, Z0 - 2], slab, "buried")]
    assert "platform" in built["items"][0]["why"] or "bed" in built["items"][0]["why"]


def _pit_floor(x, z):
    return 50 if 20 <= x <= 32 else 64


def test_a_player_block_a_pier_stands_on_is_listed_for_the_token(tmp_path):
    data = {"element": "span", "seed": 1, "world": "world", "mode": "rail", "route": "straight",
            "from": {"at": [0, 65, Z0]}, "to": {"at": [52, 65, Z0]}, "heights": "heights.json"}
    floor = {(x, 50, z): "minecraft:stone_bricks" for x in range(20, 33) for z in range(Z0 - 6, Z0 + 7)}
    design, project, r = _line_project(tmp_path, data, _pit_floor, cells=floor)
    assert "bridge" in r.kinds
    built = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]
    carried = [i for i in built["items"] if i["action"] == "carries"]
    assert carried and all(i["block"] == "minecraft:stone_bricks" and i["cell"][1] == 50 for i in carried)
    assert all("pier" in i["why"] for i in carried) and built["token"]


def test_a_player_block_left_in_a_bore_is_named_by_the_clearance_refusal(tmp_path):
    design, project = _nether(tmp_path, cells={(20, 71, Z0): "minecraft:oak_planks"})
    report = transit.emit_line(design, project, first_phase=1, preview=True).report
    clearance = next(c for c in report["check"]["checks"] if c["name"] == "clearance")
    assert not clearance["ok"] and "player block minecraft:oak_planks at (20, 71, 20)" in clearance["detail"]
    with pytest.raises(VerifyError, match=r"player block minecraft:oak_planks at \(20, 71, 20\)"):
        transit.emit_line(design, project, first_phase=1)


def test_a_player_block_a_lamp_post_stands_on_is_listed_for_the_token(tmp_path):
    design, project = _project(tmp_path, ground=lambda x, z: 64, built={(10, 64, Z0 + 2): "minecraft:oak_planks"})
    built = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]
    assert [(i["cell"], i["block"], i["action"]) for i in built["items"]] == [
        ([10, 64, Z0 + 2], "minecraft:oak_planks", "carries")]
    assert "lamp post" in built["items"][0]["why"] and built["token"]
