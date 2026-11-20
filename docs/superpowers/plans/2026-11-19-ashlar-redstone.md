# Ashlar Redstone (Sub-project 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port Chapman's `system-redstone` skill to Ashlar for Claude Code and Codex, add a functional-test protocol to `exec-ashlar`, add an offline resting-state checker and a benchmark suite, then prove the result live on rungs 0–2 after the merge.

**Architecture:** `system-redstone` designs a machine as modules in local coordinates, stamps them with `exec-ashlar`'s `stamp.py`, and checks every redstone part's written state offline with a new stdlib checker (`redstone_plan.py` parses plans, `redstone_model.py` models Java power and settles the circuit, `redstone_rest.py` is the CLI). It hands the plan to `exec-ashlar build` and then to a new `exec-ashlar test` mode, which runs a `tests` table from `plan.toon` with allowlisted container loads and reads, and records four verdicts (built, at rest, agent tested, manual). A new `ashlar_place.py read` subcommand, built on a column reader shared with the terrain branch, pulls exact block states for the checker's `diff`.

**Tech Stack:** Markdown Agent Skills (Claude Code and Codex); Python 3.11+ standard library; pytest through `uv run`; Node 20+ for upstream's `scripts/validate-plugin.mjs`; Ashlar 0.4.9 MCP tools on Paper 26.3.

**Spec:** `docs/superpowers/specs/2026-11-19-ashlar-redstone-design.md` (approved as `8373799`, two Java dust rules corrected in `e5b245b`). Executors read the spec and this plan together. "Spec §N" means that section; text marked "verbatim from spec §N" is copied word for word, changing only heading levels and cross-references.

## Global Constraints

