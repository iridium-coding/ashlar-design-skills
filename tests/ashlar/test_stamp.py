"""Tests for stamp.py."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import stamp as st

STAMP = Path(__file__).resolve().parents[2] / "skills" / "exec-ashlar" / "scripts" / "stamp.py"


def test_rotation_maps_corners_clockwise():
    size = [3, 1, 2]
    assert st.transform_point([2, 0, 0], size, 90, "none", [0, 0, 0]) == [1, 0, 2]
    assert st.transform_point([0, 0, 0], size, 90, "none", [0, 0, 0]) == [1, 0, 0]
    assert st.transform_point([0, 0, 0], size, 180, "none", [0, 0, 0]) == [2, 0, 1]
    assert st.transform_point([0, 0, 1], size, 270, "none", [10, 64, -5]) == [11, 64, -3]
    assert st.transform_point([0, 0, 0], size, 0, "x", [0, 0, 0]) == [2, 0, 0]
    assert st.transform_point([0, 0, 0], size, 0, "z", [0, 0, 0]) == [0, 0, 1]


def test_four_quarter_turns_are_identity():
    state = "minecraft:oak_stairs[facing=north,half=bottom,shape=inner_left]"
    turned = state
    for _ in range(4):
        turned = st.transform_state(turned, 90, "none")
    assert turned == state


@pytest.mark.parametrize("state,rotation,mirror,expected", [
    ("minecraft:oak_stairs[facing=north,half=bottom,shape=straight]", 90, "none",
     "minecraft:oak_stairs[facing=east,half=bottom,shape=straight]"),
    ("minecraft:oak_stairs[facing=north,shape=inner_left]", 0, "x",
     "minecraft:oak_stairs[facing=north,shape=inner_right]"),
    ("minecraft:oak_stairs[facing=north,shape=outer_right]", 0, "z",
     "minecraft:oak_stairs[facing=south,shape=outer_left]"),
    ("minecraft:oak_door[facing=east,half=lower,hinge=left]", 0, "x",
     "minecraft:oak_door[facing=west,half=lower,hinge=right]"),
    ("minecraft:oak_sign[rotation=4]", 90, "none", "minecraft:oak_sign[rotation=8]"),
    ("minecraft:oak_sign[rotation=4]", 0, "x", "minecraft:oak_sign[rotation=12]"),
    ("minecraft:oak_sign[rotation=2]", 0, "z", "minecraft:oak_sign[rotation=6]"),
    ("minecraft:oak_log[axis=x]", 90, "none", "minecraft:oak_log[axis=z]"),
    ("minecraft:oak_log[axis=y]", 90, "none", "minecraft:oak_log[axis=y]"),
    ("minecraft:rail[shape=north_south]", 90, "none", "minecraft:rail[shape=east_west]"),
    ("minecraft:rail[shape=ascending_east]", 90, "none", "minecraft:rail[shape=ascending_south]"),
    ("minecraft:rail[shape=south_east]", 90, "none", "minecraft:rail[shape=south_west]"),
    ("minecraft:oak_fence[east=true,north=false,south=false,waterlogged=false,west=true]", 90,
     "none", "minecraft:oak_fence[waterlogged=false]"),
    ("minecraft:cobblestone_wall[east=low,north=none,south=none,up=true,west=tall]", 90,
     "none", "minecraft:cobblestone_wall[up=true]"),
    ("minecraft:vine[east=false,north=true,south=false,up=false,west=false]", 90, "none",
     "minecraft:vine[south=false,east=true,west=false,up=false,north=false]"),
    ("minecraft:chest[facing=south,type=left]", 0, "none", "minecraft:chest[facing=south,type=single]"),
    ("minecraft:crafter[orientation=north_up,triggered=false]", 90, "none",
     "minecraft:crafter[orientation=east_up,triggered=false]"),
    ("minecraft:observer[facing=up]", 90, "none", "minecraft:observer[facing=up]"),
    ("minecraft:oak_wall_sign[facing=north]", 180, "none", "minecraft:oak_wall_sign[facing=south]"),
])
def test_block_state_transforms(state, rotation, mirror, expected):
    assert st.transform_state(state, rotation, mirror) == expected


def test_stamp_module_normalises_boxes_and_keeps_signs():
    module = {"name": "hut", "size": [3, 2, 2],
              "fills": [{"from": [0, 0, 0], "to": [2, 0, 1], "block": "minecraft:stone",
                         "filter": "minecraft:air"}],
              "blocks": [{"pos": [2, 1, 0], "block": "minecraft:oak_wall_sign[facing=north]",
                          "sign": {"front": ["Hi"]}}]}
    out = st.stamp(module, [100, 64, 100], 90, "none")
    assert out["fills"] == [{"from": [100, 64, 100], "to": [101, 64, 102],
                             "block": "minecraft:stone", "filter": "minecraft:air"}]
    assert out["blocks"] == [{"pos": [101, 65, 102],
                              "block": "minecraft:oak_wall_sign[facing=east]",
                              "sign": {"front": ["Hi"]}}]


def test_stamp_rejects_text_and_out_of_bounds():
    with pytest.raises(st.StampError):
        st.stamp({"size": [1, 1, 1], "text": [{}]}, [0, 0, 0], 0, "none")
    with pytest.raises(st.StampError):
        st.stamp({"size": [2, 2, 2], "blocks": [{"pos": [2, 0, 0], "block": "minecraft:stone"}]},
                 [0, 0, 0], 0, "none")
    with pytest.raises(st.StampError):
        st.stamp({"size": [2, 2, 2]}, [0, 0, 0], 45, "none")


def test_placements_from_plan_toon(tmp_path):
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "hut.json").write_text(json.dumps(
        {"size": [3, 2, 2], "fills": [{"from": [0, 0, 0], "to": [2, 1, 1],
                                       "block": "minecraft:stone"}]}), encoding="utf-8")
    plan = tmp_path / "plan.toon"
    plan.write_text(
        "plan:\n  project: t\n"
        "placements[3]{module,origin,rotation,mirror,phase}:\n"
        "  hut,0 64 0,0,none,2\n  hut,10 64 0,90,x,2\n  hut,1 64 1,0,none,3\n"
        "acceptance[0]{phase,at,expect}:\n", encoding="utf-8")
    rows = st.read_placements(plan, 2)
    assert [r["origin"] for r in rows] == [[0, 64, 0], [10, 64, 0]]
    assert len(st.stamp_all(rows, tmp_path / "modules")["fills"]) == 2
    with pytest.raises(st.StampError):
        st.stamp_all(st.read_placements(plan, None), tmp_path / "modules")



def test_placements_accept_toon_quoted_cells(tmp_path):
    # TOON quotes a cell that starts with "-" (a negative coordinate); the
    # reader must take quoted and unquoted cells alike.
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "hut.json").write_text(json.dumps(
        {"size": [3, 2, 2], "fills": [{"from": [0, 0, 0], "to": [2, 1, 1],
                                       "block": "minecraft:stone"}]}), encoding="utf-8")
    plan = tmp_path / "plan.toon"
    plan.write_text(
        "placements[2]{module,origin,rotation,mirror,phase}:\n"
        '  "hut","-890 64 -153",0,none,2\n'
        '  hut,"-880 64 -153",90,"x",2\n', encoding="utf-8")
    rows = st.read_placements(plan, None)
    assert [r["module"] for r in rows] == ["hut", "hut"]
    assert [r["origin"] for r in rows] == [[-890, 64, -153], [-880, 64, -153]]
    assert rows[1]["mirror"] == "x"
    assert len(st.stamp_all(rows, tmp_path / "modules")["fills"]) == 2


@pytest.mark.parametrize("row", [
    '  hut,"-890 64 -153,0,none,2',   # unterminated quote
    "  hut,1 two 3,0,none,2",          # not a coordinate
    "  hut,1 2,0,none,2",              # two numbers, not three
    "  hut,1 2 3,ninety,none,2",       # rotation is not a number
])
def test_placements_bad_row_is_a_stamp_error(tmp_path, row):
    plan = tmp_path / "plan.toon"
    plan.write_text("placements[1]{module,origin,rotation,mirror,phase}:\n"
                    + row + "\n", encoding="utf-8")
    with pytest.raises(st.StampError):
        st.read_placements(plan, None)

def test_cli_negative_origin(tmp_path):
    module = tmp_path / "m.json"
    module.write_text(json.dumps({"size": [1, 1, 1], "blocks": [
        {"pos": [0, 0, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(STAMP), str(module), "--at=-10,64,-5"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["blocks"][0]["pos"] == [-10, 64, -5]


def test_out_creates_the_parent_folder(tmp_path):
    module = tmp_path / "m.json"
    module.write_text(json.dumps({"size": [1, 1, 1], "blocks": [
        {"pos": [0, 0, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    out = tmp_path / "deep" / "phases" / "01-x.json"
    proc = subprocess.run([sys.executable, str(STAMP), str(module), "--at=0,64,0",
                           "--out", str(out)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["blocks"][0]["pos"] == [0, 64, 0]


TREE = {"name": "t", "size": [3, 4, 3], "kind": "vegetation", "anchor": [1, 0, 1],
        "ground": {"fills": [], "blocks": []},
        "wood": {"fills": [{"from": [1, 0, 1], "to": [1, 2, 1], "block": "minecraft:oak_log[axis=y]"}],
                 "blocks": []},
        "leaves": {"fills": [{"from": [0, 3, 0], "to": [2, 3, 2],
                              "block": "minecraft:oak_leaves[persistent=true]"}],
                   "blocks": [{"pos": [1, 2, 0], "block": "minecraft:oak_leaves[persistent=true]"}]}}
HUT = {"name": "hut", "size": [3, 2, 2],
       "fills": [{"from": [0, 0, 0], "to": [2, 1, 1], "block": "minecraft:stone"}]}


def _write_modules(tmp_path, modules):
    folder = tmp_path / "modules"
    folder.mkdir(exist_ok=True)
    for name, module in modules.items():
        (folder / f"{name}.json").write_text(json.dumps(module), encoding="utf-8")
    return folder


def _row(module, origin, rotation=0, mirror="none", phase=1):
    return {"module": module, "origin": origin, "rotation": rotation, "mirror": mirror,
            "phase": phase}


def test_vegetation_overlap_allowed_and_ordered(tmp_path):
    modules = _write_modules(tmp_path, {"tree": TREE})
    out = st.stamp_all([_row("tree", [0, 64, 0]), _row("tree", [2, 64, 0])], modules)
    assert out["blocks"] == []
    wood = [i for i, f in enumerate(out["fills"]) if f["block"].startswith("minecraft:oak_log")]
    leaves = [i for i, f in enumerate(out["fills"]) if "oak_leaves" in f["block"]]
    assert len(wood) == 2 and len(leaves) == 4
    assert max(wood) < min(leaves)


def test_vegetation_parts_carry_the_air_filter(tmp_path):
    tree = json.loads(json.dumps(TREE))
    tree["ground"] = {"fills": [], "blocks": [{"pos": [0, 0, 0], "block": "minecraft:dirt"},
                                              {"pos": [1, 0, 0], "block": "minecraft:dirt"}]}
    modules = _write_modules(tmp_path, {"tree": tree})
    out = st.stamp_all([_row("tree", [0, 64, 0])], modules)
    assert out["blocks"] == []
    assert out["fills"][0] == {"from": [0, 64, 0], "to": [1, 64, 0], "block": "minecraft:dirt"}
    assert "filter" not in out["fills"][0]
    rest = out["fills"][1:]
    assert rest and all(f["filter"] == "minecraft:air" for f in rest)
    assert rest[0] == {"from": [1, 64, 1], "to": [1, 66, 1], "block": "minecraft:oak_log[axis=y]",
                       "filter": "minecraft:air"}
    assert rest[-1] == {"from": [1, 66, 0], "to": [1, 66, 0],
                        "block": "minecraft:oak_leaves[persistent=true]", "filter": "minecraft:air"}


def test_vegetation_cannot_overlap_a_building(tmp_path):
    modules = _write_modules(tmp_path, {"tree": TREE, "hut": HUT})
    with pytest.raises(st.StampError):
        st.stamp_all([_row("hut", [0, 64, 0]), _row("tree", [2, 64, 0])], modules)
    with pytest.raises(st.StampError):
        st.stamp_all([_row("tree", [2, 64, 0]), _row("hut", [0, 64, 0])], modules)


@pytest.mark.parametrize("rotation,axis", [(90, "z"), (270, "z"), (180, "x")])
def test_vegetation_rotation_turns_log_axis(tmp_path, rotation, axis):
    tree = json.loads(json.dumps(TREE))
    tree["wood"] = {"fills": [{"from": [0, 1, 1], "to": [2, 1, 1], "block": "minecraft:oak_log[axis=x]"}],
                    "blocks": []}
    modules = _write_modules(tmp_path, {"tree": tree})
    out = st.stamp_all([_row("tree", [0, 64, 0], rotation=rotation)], modules)
    log = next(f for f in out["fills"] if "oak_log" in f["block"])
    assert log["block"] == f"minecraft:oak_log[axis={axis}]"


def test_vegetation_mirror_flips_cells(tmp_path):
    tree = json.loads(json.dumps(TREE))
    tree["leaves"]["blocks"] = [{"pos": [0, 2, 0], "block": "minecraft:oak_leaves[persistent=true]"}]
    modules = _write_modules(tmp_path, {"tree": tree})
    out = st.stamp_all([_row("tree", [0, 64, 0], mirror="x")], modules)
    leaf = out["fills"][-1]
    assert leaf["from"] == [2, 66, 0] and leaf["to"] == [2, 66, 0]
    assert leaf["filter"] == "minecraft:air"
    wood = next(f for f in out["fills"] if "oak_log" in f["block"])
    assert wood["from"] == [1, 64, 1] and wood["to"] == [1, 66, 1]


@pytest.mark.parametrize("change", [
    lambda m: m.pop("anchor"),
    lambda m: m.update(anchor=[3, 0, 0]),
    lambda m: m.update(roots={"fills": [], "blocks": []}),
    lambda m: m.update(fills=[]),
])
def test_vegetation_module_needs_anchor_and_parts(change):
    module = json.loads(json.dumps(TREE))
    change(module)
    with pytest.raises(st.StampError):
        st.stamp(module, [0, 64, 0], 0, "none")
