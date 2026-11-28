from __future__ import annotations

import numpy as np
import pytest
from sitegen import LEAVES, make_site
from terrain import blocks, track
from terrain import transit_design as td
from terrain.route import Route, Section
from terrain.site import base_id

Z0 = 20


def _line(tmp_path, mode, cells, levels, *, kinds=None, corners=(), start_stop=None, end_stop=None,
          site_cells=None, extra=None, ground=64):
    """A design, a route along `cells`, one section covering it and a site over its box."""
    n = len(cells)
    data = {"element": "t", "seed": 7, "world": "world", "mode": mode, "route": "straight",
            "from": {"at": [*cells[0][:1], 66 if mode == "ice" else None, cells[0][1]], "stop": start_stop},
            "to": {"at": [cells[-1][0], 66 if mode == "ice" else None, cells[-1][1]], "stop": end_stop}}
    data.update(extra or {})
    design = td.parse_line(data, tmp_path)
    r = Route("t", mode, "world", "overworld", "h", list(cells), [float(v) for v in levels],
              list(kinds or ["grade"] * n), [None] * n, [None] * n, list(corners), [])
    xs, zs = [c[0] for c in cells], [c[1] for c in cells]
    box = (min(xs) - 10, 40, min(zs) - 10, max(xs) + 10, 100, max(zs) + 10)
    section = Section("s01", 0, n - 1, box, "world")
    r.sections = [section]
    site = make_site(tmp_path / "site", box, ground=ground, cells=site_cells, world="world")
    return design, r, section, site


def _rail_line(tmp_path, levels, *, end_stop=None, start_stop=None, cells=None, kinds=None):
    line = [(x, Z0) for x in range(len(levels))]
    return _line(tmp_path, "rail", line, levels, kinds=kinds, start_stop=start_stop, end_stop=end_stop,
                 site_cells=cells)


def _rail_with_corner(tmp_path):
    cells = [(x, 10) for x in range(5, 30)] + [(29, z) for z in range(11, 46)]
    assert len(cells) == 60
    return _line(tmp_path, "rail", cells, [65] * 60, corners=[24])


def _road_line(tmp_path, levels):
    return _line(tmp_path, "road", [(x, Z0) for x in range(len(levels))], levels)


def _ice_line(tmp_path, level, length=30):
    return _line(tmp_path, "ice", [(x, Z0) for x in range(length)], [level] * length)


def _path_line(tmp_path, levels, **kw):
    return _line(tmp_path, "path", [(x, Z0) for x in range(len(levels))], levels, **kw)


@pytest.mark.parametrize(("prev", "cell", "nxt", "shape"), [
    pytest.param((0, 0, 64), (1, 0, 64), (2, 0, 64), "east_west", id="straight-x"),
    pytest.param((0, 0, 64), (0, 1, 64), (0, 2, 64), "north_south", id="straight-z"),
    pytest.param((0, 0, 64), (1, 0, 64), (1, 1, 64), "south_west", id="corner-west-south"),
    pytest.param((1, 0, 64), (1, 1, 64), (2, 1, 64), "north_east", id="corner-north-east"),
    pytest.param((0, 0, 64), (1, 0, 64), (2, 0, 65), "ascending_east", id="rise-ahead"),
    pytest.param((0, 0, 65), (1, 0, 64), (2, 0, 64), "ascending_west", id="rise-behind"),
    pytest.param(None, (0, 0, 64), (0, 1, 64), "north_south", id="line-start"),
    pytest.param((0, 1, 64), (0, 0, 64), (0, -1, 65), "ascending_north", id="rise-north"),
    pytest.param((5, 4, 64), (5, 5, 64), None, "north_south", id="line-end"),
    pytest.param((2, 2, 64), (1, 2, 64), (1, 1, 64), "north_east", id="corner-east-north"),
])
def test_rail_shape(prev, cell, nxt, shape):
    assert track.rail_shape(prev, cell, nxt) == shape


