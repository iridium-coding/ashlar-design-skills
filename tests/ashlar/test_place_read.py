"""ashlar_place.py read: shared column reader and the read subcommand."""
import json

import pytest

from ashlar_place import EXIT_SERVER, PlacerError, column_tiles, parse_columns, volume
from test_place_mcp import assert_no_secrets, calls, config, run


def _disjoint(a, b):
    return any(a[i] > b[i + 3] or b[i] > a[i + 3] for i in range(3))


def test_column_tiles_respects_both_caps():
    box = (0, -64, 0, 99, 319, 99)
    tiles = column_tiles(box)
    assert sum(volume(t) for t in tiles) == volume(box)
    assert all(_disjoint(a, b) for i, a in enumerate(tiles) for b in tiles[i + 1:])
    for t in tiles:
        assert (t[3] - t[0] + 1) * (t[5] - t[2] + 1) <= 1024
        assert volume(t) <= 200_000
        assert (t[1], t[4]) == (-64, 319)


def test_column_tiles_small_box_is_one_tile():
    assert column_tiles((0, 64, 0, 1, 65, 1)) == [(0, 64, 0, 1, 65, 1)]


def test_column_tiles_splits_a_long_thin_strip_in_z():
    box = (0, -64, 0, 0, 319, 1999)
    tiles = column_tiles(box)
    assert sum(volume(t) for t in tiles) == volume(box)
    assert all(volume(t) <= 200_000 for t in tiles)
    assert all(_disjoint(a, b) for i, a in enumerate(tiles) for b in tiles[i + 1:])


def test_parse_columns_runs_and_namespace():
    text = ("Region (default) x=[0..0] y=[62..70] z=[0..0], runs bottom to top:\n"
            "0,0: 62 water[level=0] | 63-70 air")
    assert parse_columns(text) == {(0, 0): [(62, 62, "minecraft:water[level=0]"),
                                            (63, 70, "minecraft:air")]}


def test_parse_columns_negative_coordinates_and_ys():
    text = "-3,-5: -64--62 bedrock | -61-10 minecraft:stone"
    assert parse_columns(text) == {(-3, -5): [(-64, -62, "minecraft:bedrock"),
                                              (-61, 10, "minecraft:stone")]}


def test_parse_columns_keeps_states_with_commas():
    text = "1,2: 65 redstone_wire[east=side,north=none,power=0,south=none,west=side]"
    assert parse_columns(text)[(1, 2)][0][2] == (
        "minecraft:redstone_wire[east=side,north=none,power=0,south=none,west=side]")


def test_parse_columns_bad_run_raises_server_error():
    with pytest.raises(PlacerError) as info:
        parse_columns("0,0: nonsense")
    assert info.value.code == EXIT_SERVER


def test_read_writes_every_cell(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "1", "65", "1", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_INSPECT_BOTTOM="redstone_wire[power=3]")))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["world"] is None
    assert data["from"] == [0, 64, 0] and data["to"] == [1, 65, 1]
    assert len(data["cells"]) == 8
    assert data["cells"]["0,64,0"] == "minecraft:redstone_wire[power=3]"
    assert data["cells"]["1,65,1"] == "minecraft:air"
    made = calls(tmp_path)
    assert [c["name"] for c in made] == ["mc_inspect"]
    assert made[0]["arguments"] == {"from": [0, 64, 0], "to": [1, 65, 1],
                                    "format": "columns"}
    assert_no_secrets(proc)


def test_read_passes_world(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "0", "64", "0", "--out", str(out),
               "--world", "nether", "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert calls(tmp_path)[0]["arguments"]["world"] == "nether"
    assert json.loads(out.read_text(encoding="utf-8"))["world"] == "nether"


def test_read_tiles_large_box(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "39", "64", "39", "--out", str(out),
               "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert len([c for c in calls(tmp_path) if c["name"] == "mc_inspect"]) == 2
    assert len(json.loads(out.read_text(encoding="utf-8"))["cells"]) == 1600


def test_read_negative_coordinates_cli(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "-5", "64", "-5", "-4", "64", "-4", "--out", str(out),
               "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert len(json.loads(out.read_text(encoding="utf-8"))["cells"]) == 4


def test_read_server_error_exits_5_and_writes_nothing(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "1", "65", "1", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_FAIL_INSPECT="1")))
    assert proc.returncode == 5
    assert not out.exists()
    assert_no_secrets(proc)


def test_read_rejects_y_outside_world(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "400", "0", "1", "401", "1", "--out", str(out),
               "--config", str(config(tmp_path)))
    assert proc.returncode == 2
    assert not out.exists()


def test_read_parse_error_is_redacted_and_writes_nothing(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "1", "65", "1", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_INSPECT_BOTTOM="stone tok-SECRET-123")))
    assert proc.returncode == 5
    assert not out.exists()
    assert "cannot parse" in proc.stderr
    assert_no_secrets(proc)


def test_read_incomplete_reply_exits_5_and_writes_nothing(tmp_path):
    out = tmp_path / "r.json"
    proc = run("read", "0", "64", "0", "1", "65", "1", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_INSPECT_SKIP="1,1")))
    assert proc.returncode == 5
    assert "of 8 cells" in proc.stderr
    assert not out.exists()
    assert_no_secrets(proc)
