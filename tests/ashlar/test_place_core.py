"""Offline tests for ashlar_place.py."""
import json

import pytest

import ashlar_place as ap
import stamp as st


def test_expand_variables():
    assert ap.expand("${A}-${B:-dflt}-${C}", {"A": "1"}) == "1-dflt-"


def test_find_server_order(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    (home / ".codex").mkdir(parents=True)
    cwd.mkdir()
    (home / ".codex" / "config.toml").write_text(
        '[mcp_servers.ashlar]\ncommand = "npx"\nargs = ["-y", "ashlar-mcp", "--stdio"]\n'
        '[mcp_servers.ashlar.env]\nMC_PLUGIN_URL = "ws://198.51.100.7:8159"\n',
        encoding="utf-8")
    entry = ap.find_server("ashlar", None, cwd, home, {})
    assert entry.command == "npx" and entry.args == ["-y", "ashlar-mcp", "--stdio"]
    assert entry.env == {"MC_PLUGIN_URL": "ws://198.51.100.7:8159"}
    assert entry.source.endswith("config.toml")
    (cwd / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"ashlar": {"command": "node", "args": ["mcp.js"]}}}), encoding="utf-8")
    assert ap.find_server("ashlar", None, cwd, home, {}).command == "node"
    (home / ".claude.json").write_text(json.dumps({"projects": {str(cwd): {
        "mcpServers": {"ashlar": {"type": "stdio", "command": "proj-cmd"}}}}}), encoding="utf-8")
    assert ap.find_server("ashlar", None, cwd, home, {}).command == "proj-cmd"
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": "${CMD:-fallback}", "env": {"T": "${TOKEN}"}}}}),
        encoding="utf-8")
    entry = ap.find_server("ashlar", None, cwd, home, {"TOKEN": "abc"})
    assert entry.command == "fallback" and entry.env == {"T": "abc"}


def test_find_server_errors(tmp_path):
    with pytest.raises(ap.PlacerError) as err:
        ap.find_server("ashlar", None, tmp_path, tmp_path, {})
    assert err.value.code == ap.EXIT_INPUT
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"mcpServers": {"ashlar": {"type": "http", "url": "https://x"}}}),
                      encoding="utf-8")
    with pytest.raises(ap.PlacerError) as err:
        ap.find_server("ashlar", str(config), tmp_path, tmp_path, {})
    assert "not a stdio server" in str(err.value)


def test_redact_hides_secrets_and_urls():
    out = ap.redact("connecting to ws://203.0.113.9:8159 token=tok-SECRET-123",
                    ["tok-SECRET-123", "ws://203.0.113.9:8159"])
    assert "203.0.113.9" not in out and "tok-SECRET-123" not in out and "***" in out


def test_load_build_rules(tmp_path):
    limits = ap.Limits()

    def write(obj):
        path = tmp_path / "b.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    ok = ap.load_build(write([{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}]),
                       limits)
    assert ok["fills"][0]["block"] == "minecraft:stone" and ok["blocks"] == []
    bad = [
        {"text": [{"text": "HI", "pos": [0, 64, 0], "block": "minecraft:stone"}]},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}], "snapshot": True},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}], "extra": 1},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "stone"}]},
        {"fills": [{"from": [0, 400, 0], "to": [1, 64, 1], "block": "minecraft:stone"}]},
        {"blocks": [{"pos": [0, True, 0], "block": "minecraft:stone"}]},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone", "mode": "spiral"}]},
        {"fills": [], "blocks": []},
    ]
    for obj in bad:
        with pytest.raises(ap.PlacerError) as err:
            ap.load_build(write(obj), limits)
        assert err.value.code == ap.EXIT_INPUT, obj


def test_chunks_across_zero():
    assert ap.chunks((-1, 0, -1, 0, 0, 0)) == 4
    assert ap.chunks((0, 0, 0, 15, 0, 15)) == 1
    assert ap.chunks((-16, 0, 0, -1, 0, 0)) == 1


def test_split_fill_covers_same_cells_within_limits():
    limits = ap.Limits(max_blocks=1000)
    pieces = ap.split_fill({"from": [0, 0, 0], "to": [29, 9, 9], "block": "minecraft:stone"}, limits)
    volumes = [ap.volume(ap.box_of(p["from"], p["to"])) for p in pieces]
    assert sum(volumes) == 3000 and max(volumes) <= 1000


def test_shell_fill_over_limit_is_refused():
    with pytest.raises(ap.PlacerError) as err:
        ap.split_fill({"from": [0, 0, 0], "to": [29, 9, 9], "block": "minecraft:stone",
                       "mode": "hollow"}, ap.Limits(max_blocks=1000))
    assert err.value.code == ap.EXIT_REFUSED


def test_pages_preserve_order_and_put_fills_first():
    build = {"fills": [
        {"from": [0, 64, 0], "to": [9, 73, 9], "block": "minecraft:air"},
        {"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"},
        {"from": [0, 65, 0], "to": [0, 66, 0], "block": "minecraft:oak_log"}],
        "blocks": [{"pos": [1, 65, 1], "block": "minecraft:torch"},
                   {"pos": [2, 65, 1], "block": "minecraft:torch"}],
        "connect": True}
    pages = ap.make_pages(build, ap.Limits(max_blocks=1000))
    kinds = ["fills" if "fills" in p.args else "blocks" for p in pages]
    assert kinds == ["fills", "fills", "blocks"]
    flat = [f["block"] for p in pages if "fills" in p.args for f in p.args["fills"]]
    assert flat == ["minecraft:air", "minecraft:stone", "minecraft:oak_log"]
    assert all(p.cells <= 1000 and p.args["connect"] is True for p in pages)


