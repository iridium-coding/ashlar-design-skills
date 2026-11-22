"""Blending into the existing ground, pads, water plans, existing liquid and the
edge/water checks."""
import time

import numpy as np
import pytest

from sitegen import AIR, GRASS, LOG, STONE, WATER, make_site
from terrain import recipe as R
from terrain.field import HeightField
from terrain.site import (LiquidLevels, Site, auto_band, blend_to_existing, find_trees,
                          ground_for, hold_shores, is_retained, is_still, liquid_levels, surface_y,
                          water_levels, write_site)
from terrain.verify import verify

LEAF_WL = "minecraft:oak_leaves[distance=1,persistent=false,waterlogged=true]"
FLOW = "minecraft:water[level=3]"


def _recipe(origin=(0, 0, 0), n=32, **extra):
    rec = {"version": 1, "origin": list(origin), "nx": n, "nz": n, "sea_level": 40,
           "seed": 3, "graph": {"type": "Constant", "value": 100.0}}
    rec.update(extra)
    return rec


def _field(h, sea=40.0):
    hf = HeightField(h.shape[0], h.shape[1], sea_level=sea)
    hf.h = np.asarray(h, dtype=float).copy()
    return hf


def _site_around(tmp_path, n, origin=(0, 0), ground=64):
    ox, oz = origin
    return make_site(tmp_path / "site", (ox - 8, 0, oz - 8, ox + n + 7, 200, oz + n + 7),
                     ground=ground)


