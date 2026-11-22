"""Blending into the existing ground, pads, water plans and the edge/water checks."""
import numpy as np
import pytest

from sitegen import make_site
from terrain import recipe as R
from terrain.field import HeightField
from terrain.site import (auto_band, blend_to_existing, ground_for, water_levels)
from terrain.verify import verify


def _recipe(origin=(0, 0, 0), n=32, **extra):
    rec = {"version": 1, "origin": list(origin), "nx": n, "nz": n, "sea_level": 40,
           "seed": 3, "graph": {"type": "Constant", "value": 100.0}}
    rec.update(extra)
    return rec


def _field(h, sea=40.0):
    hf = HeightField(h.shape[0], h.shape[1], sea_level=sea)
    hf.h = h.astype(float).copy()
    return hf


def _cone(n, peak=164.0, base=64.0):
    x, z = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    r = np.hypot(x - (n - 1) / 2, z - (n - 1) / 2)
    return np.clip(peak - r * 8.0, base, peak)


def test_recipe_pads_are_flat_and_blended(tmp_path):
    rng = np.random.default_rng(1)
    hf = _field(rng.uniform(90, 110, (48, 48)))
    base = hf.h.copy()
    rec = _recipe(origin=(-30, 60, -20), n=48,
                  graph={"type": "Constant", "value": 100.0})
    rec["pads"] = [{"center": [-6, 4], "half": [4, 3], "level": 70, "shoulder": 6}]
    out = R.build_field(rec)
    # world (-6, 4) with origin (-30, -20) -> grid (24, 24)
    assert np.all(out.h[20:29, 21:28] == 70.0)
    assert out.h[24, 24 + 3 + 6] == pytest.approx(100.0, abs=1.0)   # past the shoulder
    mid = out.h[24, 24 + 3 + 3]
    assert 70.0 < mid < 100.0                                         # blended over the shoulder
    assert base is not None


