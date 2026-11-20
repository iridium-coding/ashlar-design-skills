#!/usr/bin/env python3
"""Send generated Minecraft geometry to a Paper server through Ashlar.

Starts the `ashlar-mcp` server the same way the client config does (Claude
Code `~/.claude.json`, a project `.mcp.json`, or Codex `~/.codex/config.toml`),
speaks MCP over stdio, and sends a phase file as paged `mc_build` calls after a
player check and snapshots.

  ashlar_place.py check  [--server NAME] [--config PATH]
  ashlar_place.py plan   FILE [limit options]
  ashlar_place.py place  FILE (--snapshot [--label L] | --no-snapshot)
                         [--world W] [--player-margin 2] [--max-snapshots 15]
                         [--log PATH] [--server NAME] [--config PATH] [limit options]
  ashlar_place.py read   X1 Y1 Z1 X2 Y2 Z2 --out FILE [--world W]
                         [--server NAME] [--config PATH]

A phase file is an `mc_build` arguments object (`fills`, `blocks`, `liquids`,
`connect`, `world`) or a bare list of fills. Exit codes: 0 ok, 2 invalid input,
3 refused by a limit or snapshot rule, 4 player in the area (or an unreadable
player list), 5 server error. Nothing printed ever contains a value from the
server entry's `env` (or a secret-looking command-line argument): replies are
parsed as received and redacted only when printed, logged or put in a message.

Config lookup order: `~/.claude.json`, then `./.mcp.json`, then
`~/.codex/config.toml`. The workspace's own `.mcp.json` is trusted: an entry
named like the server is launched as written, with no approval prompt.
"""
from __future__ import annotations

import sys


def require_python(version: tuple[int, ...] | None = None) -> None:
    """Exit cleanly, with one line on stderr, on Python older than 3.11."""
    if tuple(version if version is not None else sys.version_info[:2]) < (3, 11):
        print("ashlar_place.py needs Python 3.11 or newer; run it with `uv run "
              "--no-project --python 3.11 python ashlar_place.py ...`",
              file=sys.stderr)
        raise SystemExit(2)


require_python()

import argparse
import json
import os
import queue
import re
import subprocess
import threading
import time
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_INPUT, EXIT_REFUSED, EXIT_PLAYER, EXIT_SERVER = 0, 2, 3, 4, 5
SHELL_MODES = {"outline", "hollow", "walls"}
FILL_MODES = {"replace", "keep"} | SHELL_MODES
TOP_KEYS = {"fills", "blocks", "liquids", "connect", "world"}

Box = tuple[int, int, int, int, int, int]


