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

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .blocks import cells_write
from .live import LiveWrite
from .route import Route, Section
from .site import _AIR, _LAVA, NATURAL, Site, base_id, is_water_state
from .transit_design import LineDesign

_DIRS = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}
AIR = "minecraft:air"
REDSTONE_BLOCK = "minecraft:redstone_block"
BED_KINDS = ("grade", "cut", "fill", "tunnel")
LIT_KINDS = ("grade", "cut", "fill")
TERMINUS_QUIET = 8      # cells next to a terminus end without boosters
LAUNCH = (8, 11)        # launch group: the 9th to 11th cells from a terminus end
CLEARANCE = 3
_SALT = {"ballast": 1, "surface": 2, "edge": 3, "guard": 4, "lamp_post": 5, "lamp": 6, "end_block": 7,
         "ice": 8, "width": 9}


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


# ------------------------------------------------------------------ helpers
def _heading(route: Route, i: int, *, incoming: bool = False) -> tuple[int, int]:
    cells = route.cells
    if len(cells) < 2:
        return (1, 0)
    a, b = (cells[i - 1], cells[i]) if incoming or i == len(cells) - 1 else (cells[i], cells[i + 1])
    return (_sign(b[0] - a[0]), _sign(b[1] - a[1]))


def _footprint(route: Route, i: int, lo: int, hi: int) -> set[tuple[int, int]]:
    """Cells at offsets lo..hi across the line at cell i; a corner takes both legs."""
    x, z = route.cells[i]
    headings = {_heading(route, i)}
    if i in route.corners:
        headings.add(_heading(route, i, incoming=True))
    return {(x - dz * off, z + dx * off) for dx, dz in headings for off in range(lo, hi + 1)}


def _side_cell(route: Route, i: int, offset: int) -> tuple[int, int]:
    x, z = route.cells[i]
    dx, dz = _heading(route, i)
    return x - dz * offset, z + dx * offset


def _pick(design: LineDesign, role: str, *key: int) -> str:
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


def _slab(block: str) -> str:
    return f"{_variant(block, '_slab')}[type=bottom,waterlogged=false]"


def _stairs(block: str, facing: str) -> str:
    return f"{_variant(block, '_stairs')}[facing={facing},half=bottom,shape=straight,waterlogged=false]"


def _inside(site: Site, x: int, y: int, z: int) -> bool:
    x1, y1, z1, x2, y2, z2 = site.box
    return x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2


def _carvable(state: str) -> bool:
    block = base_id(state)
    return block in NATURAL and block not in _AIR and block not in _LAVA and not is_water_state(state)


def _carve(site: Site, columns: dict[tuple[int, int], int], height: int = CLEARANCE) -> dict:
    """Air for the natural, non-liquid blocks `height` cells up from each column's lowest y."""
    out = {}
    for (x, z), y0 in columns.items():
        for y in range(y0, y0 + height):
            if _inside(site, x, y, z) and _carvable(site.block(x, y, z)):
                out[(x, y, z)] = AIR
    return out


def _lower(columns: dict[tuple[int, int], int], x: int, z: int, y: int) -> None:
    columns[(x, z)] = min(columns.get((x, z), y), y)


def _layers(site: Site, **layers: dict) -> list[tuple[str, LiveWrite]]:
    """Live writes of the named cell maps, clipped to the site and without the empty ones."""
    out = []
    for name, cells in layers.items():
        write = cells_write({c: s for c, s in cells.items() if _inside(site, *c)})
        if write is not None:
            out.append((name, write))
    return out


def _lamp_column(design: LineDesign, cell: tuple[int, int], base: int,
                 out: dict[tuple[int, int, int], str]) -> None:
    x, z = cell
    out[(x, base, z)] = _pick(design, "lamp_post", x, base, z)
    out[(x, base + 1, z)] = _pick(design, "lamp_post", x, base + 1, z)
    out[(x, base + 2, z)] = _pick(design, "lamp", x, base + 2, z)


