"""The commands runner (place feature, fillbiome), biome probe and biome restore."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_place_mcp import PLACER, calls, config, run  # noqa: E402

_spec = importlib.util.spec_from_file_location("ashlar_place", PLACER)
ap = importlib.util.module_from_spec(_spec)
sys.modules["ashlar_place"] = ap
_spec.loader.exec_module(ap)

BOX = [0, 60, 0, 127, 120, 127]
TREE = "place feature minecraft:oak {} 64 {}"


def commands_file(tmp_path, commands, box=None, kind="features", name="cmds.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"version": 1, "kind": kind, "box": box or BOX,
                                "world": None, "commands": commands}), encoding="utf-8")
    return path


def world_file(tmp_path, **world):
    path = tmp_path / "world.json"
    path.write_text(json.dumps({"ground": 63, **world}), encoding="utf-8")
    return path


def trees(*xs):
    return [TREE.format(x, 8) for x in xs]


def console(tmp_path):
    return [c["arguments"]["command"] for c in calls(tmp_path) if c["name"] == "mc_command"]


def chunk_cells(command):
    """Chunks a forceload add/remove command (block coordinates) covers."""
    parts = command.split()
    nums = [int(p) for p in parts[2:]]
    x1, z1, x2, z2 = nums[0], nums[1], nums[-2], nums[-1]
    return {(cx, cz) for cx in range(x1 >> 4, (x2 >> 4) + 1)
            for cz in range(z1 >> 4, (z2 >> 4) + 1)}


def forceloads(tmp_path, verb):
    out = []
    for command in console(tmp_path):
        plain = command.removeprefix("minecraft:")
        if plain.startswith(f"forceload {verb} "):
            out.append(plain)
    return out


def report_of(proc):
    return json.loads(proc.stdout)


# ------------------------------------------------------------------ offline

@pytest.mark.parametrize("command", [
    "setblock 1 64 1 minecraft:stone",
    "place feature minecraft:oak 1 64",              # short
    "place feature oak 1 64 1",                      # no namespace
    "fillbiome 0 64 0 15 64 15",                     # no biome
    "fillbiome 0 64 0 15 192 15 minecraft:plains",   # 16 x 129 x 16
    "place feature minecraft:oak 500 64 1",          # outside the box
    "place feature minecraft:oak 1 999 1",           # bad y
    "/place feature minecraft:oak 1 64 1",           # leading slash
    "minecraft:place feature minecraft:oak 1 64 1",  # prefix is the runner's job
])
def test_load_commands_accepts_only_the_two_forms(tmp_path, command):
    path = commands_file(tmp_path, [command])
    with pytest.raises(ap.PlacerError) as err:
        ap.load_commands(path, ap.Limits())
    assert err.value.code == ap.EXIT_INPUT
    proc = run("commands", str(path), "--check", "--config", str(config(tmp_path)))
    assert proc.returncode == 2 and calls(tmp_path) == []


def test_load_commands_refuses_a_fillbiome_over_the_volume_limit(tmp_path):
    box = [0, 0, 0, 15, 250, 15]
    ok = commands_file(tmp_path, ["fillbiome 0 0 0 15 127 15 minecraft:plains"], box=box)
    ap.load_commands(ok, ap.Limits())                       # 16 x 128 x 16 = 32,768
    big = commands_file(tmp_path, ["fillbiome 0 0 0 15 128 15 minecraft:plains"], box=box,
                        name="big.json")                    # 16 x 129 x 16
    with pytest.raises(ap.PlacerError) as err:
        ap.load_commands(big, ap.Limits())
    assert err.value.code == ap.EXIT_INPUT
    ap.load_commands(big, ap.Limits(), max_biome_blocks=40_000)


def test_load_commands_accepts_valid_commands_and_check_is_offline(tmp_path):
    path = commands_file(tmp_path, ["place feature minecraft:oak 1 64 1",
                                    "fillbiome 0 64 0 15 120 15 minecraft:plains"])
    data = ap.load_commands(path, ap.Limits())
    assert data["box"] == tuple(BOX) and len(data["commands"]) == 2
    proc = run("commands", str(path), "--check", "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["forms"] == {"fillbiome": 1, "place feature": 1}
    assert calls(tmp_path) == []


def test_command_chunks_and_forceload_tiles_across_zero():
    assert ap.command_chunks("place feature minecraft:oak -1 64 -1") == {
        (cx, cz) for cx in (-2, -1, 0) for cz in (-2, -1, 0)}
    assert ap.command_chunks("fillbiome -16 0 0 15 10 15 minecraft:plains") == {(-1, 0), (0, 0)}
    tiles = ap.forceload_tiles({(cx, cz) for cx in range(-20, 20) for cz in range(-3, 3)})
    assert all((t[2] - t[0] + 1) * (t[3] - t[1] + 1) <= 256 for t in tiles)
    assert {(cx, cz) for t in tiles for cx in range(t[0], t[2] + 1) for cz in range(t[1], t[3] + 1)} \
        >= {(cx, cz) for cx in range(-20, 20) for cz in range(-3, 3)}


def test_parse_forceload_query_real_replies():
    dim = "minecraft:overworld"
    assert ap.parse_forceload_query(f"No force loaded chunks were found in {dim}") == set()
    assert ap.parse_forceload_query(
        f"A force loaded chunk was found in {dim} at: [3, -4]") == {(3, -4)}
    assert ap.parse_forceload_query(
        f"5 force loaded chunks were found in {dim} at: [1, 2], [3, 4], [-1, -2]"
    ) == {(1, 2), (3, 4), (-1, -2)}
    with pytest.raises(ap.PlacerError) as err:
        ap.parse_forceload_query("There are 2 force loaded chunks")
    assert err.value.code == ap.EXIT_SERVER


# ------------------------------------------------------------------- runner

def test_runner_prefixes_and_pairs_forceloads(tmp_path):
    world = world_file(tmp_path)
    path = commands_file(tmp_path, trees(40, 56))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 0, proc.stderr
    log = calls(tmp_path)
    assert [c["name"] for c in log] == ["mc_command", "mc_players", "mc_command",
                                        "mc_command", "mc_command", "mc_command"]
    texts = console(tmp_path)
    assert texts[0] == "minecraft:forceload query"
    assert texts[1].startswith("minecraft:forceload add ")
    assert texts[2] == "minecraft:place feature minecraft:oak 40 64 8"
    assert texts[3] == "minecraft:place feature minecraft:oak 56 64 8"
    assert texts[4] == texts[1].replace(" add ", " remove ")
    assert json.loads(world.read_text(encoding="utf-8")).get("forceloaded") == []
    report = report_of(proc)
    assert report["counts"] == {"place feature": 2}
    assert report["features"] == {"minecraft:oak": 2}
    assert report["forceloads_added"] == report["forceloads_removed"] and report["failed"] == []


def test_runner_skips_already_loaded_chunks(tmp_path):
    world = world_file(tmp_path, forceloaded=[[0, 0]])
    path = commands_file(tmp_path, trees(8))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 0, proc.stderr
    adds, removes = forceloads(tmp_path, "add"), forceloads(tmp_path, "remove")
    # chunks -1..1 around the tree minus the loaded (0, 0): eight single-chunk adds
    assert len(adds) == 8 and len(removes) == 8
    assert all(len(chunk_cells(c)) == 1 and (0, 0) not in chunk_cells(c)
               for c in adds + removes)
    assert sorted(a.replace(" add ", " remove ") for a in adds) == sorted(removes)
    assert json.loads(world.read_text(encoding="utf-8"))["forceloaded"] == [[0, 0]]


def test_runner_records_failed_tree_and_continues(tmp_path):
    path = commands_file(tmp_path, trees(40, 41, 42))
    proc = run("commands", str(path), "--config", str(config(tmp_path, FAKE_FAIL_FEATURE="2")))
    assert proc.returncode == 6, proc.stderr
    assert len([c for c in console(tmp_path) if "place feature" in c]) == 3
    report = report_of(proc)
    assert [f["index"] for f in report["failed"]] == [2]
    assert report["failed"][0]["reply"].startswith("Failed to place feature")
    assert report["features"] == {"minecraft:oak": 2}
    assert report["forceloads_added"] == report["forceloads_removed"]


def test_runner_unknown_feature_and_unchanged_biome_replies(tmp_path):
    world = world_file(tmp_path, biomes={"0,0": "minecraft:plains"})
    path = commands_file(tmp_path, ["place feature minecraft:foo 8 64 8",
                                    "fillbiome 0 64 0 15 70 15 minecraft:plains"])
    proc = run("commands", str(path), "--config", str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 6, proc.stderr
    report = report_of(proc)
    assert [f["index"] for f in report["failed"]] == [1]      # "There is no feature"
    assert report["counts"] == {"place feature": 1, "fillbiome": 1}  # "No biome entries" is ok


def test_runner_server_error_still_removes_forceload_and_resumes(tmp_path):
    world = world_file(tmp_path)
    path = commands_file(tmp_path, trees(40, 41, 42, 43))
    progress = tmp_path / "progress.jsonl"
    proc = run("commands", str(path), "--progress", str(progress), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world), FAKE_ERROR_COMMAND="3")))
    assert proc.returncode == 5, proc.stderr
    assert console(tmp_path)[-1].startswith("minecraft:forceload remove ")
    assert json.loads(world.read_text(encoding="utf-8"))["forceloaded"] == []
    assert [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines()] == [
        json.loads(header_of(path)), {"index": 1, "ok": True}, {"index": 2, "ok": True}]
    before = len(console(tmp_path))
    proc = run("commands", str(path), "--progress", str(progress), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 0, proc.stderr
    placed = [c for c in console(tmp_path)[before:] if "place feature" in c]
    assert placed == [f"minecraft:place feature minecraft:oak {x} 64 8" for x in (42, 43)]
    assert report_of(proc)["skipped"] == 2
    assert len(progress.read_text(encoding="utf-8").splitlines()) == 5  # header + 4


def header_of(path):
    import hashlib
    return json.dumps({"commands_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def test_runner_resume_skips_recorded_and_keeps_earlier_failures(tmp_path):
    path = commands_file(tmp_path, trees(40, 41))
    progress = tmp_path / "progress.jsonl"
    progress.write_text(header_of(path) + '\n{"index": 1, "ok": false}\n', encoding="utf-8")
    proc = run("commands", str(path), "--progress", str(progress), "--config",
               str(config(tmp_path)))
    assert proc.returncode == 6, proc.stderr
    assert [c for c in console(tmp_path) if "place feature" in c] == [
        "minecraft:place feature minecraft:oak 41 64 8"]
    failed = report_of(proc)["failed"]
    assert [f["index"] for f in failed] == [1] and failed[0]["earlier_run"] is True


def test_runner_writes_a_header_and_refuses_a_foreign_progress_file(tmp_path):
    path = commands_file(tmp_path, trees(40))
    progress = tmp_path / "progress.jsonl"
    proc = run("commands", str(path), "--progress", str(progress), "--config",
               str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    lines = progress.read_text(encoding="utf-8").splitlines()
    assert lines[0] == header_of(path) and json.loads(lines[1]) == {"index": 1, "ok": True}
    other = commands_file(tmp_path, trees(50), name="other.json")
    before = len(calls(tmp_path))
    for text in (lines[0] + "\n", '{"index": 1, "ok": true}\n',
                 json.dumps({"commands_sha256": "0" * 64}) + "\n"):
        progress.write_text(text, encoding="utf-8")
        proc = run("commands", str(other), "--progress", str(progress), "--config",
                   str(config(tmp_path)))
        assert proc.returncode == 2, proc.stderr
    assert len(calls(tmp_path)) == before            # refused before any server contact


def test_runner_stops_before_a_tile_with_a_player(tmp_path):
    world = world_file(tmp_path)
    box = [0, 60, 0, 10100, 100, 100]
    path = commands_file(tmp_path, [TREE.format(8, 8), TREE.format(10008, 8)], box=box)
    player = "Alex  world  pos x=10005 y=65 z=5  facing north (block in front: 10005,65,4)  survival"
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world), FAKE_PLAYERS=player)))
    assert proc.returncode == 4, proc.stderr
    placed = [c for c in console(tmp_path) if "place feature" in c]
    assert placed == ["minecraft:place feature minecraft:oak 8 64 8"]
    assert len(forceloads(tmp_path, "add")) == len(forceloads(tmp_path, "remove")) == 1
    assert json.loads(world.read_text(encoding="utf-8"))["forceloaded"] == []
    assert report_of(proc)["tiles_done"] == 1


def test_runner_wraps_execute_in_for_another_dimension(tmp_path):
    path = commands_file(tmp_path, ["place feature minecraft:oak 8 64 8"])
    proc = run("commands", str(path), "--dimension", "minecraft:the_nether", "--config",
               str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    wrap = "minecraft:execute in minecraft:the_nether run "
    texts = console(tmp_path)
    assert texts[0] == wrap + "forceload query"
    assert texts[1].startswith(wrap + "forceload add ")
    assert texts[2] == wrap + "place feature minecraft:oak 8 64 8"
    assert texts[3] == texts[1].replace(" add ", " remove ")
    bad = run("commands", str(path), "--dimension", "x run kill @e", "--config",
              str(config(tmp_path)))
    assert bad.returncode == 2


def test_runner_add_not_confirmed_stops_and_is_not_removed(tmp_path):
    world = world_file(tmp_path)
    path = commands_file(tmp_path, trees(40))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world), FAKE_FAIL_ADD="1")))
    assert proc.returncode == 5, proc.stderr
    assert forceloads(tmp_path, "remove") == []
    assert not [c for c in console(tmp_path) if "place feature" in c]


def test_runner_later_add_fails_earlier_adds_are_still_removed(tmp_path):
    world = world_file(tmp_path, forceloaded=[[0, 0]])     # forces one add per chunk
    path = commands_file(tmp_path, trees(8))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_WORLD=str(world), FAKE_FAIL_ADD="3")))
    assert proc.returncode == 5, proc.stderr
    adds, removes = forceloads(tmp_path, "add"), forceloads(tmp_path, "remove")
    assert len(adds) == 3 and len(removes) == 2
    assert sorted(removes) == sorted(a.replace(" add ", " remove ") for a in adds[:2])
    assert json.loads(world.read_text(encoding="utf-8"))["forceloaded"] == [[0, 0]]


def test_runner_reports_a_failed_removal_loudly(tmp_path):
    path = commands_file(tmp_path, trees(40))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_FAIL_REMOVE="1")))
    assert proc.returncode == 5
    report = report_of(proc)
    assert report["forceload_left"] == report["forceloads_added"] != []
    assert "FORCE-LOAD LEFT" in proc.stderr


# ------------------------------------------------------------------- probe

def probe_inputs(tmp_path):
    surface = [None] * 48
    ground = [None] * 48
    surface[8] = 70
    ground[24] = 66
    heights = tmp_path / "heights.json"
    heights.write_text(json.dumps({"version": 1, "world": None, "origin": [0, 8],
                                   "size": [48, 1], "ground": ground, "surface": surface,
                                   "top": surface}), encoding="utf-8")
    biomes = tmp_path / "biomes.json"
    biomes.write_text(json.dumps({"ids": ["minecraft:plains", "minecraft:desert",
                                          "minecraft:forest"]}), encoding="utf-8")
    return heights, biomes


def test_biome_probe_orders_candidates_and_marks_unknown(tmp_path):
    heights, biomes = probe_inputs(tmp_path)
    world = world_file(tmp_path, biomes={"0,0": "minecraft:forest", "1,0": "minecraft:forest",
                                         "2,0": "minecraft:meadow"})
    out = tmp_path / "probe.json"
    proc = run("biome-probe", "--box", "0", "60", "0", "47", "80", "15", "--heights", str(heights),
               "--biomes", str(biomes), "--candidates", "minecraft:taiga", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 0, proc.stderr
    f5 = json.loads(out.read_text(encoding="utf-8"))
    assert f5 == {"version": 1, "world": None, "box": [0, 60, 0, 47, 80, 15],
                  "chunks": {"0,0": "minecraft:forest", "1,0": "minecraft:forest",
                             "2,0": "unknown"}}
    tests = [c.removeprefix("minecraft:execute if biome ") for c in console(tmp_path)
             if "execute if biome" in c]
    assert tests == (
        [f"8 70 8 minecraft:{b}" for b in ("taiga", "plains", "desert", "forest")]
        + ["24 66 8 minecraft:forest"]                       # previous chunk's biome first
        + [f"40 60 8 minecraft:{b}" for b in ("forest", "taiga", "plains", "desert")])
    assert len(forceloads(tmp_path, "add")) == len(forceloads(tmp_path, "remove")) == 1
    assert json.loads(world.read_text(encoding="utf-8"))["forceloaded"] == []


def test_biome_probe_accepts_a_plain_list_and_checks_players(tmp_path):
    heights, biomes = probe_inputs(tmp_path)
    biomes.write_text(json.dumps(["minecraft:plains"]), encoding="utf-8")
    player = "Alex  world  pos x=5 y=65 z=5  facing north (block in front: 5,65,4)  survival"
    proc = run("biome-probe", "--box", "0", "60", "0", "15", "80", "15", "--heights", str(heights),
               "--biomes", str(biomes), "--out", str(tmp_path / "p.json"),
               "--config", str(config(tmp_path, FAKE_PLAYERS=player)))
    assert proc.returncode == 4 and not (tmp_path / "p.json").exists()
    assert forceloads(tmp_path, "add") == []


# ----------------------------------------------------------------- restore

def test_biome_restore_tiles_chunks_within_limit(tmp_path):
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"version": 1, "world": "world", "box": [0, 0, 0, 31, 299, 15],
                                 "chunks": {"0,0": "minecraft:plains", "1,0": "unknown"}}),
                     encoding="utf-8")
    out = tmp_path / "restore.json"
    proc = run("biome-restore", str(probe), "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    f3 = json.loads(out.read_text(encoding="utf-8"))
    assert f3["kind"] == "biomes" and f3["box"] == [0, 0, 0, 31, 299, 15]
    assert f3["world"] == "world" and f3["skipped"] == [[1, 0]]
    assert "[1, 0]" in proc.stdout
    assert f3["commands"] == [
        "fillbiome 0 0 0 15 127 15 minecraft:plains",
        "fillbiome 0 128 0 15 255 15 minecraft:plains",
        "fillbiome 0 256 0 15 299 15 minecraft:plains"]
    limits = ap.Limits()
    ap.load_commands(out, limits)  # the runner accepts what restore writes
    for command in f3["commands"]:
        _, g = ap.parse_command(command)
        assert (int(g["x2"]) - int(g["x1"]) + 1) * (int(g["y2"]) - int(g["y1"]) + 1) \
            * (int(g["z2"]) - int(g["z1"]) + 1) <= 32_768
        assert int(g["x1"]) % 16 == 0 and int(g["x2"]) % 16 == 15


# ------------------------------------------------- alignment and redaction

@pytest.mark.parametrize("box", [
    ["1", "60", "0", "47", "80", "15"], ["0", "60", "0", "46", "80", "15"],
    ["0", "60", "3", "47", "80", "15"], ["0", "60", "0", "47", "80", "14"]])
def test_biome_probe_refuses_an_unaligned_box_before_any_server_call(tmp_path, box):
    heights, biomes = probe_inputs(tmp_path)
    proc = run("biome-probe", "--box", *box, "--heights", str(heights), "--biomes", str(biomes),
               "--out", str(tmp_path / "p.json"), "--config", str(config(tmp_path)))
    assert proc.returncode == 2 and calls(tmp_path) == []


@pytest.mark.parametrize("box, chunks", [
    ([1, 0, 0, 31, 99, 15], {"0,0": "minecraft:plains"}),            # unaligned
    ([16, 0, 0, 0, 99, 15], {"0,0": "minecraft:plains"}),             # unordered
    ([0, 0, 0, 15, 99, 15], {"1,0": "minecraft:plains"}),             # chunk outside box
    ([0, 0, 0, 15, 99, 15], {"0,-1": "minecraft:plains"}),
])
def test_biome_restore_refuses_a_bad_probe(tmp_path, box, chunks):
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"version": 1, "world": None, "box": box, "chunks": chunks}),
                     encoding="utf-8")
    proc = run("biome-restore", str(probe), "--out", str(tmp_path / "r.json"))
    assert proc.returncode == 2 and not (tmp_path / "r.json").exists()


def test_a_secret_across_the_truncation_point_is_redacted(tmp_path):
    path = commands_file(tmp_path, trees(40))
    proc = run("commands", str(path), "--config",
               str(config(tmp_path, FAKE_QUERY_ECHO_SECRET="1")))
    assert proc.returncode == 5
    assert "tok-" not in proc.stderr and "SECRET" not in proc.stderr
    assert "x" * 100 in proc.stderr and "***" in proc.stderr