class PlacerError(Exception):
    """A failure with the exit code the command line should return."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Limits:
    max_blocks: int = 500_000
    max_chunks: int = 1024
    max_ops: int = 4096
    snapshot_volume: int = 200_000
    min_y: int = -64
    max_y: int = 319


@dataclass
class Page:
    args: dict[str, Any]
    box: Box
    cells: int


# ------------------------------------------------------------------- config

@dataclass
class ServerEntry:
    command: str
    args: list[str]
    env: dict[str, str] = field(repr=False)
    source: str


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_URL = re.compile(r"\b(?:wss?|https?)://\S+")


def expand(value: str, environ: dict[str, str]) -> str:
    """Expand ${VAR} and ${VAR:-default} from `environ`."""
    def repl(match: re.Match[str]) -> str:
        default = match.group(2) if match.group(2) is not None else ""
        return environ.get(match.group(1), default)
    return _VAR.sub(repl, value)


def _lookup(path: Path, name: str, cwd: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        return (tomllib.loads(text).get("mcp_servers") or {}).get(name)
    data = json.loads(text)
    servers = data.get("mcpServers") or {}
    if name in servers:
        return servers[name]
    project = (data.get("projects") or {}).get(str(cwd)) or {}
    return (project.get("mcpServers") or {}).get(name)


def find_server(name: str, config: str | None, cwd: Path, home: Path,
                environ: dict[str, str]) -> ServerEntry:
    """Find the stdio MCP server entry called `name`."""
    if config:
        candidates = [Path(config)]
        if not candidates[0].is_file():
            raise PlacerError(f"config file not found: {config}", EXIT_INPUT)
    else:
        candidates = [home / ".claude.json", cwd / ".mcp.json",
                      home / ".codex" / "config.toml"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = _lookup(path, name, cwd)
        except ValueError as exc:  # JSONDecodeError and TOMLDecodeError
            raise PlacerError(f"cannot parse {path} ({exc.__class__.__name__})",
                              EXIT_INPUT) from None
        if raw is None:
            continue
        if not isinstance(raw, dict) or not raw.get("command"):
            raise PlacerError(f"server {name!r} in {path} is not a stdio server "
                              "(no 'command')", EXIT_INPUT)
        return ServerEntry(
            command=expand(str(raw["command"]), environ),
            args=[expand(str(a), environ) for a in raw.get("args") or []],
            env={str(k): expand(str(v), environ)
                 for k, v in (raw.get("env") or {}).items()},
            source=str(path),
        )
    raise PlacerError(f"no MCP server named {name!r} in: "
                      + ", ".join(str(c) for c in candidates), EXIT_INPUT)


_SECRET_FLAG = re.compile(r"token|key|secret|password", re.IGNORECASE)


def secrets_of(entry: ServerEntry) -> list[str]:
    """Values to hide: every env value and the value of a secret-looking flag."""
    secrets = list(entry.env.values())
    args = entry.args
    for i, arg in enumerate(args):
        if not arg.startswith("-"):
            continue
        name, equals, value = arg.lstrip("-").partition("=")
        if not _SECRET_FLAG.search(name):
            continue
        if equals:
            secrets.append(value)
        elif i + 1 < len(args):
            secrets.append(args[i + 1])
    return secrets


def redact(text: str, secrets: list[str]) -> str:
    """Replace every secret value, and any URL, with ***."""
    for secret in sorted({s for s in secrets if len(s) >= 4}, key=len, reverse=True):
        text = text.replace(secret, "***")
    return _URL.sub("***", text)


# ----------------------------------------------------------------- geometry

def box_of(a: list[int], b: list[int]) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]),
            max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]))


def volume(box: Box) -> int:
    return (box[3] - box[0] + 1) * (box[4] - box[1] + 1) * (box[5] - box[2] + 1)


def chunks(box: Box) -> int:
    """16x16 chunk columns the box's x/z footprint touches."""
    return ((box[3] >> 4) - (box[0] >> 4) + 1) * ((box[5] >> 4) - (box[2] >> 4) + 1)


def union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes))


def halve(box: Box) -> tuple[Box, Box]:
    """Split a box in two across its longest axis."""
    sizes = [box[3] - box[0], box[4] - box[1], box[5] - box[2]]
    axis = sizes.index(max(sizes))
    mid = (box[axis] + box[axis + 3]) // 2
    first, second = list(box), list(box)
    first[axis + 3] = mid
    second[axis] = mid + 1
    return tuple(first), tuple(second)  # type: ignore[return-value]


def tile(box: Box, cap: int) -> list[Box]:
    """Cover `box` with boxes of at most `cap` cells."""
    if volume(box) <= cap:
        return [box]
    first, second = halve(box)
    return tile(first, cap) + tile(second, cap)


