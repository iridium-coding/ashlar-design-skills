# system-transit on Ashlar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `system-transit` to Ashlar with a transit toolkit (`route`, `line`, `portal`, `transit-check`) that turns one link design at a time into checked, backed-up `exec-ashlar` phases.

**Architecture:** Focused new modules in the terrain toolkit: shared block helpers moved out of `caves.py`, line-design parsing, route search and profile, corridor grading through the existing `emit_field` (with a protect mask), generated track and structures checked with `check_form_layers` on the graded state, transit checks, and line and portal emission behind the `terrain.py` launcher. The skill text and the `exec-ashlar` references are rewritten to drive them.

**Tech Stack:** Python 3.12 (numpy, scipy, Pillow, opensimplex, the existing dependencies only), pytest through `uv`, Markdown skills, the Node plugin validator.

**Spec:** `docs/superpowers/specs/2026-11-25-ashlar-system-transit-design.md`

## Global Constraints

- Work only in the worktree `/Users/bsw/Development/Minecraft/ashlar-design-skills-transit` on branch `transit`. Never push, never write to the Minecraft world.
- Commit at the end of every task. Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `PYTEST` below means `uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest`. The full suite `$PYTEST tests/ashlar -q` stays green after every task.
- New modules live in `skills/terrain-shape/tools/terrain/` and tests import them as `from terrain import <module>`. No new dependencies.
- Ruff: new files have zero findings and changed files gain none, under the user's config (`uvx ruff check --output-format concise <files>`; compare a changed file with `git show origin/main:<file>`).
- Coordinates are world coordinates. Boxes are inclusive `(x1, y1, z1, x2, y2, z2)`. Heights (`ground`, `surface`, `top` in F2 files, read with `site.load_heights`) are the y of the top block; `make_site(ground=g)` puts grass at y `g`.
- A route's `levels[i]` is the running-surface height: the y of the rail cell (rail), the walking-surface top in half blocks (road), whole blocks (path, ice). The formation's top block is at `floor(level) - 1`. A cell is at grade when `|level - (ground + 1)| <= 1`.
- Spec defaults: `max_fill` 6, `max_cut` 8, `min_bridge` 4, `min_tunnel` 6, `water_clearance` 3, `fill_ratio` 1.5, `cut_ratio` 1.0, rock cut ratio 0.5, section length 96, booster every 24 cells on the level and every 2nd cell on slopes, light minimum 1 (Overworld) and 12 (Nether), search-box margin `max(64, link_length // 4)`, version `26.3`.
- Rail: moves along x or z only; a corner is one cell; the corner and both neighbours share a level; at most one block of level change per cell; every powered rail is `powered=true` on its own `minecraft:redstone_block` directly below; none on a corner. A terminus has no boosters on its last 8 cells and a launch group of 3 boosters on cells 9–11 from the end.
- Clearance: carve 3 above a rail (the check needs 2); roads and paths keep 3 above the surface.
- Spawning (Wiki, read 2026-11-25): Overworld spawnable cells need block light ≥ 1, Nether ≥ 12. Rails, bottom slabs, glass, plain ice, leaves, trapdoors, scaffolding and copper grates are not spawnable; packed and blue ice are.
- Player blocks: every non-natural block a layer changes is listed by `blocks.touched_blocks`, and writing needs `--approve-built <token>` from `blocks.built_token`. Linings keep existing non-natural solid blocks instead of overwriting them.
- Piers may replace still water only with `bridges.piers_in_water: true`; never flowing water or lava; displaced cells are counted.
- Portals: Nether x, z = `floor(overworld / 8)`, Overworld = Nether × 8, Y unchanged; search 128 (Overworld) and 16 (Nether); nearest portal by 3-D Euclidean distance with Y.
- Skill text follows §7.5 of `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md` (labelled `Claude Code:`, `Codex:`, `Otherwise:` lines).
- Ruling (plan): F2 heights cannot tell lava from water, so the route search does not treat lava specially. Lava is caught by the section reads (the emitter checks and `line`'s refusals), and the skill re-routes with an `avoid` box.

**User decisions (already made):**
- "B: transit toolkit" (approach, 2026-11-25).
- "Approve design" (the spec as written, 2026-11-25).
- A player block may be touched or moved only after the user has seen what, where and why and said yes (2026-11-25, the cave rule).
- Ground integration is on by default and declinable at approval (2026-11-25).
- Ask before each push and merge; world writes only with the user's yes at the time (standing).

## Review Focus

1. An endpoint inside an `avoid` box, on a null column, or outside the heights file → `RouteError` naming that endpoint, before any search. Task 3, `test_route_refuses_endpoint_inside_avoid_box`.
2. Null (unread or ungenerated) columns cutting every path → `RouteError` "no route", never a route through null cells. Task 3, `test_route_refuses_when_null_columns_block_every_path`.
3. A missing or too-small section read → `line` refuses, naming the section, its box and its read folder. Task 10, `test_line_refuses_missing_section_read`.
4. Fixed endpoint levels the grade rules cannot reach → `RouteError` naming the cell, never a silent grade violation. Task 4, `test_profile_refuses_unreachable_endpoint_level`.
5. A design edit after a preview changes the touched-block list → a new token, and the old token is refused. Task 10, `test_design_edit_changes_built_token`.

---

### Task 1: Shared block helpers

**Goal:** Move the cave module's block, mask, light and player-block helpers into a shared `blocks.py`, unchanged in behaviour, so transit and caves use one copy.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/blocks.py`
- Modify: `skills/terrain-shape/tools/terrain/caves.py` (import from `blocks`, delete the moved bodies)
- Test: `tests/ashlar/terrain/test_blocks.py`

**Acceptance Criteria:**
- [ ] `blocks.py` exposes the functions in Interfaces; `caves.py` imports them and keeps no duplicate bodies.
- [ ] All existing cave tests pass unchanged.
- [ ] `cells_write` round-trips through `apply_writes`; `touched_blocks` reports a chest with the callback's reason and `loses_data`.

**Verify:** `$PYTEST tests/ashlar/terrain/test_blocks.py tests/ashlar/terrain/test_caves.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/blocks.py", "skills/terrain-shape/tools/terrain/caves.py", "tests/ashlar/terrain/test_blocks.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_blocks.py tests/ashlar/terrain/test_caves.py -q", "acceptanceCriteria": ["blocks.py exposes the Interfaces and caves.py imports them with no duplicate bodies", "all existing cave tests pass unchanged", "cells_write round-trips through apply_writes and touched_blocks reports the chest with the callback reason and loses_data"], "modelTier": "standard"}
```

**Interfaces** (`blocks.py`; names on the right are the current `caves.py` names):

```python
def apply_writes(site: Site, layers: Sequence[tuple[str, LiveWrite]]) -> Site      # caves._apply
def cells_write(cells: Mapping[tuple[int, int, int], str]) -> LiveWrite | None      # new: bounding-box write, palette[0] == "skip"
def mask_write(mask: np.ndarray, site: Site, states: np.ndarray | None, palette: list[str]) -> LiveWrite  # caves._write
def face_dilate(mask: np.ndarray) -> np.ndarray      # _face_dilate
def above(mask: np.ndarray) -> np.ndarray            # _above
def below(mask: np.ndarray) -> np.ndarray            # _below
def beside(mask: np.ndarray) -> np.ndarray           # _beside
def site_ids(site: Site) -> tuple[np.ndarray, list[str]]   # _site_ids
def site_flags(site: Site) -> np.ndarray             # _site_flags
def full_cube(state: str) -> bool                    # _full_cube
def lets_light(state: str) -> bool                   # _lets_light
def cell_classes(site: Site) -> tuple[np.ndarray, np.ndarray]   # _classes
def light_of(state: str) -> int                      # _light_of
def flood(transparent: np.ndarray, level: np.ndarray) -> np.ndarray   # _flood
def site_light(site: Site, skip: np.ndarray | None = None) -> np.ndarray   # _site_light
def block_light(transparent, sources, box) -> np.ndarray
def holds_data(state: str) -> bool
def touched_blocks(site: Site, layers: Sequence[tuple[str, LiveWrite]],
                   why: Callable[[str, tuple[int, int, int]], str]) -> list[dict]
def built_token(items: list[dict]) -> str | None
```

`touched_blocks` is today's `_touched` loop with the reason text taken out: for each changed non-natural block it records `{"cell", "block", "action": mode, "why": why(mode, cell)}` plus `"loses_data": True` when `holds_data`. `caves._touched` becomes a thin wrapper that passes a callback producing today's texts (shape names, moves, pools). Move the constants these need (`_LIGHT_LEVELS`, `_PARTIAL_SUFFIXES`, `_LIGHT_THROUGH`, `DRESSABLE` stays in caves).

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
from terrain import blocks
from sitegen import make_site

def test_cells_write_round_trips_through_apply_writes(tmp_path):
    site = make_site(tmp_path / "s", (0, 60, 0, 4, 70, 4))
    write = blocks.cells_write({(1, 65, 1): "minecraft:stone", (3, 66, 2): "minecraft:rail[shape=north_south]"})
    after = blocks.apply_writes(site, [("build", write)])
    assert write.palette[0] == "skip"
    assert after.block(1, 65, 1) == "minecraft:stone"
    assert after.block(3, 66, 2) == "minecraft:rail[shape=north_south]"
    assert after.block(0, 65, 0) == site.block(0, 65, 0)

def test_cells_write_of_nothing_is_none():
    assert blocks.cells_write({}) is None

def test_touched_blocks_lists_player_blocks_with_the_callback_reason(tmp_path):
    site = make_site(tmp_path / "s", (0, 60, 0, 4, 70, 4), cells={(2, 65, 2): "minecraft:chest[facing=north]"})
    write = blocks.cells_write({(2, 65, 2): "minecraft:air", (1, 63, 1): "minecraft:air"})
    items = blocks.touched_blocks(site, [("carve", write)], lambda mode, cell: f"{mode} at {cell}")
    assert items == [{"cell": [2, 65, 2], "block": "minecraft:chest[facing=north]", "action": "carve",
                      "why": "carve at (2, 65, 2)", "loses_data": True}]
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_blocks.py -q` → FAIL (`cannot import name 'blocks'`)
- [ ] **Step 3: Create `blocks.py`** by moving the listed functions (rename to the public names), add `cells_write`, and change `caves.py` to import them.
- [ ] **Step 4: Run** `$PYTEST tests/ashlar/terrain/test_blocks.py tests/ashlar/terrain/test_caves.py -q` → all pass
- [ ] **Step 5: Commit** — `git add skills/terrain-shape/tools/terrain/blocks.py skills/terrain-shape/tools/terrain/caves.py tests/ashlar/terrain/test_blocks.py && git commit -m "refactor(terrain): share block, light and player-block helpers"`

---

### Task 2: Line design files

**Goal:** Parse and validate `terrain/<element>.line.json` into a `LineDesign` with the spec's defaults, and add a heights fixture helper for the tests.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/transit_design.py`
- Modify: `tests/ashlar/terrain/sitegen.py` (add `make_heights`)
- Test: `tests/ashlar/terrain/test_transit_design.py`

**Acceptance Criteria:**
- [ ] Defaults equal the spec values listed in Global Constraints.
- [ ] A Nether world needs `route: straight` and equal endpoint levels; an ice line needs equal endpoint levels.
- [ ] Unknown mode, three road lanes, a search without heights, an unknown stop and a negative limit are refused with the key named.
- [ ] `search_box` grows the endpoint box by `max(64, link_length // 4)`.

**Verify:** `$PYTEST tests/ashlar/terrain/test_transit_design.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/transit_design.py", "tests/ashlar/terrain/sitegen.py", "tests/ashlar/terrain/test_transit_design.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_transit_design.py -q", "acceptanceCriteria": ["defaults equal the spec values", "a Nether world needs a straight route and equal endpoint levels; ice needs equal levels", "invalid designs are refused naming the key", "search_box grows by max(64, link_length // 4)"], "modelTier": "standard"}
```

**Interfaces:**

```python
MODES = ("rail", "road", "path", "ice"); ROUTES = ("search", "straight"); STOPS = ("terminus", "room", "open")
KINDS = ("grade", "cut", "fill", "bridge", "tunnel", "tube")

@dataclass(frozen=True)
class Endpoint: x: int; y: int | None; z: int; stop: str | None
@dataclass(frozen=True)
class Limits: max_fill: int = 6; max_cut: int = 8; min_bridge: int = 4; min_tunnel: int = 6; water_clearance: int = 3; fill_ratio: float = 1.5; cut_ratio: float = 1.0; rock_cut_ratio: float = 0.5
@dataclass(frozen=True)
class Boosters: flat: int = 24; slope: int = 2
@dataclass(frozen=True)
class Bridges: kind: str = "auto"; pier_spacing: int = 8; railings: bool = True; piers_in_water: bool = False   # kind: auto | beam | arch
@dataclass(frozen=True)
class Tunnels: width: int; height: int; roof: int = 3
@dataclass(frozen=True)
class Lights: block: str; spacing: int; minimum: int
@dataclass(frozen=True)
class LineDesign:
    element: str; seed: int; world: str | None; dimension: str; mode: str; route: str
    start: Endpoint; end: Endpoint; via: tuple[tuple[int, int], ...]; heights: Path | None
    avoid: tuple[tuple[int, int, int, int], ...]; width: int; lanes: int; style: str
    palette: dict[str, dict[str, int]]; profile: tuple[tuple[int, float], ...]
    limits: Limits; bridges: Bridges; tunnels: Tunnels; lights: Lights; boosters: Boosters
    section_length: int; version: str; project: Path; source: dict

STYLES: dict[str, dict[str, dict[str, int]]]   # style -> role -> weighted block ids
def parse_line(data: dict, project_dir: Path) -> LineDesign
def load_line(path: Path, project_dir: Path | None = None) -> LineDesign
def link_length(design: LineDesign) -> float    # Euclidean length of start -> via... -> end in x/z
def search_box(design: LineDesign) -> tuple[int, int, int, int]   # (x1, z1, x2, z2)
def formation_half(design: LineDesign) -> float  # rail 1.5, road (4*lanes + 2)/2, path width/2, ice 2
```

Pinned rules: `from`/`to` are `{"at": [x, y|null, z], "stop"?}`; `dimension` defaults to `"nether"` when `world` ends in `_nether` or equals `nether`, else `"overworld"`; `heights` is required for `route: search`. Tunnel sizes: rail (3, 4), road (`4*lanes + 2`, 5), path (`max(3, width + 2)`, 3), ice (3, 3). Lights: spacing 12 and minimum 1 in the Overworld, spacing 4 and minimum 12 in the Nether; `lights.block` default `minecraft:shroomlight`. Styles `stone`, `wood`, `cobble`, `brick`, `nether`, each with the roles `ballast surface edge deck pier lining railing guard lamp_post lamp end_block platform ice` (exact blocks are the implementer's choice; `ice` defaults to `minecraft:packed_ice`, `blue` style key `ice: {"minecraft:blue_ice": 1}` allowed through `palette`). `palette` in the file overrides roles. Every invalid value raises `ValueError` whose message names the key.

`make_heights(path, origin, ground, *, surface=None, top=None) -> dict` in `sitegen.py`: arrays shaped `(nx, nz)` of top-block y (NaN for null), `surface`/`top` default to `ground`; returns the F2 dict and writes it when `path` is given.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from terrain import transit_design as td

def _base(**extra):
    data = {"element": "north-line", "seed": 5, "world": "world", "mode": "rail",
            "from": {"at": [0, 65, 0]}, "to": {"at": [200, 65, 0], "stop": "terminus"}, "heights": "heights.json"}
    data.update(extra)
    return data

def test_defaults_follow_the_spec(tmp_path):
    d = td.parse_line(_base(), tmp_path)
    assert (d.limits.max_fill, d.limits.max_cut, d.limits.min_bridge, d.limits.min_tunnel, d.limits.water_clearance) == (6, 8, 4, 6, 3)
    assert (d.limits.fill_ratio, d.limits.cut_ratio, d.limits.rock_cut_ratio, d.section_length, d.version) == (1.5, 1.0, 0.5, 96, "26.3")
    assert (d.dimension, d.route, d.lights.minimum, d.boosters.flat, d.boosters.slope) == ("overworld", "search", 1, 24, 2)
    assert (d.tunnels.width, d.tunnels.height, d.tunnels.roof) == (3, 4, 3)
    assert d.end.stop == "terminus" and d.start.stop is None

def test_nether_world_needs_a_straight_level_line(tmp_path):
    with pytest.raises(ValueError, match="straight"):
        td.parse_line(_base(world="world_nether"), tmp_path)
    d = td.parse_line(_base(world="world_nether", route="straight"), tmp_path)
    assert (d.dimension, d.lights.minimum, d.lights.spacing) == ("nether", 12, 4)

def test_ice_line_needs_equal_endpoint_levels(tmp_path):
    with pytest.raises(ValueError, match="level"):
        td.parse_line(_base(mode="ice", to={"at": [200, 70, 0]}), tmp_path)

@pytest.mark.parametrize(("extra", "match"), [
    pytest.param({"mode": "tram"}, "mode", id="unknown-mode"),
    pytest.param({"mode": "road", "lanes": 3}, "lanes", id="three-lanes"),
    pytest.param({"heights": None}, "heights", id="search-without-heights"),
    pytest.param({"to": {"at": [200, 65, 0], "stop": "station"}}, "stop", id="unknown-stop"),
    pytest.param({"limits": {"max_fill": -1}}, "max_fill", id="negative-limit"),
])
def test_invalid_designs_are_refused(tmp_path, extra, match):
    with pytest.raises(ValueError, match=match):
        td.parse_line(_base(**extra), tmp_path)

def test_search_box_grows_by_a_quarter_of_the_link_or_64(tmp_path):
    assert td.search_box(td.parse_line(_base(), tmp_path)) == (-64, -64, 264, 64)
    assert td.search_box(td.parse_line(_base(to={"at": [1000, 65, 0]}), tmp_path)) == (-250, -250, 1250, 250)
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_transit_design.py -q` → FAIL (import error)
- [ ] **Step 3: Implement** `transit_design.py` and `make_heights` per Interfaces.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): line design files with spec defaults"` (add the three files)

---

### Task 3: Route search

**Goal:** Find plan-view routes: straight axis legs, and an A* search (coarse, then refined in a band) with the spec's costs, `avoid` boxes, waypoints and clear refusals.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/route.py`
- Test: `tests/ashlar/terrain/test_route.py`

**Acceptance Criteria:**
- [ ] `straight_cells` walks axis legs through `via` with single-cell corners and returns their indices.
- [ ] `search_cells` stays out of `avoid` boxes grown by 2, takes the pass through a ridge, and in rail and ice modes moves along axes only.
- [ ] Endpoints inside an `avoid` box, on a null column or outside the grid, and grids where null columns block every path, raise `RouteError` naming the cause.

**Verify:** `$PYTEST tests/ashlar/terrain/test_route.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/route.py", "tests/ashlar/terrain/test_route.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_route.py -q", "acceptanceCriteria": ["straight_cells walks axis legs through via with single-cell corners", "search_cells avoids grown avoid boxes, takes the ridge pass, and moves along axes in rail and ice modes", "bad endpoints and blocked grids raise RouteError naming the cause"], "modelTier": "standard"}
```

**Interfaces:**

```python
class RouteError(ValueError): ...
@dataclass
class Grid:
    origin: tuple[int, int]; ground: np.ndarray; surface: np.ndarray; top: np.ndarray   # (nx, nz), NaN = null
    def index(self, x: int, z: int) -> tuple[int, int] | None
def grid_from_heights(heights: dict) -> Grid
def load_grid(path: Path) -> Grid
def straight_cells(design: LineDesign) -> tuple[list[tuple[int, int]], list[int]]   # cells, corner indices
def search_cells(design: LineDesign, grid: Grid) -> tuple[list[tuple[int, int]], list[int]]
```

Search decisions: rail and ice use 4-neighbour moves with a corner penalty of 12; road and path use 8-neighbour moves, then two passes of Chaikin smoothing rasterised back to an 8-connected cell list. Step cost = step length × (1 + 0.5·|Δground| + 0.3·cross slope) + 6 per water column (`surface > ground`); impassable: `avoid` boxes grown by 2, null columns, outside the grid. A* with the straight-line heuristic. When the grid has more than 250,000 columns, search a grid coarsened by `f = ceil(sqrt(columns / 250000))` (mean ground, any-null is null), then refine at full resolution inside a band of half-width `2f + 16` around the coarse path. Waypoints are separate legs joined at the shared cell. Corners are the indices where the step direction changes (rail, ice).

**Steps:**

- [ ] **Step 1: Write the failing tests** (`_grid(nx, nz, y)` builds `route.grid_from_heights(make_heights(None, (0, 0), np.full((nx, nz), y, float)))`; `_design(tmp_path, **kw)` calls `td.parse_line` with a `heights` value and the given keys)

```python
def test_straight_route_runs_axis_legs_through_via(tmp_path):
    d = _design(tmp_path, route="straight", start=[0, 65, 0], end=[20, 65, 10], via=[[20, 0]])
    cells, corners = route.straight_cells(d)
    assert cells[0] == (0, 0) and cells[-1] == (20, 10) and len(cells) == 31
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(cells, cells[1:], strict=False))
    assert corners == [20]

def test_search_goes_around_avoid_box(tmp_path):
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20], avoid=[[30, 5, 50, 35]])
    cells, _ = route.search_cells(d, _grid(80, 40, 64))
    assert cells[0] == (5, 20) and cells[-1] == (75, 20)
    assert not any(28 <= x <= 52 and 3 <= z <= 37 for x, z in cells)

def test_search_takes_the_pass_through_a_ridge(tmp_path):
    ground = np.full((80, 40), 64.0); ground[38:43, :] = 84; ground[38:43, 30:35] = 64
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20])
    cells, _ = route.search_cells(d, route.grid_from_heights(make_heights(None, (0, 0), ground)))
    assert all(30 <= z <= 34 for x, z in cells if 38 <= x <= 42)

def test_rail_search_moves_along_axes_with_few_corners(tmp_path):
    d = _design(tmp_path, start=[0, 65, 0], end=[60, 65, 30])
    cells, corners = route.search_cells(d, _grid(70, 40, 64))
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(cells, cells[1:], strict=False))
    assert len(corners) <= 2

def test_route_refuses_endpoint_inside_avoid_box(tmp_path):
    d = _design(tmp_path, mode="road", start=[40, 65, 20], end=[75, 65, 20], avoid=[[30, 5, 50, 35]])
    with pytest.raises(route.RouteError, match="inside an avoid box"):
        route.search_cells(d, _grid(80, 40, 64))

def test_route_refuses_when_null_columns_block_every_path(tmp_path):
    ground = np.full((80, 40), 64.0); ground[40:42, :] = np.nan
    d = _design(tmp_path, mode="road", start=[5, 65, 20], end=[75, 65, 20])
    with pytest.raises(route.RouteError, match="no route"):
        route.search_cells(d, route.grid_from_heights(make_heights(None, (0, 0), ground)))
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_route.py -q` → FAIL (import error)
- [ ] **Step 3: Implement** the Interfaces with the search decisions above.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): route search with avoid boxes and refusals"`

---

### Task 4: Vertical profile

**Goal:** Fit running levels along a route under the mode's grade rules and class each cell as grade, cut, fill, bridge or tunnel, merging short stretches.

**Files:**
- Modify: `skills/terrain-shape/tools/terrain/route.py`
- Test: `tests/ashlar/terrain/test_route_profile.py`

**Acceptance Criteria:**
- [ ] Rail levels change by at most 1 per cell; a corner and its neighbours share a level; road levels move in half blocks; ice stays level.
- [ ] A valley deeper than `max_fill` is a bridge, a ridge higher than `max_cut` with cover is a tunnel, water crossings keep `water_clearance`.
- [ ] Short bridges grow to `min_bridge`; short shallow tunnels become cuts.
- [ ] Unreachable fixed levels raise `RouteError` naming the cell.

**Verify:** `$PYTEST tests/ashlar/terrain/test_route_profile.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/route.py", "tests/ashlar/terrain/test_route_profile.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_route_profile.py -q", "acceptanceCriteria": ["grade rules per mode hold (rail 1 per cell, corners level, road half steps, ice level)", "valleys become bridges, covered ridges tunnels, water crossings keep clearance", "short bridges grow to min_bridge and short shallow tunnels become cuts", "unreachable fixed levels raise RouteError naming the cell"], "modelTier": "frontier"}
```

**Interfaces:**

```python
def fit_profile(design: LineDesign, cells: list[tuple[int, int]], corners: list[int],
                grid: Grid | None) -> tuple[list[float], list[str]]    # levels, kinds
def classify(design: LineDesign, levels: list[float], ground: list[float], surface: list[float]) -> list[str]
```

The algorithm (decided; the tests do not pin it):

```text
unit u = 0.5 (road) else 1; candidates L from min(ground) - max_cut - tunnel height - roof - 2
  to max(surface) + max_fill + water_clearance + 2, clipped to -60..315, in steps of u
t = ground + 1; d = L - t; w = formation width (rail 3, road 4*lanes + 2, path width, ice 4)
cell cost(i, L):
  water (surface > ground) and L < surface + 1 + water_clearance -> inf; water otherwise -> bridge
  d > max_fill -> bridge 40 + 2d
  0 < d <= max_fill -> fill d * (w + d * fill_ratio)
  d < -max_cut and t - L >= tunnel height + 1 + roof -> tunnel 60
  d < 0 -> cut |d| * (w + |d| * cut_ratio)
transition: |L_i - L_(i-1)| <= u (ice: 0), plus 0.2 * |L_i - L_(i-1)|
constraints: rail corners c -> L_(c-1) = L_c = L_(c+1); endpoints with y fixed; profile points fixed
dynamic programming with backtracking; no finite path -> RouteError("cannot reach level …")
classify: bridge (water, or d > max_fill), tunnel (d < -max_cut with cover), grade (|d| <= 1), fill (d > 1), cut (d < -1)
merge: a bridge run shorter than min_bridge grows symmetrically to min_bridge inside the route;
  a tunnel run shorter than min_tunnel becomes cut when its deepest cut <= 2 * max_cut, else grows to min_tunnel
  where cover allows, else RouteError naming the stretch
grid None (straight underground or Nether): levels all start.y, kinds all "tunnel" (Task 8 reclasses from reads)
```

**Steps:**

- [ ] **Step 1: Write the failing tests** (`_along_x(tmp_path, ground_list, **kw)` builds a straight design along +x from x=0, a grid from `ground_list` repeated over z 0..8, and returns `route.fit_profile(...)`)

```python
def test_rail_profile_changes_at_most_one_block_per_cell(tmp_path):
    levels, _ = _along_x(tmp_path, [64 + i // 2 for i in range(60)])
    assert max(abs(a - b) for a, b in zip(levels, levels[1:], strict=False)) <= 1

def test_rail_corner_and_neighbours_share_a_level(tmp_path):
    levels, corners = _with_corner_on_ramp(tmp_path)          # corner at index 20 on a 1-in-2 ramp
    assert levels[19] == levels[20] == levels[21] and corners == [20]

def test_valley_deeper_than_max_fill_is_a_bridge(tmp_path):
    ground = [64] * 30 + [50] * 10 + [64] * 30
    _, kinds = _along_x(tmp_path, ground)
    assert set(kinds[30:40]) == {"bridge"} and kinds[0] == "grade"

def test_ridge_higher_than_max_cut_with_cover_is_a_tunnel(tmp_path):
    ramp = [64 + 4 * i for i in range(1, 6)]
    _, kinds = _along_x(tmp_path, [64] * 25 + ramp + [84] * 15 + ramp[::-1] + [64] * 25)
    assert "tunnel" in kinds[32:42] and "cut" in kinds[24:30]

def test_short_bridge_grows_to_min_bridge(tmp_path):
    _, kinds = _along_x(tmp_path, [64] * 30 + [56] * 2 + [64] * 30)
    assert kinds.count("bridge") == 4

def test_short_tunnel_becomes_a_cut_when_shallow_enough(tmp_path):
    _, kinds = _along_x(tmp_path, [64] * 30 + [75] * 3 + [64] * 30)
    assert "tunnel" not in kinds

def test_water_crossing_keeps_clearance(tmp_path):
    levels, kinds = _river(tmp_path)                           # ground 56, surface 62 over x 30..35
    assert set(kinds[30:36]) == {"bridge"} and min(levels[30:36]) >= 66

def test_road_levels_move_in_half_blocks(tmp_path):
    levels, _ = _along_x(tmp_path, [64 + i // 2 for i in range(60)], mode="road")
    assert all((2 * v).is_integer() for v in levels)
    assert max(abs(a - b) for a, b in zip(levels, levels[1:], strict=False)) <= 0.5

def test_ice_profile_is_level(tmp_path):
    levels, _ = _along_x(tmp_path, [64] * 20 + [70] * 20, mode="ice", start_y=66, end_y=66)
    assert set(levels) == {66}

def test_profile_refuses_unreachable_endpoint_level(tmp_path):
    with pytest.raises(route.RouteError, match="cannot reach"):
        _along_x(tmp_path, [64] * 10, start_y=65, end_y=81)
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_route_profile.py -q` → FAIL (`fit_profile` missing)
- [ ] **Step 3: Implement** `fit_profile` and `classify` per the algorithm.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): vertical profile and stretch classes"`

