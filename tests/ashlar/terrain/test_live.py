"""Live materialisation (spec 7.5, rulings R15/R18/R22): exactly the cells to write, fills,
tiles, liquid checks and the expected surface."""
import hashlib

import numpy as np
import pytest
from sitegen import AIR, LEAVES, LOG, STONE, WATER, make_site, tree
from terrain.field import HeightField
from terrain.live import (
    LiveWrite,
    decode,
    expected_surface,
    greedy_fills,
    liquid_violations,
    materialize_live,
    split_columns,
)
from terrain.materialize import MaterialSpec
from terrain.recipe import build_field
from terrain.site import (
    drain_bodies,
    find_trees,
    hold_shores,
    liquid_levels,
    water_levels,
)

BOX = (0, 40, 0, 7, 100, 7)
LAVA = "minecraft:lava[level=0]"
FLOW = "minecraft:water[level=3]"
LEAF_WL = "minecraft:oak_leaves[distance=1,persistent=false,waterlogged=true]"


# ----------------------------------------------------------------- helpers
def spec(strata=None):
    s = MaterialSpec(layers=[], base={"minecraft:grass_block": 1.0},
                     subsurface="minecraft:dirt", subsurface_depth=3, stone="minecraft:stone")
    if strata:
        s.strata = strata
    return s


def field(h):
    h = np.asarray(h, dtype=float)
    hf = HeightField(h.shape[0], h.shape[1], sea_level=-100.0)
    hf.h = h.copy()
    return hf


def rec(ox, oz, nx, nz, **extra):
    out = {"origin": [ox, 0, oz], "nx": nx, "nz": nz}
    out.update(extra)
    return out


def written(w):
    """{(x, y, z): palette string} for every code > 0."""
    ox, oy, oz = w.origin
    return {(int(x) + ox, int(y) + oy, int(z) + oz): w.palette[int(w.codes[x, y, z])]
            for x, y, z in np.argwhere(w.codes > 0)}


def code_at(w, cell):
    ox, oy, oz = w.origin
    x, y, z = cell[0] - ox, cell[1] - oy, cell[2] - oz
    nx, ny, nz = w.codes.shape
    if 0 <= x < nx and 0 <= y < ny and 0 <= z < nz:
        return int(w.codes[x, y, z])
    return 0


def state_after(site, w, cell):
    c = code_at(w, cell)
    return w.palette[c] if c else site.block(*cell)


def ground_map(box, base=64, overrides=None):
    x1, _, z1, x2, _, z2 = box
    g = {(x, z): base for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}
    g.update(overrides or {})
    return g


def to_array(box, ground):
    x1, _, z1, x2, _, z2 = box
    return np.array([[float(ground[(x, z)]) for z in range(z1, z2 + 1)]
                     for x in range(x1, x2 + 1)])


def water_cells(ground, cols, level, state=WATER):
    return {(x, y, z): state for (x, z) in cols for y in range(ground[(x, z)] + 1, level + 1)}


POND = [(3, 3), (3, 4), (4, 3), (4, 4)]


def pond_world(tmp_path, kinds=None, bank=64, bed=60, box=BOX, extra=None):
    """Banks at `bank`, a 2 x 2 pond with a bed at `bed` holding the given cells y 61..63."""
    kinds = kinds or [WATER, WATER, WATER]
    g = ground_map(box, bank, {c: bed for c in POND})
    cells = {}
    for (x, z) in POND:
        for i, st in enumerate(kinds):
            cells[(x, bed + 1 + i, z)] = st
    cells.update(extra or {})
    return make_site(tmp_path / "s", box, ground=g, cells=cells), g


def manual(site, cells):
    """A LiveWrite from {(x, y, z): state} over their bounding box."""
    xs, ys, zs = zip(*cells)
    origin = (min(xs), min(ys), min(zs))
    palette = ["skip", "minecraft:air"]
    codes = np.zeros((max(xs) - origin[0] + 1, max(ys) - origin[1] + 1, max(zs) - origin[2] + 1),
                     np.uint16)
    for (x, y, z), st in cells.items():
        if st not in palette:
            palette.append(st)
        codes[x - origin[0], y - origin[1], z - origin[2]] = palette.index(st)
    return LiveWrite(origin=origin, codes=codes, palette=palette)


