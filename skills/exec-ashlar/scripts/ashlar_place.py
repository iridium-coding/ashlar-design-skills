#!/usr/bin/env python3
"""Send generated Minecraft geometry to a Paper server through Ashlar.

Starts the `ashlar-mcp` server the same way the client config does (Claude
Code `~/.claude.json`, a project `.mcp.json`, or Codex `~/.codex/config.toml`),
speaks MCP over stdio, and sends a phase file as paged `mc_build` calls after a
player check and snapshots.

  ashlar_place.py check  [--server NAME] [--config PATH]
  ashlar_place.py plan   FILE [limit options]
  ashlar_place.py place  FILE (--snapshot [--label L] | --no-snapshot | --backup DIR)
                         [--world W] [--player-margin 2] [--max-snapshots 15]
                         [--log PATH] [--server NAME] [--config PATH] [limit options]
  ashlar_place.py read   X1 Y1 Z1 X2 Y2 Z2 --out FILE [--world W]
                         [--server NAME] [--config PATH]
  ashlar_place.py backup --box X1 Y1 Z1 X2 Y2 Z2 --out DIR [--world W]
                         [--log PATH] [--server NAME] [--config PATH] [limit options]
  ashlar_place.py restore DIR [--world W] [--player-margin 2] [--log PATH]
                         [--server NAME] [--config PATH] [limit options]

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
import gzip
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
import tomllib
from datetime import datetime, timezone
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
    max_flowing: int = 2000


@dataclass
class Page:
    args: dict[str, Any]
    box: Box
    cells: int
    liquid: int = 0


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
    return validate_build(data, limits, str(path))


def validate_build(data: dict[str, Any], limits: Limits, where: str) -> dict[str, Any]:
    """Validate an mc_build arguments object; `where` names it in messages."""
    path = where
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
        item = f"fills[{i}]"
        if not isinstance(fill, dict):
            raise PlacerError(f"{item}: expected an object", EXIT_INPUT)
        _coords(fill.get("from"), f"{item}.from", limits)
        _coords(fill.get("to"), f"{item}.to", limits)
        _block(fill.get("block"), f"{item}.block")
        if "filter" in fill:
            _block(fill["filter"], f"{item}.filter")
        if fill.get("mode", "replace") not in FILL_MODES:
            raise PlacerError(f"{item}.mode: must be one of {sorted(FILL_MODES)}",
                              EXIT_INPUT)
    for i, block in enumerate(blocks):
        item = f"blocks[{i}]"
        if not isinstance(block, dict):
            raise PlacerError(f"{item}: expected an object", EXIT_INPUT)
        _coords(block.get("pos"), f"{item}.pos", limits)
        _block(block.get("block"), f"{item}.block")
    return {**data, "fills": fills, "blocks": blocks}


# ------------------------------------------------------------------- paging

LIQUIDS = {"minecraft:water", "minecraft:lava"}


def is_liquid(state: str) -> bool:
    return state.split("[")[0] in LIQUIDS


def split_fill(fill: dict[str, Any], limits: Limits,
               flowing: bool = False) -> list[dict[str, Any]]:
    """Split a fill that is too big for one call; shell fills cannot be split.

    With `flowing`, a water or lava fill is also split to `max_flowing` cells."""
    box = box_of(fill["from"], fill["to"])
    cap_liquid = flowing and is_liquid(fill["block"])
    if (volume(box) <= limits.max_blocks and chunks(box) <= limits.max_chunks
            and not (cap_liquid and volume(box) > max(1, limits.max_flowing))):
        return [fill]
    mode = fill.get("mode", "replace")
    if mode in SHELL_MODES:
        raise PlacerError(f"a '{mode}' fill over the per-call limit cannot be split "
                          "without changing its shape; split it into separate fills "
                          "in the phase file", EXIT_REFUSED)
    pieces: list[dict[str, Any]] = []
    for half in halve(box):
        pieces += split_fill({**fill, "from": list(half[:3]), "to": list(half[3:])},
                             limits, flowing)
    return pieces


def _liquid_cells(item: dict[str, Any], box: Box) -> int:
    return volume(box) if is_liquid(item["block"]) else 0


def _pack(items: list[tuple[dict[str, Any], Box]], limits: Limits,
          flowing: bool = False) -> list[list[tuple[dict[str, Any], Box]]]:
    """Order-preserving packing within the block, chunk, entry and flowing limits."""
    groups: list[list[tuple[dict[str, Any], Box]]] = []
    current: list[tuple[dict[str, Any], Box]] = []
    cells = liquid = 0
    merged: Box | None = None
    for item, box in items:
        size = volume(box)
        wet = _liquid_cells(item, box)
        grown = box if merged is None else union([merged, box])
        if current and (cells + size > limits.max_blocks
                        or chunks(grown) > limits.max_chunks
                        or len(current) >= limits.max_ops
                        or (flowing and liquid + wet > limits.max_flowing)):
            groups.append(current)
            current, cells, liquid, grown = [], 0, 0, box
        current.append((item, box))
        cells += size
        liquid += wet
        merged = grown
    if current:
        groups.append(current)
    return groups


def make_pages(build: dict[str, Any], limits: Limits) -> list[Page]:
    """Pages in mc_build's own order: every fill page before any block page."""
    shared = {k: build[k] for k in ("liquids", "connect", "world") if k in build}
    flowing = build.get("liquids") == "flow"
    fills = [(piece, box_of(piece["from"], piece["to"]))
             for fill in build["fills"] for piece in split_fill(fill, limits, flowing)]
    blocks = [(block, box_of(block["pos"], block["pos"])) for block in build["blocks"]]
    pages: list[Page] = []
    for kind, items in (("fills", fills), ("blocks", blocks)):
        for group in _pack(items, limits, flowing):
            pages.append(Page(args={**shared, kind: [item for item, _ in group]},
                              box=union([box for _, box in group]),
                              cells=sum(volume(box) for _, box in group),
                              liquid=sum(_liquid_cells(item, box) for item, box in group)))
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
        "liquid_cells": sum(page.liquid for page in pages),
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
Columns = dict[tuple[int, int], Runs]
_COLUMN = re.compile(r"^(-?\d+),(-?\d+):\s*(.*)$")
_RUN = re.compile(r"^(-?\d+)(?:-(-?\d+))?\s+(\S+)$")


