#!/usr/bin/env python3
"""Stand-in for ashlar-mcp in tests: newline-delimited JSON-RPC over stdio.

Environment knobs:
  FAKE_LOG         append one JSON line per tools/call: {"name": ..., "arguments": ...}
  FAKE_PLAYERS     mc_players reply text (default "No players online.")
  FAKE_FAIL_BUILD  1-based number of the mc_build call that returns isError
  FAKE_WARN        when set, every mc_build reply has a WARNINGS section
  FAKE_FAIL_SNAPSHOT  when set, mc_snapshot returns isError
  FAKE_SERVER_REQUEST when set, every request is preceded by a server-initiated
                      request that reuses the client's id
Like the real server it logs "connecting to <MC_PLUGIN_URL>" on stderr.
"""
import json
import os
import sys


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def text(body, error=False):
    return {"content": [{"type": "text", "text": body}], "isError": error}


def main():
    print(f"[fake] connecting to {os.environ.get('MC_PLUGIN_URL', '')}",
          file=sys.stderr, flush=True)
    builds = snapshots = 0
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        rid, method = message["id"], message.get("method")
        if os.environ.get("FAKE_SERVER_REQUEST"):
            send({"jsonrpc": "2.0", "id": rid, "method": "ping"})
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-ashlar", "version": "0"}}})
            continue
        if method != "tools/call":
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": "no such method"}})
            continue
        name = message["params"]["name"]
        arguments = message["params"].get("arguments", {})
        if os.environ.get("FAKE_LOG"):
            with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"name": name, "arguments": arguments}) + "\n")
        if name == "mc_status":
            result = text("Plugin version: 0.4.9\nServer: fake")
        elif name == "mc_players":
            result = text(os.environ.get("FAKE_PLAYERS", "No players online."))
        elif name == "mc_snapshot":
            snapshots += 1
            if os.environ.get("FAKE_FAIL_SNAPSHOT"):
                send({"jsonrpc": "2.0", "id": rid,
                      "result": text("Error: no room", error=True)})
                continue
            sid = f"snap-test-{snapshots}"
            result = text(f'Snapshot {sid} created for world "world", volume 1, at now.\n'
                          f'Call mc_restore({{"id":"{sid}"}}) to restore this region later.')
        elif name == "mc_build":
            builds += 1
            send({"jsonrpc": "2.0", "method": "notifications/progress",
                  "params": {"progressToken": builds, "progress": 1}})
            if str(builds) == os.environ.get("FAKE_FAIL_BUILD"):
                result = text("Error: boom", error=True)
            else:
                body = "Fills: ok\n  detail: 3 cells"
                if os.environ.get("FAKE_WARN"):
                    body += ("\nWARNINGS (blocks that would fall):\n"
                             "  minecraft:torch at 1,64,1 - unsupported")
                result = text(body)
        else:
            result = text(f"unknown tool {name}", error=True)
        send({"jsonrpc": "2.0", "id": rid, "result": result})


if __name__ == "__main__":
    main()
