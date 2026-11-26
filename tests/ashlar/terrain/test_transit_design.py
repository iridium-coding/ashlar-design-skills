import json

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
    pytest.param({"mode": "tram"}, "mode must be one of", id="unknown-mode"),
    pytest.param({"mode": "road", "lanes": 3}, "lanes must be 1 or 2", id="three-lanes"),
    pytest.param({"heights": None}, "heights is required", id="search-without-heights"),
    pytest.param({"to": {"at": [200, 65, 0], "stop": "station"}}, "to.stop must be one of", id="unknown-stop"),
    pytest.param({"limits": {"max_fill": -1}}, "limits.max_fill must be at least 0", id="negative-limit"),
    pytest.param({"section_length": 50}, "section_length is not a known", id="top-level-section-length"),
    pytest.param({"colour": "red"}, "colour is not a known", id="unknown-top-key"),
    pytest.param({"mode": "path", "width": 4}, "width must be 1 to 3", id="wide-path"),
    pytest.param({"lights": {"minimum": 3}}, "lights.minimum is not a known", id="lights-minimum-key"),
    pytest.param({"limits": {"max_dig": 3}}, "limits.max_dig is not a known", id="unknown-nested-key"),
    pytest.param({"world": "world_nether", "route": "straight", "to": {"at": [200, 70, 0]}},
                 "same level", id="nether-unequal-levels"),
    pytest.param({"world": "world_nether", "route": "straight", "from": {"at": [0, None, 0]}},
                 "same level", id="nether-null-level"),
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


def test_file_keys_follow_the_spec(tmp_path):
    d = td.parse_line(_base(sections={"length": 60}, lights={"min": 4, "spacing": 8},
                            tunnels={"lining": "stone_bricks"}), tmp_path)
    assert (d.section_length, d.lights.minimum, d.lights.spacing) == (60, 4, 8)
    assert d.palette["lining"] == {"minecraft:stone_bricks": 1}


@pytest.mark.parametrize(("extra", "size"), [
    ({}, (3, 4)), ({"mode": "road"}, (6, 5)), ({"mode": "road", "lanes": 2}, (10, 5)),
    ({"mode": "path"}, (5, 3)), ({"mode": "path", "width": 1}, (3, 3)),
    ({"mode": "ice"}, (3, 3))])
def test_tunnel_defaults_per_mode(tmp_path, extra, size):
    d = td.parse_line(_base(**extra), tmp_path)
    assert (d.tunnels.width, d.tunnels.height) == size


def test_formation_half_per_mode(tmp_path):
    half = lambda **e: td.formation_half(td.parse_line(_base(**e), tmp_path))
    assert (half(), half(mode="road"), half(mode="road", lanes=2)) == (1.5, 3.0, 5.0)
    assert (half(mode="path"), half(mode="path", width=2), half(mode="ice")) == (1.5, 1.0, 2.0)


def test_nether_defaults_to_the_nether_style(tmp_path):
    d = td.parse_line(_base(world="nether", route="straight"), tmp_path)
    assert d.style == "nether" and d.palette["lamp"] == {"minecraft:soul_lantern": 1}
    assert d.palette["ice"] == {"minecraft:packed_ice": 1}


def test_palette_overrides_whole_roles(tmp_path):
    d = td.parse_line(_base(palette={"surface": {"oak_planks": 2}}), tmp_path)
    assert d.palette["surface"] == {"minecraft:oak_planks": 2}
    assert d.palette["ballast"] == td.STYLES["stone"]["ballast"]
    assert all(set(td.ROLES) <= set(p) for p in td.STYLES.values())


def test_via_points_lengthen_the_link_and_grow_the_box(tmp_path):
    d = td.parse_line(_base(via=[[100, 100]]), tmp_path)
    assert td.link_length(d) == pytest.approx(141.4213562 + 141.4213562, rel=1e-6)
    assert td.search_box(d) == (-70, -70, 270, 170)


def test_load_line_defaults_the_project_to_the_folder_above_terrain(tmp_path):
    (tmp_path / "terrain").mkdir()
    path = tmp_path / "terrain" / "north-line.line.json"
    path.write_text(json.dumps(_base()), encoding="utf-8")
    d = td.load_line(path)
    assert d.project == tmp_path and d.heights == tmp_path / "heights.json"
    with pytest.raises(ValueError, match="cannot read the line design"):
        td.load_line(tmp_path / "missing.json")
