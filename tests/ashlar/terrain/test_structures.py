from __future__ import annotations

import math
from itertools import pairwise

import pytest
from sitegen import STONE, WATER, make_site
from terrain import blocks, route, structures, track, transit_checks
from terrain import transit_design as td
from terrain.route import Route, Section
from terrain.site import base_id

PLANKS = "minecraft:oak_planks"
CAVE_AIR = "minecraft:cave_air"
NETHERRACK = "minecraft:netherrack"
LAVA = "minecraft:lava[level=0]"
Z0 = 20


def _build(tmp_path, cells, levels, kinds, *, mode="rail", extra=None, start_stop=None, end_stop=None,
           site_cells=None, ground=64, water=None, y_box=(40, 100)):
    """A design, a route along `cells`, one section covering it and a site over its box."""
    n = len(cells)
    nether = (extra or {}).get("dimension") == "nether"
    y = int(levels[0]) if nether else None
    data = {"element": "t", "seed": 7, "world": "world", "mode": mode, "route": "straight",
            "from": {"at": [cells[0][0], y, cells[0][1]], "stop": start_stop},
            "to": {"at": [cells[-1][0], y, cells[-1][1]], "stop": end_stop}}
    data.update(extra or {})
    design = td.parse_line(data, tmp_path)
    r = Route("t", mode, "world", design.dimension, "h", list(cells), [float(v) for v in levels],
              list(kinds), [None] * n, [None] * n, [], [])
    xs, zs = [c[0] for c in cells], [c[1] for c in cells]
    box = (min(xs) - 10, y_box[0], min(zs) - 10, max(xs) + 10, y_box[1], max(zs) + 10)
    section = Section("s01", 0, n - 1, box, "world")
    r.sections = [section]
    site = make_site(tmp_path / "site", box, ground=ground, water=water, cells=site_cells, world="world")
    return design, r, section, site


def _row(length, x0=5):
    return [(x0 + k, Z0) for k in range(length)]


def _valley_bridge(tmp_path, length=12, depth=12, *, cells=None, extra=None, level=65):
    line = _row(length)
    ground = {(x, z): 64 - depth for x, _ in line for z in range(Z0 - 12, Z0 + 13)}
    return _build(tmp_path, line, [level] * length, ["bridge"] * length, extra=extra, site_cells=cells,
                  ground=ground)


def _under_deck(after, r, i, level=65):
    x, z = r.cells[i]
    return base_id(after.block(x, level - 2, z))


def _pier_indices(after, r, design):
    return [i for i in range(len(r.cells)) if _under_deck(after, r, i) in design.palette["pier"]]