def column_tiles(box: Box, max_columns: int = 1024,
                 max_cells: int = 200_000) -> list[Box]:
    """Cover `box` with x/z rectangles that keep its full y range.

    Each tile has at most `max_columns` columns and `max_cells` cells."""
    height = box[4] - box[1] + 1
    cap = max(1, min(max_columns, max_cells // height))
    width, depth = box[3] - box[0] + 1, box[5] - box[2] + 1
    if width * depth <= cap:
        return [box]
    step_x = min(width, cap)
    step_z = max(1, min(depth, cap // step_x))
    return [(x, box[1], z, min(x + step_x - 1, box[3]), box[4],
             min(z + step_z - 1, box[5]))
            for x in range(box[0], box[3] + 1, step_x)
            for z in range(box[2], box[5] + 1, step_z)]


# -------------------------------------------------------------------- input

def _coords(value: Any, where: str, limits: Limits) -> None:
    if (not isinstance(value, list) or len(value) != 3
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
        raise PlacerError(f"{where}: expected [x, y, z] integers", EXIT_INPUT)
    if not limits.min_y <= value[1] <= limits.max_y:
        raise PlacerError(f"{where}: y={value[1]} is outside "
                          f"{limits.min_y}..{limits.max_y}", EXIT_INPUT)


def _block(value: Any, where: str) -> None:
    if not isinstance(value, str) or not value.startswith("minecraft:"):
        raise PlacerError(f"{where}: expected a 'minecraft:' block state string",
                          EXIT_INPUT)


def load_build(path: Path, limits: Limits) -> dict[str, Any]:
    """Read and validate a phase file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlacerError(f"cannot read {path}: {exc}", EXIT_INPUT) from None
    if isinstance(data, list):
        data = {"fills": data}
    if not isinstance(data, dict):
        raise PlacerError(f"{path}: expected an mc_build object or a list of fills",
                          EXIT_INPUT)
    if "text" in data:
        raise PlacerError(f"{path}: 'text' (lettering) is not accepted here; "
                          "place it with the client's own mc_build call", EXIT_INPUT)
    if "snapshot" in data:
        raise PlacerError(f"{path}: remove 'snapshot' and use --snapshot instead",
                          EXIT_INPUT)
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise PlacerError(f"{path}: unknown keys {unknown}", EXIT_INPUT)
    fills, blocks = data.get("fills") or [], data.get("blocks") or []
    if not fills and not blocks:
        raise PlacerError(f"{path}: nothing to place", EXIT_INPUT)
    for i, fill in enumerate(fills):
        where = f"fills[{i}]"
        if not isinstance(fill, dict):
            raise PlacerError(f"{where}: expected an object", EXIT_INPUT)
        _coords(fill.get("from"), f"{where}.from", limits)
        _coords(fill.get("to"), f"{where}.to", limits)
        _block(fill.get("block"), f"{where}.block")
        if fill.get("mode", "replace") not in FILL_MODES:
            raise PlacerError(f"{where}.mode: must be one of {sorted(FILL_MODES)}",
                              EXIT_INPUT)
    for i, block in enumerate(blocks):
        where = f"blocks[{i}]"
        if not isinstance(block, dict):
            raise PlacerError(f"{where}: expected an object", EXIT_INPUT)
        _coords(block.get("pos"), f"{where}.pos", limits)
        _block(block.get("block"), f"{where}.block")
    return {**data, "fills": fills, "blocks": blocks}


# ------------------------------------------------------------------- paging

def split_fill(fill: dict[str, Any], limits: Limits) -> list[dict[str, Any]]:
    """Split a fill that is too big for one call; shell fills cannot be split."""
    box = box_of(fill["from"], fill["to"])
    if volume(box) <= limits.max_blocks and chunks(box) <= limits.max_chunks:
        return [fill]
    mode = fill.get("mode", "replace")
    if mode in SHELL_MODES:
        raise PlacerError(f"a '{mode}' fill over the per-call limit cannot be split "
                          "without changing its shape; split it into separate fills "
                          "in the phase file", EXIT_REFUSED)
    pieces: list[dict[str, Any]] = []
    for half in halve(box):
        pieces += split_fill({**fill, "from": list(half[:3]), "to": list(half[3:])},
                             limits)
    return pieces


def _pack(items: list[tuple[dict[str, Any], Box]],
          limits: Limits) -> list[list[tuple[dict[str, Any], Box]]]:
    """Order-preserving packing within the block, chunk and entry limits."""
    groups: list[list[tuple[dict[str, Any], Box]]] = []
    current: list[tuple[dict[str, Any], Box]] = []
    cells = 0
    merged: Box | None = None
    for item, box in items:
        size = volume(box)
        grown = box if merged is None else union([merged, box])
        if current and (cells + size > limits.max_blocks
                        or chunks(grown) > limits.max_chunks
                        or len(current) >= limits.max_ops):
            groups.append(current)
            current, cells, grown = [], 0, box
        current.append((item, box))
        cells += size
        merged = grown
    if current:
        groups.append(current)
    return groups


def make_pages(build: dict[str, Any], limits: Limits) -> list[Page]:
    """Pages in mc_build's own order: every fill page before any block page."""
    shared = {k: build[k] for k in ("liquids", "connect", "world") if k in build}
    fills = [(piece, box_of(piece["from"], piece["to"]))
             for fill in build["fills"] for piece in split_fill(fill, limits)]
    blocks = [(block, box_of(block["pos"], block["pos"])) for block in build["blocks"]]
    pages: list[Page] = []
    for kind, items in (("fills", fills), ("blocks", blocks)):
        for group in _pack(items, limits):
            pages.append(Page(args={**shared, kind: [item for item, _ in group]},
                              box=union([box for _, box in group]),
                              cells=sum(volume(box) for _, box in group)))
    return pages


def plan_summary(build: dict[str, Any], limits: Limits,
                 path: Path) -> tuple[dict[str, Any], list[Page], list[Box]]:
    """Pages, snapshot tiles and a JSON-ready summary for one phase file."""
    pages = make_pages(build, limits)
    whole = union([page.box for page in pages])
    tiles = tile(whole, limits.snapshot_volume)
    summary = {
        "file": str(path),
        "bbox": {"from": list(whole[:3]), "to": list(whole[3:])},
        "cells": sum(page.cells for page in pages),
        "chunks": chunks(whole),
        "y_range": [whole[1], whole[4]],
        "pages": [{"kind": "fills" if "fills" in page.args else "blocks",
                   "entries": len(page.args.get("fills") or page.args.get("blocks")),
                   "cells": page.cells} for page in pages],
        "snapshot_tiles": len(tiles),
    }
    return summary, pages, tiles


# ------------------------------------------------------- players and replies

PLAYER_LINE = re.compile(r"^(?P<name>\S+)\s+(?P<world>\S+)\s+pos x=(?P<x>-?\d+) "
                         r"y=(?P<y>-?\d+) z=(?P<z>-?\d+)")
SNAPSHOT_ID = re.compile(r"^Snapshot (\S+) created")


def parse_players(text: str) -> list[tuple[str, str, int, int, int]]:
    """Parse mc_players text; refuse anything unexpected."""
    if not text.strip():
        raise PlacerError("could not read the player list (empty mc_players "
                          "reply); refusing to build", EXIT_PLAYER)
    if text.strip() == "No players online.":
        return []
    players = []
    for line in text.strip().splitlines():
        match = PLAYER_LINE.match(line.strip())
        if not match:
            raise PlacerError("cannot read the mc_players output; refusing to build",
                              EXIT_PLAYER)
        players.append((match["name"], match["world"], int(match["x"]),
                        int(match["y"]), int(match["z"])))
    return players


def players_inside(players: list[tuple[str, str, int, int, int]], box: Box,
                   margin: int, world: str | None) -> list[str]:
    """Names of players inside `box` grown by `margin` (same world when given)."""
    x1, y1, z1, x2, y2, z2 = box
    return [name for name, player_world, x, y, z in players
            if (world is None or player_world == world)
            and x1 - margin <= x <= x2 + margin
            and y1 - margin <= y <= y2 + margin
            and z1 - margin <= z <= z2 + margin]


def snapshot_id(text: str, secrets: list[str] | None = None) -> str:
    match = SNAPSHOT_ID.match(text.strip())
    if not match:
        raise PlacerError("unexpected mc_snapshot reply: "
                          + redact(text[:200], secrets or []), EXIT_SERVER)
    return match.group(1)


def result_lines(text: str) -> list[str]:
    """Reply lines for the report: keep indented detail, drop WARNINGS blocks."""
    kept, in_warnings = [], False
    for line in text.splitlines():
        if line.startswith("WARNINGS"):
            in_warnings = True
        elif in_warnings and line.startswith("  "):
            pass
        else:
            in_warnings = False
            if line.strip():
                kept.append(line)
    return kept[:10]


def warnings_of(text: str) -> list[str]:
    """The indented lines of mc_build's WARNINGS section."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("WARNINGS"):
            return [w.strip() for w in lines[i + 1:] if w.startswith("  ")]
    return []


# ------------------------------------------------------------------- client

class McpClient:
    """Minimal MCP client for one stdio server process."""

    def __init__(self, entry: ServerEntry, start_timeout: float = 120.0,
                 call_timeout: float = 600.0) -> None:
        self.secrets = secrets_of(entry)
        self.call_timeout = call_timeout
        self._stderr: deque[str] = deque(maxlen=40)
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        try:
            self.proc = subprocess.Popen(
                [entry.command, *entry.args], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, **entry.env}, text=True, encoding="utf-8",
                errors="replace", bufsize=1)
        except OSError as exc:
            raise PlacerError(f"cannot start the MCP server ({exc.__class__.__name__})",
                              EXIT_SERVER) from None
        self._out = threading.Thread(target=self._pump_stdout, daemon=True)
        self._err = threading.Thread(target=self._pump_stderr, daemon=True)
        self._out.start()
        self._err.start()
        try:
            self._request("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "ashlar-place", "version": "1"}}, start_timeout)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except PlacerError:
            self.close()
            raise

    def _pump_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _pump_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip("\n"))

    def redact(self, text: str) -> str:
        return redact(text, self.secrets)

    def stderr_tail(self) -> str:
        return self.redact("\n".join(self._stderr))

    def _died(self, what: str) -> PlacerError:
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        self._err.join(timeout=2)
        return PlacerError(f"{what}:\n{self.stderr_tail()}", EXIT_SERVER)

    def _send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except OSError:
            raise self._died("the MCP server exited early") from None

    def _request(self, method: str, params: dict[str, Any],
                 timeout: float) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method,
                    "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlacerError(f"timed out waiting for {method}", EXIT_SERVER)
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise self._died("the MCP server exited")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if (not isinstance(message, dict) or "method" in message
                    or message.get("id") != request_id):
                continue  # server requests, notifications, anything not our reply
            if "error" in message:
                detail = str((message.get("error") or {}).get("message"))
                raise PlacerError(f"{method} failed: {self.redact(detail)}",
                                  EXIT_SERVER)
            return message.get("result") or {}

    def call(self, tool: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Call a tool; return its raw text and whether it reported an error.

        The text is unredacted so it can be parsed; pass it through `redact`
        before it is printed, logged or put in a message."""
        result = self._request("tools/call", {"name": tool, "arguments": arguments},
                               self.call_timeout)
        text = "\n".join(item.get("text", "") for item in result.get("content") or []
                         if isinstance(item, dict) and item.get("type") == "text")
        return text, bool(result.get("isError"))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ------------------------------------------------------ column reading

Runs = list[tuple[int, int, str]]
_COLUMN = re.compile(r"^(-?\d+),(-?\d+):\s*(.*)$")
_RUN = re.compile(r"^(-?\d+)(?:-(-?\d+))?\s+(\S+)$")


def parse_columns(text: str) -> dict[tuple[int, int], Runs]:
    """Parse `mc_inspect` `columns` output into {(x, z): [(y1, y2, state), ...]}."""
    columns: dict[tuple[int, int], Runs] = {}
    for line in text.splitlines():
        head = _COLUMN.match(line.strip())
        if not head:
            continue
        runs: Runs = []
        for part in head[3].split(" | "):
            run = _RUN.match(part.strip())
            if not run:
                raise PlacerError(f"cannot parse inspect run {part!r} in column "
                                  f"{head[1]},{head[2]}", EXIT_SERVER)
            state = run[3] if ":" in run[3].split("[")[0] else "minecraft:" + run[3]
            runs.append((int(run[1]), int(run[2] or run[1]), state))
        columns[(int(head[1]), int(head[2]))] = runs
    return columns


def read_columns(client: "McpClient", box: Box, world: str | None) -> dict[tuple[int, int], Runs]:
    """Read the exact block runs of every column in `box` through `mc_inspect`."""
    columns: dict[tuple[int, int], Runs] = {}
    for part in column_tiles(box):
        args: dict[str, Any] = {"from": list(part[:3]), "to": list(part[3:]),
                                "format": "columns"}
        if world is not None:
            args["world"] = world
        text, is_error = client.call("mc_inspect", args)
        if is_error:
            raise PlacerError("mc_inspect failed: " + client.redact(text), EXIT_SERVER)
        columns.update(parse_columns(text))
    return columns


# --------------------------------------------------------- check and place

def _server(ns: argparse.Namespace) -> ServerEntry:
    return find_server(ns.server, ns.config, Path.cwd(), Path.home(), dict(os.environ))


def cmd_check(ns: argparse.Namespace) -> int:
    entry = _server(ns)
    client = McpClient(entry)
    try:
        text, is_error = client.call("mc_status", {})
    finally:
        client.close()
    print(f"server entry {ns.server!r} from {entry.source}")
    print(client.redact(text))
    return EXIT_SERVER if is_error else EXIT_OK


def _emit(report: dict[str, Any], log: str | None) -> None:
    text = json.dumps(report, indent=2)
    print(text)
    if log:
        try:
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            print(f"ashlar_place: warning: could not write the log "
                  f"({exc.__class__.__name__}: {exc.strerror})", file=sys.stderr)


def cmd_place(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.file)
    build = load_build(path, limits)
    _, pages, tiles = plan_summary(build, limits, path)
    world = ns.world or build.get("world")
    if ns.world:
        for page in pages:
            page.args["world"] = ns.world
    if ns.snapshot and len(tiles) > ns.max_snapshots:
        raise PlacerError(f"this file needs {len(tiles)} snapshots (limit "
                          f"{ns.max_snapshots}); split it into smaller phase files",
                          EXIT_REFUSED)
    entry = _server(ns)
    report: dict[str, Any] = {"file": str(path), "pages_total": len(pages),
                              "pages_done": 0, "snapshots": [], "warnings": [],
                              "results": [], "error": None}
    client = McpClient(entry)
    try:
        text, is_error = client.call("mc_players", {})
        if is_error:
            raise PlacerError("mc_players failed: " + client.redact(text),
                              EXIT_SERVER)
        whole = union([page.box for page in pages])
        inside = players_inside(parse_players(text), whole, ns.player_margin, world)
        if inside:
            raise PlacerError("players inside the build area: " + ", ".join(inside),
                              EXIT_PLAYER)
        for i, box in enumerate(tiles if ns.snapshot else [], 1):
            args: dict[str, Any] = {"action": "create", "from": list(box[:3]),
                                    "to": list(box[3:]),
                                    "label": f"{ns.label} {i}/{len(tiles)}"}
            if world:
                args["world"] = world
            text, is_error = client.call("mc_snapshot", args)
            if is_error:
                raise PlacerError("mc_snapshot failed: " + client.redact(text),
                                  EXIT_SERVER)
            report["snapshots"].append(
                client.redact(snapshot_id(text, client.secrets)))
        for i, page in enumerate(pages, 1):
            text, is_error = client.call("mc_build", page.args)
            if is_error:
                raise PlacerError(f"mc_build failed on page {i}/{len(pages)}: "
                                  + client.redact(text), EXIT_SERVER)
            report["pages_done"] = i
            report["warnings"] += [client.redact(w) for w in warnings_of(text)]
            report["results"].append({"page": i, "result": [
                client.redact(line) for line in result_lines(text)]})
    except PlacerError as exc:
        report["error"] = str(exc)
        _emit(report, ns.log)
        raise
    finally:
        client.close()
    _emit(report, ns.log)
    return EXIT_OK


def cmd_read(ns: argparse.Namespace) -> int:
    limits = Limits()
    a, b = [ns.x1, ns.y1, ns.z1], [ns.x2, ns.y2, ns.z2]
    _coords(a, "from", limits)
    _coords(b, "to", limits)
    box = box_of(a, b)
    client = McpClient(_server(ns))
    try:
        columns = read_columns(client, box, ns.world)
    finally:
        client.close()
    cells: dict[str, str] = {}
    for (x, z), runs in columns.items():
        for y1, y2, state in runs:
            for y in range(y1, y2 + 1):
                cells[f"{x},{y},{z}"] = state
    if len(cells) != volume(box) or any(
            f"{x},{y},{z}" not in cells
            for x in range(box[0], box[3] + 1) for z in range(box[2], box[5] + 1)
            for y in range(box[1], box[4] + 1)):
        raise PlacerError(f"mc_inspect returned {len(cells)} of {volume(box)} cells",
                          EXIT_SERVER)
    try:
        Path(ns.out).write_text(json.dumps({
            "world": ns.world, "from": list(box[:3]), "to": list(box[3:]),
            "cells": cells}), encoding="utf-8")
    except OSError as exc:
        raise PlacerError(f"cannot write {ns.out} ({exc.__class__.__name__})",
                          EXIT_INPUT) from None
    print(f"read {len(cells)} cells in {len(column_tiles(box))} calls -> {ns.out}")
    return EXIT_OK


# ---------------------------------------------------------------------- cli

def _add_limits(parser: argparse.ArgumentParser) -> None:
    defaults = Limits()
    parser.add_argument("--max-blocks", type=int, default=defaults.max_blocks)
    parser.add_argument("--max-chunks", type=int, default=defaults.max_chunks)
    parser.add_argument("--max-ops", type=int, default=defaults.max_ops)
    parser.add_argument("--snapshot-volume", type=int, default=defaults.snapshot_volume)
    parser.add_argument("--min-y", type=int, default=defaults.min_y)
    parser.add_argument("--max-y", type=int, default=defaults.max_y)


def _limits(ns: argparse.Namespace) -> Limits:
    return Limits(ns.max_blocks, ns.max_chunks, ns.max_ops, ns.snapshot_volume,
                  ns.min_y, ns.max_y)


def cmd_plan(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.file)
    summary, _, _ = plan_summary(load_build(path, limits), limits, path)
    print(json.dumps(summary, indent=2))
    return EXIT_OK


def _add_server(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server", default="ashlar",
                        help="MCP server name in the client config (default ashlar)")
    parser.add_argument("--config", help="read this config file instead")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashlar_place.py",
        description="Send generated Minecraft geometry through Ashlar.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="connect and run mc_status")
    _add_server(check)

    plan = sub.add_parser("plan", help="validate a phase file offline")
    plan.add_argument("file")
    _add_limits(plan)

    place = sub.add_parser("place", help="snapshot and place a phase file")
    place.add_argument("file")
    _add_limits(place)
    _add_server(place)
    choice = place.add_mutually_exclusive_group(required=True)
    choice.add_argument("--snapshot", action="store_true")
    choice.add_argument("--no-snapshot", action="store_true")
    place.add_argument("--label", default="ashlar_place")
    place.add_argument("--world")
    place.add_argument("--player-margin", type=int, default=2)
    place.add_argument("--max-snapshots", type=int, default=15)
    place.add_argument("--log")

    read = sub.add_parser("read", help="write a box's exact block states to JSON")
    for name in ("x1", "y1", "z1", "x2", "y2", "z2"):
        read.add_argument(name, type=int)
    read.add_argument("--out", required=True)
    read.add_argument("--world")
    _add_server(read)
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "plan": cmd_plan, "place": cmd_place,
                "read": cmd_read}
    try:
        return handlers[ns.cmd](ns)
    except PlacerError as exc:
        print(f"ashlar_place: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