def test_boosters_sit_on_redstone_blocks_and_skip_corners(tmp_path):
    design, r, section, site = _rail_with_corner(tmp_path)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    boosters = [c for c in track.rail_cells(design, r) if c.booster]
    assert boosters and 24 not in [r.cells.index((c.x, c.z)) for c in boosters]
    for c in boosters:
        assert after.block(c.x, c.y, c.z).startswith("minecraft:powered_rail")
        assert "powered=true" in after.block(c.x, c.y, c.z)
        assert after.block(c.x, c.y - 1, c.z) == "minecraft:redstone_block"


def test_corner_cell_is_a_plain_rail_with_a_corner_shape(tmp_path):
    design, r, section, site = _rail_with_corner(tmp_path)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(29, 65, 10) == "minecraft:rail[shape=south_west]"
    assert after.block(28, 65, 10) == "minecraft:rail[shape=east_west]"
    assert after.block(29, 65, 11) == "minecraft:rail[shape=north_south]"


def test_every_plain_rail_state_is_exact(tmp_path):
    design, r, section, site = _rail_with_corner(tmp_path)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    for c in track.rail_cells(design, r):
        want = (f"minecraft:powered_rail[powered=true,shape={c.shape}]" if c.booster
                else f"minecraft:rail[shape={c.shape}]")
        assert after.block(c.x, c.y, c.z) == want


def test_booster_spacing_on_the_level_and_on_slopes(tmp_path):
    cells = track.rail_cells(*_rail_line(tmp_path, levels=[65] * 50 + [65 + i for i in range(1, 11)] + [75] * 40)[:2])
    flat = [i for i, c in enumerate(cells) if c.booster and i < 50]
    slope = [i for i, c in enumerate(cells) if c.booster and 50 <= i < 60]
    assert flat == [0, 8, 16, 24, 32, 40, 48]
    assert slope == [50, 52, 54, 56, 58]


def test_slope_rails_ascend_toward_the_higher_cell(tmp_path):
    design, r, *_ = _rail_line(tmp_path, levels=[65] * 5 + [66, 67, 68] + [68] * 5)
    shapes = [c.shape for c in track.rail_cells(design, r)]
    assert shapes[4:8] == ["ascending_east"] * 3 + ["east_west"]


def test_terminus_has_no_boosters_on_the_last_eight_cells_and_a_launch_group(tmp_path):
    cells = track.rail_cells(*_rail_line(tmp_path, levels=[65] * 60, end_stop="terminus")[:2])
    assert not any(c.booster for c in cells[-8:])
    assert all(c.booster for c in cells[-11:-8])


def test_a_terminus_at_the_start_mirrors_the_rule(tmp_path):
    cells = track.rail_cells(*_rail_line(tmp_path, levels=[65] * 60, start_stop="terminus")[:2])
    assert not any(c.booster for c in cells[:8])
    assert all(c.booster for c in cells[8:11])


def test_clearance_carves_leaves_over_the_rail(tmp_path):
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, cells={(10, 67, 20): LEAVES})
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(10, 67, 20) == "minecraft:air"


def test_clearance_carves_three_high_over_the_whole_bed_and_spares_the_rest(tmp_path):
    keep = {(10, 69, 20): LEAVES, (10, 66, 23): LEAVES, (10, 67, 21): "minecraft:oak_planks",
            (11, 66, 19): "minecraft:water[level=0]", (12, 66, 21): LEAVES, (12, 68, 19): LEAVES}
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, cells=keep)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(10, 69, 20) == LEAVES          # four above the rail
    assert after.block(10, 66, 23) == LEAVES          # outside the bed
    assert after.block(10, 67, 21) == "minecraft:oak_planks"   # a player block
    assert after.block(11, 66, 19) == "minecraft:water[level=0]"   # a liquid
    assert after.block(12, 66, 21) == "minecraft:air"
    assert after.block(12, 68, 19) == "minecraft:air"


def test_ballast_bed_is_three_wide_below_the_rail_on_grade_only(tmp_path):
    kinds = ["grade"] * 10 + ["bridge"] * 10 + ["tunnel"] * 10
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, kinds=kinds)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    ballast = set(design.palette["ballast"])
    for x in (3, 25):
        assert {base_id(after.block(x, 64, z)) for z in (19, 20, 21)} <= ballast
    assert after.block(15, 64, 19) == "minecraft:grass_block[snowy=false]"   # bridge: no bed
    assert after.block(0, 64, 20) == "minecraft:redstone_block"            # booster bed on every kind
    assert after.block(24, 64, 20) == "minecraft:redstone_block"


