import math

import numpy as np
from sitegen import make_site
from terrain import corridor
from terrain import transit_design as td
from terrain.ashlar_emit import emit_field
from terrain.route import Route, Section
from terrain.site import surfaces

Z0 = 20


def _flat_line(tmp_path, ground, level, length=40, kinds=None, z0=Z0):
    """A rail design, a straight route along +x at z=z0, one section and a site over its box."""
    data = {"element": "t", "seed": 7, "world": "world", "mode": "rail", "heights": "heights.json",
            "from": {"at": [0, 65, z0]}, "to": {"at": [length - 1, 65, z0]}}
    design = td.parse_line(data, tmp_path)
    cells = [(x, z0) for x in range(length)]
    kinds = kinds or ["grade"] * length
    r = Route("t", "rail", "world", "overworld", "h", cells, [float(level)] * length, list(kinds),
              [None] * length, [None] * length, [], [])
    reach = math.ceil(td.formation_half(design) + 16)
    box = (-10, 40, z0 - reach, length + 9, 100, z0 + reach)
    section = Section("s01", 0, length - 1, box, "world")
    r.sections = [section]
    site = make_site(tmp_path / "site", box, ground=ground, world="world")
    return design, r, section, site


def _ground_array(site):
    return surfaces(site).ground


def _rolling():
    return {(x, z): 64 + round(2 * math.sin(x / 7) + 2 * math.cos(z / 5)) for x in range(-30, 120) for z in range(-30, 80)}


def _a_protected_column(plan, site):
    i, j = np.argwhere(plan.protect)[0]
    return site.box[0] + int(i), site.box[2] + int(j)


def test_formation_inside_and_cut_slope_outside(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61)
    plan = corridor.corridor_plan(design, r, section, site)
    col = lambda x, z: plan.field.h[x - site.box[0], z - site.box[2]]
    half = td.formation_half(design)
    assert col(20, 20) == 60
    assert abs(col(20, 20 + math.ceil(half) + 4) - 64) <= 1
    assert plan.protect[20 - site.box[0], 20 + math.ceil(half) + 9 - site.box[2]]


def test_fill_slope_spreads_by_fill_ratio(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=69)
    plan = corridor.corridor_plan(design, r, section, site)
    half = td.formation_half(design)
    assert abs(plan.field.h[20 - site.box[0], 20 + math.ceil(half + 1.5 * 4) - site.box[2]] - 64) <= 1


def test_bridge_and_tunnel_columns_are_protected(tmp_path):
    kinds = ["grade"] * 10 + ["bridge"] * 10 + ["tunnel"] * 10 + ["grade"] * 10
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61, kinds=kinds)
    plan = corridor.corridor_plan(design, r, section, site)
    assert plan.protect[15 - site.box[0], 20 - site.box[2]] and plan.protect[25 - site.box[0], 20 - site.box[2]]
    assert not plan.protect[5 - site.box[0], 20 - site.box[2]]


def test_columns_beyond_the_section_are_protected(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61)
    r.sections = [Section("s01", 10, 29, section.box, "world")]
    plan = corridor.corridor_plan(design, r, r.sections[0], site)
    assert plan.protect[5 - site.box[0], 20 - site.box[2]] and plan.protect[35 - site.box[0], 20 - site.box[2]]
    assert not plan.protect[20 - site.box[0], 20 - site.box[2]]


def test_toe_line_is_not_straight(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=70, level=65, length=90)
    plan = corridor.corridor_plan(design, r, section, site)
    changed = plan.field.h != _ground_array(site)
    widths = [np.ptp(np.flatnonzero(changed[i])) for i in range(10, 80)]
    assert np.std(widths) >= 0.5


def test_graded_site_passes_emit_field_preview(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=_rolling(), level=66, length=60)
    plan = corridor.corridor_plan(design, r, section, site)
    emit_field(plan.field, plan.spec, site, tmp_path / "p", element="t-s01", first_phase=1,
               protect=plan.protect, require_relief=False, preview=True)
    graded, mass, _ = corridor.graded_site(design, r, section, site)
    assert mass is not None
    x, z = _a_protected_column(plan, site)
    assert graded.columns[(x, z)] == site.columns[(x, z)]
    cx, cz = 30, 20
    top = max(hi for lo, hi, state in graded.columns[(cx, cz)] if state != "minecraft:air")
    assert top == 65


def test_outer_seam_rows_skip_section_boundaries(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=70, level=65, length=90)
    rows = corridor.outer_seam_rows(design, r, section, corridor.corridor_plan(design, r, section, site))
    half = td.formation_half(design)
    assert rows and all(abs(p[1] - 20) > half for row in rows for p in (row["from"], row["to"]))
    assert not any((row["from"][1] - 20) * (row["to"][1] - 20) < 0 for row in rows)   # none crosses the line
    assert {row["outward"] for row in rows} == {"z", "-z"}


