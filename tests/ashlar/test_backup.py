"""Column backups (F1), exact restore and `place --backup` against the fake server."""
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_place_mcp import PLACER, calls, config, run  # noqa: E402

_spec = importlib.util.spec_from_file_location("ashlar_place", PLACER)
ap = importlib.util.module_from_spec(_spec)
sys.modules["ashlar_place"] = ap
_spec.loader.exec_module(ap)

BOX = ["0", "60", "0", "3", "70", "3"]
INSIDE = "Alex  world  pos x=1 y=65 z=1  facing north (block in front: 1,65,0)  survival"


def world_file(tmp_path, cells=None):
    path = tmp_path / "world.json"
    path.write_text(json.dumps({"ground": 63, "cells": cells or {"2,61,2": "minecraft:gold_block"}}),
                    encoding="utf-8")
    return path


def phase_file(tmp_path):
    path = tmp_path / "phase.json"
    path.write_text(json.dumps({
        "fills": [{"from": [0, 64, 0], "to": [3, 66, 3], "block": "minecraft:oak_planks"},
                  {"from": [1, 60, 1], "to": [2, 62, 2], "block": "minecraft:water[level=0]"},
                  {"from": [0, 70, 0], "to": [3, 70, 3], "block": "minecraft:glass"}],
        "blocks": [{"pos": [1, 67, 1], "block": "minecraft:torch"}]}), encoding="utf-8")
    return path


def backup(tmp_path, out, **env):
    env.setdefault("FAKE_WORLD", str(world_file(tmp_path)) if not (tmp_path / "world.json").exists()
                   else str(tmp_path / "world.json"))
    return run("backup", "--box", *BOX, "--out", str(out),
               "--config", str(config(tmp_path, **env)))


def read(out):
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads(gzip.decompress((out / "columns.json.gz").read_bytes()))
    return manifest, payload


def test_parse_columns_handles_negative_y_and_states():
    text = ("Region (default) x=[5..5] y=[-64..10] z=[-3..-3] …\n"
            "5,-3: -64--1 deepslate | 0-0 oak_stairs[facing=north,half=bottom] | 1-10 air")
    assert ap.parse_columns(text) == {(5, -3): [
        (-64, -1, "minecraft:deepslate"),
        (0, 0, "minecraft:oak_stairs[facing=north,half=bottom]"),
        (1, 10, "minecraft:air")]}


def test_column_tiles_respect_limits_and_cover_box():
    box = (-40, 0, -40, 39, 299, 39)
    tiles = ap.column_tiles(box)
    seen = Counter((x, z) for t in tiles for x in range(t[0], t[3] + 1)
                   for z in range(t[2], t[5] + 1))
    assert set(seen.values()) == {1} and len(seen) == 80 * 80
    assert all((t[3] - t[0] + 1) * (t[5] - t[2] + 1) <= 1024 for t in tiles)
    assert all(ap.volume(t) <= 200_000 for t in tiles)


def test_backup_writes_manifest_and_columns(tmp_path):
    out = tmp_path / "bk"
    proc = backup(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    manifest, payload = read(out)
    assert manifest["complete"] is True and manifest["columns"] == 16
    assert manifest["box"] == [0, 60, 0, 3, 70, 3] and manifest["plugin"] == "0.4.9"
    assert manifest["sha256"] == hashlib.sha256((out / "columns.json.gz").read_bytes()).hexdigest()
    assert len(payload["columns"]) == 16 and payload["version"] == 1
    assert payload["columns"]["2,2"] == [[60, 60, "minecraft:stone"],
                                         [61, 61, "minecraft:gold_block"],
                                         [62, 62, "minecraft:stone"],
                                         [63, 70, "minecraft:air"]]
    assert payload["columns"]["0,0"] == [[60, 62, "minecraft:stone"], [63, 70, "minecraft:air"]]
    assert sorted(p.name for p in out.iterdir()) == ["columns.json.gz", "manifest.json"]
    assert (out / "manifest.json").read_text(encoding="utf-8").endswith("}\n")


def test_backup_bytes_are_deterministic():
    payload = {"version": 1, "world": None, "box": [0, 0, 0, 0, 0, 0],
               "columns": {"0,0": [[0, 0, "minecraft:air"]]}}
    blob = ap.encode_columns(payload)
    assert blob == gzip.compress(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                                 .encode("utf-8"), mtime=0)


def test_backup_refuses_incomplete_read(tmp_path):
    out = tmp_path / "bk"
    proc = backup(tmp_path, out, FAKE_INSPECT_SKIP="2,2")
    assert proc.returncode == 3, proc.stderr
    assert not out.exists() or list(out.iterdir()) == []


def test_backup_refuses_when_restore_would_not_validate(tmp_path):
    out = tmp_path / "bk"
    proc = run("backup", "--box", "0", "300", "0", "1", "330", "1", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))))
    assert proc.returncode == 2 and not out.exists()


def test_load_backup_rejects_bad_checksum(tmp_path):
    out = tmp_path / "bk"
    assert backup(tmp_path, out).returncode == 0
    blob = bytearray((out / "columns.json.gz").read_bytes())
    blob[-1] ^= 0xFF
    (out / "columns.json.gz").write_bytes(bytes(blob))
    with pytest.raises(ap.PlacerError) as caught:
        ap.load_backup(out)
    assert caught.value.code == 2


