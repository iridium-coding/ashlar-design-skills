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

A phase file is an `mc_build` arguments object (`fills`, `blocks`, `liquids`,
`connect`, `world`) or a bare list of fills. Exit codes: 0 ok, 2 invalid input,
3 refused by a limit or snapshot rule, 4 player in the area (or an unreadable
player list), 5 server error. Nothing printed ever contains a value from the
server entry's `env`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
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
    env: dict[str, str]
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


def snapshot_id(text: str) -> str:
    match = SNAPSHOT_ID.match(text.strip())
    if not match:
        raise PlacerError("unexpected mc_snapshot reply: " + text[:200], EXIT_SERVER)
    return match.group(1)


def warnings_of(text: str) -> list[str]:
    """The indented lines of mc_build's WARNINGS section."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("WARNINGS"):
            return [w.strip() for w in lines[i + 1:] if w.startswith("  ")]
    return []


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashlar_place.py",
        description="Send generated Minecraft geometry through Ashlar.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="validate a phase file offline")
    plan.add_argument("file")
    _add_limits(plan)
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    handlers = {"plan": cmd_plan}
    try:
        return handlers[ns.cmd](ns)
    except PlacerError as exc:
        print(f"ashlar_place: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
