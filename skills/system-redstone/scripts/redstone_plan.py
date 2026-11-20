#!/usr/bin/env python3
"""Plan loading for the redstone resting-state checker.

Turns an exec-ashlar plan (plan.toon, stamped phase files, setup console
commands) and `ashlar_place.py read` JSON into a block-state world. Loading
only: no redstone logic lives here.
"""
from __future__ import annotations

import sys


def require_python(version: tuple[int, ...] | None = None) -> None:
    """Exit cleanly, with one line on stderr, on Python older than 3.11."""
    if tuple(version if version is not None else sys.version_info[:2]) < (3, 11):
        print("redstone_plan.py needs Python 3.11 or newer; run it with `uv run "
              "--no-project --python 3.11 python redstone_plan.py ...`", file=sys.stderr)
        raise SystemExit(2)


require_python()

import json
import re
from collections import ChainMap
from dataclasses import dataclass, field
from pathlib import Path

Pos = tuple[int, int, int]
AIR = "minecraft:air"
AIR_MATERIALS = {AIR, "minecraft:cave_air", "minecraft:void_air"}
# Defaults verified in the shipped Java 26.3 RepeaterBlock constructor. Apply
# them only when evaluating filters against an earlier placement instruction.
FILTER_DEFAULTS = {"minecraft:repeater": {"delay": "1", "facing": "north", "locked": "false", "powered": "false"}}


class PlanError(Exception):
    """Bad input; the CLI exits 2."""


# --- block states ---------------------------------------------------------

_STATE_RE = re.compile(r"^((?:[a-z0-9_.-]+:)?[a-z0-9_./-]+)(?:\[(.*)\])?$", re.DOTALL)


@dataclass(frozen=True)
class State:
    id: str
    props: tuple[tuple[str, str], ...] = ()

    def get(self, key: str, default: str | None = None) -> str | None:
        for k, v in self.props:
            if k == key:
                return v
        return default

    def with_props(self, **changes: str) -> "State":
        merged = dict(self.props)
        merged.update(changes)
        return State(self.id, tuple(sorted(merged.items())))


def parse_state(text: str) -> State:
    m = _STATE_RE.match(text.strip()) if isinstance(text, str) else None
    if not m:
        raise PlanError(f"bad block state {text!r}")
    block_id, body = m.group(1), m.group(2)
    if ":" not in block_id:
        block_id = "minecraft:" + block_id
    props: dict[str, str] = {}
    if body:
        for pair in body.split(","):
            key, eq, value = pair.partition("=")
            key, value = key.strip(), value.strip()
            if not eq or not key or not value:
                raise PlanError(f"bad block state {text!r}: property {pair!r} is not key=value")
            props[key] = value
    return State(block_id, tuple(sorted(props.items())))


def format_state(state: State) -> str:
    if not state.props:
        return state.id
    return f"{state.id}[{','.join(f'{k}={v}' for k, v in state.props)}]"


@dataclass(frozen=True)
class Stack:
    item: str
    count: int


# --- TOON -----------------------------------------------------------------

def _split_cells(line: str) -> list[str]:
    cells: list[str] = []
    cur: list[str] = []
    in_quote = False
    quoted = False
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
            in_quote = True
            quoted = True
            cur = []
        elif ch == ",":
            cells.append("".join(cur) if quoted else "".join(cur).strip())
            cur, quoted = [], False
        else:
            cur.append(ch)
        i += 1
    if in_quote:
        raise PlanError("unterminated quote")
    cells.append("".join(cur) if quoted else "".join(cur).strip())
    return cells


