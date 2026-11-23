import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from sitegen import WATER, make_site
from terrain.ashlar_emit import emit_ashlar, plan_rows_toon
from terrain.emit import VerifyError
from voxel import Palette, VoxelModel

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills/terrain-shape/scripts/terrain.py"
PLACER = REPO / "skills/exec-ashlar/scripts/ashlar_place.py"
BOX = (-6, 42, 8, 21, 96, 35)


def cli(cwd, *args):
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *map(str, args)], cwd=cwd, capture_output=True, text=True, check=False
    )


def hill(project, *, cells=None):
    make_site(project / "site", BOX, cells=cells, world="overworld")
    return {
        "element": "hill",
        "nx": 24,
        "nz": 24,
        "origin": [-4, 0, 10],
        "site": {"read": "site", "band": 11},
        "graph": {"type": "Constant", "value": 80},
        "summary": 'Hill, with a "lookout"',
    }


def form(project, name, pos, state="minecraft:stone", mode="build"):
    pal = Palette()
    model = VoxelModel(1, 1, 1, pal)
    model.g[0, 0, 0] = pal.add(state, None)
    model.save_npy(str(project / f"{name}.npy"))
    pal.to_json(str(project / f"{name}.json"))
    return {
        "name": name,
        "model": f"{name}.npy",
        "palette": f"{name}.json",
        "origin": list(pos),
        "mode": mode,
    }


def test_emit_writes_phases_rows_and_surface_file(tmp_path):
    recipe = hill(tmp_path)
    recipe["forms"] = [form(tmp_path, "spire", (5, 88, 18)), form(tmp_path, "cut", (4, 64, 18), mode="carve")]
    result = emit_ashlar(recipe, tmp_path, first_phase=4, standalone=True)
    assert result.report.ok
    assert [r["name"] for r in result.phases] == ["hill-mass-1", "hill-carve-1", "hill-build-1"]
    for phase in result.phases:
        assert phase["rollback"] == "backup" and phase["via"] == "placer"
        phasefile = tmp_path / phase["file"]
        assert json.loads(phasefile.read_text())["world"] == "overworld"
        out = subprocess.check_output([sys.executable, str(PLACER), "plan", str(phasefile)], text=True)
        summary = json.loads(out)
        assert phase["blocks"] == summary["cells"]
        assert list(phase["from"]) == summary["bbox"]["from"]
        assert list(phase["to"]) == summary["bbox"]["to"]
    assert result.bbox[4] == 88
    assert len(result.quality["seam"]) == 4
    assert not result.quality.get("water_continuity")
    surface = json.loads(result.surface_file.read_text())
    assert surface["top"][(5 + 4) * 24 + (18 - 10)] == 88
    assert surface["origin"] == [-4, 10] and surface["size"] == [24, 24]
    assert len(surface["top"]) == len(surface["skip"]) == 24**2
    for view in ["hillshade", "relief", "profile", "slope", "eye"]:
        with Image.open(tmp_path / f"terrain/hill_{view}.png") as image:
            image.verify()
    assert "PASS" in (tmp_path / "terrain/hill.verify.txt").read_text()
    assert json.loads((tmp_path / "terrain/hill.recipe.json").read_text()) == recipe
    rows = plan_rows_toon(result)
    assert "phases[3]{id,name,file,blocks,from,to,via,rollback}:" in rows
    assert rows.strip() in (tmp_path / "plan.toon").read_text()
    assert "approved: no" in (tmp_path / "plan.toon").read_text()
    assert (tmp_path / "terrain/hill.plan-rows.toon").read_text().strip() == rows.strip()
    assert any("GATE A ovt_" in note for note in result.notes)


