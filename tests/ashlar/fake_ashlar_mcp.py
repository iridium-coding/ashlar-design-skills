#!/usr/bin/env python3
"""Stand-in for ashlar-mcp in tests: newline-delimited JSON-RPC over stdio.

Environment knobs:
  FAKE_LOG         append one JSON line per tools/call: {"name": ..., "arguments": ...}
  FAKE_PLAYERS     mc_players reply text (default "No players online.")
  FAKE_FAIL_BUILD  1-based number of the mc_build call that returns isError
  FAKE_WARN        when set, every mc_build reply has a WARNINGS section
  FAKE_FAIL_SNAPSHOT  when set, mc_snapshot returns isError
  FAKE_FAIL_INSPECT   when set, mc_inspect returns isError ("Error: region too large")
  FAKE_INSPECT_BOTTOM when set (and FAKE_WORLD is not), the bottom cell of every
                      inspected column is this state; every other cell is air
  FAKE_INSPECT_SKIP   when set, mc_inspect omits the column "x,z" given here
  FAKE_WORLD          path to a JSON world {"ground": 63, "cells": {"x,y,z": "minecraft:..."}}:
                      a cell below `ground` is stone, else air, unless `cells` says
                      otherwise. mc_inspect columns reads it (ids without the
                      namespace, equal neighbours merged); mc_build applies `fills`
                      (replace, optional `filter` = only cells whose current id is the
                      filter's id), then `blocks`, and the file is rewritten after
                      every call that changes it
  (mc_survey with matrix: true reads FAKE_WORLD; no world -> isError)
  FAKE_SERVER_REQUEST when set, every request is preceded by a server-initiated
                      request that reuses the client's id
  FAKE_FAIL_FEATURE   1-based number of the place feature / fillbiome call whose reply is
                      "Failed to place feature"
  FAKE_ERROR_COMMAND  1-based number of the place feature / fillbiome call that returns
                      isError ("Error: plugin unreachable")
  FAKE_FAIL_ADD       1-based number of the forceload add that does not mark (replies
                      "No chunks were marked for force loading")
  FAKE_FAIL_REMOVE    when set, forceload remove removes nothing and says so
  FAKE_QUERY_ECHO_SECRET  when set, forceload query replies 195 x's followed by
                      MC_PLUGIN_TOKEN (a secret straddling a 200-character cut)
  mc_command (console, vanilla English replies, `execute in DIM run` honoured):
    forceload add|remove|query, place feature, fillbiome, execute if biome. The
    force-loaded set is world["forceloaded"] ([[cx, cz], ...], "forceloaded@DIM" for
    another dimension) and biomes are world["biomes"] ({"cx,cz": id}, default
    minecraft:plains) in FAKE_WORLD, or in memory when it is not set. Place feature,
    fillbiome and execute if biome in a chunk that is not force-loaded reply
    "That position is not loaded".
  FAKE_ERA            which MCP era the fake speaks (MCP 2026-07-28 "Versioning"):
                      unset or "legacy": `initialize` handshake; any other method before
                        it, `server/discover` included, gets FAKE_DISCOVER_CODE (default
                        -32601 "no such method")
                      "legacy-silent": like legacy, but never answers server/discover
                      "modern": answers server/discover, rejects `initialize`, and needs
                        `io.modelcontextprotocol/protocolVersion` (one of
                        FAKE_SUPPORTED, comma-separated, default 2026-07-28) and
                        `io.modelcontextprotocol/clientCapabilities` in every request's
                        `_meta`: a missing field gets -32602, an unknown version -32022
                        with data.supported; results carry resultType FAKE_RESULT_TYPE
                        (default "complete") and serverInfo in `_meta`
                      "dual": modern, and `initialize` also works
                      "modern-capability": server/discover gets -32021
                        (MissingRequiredClientCapabilityError)
  FAKE_DISCOVER_DELAY seconds to wait before answering server/discover (modern eras)
  FAKE_DISCOVER_VALIDATES when set, server/discover in a modern era checks `_meta` too
                      (an unknown version gets -32022)
  FAKE_META_LOG       append one JSON line per request: {"method": ..., "meta": ...}
Like the real server it logs "connecting to <MC_PLUGIN_URL>" on stderr.
"""
import json
import os
import re
import sys
import threading
import time

PV, CAPS = "io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO = {"io.modelcontextprotocol/serverInfo": {"name": "fake-ashlar", "version": "0"}}
_LOCK = threading.Lock()


def send(message):
    with _LOCK:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def era():
    return os.environ.get("FAKE_ERA", "legacy")