---

### Task 5: Sections, route files, previews and the `route` command

**Goal:** Split a route into read sections with boxes, save and load route JSON, write route previews and a report, and add `terrain.py route`.

**Files:**
- Modify: `skills/terrain-shape/tools/terrain/route.py` (`Section`, `Route`, `make_sections`, `plan_route`, `write_route`, `load_route`)
- Create: `skills/terrain-shape/tools/terrain/transit_preview.py`, `skills/terrain-shape/tools/terrain/transit.py` (`run_route`, `add_transit_parsers`, `run_transit`)
- Modify: `skills/terrain-shape/scripts/terrain.py` (import and register the transit parsers; dispatch `route`, `line`, `portal`, `transit-check` to `run_transit`)
- Test: `tests/ashlar/terrain/test_route_sections.py`

**Acceptance Criteria:**
- [ ] Sections hold `section_length` cells (the last may be shorter), are named `s01`, `s02`, …, and their boxes cover the corridor, the margin, the ground below and the tops above.
- [ ] Route JSON round-trips and records a hash of the route-relevant design keys.
- [ ] `terrain.py route DESIGN --project P` exits 0, writes `terrain/<element>.route.json`, `terrain/<element>.route-report.json` and previews, and prints the section reads.

**Verify:** `$PYTEST tests/ashlar/terrain/test_route_sections.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/route.py", "skills/terrain-shape/tools/terrain/transit_preview.py", "skills/terrain-shape/tools/terrain/transit.py", "skills/terrain-shape/scripts/terrain.py", "tests/ashlar/terrain/test_route_sections.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_route_sections.py -q", "acceptanceCriteria": ["sections of section_length named s01.. with boxes covering corridor, margin, ground and tops", "route JSON round-trips with a design hash", "terrain.py route writes route, report, previews and prints the section reads"], "modelTier": "standard"}
```