def test_entry_limit_splits_pages():
    blocks = [{"pos": [i, 64, 0], "block": "minecraft:stone"} for i in range(5)]
    pages = ap.make_pages({"fills": [], "blocks": blocks}, ap.Limits(max_ops=2))
    assert [len(p.args["blocks"]) for p in pages] == [2, 2, 1]


def test_tiles_respect_cap_and_cover_box():
    box = (0, 60, 0, 99, 79, 99)
    assert ap.tile(box, 200_000) == [box]
    big = (0, 60, 0, 199, 79, 99)
    tiles = ap.tile(big, 200_000)
    assert len(tiles) == 2 and all(ap.volume(t) <= 200_000 for t in tiles)
    assert sum(ap.volume(t) for t in tiles) == ap.volume(big)


def test_parse_players_variants():
    text = ("Alex  world  pos x=10 y=64 z=-5  facing north (block in front: 10,64,-6)  survival"
            "  looking at minecraft:stone at 10,63,-6 (up face)\n"
            "Sam  world_nether  pos x=100 y=70 z=100  facing east (block in front: 101,70,100)  creative")
    players = ap.parse_players(text)
    assert players == [("Alex", "world", 10, 64, -5), ("Sam", "world_nether", 100, 70, 100)]
    assert ap.players_inside(players, (0, 60, -10, 20, 80, 0), 2, None) == ["Alex"]
    assert ap.players_inside(players, (98, 60, 98, 99, 80, 99), 2, "world") == []
    assert ap.players_inside(players, (98, 60, 98, 99, 80, 99), 2, None) == ["Sam"]
    assert ap.parse_players("No players online.") == []
    with pytest.raises(ap.PlacerError) as err:
        ap.parse_players("something unexpected")
    assert err.value.code == ap.EXIT_PLAYER


def test_snapshot_id_and_warnings():
    reply = ('Snapshot snap-20261117-1-ab created for world "world", volume 9, at t.\n'
             'Call mc_restore({"id":"snap-20261117-1-ab"}) to restore this region later.')
    assert ap.snapshot_id(reply) == "snap-20261117-1-ab"
    text = ("Fills: done\nWARNINGS (blocks that would fall):\n"
            "  minecraft:torch at 1,64,1 - unsupported\n  minecraft:ladder at 2,64,1 - unsupported")
    assert ap.warnings_of(text) == ["minecraft:torch at 1,64,1 - unsupported",
                                    "minecraft:ladder at 2,64,1 - unsupported"]
    assert ap.warnings_of("Fills: done") == []


def test_cli_plan_prints_summary(tmp_path, capsys):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({
        "fills": [{"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"}],
        "blocks": [{"pos": [0, 65, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    assert ap.main(["plan", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["cells"] == 101 and summary["snapshot_tiles"] == 1
    assert summary["bbox"] == {"from": [0, 64, 0], "to": [9, 65, 9]}
    assert [page["kind"] for page in summary["pages"]] == ["fills", "blocks"]


def test_cli_plan_reports_invalid_input(tmp_path, capsys):
    path = tmp_path / "b.json"
    path.write_text("[]", encoding="utf-8")
    assert ap.main(["plan", str(path)]) == ap.EXIT_INPUT
    assert "nothing to place" in capsys.readouterr().err


def test_parse_players_refuses_an_empty_reply():
    for text in ("", "  \n "):
        with pytest.raises(ap.PlacerError) as err:
            ap.parse_players(text)
        assert err.value.code == ap.EXIT_PLAYER and "player list" in str(err.value)


def test_result_lines_keep_detail_and_drop_the_warnings_block():
    text = "Fills: ok\n  detail 1\nWARNINGS (x):\n  torch at 1,1,1\nBlocks: ok\n  detail 2"
    assert ap.result_lines(text) == ["Fills: ok", "  detail 1", "Blocks: ok", "  detail 2"]


def test_server_entry_repr_hides_env():
    entry = ap.ServerEntry("cmd", ["a"], {"T": "tok-SECRET-123"}, "x.json")
    assert "tok-SECRET-123" not in repr(entry)


def test_secrets_of_includes_env_and_secret_flag_values():
    entry = ap.ServerEntry(
        "cmd", ["--token", "t1-abcd", "--api-key=k2-abcd", "--SECRET", "s3-abcd",
                "--password", "p4-abcd", "--port", "8159", "plain"],
        {"U": "ws://x:1"}, "x.json")
    assert ap.secrets_of(entry) == ["ws://x:1", "t1-abcd", "k2-abcd", "s3-abcd", "p4-abcd"]


def test_python_guard_exits_cleanly_on_old_python(capsys):
    for module in (ap, st):
        with pytest.raises(SystemExit) as err:
            module.require_python((3, 10))
        assert err.value.code == 2
        message = capsys.readouterr().err
        assert "needs Python 3.11 or newer" in message and "--python 3.11" in message
        module.require_python((3, 11))
        module.require_python()