def _bridge_kind(tmp_path, length):
    design, r, section, site = _valley_bridge(tmp_path, length=length)
    after = blocks.apply_writes(site, structures.bridge_layers(design, r, section, site)[0])
    return "arch" if _under_deck(after, r, length // 2) in design.palette["pier"] else "beam"


def _lake_bridge(tmp_path, piers_in_water):
    line = _row(12)
    wet = {(x, z): 62 for x, _ in line for z in range(Z0 - 12, Z0 + 13)}
    bed = {(x, y, z): STONE for (x, z) in wet for y in range(40, 50)}
    return _build(tmp_path, line, [65] * 12, ["bridge"] * 12, water=wet, site_cells=bed,
                  extra={"bridges": {"piers_in_water": piers_in_water}})


def _hill_tunnel(tmp_path, cells=None, *, kinds=None, extra=None, length=30):
    line = _row(length)
    return _build(tmp_path, line, [65] * length, kinds or ["tunnel"] * length, site_cells=cells, ground=80,
                  extra=extra)


def _wall_cells(r, a, b):
    return [track.side_cell(r, i, off) for i in range(a, b + 1) for off in (-2, 2)]


def _nether_line(tmp_path, cavern=None, lava_at=None, *, cavern_floor=60, host=None):
    line = [(x, 1) for x in range(40)]
    cells = {}
    if host:
        cells.update({(x, y, z): host for x in range(-2, 42) for z in range(-5, 8) for y in range(55, 90)})
    for x in cavern or ():
        cells.update({(x, y, z): "minecraft:air" for z in range(-6, 9) for y in range(cavern_floor, 80)})
    if lava_at:
        cells[lava_at] = LAVA
    return _build(tmp_path, line, [70] * 40, ["tunnel"] * 40, site_cells=cells, ground=90,
                  extra={"dimension": "nether", "world": "world_nether"})


def _rail_line_with_terminus(tmp_path, stop="terminus", length=40):
    line = _row(length, 0)
    return _build(tmp_path, line, [65] * length, ["grade"] * length, end_stop=stop)


def _one_past_end(r):
    x, z = r.cells[-1]
    dx, dz = track.heading(r, len(r.cells) - 1)
    return x + dx, round(r.levels[-1]), z + dz


# ------------------------------------------------------------------ bridges
def test_beam_bridge_piers_reach_ground_at_most_spacing_apart(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=12, depth=12)
    layers, stats = structures.bridge_layers(design, r, section, site)
    piers = _pier_indices(blocks.apply_writes(site, layers), r, design)
    assert piers[0] == 0
    assert piers[-1] == 11
    assert max(b - a for a, b in pairwise(piers)) <= 8
    assert stats["piers"] == len(piers)


def test_beam_piers_stand_on_the_ground_without_a_gap(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=12, depth=12)
    after = blocks.apply_writes(site, structures.bridge_layers(design, r, section, site)[0])
    x, z = r.cells[8]
    assert all(base_id(after.block(x, y, z)) in design.palette["pier"] for y in range(53, 64))
    assert after.block(x, 52, z) == site.block(x, 52, z)


def test_deck_railings_and_lamps_follow_the_level(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=12, depth=12)
    after = blocks.apply_writes(site, structures.bridge_layers(design, r, section, site, light_spacing=4)[0])
    x, z = r.cells[2]
    assert all(base_id(after.block(x, 64, z + off)) in design.palette["deck"] for off in range(-2, 3))
    assert base_id(after.block(x, 65, z + 2)) in design.palette["railing"]
    assert base_id(after.block(x, 65, z - 2)) in design.palette["railing"]
    assert after.block(x, 65, z) == "minecraft:air"
    heads = [base_id(after.block(r.cells[i][0], 67, r.cells[i][1] + off)) for i in (4, 8) for off in (-2, 2)]
    assert set(heads) & set(design.palette["lamp"])
    assert base_id(after.block(r.cells[4][0], 66, r.cells[4][1] - 2)) in design.palette["lamp_post"]


def test_deck_leaves_a_boosters_redstone_block_alone(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=12, depth=12)
    boosters = [c for c in track.rail_cells(design, r) if c.booster]
    assert boosters
    after = blocks.apply_writes(site, structures.bridge_layers(design, r, section, site)[0])
    for c in boosters:
        assert after.block(c.x, c.y - 1, c.z) == site.block(c.x, c.y - 1, c.z)


def test_auto_picks_beam_up_to_16_and_arches_above(tmp_path):
    assert _bridge_kind(tmp_path / "a", length=14) == "beam"
    assert _bridge_kind(tmp_path / "b", length=30) == "arch"


def test_arch_spans_stay_under_40_cells_and_leave_an_opening(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=70, depth=14)
    layers, stats = structures.bridge_layers(design, r, section, site)
    after = blocks.apply_writes(site, layers)
    piers = [i for i, (x, z) in enumerate(r.cells) if base_id(after.block(x, 52, z)) in design.palette["pier"]]
    assert stats["piers"] == math.ceil(70 / 32) + 1
    assert piers[0] == 0
    assert piers[-1] == 69
    assert max(b - a for a, b in pairwise(piers)) <= 40
    mid = (piers[0] + piers[1]) // 2
    x, z = r.cells[mid]
    assert after.block(x, 63, z) != "minecraft:air"
    assert after.block(x, 55, z) == "minecraft:air"


def test_a_bridge_over_ground_above_the_deck_gets_zero_height_piers(tmp_path):
    line = _row(10)
    design, r, section, site = _build(tmp_path, line, [65] * 10, ["bridge"] * 10, ground=70)
    layers, stats = structures.bridge_layers(design, r, section, site)
    after = blocks.apply_writes(site, layers)
    assert stats["piers"] == 3
    assert all(after.block(x, 60, z) == site.block(x, 60, z) for x, z in r.cells)


def test_piers_in_still_water_need_the_flag(tmp_path):
    with pytest.raises(route.RouteError, match="piers_in_water"):
        structures.bridge_layers(*_lake_bridge(tmp_path, piers_in_water=False))


def test_piers_in_still_water_are_counted_with_the_flag(tmp_path):
    design, r, section, site = _lake_bridge(tmp_path, piers_in_water=True)
    layers, stats = structures.bridge_layers(design, r, section, site)
    assert stats["displaced_water"] > 0
    x, z = r.cells[0]
    assert base_id(blocks.apply_writes(site, layers).block(x, 55, z)) in design.palette["pier"]


def test_flowing_water_under_a_pier_is_refused(tmp_path):
    x, z = _row(12)[0]
    with pytest.raises(route.RouteError, match=rf"\({x}, 58, {z}\)"):
        structures.bridge_layers(*_valley_bridge(
            tmp_path, cells={(x, 58, z): "minecraft:water[level=3]"}, extra={"bridges": {"piers_in_water": True}}))


def test_lava_under_a_pier_is_refused_even_with_the_flag(tmp_path):
    x, z = _row(12)[0]
    with pytest.raises(route.RouteError, match=rf"\({x}, 58, {z}\)"):
        structures.bridge_layers(*_valley_bridge(
            tmp_path, cells={(x, 58, z): LAVA}, extra={"bridges": {"piers_in_water": True}}))


# ------------------------------------------------------------------ tunnels
def test_tunnel_bore_is_air_lined_and_lit(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    x, z = r.cells[10]
    assert all(after.block(x, y, z) == "minecraft:air" for y in range(65, 69))
    assert any(after.block(x2, 66, z2) == design.lights.block for x2, z2 in _wall_cells(r, 6, 18))
    assert base_id(after.block(x, 64, z)) in design.palette["lining"]
    assert base_id(after.block(x, 69, z + 1)) in design.palette["lining"]
    assert base_id(after.block(x, 67, z - 2)) in design.palette["lining"]


def test_tunnel_mouths_use_the_edge_block(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    x, z = r.cells[0]
    assert base_id(after.block(x, 67, z + 2)) in design.palette["edge"]
    assert "type=double" in after.block(x, 67, z + 2)


def test_lining_keeps_built_blocks_and_seals_cave_air(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path, cells={(10, 66, 22): PLANKS, (12, 66, 22): CAVE_AIR})
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    assert after.block(10, 66, 22) == PLANKS
    assert after.block(12, 66, 22) != CAVE_AIR


@pytest.mark.parametrize("liquid", [WATER, LAVA])
@pytest.mark.parametrize("cell", [(10, 67, 22), (10, 66, 20)])
def test_tunnel_refuses_liquid_in_the_shell_or_bore(tmp_path, liquid, cell):
    design, r, section, site = _hill_tunnel(tmp_path, cells={cell: liquid})
    with pytest.raises(route.RouteError, match=rf"\({cell[0]}, {cell[1]}, {cell[2]}\)"):
        structures.tunnel_layers(design, r, section, site, light_spacing=6)


def test_netherrack_is_host_rock_in_the_nether(tmp_path):
    design, r, section, site = _nether_line(tmp_path, host=NETHERRACK)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=4))
    assert all(after.block(10, y, 1) == "minecraft:air" for y in range(70, 74))
    assert base_id(after.block(10, 74, 1)) in design.palette["lining"]


def test_nether_kinds_tunnel_tube_and_lava(tmp_path):
    design, r, section, site = _nether_line(tmp_path, cavern=range(20, 30))
    kinds = structures.nether_kinds(design, r, section, site)
    assert set(kinds[20:30]) == {"tube"}
    assert kinds[5] == "tunnel"
    design, r, section, site = _nether_line(tmp_path / "lava", lava_at=(15, 70, 1))
    with pytest.raises(route.RouteError, match=r"\(15, 70, 1\)"):
        structures.nether_kinds(design, r, section, site)


def test_a_tube_builds_every_shell_cell_and_stands_on_piers(tmp_path):
    design, r, section, site = _nether_line(tmp_path, cavern=range(20, 30))
    r.kinds = structures.nether_kinds(design, r, section, site)
    layers = structures.tunnel_layers(design, r, section, site, light_spacing=4)
    after = blocks.apply_writes(site, layers)
    assert base_id(after.block(25, 69, 1)) in design.palette["deck"]
    assert base_id(after.block(25, 74, 1)) in design.palette["lining"]
    assert base_id(after.block(25, 72, 3)) in design.palette["lining"]
    _, stats = structures.bridge_layers(design, r, section, site)
    assert stats["piers"] > 0
    assert stats["unsupported_tube"] == 0


def test_a_tube_over_a_void_counts_unsupported_piers(tmp_path):
    design, r, section, site = _nether_line(tmp_path, cavern=range(20, 30), cavern_floor=41)
    r.kinds = structures.nether_kinds(design, r, section, site)
    layers, stats = structures.bridge_layers(design, r, section, site)
    assert layers == []
    assert stats["unsupported_tube"] > 0
    assert stats["piers"] == 0


# ------------------------------------------------------------------ stops
def test_terminus_end_block_and_platform(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path)
    after = blocks.apply_writes(site, structures.stop_layers(design, r, section, site, light_spacing=12))
    end = _one_past_end(r)
    assert base_id(after.block(*end)) in design.palette["end_block"]
    assert all(base_id(after.block(x, 65, Z0 + off)) in design.palette["platform"]
               for x in range(32, 40) for off in (-2, -1))
    assert base_id(after.block(39, 68, Z0 - 2)) in design.palette["lamp"]
    assert after.block(31, 65, Z0 - 1) == site.block(31, 65, Z0 - 1)
    assert after.block(35, 65, Z0 + 1) == site.block(35, 65, Z0 + 1)


def test_open_stop_adds_nothing(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path, stop="open")
    assert structures.stop_layers(design, r, section, site, light_spacing=12) == []


def test_a_room_is_lined_and_lit(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path, stop="room")
    after = blocks.apply_writes(site, structures.stop_layers(design, r, section, site, light_spacing=12))
    assert all(after.block(x, y, z) == "minecraft:air" for x in range(37, 42) for z in range(18, 23)
               for y in range(66, 69))
    assert base_id(after.block(42, 66, 20)) in design.palette["lining"]
    assert base_id(after.block(40, 69, 20)) in design.palette["lining"]
    assert after.block(40, 66, 17) != site.block(40, 66, 17)
    assert after.block(36, 66, 20) == "minecraft:air"
    lit = [(x, y, z) for x in range(36, 43) for y in range(64, 71) for z in range(17, 24)
           if after.block(x, y, z) == design.lights.block]
    assert len(lit) >= 4


def test_a_room_keeps_built_blocks(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path, stop="room")
    walled = {(42, 66, 20): PLANKS}
    site = make_site(tmp_path / "keep", site.box, ground=64, cells=walled, world="world")
    after = blocks.apply_writes(site, structures.stop_layers(design, r, section, site, light_spacing=12))
    assert after.block(42, 66, 20) == PLANKS


# ------------------------------------------------------------------ fix round 1
def test_tube_piers_are_contiguous_from_the_floor_to_the_ground(tmp_path):
    design, r, section, site = _nether_line(tmp_path, cavern=range(20, 30))
    r.kinds = structures.nether_kinds(design, r, section, site)
    layers, stats = structures.bridge_layers(design, r, section, site)
    after = blocks.apply_writes(site, layers)
    assert stats["piers"] > 0
    for x in (20, 28, 29):
        assert all(base_id(after.block(x, y, 1)) in design.palette["pier"] for y in range(60, 69))
        assert after.block(x, 59, 1) == site.block(x, 59, 1)


@pytest.mark.parametrize("kind", ["beam", "arch"])
def test_a_bridge_across_a_section_boundary_emits_each_sections_own_cells(tmp_path, kind):
    line = _row(30)
    ground = {(x, z): 52 for x in range(-5, 45) for z in range(Z0 - 12, Z0 + 13)}
    design, r, _, _ = _build(tmp_path / "full", line, [65] * 30, ["bridge"] * 30, ground=ground,
                             extra={"bridges": {"kind": kind}})
    r.ground = [52.0] * 30
    sections = [Section("s01", 0, 14, (2, 40, Z0 - 4, 21, 100, Z0 + 4), "world"),
                Section("s02", 15, 29, (19, 40, Z0 - 4, 38, 100, Z0 + 4), "world")]
    r.sections = sections
    after_all = None
    stats_all = []
    for k, sec in enumerate(sections):
        site = make_site(tmp_path / f"s{k}", sec.box, ground={(x, z): 52 for x in range(-5, 45)
                                                               for z in range(Z0 - 12, Z0 + 13)}, world="world")
        layers, stats = structures.bridge_layers(design, r, sec, site)
        stats_all.append(stats["piers"])
        for _, w in layers:
            ox, _, _ = w.origin
            assert ox >= sec.box[0]
            assert ox + w.codes.shape[0] - 1 <= sec.box[3]
        after_all = layers if after_all is None else [*after_all, *layers]
    assert stats_all[0] >= 1
    assert stats_all[1] >= 1
    full = make_site(tmp_path / "all", (2, 40, Z0 - 4, 38, 100, Z0 + 4), ground=52, world="world")
    after = blocks.apply_writes(full, after_all)
    x0, x1 = r.cells[0][0], r.cells[-1][0]
    assert all(base_id(after.block(x, 63, Z0)) in design.palette["pier"] for x in (x0, x1)) or kind == "beam"
    assert all(base_id(after.block(x0, y, Z0)) in design.palette["pier"] for y in range(53, 64))
    assert all(base_id(after.block(x1, y, Z0)) in design.palette["pier"] for y in range(53, 64))


def test_a_one_cell_arch_run_is_a_beam(tmp_path):
    design, r, section, site = _build(tmp_path, [(5, Z0)], [65], ["bridge"], ground=52,
                                      extra={"bridges": {"kind": "arch"}})
    _, stats = structures.bridge_layers(design, r, section, site)
    assert stats["piers"] == 1


@pytest.mark.parametrize("below", ["minecraft:crimson_roots", "minecraft:weeping_vines[age=3]",
                                   "minecraft:oak_slab[type=bottom,waterlogged=false]"])
def test_plants_and_partial_blocks_are_not_pier_ground(tmp_path, below):
    x, z = _row(12)[0]
    design, r, section, site = _valley_bridge(tmp_path, cells={(x, 58, z): below})
    after = blocks.apply_writes(site, structures.bridge_layers(design, r, section, site)[0])
    assert all(base_id(after.block(x, y, z)) in design.palette["pier"] for y in range(53, 64))


def test_the_mouth_is_only_where_a_neighbour_is_neither_tunnel_nor_tube(tmp_path):
    kinds = ["tunnel"] * 15 + ["tube"] * 15
    design, r, section, site = _hill_tunnel(tmp_path, kinds=kinds)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=50))
    for i in (14, 15):
        x, z = r.cells[i]
        assert "type=double" not in after.block(x, 67, z + 2)
    for i in (0, 29):
        x, z = r.cells[i]
        assert "type=double" in after.block(x, 67, z + 2)


