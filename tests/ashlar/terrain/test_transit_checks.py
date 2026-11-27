from __future__ import annotations

import math

import pytest
from sitegen import STONE, make_site
from terrain import blocks, structures, track, transit_checks
from terrain import transit_design as td
from terrain.route import Route, Section
from terrain.site import base_id

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
