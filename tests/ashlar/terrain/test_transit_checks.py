from __future__ import annotations

import math

import pytest
from sitegen import STONE, make_site
from terrain import blocks, structures, track, transit_checks
from terrain import transit_design as td
from terrain.route import Route, Section
from terrain.site import Site, base_id

Z0 = 20
LAVA = "minecraft:lava[level=0]"
ORDER = {"carve": 0, "build": 1, "track": 2, "light": 3}


def _line(tmp_path, mode, kinds, *, levels=None, ground=None, extra=None, end_stop=None, x0=5):
    n = len(kinds)
    cells = [(x0 + k, Z0) for k in range(n)]
    levels = levels or [65] * n
    nether = (extra or {}).get("dimension") == "nether"
    y = levels[0] if nether or mode == "ice" else None
    data = {"element": "t", "seed": 7, "world": "world", "mode": mode, "route": "straight",
            "from": {"at": [cells[0][0], y, cells[0][1]]},
            "to": {"at": [cells[-1][0], y, cells[-1][1]], "stop": end_stop}}
    data.update(extra or {})
    design = td.parse_line(data, tmp_path)
    r = Route("t", mode, "world", design.dimension, "h", cells, [float(v) for v in levels], list(kinds),
              [None] * n, [None] * n, [], [])
    box = (x0 - 10, 40, Z0 - 14, x0 + n + 10, 100, Z0 + 14)
    section = Section("s01", 0, n - 1, box, "world")
    r.sections = [section]
    site = make_site(tmp_path / "site", box, ground=ground if ground is not None else 64, world="world")
    return design, r, section, site


def _compose(design, r, section, site, light_spacing=None):
    """The layers of Tasks 7 and 8 merged by mode (carve, build, track, light) and applied."""
    layers = [*structures.bridge_layers(design, r, section, site, light_spacing=light_spacing)[0],
              *structures.tunnel_layers(design, r, section, site, light_spacing=light_spacing),
              *structures.stop_layers(design, r, section, site, light_spacing=light_spacing),
              *track.track_layers(design, r, section, site, light_spacing=light_spacing)]
    layers.sort(key=lambda layer: ORDER[layer[0]])
    return {section.name: blocks.apply_writes(site, layers)}


def _valley(cells, depth=12):
    return {(x, z): 64 - depth for x, _ in cells for z in range(Z0 - 14, Z0 + 15)}


def _mixed(kinds_by_run, tmp_path, **kw):
    kinds = [k for k, count in kinds_by_run for _ in range(count)]
    cells = [(5 + i, Z0) for i in range(len(kinds))]
    ground = {}
    for (x, _), kind in zip(cells, kinds, strict=True):
        for z in range(Z0 - 14, Z0 + 15):
            ground[x, z] = {"bridge": 52, "tunnel": 80}.get(kind, 64)
    return _line(tmp_path, "rail", kinds, ground=ground, **kw)


def _built(tmp_path, kind="rail-with-bridge-and-tunnel", *, light_spacing=None):
    if kind == "rail-with-bridge-and-tunnel":
        parts = _mixed([("grade", 8), ("bridge", 14), ("grade", 4), ("tunnel", 20), ("grade", 8)], tmp_path,
                       end_stop="terminus")
    elif kind == "arch":
        parts = _mixed([("grade", 4), ("bridge", 40), ("grade", 4)], tmp_path)
    elif kind == "road":
        parts = _line(tmp_path, "road", ["grade"] * 30)
    elif kind == "path":
        parts = _line(tmp_path, "path", ["grade"] * 30)
    elif kind == "ice":
        parts = _line(tmp_path, "ice", ["grade"] * 30, levels=[66] * 30)
    elif kind == "road-half":
        parts = _line(tmp_path, "road", ["grade"] * 30, levels=[65] * 15 + [65.5] * 15)
    elif kind == "room":
        parts = _line(tmp_path, "rail", ["grade"] * 30, end_stop="room")
    elif kind == "nether-tunnel":
        parts = _line(tmp_path, "rail", ["tunnel"] * 40, levels=[70] * 40, ground=90,
                      extra={"dimension": "nether", "world": "world_nether"})
    else:
        raise AssertionError(kind)
    design, r, section, site = parts
    return design, r, _compose(design, r, section, site, light_spacing)


