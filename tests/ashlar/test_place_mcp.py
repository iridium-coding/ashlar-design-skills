"""ashlar_place.py against a fake ashlar-mcp server."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLACER = REPO / "skills" / "exec-ashlar" / "scripts" / "ashlar_place.py"
FAKE = Path(__file__).with_name("fake_ashlar_mcp.py")
URL, TOKEN = "ws://203.0.113.9:8159", "tok-SECRET-123"


def config(tmp_path, **fake_env):
    env = {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN,
           "FAKE_LOG": str(tmp_path / "calls.jsonl"), **fake_env}
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": [str(FAKE)], "env": env}}}),
        encoding="utf-8")
    return path


def run(*args):
    return subprocess.run([sys.executable, str(PLACER), *args],
                          capture_output=True, text=True, timeout=60)


def calls(tmp_path):
    log = tmp_path / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def build_file(tmp_path):
    path = tmp_path / "phase.json"
    path.write_text(json.dumps({
        "fills": [{"from": [0, 64, 0], "to": [9, 73, 9], "block": "minecraft:air"},
                  {"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"}],
        "blocks": [{"pos": [1, 65, 1], "block": "minecraft:torch"}]}), encoding="utf-8")
    return path


def assert_no_secrets(proc):
    for stream in (proc.stdout, proc.stderr):
        assert "203.0.113.9" not in stream and TOKEN not in stream


def test_check_reports_status_without_secrets(tmp_path):
    proc = run("check", "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert "Plugin version: 0.4.9" in proc.stdout
    assert_no_secrets(proc)


def test_place_snapshots_then_pages_in_order(tmp_path):
    log = tmp_path / "report.log"
    proc = run("place", str(build_file(tmp_path)), "--snapshot", "--label", "t",
               "--max-blocks", "1000", "--log", str(log),
               "--config", str(config(tmp_path, FAKE_WARN="1")))
    assert proc.returncode == 0, proc.stderr
    names = [c["name"] for c in calls(tmp_path)]
    assert names == ["mc_players", "mc_snapshot", "mc_build", "mc_build", "mc_build"]
    builds = [c["arguments"] for c in calls(tmp_path) if c["name"] == "mc_build"]
    assert [list(b) for b in builds] == [["fills"], ["fills"], ["blocks"]]
    snapshot = [c["arguments"] for c in calls(tmp_path) if c["name"] == "mc_snapshot"][0]
    assert snapshot == {"action": "create", "from": [0, 64, 0], "to": [9, 73, 9], "label": "t 1/1"}
    report = json.loads(proc.stdout)
    assert report["snapshots"] == ["snap-test-1"] and report["pages_done"] == 3
    assert "minecraft:torch at 1,64,1 - unsupported" in report["warnings"]
    assert json.loads(log.read_text(encoding="utf-8")) == report
    assert_no_secrets(proc)


def test_place_refuses_when_player_inside(tmp_path, monkeypatch):
    # Passed through the process environment, not the server entry: every entry
    # env value is redacted from replies, which would blank the player list.
    players = "Alex  world  pos x=5 y=65 z=5  facing north (block in front: 5,65,4)  survival"
    monkeypatch.setenv("FAKE_PLAYERS", players)
    proc = run("place", str(build_file(tmp_path)), "--snapshot",
               "--config", str(config(tmp_path)))
    assert proc.returncode == 4
    assert [c["name"] for c in calls(tmp_path)] == ["mc_players"]
    assert "Alex" in proc.stderr


def test_place_reports_partial_progress_on_failure(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--max-blocks", "1000",
               "--config", str(config(tmp_path, FAKE_FAIL_BUILD="2")))
    assert proc.returncode == 5
    report = json.loads(proc.stdout)
    assert report["pages_done"] == 1 and "page 2/3" in report["error"]
    assert_no_secrets(proc)


def test_server_crash_redacts_url_and_token(tmp_path):
    crash = ("import os, sys; sys.stderr.write('connecting to ' + os.environ['MC_PLUGIN_URL']"
             " + ' token ' + os.environ['MC_PLUGIN_TOKEN'] + '\\n'); sys.exit(1)")
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": ["-c", crash],
        "env": {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN}}}}), encoding="utf-8")
    proc = run("check", "--config", str(path))
    assert proc.returncode == 5
    assert "***" in proc.stderr
    assert_no_secrets(proc)


def test_place_needs_a_snapshot_choice(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--config", str(config(tmp_path)))
    assert proc.returncode == 2


def test_place_refuses_too_many_snapshots_before_starting_server(tmp_path):
    path = tmp_path / "big.json"
    path.write_text(json.dumps([{"from": [0, 0, 0], "to": [399, 99, 99],
                                 "block": "minecraft:stone"}]), encoding="utf-8")
    proc = run("place", str(path), "--snapshot", "--max-snapshots", "2",
               "--config", str(config(tmp_path)))
    assert proc.returncode == 3
    assert calls(tmp_path) == []