@pytest.mark.parametrize(
    ("problem", "error"),
    [
        ("flat", "not_degenerate"),
        ("gravity", "gravity"),
        ("spill", "hold_shores"),
        ("drain", "drain"),
        ("overlap", "lava"),
        ("reaction", "lava"),
    ],
)
def test_unsafe_recipe_fails_before_files(tmp_path, problem, error):
    pos = (-4, 65, 17)
    cells = {pos: WATER} if problem in {"drain", "spill", "overlap", "reaction"} else {}
    recipe = hill(tmp_path, cells=cells)
    if problem == "flat":
        recipe["graph"]["value"] = 64
    elif problem == "gravity":
        recipe["forms"] = [form(tmp_path, "sand", (4, 90, 17), "minecraft:sand")]
    elif problem == "spill":
        recipe["forms"] = [form(tmp_path, "bed", (-4, 64, 17), mode="carve")]
    elif problem == "drain":
        recipe["forms"] = [form(tmp_path, "drain", pos, mode="carve")]
    elif problem == "overlap":
        recipe["forms"] = [form(tmp_path, "lava", pos, "minecraft:lava")]
    else:
        recipe["forms"] = [form(tmp_path, "lava", (-4, 66, 17), "minecraft:lava")]
    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(VerifyError, match=error):
        emit_ashlar(recipe, tmp_path, first_phase=1, standalone=True)
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("key", ["biome_change", "biomes"])
def test_held_recipe_operations_are_refused(tmp_path, key):
    recipe = hill(tmp_path)
    recipe[key] = True
    with pytest.raises(ValueError, match=key):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "phases").exists()


def test_field_and_survey_from_another_directory(tmp_path):
    project = tmp_path / "project"
    recipe = hill(project, cells={(-4, 67, 16): "minecraft:oak_planks"})
    recipe_file = tmp_path / "input.json"
    recipe_file.write_text(json.dumps(recipe))
    survey = cli(tmp_path, "survey", "--site", project / "site", "--box", *BOX)
    assert survey.returncode == 1 and "minecraft:oak_planks" in survey.stdout
    result = cli(tmp_path, "field", recipe_file, "--project", project)
    assert result.returncode == 0, result.stderr
    assert (project / "terrain/previews/hill_eye.png").exists()
    assert not (project / "phases").exists()
    recipe["forms"] = [form(project, "bad", (5, 88, 18), "minecraft:gravel")]
    recipe_file.write_text(json.dumps(recipe))
    assert cli(tmp_path, "field", recipe_file, "--project", project).returncode == 1


def test_compare_and_seam_cli(tmp_path):
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps(
            {"version": 1, "origin": [11, -2], "size": [2, 2], "top": [61, 62, 63, 300], "skip": [0, 0, 0, 1]}
        )
    )
    heights = tmp_path / "heights.json"
    levels = [60, 61, 61, 62, 63, 63]
    data = {
        "version": 1,
        "origin": [10, -2],
        "size": [3, 2],
        "ground": levels,
        "surface": levels,
        "top": levels,
    }
    heights.write_text(json.dumps(data))
    assert cli(tmp_path, "compare", expected, heights).returncode == 0
    common = ("seam", heights, "--from", 11, -2, "--to", 11, -1, "--outward=-x")
    assert cli(tmp_path, *common).returncode == 0
    data["ground"] = data["surface"] = [50, 51, 50, 62, 63, 63]
    heights.write_text(json.dumps(data))
    assert cli(tmp_path, *common).returncode == 1
    assert cli(tmp_path, "compare", expected, heights).returncode == 1


def test_drain_preview_receipts_and_stale_approval(tmp_path):
    from terrain.site import drain_bodies, load_site

    recipe = hill(tmp_path, cells={(-2, 65, 17): WATER, (-2, 65, 21): WATER})
    recipe["drain"] = [{"at": [-2, 17]}, {"at": [-2, 21]}]
    bodies = drain_bodies(load_site(tmp_path / "site"), recipe)
    assert len(bodies) == 2
    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(VerifyError, match=bodies[1].id):
        emit_ashlar(recipe, tmp_path, first_phase=1, drain_approved=[bodies[0].id])
    with pytest.raises(VerifyError, match="stale"):
        emit_ashlar(recipe, tmp_path, first_phase=1, drain_approved=[b.id for b in bodies] + ["bad"])
    assert sorted(tmp_path.rglob("*")) == before
    recipe_file = tmp_path / "recipe.json"
    recipe_file.write_text(json.dumps(recipe))
    preview = cli(tmp_path, "field", recipe_file, "--project", tmp_path)
    assert preview.returncode == 0, preview.stderr
    for body in bodies:
        assert body.id in preview.stdout
    assert "seed" in preview.stdout and "bounds" in preview.stdout and "top" in preview.stdout
    assert not (tmp_path / "phases").exists()
    args = [word for b in bodies for word in ("--drain-approved", b.id)]
    accepted = cli(
        tmp_path, "emit", recipe_file, "--project", tmp_path, "--first-phase", 3, "--standalone", *args
    )
    assert accepted.returncode == 0, accepted.stderr
    plan = (tmp_path / "plan.toon").read_text()
    assert all(f"drain {b.id}" in plan for b in bodies)
    # An approved body does not authorize an unrelated carve.
    recipe["drain"] = recipe["drain"][:1]
    recipe["forms"] = [form(tmp_path, "other", (-2, 65, 21), mode="carve")]
    with pytest.raises(VerifyError, match="drain"):
        emit_ashlar(recipe, tmp_path, first_phase=1, drain_approved=[bodies[0].id])