def test_load_backup_rejects_incomplete_runs(tmp_path):
    out = tmp_path / "bk"
    assert backup(tmp_path, out).returncode == 0
    manifest, payload = read(out)
    payload["columns"]["0,0"] = [[60, 62, "minecraft:stone"]]
    blob = ap.encode_columns(payload)
    (out / "columns.json.gz").write_bytes(blob)
    manifest["sha256"] = hashlib.sha256(blob).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ap.PlacerError) as caught:
        ap.load_backup(out)
    assert caught.value.code == 2


def test_check_complete_negative_coordinates():
    box = (-2, -64, -2, -1, 5, -1)
    full = {(x, z): [(-64, 5, "minecraft:stone")] for x in (-2, -1) for z in (-2, -1)}
    ap.check_complete(full, box)
    del full[(-1, -1)]
    with pytest.raises(ap.PlacerError) as caught:
        ap.check_complete(full, box)
    assert caught.value.code == 3
    gap = {(0, 0): [(0, 1, "minecraft:stone"), (3, 4, "minecraft:air")]}
    with pytest.raises(ap.PlacerError):
        ap.check_complete(gap, (0, 0, 0, 0, 4, 0))


def test_restore_build_merges_neighbouring_columns():
    cols = {(x, 0): [(60, 62, "minecraft:stone"), (63, 70, "minecraft:air")] for x in (-1, 0, 1)}
    args = ap.restore_build(cols, "w")
    assert args["world"] == "w" and len(args["fills"]) == 2
    assert {"from": [-1, 60, 0], "to": [1, 62, 0], "block": "minecraft:stone"} in args["fills"]


def test_place_backup_then_restore_round_trip(tmp_path):
    out_a, out_b, out_c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    world = world_file(tmp_path)
    cfg = config(tmp_path, FAKE_WORLD=str(world))
    assert run("backup", "--box", *BOX, "--out", str(out_a), "--config", str(cfg)).returncode == 0
    proc = run("place", str(phase_file(tmp_path)), "--backup", str(out_b), "--config", str(cfg))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["backup"] == str(out_b)
    assert run("backup", "--box", *BOX, "--out", str(out_c), "--config", str(cfg)).returncode == 0
    assert read(out_c)[1]["columns"] != read(out_a)[1]["columns"]
    proc = run("restore", str(out_b), "--config", str(cfg))
    assert proc.returncode == 0, proc.stderr
    out_d = tmp_path / "d"
    assert run("backup", "--box", *BOX, "--out", str(out_d), "--config", str(cfg)).returncode == 0
    assert read(out_d)[1]["columns"] == read(out_a)[1]["columns"]
    assert read(out_b)[1]["columns"] == read(out_a)[1]["columns"]


def test_place_backup_reads_before_any_build(tmp_path):
    cfg = config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))
    proc = run("place", str(phase_file(tmp_path)), "--backup", str(tmp_path / "bk"),
               "--config", str(cfg))
    assert proc.returncode == 0, proc.stderr
    names = [c["name"] for c in calls(tmp_path)]
    assert names[:2] == ["mc_players", "mc_status"]
    first_build = names.index("mc_build")
    assert set(names[2:first_build]) == {"mc_inspect"} and first_build > 2
    assert set(names[first_build:]) == {"mc_build"}
    assert "mc_snapshot" not in names


def test_place_backup_refuses_to_overwrite_a_backup(tmp_path):
    cfg = config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))
    out = tmp_path / "bk"
    assert run("place", str(phase_file(tmp_path)), "--backup", str(out),
               "--config", str(cfg)).returncode == 0
    before = len(calls(tmp_path))
    proc = run("place", str(phase_file(tmp_path)), "--backup", str(out), "--config", str(cfg))
    assert proc.returncode == 3
    assert not [c for c in calls(tmp_path)[before:] if c["name"] == "mc_build"]


def test_restore_build_uses_static_liquids_and_no_connect():
    args = ap.restore_build({(0, 0): [(60, 62, "minecraft:water[level=0]"),
                                      (63, 70, "minecraft:air")]}, None)
    assert args["liquids"] == "static" and args["connect"] is False
    assert "world" not in args


def test_restore_refuses_when_player_inside(tmp_path):
    cfg = config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))
    out = tmp_path / "bk"
    assert run("backup", "--box", *BOX, "--out", str(out), "--config", str(cfg)).returncode == 0
    proc = run("restore", str(out), "--config", str(config(
        tmp_path, FAKE_WORLD=str(tmp_path / "world.json"), FAKE_PLAYERS=INSIDE)))
    assert proc.returncode == 4
    assert not [c for c in calls(tmp_path) if c["name"] == "mc_build"]


def test_place_backup_negative_coordinates(tmp_path):
    path = tmp_path / "neg.json"
    path.write_text(json.dumps({"fills": [{"from": [-3, 64, -3], "to": [-1, 65, -1],
                                           "block": "minecraft:stone_bricks"}]}), encoding="utf-8")
    cfg = config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))
    out = tmp_path / "bk"
    assert run("place", str(path), "--backup", str(out), "--config", str(cfg)).returncode == 0
    manifest, payload = read(out)
    assert manifest["box"] == [-3, 64, -3, -1, 65, -1] and "-3,-3" in payload["columns"]
