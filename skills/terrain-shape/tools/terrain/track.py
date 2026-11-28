"""Track: the running surface along a planned route.

``rail_cells`` turns a rail route into exact rail cells (shape and booster flag for every
cell of the whole line); ``track_layers`` writes one section as live layers in order:
``carve`` (clearance), ``build`` (bed and boosters' redstone blocks), ``track`` (rails, or
the road, path or ice surface) and ``light`` (lamps). Ashlar places blocks with no game
physics, so every rail shape and every powered rail's state is written exactly.

Conventions. Offsets across the line use the local travel direction (the outgoing leg; a
corner cell uses both legs, so its bed is the full 3 x 3). With travel along +x, offset +1 is
z + 1. Road and path surfaces span offsets ``-((w - 1) // 2) .. w // 2`` for width ``w``; the
ice lane is offsets 0 and +1 with guards at -1 and +2.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .blocks import cells_write, full_cube
from .live import LiveWrite
from .route import TERMINUS_CELLS, Route, Section
from .site import (
    _AIR,
    _LAVA,
    GROWTH,
    NATURAL,
    TRUNK,
    Site,
    base_id,
    is_water_state,
    liquid_kind,
    natural_for,
)
from .transit_design import LineDesign, formation_half

Cell = tuple[int, int, int]

_DIRS = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}
AIR = "minecraft:air"
REDSTONE_BLOCK = "minecraft:redstone_block"
BED_KINDS = ("grade", "cut", "fill", "tunnel")
LIT_KINDS = ("grade", "cut", "fill")
TERMINUS_QUIET = 8      # cells next to a terminus end without boosters
LAUNCH = (TERMINUS_QUIET, TERMINUS_CELLS)   # launch group: the 9th to 11th cells from a terminus end
CLEARANCE = 3
POST_REACH = 6          # a lamp post reaches at most this many cells down to the ground
PLATFORM = (2, 8)       # width and length of a terminus platform
_SALT = {"ballast": 1, "surface": 2, "edge": 3, "guard": 4, "lamp_post": 5, "lamp": 6, "end_block": 7,
         "ice": 8, "width": 9, "deck": 10, "pier": 11, "lining": 12, "railing": 13, "platform": 14}


@dataclass(frozen=True)
class RailCell:
    x: int
    y: int
    z: int
    shape: str
    booster: bool


# ------------------------------------------------------------------ rail shapes
def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _toward(a: tuple[int, int, float], b: tuple[int, int, float]) -> str:
    try:
        return _DIRS[(_sign(b[0] - a[0]), _sign(b[1] - a[1]))]
    except KeyError:
        raise ValueError(f"rail cells must be axis neighbours, got {a[:2]} and {b[:2]}") from None


def _facing(a: tuple[int, int], b: tuple[int, int]) -> str:
    """The compass direction from a to b along the dominant axis of the step (x on a tie)."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dz):
        return "east" if dx > 0 else "west"
    return "south" if dz > 0 else "north"


def _one_higher(neighbour: tuple[int, int, float] | None, cell: tuple[int, int, float]) -> bool:
    return neighbour is not None and abs(neighbour[2] - cell[2] - 1) < 1e-9


def rail_shape(prev: tuple[int, int, float] | None, cell: tuple[int, int, float],
               nxt: tuple[int, int, float] | None) -> str:
    """The rail shape of `cell` (x, z, level) between its neighbours on the line.

    A rise to the next cell ascends toward it, else a rise behind ascends toward the previous
    cell; otherwise the neighbours decide: both on one axis is straight, one on each a corner.
    """
    if _one_higher(nxt, cell):
        return f"ascending_{_toward(cell, nxt)}"
    if _one_higher(prev, cell):
        return f"ascending_{_toward(cell, prev)}"
    names = {_toward(cell, n) for n in (prev, nxt) if n is not None}
    x_side, z_side = names & {"east", "west"}, names & {"north", "south"}
    if x_side and z_side:
        return f"{z_side.pop()}_{x_side.pop()}"
    return "north_south" if z_side else "east_west"


def _slope(levels: list[float], i: int) -> bool:
    return any(0 <= j < len(levels) and levels[j] != levels[i] for j in (i - 1, i + 1))