def test_blend_matches_ring_and_keeps_interior(tmp_path):
    n = 64
    ground = np.full((n, n), 64.0)
    hf = _field(_cone(n))
    band = 10
    out = blend_to_existing(hf, ground, band)
    ring = np.zeros((n, n), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    assert np.all(np.abs(out.h[ring] - 64.0) <= 1.0)
    assert out.h[n // 2, n // 2] == hf.h[n // 2, n // 2]
    assert np.array_equal(out.h[band:n - band, band:n - band], hf.h[band:n - band, band:n - band])
    assert out is not hf and hf.h[n // 2, n // 2] == 164.0 - 8 * 0.5 * np.sqrt(2)


def test_auto_band_grows_with_difference():
    h = np.full((64, 64), 110.0); g = np.full((64, 64), 64.0)
    assert auto_band(h, g) == 14 and auto_band(g + 1, g) == 8
    assert auto_band(np.full((20, 20), 500.0), np.full((20, 20), 0.0)) == 10   # cap n // 2


def test_recipe_with_site_blends_after_erosion(tmp_path):
    n = 32
    make_site(tmp_path / "site", (-8, 0, -8, n + 7, 200, n + 7), ground=64)
    rec = _recipe(n=n)
    rec["erosion"] = {"thermal": {"iterations": 2}}
    rec["site"] = {"read": "site", "band": 6}
    out = R.build_field(rec, tmp_path)
    ring = np.zeros((n, n), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    assert np.all(np.abs(out.h[ring] - 64.0) <= 1.0)
    assert out.h[n // 2, n // 2] == pytest.approx(100.0, abs=1.0)
    auto = _recipe(n=n); auto["site"] = {"read": "site"}
    assert R.build_field(auto, tmp_path).h[0, 0] == pytest.approx(64.0)
    with pytest.raises(ValueError):
        R.build_field(rec)                       # site without project_dir
    # no site: unchanged behaviour
    assert R.build_field(_recipe(n=n)).h[0, 0] == pytest.approx(100.0, abs=1e-6)


def test_pad_near_edge_still_meets_ground(tmp_path):
    n = 32
    make_site(tmp_path / "site", (-8, 0, -8, n + 7, 200, n + 7), ground=64)
    rec = _recipe(n=n, site={"read": "site", "band": 6},
                  pads=[{"center": [3, 16], "half": [3, 3], "level": 90}])
    out = R.build_field(rec, tmp_path)
    assert np.all(np.abs(out.h[0, :] - 64.0) <= 1.0) and np.all(np.abs(out.h[:, 0] - 64.0) <= 1.0)


def test_ground_for_crops_and_errors(tmp_path):
    ground = {(x, z): 60 + x for x in range(-8, 40) for z in range(-8, 40)}
    make_site(tmp_path / "site", (-8, 0, -8, 39, 100, 39), ground=ground)
    rec = _recipe(origin=(2, 0, 3), n=10, site={"read": "site"})
    site, surf, g = ground_for(rec, tmp_path)
    assert g.shape == (10, 10) and g[0, 0] == 62 and g[9, 5] == 71
    with pytest.raises(ValueError, match="site read"):
        ground_for(_recipe(origin=(30, 0, 0), n=20, site={"read": "site"}), tmp_path)
    make_site(tmp_path / "bare", (0, 0, 0, 7, 10, 7), ground=-5)   # no solid block
    with pytest.raises(ValueError, match="no solid block"):
        ground_for(_recipe(origin=(0, 0, 0), n=8, site={"read": "bare"}), tmp_path)


def test_edge_match_fails_without_blend(tmp_path):
    n = 32
    make_site(tmp_path / "site", (-8, 0, -8, n + 7, 200, n + 7), ground=64)
    rec = _recipe(n=n, site={"read": "site", "band": 6})
    _, _, g = ground_for(rec, tmp_path)
    raw = R.build_field(_recipe(n=n))
    bad = verify(raw, ground=g)
    assert not bad.ok and any(c[0] == "edge_match" and not c[1] and "(0,0)" in c[2]
                              for c in bad.checks)
    good = verify(R.build_field(rec, tmp_path), ground=g)
    assert [c for c in good.checks if c[0] == "edge_match"][0][1]
    assert "edge_match" not in [c[0] for c in verify(raw).checks]


def test_water_at_edge_must_meet_existing_water():
    n = 12
    h = np.full((n, n), 50.0)
    h[0:4, 4:8] = 40.0                       # basin touching the x=0 edge
    hf = _field(h, sea=30.0)
    rec = {"origin": [0, 0, 0], "sea_level": 30, "water": [{"at": [2, 5], "level": 45}]}
    w = water_levels(hf, rec)
    # outside dry and lower: fails
    dry = np.full((n, n), np.nan)
    r = verify(hf, water=w, existing_water=dry)
    assert not r.ok and any(c[0] == "water_contained" and not c[1] for c in r.checks)
    r = verify(hf, water=w)
    assert any(c[0] == "water_contained" and not c[1] for c in r.checks)
    same = np.full((n, n), 45.0)
    r = verify(hf, water=w, existing_water=same)
    assert all(c[1] for c in r.checks if c[0] in ("water_contained", "no_dry_shelf"))


def test_water_spill_and_dry_shelf_fail():
    n = 10
    h = np.full((n, n), 50.0)
    h[3:6, 3:6] = 40.0
    hf = _field(h, sea=30.0)
    w = np.full((n, n), np.nan); w[3:6, 3:6] = 45.0
    ok = verify(hf, water=w)
    assert all(c[1] for c in ok.checks if c[0] in ("water_contained", "no_dry_shelf"))
    h2 = h.copy(); h2[6, 4] = 41.0           # lower than the water beside it and dry
    spill = verify(_field(h2, 30.0), water=w)
    names = {c[0]: c for c in spill.checks}
    assert not names["water_contained"][1] and "(5,4)" in names["water_contained"][2]
    assert not names["no_dry_shelf"][1] and "(6,4)" in names["no_dry_shelf"][2]


def test_basin_flood_fill_stays_in_its_basin():
    n = 20
    h = np.full((n, n), 40.0)
    h[:, 10] = 70.0                           # a ridge
    hf = _field(h, sea=30.0)
    rec = {"origin": [-5, 0, -5], "sea_level": 30,
           "water": [{"at": [-3, -2], "level": 50}]}      # grid (2, 3)
    w = water_levels(hf, rec)
    assert np.all(w[:, :10] == 50.0) and np.all(np.isnan(w[:, 10:]))
    with pytest.raises(ValueError):
        water_levels(hf, {**rec, "water": [{"at": [100, 0], "level": 50}]})
    with pytest.raises(ValueError):
        water_levels(hf, {**rec, "water": [{"at": [0, 5], "level": 50}]})   # on the ridge
    sea = water_levels(_field(h, sea=45.0), {"origin": [0, 0, 0], "sea_level": 45})
    assert np.all(sea[:, :10] == 45.0) and np.isnan(sea[0, 10])