def parse_columns(text: str) -> Columns:
    """Parse `mc_inspect` `columns` output into {(x, z): [(y1, y2, state), ...]}."""
    columns: Columns = {}
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


def read_columns(client: "McpClient", box: Box, world: str | None) -> Columns:
    """Read the exact block runs of every column in `box` through `mc_inspect`."""
    columns: Columns = {}
    for part in column_tiles(box):
        args: dict[str, Any] = {"from": list(part[:3]), "to": list(part[3:]),
                                "format": "columns"}
        if world is not None:
            args["world"] = world
        text, is_error = client.call("mc_inspect", args)
        if is_error:
            raise PlacerError("mc_inspect failed: " + client.redact(text), EXIT_SERVER)
        try:
            columns.update(parse_columns(text))
        except PlacerError as exc:
            raise PlacerError(client.redact(str(exc)), exc.code) from None
    return columns


# ------------------------------------------------------------ height reads

HEIGHT_TYPES = (("ground", "SOLID"), ("surface", "SOLID_OR_LIQUID_NO_LEAVES"),
                ("top", "ANY"))
SURVEY_CELLS = 200_000
_MATRIX_HEAD = re.compile(r"top-left\s*=\s*x=(-?\d+)\s+z=(-?\d+)")
_MATRIX_ROW = re.compile(r"^z=(-?\d+):\s*(.*)$")


