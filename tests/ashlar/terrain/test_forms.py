import json

import numpy as np
import pytest
from terrain.forms import Form, flow_build, form_write, gravity_violations, load_form
from terrain.live import LiveWrite, decode, greedy_fills
from terrain.site import Site
from voxel import Palette, VoxelModel


def _model():
    palette = Palette()
    palette.add("minecraft:andesite", None)
    palette.add("minecraft:oak_log[axis=x]", None)
    model = VoxelModel(2, 3, 4, palette)
    model.g[0, 1, 3] = 2
    model.g[1, 2, 0] = 1
    return model


def _write(origin, *states):
    codes = np.arange(1, len(states) + 1, dtype=np.uint16).reshape(1, -1, 1)
    return LiveWrite(origin, codes, ["skip", *states])


def test_carve_form_writes_air_only_where_occupied():
    carve = form_write(Form("notch", _model(), (-8, 62, -9), "carve"))

    assert decode(greedy_fills(carve)) == {
        (-8, 63, -6): "minecraft:air",
        (-7, 64, -9): "minecraft:air",
    }


def test_build_form_writes_loaded_palette_states(tmp_path):
    model = _model()
    model.save_npy(str(tmp_path / "rib.npy"))
    model.pal.to_json(str(tmp_path / "rib.json"))
    form = load_form(
        {
            "name": "rib",
            "model": "rib.npy",
            "palette": "rib.json",
            "origin": [-8, 62, -9],
            "mode": "build",
        },
        tmp_path,
    )

    assert form.name == "rib"
    assert decode(greedy_fills(form_write(form))) == {
        (-8, 63, -6): "minecraft:oak_log[axis=x]",
        (-7, 64, -9): "minecraft:andesite",
    }


def test_form_write_rejects_invalid_mode():
    with pytest.raises(ValueError, match="mode"):
        form_write(Form("notch", _model(), (0, 64, 0), "replace"))


def test_form_write_rejects_undefined_palette_code():
    model = _model()
    model.g[0, 0, 0] = 3
    with pytest.raises(ValueError, match="code 3"):
        form_write(Form("notch", model, (0, 64, 0), "build"))


@pytest.mark.parametrize("origin", [(0, -66, 0), (0, 318, 0), (29_999_999, 60, 0)])
def test_form_write_rejects_occupied_cells_outside_world(origin):
    with pytest.raises(ValueError, match="world"):
        form_write(Form("notch", _model(), origin, "carve"))


def test_form_write_allows_empty_margin_outside_build_height():
    model = _model()
    model.g[1, 2, 0] = 0
    write = form_write(Form("notch", model, (0, -65, 0), "carve"))

    assert decode(greedy_fills(write)) == {(0, -64, 3): "minecraft:air"}