def rail_cells(design: LineDesign, route: Route) -> list[RailCell]:
    """Every rail cell of the whole line with its exact shape and booster flag."""
    cells, levels, n = route.cells, route.levels, len(route.cells)
    corners = set(route.corners)
    quiet: set[int] = set()
    launch: set[int] = set()
    if design.start.stop == "terminus":
        quiet |= set(range(TERMINUS_QUIET))
        launch |= set(range(*LAUNCH))
    if design.end.stop == "terminus":
        quiet |= set(range(n - TERMINUS_QUIET, n))
        launch |= set(range(n - LAUNCH[1], n - LAUNCH[0]))
    out = []
    for i, (x, z) in enumerate(cells):
        prev = (*cells[i - 1], levels[i - 1]) if i > 0 else None
        nxt = (*cells[i + 1], levels[i + 1]) if i < n - 1 else None
        step = design.boosters.slope if _slope(levels, i) else design.boosters.flat
        wanted = i in launch or i % step == 0
        booster = wanted and i not in quiet and i not in corners
        out.append(RailCell(x, round(levels[i]), z, rail_shape(prev, (x, z, levels[i]), nxt), booster))
    return out


def _rail_state(cell: RailCell) -> str:
    if cell.booster:
        return f"minecraft:powered_rail[powered=true,shape={cell.shape}]"
    return f"minecraft:rail[shape={cell.shape}]"


def rail_set(design: LineDesign, route: Route) -> frozenset[Cell]:
    """Every rail cell of the whole line: no lining, railing, lamp or carve of any section replaces one."""
    if design.mode != "rail":
        return frozenset()
    return frozenset((c.x, c.y, c.z) for c in rail_cells(design, route))


def pier_ground(state: str, dimension: str) -> bool:
    """Whether a block is ground a pier or a lamp post stands on in `dimension`.

    A full cube, or a natural block of the dimension, that is not air, a liquid, a plant, a
    tree or another growth (vines, roots, lichen, cobweb, dripstone).
    """
    block = base_id(state)
    if block in _AIR or liquid_kind(state) is not None or block in GROWTH or block in TRUNK:
        return False
    return block in natural_for(dimension) or full_cube(state)


def platform_cells(design: LineDesign, route: Route, end: bool) -> list[tuple[int, int, int, bool]]:
    """(route index, x, z, on the outer edge) of the platform of a terminus at the line's start or end.

    The platform is ``PLATFORM`` 2 wide and 8 long on the left of travel, its inner edge at
    offset ``-(ceil(formation_half) - 1)``.
    """
    n = len(route.cells)
    width, length = PLATFORM
    edge = -(math.ceil(formation_half(design)) - 1)
    indices = range(n - length, n) if end else range(length)
    return [(j, *side_cell(route, j, off), off == edge - width + 1) for j in indices if 0 <= j < n
            for off in range(edge - width + 1, edge + 1)]


def platform_columns(design: LineDesign, route: Route) -> set[tuple[int, int]]:
    """The columns of every terminus platform of the line: the stop lights them, not the line's lamps."""
    return {(x, z) for end, stop in ((False, design.start.stop), (True, design.end.stop)) if stop == "terminus"
            for _, x, z, _ in platform_cells(design, route, end)}


def keeps_built(design: LineDesign, site: Site) -> Callable[[Cell], bool]:
    """Whether a bed, surface or shell cell is left as it is: a line with an ``open`` stop ends at
    something built (a landing doorway), and writes no bed, surface or shell where the read holds a
    block that is not natural."""
    if "open" not in (design.start.stop, design.end.stop):
        return lambda cell: False
    natural = natural_for(design.dimension)

    def kept(cell: Cell) -> bool:
        return inside(site, *cell) and base_id(site.block(*cell)) not in natural

    return kept


# ------------------------------------------------------------------ helpers
def heading(route: Route, i: int, *, incoming: bool = False) -> tuple[int, int]:
    cells = route.cells
    if len(cells) < 2:
        return (1, 0)
    a, b = (cells[i - 1], cells[i]) if incoming or i == len(cells) - 1 else (cells[i], cells[i + 1])
    return (_sign(b[0] - a[0]), _sign(b[1] - a[1]))


def _cross(x: int, z: int, heading: tuple[int, int], lo: int, hi: int) -> set[tuple[int, int]]:
    """Cells at offsets lo..hi across `heading`; a diagonal heading takes both axis cross-sections."""
    axes = [heading] if 0 in heading else [(heading[0], 0), (0, heading[1])]
    return {(x - dz * off, z + dx * off) for dx, dz in axes for off in range(lo, hi + 1)}


def footprint(route: Route, i: int, lo: int, hi: int) -> set[tuple[int, int]]:
    """Cells at offsets lo..hi across the line at cell i.

    Where the heading changes (a corner or a bend) the incoming and outgoing cross-sections
    are joined and the rectangle they span is filled, so the outer wedge is not left empty.
    """
    x, z = route.cells[i]
    out = heading(route, i)
    cells = _cross(x, z, out, lo, hi)
    if i > 0 and heading(route, i, incoming=True) != out:
        cells |= _cross(x, z, heading(route, i, incoming=True), lo, hi)
        xs, zs = [c[0] for c in cells], [c[1] for c in cells]
        cells = {(a, b) for a in range(min(xs), max(xs) + 1) for b in range(min(zs), max(zs) + 1)}
    return cells