def supported():
    return os.environ.get("FAKE_SUPPORTED", "2026-07-28").split(",")


def error(rid, code, message, data=None):
    body = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    send({"jsonrpc": "2.0", "id": rid, "error": body})


def discover_result():
    return {"resultType": "complete", "supportedVersions": supported(),
            "capabilities": {"tools": {}}, "ttlMs": 0, "cacheScope": "private",
            "_meta": dict(SERVER_INFO)}


def answer_discover(rid, meta):
    """Answer server/discover the way the configured era does; False when it stays silent."""
    kind = era()
    if kind == "legacy-silent":
        return False
    if kind in ("legacy",):
        error(rid, int(os.environ.get("FAKE_DISCOVER_CODE", "-32601")), "no such method")
        return True
    if kind == "modern-capability":
        error(rid, -32021, "Missing required client capability",
              {"requiredCapabilities": {"elicitation": {}}})
        return True
    if os.environ.get("FAKE_DISCOVER_VALIDATES") and modern_meta_error(rid, meta):
        return True
    delay = float(os.environ.get("FAKE_DISCOVER_DELAY", "0") or 0)

    def reply():
        time.sleep(delay)
        send({"jsonrpc": "2.0", "id": rid, "result": discover_result()})
    if delay:
        threading.Thread(target=reply, daemon=True).start()
    else:
        reply()
    return True


def modern_meta_error(rid, meta):
    """Reply with the modern validation error for `meta`; True when the request was rejected."""
    if not isinstance(meta, dict) or PV not in meta or CAPS not in meta:
        error(rid, -32602, "missing required _meta fields")
        return True
    if meta[PV] not in supported():
        error(rid, -32022, "Unsupported protocol version",
              {"supported": supported(), "requested": meta[PV]})
        return True
    return False


def text(body, error=False):
    return {"content": [{"type": "text", "text": body}], "isError": error}


def block_id(state):
    return state.split("[")[0].removeprefix("minecraft:")


def world_cell(world, x, y, z):
    default = "minecraft:stone" if y < world.get("ground", 63) else "minecraft:air"
    return world.get("cells", {}).get(f"{x},{y},{z}", default)


def apply_build(world, arguments):
    """Apply an mc_build call to `world`; return whether anything changed."""
    cells = world.setdefault("cells", {})
    for fill in arguments.get("fills") or []:
        if fill.get("mode", "replace") != "replace":
            raise ValueError("fake supports replace fills only")
        a, b = fill["from"], fill["to"]
        wanted = fill.get("filter")
        for x in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
            for y in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                for z in range(min(a[2], b[2]), max(a[2], b[2]) + 1):
                    if wanted and block_id(world_cell(world, x, y, z)) != block_id(wanted):
                        continue
                    cells[f"{x},{y},{z}"] = fill["block"]
    for block in arguments.get("blocks") or []:
        x, y, z = block["pos"]
        cells[f"{x},{y},{z}"] = block["block"]
    return True


def inspect_columns(arguments):
    a, b = arguments["from"], arguments["to"]
    x1, x2 = sorted((a[0], b[0]))
    y1, y2 = sorted((a[1], b[1]))
    z1, z2 = sorted((a[2], b[2]))
    bottom = os.environ.get("FAKE_INSPECT_BOTTOM")
    world = load_world()
    lines = [f"Region (default) x=[{x1}..{x2}] y=[{y1}..{y2}] z=[{z1}..{z2}], "
             "runs bottom to top (ids without the minecraft: prefix):"]
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            if f"{x},{z}" == os.environ.get("FAKE_INSPECT_SKIP"):
                continue
            if world is not None:
                runs = []
                for y in range(y1, y2 + 1):
                    ident = block_id(world_cell(world, x, y, z))
                    if runs and runs[-1][2] == ident:
                        runs[-1][1] = y
                    else:
                        runs.append([y, y, ident])
                lines.append(f"{x},{z}: " + " | ".join(
                    f"{lo} {i}" if lo == hi else f"{lo}-{hi} {i}" for lo, hi, i in runs))
                continue
            runs, low = [], y1
            if bottom:
                runs.append(f"{y1} {bottom}")
                low = y1 + 1
            if low <= y2:
                runs.append(f"{low} air" if low == y2 else f"{low}-{y2} air")
            lines.append(f"{x},{z}: " + " | ".join(runs))
    return "\n".join(lines)


