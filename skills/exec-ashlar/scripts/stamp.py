#!/usr/bin/env python3
"""Stamp module files (local coordinates) into world-coordinate phase files.

A module has `size` [w, h, d] and `fills`/`blocks` in local coordinates with
its minimum corner at [0, 0, 0]. Each placement mirrors the module first
(`x` flips east-west, `z` flips north-south), then rotates it clockwise as seen
from above (0, 90, 180 or 270), then moves it so its minimum corner sits at the
origin. Block states turn with it.

  stamp.py MODULE.json --at=X,Y,Z [--rotate 0|90|180|270] [--mirror none|x|z] [--out FILE]
  stamp.py --placements PLAN.toon|PLACEMENTS.json --modules DIR [--phase N] --out FILE

Write `--at=X,Y,Z` with the equals sign so a negative X is not read as an option.
"""
from __future__ import annotations

import sys


def require_python(version: tuple[int, ...] | None = None) -> None:
    """Exit cleanly, with one line on stderr, on Python older than 3.11."""
    if tuple(version if version is not None else sys.version_info[:2]) < (3, 11):
        print("stamp.py needs Python 3.11 or newer; run it with `uv run "
              "--no-project --python 3.11 python stamp.py ...`", file=sys.stderr)
        raise SystemExit(2)


require_python()

import argparse
import json
import re
from pathlib import Path
from typing import Any

CLOCKWISE = {"north": "east", "east": "south", "south": "west", "west": "north"}
MIRRORS: dict[str, dict[str, str]] = {
    "none": {}, "x": {"east": "west", "west": "east"},
    "z": {"north": "south", "south": "north"}}
SIDES = ("north", "east", "south", "west")
STAIR_SHAPES = {"straight", "inner_left", "inner_right", "outer_left", "outer_right"}
CONNECTING_SUFFIXES = ("_fence", "_wall", "_pane")
CONNECTING_IDS = {"minecraft:iron_bars", "minecraft:redstone_wire"}
PLACEMENTS_HEADER = re.compile(
    r"^placements\[\d+\]\{module,origin,rotation,mirror,phase\}:\s*$")
VEG_PARTS = ("ground", "wood", "leaves")
VEG_KEYS = {"name", "size", "kind", "anchor", *VEG_PARTS}
AIR = "minecraft:air"

Box = tuple[int, int, int, int, int, int]


class StampError(Exception):
    """Invalid module or placement."""


def parse_state(state: str) -> tuple[str, list[tuple[str, str]]]:
    match = re.fullmatch(r"([^\[\]]+)(?:\[(.*)\])?", state.strip())
    if not match:
        raise StampError(f"bad block state: {state!r}")
    props: list[tuple[str, str]] = []
    if match.group(2):
        for part in match.group(2).split(","):
            key, sep, value = part.partition("=")
            if not sep:
                raise StampError(f"bad property {part!r} in {state!r}")
            props.append((key.strip(), value.strip()))
    return match.group(1).strip(), props


def format_state(block_id: str, props: list[tuple[str, str]]) -> str:
    if not props:
        return block_id
    return block_id + "[" + ",".join(f"{k}={v}" for k, v in props) + "]"