def test_booster_redstone_block_on_a_bridge_kind(tmp_path):
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, kinds=["bridge"] * 30)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(24, 64, 20) == "minecraft:redstone_block"
    assert after.block(24, 65, 20).startswith("minecraft:powered_rail")


def test_a_section_writes_only_its_own_cells(tmp_path):
    design, r, _, site = _rail_line(tmp_path, levels=[65] * 60)
    half = Section("s02", 30, 59, r.sections[0].box, "world")
    after = blocks.apply_writes(site, track.track_layers(design, r, half, site))
    assert after.block(10, 65, 20) == "minecraft:air"
    assert after.block(41, 65, 20) == "minecraft:rail[shape=east_west]"     # 40 carries a booster


def test_rail_lamp_posts_alternate_sides_on_grade(tmp_path):
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, kinds=["grade"] * 15 + ["bridge"] * 15)
    layers = dict(track.track_layers(design, r, section, site, light_spacing=6))
    after = blocks.apply_writes(site, [("light", layers["light"])])
    post, lamp = next(iter(design.palette["lamp_post"])), next(iter(design.palette["lamp"]))
    assert after.block(0, 65, 22) == post and after.block(0, 66, 22) == post and after.block(0, 67, 22) == lamp
    assert after.block(6, 65, 18) == post and after.block(6, 67, 18) == lamp
    assert after.block(12, 65, 22) == post
    assert after.block(18, 65, 22) == "minecraft:air"      # bridge cells light themselves


def test_layers_come_in_order_and_skip_empty_ones(tmp_path):
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30)
    names = [n for n, _ in track.track_layers(design, r, section, site)]
    assert names == ["build", "track", "light"]
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, cells={(10, 67, 20): LEAVES})
    assert [n for n, _ in track.track_layers(design, r, section, site)] == ["carve", "build", "track", "light"]


def test_road_surface_uses_slabs_on_half_levels(tmp_path):
    design, r, section, site = _road_line(tmp_path, levels=[65.0, 65.5, 66.0, 66.5, 67.0] * 4)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    x, z = r.cells[1]
    assert "_slab" in after.block(x, 65, z)
    assert "type=bottom" in after.block(x, 65, z)


def test_road_is_four_wide_with_kerbs_and_a_surface_block_on_whole_levels(tmp_path):
    design, r, section, site = _road_line(tmp_path, levels=[65.0] * 20)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    surface, edge = set(design.palette["surface"]), {base_id(b) for b in design.palette["edge"]}
    assert [base_id(after.block(5, 64, z)) in surface for z in range(17, 25)] == [False] + [True] * 6 + [False]
    assert base_id(after.block(5, 65, 18)) in edge and base_id(after.block(5, 65, 23)) in edge
    assert after.block(5, 65, 20) == "minecraft:air"


def test_road_lamps_every_spacing(tmp_path):
    design, r, section, site = _road_line(tmp_path, levels=[65.0] * 40)
    light = dict(track.track_layers(design, r, section, site))["light"]
    lamp_ids = set(design.palette["lamp"])
    lamps = sum(1 for i, j, k in np.argwhere(light.codes) if base_id(light.palette[light.codes[i, j, k]]) in lamp_ids)
    assert lamps >= 40 // design.lights.spacing


def test_ice_lane_is_two_wide_with_guards(tmp_path):
    design, r, section, site = _ice_line(tmp_path, level=66)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    x, z = r.cells[5]
    assert [after.block(x, 65, z + dz) for dz in (0, 1)] == ["minecraft:packed_ice"] * 2
    assert "_slab" in after.block(x, 66, z - 1)
    assert "_slab" in after.block(x, 66, z + 2)


