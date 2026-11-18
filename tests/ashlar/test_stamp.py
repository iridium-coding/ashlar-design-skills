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


def test_cli_negative_origin(tmp_path):
    module = tmp_path / "m.json"
    module.write_text(json.dumps({"size": [1, 1, 1], "blocks": [
        {"pos": [0, 0, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(STAMP), str(module), "--at=-10,64,-5"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["blocks"][0]["pos"] == [-10, 64, -5]
