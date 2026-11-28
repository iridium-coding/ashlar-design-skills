"""Transit checks: is a line sound, projected or freshly read back.

``check_line`` runs the checks of ``CHECKS`` over per-section sites (the projected state, or
fresh reads after a build) and reports each check with up to ten failing cells. Every cell is
read from the site of the section that owns its route index, and from another site only when
the owner's site does not contain the cell (a boundary cell). A route section without a site
is an error; a cell a check needs that no site covers fails that check. Block states are compared by parsed properties, never by raw strings.

Conventions follow `track` and `structures`: the running cell of a rail is its level; a road
or path stands on the surface row ``floor(level) - 1`` (a half level adds a bottom slab at
``floor(level)``); a bridge deck lies at ``floor(level) - 1``; a bore starts at ``ceil(level)``.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType

import numpy as np

from .blocks import cell_classes, flood, full_cube, light_of, site_light
from .route import Route
from .site import (
    GROWTH,
    NATURAL,
    NETHER_NATURAL,
    Site,
    base_id,
    liquid_kind,
    natural_for,
)
from .structures import ROOM
from .track import (
    PLATFORM,
    RailCell,
    footprint,
    heading,
    inside,
    pier_ground,
    rail_cells,
    side_cell,
)
from .transit_design import LineDesign, formation_half

CHECKS = ("continuity", "support", "boosters", "clearance", "walk", "light", "deck", "seal", "grade")
MAX_CELLS = 10
Cell = tuple[int, int, int]

_RAILS = frozenset({"minecraft:rail", "minecraft:powered_rail"})
_CORNERS = frozenset({"north_east", "north_west", "south_east", "south_west"})
_ALL_NATURAL = NATURAL | NETHER_NATURAL
_AIR = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})
_SOFT = GROWTH     # growth that carries nothing
_NOT_LANTERN = frozenset({"minecraft:sea_lantern", "minecraft:jack_o_lantern"})
_PARTIAL_LAYERS = frozenset({"minecraft:snow"})
_FULL_EXTRA = frozenset({"minecraft:jack_o_lantern"})
_COLLIDES = ("_slab", "_stairs", "_fence", "_fence_gate", "_wall", "_pane", "_bars", "_trapdoor", "_door",
             "_leaves")
_NO_SPAWN = frozenset(f"minecraft:{b}" for b in (
    "bedrock", "barrier", "chorus_flower", "scaffolding", "ice", "frosted_ice"))
_SPAWN_BUG = frozenset({"minecraft:jack_o_lantern", "minecraft:redstone_lamp"})
_STAND_ON_POST = ("_fence", "_wall")    # a lantern or torch stands on the top of these as well


# ------------------------------------------------------------------ block predicates
@cache
def parse_state(state: str) -> tuple[str, Mapping[str, str]]:
    """The block id and the properties of a state; property order never matters."""
    block, _, rest = state.partition("[")
    props = dict(p.split("=", 1) for p in rest.rstrip("]").split(",") if "=" in p)
    return block, MappingProxyType(props)


def _solid(state: str, natural: frozenset[str] = _ALL_NATURAL) -> bool:
    """A full cube or natural terrain; air, liquids, plants and partial blocks are not."""
    block = base_id(state)
    if block in _AIR or block in _PARTIAL_LAYERS or liquid_kind(state) is not None:
        return False
    if block in _SOFT:
        return False
    return block in natural or block in _FULL_EXTRA or full_cube(state)


def _full_face(state: str, natural: frozenset[str]) -> bool:
    """A full cube, a ``type=top`` or ``double`` slab or ``half=top`` stairs: a rail or carpet stands on it."""
    block, props = parse_state(state)
    if block.endswith("_slab"):
        return props.get("type") in ("top", "double")
    if block.endswith("_stairs"):
        return props.get("half") == "top"
    return _solid(state, natural)


def _centre_support(state: str, natural: frozenset[str]) -> bool:
    """What a standing lantern or torch may stand on: a full face, or the top of a fence or wall post."""
    return _full_face(state, natural) or base_id(state).endswith(_STAND_ON_POST)


def _passable(state: str) -> bool:
    """Nothing the player, a cart or a boat collides with (water counts as passable, lava does not)."""
    block = base_id(state)
    if block in _AIR:
        return True
    if liquid_kind(state) is not None:
        return liquid_kind(state) == "water"
    return not (block.endswith(_COLLIDES) or _solid(state))


def _open(state: str) -> bool:
    """A cell a mob may stand in: passable and not a liquid."""
    return liquid_kind(state) is None and _passable(state)


def spawnable_floor(state: str) -> bool:
    """Whether a mob may spawn on top of `state` (Minecraft Wiki, "Mob spawning").

    The block needs a solid complete top: a full cube, a ``type=top`` or ``double`` slab,
    ``half=top`` stairs, soul sand or mud. Any glass, bedrock, barrier, trapdoors, chorus
    flowers, scaffolding, copper grates, leaves, ice and frosted ice do not count (packed ice
    and blue ice do), and neither does a block that itself emits light 14 or more. Jack
    o'lanterns and lit redstone lamps stay spawnable (a known game bug). A bottom slab or a
    carpet is not a floor.
    """
    block, props = parse_state(state)
    if block in _NO_SPAWN or block.endswith(("glass", "_trapdoor", "_leaves")) or "copper_grate" in block:
        return False
    if light_of(state) >= 14 and block not in _SPAWN_BUG:
        return False
    if block.endswith("_slab"):
        return props.get("type") in ("top", "double")
    if block.endswith("_stairs"):
        return props.get("half") == "top"
    return _solid(state)


def _walk_top(state: str) -> float | None:
    """The height above its cell floor that a walker stands at on `state`, else None."""
    block, props = parse_state(state)
    if block.endswith("_slab"):
        return 0.5 if props.get("type") == "bottom" else 1.0
    if block.endswith("_stairs"):
        return 1.0
    return 1.0 if _solid(state) else None


# ------------------------------------------------------------------ reading the sites
class _Line:
    """A design and route with the sites that cover it, and cell reads that find the right site."""

    def __init__(self, design: LineDesign, route: Route, sites: Mapping[str, Site],
                 indices: frozenset[int] | None = None) -> None:
        self.design, self.route, self.sites = design, route, sites
        self.natural = natural_for(design.dimension)
        self.n = len(route.cells)
        self.half = formation_half(design)
        self.rails: list[RailCell] = rail_cells(design, route) if design.mode == "rail" else []
        self.indices = indices                    # the route indices to check; None checks them all
        self._owners: dict[int, list[Site]] = {}
        self.uncovered: dict[Cell, None] = {}     # cells the running check needed that no site covers
        self._light: dict[int, np.ndarray] = {}

    def keep(self, i: int) -> bool:
        """Whether route index i is checked."""
        return self.indices is None or i in self.indices

    def owners(self, i: int) -> list[Site]:
        """The sites for route index i: those of the sections that hold i first, then the rest."""
        if i not in self._owners:
            own = [self.sites[s.name] for s in self.route.sections if s.start <= i <= s.end and s.name in self.sites]
            rest = [s for s in self.sites.values() if not any(s is o for o in own)]
            self._owners[i] = own + rest
        return self._owners[i]

    def site_for(self, i: int, x: int, y: int, z: int) -> Site | None:
        return next((s for s in self.owners(i) if inside(s, x, y, z)), None)

    def state(self, i: int, x: int, y: int, z: int, *, need: bool = False) -> str | None:
        """The state at a cell, or None when no site covers it (`need`: the running check fails on that)."""
        site = self.site_for(i, x, y, z)
        if site is None:
            if need:
                self.uncovered.setdefault((x, y, z))
            return None
        return site.block(x, y, z)

    def light(self, i: int, x: int, y: int, z: int) -> int | None:
        site = self.site_for(i, x, y, z)
        if site is None:
            return None
        key = id(site)
        if key not in self._light:
            self._light[key] = flood(cell_classes(site)[1], site_light(site))
        x1, y1, z1 = site.box[:3]
        return int(self._light[key][x - x1, y - y1, z - z1])

    def level_cell(self, i: int) -> int:
        """The first standing cell of index i: where a rail runs and the bore starts."""
        return math.ceil(self.route.levels[i])

    def running_y(self, i: int) -> int:
        return round(self.route.levels[i]) if self.design.mode == "rail" else math.floor(self.route.levels[i])


@dataclass
class _Outcome:
    bad: list[Cell]         # the first MAX_CELLS failing cells
    checked: int
    problem: str
    failures: int = 0
    _seen: set[Cell] | None = None
    named: list[str] | None = None      # failing cells worth naming in the detail (player blocks)

    def name(self, text: str) -> None:
        self.named = [*(self.named or []), text]

    def add(self, cell: Cell) -> None:
        if self._seen is None:
            self._seen = set()
        if cell in self._seen:
            return
        self._seen.add(cell)
        self.failures += 1
        if len(self.bad) < MAX_CELLS:
            self.bad.append(cell)


def _span(width: int) -> tuple[int, int]:
    """Offsets of a centred cross-section `width` cells wide."""
    return -((width - 1) // 2), width // 2


# ------------------------------------------------------------------ the checks
_STEPS = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}


def _rail_ends(shape: str | None) -> dict[tuple[int, int], int]:
    """The two directions a rail shape runs toward, each with how far above the rail's own y its end is.

    A flat or corner rail ends level both ways; an ascending rail's end toward its named side is
    one block up. An unknown shape has no ends.
    """
    if shape is None:
        return {}
    if shape.startswith("ascending_"):
        up = shape.removeprefix("ascending_")
        if up not in _STEPS:
            return {}
        dx, dz = _STEPS[up]
        return {(dx, dz): 1, (-dx, -dz): 0}
    names = shape.split("_")
    if len(names) != 2 or not all(n in _STEPS for n in names):
        return {}
    return {_STEPS[n]: 0 for n in names}


def _joins(a: RailCell, shape_a: str | None, b: RailCell, shape_b: str | None) -> bool:
    """Whether neighbouring rails a and b meet: each runs toward the other, their ends at one height.

    An ascending rail's upper end meets a rail one block higher, never a slope rising the other
    way (two slopes rising to a peak do not join).
    """
    step = (b.x - a.x, b.z - a.z)
    ends_a, ends_b = _rail_ends(shape_a), _rail_ends(shape_b)
    back = (-step[0], -step[1])
    if step not in ends_a or back not in ends_b:
        return False
    up_a, up_b = ends_a[step], ends_b[back]
    return a.y + up_a == b.y + up_b and not (up_a and up_b)


def _continuity(line: _Line) -> _Outcome | None:
    """Every rail is there with its planned shape, and every rail meets its neighbours on the line."""
    if line.design.mode != "rail":
        return None
    out = _Outcome([], 0, "rail cells missing, with the wrong shape or not meeting a neighbour")
    shapes: dict[int, str | None] = {}

    def shape(i: int) -> str | None:
        """The shape of the rail read at index i's planned cell, None when there is none."""
        if i not in shapes:
            rc = line.rails[i]
            state = line.state(i, rc.x, rc.y, rc.z, need=line.keep(i))
            block, props = parse_state(state) if state is not None else ("", {})
            shapes[i] = props.get("shape") if block in _RAILS else None
        return shapes[i]

    for i, rc in enumerate(line.rails):
        if not line.keep(i):
            continue
        state = line.state(i, rc.x, rc.y, rc.z, need=True)
        if state is None:
            continue
        out.checked += 1
        block, props = parse_state(state)
        if block not in _RAILS or props.get("shape") != rc.shape:
            out.add((rc.x, rc.y, rc.z))
    for i in range(line.n - 1):
        if not (line.keep(i) or line.keep(i + 1)):
            continue
        a, b = line.rails[i], line.rails[i + 1]
        if shape(i) is None or shape(i + 1) is None:
            continue                     # a missing rail is reported above
        if not _joins(a, shape(i), b, shape(i + 1)):
            for j, rc in ((i, a), (i + 1, b)):
                if line.keep(j):
                    out.add((rc.x, rc.y, rc.z))
    return out