def _lights(design: LineDesign, route: Route, section: Section, spacing: int, lo: int, hi: int,
            base: Callable[[int], int], kinds: tuple[str, ...], out: dict[tuple[int, int, int], str]) -> None:
    """Lamp posts every `spacing` cells just outside offsets lo..hi, alternating sides."""
    n = len(route.cells)
    for i in range(section.start, section.end + 1):
        if i % spacing or route.kinds[i] not in kinds:
            continue
        side = lo - 1 if (i // spacing) % 2 else hi + 1
        cell = _side_cell(route, i, side)
        near = set().union(*(_footprint(route, j, lo, hi) for j in range(max(0, i - 3), min(n, i + 4))))
        if cell not in near:
            _lamp_column(design, cell, base(i), out)


# ------------------------------------------------------------------ rail
def _rail(design: LineDesign, route: Route, section: Section, site: Site, spacing: int):
    rails = rail_cells(design, route)
    n = len(route.cells)
    carve_at: dict[tuple[int, int], int] = {}
    build: dict[tuple[int, int, int], str] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in range(section.start, section.end + 1):
        rc = rails[i]
        foot = _footprint(route, i, -1, 1)
        for x, z in foot:
            _lower(carve_at, x, z, rc.y + 1)
            if route.kinds[i] in BED_KINDS:
                build[(x, rc.y - 1, z)] = _pick(design, "ballast", x, rc.y - 1, z)
        if rc.booster:
            build[(rc.x, rc.y - 1, rc.z)] = REDSTONE_BLOCK
        track[(rc.x, rc.y, rc.z)] = _rail_state(rc)
        for stop, at in ((design.start.stop, 0), (design.end.stop, n - 1)):
            if stop == "terminus" and i == at:
                dx, dz = _heading(route, i, incoming=at > 0)
                sx, sz = (1 if at else -1) * dx, (1 if at else -1) * dz
                build[(rc.x + sx, rc.y, rc.z + sz)] = _pick(design, "end_block", rc.x + sx, rc.y, rc.z + sz)
    light: dict[tuple[int, int, int], str] = {}
    _lights(design, route, section, spacing, -1, 1, lambda i: rails[i].y, LIT_KINDS, light)
    return _layers(site, carve=_carve(site, carve_at), build=build, track=track, light=light)


# ------------------------------------------------------------------ road
def _road(design: LineDesign, route: Route, section: Section, site: Site, spacing: int):
    width = 4 * design.lanes
    lo, hi = -((width - 1) // 2), width // 2
    idx = range(section.start, section.end + 1)
    surfaced = [i for i in idx if route.kinds[i] in BED_KINDS]
    road_cells = set().union(*(_footprint(route, i, lo, hi) for i in idx))
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = route.levels[i]
        top = int(np.ceil(level))
        for x, z in _footprint(route, i, lo - 1, hi + 1):
            _lower(carve_at, x, z, top)
    for i in surfaced:
        base = int(np.floor(route.levels[i]))
        half = route.levels[i] != base
        for x, z in _footprint(route, i, lo - 1, hi + 1) - road_cells:
            track[(x, base - 1, z)] = _pick(design, "surface", x, base - 1, z)
            track[(x, base, z)] = (_pick(design, "surface", x, base, z) if half
                                   else f"{_pick(design, 'edge', x, base, z)}[type=bottom,waterlogged=false]")
    for i in surfaced:
        base = int(np.floor(route.levels[i]))
        for x, z in _footprint(route, i, lo, hi):
            block = _pick(design, "surface", x, base - 1, z)
            track[(x, base - 1, z)] = block
            if route.levels[i] != base:
                track[(x, base, z)] = _slab(block)
    light: dict[tuple[int, int, int], str] = {}
    _lights(design, route, section, spacing, lo, hi, lambda i: int(np.floor(route.levels[i])) + 1,
            LIT_KINDS, light)
    return _layers(site, carve=_carve(site, carve_at), track=track, light=light)


# ------------------------------------------------------------------ path
def _path_span(design: LineDesign, i: int) -> tuple[int, int]:
    """Offsets of the path at cell i: the design width plus or minus one, in runs of three cells."""
    rng = np.random.default_rng([design.seed % 2**32, _SALT["width"], i // 3])
    width = max(1, design.width + int(rng.integers(-1, 2)))
    return -((width - 1) // 2), width // 2


def _path(design: LineDesign, route: Route, section: Section, site: Site, spacing: int):
    idx = range(section.start, section.end + 1)
    spans = {i: _path_span(design, i) for i in range(max(0, section.start - 3), min(len(route.cells), section.end + 4))}
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = int(route.levels[i])
        for x, z in _footprint(route, i, *spans[i]):
            _lower(carve_at, x, z, level)
            if route.kinds[i] in BED_KINDS:
                track[(x, level - 1, z)] = _pick(design, "surface", x, level - 1, z)
    for i in idx:
        if route.kinds[i] not in BED_KINDS:
            continue
        level = int(route.levels[i])
        for j in (i - 1, i + 1):
            if 0 <= j < len(route.cells) and int(route.levels[j]) == level - 1:
                facing = _toward((*route.cells[j], 0), (*route.cells[i], 0))
                for x, z in _footprint(route, i, *spans[i]):
                    if not base_id(track[(x, level - 1, z)]).endswith("_stairs"):
                        track[(x, level - 1, z)] = _stairs(track[(x, level - 1, z)], facing)
                break
    light: dict[tuple[int, int, int], str] = {}
    for i in idx:
        if i % spacing or route.kinds[i] not in LIT_KINDS:
            continue
        lo, hi = spans[i]
        cell = _side_cell(route, i, lo - 1 if (i // spacing) % 2 else hi + 1)
        near = set().union(*(_footprint(route, j, *spans[j]) for j in spans if abs(j - i) <= 3))
        if cell not in near:
            _lamp_column(design, cell, int(route.levels[i]), light)
    return _layers(site, carve=_carve(site, carve_at), track=track, light=light)


# ------------------------------------------------------------------ ice
def _ice(design: LineDesign, route: Route, section: Section, site: Site, spacing: int):
    idx = range(section.start, section.end + 1)
    lane = set().union(*(_footprint(route, i, 0, 1) for i in idx))
    carve_at: dict[tuple[int, int], int] = {}
    track: dict[tuple[int, int, int], str] = {}
    light: dict[tuple[int, int, int], str] = {}
    for i in idx:
        level = int(route.levels[i])
        for x, z in _footprint(route, i, -1, 2):
            _lower(carve_at, x, z, level)
        for x, z in _footprint(route, i, 0, 1):
            track[(x, level - 1, z)] = _pick(design, "ice", x, level - 1, z)
        for x, z in _footprint(route, i, -1, 2) - lane:
            track[(x, level, z)] = _slab(_pick(design, "guard", x, level, z))
    for i in idx:
        if i % spacing:
            continue
        level = int(route.levels[i])
        x, z = _side_cell(route, i, 2 if (i // spacing) % 2 else -1)
        if (x, z) not in lane:
            light[(x, level, z)] = design.lights.block
    return _layers(site, carve=_carve(site, carve_at, CLEARANCE + 1), track=track, light=light)


_MODES = {"rail": _rail, "road": _road, "path": _path, "ice": _ice}


def track_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                 light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]:
    """Live layers for the cells of `section`, in order, omitting empty ones.

    Returns ``("carve", clearance)``, ``("build", bed)``, ``("track", rails or surface)`` and
    ``("light", lamps)``. `light_spacing` ``None`` means ``design.lights.spacing``.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    return _MODES[design.mode](design, route, section, site, spacing)