def test_flow_has_one_source_and_backup_covers_possible_spread(tmp_path):
    recipe = hill(tmp_path)
    # Build a two-high rim around the source, with a single walled receiving cell.
    rocks = set()
    for x, z in [(3, 16), (4, 15), (4, 17), (6, 16), (5, 15), (5, 17)]:
        rocks.add((x, 87, z))
    rocks.update([(4, 86, 16), (5, 86, 16)])
    recipe["forms"] = [form(tmp_path, f"wall{i}", p) for i, p in enumerate(sorted(rocks))]
    recipe["falls"] = [{"at": [4, 87, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    phase = result.phases[-1]
    payload = json.loads((tmp_path / phase["file"]).read_text())
    assert payload["liquids"] == "flow"
    assert payload["blocks"] == [{"pos": [4, 87, 16], "block": "minecraft:water"}]
    assert phase["via"] == "mcp" and phase["rollback"] == "backup"
    assert phase["blocks"] == 1 and phase["from"] == (4, 87, 16) and phase["to"] == (5, 87, 16)
    recipe["falls"] = [{"at": [-4, 90, 16]}]
    with pytest.raises(VerifyError, match="leave the site"):
        emit_ashlar(recipe, tmp_path, first_phase=1)


def test_existing_contact_allowed_and_intentional_cover_reported(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 65, 17): WATER, (-4, 66, 17): "minecraft:lava", (-4, 65, 21): WATER})
    recipe["forms"] = [form(tmp_path, "cover", (-4, 65, 21))]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert any("retained 2" in note and "covered 1" in note for note in result.notes)


def test_gate_uses_contiguous_existing_level_not_floating_cell(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 68, 17): WATER})
    recipe["water"] = [{"level": 68, "at": [-4, 17]}]
    with pytest.raises(VerifyError, match="edge without matching existing water"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_continuity_only_for_planned_water(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 65, 18): WATER})
    recipe["pads"] = [{"center": [7, 21], "half": [1, 1], "level": 73, "shoulder": 3}]
    recipe["water"] = [{"at": [7, 21], "level": 74}]
    result = emit_ashlar(recipe, tmp_path, first_phase=3)
    rows = result.quality["water_continuity"]
    assert [r["level"] for r in rows] == [74]
    assert rows[0]["region_a"][0] <= 7 <= rows[0]["region_b"][0]
    assert rows[0]["region_a"][2] <= 21 <= rows[0]["region_b"][2]


def test_unknown_receipt_with_no_requested_drain_writes_nothing(tmp_path):
    recipe = hill(tmp_path)
    with pytest.raises(VerifyError, match="stale"):
        emit_ashlar(recipe, tmp_path, first_phase=1, drain_approved=["old"])
    assert not (tmp_path / "terrain").exists()


def test_many_flow_lips_use_placer_and_right_count(tmp_path):
    recipe = hill(tmp_path)
    recipe["falls"] = [{"at": [x, 62, z]} for x in range(-2, 14) for z in range(13, 26)][:201]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    phase = result.phases[-1]
    assert phase["via"] == "placer" and phase["blocks"] == 201
    summary = json.loads(
        subprocess.check_output(
            [sys.executable, str(PLACER), "plan", str(tmp_path / phase["file"])], text=True
        )
    )
    assert summary["cells"] == summary["liquid_cells"] == 201