def _corridor(line: _Line) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Column -> (route index, lowest y, highest y) of the strip beside the line where lamps and carpets stand."""
    reach = math.ceil(line.half) + 3
    strip: dict[tuple[int, int], tuple[int, int, int]] = {}
    for i in range(line.n):
        if not line.keep(i):
            continue
        base = line.level_cell(i)
        for xz in footprint(line.route, i, -reach, reach):
            first, lo, hi = strip.setdefault(xz, (i, base - 1, base + 6))
            strip[xz] = first, min(lo, base - 1), max(hi, base + 6)
    return strip


def _holds_post(state: str) -> bool:
    """What a lamp post may stand on: anything but air, a liquid or growth (a bottom slab will do)."""
    return base_id(state) not in _AIR and liquid_kind(state) is None and base_id(state) not in _SOFT


def _post_bases(line: _Line, site: Site, x: int, z: int, lo: int, hi: int) -> list[int]:
    """The y of the lowest block of every stack of lamp-post blocks in column (x, z) that reaches lo..hi."""
    posts = frozenset(line.design.palette["lamp_post"])
    out, bottom = [], None
    for rlo, rhi, state in sorted(site.columns[(x, z)]):
        if base_id(state) in posts:
            bottom = rlo if bottom is None else bottom
            if rhi >= lo and bottom <= hi and (not out or out[-1] != bottom):
                out.append(bottom)
        else:
            bottom = None
    return out


def _support(line: _Line) -> _Outcome:
    out = _Outcome([], 0, "items without a block to stand on or hang from")
    for i, rc in enumerate(line.rails):
        if not line.keep(i):
            continue
        below = line.state(i, rc.x, rc.y - 1, rc.z, need=True)
        if below is None:
            continue
        out.checked += 1
        if not _full_face(below, line.natural):
            out.add((rc.x, rc.y, rc.z))
    for (x, z), (i, lo, hi) in _corridor(line).items():
        site = next((s for s in line.owners(i) if (x, z) in s.columns), None)
        if site is None:
            continue
        for y in _post_bases(line, site, x, z, lo, hi):
            below = line.state(i, x, y - 1, z)
            if below is None:
                continue
            out.checked += 1
            if not _holds_post(below):
                out.add((x, y, z))
        for rlo, rhi, state in site.columns[(x, z)]:
            if rhi < lo or rlo > hi or not any(k in state for k in ("lantern", "torch", "carpet")):
                continue
            block, props = parse_state(state)
            lantern = block.endswith("lantern") and block not in _NOT_LANTERN
            hanging = lantern and props.get("hanging") == "true"
            torch = block.endswith("torch") and not block.endswith("wall_torch")
            standing = (lantern or torch or block.endswith("_carpet")) and not hanging
            if not (hanging or standing):
                continue
            for y in range(max(rlo, lo), min(rhi, hi) + 1):
                near = line.state(i, x, y + 1 if hanging else y - 1, z)
                if near is None:
                    continue
                out.checked += 1
                if hanging:
                    ok = base_id(near) not in _AIR
                elif block.endswith("_carpet"):
                    ok = _full_face(near, line.natural)
                else:
                    ok = _centre_support(near, line.natural)
                if not ok:
                    out.add((x, y, z))
    return out


def _boosters(line: _Line) -> _Outcome | None:
    if line.design.mode != "rail":
        return None
    out = _Outcome([], 0, "boosters without power or a redstone block, or powered rails on a corner")
    for i, rc in enumerate(line.rails):
        if not line.keep(i):
            continue
        state = line.state(i, rc.x, rc.y, rc.z, need=True)
        if state is None:
            continue
        block, props = parse_state(state)
        if block == "minecraft:powered_rail" and props.get("shape") in _CORNERS:
            out.add((rc.x, rc.y, rc.z))
        if not rc.booster:
            continue
        out.checked += 1
        below = line.state(i, rc.x, rc.y - 1, rc.z, need=True)
        if block != "minecraft:powered_rail" or props.get("powered") != "true" or (
                below is not None and base_id(below) != "minecraft:redstone_block"):
            out.add((rc.x, rc.y, rc.z))
    return out


def _clearance(line: _Line) -> _Outcome:
    out = _Outcome([], 0, "cells blocked in the way")
    rail = line.design.mode == "rail"
    for i, (x, z) in enumerate(line.route.cells):
        if not line.keep(i):
            continue
        level = line.route.levels[i]
        base = line.running_y(i)
        half = not rail and level != base
        for y in range(base + 1, base + 3) if rail else range(base, base + 3):
            state = line.state(i, x, y, z, need=True)
            if state is None:
                continue
            out.checked += 1
            block, props = parse_state(state)
            if y == base and half and block.endswith("_slab") and props.get("type") == "bottom":
                continue
            if not _passable(state):
                out.add((x, y, z))
                if block not in line.natural and len(out.named or []) < MAX_CELLS:
                    out.name(f"player block {block} at ({x}, {y}, {z})")
    return out


def _surface(line: _Line, i: int, x: int, z: int) -> float | None:
    """The walking height at (x, z): the first walkable top from floor(level) + 1 down three rows.

    ``nan`` when the site does not cover the column, None when nothing there is walkable.
    """
    base = math.floor(line.route.levels[i])
    for y in range(base + 1, base - 4, -1):
        state = line.state(i, x, y, z, need=True)
        if state is None:
            return math.nan
        top = _walk_top(state)
        if top is not None:
            return y + top
    return None


def _walk_span(design: LineDesign) -> tuple[int, int]:
    return _span(4 * design.lanes) if design.mode == "road" else (0, 0)


def _walk(line: _Line) -> _Outcome | None:
    if line.design.mode not in ("road", "path"):
        return None
    road = line.design.mode == "road"
    limit = 0.5 if road else 1.0
    lo, hi = _walk_span(line.design)
    out = _Outcome([], 0, f"steps of more than {limit:g} between neighbouring surface cells")
    heights: dict[tuple[int, int], float | None] = {}

    def height(i: int, off: int) -> tuple[Cell, float | None]:
        x, z = side_cell(line.route, i, off)
        if (i, off) not in heights:
            heights[i, off] = _surface(line, i, x, z)
        h = heights[i, off]
        cell = (x, (math.ceil(h) - 1) if h is not None and not math.isnan(h) else math.floor(line.route.levels[i]) - 1, z)
        return cell, h

    for i in range(line.n):
        if not line.keep(i):
            continue
        for off in range(lo, hi + 1):
            here, h = height(i, off)
            if h is not None and math.isnan(h):
                continue
            if h is None:
                out.checked += 1
                out.add(here)
                continue
            for j, o in ((i, off + 1), (i + 1, off)):
                if j >= line.n or o > hi or not line.keep(j):
                    continue
                there, g = height(j, o)
                if g is None or math.isnan(g):
                    continue
                out.checked += 1
                if abs(h - g) > limit:
                    out.add(here if h >= g else there)
    return out


def _lit_cells(line: _Line) -> list[tuple[int, Cell]]:
    """(route index, cell) of every open cell above the floors that need light, in route order."""
    design, route = line.design, line.route
    cells: dict[Cell, int] = {}
    # The formation is every offset within formation_half of the centreline (1 each side for a
    # rail or a 3-wide path); a bridge uses its deck width, a bore its bore width. The terminus
    # platform follows `structures`: 2 wide, its inner edge at -(ceil(formation_half) - 1).
    lo_f, hi_f = -int(line.half), int(line.half)
    deck = _span(round(2 * line.half) + 2)
    bore = _span(design.tunnels.width)
    for i in range(line.n):
        if not line.keep(i):
            continue
        lo, hi = bore if route.kinds[i] in ("tunnel", "tube") else deck if route.kinds[i] == "bridge" else (lo_f, hi_f)
        y = line.level_cell(i)
        for x, z in footprint(route, i, lo, hi):
            cells.setdefault((x, y, z), i)
    width, length = PLATFORM
    edge = -(math.ceil(line.half) - 1)
    for end, stop in ((False, design.start.stop), (True, design.end.stop)):
        i = line.n - 1 if end else 0
        if stop == "terminus":
            for j in range(line.n - length, line.n) if end else range(length):
                if 0 <= j < line.n and line.keep(j):
                    for x, z in footprint(route, j, edge - width + 1, edge):
                        cells.setdefault((x, line.level_cell(j) + 1, z), j)
        elif stop == "room" and line.keep(i):
            for c in _room_cells(line, i, end)[0]:
                cells.setdefault(c, i)
    return sorted(((i, c) for c, i in cells.items()), key=lambda t: t[0])


def _room_cells(line: _Line, i: int, end: bool) -> tuple[list[Cell], list[Cell]]:
    """The floor row of the room around end cell i, and every air cell of its bore (5 x 4 x 5)."""
    width, height, length = ROOM
    hx, hz = heading(line.route, i)
    out = (hx, hz) if end else (-hx, -hz)
    dx, dz = (out[0], 0) if out[0] else (0, out[1])
    px, pz = -dz, dx
    x0, z0 = line.route.cells[i]
    base = line.level_cell(i)
    floor_row, bore = [], []
    for t in range(-(length // 2), length // 2 + 1):
        for s in range(-(width // 2), width // 2 + 1):
            x, z = x0 + t * dx + s * px, z0 + t * dz + s * pz
            floor_row.append((x, base, z))
            bore += [(x, y, z) for y in range(base, base + height)]
    return floor_row, bore


def _light(line: _Line) -> _Outcome:
    minimum = line.design.lights.minimum
    out = _Outcome([], 0, f"floor cells with block light below {minimum}")
    for i, (x, y, z) in _lit_cells(line):
        cell, below = line.state(i, x, y, z, need=True), line.state(i, x, y - 1, z, need=True)
        if cell is None or below is None or base_id(cell) in _RAILS or not _open(cell):
            continue
        if not spawnable_floor(below):
            continue
        value = line.light(i, x, y, z)
        if value is None:
            continue
        out.checked += 1
        if value < minimum:
            out.add((x, y, z))
    return out


def _deck(line: _Line) -> _Outcome | None:
    route = line.route
    bridge = [i for i in range(line.n) if route.kinds[i] == "bridge" and line.keep(i)]
    if not bridge:
        return None
    piers = frozenset(line.design.palette["pier"])
    out = _Outcome([], 0, "bridge cells with no pier reaching ground close enough")
    column: dict[int, list[Cell]] = {}
    grounded: set[Cell] = set()
    for i in bridge:
        x, z = route.cells[i]
        top = math.floor(route.levels[i]) - 2
        cells, y = [], top
        line.state(i, x, top, z, need=True)
        while (state := line.state(i, x, y, z)) is not None and base_id(state) in piers:
            cells.append((x, y, z))
            y -= 1
        column[i] = cells
        below = line.state(i, x, y, z)
        if below is not None and pier_ground(below, line.design.dimension):
            grounded.update(cells or [(x, top, z)])
    reach = line.design.bridges.pier_spacing // 2 + 1
    # Arch fill reaches ground through the fill beside it: grow the grounded set across touching pier cells.
    cells_at = {c: i for i, cs in column.items() for c in cs}
    frontier = [c for c in grounded if c in cells_at]
    while frontier:
        x, y, z = frontier.pop()
        i = cells_at[x, y, z]
        for j in (i - 1, i + 1):
            if j in column:
                x2, z2 = route.cells[j]
                if (x2, y, z2) in cells_at and (x2, y, z2) not in grounded:
                    grounded.add((x2, y, z2))
                    frontier.append((x2, y, z2))
    supported = {i for i in bridge if any(c in grounded for c in column[i])
                 or (not column[i] and (route.cells[i][0], math.floor(route.levels[i]) - 2, route.cells[i][1]) in grounded)}
    for i in bridge:
        x, z = route.cells[i]
        out.checked += 1
        if not any(j in supported for j in range(i - reach, i + reach + 1)):
            out.add((x, math.floor(route.levels[i]) - 1, z))
    return out


def _bores(line: _Line) -> list[tuple[int, Cell]]:
    """(route index, cell) of every bore, tube and room cell."""
    design, route = line.design, line.route
    lo, hi = _span(design.tunnels.width)
    out: list[tuple[int, Cell]] = []
    for i in range(line.n):
        if route.kinds[i] in ("tunnel", "tube") and line.keep(i):
            base = line.level_cell(i)
            out += [(i, (x, y, z)) for x, z in footprint(route, i, lo, hi)
                    for y in range(base, base + design.tunnels.height)]
    for end, stop in ((False, design.start.stop), (True, design.end.stop)):
        i = line.n - 1 if end else 0
        if stop == "room" and line.keep(i):
            out += [(i, c) for c in _room_cells(line, i, end)[1]]
    return out


def _seal(line: _Line) -> _Outcome | None:
    bores = _bores(line)
    if not bores:
        return None
    out = _Outcome([], 0, "liquid cells touching a bore or room")
    for i, (x, y, z) in bores:
        state = line.state(i, x, y, z, need=True)
        if state is None:
            continue
        out.checked += 1
        if liquid_kind(state) is not None:
            out.add((x, y, z))
        if not _passable(state):
            continue
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            near = line.state(i, x + dx, y + dy, z + dz)
            if near is not None and liquid_kind(near) is not None:
                out.add((x + dx, y + dy, z + dz))
    return out


def _grade(line: _Line) -> _Outcome:
    design, route = line.design, line.route
    out = _Outcome([], 0, "cells off their level")
    for i, (x, z) in enumerate(route.cells):
        if not line.keep(i):
            continue
        level = route.levels[i]
        if design.mode == "rail":
            want = line.rails[i].y
            line.state(i, x, want, z, need=True)
            found = [y for y in range(want - 3, want + 4)
                     if (s := line.state(i, x, y, z)) is not None and base_id(s) in _RAILS]
            if found:
                out.checked += 1
                if want not in found:
                    out.add((x, found[0], z))
        elif design.mode == "ice":
            ice = frozenset(design.palette["ice"])
            y = math.floor(level) - 1
            for gx, gz in footprint(route, i, 0, 1):
                state = line.state(i, gx, y, gz, need=True)
                if state is not None:
                    out.checked += 1
                    if base_id(state) not in ice:
                        out.add((gx, y, gz))
        else:
            h = _surface(line, i, x, z)
            if h is not None and math.isnan(h):
                continue
            out.checked += 1
            if h is None or abs(h - level) > 0.5:
                out.add((x, (math.ceil(h) - 1) if h is not None else math.floor(level) - 1, z))
    return out


_RUN: dict[str, Callable[[_Line], _Outcome | None]] = {
    "continuity": _continuity, "support": _support, "boosters": _boosters, "clearance": _clearance,
    "walk": _walk, "light": _light, "deck": _deck, "seal": _seal, "grade": _grade}


def check_line(design: LineDesign, route: Route, sites: Mapping[str, Site], *,
               sections: Collection[str] | None = None, checks: Collection[str] | None = None) -> dict:
    """Run the checks over per-section sites; the result is ``{"ok", "checks": [...]}``.

    Each check is ``{"name", "ok", "detail", "cells"}`` with up to ten failing cells as ``[x, y, z]``.
    Checks that do not apply to the mode, or find nothing to check on this route, are left out.
    A cell a check needs that no site covers fails that check. `sections` (names) limits the run
    to those route sections: only their sites are required and only their route indices are
    checked, with cells still read from any site that covers them. None checks every section.
    `checks` (names from ``CHECKS``) runs only those checks, in ``CHECKS`` order; None runs all.

    Raises:
        ValueError: when a checked route section has no entry in `sites`, or `sections` names a
            section the route does not have, or `checks` names a check that does not exist.
    """
    if checks is not None:
        unknown = sorted(set(checks) - set(CHECKS))
        if unknown:
            raise ValueError(f"no check named {', '.join(unknown)} (checks: {', '.join(CHECKS)})")
    if sections is not None:
        unknown = sorted(set(sections) - {s.name for s in route.sections})
        if unknown:
            raise ValueError(f"no route section {', '.join(unknown)}")
    checked = [s for s in route.sections if sections is None or s.name in sections]
    missing = [s.name for s in checked if s.name not in sites]
    if missing:
        raise ValueError(f"no site for section {', '.join(missing)}")
    indices = None if sections is None else frozenset(i for s in checked for i in range(s.start, s.end + 1))
    line = _Line(design, route, sites, indices)
    results = []
    for name in CHECKS if checks is None else [c for c in CHECKS if c in checks]:
        line.uncovered = {}
        outcome = _RUN[name](line)
        if outcome is None:
            continue
        gaps = list(line.uncovered)
        parts = []
        if outcome.failures:
            named = f", among them {'; '.join(outcome.named)}" if outcome.named else ""
            parts.append(f"{outcome.failures} of {outcome.checked}: {outcome.problem}{named}")
        if gaps:
            parts.append(f"{len(gaps)} cells not covered by any site")
        cells = [*outcome.bad, *gaps][:MAX_CELLS]
        results.append({"name": name, "ok": not parts, "detail": "; ".join(parts) or f"{outcome.checked} checked",
                        "cells": [list(c) for c in cells]})
    return {"ok": all(c["ok"] for c in results), "checks": results}
