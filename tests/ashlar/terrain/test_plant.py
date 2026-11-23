"""Offline checks for F3 planting and biome commands and their F6 mask."""

from itertools import combinations

import numpy as np
import pytest
from terrain import plant
from terrain.field import HeightField
from terrain.masks import slope_deg
from terrain.site import surface_y

MIX = {
    "ground": {"minecraft:flower_plain": 1},
    "understory": {"minecraft:birch": 1},
    "canopy": {"minecraft:oak": 3, "minecraft:spruce": 1},
}
KNOWN = frozenset(fid for choices in MIX.values() for fid in choices)
ORIGIN = (-11, 7)


def planned(hf, blocks, water=None, mix=MIX):
    return plant.plan_features(hf, blocks, mix, origin=ORIGIN, seed=17, known=KNOWN, water=water)


def test_no_trees_on_cliffs_or_water():
    hf = HeightField(27, 25, base=58.5, sea_level=62)
    hf.h[14:, :] += 20.2
    blocks = np.full(hf.h.shape, "minecraft:grass_block[snowy=false]", dtype=object)
    blocks[:, 8:13] = "minecraft:stone"
    water = np.full_like(hf.h, np.nan)
    water[:, :5] = 85
    water[2:12, 15:] = 56  # retained liquid buried beneath the final dry grade
    features = planned(hf, blocks, water)
    assert features
    positions = {(f.x - ORIGIN[0], f.z - ORIGIN[1]) for f in features}
    assert any(x < 12 for x, z in positions)  # explicitly dry land below nominal sea
    assert any(x >= 15 for x, z in positions)
    slope = slope_deg(hf.h)
    for f in features:
        x, z = f.x - ORIGIN[0], f.z - ORIGIN[1]
        assert z >= 5 and not 8 <= z < 13
        assert slope[x, z] < 32
        assert f.y == int(surface_y(hf.h)[x, z]) + 1

    wet = np.ones(hf.h.shape, dtype=bool)
    assert not planned(hf, blocks, wet)


def test_layers_keep_spacing_and_order():
    hf = HeightField(20, 18, base=69.5)
    blocks = np.full(hf.h.shape, "minecraft:dirt")
    result = planned(hf, blocks)
    layers = list(dict.fromkeys(f.layer for f in result))
    assert layers == ["canopy", "understory", "ground"]
    assert result == sorted(result, key=lambda f: layers.index(f.layer))
    assert result == planned(hf, blocks)
    for a, b in combinations(result, 2):
        minimum = plant.LAYER_SPACING[b.layer][0]
        assert (a.x - b.x) ** 2 + (a.z - b.z) ** 2 >= minimum**2
    assert all(f.id in MIX[f.layer] and f.y == 71 for f in result)


def test_riparian_density_uses_actual_wet_columns(monkeypatch):
    hf = HeightField(24, 8, sea_level=90, base=55)
    blocks = np.full(hf.h.shape, "minecraft:mud")
    wet = np.zeros(hf.h.shape, dtype=bool)
    wet[0, :] = True
    observed = []

    def inspect(density, **kwargs):
        observed.append(density.copy())
        return [(0, 0), (1, 0), (24, 0)]

    monkeypatch.setattr(plant.scatter, "poisson", inspect)
    assert len(planned(hf, blocks, wet, {"canopy": MIX["canopy"]})) == 1
    (d,) = observed
    assert d[0, 0] == 0 < d[-1, 0] < d[1, 0] <= 1


def test_one_cell_wide_field_needs_observed_slope():
    hf = HeightField(1, 9, base=60.5, sea_level=60)
    blocks = np.full(hf.h.shape, "minecraft:podzol")
    with pytest.raises(ValueError, match="slope"):
        planned(hf, blocks)
    kwargs = {"origin": ORIGIN, "seed": 17, "known": KNOWN, "slope_density": np.ones(hf.h.shape)}
    assert plant.plan_features(hf, blocks, MIX, **kwargs)
    hf.sea_level = 61
    assert not plant.plan_features(hf, blocks, MIX, **kwargs)