**Interfaces:**

```python
@dataclass
class Section: name: str; start: int; end: int; box: tuple[int, int, int, int, int, int]; world: str | None
@dataclass
class Route:
    element: str; mode: str; world: str | None; dimension: str; design_hash: str
    cells: list[tuple[int, int]]; levels: list[float]; kinds: list[str]
    ground: list[float | None]; surface: list[float | None]; corners: list[int]; sections: list[Section]
def make_sections(design: LineDesign, route: Route, grid: Grid | None) -> list[Section]
def plan_route(design: LineDesign, grid: Grid | None) -> Route
def write_route(route: Route, path: Path) -> None
def load_route(path: Path) -> Route
def design_hash(design: LineDesign) -> str   # sha256[:12] of the source's element/world/mode/route/from/to/via/avoid/profile/limits/width/lanes
# transit_preview.py
def route_map(design: LineDesign, grid: Grid | None, route: Route, path: Path) -> Path
def profile_view(route: Route, path: Path) -> Path
def cross_sections(route: Route, folder: Path, *, element: str, site_of: Callable[[int], Site] | None = None, limit: int = 12) -> list[Path]
# transit.py
def run_route(design: LineDesign, project: Path, *, preview: bool = False) -> dict
def add_transit_parsers(commands) -> None
def run_transit(args) -> int
```

