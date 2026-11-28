"""Structures: what carries a line across gaps and through rock.

Bridges (``bridge_layers``: deck, railings, lamps and piers; beam or arch), tunnels and
tubes (``tunnel_layers``: a bore inside a lining shell, lit), Nether classing
(``nether_kinds``) and stops (``stop_layers``: terminus end block and platform, room, open).
Ashlar places blocks with no game physics, so every cell is written exactly and the blocks
that are already there are respected: water and lava are never overwritten silently, and a
lining or a room keeps the player's solid blocks.

Conventions. Offsets across the line follow `track`: travel along +x makes offset +1 z + 1.
``base = ceil(level)`` is the first standing cell (the rail cell, or the cell above the
walking surface), so the floor row is ``floor(level) - 1`` (``base - 1`` unless a half level) and a bore spans ``base .. base + height - 1``.
Layers are ``(mode, LiveWrite)`` pairs with the modes of `track`: ``carve``, ``build``, ``light``.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from itertools import pairwise

from .blocks import full_cube
from .live import LiveWrite
from .route import TUBE_REACH, Route, RouteError, Section
from .site import (
    _AIR,
    Site,
    base_id,
    is_still,
    liquid_kind,
    natural_for,
)
from .track import (
    AIR,
    carvable,
    footprint,
    heading,
    inside,
    keeps_built,
    lamp_column,
    live_layers,
    pick,
    pier_ground,
    platform_cells,
    rail_cells,
    rail_set,
    side_cell,
    slab,
)
from .transit_design import LineDesign, formation_half

Cell = tuple[int, int, int]

ARCH_SPAN = 32          # cells per arch span (spans stay under 40)
BEAM_MAX = 16           # auto picks a beam up to this many cells
ROOM = (5, 4, 5)        # width, height and length of a room around the end cell


# ------------------------------------------------------------------ helpers
def _span(width: int) -> tuple[int, int]:
    """Offsets of a centred cross-section `width` cells wide."""
    return -((width - 1) // 2), width // 2


def _base(route: Route, i: int) -> int:
    return math.ceil(route.levels[i])


def _floor(route: Route, i: int) -> int:
    """The floor row: the block the running surface stands on (a half-level slab sits on it)."""
    return math.floor(route.levels[i]) - 1


def _is_air(state: str) -> bool:
    return base_id(state) in _AIR


def _host(design: LineDesign, state: str) -> bool:
    """Terrain a structure may replace: natural blocks, and Nether rock in the Nether."""
    block = base_id(state)
    return block in natural_for(design.dimension)


def _carvable(design: LineDesign, state: str) -> bool:
    return carvable(state, natural_for(design.dimension))


def _runs(route: Route, kind: str) -> list[tuple[int, int]]:
    """Inclusive index ranges of the maximal runs of `kind` along the whole route."""
    runs, start = [], None
    for i, k in enumerate([*route.kinds, None]):
        if k == kind and start is None:
            start = i
        elif k != kind and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def _boosters(design: LineDesign, route: Route) -> set[Cell]:
    """The cells that hold a powered rail's redstone block: no deck or lining may replace them."""
    if design.mode != "rail":
        return set()
    return {(c.x, c.y - 1, c.z) for c in rail_cells(design, route) if c.booster}


def _scan(design: LineDesign, site: Site, x: int, z: int, top: int,
          depth: int | None = None) -> tuple[list[tuple[int, str]], str | None]:
    """The cells from y=`top` down to the first solid block, with that block.

    Cells above the read are skipped. With `depth` the scan gives up after that many cells
    (the second value is then None). Without ground it ends at the bottom of the read.
    """
    x1, y1, z1, x2, y2, z2 = site.box
    if not (x1 <= x <= x2 and z1 <= z <= z2):
        return [], None
    bottom = y1 if depth is None else max(y1, top - depth + 1)
    cells: list[tuple[int, str]] = []
    for y in range(min(top, y2), bottom - 1, -1):
        state = site.block(x, y, z)
        if pier_ground(state, design.dimension):
            return cells, state
        cells.append((y, state))
    return cells, None