def _layered(tmp_path, top, below, ground=64, level=61, **kw):
    """A line over ground whose every column is `top` over `below` over stone."""
    design, r, section, site = _flat_line(tmp_path, ground=ground, level=level, **kw)
    cells = {}
    x1, _, z1, x2, _, z2 = site.box
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            cells[(x, ground, z)] = top
            for y in range(ground - 8, ground):
                cells[(x, y, z)] = below
    from sitegen import make_site

    site = make_site(tmp_path / "layered", site.box, ground=ground, cells=cells, world="world")
    return design, r, section, site


def _weights(plan):
    return plan.spec.base


def test_grass_ring_caps_grass_and_adds_the_soil_below(tmp_path):
    design, r, section, site = _layered(tmp_path, "minecraft:grass_block[snowy=false]", "minecraft:dirt")
    w = _weights(corridor.corridor_plan(design, r, section, site))
    assert w["minecraft:grass_block"] <= 0.85 + 1e-9
    assert w["minecraft:dirt"] > 0
    assert abs(sum(w.values()) - 1) < 1e-9


def test_sand_ring_over_sandstone_keeps_to_the_sand_family(tmp_path):
    design, r, section, site = _layered(tmp_path, "minecraft:sand", "minecraft:sandstone")
    w = _weights(corridor.corridor_plan(design, r, section, site))
    assert set(w) == {"minecraft:sand", "minecraft:sandstone"}
    assert w["minecraft:sand"] <= 0.85 + 1e-9


def test_sand_ring_without_a_distinct_layer_below_uses_the_family_table(tmp_path):
    design, r, section, site = _layered(tmp_path, "minecraft:sand", "minecraft:sand")
    w = _weights(corridor.corridor_plan(design, r, section, site))
    assert set(w) == {"minecraft:sand", "minecraft:sandstone"}


def test_all_weights_are_positive(tmp_path):
    for top, below in (("minecraft:grass_block[snowy=false]", "minecraft:stone"), ("minecraft:red_sand", "minecraft:red_sand")):
        design, r, section, site = _layered(tmp_path, top, below)
        w = _weights(corridor.corridor_plan(design, r, section, site))
        assert all(v > 0 for v in w.values())
        assert abs(sum(w.values()) - 1) < 1e-9


def test_stone_cut_stands_steeper_than_soil_cut(tmp_path):
    spans = {}
    for name, block in (("rock", "minecraft:stone"), ("soil", "minecraft:dirt")):
        design, r, section, site = _layered(tmp_path / name, "minecraft:grass_block[snowy=false]", block,
                                            ground=70, level=65, length=90)
        plan = corridor.corridor_plan(design, r, section, site)
        spans[name] = int(plan.changed[40 - site.box[0]].sum())
    assert spans["rock"] < spans["soil"] - 4


def test_all_protected_plan_writes_nothing(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=65, kinds=["bridge"] * 40)
    graded, write, plan = corridor.graded_site(design, r, section, site)
    assert write is None and plan.protect.all() and graded is site
    assert plan.cut_cells == 0 and plan.fill_cells == 0


def test_cut_and_fill_cells_are_counted(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61)
    cut = corridor.corridor_plan(design, r, section, site)
    assert cut.cut_cells > 0 and cut.fill_cells == 0
    assert cut.cut_cells == int(((cut.field.h < _ground_array(site)) & ~cut.protect).sum())
    design, r, section, site = _flat_line(tmp_path, ground=64, level=69)
    fill = corridor.corridor_plan(design, r, section, site)
    assert fill.fill_cells > 0 and fill.cut_cells == 0


def test_cornered_route_is_graded_at_the_corner_with_outward_seams(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61, length=31)
    cells = [(x, 20) for x in range(31)] + [(30, z) for z in range(21, 51)]
    r = Route("t", "rail", "world", "overworld", "h", cells, [61.0] * len(cells), ["grade"] * len(cells),
              [None] * len(cells), [None] * len(cells), [30], [])
    box = (-10, 40, 2, 48, 100, 68)
    from sitegen import make_site

    site = make_site(tmp_path / "corner", box, ground=64, world="world")
    section = Section("s01", 0, len(cells) - 1, box, "world")
    r.sections = [section]
    plan = corridor.corridor_plan(design, r, section, site)
    assert plan.field.h[30 - box[0], 20 - box[2]] == 60 and not plan.protect[30 - box[0], 20 - box[2]]
    assert plan.field.h[30 - box[0], 35 - box[2]] == 60
    rows = corridor.outer_seam_rows(design, r, section, plan)
    assert {row["outward"] for row in rows} == {"x", "-x", "z", "-z"}
    for row in rows:
        for x, z in (row["from"], row["to"]):
            assert {"z": z > 20, "-z": z < 20, "x": x > 30, "-x": x < 30}[row["outward"]]