def turn(direction: str, rotation: int, mirror: str) -> str:
    """Mirror, then rotate, one horizontal direction; other values pass through."""
    if direction not in CLOCKWISE:
        return direction
    direction = MIRRORS[mirror].get(direction, direction)
    for _ in range(rotation // 90):
        direction = CLOCKWISE[direction]
    return direction


def _rail_shape(value: str, rotation: int, mirror: str) -> str:
    if value.startswith("ascending_"):
        return "ascending_" + turn(value[len("ascending_"):], rotation, mirror)
    first, _, second = value.partition("_")
    ends = {turn(first, rotation, mirror), turn(second, rotation, mirror)}
    if ends == {"north", "south"}:
        return "north_south"
    if ends == {"east", "west"}:
        return "east_west"
    return (("north" if "north" in ends else "south") + "_"
            + ("east" if "east" in ends else "west"))


def transform_state(state: str, rotation: int, mirror: str) -> str:
    """Rotate and mirror one block state string."""
    block_id, props = parse_state(state)
    connecting = block_id.endswith(CONNECTING_SUFFIXES) or block_id in CONNECTING_IDS
    out: list[tuple[str, str]] = []
    for key, value in props:
        if key in SIDES:
            if not connecting:  # Ashlar's connection pass recomputes connecting blocks
                out.append((turn(key, rotation, mirror), value))
        elif key == "facing":
            out.append((key, turn(value, rotation, mirror)))
        elif key == "rotation" and value.isdigit():
            r = int(value)
            if mirror == "x":
                r = (16 - r) % 16
            elif mirror == "z":
                r = (8 - r) % 16
            out.append((key, str((r + 4 * (rotation // 90)) % 16)))
        elif key == "axis" and value in ("x", "z") and rotation in (90, 270):
            out.append((key, "z" if value == "x" else "x"))
        elif key == "shape" and value in STAIR_SHAPES:
            if mirror != "none" and value != "straight":
                kind, side = value.split("_")
                value = f"{kind}_{'right' if side == 'left' else 'left'}"
            out.append((key, value))
        elif key == "shape" and any(side in value for side in SIDES):
            out.append((key, _rail_shape(value, rotation, mirror)))
        elif key == "hinge" and mirror != "none":
            out.append((key, "right" if value == "left" else "left"))
        elif key == "type" and block_id.endswith("chest") and value in ("left", "right"):
            out.append((key, "single"))
        elif key == "orientation":
            out.append((key, "_".join(turn(part, rotation, mirror)
                                      for part in value.split("_"))))
        else:
            out.append((key, value))
    return format_state(block_id, out)


def transform_point(point: list[int], size: list[int], rotation: int, mirror: str,
                    origin: list[int]) -> list[int]:
    x, y, z = point
    width, _, depth = size
    if mirror == "x":
        x = width - 1 - x
    elif mirror == "z":
        z = depth - 1 - z
    for _ in range(rotation // 90):
        x, z = depth - 1 - z, x
        width, depth = depth, width
    return [x + origin[0], y + origin[1], z + origin[2]]


def footprint(size: list[int], rotation: int, origin: list[int]) -> Box:
    width, height, depth = size
    if rotation in (90, 270):
        width, depth = depth, width
    return (origin[0], origin[1], origin[2],
            origin[0] + width - 1, origin[1] + height - 1, origin[2] + depth - 1)


def _inside(point: Any, size: list[int], where: str) -> None:
    if (not isinstance(point, list) or len(point) != 3
            or not all(isinstance(v, int) and 0 <= v < s for v, s in zip(point, size))):
        raise StampError(f"{where}: {point!r} is outside the module size {size}")


def _check_size(size: Any) -> list[int]:
    if (not isinstance(size, list) or len(size) != 3
            or not all(isinstance(v, int) and v > 0 for v in size)):
        raise StampError("module 'size' must be three positive integers [w, h, d]")
    return size


def _check_vegetation(module: dict[str, Any]) -> None:
    """Validate an F7 vegetation module: an anchor inside the size, and only known keys."""
    _check_size(module.get("size"))
    unknown = sorted(set(module) - VEG_KEYS)
    if unknown:
        raise StampError(f"vegetation module has keys {unknown}; only ground, wood and "
                         "leaves parts are allowed")
    if "anchor" not in module:
        raise StampError("vegetation module needs an 'anchor' (the trunk base cell)")
    _inside(module["anchor"], module["size"], "anchor")
    for part in VEG_PARTS:
        body = module.get(part, {})
        if not isinstance(body, dict) or set(body) - {"fills", "blocks"}:
            raise StampError(f"vegetation part {part!r} takes only fills and blocks")


def _cells_to_fills(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn 1 x 1 x 1 cells into fills, merging runs of consecutive x with equal y, z and block."""
    runs: dict[tuple[int, int, str], list[int]] = {}
    for block in blocks:
        extra = sorted(set(block) - {"pos", "block"})
        if extra:
            raise StampError(f"vegetation cells take only pos and block, not {extra}")
        x, y, z = block["pos"]
        runs.setdefault((y, z, block["block"]), []).append(x)
    fills: list[dict[str, Any]] = []
    for (y, z, state), xs in runs.items():
        xs = sorted(set(xs))
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            fills.append({"from": [start, y, z], "to": [prev, y, z], "block": state})
            if x is not None:
                start = prev = x
    return fills


def _phase(entries: list[tuple[dict[str, Any], list[int], int, str]]) -> dict[str, list]:
    """Assemble one phase from (module, origin, rotation, mirror) entries.

    Non-vegetation output keeps its order. Vegetation then adds every `ground`
    part, every `wood` part and every `leaves` part; wood and leaves cells go
    into air only, so they are fills with the air filter and `blocks` stays
    for non-vegetation cells.
    """
    plain: dict[str, list] = {"fills": [], "blocks": []}
    veg: dict[str, list] = {part: [] for part in VEG_PARTS}
    for module, origin, rotation, mirror in entries:
        if module.get("kind") != "vegetation":
            part = stamp(module, origin, rotation, mirror)
            plain["fills"] += part["fills"]
            plain["blocks"] += part["blocks"]
            continue
        _check_vegetation(module)
        for name in VEG_PARTS:
            body = module.get(name, {"fills": [], "blocks": []})
            part = stamp({"size": module["size"], **body}, origin, rotation, mirror)
            fills = part["fills"] + _cells_to_fills(part["blocks"])
            if name != "ground":
                fills = [{**fill, "filter": AIR} for fill in fills]
            veg[name] += fills
    return {"fills": plain["fills"] + veg["ground"] + veg["wood"] + veg["leaves"],
            "blocks": plain["blocks"]}


def stamp(module: dict[str, Any], origin: list[int], rotation: int,
          mirror: str) -> dict[str, list[dict[str, Any]]]:
    """Place one module instance; returns {"fills": [...], "blocks": [...]}.

    A vegetation module returns the same shape, as a one-tree phase.
    """
    if rotation not in (0, 90, 180, 270):
        raise StampError(f"rotation must be 0, 90, 180 or 270, not {rotation}")
    if mirror not in MIRRORS:
        raise StampError(f"mirror must be none, x or z, not {mirror!r}")
    if "text" in module:
        raise StampError("modules may not contain 'text'; put lettering in its own phase")
    size = _check_size(module.get("size"))
    if module.get("kind") == "vegetation":
        return _phase([(module, origin, rotation, mirror)])
    fills = []
    for i, fill in enumerate(module.get("fills", [])):
        _inside(fill.get("from"), size, f"fills[{i}].from")
        _inside(fill.get("to"), size, f"fills[{i}].to")
        a = transform_point(fill["from"], size, rotation, mirror, origin)
        b = transform_point(fill["to"], size, rotation, mirror, origin)
        placed = {**fill, "from": [min(p, q) for p, q in zip(a, b)],
                  "to": [max(p, q) for p, q in zip(a, b)],
                  "block": transform_state(fill["block"], rotation, mirror)}
        if "filter" in fill:
            placed["filter"] = transform_state(fill["filter"], rotation, mirror)
        fills.append(placed)
    blocks = []
    for i, block in enumerate(module.get("blocks", [])):
        _inside(block.get("pos"), size, f"blocks[{i}].pos")
        blocks.append({**block,
                       "pos": transform_point(block["pos"], size, rotation, mirror, origin),
                       "block": transform_state(block["block"], rotation, mirror)})
    return {"fills": fills, "blocks": blocks}


def _overlaps(a: Box, b: Box) -> bool:
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


def _split_cells(line: str) -> list[str]:
    """Split one TOON table row on commas.

    A cell may be double-quoted (TOON quotes a cell that starts with "-", such
    as a negative coordinate, or that holds a comma); inside quotes, \\" is a
    literal quote. Unquoted cells are trimmed.
    """
    cells: list[str] = []
    cur: list[str] = []
    in_quote = quoted = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quote:
            if ch == "\\" and line[i + 1:i + 2] == '"':
                cur.append('"')
                i += 2
                continue
            if ch == '"':
                in_quote = False
            else:
                cur.append(ch)
        elif ch == '"' and not "".join(cur).strip():
            in_quote = quoted = True
            cur = []
        elif ch == ",":
            cells.append("".join(cur) if quoted else "".join(cur).strip())
            cur, quoted = [], False
        else:
            cur.append(ch)
        i += 1
    if in_quote:
        raise ValueError("unterminated quote")
    cells.append("".join(cur) if quoted else "".join(cur).strip())
    return cells


def read_placements(path: Path, phase: int | None) -> list[dict[str, Any]]:
    """Read placements from a JSON list or from a plan.toon placements table."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        rows = json.loads(text)
    else:
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines)
                      if PLACEMENTS_HEADER.match(line)), None)
        if start is None:
            raise StampError(f"{path}: no placements table")
        rows = []
        for line in lines[start + 1:]:
            if not line.strip() or not line[0].isspace():
                break
            try:
                cells = _split_cells(line.strip())
                if len(cells) != 5:
                    raise ValueError("expected 5 cells")
                module, origin, rotation, mirror, row_phase = cells
                point = [int(v) for v in origin.split()]
                if len(point) != 3:
                    raise ValueError("origin needs x y z")
                rows.append({"module": module, "origin": point,
                             "rotation": int(rotation), "mirror": mirror,
                             "phase": int(row_phase)})
            except ValueError as exc:
                raise StampError(f"{path}: bad placements row {line.strip()!r} ({exc})") from None
    if phase is not None:
        rows = [row for row in rows if row.get("phase") == phase]
    return rows


def stamp_all(placements: list[dict[str, Any]], modules_dir: Path) -> dict[str, list]:
    """Stamp every placement into one phase file.

    Placements may not overlap, except that vegetation may overlap vegetation.
    """
    entries: list[tuple[dict[str, Any], list[int], int, str]] = []
    placed: list[tuple[Box, str, bool]] = []
    cache: dict[str, dict[str, Any]] = {}
    for row in placements:
        name = row["module"]
        if name not in cache:
            cache[name] = json.loads((modules_dir / f"{name}.json").read_text(encoding="utf-8"))
        module = cache[name]
        is_veg = module.get("kind") == "vegetation"
        box = footprint(module["size"], row["rotation"], row["origin"])
        for other, other_name, other_veg in placed:
            if is_veg and other_veg:
                continue
            if _overlaps(box, other):
                raise StampError(f"{name} at {row['origin']} overlaps {other_name}")
        placed.append((box, f"{name} at {row['origin']}", is_veg))
        entries.append((module, row["origin"], row["rotation"], row.get("mirror", "none")))
    return _phase(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stamp.py",
                                     description="Stamp module files into phase files.")
    parser.add_argument("module", nargs="?", help="module JSON file")
    parser.add_argument("--at", help="origin X,Y,Z (write --at=X,Y,Z)")
    parser.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    parser.add_argument("--mirror", default="none", choices=("none", "x", "z"))
    parser.add_argument("--placements", help="plan.toon or a JSON list of placements")
    parser.add_argument("--modules", help="folder holding <module>.json files")
    parser.add_argument("--phase", type=int, help="only placements for this phase")
    parser.add_argument("--out", help="write the phase file here instead of stdout")
    ns = parser.parse_args(argv)
    try:
        if ns.placements:
            if not ns.modules or not ns.out:
                parser.error("--placements needs --modules and --out")
            result = stamp_all(read_placements(Path(ns.placements), ns.phase),
                               Path(ns.modules))
        else:
            if not ns.module or not ns.at:
                parser.error("give MODULE.json and --at=X,Y,Z, or --placements")
            origin = [int(v) for v in ns.at.split(",")]
            if len(origin) != 3:
                raise StampError("--at needs three integers X,Y,Z")
            module = json.loads(Path(ns.module).read_text(encoding="utf-8"))
            result = stamp(module, origin, ns.rotate, ns.mirror)
    except (StampError, OSError, ValueError, KeyError) as exc:
        print(f"stamp: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=1)
    if ns.out:
        try:
            out = Path(ns.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"stamp: cannot write {ns.out}: {exc.strerror}", file=sys.stderr)
            return 2
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