def _half_road_tunnel(tmp_path):
    line = _row(30)
    return _build(tmp_path, line, [65.5] * 30, ["tunnel"] * 30, mode="road", ground=80)


@pytest.mark.parametrize("tunnel_first", [True, False])
def test_a_half_level_road_slab_survives_in_either_order(tmp_path, tunnel_first):
    design, r, section, site = _half_road_tunnel(tmp_path)
    tun = structures.tunnel_layers(design, r, section, site, light_spacing=50)
    road = track.track_layers(design, r, section, site)
    after = blocks.apply_writes(site, [*tun, *road] if tunnel_first else [*road, *tun])
    x, z = r.cells[10]
    assert "_slab" in after.block(x, 65, z)
    assert base_id(after.block(x, 64, z)) in design.palette["surface"]
    assert all(after.block(x, y, z) == "minecraft:air" for y in range(66, 70))


# ------------------------------------------------------------------ follow-up 1: Nether light
_ORDER = {"carve": 0, "build": 1, "track": 2, "light": 3}
_NETHER = {"dimension": "nether", "world": "world_nether"}


def _composed(design, r, section, site, spacing=None):
    layers = [*structures.bridge_layers(design, r, section, site, light_spacing=spacing)[0],
              *structures.tunnel_layers(design, r, section, site, light_spacing=spacing),
              *structures.stop_layers(design, r, section, site, light_spacing=spacing),
              *track.track_layers(design, r, section, site, light_spacing=spacing)]
    layers.sort(key=lambda layer: _ORDER[layer[0]])
    return {section.name: blocks.apply_writes(site, layers)}