@pytest.mark.parametrize(
    ("mix", "match"),
    [
        ({"ground": {"minecraft:absent": 1}}, "minecraft:absent"),
        ({"typo": {"minecraft:oak": 1}}, "typo"),
        ({"canopy": {"minecraft:oak": -1}}, "weight"),
        ({"canopy": {"minecraft:oak": 0}}, "weight"),
        ({"canopy": {"minecraft:oak": float("nan")}}, "weight"),
    ],
)
def test_unknown_feature_ids_are_refused(mix, match):
    hf = HeightField(8, 8)
    with pytest.raises(ValueError, match=match):
        planned(hf, np.full(hf.h.shape, "minecraft:stone"), mix=mix)


def test_features_file_box_includes_reach():
    features = [
        plant.Feature("minecraft:oak", -3, 63, 19, "canopy"),
        plant.Feature("minecraft:birch", 9, 68, -7, "understory"),
    ]
    assert plant.features_file(features, world="world") == {
        "version": 1,
        "kind": "features",
        "world": "world",
        "box": [-11, 61, -15, 17, 100, 27],
        "commands": ["place feature minecraft:oak -3 63 19", "place feature minecraft:birch 9 68 -7"],
    }
    assert plant.features_file(features, world=None, reach=(18, 43))["box"] == [-21, 61, -25, 27, 111, 37]
    with pytest.raises(ValueError):
        plant.features_file([], world=None)
    with pytest.raises(ValueError):
        plant.features_file(features, world=None, reach=(-1, 32))


def test_mark_trunks_skips_radius():
    surface = {"version": 1, "origin": [-3, 9], "size": [5, 4], "top": [64] * 20, "skip": [0] * 19 + [1]}
    out = plant.mark_trunks(surface, iter([(-3, 9), (1, 8)]))
    assert out["top"] == surface["top"] and surface["skip"] == [0] * 19 + [1]
    assert out["skip"] == [
        int(x * x + z * z <= 4 or (x - 4) ** 2 + (z + 1) ** 2 <= 4 or (x, z) == (4, 3))
        for x in range(5)
        for z in range(4)
    ]