def _claim(design: LineDesign, cells: list[tuple[int, str]], x: int, z: int, out: dict[Cell, str],
           stats: dict) -> None:
    """Add pier cells, refusing lava and flowing water and counting displaced still water."""
    for y, state in cells:
        cell = (x, y, z)
        if cell in out:
            continue
        kind = liquid_kind(state)
        if kind == "lava" or (kind == "water" and not is_still(state)):
            raise RouteError(f"pier at {cell} stands in {'lava' if kind == 'lava' else 'flowing water'}")
        if kind == "water":
            if not design.bridges.piers_in_water:
                raise RouteError(f"pier at {cell} stands in water; set bridges.piers_in_water")
            stats["displaced_water"] += 1
        out[cell] = pick(design, "pier", x, y, z)


def _edge(design: LineDesign, x: int, y: int, z: int) -> str:
    """The mouth block: the edge role, a slab made a full cube so the mouth has no gap."""
    block = pick(design, "edge", x, y, z)
    return f"{block}[type=double,waterlogged=false]" if base_id(block).endswith("_slab") else block


def floor_slab(design: LineDesign, x: int, y: int, z: int) -> str:
    """The floor block of a room that nothing may spawn on: the edge role as a bottom slab.

    Raises:
        ValueError: when the palette's edge role gives a block that is not a slab.
    """
    block = pick(design, "edge", x, y, z)
    if not base_id(block).endswith("_slab"):
        raise ValueError(f"palette.edge must be a slab for a floor nothing spawns on, got {block}")
    return f"{base_id(block)}[type=bottom,waterlogged=false]"


# ------------------------------------------------------------------ bridges
def _pier_indices(design: LineDesign, run: tuple[int, int], kind: str) -> list[int]:
    s, e = run
    if kind == "beam":
        return sorted({*range(s, e + 1, design.bridges.pier_spacing), e})
    spans = math.ceil((e - s + 1) / ARCH_SPAN)
    return [s + round(j * (e - s) / spans) for j in range(spans + 1)]