def survey_matrix(arguments):
    """mc_survey with matrix: true over the fake world (from/to are [x, z] pairs)."""
    world = load_world()
    if world is None:
        return text("Error: no FAKE_WORLD", error=True)
    (xa, za), (xb, zb) = arguments["from"][:2], arguments["to"][:2]
    x1, x2, z1, z2 = min(xa, xb), max(xa, xb), min(za, zb), max(za, zb)
    kind = arguments.get("type", "SOLID")
    cells = world.get("cells", {})
    top_cell = max([int(k.split(",")[1]) for k in cells] + [world.get("ground", 63) - 1])
    start = min(319, top_cell)

    def visible(ident):
        if ident == "air":
            return False
        if kind == "ANY":
            return True
        if ident.endswith("_leaves"):
            return False
        return kind != "SOLID" or ident not in ("water", "lava")

    lines = [f"Area x=[{x1}..{x2}] z=[{z1}..{z2}] ({x2 - x1 + 1}x{z2 - z1 + 1}). "
             f"Surface y: type {kind}.",
             f"Height matrix (z rows top-to-bottom, x columns left-to-right, "
             f"top-left = x={x1} z={z1}):"]
    for z in range(z1, z2 + 1):
        row = []
        for x in range(x1, x2 + 1):
            found = "-"
            for y in range(start, -65, -1):
                if visible(block_id(world_cell(world, x, y, z))):
                    found = str(y)
                    break
            row.append(found)
        lines.append(f"z={z}: " + " ".join(row))
    return text("\n".join(lines))


def load_world():
    path = os.environ.get("FAKE_WORLD")
    if not path:
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_world(world):
    with open(os.environ["FAKE_WORLD"], "w", encoding="utf-8") as handle:
        json.dump(world, handle)


MEMORY = {}
KNOWN_BIOMES = ["minecraft:plains", "minecraft:forest", "minecraft:desert",
                "minecraft:river", "minecraft:taiga", "minecraft:swamp"]


