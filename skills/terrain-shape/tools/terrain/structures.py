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
from itertools import pairwise

from .blocks import full_cube
from .live import LiveWrite
from .route import Route, RouteError, Section
from .site import (
    _AIR,
    ATTACHED,
    LEAVES,
    NATURAL,
    NETHER_NATURAL,
    PLANTS,
    TRUNK,
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
    lamp_column,
    live_layers,
    pick,
    rail_cells,
    side_cell,
    slab,
)
from .transit_design import LineDesign, formation_half

Cell = tuple[int, int, int]

ARCH_SPAN = 32          # cells per arch span (spans stay under 40)
BEAM_MAX = 16           # auto picks a beam up to this many cells
TUBE_REACH = 24         # a tube pier must find ground within this many cells below
ROOM = (5, 4, 5)        # width, height and length of a room around the end cell
PLATFORM = (2, 8)       # width and length of a terminus platform

_VEGETATION = PLANTS | LEAVES | ATTACHED | TRUNK | frozenset(f"minecraft:{b}" for b in (
    "cobweb", "glow_lichen", "sculk_vein", "pointed_dripstone", "powder_snow", "amethyst_cluster",
    "small_amethyst_bud", "medium_amethyst_bud", "large_amethyst_bud", "crimson_roots", "warped_roots",
    "nether_sprouts", "crimson_fungus", "warped_fungus", "weeping_vines", "weeping_vines_plant",
    "twisting_vines", "twisting_vines_plant"))
_TERRAIN = NATURAL | NETHER_NATURAL


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


def _solid(state: str) -> bool:
    """Ground a pier stands on: a full cube (or natural terrain), not air, a liquid or a plant."""
    block = base_id(state)
    if _is_air(state) or liquid_kind(state) is not None or block in _VEGETATION:
        return False
    return block in _TERRAIN or full_cube(state)


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