def test_load_form_requires_project_relative_assets(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    model = _model()
    model.save_npy(str(tmp_path / "rib.npy"))
    model.pal.to_json(str(project / "rib.json"))
    with pytest.raises(ValueError, match="model.*project"):
        load_form(
            {
                "name": "rib",
                "model": "../rib.npy",
                "palette": "rib.json",
                "origin": [0, 62, 0],
                "mode": "build",
            },
            project,
        )


def _form_assets(tmp_path, grid=None, palette_text=None):
    model = _model()
    np.save(tmp_path / "rib.npy", model.g if grid is None else grid)
    palette_path = tmp_path / "rib.json"
    model.pal.to_json(str(palette_path))
    if palette_text is not None:
        palette_path.write_text(palette_text, encoding="utf-8")
    return {
        "name": "rib",
        "model": "rib.npy",
        "palette": "rib.json",
        "origin": [0, 62, 0],
        "mode": "carve",
    }


@pytest.mark.parametrize("code", [256, 257])
def test_load_form_rejects_grid_codes_that_would_wrap(tmp_path, code):
    entry = _form_assets(tmp_path, grid=np.full((1, 1, 1), code, dtype=np.uint16))

    with pytest.raises(ValueError, match="uint8"):
        load_form(entry, tmp_path)


@pytest.mark.parametrize(
    "grid", [np.zeros((2, 2), dtype=np.uint8), np.zeros((2, 0, 1), dtype=np.uint8)]
)
def test_load_form_requires_nonempty_three_dimensional_grid_shape(tmp_path, grid):
    entry = _form_assets(tmp_path, grid=grid)

    with pytest.raises(ValueError, match="3-D"):
        load_form(entry, tmp_path)


@pytest.mark.parametrize("palette_text", ["null", "[]"])
def test_load_form_reports_nonobject_palette_as_value_error(tmp_path, palette_text):
    entry = _form_assets(tmp_path, palette_text=palette_text)

    with pytest.raises(ValueError, match="palette"):
        load_form(entry, tmp_path)


@pytest.mark.parametrize(
    "palette",
    [
        {"0": ["air", "minecraft:air", None], "256": ["rib", "minecraft:stone", None]},
        {
            "0": ["stone", "minecraft:stone", None],
            "1": ["rib", "minecraft:stone", None],
        },
    ],
)
def test_load_form_rejects_invalid_palette_codes(tmp_path, palette):
    entry = _form_assets(
        tmp_path,
        grid=np.ones((1, 1, 1), dtype=np.uint8),
        palette_text=json.dumps(palette),
    )

    with pytest.raises(ValueError, match="palette"):
        load_form(entry, tmp_path)


def test_load_form_rejects_occupied_code_missing_from_palette_even_for_carve(tmp_path):
    entry = _form_assets(tmp_path, grid=np.full((1, 1, 1), 3, dtype=np.uint8))

    with pytest.raises(ValueError, match="palette.*code 3"):
        load_form(entry, tmp_path)


def test_flow_build_marks_flow_and_emits_only_sources():
    assert flow_build([{"at": [-40, 68, 12]}, {"at": [-42, 68, 14]}]) == {
        "blocks": [
            {"pos": [-40, 68, 12], "block": "minecraft:water"},
            {"pos": [-42, 68, 14], "block": "minecraft:water"},
        ],
        "liquids": "flow",
    }


@pytest.mark.parametrize(
    "fall",
    [
        {},
        {"at": [1, 70]},
        {"at": [True, 70, 3]},
        {"at": [1, 70.5, 3]},
        {"at": [1, "70", 3]},
        {"at": [1, 320, 3]},
        {"at": [1, 70, 30_000_000]},
    ],
)
def test_flow_build_rejects_impossible_source(fall):
    with pytest.raises(ValueError, match=r"falls\[0\]"):
        flow_build([fall])


def test_flow_build_checks_source_against_site_if_supplied():
    site = Site((0, 60, 0, 0, 70, 0), None, {(0, 0): [(60, 70, "minecraft:air")]})

    with pytest.raises(ValueError, match="site read"):
        flow_build([{"at": [0, 71, 0]}], site=site)
    assert flow_build([{"at": [0, 70, 0]}], site=site)["blocks"] == [
        {"pos": [0, 70, 0], "block": "minecraft:water"},
    ]


def test_gravity_check_finds_original_sand_over_a_carved_arch():
    rock = [
        (60, 64, "minecraft:stone"),
        (65, 65, "minecraft:sand"),
        (66, 68, "minecraft:air"),
    ]
    site = Site((-2, 60, -4, 0, 68, -4), None, {(x, -4): rock for x in (-2, -1, 0)})
    palette = Palette()
    stone = palette.add("minecraft:stone", None)
    arch = VoxelModel(3, 2, 1, palette).box((0, 0, 0), (2, 0, 0), stone)
    arch.g[1, 1, 0] = stone
    carve = form_write(Form("arch", arch, (-2, 63, -4), "carve"))

    assert gravity_violations([carve], site) == [(-1, 65, -4, "minecraft:sand")]


def test_gravity_uses_final_writes_in_order():
    site = Site((0, 60, 0, 0, 64, 0), None, {(0, 0): [(60, 64, "minecraft:stone")]})
    add = _write((0, 62, 0), "minecraft:white_concrete_powder")
    carve = _write((0, 61, 0), "minecraft:air")
    support = _write((0, 61, 0), "minecraft:stone")
    replace_powder = _write((0, 62, 0), "minecraft:andesite")

    assert gravity_violations([add, carve], site) == [
        (0, 62, 0, "minecraft:white_concrete_powder")
    ]
    assert gravity_violations([add, carve, support], site) == []
    assert gravity_violations([add, support, carve, replace_powder], site) == []
    assert gravity_violations([add, support, carve], site) == [
        (0, 62, 0, "minecraft:white_concrete_powder"),
    ]


@pytest.mark.parametrize(
    ("support", "falls"),
    [
        ("minecraft:air", True),
        ("minecraft:cave_air", True),
        ("minecraft:void_air", True),
        ("minecraft:water[level=5]", True),
        ("minecraft:lava[level=0]", True),
        ("minecraft:bubble_column[drag=true]", True),
        ("minecraft:seagrass", True),
        ("minecraft:fire[age=0]", True),
        ("minecraft:soul_fire", True),
        ("minecraft:short_grass", True),
        ("minecraft:red_shrub", True),
        ("minecraft:snow[layers=8]", True),
        ("minecraft:kelp[age=0]", False),
        ("minecraft:oak_stairs[waterlogged=true]", False),
        ("minecraft:mangrove_roots[waterlogged=true]", False),
        ("minecraft:poppy", False),
        ("minecraft:ice", False),
        ("minecraft:stone", False),
    ],
)
def test_gravity_classifies_support_using_paper_block_states(support, falls):
    site = Site(
        (0, 60, 0, 0, 62, 0),
        None,
        {
            (0, 0): [
                (60, 60, support),
                (61, 61, "minecraft:gravel"),
                (62, 62, "minecraft:air"),
            ],
        },
    )

    assert gravity_violations([], site) == (
        [(0, 61, 0, "minecraft:gravel")] if falls else []
    )


@pytest.mark.parametrize(
    "block",
    [
        "sand",
        "red_sand",
        "gravel",
        "suspicious_sand[dusted=0]",
        "suspicious_gravel[dusted=3]",
        "white_concrete_powder",
        "orange_concrete_powder",
        "magenta_concrete_powder",
        "light_blue_concrete_powder",
        "yellow_concrete_powder",
        "lime_concrete_powder",
        "pink_concrete_powder",
        "gray_concrete_powder",
        "light_gray_concrete_powder",
        "cyan_concrete_powder",
        "purple_concrete_powder",
        "blue_concrete_powder",
        "brown_concrete_powder",
        "green_concrete_powder",
        "red_concrete_powder",
        "black_concrete_powder",
        "anvil[facing=east]",
        "chipped_anvil[facing=south]",
        "damaged_anvil[facing=west]",
        "dragon_egg",
    ],
)
def test_gravity_flags_each_falling_block(block):
    site = Site((0, 60, 0, 0, 62, 0), None, {(0, 0): [(60, 62, "minecraft:cave_air")]})
    state = "minecraft:" + block

    assert gravity_violations([_write((0, 61, 0), state)], site) == [(0, 61, 0, state)]


def test_gravity_requires_a_site_read_for_each_occupied_cell():
    site = Site((1, 60, 0, 1, 63, 0), None, {(1, 0): [(60, 63, "minecraft:stone")]})
    left_margin = LiveWrite(
        (0, 61, 0), np.array([[[0]], [[1]]]), ["skip", "minecraft:stone"]
    )

    assert gravity_violations([left_margin], site) == []
    with pytest.raises(ValueError, match="site read"):
        gravity_violations([_write((0, 61, 0), "minecraft:stone")], site)


def test_gravity_requires_lower_read_for_new_block_at_truncated_floor():
    site = Site((0, 60, 0, 0, 62, 0), None, {(0, 0): [(60, 62, "minecraft:stone")]})

    with pytest.raises(ValueError, match="read lower"):
        gravity_violations([_write((0, 60, 0), "minecraft:sand")], site)


def test_gravity_does_not_guess_support_below_untouched_site_floor():
    site = Site(
        (0, 60, 0, 0, 62, 0),
        None,
        {
            (0, 0): [(60, 60, "minecraft:sand"), (61, 62, "minecraft:air")],
        },
    )

    assert gravity_violations([], site) == []


def test_gravity_detects_void_air_at_world_floor():
    site = Site((0, -64, 0, 0, -63, 0), None, {(0, 0): [(-64, -63, "minecraft:stone")]})

    assert gravity_violations([_write((0, -64, 0), "minecraft:gravel")], site) == [
        (0, -64, 0, "minecraft:gravel"),
    ]