def side_cell(route: Route, i: int, offset: int) -> tuple[int, int]:
    x, z = route.cells[i]
    dx, dz = heading(route, i)
    return x - dz * offset, z + dx * offset


def pick(design: LineDesign, role: str, *key: int) -> str:
    """A weighted block of `role`, fixed by the design seed and `key` (world coordinates)."""
    weights = design.palette[role]
    names = list(weights)
    if len(names) == 1:
        return names[0]
    rng = np.random.default_rng([design.seed % 2**32, _SALT[role], *(k % 2**32 for k in key)])
    p = np.array(list(weights.values()), dtype=float)
    return names[int(rng.choice(len(names), p=p / p.sum()))]


def _variant(block: str, suffix: str) -> str:
    """The slab or stairs of a full block, a wall or a fence: stone_bricks -> stone_brick_slab."""
    name = base_id(block).removeprefix("minecraft:").removesuffix("_wall").removesuffix("_fence")
    if name.endswith("_planks"):
        name = name.removesuffix("_planks")
    elif name.endswith("bricks"):
        name = name.removesuffix("s")
    return f"minecraft:{name}{suffix}"


def slab(block: str) -> str:
    return f"{_variant(block, '_slab')}[type=bottom,waterlogged=false]"


def _stairs(block: str, facing: str) -> str:
    return f"{_variant(block, '_stairs')}[facing={facing},half=bottom,shape=straight,waterlogged=false]"


def inside(site: Site, x: int, y: int, z: int) -> bool:
    x1, y1, z1, x2, y2, z2 = site.box
    return x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2


def carvable(state: str, natural: frozenset[str] = NATURAL) -> bool:
    block = base_id(state)
    return block in natural and block not in _AIR and block not in _LAVA and not is_water_state(state)


def _carve(site: Site, columns: dict[tuple[int, int], int], height: int = CLEARANCE, *,
           natural: frozenset[str] = NATURAL, rails: frozenset[Cell] = frozenset()) -> dict:
    """Air for the natural, non-liquid blocks `height` cells up from each column's lowest y, never on `rails`."""
    out = {}
    for (x, z), y0 in columns.items():
        for y in range(y0, y0 + height):
            if (x, y, z) not in rails and inside(site, x, y, z) and carvable(site.block(x, y, z), natural):
                out[(x, y, z)] = AIR
    return out


def _lower(columns: dict[tuple[int, int], int], x: int, z: int, y: int) -> None:
    columns[(x, z)] = min(columns.get((x, z), y), y)


def live_layers(site: Site, **layers: dict) -> list[tuple[str, LiveWrite]]:
    """Live writes of the named cell maps, clipped to the site and without the empty ones."""
    out = []
    for name, cells in layers.items():
        write = cells_write({c: s for c, s in cells.items() if inside(site, *c)})
        if write is not None:
            out.append((name, write))
    return out


def lamp_column(design: LineDesign, cell: tuple[int, int], base: int,
                out: dict[tuple[int, int, int], str], bottom: int | None = None) -> None:
    """A lamp post from `bottom` (default `base`) up to ``base + 1`` with the lamp on top."""
    x, z = cell
    for y in range(base if bottom is None else bottom, base + 2):
        out[(x, y, z)] = pick(design, "lamp_post", x, y, z)
    out[(x, base + 2, z)] = pick(design, "lamp", x, base + 2, z)


def post_column(design: LineDesign, site: Site, cell: tuple[int, int], base: int,
                out: dict[tuple[int, int, int], str], laid: dict[Cell, str]) -> bool:
    """A lamp column beside the line, its post reaching down to the ground.

    The post runs from the first block below `base` it can stand on up to ``base + 1``, the lamp
    on top: a block the line itself lays there (`laid`, such as a kerb slab), else ground in the
    site (`pier_ground`), at most ``POST_REACH`` below. Nothing is written, and False returned,
    when there is no such block that close.
    """
    x, z = cell
    for y in range(base - 1, base - POST_REACH - 1, -1):
        state = laid.get((x, y, z))
        if state is None and not inside(site, x, y, z):
            break
        if (state is not None and base_id(state) not in _AIR) or (
                state is None and pier_ground(site.block(x, y, z), design.dimension)):
            lamp_column(design, cell, base, out, bottom=y + 1)
            return True
    return False


