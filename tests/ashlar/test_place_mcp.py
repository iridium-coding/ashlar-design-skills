"""ashlar_place.py against a fake ashlar-mcp server."""
import json
import subprocess
import sys
import time
from pathlib import Path

import ashlar_place as ap
import pytest

REPO = Path(__file__).resolve().parents[2]
PLACER = REPO / "skills" / "exec-ashlar" / "scripts" / "ashlar_place.py"
FAKE = Path(__file__).with_name("fake_ashlar_mcp.py")
URL, TOKEN = "ws://203.0.113.9:8159", "tok-SECRET-123"


def config(tmp_path, args=(), **fake_env):
    env = {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN,
           "FAKE_LOG": str(tmp_path / "calls.jsonl"), **fake_env}
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": [str(FAKE), *args],
        "env": env}}}), encoding="utf-8")
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


ALEX_HERE = "Alex  {world}  pos x=5 y=65 z=5  facing north (block in front: 5,65,4)  survival"


def names(tmp_path):
    return [c["name"] for c in calls(tmp_path)]


def test_empty_player_reply_fails_closed(tmp_path):
    for reply in ("", "   \n"):
        (tmp_path / "calls.jsonl").unlink(missing_ok=True)
        proc = run("place", str(build_file(tmp_path)), "--snapshot",
                   "--config", str(config(tmp_path, FAKE_PLAYERS=reply)))
        assert proc.returncode == 4, proc.stderr
        assert "player list" in proc.stderr
        assert names(tmp_path) == ["mc_players"]


def test_server_request_with_our_id_is_ignored(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--max-blocks", "1000",
               "--config", str(config(tmp_path, FAKE_SERVER_REQUEST="1")))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["pages_done"] == 3


def test_snapshot_error_stops_before_any_build(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--snapshot",
               "--config", str(config(tmp_path, FAKE_FAIL_SNAPSHOT="1")))
    assert proc.returncode == 5
    assert names(tmp_path) == ["mc_players", "mc_snapshot"]
    report = json.loads(proc.stdout)
    assert report["pages_done"] == 0 and "mc_snapshot failed" in report["error"]


def test_no_page_is_sent_after_the_failing_one(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--max-blocks", "1000",
               "--config", str(config(tmp_path, FAKE_FAIL_BUILD="2")))
    assert proc.returncode == 5
    assert names(tmp_path) == ["mc_players", "mc_build", "mc_build"]


def test_world_filter_in_place(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PLAYERS", ALEX_HERE.format(world="nether"))
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--world", "world",
               "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert all(c["arguments"]["world"] == "world"
               for c in calls(tmp_path) if c["name"] == "mc_build")
    monkeypatch.setenv("FAKE_PLAYERS", ALEX_HERE.format(world="world"))
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--world", "world",
               "--config", str(config(tmp_path)))
    assert proc.returncode == 4 and "Alex" in proc.stderr


def test_env_value_equal_to_a_world_name_still_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PLAYERS", ALEX_HERE.format(world="world"))
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--world", "world",
               "--config", str(config(tmp_path, SOME_WORLD_NAME="world")))
    assert proc.returncode == 4, proc.stderr
    assert "Alex" in proc.stderr
    assert "world" not in proc.stdout + proc.stderr
    assert names(tmp_path) == ["mc_players"]


def test_report_keeps_indented_detail_but_not_warnings(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot",
               "--config", str(config(tmp_path, FAKE_WARN="1")))
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)["results"][0]["result"]
    assert result == ["Fills: ok", "  detail: 3 cells"]


def test_log_write_failure_warns_and_keeps_exit_code(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--log", str(tmp_path),
               "--config", str(config(tmp_path)))
    assert proc.returncode == 0 and "could not write the log" in proc.stderr
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--log", str(tmp_path),
               "--config", str(config(tmp_path, FAKE_FAIL_BUILD="1")))
    assert proc.returncode == 5 and "could not write the log" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_secret_flag_value_in_args_is_redacted(tmp_path):
    crash = "import sys; sys.stderr.write('argv ' + ' '.join(sys.argv[1:]) + '\\n'); sys.exit(1)"
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable,
        "args": ["-c", crash, "--api-key", "flagvalue-777", "--password=hunter2-xyz",
                 "--port", "8159"]}}}), encoding="utf-8")
    proc = run("check", "--config", str(path))
    assert proc.returncode == 5
    assert "flagvalue-777" not in proc.stderr and "hunter2-xyz" not in proc.stderr
    assert "8159" in proc.stderr


def test_non_utf8_child_output_does_not_break_the_pumps(tmp_path):
    crash = "import sys; sys.stderr.buffer.write(b'bad \\xff\\xfe bytes\\n'); sys.exit(1)"
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": ["-c", crash]}}}),
        encoding="utf-8")
    proc = run("check", "--config", str(path))
    assert proc.returncode == 5 and "Traceback" not in proc.stderr
    assert "bad" in proc.stderr


# ------------------------------------------------ MCP eras (spec 2026-07-28)

MODERN = "2026-07-28"
PV = "io.modelcontextprotocol/protocolVersion"
CAPS = "io.modelcontextprotocol/clientCapabilities"
INFO = "io.modelcontextprotocol/clientInfo"


def client(tmp_path, probe_timeout=5.0, **fake_env):
    env = {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN,
           "FAKE_META_LOG": str(tmp_path / "meta.jsonl"), **fake_env}
    entry = ap.ServerEntry(command=sys.executable, args=[str(FAKE)], env=env, source="test")
    return ap.McpClient(entry, start_timeout=20.0, call_timeout=20.0, probe_timeout=probe_timeout)