def _table(text: str, name: str, source: str) -> list[tuple[int, dict[str, str]]]:
    header = re.compile(rf"^{re.escape(name)}\[\d+\]\{{([^}}]*)\}}:\s*$")
    lines = text.splitlines()
    for idx, raw in enumerate(lines):
        m = header.match(raw)
        if not m:
            continue
        cols = [c.strip() for c in m.group(1).split(",")]
        rows: list[tuple[int, dict[str, str]]] = []
        for j in range(idx + 1, len(lines)):
            row = lines[j]
            if not row.strip():
                continue
            if not row[0].isspace():
                break
            try:
                cells = _split_cells(row.strip())
            except PlanError as exc:
                raise PlanError(f"{source}:{j + 1}: {exc}") from None
            if len(cells) != len(cols):
                raise PlanError(f"{source}:{j + 1}: {name} row has {len(cells)} cells, "
                                f"expected {len(cols)}")
            rows.append((j + 1, dict(zip(cols, cells))))
        return rows
    return []


def read_toon_table(text: str, name: str) -> list[dict[str, str]]:
    return [row for _, row in _table(text, name, "<toon>")]


# --- plan -----------------------------------------------------------------

@dataclass
class Plan:
    path: Path
    project: str
    world: str | None
    bbox: tuple[Pos, Pos]
    phases: list[dict[str, str]]
    commands: list[dict[str, str]]
    tests: list[dict[str, str]]
    command_lines: list[int] = field(default_factory=list, repr=False)


_TRIPLE = r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
_BBOX_RE = re.compile(rf"^bbox:\s*\{{\s*from:\s*{_TRIPLE}\s*,\s*to:\s*{_TRIPLE}\s*\}}\s*$")


def load_plan(path: Path) -> Plan:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as exc:
        raise PlanError(f"{path}:1: cannot read plan: {exc.strerror or exc}") from None
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "plan:"), None)
    if start is None:
        raise PlanError(f"{path}:1: no `plan:` block")
    fields: dict[str, str] = {}
    bbox: tuple[Pos, Pos] | None = None
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if not ln.strip():
            continue
        if not ln[0].isspace():
            break
        body = ln.strip()
        m = _BBOX_RE.match(body)
        if m:
            n = [int(g) for g in m.groups()]
            bbox = ((n[0], n[1], n[2]), (n[3], n[4], n[5]))
        elif body.startswith("bbox:"):
            raise PlanError(f"{path}:{i + 1}: bad bbox, expected "
                            "`bbox: {from: [x, y, z], to: [x, y, z]}`")
        else:
            key, sep, value = body.partition(":")
            if sep:
                fields[key.strip()] = value.strip().strip('"')
    if not fields.get("project"):
        raise PlanError(f"{path}:{start + 1}: plan has no project")
    if bbox is None:
        raise PlanError(f"{path}:{start + 1}: plan has no bbox")
    source = str(path)
    phases = [row for _, row in _table(text, "phases", source)]
    command_rows = _table(text, "commands", source)
    tests = [row for _, row in _table(text, "tests", source)]
    return Plan(path=path, project=fields["project"], world=fields.get("world") or None,
                bbox=bbox, phases=phases, commands=[row for _, row in command_rows],
                tests=tests, command_lines=[n for n, _ in command_rows])


# --- assemble -------------------------------------------------------------

def _int3(value: object, where: str, what: str) -> Pos:
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
        raise PlanError(f"{where}: {what} must be three integers, got {value!r}")
    return (value[0], value[1], value[2])


def _state_in(text: object, where: str) -> State:
    try:
        return parse_state(text)  # type: ignore[arg-type]
    except PlanError as exc:
        raise PlanError(f"{where}: {exc}") from None


def _matches(current: State, wanted: State, authored: bool) -> bool | None:
    if current.id != wanted.id:
        return False
    defaults = FILTER_DEFAULTS.get(current.id, {}) if authored else {}
    complete = True
    for key, value in wanted.props:
        actual = current.get(key, defaults.get(key))
        if actual is None:
            complete = False
        elif actual != value:
            return False
    return True if complete else None


# Each ambiguous cell keeps at most one pre-build state plus one state per
# distinct write at that position. The flag distinguishes an authored write
# (with Java placement defaults) from an existing, possibly partial read.
CellOutcome = tuple[State | None, bool]


