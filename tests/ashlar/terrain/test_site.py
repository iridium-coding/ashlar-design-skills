"""Site reads (F1), heights files (F2), existing surfaces and trees."""
import gzip
import hashlib
import json

import numpy as np
import pytest

import ashlar_place
from sitegen import make_site, tree
from terrain.site import (ATTACHED, LEAVES, NATURAL, PLANTS, TRUNK, Site, find_trees,
                          load_heights, load_site, surfaces, unnatural_blocks, write_site)

BOX = (0, 50, 0, 7, 80, 7)


def test_load_site_round_trip_and_checksum(tmp_path):
    made = make_site(tmp_path / "s", BOX, ground=64, trees=[tree(2, 2, 65)],
                     world="world")
    loaded = load_site(tmp_path / "s")
    assert loaded.box == BOX and loaded.world == "world"
    assert loaded.columns == made.columns
    assert loaded.block(2, 64, 2) == "minecraft:grass_block[snowy=false]"
    assert loaded.block(2, 66, 2) == "minecraft:oak_log[axis=y]"
    manifest = json.loads((tmp_path / "s" / "manifest.json").read_text())
    assert manifest["complete"] is True and manifest["plugin"] is None
    assert manifest["columns"] == 64
    blob = bytearray((tmp_path / "s" / "columns.json.gz").read_bytes())
    blob[len(blob) // 2] ^= 0x01
    (tmp_path / "s" / "columns.json.gz").write_bytes(bytes(blob))
    with pytest.raises(ValueError):
        load_site(tmp_path / "s")


def test_block_outside_box_raises(tmp_path):
    site = make_site(tmp_path / "s", BOX)
    for cell in [(-1, 60, 0), (8, 60, 0), (0, 49, 0), (0, 81, 0), (0, 60, 8)]:
        with pytest.raises(KeyError):
            site.block(*cell)


def test_surfaces_ignore_trees_and_read_water(tmp_path):
    s = surfaces(make_site(tmp_path / "s", (0, 50, 0, 7, 80, 7), ground=64,
                           trees=[tree(2, 2, 65)], water={(6, 6): 62},
                           cells={(6, y, 6): "minecraft:dirt" for y in range(50, 59)}))
    assert s.ground[2, 2] == 64 and s.top[2, 2] > 68
    assert s.ground[6, 6] == 58 and s.water[6, 6] == 62
    assert np.isnan(s.water[2, 2]) and s.origin == (0, 0)
    assert s.ground.shape == (8, 8)
    assert s.top[6, 6] == 62  # water is the highest non-air block there


def test_surfaces_ignore_attachments_plants_and_plain_water(tmp_path):
    cells = {(1, 65, 1): "minecraft:short_grass", (2, 65, 2): "minecraft:poppy",
             (3, 65, 3): "minecraft:snow[layers=2]", (4, 65, 4): "minecraft:vine[north=true]",
             (5, 65, 5): "minecraft:oak_leaves[distance=1]",
             (6, 65, 6): "minecraft:glass", (0, 65, 0): "minecraft:lava[level=0]"}
    s = surfaces(make_site(tmp_path / "s", BOX, cells=cells,
                           water={(7, 7): 60}))
    for x in range(1, 6):
        assert s.ground[x, x] == 64 and s.top[x, x] == 65
    assert s.ground[6, 6] == 65  # glass is ground-like
    assert s.ground[0, 0] == 64 and np.isnan(s.water[0, 0])  # lava is not water
    assert s.water[7, 7] == 60


def test_surfaces_nan_ground_when_column_has_no_solid(tmp_path):
    s = surfaces(make_site(tmp_path / "s", BOX, ground={(3, 3): 40}))
    assert np.isnan(s.ground[3, 3]) and np.isnan(s.top[3, 3])


def test_surfaces_negative_coordinates(tmp_path):
    box = (-8, 50, -4, -1, 80, 3)
    s = surfaces(make_site(tmp_path / "s", box, trees=[tree(-3, 0, 65)]))
    assert s.origin == (-8, -4)
    assert s.ground.shape == (8, 8)
    assert s.ground[5, 4] == 64 and s.top[5, 4] > 68  # x=-3, z=0


def _two_trees(tmp_path):
    return make_site(tmp_path / "s", (0, 50, 0, 11, 80, 7), ground=64,
                     trees=[tree(3, 3, 65), tree(8, 3, 65)],
                     cells={(1, 67, 3): "minecraft:vine[east=true]",
                            (11, 80, 7): "minecraft:vine[east=true]"})


def test_find_trees_groups_trunks_and_leaves(tmp_path):
    site = _two_trees(tmp_path)
    trees = find_trees(site)
    assert len(trees) == 2
    a, b = trees
    assert a.base_y == 65 and b.base_y == 65
    assert a.trunk_columns == {(3, 3)} and b.trunk_columns == {(8, 3)}
    for tr in (a, b):
        assert len(tr.cells) > 20
    # touching canopies: each leaf is in the nearer tree
    for tr, lo, hi in ((a, 1, 5), (b, 6, 10)):
        for (x, y, z) in tr.cells:
            if site.block(x, y, z).startswith("minecraft:oak_leaves"):
                assert lo <= x <= hi
    assert a.cells.isdisjoint(b.cells)
    # a vine joins the tree whose leaf it touches; a floating one stays out
    assert (1, 67, 3) in a.cells
    assert all((11, 80, 7) not in tr.cells for tr in trees)


def test_find_trees_ignores_far_leaves_and_is_deterministic(tmp_path):
    cells = {(x, 70, 6): "minecraft:oak_leaves[distance=7]" for x in range(0, 8)}
    site = make_site(tmp_path / "s", BOX, trees=[tree(2, 2, 65)], cells=cells)
    first = find_trees(site)
    again = find_trees(load_site(tmp_path / "s"))
    assert [(t.base_y, sorted(t.cells)) for t in first] == \
           [(t.base_y, sorted(t.cells)) for t in again]
    assert len(first) == 1
    # leaves at z=6 are 4+ steps from the trunk at (2, 2): reachable only through
    # the canopy; the ones beyond 6 steps are not in the tree
    assert (7, 70, 6) not in first[0].cells


def test_find_trees_trunk_26_connected_and_base(tmp_path):
    cells = {(2, 65, 2): "minecraft:oak_log[axis=y]", (3, 66, 3): "minecraft:oak_log[axis=y]",
             (3, 65, 3): "minecraft:stripped_oak_log[axis=y]",
             (6, 66, 6): "minecraft:mushroom_stem"}
    site = make_site(tmp_path / "s", BOX, cells=cells)
    trees = find_trees(site)
    assert len(trees) == 2
    big = max(trees, key=lambda t: len(t.cells))
    assert big.base_y == 65 and big.trunk_columns == {(2, 2), (3, 3)}
    small = min(trees, key=lambda t: len(t.cells))
    assert small.base_y == 66 and small.trunk_columns == {(6, 6)}


def test_find_trees_canopy_past_the_box_edge(tmp_path):
    site = make_site(tmp_path / "s", BOX, trees=[tree(0, 0, 65), tree(7, 7, 65, 14)])
    trees = find_trees(site)
    assert len(trees) == 2
    assert all(-1 <= x <= 8 for t in trees for (x, _y, _z) in t.cells)


def test_unnatural_blocks_flags_planks(tmp_path):
    cells = {(1, 65, 1): "minecraft:oak_planks", (1, 66, 1): "minecraft:oak_planks",
             (2, 65, 1): "minecraft:white_wool", (3, 65, 1): "minecraft:oak_door[half=lower]",
             (4, 65, 1): "minecraft:short_grass", (5, 65, 1): "minecraft:oak_log[axis=y]",
             (6, 65, 1): "minecraft:glass", (7, 65, 1): "minecraft:rail[shape=north_south]"}
    site = make_site(tmp_path / "s", BOX, cells=cells)
    counts = unnatural_blocks(site, BOX)
    assert counts == {"minecraft:oak_planks": 2, "minecraft:white_wool": 1,
                      "minecraft:oak_door": 1, "minecraft:glass": 1, "minecraft:rail": 1}
    assert unnatural_blocks(site, (0, 50, 0, 0, 80, 7)) == {}
    assert unnatural_blocks(site, (1, 66, 1, 1, 66, 1)) == {"minecraft:oak_planks": 1}


def test_block_class_lists():
    assert "minecraft:oak_log" in TRUNK and "minecraft:stripped_crimson_hyphae" in TRUNK
    assert "minecraft:mushroom_stem" in TRUNK and "minecraft:muddy_mangrove_roots" not in TRUNK
    assert "minecraft:azalea_leaves" in LEAVES and "minecraft:red_mushroom_block" in LEAVES
    assert "minecraft:vine" in ATTACHED and "minecraft:snow" in ATTACHED
    assert "minecraft:short_grass" in PLANTS and "minecraft:kelp" in PLANTS
    assert {"minecraft:stone", "minecraft:water", "minecraft:oak_log",
            "minecraft:oak_leaves", "minecraft:muddy_mangrove_roots"} <= NATURAL
    assert "minecraft:oak_planks" not in NATURAL


def test_write_site_bytes_match_the_placer_and_load_backup_accepts(tmp_path):
    site = make_site(tmp_path / "s", BOX, trees=[tree(2, 2, 65)], world="world")
    payload = {"version": 1, "world": "world", "box": list(BOX),
               "columns": {f"{x},{z}": [list(r) for r in runs]
                           for (x, z), runs in site.columns.items()}}
    blob = (tmp_path / "s" / "columns.json.gz").read_bytes()
    assert blob == ashlar_place.encode_columns(payload)
    manifest = json.loads((tmp_path / "s" / "manifest.json").read_text())
    assert manifest["sha256"] == hashlib.sha256(blob).hexdigest()
    text = (tmp_path / "s" / "manifest.json").read_text()
    assert text == json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    placer_manifest, columns = ashlar_place.load_backup(tmp_path / "s")
    assert columns == site.columns and placer_manifest["box"] == list(BOX)


def test_load_site_accepts_a_placer_backup(tmp_path):
    site = make_site(tmp_path / "s", BOX, trees=[tree(2, 2, 65)])
    ashlar_place.write_backup(tmp_path / "b", BOX, None, site.columns, "1.2.3")
    loaded = load_site(tmp_path / "b")
    assert loaded.columns == site.columns and loaded.world is None


def _rewrite(path, mutate):
    """Re-encode columns.json.gz after `mutate(payload)` with a matching manifest."""
    payload = json.loads(gzip.decompress((path / "columns.json.gz").read_bytes()))
    mutate(payload)
    blob = ashlar_place.encode_columns(payload)
    (path / "columns.json.gz").write_bytes(blob)
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["sha256"] = hashlib.sha256(blob).hexdigest()
    manifest["columns"] = len(payload["columns"])
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_load_site_rejects_bad_sites(tmp_path):
    def fresh(name):
        make_site(tmp_path / name, BOX)
        return tmp_path / name

    p = fresh("incomplete")
    manifest = json.loads((p / "manifest.json").read_text())
    manifest["complete"] = False
    (p / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_site(p)

    p = fresh("missing")
    _rewrite(p, lambda d: d["columns"].pop("3,3"))
    with pytest.raises(ValueError):
        load_site(p)

    p = fresh("gap")
    _rewrite(p, lambda d: d["columns"].__setitem__("3,3", [[50, 60, "minecraft:stone"],
                                                           [62, 80, "minecraft:air"]]))
    with pytest.raises(ValueError):
        load_site(p)

    p = fresh("short")
    _rewrite(p, lambda d: d["columns"].__setitem__("3,3", [[50, 79, "minecraft:stone"]]))
    with pytest.raises(ValueError):
        load_site(p)

    p = fresh("low")
    _rewrite(p, lambda d: d["columns"].__setitem__("3,3", [[49, 80, "minecraft:stone"]]))
    with pytest.raises(ValueError):
        load_site(p)

    with pytest.raises(ValueError):
        load_site(tmp_path / "nothing-here")


def test_write_site_refuses_incomplete_columns(tmp_path):
    site = make_site(tmp_path / "s", BOX)
    del site.columns[(1, 1)]
    with pytest.raises(ValueError):
        write_site(tmp_path / "t", site)


def test_load_heights_orders_and_nans(tmp_path):
    nx, nz = 3, 2
    data = {"version": 1, "world": None, "origin": [-5, 10], "size": [nx, nz],
            "ground": [1, 2, 3, 4, 5, None], "surface": [2, 3, 4, 5, 6, 7],
            "top": [9, None, 9, 9, 9, 9]}
    (tmp_path / "h.json").write_text(json.dumps(data))
    h = load_heights(tmp_path / "h.json")
    assert h["origin"] == (-5, 10)
    assert h["ground"].shape == (3, 2) and h["ground"].dtype.kind == "f"
    assert h["ground"][1, 0] == 3 and h["ground"][2, 0] == 5
    assert np.isnan(h["ground"][2, 1]) and np.isnan(h["top"][0, 1])
    assert h["surface"][2, 1] == 7
    bad = dict(data, ground=[1, 2])
    (tmp_path / "b.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_heights(tmp_path / "b.json")


def test_attachments_do_not_flood_ground_cover(tmp_path):
    box = (0, 50, 0, 19, 80, 19)
    snow = {(x, 65, z): "minecraft:snow[layers=1]"
            for x in range(20) for z in range(20) if (x, z) != (10, 10)}
    snow[(10, 76, 10)] = "minecraft:snow[layers=1]"  # nothing below: floats, stays out
    site = make_site(tmp_path / "s", box, trees=[tree(10, 10, 65)], cells=snow)
    # snow on top of a leaf cell joins
    leaf_top = max(y for y in range(65, 81)
                   if site.block(10, y, 11).startswith("minecraft:oak_leaves"))
    on_leaf = {(10, leaf_top + 1, 11): "minecraft:snow[layers=1]"}
    site = make_site(tmp_path / "s2", box, trees=[tree(10, 10, 65)], cells={**snow, **on_leaf})
    (t,) = find_trees(site)
    plain = make_site(tmp_path / "p", box, trees=[tree(10, 10, 65)])
    (t0,) = find_trees(plain)
    assert t.cells == t0.cells | {(10, leaf_top + 1, 11)}
    # lichen and moss lying/clinging around: same rule
    cells = {(x, 65, 12): "minecraft:moss_carpet" for x in range(20)}
    (t2,) = find_trees(make_site(tmp_path / "m", box, trees=[tree(10, 10, 65)], cells=cells))
    assert t2.cells == t0.cells


def test_hanging_chain_joins_but_neighbour_column_does_not(tmp_path):
    box = (0, 50, 0, 11, 80, 11)
    base = make_site(tmp_path / "b", box, trees=[tree(5, 5, 65)])
    (t0,) = find_trees(base)
    leaf = min(c for c in t0.cells if base.block(*c).startswith("minecraft:oak_leaves")
               and base.block(c[0], c[1] - 1, c[2]) == "minecraft:air"
               and c[1] == min(k[1] for k in t0.cells if base.block(*k).startswith("minecraft:oak_leaves")))
    x, y, z = leaf
    chain = {(x, y - i, z): "minecraft:vine[north=true]" for i in range(1, 6)}
    # a separate vine column standing beside the chain, not under the tree
    side = {(x + 4 if x + 4 <= 11 else x - 4, 60 + i, z): "minecraft:vine[north=true]"
            for i in range(0, 4)}
    site = make_site(tmp_path / "v", box, trees=[tree(5, 5, 65)], cells={**chain, **side})
    (t,) = find_trees(site)
    assert set(chain) <= t.cells
    assert not (set(side) & t.cells)


def test_side_attachment_needs_adjacency(tmp_path):
    box = (0, 50, 0, 11, 80, 11)
    cells = {(7, 66, 5): "minecraft:glow_lichen[down=true]",
             (6, 66, 5): "minecraft:glow_lichen[down=true]"}
    (t,) = find_trees(make_site(tmp_path / "g", box, cells=cells,
                                trees=[tree(5, 5, 65, radius=0)]))
    assert (6, 66, 5) in t.cells and (7, 66, 5) not in t.cells
    cells = {(7, 66, 5): "minecraft:glow_lichen[down=true]"}
    (t,) = find_trees(make_site(tmp_path / "g2", box, cells=cells,
                                trees=[tree(5, 5, 65, radius=0)]))
    assert (7, 66, 5) not in t.cells


def _col(tmp_path, name, cells, **kw):
    return surfaces(make_site(tmp_path / name, BOX, cells=cells, **kw))


def test_ice_on_water_is_water_not_ground(tmp_path):
    ice = "minecraft:ice"
    cells = {(2, y, 2): "minecraft:gravel" for y in range(50, 60)}
    cells.update({(2, y, 2): "minecraft:water[level=0]" for y in range(60, 63)})
    cells[(2, 63, 2)] = ice  # frozen surface; air above
    cells.update({(4, y, 4): "minecraft:water[level=0]" for y in range(60, 62)})
    cells.update({(4, 62, 4): ice, (4, 63, 4): ice})  # two ice cells over water
    s = _col(tmp_path, "river", cells, water={(2, 2): 50, (4, 4): 50})
    assert s.ground[2, 2] == 59 and s.water[2, 2] == 63
    assert s.top[2, 2] == 63


def test_ice_on_solid_and_packed_ice_stay_ground(tmp_path):
    cells = {(1, 65, 1): "minecraft:ice",                       # on grass/stone
             (3, 63, 3): "minecraft:water[level=0]", (3, 64, 3): "minecraft:packed_ice",
             (5, 63, 5): "minecraft:water[level=0]", (5, 64, 5): "minecraft:blue_ice"}
    s = _col(tmp_path, "solid", cells)
    assert s.ground[1, 1] == 65 and np.isnan(s.water[1, 1])
    assert s.ground[3, 3] == 64 and np.isnan(s.water[3, 3])
    assert s.ground[5, 5] == 64 and np.isnan(s.water[5, 5])


def test_waterlogged_non_ground_counts_as_water(tmp_path):
    wl = "minecraft:mangrove_roots[waterlogged=true]"
    cells = {(2, 64, 2): "minecraft:mud", (2, 65, 2): wl, (2, 66, 2): wl,
             (4, 64, 4): "minecraft:sand",
             (4, 65, 4): "minecraft:brain_coral_fan[waterlogged=true]",
             (5, 64, 5): "minecraft:sand",
             (5, 65, 5): "minecraft:tube_coral_wall_fan[facing=north,waterlogged=true]",
             (6, 64, 6): "minecraft:mud", (6, 65, 6): "minecraft:mangrove_roots[waterlogged=false]",
             (1, 65, 1): "minecraft:oak_stairs[waterlogged=true]",
             (7, 64, 7): "minecraft:sand", (7, 65, 7): "minecraft:brain_coral_block"}
    s = _col(tmp_path, "wl", cells)
    assert s.ground[2, 2] == 64 and s.water[2, 2] == 66
    assert s.ground[4, 4] == 64 and s.water[4, 4] == 65
    assert s.ground[5, 5] == 64 and s.water[5, 5] == 65
    assert s.ground[6, 6] == 64 and np.isnan(s.water[6, 6])
    assert s.ground[1, 1] == 65 and np.isnan(s.water[1, 1])   # waterlogged ground-class
    assert s.ground[7, 7] == 65 and np.isnan(s.water[7, 7])   # coral block is ground


def test_water_predicates():
    from terrain.site import is_water_state, water_run_flags
    assert is_water_state("minecraft:water[level=3]") and is_water_state("minecraft:kelp[age=1]")
    assert is_water_state("minecraft:mangrove_roots[waterlogged=true]")
    assert not is_water_state("minecraft:oak_stairs[waterlogged=true]")
    assert not is_water_state("minecraft:ice") and not is_water_state("minecraft:lava[level=0]")
    runs = [(0, 3, "minecraft:stone"), (4, 5, "minecraft:water"), (6, 6, "minecraft:ice"),
            (7, 9, "minecraft:air"), (10, 10, "minecraft:ice")]
    assert water_run_flags(runs) == [False, True, True, False, False]