def test_biome_commands_are_chunk_aligned_and_within_limit():
    result = plant.biome_commands(
        "minecraft:windswept_hills", origin=(-17, -2), size=(18, 19), y_range=(-9, 130), limit=256 * 13
    )
    cells = set()
    for c in result:
        verb, *coords, biome = c.split()
        assert (verb, biome) == ("fillbiome", "minecraft:windswept_hills")
        x1, y1, z1, x2, y2, z2 = map(int, coords)
        assert x1 % 16 == z1 % 16 == 0 and (x2, z2) == (x1 + 15, z1 + 15)
        assert y1 % 4 == 0 and y2 % 4 == 3
        assert 256 * (y2 - y1 + 1) <= 256 * 13
        for qy in range(y1 // 4, y2 // 4 + 1):
            cell = x1 // 16, qy, z1 // 16
            assert cell not in cells
            cells.add(cell)
    assert cells == {(cx, qy, cz) for cx in range(-2, 1) for cz in range(-1, 2) for qy in range(-3, 33)}


@pytest.mark.parametrize(
    "biome",
    [
        "",
        "Forest",
        "minecraft:forest replace minecraft:plains",
        "#minecraft:forest",
        "minecraft:forest\n",
        None,
        {},
    ],
)
def test_biome_commands_require_one_named_id(biome):
    with pytest.raises(ValueError, match="biome"):
        plant.biome_commands(biome, origin=(0, 0), size=(3, 3), y_range=(0, 4))


@pytest.mark.parametrize("kwargs", [{"limit": 1023}, {"size": (0, 2)}, {"y_range": (4, 3)}])
def test_biome_commands_reject_invalid_bounds(kwargs):
    args = {"origin": (0, 0), "size": (16, 16), "y_range": (0, 3), **kwargs}
    with pytest.raises(ValueError):
        plant.biome_commands("minecraft:forest", **args)


def test_features_file_clips_backup_at_physical_world_limits():
    features = [
        plant.Feature("minecraft:oak", -30_000_000, -64, 29_999_999, "canopy"),
        plant.Feature("minecraft:spruce", 1, 319, 0, "canopy"),
    ]
    assert plant.features_file(features, world=None)["box"] == [-30_000_000, -64, -8, 9, 319, 29_999_999]
    with pytest.raises(ValueError):
        plant.features_file([plant.Feature("minecraft:oak", 0, 320, 0, "canopy")], world=None)


def test_f6_rejects_a_corrupt_existing_mask():
    f6 = {"version": 1, "origin": [0, 0], "size": [2, 1], "top": [68, 68], "skip": [0, 7]}
    with pytest.raises(ValueError, match="skip"):
        plant.mark_trunks(f6, [])


def test_biome_commands_default_cap_and_real_world_limits():
    commands = plant.biome_commands("minecraft:taiga", origin=(-16, 0), size=(16, 16), y_range=(-64, 319))
    assert commands == [
        "fillbiome -16 -64 0 -1 63 15 minecraft:taiga",
        "fillbiome -16 64 0 -1 191 15 minecraft:taiga",
        "fillbiome -16 192 0 -1 319 15 minecraft:taiga",
    ]
    with pytest.raises(ValueError, match="world bounds"):
        plant.biome_commands("minecraft:taiga", origin=(-16, 0), size=(16, 16), y_range=(-65, 319))


def test_ids_cli_exact_version_fallback_and_unknown(tmp_path):
    from test_emit import cli

    result = cli(
        tmp_path,
        "ids",
        "--version",
        "26.3",
        "--features",
        "minecraft:oak,minecraft:birch",
        "--biomes",
        "minecraft:forest",
    )
    assert result.returncode == 0, result.stderr
    assert "26.3" in result.stdout
    bad = cli(tmp_path, "ids", "--version", "26.4", "--features", "minecraft:unregistered")
    assert bad.returncode == 1 and "fallback" in bad.stdout and "minecraft:unregistered" in bad.stdout


def test_plant_cli_writes_biome_file_only_when_asked(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    project = tmp_path / "project"
    site = project / "site"
    cells = {(x, 59, z): "minecraft:lava[level=0]" for x in range(-16, 0) for z in range(-9, 2)}
    cells.update({(x, 58, z): "minecraft:stone" for x in range(4, 8) for z in range(-9, 2)})
    make_site(site, (-17, 40, -10, 8, 99, 2), ground=58, cells=cells, world="overworld")
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}, "ground": {"minecraft:grass": 1}}))
    common = [
        "plant",
        "--site",
        site,
        "--box",
        -16,
        -9,
        7,
        1,
        "--project",
        project,
        "--phase",
        4,
        "--mix",
        mix,
        "--element",
        "grove",
        "--version",
        "26.3",
        "--reach",
        9,
        35,
        4,
    ]
    first = cli(tmp_path, *common)
    assert first.returncode == 0, first.stderr
    assert "commands,backup" in first.stdout and not list((project / "phases").glob("*-biome.*"))
    f = json.loads((project / "phases/04-grove-features.commands.json").read_text())
    pts = [tuple(map(int, c.split()[-3:])) for c in f["commands"]]
    assert pts and all(0 <= x < 4 and y == 59 and -9 <= z <= 1 for x, y, z in pts)
    assert f["box"] == [
        min(x for x, y, z in pts) - 9,
        55,
        min(z for x, y, z in pts) - 9,
        max(x for x, y, z in pts) + 9,
        94,
        max(z for x, y, z in pts) + 9,
    ]
    surface_path = project / "terrain/grove.surface.json"
    surface = json.loads(surface_path.read_text())
    assert any(surface["skip"]) and surface["top"][0] == 59
    surface["skip"][0] = 1
    surface_path.write_text(json.dumps(surface))
    second = cli(tmp_path, *common, "--biome-change", "minecraft:forest")
    assert second.returncode == 0, second.stderr
    f3 = json.loads((project / "phases/05-grove-biome.commands.json").read_text())
    assert all(cmd.endswith(" minecraft:forest") for cmd in f3["commands"])
    assert f3["world"] == "overworld" and f3["box"] == [-16, 48, -16, 15, 63, 15]
    assert "-16 48 -16" in second.stdout and "15 63 15" in second.stdout and "commands,biome" in second.stdout
    assert json.loads(surface_path.read_text())["skip"][0] == 1
    # The runner's pure F3 loader validates both files without connecting to a server.
    from runpy import run_path

    from test_emit import PLACER

    runner = run_path(str(PLACER))
    for path in (project / "phases").glob("*.commands.json"):
        readback = runner["load_commands"](path, runner["Limits"]())
        assert readback["commands"] == json.loads(path.read_text())["commands"]