def _ring(n):
    ring = np.zeros((n, n), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    return ring


def _cone(n, peak=164.0, base=64.0):
    x, z = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    r = np.hypot(x - (n - 1) / 2, z - (n - 1) / 2)
    return np.clip(peak - r * 8.0, base, peak)


def _site_in_memory(box, ground, cells, default=64):
    """A Site built without files (stone, grass at the ground, air above, then `cells`)."""
    x1, y1, z1, x2, y2, z2 = box
    columns = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            g = ground.get((x, z), default)
            states = [AIR] * (y2 - y1 + 1)
            for y in range(y1, g):
                states[y - y1] = STONE
            states[g - y1] = GRASS
            columns[(x, z)] = states
    for (cx, cy, cz), st in cells.items():
        columns[(cx, cz)][cy - y1] = st
    for key, states in columns.items():
        runs, start = [], 0
        for i in range(1, len(states) + 1):
            if i == len(states) or states[i] != states[start]:
                runs.append((y1 + start, y1 + i - 1, states[start]))
                start = i
        columns[key] = runs
    return Site(box=box, world=None, columns=columns)


# ------------------------------------------------------------ blend, band
def test_blend_matches_ring_and_keeps_interior():
    n = 64
    ground = np.full((n, n), 64.0)
    hf = _field(_cone(n))
    band = 10
    out = blend_to_existing(hf, ground, band)
    assert np.all(np.abs(out.h[_ring(n)] - 64.0) <= 1.0)
    assert np.array_equal(out.h[band:n - band, band:n - band],
                          hf.h[band:n - band, band:n - band])
    assert out is not hf and hf.h[n // 2, n // 2] != 64.0


def test_auto_band_grows_with_difference():
    h = np.full((64, 64), 110.0); g = np.full((64, 64), 64.0)
    assert auto_band(h, g) == 14 and auto_band(g + 1, g) == 8
    assert auto_band(np.full((20, 20), 500.0), np.full((20, 20), 0.0)) == 10   # cap n // 2


def test_recipe_with_site_blends_after_erosion(tmp_path):
    n = 32
    _site_around(tmp_path, n)
    rec = _recipe(n=n, erosion={"thermal": {"iterations": 2}}, site={"read": "site", "band": 6})
    out = R.build_field(rec, tmp_path)
    assert np.all(np.abs(out.h[_ring(n)] - 64.0) <= 1.0)
    assert out.h[n // 2, n // 2] == pytest.approx(100.0, abs=1.0)
    auto = _recipe(n=n, site={"read": "site"})
    assert R.build_field(auto, tmp_path).h[0, 0] == pytest.approx(64.0)
    with pytest.raises(ValueError):
        R.build_field(rec)                       # site without project_dir
    assert R.build_field(_recipe(n=n)).h[0, 0] == pytest.approx(100.0, abs=1e-6)


def test_auto_band_sees_the_field_before_pads(tmp_path):
    n = 40
    _site_around(tmp_path, n)
    plain = R.build_field(_recipe(n=n, site={"read": "site"}), tmp_path)
    pad = {"center": [14, 20], "half": [2, 2], "level": 300, "shoulder": 10}
    padded = R.build_field(_recipe(n=n, site={"read": "site"}, pads=[pad]), tmp_path)
    # columns x >= 28 are beyond the pad's shoulder: only the band could differ there
    assert np.array_equal(plain.h[28:, :], padded.h[28:, :])


# --------------------------------------------------------------------- pads
def test_recipe_pads_are_flat_and_blended():
    rec = _recipe(origin=(-30, 60, -20), n=48,
                  pads=[{"center": [-6, 4], "half": [4, 3], "level": 70, "shoulder": 6}])
    out = R.build_field(rec)
    # world (-6, 4) with origin (-30, -20) -> grid (24, 24)
    assert np.all(out.h[20:29, 21:28] == 70.0)
    assert out.h[24, 24 + 3 + 6] == pytest.approx(100.0, abs=1e-6)   # past the shoulder
    assert 70.0 < out.h[24, 24 + 3 + 3] < 100.0                       # blended over it


def test_two_nearby_pads_are_both_flat_and_exact():
    pads = [{"center": [10, 20], "half": [3, 3], "level": 70},
            {"center": [18, 20], "half": [3, 3], "level": 80}]
    for order in (pads, pads[::-1]):
        out = R.build_field(_recipe(n=40, pads=order))
        assert np.all(out.h[7:14, 17:24] == 70.0)
        assert np.all(out.h[15:22, 17:24] == 80.0)


def test_pads_overlapping_at_different_levels_error():
    over = [{"center": [10, 20], "half": [3, 3], "level": 70},
            {"center": [13, 20], "half": [3, 3], "level": 80}]
    with pytest.raises(ValueError, match="overlap"):
        R.build_field(_recipe(n=40, pads=over))
    same = [dict(p, level=70) for p in over]
    assert np.all(R.build_field(_recipe(n=40, pads=same)).h[7:17, 17:24] == 70.0)


def test_pad_integer_levels_only():
    for bad in (70.5, True):
        with pytest.raises(ValueError, match="integer"):
            R.build_field(_recipe(pads=[{"center": [10, 10], "half": [2, 2], "level": bad}]))


def test_pad_on_the_ring_errors_but_an_exactly_touching_shoulder_does_not(tmp_path):
    n = 32
    _site_around(tmp_path, n)
    near = _recipe(n=n, site={"read": "site", "band": 6},
                   pads=[{"center": [3, 16], "half": [3, 3], "level": 90}])
    with pytest.raises(ValueError, match="pad 0"):
        R.build_field(near, tmp_path)
    # ring column x = 0 is exactly `shoulder` (9) from the footprint x 9..15: weight 0
    touch = _recipe(n=n, site={"read": "site", "band": 6},
                    pads=[{"center": [12, 16], "half": [3, 3], "level": 90}])
    out = R.build_field(touch, tmp_path)
    assert np.all(np.abs(out.h[_ring(n)] - 64.0) <= 1.0)
    assert np.all(out.h[9:16, 13:20] == 90.0)


def test_pads_in_a_site_field_stay_flat_with_negative_origin(tmp_path):
    n = 60
    _site_around(tmp_path, n, origin=(-50, -60))
    rec = _recipe(origin=(-50, 0, -60), n=n, site={"read": "site", "band": 6},
                  pads=[{"center": [-30, -30], "half": [3, 3], "level": 80},
                        {"center": [-22, -30], "half": [3, 3], "level": 75}])
    out = R.build_field(rec, tmp_path)           # grid centres (20, 30) and (28, 30)
    assert np.all(out.h[17:24, 27:34] == 80.0) and np.all(out.h[25:32, 27:34] == 75.0)
    assert np.all(np.abs(out.h[_ring(n)] - 64.0) <= 1.0)


# ------------------------------------------------------ ground_for, edges
def test_ground_for_crops_and_errors(tmp_path):
    ground = {(x, z): 60 + x for x in range(-8, 40) for z in range(-8, 40)}
    make_site(tmp_path / "site", (-8, 0, -8, 39, 100, 39), ground=ground)
    rec = _recipe(origin=(2, 0, 3), n=10, site={"read": "site"})
    _site, _surf, g = ground_for(rec, tmp_path)
    assert g.shape == (10, 10) and g[0, 0] == 62 and g[9, 5] == 71
    with pytest.raises(ValueError, match="site read"):
        ground_for(_recipe(origin=(30, 0, 0), n=20, site={"read": "site"}), tmp_path)
    make_site(tmp_path / "bare", (0, 0, 0, 7, 10, 7), ground=-5)   # no solid block
    with pytest.raises(ValueError, match="no solid block"):
        ground_for(_recipe(origin=(0, 0, 0), n=8, site={"read": "bare"}), tmp_path)


def test_edge_match_fails_without_blend(tmp_path):
    n = 32
    _site_around(tmp_path, n)
    rec = _recipe(n=n, site={"read": "site", "band": 6})
    _s, _surf, g = ground_for(rec, tmp_path)
    raw = R.build_field(_recipe(n=n))
    bad = verify(raw, ground=g)
    assert not bad.ok and any(c[0] == "edge_match" and not c[1] and "(0,0)" in c[2]
                              for c in bad.checks)
    good = verify(R.build_field(rec, tmp_path), ground=g)
    assert [c for c in good.checks if c[0] == "edge_match"][0][1]
    assert "edge_match" not in [c[0] for c in verify(raw).checks]


def test_edge_match_rounds_like_the_build():
    g = np.full((6, 6), 63.0)
    ok = verify(_field(np.full((6, 6), 64.4)), ground=g)          # builds as 64: one above
    bad = verify(_field(np.full((6, 6), 64.6)), ground=g)         # builds as 65: two above
    assert [c for c in ok.checks if c[0] == "edge_match"][0][1]
    assert not [c for c in bad.checks if c[0] == "edge_match"][0][1]


# -------------------------------------------------------------- water plan
def _channel(sill_h):
    h = np.full((20, 10), 80.0)
    h[:, 4] = 40.0
    h[10, 4] = sill_h
    return _field(h, sea=30.0)


def test_water_at_edge_must_meet_existing_water():
    n = 12
    h = np.full((n, n), 50.0)
    h[0:4, 4:8] = 40.0                       # basin touching the x=0 edge
    hf = _field(h, sea=30.0)
    rec = {"origin": [0, 0, 0], "sea_level": 30, "water": [{"at": [2, 5], "level": 45}]}
    w = water_levels(hf, rec)
    no_still = np.full((n, n), np.nan)       # existing_water is L: no still liquid outside
    r = verify(hf, water=w, existing_water=no_still)
    assert any(c[0] == "water_contained" and not c[1] for c in r.checks)
    r = verify(hf, water=w)
    assert any(c[0] == "water_contained" and not c[1] for c in r.checks)
    r = verify(hf, water=w, existing_water=np.full((n, n), 45.0))
    assert all(c[1] for c in r.checks if c[0] in ("water_contained", "no_dry_shelf"))


def test_water_spill_and_dry_shelf_fail():
    n = 10
    h = np.full((n, n), 50.0)
    h[3:6, 3:6] = 40.0
    w = np.full((n, n), np.nan); w[3:6, 3:6] = 45.0
    ok = verify(_field(h, 30.0), water=w)
    assert all(c[1] for c in ok.checks if c[0] in ("water_contained", "no_dry_shelf"))
    h2 = h.copy(); h2[6, 4] = 41.0           # lower than the water beside it and dry
    names = {c[0]: c for c in verify(_field(h2, 30.0), water=w).checks}
    assert not names["water_contained"][1] and "(5,4)" in names["water_contained"][2]
    assert not names["no_dry_shelf"][1] and "(6,4)" in names["no_dry_shelf"][2]


def test_basin_flood_fill_stays_in_its_basin():
    n = 20
    h = np.full((n, n), 40.0)
    h[:, 10] = 70.0                           # a ridge
    hf = _field(h, sea=30.0)
    rec = {"origin": [-5, 0, -5], "sea_level": 30, "water": [{"at": [-3, -2], "level": 50}]}
    w = water_levels(hf, rec)                 # grid (2, 3)
    assert np.all(w[:, :10] == 50.0) and np.all(np.isnan(w[:, 10:]))
    with pytest.raises(ValueError):
        water_levels(hf, {**rec, "water": [{"at": [100, 0], "level": 50}]})
    with pytest.raises(ValueError):
        water_levels(hf, {**rec, "water": [{"at": [0, 5], "level": 50}]})   # on the ridge
    sea = water_levels(_field(h, sea=45.0), {"origin": [0, 0, 0], "sea_level": 45})
    assert np.all(sea[:, :10] == 45.0) and np.isnan(sea[0, 10])


def test_two_reaches_with_a_sill_keep_both_levels():
    entries = [{"at": [2, 4], "level": 50}, {"at": [15, 4], "level": 45}]
    for water in (entries, entries[::-1]):
        w = water_levels(_channel(52.0), {"origin": [0, 0, 0], "water": water})
        assert np.all(w[0:10, 4] == 50.0) and np.all(w[11:20, 4] == 45.0)
        assert np.isnan(w[10, 4])


def test_same_channel_without_a_sill_errors_in_both_orders():
    entries = [{"at": [2, 4], "level": 50}, {"at": [15, 4], "level": 45}]
    for water in (entries, entries[::-1]):
        with pytest.raises(ValueError) as err:
            water_levels(_channel(47.0), {"origin": [0, 0, 0], "water": water})
        msg = str(err.value)
        assert "50" in msg and "45" in msg and "(" in msg
    same = [{"at": [2, 4], "level": 45}, {"at": [15, 4], "level": 45}]
    assert np.all(water_levels(_channel(40.0), {"origin": [0, 0, 0], "water": same})[:, 4] == 45)


def _lake_field():
    h = np.full((20, 20), 80.0)
    h[5:10, 5:10] = 55.0                      # enclosed lake bed
    h[18:20, 15] = 55.0                       # a puddle that reaches the outer ring
    return h


def test_enclosed_lake_above_sea_level_passes_and_the_open_sea_stays_sea():
    rec = {"origin": [0, 0, 0], "sea_level": 62, "water": [{"at": [7, 7], "level": 70}]}
    w = water_levels(_field(_lake_field(), sea=30.0), rec)
    assert np.all(w[5:10, 5:10] == 70.0)
    assert np.all(w[18:20, 15] == 62.0) and np.isnan(w[0, 0])


def test_flood_into_the_open_sea_at_another_level_errors():
    h = _lake_field()
    h[10:18, 7] = 55.0; h[17, 7:16] = 55.0; h[17:20, 15] = 55.0    # a channel to the ring
    rec = {"origin": [0, 0, 0], "sea_level": 62, "water": [{"at": [7, 7], "level": 70}]}
    with pytest.raises(ValueError, match="`water` entry"):
        water_levels(_field(h, sea=30.0), rec)
    ok = {**rec, "water": [{"at": [7, 7], "level": 62}]}
    assert np.all(water_levels(_field(h, sea=30.0), ok)[5:10, 5:10] == 62.0)


def test_water_rounds_the_field_like_the_build():
    rec = {"origin": [0, 0, 0], "water": [{"at": [1, 1], "level": 45}]}
    h = np.full((6, 6), 50.0)
    h[1, 1] = 40.0; h[2, 1] = 44.6           # 44.6 builds as 45: not below the level
    w = water_levels(_field(h, 30.0), rec)
    assert w[1, 1] == 45 and np.isnan(w[2, 1])
    h[2, 1] = 44.4                            # builds as 44: flooded
    assert water_levels(_field(h, 30.0), rec)[2, 1] == 45
    hh = np.full((6, 6), 60.0); hh[2:4, 2:4] = 40.0; hh[1, 2] = 44.6
    ww = np.full((6, 6), np.nan); ww[2:4, 2:4] = 45.0
    names = {c[0]: c for c in verify(_field(hh, 30.0), water=ww).checks}
    assert names["water_contained"][1] and names["no_dry_shelf"][1]


def test_levels_must_be_integers():
    hf = _field(np.full((6, 6), 30.0), 20.0)
    for bad in (45.5, True):
        with pytest.raises(ValueError, match="integer"):
            water_levels(hf, {"origin": [0, 0, 0], "water": [{"at": [1, 1], "level": bad}]})


def test_surface_y_rounds_and_keeps_nan():
    out = surface_y(np.array([44.4, 44.6, np.nan, -0.6]))
    assert out[0] == 44 and out[1] == 45 and np.isnan(out[2]) and out[3] == -1


# ------------------------------------------------------ sea level with a site
def test_site_without_sea_level_plans_no_water_and_keeps_land(tmp_path):
    n = 32
    _site_around(tmp_path, n, ground=50)
    rec = _recipe(n=n, graph={"type": "Constant", "value": 50.0},
                  erosion={"thermal": {"iterations": 2}, "fluvial": {"threshold": 5.0}},
                  site={"read": "site", "band": 6})
    del rec["sea_level"]
    info = {}
    hf = R.build_field(rec, tmp_path, info)
    assert hf.sea_level < hf.h.min()
    assert np.all(np.isnan(water_levels(hf, rec)))
    land = [c for c in verify(hf).checks if c[0] == "land_present"][0]
    assert land[1], land
    assert info["held_columns"] == 0


def test_site_with_non_integer_sea_level_errors(tmp_path):
    _site_around(tmp_path, 32)
    for bad in (62.5, True):
        with pytest.raises(ValueError, match="sea_level"):
            R.build_field(_recipe(n=32, sea_level=bad, site={"read": "site"}), tmp_path)


def test_site_belt_without_interior_level_or_base_errors(tmp_path):
    n = 32
    _site_around(tmp_path, n)
    belt = {"centerline": [[4, 4], [27, 27]], "corridor_half": 2.0,
            "keypoints": [{"s": 0.0, "peak": 5, "rise": 4}]}
    rec = _recipe(n=n, site={"read": "site"}, belt=belt)
    del rec["sea_level"]; del rec["graph"]
    with pytest.raises(ValueError, match="base"):
        R.build_field(rec, tmp_path)
    belt2 = {**belt, "keypoints": [{"s": 0.0, "peak": 5, "rise": 4, "base": 80}]}
    with pytest.raises(ValueError, match="interior_level"):
        R.build_field({**rec, "belt": belt2}, tmp_path)
    belt3 = {**belt2, "interior_level": 70}
    assert R.build_field({**rec, "belt": belt3}, tmp_path).nx == n


# -------------------------------------------------------- existing liquid
def _pond_site():
    """Ground 64 with a pond at x 4..7, z 4..7: ground 60, still water 61..64."""
    cells = {(x, y, z): WATER for x in range(4, 8) for z in range(4, 8) for y in range(61, 65)}
    ground = {(x, z): 60 for x in range(4, 8) for z in range(4, 8)}
    return _site_in_memory((-8, 0, -8, 23, 100, 23), ground, cells)


def test_predicates():
    assert is_retained("minecraft:water[level=0]") and is_retained("minecraft:lava[level=0]")
    assert is_retained("minecraft:kelp[age=3]") and is_retained(LEAF_WL)
    assert not is_retained("minecraft:oak_leaves[distance=1]") and not is_retained(STONE)
    assert is_retained("minecraft:ice", below_is_water=True)
    assert not is_retained("minecraft:ice")
    assert is_still(WATER) and is_still("minecraft:bubble_column[drag=true]")
    assert not is_still(FLOW) and not is_still("minecraft:lava[level=2]")
    assert is_still("minecraft:lava[level=0]")


def test_liquid_levels_pond_and_dry():
    ll = liquid_levels(_pond_site())
    assert isinstance(ll, LiquidLevels)
    i = 5 + 8                                 # site origin is (-8, -8)
    assert ll.level[i, i] == 64 and ll.kind[i, i] == "water" and ll.top[i, i] == 64
    assert np.isnan(ll.level[0, 0]) and ll.kind[0, 0] is None and np.isnan(ll.top[0, 0])
    assert ll.joined == {}


def test_waterlogged_leaf_high_above_dry_ground_gives_no_level():
    leaf = _site_in_memory((-8, 0, -8, 23, 100, 23), {}, {(12, 70, 12): LEAF_WL})
    ll = liquid_levels(leaf)
    i = 12 + 8
    assert np.isnan(ll.level[i, i]) and ll.top[i, i] == 70


def test_stepped_stream_and_flowing_cell_give_no_level():
    site = _site_in_memory((-8, 0, -8, 23, 100, 23), {(3, 3): 60, (5, 5): 60},
                           {(3, 61, 3): FLOW,        # flowing, right on the ground
                            (5, 62, 5): WATER})      # still, but a cell above the ground
    ll = liquid_levels(site)
    for x, z, top in ((3, 3, 61), (5, 5, 62)):
        assert np.isnan(ll.level[x + 8, z + 8]) and ll.top[x + 8, z + 8] == top


def test_trunk_standing_in_a_pond_joins_its_water():
    trunk = {(5, y, 5): LOG for y in range(61, 71)}
    cells = {(x, y, z): WATER for x in range(4, 8) for z in range(4, 8) for y in range(61, 65)}
    cells.update(trunk)
    ground = {(x, z): 60 for x in range(4, 8) for z in range(4, 8)}
    site = _site_in_memory((-8, 0, -8, 23, 100, 23), ground, cells)
    assert np.isnan(liquid_levels(site).level[5 + 8, 5 + 8])
    ll = liquid_levels(site, removed=trunk.keys())
    assert ll.level[5 + 8, 5 + 8] == 64 and ll.kind[5 + 8, 5 + 8] == "water"
    assert ll.joined == {(5, y, 5): "water" for y in range(61, 65)}
    assert np.isnan(ll.top[5 + 8, 5 + 8])     # the trunk column holds no liquid of its own


def test_liquid_levels_is_linear_enough_for_a_300_site():
    x1, y1, z1, x2, y2, z2 = box = (0, 0, 0, 299, 80, 299)
    columns = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            if 100 <= x < 200 and 100 <= z < 200:
                columns[(x, z)] = [(0, 59, STONE), (60, 60, GRASS), (61, 64, WATER),
                                   (65, 80, AIR)]
            else:
                columns[(x, z)] = [(0, 63, STONE), (64, 64, GRASS), (65, 80, AIR)]
    site = Site(box=box, world=None, columns=columns)
    removed = {(150, y, z) for z in range(100, 200) for y in range(61, 70)}
    t0 = time.perf_counter()
    ll = liquid_levels(site, removed=removed)
    assert time.perf_counter() - t0 < 20
    assert ll.level[120, 120] == 64 and len(ll.joined) == 100 * 4


# ------------------------------------------------------------- hold_shores
def _river(origin):
    ox, oz = origin
    n = 16
    ground = {(ox + x, oz + z): 60 for x in range(-8, n + 8) for z in (8, 9)}
    cells = {(ox + x, y, oz + z): WATER for x in range(-8, n + 8) for z in (8, 9)
             for y in range(61, 65)}
    ground[(ox + 3, oz + 2)] = 60
    cells[(ox + 3, 61, oz + 2)] = FLOW
    return _site_in_memory((ox - 8, 0, oz - 8, ox + n + 7, 100, oz + n + 7), ground, cells)


@pytest.mark.parametrize("origin", [(0, 0), (-10, -5), (-30, 20)])
def test_hold_shores_on_a_river_bank_and_a_flowing_column(origin):
    n = 16
    site = _river(origin)
    h = np.full((n, n), 50.0)
    h[5, 10] = 63.6                            # builds as 64: already at the bank
    skip = np.zeros((n, n), bool); skip[12:15, 10:13] = True
    before = h.copy()
    out = hold_shores(h, site, origin=origin, skip=skip)
    assert np.array_equal(h, before) and out is not h
    assert np.all(out[:, 8:10] == 50.0)        # river columns hold a still level: untouched
    assert np.all(out[1:15, 7] == 64.0)        # the south... bank beside the river is held
    bank = [x for x in range(1, 15) if x != 5 and not skip[x, 10]]
    assert np.all(out[bank, 10] == 64.0) and out[5, 10] == 63.6
    assert np.all(out[12:15, 10:13] == 50.0)   # footprint skipped
    assert out[3, 2] == 60.0                   # liquid with no still level: up to the ground
    assert out[2, 2] == 61.0 and out[4, 2] == 61.0 and out[3, 1] == 61.0 and out[3, 3] == 61.0
    assert out[8, 3] == 50.0                   # nothing near it
    ring = _ring(n)
    assert np.array_equal(out[ring], before[ring])             # the outer ring never changes


def test_hold_shores_recipe_key(tmp_path):
    n = 24
    river = {(x, z): 60 for x in range(-8, n + 8) for z in (8, 9)}
    cells = {(x, y, z): WATER for x in range(-8, n + 8) for z in (8, 9) for y in range(61, 65)}
    write_site(tmp_path / "site", _site_in_memory((-8, 0, -8, n + 7, 100, n + 7), river, cells))
    rec = _recipe(n=n, graph={"type": "Constant", "value": 50.0},
                  site={"read": "site", "band": 4}, hold_shores=True,
                  pads=[{"center": [12, 6], "half": [1, 1], "level": 55, "shoulder": 2}])
    info = {}
    out = R.build_field(rec, tmp_path, info)
    assert np.all(out.h[11:14, 5:8] == 55.0)                   # the footprint was skipped
    assert out.h[5, 7] == 64.0 and out.h[5, 10] == 64.0        # the bank is held
    assert info["held_columns"] > 0
    off = R.build_field({**rec, "hold_shores": False}, tmp_path)
    assert off.h[5, 7] == 50.0
    for bad in ("yes", 1, None):
        with pytest.raises(ValueError, match="hold_shores"):
            R.build_field({**rec, "hold_shores": bad}, tmp_path)
    with pytest.raises(ValueError, match="hold_shores"):
        R.build_field(_recipe(n=n, hold_shores=True))


# ----------------------------------------------- R22: trees over water, felled
def test_felled_trunk_below_the_pond_bed_joins_the_water_down_to_its_ground():
    """Trunk column ground 74 in a pond whose bed is 76 and surface 80: felling the tree
    must leave water, not air, from 75 up to 80."""
    pond = [(x, z) for x in range(4, 8) for z in range(4, 8)]
    ground = {c: 76 for c in pond}
    ground[(5, 5)] = 74
    trunk = {(5, y, 5): LOG for y in range(75, 91)}
    cells = {(x, y, z): WATER for (x, z) in pond if (x, z) != (5, 5) for y in range(77, 81)}
    cells.update(trunk)
    site = _site_in_memory((-8, 0, -8, 23, 100, 23), ground, cells)
    ll = liquid_levels(site, removed=trunk.keys())
    assert ll.level[5 + 8, 5 + 8] == 80 and ll.kind[5 + 8, 5 + 8] == "water"
    assert set(ll.joined) == {(5, y, 5) for y in range(75, 81)}    # none above the surface
    assert np.isnan(liquid_levels(site).level[5 + 8, 5 + 8])


def test_hold_shores_holds_a_bank_beside_a_leaf_at_the_surface_y():
    """A leaf at y 64 over the pond beside a bank column: with the tree removed it is
    water, so the bank must be held up to 64, not just to the retained top 63."""
    pond = [(x, z) for x in range(4, 7) for z in range(5, 8)]
    ground = {c: 60 for c in pond}
    cells = {(x, y, z): WATER for (x, z) in pond for y in range(61, 65)}
    cells.update({(5, y, 6): LOG for y in range(61, 71)})    # a trunk in the pond, and a leaf at its surface y
    cells[(5, 64, 5)] = "minecraft:oak_leaves[distance=1,persistent=false]"
    site = _site_in_memory((-8, 0, -8, 23, 100, 23), ground, cells)
    removed = [c for t in find_trees(site) for c in t.cells]
    assert (5, 64, 5) in removed
    assert liquid_levels(site, removed=removed).joined[(5, 64, 5)] == "water"
    h = np.full((16, 16), 50.0)
    out = hold_shores(h, site, origin=(0, 0))
    assert out[5, 4] == 64.0                                 # bank beside the leaf column
    assert out[2, 2] == 50.0


