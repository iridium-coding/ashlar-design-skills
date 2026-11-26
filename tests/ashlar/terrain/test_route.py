from itertools import pairwise

import numpy as np
import pytest
from sitegen import make_heights
from terrain import route
from terrain import transit_design as td


def _grid(nx, nz, y):
    return route.grid_from_heights(make_heights(None, (0, 0), np.full((nx, nz), y, float)))


def _design(tmp_path, **kw):
    data = {"element": "test-line", "seed": 1, "world": "world", "mode": "rail", "heights": "heights.json",
            "from": {"at": kw.pop("start", [0, 65, 0])}, "to": {"at": kw.pop("end", [60, 65, 30])}}
    if "via" in kw:
        data["via"] = kw.pop("via")
    data.update(kw)
    return td.parse_line(data, tmp_path)


def _axis_steps(cells):
    return all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in pairwise(cells))


def test_straight_route_runs_axis_legs_through_via(tmp_path):
    d = _design(tmp_path, route="straight", start=[0, 65, 0], end=[20, 65, 10], via=[[20, 0]])
    cells, corners = route.straight_cells(d)
    assert cells[0] == (0, 0) and cells[-1] == (20, 10) and len(cells) == 31
    assert _axis_steps(cells)
    assert corners == [20]


def test_search_goes_around_avoid_box(tmp_path):
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20], avoid=[[30, 5, 50, 35]])
    cells, _ = route.search_cells(d, _grid(80, 40, 64))
    assert cells[0] == (5, 20) and cells[-1] == (75, 20)
    assert not any(28 <= x <= 52 and 3 <= z <= 37 for x, z in cells)


def test_search_takes_the_pass_through_a_ridge(tmp_path):
    ground = np.full((80, 40), 64.0)
    ground[38:43, :] = 84
    ground[38:43, 30:35] = 64
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20])
    cells, _ = route.search_cells(d, route.grid_from_heights(make_heights(None, (0, 0), ground)))
    assert all(30 <= z <= 34 for x, z in cells if 38 <= x <= 42)


def test_rail_search_moves_along_axes_with_few_corners(tmp_path):
    d = _design(tmp_path, start=[0, 65, 0], end=[60, 65, 30])
    cells, corners = route.search_cells(d, _grid(70, 40, 64))
    assert _axis_steps(cells)
    assert len(corners) <= 2


def test_route_refuses_endpoint_inside_avoid_box(tmp_path):
    d = _design(tmp_path, mode="road", start=[40, 65, 20], end=[75, 65, 20], avoid=[[30, 5, 50, 35]])
    with pytest.raises(route.RouteError, match="inside an avoid box"):
        route.search_cells(d, _grid(80, 40, 64))


def test_route_refuses_when_null_columns_block_every_path(tmp_path):
    ground = np.full((80, 40), 64.0)
    ground[40:42, :] = np.nan
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20])
    with pytest.raises(route.RouteError, match="no route"):
        route.search_cells(d, route.grid_from_heights(make_heights(None, (0, 0), ground)))


def test_route_refuses_endpoints_on_null_or_outside_the_grid(tmp_path):
    ground = np.full((80, 40), 64.0)
    ground[75, 20] = np.nan
    grid = route.grid_from_heights(make_heights(None, (0, 0), ground))
    with pytest.raises(route.RouteError, match=r"to \(75, 20\).*null"):
        route.search_cells(_design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20]), grid)
    with pytest.raises(route.RouteError, match=r"from \(-5, 20\).*outside"):
        route.search_cells(_design(tmp_path, mode="road", start=[-5, 65, 20], end=[70, 65, 20]), grid)
    with pytest.raises(route.RouteError, match=r"via \(300, 5\).*outside"):
        route.search_cells(_design(tmp_path, mode="road", start=[5, 65, 20], end=[70, 65, 20], via=[[300, 5]]), grid)


def test_search_passes_through_via_and_prefers_dry_columns(tmp_path):
    ground = np.full((60, 40), 64.0)
    surface = ground.copy()
    surface[20:30, 0:30] = 66
    d = _design(tmp_path, mode="road", start=[5, 65, 10], end=[55, 65, 10], via=[[30, 35]])
    cells, _ = route.search_cells(d, route.grid_from_heights(make_heights(None, (0, 0), ground, surface=surface)))
    assert (30, 35) in cells and cells[0] == (5, 10) and cells[-1] == (55, 10)


def test_large_grid_is_searched_coarse_then_refined(tmp_path):
    grid = _grid(600, 450, 64)
    d = _design(tmp_path, mode="road", start=[10, 65, 10], end=[580, 65, 430])
    cells, _ = route.search_cells(d, grid)
    assert cells[0] == (10, 10) and cells[-1] == (580, 430)
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1 for a, b in pairwise(cells))