def _write(sites, cells):
    site = sites["s01"]
    return {"s01": blocks.apply_writes(site, [("x", blocks.cells_write(cells))])}


def _first(r, kind, skip=0):
    return [i for i, k in enumerate(r.kinds) if k == kind][skip]


def _mutate(sites, r, design, mutation):
    site = sites["s01"]
    rails = track.rail_cells(design, r) if design.mode == "rail" else []
    plain = next((c for i, c in enumerate(rails) if not c.booster and r.kinds[i] == "grade" and 1 < i), None)
    if mutation == "remove_rail":
        return _write(sites, {(plain.x, plain.y, plain.z): "minecraft:air"})
    if mutation == "remove_redstone_block":
        c = next(c for c in rails if c.booster)
        return _write(sites, {(c.x, c.y - 1, c.z): STONE})
    if mutation == "air_under_rail":
        return _write(sites, {(plain.x, plain.y - 1, plain.z): "minecraft:air"})
    if mutation == "stone_over_rail":
        return _write(sites, {(plain.x, plain.y + 1, plain.z): STONE})
    if mutation == "raise_rail":
        return _write(sites, {(plain.x, plain.y, plain.z): "minecraft:air",
                              (plain.x, plain.y + 1, plain.z): f"minecraft:rail[shape={plain.shape}]"})
    if mutation == "remove_piers":
        piers = set(design.palette["pier"])
        x1, y1, z1, x2, y2, z2 = site.box
        gone = {(x, y, z): "minecraft:air" for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)
                for y in range(y1, y2 + 1) if base_id(site.block(x, y, z)) in piers
                and any(r.kinds[i] == "bridge" and r.cells[i][0] == x for i in range(len(r.cells)))}
        assert gone
        return _write(sites, gone)
    if mutation == "lava_beside_bore":
        i = _first(r, "tunnel", 8)
        x, z = r.cells[i]
        return _write(sites, {(x, math.ceil(r.levels[i]) + 1, z + 2): LAVA})
    if mutation == "remove_lights":
        gone = {}
        for (x, z), runs in site.columns.items():
            for lo, hi, state in runs:
                if base_id(state) in design.palette["lamp"] or base_id(state) == design.lights.block:
                    gone.update({(x, y, z): "minecraft:air" for y in range(lo, hi + 1)})
        assert gone
        return _write(sites, gone)
    if mutation == "two_block_step":
        x, z = r.cells[10]
        base = math.floor(r.levels[10])
        return _write(sites, {(x, base, z): STONE, (x, base + 1, z): STONE})
    raise AssertionError(mutation)


def _failed(report):
    return {c["name"]: c for c in report["checks"] if not c["ok"]}


# ------------------------------------------------------------------ generated lines pass
def test_generated_line_passes_every_check(tmp_path):
    design, r, sites = _built(tmp_path, kind="rail-with-bridge-and-tunnel")
    report = transit_checks.check_line(design, r, sites)
    assert report["ok"], report
    assert [c["name"] for c in report["checks"]] == [
        "continuity", "support", "boosters", "clearance", "light", "deck", "seal", "grade"]


def test_an_arch_bridge_passes_the_deck_check(tmp_path):
    design, r, sites = _built(tmp_path, kind="arch", light_spacing=8)   # 12 leaves the far end dark
    report = transit_checks.check_line(design, r, sites)
    assert report["ok"], report
    assert any(c["name"] == "deck" for c in report["checks"])


@pytest.mark.parametrize(("kind", "names"), [
    pytest.param("road", ["support", "clearance", "walk", "light", "grade"], id="road"),
    pytest.param("path", ["support", "clearance", "walk", "light", "grade"], id="path"),
    pytest.param("ice", ["support", "clearance", "light", "grade"], id="ice"),
])
def test_other_modes_pass_with_their_checks(tmp_path, kind, names):
    design, r, sites = _built(tmp_path, kind=kind)
    report = transit_checks.check_line(design, r, sites)
    assert report["ok"], report
    assert [c["name"] for c in report["checks"]] == names