Section box (decided): cells `[k·L, min((k+1)·L, n) - 1]`; horizontal reach `R = ceil(half + max(max_fill·fill_ratio, max_cut·cut_ratio, tunnels.width) + 8)` around the section's cells (`half = transit_design.formation_half(design)`); `y1 = min(min(ground), min(floor(level)) - 1) - 6`; `y2 = max(max(top over the box columns) + 2, max(level) + tunnels.height + tunnels.roof + 2)`; with no grid (Nether) `y1 = level - 6`, `y2 = level + tunnels.height + 6`; clipped to -64..319. The report has `length`, counts per kind, `max_cut`, `max_fill`, `bridges` and `tunnels` as `[start, end, worst]`, and `reads`: `[{"section", "box", "out": "site/<element>-<name>", "world"}]`. Previews go to `terrain/previews/`: `<element>-route.png`, `<element>-profile.png`, `<element>-xs-NN.png` (at stretch changes, at most 12). The CLI prints `{"route": path, "report": …, "previews": […]}`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_sections_split_every_length_cells_and_cover_the_corridor(tmp_path):
    r = _planned(tmp_path, length=250)                            # flat ground 64, rail along +x, section_length 96
    assert [s.name for s in r.sections] == ["s01", "s02", "s03"]
    assert [(s.start, s.end) for s in r.sections] == [(0, 95), (96, 191), (192, 249)]
    for s in r.sections:
        x1, y1, z1, x2, y2, z2 = s.box
        assert all(x1 + 8 <= x <= x2 - 8 and z1 + 8 <= z <= z2 - 8 for x, z in r.cells[s.start:s.end + 1])

def test_section_box_reaches_below_ground_and_above_the_tallest_top(tmp_path):
    r = _planned(tmp_path, length=120, top_bump=(60, 4, 90))       # a tree top at (60, 4) y 90
    box = r.sections[0].box
    assert box[1] <= 64 - 6 and box[4] >= 92

def test_route_json_round_trips(tmp_path):
    r = _planned(tmp_path, length=120)
    route.write_route(r, tmp_path / "r.json")
    assert route.load_route(tmp_path / "r.json") == r

def test_route_command_writes_route_report_previews_and_reads(tmp_path):
    project = _project_with_heights(tmp_path)                       # writes heights.json and terrain/north-line.line.json
    out = subprocess.run([sys.executable, str(LAUNCHER), "route", str(project / "terrain/north-line.line.json"),
                          "--project", str(project)], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert (project / "terrain/north-line.route.json").exists()
    assert (project / "terrain/previews/north-line-profile.png").exists()
    assert data["report"]["reads"][0]["out"] == "site/north-line-s01"
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_route_sections.py -q` → FAIL
- [ ] **Step 3: Implement** the Interfaces; wire `terrain.py` like `add_cave_parsers`/`run_cave`.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): route sections, files, previews and the route command"`

---

### Task 6: Corridor grading

**Goal:** Build each section's designed surface (formation clipped between cut and fill slopes, noisy toe lines), its protect mask and material spec, the graded site, and the outer seam rows.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/corridor.py`
- Test: `tests/ashlar/terrain/test_corridor.py`

**Acceptance Criteria:**
- [ ] Inside the formation the target top block is `floor(level) - 1`; the cut slope meets the ground at about `half + depth·cut_ratio`, the fill toe at about `half + height·fill_ratio` (±1 for noise).
- [ ] Bridge, tunnel and tube columns, unchanged columns and columns nearest another section are protected.
- [ ] The toe line of a long cut is not straight.
- [ ] `emit_field` accepts the plan in preview mode, and the graded site leaves protected columns unchanged.
- [ ] Seam rows run along the corridor's outer edges only.

**Verify:** `$PYTEST tests/ashlar/terrain/test_corridor.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/corridor.py", "tests/ashlar/terrain/test_corridor.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_corridor.py -q", "acceptanceCriteria": ["formation at floor(level)-1, cut and fill slopes meet ground at the ratios within 1", "bridge, tunnel, tube, unchanged and other-section columns are protected", "a long cut's toe line is not straight", "emit_field preview accepts the plan and protected columns stay unchanged", "seam rows only on outer edges"], "modelTier": "standard"}
```

**Interfaces:**

```python
@dataclass
class CorridorPlan:
    field: HeightField; protect: np.ndarray; spec: MaterialSpec; cut_cells: int; fill_cells: int
def corridor_plan(design: LineDesign, route: Route, section: Section, site: Site) -> CorridorPlan
def graded_site(design: LineDesign, route: Route, section: Section, site: Site) -> tuple[Site, LiveWrite | None, CorridorPlan]
def outer_seam_rows(design: LineDesign, route: Route, section: Section, plan: CorridorPlan) -> list[dict]
```

Decisions: the field covers the whole section box (so `emit_field` needs no recipe) and holds top-block y values. A `Centerline` through the route's cells (world coordinates as floats, a few cells past the section ends) gives each column `(s, d)`; `level(s)` interpolates the route levels by chainage. With `f = floor(level) - 1`, `n` seeded value noise in [-1, 1] (frequency 0.15, seed `design.seed`), `ratio' = ratio·(1 + 0.25n)` and `|d|' = |d| + 1.5n`: `lo = f - (|d|' - half)/fill_ratio'`, `hi = f + (|d|' - half)/cut_ratio'` (rock cut ratio when the column's block at depth `f` is stone, deepslate, andesite, diorite, granite or tuff), `target = round(clip(ground, lo, hi))`. Only cells of kind grade, cut and fill are graded. Protected: `target == ground`, columns whose nearest route index is a bridge, tunnel or tube cell or lies outside `[section.start, section.end]`. `spec` takes surface weights from the top blocks of the box's unprotected-but-unchanged ring (normalised as `apron.surrounding_palette` does) and builds the `MaterialSpec` the way `apron.design_apron` does. `graded_site` runs `materialize_live(plan.field, plan.spec, site, None, protect=plan.protect)` and `blocks.apply_writes`. Seam rows `{"from": [x, z], "to": [x, z], "max_step": 1, "outward": dir}` follow the outermost changed columns on each side, broken where the section ends.

**Steps:**

- [ ] **Step 1: Write the failing tests** (`_flat_line(tmp_path, ground, level, length=40, kinds=None)` builds a rail design, a straight route along +x at z=20 with the given level and kinds, one section, and `make_site` over the section box)

```python
def test_formation_inside_and_cut_slope_outside(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=61)
    plan = corridor.corridor_plan(design, r, section, site)
    col = lambda x, z: plan.field.h[x - site.box[0], z - site.box[2]]
    half = td.formation_half(design)
    assert col(20, 20) == 60
    assert abs(col(20, 20 + math.ceil(half) + 4) - 64) <= 1
    assert plan.protect[20 - site.box[0], 20 + math.ceil(half) + 9 - site.box[2]]

def test_fill_slope_spreads_by_fill_ratio(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=64, level=69)
    plan = corridor.corridor_plan(design, r, section, site)
    half = td.formation_half(design)
    assert abs(plan.field.h[20 - site.box[0], 20 + math.ceil(half + 1.5 * 4) - site.box[2]] - 64) <= 1

def test_bridge_and_tunnel_columns_are_protected(tmp_path):
    kinds = ["grade"] * 10 + ["bridge"] * 10 + ["tunnel"] * 10 + ["grade"] * 10
    design, r, section, site = _flat_line(tmp_path, ground=64, level=65, kinds=kinds)
    plan = corridor.corridor_plan(design, r, section, site)
    assert plan.protect[15 - site.box[0], 20 - site.box[2]] and plan.protect[25 - site.box[0], 20 - site.box[2]]

def test_toe_line_is_not_straight(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=70, level=65, length=90)
    plan = corridor.corridor_plan(design, r, section, site)
    changed = plan.field.h != _ground_array(site)
    widths = [np.flatnonzero(changed[i]).ptp() for i in range(10, 80)]
    assert np.std(widths) >= 0.5

def test_graded_site_passes_emit_field_preview(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=_rolling(), level=66, length=60)
    plan = corridor.corridor_plan(design, r, section, site)
    emit_field(plan.field, plan.spec, site, tmp_path / "p", element="t-s01", first_phase=1,
               protect=plan.protect, require_relief=False, preview=True)
    graded, mass, _ = corridor.graded_site(design, r, section, site)
    x, z = _a_protected_column(plan, site)
    assert graded.columns[(x, z)] == site.columns[(x, z)]

def test_outer_seam_rows_skip_section_boundaries(tmp_path):
    design, r, section, site = _flat_line(tmp_path, ground=70, level=65, length=90)
    rows = corridor.outer_seam_rows(design, r, section, corridor.corridor_plan(design, r, section, site))
    half = td.formation_half(design)
    assert rows and all(abs(p[1] - 20) > half for row in rows for p in (row["from"], row["to"]))
    assert not any((row["from"][1] - 20) * (row["to"][1] - 20) < 0 for row in rows)   # none crosses the line
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_corridor.py -q` → FAIL
- [ ] **Step 3: Implement** the Interfaces with the decisions above.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): corridor grading through the terrain emitter"`

---

### Task 7: Track

**Goal:** Generate the running surface per mode: rail (ballast, exact shapes, boosters on redstone blocks, termini, clearance), road (surface, slabs, kerbs, lamps), path (irregular width, stairs) and ice (lane, guards, lights).

**Files:**
- Create: `skills/terrain-shape/tools/terrain/track.py`
- Test: `tests/ashlar/terrain/test_track.py`

**Acceptance Criteria:**
- [ ] `rail_shape` returns the shape table below for straights, corners and slopes.
- [ ] Every powered rail is `powered=true` on a redstone block, none on a corner; spacing 24 on the level and every 2nd slope cell; a terminus has no boosters on its last 8 cells and boosters on cells 9–11 from the end.
- [ ] Natural blocks 1–3 above the rail bed are carved to air.
- [ ] Roads put bottom slabs on half levels and lamps every `lights.spacing` cells; ice lanes are 2 wide with guards on both sides.

**Verify:** `$PYTEST tests/ashlar/terrain/test_track.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/track.py", "tests/ashlar/terrain/test_track.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_track.py -q", "acceptanceCriteria": ["rail_shape follows the shape table", "boosters on redstone blocks, none on corners, spacing 24 flat and every 2nd slope cell, terminus rules", "natural blocks 1-3 above the bed are carved", "road slabs on half levels and lamps at spacing; ice lane 2 wide with guards"], "modelTier": "standard"}
```

**Interfaces:**

```python
@dataclass(frozen=True)
class RailCell: x: int; y: int; z: int; shape: str; booster: bool
def rail_shape(prev: tuple[int, int, float] | None, cell: tuple[int, int, float], nxt: tuple[int, int, float] | None) -> str
def rail_cells(design: LineDesign, route: Route) -> list[RailCell]          # the whole line
def track_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                 light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]   # None -> design.lights.spacing
# returns, in order and omitting empty writes: ("carve", clearance), ("build", bed), ("track", rails or surface), ("light", lamps)
```

