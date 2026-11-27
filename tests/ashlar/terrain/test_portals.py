"""Portal pairs: the maths, the pair check, frames, landings, emission and the command."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sitegen import make_site
from terrain import blocks, portals, route
from terrain.site import Site, load_site, write_site

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills" / "terrain-shape" / "scripts" / "terrain.py"
NETHERRACK, AIR, LAVA = "minecraft:netherrack", "minecraft:air", "minecraft:lava[level=0]"
PORTAL_X = "minecraft:nether_portal[axis=x]"
DESIGN = "terrain/east-gate.portal.json"


def _data(**extra) -> dict:
    data = {"element": "east-gate", "overworld": {"world": "world"}, "nether": {"world": "world_nether"},
            "size": [4, 5], "doorways": []}
    data.update(extra)
    return data


def _design(tmp_path, nether_at=None, overworld_at=None, axis="x", **extra):
    data = _data(**extra)
    data["nether"] = {**data["nether"], "axis": axis, **({"at": nether_at} if nether_at else {})}
    if overworld_at:
        data["overworld"] = {**data["overworld"], "at": overworld_at}
    return portals.parse_portal(data, tmp_path)


def _nether_site(path, box, cells=None, lava_everywhere=False):
    x1, y1, z1, x2, y2, z2 = box
    cells = cells or {}
    columns = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            states = [LAVA if lava_everywhere else NETHERRACK if y <= 64 else AIR for y in range(y1, y2 + 1)]
            for y in range(y1, y2 + 1):
                if (x, y, z) in cells:
                    states[y - y1] = cells[(x, y, z)]
            runs, start = [], 0
            for i in range(1, len(states) + 1):
                if i == len(states) or states[i] != states[start]:
                    runs.append((y1 + start, y1 + i - 1, states[start]))
                    start = i
            columns[(x, z)] = runs
    site = Site(box=box, world="world_nether", columns=columns)
    write_site(path, site)
    return site


def _bare_sites(tmp_path, design, extra=None, nether_lava=None, lava_everywhere=False):
    """Reads of both worlds over the read boxes: ground at 64, netherrack in the Nether."""
    boxes = portals.read_boxes(design)
    extra = extra or {}
    sites = {
        "overworld": make_site(tmp_path / "ow", boxes["overworld"], ground=64, world="world",
                               cells={c: s for (d, c), s in extra.items() if d == "overworld"}),
        "nether": _nether_site(tmp_path / "ne", boxes["nether"],
                               cells={**{c: s for (d, c), s in extra.items() if d == "nether"},
                                      **({nether_lava: LAVA} if nether_lava else {})}, lava_everywhere=lava_everywhere),
    }
    return sites


def _pair_sites(tmp_path, extra_portal=None, doorways=(), nether_lava=None):
    """The design (nether end given at [10, 70, 5]) and both reads with the pair built."""
    design = _design(tmp_path, nether_at=[10, 70, 5], doorways=[list(d) for d in doorways])
    extra = {extra_portal[:2] and (extra_portal[0], extra_portal[1]): PORTAL_X} if extra_portal else {}
    sites = _bare_sites(tmp_path, design, extra, nether_lava)
    if nether_lava is None:
        sites = {d: blocks.apply_writes(s, portals.portal_layers(design, d, s)) for d, s in sites.items()}
        if extra_portal:     # the extra portal comes after the build
            dim, cell = extra_portal
            sites[dim] = blocks.apply_writes(sites[dim], [("x", blocks.cells_write({cell: PORTAL_X}))])
    return design, sites


def _frame_box_cells(design, dim):
    cells = portals.frame_cells(design, dim) + portals.opening(design, dim)
    return sorted(cells)


def _min_floor_light(site, design):
    level = blocks.flood(blocks.cell_classes(site)[1], blocks.site_light(site))
    ox, oy, oz = portals.frame_origin(design, "nether")
    skip = set(_frame_box_cells(design, "nether"))
    values = []
    for x in range(ox - 1, ox + 5):
        for z in range(oz - 5, oz + 6):
            cell = (x, oy + 1, z)
            if cell not in skip and not blocks.full_cube(site.block(*cell)):
                values.append(int(level[x - site.box[0], cell[1] - site.box[1], z - site.box[2]]))
    return min(values)


# ------------------------------------------------------------------ maths
def test_scale_overworld_to_nether_and_back():
    assert portals.scale((3600, 70, 0), "nether") == (450, 70, 0)
    assert portals.scale((-109, 40, 20), "overworld") == (-872, 40, 160)
    assert portals.scale((-1, 64, -9), "nether") == (-1, 64, -2)


def test_the_other_end_is_the_given_one_scaled(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5])
    assert portals.frame_origin(design, "overworld") == (80, 70, 40)
    assert portals.frame_origin(design, "nether") == (10, 70, 5)


def test_arrival_points_spread_sixteen_into_the_overworld(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5], axis="x")
    xs = [p[0] for p in portals.arrival_points(design, "overworld")]
    assert max(xs) - min(xs) == 16


def test_design_parsing_refuses_bad_input(tmp_path):
    with pytest.raises(ValueError, match="overworld.at or nether.at"):
        portals.parse_portal(_data(), tmp_path)
    with pytest.raises(ValueError, match="size"):
        portals.parse_portal(_data(size=[3, 5], overworld={"world": "world", "at": [0, 70, 0]}), tmp_path)
    with pytest.raises(ValueError, match="facing"):
        _design(tmp_path, nether_at=[10, 70, 5], doorways=[[1, 2, 3, "up"]])


# ------------------------------------------------------------------ the pair check
def test_pair_check_passes_with_no_other_portal(tmp_path):
    design, sites = _pair_sites(tmp_path)
    assert portals.pair_check(design, sites)["ok"]


def test_pair_check_flags_a_nearer_portal(tmp_path):
    design, sites = _pair_sites(tmp_path, extra_portal=("overworld", (95, 70, 41)))
    report = portals.pair_check(design, sites)
    assert not report["ok"] and [95, 70, 41] in report["checks"][0]["cells"]
    assert report["checks"][1]["ok"]


# ------------------------------------------------------------------ frames and landings
def test_portal_layers_build_frame_and_axis_blocks(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5])
    sites = _bare_sites(tmp_path, design)
    after = blocks.apply_writes(sites["overworld"], portals.portal_layers(design, "overworld", sites["overworld"]))
    states = [after.block(*c) for c in _frame_box_cells(design, "overworld")]
    assert states.count("minecraft:obsidian") == 14 and states.count(PORTAL_X) == 6


def test_a_z_axis_frame_lies_in_the_z_plane(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5], axis="z")
    assert {c[0] for c in portals.frame_cells(design, "nether")} == {10}
    assert {c[2] for c in portals.opening(design, "nether")} == {6, 7}


def test_overworld_landing_is_a_platform_three_deep_on_both_faces(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5])
    site = make_site(tmp_path / "ow", portals.read_boxes(design)["overworld"], ground=64, world="world")
    after = blocks.apply_writes(site, portals.portal_layers(design, "overworld", site))
    ox, oy, oz = portals.frame_origin(design, "overworld")
    for dz in (-3, 3):
        assert "stone" in after.block(ox + 1, oy, oz + dz) or "blackstone" in after.block(ox + 1, oy, oz + dz)
    assert after.block(ox + 1, oy + 1, oz + 3) == AIR


def test_nether_landing_is_lit_to_twelve_and_keeps_doorways_open(tmp_path):
    design, sites = _pair_sites(tmp_path, doorways=[[13, 71, 9, "south"]])
    after = sites["nether"]
    assert after.block(13, 71, 9) == AIR and after.block(13, 72, 9) == AIR
    assert after.block(13, 71, 11) == AIR and after.block(13, 72, 11) == AIR    # through the wall
    assert after.block(12, 72, 11).endswith("[type=double,waterlogged=false]")      # the mouth is framed in edge
    assert after.block(12, 71, 11).endswith("[type=double,waterlogged=false]")
    assert _min_floor_light(after, design) >= 12


def test_nether_floor_is_a_bottom_slab_nothing_spawns_on(tmp_path):
    from terrain.transit_checks import parse_state, spawnable_floor
    _, sites = _pair_sites(tmp_path)
    state = sites["nether"].block(9, 71, 3)
    assert parse_state(state)[1]["type"] == "bottom" and not spawnable_floor(state)


def test_a_doorway_that_misses_the_wall_is_refused(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5], doorways=[[100, 71, 100, "south"]])
    site = _bare_sites(tmp_path, design)["nether"]
    with pytest.raises(ValueError, match="doorway"):
        portals.portal_layers(design, "nether", site)


def test_nether_end_in_lava_is_refused_with_the_cell(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5])
    site = _bare_sites(tmp_path, design, nether_lava=(12, 70, 7))["nether"]
    with pytest.raises(route.RouteError, match=r"\(12, 70, 7\)"):
        portals.portal_layers(design, "nether", site)


def test_a_computed_nether_end_moves_to_the_nearest_level_that_fits(tmp_path):
    design = _design(tmp_path, overworld_at=[80, 70, 40], axis="x")
    lava = (12, 70, 7)
    site = _bare_sites(tmp_path, design, nether_lava=lava)["nether"]
    fitted = portals.fit_nether(design, site)
    assert portals.frame_origin(fitted, "nether") == (10, 71, 5)


def test_no_nether_level_that_fits_names_a_lava_cell(tmp_path):
    design = _design(tmp_path, overworld_at=[80, 70, 40], axis="x")
    site = _bare_sites(tmp_path, design, lava_everywhere=True)["nether"]
    with pytest.raises(route.RouteError, match="lava at"):
        portals.fit_nether(design, site)


def test_existing_player_blocks_in_the_landing_are_kept(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5])
    wall = "minecraft:bricks"
    site = _bare_sites(tmp_path, design, {("nether", (9, 71, 3)): wall})["nether"]
    after = blocks.apply_writes(site, portals.portal_layers(design, "nether", site))
    assert after.block(9, 71, 3) == wall


# ------------------------------------------------------------------ the checks
def test_check_portal_passes_a_built_pair_and_fails_a_broken_one(tmp_path):
    design, sites = _pair_sites(tmp_path)
    assert portals.check_portal(design, sites)["ok"]
    cell = portals.opening(design, "overworld")[0]
    broken = blocks.apply_writes(sites["overworld"], [("x", blocks.cells_write({cell: "minecraft:nether_portal[axis=z]"}))])
    report = portals.check_portal(design, {**sites, "overworld": broken})
    assert [c["name"] for c in report["checks"] if not c["ok"]] == ["axis"]
    gone = portals.frame_cells(design, "nether")[0]
    broken = blocks.apply_writes(sites["nether"], [("x", blocks.cells_write({gone: AIR}))])
    assert "frame" in {c["name"] for c in portals.check_portal(design, {**sites, "nether": broken})["checks"] if not c["ok"]}


def test_check_portal_fails_a_dark_landing(tmp_path):
    design, sites = _pair_sites(tmp_path)
    ox, oy, oz = portals.frame_origin(design, "nether")
    dark = blocks.apply_writes(sites["nether"], [("x", blocks.cells_write(
        {(ox - 2, oy + 1, z): "minecraft:bricks" for z in range(oz - 6, oz + 7)}))])
    assert "light" in {c["name"] for c in portals.check_portal(design, {**sites, "nether": dark})["checks"] if not c["ok"]}


# ------------------------------------------------------------------ the command
def _cli(command, project, *args):
    return subprocess.run([sys.executable, str(LAUNCHER), command, str(project / DESIGN), *map(str, args)],
                          capture_output=True, text=True, check=False)


def _portal_project(tmp_path, **extra):
    project = tmp_path / "proj"
    (project / "terrain").mkdir(parents=True)
    data = _data(**extra)
    data["overworld"] = {"world": "world", "at": [3600, 70, 0], "axis": "x"}
    (project / DESIGN).write_text(json.dumps(data), encoding="utf-8")
    return project


def _write_reads(project, extra=None):
    design = portals.load_portal(project / DESIGN, project)
    boxes = portals.read_boxes(design)
    make_site(project / "site/east-gate-overworld", boxes["overworld"], ground=64, world="world", cells=extra or {})
    _nether_site(project / "site/east-gate-nether", boxes["nether"])


def test_portal_command_lists_reads_then_emits_phases_for_both_worlds(tmp_path):
    project = _portal_project(tmp_path)
    first = _cli("portal", project, "--project", project, "--first-phase", "3")
    assert first.returncode == 1 and "site/east-gate-overworld" in first.stderr and "site/east-gate-nether" in first.stderr
    _write_reads(project)
    second = _cli("portal", project, "--project", project, "--first-phase", "3")
    assert second.returncode == 0, second.stderr
    files = sorted((project / "phases").glob("*.json"))
    worlds = {json.loads(p.read_text())["world"] for p in files}
    assert worlds == {"world", "world_nether"}
    ids = [int(p.name.split("-")[0]) for p in files]
    assert ids == list(range(3, 3 + len(ids)))
    assert (project / "terrain/east-gate.plan-rows.toon").exists()
    assert "transit" in (project / "terrain/east-gate.plan-rows.toon").read_text()
    rows = json.loads(second.stdout)["phases"]
    assert rows[0]["world"] == "world" and rows[-1]["world"] == "world_nether"


def test_portal_preview_writes_the_report_only(tmp_path):
    project = _portal_project(tmp_path)
    _write_reads(project)
    run = _cli("portal", project, "--project", project, "--first-phase", "1", "--preview")
    assert run.returncode == 0, run.stderr
    assert not (project / "phases").exists() and (project / "terrain/east-gate.portal-report.json").exists()


def test_portal_command_needs_the_token_for_player_blocks(tmp_path):
    project = _portal_project(tmp_path)
    design = portals.load_portal(project / DESIGN, project)
    ox, oy, oz = portals.frame_origin(design, "overworld")
    _write_reads(project, {(ox + 1, oy, oz): "minecraft:bricks"})
    run = _cli("portal", project, "--project", project, "--first-phase", "1")
    assert run.returncode == 1 and "--approve-built" in run.stderr
    token = json.loads((project / "terrain/east-gate.portal-report.json").read_text())["built"]["token"]
    ok = _cli("portal", project, "--project", project, "--first-phase", "1", "--approve-built", token)
    assert ok.returncode == 0, ok.stderr


def test_portal_command_refuses_a_read_of_another_world(tmp_path):
    project = _portal_project(tmp_path)
    _write_reads(project)
    design = portals.load_portal(project / DESIGN, project)
    make_site(project / "site/east-gate-overworld", portals.read_boxes(design)["overworld"], world="elsewhere")
    run = _cli("portal", project, "--project", project, "--first-phase", "1")
    assert run.returncode == 1 and "elsewhere" in run.stderr


def test_transit_check_on_a_portal_design(tmp_path):
    project = _portal_project(tmp_path)
    _write_reads(project)
    assert _cli("portal", project, "--project", project, "--first-phase", "1").returncode == 0
    built = {}
    cells: dict = {}
    for path in sorted((project / "phases").glob("*.json"), key=lambda p: int(p.name.split("-")[0])):
        payload = json.loads(path.read_text())
        from terrain.live import decode
        cells.setdefault(payload["world"], {}).update(decode(payload["fills"]))
    for dim in ("overworld", "nether"):
        site = load_site(project / f"site/east-gate-{dim}")
        out = project / "built" / dim
        write_site(out, blocks.apply_writes(site, [("build", blocks.cells_write(cells["world" if dim == "overworld" else "world_nether"]))]))
        built[dim] = out
    run = _cli("transit-check", project, "--sites", built["overworld"], built["nether"], "--project", project)
    assert run.returncode == 0, run.stdout + run.stderr
    assert {c["name"] for c in json.loads(run.stdout)["checks"]} >= {"frame", "axis", "light", "pair-overworld"}
    # take a frame block out of the nether read: the check fails
    site = load_site(built["nether"])
    gone = portals.frame_cells(portals.load_portal(project / DESIGN, project), "nether")[0]
    write_site(built["nether"], blocks.apply_writes(site, [("x", blocks.cells_write({gone: AIR}))]))
    bad = _cli("transit-check", project, "--sites", built["overworld"], built["nether"], "--project", project)
    assert bad.returncode == 1
