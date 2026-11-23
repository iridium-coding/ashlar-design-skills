import json

import numpy as np
import pytest
from sitegen import make_site, tree
from terrain.apron import apron_seams, design_apron, surrounding_palette
from terrain.ashlar_emit import emit_field
from terrain.materialize import MaterialSpec
from terrain.site import surface_y, surfaces

BOX = (-12, 30, 14, 54)
PAD = (-2, 40, 1, 44)


def site_at(tmp_path, **kwargs):
    return make_site(tmp_path / "site", (-13, 35, 29, 15, 93, 55), **kwargs)


def ring(values):
    return np.concatenate((values[0], values[-1], values[1:-1, 0], values[1:-1, -1]))


def test_protected_region_never_written(tmp_path):
    site = site_at(tmp_path, trees=[tree(-1, 42, 65)])
    result = design_apron(site, BOX, protect=[PAD], pads={PAD: 72})
    spec = MaterialSpec.natural(result.field)
    recipe = {"origin": [BOX[0], 0, BOX[1]]}
    apron_seams(result, site, BOX, after_host=True)
    emitted = emit_field(
        result.field,
        spec,
        site,
        tmp_path / "project",
        recipe=recipe,
        protect=result.protect,
        water=None,
        element="apron",
        first_phase=1,
    )
    assert emitted.report.ok and emitted.phases
    for phase in emitted.phases:
        payload = json.loads((tmp_path / "project" / phase["file"]).read_text())
        assert payload["fills"]
        for fill in payload["fills"]:
            x1, _, z1 = fill["from"]
            x2, _, z2 = fill["to"]
            assert x2 < PAD[0] or z2 < PAD[1] or x1 > PAD[2] or z1 > PAD[3]
    assert result.protect.sum() == 20


def test_planned_pads_meet_aprons(tmp_path):
    site = site_at(tmp_path)
    second = (5, 46, 7, 49)
    result = design_apron(site, BOX, protect=[PAD], pads={PAD: 71, second: 67})
    h = result.field.h
    assert np.all(ring(h) == 64)
    for (x1, z1, x2, z2), y in [(PAD, 71), (second, 67)]:
        i, j, k, l = x1 - BOX[0], z1 - BOX[1], x2 - BOX[0], z2 - BOX[1]
        assert np.all(h[i : k + 1, j : l + 1] == y)
        assert np.all(h[[i - 1, k + 1], j : l + 1] == y)
        assert np.all(h[i : k + 1, [j - 1, l + 1]] == y)
    assert not result.protect[18, 18]


@pytest.mark.parametrize("step", [6, 7])
def test_delta_stats_and_threshold(tmp_path, step):
    site = site_at(tmp_path)
    result = design_apron(site, BOX, protect=[PAD], pads={PAD: 64 + step})
    change = abs(surface_y(result.field.h) - 64)
    change[result.protect] = 0  # host's planned pad is unwritten in the terrain phase
    assert result.delta == {"max": step, "mean": change.mean(), "moved": np.count_nonzero(change)}
    assert result.needs_ok is (step > 6)


def test_naturalise_without_protect(tmp_path):
    site = site_at(tmp_path, ground={(4, 44): 77, (-12, 30): 68})
    old = surfaces(site).ground[1:-1, 1:-1]
    result = design_apron(site, BOX)
    assert np.array_equal(ring(result.field.h), ring(old))
    assert result.field.h[16, 14] < 75
    assert not result.protect.any()
    assert result.delta["moved"] > 0
    assert np.array_equal(result.field.h, design_apron(site, BOX).field.h)


@pytest.mark.parametrize(("step", "width"), [(2, 8), (6, 12), (15, 24)])
def test_auto_apron_width_uses_cross_edge_step(tmp_path, step, width):
    site = site_at(tmp_path, ground={(x, z): 64 + step for x in range(-2, 2) for z in range(40, 45)})
    auto = design_apron(site, BOX, protect=[PAD])
    explicit = design_apron(site, BOX, protect=[PAD], apron=width)
    assert np.array_equal(auto.field.h, explicit.field.h)
    assert not np.array_equal(auto.field.h, design_apron(site, BOX, protect=[PAD], apron=width - 1).field.h)
    assert np.all(auto.field.h[auto.protect] == 64 + step)