Shape table (decided; +x east, −x west, +z south, −z north): if the next cell is one higher → `ascending_<direction to next>`; elif the previous cell is one higher → `ascending_<direction to previous>`; else neighbours on the x axis → `east_west`, on the z axis → `north_south`, one on each → `<north|south>_<east|west>`. Rail y = `level`; the bed (palette `ballast`) is 3 wide at `level - 1` on cells of kind grade, cut, fill and tunnel; a booster's centre bed block is `minecraft:redstone_block` on every kind. Boosters: index `i` not a corner and not within the 8 cells next to a terminus end; on slope cells (level differs from a neighbour) when `i % boosters.slope == 0`, on level cells when `i % boosters.flat == 0`; plus the launch group 9th–11th cells from each terminus end. Clearance: natural non-liquid blocks at `level+1 … level+3` over the 3-wide bed become air. Rail and path: lamp posts (`lamp_post` 2 high with `lamp` on top) every `light_spacing` cells beside the bed, alternating sides, on cells of kind grade, cut and fill (bridges, tunnels and rooms light themselves in Task 8). Road: surface width `4·lanes`, kerbs (`edge`) one each side; a half level puts a bottom slab of the surface block at `floor(level)` on top of the graded block; lamps on the kerb every `light_spacing` cells, alternating sides. Path: `surface` weights with width varying ±1 by seeded noise; full steps get stairs facing up the slope. Ice: the 2-wide lane of `ice` at `level - 1`; bottom slabs of `guard` at `level` on both sides; every `light_spacing` cells one guard becomes `lights.block`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(("prev", "cell", "nxt", "shape"), [
    pytest.param((0, 0, 64), (1, 0, 64), (2, 0, 64), "east_west", id="straight-x"),
    pytest.param((0, 0, 64), (0, 1, 64), (0, 2, 64), "north_south", id="straight-z"),
    pytest.param((0, 0, 64), (1, 0, 64), (1, 1, 64), "south_west", id="corner-west-south"),
    pytest.param((1, 0, 64), (1, 1, 64), (2, 1, 64), "north_east", id="corner-north-east"),
    pytest.param((0, 0, 64), (1, 0, 64), (2, 0, 65), "ascending_east", id="rise-ahead"),
    pytest.param((0, 0, 65), (1, 0, 64), (2, 0, 64), "ascending_west", id="rise-behind"),
    pytest.param(None, (0, 0, 64), (0, 1, 64), "north_south", id="line-start"),
])
def test_rail_shape(prev, cell, nxt, shape):
    assert track.rail_shape(prev, cell, nxt) == shape

def test_boosters_sit_on_redstone_blocks_and_skip_corners(tmp_path):
    design, r, section, site = _rail_with_corner(tmp_path)        # 60 cells, corner at 24 (a booster index)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    boosters = [c for c in track.rail_cells(design, r) if c.booster]
    assert boosters and 24 not in [r.cells.index((c.x, c.z)) for c in boosters]
    for c in boosters:
        assert after.block(c.x, c.y, c.z).startswith("minecraft:powered_rail") and "powered=true" in after.block(c.x, c.y, c.z)
        assert after.block(c.x, c.y - 1, c.z) == "minecraft:redstone_block"

def test_booster_spacing_on_the_level_and_on_slopes(tmp_path):
    cells = track.rail_cells(*_rail_line(tmp_path, levels=[65] * 50 + [65 + i for i in range(1, 11)] + [75] * 40)[:2])
    flat = [i for i, c in enumerate(cells) if c.booster and i < 50]
    slope = [i for i, c in enumerate(cells) if c.booster and 50 <= i < 60]
    assert flat == [0, 24, 48] and slope == [50, 52, 54, 56, 58]

def test_terminus_has_no_boosters_on_the_last_eight_cells_and_a_launch_group(tmp_path):
    cells = track.rail_cells(*_rail_line(tmp_path, levels=[65] * 60, end_stop="terminus")[:2])
    assert not any(c.booster for c in cells[-8:])
    assert all(c.booster for c in cells[-11:-8])

def test_clearance_carves_leaves_over_the_rail(tmp_path):
    design, r, section, site = _rail_line(tmp_path, levels=[65] * 30, cells={(10, 67, 20): LEAVES})
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    assert after.block(10, 67, 20) == "minecraft:air"

def test_road_surface_uses_slabs_on_half_levels(tmp_path):
    design, r, section, site = _road_line(tmp_path, levels=[65.0, 65.5, 66.0, 66.5, 67.0] * 4)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    x, z = r.cells[1]
    assert "_slab" in after.block(x, 65, z) and "type=bottom" in after.block(x, 65, z)

def test_road_lamps_every_spacing(tmp_path):
    design, r, section, site = _road_line(tmp_path, levels=[65.0] * 40)
    light = dict(track.track_layers(design, r, section, site))["light"]
    lamp_ids = set(design.palette["lamp"])
    lamps = sum(1 for i, j, k in np.argwhere(light.codes) if base_id(light.palette[light.codes[i, j, k]]) in lamp_ids)
    assert lamps >= 40 // design.lights.spacing

def test_ice_lane_is_two_wide_with_guards(tmp_path):
    design, r, section, site = _ice_line(tmp_path, level=66)
    after = blocks.apply_writes(site, track.track_layers(design, r, section, site))
    x, z = r.cells[5]
    assert [after.block(x, 65, z + dz) for dz in (0, 1)] == ["minecraft:packed_ice"] * 2
    assert "_slab" in after.block(x, 66, z - 1) and "_slab" in after.block(x, 66, z + 2)
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_track.py -q` → FAIL
- [ ] **Step 3: Implement** the Interfaces and the table.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): rail, road, path and ice track"`

---

### Task 8: Structures

**Goal:** Bridges (beam, arch, piers, piers in water), tunnels (bore, lining that keeps built blocks, lights, mouths), Nether classing (tunnel, tube, lava refusal) and stops (terminus end and platform, room, open).

**Files:**
- Create: `skills/terrain-shape/tools/terrain/structures.py`
- Test: `tests/ashlar/terrain/test_structures.py`

**Acceptance Criteria:**
- [ ] Beam piers stand at most `pier_spacing` apart and reach solid ground; `auto` picks beam up to 16 cells and arches (spans ≤ 40) above that.
- [ ] Piers in still water need `piers_in_water` and are counted; flowing water or lava under a pier is refused.
- [ ] Tunnel bores are air, the shell is lining with lights, existing non-natural blocks are kept, cave air in the shell is sealed, and water or lava in the bore or shell is refused naming the cell.
- [ ] `nether_kinds` returns tunnel or tube per cell and refuses lava naming the cell.
- [ ] A terminus adds an end block and a platform; a room is lined and lit; `open` adds nothing.

**Verify:** `$PYTEST tests/ashlar/terrain/test_structures.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/structures.py", "tests/ashlar/terrain/test_structures.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_structures.py -q", "acceptanceCriteria": ["beam piers at most pier_spacing apart reach ground; auto picks beam to 16 then arches", "piers in still water need the flag and are counted; flowing water and lava refused", "tunnel bore air, lining lit, built blocks kept, cave air sealed, liquid refused naming the cell", "nether_kinds classes tunnel or tube and refuses lava", "terminus end block and platform, lined lit room, open adds nothing"], "modelTier": "standard"}
```

**Interfaces:**

```python
def nether_kinds(design: LineDesign, route: Route, section: Section, site: Site) -> list[str]
def bridge_layers(design: LineDesign, route: Route, section: Section, site: Site) -> tuple[list[tuple[str, LiveWrite]], dict]
    # stats {"piers": int, "displaced_water": int, "unsupported_tube": int}
def tunnel_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                  light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]   # None -> design.lights.spacing
def stop_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]
```

`bridge_layers` also takes `light_spacing: int | None = None`. Decisions: cross-section offsets are perpendicular to the local direction. Bridge deck: `deck` blocks at `floor(level) - 1`, formation width + 2, `railing` on the outer cells at `floor(level)` when `railings`, and a lamp (`lamp_post` + `lamp`) on the railing line every `light_spacing` cells, alternating sides. Beam piers: a 1-cell-thick wall of `pier` under the deck width at every `pier_spacing`-th bridge cell and at both bridge ends, down to the first solid natural block. Arch: piers at span ends (spans ≤ 40, `ceil(length / 32)` spans), spandrel fill under the deck where `y >= deck - 1 - rise·(1 - (2u - 1)²)`, `rise = min(span / 4, deck - ground - 2)`, `u` ∈ [0, 1] along the span. A pier cell in water: still water with the flag → allowed and counted; still water without it → `RouteError("pier at … stands in water; set bridges.piers_in_water")`; flowing water or lava → refused. Tunnel: bore width `tunnels.width` (centred), y `level … level + height - 1`, carved where natural; shell ring at the next offset outwards, floor row at `level - 1`, roof row at `level + height`; `lining` blocks where the shell cell is natural or air; non-natural solid cells kept; liquid in bore or shell → `RouteError` naming the cell; every `light_spacing` cells one wall block at `level + 1` becomes `lights.block`, alternating sides; the end cells' shell uses `edge` (the mouth). Tube: the same section with every shell cell built; piers as beam piers when solid non-lava ground is within 24 below, else counted in `unsupported_tube`. `nether_kinds`: lava in the bore or shell → `RouteError` naming it; at least half the bore cells air or cave air → `"tube"`, else `"tunnel"`. Stops: terminus → `end_block` at the cell one step past the end at `level`, `platform` 2 wide × 8 long at `level` on the left of travel; room → a lined room 5 wide × 4 high × 5 long around the end cell with lights; open → nothing.

**Steps:**

- [ ] **Step 1: Write the failing tests** (fixtures build sites with `make_site`, routes with given kinds and levels)

```python
def test_beam_bridge_piers_reach_ground_at_most_spacing_apart(tmp_path):
    design, r, section, site = _valley_bridge(tmp_path, length=12, depth=12)
    layers, stats = structures.bridge_layers(design, r, section, site)
    piers = _pier_indices(blocks.apply_writes(site, layers), r, design)
    assert piers[0] == 0 and piers[-1] == 11 and max(b - a for a, b in zip(piers, piers[1:], strict=False)) <= 8
    assert stats["piers"] == len(piers)

def test_auto_picks_beam_up_to_16_and_arches_above(tmp_path):
    assert _bridge_kind(tmp_path, length=14) == "beam" and _bridge_kind(tmp_path, length=30) == "arch"

def test_piers_in_still_water_need_the_flag(tmp_path):
    with pytest.raises(route.RouteError, match="piers_in_water"):
        structures.bridge_layers(*_lake_bridge(tmp_path, piers_in_water=False))

def test_piers_in_still_water_are_counted_with_the_flag(tmp_path):
    _, stats = structures.bridge_layers(*_lake_bridge(tmp_path, piers_in_water=True))
    assert stats["displaced_water"] > 0

def test_tunnel_bore_is_air_lined_and_lit(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path)
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    x, z = r.cells[10]
    assert all(after.block(x, y, z) == "minecraft:air" for y in range(65, 69))
    assert any(after.block(x2, 66, z2) == design.lights.block for x2, z2 in _wall_cells(r, 6, 18))

def test_lining_keeps_built_blocks_and_seals_cave_air(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path, cells={(10, 66, 22): PLANKS, (12, 66, 22): CAVE_AIR})
    after = blocks.apply_writes(site, structures.tunnel_layers(design, r, section, site, light_spacing=6))
    assert after.block(10, 66, 22) == PLANKS and after.block(12, 66, 22) != CAVE_AIR

def test_tunnel_refuses_water_in_the_shell(tmp_path):
    design, r, section, site = _hill_tunnel(tmp_path, cells={(10, 67, 22): WATER})
    with pytest.raises(route.RouteError, match=r"\(10, 67, 22\)"):
        structures.tunnel_layers(design, r, section, site, light_spacing=6)

def test_nether_kinds_tunnel_tube_and_lava(tmp_path):
    design, r, section, site = _nether_line(tmp_path, cavern=range(20, 30))
    kinds = structures.nether_kinds(design, r, section, site)
    assert set(kinds[20:30]) == {"tube"} and kinds[5] == "tunnel"
    design, r, section, site = _nether_line(tmp_path / "lava", lava_at=(15, 70, 1))
    with pytest.raises(route.RouteError, match=r"\(15, 70, 1\)"):
        structures.nether_kinds(design, r, section, site)

def test_terminus_end_block_and_platform(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path)
    after = blocks.apply_writes(site, structures.stop_layers(design, r, section, site, light_spacing=12))
    end = _one_past_end(r)
    assert base_id(after.block(*end)) in design.palette["end_block"]

def test_open_stop_adds_nothing(tmp_path):
    design, r, section, site = _rail_line_with_terminus(tmp_path, stop="open")
    assert structures.stop_layers(design, r, section, site, light_spacing=12) == []
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_structures.py -q` → FAIL
- [ ] **Step 3: Implement** the Interfaces with the decisions above.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): bridges, tunnels, tubes and stops"`