def bridge_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                  light_spacing: int | None = None) -> tuple[list[tuple[str, LiveWrite]], dict]:
    """Deck, railings, lamps and piers of the bridge cells in `section`, and tube piers.

    Returns ``(layers, stats)`` with stats ``piers`` (walls stood), ``displaced_water`` (still
    water cells a pier replaced), ``unsupported_tube`` (tube piers with no ground within
    ``TUBE_REACH`` cells below, left out) and ``tube_read_floor`` (the read's floor y, when it
    ended the search for such a pier short of ``TUBE_REACH``; else None). Railings and lamps
    keep off the running width of every route cell within the deck's reach, this section's or a
    neighbour's (a deck corner reaches two cells along both legs), and off every rail cell.
    Raises `RouteError` when a pier would stand in flowing water or lava, or in still water
    without ``bridges.piers_in_water``.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    stats: dict = {"piers": 0, "displaced_water": 0, "unsupported_tube": 0, "tube_read_floor": None}
    first, last = section.start, section.end
    width = round(2 * formation_half(design)) + 2
    lo, hi = _span(width)
    reserved = _boosters(design, route)
    rails = rail_set(design, route)
    deck: dict[tuple[int, int], tuple[int, bool]] = {}
    for i in range(first, last + 1):
        if route.kinds[i] != "bridge":
            continue
        level = route.levels[i]
        y, half = math.floor(level) - 1, level != math.floor(level)
        for xz in footprint(route, i, lo, hi):
            deck[xz] = (y, half)
    inner: set[tuple[int, int]] = set()
    for j in range(max(0, first - hi), min(len(route.cells), last + hi + 1)):
        inner |= footprint(route, j, lo + 1, hi - 1)
    build: dict[Cell, str] = {}
    for (x, z), (y, half) in deck.items():
        if (x, y, z) not in reserved:
            build[(x, y, z)] = pick(design, "deck", x, y, z)
        if half:
            build[(x, y + 1, z)] = slab(pick(design, "deck", x, y + 1, z))
        top = (x, y + 1 + half, z)
        if design.bridges.railings and (x, z) not in inner and top not in rails:
            build[top] = pick(design, "railing", *top)
    light: dict[Cell, str] = {}
    for i in range(first, last + 1):
        if route.kinds[i] != "bridge" or i % spacing:
            continue
        x, z = side_cell(route, i, lo if (i // spacing) % 2 else hi)
        if (x, z) in deck and (x, z) not in inner:
            y, half = deck[(x, z)]
            if not {(x, y + 1 + half + k, z) for k in range(3)} & rails:
                lamp_column(design, (x, z), y + 1 + half, light)
    piers: dict[Cell, str] = {}
    for run in _runs(route, "bridge"):
        length = run[1] - run[0] + 1
        arch = length >= 2 and (design.bridges.kind == "arch"
                                or (design.bridges.kind == "auto" and length > BEAM_MAX))
        indices = _pier_indices(design, run, "arch" if arch else "beam")
        for i in (j for j in indices if first <= j <= last):
            stats["piers"] += 1
            for x, z in footprint(route, i, lo, hi):
                _claim(design, _scan(design, site, x, z, deck[(x, z)][0] - 1)[0], x, z, piers, stats)
        if arch:
            _arch(design, route, site, indices, (lo, hi), (first, last), piers, stats)
    _tube_piers(design, route, section, site, piers, stats)
    return live_layers(site, build={**piers, **build}, light=light), stats


def _arch(design: LineDesign, route: Route, site: Site, indices: list[int], span: tuple[int, int],
          limits: tuple[int, int], piers: dict[Cell, str], stats: dict) -> None:
    """Spandrel fill under the deck of each arch span: an opening between the piers."""
    lo, hi = span
    for a, b in pairwise(indices):
        cells = [i for i in range(a, b + 1) if limits[0] <= i <= limits[1]]
        if not cells:
            continue
        scans: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
        lows: list[int] = []
        for i in range(a, b + 1):
            top = math.floor(route.levels[i]) - 2
            for x, z in footprint(route, i, lo, hi):
                if site.box[0] <= x <= site.box[3] and site.box[2] <= z <= site.box[5]:
                    found, _ = _scan(design, site, x, z, top)
                    scans[(i, x, z)] = found
                    lows.append(found[-1][0] - 1 if found else top)
                elif route.ground[i] is not None:
                    lows.append(math.floor(route.ground[i]))
        deck_y = min(math.floor(route.levels[i]) - 1 for i in range(a, b + 1))
        rise = min((b - a) / 4, deck_y - max(lows) - 2) if lows else 0
        for i in cells:
            u = (i - a) / (b - a)
            lowest = math.ceil(math.floor(route.levels[i]) - 2 - rise * (2 * u - 1) ** 2)
            for x, z in footprint(route, i, lo, hi):
                _claim(design, [c for c in scans.get((i, x, z), []) if c[0] >= lowest], x, z, piers, stats)


def _tube_piers(design: LineDesign, route: Route, section: Section, site: Site, piers: dict[Cell, str],
                stats: dict) -> None:
    lo, hi = _span(design.tunnels.width)
    for run in _runs(route, "tube"):
        for i in (j for j in _pier_indices(design, run, "beam") if section.start <= j <= section.end):
            top = _floor(route, i) - 1
            columns = {}
            for x, z in footprint(route, i, lo - 1, hi + 1):
                found, ground = _scan(design, site, x, z, top, TUBE_REACH)
                if ground is not None and not any(liquid_kind(s) for _, s in found):
                    columns[(x, z)] = found
            if route.cells[i] in columns:
                stats["piers"] += 1
                for (x, z), found in columns.items():
                    for y, _ in found:
                        piers[(x, y, z)] = pick(design, "pier", x, y, z)
            else:
                stats["unsupported_tube"] += 1
                if site.box[1] > top - TUBE_REACH + 1:      # the read ended the search before TUBE_REACH
                    stats["tube_read_floor"] = site.box[1]


# ------------------------------------------------------------------ tunnels and tubes
def _section_cells(design: LineDesign, route: Route, i: int) -> tuple[set[Cell], dict[Cell, str]]:
    """The bore cells of cell i and its shell: cell -> role (``lining`` or ``deck`` for a tube floor)."""
    width, height = design.tunnels.width, design.tunnels.height
    lo, hi = _span(width)
    base = _base(route, i)
    core = footprint(route, i, lo, hi)
    floor_y = _floor(route, i)
    bore = {(x, y, z) for x, z in core for y in range(base, base + height)}
    floor = "deck" if route.kinds[i] == "tube" else "lining"
    shell: dict[Cell, str] = {}
    for x, z in footprint(route, i, lo - 1, hi + 1):
        shell[(x, floor_y, z)] = floor
        shell[(x, base + height, z)] = "lining"
        if (x, z) not in core:
            shell.update({(x, y, z): "lining" for y in range(floor_y + 1, base + height)})
    return bore, shell


def enclose(design: LineDesign, site: Site, bore: set[Cell], shell: dict[Cell, str], *,
            reserved: set[Cell], lamps: set[Cell], rails: frozenset[Cell] = frozenset(),
            kept: Callable[[Cell], bool] | None = None) -> list[tuple[str, LiveWrite]]:
    """Carve the bore, line the shell where it is natural or air, light the `lamps` cells.

    Existing non-natural solid blocks are kept (never written over), and so is every shell cell
    `kept` names (a line's ``open`` stop keeps what is built there). No cell of `rails` is
    carved or lined. Water or lava in the bore or shell raises `RouteError` naming the cell. A
    shell cell's role is a palette role, ``edge`` (a full mouth block) or ``slab`` (a bottom slab
    floor, see `floor_slab`).
    """
    carve: dict[Cell, str] = {}
    build: dict[Cell, str] = {}
    light: dict[Cell, str] = {}
    for cell in sorted(bore | set(shell)):
        if not inside(site, *cell):
            continue
        state = site.block(*cell)
        kind = liquid_kind(state)
        if kind:
            raise RouteError(f"{'bore' if cell in bore else 'lining'} cell {cell} holds {kind}")
        if cell in rails:
            continue
        if cell in bore:
            if _carvable(design, state):
                carve[cell] = AIR
            continue
        if cell in reserved or (kept is not None and kept(cell)) or not (
                _is_air(state) or _host(design, state) or not full_cube(state)):
            continue
        x, y, z = cell
        role = shell[cell]
        build[cell] = (_edge(design, x, y, z) if role == "edge" else floor_slab(design, x, y, z)
                       if role == "slab" else pick(design, role, x, y, z))
        if cell in lamps:
            light[cell] = design.lights.block
    return live_layers(site, carve=carve, build=build, light=light)


def tunnel_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                  light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]:
    """Bore, lining shell and lights for the tunnel and tube cells of `section`.

    The bore is ``tunnels.width`` wide and ``tunnels.height`` high from the first standing
    cell; the shell is one ring around it (floor, walls, roof). A tube is the same section
    standing free: its floor is the deck. The end cells of a run use the ``edge`` block (the
    mouth). Every ``light_spacing`` cells a wall block at ``level + 1`` becomes
    ``lights.block``, alternating sides; where that cannot reach ``lights.minimum`` on the far side
    (``14 - width < minimum``) both walls get a lamp at the first standing height instead, and
    so does each mouth. `light_spacing` ``None`` means ``design.lights.spacing``.

    The shell keeps out of the running space (the bore's cross-section at its own level) of every
    route cell within the shell's reach, this section's or a neighbour's, whatever its kind: a
    corner's shell reaches two cells along both legs, which may belong to the previous section.
    It keeps out of a ``room`` at the line's end too (the room lines itself). No rail cell is
    carved or lined.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    lo, hi = _span(design.tunnels.width)
    last = len(route.cells) - 1
    pairs = 14 - design.tunnels.width < design.lights.minimum
    bored = ("tunnel", "tube")
    bore: set[Cell] = set()
    shell: dict[Cell, str] = {}
    lamps: set[Cell] = set()
    for i in range(section.start, section.end + 1):
        if route.kinds[i] not in ("tunnel", "tube"):
            continue
        cells, ring = _section_cells(design, route, i)
        bore |= cells
        mouth = i == 0 or i == last or route.kinds[i - 1] not in bored or route.kinds[i + 1] not in bored
        if mouth:
            ring = {c: "edge" for c in ring}
        for cell, role in ring.items():
            shell.setdefault(cell, role)
        if i % spacing == 0 or (pairs and mouth):
            if pairs:
                for off in (lo - 1, hi + 1):
                    x, z = side_cell(route, i, off)
                    lamps.add((x, _base(route, i), z))
            else:
                x, z = side_cell(route, i, lo - 1 if (i // spacing) % 2 else hi + 1)
                lamps.add((x, _base(route, i) + 1, z))
    for cell in bore:
        shell.pop(cell, None)
    reach = max(1 - lo, hi + 1)
    for j in range(max(0, section.start - reach), min(len(route.cells), section.end + reach + 1)):
        base = _base(route, j)
        for x, z in footprint(route, j, lo, hi):
            for y in range(base, base + design.tunnels.height):
                shell.pop((x, y, z), None)
    for i, outward in _room_ends(design, route):      # a room at the line's end owns its cells
        room_bore, room_shell, _ = _room_parts(design, route, i, outward)
        for cell in room_bore | set(room_shell):
            shell.pop(cell, None)
    return enclose(design, site, bore, shell, reserved=_boosters(design, route), lamps=lamps,
                   rails=rail_set(design, route), kept=keeps_built(design, site))


def nether_kinds(design: LineDesign, route: Route, section: Section, site: Site) -> list[str]:
    """``"tube"`` or ``"tunnel"`` for each cell of `section` (index ``i - section.start``).

    A cell is a tube when at least half of its bore cells are air or cave air, else a tunnel.
    Lava in the bore or shell raises `RouteError` naming the cell.
    """
    out = []
    for i in range(section.start, section.end + 1):
        bore, shell = _section_cells(design, route, i)
        for cell in sorted(bore | set(shell)):
            if inside(site, *cell) and liquid_kind(site.block(*cell)) == "lava":
                raise RouteError(f"{'bore' if cell in bore else 'lining'} cell {cell} holds lava")
        read = [c for c in bore if inside(site, *c)]
        air = sum(_is_air(site.block(*c)) for c in read)
        out.append("tube" if read and 2 * air >= len(read) else "tunnel")
    return out


# ------------------------------------------------------------------ stops
def _running(design: LineDesign) -> tuple[int, int]:
    """Offsets across the line of the cells its rail, ice lane or walking surface runs on."""
    if design.mode == "rail":
        return 0, 0
    if design.mode == "ice":
        return 0, 1
    return _span(4 * design.lanes if design.mode == "road" else design.width)


def _room_ends(design: LineDesign, route: Route) -> list[tuple[int, tuple[int, int]]]:
    """(end cell, outward heading) of each ``room`` stop of the line."""
    n = len(route.cells)
    out = []
    for end, stop in ((False, design.start.stop), (True, design.end.stop)):
        if stop == "room":
            i = n - 1 if end else 0
            hx, hz = heading(route, i)
            out.append((i, (hx, hz) if end else (-hx, -hz)))
    return out


def _room(design: LineDesign, route: Route, site: Site, i: int,
          outward: tuple[int, int]) -> list[tuple[str, LiveWrite]]:
    """A lined, lit room around cell i, open at the side the line comes from."""
    bore, shell, lamps = _room_parts(design, route, i, outward)
    return enclose(design, site, bore, shell, reserved=_boosters(design, route), lamps=lamps,
                   rails=rail_set(design, route))


def _room_parts(design: LineDesign, route: Route, i: int,
                outward: tuple[int, int]) -> tuple[set[Cell], dict[Cell, str], set[Cell]]:
    """The bore, shell and lamp cells of the room around end cell i.

    In the Nether, where hoglins and magma cubes spawn at any light, every standing cell of the
    room is a bottom ``edge`` slab nothing spawns on, except the cells the line itself runs on
    (its rails, lane or walking surface).
    """
    width, height, length = ROOM
    dx, dz = (outward[0], 0) if outward[0] else (0, outward[1])
    px, pz = -dz, dx
    x0, z0 = route.cells[i]
    base = _base(route, i)
    floor_y = _floor(route, i)
    half_w, half_l = width // 2, length // 2
    bore_lo, bore_hi = _span(design.tunnels.width)
    door_lo, door_hi = max(bore_lo, -half_w), min(bore_hi, half_w)
    own: set[tuple[int, int]] = set()
    if design.dimension == "nether":
        run_lo, run_hi = _running(design)
        for j in range(max(0, i - length), min(len(route.cells), i + length + 1)):
            own |= footprint(route, j, run_lo, run_hi)
    bore: set[Cell] = set()
    shell: dict[Cell, str] = {}
    lamps: set[Cell] = set()
    for t in range(-half_l - 1, half_l + 2):
        for s in range(-half_w - 1, half_w + 2):
            x, z = x0 + t * dx + s * px, z0 + t * dz + s * pz
            if abs(t) <= half_l and abs(s) <= half_w:
                slab_floor = design.dimension == "nether" and (x, z) not in own
                bore |= {(x, y, z) for y in range(base + slab_floor, base + height)}
                shell[(x, floor_y, z)] = shell[(x, base + height, z)] = "lining"
                if slab_floor:
                    shell[(x, base, z)] = "slab"
            else:
                door = t == -half_l - 1 and door_lo <= s <= door_hi
                for y in range(floor_y, base + height + 1):
                    if not (door and base <= y < base + min(height, design.tunnels.height)):
                        shell[(x, y, z)] = "lining"
    if design.lights.minimum > 9:
        # Every side-wall and far-wall cell at the first standing height: no floor cell is more than 3 away.
        ring = [(t, s) for t in range(-half_l, half_l + 1) for s in (-half_w - 1, half_w + 1)]
        ring += [(half_l + 1, s) for s in range(-half_w, half_w + 1)]
        lamps |= {(x0 + t * dx + s * px, base, z0 + t * dz + s * pz) for t, s in ring}
    else:
        for t, s in ((half_l + 1, -1), (half_l + 1, 1), (-1, -half_w - 1), (1, -half_w - 1),
                     (-1, half_w + 1), (1, half_w + 1)):
            lamps.add((x0 + t * dx + s * px, base + height - 2, z0 + t * dz + s * pz))
    return bore, shell, lamps


def _terminus(design: LineDesign, route: Route, site: Site, end: bool, spacing: int
              ) -> list[tuple[str, LiveWrite]]:
    """The end block one cell past the line and a platform on the left of travel."""
    n = len(route.cells)
    i = n - 1 if end else 0
    hx, hz = heading(route, i)
    if not end:
        hx, hz = -hx, -hz
    x, z = route.cells[i]
    y = _base(route, i)
    build: dict[Cell, str] = {(x + hx, y, z + hz): pick(design, "end_block", x + hx, y, z + hz)}
    carve: dict[Cell, str] = {}
    light: dict[Cell, str] = {}
    rails = rail_set(design, route)
    for j, px, pz, outer in platform_cells(design, route, end):
        py = _base(route, j)
        if (px, py, pz) in rails:
            continue
        build[(px, py, pz)] = pick(design, "platform", px, py, pz)
        if inside(site, px, py - 1, pz) and _is_air(site.block(px, py - 1, pz)):
            build[(px, py - 1, pz)] = pick(design, "platform", px, py - 1, pz)
        for above in (py + 1, py + 2):
            if (px, above, pz) not in rails and inside(site, px, above, pz) and _carvable(
                    design, site.block(px, above, pz)):
                carve[(px, above, pz)] = AIR
        if outer and (n - 1 - j if end else j) % spacing == 0:
            lamp_column(design, (px, pz), py + 1, light)
    return live_layers(site, carve=carve, build=build, light=light)


def stop_layers(design: LineDesign, route: Route, section: Section, site: Site, *,
                light_spacing: int | None = None) -> list[tuple[str, LiveWrite]]:
    """What the end stops of the line add inside `section`.

    ``terminus`` adds an end block one cell past the last rail (``end_block``, at the rail level)
    and a ``platform`` 2 wide and 8 long on the left of travel; ``room`` a lined, lit room 5 wide,
    4 high and 5 long around the end cell, open where the line enters; ``open`` adds nothing.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    out: list[tuple[str, LiveWrite]] = []
    n = len(route.cells)
    for end, stop in ((False, design.start.stop), (True, design.end.stop)):
        i = n - 1 if end else 0
        if section.start <= i <= section.end and stop == "terminus":
            out += _terminus(design, route, site, end, spacing)
    for i, outward in _room_ends(design, route):
        if section.start <= i <= section.end:
            out += _room(design, route, site, i, outward)
    return out