def test_hold_existing_shore_after_erosion(tmp_path):
    ground = {(-1, 42): 56, (0, 42): 72}
    cells = {(-1, y, 42): "minecraft:water[level=0]" for y in range(57, 73)}
    site = site_at(tmp_path, ground=ground, cells=cells)
    result = design_apron(site, BOX)
    assert surface_y(result.field.h)[12, 12] >= 72


def test_surrounding_palette_parses_stats():
    stats = """Region with 1400 cells. 9 distinct block state(s):
        14   25.0%  minecraft:grass_block[snowy=false]
         4    7.1%  minecraft:grass_block[snowy=true]
         6   10.7%  minecraft:clay
        10   17.9%  minecraft:air
         9   16.1%  minecraft:short_grass
         8   14.3%  minecraft:oak_log[axis=y]
         8   14.3%  minecraft:stone_bricks
         8   14.3%  minecraft:farmland[moisture=3]
         8   14.3%  minecraft:water[level=0]
         2    3.6%  minecraft:gravel"""
    assert surrounding_palette(stats, top=2) == {"minecraft:grass_block": 0.75, "minecraft:clay": 0.25}
    with pytest.raises(ValueError, match="surface"):
        surrounding_palette("         8   14.3%  minecraft:oak_planks")


def test_seams_cover_whole_union_and_observe_physical_ground(tmp_path):
    second = (0, 42, 3, 46)
    site = site_at(tmp_path, trees=[tree(-1, 40, 65)])
    result = design_apron(site, BOX, protect=[PAD, second])
    paths = apron_seams(result, site, BOX)
    directions = {"x": (1, 0), "-x": (-1, 0), "z": (0, 1), "-z": (0, -1)}
    covered = set()
    for path in paths[4:]:
        dx, dz = directions[path.outward]
        (x, z), (ex, ez) = path.start, path.end
        for i in range(x, ex + 1):
            for j in range(z, ez + 1):
                covered.add((i, j, dx, dz))
    expected = {
        (i + BOX[0], j + BOX[1], dx, dz)
        for i, j in np.argwhere(~result.protect)
        for dx, dz in directions.values()
        if 0 <= i + dx < 27 and 0 <= j + dz < 25 and result.protect[i + dx, j + dz]
    }
    assert covered == expected
    planned = design_apron(site, BOX, protect=[PAD], pads={PAD: 72})
    with pytest.raises(ValueError, match="seam"):
        apron_seams(planned, site, BOX)
    assert len(apron_seams(planned, site, BOX, after_host=True)) == 8