# ------------------------------------------------------------------ each check fails on its mutation
@pytest.mark.parametrize(("check", "mutation"), [
    pytest.param("continuity", "remove_rail", id="missing-rail"),
    pytest.param("boosters", "remove_redstone_block", id="booster-without-block"),
    pytest.param("support", "air_under_rail", id="floating-rail"),
    pytest.param("clearance", "stone_over_rail", id="blocked-rail"),
    pytest.param("deck", "remove_piers", id="deck-without-piers"),
    pytest.param("seal", "lava_beside_bore", id="lava-beside-bore"),
    pytest.param("grade", "raise_rail", id="rail-off-level"),
    pytest.param("light", "remove_lights", id="dark-floor"),
])
def test_each_check_fails_on_its_mutation(tmp_path, check, mutation):
    design, r, sites = _built(tmp_path, kind="rail-with-bridge-and-tunnel")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, mutation))
    failed = _failed(report)
    assert not report["ok"]
    assert check in failed
    assert 0 < len(failed[check]["cells"]) <= 10
    assert all(len(c) == 3 for c in failed[check]["cells"])


def test_the_failing_cell_is_the_mutated_one(tmp_path):
    design, r, sites = _built(tmp_path)
    plain = next(c for i, c in enumerate(track.rail_cells(design, r)) if not c.booster and i > 1
                 and r.kinds[i] == "grade")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, "remove_rail"))
    assert _failed(report)["continuity"]["cells"] == [[plain.x, plain.y, plain.z]]


def test_walk_fails_on_a_two_block_step(tmp_path):
    design, r, sites = _built(tmp_path, kind="road")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, "two_block_step"))
    assert "walk" in _failed(report)


def test_a_path_may_step_a_block_but_not_two(tmp_path):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10]
    one = _write(sites, {(x, 65, z): STONE})
    assert "walk" not in _failed(transit_checks.check_line(design, r, one))
    two = _write(sites, {(x, 65, z): STONE, (x, 66, z): STONE})
    assert "walk" in _failed(transit_checks.check_line(design, r, two))


def test_failing_cells_are_capped_at_ten(tmp_path):
    design, r, sites = _built(tmp_path, kind="road")
    cells = {(r.cells[i][0], 65, r.cells[i][1]): STONE for i in range(2, 28)}
    report = transit_checks.check_line(design, r, _write(sites, cells))
    assert len(_failed(report)["clearance"]["cells"]) == 10


# ------------------------------------------------------------------ rulings
def test_properties_are_compared_not_state_strings(tmp_path):
    design, r, sites = _built(tmp_path)
    c = next(c for c in track.rail_cells(design, r) if not c.booster)
    reordered = _write(sites, {(c.x, c.y, c.z): f"minecraft:rail[waterlogged=false,shape={c.shape}]"})
    assert transit_checks.check_line(design, r, reordered)["ok"]


@pytest.mark.parametrize("below", [
    "minecraft:spruce_fence", "minecraft:stone_brick_wall", "minecraft:stone_brick_slab[type=top]",
    "minecraft:stone", "minecraft:oak_stairs[half=top,facing=north]"])
def test_a_standing_lantern_may_stand_on_posts_and_full_faces(tmp_path, below):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10][0], Z0 + 4
    cells = {(x, 64, z): below, (x, 65, z): "minecraft:lantern[hanging=false]"}
    assert "support" not in _failed(transit_checks.check_line(design, r, _write(sites, cells)))


@pytest.mark.parametrize("below", [
    "minecraft:stone_brick_slab[type=bottom]", "minecraft:air", "minecraft:oak_stairs[half=bottom]"])
def test_a_standing_lantern_fails_on_a_partial_or_missing_floor(tmp_path, below):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10][0], Z0 + 4
    cells = {(x, 64, z): below, (x, 65, z): "minecraft:lantern"}
    assert [x, 65, z] in _failed(transit_checks.check_line(design, r, _write(sites, cells)))["support"]["cells"]


def test_rails_do_not_stand_on_fences(tmp_path):
    design, r, sites = _built(tmp_path)
    c = next(c for i, c in enumerate(track.rail_cells(design, r)) if not c.booster and i > 1
             and r.kinds[i] == "grade")
    fenced = _write(sites, {(c.x, c.y - 1, c.z): "minecraft:spruce_fence"})
    assert "support" in _failed(transit_checks.check_line(design, r, fenced))


