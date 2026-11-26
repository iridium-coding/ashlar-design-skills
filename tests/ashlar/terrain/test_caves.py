"""Designed caves: design validation, carving, dressing, lighting, pools, emit and checks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sitegen import make_site
from terrain import caves
from terrain.site import Site
from terrain.emit import VerifyError

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "skills" / "terrain-shape" / "scripts" / "terrain.py"
BOX = (0, 20, 0, 39, 70, 39)  # stone below y 64, grass at 64, air above


def _design(**extra) -> dict:
    base = {
        "element": "hall",
        "seed": 3,
        "site": "site",
        "chambers": [{"center": [20, 45, 20], "radii": [8, 5, 8]}],
    }
    base.update(extra)
    return base


def _setup(tmp_path, cells=None, ground=64, **extra):
    project = tmp_path / "proj"
    site = make_site(project / "site", BOX, ground=ground, cells=cells or {})
    design = caves.parse_design(_design(**extra), project)
    return project, site, design


def _idx(site: Site, x: int, y: int, z: int) -> tuple[int, int, int]:
    return x - site.box[0], y - site.box[1], z - site.box[2]


# ----------------------------------------------------------------- design file
@pytest.mark.parametrize(("change", "message"), [
    pytest.param({"element": "Bad Name"}, "element", id="element-not-kebab"),
    pytest.param({"style": "glass"}, "style", id="unknown-style"),
    pytest.param({"chambers": [{"center": [1, 2, 3]}]}, "radii", id="chamber-without-radii"),
    pytest.param({"chambers": [], "passages": [], "ravines": []}, "at least one", id="no-shapes"),
    pytest.param({"roof": -1}, "roof", id="negative-roof"),
    pytest.param({"lights": {"min": 16}}, "min", id="light-min-too-high"),
    pytest.param({"features": [{"id": "minecraft:not_a_feature", "on": "floor", "per_100": 1}]},
                 "unknown feature", id="unknown-feature"),
    pytest.param({"features": [{"id": "minecraft:sculk_patch_deep_dark", "on": "floor", "per_100": 1}]},
                 "warden", id="sculk-banned"),
])
def test_design_errors_name_the_problem(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        caves.parse_design(_design(**change), tmp_path)


def test_design_defaults(tmp_path):
    d = caves.parse_design(_design(), tmp_path)
    assert d.roof == 4 and d.style == "plain" and d.lights.minimum == 1
    assert d.limits == {"max_span": 24, "ceiling_std": 0.75, "flat_run": 14}
    assert d.features  # the style supplies default features


# ----------------------------------------------------------------------- carving
def test_void_is_deterministic_and_seeded(tmp_path):
    project, site, design = _setup(tmp_path)
    a, _ = caves.void_mask(design, site)
    b, _ = caves.void_mask(design, site)
    other = caves.parse_design(_design(seed=4), project)
    c, _ = caves.void_mask(other, site)
    assert a.any() and np.array_equal(a, b) and not np.array_equal(a, c)


def test_roof_is_kept_except_in_shafts(tmp_path):
    project, site, design = _setup(tmp_path, chambers=[{"center": [20, 58, 20], "radii": [7, 7, 7]}])
    void, report = caves.void_mask(design, site)
    ys = np.nonzero(void)[1] + site.box[1]
    assert ys.max() <= 64 - design.roof - 1 and report["roof_trimmed"] > 0
    shafted = caves.parse_design(
        _design(chambers=[{"center": [20, 58, 20], "radii": [7, 7, 7]}],
                shafts=[{"at": [20, 20], "from": 55, "radius": 2}]), project)
    void, _ = caves.void_mask(shafted, site)
    assert void[_idx(site, 20, 64, 20)], "the shaft opens the surface block"
    assert not void[_idx(site, 27, 64, 27)]


def test_pillars_stay_solid(tmp_path):
    _, site, design = _setup(tmp_path, pillars=[{"at": [20, 20], "radius": 2}])
    void, _ = caves.void_mask(design, site)
    x, y, z = _idx(site, 20, 41, 20)
    assert not void[x, y:y + 8, z].any()
    assert void[_idx(site, 25, 45, 20)]


def test_passages_and_ravines_carve_along_their_paths(tmp_path):
    _, site, design = _setup(
        tmp_path, chambers=[],
        passages=[{"points": [[5, 40, 5], [30, 44, 30]], "radius": [2, 3]}],
        ravines=[{"points": [[5, 34], [34, 34]], "top": 55, "bottom": 30, "width": 4}])
    void, _ = caves.void_mask(design, site)
    assert void[_idx(site, 5, 40, 5)] and void[_idx(site, 18, 42, 18)]
    assert void[_idx(site, 20, 54, 34)] and void[_idx(site, 20, 32, 34)]
    assert not void[_idx(site, 20, 54, 28)]


def test_player_blocks_in_the_void_are_flagged_not_refused(tmp_path):
    _, site, design = _setup(tmp_path, cells={(20, 45, 20): "minecraft:oak_planks"})
    plan = caves.plan_cave(design, site)
    assert plan.touched == [{"cell": [20, 45, 20], "block": "minecraft:oak_planks",
                             "action": "carve", "why": "inside chamber 0"}]


# ----------------------------------------------------------------------- dressing
def test_dress_touches_only_natural_shell_cells(tmp_path):
    ore = (12, 45, 20)
    _, site, design = _setup(tmp_path, cells={ore: "minecraft:coal_ore"},
                             chambers=[{"center": [20, 45, 20], "radii": [8, 5, 8], "roughness": 0}])
    void, _ = caves.void_mask(design, site)
    dress = caves.dress_write(design, site, void)
    written = np.zeros(void.shape, bool)
    off = tuple(o - b for o, b in zip(dress.origin, site.box[:3], strict=True))
    sl = tuple(slice(a, a + n) for a, n in zip(off, dress.codes.shape, strict=True))
    written[sl] = dress.codes != 0
    assert written.any() and not (written & void).any()
    near = np.zeros(void.shape, bool)
    for axis in range(3):
        for shift in (1, -1):
            near |= np.roll(void, shift, axis=axis)
    assert not (written & ~near).any(), "only face neighbours of the void are dressed"
    assert void[_idx(site, ore[0] + 1, ore[1], ore[2])], "the ore borders the void"
    assert not written[_idx(site, *ore)], "ores keep showing"


def test_deep_cells_use_deepslate_kinds(tmp_path):
    project = tmp_path / "proj"
    site = make_site(project / "site", (0, -20, 0, 39, 70, 39), ground=64)
    design = caves.parse_design(_design(chambers=[{"center": [20, -6, 20], "radii": [8, 4, 8]}]), project)
    void, _ = caves.void_mask(design, site)
    dress = caves.dress_write(design, site, void)
    states = {dress.palette[c] for c in np.unique(dress.codes) if c}
    below = [s for s in states if "deepslate" in s or "tuff" in s]
    assert below, states


# ----------------------------------------------------------------------- lighting
def test_lights_reach_every_floor_cell(tmp_path):
    _, site, design = _setup(tmp_path)
    void, _ = caves.void_mask(design, site)
    lights = caves.light_cells(design, site, void)
    sources = [(x, y, z, caves._light_of(state)) for x, y, z, state in lights]
    level = caves.block_light(void, sources, site.box)
    floor = caves.standable(void)
    assert floor.any() and level[floor].min() >= design.lights.minimum


def test_dark_cave_has_no_lights(tmp_path):
    _, site, design = _setup(tmp_path, lights=False)
    void, _ = caves.void_mask(design, site)
    assert caves.light_cells(design, site, void) == []


# -------------------------------------------------------------------------- pools
def test_pool_fills_connected_cells_up_to_its_level(tmp_path):
    _, site, design = _setup(tmp_path, chambers=[{"center": [20, 45, 20], "radii": [8, 5, 8]}],
                             pools=[{"at": [20, 41, 20], "level": 42}])
    void, _ = caves.void_mask(design, site)
    water = caves.pool_mask(design, site, void)
    ys = np.nonzero(water)[1] + site.box[1]
    assert water.any() and ys.max() <= 42 and not (water & ~void).any()


# ------------------------------------------------------------------------- emit
def test_emit_writes_backed_up_phases_features_and_rows(tmp_path):
    project, site, design = _setup(tmp_path)
    result = caves.emit_cave(design, project, first_phase=3)
    names = [row["name"] for row in result.rows]
    assert names[0].startswith("hall-carve") and any(n.startswith("hall-light") for n in names)
    assert all(row["rollback"] == "backup" for row in result.rows)
    assert [row["id"] for row in result.rows] == list(range(3, 3 + len(result.rows)))
    features = [row for row in result.rows if row["via"] == "commands"]
    assert len(features) == 1
    spec = json.loads((project / features[0]["file"]).read_text())
    assert spec["kind"] == "features" and spec["commands"][0].startswith("place feature minecraft:")
    for row in result.rows:
        assert (project / row["file"]).exists()
    assert result.quality["cave"][0]["file"] == "terrain/hall.cave.json"
    rows = (project / "terrain" / "hall.plan-rows.toon").read_text()
    assert "cave[1]{file}:" in rows
    assert (project / "terrain" / "previews" / "hall-plan.png").exists()


@pytest.mark.parametrize("name", ["x", "z"])
def test_section_previews_are_upright(tmp_path, name):
    from PIL import Image

    project, _, design = _setup(tmp_path)
    caves.emit_cave(design, project, first_phase=1, preview=True)

    img = Image.open(project / "terrain" / "previews" / f"hall-section-{name}.png").convert("RGB")
    ny = BOX[4] - BOX[1] + 1
    assert img.height == ny * 6  # rows run along y
    assert img.getpixel((0, 0)) == caves._COLOURS["air"]  # sky on top
    assert img.getpixel((0, img.height - 1)) == caves._COLOURS["rock"]  # rock at the bottom


# Blocks glow lichen grows on: `can_be_placed_on` in the 26.3 worldgen data
# (data/minecraft/worldgen/feature/glow_lichen.json).
LICHEN_HOSTS = frozenset(f"minecraft:{n}" for n in (
    "stone", "andesite", "diorite", "granite", "dripstone_block", "calcite", "tuff",
    "deepslate", "sulfur", "cinnabar"))


def _block(site: Site, x: int, y: int, z: int) -> str:
    for lo, hi, state in site.columns[(x, z)]:
        if lo <= y <= hi:
            return state.split("[")[0]
    raise KeyError((x, y, z))


def _features(project: Path, element: str = "hall") -> list[tuple[str, int, int, int]]:
    spec = json.loads((project / "terrain" / f"{element}.features.json").read_text())
    rows = [command.split() for command in spec["commands"]]  # place feature <id> x y z
    return [(fid, int(x), int(y), int(z)) for _, _, fid, x, y, z in rows]


def test_glow_lichen_spots_touch_rock_it_grows_on(tmp_path):
    project, site, design = _setup(
        tmp_path, style="lush",
        palette={"wall": {"moss_block": 3, "stone": 1}, "ceiling": {"moss_block": 1}},
        features=[{"id": "glow_lichen", "on": "wall", "per_100": 5}])
    caves.emit_cave(design, project, first_phase=1)
    final = caves.final_states(design, site)

    lichen = [(x, y, z) for fid, x, y, z in _features(project) if fid == "minecraft:glow_lichen"]
    bare = [(x, y, z) for x, y, z in lichen  # lichen grows on walls and ceilings, never floors
            if not any(_block(final, *face) in LICHEN_HOSTS for face in
                       ((x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1), (x, y + 1, z)))]

    assert lichen
    assert bare == []


def test_glow_lichen_runs_before_features_that_cover_rock(tmp_path):
    project, _, design = _setup(tmp_path, style="lush")
    caves.emit_cave(design, project, first_phase=1)

    order =[fid for fid, *_ in _features(project)]
    others = [i for i, fid in enumerate(order) if fid != "minecraft:glow_lichen"]

    assert "minecraft:glow_lichen" in order and others
    assert "minecraft:glow_lichen" not in order[others[0]:]


def test_emit_refuses_to_breach_buried_water(tmp_path):
    water = {(29, y, z): "minecraft:water[level=0]" for y in range(40, 50) for z in range(15, 26)}
    project, site, design = _setup(tmp_path, cells=water, lights=False,
                                   chambers=[{"center": [20, 45, 20], "radii": [10, 5, 6], "roughness": 0}])
    with pytest.raises(VerifyError, match="liquid"):
        caves.emit_cave(design, project, first_phase=1)


def test_emit_refuses_hanging_gravel(tmp_path):
    gravel = {(x, 50, z): "minecraft:gravel" for x in range(10, 31) for z in range(10, 31)}
    project, site, design = _setup(tmp_path, cells=gravel, lights=False, roof=2,
                                   chambers=[{"center": [20, 46, 20], "radii": [7, 4, 7], "roughness": 0}])
    with pytest.raises(VerifyError, match="gravity"):
        caves.emit_cave(design, project, first_phase=1)



def test_emit_refuses_a_design_that_fails_its_checks_but_preview_reports_it(tmp_path):
    wide = [{"center": [20, 45, 20], "radii": [17, 5, 17], "roughness": 0}]
    project, site, design = _setup(tmp_path, chambers=wide, lights=False)
    preview = caves.emit_cave(design, project, first_phase=1, preview=True)
    assert not preview.report["check"]["ok"]
    with pytest.raises(VerifyError, match="span"):
        caves.emit_cave(design, project, first_phase=1)
    assert not (project / "phases").exists()

# ------------------------------------------------------------------------ checks
def _post_build(site: Site, design, *, lit: bool) -> Site:
    """Apply the planned layers to a copy of the site read, as a fresh read would show."""
    void, _ = caves.void_mask(design, site)
    states = caves.final_states(design, site, void, lit=lit)
    return states


def test_cave_check_passes_a_built_cave(tmp_path):
    project, site, design = _setup(tmp_path)
    after = _post_build(site, design, lit=True)
    report = caves.check_cave(design, after)
    assert report["ok"], report


def test_cave_check_flags_a_dark_cave_and_a_flat_ceiling(tmp_path):
    flat = {(x, y, z): "minecraft:air" for x in range(10, 31) for y in range(40, 46) for z in range(10, 31)}
    project = tmp_path / "proj"
    site = make_site(project / "site", BOX, ground=64, cells=flat)
    design = caves.parse_design(_design(chambers=[{"center": [20, 42, 20], "radii": [10, 3, 10]}]), project)
    report = caves.check_cave(design, site)
    assert not report["ok"]
    failed = {c["name"] for c in report["checks"] if not c["ok"]}
    assert {"light", "ceiling"} <= failed


# --------------------------------------------------------------------------- CLI
def test_cli_cave_preview_then_check(tmp_path):
    project, site, _ = _setup(tmp_path)
    (project / "terrain").mkdir(exist_ok=True)
    design_path = project / "terrain" / "hall.cave.json"
    design_path.write_text(json.dumps(_design()), encoding="utf-8")
    run = subprocess.run([sys.executable, str(LAUNCHER), "cave", str(design_path), "--project",
                          str(project), "--first-phase", "1", "--preview"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["preview"] and out["phases"] and not (project / "phases").exists()
    check = subprocess.run([sys.executable, str(LAUNCHER), "cave-check", str(design_path),
                            "--site", str(project / "site")], capture_output=True, text=True)
    assert check.returncode == 1  # the untouched site has no cave yet
    assert json.loads(check.stdout)["ok"] is False


# ------------------------------------------------------------------ existing caves
ROOM = {(x, y, z): "minecraft:air" for x in range(10, 31) for y in range(40, 46) for z in range(10, 31)}
ADOPT = [{"at": [20, 40, 20], "box": [5, 35, 5, 34, 60, 34]}]


def _existing(tmp_path, cells=None, **extra):
    project = tmp_path / "proj"
    site = make_site(project / "site", BOX, ground=64, cells={**ROOM, **(cells or {})})
    data = {"element": "base", "seed": 3, "site": "site", "existing": ADOPT, **extra}
    return project, site, caves.parse_design(data, project)


def test_existing_cave_is_adopted_without_carving(tmp_path):
    project, site, design = _existing(tmp_path)
    plan = caves.plan_cave(design, site)
    assert int(plan.space.region.sum()) == len(ROOM)
    assert [mode for mode, _ in plan.layers] == ["light"]
    result = caves.emit_cave(design, project, first_phase=1)
    assert not any("carve" in row["name"] for row in result.rows)


def test_existing_cave_stops_at_the_surface(tmp_path):
    chimney = {(25, y, 25): "minecraft:air" for y in range(46, 65)}
    _, site, design = _existing(tmp_path, cells=chimney)
    region = caves.existing_region(design, site)
    ys = np.nonzero(region)[1] + site.box[1]
    assert ys.max() < 64
    assert not region[_idx(site, 25, 42, 25)], "a column open to the sky is not cave"
    assert region[_idx(site, 24, 42, 25)]


def test_existing_cave_point_must_be_open(tmp_path):
    project = tmp_path / "proj"
    site = make_site(project / "site", BOX, ground=64, cells=ROOM)
    design = caves.parse_design({"element": "base", "site": "site",
                                 "existing": [{"at": [20, 30, 20], "box": [5, 25, 5, 34, 60, 34]}]}, project)
    with pytest.raises(ValueError, match="open cell"):
        caves.existing_region(design, site)


def test_lights_count_lanterns_already_there(tmp_path):
    lanterns = {(x, 40, z): "minecraft:lantern[hanging=false]" for x in range(12, 31, 6) for z in range(12, 31, 6)}
    _, bare_site, bare = _existing(tmp_path / "bare")
    _, lit_site, lit = _existing(tmp_path / "lit", cells=lanterns)
    bare_void, _ = caves.void_mask(bare, bare_site)
    lit_void, _ = caves.void_mask(lit, lit_site)
    assert caves.light_cells(bare, bare_site, bare_void)
    assert caves.light_cells(lit, lit_site, lit_void) == []


def test_lanterns_hang_under_a_built_ceiling(tmp_path):
    builds = {(x, y, z): "minecraft:spruce_planks" for x in range(9, 32) for z in range(9, 32) for y in (39, 46)}
    _, site, design = _existing(tmp_path, cells=builds)
    void, _ = caves.void_mask(design, site)
    lights = caves.light_cells(design, site, void)
    assert lights and {state for *_, state in lights} == {"minecraft:lantern[hanging=true]"}
    assert {y for _, y, _, _ in lights} == {45}


def test_touched_player_blocks_need_the_users_token(tmp_path):
    fence = {(20, 41, 20): "minecraft:oak_fence", (21, 41, 20): "minecraft:chest[facing=north]"}
    project, site, design = _setup(tmp_path, cells=fence)
    preview = caves.emit_cave(design, project, first_phase=1, preview=True)
    built = preview.report["built"]
    assert built["count"] == 2 and built["loses_data"] == 1 and built["token"].startswith("built-")
    assert {i["why"] for i in built["items"]} == {"inside chamber 0"}
    with pytest.raises(VerifyError, match=built["token"]):
        caves.emit_cave(design, project, first_phase=1)
    assert not (project / "phases").exists()
    result = caves.emit_cave(design, project, first_phase=1, approve_built=built["token"])
    assert result.rows and (project / result.rows[0]["file"]).exists()


def test_a_move_rescues_a_block_from_the_carve(tmp_path):
    lantern = {(20, 41, 20): "minecraft:lantern[hanging=false]"}
    _, site, design = _setup(tmp_path, cells=lantern, moves=[{"from": [20, 41, 20], "to": [20, 65, 20]}])
    plan = caves.plan_cave(design, site)
    assert plan.touched[0]["why"] == "inside chamber 0; moved to (20, 65, 20)"
    after = caves.final_states(design, site)
    assert after.block(20, 65, 20) == "minecraft:lantern[hanging=false]"


def test_moving_half_a_door_is_refused(tmp_path):
    door = {(20, 65, 20): "minecraft:oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]",
            (20, 66, 20): "minecraft:oak_door[facing=north,half=upper,hinge=left,open=false,powered=false]"}
    _, site, design = _setup(tmp_path, cells=door, moves=[{"from": [20, 65, 20], "to": [22, 65, 20]}])
    with pytest.raises(ValueError, match="other half"):
        caves.plan_cave(design, site)


def test_features_keep_clear_of_player_blocks(tmp_path):
    table = {(24, 40, 24): "minecraft:crafting_table"}
    _, site, design = _existing(tmp_path, cells=table, style="lush")
    plan = caves.plan_cave(design, site)
    after = caves._apply(site, plan.layers)
    features = caves.feature_plan(design, after, plan.space.void, plan.water, plan.lights,
                                  carved=plan.space.carved)
    assert features
    assert min(abs(f.x - 24) + abs(f.y - 40) + abs(f.z - 24) for f in features) > 3


@pytest.mark.parametrize(("dress", "reaches_old_walls"), [
    pytest.param("new", False, id="new-only"),
    pytest.param("all", True, id="whole-cave"),
])
def test_dress_new_leaves_the_adopted_walls(tmp_path, dress, reaches_old_walls):
    passage = [{"points": [[31, 42, 20], [36, 42, 20]], "radius": [2, 2]}]
    _, site, design = _existing(tmp_path, passages=passage, dress=dress)
    plan = caves.plan_cave(design, site)
    dressed = dict(plan.layers)["dress"]
    x0 = dressed.origin[0]
    xs = np.nonzero(dressed.codes)[0] + x0
    assert bool(xs.min() < 25) == reaches_old_walls


def test_cave_check_lights_an_adopted_cave(tmp_path):
    _, site, design = _existing(tmp_path)
    assert not caves.check_cave(design, site)["ok"]
    assert caves.check_cave(design, caves.final_states(design, site))["ok"]