@pytest.mark.parametrize(
    "feature,biome",
    [
        ("minecraft:fake", None),
        ("minecraft:oak", "minecraft:missing"),
        ("minecraft:lake_lava", None),
        ("minecraft:oak", "forest"),
    ],
)
def test_plant_cli_rejects_unknown_or_nonvegetation_before_writing(tmp_path, feature, biome):
    import json

    from sitegen import make_site
    from test_emit import cli

    site = tmp_path / "site"
    project = tmp_path / "out"
    make_site(site, (-9, 54, -2, 8, 90, 5))
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {feature: 1}}))
    args = ["plant", "--site", site, "--box", -8, -2, 7, 3, "--phase", 1, "--project", project, "--mix", mix]
    result = cli(tmp_path, *args, *(["--biome-change", biome] if biome else []))
    assert result.returncode == 1 and (biome or feature) in result.stderr
    assert not project.exists()


def test_recipe_planting_uses_final_projection_and_exact_drain_receipts(tmp_path):
    import json

    from sitegen import WATER
    from terrain.ashlar_emit import emit_ashlar
    from terrain.site import drain_bodies, load_site
    from test_emit import cli, form, hill

    project = tmp_path / "project"
    recipe = hill(project, cells={(-3, 65, 17): WATER, (-3, 65, 21): WATER})
    recipe["drain"] = [{"at": [-3, 17]}]
    recipe["forms"] = [form(project, "slab", (1, 84, 16), "minecraft:stone")]
    (receipt,) = drain_bodies(load_site(project / "site"), recipe)
    emit_ashlar(recipe, project, first_phase=1, drain_approved=[receipt.id])
    recipe_path = project / "terrain/hill.recipe.json"
    path = project / "terrain/hill.surface.json"
    surface = json.loads(path.read_text())
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"ground": {"minecraft:grass": 1}}))
    args = ["plant", "--recipe", recipe_path, "--phase", 8, "--project", project, "--mix", mix]
    denied = cli(tmp_path, *args)
    assert denied.returncode == 1 and receipt.id in denied.stderr
    assert not (project / "phases/08-hill-features.commands.json").exists()
    ok = cli(tmp_path, *args, "--drain-approved", receipt.id)
    assert ok.returncode == 0, ok.stderr
    payload = json.loads((project / "phases/08-hill-features.commands.json").read_text())
    pts = [tuple(map(int, c.split()[-3:])) for c in payload["commands"]]
    assert pts and all((x, z) not in {(1, 16), (-3, 21)} for x, y, z in pts)
    for x, y, z in pts:
        idx = (x + 4) * 24 + (z - 10)
        assert surface["top"][idx] + 1 == y
    assert json.loads(path.read_text())["top"] == surface["top"]
    _, blocks, wet, _, _ = plant.recipe_planting(recipe, project, [receipt.id])
    assert np.isnan(wet[1, 7]) and wet[1, 11] == 65
    assert blocks[5, 6] is None  # stone form above the fitted ground