- **Repository:** the worktree `/Users/bsw/Development/Minecraft/ashlar-design-skills-redstone`, branch `redstone`. Run every command from the worktree root. The workspace root, which holds `.minecraft-builder/`, `.claude/` and `.agents/`, is `/Users/bsw/Development/Minecraft`. Never switch the branch of the main clone `ashlar-design-skills/` except in Task 11, with the user's OK.
- **Commits:** every task ends with a commit on `redstone`, whose message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push, open a PR or merge except in Task 10, and only after the user says yes at that moment.
- **Test commands:**
  - everything: `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q`
  - one file: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/<file> -q`
  - upstream validator: `node scripts/validate-plugin.mjs` → `✓ plugin, marketplace, skills, and agents are valid`
- **Python:** scripts use only the standard library, start with the same `require_python()` guard as `stamp.py` (exit 2 with a one-line message on Python older than 3.11), and are run as `python3 <skill>/scripts/<name>.py`. Sibling modules in the same `scripts/` folder import each other by plain `import`.
- **Orientation conventions (vanilla Java), used by the model, the fixtures and the skill text:**
  - repeater and comparator: `facing` points at the **input**; input at `pos + facing`, output at `pos − facing`;
  - observer: watches `pos + facing`, outputs at `pos − facing`;
  - piston: the head goes to `pos + facing`;
  - hopper: pushes into `pos + facing` (`down` or horizontal);
  - lever and button: `face=floor` sits on the block below, `ceiling` hangs on the block above, `wall` hangs on `pos − facing`;
  - wall torch hangs on `pos − facing`, a standing torch on the block below;
  - door halves: `half=lower` at y, `half=upper` at y+1.
- **Shared column reader** (agreed with the terrain branch on 2026-11-19; both plans use these exact names in `skills/exec-ashlar/scripts/ashlar_place.py`):
  - `column_tiles(box: Box, max_columns: int = 1024, max_cells: int = 200_000) -> list[Box]`
  - `parse_columns(text: str) -> dict[tuple[int, int], list[tuple[int, int, str]]]`
  - `read_columns(client: McpClient, box: Box, world: str | None) -> dict[tuple[int, int], list[tuple[int, int, str]]]`

  If `origin/main` (or the `terrain` branch, once merged) already has them, reuse them and drop the matching steps in Task 1.
- **Skill text rules** (from sub-project 1 spec §7.5, enforced by `tests/ashlar/test_skill_text.py`):
  - No Chapman tool names. No `${CLAUDE_PLUGIN_ROOT}`, `exec-plan`, `exec-worker`, `exec-inspect`, `exec-blueprint`, `exec-reflect`, `survey-site`, `mcbuilder`, "orchestrator", "Fabric", `32,768`, or a world top of 320.
  - Client-specific tool names appear only on lines labelled `Claude Code:` or `Codex:`, each pair followed by an `Otherwise:` line.
  - Cross-skill links use sibling paths (`../exec-ashlar/...`) or the `exec-ashlar/reference/<file>.md` form; never repo-root paths.
  - Shared text names Ashlar tools without a client prefix (`mc_build`, not `mcp__ashlar__mc_build`).
- **Upstream files:** do not edit Chapman's other skills (`exec-inspect`, `exec-reflect`, the `build-*`, `terrain-*` and `setup-*` skills), his agents or `tools/`. Beyond `skills/system-redstone/` and `skills/exec-ashlar/`, the only repo files this plan changes are `tests/ashlar/*`, `CLAUDE.md`, `README.md`, `skills/TAXONOMY.md` and the new `docs/benchmarks/redstone/`.
- **Console:** the allowlist in `skills/exec-ashlar/reference/commands.md` does not change. Test `load` rows use only `item replace block` and `data merge block`.
- **Ashlar limits:** 1,024 columns per `mc_inspect` columns call; 200,000 cells per read or snapshot; 16 queued operations (send reads in batches of at most 12); overworld y −64 to 319.
- **Live world:**
  - Only Tasks 9 (read-only) and 11–14 touch the server.
  - Writes happen only through `exec-ashlar`'s approval gate, after the user says yes at that moment.
  - Benchmark results go to `/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md`, never into the repo.
- **Secrets and server facts:** never print, log or commit the Ashlar URL or token (in `~/.claude.json` and `~/.codex/config.toml`), and never read those files with a command that echoes values. No server folder names, hosts, IPs or player names in the repo.
- **Workspace links:** create `.claude/skills/system-redstone` and `.agents/skills/system-redstone` only in Task 11. Earlier links would serve Chapman's unported skill.

**User decisions (already made):**
- Benchmarks, in the user's words: "the first substantial benchmark should be a two-item automatic sorting system with an overflow chest"; "This should be followed by a 2×2 sticky-piston door … I'd manually activate it and verify that it opens and closes correctly through at least ten consecutive cycles"; "After that, I'd like to benchmark an observer-driven sugar cane farm, a controllable redstone clock, and ultimately a 3×3 piston door."
- "the skill should distinguish between successfully constructing a design and verifying that the design functions. If Ashlar cannot operate the lever or otherwise trigger a machine, the agent should explicitly report that manual validation is required rather than claim the machine is working."
- "Eventually, we should test constructing the same design in different orientations, with different available footprints, and recovering gracefully from failed builds."
- Test inputs on lever-driven machines: "Offer it per build".
- Approach: "C: with the checker".
- Design parts 1–3: "Looks right", each time.
- Live runs: "Merge first".
- Spec: "Approve and commit". Plan: "Write the plan".
- Standing rules from sub-projects 1 and 2: complex redstone is fine when the prompt calls for it; `mc_command` stays allowlist-only (the user declined an "ask" permission), never command blocks or `Command` NBT; ask before any push, merge or live-world write.

## Review Focus

Inputs the spec implies but that are easy to miss. Each has a pinned test in the task that owns the code.

1. **Negative coordinates and negative y in `mc_inspect` output**, for example `-3,-5: -64--62 bedrock`. Expected: correct columns and runs, never a crash or a shifted run. Test: `test_parse_columns_negative_coordinates_and_ys` (Task 1).
2. **Console commands in `plan.toon` holding commas and escaped quotes** (SNBT in `data merge block`, item components). Expected: the command cell comes back intact. Test: `test_toon_rows_keep_quoted_commas_and_quotes` (Task 2).
3. **The same machine stamped in another rotation or mirrored.** Expected: the checker gives the same verdicts in every orientation. Test: `test_rotation_and_mirror_give_same_verdicts` (Task 4).
4. **A latch written in either of its stable states.** Expected: clean, not "cannot settle". Test: `test_rs_latch_keeps_written_state` (Task 3).
5. **A block the model does not know, next to redstone** (a rail, a target block, a modded block). Expected: listed as unmodelled for a hand check, never silently treated as air or as a conductor. Test: `test_unknown_neighbour_is_reported_unmodelled` (Task 3).

---

## File map

| File | Responsibility | Task |
| --- | --- | --- |
| `skills/exec-ashlar/scripts/ashlar_place.py` | add the shared column reader and the `read` subcommand | 1 |
| `tests/ashlar/fake_ashlar_mcp.py` | answer `mc_inspect` columns calls | 1 |
| `tests/ashlar/test_place_read.py` | reader and `read` tests | 1 |
| `skills/system-redstone/scripts/redstone_plan.py` | block states, TOON tables, plan and phase loading, setup loads, read files | 2 |
| `skills/system-redstone/scripts/redstone_model.py` | conductivity and stack tables, Java power rules, dust shapes, settling, structural checks | 3 |
| `skills/system-redstone/scripts/redstone_rest.py` | CLI: `check`, `diff`, `containers`; reports and exit codes | 4 |
| `tests/ashlar/conftest.py` | also put `skills/system-redstone/scripts` on `sys.path` | 2 |
| `tests/ashlar/test_redstone_plan.py`, `test_redstone_model.py`, `test_redstone_rest.py` | checker tests | 2, 3, 4 |
| `tests/ashlar/redstone_fixtures.py` | fixture builders: sorter slice, 2×2 door module, clocks | 4 |
| `skills/exec-ashlar/SKILL.md`, `reference/{plan-format,execution,verification,registry,commands}.md` | `tests` table, `test` mode, verdicts, gate additions, recovery | 5 |
| `skills/system-redstone/**` (all Markdown) | the text port | 6 |
| `tests/ashlar/test_skill_text.py` | add `system-redstone`; more Chapman names | 6 |
| `CLAUDE.md`, `README.md`, `skills/TAXONOMY.md` | fork notes | 7 |
| `docs/benchmarks/redstone/*.md` | the benchmark suite | 8 |

---

### Task 1: Shared column reader and `ashlar_place.py read`

**Goal:** Add the column reader shared with the terrain branch and a read-only `read` subcommand that writes a box's exact block states to JSON.

**Files:**
- Modify: `skills/exec-ashlar/scripts/ashlar_place.py` (module docstring usage lines, new functions after `tile()`, `cmd_read`, `build_parser`, `main` handlers)
- Modify: `tests/ashlar/fake_ashlar_mcp.py`
- Create: `tests/ashlar/test_place_read.py`

**Interfaces** (used by Tasks 4, 5 and 9):
- `column_tiles`, `parse_columns`, `read_columns`: the signatures in Global Constraints.
- `cmd_read(ns: argparse.Namespace) -> int`.
- Command line: `ashlar_place.py read X1 Y1 Z1 X2 Y2 Z2 --out FILE [--world W] [--server NAME] [--config PATH]`.
- Output JSON: `{"world": W or null, "from": [x, y, z], "to": [x, y, z], "cells": {"x,y,z": "minecraft:<state>", ...}}`, with every cell in the box including air, corners sorted.

**Acceptance Criteria:**
- [ ] `column_tiles` covers the box exactly, with no overlaps; every tile keeps the box's full y range and has at most `max_columns` columns and `max_cells` cells.
- [ ] `parse_columns` skips the header line and any line that does not start with `<int>,<int>:`. It parses single-y runs (`62 water[level=0]`), ranges (`63-70 air`) and negative values (`-64--62 bedrock`), and adds `minecraft:` where missing. A column line whose runs do not parse raises `PlacerError(…, EXIT_SERVER)`.
- [ ] `read` writes the JSON only after every tile succeeds. On an `isError` reply it exits 5, writes nothing and prints no secret. A y outside −64..319 exits 2.
- [ ] Every existing test still passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_place_read.py tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q` → all pass

**Steps:**

- [ ] **Step 0: Check whether the terrain branch already landed the reader**

Run: `git fetch origin && git log --oneline origin/main -- skills/exec-ashlar/scripts/ashlar_place.py | head -5` and `git grep -n "def column_tiles" origin/main -- skills/exec-ashlar/scripts/ashlar_place.py`
If `column_tiles` exists on `origin/main`, rebase `redstone` onto it (`git rebase origin/main`), skip Steps 1–4 for the three shared functions, and keep only the `read` subcommand work.

- [ ] **Step 1: Teach the fake server `mc_inspect`**

In `fake_ashlar_mcp.py`, add an `mc_inspect` branch and document three new knobs in the docstring:
- `FAKE_FAIL_INSPECT`: when set, reply `isError` with `Error: region too large`.
- `FAKE_INSPECT_BOTTOM`: when set, the bottom cell of every column is this state.
- Every other cell is `air`.

For `format: "columns"`, reply with the header line `Region (default) x=[x1..x2] y=[y1..y2] z=[z1..z2], runs bottom to top (ids without the minecraft: prefix):`, then one line per column, `x` outer and `z` inner: `f"{x},{z}: {runs}"`. Write runs as `"{y1}-{y2} air"`, or `"{y} air"` for a single cell, with the bottom cell split off as `"{y1} {FAKE_INSPECT_BOTTOM}"` when that knob is set, and runs joined by `" | "`. Sort `from` and `to` before use.

- [ ] **Step 2: Write the failing tests** in `tests/ashlar/test_place_read.py`

Reuse `config`, `run`, `calls`, `assert_no_secrets` from `test_place_mcp.py` by importing them (`from test_place_mcp import config, run, calls, assert_no_secrets`).

```python
from ashlar_place import column_tiles, parse_columns, volume

def _disjoint(a, b):
    return any(a[i] > b[i + 3] or b[i] > a[i + 3] for i in range(3))

def test_column_tiles_respects_both_caps():
    box = (0, -64, 0, 99, 319, 99)
    tiles = column_tiles(box)
    assert sum(volume(t) for t in tiles) == volume(box)
    assert all(_disjoint(a, b) for i, a in enumerate(tiles) for b in tiles[i + 1:])
    for t in tiles:
        assert (t[3] - t[0] + 1) * (t[5] - t[2] + 1) <= 1024
        assert volume(t) <= 200_000
        assert (t[1], t[4]) == (-64, 319)

def test_column_tiles_small_box_is_one_tile():
    assert column_tiles((0, 64, 0, 1, 65, 1)) == [(0, 64, 0, 1, 65, 1)]

def test_parse_columns_runs_and_namespace():
    text = ("Region (default) x=[0..0] y=[62..70] z=[0..0], runs bottom to top:\n"
            "0,0: 62 water[level=0] | 63-70 air")
    assert parse_columns(text) == {(0, 0): [(62, 62, "minecraft:water[level=0]"),
                                            (63, 70, "minecraft:air")]}

def test_parse_columns_negative_coordinates_and_ys():
    text = "-3,-5: -64--62 bedrock | -61-10 minecraft:stone"
    assert parse_columns(text) == {(-3, -5): [(-64, -62, "minecraft:bedrock"),
                                              (-61, 10, "minecraft:stone")]}

def test_parse_columns_keeps_states_with_commas():
    text = "1,2: 65 redstone_wire[east=side,north=none,power=0,south=none,west=side]"
    assert parse_columns(text)[(1, 2)][0][2] == (
        "minecraft:redstone_wire[east=side,north=none,power=0,south=none,west=side]")
```

CLI tests (subprocess, with the fake server config):
- `test_read_writes_every_cell`: `read 0 64 0 1 65 1 --out <tmp>/r.json` with `FAKE_INSPECT_BOTTOM="redstone_wire[power=3]"`. The return code is 0, and the JSON has 8 cells, with `cells["0,64,0"] == "minecraft:redstone_wire[power=3]"` and `cells["1,65,1"] == "minecraft:air"`. The call log shows one `mc_inspect` with `format == "columns"`, `from == [0, 64, 0]` and `to == [1, 65, 1]`.
- `test_read_tiles_large_box`: `read 0 64 0 39 64 39` makes 2 `mc_inspect` calls and writes 1,600 cells.
- `test_read_negative_coordinates_cli`: `read -5 64 -5 -4 64 -4` returns 0 and writes 4 cells.
- `test_read_server_error_exits_5_and_writes_nothing`: with `FAKE_FAIL_INSPECT=1`, the return code is 5, the out file does not exist, and `assert_no_secrets(proc)` passes.
- `test_read_rejects_y_outside_world`: `read 0 400 0 1 401 1` returns 2.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_place_read.py -q`
Expected: FAIL with an `ImportError` for `column_tiles`

- [ ] **Step 4: Implement the three shared functions and `cmd_read`**

- `column_tiles`: split the box in x and z only, into rectangles of at most `min(max_columns, max_cells // height)` columns. Keep the existing `tile()` for snapshots.
- `parse_columns`: one regex per line, `^(-?\d+),(-?\d+):\s*(.*)$`. Split the rest on `" | "`; each run matches `^(-?\d+)(?:-(-?\d+))?\s+(\S+)$`.
- `read_columns`: call `client.call("mc_inspect", {"from": [...], "to": [...], "format": "columns"} + world)` per tile, and merge the results.
- `cmd_read`:
  - validate the six ints with `_coords(...)` and the default `Limits`;
  - read through `McpClient(_server(ns))`, closing it in `finally`;
  - flatten the runs to `{"x,y,z": state}`, check every cell in the box was read (`PlacerError(EXIT_SERVER)` otherwise), then write the file;
  - print one line, `read <cells> cells in <calls> calls -> <out>`.

Add `read` to `build_parser` (`_add_server`, `--out` required, `--world`) and to `main`'s handlers, and add the usage line to the module docstring.

- [ ] **Step 5: Run the tests to verify they pass**

Run: the **Verify** command. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/fake_ashlar_mcp.py tests/ashlar/test_place_read.py
git commit -m "feat(exec-ashlar): shared column reader and ashlar_place.py read"
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/fake_ashlar_mcp.py", "tests/ashlar/test_place_read.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_place_read.py tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q", "acceptanceCriteria": ["column_tiles covers the box exactly within both caps", "parse_columns handles headers, single-y runs, ranges, negatives and adds minecraft:", "read writes JSON only after every tile succeeds; isError exits 5 with no file and no secrets; bad y exits 2", "existing placer tests pass"], "modelTier": "standard"}
```

---

### Task 2: Checker plan loading (`redstone_plan.py`)

**Goal:** Parse block states, `plan.toon` tables, phase files, setup container loads and `read` JSON into the world model the checker works on.

**Files:**
- Create: `skills/system-redstone/scripts/redstone_plan.py`
- Modify: `tests/ashlar/conftest.py` (also insert `REPO/skills/system-redstone/scripts`)
- Create: `tests/ashlar/test_redstone_plan.py`

**Interfaces** (used by Tasks 3 and 4):

```python
Pos = tuple[int, int, int]

class PlanError(Exception): ...          # bad input; the CLI exits 2

@dataclass(frozen=True)
class State:
    id: str                               # always "minecraft:..."
    props: tuple[tuple[str, str], ...]    # sorted by key
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def with_props(self, **changes: str) -> "State": ...

def parse_state(text: str) -> State
def format_state(state: State) -> str     # "minecraft:id[k=v,...]", keys sorted, no [] when empty

@dataclass(frozen=True)
class Stack:
    item: str                             # "minecraft:..." without components
    count: int

@dataclass
class Plan:
    path: Path
    project: str
    world: str | None
    bbox: tuple[Pos, Pos]
    phases: list[dict[str, str]]
    commands: list[dict[str, str]]        # the command cell unquoted and unescaped
    tests: list[dict[str, str]]

def read_toon_table(text: str, name: str) -> list[dict[str, str]]   # [] when absent
def load_plan(path: Path) -> Plan
def assemble(plan: Plan, background: dict[Pos, State] | None = None) -> dict[Pos, State]
def setup_loads(plan: Plan) -> dict[Pos, dict[int, Stack]]           # pos -> slot -> stack
def load_read(path: Path) -> tuple[dict[Pos, State], tuple[Pos, Pos]]
```

**Rules:**
- **TOON tables:** a header `^<name>\[\d+\]\{<cols>\}:\s*$` (the count is not checked), then the following indented lines. Cells split on commas outside double quotes; a quoted cell loses its quotes and has `\"` turned into `"`.
- **The `plan:` block:** gives `project`, `world` (optional) and `bbox: {from: [x, y, z], to: [x, y, z]}`.
- **`assemble`:**
  - Applies the `phases` rows in order, skipping rows with `via` `commands` or `file` `-`. Phase files are relative to the plan's folder; a bare list means `{"fills": list}`.
  - Within a phase, fills come in order, then blocks; `text` is ignored.
  - Fill modes match `exec-ashlar/reference/tools-and-limits.md`:
    - `replace` writes every cell;
    - `keep` writes only cells that are absent or air;
    - `outline` writes the 6-face shell;
    - `hollow` writes the shell and sets the inside to air;
    - `walls` writes the 4 vertical sides.
  - `filter` limits a fill to cells whose current state has the same id and equal values for the properties the filter names. An absent cell counts as `minecraft:air`.
  - Background cells fill only positions the plan never writes.
- **`setup_loads`:** reads `commands` rows whose `phase` is a `commands` phase:
  - `[minecraft:]item replace block X Y Z container.N with ITEM[COMPONENTS] [COUNT]`, where the count defaults to 1 and the components are dropped from the item;
  - `[minecraft:]data merge block X Y Z {…Items:[{Slot:Nb,id:"…",count:N},…]…}`, accepting `Slot`/`slot` and `count`/`Count`.

  Rows from the `tests` table are never setup.

**Acceptance Criteria:**
- [ ] Every test below passes, and `test_place_*` still passes.
- [ ] `PlanError` names the file and line for an unreadable plan, a bad state string or a bad command row.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_plan.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/ashlar/test_redstone_plan.py`

```python
from redstone_plan import (PlanError, Stack, assemble, format_state, load_plan,
                           load_read, parse_state, read_toon_table, setup_loads)

def test_parse_state_roundtrip():
    s = parse_state("repeater[facing=north,delay=2]")
    assert s.id == "minecraft:repeater" and s.get("delay") == "2"
    assert format_state(s) == "minecraft:repeater[delay=2,facing=north]"
    assert format_state(parse_state("minecraft:stone")) == "minecraft:stone"

def test_toon_rows_keep_quoted_commas_and_quotes():
    text = ('commands[1]{phase,seq,command,purpose}:\n'
            '  4,1,"data merge block 1 2 3 {Items:[{Slot:0b,id:\\"minecraft:stone\\",count:18}]}",filters\n')
    row = read_toon_table(text, "commands")[0]
    assert row["command"] == 'data merge block 1 2 3 {Items:[{Slot:0b,id:"minecraft:stone",count:18}]}'
    assert row["purpose"] == "filters"
```

Further tests, each written as plain asserts on a small `plan.toon` and phase JSON written into `tmp_path`:
- `test_load_plan_reads_header_and_tables`: the project, the `bbox`, three `phases` rows with their `via`.
- `test_assemble_applies_phases_fills_then_blocks`: phase 1 fills stone over `0 0 0`–`2 0 2`; phase 2's blocks set `1 0 1` to dirt; a `keep` fill of glass over the same box changes nothing.
- `test_assemble_shell_modes`: on a 3×3×3 box, `walls` leaves the centre column unset, `outline` sets the top and bottom, and `hollow` sets the centre to air.
- `test_assemble_filter_matches_unspecified_props_as_wildcards`: a fill with `filter: "minecraft:oak_stairs"` replaces `oak_stairs[facing=east,half=top]`.
- `test_setup_loads_item_replace_and_data_merge`:
  - `item replace block 5 64 5 container.0 with minecraft:cobblestone 18` and `… container.1 with minecraft:stick[custom_name="F"]` give `{(5, 64, 5): {0: Stack("minecraft:cobblestone", 18), 1: Stack("minecraft:stick", 1)}}`;
  - a `data merge block` row with two `Items` entries gives both slots.
- `test_setup_loads_ignores_test_rows`: a `tests` `load` row adds nothing.
- `test_load_read_parses_cells`: the JSON shape from Task 1 comes back as `{(0, 64, 0): State(...)}` plus its box.
- `test_bad_state_raises_plan_error`: `parse_state("stone[facing")` raises `PlanError`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: the **Verify** command. Expected: FAIL with `ModuleNotFoundError: redstone_plan`

- [ ] **Step 3: Implement `redstone_plan.py`** with the interfaces and rules above, plus the `require_python()` guard. Add the second `sys.path` insert to `conftest.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the **Verify** command. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/system-redstone/scripts/redstone_plan.py tests/ashlar/conftest.py tests/ashlar/test_redstone_plan.py
git commit -m "feat(system-redstone): checker plan loading"
```

```json:metadata
{"files": ["skills/system-redstone/scripts/redstone_plan.py", "tests/ashlar/conftest.py", "tests/ashlar/test_redstone_plan.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_plan.py -q", "acceptanceCriteria": ["all test_redstone_plan.py tests pass", "PlanError names file and line for bad input"], "modelTier": "standard"}
```

---

### Task 3: Redstone model and settling (`redstone_model.py`)

**Goal:** Model Java Edition redstone power for the components the benchmarks use, settle a circuit from its written states, and report mismatches, structural errors, loops that cannot settle and unmodelled neighbours.

**Files:**
- Create: `skills/system-redstone/scripts/redstone_model.py`
- Create: `tests/ashlar/test_redstone_model.py`

**Interfaces** (used by Task 4):

```python
POWER_PROPS = ("power", "powered", "lit", "extended", "enabled", "triggered", "locked", "open")

def is_conductor(state: State | None) -> bool | None      # None: unknown
def stack_size(item: str) -> tuple[int, bool]             # (size, known)
def container_slots(world: dict[Pos, State], pos: Pos) -> int | None   # None: not a container
def container_signal(world, contents: dict[Pos, dict[int, Stack]], pos: Pos) -> int

@dataclass
class Report:
    mismatches: list[tuple[Pos, str, str, str]]   # pos, written, expected, reason
    structural: list[tuple[Pos, str]]
    unsettled: list[Pos]
    unmodelled: list[tuple[Pos, str]]             # pos, reason
    warnings: list[str]

def solve(world: dict[Pos, State], contents: dict[Pos, dict[int, Stack]],
          max_rounds: int = 64) -> tuple[dict[Pos, State], list[Pos]]
def check_world(world: dict[Pos, State], contents: dict[Pos, dict[int, Stack]]) -> tuple[dict[Pos, State], Report]
def switch_on(world: dict[Pos, State], pos: Pos) -> dict[Pos, State]   # lever/button/plate powered=true
def power_diff(before: dict[Pos, State], after: dict[Pos, State]) -> list[tuple[Pos, str, str]]
    # (pos, before, after) as format_state strings, for every position whose power properties differ, sorted by pos
```

**The model contract.** Every rule gets at least one test, with a comment citing its source: the wiki page and section read on 2026-11-19 (spec §8.3 table), or "vanilla Java behaviour" for the orientation conventions in Global Constraints.

| # | Rule |
| --- | --- |
| R1 | **Conductors.** A curated table seeded from the wiki's "Conductivity" page (fetch it through the Minecraft Wiki MCP or `trafilatura -u https://minecraft.wiki/w/Conductivity`). It covers at least the full blocks used in the fixtures, the containers and redstone parts (conductive: dispenser, dropper, note block, redstone lamp, target, barrel; not conductive: glass and stained glass, slabs other than `type=double`, stairs, walls, fences, panes, leaves, glowstone, hopper, chest, trapped chest, piston, sticky piston, piston head, observer, redstone block) and air. Anything else returns `None`. |
| R2 | **Torch lit.** Unlit when its block (standing: below; wall: `pos − facing`) is powered, strongly or weakly. When that block is not a conductor, its own signal counts (a torch on a redstone block is unlit). |
| R3 | **Torch output.** Powers dust and components on every side except its own block, and strongly powers the block above. Powers no other block. |
| R4 | **Lever and button.** When powered, they power adjacent dust and components and strongly power the block they hang on. |
| R5 | **Redstone block.** Powers adjacent dust and components at 15; powers no block. |
| R6 | **Repeater.** Input from `pos + facing` (a source's signal toward it, or a conductor's strong or weak power). `locked` is true when a repeater or comparator on either side faces into it with output above 0; a locked repeater keeps its written `powered`. When powered it outputs 15 at `pos − facing` and strongly powers that block. |
| R7 | **Comparator.** The rear is the signal from `pos + facing`. If that block is a container, its fullness counts instead; if it is a conductor powered below 15 with a container at `pos + 2·facing`, that container's fullness counts. The side is the larger of the two sides' dust power, 15 for a redstone block, or the output of a repeater or comparator facing into it. The output is 0 if the rear is 0 or the side is greater than the rear; otherwise it is the rear in compare mode, or the rear minus the side in subtract mode. `powered` is output above 0; it strongly powers `pos − facing`. |
| R8 | **Containers.** Hopper 5 slots, dropper and dispenser 9, chest, trapped chest and barrel 27; two chests side by side with the same `facing`, on the axis across that facing, pair to 54 with contents combined. A chest or trapped chest with a conductor above it reads 0. Signal: 0 when empty, else `floor(1 + (Σ count·64/stack_size / 64 / slots) × 14)`. |
| R9 | **Observer.** `powered=true` at rest is a structural error. If written powered it acts as a 15 source at `pos − facing`, strongly powering that block. |
| R10 | **Dust shape** (Java). A side connects to dust; to a power source on any side (lever, button, pressure plate, torch, redstone block, comparator); to a repeater only along its axis; to an observer only at its back (`d == observer facing`); up a step (the neighbour can hold dust, has dust on top, and no conductor sits above this dust); or down a step (the neighbour is not a conductor and has dust below it). It never connects to pistons or other mechanism components. One connection makes a line through both sides; two or more give exactly those sides. With none: a wire written with all four sides `side` is a cross; otherwise it is a dot. |
| R11 | **Dust power.** The largest of: non-dust sources around it (sources pointing at it and strongly powered conductors sharing any face with it) and neighbouring dust power − 1 (same level; up a step only through a conductor whose top has dust, with no conductor above this dust; down a step only past a non-conductor). Powered dust weakly powers the block below it and each block its sides point into; a dot points into nothing. |
| R12 | **Component signal**, for lamps, hoppers, note blocks, doors, trapdoors and fence gates. True when any neighbour gives signal toward it: a source (not a torch hanging on it), a repeater, comparator or observer output facing it, dust pointing into it or sitting on it, or an adjacent conductor that is strongly or weakly powered. |
| R13 | **Pistons, droppers and dispensers.** Powered by R12 at their own position (pistons: excluding the face they push), or by quasi-connectivity: R12 evaluated for `pos + up`, excluding the piston itself. Pistons: `extended` must equal powered. Droppers and dispensers: `triggered` must equal powered. |
| R14 | **Piston structure.** An extended piston needs `piston_head[facing=<same>, type=<sticky for sticky_piston, else normal>, short=false]` at `pos + facing`. A head needs an extended base of the matching type at `head − facing`. Anything else at `pos + facing` of an extended piston is an error. |
| R15 | **Activation.** Hopper `enabled = not signal`. Lamp `lit = signal`. Note block, trapdoor and fence gate `powered = signal`. Doors: `powered = signal at either half`, the same on both halves. When a door, trapdoor or gate is powered at rest, `open` must be true. |
| R16 | **Settling.** Start from the written states. Each round recomputes dust (to a fixed point within the round), then torches, repeaters (respecting locks), comparators, then the derived states (R13, R15), all from the previous round's values. Stop when a round changes nothing. Report every position that varies across a repeated cycle. If the round limit is reached before a cycle repeats, report the positions observed changing during the bounded run. |
| R17 | **Unmodelled and unwritten neighbours.** A neighbour of a modelled component is listed as unmodelled with a reason, and treated as a non-conductor giving no signal, when it is a redstone-relevant block outside this model (rails, tripwire and hooks, daylight detector, target, lectern, sculk sensors, copper bulb, crafter, cake, cauldron, composter, item frame, bell, trapped chest output), or `is_conductor(...) is None`. A neighbour absent from the world (not written by the plan, no `--background`) is treated as air, per spec §8.1, and adds one entry to `Report.warnings` per modelled component at the edge: `x y z: neighbour not written by the plan; treated as air; pass --background to include the site`. Warnings never change the exit code. (Ruling 2026-11-20, plan author.) |
| R18 | **Stack sizes.** 16 for ender pearls, eggs, snowballs, signs, banners, empty buckets, honey bottles, armor stands and written books. 1 for tools, weapons, armour, minecarts, boats, saddles, potions, filled buckets, shulker boxes, writable books, enchanted books, music discs, totems, elytra, tridents, bows, crossbows, shields, fishing rods, shears and flint and steel. Java 26.3 registers `written_book` at 16 and `writable_book` at 1. 64 for a known common set, at least the items in this plan's fixtures and benchmarks. An unknown item counts as 64 and adds a warning. |

**Acceptance Criteria:**
- [ ] Every rule R1–R18 has at least one passing test with a source comment.
- [ ] `check_world` reports written power properties that differ from the settled state as mismatches, with the rule as the reason (for example `R2: block below is powered`).
- [ ] Review Focus 4 and 5 tests pass.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_model.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/ashlar/test_redstone_model.py`

Build worlds as dicts with a small local helper `w(**cells)`, or a list of `(pos, "state")` pairs. Pinned values:

```python
def test_comparator_reads_hopper_fullness_22_and_23():
    # filter hopper: 18 cobblestone + 1 stick in each of slots 1-4 = 22 items -> 1; 23 -> 2
    ...
    assert container_signal(world, {hopper: slots22}, hopper) == 1
    assert container_signal(world, {hopper: slots23}, hopper) == 2

def test_container_signal_stack_sizes_and_double_chest():
    assert container_signal(world, {hopper: {0: Stack("minecraft:ender_pearl", 1)}}, hopper) == 1
    assert container_signal(world, {dropper: {0: Stack("minecraft:minecart", 1)}}, dropper) == 2
    four_stacks = {i: Stack("minecraft:cobblestone", 64) for i in range(4)}
    assert container_signal(world_single_chest, {chest: four_stacks}, chest) == 3
    assert container_signal(world_double_chest, {chest_a: four_stacks}, chest_a) == 2
```

Named tests, one or more per rule, each asserting the settled state or the report:
- `test_torch_unlit_when_its_block_is_powered_by_dust` (R2)
- `test_torch_on_redstone_block_is_unlit` (R2)
- `test_torch_strongly_powers_block_above_but_not_side_blocks` (R3): a lamp next to the side block stays unlit; dust on the block above is powered.
- `test_lever_strongly_powers_its_block` (R4): dust next to the lever's block gets 15.
- `test_redstone_block_powers_dust_not_blocks` (R5)
- `test_repeater_reads_input_from_its_facing_side` (R6): `repeater[facing=north]` at `0 0 0` is powered by a redstone block at `0 0 -1` and powers a lamp at `0 0 1`. Use a separate setup to check that the repeater gives no power behind it, since a lamp at `0 0 -2` in the first setup touches the input source.
- `test_repeater_locked_by_powered_side_repeater` (R6)
- `test_comparator_reads_hopper_fullness_22_and_23` (R7, R8)
- `test_comparator_reads_through_conductor_unless_block_powered_15` (R7)
- `test_comparator_compare_and_subtract` (R7): rear 10, side 4 gives compare 10 and subtract 6; side 11 gives 0.
- `test_container_signal_stack_sizes_and_double_chest` (R8, R18)
- `test_chest_under_conductor_reads_zero` (R8)
- `test_observer_written_powered_is_structural_error` (R9)
- `test_dust_line_powers_block_it_points_into_and_below` (R10, R11)
- `test_lone_dust_dot_vs_cross` (R10): a lone wire written without sides powers only the block below; one written with four `side`s powers a lamp beside it.
- `test_dust_does_not_connect_to_piston_side` (R10)
- `test_dust_steps_down_only_from_conductive_block` (R11): dust on stone one level up powers lower dust beside it; dust on glass does not; lower dust powers dust on glass.
- `test_conductive_block_above_cuts_step` (R10, R11)
- `test_weakly_powered_block_activates_lamp_but_not_dust` (R11, R12)
- `test_piston_quasi_connectivity_from_block_above` (R13): a lever next to the air block above a piston powers it.
- `test_piston_not_powered_through_its_front_face` (R13)
- `test_dropper_triggered_by_quasi_connectivity` (R13)
- `test_piston_head_structural_errors` (R14): an extended piston without a head, a head without a base, and a sticky base with a `type=normal` head each give one structural entry.
- `test_hopper_locked_when_powered` (R15)
- `test_door_powered_from_upper_half_and_open_when_powered` (R15)
- `test_rs_latch_keeps_written_state` (R16, Review Focus 4): an RS-NOR latch from two cross-coupled torches (wiki "Logic circuit", memory section) written in either stable state is clean; written with both torches lit, it reports mismatches or unsettled positions.
- `test_torch_loop_cannot_settle` (R16): a torch whose output dust powers its own block reports both positions unsettled.
- `test_unknown_neighbour_is_reported_unmodelled` (R17, Review Focus 5): a `minecraft:powered_rail` next to dust and an unknown `example:block` next to a lamp are each listed, and the lamp stays unlit.
- `test_unknown_item_counts_as_64_with_warning` (R18)

- [ ] **Step 2: Run the tests to verify they fail**

Run: the **Verify** command. Expected: FAIL with `ModuleNotFoundError: redstone_model`

- [ ] **Step 3: Implement `redstone_model.py`**

Per the contract. Keep signal lookups as small functions:
- `strong_into(world, pos)`;
- `weak_into(world, pos)` (dust only);
- `signal_toward(world, src, toward)`;
- `component_signal(world, pos, exclude=())`.

Recompute dust shapes inside each round from the current neighbours.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the **Verify** command. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/system-redstone/scripts/redstone_model.py tests/ashlar/test_redstone_model.py
git commit -m "feat(system-redstone): Java redstone model and settling"
```

```json:metadata
{"files": ["skills/system-redstone/scripts/redstone_model.py", "tests/ashlar/test_redstone_model.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_model.py -q", "acceptanceCriteria": ["every rule R1-R18 has a passing test with a source comment", "check_world reports written power properties that differ from the settled state with the rule as reason", "Review Focus 4 and 5 tests pass"], "modelTier": "frontier"}
```

---

### Task 4: Checker CLI (`redstone_rest.py`) and fixture tests

**Goal:** Ship the `check`, `diff` and `containers` commands from spec §8.1–8.5, and prove them on the sorter slice, the 2×2 door, clocks and rotations.

**Files:**
- Create: `skills/system-redstone/scripts/redstone_rest.py`
- Create: `tests/ashlar/redstone_fixtures.py`
- Create: `tests/ashlar/test_redstone_rest.py`

**Interfaces** (used by Tasks 5, 6, 9 and 12):

```python
@dataclass
class CheckResult:
    as_built: Report                                  # written states vs settled, containers empty
    loaded_world: dict[Pos, State]                    # settled after the setup loads
    loaded_changes: list[tuple[Pos, str, str]]
    input_changes: dict[Pos, list[tuple[Pos, str, str]]]
    input_unsettled: dict[Pos, list[Pos]]

def run_check(plan_path: Path, inputs: Sequence[Pos] = (), background: Path | None = None) -> CheckResult
def run_diff_plan(plan_path: Path, read_path: Path, loaded: bool) -> list[tuple[Pos, str, str]]
def run_diff_reads(a: Path, b: Path) -> list[tuple[Pos, str, str]]
def list_containers(plan_path: Path) -> list[tuple[Pos, str]]
def main(argv: list[str] | None = None) -> int
```

Command line (spec §8.1):
- `check PLAN [--input X Y Z]... [--background READ.json]`
- `diff PLAN READ.json [--loaded]`
- `diff READ_A.json READ_B.json`, chosen when the first argument ends in `.json`
- `containers PLAN`

**Behaviour:**
- **`--input`:** for a lever, button or plate, uses `switch_on`; for a container (a test-input hopper), adds one `minecraft:cobblestone` to its first empty slot. It starts from `loaded_world`.
- **`diff PLAN READ`:** compares each written cell. The block id must match, and so must each property the plan writes, except power properties and connection-pass properties (spec §6.4). A cell missing from the read is a mismatch (`not read`).
- **`diff --loaded`:** compares the power properties of every modelled component with `loaded_world`.
- **`diff READ READ`:** compares the power properties of the modelled components present in both reads.
- **The report:** stdout text, starting with `check <project>: <n> mismatches, <n> structural, <n> unsettled, <n> unmodelled`, then one line per entry (spec §8.5).
- **Exit codes:**
  - `check`: 0 clean; 1 mismatches, structural errors or unsettled as built; 3 clean except unmodelled parts. Input results never change the exit code, because a clock is expected not to settle.
  - `diff`: 0 no differences, 1 differences.
  - Any command: 2 for invalid input (`PlanError`, a missing file).

**Fixtures** (`redstone_fixtures.py`). The implementer designs each one from the cited wiki design. `Local = tuple[int, int, int]` is a position in the module's own coordinates, and a setup load is `(local position, slot, item id, count)`:
- `sorter_slice_module(filter_items: int) -> tuple[dict, dict[str, Local], list[tuple[Local, int, str, int]]]`: one filter slice of the standard Java hopper item sorter (wiki "Tutorials/Hopper" item-sorter section). It returns the module dict (`stamp.py` format), its names (`line_hopper`, `filter_hopper`, `comparator`, `lock_torch`, `output_hopper`, `chest`) and its setup loads: `filter_items − 4` cobblestone in the filter hopper's slot 0 and one stick in each of slots 1–4.
- `door_2x2_module() -> tuple[dict, dict[str, Local | list[Local]]]`: a 2×2 sticky-piston door opened by a lever (wiki "Tutorials/Door mechanisms" or "Piston door"). Names: `lever`, `pistons` (four positions), `doorway` (four positions).
- `clock_module(with_switch: bool) -> tuple[dict, dict[str, Local]]`: a redstone clock that runs only while its lever is on, or free-running when `with_switch` is false. Names: `switch`, `output`.
- `plan_from_module(tmp: Path, module: dict, rotation: int = 0, mirror: str = "none", setup: Sequence[tuple[Local, int, str, int]] = ()) -> tuple[Path, Callable[[Local], Pos]]`:
  - creates `tmp` if missing;
  - stamps with `stamp.stamp(...)` at origin `0 64 0`;
  - writes `plan.toon`, the phase file, and a setup `commands` phase holding one `item replace block X Y Z container.<slot> with <item> <count>` row per load at its world position;
  - returns the plan path and `at`, which maps a local position to its world position through `stamp.transform_point`.

**Acceptance Criteria:**
- [ ] All tests below pass, and the whole suite stays green.
- [ ] The sorter slice at 22 items: as built clean; loaded comparator `powered=true`, lock torch `lit=true`, output hopper `enabled=false`. At 23 items: lock torch `lit=false`, output hopper `enabled=true`.
- [ ] The door, in every rotation and mirrored: as built clean; `--input` on the lever changes `extended` on exactly the four pistons.
- [ ] Clock with switch: as built clean; `--input` on the switch gives unsettled positions. Free-running clock: `as_built.unsettled` is not empty.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_rest.py tests/ashlar/test_redstone_model.py tests/ashlar/test_redstone_plan.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the fixtures and the failing tests** in `tests/ashlar/test_redstone_rest.py`

```python
def test_sorter_slice_at_rest_is_clean(tmp_path):
    module, names, setup = sorter_slice_module(22)
    plan, at = plan_from_module(tmp_path, module, setup=setup)
    r = run_check(plan)
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == []
    assert r.loaded_world[at(names["comparator"])].get("powered") == "true"
    assert r.loaded_world[at(names["lock_torch"])].get("lit") == "true"
    assert r.loaded_world[at(names["output_hopper"])].get("enabled") == "false"

def test_rotation_and_mirror_give_same_verdicts(tmp_path):
    module, names = door_2x2_module()
    for rotation, mirror in [(0, "none"), (90, "none"), (180, "none"), (270, "none"), (0, "x")]:
        plan, at = plan_from_module(tmp_path / f"{rotation}{mirror}", module, rotation, mirror)
        r = run_check(plan, inputs=[at(names["lever"])])
        assert r.as_built.mismatches == [] and r.as_built.structural == []
        changed = {p for p, before, after in r.input_changes[at(names["lever"])]
                   if "piston" in before and "extended" in before + after}
        assert changed == {at(p) for p in names["pistons"]}
```

Also write:
- `test_sorter_slice_23_items_unlocks`
- `test_sorter_slice_wrong_torch_is_flagged`: a lock torch written `lit=false` gives one mismatch at `lock_torch` whose expected state has `lit=true`.
- `test_door_at_rest_and_lever_on`
- `test_clock_with_switch_settles_until_switched_on`
- `test_free_running_clock_cannot_settle`
- `test_containers_lists_every_container_sorted`
- CLI, through `main([...])` with `capsys`:
  - `test_cli_check_exit_codes`: clean 0; wrong torch 1; missing plan 2; a rail beside dust 3.
  - `test_cli_diff_plan_built_ignores_power_and_connection_props`: a read whose wire sides and `power` differ from the plan reports nothing; a different repeater `delay` is reported.
  - `test_cli_diff_loaded_reports_a_wrong_torch`
  - `test_cli_diff_reads_reports_power_changes`

- [ ] **Step 2: Run the tests to verify they fail**

Run: the **Verify** command. Expected: FAIL with `ModuleNotFoundError: redstone_rest`

- [ ] **Step 3: Implement `redstone_rest.py`** with the interfaces and behaviour above, plus the `require_python()` guard and an `argparse` CLI.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the **Verify** command, then the full suite. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/system-redstone/scripts/redstone_rest.py tests/ashlar/redstone_fixtures.py tests/ashlar/test_redstone_rest.py
git commit -m "feat(system-redstone): redstone_rest.py check, diff and containers"
```

```json:metadata
{"files": ["skills/system-redstone/scripts/redstone_rest.py", "tests/ashlar/redstone_fixtures.py", "tests/ashlar/test_redstone_rest.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_redstone_rest.py tests/ashlar/test_redstone_model.py tests/ashlar/test_redstone_plan.py -q", "acceptanceCriteria": ["sorter slice at 22 items clean with comparator powered, lock torch lit, output hopper locked; 23 items unlocks", "door clean in every rotation and mirrored; lever input changes exactly the four pistons", "clock with switch settles until switched on; free-running clock cannot settle", "whole suite green"], "modelTier": "frontier"}
```

---

### Task 5: `exec-ashlar` test protocol (docs)

**Goal:** Teach `exec-ashlar` the `tests` table, the `test` mode, the four verdicts, the gate additions and the recovery rules from spec §6.

**Order:** runs after Task 6 (ruling 2026-11-20, plan author): `execution.md` links `../system-redstone/reference/ashlar-redstone.md`, which Task 6 creates, and `node scripts/validate-plugin.mjs` fails on dead reference links. Blocked by Tasks 1, 4 and 6.

**Files:**
- Modify: `skills/exec-ashlar/SKILL.md`
- Modify: `skills/exec-ashlar/reference/plan-format.md`
- Modify: `skills/exec-ashlar/reference/execution.md`
- Modify: `skills/exec-ashlar/reference/verification.md`
- Modify: `skills/exec-ashlar/reference/registry.md`
- Modify: `skills/exec-ashlar/reference/commands.md`

**Acceptance Criteria:**
- [ ] `SKILL.md`:
  - the modes table has `test <project> [<test>…]` (and `--manual`);
  - a `## test` section holds the steps of spec §6.3, verbatim from the spec, with script paths as `<skill>/scripts/ashlar_place.py read` and `<skill>/../system-redstone/scripts/redstone_rest.py`;
  - build step 6 reports the four verdicts (spec §6.4 wording on "works");
  - the hard rules add: test `load` rows run only as listed in the approved plan; never clear containers through the console.
- [ ] `plan-format.md`:
  - a `## tests` section with both examples, the kinds table and the per-test baseline paragraph, verbatim from spec §6.1;
  - the `tests` table appears in the `plan.toon` field list;
  - validation gains the four items of spec §6.2.
- [ ] `execution.md`:
  - the approval gate lists the spec §6.5 additions;
  - "Liquids and redstone" is rewritten to spec §5.4's resting-state, starting and no-nudge rules (short form, pointing to `../system-redstone/reference/ashlar-redstone.md`);
  - a `## Resuming and fixing` section holds spec §6.6, verbatim.
- [ ] `verification.md`: a `## Redstone` section explains the `built` full-read `diff`, `diff --loaded` for `at_rest`, and the power and connection-pass property lists (spec §6.4), and points to `test`.
- [ ] `registry.md` documents the `verdicts` key with the spec §6.4 example and values.
- [ ] `commands.md` notes that test `load` rows are world-changing commands from the approved plan's `tests` table, shown at the gate, with one `item replace block` example. The allowed forms do not change.
- [ ] `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q` passes, and so does `node scripts/validate-plugin.mjs`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs` → all pass; `✓ plugin, marketplace, skills, and agents are valid`

**Steps:**

- [ ] **Step 1: Edit the six files** per the acceptance criteria. Keep the existing text that is not named above. Keep line length and style like the surrounding text.
- [ ] **Step 2: Run the Verify command.** Expected: pass. If the text test flags a word, rephrase (for example never "orchestrator").
- [ ] **Step 3: Commit**

```bash
git add skills/exec-ashlar
git commit -m "docs(exec-ashlar): tests table, test mode, verdicts and recovery"
```

```json:metadata
{"files": ["skills/exec-ashlar/SKILL.md", "skills/exec-ashlar/reference/plan-format.md", "skills/exec-ashlar/reference/execution.md", "skills/exec-ashlar/reference/verification.md", "skills/exec-ashlar/reference/registry.md", "skills/exec-ashlar/reference/commands.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["test mode, tests table, verdicts, gate additions and resume rule documented per spec §6", "allowlist forms unchanged", "text checks and validator pass"], "modelTier": "standard"}
```

---

### Task 6: Port the `system-redstone` text

**Goal:** Rewrite `system-redstone`'s Markdown for Ashlar per spec §5, keeping Chapman's Java design knowledge, so the static text checks cover it.

**Order:** runs before Task 5 (ruling 2026-11-20, plan author); blocked by Task 4 only. Its links go to `exec-ashlar` reference files that already exist, and it names the `test` mode in prose only.

**Files:**
- Modify: `tests/ashlar/test_skill_text.py`
- Modify: `skills/system-redstone/SKILL.md`
- Create: `skills/system-redstone/reference/ashlar-redstone.md`
- Create: `skills/system-redstone/reference/checker.md`
- Modify: `skills/system-redstone/reference/setblock-redstone-limits.md` (becomes a stub)
- Modify: `skills/system-redstone/reference/{java-redstone,design-patterns,contraptions-farms,contraptions-mechanisms,interview,community-sources,verification}.md`

**Acceptance Criteria:**
- [ ] `SKILLS` in `test_skill_text.py` includes `system-redstone`. `CHAPMAN_TOOLS` adds `events_subscribe`, `events_poll`, `events_unsubscribe`, `function_run`, `function_list`, `function_get_definition`, `inventory_get`, `inventory_count_items`, `entity_get`, `datapack_enable`, `datapack_list_enabled` and `level_get_mob_spawns`, and `FORBIDDEN` adds `re.compile(r"\bscoreboard_")`.
- [ ] The frontmatter is exactly:
  - `name: system-redstone`;
  - `model: opus`;
  - `effort: high`;
  - `allowed-tools: mcp__ashlar__mc_status mcp__ashlar__mc_players mcp__ashlar__mc_survey mcp__ashlar__mc_render mcp__ashlar__mc_inspect`;
  - `metadata.short-description: Design, build and test redstone machines through Ashlar`;
  - `description:` "Designs redstone contraptions for a Paper server reached through Ashlar (item sorters, piston doors, farms, clocks, elevators, note-block music, traps), Java-correct and written in their resting state, builds them through exec-ashlar, and tests what Ashlar's tools can drive, reporting plainly what still needs the user. Use when the user wants a contraption or a working machine, or when a design skill hands one off."
- [ ] `SKILL.md` sections:
  - When to use;
  - Connection (`mc_status`);
  - Placement under Ashlar (a summary, then "read `reference/ashlar-redstone.md` first");
  - Core principle (Java mechanics, kept);
  - Process (spec §5.3 steps 1–9);
  - Test inputs and fixtures (spec §5.5);
  - Scripts: `redstone_rest.py` commands, `../exec-ashlar/scripts/stamp.py` and `ashlar_place.py read`, and the `<skill>` folder on labelled lines as in `exec-ashlar/SKILL.md`;
  - Reference library (a table of every reference file, `ashlar-redstone.md` marked read first);
  - Hard rules (spec §5.7);
  - Tracking progress (labelled lines);
  - Report (the four verdicts; hand-offs).
- [ ] `reference/ashlar-redstone.md` holds spec §5.4 verbatim (rules and the resting-state table), plus the chunk and Paper notes.
- [ ] `reference/checker.md` covers the commands, inputs, the report lines, exit codes, `--background`, what the checker does not model (spec §8.4, verbatim), and that rung 0 decides the lone-dust shape.
- [ ] `reference/setblock-redstone-limits.md` is exactly this stub:

  ```markdown
  # Placement limits (superseded)

  This file described a server whose block placement sends block updates.
  Ashlar places blocks without physics, so none of it applies here. Read
  `ashlar-redstone.md` instead.
  ```

- [ ] The other reference files follow spec §5.6 and §5.8. Every Chapman tool, agent and skill name is gone. The sorter entry uses the comparator formula (spec finding 13). "Ship it pre-loaded" sections use `item replace block` or `data merge block` rows in a setup `commands` phase. `interview.md` has the new questions, with `AskUserQuestion` and `request_user_input` on labelled lines. `verification.md` is rewritten per spec §5.8.
- [ ] The design catalog, the logic patterns and the Java mechanics and timing stay as Chapman wrote them, apart from those changes.
- [ ] `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q` passes, and so does `node scripts/validate-plugin.mjs`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs` → all pass

**Steps:**

- [ ] **Step 1: Extend the text test** (the `SKILLS`, `CHAPMAN_TOOLS` and `FORBIDDEN` changes above), and add one unit test: `test_leftovers_detects_redstone_tool_names`, asserting `leftovers("call events_poll") == [(1, "events_poll")]` and `leftovers("use scoreboard_* here") == [(1, "scoreboard_")]`.
- [ ] **Step 2: Run the text test to verify it fails**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q`
Expected: FAIL, listing the Chapman leftovers in `skills/system-redstone/`

- [ ] **Step 3: Write the new files and port the existing ones** per the acceptance criteria and spec §5.
- [ ] **Step 4: Run the Verify command.** Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add tests/ashlar/test_skill_text.py skills/system-redstone
git commit -m "docs(system-redstone): port the skill to Ashlar"
```

```json:metadata
{"files": ["tests/ashlar/test_skill_text.py", "skills/system-redstone/SKILL.md", "skills/system-redstone/reference/"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["system-redstone in SKILLS with the extra Chapman names", "frontmatter exactly as specified", "SKILL.md sections and new reference files per spec §5", "setblock-redstone-limits.md is the exact stub", "text checks and validator pass"], "modelTier": "frontier"}
```

---

### Task 7: Fork notes in `CLAUDE.md`, `README.md` and `TAXONOMY.md`

**Goal:** Say in the repo's own docs that the fork's `system-redstone` targets Ashlar, and include it in the install loop.

**Files:**
- Modify: `CLAUDE.md` (fork note, lines 5–14)
- Modify: `README.md` (fork note and install loop, lines 5–18)
- Modify: `skills/TAXONOMY.md` (the `system-redstone` row, line 39; the fork note, line 52)

**Acceptance Criteria:**
- [ ] `CLAUDE.md`: "the six `design-*` skills, `survey-research` and the new `exec-ashlar` skill" becomes "the six `design-*` skills, `survey-research`, the new `exec-ashlar` skill and the ported `system-redstone` skill". "eight skills" and "Check the eight" become "nine". The note ends with: "`system-redstone`'s checker and test protocol are in `docs/superpowers/specs/2026-11-19-ashlar-redstone-design.md`."
- [ ] `README.md`: the fork note says it "adds the `exec-ashlar` skill and ports `system-redstone`", and the `for s in …` loop includes `system-redstone`.
- [ ] `TAXONOMY.md`: the row's description becomes "Redstone & mechanical contraptions (was engineer); the fork's version builds and tests through Ashlar". The fork note reads "adds `exec-ashlar`, ports `system-redstone`, and adapts the six `design-*` skills and `survey-research` to build through Ashlar; see the fork's README."
- [ ] `node scripts/validate-plugin.mjs` passes.

**Verify:** `node scripts/validate-plugin.mjs && grep -c "system-redstone" CLAUDE.md README.md skills/TAXONOMY.md` → `✓ … valid`; each count ≥ 1 (`README.md` ≥ 2)

**Steps:**

- [ ] **Step 1: Make the three edits** exactly as in the acceptance criteria.
- [ ] **Step 2: Run the Verify command.** Expected: pass.
- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md skills/TAXONOMY.md
git commit -m "docs: note the ported system-redstone in the fork notes"
```

```json:metadata
{"files": ["CLAUDE.md", "README.md", "skills/TAXONOMY.md"], "verifyCommand": "node scripts/validate-plugin.mjs && grep -c system-redstone CLAUDE.md README.md skills/TAXONOMY.md", "acceptanceCriteria": ["CLAUDE.md, README.md and TAXONOMY.md edited exactly as specified", "validator passes"], "modelTier": "mechanical"}
```

---

### Task 8: Benchmark suite

**Goal:** Write the benchmark ladder of spec §9 as prompt-plus-criteria files that never contain a layout.

**Files:**
- Create: `docs/benchmarks/redstone/README.md`
- Create: `docs/benchmarks/redstone/00-calibration.md`, `01-sorter.md`, `02-door-2x2.md`, `03-cane-farm.md`, `04-clock.md`, `05-door-3x3.md`

**Acceptance Criteria:**
- [ ] `README.md` holds:
  - the ladder table (rung, machine, who tests, done-bar membership);
  - the run protocol, verbatim from spec §9.2;
  - the variants, verbatim from spec §9.9;
  - the results format: a Markdown table for `.minecraft-builder/benchmarks/redstone-results.md` with columns date, rung, variant, client, model, server version, Ashlar version, built, at rest, agent tested, manual, criteria, snapshots used, fix rounds, notes.
- [ ] Each rung file has the sections Prompt, Site constraints, Test quantities, Pass criteria, Who tests what and Variants, with spec §9.4–9.8's text. The prompts are marked "draft; the user may edit".
- [ ] `00-calibration.md` holds spec §9.3's table, plus how its results flow back (spec §7).
- [ ] Each rung file's tighter footprint variant (draft values, marked as such):
  - sorter: within 6 × 4 × 5 blocks (x × z × y);
  - 2×2 door: all redstone on one side of the wall, within 3 blocks of it;
  - cane farm: within 7 × 3 blocks of floor;
  - clock: within 3 × 3 × 2;
  - 3×3 door: all wiring below the floor, at most 4 blocks deep.
- [ ] No rung file holds coordinates, block lists or schematics: `grep -nE "\b-?[0-9]+ -?[0-9]+ -?[0-9]+\b" docs/benchmarks/redstone/*.md` prints nothing.

**Verify:** `ls docs/benchmarks/redstone/ && grep -c "Pass criteria" docs/benchmarks/redstone/0*.md` → seven files; each rung file shows 1

**Steps:**

- [ ] **Step 1: Write the seven files** per the acceptance criteria.
- [ ] **Step 2: Run the Verify command and the coordinate grep.** Expected: as stated.
- [ ] **Step 3: Commit**

```bash
git add docs/benchmarks/redstone
git commit -m "docs: add the redstone benchmark suite"
```

```json:metadata
{"files": ["docs/benchmarks/redstone/"], "verifyCommand": "ls docs/benchmarks/redstone/ && grep -c 'Pass criteria' docs/benchmarks/redstone/0*.md", "acceptanceCriteria": ["README and seven rung files with the required sections", "no coordinates, block lists or schematics in rung files"], "modelTier": "standard"}
```

---

### Task 9: Offline dry runs and a live read-only check

**Goal:** Show, before the merge and without any world write, that `system-redstone` produces plans for the rung 1 and rung 2 prompts that pass validation and the checker, and that `ashlar_place.py read` works on the live server.

**Files:**
- No repo changes, unless a defect is found (fix it in the owning file, re-run that task's Verify, and commit with `fix(...)`).
- Scratch output: `/Users/bsw/Development/Minecraft/.minecraft-builder/dryrun-sorter/`, `.../dryrun-door/` (deleted at the end, with their registry entries).

**Acceptance Criteria:**
- [ ] For each prompt (rung 1 and rung 2, from `docs/benchmarks/redstone/`), a dry run stops at the approval gate. Its `plan.toon` passes every validation item in `exec-ashlar/reference/plan-format.md`. Its `redstone_rest.py check` exits 0, or 3 with every unmodelled part noted in the plan.
- [ ] Each plan has a `tests` table, and the gate summary lists the test loads, force-loads and manual steps (spec §6.5).
- [ ] `python3 skills/exec-ashlar/scripts/ashlar_place.py read <a 4×4×4 box inside the dry-run site> --out <the executor's scratchpad>/read.json` exits 0 and writes 64 cells. The output never goes into the repo.
- [ ] The scratch folders and the registry entries `dryrun-sorter` and `dryrun-door` are removed afterwards (registry by read, change, write).

**Verify:** the three commands' outputs captured in the task report (validation result, the checker's exit code and summary line, the `read` summary line)

**Steps:**

- [ ] **Step 1: Run the dry runs.** The coordinator dispatches the workspace's `ashlar-dry-run` agent (Claude Code), once per prompt. Tell it to follow the worktree's `skills/system-redstone/SKILL.md` and `skills/exec-ashlar/SKILL.md` by path (the workspace links still serve the clone's old skills), to use project names `dryrun-sorter` and `dryrun-door`, and to stop at the approval gate.
- [ ] **Step 2: Check the plans.** In the main session, run `stamp.py` for each plan's placements and then `redstone_rest.py check` on each plan. The dry-run agent has no shell.
- [ ] **Step 3: Run the live read.** Do the read-only `ashlar_place.py read` from the worktree.
- [ ] **Step 4: Clean up.** Remove the scratch folders and registry entries, then record the results in the task report.

```json:metadata
{"files": [], "verifyCommand": "dry-run plan validation result, redstone_rest.py check exit code and summary, ashlar_place.py read summary (captured in the task report)", "acceptanceCriteria": ["rung 1 and rung 2 dry runs stop at the gate with valid plans and a clean check", "plans carry tests tables and gate summaries per spec §6.5", "live read writes 64 cells", "scratch folders and registry entries removed"], "modelTier": "standard"}
```

---

### Task 10: Whole-branch check and the implementation PR

**Goal:** Verify the whole branch, then push it and open the implementation PR, and later merge it, each step only with the user's yes at that moment.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-19-ashlar-redstone-design.md` (status line only: "implemented on `redstone`; PR #<n>")

**Acceptance Criteria:**
- [ ] The full suite passes: `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q`.
- [ ] `node scripts/validate-plugin.mjs` passes.
- [ ] `git diff origin/main...redstone` contains no URL with a host or IP, no token-like value, no server folder name and no player name.
- [ ] The user said yes to pushing and opening the PR. The PR (base `main`, head `redstone`) has a body summarising the spec, the tests run and the Task 9 results, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- [ ] The user said yes to merging, and the PR is merged.

**Verify:** `gh pr view <n> --repo iridium-coding/ashlar-design-skills --json state,mergedAt` → `"state":"MERGED"`

**Steps:**

- [ ] **Step 1: Run the checks and review the diff** per the first three criteria.
- [ ] **Step 2: Ask the user** to push `redstone` and open the PR. On yes: `git push -u origin redstone`, then `gh pr create --base main --head redstone …`.
- [ ] **Step 3: Ask the user to merge.** Merge only on their yes, with the merge method they choose.

```json:metadata
{"files": ["docs/superpowers/specs/2026-11-19-ashlar-redstone-design.md"], "verifyCommand": "gh pr view <n> --repo iridium-coding/ashlar-design-skills --json state,mergedAt", "acceptanceCriteria": ["full suite passes", "validator passes", "diff free of secrets and server facts", "user said yes before push and PR", "user said yes before merge; PR state MERGED"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```

---

### Task 11: Check out the merged `main` and link `system-redstone`

**Goal:** Make the merged skills live in the workspace for Claude Code and Codex.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Workspace, outside the repo: `/Users/bsw/Development/Minecraft/.claude/skills/system-redstone` and `/Users/bsw/Development/Minecraft/.agents/skills/system-redstone`, both symlinks to `../../ashlar-design-skills/skills/system-redstone`.

**Acceptance Criteria:**
- [ ] The user said yes to switching the clone. It had `ashlar` checked out on 2026-11-20, with sub-project 1's untracked `.tasks.json`. In `/Users/bsw/Development/Minecraft/ashlar-design-skills`, run `git checkout main && git pull --ff-only`. Untracked files stay untouched. Tell the terrain session (through the coordinator) that the clone now serves `main`.
- [ ] Both links exist and resolve to a folder whose `SKILL.md` frontmatter has `metadata.short-description: Design, build and test redstone machines through Ashlar`.
- [ ] A fresh Claude Code session in the workspace root lists `system-redstone`.
- [ ] Codex, started in the workspace root by the user, finds `system-redstone`, reads its `SKILL.md` and runs `redstone_rest.py check` on a plan. The output is captured.

**Verify:** `readlink /Users/bsw/Development/Minecraft/.claude/skills/system-redstone /Users/bsw/Development/Minecraft/.agents/skills/system-redstone && grep -m1 short-description /Users/bsw/Development/Minecraft/.claude/skills/system-redstone/SKILL.md` → both links shown; the line matches

**Steps:**

- [ ] **Step 1: Ask the user,** then switch the clone to `main`.
- [ ] **Step 2: Create the two links** (`ln -sfn`).
- [ ] **Step 3: Run the Claude Code listing check, and ask the user to run the Codex check.**

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.claude/skills/system-redstone", "/Users/bsw/Development/Minecraft/.agents/skills/system-redstone"], "verifyCommand": "readlink /Users/bsw/Development/Minecraft/.claude/skills/system-redstone /Users/bsw/Development/Minecraft/.agents/skills/system-redstone", "acceptanceCriteria": ["user said yes; clone on main, fast-forwarded", "both links resolve to the ported skill", "Claude Code lists system-redstone", "Codex finds it and runs redstone_rest.py check"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```

---

### Task 12: Rung 0 calibration (live)

**Goal:** Run the calibration build of spec §9.3 and fold every surprise back into the skill and the checker before rung 1.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Workspace: `/Users/bsw/Development/Minecraft/.minecraft-builder/rs-calibration/` (plan, phases, build log)
- If a check differs from the spec: a follow-up branch `redstone-calibration` from `main`, changing `skills/system-redstone/reference/ashlar-redstone.md`, `redstone_model.py` (and its tests) and the spec, merged through its own PR with the user's OK.

**Acceptance Criteria:**
- [ ] The coordinator writes the calibration plan (project `rs-calibration`). It covers the seven checks of `docs/benchmarks/redstone/00-calibration.md`, plus one lone wire written with no sides and one written with all four sides. Its `tests` table drives checks 2, 3 and 7.
- [ ] `redstone_rest.py check` passes before the gate, apart from the deliberate wrong torch (check 5), which it flags.
- [ ] The build passes the gate with the user's yes. `exec-ashlar test rs-calibration` runs, and `redstone_rest.py diff --loaded` runs on the calibration read.
- [ ] Each check's result is recorded in `/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md`. The lone-dust finding is written into `ashlar-redstone.md` and `checker.md`.
- [ ] A result that breaks the test protocol (checks 2 or 3) stops the plan and goes to the user (spec §7).
- [ ] The calibration build is rolled back with the user's yes.

**Verify:** the results file rows for rung 0, and `git log --oneline main -3` showing any calibration follow-up merge

**Steps:**

- [ ] **Step 1: Write the calibration plan and run the checker.**
- [ ] **Step 2: Build and test through the gate.**
- [ ] **Step 3: Record the results and fold in any surprise.**
- [ ] **Step 4: Roll back.**

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.minecraft-builder/rs-calibration/"], "verifyCommand": "rung 0 rows in /Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md", "acceptanceCriteria": ["calibration plan covers the seven checks plus both lone-wire forms", "checker clean except the deliberate wrong torch", "built and tested through the gate with the user's yes", "results recorded and the lone-dust finding written into the skill", "protocol-breaking results stop the plan", "rolled back with the user's yes"], "modelTier": "frontier", "userGate": true, "tags": ["user-gate"]}
```

---

### Task 13: Rung 1, the sorter (live)

**Goal:** Pass rung 1's six criteria (spec §9.4), tested by the agent over two batches, in a fresh session working from the prompt alone.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Workspace: `.minecraft-builder/<the run's project>/` and `.minecraft-builder/benchmarks/redstone-results.md`
- If a defect is found: a follow-up branch from `main`, merged with the user's OK, then the rung is re-run.

**Acceptance Criteria:**
- [ ] The user ran the rung 1 prompt in a fresh session in the workspace root, approving or refusing each gate.
- [ ] The run's report shows `built: pass`, `at_rest: pass`, `agent_tested: pass` and `manual: n/a`.
- [ ] Each of the six criteria has evidence in `build-log.md`: the gate approvals, snapshots, allowlisted commands, the `check` result, both batches' `gained`, `holds`, `conserve` and `rest` rows passing, and no manual redstone change between batches.
- [ ] The transcript shows that the run never read `docs/benchmarks/`.
- [ ] The result row is recorded, and the machine is rolled back with the user's yes (or kept, if the user says so).

**Verify:** the rung 1 row in `/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md`, showing the four verdicts and the six criteria as passed

**Steps:**

- [ ] **Step 1: Hand the user the prompt** from `docs/benchmarks/redstone/01-sorter.md`, and ask them to run it in a fresh session in the workspace root.
- [ ] **Step 2: Check the run's evidence** against the criteria.
- [ ] **Step 3: Record the result** and roll back.

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md"], "verifyCommand": "rung 1 row in /Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md", "acceptanceCriteria": ["fresh-session run by the user", "verdicts built/at_rest/agent_tested pass, manual n/a", "evidence for all six criteria in build-log.md", "run never read docs/benchmarks/", "result recorded; rolled back or kept per the user"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```

---

### Task 14: Rung 2, the 2×2 sticky-piston door (live)

**Goal:** Pass rung 2's criteria (spec §9.5) through the user's ten guided cycles, with no piston left in the wrong state.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Workspace: `.minecraft-builder/<the run's project>/` and `.minecraft-builder/benchmarks/redstone-results.md`

**Acceptance Criteria:**
- [ ] The user ran the rung 2 prompt in a fresh session in the workspace root.
- [ ] `check` was clean, and `check --input` on the lever moved every door piston.
- [ ] The guided manual test ran ten cycles. After each flip the agent read the door and recorded open (four doorway cells air) and closed (four door blocks back, pistons at rest).
- [ ] The final `rest` check is clean: no door block missing, displaced or dropped, and no piston extended without its block.
- [ ] The report shows `built: pass`, `at_rest: pass`, `manual: pass`, and `agent_tested` `pass` or `n/a` (`pass` if the user accepted a test input).
- [ ] The result row is recorded, and the machine is rolled back with the user's yes (or kept). With rungs 0–2 done, the spec's status line becomes "complete: rungs 0–2 passed on <date>".

**Verify:** the rung 2 row in `/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md`, showing ten passed cycles and the four verdicts

**Steps:**

- [ ] **Step 1: Hand the user the prompt** from `docs/benchmarks/redstone/02-door-2x2.md`.
- [ ] **Step 2: Follow the guided cycles' evidence.**
- [ ] **Step 3: Record the result, roll back, and update the spec's status** (on a docs branch merged with the user's OK, or in the next follow-up PR).

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md"], "verifyCommand": "rung 2 row in /Users/bsw/Development/Minecraft/.minecraft-builder/benchmarks/redstone-results.md", "acceptanceCriteria": ["fresh-session run by the user", "check clean and lever input moves every door piston", "ten guided cycles recorded open and closed", "final rest check clean", "verdicts built, at_rest and manual pass", "result recorded; spec status updated"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```