---

### Task 9: Transit checks

**Goal:** `check_line` runs continuity, support, boosters, clearance, walk, light, deck, seal and grade over per-section sites, for the projected state and for fresh reads.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/transit_checks.py`
- Test: `tests/ashlar/terrain/test_transit_checks.py`

**Acceptance Criteria:**
- [ ] A line built from Tasks 7–8 passes every check.
- [ ] Each check fails on its own mutation (a missing rail, a booster without its block, a floating rail, a block over the rail, a 2-block step on a road, a dark floor cell, a deck without piers, lava beside a bore, a rail off its level) and lists up to 10 cells.
- [ ] Light needs ≥ 1 in the Overworld and ≥ 12 in the Nether.

**Verify:** `$PYTEST tests/ashlar/terrain/test_transit_checks.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/transit_checks.py", "tests/ashlar/terrain/test_transit_checks.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_transit_checks.py -q", "acceptanceCriteria": ["a generated line passes every check", "each check fails on its mutation and lists up to 10 cells", "light needs 1 in the Overworld and 12 in the Nether"], "modelTier": "standard"}
```

**Interfaces:**

```python
CHECKS = ("continuity", "support", "boosters", "clearance", "walk", "light", "deck", "seal", "grade")
def check_line(design: LineDesign, route: Route, sites: Mapping[str, Site]) -> dict
    # {"ok": bool, "checks": [{"name": str, "ok": bool, "detail": str, "cells": [[x, y, z], …]}]}; checks not
    # applicable to the mode are left out; each cell is read from the section site that contains it
```

Definitions (decided): continuity — every `track.rail_cells` entry holds `rail` or `powered_rail` with that shape. support — rails, standing lanterns, torches and carpets sit on a full cube, a `type=top` slab or `half=top` stairs; hanging lanterns hang under a non-air block. boosters — expected boosters are `powered=true` over `redstone_block`, and no powered rail has a corner shape. clearance — rail: `level+1 … level+2` passable over every rail; road and path: `floor(level) … floor(level)+2` passable over the centreline. walk (road, path) — walking heights read from the site (full block top `y+1`, bottom slab `y+0.5`) change by ≤ 0.5 (road) or ≤ 1 (path) between neighbours. light — open cells with a spawnable block below (full solid top and not in the non-spawnable list) on the formation (within `formation_half` of the centreline at the running level), on decks and platforms, and on tunnel, tube and room floors, need `blocks.flood` light ≥ `lights.minimum`. deck — every bridge cell is within `pier_spacing // 2 + 1` cells of a pier column that reaches a solid natural block, or under arch fill that does. seal — no water or lava face-adjacent to a bore, tube or room air cell. grade — rail y equals the level; road and path surface within 0.5; ice at `level - 1`.

**Steps:**

- [ ] **Step 1: Write the failing tests** — one passing test on a generated line (`_built(tmp_path, kind=…)` applies Tasks 7–8 layers to a synthetic site and returns `design, route, {"s01": site}`), and one failing test per check that mutates one cell with `blocks.apply_writes(site, [("x", blocks.cells_write({cell: state}))])`:

```python
def test_generated_line_passes_every_check(tmp_path):
    design, r, sites = _built(tmp_path, kind="rail-with-bridge-and-tunnel")
    report = transit_checks.check_line(design, r, sites)
    assert report["ok"], report

@pytest.mark.parametrize(("check", "mutation"), [
    pytest.param("continuity", "remove_rail", id="missing-rail"),
    pytest.param("boosters", "remove_redstone_block", id="booster-without-block"),
    pytest.param("support", "air_under_rail", id="floating-rail"),
    pytest.param("clearance", "stone_over_rail", id="blocked-rail"),
    pytest.param("deck", "remove_piers", id="deck-without-piers"),
    pytest.param("seal", "lava_beside_bore", id="lava-beside-bore"),
    pytest.param("grade", "raise_rail", id="rail-off-level"),
    pytest.param("light", "remove_lights", id="dark-floor"),
])
def test_each_check_fails_on_its_mutation(tmp_path, check, mutation):
    design, r, sites = _built(tmp_path, kind="rail-with-bridge-and-tunnel")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, mutation))
    failed = {c["name"]: c for c in report["checks"] if not c["ok"]}
    assert not report["ok"] and check in failed and 0 < len(failed[check]["cells"]) <= 10

def test_walk_fails_on_a_two_block_step(tmp_path):
    design, r, sites = _built(tmp_path, kind="road")
    report = transit_checks.check_line(design, r, _mutate(sites, r, design, "two_block_step"))
    assert any(c["name"] == "walk" and not c["ok"] for c in report["checks"])

def test_nether_tunnel_needs_light_twelve(tmp_path):
    design, r, sites = _built(tmp_path, kind="nether-tunnel", light_spacing=12)   # too sparse for 12
    report = transit_checks.check_line(design, r, sites)
    assert any(c["name"] == "light" and not c["ok"] for c in report["checks"])
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_transit_checks.py -q` → FAIL
- [ ] **Step 3: Implement** `check_line` per the definitions.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): projected and post-build line checks"`

---

### Task 10: Line emission and the `line` and `transit-check` commands

**Goal:** Emit a line section by section (grading phases through `emit_field`, infrastructure phases through `check_form_layers`), with projected checks, the player-block token, merged plan rows, the report with registry boxes, previews, and the `line` and `transit-check` commands.

**Files:**
- Modify: `skills/terrain-shape/tools/terrain/transit.py`
- Test: `tests/ashlar/terrain/test_transit.py`

**Acceptance Criteria:**
- [ ] `--preview` writes reports and previews and no phase files.
- [ ] Phase ids are contiguous from `--first-phase`: per section the grading phases, then carve, build, track and light.
- [ ] A missing section read, a read that does not cover the section box, a stale route and a world mismatch are refused, naming the section and its read folder.
- [ ] Player blocks need the report's token; a design edit changes the token and the old token is refused.
- [ ] Plan rows carry `transit{file}`, every section's `surface_match` and only outer-edge `seam` rows; the report has `boxes`.
- [ ] `transit-check` exits 0 on the projected line and 1 after a rail is removed.

**Verify:** `$PYTEST tests/ashlar/terrain/test_transit.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/transit.py", "tests/ashlar/terrain/test_transit.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_transit.py -q", "acceptanceCriteria": ["preview writes reports and previews only", "contiguous phase ids: grading then carve, build, track, light per section", "missing or short section read, stale route and world mismatch refused naming section and folder", "player blocks need the token; a design edit changes it and the old one is refused", "plan rows carry transit, surface_match and outer seams; report has boxes", "transit-check exits 0 on the projected line and 1 after a rail is removed"], "modelTier": "frontier"}
```

**Interfaces:**

```python
@dataclass
class LineResult:
    rows: list[dict]; quality: dict[str, list[dict]]; notes: list[str]; bbox: tuple[int, ...]; report: dict; previews: list[Path]
def section_read(project: Path, design: LineDesign, section: Section) -> Site
def emit_line(design: LineDesign, project: Path, *, first_phase: int, preview: bool = False, standalone: bool = False,
              approve_built: str | None = None, max_columns: int = 128) -> LineResult
```