def _light_check(design, r, sites):
    return next(c for c in transit_checks.check_line(design, r, sites)["checks"] if c["name"] == "light")


def test_a_nether_rail_tunnel_is_lit_to_twelve(tmp_path):
    line = _row(40)
    design, r, section, site = _build(tmp_path, line, [70] * 40, ["tunnel"] * 40, ground=90, extra=_NETHER)
    assert design.lights.spacing == 4
    check = _light_check(design, r, _composed(design, r, section, site))
    assert check["ok"], check


def test_a_nether_ice_tunnel_is_lit_to_twelve(tmp_path):
    line = _row(40)
    design, r, section, site = _build(tmp_path, line, [70] * 40, ["tunnel"] * 40, mode="ice", ground=90,
                                      extra=_NETHER)
    check = _light_check(design, r, _composed(design, r, section, site, 2))
    assert check["ok"], check


def test_a_nether_room_is_lit_to_twelve(tmp_path, monkeypatch):
    monkeypatch.setattr(transit_checks, "MAX_CELLS", 10_000)
    line = _row(14)
    design, r, section, site = _build(tmp_path, line, [65] * 14, ["grade"] * 14, end_stop="room",
                                      extra=_NETHER)
    check = _light_check(design, r, _composed(design, r, section, site, 4))
    x_end = r.cells[-1][0]
    room = {tuple(c) for c in check["cells"] if abs(c[0] - x_end) <= 2 and abs(c[2] - Z0) <= 2}
    assert not room