def test_flow_lip_cannot_remove_support_or_claim_lava(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 65, 19): "minecraft:lava"})
    recipe["falls"] = [{"at": [-4, 65, 19]}]
    with pytest.raises(VerifyError, match="water/lava"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    recipe["forms"] = [form(tmp_path, "sand", (-4, 65, 21), "minecraft:sand")]
    recipe["falls"] = [{"at": [-4, 64, 21]}]
    with pytest.raises(VerifyError, match="gravity"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "phases").exists()


def test_direct_field_protected_columns_and_tree_skip(tmp_path):
    import numpy as np
    from sitegen import LOG
    from terrain.ashlar_emit import emit_field
    from terrain.live import decode
    from terrain.materialize import MaterialSpec
    from terrain.recipe import build_field
    from terrain.site import load_site

    recipe = hill(tmp_path, cells={(-4, 65, 17): LOG, (-4, 66, 17): LOG, (-3, 66, 17): LOG})
    site = load_site(tmp_path / "site")
    hf = build_field(recipe, tmp_path)
    mask = np.zeros(hf.h.shape, bool)
    mask[4, 4] = True
    spec = MaterialSpec.natural(hf)
    result = emit_field(
        hf, spec, site, tmp_path, recipe=recipe, element="direct", first_phase=8, protect=mask, max_columns=12
    )
    assert len(result.phases) == 4
    surface = json.loads(result.surface_file.read_text())
    for i, j in [(0, 7), (1, 7), (4, 4)]:
        assert surface["skip"][i * 24 + j] == 1
    for row in result.phases:
        payload = json.loads((tmp_path / row["file"]).read_text())
        assert all((x, z) != (0, 14) for x, y, z in decode(payload["fills"]))


def test_later_build_cannot_hide_an_earlier_water_lava_reaction(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 65, 19): WATER})
    recipe["forms"] = [
        form(tmp_path, "molten", (-4, 64, 19), "minecraft:lava"),
        form(tmp_path, "later", (-4, 64, 19), "minecraft:stone"),
    ]
    with pytest.raises(VerifyError, match="water/lava"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_later_repair_cannot_hide_a_breached_bank(tmp_path):
    recipe = hill(tmp_path, cells={(-4, 65, 19): WATER})
    recipe["forms"] = [
        form(tmp_path, "cut", (-4, 64, 19), mode="carve"),
        form(tmp_path, "patch", (-4, 64, 19)),
    ]
    with pytest.raises(VerifyError, match="hold_shores"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_follow_on_water_cannot_overwrite_new_lava_even_when_enclosed(tmp_path):
    recipe = hill(tmp_path)
    recipe["forms"] = [
        form(tmp_path, "lava", (3, 64, 20), "minecraft:lava"),
        form(tmp_path, "water", (3, 64, 20), "minecraft:water"),
    ]
    with pytest.raises(VerifyError, match="water/lava"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_margin_form_changes_phase_project_and_reported_reach(tmp_path):
    recipe = hill(tmp_path)
    recipe["forms"] = [form(tmp_path, "edge", (-6, 72, 18))]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.bbox[0] == -6
    assert result.phases[-1]["from"] == (-6, 72, 18)
    assert any("farthest write 2 blocks outside the box" in n for n in result.notes)


@pytest.mark.parametrize("state", ["minecraft:fire[age=0]", "minecraft:torch", "minecraft:unknown_shape"])
def test_review_non_solid_cover_cannot_drain(tmp_path, state):
    pos = (-4, 65, 17)
    recipe = hill(tmp_path, cells={pos: WATER})
    recipe["forms"] = [form(tmp_path, "replace", pos, state)]
    with pytest.raises(VerifyError, match="drain"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


@pytest.mark.parametrize("state", ["minecraft:fire", "minecraft:torch"])
def test_review_fire_and_torch_are_not_ground_or_flow_banks(tmp_path, state):
    recipe = hill(tmp_path, cells={(3, 52, 16): state})
    recipe["forms"] = [form(tmp_path, "marker", (5, 90, 20), state)]
    recipe["falls"] = [{"at": [4, 52, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["from"] == (3, 52, 16)
    grid = json.loads(result.surface_file.read_text())
    idx = (5 + 4) * 24 + 20 - 10
    assert grid["skip"][idx] == 0 and grid["top"][idx] < 90


def test_review_unknown_shape_in_flow_envelope_and_dry_form_permitted(tmp_path):
    recipe = hill(tmp_path, cells={(3, 52, 16): "minecraft:unknown_shape"})
    recipe["forms"] = [form(tmp_path, "marker", (5, 90, 20), "minecraft:unknown_model")]
    recipe["falls"] = [{"at": [4, 52, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["from"] == (3, 52, 16)
    assert json.loads(result.surface_file.read_text())["skip"][(5 + 4) * 24 + 20 - 10] == 1


@pytest.mark.parametrize("existing", [False, True])
def test_review_possible_source_formation_extends_flow_to_seventh_cell(tmp_path, existing):
    cells = {(1, 52, z): "minecraft:air" for z in range(16, 25)}
    if existing:
        cells[2, 52, 16] = WATER
    recipe = hill(tmp_path, cells=cells)
    recipe["falls"] = [{"at": [0, 52, 16]}]
    if not existing:
        recipe["falls"].append({"at": [2, 52, 16]})
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["to"][2] >= 23
    cells[1, 52, 24] = "minecraft:lava"
    recipe.update(hill(tmp_path, cells=cells))
    with pytest.raises(VerifyError, match="lava"):
        emit_ashlar(recipe, tmp_path, first_phase=1)


def test_review_gravity_checked_before_later_support(tmp_path):
    recipe = hill(tmp_path)
    recipe["forms"] = [
        form(tmp_path, "sand", (4, 90, 17), "minecraft:sand"),
        form(tmp_path, "support", (4, 89, 17)),
    ]
    with pytest.raises(VerifyError, match="gravity"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_review_new_static_water_on_unobserved_face_was_air(tmp_path):
    recipe = hill(tmp_path, cells={(-6, 52, 16): "minecraft:air"})
    recipe["forms"] = [form(tmp_path, "pool", (-6, 52, 16), "minecraft:water")]
    with pytest.raises(VerifyError, match="unobserved"):
        emit_ashlar(recipe, tmp_path, first_phase=1)
    assert not (tmp_path / "terrain").exists()


def test_review_seam_underwater_ground_and_trunks(tmp_path):
    data = {
        "version": 1,
        "origin": [0, 0],
        "size": [2, 1],
        "ground": [60, 63],
        "surface": [65, 65],
        "top": [65, 65],
    }
    heights = tmp_path / "heights.json"
    heights.write_text(json.dumps(data))
    args = ("--from", 0, 0, "--to", 0, 0, "--outward", "x")
    assert cli(tmp_path, "seam", heights, *args).returncode == 1
    data.update(ground=[69, 64], surface=[69, 64], top=[71, 64])
    heights.write_text(json.dumps(data))
    ambiguous = cli(tmp_path, "seam", heights, *args)
    assert ambiguous.returncode == 1 and "--site" in ambiguous.stderr
    site = tmp_path / "post-build"
    make_site(site, (0, 58, 0, 1, 75, 0), cells={(0, y, 0): "minecraft:oak_log" for y in range(65, 70)})
    assert cli(tmp_path, "seam", "--site", site, *args).returncode == 0


def test_review_preview_after_emit_keeps_artifacts_consistent(tmp_path):
    recipe = hill(tmp_path)
    emit_ashlar(recipe, tmp_path, first_phase=1, standalone=True)
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    before = {p: p.read_bytes() for p in files}
    from terrain.ashlar_emit import preview_field

    preview_field({**recipe, "graph": {"type": "Constant", "value": 77}}, tmp_path)
    assert all(p.read_bytes() == content for p, content in before.items())
    assert (tmp_path / "terrain/previews/hill_eye.png").exists()


def test_review_direct_reach_separate_from_flow_backup(tmp_path):
    recipe = hill(tmp_path, cells={(-5, 52, 16): "minecraft:air"})
    recipe["falls"] = [{"at": [-4, 52, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["from"] == (-5, 52, 16)
    assert any("farthest write 0 blocks outside" in n for n in result.notes)


def test_static_upgrade_of_flow_to_source_needs_observed_boundary(tmp_path):
    recipe = hill(tmp_path, cells={(-6, 52, 16): "minecraft:water[level=3]"})
    recipe["forms"] = [form(tmp_path, "pool", (-6, 52, 16), "minecraft:water")]
    with pytest.raises(VerifyError, match="unobserved"):
        emit_ashlar(recipe, tmp_path, first_phase=1)


def test_possible_water_reach_preserves_gravity_support(tmp_path):
    recipe = hill(tmp_path, cells={(3, 52, 16): "minecraft:torch", (3, 53, 16): "minecraft:sand"})
    recipe["falls"] = [{"at": [4, 52, 16]}]
    with pytest.raises(VerifyError, match="gravity"):
        emit_ashlar(recipe, tmp_path, first_phase=1)


def test_possible_water_reach_respects_protected_receiving_columns(tmp_path):
    import numpy as np
    from terrain.ashlar_emit import emit_field
    from terrain.materialize import MaterialSpec
    from terrain.recipe import build_field
    from terrain.site import load_site

    recipe = hill(tmp_path, cells={(1, 52, z): "minecraft:air" for z in range(16, 25)})
    recipe["falls"] = [{"at": [0, 52, 16]}, {"at": [2, 52, 16]}]
    hf = build_field(recipe, tmp_path)
    protected = np.zeros(hf.h.shape, bool)
    protected[1 + 4, 23 - 10] = True
    with pytest.raises(VerifyError, match="protected"):
        emit_field(
            hf,
            MaterialSpec.natural(hf),
            load_site(tmp_path / "site"),
            tmp_path,
            recipe=recipe,
            element="hill",
            first_phase=1,
            protect=protected,
        )
    assert not (tmp_path / "phases").exists()


def test_site_seam_ignores_non_ground_torches(tmp_path):
    site = tmp_path / "post-build"
    make_site(site, (0, 58, 0, 1, 75, 0), cells={(0, 70, 0): "minecraft:torch"})
    assert (
        cli(tmp_path, "seam", "--site", site, "--from", 0, 0, "--to", 0, 0, "--outward", "x").returncode == 0
    )


def test_converging_sources_reach_a_fixed_point(tmp_path):
    cells = {(1, 52, z): "minecraft:air" for z in range(16, 26)}
    recipe = hill(tmp_path, cells=cells)
    # The renewal at (1, 16) enables another at (1, 17) one step down the corridor.
    recipe["falls"] = [{"at": [0, 52, 17]}, {"at": [2, 52, 16]}, {"at": [0, 52, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["to"][2] >= 24


def test_turning_waterlogged_boundary_into_open_fluid_requires_a_read(tmp_path):
    recipe = hill(tmp_path, cells={(-6, 52, 16): "minecraft:mangrove_roots[waterlogged=true]"})
    recipe["forms"] = [form(tmp_path, "pool", (-6, 52, 16), "minecraft:water")]
    with pytest.raises(VerifyError, match="unobserved"):
        emit_ashlar(recipe, tmp_path, first_phase=1)


NEST = "minecraft:bee_nest[facing=east,honey_level=0]"


@pytest.mark.parametrize("floor", [NEST, "minecraft:shelf_mushroom", "minecraft:cactus"])
def test_attachment_and_plant_may_support_source_renewal(tmp_path, floor):
    cells = {(1, 52, z): "minecraft:air" for z in range(16, 25)}
    cells[1, 51, 16] = floor
    recipe = hill(tmp_path, cells=cells)
    recipe["falls"] = [{"at": [0, 52, 16]}, {"at": [2, 52, 16]}]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    assert result.phases[-1]["to"][2] >= 23


def test_bee_nest_counts_as_solid_surface_and_bank(tmp_path):
    recipe = hill(tmp_path, cells={(5, 52, 16): NEST})
    recipe["forms"] = [
        form(tmp_path, "nest", (4, 90, 17), NEST),
        form(tmp_path, "water", (4, 52, 16), "minecraft:water"),
    ]
    result = emit_ashlar(recipe, tmp_path, first_phase=1)
    surface = json.loads(result.surface_file.read_text())
    index = (4 + 4) * 24 + 17 - 10
    assert surface["top"][index] == 90 and surface["skip"][index] == 0


@pytest.mark.parametrize(("site_floor", "ceiling"), [(42, 96), (-64, 96), (42, 319)])
def test_changed_source_at_read_ceiling_needs_its_upper_neighbour(tmp_path, site_floor, ceiling):
    recipe = hill(tmp_path)
    make_site(tmp_path / "site", (BOX[0], site_floor, BOX[2], BOX[3], ceiling, BOX[5]))
    x, z = 4, 17
    walls = [
        (x - 1, ceiling, z),
        (x + 1, ceiling, z),
        (x, ceiling, z - 1),
        (x, ceiling, z + 1),
        (x, ceiling - 1, z),
    ]
    recipe["forms"] = [form(tmp_path, f"wall{i}", p) for i, p in enumerate(walls)]
    recipe["forms"].append(form(tmp_path, "pool", (x, ceiling, z), "minecraft:water"))
    if ceiling < 319:
        with pytest.raises(VerifyError, match="unobserved"):
            emit_ashlar(recipe, tmp_path, first_phase=1)
        assert not (tmp_path / "terrain").exists()
    else:
        assert emit_ashlar(recipe, tmp_path, first_phase=1).report.ok