def test_a_hanging_lantern_needs_a_block_above(tmp_path):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10][0], Z0 + 4
    hung = _write(sites, {(x, 70, z): "minecraft:lantern[hanging=true]"})
    assert "support" in _failed(transit_checks.check_line(design, r, hung))
    held = _write(sites, {(x, 71, z): STONE, (x, 70, z): "minecraft:lantern[hanging=true]"})
    assert "support" not in _failed(transit_checks.check_line(design, r, held))


@pytest.mark.parametrize(("state", "spawnable"), [
    pytest.param("minecraft:stone", True, id="stone"),
    pytest.param("minecraft:gravel", True, id="gravel"),
    pytest.param("minecraft:grass_block[snowy=false]", True, id="grass"),
    pytest.param("minecraft:soul_sand", True, id="soul-sand"),
    pytest.param("minecraft:mud", True, id="mud"),
    pytest.param("minecraft:packed_ice", True, id="packed-ice"),
    pytest.param("minecraft:blue_ice", True, id="blue-ice"),
    pytest.param("minecraft:stone_slab[type=top]", True, id="top-slab"),
    pytest.param("minecraft:stone_slab[type=double]", True, id="double-slab"),
    pytest.param("minecraft:oak_stairs[half=top,facing=north]", True, id="top-stairs"),
    pytest.param("minecraft:jack_o_lantern[facing=north]", True, id="jack-o-lantern-bug"),
    pytest.param("minecraft:redstone_lamp[lit=true]", True, id="lit-lamp-bug"),
    pytest.param("minecraft:stone_slab[type=bottom]", False, id="bottom-slab"),
    pytest.param("minecraft:oak_stairs[half=bottom,facing=north]", False, id="bottom-stairs"),
    pytest.param("minecraft:white_carpet", False, id="carpet"),
    pytest.param("minecraft:glass", False, id="glass"),
    pytest.param("minecraft:tinted_glass", False, id="tinted-glass"),
    pytest.param("minecraft:red_stained_glass", False, id="stained-glass"),
    pytest.param("minecraft:bedrock", False, id="bedrock"),
    pytest.param("minecraft:barrier", False, id="barrier"),
    pytest.param("minecraft:oak_trapdoor[half=top,open=false]", False, id="trapdoor"),
    pytest.param("minecraft:chorus_flower[age=0]", False, id="chorus-flower"),
    pytest.param("minecraft:scaffolding", False, id="scaffolding"),
    pytest.param("minecraft:copper_grate", False, id="copper-grate"),
    pytest.param("minecraft:waxed_oxidized_copper_grate", False, id="waxed-copper-grate"),
    pytest.param("minecraft:oak_leaves[distance=1]", False, id="leaves"),
    pytest.param("minecraft:ice", False, id="ice"),
    pytest.param("minecraft:frosted_ice[age=0]", False, id="frosted-ice"),
    pytest.param("minecraft:glowstone", False, id="emits-15"),
    pytest.param("minecraft:shroomlight", False, id="shroomlight"),
    pytest.param("minecraft:sea_lantern", False, id="sea-lantern"),
    pytest.param("minecraft:air", False, id="air"),
    pytest.param("minecraft:water[level=0]", False, id="water"),
    pytest.param("minecraft:spruce_fence", False, id="fence"),
])
def test_spawnable_floor(state, spawnable):
    assert transit_checks.spawnable_floor(state) is spawnable


def test_a_rail_cell_is_exempt_from_the_light_check(tmp_path):
    design, r, sites = _built(tmp_path, kind="rail-with-bridge-and-tunnel")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, "remove_lights"))
    rails = {(c.x, c.y, c.z) for c in track.rail_cells(design, r)}
    assert not rails & {tuple(c) for c in _failed(report)["light"]["cells"]}


def test_nether_tunnel_needs_light_twelve(tmp_path):
    design, r, sites = _built(tmp_path, kind="nether-tunnel", light_spacing=12)
    assert design.lights.minimum == 12
    report = transit_checks.check_line(design, r, sites)
    assert "light" in _failed(report)


def test_the_same_tunnel_with_a_minimum_of_one_passes_the_light_check(tmp_path):
    design, r, sites = _built(tmp_path, kind="nether-tunnel", light_spacing=12)
    design = td.parse_line({**design.source, "lights": {"min": 1}}, tmp_path)
    assert "light" not in _failed(transit_checks.check_line(design, r, sites))