def test_the_overworld_tunnel_keeps_alternating_single_lamps(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    x, z = r.cells[12]
    assert after.block(x, 66, z + 2) == design.lights.block
    assert after.block(x, 66, z - 2) != design.lights.block


def test_the_nether_style_lamp_is_a_lantern(tmp_path):
    design = _nether_line(tmp_path)[0]
    assert design.palette["lamp"] == {"minecraft:lantern": 1}


@pytest.mark.parametrize(("state", "dimension", "ground"), [
    ("minecraft:stone", "overworld", True),
    ("minecraft:oak_leaves[distance=1,persistent=false]", "overworld", False),
    ("minecraft:short_grass", "overworld", False),
    ("minecraft:water[level=0]", "overworld", False),
    ("minecraft:air", "overworld", False),
    ("minecraft:oak_planks", "overworld", True),
    ("minecraft:oak_slab[type=bottom,waterlogged=false]", "overworld", False),
    ("minecraft:netherrack", "nether", True),
    ("minecraft:basalt[axis=y]", "nether", True),
    ("minecraft:crimson_roots", "nether", False),
    ("minecraft:weeping_vines[age=3]", "nether", False),
    ("minecraft:lava[level=0]", "nether", False),
])
def test_pier_ground(state, dimension, ground):
    assert structures.pier_ground(state, dimension) is ground