def _scan(site: Site, x: int, z: int, top: int, depth: int | None = None) -> tuple[list[tuple[int, str]], str | None]:
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
        if _solid(state):
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
    water cells a pier replaced) and ``unsupported_tube`` (tube piers with no ground within 24
    cells below, left out). Raises `RouteError` when a pier would stand in flowing water or
    lava, or in still water without ``bridges.piers_in_water``.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    stats = {"piers": 0, "displaced_water": 0, "unsupported_tube": 0}
    first, last = section.start, section.end
    width = round(2 * formation_half(design)) + 2
    lo, hi = _span(width)
    reserved = _boosters(design, route)
    deck: dict[tuple[int, int], tuple[int, bool]] = {}
    inner: set[tuple[int, int]] = set()
    for i in range(first, last + 1):
        if route.kinds[i] != "bridge":
            continue
        level = route.levels[i]
        y, half = math.floor(level) - 1, level != math.floor(level)
        for xz in footprint(route, i, lo, hi):
            deck[xz] = (y, half)
        inner |= footprint(route, i, lo + 1, hi - 1)
    build: dict[Cell, str] = {}
    for (x, z), (y, half) in deck.items():
        if (x, y, z) not in reserved:
            build[(x, y, z)] = pick(design, "deck", x, y, z)
        if half:
            build[(x, y + 1, z)] = slab(pick(design, "deck", x, y + 1, z))
        if design.bridges.railings and (x, z) not in inner:
            build[(x, y + 1 + half, z)] = pick(design, "railing", x, y + 1 + half, z)
    light: dict[Cell, str] = {}
    for i in range(first, last + 1):
        if route.kinds[i] != "bridge" or i % spacing:
            continue
        x, z = side_cell(route, i, lo if (i // spacing) % 2 else hi)
        if (x, z) in deck:
            y, half = deck[(x, z)]
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
                _claim(design, _scan(site, x, z, deck[(x, z)][0] - 1)[0], x, z, piers, stats)
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
                    found, _ = _scan(site, x, z, top)
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
                found, ground = _scan(site, x, z, top, TUBE_REACH)
                if ground is not None and not any(liquid_kind(s) for _, s in found):
                    columns[(x, z)] = found
            if route.cells[i] in columns:
                stats["piers"] += 1
                for (x, z), found in columns.items():
                    for y, _ in found:
                        piers[(x, y, z)] = pick(design, "pier", x, y, z)
            else:
                stats["unsupported_tube"] += 1


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


def _enclose(design: LineDesign, site: Site, bore: set[Cell], shell: dict[Cell, str], *,
             reserved: set[Cell], lamps: set[Cell]) -> list[tuple[str, LiveWrite]]:
    """Carve the bore, line the shell where it is natural or air, light the `lamps` cells.

    Existing non-natural solid blocks are kept (never written over). Water or lava in the bore
    or shell raises `RouteError` naming the cell.
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
        if cell in bore:
            if _carvable(design, state):
                carve[cell] = AIR
            continue
        if cell in reserved or not (_is_air(state) or _host(design, state) or not full_cube(state)):
            continue
        x, y, z = cell
        role = shell[cell]
        build[cell] = _edge(design, x, y, z) if role == "edge" else pick(design, role, x, y, z)
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
    ``lights.block``, alternating sides. `light_spacing` ``None`` means ``design.lights.spacing``.
    """
    spacing = design.lights.spacing if light_spacing is None else light_spacing
    lo, hi = _span(design.tunnels.width)
    last = len(route.cells) - 1
    bored = ("tunnel", "tube")
    bore: set[Cell] = set()
    shell: dict[Cell, str] = {}
    lamps: set[Cell] = set()
    for i in range(section.start, section.end + 1):
        if route.kinds[i] not in ("tunnel", "tube"):
            continue
        cells, ring = _section_cells(design, route, i)
        bore |= cells
        if i == 0 or i == last or route.kinds[i - 1] not in bored or route.kinds[i + 1] not in bored:
            ring = {c: "edge" for c in ring}
        for cell, role in ring.items():
            shell.setdefault(cell, role)
        if i % spacing == 0:
            x, z = side_cell(route, i, lo - 1 if (i // spacing) % 2 else hi + 1)
            lamps.add((x, _base(route, i) + 1, z))
    for cell in bore:
        shell.pop(cell, None)
    return _enclose(design, site, bore, shell, reserved=_boosters(design, route), lamps=lamps)


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
def _room(design: LineDesign, route: Route, site: Site, i: int,
          outward: tuple[int, int]) -> list[tuple[str, LiveWrite]]:
    """A lined, lit room around cell i, open at the side the line comes from."""
    width, height, length = ROOM
    dx, dz = (outward[0], 0) if outward[0] else (0, outward[1])
    px, pz = -dz, dx
    x0, z0 = route.cells[i]
    base = _base(route, i)
    floor_y = _floor(route, i)
    half_w, half_l = width // 2, length // 2
    bore_lo, bore_hi = _span(design.tunnels.width)
    door_lo, door_hi = max(bore_lo, -half_w), min(bore_hi, half_w)
    bore: set[Cell] = set()
    shell: dict[Cell, str] = {}
    lamps: set[Cell] = set()
    for t in range(-half_l - 1, half_l + 2):
        for s in range(-half_w - 1, half_w + 2):
            x, z = x0 + t * dx + s * px, z0 + t * dz + s * pz
            if abs(t) <= half_l and abs(s) <= half_w:
                bore |= {(x, y, z) for y in range(base, base + height)}
                shell[(x, floor_y, z)] = shell[(x, base + height, z)] = "lining"
            else:
                door = t == -half_l - 1 and door_lo <= s <= door_hi
                for y in range(floor_y, base + height + 1):
                    if not (door and base <= y < base + min(height, design.tunnels.height)):
                        shell[(x, y, z)] = "lining"
    for t, s in ((half_l + 1, -1), (half_l + 1, 1), (-1, -half_w - 1), (1, -half_w - 1),
                 (-1, half_w + 1), (1, half_w + 1)):
        lamps.add((x0 + t * dx + s * px, base + height - 2, z0 + t * dz + s * pz))
    return _enclose(design, site, bore, shell, reserved=_boosters(design, route), lamps=lamps)


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
    edge = -(math.ceil(formation_half(design)) - 1)
    width, length = PLATFORM
    indices = range(n - length, n) if end else range(length)
    for j in indices:
        if not 0 <= j < n:
            continue
        py = _base(route, j)
        for off in range(edge - width + 1, edge + 1):
            px, pz = side_cell(route, j, off)
            build[(px, py, pz)] = pick(design, "platform", px, py, pz)
            if inside(site, px, py - 1, pz) and _is_air(site.block(px, py - 1, pz)):
                build[(px, py - 1, pz)] = pick(design, "platform", px, py - 1, pz)
            for above in (py + 1, py + 2):
                if inside(site, px, above, pz) and _carvable(design, site.block(px, above, pz)):
                    carve[(px, above, pz)] = AIR
        if (n - 1 - j if end else j) % spacing == 0:
            px, pz = side_cell(route, j, edge - width + 1)
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
        if not section.start <= i <= section.end:
            continue
        if stop == "terminus":
            out += _terminus(design, route, site, end, spacing)
        elif stop == "room":
            hx, hz = heading(route, i)
            out += _room(design, route, site, i, (hx, hz) if end else (-hx, -hz))
    return out