def test_biome_preview_discloses_world_and_true_box_without_output(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    site = tmp_path / "site"
    project = tmp_path / "out"
    make_site(site, (-9, 54, -2, 8, 90, 5), world="test-world")
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}}))
    args = [
        "plant",
        "--site",
        site,
        "--box",
        -8,
        -2,
        7,
        3,
        "--phase",
        2,
        "--project",
        project,
        "--mix",
        mix,
        "--biome-preview",
        "minecraft:taiga",
    ]
    preview = cli(tmp_path, *args)
    assert preview.returncode == 0, preview.stderr
    assert "minecraft:taiga in world test-world from -16 56 -16 to 15 71 15" in preview.stdout
    assert not project.exists()


def test_large_verified_vegetation_needs_declared_growth_bounds():
    mix = {"canopy": {"minecraft:mangrove": 1}}
    known = frozenset(mix["canopy"])
    with pytest.raises(ValueError, match="reach"):
        plant.vegetation_reach(mix, known, None)
    assert plant.vegetation_reach(mix, known, (26, 56, 18)) == (26, 56, 18)


def test_plant_rejects_site_free_nondefault_dimension(tmp_path):
    import json

    from test_emit import cli

    recipe = {
        "element": "woods",
        "dimension": "minecraft:the_nether",
        "nx": 12,
        "nz": 12,
        "origin": [0, 0, 0],
        "graph": {"type": "Constant", "value": 64},
        "material": {"surface": {"minecraft:dirt": 1}},
    }
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(recipe))
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}}))
    args = ["plant", "--recipe", path, "--project", tmp_path / "out", "--mix", mix, "--phase", 1]
    result = cli(tmp_path, *args)
    assert result.returncode == 1 and "F1 world" in result.stderr
    assert not (tmp_path / "out").exists()
    recipe["dimension"] = "minecraft:overworld"
    path.write_text(json.dumps(recipe))
    result = cli(tmp_path, *args)
    assert result.returncode == 0, result.stderr
    output = json.loads((tmp_path / "out/phases/01-woods-features.commands.json").read_text())
    assert output["world"] is None


def test_rounded_diagonal_cliff_rejects_positions():
    hf = HeightField(28, 28)
    x, z = np.indices(hf.h.shape)
    hf.h = np.where((x + z) % 4 < 2, 65.49, 65.51)
    blocks = np.full(hf.h.shape, "minecraft:grass_block")
    result = planned(hf, blocks)
    slope = slope_deg(surface_y(hf.h))
    assert all(slope[f.x - ORIGIN[0], f.z - ORIGIN[1]] < 32 for f in result)


def test_site_crop_measures_slopes_from_neighbouring_ground(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    site = tmp_path / "site"
    ground = {(x, z): 64 + 3 * x for x in range(-2, 3) for z in range(-7, 8)}
    make_site(site, (-2, 45, -7, 2, 95, 7), ground=ground)
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}}))
    args = [
        "plant",
        "--site",
        site,
        "--box",
        0,
        -5,
        0,
        5,
        "--project",
        tmp_path / "forest",
        "--phase",
        1,
        "--mix",
        mix,
    ]
    steep = cli(tmp_path, *args)
    assert steep.returncode == 0, steep.stderr
    assert not list((tmp_path / "forest").rglob("*.commands.json"))
    make_site(site, (0, 45, -7, 0, 95, 7), ground=64)
    unresolved = cli(tmp_path, *args)
    assert unresolved.returncode == 1 and "slope" in unresolved.stderr


def test_empty_rerun_refuses_stale_features_and_biomes(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    make_site(tmp_path / "site", (-2, 50, -2, 15, 90, 15), ground=64)
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}}))
    project = tmp_path / "out"
    args = [
        "plant",
        "--site",
        tmp_path / "site",
        "--box",
        0,
        0,
        14,
        14,
        "--phase",
        4,
        "--project",
        project,
        "--mix",
        mix,
    ]
    assert cli(tmp_path, *args, "--biome-change", "minecraft:forest").returncode == 0
    originals = {p: p.read_bytes() for p in project.rglob("*.json")}
    for contents in ({"canopy": {"minecraft:oak": 1}}, {}):
        mix.write_text(json.dumps(contents))
        rerun = cli(tmp_path, *args)
        assert rerun.returncode == 1 and "existing" in rerun.stderr
        assert {p: p.read_bytes() for p in originals} == originals