def console(command, counters):
    """Reply to one console command (vanilla English strings)."""
    command = command.removeprefix("minecraft:")
    dim, key = "minecraft:overworld", "forceloaded"
    match = re.match(r"execute in (\S+) run (.*)$", command)
    if match:
        dim, command = match.group(1), match.group(2)
        key = f"forceloaded@{dim}"
    world = load_world()
    persisted = world is not None
    if world is None:
        world = MEMORY
    loaded = {tuple(c) for c in world.get(key, [])}
    biomes = world.setdefault("biomes", {})
    parts = command.split()

    def save():
        world[key] = sorted(list(c) for c in loaded)
        if persisted:
            save_world(world)

    if parts[:2] in (["forceload", "add"], ["forceload", "remove"]) and len(parts) in (4, 6):
        adding = parts[1] == "add"
        nums = [int(p) for p in parts[2:]]
        x1, z1, x2, z2 = (nums[0], nums[1], nums[-2], nums[-1])
        cells = {(cx, cz) for cx in range(min(x1, x2) >> 4, (max(x1, x2) >> 4) + 1)
                 for cz in range(min(z1, z2) >> 4, (max(z1, z2) >> 4) + 1)}
        if len(cells) > 256:
            return text(f"Too many chunks in the specified area (maximum 256, but "
                        f"specified {len(cells)})", error=False)
        if adding:
            counters["add"] = counters.get("add", 0) + 1
            changed = cells - loaded
            if not changed or str(counters["add"]) == os.environ.get("FAKE_FAIL_ADD"):
                return text("No chunks were marked for force loading")
            loaded |= cells
        else:
            changed = cells & loaded
            if not changed or os.environ.get("FAKE_FAIL_REMOVE"):
                return text("No chunks were removed from force loading")
            loaded -= cells
        save()
        verb = "Marked" if adding else "Unmarked"
        tail = "to be force loaded" if adding else "from force loading"
        if len(changed) == 1:
            cx, cz = next(iter(changed))
            return text(f"{verb} chunk {cx}, {cz} (at {cx * 16}, {cz * 16}) in {dim} {tail}")
        return text(f"{verb} {len(changed)} chunks in {dim} {tail}")
    if parts == ["forceload", "query"]:
        if os.environ.get("FAKE_QUERY_ECHO_SECRET"):
            return text("x" * 195 + os.environ.get("MC_PLUGIN_TOKEN", ""))
        if not loaded:
            return text(f"No force loaded chunks were found in {dim}")
        pairs = ", ".join(f"[{cx}, {cz}]" for cx, cz in sorted(loaded))
        if len(loaded) == 1:
            return text(f"A force loaded chunk was found in {dim} at: {pairs}")
        return text(f"{len(loaded)} force loaded chunks were found in {dim} at: {pairs}")
    if parts[:2] == ["place", "feature"] and len(parts) == 6 or parts[:1] == ["fillbiome"]:
        counters["calls"] = counters.get("calls", 0) + 1
        number = str(counters["calls"])
        if number == os.environ.get("FAKE_ERROR_COMMAND"):
            return text("Error: plugin unreachable", error=True)
        if parts[0] == "fillbiome":
            x1, y1, z1, x2, y2, z2 = (int(p) for p in parts[1:7])
            cells = {(cx, cz) for cx in range(min(x1, x2) >> 4, (max(x1, x2) >> 4) + 1)
                     for cz in range(min(z1, z2) >> 4, (max(z1, z2) >> 4) + 1)}
            size = ((abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1))
            if size > 32768:
                return text(f"Too many blocks in the specified volume (maximum 32768, "
                            f"but specified {size})")
            if not cells <= loaded:
                return text("That position is not loaded")
            changed = [c for c in cells if biomes.get(f"{c[0]},{c[1]}") != parts[7]]
            for c in changed:
                biomes[f"{c[0]},{c[1]}"] = parts[7]
            if persisted:
                save_world(world)
            if not changed:
                return text("No biome entries were changed")
            n = max(1, size // 64)
            return text(f"{n} biome {'entry' if n == 1 else 'entries'} set between "
                        f"{x1}, {y1}, {z1} and {x2}, {y2}, {z2}")
        x, y, z = (int(p) for p in parts[3:6])
        if (x >> 4, z >> 4) not in loaded:
            return text("That position is not loaded")
        if number == os.environ.get("FAKE_FAIL_FEATURE"):
            return text("Failed to place feature")
        if parts[2] == "minecraft:foo":
            return text('There is no feature with type "minecraft:foo"')
        return text(f'Placed "{parts[2]}" at {x}, {y}, {z}')
    if parts[:3] == ["execute", "if", "biome"] and len(parts) == 7:
        x, y, z = (int(p) for p in parts[3:6])
        if parts[6] not in KNOWN_BIOMES:
            return text(f"Can't find element '{parts[6]}' of type 'minecraft:worldgen/biome'")
        if (x >> 4, z >> 4) not in loaded:
            return text("That position is not loaded")
        here = biomes.get(f"{x >> 4},{z >> 4}", "minecraft:plains")
        return text("Test passed" if here == parts[6] else "Test failed")
    return text("Unknown or incomplete command, see below for error", error=False)


def main():
    print(f"[fake] connecting to {os.environ.get('MC_PLUGIN_URL', '')}",
          file=sys.stderr, flush=True)
    builds = snapshots = 0
    counters = {}
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        rid, method = message["id"], message.get("method")
        meta = (message.get("params") or {}).get("_meta")
        if os.environ.get("FAKE_META_LOG"):
            with open(os.environ["FAKE_META_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"method": method, "meta": meta}) + "\n")
        if os.environ.get("FAKE_SERVER_REQUEST"):
            send({"jsonrpc": "2.0", "id": rid, "method": "ping"})
        modern = era() in ("modern", "dual")
        if method == "server/discover":
            answer_discover(rid, meta)
            continue
        if method == "initialize":
            if era() == "modern":
                error(rid, -32601, "initialize is not supported; this server speaks MCP "
                      + ", ".join(supported()))
                continue
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-ashlar", "version": "0"}}})
            continue
        if modern and (era() == "modern" or meta is not None) and modern_meta_error(rid, meta):
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
                world = load_world()
                if world is not None and apply_build(world, arguments):
                    save_world(world)
                body = "Fills: ok\n  detail: 3 cells"
                if os.environ.get("FAKE_WARN"):
                    body += ("\nWARNINGS (blocks that would fall):\n"
                             "  minecraft:torch at 1,64,1 - unsupported")
                result = text(body)
        elif name == "mc_command":
            result = console(arguments["command"], counters)
        elif name == "mc_inspect":
            if os.environ.get("FAKE_FAIL_INSPECT"):
                result = text("Error: region too large", error=True)
            else:
                result = text(inspect_columns(arguments))
        elif name == "mc_survey" and arguments.get("matrix"):
            result = survey_matrix(arguments)
        else:
            result = text(f"unknown tool {name}", error=True)
        if modern and meta is not None:
            kind = os.environ.get("FAKE_RESULT_TYPE", "complete")
            if kind != "complete":
                result = {"requestState": "opaque"}
            result = {"resultType": kind, **result, "_meta": dict(SERVER_INFO)}
        send({"jsonrpc": "2.0", "id": rid, "result": result})


if __name__ == "__main__":
    main()