@dataclass
class _AmbiguousCell:
    outcomes: set[CellOutcome]
    reason: str


def _conditional_write(world: ChainMap[Pos, State], unresolved: dict[Pos, _AmbiguousCell], pos: Pos,
                       new: State, keep: bool, flt: State | None, require_known: bool, where: str) -> None:
    pending = unresolved.get(pos)
    current = world.get(pos, None if require_known else State(AIR))
    authored = pos in world.maps[0]
    before = pending.outcomes if pending else {(current, authored)}
    after: set[CellOutcome] = set()
    for state, was_written in before:
        if state is None:
            match = None
        elif keep and state.id not in AIR_MATERIALS:
            match = False
        else:
            match = flt is None or _matches(state, flt, was_written)
        if match is not False:
            after.add((new, True))
        if match is not True:
            after.add((state, was_written))

    if len(after) == 1:
        state, was_written = after.pop()
        if was_written:
            assert state is not None
            world[pos] = state
        unresolved.pop(pos, None)
    elif pending:
        pending.outcomes = after
    else:
        if current is None:
            reason = (f"{where}: conditional fill at {pos} needs the pre-build state; "
                      "pass --background with a pre-build read covering the conditional fills")
        else:
            assert flt is not None  # A known material is sufficient for an unfiltered keep.
            remedy = ("specify the filtered properties explicitly in the earlier write" if authored else
                      "supply a complete state for the existing block in --background")
            reason = f"{where}: cannot evaluate filter {format_state(flt)} at {pos}; {remedy}"
        unresolved[pos] = _AmbiguousCell(after, reason)


def _apply_fill(world: ChainMap[Pos, State], fill: object, where: str,
                unresolved: dict[Pos, _AmbiguousCell], require_known_conditions: bool) -> None:
    if not isinstance(fill, dict) or "from" not in fill or "to" not in fill or "block" not in fill:
        raise PlanError(f"{where}: fill needs from, to and block")
    a = _int3(fill["from"], where, "fill from")
    b = _int3(fill["to"], where, "fill to")
    block = _state_in(fill["block"], where)
    mode = fill.get("mode", "replace")
    if mode not in ("replace", "keep", "outline", "hollow", "walls"):
        raise PlanError(f"{where}: unknown fill mode {mode!r}")
    flt = _state_in(fill["filter"], where) if fill.get("filter") else None
    if mode == "keep" and flt is not None and flt.id not in AIR_MATERIALS:
        return  # The cell cannot simultaneously be air and match this filter.
    air = State(AIR)
    lo = tuple(min(p, q) for p, q in zip(a, b))
    hi = tuple(max(p, q) for p, q in zip(a, b))
    for x in range(lo[0], hi[0] + 1):
        for y in range(lo[1], hi[1] + 1):
            for z in range(lo[2], hi[2] + 1):
                edge_xz = x in (lo[0], hi[0]) or z in (lo[2], hi[2])
                shell = edge_xz or y in (lo[1], hi[1])
                if mode == "walls" and not edge_xz:
                    continue
                if mode == "outline" and not shell:
                    continue
                new = block
                if mode == "hollow" and not shell:
                    new = air
                pos = (x, y, z)
                if mode == "keep" or flt is not None:
                    _conditional_write(world, unresolved, pos, new, mode == "keep", flt, require_known_conditions, where)
                else:
                    world[pos] = new
                    unresolved.pop(pos, None)


