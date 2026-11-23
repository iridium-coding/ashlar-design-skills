"""Generated trees must survive the same transforms the production stamper uses."""

from collections import deque
from dataclasses import replace
from itertools import product

import numpy as np
import pytest
import stamp
from PIL import Image
from terrain import trees

NAMES = (
    "broad-oak",
    "conifer-spire",
    "umbrella-pine",
    "weeping-willow",
    "windswept-cypress",
    "dead-snag",
    "giant-fantasy",
)
DIRECTIONS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def reachable(start, allowed, max_depth):
    seen = set(start)
    queue = deque((p, 0) for p in start)
    while queue:
        (x, y, z), depth = queue.popleft()
        if depth >= max_depth:
            continue
        for dx, dy, dz in DIRECTIONS:
            p = x + dx, y + dy, z + dz
            if p in allowed and p not in seen:
                seen.add(p)
                queue.append((p, depth + 1))
    return seen


def test_same_seed_same_tree():
    p = trees.PRESETS["giant-fantasy"]
    assert trees.generate(p) == trees.generate(p)
    assert trees.generate(p) != trees.generate(replace(p, seed=p.seed + 1))


@pytest.mark.parametrize("name", NAMES)
def test_every_preset_generates_a_valid_tree(name):
    params = trees.PRESETS[name]
    t = trees.generate(params)
    assert t.anchor in t.wood and t.anchor[1] == min(y for x, y, z in t.wood)
    assert set(t.wood) == reachable([t.anchor], t.wood, len(t.wood))
    assert t.leaves.keys() <= reachable(t.wood, t.leaves, 6)
    assert bool(t.leaves) == (name != "dead-snag")
    assert set(t.leaves.values()) <= {params.leaves + "[persistent=true]"}
    assert set(t.wood.values()) <= {params.wood + f"[axis={a}]" for a in "xyz"}
    assert t.wood.keys().isdisjoint(t.leaves) and t.ground.keys().isdisjoint(t.wood | t.leaves)
    assert bool(t.ground) == params.roots
    assert all(y == t.anchor[1] - 1 for x, y, z in t.ground)
    module = trees.to_module(t, name)
    parts = [module[key] for key in ("ground", "wood", "leaves")]
    assert all(set(part) == {"fills", "blocks"} for part in parts)
    bounds = [*t.wood, *t.leaves, *t.ground]
    assert module["size"] == [max(axis) - min(axis) + 1 for axis in zip(*bounds)]
    assert module["anchor"] == [v - min(axis) for v, axis in zip(t.anchor, zip(*bounds))]


def test_branch_logs_follow_their_axis():
    t = trees.generate(
        replace(
            trees.PRESETS["dead-snag"],
            branch_angle=90,
            curve=0,
            lean=(0, 0),
            branches=8,
            branch_levels=1,
            branch_length=0.85,
        )
    )
    for axis, delta in (("x", (1, 0, 0)), ("z", (0, 0, 1))):
        along = [p for p, state in t.wood.items() if state.endswith(f"[axis={axis}]")]
        assert along
        for x, y, z in along:
            dx, dy, dz = delta
            assert (x + dx, y + dy, z + dz) in t.wood or (x - dx, y - dy, z - dz) in t.wood


def test_module_round_trips_through_stamp():
    tree = trees.generate(trees.PRESETS["weeping-willow"])
    module = trees.to_module(tree, "bank-willow")
    low = tuple(min(v) for v in zip(*tree.ground, *tree.wood, *tree.leaves))
    for rotation, mirror in product(range(0, 360, 90), ("none", "x", "z")):
        phase = stamp.stamp(module, [-17, 60, 9], rotation, mirror)
        assert phase["blocks"] == []
        actual = {}
        for fill in phase["fills"]:
            for pos in product(*(range(a, b + 1) for a, b in zip(fill["from"], fill["to"]))):
                assert pos not in actual
                actual[pos] = (fill["block"], fill.get("filter"))
        expected = {}
        for parts in (tree.ground, tree.wood, tree.leaves):
            for pos, state in parts.items():
                local = [v - a for v, a in zip(pos, low)]
                world = stamp.transform_point(local, module["size"], rotation, mirror, [-17, 60, 9])
                expected[tuple(world)] = (
                    stamp.transform_state(state, rotation, mirror),
                    None if parts is tree.ground else "minecraft:air",
                )
        assert actual == expected


def test_tree_placements_put_anchor_on_surface():
    module = trees.to_module(trees.generate(trees.PRESETS["windswept-cypress"]), "cypress")
    origin = (-17, -9)
    surface = np.arange(120).reshape(12, 10) + 61
    points = [(origin[0] + x, origin[1] + z) for x, z in np.ndindex(surface.shape)]
    rows = trees.tree_placements(points, surface, origin, module, phase=2, seed=44)
    assert len(rows) == len(points)
    assert rows == trees.tree_placements(points, surface, origin, module, phase=2, seed=44)
    assert {(r["rotation"], r["mirror"]) for r in rows} == set(product(range(0, 360, 90), ("none", "x", "z")))
    for (x, z), r in zip(points, rows):
        mapped = stamp.transform_point(
            module["anchor"], module["size"], r["rotation"], r["mirror"], r["origin"]
        )
        assert mapped == [x, surface[x - origin[0], z - origin[1]] + 1, z]
        assert r["phase"] == 2 and r["module"] == "cypress"