def parse_matrix(text: str) -> tuple[int, dict[int, list[int | None]]]:
    """Parse `mc_survey` matrix text into (top-left x, {z: row}); non-integers are None."""
    head = _MATRIX_HEAD.search(text)
    if not head:
        raise PlacerError("mc_survey reply has no height matrix header", EXIT_SERVER)
    rows: dict[int, list[int | None]] = {}
    for line in text.splitlines():
        row = _MATRIX_ROW.match(line.strip())
        if row:
            rows[int(row[1])] = [int(t) if re.fullmatch(r"-?\d+", t) else None
                                 for t in row[2].split()]
    return int(head[1]), rows


def height_tiles(area: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    """Cover an x/z area with bands of whole z rows of at most 200,000 cells."""
    x1, z1, x2, z2 = area
    width = x2 - x1 + 1
    if width > SURVEY_CELLS:
        raise PlacerError(f"area is {width} cells wide; the most one mc_survey row "
                          f"can read is {SURVEY_CELLS}", EXIT_INPUT)
    rows = SURVEY_CELLS // width
    return [(x1, z, x2, min(z + rows - 1, z2)) for z in range(z1, z2 + 1, rows)]


def read_heights(client: "McpClient", area: tuple[int, int, int, int],
                 world: str | None) -> dict[str, Any]:
    """Read ground, surface and top heights of an x/z area as a heights file (F2)."""
    x1, z1, x2, z2 = area
    nx, nz = x2 - x1 + 1, z2 - z1 + 1
    grids: dict[str, list[int | None]] = {k: [None] * (nx * nz) for k, _ in HEIGHT_TYPES}
    for part in height_tiles(area):
        for key, kind in HEIGHT_TYPES:
            args: dict[str, Any] = {"from": [part[0], part[1]], "to": [part[2], part[3]],
                                    "type": kind, "matrix": True}
            if world is not None:
                args["world"] = world
            text, is_error = client.call("mc_survey", args)
            if is_error:
                raise PlacerError("mc_survey failed: " + client.redact(text), EXIT_SERVER)
            try:
                left, rows = parse_matrix(text)
            except PlacerError as exc:
                raise PlacerError(client.redact(str(exc)), exc.code) from None
            if left != part[0]:
                raise PlacerError(f"mc_survey matrix starts at x={left}, "
                                  f"not {part[0]}", EXIT_SERVER)
            for z in range(part[1], part[3] + 1):
                row = rows.get(z)
                if row is None or len(row) != nx:
                    raise PlacerError(f"mc_survey matrix is missing or short at z={z}",
                                      EXIT_SERVER)
                for xi, value in enumerate(row):
                    grids[key][xi * nz + (z - z1)] = value
    return {"version": 1, "world": world, "origin": [x1, z1], "size": [nx, nz], **grids}


# ------------------------------------------------------------------ backups

PLUGIN_VERSION = re.compile(r"^Plugin version:\s*(\S+)", re.MULTILINE)


def check_complete(columns: Columns, box: Box) -> None:
    """Every column of `box` is present with contiguous runs over its full y range."""
    for x in range(box[0], box[3] + 1):
        for z in range(box[2], box[5] + 1):
            runs = columns.get((x, z))
            if not runs:
                raise PlacerError(f"column {x},{z} is missing from the read",
                                  EXIT_REFUSED)
            expected = box[1]
            for y1, y2, _ in runs:
                if y1 != expected or y2 < y1:
                    raise PlacerError(f"column {x},{z} has a gap or overlap at "
                                      f"y={expected}", EXIT_REFUSED)
                expected = y2 + 1
            if expected != box[4] + 1:
                raise PlacerError(f"column {x},{z} covers y={box[1]}..{expected - 1}, "
                                  f"not {box[1]}..{box[4]}", EXIT_REFUSED)


def restore_build(columns: Columns, world: str | None) -> dict[str, Any]:
    """mc_build arguments that put `columns` back exactly.

    One fill per run; runs equal in (z, y1, y2, state) at consecutive x merge."""
    fills: list[dict[str, Any]] = []
    open_fill: dict[tuple[int, int, int, str], dict[str, Any]] = {}
    for (x, z) in sorted(columns, key=lambda key: (key[1], key[0])):
        for y1, y2, state in columns[(x, z)]:
            key = (z, y1, y2, state)
            current = open_fill.get(key)
            if current is not None and current["to"][0] == x - 1:
                current["to"][0] = x
            else:
                current = {"from": [x, y1, z], "to": [x, y2, z], "block": state}
                open_fill[key] = current
                fills.append(current)
    args: dict[str, Any] = {"fills": fills, "blocks": [], "liquids": "static",
                            "connect": False}
    if world is not None:
        args["world"] = world
    return args


def encode_columns(payload: dict[str, Any]) -> bytes:
    """The exact bytes of columns.json.gz (format F1): gzip of compact sorted JSON."""
    return gzip.compress(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                         .encode("utf-8"), mtime=0)


def _manifest_complete(path: Path) -> bool:
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("complete") is True


def refuse_existing_backup(out: Path) -> None:
    if _manifest_complete(out):
        raise PlacerError(f"{out} already holds a complete backup; "
                          "choose another folder", EXIT_REFUSED)


def write_backup(out: Path, box: Box, world: str | None, columns: Columns,
                 plugin: str | None) -> dict[str, Any]:
    """Write backup format F1 into `out` and return the manifest.

    Byte-exact format (the terrain toolkit writes the same bytes):
      columns.json.gz = gzip.compress(json.dumps(payload, sort_keys=True,
          separators=(",", ":")).encode("utf-8"), mtime=0), payload =
          {"version": 1, "world": world, "box": [x1, y1, z1, x2, y2, z2],
           "columns": {"<x>,<z>": [[y1, y2, state], ...]}}
      manifest.json = json.dumps(manifest, indent=2, sort_keys=True) + "\n",
          manifest = {"version": 1, "box": [...], "world": world, "created":
          "YYYY-MM-DDTHH:MM:SSZ" (UTC), "columns": count, "sha256": hex digest of
          the exact columns.json.gz bytes, "plugin": str | None, "complete": true}
    Both files go to temporary names first and are renamed into place, the
    manifest last, so a folder without a manifest is never a complete backup."""
    check_complete(columns, box)
    payload = {"version": 1, "world": world, "box": list(box),
               "columns": {f"{x},{z}": [[y1, y2, state] for y1, y2, state in columns[(x, z)]]
                           for x in range(box[0], box[3] + 1)
                           for z in range(box[2], box[5] + 1)}}
    blob = encode_columns(payload)
    manifest = {"version": 1, "box": list(box), "world": world,
                "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "columns": len(payload["columns"]),
                "sha256": hashlib.sha256(blob).hexdigest(), "plugin": plugin,
                "complete": True}
    temps = [out / ".columns.json.gz.tmp", out / ".manifest.json.tmp"]
    try:
        out.mkdir(parents=True, exist_ok=True)
        temps[0].write_bytes(blob)
        temps[1].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        temps[0].replace(out / "columns.json.gz")
        temps[1].replace(out / "manifest.json")
    except OSError as exc:
        for temp in temps:
            temp.unlink(missing_ok=True)
        raise PlacerError(f"cannot write the backup in {out} "
                          f"({exc.__class__.__name__})", EXIT_INPUT) from None
    return manifest


def load_backup(path: Path) -> tuple[dict[str, Any], Columns]:
    """Read and verify a backup folder (checksum, shape, complete runs)."""
    def bad(why: str) -> PlacerError:
        return PlacerError(f"{path}: {why}", EXIT_INPUT)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        blob = (path / "columns.json.gz").read_bytes()
    except (OSError, ValueError) as exc:
        raise bad(f"cannot read the backup ({exc.__class__.__name__})") from None
    if not isinstance(manifest, dict) or manifest.get("complete") is not True:
        raise bad("not a complete backup")
    if hashlib.sha256(blob).hexdigest() != manifest.get("sha256"):
        raise bad("columns.json.gz does not match the manifest checksum")
    try:
        payload = json.loads(gzip.decompress(blob))
        box = tuple(manifest["box"])
        if (len(box) != 6 or payload["version"] != 1
                or list(box) != payload["box"]):
            raise ValueError("box or version mismatch")
        columns: Columns = {}
        for key, runs in payload["columns"].items():
            x, z = key.split(",")
            columns[(int(x), int(z))] = [(int(y1), int(y2), str(state))
                                         for y1, y2, state in runs]
    except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
        raise bad(f"malformed backup ({exc.__class__.__name__})") from None
    if len(columns) != manifest.get("columns"):
        raise bad("column count does not match the manifest")
    try:
        check_complete(columns, box)  # type: ignore[arg-type]
    except PlacerError as exc:
        raise bad(str(exc)) from None
    return manifest, columns


def _restore_pages(columns: Columns, world: str | None,
                   limits: Limits, where: str) -> list[Page]:
    """Validated, paged restore fills; refusals here are exit 3."""
    try:
        build = validate_build(restore_build(columns, world), limits, where)
    except PlacerError as exc:
        raise PlacerError(str(exc), EXIT_REFUSED if exc.code == EXIT_INPUT
                          else exc.code) from None
    return make_pages(build, limits)


def take_backup(client: "McpClient", box: Box, world: str | None, out: Path,
                limits: Limits) -> dict[str, Any]:
    """Read `box` column by column and write a backup; nothing is written unless
    the read is complete and the restore fills pass validation and paging."""
    text, is_error = client.call("mc_status", {})
    if is_error:
        raise PlacerError("mc_status failed: " + client.redact(text), EXIT_SERVER)
    found = PLUGIN_VERSION.search(text)
    plugin = client.redact(found.group(1)) if found else None
    columns = read_columns(client, box, world)
    check_complete(columns, box)
    _restore_pages(columns, world, limits, "the restore fills")
    return write_backup(out, box, world, columns, plugin)


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


def _check_players(client: McpClient, box: Box, margin: int,
                   world: str | None) -> None:
    text, is_error = client.call("mc_players", {})
    if is_error:
        raise PlacerError("mc_players failed: " + client.redact(text), EXIT_SERVER)
    inside = players_inside(parse_players(text), box, margin, world)
    if inside:
        raise PlacerError("players inside the build area: " + ", ".join(inside),
                          EXIT_PLAYER)


def _run_pages(client: McpClient, pages: list[Page], report: dict[str, Any]) -> None:
    for i, page in enumerate(pages, 1):
        text, is_error = client.call("mc_build", page.args)
        if is_error:
            raise PlacerError(f"mc_build failed on page {i}/{len(pages)}: "
                              + client.redact(text), EXIT_SERVER)
        report["pages_done"] = i
        report["warnings"] += [client.redact(w) for w in warnings_of(text)]
        report["results"].append({"page": i, "result": [
            client.redact(line) for line in result_lines(text)]})


def cmd_place(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.file)
    build = load_build(path, limits)
    _, pages, tiles = plan_summary(build, limits, path)
    world = ns.world or build.get("world")
    if ns.world:
        for page in pages:
            page.args["world"] = ns.world
    if ns.backup:
        refuse_existing_backup(Path(ns.backup))
    if ns.snapshot and len(tiles) > ns.max_snapshots:
        raise PlacerError(f"this file needs {len(tiles)} snapshots (limit "
                          f"{ns.max_snapshots}); split it into smaller phase files",
                          EXIT_REFUSED)
    entry = _server(ns)
    report: dict[str, Any] = {"file": str(path), "pages_total": len(pages),
                              "pages_done": 0, "snapshots": [], "backup": None,
                              "warnings": [], "results": [], "error": None}
    client = McpClient(entry)
    try:
        whole = union([page.box for page in pages])
        _check_players(client, whole, ns.player_margin, world)
        if ns.backup:
            take_backup(client, whole, world, Path(ns.backup), limits)
            report["backup"] = ns.backup
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
        _run_pages(client, pages, report)
    except PlacerError as exc:
        report["error"] = str(exc)
        _emit(report, ns.log)
        raise
    finally:
        client.close()
    _emit(report, ns.log)
    return EXIT_OK


def cmd_backup(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    a, b = [ns.box[0], ns.box[1], ns.box[2]], [ns.box[3], ns.box[4], ns.box[5]]
    _coords(a, "--box from", limits)
    _coords(b, "--box to", limits)
    box = box_of(a, b)
    out = Path(ns.out)
    refuse_existing_backup(out)
    client = McpClient(_server(ns))
    try:
        manifest = take_backup(client, box, ns.world, out, limits)
    finally:
        client.close()
    _emit({"backup": str(out), "manifest": manifest}, ns.log)
    return EXIT_OK


def cmd_restore(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.dir)
    manifest, columns = load_backup(path)
    world = ns.world or manifest.get("world")
    pages = _restore_pages(columns, world, limits, f"{path} restore fills")
    box: Box = tuple(manifest["box"])  # type: ignore[assignment]
    report: dict[str, Any] = {"backup": str(path), "pages_total": len(pages),
                              "pages_done": 0, "warnings": [], "results": [],
                              "error": None}
    client = McpClient(_server(ns))
    try:
        _check_players(client, box, ns.player_margin, world)
        _run_pages(client, pages, report)
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


def cmd_heights(ns: argparse.Namespace) -> int:
    area = (min(ns.area[0], ns.area[2]), min(ns.area[1], ns.area[3]),
            max(ns.area[0], ns.area[2]), max(ns.area[1], ns.area[3]))
    client = McpClient(_server(ns))
    try:
        heights = read_heights(client, area, ns.world)
    finally:
        client.close()
    try:
        Path(ns.out).write_text(json.dumps(heights), encoding="utf-8")
    except OSError as exc:
        raise PlacerError(f"cannot write {ns.out} ({exc.__class__.__name__})",
                          EXIT_INPUT) from None
    print(f"read {heights['size'][0]}x{heights['size'][1]} heights in "
          f"{len(height_tiles(area))} tiles -> {ns.out}")
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
    parser.add_argument("--max-flowing", type=int, default=defaults.max_flowing)


def _limits(ns: argparse.Namespace) -> Limits:
    return Limits(ns.max_blocks, ns.max_chunks, ns.max_ops, ns.snapshot_volume,
                  ns.min_y, ns.max_y, ns.max_flowing)


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
    choice.add_argument("--backup", metavar="DIR",
                        help="write a column backup (F1) into DIR before building")
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

    heights = sub.add_parser("heights", help="write an x/z area's heights file (F2)")
    heights.add_argument("--area", type=int, nargs=4, required=True,
                         metavar=("X1", "Z1", "X2", "Z2"))
    heights.add_argument("--out", required=True)
    heights.add_argument("--world")
    _add_server(heights)

    backup = sub.add_parser("backup", help="write a column backup (F1) of a box")
    backup.add_argument("--box", type=int, nargs=6, required=True,
                        metavar=("X1", "Y1", "Z1", "X2", "Y2", "Z2"))
    backup.add_argument("--out", required=True, metavar="DIR")
    backup.add_argument("--world")
    backup.add_argument("--log")
    _add_limits(backup)
    _add_server(backup)

    restore = sub.add_parser("restore", help="put a column backup back exactly")
    restore.add_argument("dir")
    restore.add_argument("--world")
    restore.add_argument("--player-margin", type=int, default=2)
    restore.add_argument("--log")
    _add_limits(restore)
    _add_server(restore)
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "plan": cmd_plan, "place": cmd_place,
                "read": cmd_read, "heights": cmd_heights, "backup": cmd_backup, "restore": cmd_restore}
    try:
        return handlers[ns.cmd](ns)
    except PlacerError as exc:
        print(f"ashlar_place: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