def written_cells(plan: Plan, background: dict[Pos, State] | None = None, *,
                  require_known_conditions: bool = False) -> dict[Pos, State]:
    """Collect successful plan writes; conditional fills consult the existing site."""
    written: dict[Pos, State] = {}
    world = ChainMap(written, background or {})
    unresolved: dict[Pos, _AmbiguousCell] = {}
    for row in plan.phases:
        if row.get("via") == "commands" or row.get("file", "-") == "-":
            continue
        file = plan.path.parent / row["file"]
        try:
            data = json.loads(file.read_text())
        except OSError as exc:
            raise PlanError(f"{file}: cannot read phase file: {exc.strerror or exc}") from None
        except json.JSONDecodeError as exc:
            raise PlanError(f"{file}:{exc.lineno}: bad JSON: {exc.msg}") from None
        if isinstance(data, list):
            data = {"fills": data}
        if not isinstance(data, dict):
            raise PlanError(f"{file}: phase file must be an object or a list of fills")
        if data.get("text"):
            raise PlanError(f"{file}: server-rendered text requires a hand check; "
                            "use explicit blocks for offline verification")
        for key in ("fills", "blocks"):
            if key in data and not isinstance(data[key], list):
                raise PlanError(f"{file}: {key} must be a list")
        for i, fill in enumerate(data.get("fills") or []):
            _apply_fill(world, fill, f"{file} fills[{i}]", unresolved, require_known_conditions)
        for i, entry in enumerate(data.get("blocks") or []):
            where = f"{file} blocks[{i}]"
            if not isinstance(entry, dict) or "pos" not in entry or "block" not in entry:
                raise PlanError(f"{where}: block needs pos and block")
            pos = _int3(entry["pos"], where, "block pos")
            world[pos] = _state_in(entry["block"], where)
            if unresolved:
                unresolved.pop(pos, None)
    if unresolved:
        raise PlanError(next(iter(unresolved.values())).reason)
    return written


def assemble(plan: Plan, background: dict[Pos, State] | None = None) -> dict[Pos, State]:
    return (background or {}) | written_cells(plan, background)


# --- setup loads ----------------------------------------------------------

_ITEM_RE = re.compile(r"^(?:minecraft:)?item\s+replace\s+block\s+(\S+)\s+(\S+)\s+(\S+)\s+"
                      r"container\.(\d+)\s+with\s+(.*)$", re.DOTALL)
_DATA_RE = re.compile(r"^(?:minecraft:)?data\s+merge\s+block\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)$",
                      re.DOTALL)
_NUM = r"-?\d+[bBsSlL]?"


def _coords(parts: tuple[str, ...], where: str) -> Pos:
    try:
        x, y, z = (int(p) for p in parts)
    except ValueError:
        raise PlanError(f"{where}: coordinates must be plain integers, got "
                        f"{' '.join(parts)!r}") from None
    return (x, y, z)


def _scan_group(text: str, start: int, where: str) -> int:
    """Index just past the bracket group opening at text[start], honouring quotes."""
    pairs = {"[": "]", "{": "}", "(": ")"}
    stack: list[str] = []
    quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in "]})":
            if not stack or stack.pop() != ch:
                raise PlanError(f"{where}: unbalanced brackets")
            if not stack:
                return i + 1
        i += 1
    raise PlanError(f"{where}: unbalanced brackets or quotes")