@pytest.mark.parametrize("canopy", trees.CANOPIES)
def test_custom_canopies_and_preview(canopy, tmp_path):
    tree = trees.generate(trees.TreeParams(canopy=canopy, seed=13))
    assert bool(tree.leaves) == (canopy != "dead")
    paths = trees.preview(tree, str(tmp_path / canopy))
    assert len(paths) == 3
    for path in paths:
        with Image.open(path) as im:
            assert im.format == "PNG" and len(im.getcolors()) > 1


def test_no_foliage_when_density_is_zero():
    assert not trees.generate(trees.TreeParams(leaf_density=0)).leaves


@pytest.mark.parametrize(
    "edit",
    [
        {"wood": "minecraft:air"},
        {"leaves": "minecraft:stone"},
        {"leaf_density": float("nan")},
        {"lean": (1,)},
        {"trunk_width": 4},
    ],
)
def test_refuses_invalid_custom_parameters(edit):
    with pytest.raises(ValueError):
        trees.generate(replace(trees.TreeParams(), **edit))


@pytest.mark.parametrize(
    ("points", "surface"), [([(-1, 0)], [[80]]), ([(0, 0)], [[None]]), ([(0, 0)], [[319]])]
)
def test_refuses_unplaceable_trunks(points, surface):
    module = trees.to_module(trees.generate(trees.TreeParams()), "oak")
    with pytest.raises(ValueError):
        trees.tree_placements(points, np.array(surface), (0, 0), module, phase=3, seed=19)


def test_tree_actions_stamp_exact_wood_and_merge_existing_surface(tmp_path):
    import json

    source = tmp_path / "external"
    project = tmp_path / "project"
    files = trees.write_tree(
        "windswept-cypress", ["lean=[0.8,-0.15]", "height=17", "seed=74"], "ridge", source
    )
    assert {f.name for f in files} == {"ridge.json", "ridge_iso.png", "ridge_side.png", "ridge_front.png"}
    assert (
        trees.write_tree("windswept-cypress", ["lean=[0.8,-0.15]", "height=17", "seed=74"], "ridge", source)
        == files
    )
    with pytest.raises(ValueError, match="exist"):
        trees.write_tree("dead-snag", [], "ridge", source)
    positions = source / "points.json"
    positions.write_text("[[-3, 8], [4, 5]]")
    f6 = {"version": 1, "origin": [-30, -20], "size": [70, 62], "top": [61] * 4340, "skip": [0] * 4340}
    f6["skip"][9] = 1
    path = source / "bank.surface.json"
    path.write_text(json.dumps(f6))
    kwargs = {"phase": 8, "seed": 41, "surface_path": path}
    row, saved = trees.place_trees(files[0], positions, project, **kwargs)
    phase = json.loads((project / row["file"]).read_text())
    assert (row["id"], row["via"], row["rollback"]) == (8, "placer", "backup")
    assert row["file"] == "phases/08-ridge-trees.json"
    assert (project / "terrain/ridge.placements.json").is_file()
    expected = f6["skip"].copy()
    for f in phase["fills"]:
        assert f["filter"] == "minecraft:air"
        if "log[" in f["block"]:
            xa, _, za = f["from"]
            xb, _, zb = f["to"]
            for x, z in product(range(xa, xb + 1), range(za, zb + 1)):
                expected[(x + 30) * 62 + z + 20] = 1
    assert sum(expected) > 15
    assert json.loads(saved.read_text()) == {**f6, "skip": expected}
    assert json.loads(path.read_text()) == f6
    assert trees.place_trees(files[0], positions, project, phase=8, seed=41, surface_path=saved) == (
        row,
        saved,
    )
    positions.write_text("[[0,0]]")
    with pytest.raises(ValueError, match="exist"):
        trees.place_trees(files[0], positions, project, **kwargs)


def test_site_action_observes_actual_bed_and_liquid(tmp_path):
    import json

    from sitegen import make_site

    files = trees.write_tree("dead-snag", ["branches=0"], "snag", tmp_path / "modules")
    site = tmp_path / "read"
    make_site(site, (-9, 12, -9, 9, 53, 9), ground=27, cells={(0, 28, 0): "minecraft:lava"}, world="test")
    points = tmp_path / "points.json"
    points.write_text("[[0,0]]")
    project = tmp_path / "project"
    with pytest.raises(ValueError, match="wet|growable"):
        trees.place_trees(files[0], points, project, phase=3, site_path=site)
    assert not (project / "terrain/snag.placements.json").exists()
    points.write_text("[[3,2]]")
    row, f6 = trees.place_trees(files[0], points, project, phase=3, site_path=site)
    phase = json.loads((project / row["file"]).read_text())
    assert phase["world"] == "test" and row["from"][1] == 28 and f6.is_file()


