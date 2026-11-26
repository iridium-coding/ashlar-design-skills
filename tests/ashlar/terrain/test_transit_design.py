import numpy as np
import pytest
from sitegen import make_heights
from terrain import transit_design as td
from terrain.site import load_heights


def _base(**extra):
    data = {"element": "north-line", "seed": 5, "world": "world", "mode": "rail",
            "from": {"at": [0, 65, 0]}, "to": {"at": [200, 65, 0], "stop": "terminus"}, "heights": "heights.json"}
    data.update(extra)
    return data


def test_defaults_follow_the_spec(tmp_path):
    d = td.parse_line(_base(), tmp_path)
    assert (d.limits.max_fill, d.limits.max_cut, d.limits.min_bridge, d.limits.min_tunnel, d.limits.water_clearance) == (6, 8, 4, 6, 3)
    assert (d.limits.fill_ratio, d.limits.cut_ratio, d.limits.rock_cut_ratio, d.section_length, d.version) == (1.5, 1.0, 0.5, 96, "26.3")
    assert (d.dimension, d.route, d.lights.minimum, d.boosters.flat, d.boosters.slope) == ("overworld", "search", 1, 24, 2)
    assert (d.tunnels.width, d.tunnels.height, d.tunnels.roof) == (3, 4, 3)
    assert d.end.stop == "terminus" and d.start.stop is None


def test_nether_world_needs_a_straight_level_line(tmp_path):
    with pytest.raises(ValueError, match="straight"):
        td.parse_line(_base(world="world_nether"), tmp_path)
    d = td.parse_line(_base(world="world_nether", route="straight"), tmp_path)
    assert (d.dimension, d.lights.minimum, d.lights.spacing) == ("nether", 12, 4)


def test_ice_line_needs_equal_endpoint_levels(tmp_path):
    with pytest.raises(ValueError, match="level"):
        td.parse_line(_base(mode="ice", to={"at": [200, 70, 0]}), tmp_path)


@pytest.mark.parametrize(("extra", "match"), [
    pytest.param({"mode": "tram"}, "mode", id="unknown-mode"),
    pytest.param({"mode": "road", "lanes": 3}, "lanes", id="three-lanes"),
    pytest.param({"heights": None}, "heights", id="search-without-heights"),
    pytest.param({"to": {"at": [200, 65, 0], "stop": "station"}}, "stop", id="unknown-stop"),
    pytest.param({"limits": {"max_fill": -1}}, "max_fill", id="negative-limit"),
])
def test_invalid_designs_are_refused(tmp_path, extra, match):
    with pytest.raises(ValueError, match=match):
        td.parse_line(_base(**extra), tmp_path)


def test_search_box_grows_by_a_quarter_of_the_link_or_64(tmp_path):
    assert td.search_box(td.parse_line(_base(), tmp_path)) == (-64, -64, 264, 64)
    assert td.search_box(td.parse_line(_base(to={"at": [1000, 65, 0]}), tmp_path)) == (-250, -250, 1250, 250)


def test_make_heights_round_trips_through_load_heights(tmp_path):
    ground = np.array([[60.0, 61.0, np.nan], [62.0, 63.0, 64.0]])
    path = tmp_path / "heights.json"
    out = make_heights(path, (10, 20), ground, top=ground + 1)
    assert out["size"] == [2, 3] and out["ground"][2] is None
    loaded = load_heights(path)
    assert loaded["origin"] == (10, 20)
    np.testing.assert_array_equal(loaded["ground"], ground)
    np.testing.assert_array_equal(loaded["surface"], ground)
    np.testing.assert_array_equal(loaded["top"], ground + 1)
