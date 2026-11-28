import time
from itertools import pairwise

import numpy as np
import pytest
from sitegen import make_heights
from terrain import route, track
from terrain import transit_design as td


def _line(tmp_path, start, end, *, mode="rail", via=None, **kw):
    data = {"element": "test-line", "seed": 1, "world": "world", "mode": mode, "route": "straight",
            "from": {"at": list(start)}, "to": {"at": list(end)}}
    if via is not None:
        data["via"] = via
    data.update(kw)
    return td.parse_line(data, tmp_path)


def _rows(values, nz=9):
    return np.repeat(np.asarray(values, dtype=float)[:, None], nz, axis=1)


def _along_x(tmp_path, ground_list, *, mode="rail", start_y=None, end_y=None, surface_list=None, **kw):
    """Fit a straight line along +x from x=0 at z=4 over `ground_list` repeated over z 0..8."""
    surface = None if surface_list is None else _rows(surface_list)
    grid = route.grid_from_heights(make_heights(None, (0, 0), _rows(ground_list), surface=surface))
    design = _line(tmp_path, [0, start_y, 4], [len(ground_list) - 1, end_y, 4], mode=mode, **kw)
    cells, corners = route.straight_cells(design)
    return route.fit_profile(design, cells, corners, grid)


def _with_corner_on_ramp(tmp_path):
    """A rail along x then z with its corner at chainage 20, on ground rising 1 in 2 along the chainage."""
    x, z = np.meshgrid(np.arange(30), np.arange(40), indexing="ij")
    grid = route.grid_from_heights(make_heights(None, (0, 0), 64 + (x + z) // 2))
    design = _line(tmp_path, [0, None, 0], [20, None, 30], via=[[20, 0]])
    cells, corners = route.straight_cells(design)
    levels, _ = route.fit_profile(design, cells, corners, grid)
    return levels, corners


def _river(tmp_path):
    """Ground 64 with a river over x 30..35: ground 56 under a water surface at 62."""
    ground = [64] * 30 + [56] * 6 + [64] * 30
    surface = [64] * 30 + [62] * 6 + [64] * 30
    return _along_x(tmp_path, ground, surface_list=surface)


def test_rail_profile_changes_at_most_one_block_per_cell(tmp_path):
    levels, _ = _along_x(tmp_path, [64 + i // 2 for i in range(60)])
    assert max(abs(a - b) for a, b in pairwise(levels)) <= 1


def test_rail_corner_and_neighbours_share_a_level(tmp_path):
    levels, corners = _with_corner_on_ramp(tmp_path)          # corner at index 20 on a 1-in-2 ramp
    assert levels[19] == levels[20] == levels[21] and corners == [20]


def test_valley_deeper_than_max_fill_is_a_bridge(tmp_path):
    ground = [64] * 30 + [50] * 10 + [64] * 30
    _, kinds = _along_x(tmp_path, ground)
    assert set(kinds[30:40]) == {"bridge"} and kinds[0] == "grade"


def test_ridge_higher_than_max_cut_with_cover_is_a_tunnel(tmp_path):
    ramp = [64 + 4 * i for i in range(1, 6)]
    _, kinds = _along_x(tmp_path, [64] * 25 + ramp + [84] * 15 + ramp[::-1] + [64] * 25)
    assert "tunnel" in kinds[32:42] and "cut" in kinds[24:30]


def _broken_joints(levels):
    """Joints between neighbouring rails of a line along +x whose heights do not meet.

    Each rail's ends sit at its level, one higher on the side it ascends toward; two neighbours
    meet when their facing ends are at one height and they are not two slopes rising to a peak.
    """
    cells = [(x, 4, v) for x, v in enumerate(levels)]
    ends = []
    for i, cell in enumerate(cells):
        shape = track.rail_shape(cells[i - 1] if i else None, cell, cells[i + 1] if i + 1 < len(cells) else None)
        y = int(cell[2])
        ends.append((y + (shape == "ascending_west"), y + (shape == "ascending_east"), shape))
    return [i for i, (a, b) in enumerate(pairwise(ends))
            if a[1] != b[0] or (a[2] == "ascending_east" and b[2] == "ascending_west")]


def _vees(levels):
    return [i for i in range(1, len(levels) - 1) if levels[i - 1] > levels[i] < levels[i + 1]]


@pytest.mark.parametrize("ground", [
    pytest.param([64] * 10 + [61] + [64] * 10, id="one-wide-ditch"),
    pytest.param([64] * 10 + [62, 60, 58, 56, 58, 60, 62] + [64] * 10, id="symmetric-valley"),
])
def test_a_rail_dip_bottoms_out_over_two_level_cells_so_every_joint_meets(tmp_path, ground):
    levels, _ = _along_x(tmp_path, ground)
    assert _vees(levels) == []
    assert _broken_joints(levels) == []


def test_a_fixed_rail_low_point_gets_a_two_cell_bottom(tmp_path):
    levels, _ = _along_x(tmp_path, [64] * 21, profile=[[10, 64]])
    assert levels[10] == 64 and _vees(levels) == [] and _broken_joints(levels) == []


def test_a_one_cell_rail_crest_is_allowed(tmp_path):
    levels, _ = _along_x(tmp_path, [64] * 21, profile=[[10, 66]])
    assert levels[8:13] == [65, 65, 66, 65, 65] and _broken_joints(levels) == []


def test_rail_termini_run_level_over_their_quiet_and_launch_cells(tmp_path):
    ground = [64 + i // 2 for i in range(40)]           # a steady 1-in-2 climb from end to end
    grid = route.grid_from_heights(make_heights(None, (0, 0), _rows(ground)))
    design = td.parse_line({"element": "test-line", "seed": 1, "world": "world", "mode": "rail",
                            "route": "straight", "from": {"at": [0, None, 4], "stop": "terminus"},
                            "to": {"at": [39, None, 4], "stop": "terminus"}}, tmp_path)
    cells, corners = route.straight_cells(design)
    levels, _ = route.fit_profile(design, cells, corners, grid)
    assert len(set(levels[:11])) == 1 and len(set(levels[-11:])) == 1
    assert max(abs(a - b) for a, b in pairwise(levels)) == 1 and _broken_joints(levels) == []


def test_short_bridge_grows_to_min_bridge(tmp_path):
    _, kinds = _along_x(tmp_path, [64] * 30 + [56] * 2 + [64] * 30)
    assert kinds.count("bridge") == 4


def test_short_tunnel_becomes_a_cut_when_shallow_enough(tmp_path):
    _, kinds = _along_x(tmp_path, [64] * 30 + [75] * 3 + [64] * 30)
    assert "tunnel" not in kinds


def test_water_crossing_keeps_clearance(tmp_path):
    levels, kinds = _river(tmp_path)                           # ground 56, surface 62 over x 30..35
    assert set(kinds[30:36]) == {"bridge"} and min(levels[30:36]) >= 66


def test_road_levels_move_in_half_blocks(tmp_path):
    levels, _ = _along_x(tmp_path, [64 + i // 2 for i in range(60)], mode="road")
    assert all((2 * v).is_integer() for v in levels)
    assert max(abs(a - b) for a, b in pairwise(levels)) <= 0.5


def test_ice_profile_is_level(tmp_path):
    levels, _ = _along_x(tmp_path, [64] * 20 + [70] * 20, mode="ice", start_y=66, end_y=66)
    assert set(levels) == {66}


def test_profile_refuses_unreachable_endpoint_level(tmp_path):
    with pytest.raises(route.RouteError, match="cannot reach"):
        _along_x(tmp_path, [64] * 10, start_y=65, end_y=81)


# ------------------------------------------------------------ beyond the brief
def test_unreachable_level_names_the_cell(tmp_path):
    with pytest.raises(route.RouteError, match=r"cannot reach level 81 at cell 9 \(9, 4\)"):
        _along_x(tmp_path, [64] * 10, start_y=65, end_y=81)


def test_ice_over_water_below_the_clearance_is_refused_naming_the_cell(tmp_path):
    ground = [64] * 10 + [56] * 4 + [64] * 10
    surface = [64] * 10 + [64] * 4 + [64] * 10
    with pytest.raises(route.RouteError, match=r"cannot reach level 68 at cell 10 \(10, 4\)"):
        _along_x(tmp_path, ground, surface_list=surface, mode="ice", start_y=65, end_y=65)


def test_endpoint_and_profile_levels_are_hard_constraints(tmp_path):
    levels, _ = _along_x(tmp_path, [64] * 40, start_y=62, end_y=67, profile=[[20, 70]])
    assert (levels[0], levels[20], levels[-1]) == (62, 70, 67)
    assert max(abs(a - b) for a, b in pairwise(levels)) <= 1


@pytest.mark.parametrize("mode", ["rail", "road"])
def test_valley_bridge_deck_stays_level_at_the_approach_level(tmp_path, mode):
    levels, kinds = _along_x(tmp_path, [64] * 30 + [50] * 10 + [64] * 30, mode=mode)
    deck = {level for level, kind in zip(levels, kinds, strict=True) if kind == "bridge"}
    assert levels[0] == 65 and deck == {levels[0]}


def test_free_ends_fit_the_ground_at_grade(tmp_path):
    levels, kinds = _along_x(tmp_path, [70] * 20)
    assert set(levels) == {71} and set(kinds) == {"grade"}


def test_path_levels_are_whole_blocks(tmp_path):
    levels, _ = _along_x(tmp_path, [64 + i // 3 for i in range(45)], mode="path")
    assert all(float(v).is_integer() for v in levels)
    assert max(abs(a - b) for a, b in pairwise(levels)) <= 1


def test_short_deep_tunnel_without_cover_to_grow_is_refused_naming_the_stretch(tmp_path):
    with pytest.raises(route.RouteError, match=r"tunnel from \(30, 4\) to \(32, 4\)"):
        _along_x(tmp_path, [64] * 30 + [95] * 3 + [64] * 30)


def test_classify_uses_the_level_conventions(tmp_path):
    design = _line(tmp_path, [0, None, 0], [11, None, 0])
    ground = [64, 64, 64, 64, 64, 80, 64, 64, 60, 64, 64, 64]
    levels = [65, 66, 63, 68, 65, 65, 65, 65, 68, 65, 65, 65]
    kinds = route.classify(design, levels, ground, list(ground))
    # d = level - (ground + 1): 0 and +1 grade, -2 cut, +3 fill, -16 a one-cell tunnel shallow
    # enough (<= 2 * max_cut) to become a cut, +7 a one-cell bridge grown to min_bridge 4
    assert kinds == ["grade", "grade", "cut", "fill", "grade", "cut",
                     "bridge", "bridge", "bridge", "bridge", "grade", "grade"]


def test_line_without_heights_runs_level_as_a_tunnel(tmp_path):
    design = _line(tmp_path, [0, 40, 0], [30, 40, 0])
    cells, corners = route.straight_cells(design)
    levels, kinds = route.fit_profile(design, cells, corners, None)
    assert set(levels) == {40} and set(kinds) == {"tunnel"} and len(levels) == len(cells)


def test_line_without_heights_needs_a_shared_endpoint_level(tmp_path):
    design = _line(tmp_path, [0, 40, 0], [30, None, 0])
    cells, corners = route.straight_cells(design)
    with pytest.raises(route.RouteError, match="same level"):
        route.fit_profile(design, cells, corners, None)


def test_profile_refuses_cells_off_the_heights_grid(tmp_path):
    grid = route.grid_from_heights(make_heights(None, (0, 0), _rows([64] * 10)))
    design = _line(tmp_path, [0, None, 4], [14, None, 4])
    cells, corners = route.straight_cells(design)
    with pytest.raises(route.RouteError, match=r"cell 10 \(10, 4\) is outside the heights grid"):
        route.fit_profile(design, cells, corners, grid)


def test_long_route_fits_quickly(tmp_path):
    n = 4000
    ground = [64 + round(30 * np.sin(i / 90) + 8 * np.sin(i / 13)) for i in range(n)]
    t0 = time.perf_counter()
    levels, kinds = _along_x(tmp_path, ground, mode="road")
    assert time.perf_counter() - t0 < 10
    assert len(levels) == len(kinds) == n
    assert max(abs(a - b) for a, b in pairwise(levels)) <= 0.5