def test_preexisting_outer_cliff_fails_projected_seam(tmp_path):
    site = site_at(tmp_path, ground={(-13, 40): 67})
    with pytest.raises(ValueError, match="seam"):
        apron_seams(design_apron(site, BOX), site, BOX)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"protect": [(-16, 40, -2, 42)]}, "inside"),
        ({"pads": {PAD: 70, (0, 42, 2, 43): 68}}, "overlap"),
        ({"pads": {(-12, 32, -10, 34): 75}}, "ring"),
        ({"apron": 0}, "positive"),
    ],
)
def test_invalid_geometry(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        design_apron(site_at(tmp_path), BOX, **kwargs)


def test_seam_cannot_cut_a_retained_bank(tmp_path):
    # The column (2, 42) is both the pad's outside shoulder and the dam on its east.
    site = site_at(
        tmp_path,
        ground={(2, 42): 72, (3, 42): 60},
        cells={(3, y, 42): "minecraft:water[level=0]" for y in range(61, 72)},
    )
    with pytest.raises(ValueError, match="shore.*seam"):
        design_apron(site, BOX, protect=[PAD], pads={PAD: 64})


def test_outer_seams_need_exact_site_read_on_both_sides(tmp_path):
    site = make_site(tmp_path / "site", (BOX[0], 50, BOX[1], BOX[2], 85, BOX[3]))
    result = design_apron(site, BOX)
    with pytest.raises(ValueError, match="outside.*site"):
        apron_seams(result, site, BOX)


def _args(*args):
    import argparse

    from terrain.apron import add_apron_parser

    parser = argparse.ArgumentParser()
    add_apron_parser(parser.add_subparsers(required=True))
    return parser.parse_args(["apron", *map(str, args)])


def test_cli_grouped_pads_and_saved_seams(tmp_path, capsys):
    from PIL import Image
    from terrain.apron import run_apron

    site_at(tmp_path)
    project = tmp_path / "project"
    args = [
        "--site",
        tmp_path / "site",
        "--box",
        *BOX,
        "--protect",
        6,
        42,
        8,
        44,
        "--protect",
        *PAD,
        "--pad",
        72,
        "--element",
        "yard",
        "--project",
        project,
        "--first-phase",
        3,
        "--host-palette",
        '{"minecraft:stone_bricks":3,"minecraft:andesite":1}',
    ]
    for preview in [True, False]:
        assert run_apron(_args(*args, *(["--preview"] if preview else []))) == 0
        output = capsys.readouterr().out
        assert "needs_ok=true" in output and "host" in output
        folder = project / ("terrain/previews" if preview else "terrain")
        for suffix in ["_before.png", "_after.png", "_seam-profile.png"]:
            with Image.open(folder / ("yard" + suffix)) as image:
                image.verify()
        if preview:
            assert not (project / "phases").exists()
            assert not (folder / "yard.plan-rows.toon").exists()
        else:
            snippet = (folder / "yard.plan-rows.toon").read_text()
            assert "seam[12]{from,to,max_step,outward}" in snippet
            assert (project / "phases/03-yard-mass-1.json").exists()
            assert "after the host" in snippet
        archived = json.loads((folder / "yard.recipe.json").read_text())
        assert archived["apron"]["pads"] == [{"box": list(PAD), "level": 72}]


def test_standalone_apron_writes_final_quality_into_plan(tmp_path):
    from terrain.apron import run_apron

    site_at(tmp_path, ground={(x, z): 72 for x in range(-2, 2) for z in range(40, 45)})
    project = tmp_path / "ground"
    args = _args(
        "--site",
        tmp_path / "site",
        "--box",
        *BOX,
        "--protect",
        *PAD,
        "--project",
        project,
        "--element",
        "ground",
        "--first-phase",
        1,
        "--standalone",
    )
    assert run_apron(args) == 0
    assert "seam[8]{from,to,max_step,outward}" in (project / "plan.toon").read_text()


def test_host_surface_blends_across_width_and_avoids_wet_ground(tmp_path):
    from terrain.apron import apron_material
    from terrain.materialize import resolve_surface

    site = site_at(
        tmp_path, ground={(2, 41): 62}, cells={(2, y, 41): "minecraft:water[level=0]" for y in (63, 64)}
    )
    result = design_apron(site, BOX, protect=[PAD], apron=8)
    host = {"minecraft:stone_bricks": 1}
    surround = {"minecraft:podzol": 1}
    surface, _ = resolve_surface(result.field, apron_material(result, site, BOX, surround, host, seed=13))
    assert surface[2 - BOX[0], 41 - BOX[1]] == "minecraft:podzol"
    assert surface[2 - BOX[0], 44 - BOX[1]] == "minecraft:stone_bricks"
    assert np.all(surface[-1] == "minecraft:podzol")
    assert {"minecraft:stone_bricks", "minecraft:podzol"} == set(
        surface[(result.host_weight > 0.25) & (result.host_weight < 0.75)]
    )
    repeat, _ = resolve_surface(result.field, apron_material(result, site, BOX, surround, host, seed=13))
    assert np.array_equal(surface, repeat)
    for invalid in [{"minecraft:air": 1}, {"minecraft:glass": -1}, {"minecraft:water": 1}]:
        with pytest.raises(ValueError, match="host palette"):
            apron_material(result, site, BOX, surround, invalid)


def test_cli_rejects_pad_before_protect_and_duplicate_pad(tmp_path):
    schema = [
        "--site",
        tmp_path / "site",
        "--box",
        *BOX,
        "--element",
        "yard",
        "--project",
        tmp_path,
        "--first-phase",
        1,
    ]
    for flags in [("--pad", 72), ("--protect", *PAD, "--pad", 72, "--pad", 73)]:
        with pytest.raises(SystemExit):
            _args(*schema, *flags)