def requests(tmp_path):
    log = tmp_path / "meta.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def status(c):
    try:
        return c.call("mc_status", {})
    finally:
        c.close()


def test_a_legacy_server_is_reached_through_initialize_after_the_probe(tmp_path):
    c = client(tmp_path)
    assert (c.era, c.protocol_version) == ("legacy", "2025-06-18")
    assert status(c) == ("Plugin version: 0.4.9\nServer: fake", False)
    sent = requests(tmp_path)
    assert [r["method"] for r in sent] == ["server/discover", "initialize", "tools/call"]
    assert sent[0]["meta"][PV] == MODERN and CAPS in sent[0]["meta"] and INFO in sent[0]["meta"]
    assert sent[2]["meta"] is None  # legacy requests carry no per-request metadata


@pytest.mark.parametrize("code", [-32601, -32602, -32600, -32603, -32000],
                         ids=["method-not-found", "invalid-params", "invalid-request",
                              "internal", "server-defined"])
def test_the_legacy_fallback_is_not_keyed_to_one_error_code(tmp_path, code):
    c = client(tmp_path, FAKE_DISCOVER_CODE=str(code))
    assert c.era == "legacy"
    assert status(c)[0].startswith("Plugin version")


def test_a_silent_legacy_server_falls_back_after_the_probe_timeout(tmp_path):
    started = time.monotonic()
    c = client(tmp_path, probe_timeout=0.5, FAKE_ERA="legacy-silent")
    assert c.era == "legacy" and time.monotonic() - started < 10
    assert status(c)[0].startswith("Plugin version")


def test_a_modern_server_gets_metadata_on_every_request_and_no_handshake(tmp_path):
    c = client(tmp_path, FAKE_ERA="modern")
    assert (c.era, c.protocol_version) == ("modern", MODERN)
    assert status(c) == ("Plugin version: 0.4.9\nServer: fake", False)
    sent = requests(tmp_path)
    assert [r["method"] for r in sent] == ["server/discover", "tools/call"]
    meta = sent[1]["meta"]
    assert meta[PV] == MODERN and meta[CAPS] == {}
    assert meta[INFO] == {"name": "ashlar-place", "version": ap.CLIENT_VERSION}


def test_a_dual_era_server_stays_modern(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SUPPORTED", f"{MODERN},2025-06-18")
    c = client(tmp_path, FAKE_ERA="dual")
    assert c.era == "modern"
    status(c)
    assert "initialize" not in [r["method"] for r in requests(tmp_path)]


def test_a_discover_result_offering_only_the_legacy_version_gets_the_handshake(tmp_path,
                                                                             monkeypatch):
    monkeypatch.setenv("FAKE_SUPPORTED", "2025-06-18")
    c = client(tmp_path, FAKE_ERA="dual")
    assert (c.era, c.protocol_version) == ("legacy", "2025-06-18")
    assert status(c)[0].startswith("Plugin version")
    assert [r["method"] for r in requests(tmp_path)] == ["server/discover", "initialize",
                                                          "tools/call"]


# Values in the server entry's env are redacted as secrets, so knobs whose values
# must appear in a message are set in the process environment instead.

def test_a_discover_result_with_no_shared_version_names_the_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SUPPORTED", "2027-03-01")
    with pytest.raises(ap.PlacerError, match=r"2027-03-01") as err:
        client(tmp_path, FAKE_ERA="modern")
    assert err.value.code == ap.EXIT_SERVER
    assert "initialize" not in [r["method"] for r in requests(tmp_path)]


def test_an_unsupported_version_error_on_the_probe_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SUPPORTED", "2027-03-01")
    with pytest.raises(ap.PlacerError, match=r"supports MCP 2027-03-01"):
        client(tmp_path, FAKE_ERA="modern", FAKE_DISCOVER_VALIDATES="1")
    assert [r["method"] for r in requests(tmp_path)] == ["server/discover"]


def test_a_missing_capability_error_is_modern_and_names_the_capability(tmp_path):
    with pytest.raises(ap.PlacerError, match=r"elicitation"):
        client(tmp_path, FAKE_ERA="modern-capability")
    assert "initialize" not in [r["method"] for r in requests(tmp_path)]


def test_a_late_discover_reply_beats_a_rejected_initialize(tmp_path):
    c = client(tmp_path, probe_timeout=0.5, FAKE_ERA="modern", FAKE_DISCOVER_DELAY="1.5")
    assert (c.era, c.protocol_version) == ("modern", MODERN)
    assert status(c)[0].startswith("Plugin version")


@pytest.mark.parametrize("kind", ["input_required", "something_new"])
def test_a_result_that_is_not_complete_is_refused(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("FAKE_RESULT_TYPE", kind)
    c = client(tmp_path, FAKE_ERA="modern")
    try:
        with pytest.raises(ap.PlacerError, match=kind):
            c.call("mc_status", {})
    finally:
        c.close()


@pytest.mark.parametrize(("era", "line"), [("legacy", "MCP 2025-06-18 (legacy handshake)"),
                                           ("modern", f"MCP {MODERN} (per-request metadata)")])
def test_check_names_the_protocol_it_used(tmp_path, era, line):
    proc = run("check", "--config", str(config(tmp_path, FAKE_ERA=era)))
    assert proc.returncode == 0, proc.stderr
    assert line in proc.stdout
    assert_no_secrets(proc)