# ------------------------------------------------------------------ fix round 1: coverage and owners
def _cropped(site, x2):
    """The site cut off after column x2."""
    box = (*site.box[:3], x2, *site.box[4:])
    return Site(box=box, world=site.world, columns={k: v for k, v in site.columns.items() if k[0] <= x2})


def test_a_section_without_a_site_is_an_error_naming_it(tmp_path):
    design, r, _ = _built(tmp_path)
    with pytest.raises(ValueError, match="no site for section s01"):
        transit_checks.check_line(design, r, {})


def test_every_missing_section_is_named(tmp_path):
    design, r, sites = _built(tmp_path)
    r.sections = [Section("s01", 0, 20, r.sections[0].box, "world"), Section("s02", 21, 53, r.sections[0].box, "world"),
                  Section("s03", 54, 53, r.sections[0].box, "world")]
    with pytest.raises(ValueError, match="s02, s03"):
        transit_checks.check_line(design, r, sites)


@pytest.mark.parametrize(("kind", "check"), [("rail-with-bridge-and-tunnel", "continuity"), ("road", "clearance")])
def test_a_site_that_misses_part_of_the_line_fails_naming_the_uncovered_cells(tmp_path, kind, check):
    design, r, sites = _built(tmp_path, kind=kind)
    report = transit_checks.check_line(design, r, {"s01": _cropped(sites["s01"], 20)})
    failed = _failed(report)[check]
    assert "not covered by any site" in failed["detail"]
    assert 0 < len(failed["cells"]) <= 10
    assert all(c[0] > 20 for c in failed["cells"])
    assert not report["ok"]


def _two_sections(tmp_path):
    """A road read as sections a (0-14) and b (15-29), each with its own copy of the site."""
    design, r, sites = _built(tmp_path, kind="road")
    box = r.sections[0].box
    r.sections = [Section("a", 0, 14, box, "world"), Section("b", 15, 29, box, "world")]
    return design, r, sites["s01"]


def _block_at(site, r, i):
    x, z = r.cells[i]
    return blocks.apply_writes(site, [("x", blocks.cells_write({(x, 65, z): STONE}))])


def test_a_cell_is_read_from_the_site_of_its_own_section(tmp_path):
    design, r, clear = _two_sections(tmp_path)
    # Section a's site is blocked at index 20, which b owns and b's site leaves clear: no failure.
    report = transit_checks.check_line(design, r, {"a": _block_at(clear, r, 20), "b": clear})
    assert "clearance" not in _failed(report)
    # The same block at index 5, owned by a, fails.
    report = transit_checks.check_line(design, r, {"a": _block_at(clear, r, 5), "b": clear})
    x, z = r.cells[5]
    assert [x, 65, z] in _failed(report)["clearance"]["cells"]
    # And a block only in b's site at an index a owns is ignored.
    report = transit_checks.check_line(design, r, {"a": clear, "b": _block_at(clear, r, 5)})
    assert "clearance" not in _failed(report)


def test_a_boundary_cell_falls_back_to_another_site(tmp_path):
    design, r, clear = _two_sections(tmp_path)
    short = _cropped(clear, r.cells[10][0])      # a's own read ends before index 11
    report = transit_checks.check_line(design, r, {"a": short, "b": _block_at(clear, r, 12)})
    x, z = r.cells[12]
    assert [x, 65, z] in _failed(report)["clearance"]["cells"]


# ------------------------------------------------------------------ fix round 1: support and more behaviour
@pytest.mark.parametrize("block", ["minecraft:sea_lantern", "minecraft:jack_o_lantern[facing=north]"])
def test_full_cube_lantern_blocks_need_no_floor(tmp_path, block):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10][0], Z0 + 4
    cells = {(x, 70, z): block}
    assert "support" not in _failed(transit_checks.check_line(design, r, _write(sites, cells)))


def test_a_copper_lantern_still_needs_a_floor(tmp_path):
    design, r, sites = _built(tmp_path, kind="path")
    x, z = r.cells[10][0], Z0 + 4
    report = transit_checks.check_line(design, r, _write(sites, {(x, 70, z): "minecraft:copper_lantern"}))
    assert [x, 70, z] in _failed(report)["support"]["cells"]