def test_wide_or_fallen_solid_features_mask_full_reach():
    surface = {"version": 1, "size": [20, 20], "origin": [-7, -7], "top": [64] * 400, "skip": [0] * 400}
    fallen = plant.Feature("minecraft:fallen_oak_tree", 0, 65, 0, "ground")
    f6 = plant.mark_feature_trunks(surface, [fallen], (8, 32, 2))
    assert f6["skip"][(7 + 7) * 20 + 7] and f6["skip"][15 * 20 + 15]
    assert not f6["skip"][19 * 20 + 19] and surface["skip"] == [0] * 400
    oak = plant.Feature("minecraft:oak", 0, 65, 0, "canopy")
    assert plant.mark_feature_trunks(surface, [oak], (8, 32, 2)) == plant.mark_trunks(surface, [(0, 0)])


def test_biome_only_uses_own_phase_and_preserves_manual_planting(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    project = tmp_path / "out"
    make_site(tmp_path / "site", (-3, 48, -3, 12, 91, 12), ground=64, world="forest-world")
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:oak": 1}}))
    args = [
        "plant",
        "--site",
        tmp_path / "site",
        "--box",
        -1,
        -1,
        10,
        10,
        "--project",
        project,
        "--element",
        "grove",
    ]
    assert cli(tmp_path, *args, "--mix", mix, "--phase", 4).returncode == 0
    files = list(project.rglob("*.json"))
    for path in files:
        data = json.loads(path.read_text())
        if "skip" in data:
            data["skip"][-1] = 1
        else:
            data["commands"] = data["commands"][:1]
        path.write_text(json.dumps(data, indent=2))
    originals = {p: p.read_bytes() for p in files}
    preview = cli(tmp_path, *args, "--biome-only", "--biome-preview", "minecraft:taiga", "--phase", 7)
    assert preview.returncode == 0, preview.stderr
    assert {p: p.read_bytes() for p in project.rglob("*.json")} == originals
    result = cli(tmp_path, *args, "--biome-only", "--biome-change", "minecraft:taiga", "--phase", 7)
    assert result.returncode == 0, result.stderr
    assert {p: p.read_bytes() for p in originals} == originals
    assert list(set(project.rglob("*.json")) - originals.keys()) == [
        project / "phases/07-grove-biome.commands.json"
    ]


def test_f1_dimension_requires_a_matching_approved_wrapper(tmp_path):
    import json

    from sitegen import make_site
    from test_emit import cli

    make_site(tmp_path / "site", (-1, 40, -1, 8, 90, 8), world="forest_nether")
    mix = tmp_path / "mix.json"
    mix.write_text(json.dumps({"canopy": {"minecraft:birch": 1}}))
    args = [
        "plant",
        "--site",
        tmp_path / "site",
        "--box",
        0,
        0,
        7,
        7,
        "--phase",
        3,
        "--mix",
        mix,
        "--project",
        tmp_path / "out",
        "--dimension",
        "minecraft:the_nether",
    ]
    preview = cli(tmp_path, *args, "--biome-preview", "minecraft:forest")
    assert preview.returncode == 0, preview.stderr
    assert "forest_nether" in preview.stdout and "--dimension minecraft:the_nether" in preview.stdout
    biome = cli(tmp_path, *args, "--biome-change", "minecraft:forest")
    assert biome.returncode == 1 and "probe" in biome.stderr and not (tmp_path / "out").exists()
    features = cli(tmp_path, *args)
    assert features.returncode == 0 and "--dimension minecraft:the_nether" in features.stdout
    f3 = json.loads((tmp_path / "out/phases/03-planting-features.commands.json").read_text())
    assert f3["world"] == "forest_nether"
    import subprocess
    import sys

    from test_emit import PLACER

    parsed = subprocess.run(
        [
            sys.executable,
            str(PLACER),
            "commands",
            str(tmp_path / "out/phases/03-planting-features.commands.json"),
            "--check",
            "--dimension",
            "minecraft:the_nether",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(parsed.stdout)["dimension"] == "minecraft:the_nether"