@pytest.mark.parametrize(
    "positions", ["[]", "[[2,2],[2,2]]", "[[true,1]]", "[[1.5,1]]", "[[1,1,2]]", '{"points":[[1,2]]}']
)
def test_tree_place_rejects_malformed_points_before_publication(tmp_path, positions):
    import json

    f = tmp_path / "source.json"
    f.write_text(json.dumps(trees.to_module(trees.generate(trees.TreeParams()), "oak")))
    points = tmp_path / "points.json"
    points.write_text(positions)
    surface = tmp_path / "stand.surface.json"
    surface.write_text(
        json.dumps({"version": 1, "origin": [0, 0], "size": [5, 5], "top": [60] * 25, "skip": [0] * 25})
    )
    with pytest.raises(ValueError, match="point"):
        trees.place_trees(f, points, tmp_path / "project", phase=2, surface_path=surface)
    assert not (tmp_path / "project/terrain/oak.placements.json").exists()


def test_rejected_tree_does_not_replace_an_existing_project_module(tmp_path):
    import json

    source = tmp_path / "draft"
    files = trees.write_tree("dead-snag", ["branches=0", "curve=0"], "snag", source)
    points = source / "points.json"
    points.write_text("[[1,1]]")
    surface = source / "read.surface.json"
    surface.write_text(
        json.dumps({"version": 1, "origin": [-5, -5], "size": [15, 15], "top": [58] * 225, "skip": [0] * 225})
    )
    project = tmp_path / "project"
    dest = project / "modules/snag.json"
    dest.parent.mkdir(parents=True)
    dest.write_text('{"name":"my existing project module"}')
    with pytest.raises(ValueError, match="existing"):
        trees.place_trees(files[0], points, project, phase=4, surface_path=surface)
    assert dest.read_text() == '{"name":"my existing project module"}'
    assert not (project / "phases/04-snag-trees.json").exists()


def test_f7_anchor_must_be_emitted_axis_wood():
    module = {
        "name": "bad",
        "kind": "vegetation",
        "anchor": [0, 0, 0],
        "size": [2, 2, 1],
        "wood": {"blocks": [{"pos": [1, 1, 0], "block": "minecraft:oak_log[axis=y]"}]},
    }
    with pytest.raises(ValueError, match="anchor"):
        trees.tree_placements([(0, 0)], np.array([[59]]), (0, 0), module, phase=1, seed=3)


def test_custom_f6_skip_at_anchor_is_protected(tmp_path):
    import json

    files = trees.write_tree("dead-snag", ["branches=0"], "snag", tmp_path / "draft")
    points = tmp_path / "points.json"
    points.write_text("[[1,1]]")
    f6 = {"version": 1, "origin": [0, 0], "size": [15, 15], "top": [58] * 225, "skip": [0] * 225}
    f6["skip"][16] = 1
    path = tmp_path / "surface.json"
    path.write_text(json.dumps(f6))
    with pytest.raises(ValueError, match="skip|protected"):
        trees.place_trees(files[0], points, tmp_path / "out", phase=4, surface_path=path)
    assert not (tmp_path / "out/phases/04-snag-trees.json").exists()


def test_tree_parser_dispatches_both_commands_and_prints_executable_row(tmp_path, capsys):
    import argparse
    import json

    parser = argparse.ArgumentParser()
    trees.add_tree_parsers(parser.add_subparsers(dest="command", required=True))
    out = tmp_path / "design"
    args = parser.parse_args(
        [
            "tree",
            "--preset",
            "dead-snag",
            "--set",
            "height=4",
            "trunk_width=1",
            "--set",
            "branches=0",
            "curve=0",
            "--name",
            "sample",
            "--out",
            str(out),
        ]
    )
    assert trees.run_tree(args) == 0
    assert (out / "sample.json").is_file() and "sample_front.png" in capsys.readouterr().out
    f6 = out / "plot.surface.json"
    f6.write_text(
        json.dumps({"version": 1, "origin": [-2, -4], "size": [4, 4], "top": [70] * 16, "skip": [0] * 16})
    )
    points = out / "sample-points.json"
    points.write_text("[[-1,-2]]")
    project = tmp_path / "project"
    argv = [
        "tree-place",
        "--module",
        str(out / "sample.json"),
        "--points",
        str(points),
        "--surface",
        str(f6),
        "--phase",
        "2",
        "--project",
        str(project),
    ]
    assert trees.run_tree(parser.parse_args(argv)) == 0
    stdout = capsys.readouterr().out
    assert "phases[1]{id,name,file,blocks,from,to,via,rollback}" in stdout
    assert "02-sample-trees.json,4,-1 71 -2,-1 74 -2,placer,backup" in stdout
    assert (project / "modules/sample.json").read_bytes() == (out / "sample.json").read_bytes()
    assert parser.parse_args(argv + ["--seed", "48"]).seed == 48