Per section, in order (decided): load `site/<element>-<name>` (refuse when missing, when its box does not contain the section box, or when `site.world != design.world`, quoting the read's box and folder); Nether or underground straight lines take `structures.nether_kinds` into `route.kinds`; `corridor.graded_site`, and when the mass write is not empty `emit_field(plan.field, plan.spec, site, project, element=f"{element}-{name}", first_phase=next_id, protect=plan.protect, require_relief=False, seam_rows=corridor.outer_seam_rows(…), preview=preview)`; infrastructure on the graded site as `[structures carve, structures + stops build, track carve/build/track, light]`, merged by mode into the order carve, build, track, light; lighting starts at `design.lights.spacing` and halves (at most 4 times) until the section's light check passes; `blocks.touched_blocks(site, [("grade", mass), *layers], why)` with reasons such as `"inside the rail bore at chainage 120"`; `check_form_layers(graded, layers, max_columns=max_columns)`; `final = blocks.apply_writes(graded, layers)`; phase files `phases/NN-<element>-<name>-<mode>-<k>.json` with `{"fills": greedy_fills(tile), "liquids": "static", "world": site.world}`, via `placer`, rollback `backup`. After all sections: `transit_checks.check_line` on the final sites (failure → `VerifyError` listing failed checks unless previewing); the token from `blocks.built_token` (non-preview, items present, `approve_built != token` → `VerifyError` naming the count and the token's report path). Write `terrain/<element>.plan-rows.toon` with `plan_rows_toon(EmitResult(rows, quality, notes, bbox, None, None))`, where quality is `{"transit": [{"file": "terrain/<element>.line.json"}], "surface_match": …, "seam": …}`; `terrain/<element>.line-report.json` with `sections`, `check`, `built {token, count, items}`, `boxes` (the section boxes), `displaced_water`, `unsupported_tube`; previews with `transit_preview.cross_sections(route, …, site_of=…)`; `--standalone` writes `plan.toon` with the cave-style header. The route comes from `terrain/<element>.route.json`; refuse when missing ("run terrain.py route first") or when its `design_hash` differs ("the route is stale; run terrain.py route again").

CLI: `line DESIGN --project DIR --first-phase N [--preview] [--standalone] [--approve-built TOKEN]` prints `{"preview", "phases", "bbox", "notes", "report", "previews"}`. `transit-check DESIGN --sites DIR [DIR …] [--project DIR]` loads a line design (or, after Task 11, a portal design by its `.portal.json` suffix), maps each read to the section whose box it contains, prints the report and exits 1 on a failure.

**Steps:**

- [ ] **Step 1: Write the failing tests** (`_project(tmp_path, …)` writes heights, a rail design with a valley and a hill, runs `run_route`, and writes every section read with `make_site` from the same ground arrays)

```python
def test_line_preview_writes_reports_and_previews_but_no_phases(tmp_path):
    design, project = _project(tmp_path)
    result = transit.emit_line(design, project, first_phase=1, preview=True)
    assert result.previews and (project / "terrain/north-line.line-report.json").exists()
    assert not (project / "phases").exists()

def test_line_emit_orders_grading_then_infrastructure_with_contiguous_ids(tmp_path):
    design, project = _project(tmp_path)
    rows = transit.emit_line(design, project, first_phase=3).rows
    assert [r["id"] for r in rows] == list(range(3, 3 + len(rows)))
    s01 = [r["name"].split("-s01-")[1].split("-")[0] for r in rows if "-s01-" in r["name"]]
    assert s01 == sorted(s01, key=["mass", "carve", "build", "track", "light"].index)

def test_line_refuses_missing_section_read(tmp_path):
    design, project = _project(tmp_path)
    shutil.rmtree(project / "site/north-line-s02")
    with pytest.raises(ValueError, match=r"s02.*site/north-line-s02"):
        transit.emit_line(design, project, first_phase=1)

def test_line_refuses_a_stale_route(tmp_path):
    design, project = _project(tmp_path)
    edited = _edit(design, to={"at": [190, 65, 20], "stop": "terminus"})
    with pytest.raises(ValueError, match="stale"):
        transit.emit_line(edited, project, first_phase=1)

def test_line_requires_the_token_for_player_blocks(tmp_path):
    design, project = _project(tmp_path, built={(40, 66, 20): "minecraft:oak_fence"})
    with pytest.raises(VerifyError, match="player block"):
        transit.emit_line(design, project, first_phase=1)
    token = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]["token"]
    assert transit.emit_line(design, project, first_phase=1, approve_built=token).rows

def test_design_edit_changes_built_token(tmp_path):
    design, project = _project(tmp_path, built={(40, 66, 20): "minecraft:oak_fence", (60, 66, 20): "minecraft:chest"})
    old = transit.emit_line(design, project, first_phase=1, preview=True).report["built"]["token"]
    edited, project = _project(tmp_path / "b", built={(40, 66, 20): "minecraft:oak_fence"})
    new = transit.emit_line(edited, project, first_phase=1, preview=True).report["built"]["token"]
    assert new != old
    with pytest.raises(VerifyError):
        transit.emit_line(edited, project, first_phase=1, approve_built=old)

def test_plan_rows_carry_transit_surface_match_and_outer_seams(tmp_path):
    design, project = _project(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    text = (project / "terrain/north-line.plan-rows.toon").read_text()
    assert "transit[1]{file}:" in text and "surface_match[" in text and "seam[" in text
    assert json.loads((project / "terrain/north-line.line-report.json").read_text())["boxes"]

def test_transit_check_cli_passes_on_the_projected_line_and_fails_on_a_gap(tmp_path):
    design, project = _project(tmp_path)
    transit.emit_line(design, project, first_phase=1)
    dirs = _write_projected_sites(project)              # applies every phase file's fills to the section reads
    assert _cli("transit-check", project, dirs).returncode == 0
    _remove_one_rail(dirs[0], project)
    assert _cli("transit-check", project, dirs).returncode == 1
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_transit.py -q` → FAIL
- [ ] **Step 3: Implement** `emit_line`, `section_read` and the two commands per the decisions.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): line emission with checks, token, plan rows and transit-check"`

---

### Task 11: Portals

**Goal:** Portal pair math, the arrival spread, the stealing-portal check, frames and portal blocks, landings with doorways, emission for both worlds, `terrain.py portal`, and portal support in `transit-check`.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/portals.py`
- Modify: `skills/terrain-shape/tools/terrain/transit.py` (the `portal` parser and dispatch; `transit-check` for `.portal.json`)
- Test: `tests/ashlar/terrain/test_portals.py`

**Acceptance Criteria:**
- [ ] `scale` maps (3600, 70, 0) to the Nether as (450, 70, 0), (−109, 40, 20) to the Overworld as (−872, 40, 160) and (−1, 64, −9) to the Nether as (−1, 64, −2).
- [ ] A 2-wide Nether opening's arrival points span 16 blocks in the Overworld.
- [ ] The pair check passes with no other portal and fails, naming the cell, when another portal block is nearer to any arrival point.
- [ ] A 4×5 frame has 14 obsidian and 6 `nether_portal[axis=x]` blocks; the Nether landing is lit to 12 and keeps its doorways open; a Nether end in lava is refused naming the cell.
- [ ] `terrain.py portal` lists the read boxes when reads are missing, and with reads writes phases for both worlds.

**Verify:** `$PYTEST tests/ashlar/terrain/test_portals.py -q` → all pass

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/portals.py", "skills/terrain-shape/tools/terrain/transit.py", "tests/ashlar/terrain/test_portals.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_portals.py -q", "acceptanceCriteria": ["scale maps the three pinned points", "a 2-wide Nether opening spreads 16 blocks in the Overworld", "pair check passes clean and fails naming a nearer portal", "4x5 frame has 14 obsidian and 6 axis portal blocks; Nether landing lit to 12 with open doorways; lava refused", "portal command lists reads then writes phases for both worlds"], "modelTier": "standard"}
```

**Interfaces:**

```python
@dataclass(frozen=True)
class PortalEnd: world: str; dimension: str; at: tuple[int, int, int] | None; axis: str; existing: bool
@dataclass(frozen=True)
class PortalDesign:
    element: str; seed: int; size: tuple[int, int]; overworld: PortalEnd; nether: PortalEnd
    doorways: tuple[tuple[int, int, int, str], ...]; style: str; palette: dict[str, dict[str, int]]; project: Path
def parse_portal(data: dict, project_dir: Path) -> PortalDesign
def load_portal(path: Path, project_dir: Path | None = None) -> PortalDesign
def scale(point: tuple[int, int, int], into: str) -> tuple[int, int, int]
def frame_origin(design: PortalDesign, dimension: str) -> tuple[int, int, int]   # bottom outer corner (min x, z)
def opening(design: PortalDesign, dimension: str) -> list[tuple[int, int, int]]
def arrival_points(design: PortalDesign, into: str) -> list[tuple[float, float, float]]
def read_boxes(design: PortalDesign) -> dict[str, tuple[int, int, int, int, int, int]]
def pair_check(design: PortalDesign, sites: Mapping[str, Site]) -> dict
def portal_layers(design: PortalDesign, dimension: str, site: Site) -> list[tuple[str, LiveWrite]]
def emit_portal(design: PortalDesign, project: Path, *, first_phase: int, preview: bool = False, standalone: bool = False,
                approve_built: str | None = None, max_columns: int = 128) -> dict
```

Decisions: the given end's `at` is the frame's bottom outer corner; the other end is `scale(at)` with the same axis and size. When the Nether `at` is not given, its y is the scaled y if the landing fits there (33..120, no lava in the landing shell), else the nearest y that fits, else `RouteError` naming the lava cell. Arrival points: for each opening cell of the source end, its corner, centre and far edge along the opening (`+0`, `+0.5`, `+1`) and mid-height, scaled into the other dimension, so a 2-wide opening covers its whole width. The pair passes for a dimension when, for every arrival point, the nearest `nether_portal` cell of the partner opening is strictly nearer (3-D Euclidean) than every other `nether_portal` block in that dimension's read, and lies within the search radius (horizontal Chebyshev ≤ 128 Overworld, 16 Nether). `read_boxes`: per dimension, the frame and landing, plus every arrival point grown by its distance to the partner + 3. Frame: outer `w × h` (default 4 × 5) of `minecraft:obsidian`, opening `nether_portal[axis=<axis>]`. Overworld landing: a `platform` 3 deep on both faces at `frame y - 1`. Nether landing: an enclosed room around both faces (5 deep each side, 4 high, frame width + 2 wide), lined like a tunnel (keeps non-natural blocks), lit to `lights.minimum` 12, with each `doorway` `(x, y, z, facing)` left open 2 high and framed in `edge`. Emission writes per-dimension phases (`world` in each payload) through `check_form_layers`, with the token rule from Task 10 and the `transit{file}` row pointing at the portal design. `transit-check` on a portal design checks the frame, the axis blocks, the landing light and `pair_check` on the fresh reads.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_scale_overworld_to_nether_and_back():
    assert portals.scale((3600, 70, 0), "nether") == (450, 70, 0)
    assert portals.scale((-109, 40, 20), "overworld") == (-872, 40, 160)
    assert portals.scale((-1, 64, -9), "nether") == (-1, 64, -2)

def test_arrival_points_spread_sixteen_into_the_overworld(tmp_path):
    design = _design(tmp_path, nether_at=[10, 70, 5], axis="x")          # opening 2 wide along x
    xs = [p[0] for p in portals.arrival_points(design, "overworld")]
    assert max(xs) - min(xs) == 16

def test_pair_check_passes_with_no_other_portal(tmp_path):
    design, sites = _pair_sites(tmp_path)
    assert portals.pair_check(design, sites)["ok"]

def test_pair_check_flags_a_nearer_portal(tmp_path):
    design, sites = _pair_sites(tmp_path, extra_portal=("overworld", (95, 70, 41)))
    report = portals.pair_check(design, sites)
    assert not report["ok"] and [95, 70, 41] in report["checks"][0]["cells"]

def test_portal_layers_build_frame_and_axis_blocks(tmp_path):
    design, sites = _pair_sites(tmp_path)
    after = blocks.apply_writes(sites["overworld"], portals.portal_layers(design, "overworld", sites["overworld"]))
    states = [after.block(x, y, z) for x, y, z in _frame_box_cells(design, "overworld")]
    assert states.count("minecraft:obsidian") == 14 and states.count("minecraft:nether_portal[axis=x]") == 6

def test_nether_landing_is_lit_to_twelve_and_keeps_doorways_open(tmp_path):
    design, sites = _pair_sites(tmp_path, doorways=[[13, 70, 9, "south"]])
    after = blocks.apply_writes(sites["nether"], portals.portal_layers(design, "nether", sites["nether"]))
    assert after.block(13, 70, 9) == "minecraft:air" and after.block(13, 71, 9) == "minecraft:air"
    assert _min_floor_light(after, design) >= 12

def test_nether_end_in_lava_is_refused_with_the_cell(tmp_path):
    design, sites = _pair_sites(tmp_path, nether_lava=(12, 70, 7))
    with pytest.raises(route.RouteError, match=r"\(12, 70, 7\)"):
        portals.portal_layers(design, "nether", sites["nether"])

def test_portal_command_lists_reads_then_emits_phases_for_both_worlds(tmp_path):
    project = _portal_project(tmp_path)
    first = _cli("portal", project)
    assert first.returncode == 1 and "site/east-gate-overworld" in first.stderr
    _write_reads(project)
    second = _cli("portal", project)
    assert second.returncode == 0
    worlds = {json.loads(p.read_text())["world"] for p in (project / "phases").glob("*.json")}
    assert worlds == {"world", "world_nether"}
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/terrain/test_portals.py -q` → FAIL
- [ ] **Step 3: Implement** the Interfaces; reads live at `site/<element>-overworld` and `site/<element>-nether`.
- [ ] **Step 4: Run** → all pass
- [ ] **Step 5: Commit** — `git commit -m "feat(transit): portal pairs, landings and the portal command"`

---

### Task 12: `exec-ashlar` references and the toolkit API

**Goal:** Document the `transit` row, the ride-test steps, the registry's `boxes`, and the new toolkit commands; pin them with text tests.

**Files:**
- Modify: `skills/exec-ashlar/reference/plan-format.md`, `skills/exec-ashlar/reference/verification.md`, `skills/exec-ashlar/reference/registry.md`, `skills/exec-ashlar/reference/survey.md`, `skills/exec-ashlar/reference/execution.md`, `skills/exec-ashlar/reference/commands.md`, `skills/exec-ashlar/SKILL.md`
- Modify: `skills/terrain-shape/reference/terrain/toolkit-api.md`
- Test: `tests/ashlar/test_transit_text.py`

**Acceptance Criteria:**
- [ ] `plan-format.md` and `verification.md` have a `transit{file}` row (fresh exact reads of the report's `boxes` or the portal read boxes, then `terrain.py transit-check`, pass on exit 0).
- [ ] The `tests` table has a `summon` kind (one quoted tagged `summon` command, a world change shown at the gate) and an `await` detail `entity` (`<tag> within <seconds>`: repeat `data get entity … Pos` until the entity is within 2 blocks of `at`); the test mode kills the test's tagged entities before releasing force-loads.
- [ ] `registry.md` documents `boxes`; `survey.md`'s overlap check uses `boxes` when present.
- [ ] `toolkit-api.md` lists `route`, `line`, `portal` and `transit-check` and the new modules.

**Verify:** `$PYTEST tests/ashlar/test_transit_text.py tests/ashlar/test_skill_text.py -q` → all pass

```json:metadata
{"files": ["skills/exec-ashlar/reference/plan-format.md", "skills/exec-ashlar/reference/verification.md", "skills/exec-ashlar/reference/registry.md", "skills/exec-ashlar/reference/survey.md", "skills/exec-ashlar/reference/execution.md", "skills/exec-ashlar/reference/commands.md", "skills/exec-ashlar/SKILL.md", "skills/terrain-shape/reference/terrain/toolkit-api.md", "tests/ashlar/test_transit_text.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/test_transit_text.py tests/ashlar/test_skill_text.py -q", "acceptanceCriteria": ["transit{file} row in plan-format and verification", "summon kind and entity await in the tests table; test mode kills tagged test entities before releasing force-loads", "registry documents boxes and survey overlap uses them", "toolkit-api lists route, line, portal and transit-check"], "modelTier": "standard"}
```

**Steps:**

- [ ] **Step 1: Write the failing text tests**

```python
REPO = Path(__file__).resolve().parents[2]
read = lambda rel: (REPO / rel).read_text(encoding="utf-8")

def test_transit_row_is_documented():
    assert "`transit{file}`" in read("skills/exec-ashlar/reference/plan-format.md")
    text = read("skills/exec-ashlar/reference/verification.md")
    assert "`transit{file}`" in text and "terrain.py transit-check" in text

def test_tests_table_has_summon_and_entity_await():
    text = read("skills/exec-ashlar/reference/plan-format.md")
    assert "| `summon` |" in text and "`entity`" in text and "within <seconds>" in text
    assert "kill" in read("skills/exec-ashlar/SKILL.md").split("## test")[1].split("## rollback")[0]

def test_registry_boxes_are_documented_and_used_for_overlap():
    assert "`boxes`" in read("skills/exec-ashlar/reference/registry.md")
    assert "`boxes`" in read("skills/exec-ashlar/reference/survey.md")

def test_toolkit_api_lists_the_transit_commands():
    text = read("skills/terrain-shape/reference/terrain/toolkit-api.md")
    assert all(f"`{c} DESIGN" in text for c in ("route", "line", "portal", "transit-check"))
```

- [ ] **Step 2: Run and see them fail** — `$PYTEST tests/ashlar/test_transit_text.py -q` → FAIL
- [ ] **Step 3: Edit the references** per the criteria, in the house style (plain sentences, no new jargon).
- [ ] **Step 4: Run** `$PYTEST tests/ashlar/test_transit_text.py tests/ashlar/test_skill_text.py -q` → all pass
- [ ] **Step 5: Commit** — `git commit -m "docs(exec-ashlar): transit row, ride-test steps and registry boxes"`

---

### Task 13: The `system-transit` skill

**Goal:** Rewrite `system-transit` for Ashlar (skill and references), update README, TAXONOMY and CLAUDE.md, and bring the skill under the text tests and the validator.

**Files:**
- Modify: `skills/system-transit/SKILL.md`, `skills/system-transit/reference/topology.md`, `skills/system-transit/reference/nether-hub.md`, `skills/system-transit/reference/bridges-tunnels.md`, `skills/system-transit/reference/water-and-air.md`, `skills/system-transit/reference/interview.md`
- Create: `skills/system-transit/reference/lines.md`, `skills/system-transit/reference/previews-and-checks.md`
- Delete: `skills/system-transit/reference/surface-routes.md`, `skills/system-transit/reference/blueprints.md`
- Modify: `README.md`, `skills/TAXONOMY.md`, `CLAUDE.md`, `tests/ashlar/test_skill_text.py`

**Acceptance Criteria:**
- [ ] `test_skill_text.py` treats `system-transit` as an Ashlar skill and its rules pass (no Chapman tool names such as `exec-worker`, `exec-blueprint`, `exec-inspect`, `survey-site`, `mcbuilder:registry`, `continuity.py`, `level_get_mob_spawns`, `entity_summon`, `block_set_state`).
- [ ] `SKILL.md` drives `ashlar_place.py heights`, `terrain.py route --preview`, the section reads from the report, `terrain.py line --preview`, the built-list approval with `--approve-built`, `terrain.py portal`, emission, `exec-ashlar build` with separate approval, the `transit` row, the ride test and the user's ride, with labelled client lines.
- [ ] The references carry the spec's rules (topology and modes, rail rules, spawning thresholds including spawnable packed and blue ice, piers in water, portal math with the arrival spread, hubs as landings with doorways, previews, checks and verdicts). Chapman's gold-block claim appears only if the Wiki's Piglin page confirms it.
- [ ] `SKILL.md` records the line report's `boxes` in the project's registry entry, so `exec-ashlar`'s overlap check uses them.
- [ ] README, TAXONOMY and CLAUDE.md count fifteen Ashlar skills and describe `system-transit`; `node scripts/validate-plugin.mjs` passes.

**Verify:** `$PYTEST tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs` → all pass, `✓ plugin, marketplace, skills, and agents are valid`

```json:metadata
{"files": ["skills/system-transit/SKILL.md", "skills/system-transit/reference/topology.md", "skills/system-transit/reference/nether-hub.md", "skills/system-transit/reference/bridges-tunnels.md", "skills/system-transit/reference/water-and-air.md", "skills/system-transit/reference/interview.md", "skills/system-transit/reference/lines.md", "skills/system-transit/reference/previews-and-checks.md", "README.md", "skills/TAXONOMY.md", "CLAUDE.md", "tests/ashlar/test_skill_text.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["system-transit is an Ashlar skill in test_skill_text and passes its rules", "SKILL.md drives heights, route, section reads, line, approval token, portal, build, transit row and rides with labelled client lines", "references carry the spec rules; gold-block claim only if the Wiki confirms", "SKILL.md records the line report's boxes in the registry entry", "README, TAXONOMY and CLAUDE.md count fifteen Ashlar skills; validator passes"], "modelTier": "standard"}
```

**Steps:**

- [ ] **Step 1: Add `system-transit` to the Ashlar skill set in `test_skill_text.py`** and add a test that `SKILL.md` names `terrain.py route`, `terrain.py line`, `terrain.py portal`, `transit-check` and `--approve-built`. Run `$PYTEST tests/ashlar/test_skill_text.py -q` → FAIL (Chapman names, missing commands).
- [ ] **Step 2: Read the Wiki's Piglin page** (`minecraft_wiki_get_page` "Piglin", behaviour sections) to settle the gold-block claim.
- [ ] **Step 3: Rewrite the skill and references** per the criteria, mirroring `terrain-cave`'s structure (survey, design and review, approval, hand-off, after the build, non-negotiables).
- [ ] **Step 4: Update README, TAXONOMY and CLAUDE.md**; run `$PYTEST tests/ashlar/test_skill_text.py -q && node scripts/validate-plugin.mjs` → pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(system-transit): port the skill to Ashlar"`

---

### Task 14: End-to-end offline check and final verification

**Goal:** Prove a whole line offline (route, section reads, line, simulated build, transit-check), then run the full suite, ruff and the validator.

**Files:**
- Create: `tests/ashlar/terrain/test_transit_e2e.py`

**Acceptance Criteria:**
- [ ] A rail line with a bridge, a tunnel and two termini goes route → reads → line → every phase applied → `check_line` passes; removing one rail makes `continuity` fail.
- [ ] `$PYTEST tests/ashlar -q` passes; ruff reports no findings in new files and none added in changed files; the validator passes.

**Verify:** `$PYTEST tests/ashlar -q && node scripts/validate-plugin.mjs` → all pass

```json:metadata
{"files": ["tests/ashlar/terrain/test_transit_e2e.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar -q && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["route to reads to line to applied phases passes check_line, and a removed rail fails continuity", "full suite passes, ruff clean for new and changed files, validator passes"], "modelTier": "standard"}
```

**Steps:**

- [ ] **Step 1: Write the end-to-end test**

```python
def test_rail_line_end_to_end(tmp_path):
    project = _terrain_project(tmp_path)                 # heights with a valley and a hill; design rail, two termini
    design = td.load_line(project / "terrain/north-line.line.json", project)
    transit.run_route(design, project)
    r = route.load_route(project / "terrain/north-line.route.json")
    sites = _write_reads(project, r)                     # make_site over each section box from the same ground
    result = transit.emit_line(design, project, first_phase=1)
    built = _apply_phases(sites, project, result.rows)   # fills -> blocks.cells_write -> blocks.apply_writes
    assert {"bridge", "tunnel"} <= set(r.kinds)
    assert transit_checks.check_line(design, r, built)["ok"]
    broken = _remove_rail(built, r)
    report = transit_checks.check_line(design, r, broken)
    assert any(c["name"] == "continuity" and not c["ok"] for c in report["checks"])
```

- [ ] **Step 2: Run** `$PYTEST tests/ashlar/terrain/test_transit_e2e.py -q` → pass (fix the owning module if not, with a test there).
- [ ] **Step 3: Run the full suite, ruff and the validator** — `$PYTEST tests/ashlar -q`; `uvx ruff check --output-format concise` on every new file (expect no findings) and on each changed file compared with `origin/main`; `node scripts/validate-plugin.mjs`.
- [ ] **Step 4: Commit** — `git commit -m "test(transit): end-to-end offline line"`

---

## After the plan (not tasks)

- The user reviews the branch; commit and PR only on their word.
- After merge: link `system-transit` into `~/Development/Minecraft/.claude/skills` and `.agents/skills` (it is not linked today), and run the spec's live calibration rungs, each with the user's yes at the time.