# -------------------------------------------------------- brief: the ten tests
def test_raised_ground_fills_from_old_ground_minus_seal(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    w = materialize_live(field(np.full((8, 8), 70.0)), spec(), site, None)
    cells = written(w)
    assert w.origin == (0, 60, 0) and w.codes.shape == (8, 11, 8)
    assert w.palette[0] == "skip" and w.palette[1] == "minecraft:air"
    for x in range(8):
        for z in range(8):
            assert all((x, y, z) not in cells for y in range(40, 60))
            assert all(cells[(x, y, z)] == "minecraft:stone" for y in range(60, 67))
            assert all(cells[(x, y, z)] == "minecraft:dirt" for y in range(67, 70))
            assert cells[(x, 70, z)] == "minecraft:grass_block"
            assert (x, 71, z) not in cells
    assert w.removed_trees == 0 and w.reach == 0


def test_lowered_ground_clears_air_to_old_top(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    w = materialize_live(field(np.full((8, 8), 58.0)), spec(), site, None)
    cells = written(w)
    assert w.origin[1] == 54
    for (x, z) in [(0, 0), (3, 3), (7, 5)]:
        assert cells[(x, 54, z)] == "minecraft:stone"
        assert all(cells[(x, y, z)] == "minecraft:dirt" for y in range(55, 58))
        assert cells[(x, 58, z)] == "minecraft:grass_block"
        assert all(cells[(x, y, z)] == "minecraft:air" for y in range(59, 65))
        assert (x, 65, z) not in cells and (x, 53, z) not in cells


def test_cliff_faces_and_seal_band(tmp_path):
    h = np.full((8, 8), 60.0)
    h[4:, :] = 80.0
    site = make_site(tmp_path / "s", BOX, ground=64)
    cells = written(materialize_live(field(h), spec(), site, None))
    assert cells[(4, 56, 3)] == "minecraft:stone" and (4, 55, 3) not in cells   # beside s = 60
    assert cells[(3, 56, 3)] == "minecraft:stone" and (3, 55, 3) not in cells
    # a cave pocket just under unchanged ground is sealed
    pocket = make_site(tmp_path / "p", BOX, ground=64, cells={(5, 62, 5): AIR})
    w = materialize_live(field(np.full((8, 8), 64.0)), spec(), pocket, None)
    assert written(w)[(5, 62, 5)] == "minecraft:dirt" and (5, 59, 5) not in written(w)


def test_crossing_trees_removed_whole_or_kept(tmp_path):
    box = (0, 40, 0, 15, 100, 15)
    site = make_site(tmp_path / "s", box, ground=64,
                     trees=[tree(4, 6, 65), tree(2, 12, 65)])
    a, b = sorted(find_trees(site), key=lambda t: sorted(t.trunk_columns))[::-1]
    assert a.trunk_columns == {(4, 6)} and b.trunk_columns == {(2, 12)}
    w = materialize_live(field(np.full((8, 8), 60.0)), spec(), site, rec(4, 4, 8, 8))
    assert w.removed_trees == 1 and w.reach == 2
    assert all(code_at(w, c) == 1 for c in a.cells)
    assert all(code_at(w, c) == 0 for c in b.cells)
    outside = {c for c in written(w) if not (4 <= c[0] <= 11 and 4 <= c[2] <= 11)}
    assert outside and outside <= a.cells


def test_water_fills_between_surface_and_level(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    wl = np.full((8, 8), np.nan)
    wl[3, 3] = 63
    cells = written(materialize_live(field(np.full((8, 8), 60.0)), spec(), site, None, water=wl))
    assert all(cells[(3, y, 3)] == "minecraft:water" for y in (61, 62, 63))
    assert cells[(3, 64, 3)] == "minecraft:air" and cells[(3, 60, 3)] == "minecraft:grass_block"
    assert cells[(2, 61, 3)] == "minecraft:air"


def test_strata_bands_by_absolute_y(tmp_path):
    h = np.full((8, 8), 70.0)
    h[4:, :] = 74.0
    strata = [("minecraft:red_sandstone", 2), ("minecraft:orange_terracotta", 3)]
    site = make_site(tmp_path / "s", BOX, ground=50)
    cells = written(materialize_live(field(h), spec(strata), site, rec(0, 0, 8, 8,
                                     material={"strata_top": 66})))
    for x in (1, 5):
        assert cells[(x, 66, 3)] == cells[(x, 65, 3)] == "minecraft:red_sandstone"
        assert cells[(x, 64, 3)] == cells[(x, 62, 3)] == "minecraft:orange_terracotta"
        assert cells[(x, 61, 3)] == "minecraft:stone"
    assert cells[(5, 67, 3)] == cells[(5, 70, 3)] == "minecraft:stone"      # above the top
    assert cells[(5, 71, 3)] == "minecraft:dirt"
    # default top is max(s) = 74; deep rock ends at s - 4
    w = materialize_live(field(h), spec(strata), site, None)
    assert written(w)[(5, 70, 3)] == "minecraft:orange_terracotta"          # 74 - 70 = 4 -> band 2
    assert written(w)[(1, 66, 3)] == "minecraft:stone"                     # below both bands


def test_greedy_fills_decode_exactly():
    rng = np.random.default_rng(5)
    codes = rng.integers(0, 4, size=(9, 7, 6)).astype(np.uint16)
    codes[2:6, 1:5, 1:4] = 2                         # a solid box to merge
    codes[codes == 3] = 0
    w = LiveWrite(origin=(-4, 10, -7), codes=codes,
                  palette=["skip", "minecraft:air", "minecraft:stone", "minecraft:dirt"])
    fills = greedy_fills(w)
    want = {(x - 4, y + 10, z - 7): w.palette[int(codes[x, y, z])]
            for x, y, z in np.argwhere(codes > 0)}
    assert decode(fills) == want
    volume = sum((f["to"][0] - f["from"][0] + 1) * (f["to"][1] - f["from"][1] + 1)
                 * (f["to"][2] - f["from"][2] + 1) for f in fills)
    assert volume == len(want) and len(fills) < len(want)        # disjoint exact cover, merged
    assert all(f["block"].startswith("minecraft:") for f in fills)
    assert greedy_fills(w) == fills                              # deterministic


def test_split_columns_respects_size():
    codes = np.zeros((300, 3, 20), np.uint16)
    codes[:, 1, :] = 2
    codes[130:140, :, :] = 0
    w = LiveWrite(origin=(-50, 64, 10), codes=codes, palette=["skip", "minecraft:air", "minecraft:stone"])
    tiles = split_columns(w, 128)
    assert tiles and all(t.codes.shape[0] <= 128 and t.codes.shape[2] <= 128 for t in tiles)
    assert all((t.codes > 0).any() for t in tiles)
    merged = {}
    for t in tiles:
        part = written(t)
        assert not set(part) & set(merged)
        merged.update(part)
    assert merged == written(w) and len(merged) == int((codes > 0).sum())
    assert decode(greedy_fills(tiles[-1])) == written(tiles[-1])


def test_expected_surface_marks_water_and_skips_kept_trunks():
    h = np.full((4, 3), 64.0)
    h[1, 1] = 60.4
    water = np.full((4, 3), np.nan)
    water[1, 1] = 63
    out = expected_surface(field(h), water, {(-9, 11)}, (-10, 10))
    assert out["version"] == 1 and out["origin"] == [-10, 10] and out["size"] == [4, 3]
    assert out["top"][1 * 3 + 1] == 63 and out["top"][0] == 64
    assert out["skip"][1 * 3 + 1] == 1 and sum(out["skip"]) == 1
    assert expected_surface(field(h), None, set(), (0, 0))["top"][4] == 60


def test_seal_must_exceed_subsurface_depth(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    hf = field(np.full((8, 8), 64.0))
    for seal in (3, 2, 0):
        with pytest.raises(ValueError, match="seal"):
            materialize_live(hf, spec(), site, None, seal=seal)
    assert materialize_live(hf, spec(), site, None, seal=5).origin[1] == 59


# ------------------------------------------------------------ plumbing rules
def test_negative_origin_and_world_cells(tmp_path):
    box = (-8, 40, -6, -1, 100, -1)
    site = make_site(tmp_path / "s", box, ground=64, trees=[tree(-6, -4, 65)])
    w = materialize_live(field(np.full((8, 6), 70.0)), spec(), site, rec(-8, -6, 8, 6))
    assert w.origin == (-8, 60, -6)
    cells = decode(greedy_fills(w))
    assert cells[(-3, 70, -2)] == "minecraft:grass_block" and cells[(-8, 60, -6)] == "minecraft:stone"
    assert w.removed_trees == 1 and all(code_at(w, c) > 0 for c in find_trees(site)[0].cells)


def test_recipe_none_needs_the_site_box_and_values_are_checked(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    with pytest.raises(ValueError):
        materialize_live(field(np.full((4, 4), 70.0)), spec(), site, None)
    with pytest.raises(ValueError):
        materialize_live(field(np.full((4, 4), 70.0)), spec(), site, rec(6, 6, 4, 4))   # off the site
    with pytest.raises(ValueError):
        materialize_live(field(np.full((8, 8), 400.0)), spec(), site, None)
    h = np.full((8, 8), 70.0)
    h[2, 2] = np.nan
    with pytest.raises(ValueError):
        materialize_live(field(h), spec(), site, None)
    nan_ground = make_site(tmp_path / "n", BOX, ground={(3, 3): 30})
    with pytest.raises(ValueError, match="ground"):
        materialize_live(field(np.full((8, 8), 70.0)), spec(), nan_ground, None)


def test_read_must_cover_what_is_judged(tmp_path):
    low = make_site(tmp_path / "l", (0, 58, 0, 7, 100, 7), ground=64)
    with pytest.raises(ValueError, match="lower"):
        materialize_live(field(np.full((8, 8), 60.0)), spec(), low, None)       # b = 56, read from 58
    ok = materialize_live(field(np.full((8, 8), 64.0)), spec(), low, None)      # b = 60, needs >= 59
    assert ok.origin[1] == 60
    high = make_site(tmp_path / "h", (0, 40, 0, 7, 70, 7), ground=64, cells={(2, 70, 2): STONE})
    with pytest.raises(ValueError, match="higher"):
        materialize_live(field(np.full((8, 8), 64.0)), spec(), high, None)
    floor = make_site(tmp_path / "f", (0, -64, 0, 7, 20, 7), ground=0)
    assert materialize_live(field(np.full((8, 8), -60.0)), spec(), floor, None).origin[1] == -64


def test_protected_columns_are_never_written_and_count_as_ground(tmp_path):
    g = ground_map(BOX, 64, {(3, 3): 60})
    site = make_site(tmp_path / "s", BOX, ground=g, trees=[tree(3, 3, 61), tree(5, 5, 65)])
    prot = np.zeros((8, 8), bool)
    prot[3, 3] = True
    w = materialize_live(field(np.full((8, 8), 70.0)), spec(), site, None, protect=prot)
    cells = written(w)
    assert not any((x, z) == (3, 3) for x, _, z in cells)
    assert cells[(4, 56, 3)] == "minecraft:stone" and (4, 55, 3) not in cells   # n = 60 beside it
    # the tree rooted on the protected column is kept; the one on changed ground is removed
    assert w.removed_trees == 1
    both = materialize_live(field(np.full((8, 8), 70.0)), spec(), site, None, protect=prot)
    assert code_at(both, (3, 62, 3)) == 0
    with pytest.raises(ValueError):
        materialize_live(field(np.full((8, 8), 70.0)), spec(), site, None, protect=np.zeros((3, 3), bool))


def test_removed_tree_cells_in_a_protected_column_are_left(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64, trees=[tree(2, 2, 65)])
    prot = np.zeros((8, 8), bool)
    prot[3, 2] = True                                   # a canopy column
    w = materialize_live(field(np.full((8, 8), 60.0)), spec(), site, None, protect=prot)
    assert w.removed_trees == 1
    assert not any((x, z) == (3, 2) for x, _, z in written(w))
    assert code_at(w, (2, 68, 2)) == 1                  # the trunk column is cleared


def test_kept_trunks_and_liquid_top_skip_leaves(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64, trees=[tree(4, 4, 65)],
                     cells={(2, 70, 6): LEAF_WL})
    w = materialize_live(field(np.full((8, 8), 64.0)), spec(), site, None)
    assert w.kept_trunks == {(4, 4)} and w.removed_trees == 0
    assert np.isnan(w.liquid_top).all()                 # a waterlogged leaf is not a surface
    gone = materialize_live(field(np.full((8, 8), 60.0)), spec(), site, None)
    assert gone.kept_trunks == set() and gone.removed_trees == 1


# --------------------------------------------------------- existing liquid
KEPT = {
    "water": [WATER, WATER, WATER],
    "lava": [LAVA, LAVA, LAVA],
    "frozen": [WATER, WATER, "minecraft:ice"],
    "kelp": ["minecraft:kelp_plant[age=3]", "minecraft:kelp_plant[age=3]", "minecraft:kelp[age=5]"],
    "flowing": [FLOW, FLOW, FLOW],
}


@pytest.mark.parametrize("name", sorted(KEPT))
def test_existing_interior_liquid_is_kept_when_ground_is_unchanged(tmp_path, name):
    site, g = pond_world(tmp_path, KEPT[name])
    w = materialize_live(field(to_array(BOX, g)), spec(), site, None)
    cells = written(w)
    for (x, z) in POND:
        assert all(code_at(w, (x, y, z)) == 0 for y in (61, 62, 63))
        assert cells[(x, 60, z)] == "minecraft:grass_block"
    assert w.liquid == {"kept": 12, "covered": 0, "added": 0}
    assert liquid_violations(w, site) == []


def test_a_river_crossing_the_box_is_kept(tmp_path):
    g = ground_map(BOX, 64, {(x, z): 60 for x in range(8) for z in (3, 4)})
    cells = {(x, y, z): WATER for x in range(8) for z in (3, 4) for y in (61, 62, 63)}
    site = make_site(tmp_path / "s", BOX, ground=g, cells=cells)
    w = materialize_live(field(to_array(BOX, g)), spec(), site, None)
    assert all(code_at(w, c) == 0 for c in cells)
    assert w.liquid["kept"] == 48 and liquid_violations(w, site) == []
    assert w.liquid_top[3, 3] == 63 and np.isnan(w.liquid_top[0, 0])


def test_ground_raised_over_a_pond_covers_it(tmp_path):
    site, g = pond_world(tmp_path)
    h = to_array(BOX, g)
    h[3:5, 3:5] = 66.0
    w = materialize_live(field(h), spec(), site, None)
    assert w.liquid == {"kept": 0, "covered": 12, "added": 0}
    assert written(w)[(3, 66, 3)] == "minecraft:grass_block" and np.isnan(w.liquid_top[3, 3])


@pytest.mark.parametrize("kind, block", [("water", "minecraft:water"), ("lava", "minecraft:lava")])
def test_lowering_a_bed_under_a_pond_refills_to_l_with_that_kind(tmp_path, kind, block):
    site, g = pond_world(tmp_path, KEPT[kind])
    h = to_array(BOX, g)
    for c in POND:
        h[c] = 56.0
    w = materialize_live(field(h), spec(), site, None)
    cells = written(w)
    for (x, z) in POND:
        assert [cells[(x, y, z)] for y in (57, 58, 59, 60)] == [block] * 4
        assert all(code_at(w, (x, y, z)) == 0 for y in (61, 62, 63))
        assert cells[(x, 56, z)] == "minecraft:grass_block"
    assert w.liquid == {"kept": 12, "covered": 0, "added": 16}
    assert w.liquid_top[3, 3] == 63
    assert liquid_violations(w, site) == []


def test_felled_wet_canopy_with_exposed_joins_fails_the_spill_gate(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64, trees=[tree(4, 3, 65, height=6, radius=1)],
                     cells={(3, 70, 3): LEAF_WL})
    gone = materialize_live(field(np.full((8, 8), 60.0)), spec(), site, None)
    assert state_after(site, gone, (3, 70, 3)) == "minecraft:water"
    assert gone.liquid["added"] > 0
    assert any(v["contact"] == "beside" for v in liquid_violations(gone, site))
    kept = materialize_live(field(np.full((8, 8), 64.0)), spec(), site, None)
    assert code_at(kept, (3, 70, 3)) == 0 and kept.liquid["kept"] == 1


def test_planned_water_raises_a_level_never_lowers(tmp_path):
    site, g = pond_world(tmp_path, bank=66)
    h = to_array(BOX, g)
    wl = np.full((8, 8), np.nan)
    for c in POND:
        wl[c] = 65
    w = materialize_live(field(h), spec(), site, None, water=wl)
    cells = written(w)
    assert all(cells[(x, y, z)] == "minecraft:water" for (x, z) in POND for y in (64, 65))
    assert all(code_at(w, (x, y, z)) == 0 for (x, z) in POND for y in (61, 62, 63))
    assert liquid_violations(w, site) == []
    # an entry below the existing level is an error naming level, L and a cell
    low = rec(0, 0, 8, 8, water=[{"level": 62, "at": [3, 3]}])
    from terrain.site import water_levels
    lowered = water_levels(field(h), low)
    with pytest.raises(ValueError) as err:
        materialize_live(field(h), spec(), site, low, water=lowered)
    assert "62" in str(err.value) and "63" in str(err.value) and "(3, 3)" in str(err.value)
    wl2 = np.full((8, 8), np.nan)
    wl2[3, 3] = 62
    with pytest.raises(ValueError, match="62"):
        materialize_live(field(h), spec(), site, None, water=wl2)               # None: all entries


def test_a_blanket_sea_below_the_existing_level_yields(tmp_path):
    site, g = pond_world(tmp_path)
    h = to_array(BOX, g)
    for c in POND:
        h[c] = 56.0
    sea = rec(0, 0, 8, 8, sea_level=62)
    from terrain.site import water_levels
    wl = water_levels(field(h), sea)
    assert wl[3, 3] == 62
    w = materialize_live(field(h), spec(), site, sea, water=wl)
    cells = written(w)
    assert all(cells[(x, y, z)] == "minecraft:water" for (x, z) in POND for y in (57, 58, 59, 60))
    assert all(code_at(w, (x, y, z)) == 0 for (x, z) in POND for y in (61, 62, 63))
    high = rec(0, 0, 8, 8, sea_level=65)
    site66, g66 = pond_world(tmp_path / "x", bank=66)
    h66 = to_array(BOX, g66)
    wl66 = water_levels(field(h66), high)
    assert wl66[3, 3] == 65
    raised = materialize_live(field(h66), spec(), site66, high, water=wl66)
    assert all(written(raised)[(3, y, 3)] == "minecraft:water" for y in (64, 65))


def test_r22_trunk_in_a_pond_below_the_bed_leaves_no_air_under_the_water(tmp_path):
    box = (0, 40, 0, 11, 100, 11)
    g = ground_map(box, 76, {(5, 5): 74})
    for x in range(12):
        for z in range(12):
            if (x + z) % 3 == 0 and (x, z) != (5, 5):
                g[(x, z)] = 77
    cells = water_cells(g, g, 80)
    site = make_site(tmp_path / "s", box, ground=g, cells=cells,
                     trees=[tree(5, 5, 75, height=8, radius=1)])
    assert find_trees(site)[0].trunk_columns == {(5, 5)}
    h = to_array(box, g)
    h[5, 5] = 72.0
    w = materialize_live(field(h), spec(), site, None)
    for y in range(73, 81):
        assert state_after(site, w, (5, y, 5)).startswith("minecraft:water"), y
    assert state_after(site, w, (5, 81, 5)) == AIR
    assert liquid_violations(w, site) == []


def test_r22_leaf_at_the_surface_beside_a_bank_with_hold_shores(tmp_path):
    box = (0, 40, 0, 9, 100, 4)
    g = ground_map(box, 64, {(x, z): 55 for x in (0, 1) for z in range(5)} |
                   {(2, z): 63 for z in range(5)})
    cells = water_cells(g, [(x, z) for x in (0, 1) for z in range(5)], 64)
    for z in range(5):
        cells[(2, 64, z)] = LEAVES
        cells[(2, 65, z)] = LEAVES
        cells[(3, 65, z)] = LEAVES
    cells.update({(4, y, z): LOG for z in range(5) for y in range(65, 70)})
    site = make_site(tmp_path / "s", box, ground=g, cells=cells)
    h = to_array(box, g)
    h[3:, 1:4] = 60.0                       # lower the banks beyond the leaf row, interior only
    safe = hold_shores(h, site, origin=(0, 0))
    assert safe[3, 2] == 64.0                # held up beside the felled leaf
    w = materialize_live(field(safe), spec(), site, None)
    assert w.removed_trees == 1
    assert state_after(site, w, (2, 64, 2)).startswith("minecraft:water")
    assert liquid_violations(w, site) == []
    spill = materialize_live(field(h), spec(), site, None)
    assert liquid_violations(spill, site)    # without the held bank it spills


# --------------------------------------------------------- liquid_violations
def test_violations_catch_a_lowered_bank_and_hold_shores_fixes_it(tmp_path):
    g = ground_map(BOX, 64, {(3, 3): 60})
    site = make_site(tmp_path / "s", BOX, ground=g, cells=water_cells(g, [(3, 3)], 64))
    h = to_array(BOX, g)
    h[4, 3] = 60.0
    found = liquid_violations(materialize_live(field(h), spec(), site, None), site)
    assert {"cell": (3, 64, 3), "kind": "water", "level": 64, "neighbour": (4, 64, 3),
            "contact": "beside"} in found
    held = hold_shores(h, site, origin=(0, 0))
    assert held[4, 3] == 64.0
    assert liquid_violations(materialize_live(field(held), spec(), site, None), site) == []


@pytest.fixture
def floating(tmp_path):
    """A lone water cell at (5, 64, 5) over stone, with air around and above (a contact that
    existed before any write)."""
    g = ground_map(BOX, 60)
    return make_site(tmp_path / "s", BOX, ground=g, cells={(5, 61, 5): WATER}), (5, 61, 5)


def test_violations_catch_a_carved_cell_below_water(floating):
    site, cell = floating
    carve = manual(site, {(5, 60, 5): AIR})
    found = liquid_violations(carve, site)
    assert found == [{"cell": cell, "kind": "water", "level": 61, "neighbour": (5, 60, 5),
                      "contact": "below"}]
    assert liquid_violations([carve], site) == found


def test_violations_ignore_a_contact_that_already_existed(floating):
    site, _ = floating
    assert liquid_violations(manual(site, {(0, 50, 0): AIR}), site) == []
    assert liquid_violations(manual(site, {(5, 61, 5): "minecraft:water"}), site) == []


def test_violations_exempt_falls(floating):
    site, cell = floating
    carve = manual(site, {(5, 60, 5): AIR})
    assert liquid_violations(carve, site, falls=[cell]) == []
    assert liquid_violations(carve, site, falls=[(1, 1, 1)]) != []


def test_violations_fail_closed_at_the_reads_edge(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64)
    dug = manual(site, {(0, 64, 3): "minecraft:water"})
    found = liquid_violations(dug, site)
    assert found == [{"cell": (0, 64, 3), "kind": "water", "level": 64, "neighbour": None,
                      "contact": "outside the read"}]
    lava = liquid_violations(manual(site, {(7, 64, 3): "minecraft:lava"}), site)
    assert lava[0]["kind"] == "lava"
    already = make_site(tmp_path / "a", BOX, ground=64, cells={(0, 64, 3): WATER})
    assert liquid_violations(dug, already) == []                       # fluid already
    leafy = make_site(tmp_path / "l", BOX, ground=64, cells={(0, 64, 3): LEAVES})
    assert liquid_violations(dug, leafy) == []                         # a cleared tree cell
    low = make_site(tmp_path / "f", (0, 50, 0, 7, 100, 7), ground=64)
    assert liquid_violations(manual(low, {(3, 50, 3): "minecraft:water"}), low)   # below the read
    floor = make_site(tmp_path / "w", (0, -64, 0, 7, 100, 7), ground=64)
    assert liquid_violations(manual(floor, {(3, -64, 3): "minecraft:water"}), floor) == []
    with pytest.raises(ValueError):
        liquid_violations(manual(site, {(8, 64, 3): AIR}), site)       # a write outside the read


def test_waterlogged_states_and_plants_count_as_fluid_and_open(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64, cells={(3, 65, 3): "minecraft:short_grass"})
    stairs = "minecraft:oak_stairs[waterlogged=true]"
    found = liquid_violations(manual(site, {(2, 65, 3): stairs}), site)
    assert {v["cell"] for v in found} == {(2, 65, 3)}
    assert {v["neighbour"] for v in found} == {(3, 65, 3), (1, 65, 3), (2, 65, 2), (2, 65, 4)}
    assert liquid_violations(manual(site, {(2, 65, 3): "minecraft:oak_stairs[waterlogged=false]"}),
                             site) == []


# ----------------------------------------------------------- expected surface
def test_expected_surface_at_a_waterfall(tmp_path):
    g = ground_map(BOX, 60)
    cells = {(3, y, 3): "minecraft:water[level=1]" for y in range(61, 71)}
    site = make_site(tmp_path / "s", BOX, ground=g, cells=cells)
    hf = field(to_array(BOX, g))
    w = materialize_live(hf, spec(), site, None)
    assert w.liquid_top[3, 3] == 70 and np.isnan(w.liquid_top[2, 3])
    plain = expected_surface(hf, None, w.kept_trunks, (0, 0))
    full = expected_surface(hf, None, w.kept_trunks, (0, 0), retained=w.liquid_top)
    assert plain["top"][3 * 8 + 3] == 60 and full["top"][3 * 8 + 3] == 70
    assert full["top"][0] == 60
    with_water = np.full((8, 8), np.nan)
    with_water[3, 3] = 72
    assert expected_surface(hf, with_water, set(), (0, 0), retained=w.liquid_top)["top"][27] == 72


# ----------------------------------------------------------------------- fuzz
def _wooded_pond(rng, tmp_path, i):
    box = (0, 40, 0, 17, 100, 17)
    base = 66
    g = ground_map(box, base)
    x0, z0 = (int(v) for v in rng.integers(5, 8, 2))
    x1, z1 = x0 + int(rng.integers(3, 6)), z0 + int(rng.integers(3, 6))
    cols = [(x, z) for x in range(x0, x1) for z in range(z0, z1)]
    level = int(rng.integers(63, 67))
    for c in cols:
        g[c] = int(rng.integers(57, 62))
    cells = {}
    for c in cols:
        cells.update(water_cells(g, [c], level))
    for _ in range(int(rng.integers(0, 3))):                 # waterlogged leaves over the bank
        c = (int(rng.integers(2, 16)), int(rng.integers(2, 16)))
        cells[(c[0], int(rng.integers(66, 72)), c[1])] = LEAF_WL
    trees, used = [], set()
    for _ in range(int(rng.integers(3, 7))):
        x, z = (int(v) for v in rng.integers(2, 16, 2))
        if any(abs(x - a) < 3 and abs(z - b) < 3 for a, b in used):
            continue
        used.add((x, z))
        trees.append(tree(x, z, g[(x, z)] + 1, height=int(rng.integers(4, 9)),
                          radius=int(rng.integers(1, 3))))
    site = make_site(tmp_path / f"s{i}", box, ground=g, cells=cells, trees=trees)
    h = to_array(box, g)
    for _ in range(int(rng.integers(1, 4))):                 # lowered blobs, interior only
        a, b = (int(v) for v in rng.integers(2, 12, 2))
        h[a:a + int(rng.integers(2, 7)), b:b + int(rng.integers(2, 7))] -= int(rng.integers(1, 7))
    ring = np.ones(h.shape, bool)
    ring[1:-1, 1:-1] = False
    h = np.where(ring, to_array(box, g), np.minimum(h, to_array(box, g)))
    return site, hold_shores(h, site, origin=(0, 0))


@pytest.mark.parametrize("seed", range(40))
def test_fuzz_wooded_ponds_with_lowered_ground_leave_no_spill(tmp_path, seed):
    rng = np.random.default_rng(1000 + seed)
    site, h = _wooded_pond(rng, tmp_path, seed)
    w = materialize_live(field(h), spec(), site, None)
    assert liquid_violations(w, site) == []
    assert decode(greedy_fills(w)) == written(w)
    for tree_group in find_trees(site):
        if tree_group.trunk_columns <= w.kept_trunks:
            assert all(code_at(w, cell) == 0 for cell in tree_group.cells
                       if cell[1] > h[cell[0], cell[2]])
        else:
            assert all(code_at(w, cell) > 0 for cell in tree_group.cells)


def test_reads_margin_ground_for_faces_and_margin_liquid_for_spills(tmp_path):
    # The active grid begins at (2, 2). Its west neighbour is in the read margin.
    g = ground_map(BOX, 70, {(1, 3): 52})
    site = make_site(tmp_path / "s", BOX, ground=g, cells=water_cells(g, [(1, 3)], 62))
    h = np.full((3, 3), 70.0)
    w = materialize_live(field(h), spec(), site, rec(2, 2, 3, 3))
    assert code_at(w, (2, 48, 3)) > 0 and code_at(w, (2, 47, 3)) == 0
    assert liquid_violations(w, site) == []
    h[0, 1] = 60
    cut = materialize_live(field(h), spec(), site, rec(2, 2, 3, 3))
    assert liquid_violations(cut, site) == [
        {"cell": (1, y, 3), "kind": "water", "level": y,
         "neighbour": (2, y, 3), "contact": "beside"} for y in (61, 62)]
    protect = np.zeros(h.shape, bool)
    protect[0, 1] = True
    held = materialize_live(field(h), spec(), site, rec(2, 2, 3, 3), protect=protect)
    assert all((x, z) != (2, 3) for x, _, z in written(held))
    assert liquid_violations(held, site) == []


def test_crossing_tree_gets_liquid_at_each_join_beyond_the_grid(tmp_path):
    g = ground_map(BOX, 65, {(1, 4): 60, (2, 4): 60, (3, 4): 60})
    cells = water_cells(g, [(1, 4)], 64)
    cells.update({(2, 64, 4): LEAVES, (2, 63, 4): LEAVES,
                  (3, 64, 4): LEAVES, (4, 64, 4): LOG})
    # A sheltered leaf connects to the root and to a water source outside the grid.
    cells[4, 65, 4] = LOG
    site = make_site(tmp_path / "s", BOX, ground=g, cells=cells)
    assert find_trees(site)[0].trunk_columns == {(4, 4)}
    h = np.full((2, 3), 65.0)
    h[0, 1] = 62
    w = materialize_live(field(h), spec(), site, rec(4, 3, 2, 3))
    assert w.removed_trees == 1 and w.reach == 2
    assert {p for p in written(w) if p[0] < 4} == {(2, 63, 4), (2, 64, 4), (3, 64, 4)}
    for cell in ((2, 63, 4), (2, 64, 4), (3, 64, 4)):
        assert state_after(site, w, cell) == "minecraft:water"
    assert all(code_at(w, (1, y, 4)) == 0 for y in range(61, 65))
    assert any(row["contact"] == "below" and row["cell"] == (3, 64, 4)
               for row in liquid_violations(w, site))


def test_raised_ground_can_cover_kept_canopy_without_clearing_above_it(tmp_path):
    site = make_site(tmp_path / "s", BOX, ground=64, trees=[tree(4, 4, 65)])
    h = np.full((8, 8), 64.0)
    h[3, 4] = 69
    w = materialize_live(field(h), spec(), site, None)
    assert w.removed_trees == 0 and w.kept_trunks == {(4, 4)}
    assert state_after(site, w, (3, 69, 4)) == "minecraft:grass_block"
    assert code_at(w, (3, 70, 4)) == 0 and site.block(3, 70, 4) == LEAVES
    assert code_at(w, (4, 68, 4)) == 0  # t ignores the kept canopy and trunk


@pytest.mark.parametrize("state", ["minecraft:lava[level=5]", "minecraft:bubble_column[drag=true]",
                                   "minecraft:brain_coral_fan[waterlogged=true]"])
def test_retained_states_survive_verbatim(tmp_path, state):
    site, g = pond_world(tmp_path, [state] * 3)
    w = materialize_live(field(to_array(BOX, g)), spec(), site, None)
    for x, z in POND:
        for y in range(61, 64):
            assert code_at(w, (x, y, z)) == 0 and site.block(x, y, z) == state
    assert liquid_violations(w, site) == []


def test_blanket_sea_at_a_retained_lava_level_refills_with_lava(tmp_path):
    site, g = pond_world(tmp_path, [LAVA] * 3)
    h = to_array(BOX, g)
    h[3:5, 3:5] = 57
    recipe = rec(0, 0, 8, 8, sea_level=63)
    from terrain.site import water_levels
    hf = field(h)
    w = materialize_live(hf, spec(), site, recipe, water=water_levels(hf, recipe))
    for x, z in POND:
        assert state_after(site, w, (x, 60, z)) == "minecraft:lava"
        assert code_at(w, (x, 61, z)) == 0 and state_after(site, w, (x, 61, z)) == LAVA
    assert liquid_violations(w, site) == []


def test_explicit_flood_at_sea_level_cannot_silently_lower_a_lake(tmp_path):
    site, g = pond_world(tmp_path)
    recipe = rec(0, 0, 8, 8, sea_level=62, water=[{"level": 62, "at": [3, 3]}])
    hf = field(to_array(BOX, g))
    from terrain.site import water_levels
    with pytest.raises(ValueError, match=r"62.*63.*\(3, 3\)"):
        materialize_live(hf, spec(), site, recipe, water=water_levels(hf, recipe))


def test_liquid_contacts_use_the_combined_final_placement(floating):
    site, source = floating
    excavate = manual(site, {(5, 60, 5): AIR})
    close = manual(site, {(5, 60, 5): STONE})
    assert liquid_violations([excavate, close], site) == []
    leaks = liquid_violations([close, excavate], site)
    assert len(leaks) == 1 and leaks[0]["cell"] == source and leaks[0]["contact"] == "below"
    assert liquid_violations([close, excavate], site, falls=[{"at": list(source)}]) == []


def test_unchanged_neighbour_sees_new_lava_contact(tmp_path):
    site, _ = pond_world(tmp_path, [LAVA] * 3)
    coords = (2, 62, 3)
    assert liquid_violations(manual(site, {coords: AIR}), site) == [
        {"cell": (3, 62, 3), "kind": "lava", "level": 62, "neighbour": coords, "contact": "beside"}]



def test_disconnected_waterlogged_cell_on_a_removed_tree_cannot_be_drained(tmp_path):
    cells = {(4, y, 3): LOG for y in range(65, 72)}
    cells.update({(3, 71, 3): LOG, (2, 71, 3): LOG, (2, 70, 3): LEAF_WL})
    site = make_site(tmp_path / "s", BOX, ground=64, cells=cells)
    wet = (2, 70, 3)
    assert wet in find_trees(site)[0].cells
    kept = materialize_live(field(np.full((8, 8), 64.0)), spec(), site, None)
    assert code_at(kept, wet) == 0 and np.isnan(kept.liquid_top[2, 3])
    h = np.full((8, 8), 64.0)
    h[4, 3] -= 1
    with pytest.raises(ValueError, match=r"\(2, 70, 3\).*keep the tree or adjust"):
        materialize_live(field(h), spec(), site, None)
    h[2, 3] = 70
    covered = materialize_live(field(h), spec(), site, None)
    assert state_after(site, covered, wet) == "minecraft:grass_block"
    assert covered.liquid["covered"] == 1


def test_a_preexisting_open_contact_is_unchanged_by_kind_or_flow_level(floating):
    site, cell = floating
    for state in ("minecraft:water[level=2]", "minecraft:lava"):
        assert liquid_violations(manual(site, {cell: state}), site) == []



@pytest.mark.parametrize("states,bed,plan,reason", [
    ([LAVA, LAVA, LAVA], 60, 64, "claim retained lava"),
    ([LAVA, "minecraft:lava[level=4]", "minecraft:lava[level=6]"], 60, 63, "claim retained lava"),
    ([LAVA, LAVA, LAVA], 58, 63, "claim retained lava"),
    (["minecraft:lava[level=4]"] * 3, 60, 63, "replace surface lava"),
])
def test_planned_water_refuses_surface_lava_conflicts(tmp_path, states, bed, plan, reason):
    site, g = pond_world(tmp_path, states)
    h = to_array(BOX, g)
    h[3, 3] = bed
    wl = np.full(h.shape, np.nan)
    wl[3, 3] = plan
    with pytest.raises(ValueError, match=reason):
        materialize_live(field(h), spec(), site, None, water=wl)


def test_new_solid_bed_can_cover_lava_under_planned_water(tmp_path):
    site, g = pond_world(tmp_path, [LAVA] * 3)
    h = to_array(BOX, g)
    h[3:5, 3:5] = 63
    wl = np.full(h.shape, np.nan)
    wl[3:5, 3:5] = 64
    w = materialize_live(field(h), spec(), site, None, water=wl)
    assert w.liquid == {"covered": 12, "kept": 0, "added": 4}
    assert liquid_violations(w, site) == []


def test_unqualified_material_ids_have_the_vanilla_namespace(tmp_path):
    site = make_site(tmp_path / "s", BOX)
    material = spec()
    material.base = {"grass_block": 1.0}
    material.stone = "deepslate"
    w = materialize_live(field(np.full((8, 8), 64.0)), material, site, None)
    assert {f["block"] for f in greedy_fills(w)} == {"minecraft:grass_block", "minecraft:dirt",
                                                      "minecraft:deepslate"}



def test_protected_trunk_of_a_partly_removed_multitrunk_tree_is_skipped(tmp_path):
    cells = {(x, y, 3): LOG for x in (3, 4) for y in range(65, 69)}
    site = make_site(tmp_path / "s", BOX, ground=64, cells=cells)
    assert find_trees(site)[0].trunk_columns == {(3, 3), (4, 3)}
    mask = np.zeros((8, 8), bool)
    mask[3, 3] = True
    h = np.full(mask.shape, 64.0)
    h[4, 3] = 63
    hf = field(h)
    w = materialize_live(hf, spec(), site, None, protect=mask)
    assert w.removed_trees == 1 and w.kept_trunks == {(3, 3)}
    assert code_at(w, (3, 65, 3)) == 0 and code_at(w, (4, 65, 3)) == 1
    assert expected_surface(hf, None, w.kept_trunks, (0, 0))["skip"][3 * 8 + 3] == 1


def test_tiles_skip_empty_intervals_on_both_axes_and_exactly_cover_writes():
    codes = np.zeros((257, 1, 257), np.uint16)
    codes[0, 0, 0] = codes[256, 0, 256] = 2
    w = LiveWrite((12, -1, -130), codes, ["skip", AIR, STONE])
    tiles = split_columns(w)
    assert len(tiles) == 2
    assert decode([f for tile in tiles for f in greedy_fills(tile)]) == written(w)
    assert decode([{"from": [0, 0, 0], "to": [0, 0, 0], "block": block}
                   for block in (STONE, AIR)]) == {(0, 0, 0): AIR}


@pytest.mark.parametrize("also_water", [False, True])
def test_wet_felled_leaf_cannot_join_lava(tmp_path, also_water):
    wet = (2, 70, 3)
    cells = {(4, y, 3): LOG for y in range(65, 72)}
    cells.update({(3, 71, 3): LOG, (2, 71, 3): LOG, wet: LEAF_WL, (2, 70, 2): LAVA})
    if also_water:
        cells[3, 70, 3] = WATER
    site = make_site(tmp_path / "s", BOX, ground=64, cells=cells)
    h = np.full((8, 8), 64.0)
    h[4, 3] = 63
    with pytest.raises(ValueError, match=r"\(2, 70, 3\).*water.*lava"):
        materialize_live(field(h), spec(), site, None)


@pytest.mark.parametrize("level", [63, 64])
def test_explicit_flood_cannot_claim_a_still_lava_pool(tmp_path, level):
    from terrain.site import water_levels
    site, g = pond_world(tmp_path, [LAVA] * 3, bank=66)
    recipe = rec(0, 0, 8, 8, sea_level=63, water=[{"level": level, "at": [3, 3]}])
    hf = field(to_array(BOX, g))
    with pytest.raises(ValueError, match=rf"water level {level}.*lava.*\(3, 63, 3\)"):
        materialize_live(hf, spec(), site, recipe, water=water_levels(hf, recipe))


@pytest.mark.parametrize("fell", [False, True])
def test_f6_observes_branches_and_solid_caps_away_from_tree_roots(tmp_path, fell):
    cells = {(4, y, 3): LOG for y in range(65, 72)}
    cells.update({(3, 71, 3): LOG, (2, 71, 3): "minecraft:brown_mushroom_block",
                  (1, 71, 3): LEAVES})
    site = make_site(tmp_path / "s", BOX, ground=64, cells=cells)
    assert find_trees(site)[0].trunk_columns == {(4, 3)}
    h = np.full((8, 8), 64.0)
    mask = np.zeros(h.shape, bool)
    if fell:
        h[4, 3] = 63
        mask[1:4, 3] = True
    w = materialize_live(field(h), spec(), site, None, protect=mask)
    assert w.removed_trees == int(fell)
    result = expected_surface(field(h), None, w.kept_trunks, (0, 0), retained=w.liquid_top)
    for x in (2, 3):
        assert code_at(w, (x, 71, 3)) == 0
        assert result["skip"][x*8+3] or result["top"][x*8+3] == 71
    assert result["skip"][1*8+3] == 0 and result["top"][1*8+3] == 64
    assert result["skip"][4*8+3] == int(not fell)


def test_explicit_water_checks_submerged_lava_even_under_retained_water(tmp_path):
    from terrain.site import water_levels

    site, g = pond_world(tmp_path, [LAVA, WATER, WATER])
    hf = field(to_array(BOX, g))
    explicit = rec(0, 0, 8, 8, sea_level=63, water=[{"level": 63, "at": [3, 3]}])
    with pytest.raises(ValueError, match=r"water level 63.*lava.*\(3, 61, 3\)"):
        materialize_live(hf, spec(), site, explicit, water=water_levels(hf, explicit))

    sea = rec(0, 0, 8, 8, sea_level=63)
    kept = materialize_live(hf, spec(), site, sea, water=water_levels(hf, sea))
    assert kept.liquid == {"kept": 12, "covered": 0, "added": 0}
    assert all(code_at(kept, (x, 61, z)) == 0 for x, z in POND)

    hf.h[3:5, 3:5] = 61
    raised = materialize_live(hf, spec(), site, explicit, water=water_levels(hf, explicit))
    assert raised.liquid == {"kept": 8, "covered": 4, "added": 0}
    for x, z in POND:
        assert state_after(site, raised, (x, 61, z)) == "minecraft:grass_block"
        assert all(code_at(raised, (x, y, z)) == 0 for y in (62, 63))


def test_drain_component_identity_and_horizontal_trunk_bridge(tmp_path):

    cells = {(2, 65, 3): WATER, (2, 66, 3): "minecraft:ice", (3, 65, 3): LOG,
             (3, 66, 3): LOG, (4, 65, 3): FLOW, (4, 65, 4): "minecraft:seagrass",
             (4, 65, 5): LAVA, (3, 67, 3): WATER, (4, 67, 3): WATER,
             (5, 66, 4): WATER}
    site = make_site(tmp_path / "s", BOX, cells=cells)
    recipe = rec(0, 0, 8, 8, drain=[{"at": [2, 3]}, {"at": [4, 5]}, {"at": [2, 3]}])
    body, = drain_bodies(site, recipe)
    expected = {(2, 65, 3): "water", (2, 66, 3): "water", (4, 65, 3): "water",
                (4, 65, 4): "water", (4, 65, 5): "lava"}
    lines = "\n".join(f"{x},{y},{z},{kind}" for (x, y, z), kind in sorted(expected.items()))
    assert body.cells == expected and body.seed == (2, 3)
    assert body.id == hashlib.sha256(lines.encode()).hexdigest()[:12]
    assert body.bbox == (2, 65, 3, 4, 66, 5)
    assert set(body.kinds) == {"water", "lava"}
    assert set(body.columns) == {(2, 3), (4, 3), (4, 4), (4, 5)}
    reverse, = drain_bodies(site, {**recipe, "drain": [{"at": [4, 5]}, {"at": [2, 3]}]})
    assert reverse.id == body.id and reverse.seed == (4, 5)
    site2 = make_site(tmp_path / "s2", BOX, cells={**cells, (4, 65, 5): WATER})
    assert drain_bodies(site2, recipe)[0].id != body.id


@pytest.mark.parametrize("entries", [
    None, {}, [[3, 3]], [{"x": 3, "z": 3}], [{"at": []}], [{"at": [3, 3, 0]}],
    [{"at": [True, 3]}], [{"at": [3, 3.5]}], [{"at": ["3", 3]}], [{"at": [8, 3]}],
    [{"at": [6, 6]}], [{"at": [3, 3], "level": 4}],
])
def test_drain_rejects_malformed_or_dry_seed(tmp_path, entries):
    site, _ = pond_world(tmp_path)
    with pytest.raises(ValueError, match="drain"):
        drain_bodies(site, rec(0, 0, 8, 8, drain=entries))


@pytest.mark.parametrize("case", ["river", "cropped", "trunk_edge", "protected", "missing", "read_top", "read_floor"])
def test_drain_refuses_unbounded_or_protected_body(tmp_path, case):
    cells = {(3, 65, 3): WATER, (2, 65, 3): FLOW}
    recipe = rec(0, 0, 8, 8, drain=[{"at": [3, 3]}])
    mask = np.zeros((8, 8), bool)
    if case == "river":
        cells.update({(x, 65, 3): WATER for x in range(2)})
    elif case == "cropped":
        recipe.update(origin=[2, 0, 0], nx=5)
        mask = np.zeros((5, 8), bool)
    elif case == "trunk_edge":
        cells.update({(x, 65, 3): LOG for x in range(2)})
    elif case == "protected":
        mask[2, 3] = True
    elif case == "read_top":
        cells.update({(3, y, 3): FLOW for y in range(66, 101)})
    site = make_site(tmp_path / "s", BOX, cells=cells, water={(3, 3): 64} if case == "read_floor" else {})
    if case == "missing":
        del site.columns[1, 3]
    with pytest.raises(ValueError, match="ring|edge|protected|read|missing"):
        drain_bodies(site, recipe, protect=mask)


@pytest.mark.parametrize("plan", ["dry", "lower_water", "raised_ground"])
@pytest.mark.parametrize("liquid", [WATER, LAVA])
def test_drain_material_and_preserved_second_pond(tmp_path, plan, liquid):
    site, g = pond_world(tmp_path, kinds=[liquid] * 3, extra={(6, 65, 6): WATER})
    recipe = rec(0, 0, 8, 8, drain=[{"at": [3, 3]}])
    hf = field(to_array(BOX, g))
    if plan == "lower_water":
        recipe["water"] = [{"at": [3, 3], "level": 62}]
    if plan == "raised_ground":
        hf.h[3:5, 3:5] = 62
    drains = drain_bodies(site, recipe)
    ll = liquid_levels(site, excluded=drains[0].cells)
    assert np.isnan(ll.level[3, 3]) and np.isnan(ll.top[3, 3]) and ll.level[6, 6] == 65
    w = materialize_live(hf, spec(), site, recipe, water=water_levels(hf, recipe), drains=drains)
    for x, z in POND:
        assert state_after(site, w, (x, 63, z)) == AIR
        for y in (61, 62):
            state = state_after(site, w, (x, y, z))
            assert state == {"dry": AIR, "lower_water": "minecraft:water",
                             "raised_ground": "minecraft:dirt" if y == 61 else "minecraft:grass_block"}[plan]
    assert code_at(w, (6, 65, 6)) == 0
    assert w.liquid["kept"] == 1 and w.liquid["covered"] == 0
    assert liquid_violations(w, site) == []


def test_drain_kept_wet_tree_high_cells_and_felled_tree_flood(tmp_path):
    root = "minecraft:mangrove_roots[waterlogged=true]"
    cells = {(3, 65, 3): root, (3, 66, 3): root, (3, 67, 3): root,
             (3, 68, 3): LEAF_WL, (4, 65, 3): LOG}
    site = make_site(tmp_path / "s", BOX, cells=cells)
    recipe = rec(0, 0, 8, 8, drain=[{"at": [3, 3]}])
    drains = drain_bodies(site, recipe)
    ll = liquid_levels(site, removed=find_trees(site)[0].cells, excluded=drains[0].cells)
    assert not ll.joined and np.isnan(ll.level).all()
    hf = field(np.full((8, 8), 64))
    kept = materialize_live(hf, spec(), site, recipe, drains=drains)
    for cell in drains[0].cells:
        assert state_after(site, kept, cell) == cells[cell].replace("waterlogged=true", "waterlogged=false")
    assert code_at(kept, (4, 65, 3)) == 0 and np.isnan(kept.liquid_top).all()
    hf.h[3, 3] = 63
    felled = materialize_live(hf, spec(), site, recipe, drains=drains)
    assert all(state_after(site, felled, c) == AIR for c in cells)
    assert felled.removed_trees == 1 and felled.liquid["added"] == 0


def test_drain_hold_shores_and_keep_default(tmp_path):

    site, _ = pond_world(tmp_path)
    recipe = rec(0, 0, 8, 8, graph={"type": "Constant", "value": 54},
                 site={"read": "s", "band": 1}, hold_shores=True)
    keep = build_field(recipe, tmp_path)
    assert drain_bodies(site, recipe) == []
    none = build_field({**recipe, "drain": []}, tmp_path)
    assert np.array_equal(keep.h, none.h) and keep.h[2, 3] == 63
    drained = build_field({**recipe, "drain": [{"at": [3, 3]}]}, tmp_path)
    assert drained.h[2, 3] == 54
    with pytest.raises(ValueError, match="drain"):
        build_field({**recipe, "site": None, "hold_shores": False, "drain": [{"at": [3, 3]}]}, tmp_path)


def test_drain_seed_chooses_lowest_component_and_leaves_higher_run(tmp_path):
    # Two disconnected retained runs share world coordinates (x,z).
    box = (-15, 40, 92, -7, 100, 100)
    site = make_site(tmp_path / "s", box, cells={(-11, 66, 95): FLOW, (-11, 69, 95): WATER})
    recipe = rec(-14, 93, 7, 7, drain=[{"at": [-11, 95]}])
    bodies = drain_bodies(site, recipe)
    assert bodies[0].cells == {(-11, 66, 95): "water"}
    ll = liquid_levels(site, excluded=bodies[0].cells)
    assert ll.top[4, 3] == 69 and np.isnan(ll.level[4, 3])
    result = materialize_live(field(np.full((7, 7), 62.0)), spec(), site, recipe, drains=bodies)
    assert state_after(site, result, (-11, 66, 95)) == AIR
    assert code_at(result, (-11, 69, 95)) == 0
    assert result.liquid["kept"] == 1 and result.liquid_top[3, 2] == 69


def test_drain_does_not_apply_partial_stale_or_protected_descriptor(tmp_path):
    site, ground = pond_world(tmp_path)
    recipe = rec(0, 0, 8, 8, drain=[{"at": [3, 3]}])
    hf = field(to_array(BOX, ground))
    bodies = drain_bodies(site, recipe)
    mask = np.zeros((8, 8), bool)
    mask[4, 4] = True
    with pytest.raises(ValueError, match="protected"):
        materialize_live(hf, spec(), site, recipe, protect=mask, drains=bodies)
    changed, _ = pond_world(tmp_path / "changed", kinds=[WATER, LAVA, WATER])
    with pytest.raises(ValueError, match="descriptors"):
        materialize_live(hf, spec(), changed, recipe, drains=bodies)
    bodies[0].cells.pop((3, 61, 3))
    with pytest.raises(ValueError, match="descriptors"):
        materialize_live(hf, spec(), site, recipe, drains=bodies)


def test_drain_refill_blanket_yields_to_separate_lava_body(tmp_path):
    # Both basins lie below sea level. The retained lava still outranks the blanket.
    ground = ground_map(BOX, 65, {(3, 3): 60, (5, 5): 60})
    cells = {(3, y, 3): WATER for y in range(61, 64)}
    cells.update({(5, y, 5): LAVA for y in range(61, 64)})
    site = make_site(tmp_path / "s", BOX, ground=ground, cells=cells)
    recipe = rec(0, 0, 8, 8, sea_level=62, drain=[{"at": [3, 3]}])
    hf = field(to_array(BOX, ground))
    result = materialize_live(hf, spec(), site, recipe, water=water_levels(hf, recipe),
                              drains=drain_bodies(site, recipe))
    assert state_after(site, result, (3, 63, 3)) == AIR
    assert state_after(site, result, (3, 62, 3)) == "minecraft:water"
    assert all(code_at(result, (5, y, 5)) == 0 for y in range(61, 64))
    assert not liquid_violations(result, site)


def test_drain_descriptor_reseed_of_same_body(tmp_path):
    site, ground = pond_world(tmp_path)
    original = rec(0, 0, 8, 8, drain=[{"at": [3, 3]}])
    alternate = {**original, "drain": [{"at": [4, 4]}]}
    write = materialize_live(field(to_array(BOX, ground)), spec(), site, alternate,
                             drains=drain_bodies(site, original))
    assert state_after(site, write, (4, 63, 4)) == AIR


@pytest.mark.parametrize("requested", [True, False])
def test_drain_descriptor_set_must_match_recipe_even_when_empty(tmp_path, requested):
    site, ground = pond_world(tmp_path)
    keep = rec(0, 0, 8, 8)
    drain = {**keep, "drain": [{"at": [3, 3]}]}
    bodies = drain_bodies(site, drain)
    if requested:
        bodies.clear()
    with pytest.raises(ValueError, match="descriptors"):
        materialize_live(field(to_array(BOX, ground)), spec(), site, drain if requested else keep,
                         drains=bodies)