def test_ice_lights_replace_a_guard_every_spacing_cells(tmp_path):
    design, r, section, site = _ice_line(tmp_path, level=66)
    layers = dict(track.track_layers(design, r, section, site, light_spacing=10))
    after = blocks.apply_writes(site, [("track", layers["track"]), ("light", layers["light"])])
    assert after.block(0, 66, 19) == design.lights.block        # side -1
    assert after.block(10, 66, 22) == design.lights.block       # side +2
    assert "_slab" in after.block(5, 66, 19)


def test_path_width_varies_by_one_and_is_deterministic(tmp_path):
    levels = [65] * 60
    design, r, section, site = _path_line(tmp_path, levels)
    a = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    b = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    widths = {sum(1 for z in range(14, 27) if base_id(a.block(x, 64, z)) in design.palette["surface"])
              for x in range(60)}
    assert widths <= {2, 3, 4} and len(widths) > 1
    assert all(a.block(x, 64, z) == b.block(x, 64, z) for x in range(60) for z in range(14, 27))


def test_path_steps_get_stairs_facing_up_the_slope(tmp_path):
    design, r, section, site = _path_line(tmp_path, [65] * 5 + [66] * 5)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(5, 65, 20).endswith("_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    down = _path_line(tmp_path, [66] * 5 + [65] * 5)
    after = blocks.apply_writes(down[3], track.track_layers(*down))
    assert after.block(4, 65, 20).endswith("_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")


def _holes(site, surface_ids, cells, y):
    """Non-surface cells at height y whose opposite neighbours on an axis are both surface."""
    x1, _, z1, x2, _, z2 = site.box
    solid = {(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)
             if base_id(site.block(x, y, z)) in surface_ids}
    near = {(x + dx, z + dz) for x, z in cells for dx in range(-8, 9) for dz in range(-8, 9)}
    return [(x, z) for x, z in near - solid
            if {(x - 1, z), (x + 1, z)} <= solid or {(x, z - 1), (x, z + 1)} <= solid]


def _road_surface_ids(design):
    return set(design.palette["surface"])


def test_a_booster_before_a_corner_keeps_its_redstone_block(tmp_path):
    cells = [(x, Z0) for x in range(26)] + [(25, z) for z in range(Z0 + 1, Z0 + 20)]
    design, r, section, site = _line(tmp_path, "rail", cells, [65] * len(cells), corners=[25])
    assert track.rail_cells(design, r)[24].booster
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(24, 64, Z0) == "minecraft:redstone_block"
    assert after.block(24, 65, Z0).startswith("minecraft:powered_rail")


def test_a_diagonal_road_has_no_holes_between_the_kerbs(tmp_path):
    cells = [(i, Z0 + i) for i in range(20)]
    design, r, section, site = _line(tmp_path, "road", cells, [65.0] * 20)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert _holes(after, _road_surface_ids(design), cells, 64) == []


def test_a_road_bend_fills_the_outer_corner(tmp_path):
    cells = [(x, Z0) for x in range(16)] + [(15, z) for z in range(Z0 + 1, Z0 + 16)]
    design, r, section, site = _line(tmp_path, "road", cells, [65.0] * len(cells))
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert _holes(after, _road_surface_ids(design), cells, 64) == []
    assert base_id(after.block(16, 64, Z0 - 1)) in design.palette["surface"]


def test_a_diagonal_path_step_gets_stairs_facing_up_the_slope(tmp_path):
    cells = [(i, Z0 + i) for i in range(10)]
    design, r, section, site = _line(tmp_path, "path", cells, [65] * 5 + [66] * 5)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(5, 65, Z0 + 5).endswith("_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")


def test_nether_rail_clearance_carves_netherrack(tmp_path):
    cells = {(x, y, Z0): "minecraft:netherrack" for x in range(30) for y in (66, 67)}
    design, r, section, site = _line(
        tmp_path, "rail", [(x, Z0) for x in range(30)], [65] * 30, site_cells=cells,
        extra={"dimension": "nether", "world": "world_nether",
               "from": {"at": [0, 65, Z0], "stop": None}, "to": {"at": [29, 65, Z0], "stop": None}})
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(10, 66, Z0) == "minecraft:air"
    assert after.block(10, 67, Z0) == "minecraft:air"