def _lights(design: LineDesign, route: Route, section: Section, site: Site, spacing: int, lo: int, hi: int,
            base: Callable[[int], int], kinds: tuple[str, ...], out: dict[tuple[int, int, int], str],
            laid: dict[Cell, str], skipped: list[Cell] | None) -> None:
    """Lamp posts every `spacing` cells just outside offsets lo..hi, alternating sides.

    No lamp stands on the line's formation or on a terminus platform (the stop lights it); a
    lamp whose post finds nothing to stand on close below is left out and added to `skipped`.
    """
    n = len(route.cells)
    platform = platform_columns(design, route)
    for i in range(section.start, section.end + 1):
        if i % spacing or route.kinds[i] not in kinds:
            continue
        side = lo - 1 if (i // spacing) % 2 else hi + 1
        cell = side_cell(route, i, side)
        near = set().union(*(footprint(route, j, lo, hi) for j in range(max(0, i - 3), min(n, i + 4))))
        if cell not in near and cell not in platform and not post_column(design, site, cell, base(i), out, laid) \
                and skipped is not None:
            skipped.append((cell[0], base(i) + 2, cell[1]))


# ------------------------------------------------------------------ rail
def _bed(design: LineDesign, site: Site, x: int, y: int, z: int) -> str:
    """The ballast of a bed cell, or the lining role where the cell below is no ground (a cave): no gravel falls."""
    if inside(site, x, y - 1, z) and not pier_ground(site.block(x, y - 1, z), design.dimension):
        return pick(design, "lining", x, y, z)
    return pick(design, "ballast", x, y, z)


def _rail(design: LineDesign, route: Route, section: Section, site: Site, spacing: int,
          skipped: list[Cell] | None):
    rails = rail_cells(design, route)
    kept = keeps_built(design, site)
    carve_at: dict[tuple[int, int], int] = {}
    build: dict[tuple[int, int, int], str] = {}
    power: dict[tuple[int, int, int], str] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in range(section.start, section.end + 1):
        rc = rails[i]
        foot = footprint(route, i, -1, 1)
        for x, z in foot:
            _lower(carve_at, x, z, rc.y + 1)
            if route.kinds[i] in BED_KINDS and not kept((x, rc.y - 1, z)):
                build[(x, rc.y - 1, z)] = _bed(design, site, x, rc.y - 1, z)
        if rc.booster:
            power[(rc.x, rc.y - 1, rc.z)] = REDSTONE_BLOCK
        track[(rc.x, rc.y, rc.z)] = _rail_state(rc)
    light: dict[tuple[int, int, int], str] = {}
    _lights(design, route, section, site, spacing, -1, 1, lambda i: rails[i].y, LIT_KINDS, light,
            {**build, **track}, skipped)
    build.update(power)     # every bed first, so no ballast replaces a booster's redstone block
    natural = natural_for(design.dimension)
    carve = _carve(site, carve_at, natural=natural, rails=rail_set(design, route))
    return live_layers(site, carve=carve, build=build, track=track, light=light)


# ------------------------------------------------------------------ road
def _road(design: LineDesign, route: Route, section: Section, site: Site, spacing: int,
          skipped: list[Cell] | None):
    kept = keeps_built(design, site)
    width = 4 * design.lanes
    lo, hi = -((width - 1) // 2), width // 2
    idx = range(section.start, section.end + 1)
    surfaced = [i for i in idx if route.kinds[i] in BED_KINDS]
    road_cells = set().union(*(footprint(route, i, lo, hi) for i in idx))
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = route.levels[i]
        top = int(np.ceil(level))
        for x, z in footprint(route, i, lo - 1, hi + 1):
            _lower(carve_at, x, z, top)
    for i in surfaced:
        base = int(np.floor(route.levels[i]))
        half = route.levels[i] != base
        for x, z in footprint(route, i, lo - 1, hi + 1) - road_cells:
            track[(x, base - 1, z)] = pick(design, "surface", x, base - 1, z)
            track[(x, base, z)] = (pick(design, "surface", x, base, z) if half
                                   else f"{pick(design, 'edge', x, base, z)}[type=bottom,waterlogged=false]")
    for i in surfaced:
        base = int(np.floor(route.levels[i]))
        for x, z in footprint(route, i, lo, hi):
            block = pick(design, "surface", x, base - 1, z)
            track[(x, base - 1, z)] = block
            if route.levels[i] != base:
                track[(x, base, z)] = slab(block)
    track = {c: v for c, v in track.items() if not kept(c)}
    light: dict[tuple[int, int, int], str] = {}
    _lights(design, route, section, site, spacing, lo, hi, lambda i: int(np.floor(route.levels[i])) + 1,
            LIT_KINDS, light, track, skipped)
    natural = natural_for(design.dimension)
    return live_layers(site, carve=_carve(site, carve_at, natural=natural), track=track, light=light)


# ------------------------------------------------------------------ path
def _path_span(design: LineDesign, i: int) -> tuple[int, int]:
    """Offsets of the path at cell i: the design width plus or minus one, in runs of three cells."""
    rng = np.random.default_rng([design.seed % 2**32, _SALT["width"], i // 3])
    width = max(1, design.width + int(rng.integers(-1, 2)))
    return -((width - 1) // 2), width // 2


def _path(design: LineDesign, route: Route, section: Section, site: Site, spacing: int,
          skipped: list[Cell] | None):
    kept = keeps_built(design, site)
    idx = range(section.start, section.end + 1)
    spans = {i: _path_span(design, i) for i in range(max(0, section.start - 3), min(len(route.cells), section.end + 4))}
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = int(route.levels[i])
        for x, z in footprint(route, i, *spans[i]):
            _lower(carve_at, x, z, level)
            if route.kinds[i] in BED_KINDS and not kept((x, level - 1, z)):
                track[(x, level - 1, z)] = pick(design, "surface", x, level - 1, z)
    for i in idx:
        if route.kinds[i] not in BED_KINDS:
            continue
        level = int(route.levels[i])
        for j in (i - 1, i + 1):
            if 0 <= j < len(route.cells) and int(route.levels[j]) == level - 1:
                facing = _facing(route.cells[j], route.cells[i])
                for x, z in footprint(route, i, *spans[i]):
                    cell = (x, level - 1, z)
                    if cell in track and not base_id(track[cell]).endswith("_stairs"):
                        track[cell] = _stairs(track[cell], facing)
                break
    light: dict[tuple[int, int, int], str] = {}
    platform = platform_columns(design, route)
    for i in idx:
        if i % spacing or route.kinds[i] not in LIT_KINDS:
            continue
        lo, hi = spans[i]
        cell = side_cell(route, i, lo - 1 if (i // spacing) % 2 else hi + 1)
        near = set().union(*(footprint(route, j, *spans[j]) for j in spans if abs(j - i) <= 3))
        level = int(route.levels[i])
        if cell not in near and cell not in platform and not post_column(design, site, cell, level, light, track) \
                and skipped is not None:
            skipped.append((cell[0], level + 2, cell[1]))
    natural = natural_for(design.dimension)
    return live_layers(site, carve=_carve(site, carve_at, natural=natural), track=track, light=light)


# ------------------------------------------------------------------ ice
def _ice(design: LineDesign, route: Route, section: Section, site: Site, spacing: int,
         skipped: list[Cell] | None):
    kept = keeps_built(design, site)
    idx = range(section.start, section.end + 1)
    lane = set().union(*(footprint(route, i, 0, 1) for i in idx))
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    light: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = int(route.levels[i])
        for x, z in footprint(route, i, -1, 2):
            _lower(carve_at, x, z, level)
        for x, z in footprint(route, i, 0, 1):
            track[(x, level - 1, z)] = pick(design, "ice", x, level - 1, z)
        for x, z in footprint(route, i, -1, 2) - lane:
            track[(x, level, z)] = slab(pick(design, "guard", x, level, z))
    for i in idx:
        if i % spacing:
            continue
        level = int(route.levels[i])
        x, z = side_cell(route, i, 2 if (i // spacing) % 2 else -1)
        if (x, z) not in lane:
            light[(x, level, z)] = design.lights.block
    track = {c: v for c, v in track.items() if not kept(c)}
    natural = natural_for(design.dimension)
    return live_layers(site, carve=_carve(site, carve_at, CLEARANCE + 1, natural=natural), track=track, light=light)


_MODES = {"rail": _rail, "road": _road, "path": _path, "ice": _ice}


def track_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                 light_spacing: int | None = None, skipped: list[Cell] | None = None) -> list[tuple[str, LiveWrite]]:
    """Live layers for the cells of `section`, in order, omitting empty ones.

    Returns ``("carve", clearance)``, ``("build", bed)``, ``("track", rails or surface)`` and
    ``("light", lamps)``. `light_spacing` ``None`` means ``design.lights.spacing``. A lamp post
    beside the line reaches down to the ground (at most ``POST_REACH``); a lamp with no ground
    that close is left out and its lamp cell added to `skipped` when given.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    return _MODES[design.mode](design, route, section, site, spacing, skipped)