def test_a_powered_rail_on_a_corner_fails_boosters(tmp_path):
    design, r, sites = _built(tmp_path)
    c = next(c for i, c in enumerate(track.rail_cells(design, r)) if not c.booster and i > 1 and r.kinds[i] == "grade")
    corner = _write(sites, {(c.x, c.y, c.z): "minecraft:powered_rail[powered=true,shape=north_east]"})
    assert [c.x, c.y, c.z] in _failed(transit_checks.check_line(design, r, corner))["boosters"]["cells"]


@pytest.mark.parametrize(("kind", "cells"), [
    pytest.param("road", lambda x, z: {(x, 65, z): STONE}, id="road"),
    pytest.param("path", lambda x, z: {(x, 65, z): STONE}, id="path"),
    pytest.param("ice", lambda x, z: {(x, 65, z): STONE}, id="ice"),
])
def test_grade_fails_on_a_raised_surface(tmp_path, kind, cells):
    design, r, sites = _built(tmp_path, kind=kind)
    x, z = r.cells[10]
    report = transit_checks.check_line(design, r, _write(sites, cells(x, z)))
    assert "grade" in _failed(report)


def test_seal_fails_beside_a_tube(tmp_path):
    design, r, sites = _built(tmp_path, kind="nether-tunnel")
    r.kinds[5:25] = ["tube"] * 20
    assert "seal" not in _failed(transit_checks.check_line(design, r, sites))
    x, z = r.cells[15]
    report = transit_checks.check_line(design, r, _write(sites, {(x, 71, z + 2): LAVA}))
    assert [x, 71, z + 2] in _failed(report)["seal"]["cells"]


def test_a_room_stop_is_lit_in_the_overworld(tmp_path):
    design, r, sites = _built(tmp_path, kind="room")
    report = transit_checks.check_line(design, r, sites)
    assert report["ok"], report
    assert any(c["name"] == "seal" for c in report["checks"])


def test_a_dark_room_cell_fails_light(tmp_path, monkeypatch):
    monkeypatch.setattr(transit_checks, "MAX_CELLS", 10_000)     # the room is the last cells, past the cap
    design, r, sites = _built(tmp_path, kind="room")
    end_x, end_z = r.cells[-1]
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, "remove_lights"))
    assert any(abs(c[0] - end_x) <= 2 and abs(c[2] - end_z) <= 2 for c in _failed(report)["light"]["cells"])


def test_a_road_half_step_of_exactly_half_a_block_passes_walk(tmp_path):
    design, r, sites = _built(tmp_path, kind="road-half")
    report = transit_checks.check_line(design, r, sites)
    assert "walk" not in _failed(report), report
    assert any(c["name"] == "walk" for c in report["checks"])


# ------------------------------------------------------------------ one section on its own
def test_check_line_can_check_one_section_on_its_own(tmp_path):
    design, r, clear = _two_sections(tmp_path)
    blocked = _block_at(clear, r, 20)                       # a block on b's part of the road
    # a on its own needs only a's site and ignores b's cells, here and beyond the boundary.
    assert transit_checks.check_line(design, r, {"a": blocked}, sections=["a"])["ok"]
    # b on its own fails on the block.
    x, z = r.cells[20]
    report = transit_checks.check_line(design, r, {"b": blocked}, sections=["b"])
    assert [x, 65, z] in _failed(report)["clearance"]["cells"]
    # Without the limit every section needs its site, as before.
    with pytest.raises(ValueError, match="no site for section b"):
        transit_checks.check_line(design, r, {"a": blocked})
    with pytest.raises(ValueError, match="no site for section a"):
        transit_checks.check_line(design, r, {"b": blocked}, sections=["a", "b"])
    with pytest.raises(ValueError, match="no route section c"):
        transit_checks.check_line(design, r, {"a": blocked}, sections=["c"])


def test_a_limited_check_counts_only_the_cells_of_its_sections(tmp_path):
    design, r, clear = _two_sections(tmp_path)
    whole = {c["name"]: c["detail"] for c in transit_checks.check_line(design, r, {"a": clear, "b": clear})["checks"]}
    part = {c["name"]: c["detail"] for c in
            transit_checks.check_line(design, r, {"a": clear}, sections=["a"])["checks"]}
    assert whole["clearance"] == "90 checked" and part["clearance"] == "45 checked"