def _top_level(text: str, sep: str, where: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    cur: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "[{(":
            depth += 1
            cur.append(ch)
        elif ch in "]})":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if depth != 0 or quote:
        raise PlanError(f"{where}: unbalanced brackets or quotes")
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _item_stack(rest: str, where: str) -> Stack:
    rest = rest.strip()
    m = re.match(r"^((?:[a-z0-9_.-]+:)?[a-z0-9_./-]+)", rest)
    if not m:
        raise PlanError(f"{where}: bad item in {rest!r}")
    item = m.group(1)
    if ":" not in item:
        item = "minecraft:" + item
    tail = rest[m.end():]
    if tail.startswith("["):
        tail = tail[_scan_group(tail, 0, where):]
    tail = tail.strip()
    if not tail:
        return Stack(item, 1)
    if not re.fullmatch(r"\d+", tail):
        raise PlanError(f"{where}: bad item count {tail!r}")
    return Stack(item, int(tail))


def _data_stacks(nbt: str, where: str) -> dict[int, Stack] | None:
    nbt = nbt.strip()
    if not nbt.startswith("{"):
        raise PlanError(f"{where}: data merge needs an NBT compound")
    if _scan_group(nbt, 0, where) != len(nbt):
        raise PlanError(f"{where}: unexpected text after the NBT compound")
    for pair in _top_level(nbt[1:-1], ",", where):
        key, sep, value = pair.partition(":")
        if not sep or _unquote(key) != "Items":
            continue
        value = value.strip()
        if not value.startswith("[") or _scan_group(value, 0, where) != len(value):
            raise PlanError(f"{where}: Items must be a list")
        stacks: dict[int, Stack] = {}
        for entry in _top_level(value[1:-1], ",", where):
            entry = entry.strip()
            if not entry.startswith("{") or _scan_group(entry, 0, where) != len(entry):
                raise PlanError(f"{where}: Items entry must be a compound")
            fields: dict[str, str] = {}
            for kv in _top_level(entry[1:-1], ",", where):
                k, s, v = kv.partition(":")
                if s:
                    fields[k.strip().strip("\"'")] = v.strip()
            slot = next((fields[k] for k in ("Slot", "slot") if k in fields), None)
            count = next((fields[k] for k in ("count", "Count") if k in fields), "1b")
            ident = fields.get("id")
            if slot is None or ident is None:
                raise PlanError(f"{where}: Items entry needs Slot and id")
            if not re.fullmatch(_NUM, slot) or not re.fullmatch(_NUM, count):
                raise PlanError(f"{where}: bad Slot or count in Items entry")
            item = _unquote(ident)
            if ":" not in item:
                item = "minecraft:" + item
            stacks[int(slot[:-1] if slot[-1].isalpha() else slot)] = Stack(
                item, int(count[:-1] if count[-1].isalpha() else count))
        return stacks
    return None


def setup_loads(plan: Plan) -> dict[Pos, dict[int, Stack]]:
    setup_ids = {row.get("id") for row in plan.phases if row.get("via") == "commands"}
    loads: dict[Pos, dict[int, Stack]] = {}
    for index, row in enumerate(plan.commands):
        if row.get("phase") not in setup_ids:
            continue
        line = plan.command_lines[index] if index < len(plan.command_lines) else 0
        where = f"{plan.path}:{line}"
        command = row.get("command", "").strip().lstrip("/").strip()
        if re.match(r"^(?:minecraft:)?item\s+replace\s+block\b", command):
            m = _ITEM_RE.match(command)
            if not m:
                raise PlanError(f"{where}: malformed item replace command {command!r}")
            pos = _coords(m.group(1, 2, 3), where)
            loads.setdefault(pos, {})[int(m.group(4))] = _item_stack(m.group(5), where)
        elif re.match(r"^(?:minecraft:)?data\s+merge\s+block\b", command):
            m = _DATA_RE.match(command)
            if not m:
                raise PlanError(f"{where}: malformed data merge command {command!r}")
            pos = _coords(m.group(1, 2, 3), where)
            stacks = _data_stacks(m.group(4), where)
            if stacks is not None:
                loads[pos] = stacks
    return loads


# --- read JSON ------------------------------------------------------------

def load_read(path: Path) -> tuple[dict[Pos, State], tuple[Pos, Pos]]:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise PlanError(f"{path}:1: cannot read: {exc.strerror or exc}") from None
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path}:{exc.lineno}: bad JSON: {exc.msg}") from None
    if not isinstance(data, dict) or not isinstance(data.get("cells"), dict):
        raise PlanError(f"{path}:1: not an ashlar_place.py read result (no `cells` object)")
    where = str(path)
    box = (_int3(data.get("from"), where, "from"), _int3(data.get("to"), where, "to"))
    cells: dict[Pos, State] = {}
    for key, text in data["cells"].items():
        parts = key.split(",")
        try:
            pos = _int3([int(p) for p in parts], where, "cell key")
        except ValueError:
            raise PlanError(f"{where}: bad cell key {key!r}") from None
        cells[pos] = _state_in(text, f"{where} cell {key}")
    return cells, box
