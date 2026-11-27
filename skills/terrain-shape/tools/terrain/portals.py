"""Portal pairs: the pair maths, the stealing-portal check, frames, landings and emission.

A portal design (``terrain/<element>.portal.json``) names one end of a pair, or both; the other
end is the first one scaled into its dimension (x and z by 8, y unchanged). Each end is an
obsidian frame (outer ``w x h``, default 4 x 5) with ``nether_portal`` blocks in its opening and a
landing: a ``platform`` in the Overworld, a lit, lined room with a bottom-slab floor in the
Nether (so nothing spawns on it), with the design's ``doorways`` left open and framed.

Conventions. ``at`` is the frame's bottom outer corner (minimum x and z). The bottom row of the
frame is the floor row of the landing; the first standing cell is ``at.y + 1``. The frame lies in
the plane of its axis: an ``x`` frame spans x and has its faces on +z and -z.

The pair check follows the game's portal search: the search origin is the block that holds the
scaled arrival point, the candidates are the ``nether_portal`` blocks within 128 (Overworld) or 16
(Nether) blocks horizontally, at any height, and the nearest by squared block distance wins, ties
to the lower y. A pair passes when that winner belongs to the partner opening for every arrival
point of the other end.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import blocks, structures
from .ashlar_emit import EmitResult, check_form_layers, plan_rows_toon
from .emit import VerifyError
from .live import LiveWrite, greedy_fills
from .route import RouteError
from .site import Site, base_id, integer_level, liquid_kind, load_site, natural_for
from .track import AIR, carvable, inside, live_layers
from .transit_checks import MAX_CELLS, parse_state
from .transit_design import STYLES, palette_for

DIMENSIONS = ("overworld", "nether")
AXES = ("x", "z")
FACINGS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
TOP_KEYS = frozenset({"element", "seed", "overworld", "nether", "size", "doorways", "style", "palette", "version"})
END_KEYS = frozenset({"world", "at", "axis", "existing"})
SCALE = 8
RADIUS = {"overworld": 128, "nether": 16}       # horizontal search radius of the game
LIMITS = {"overworld": (-64, 319), "nether": (0, 255)}
FIT_Y = (33, 120)           # the Nether levels a landing may use, shell included
PORTAL, FRAME = "minecraft:nether_portal", "minecraft:obsidian"
LANDING_LIGHT, LANDING_LAMP = 12, "minecraft:shroomlight"
PAD = 1                     # landing cells beside the frame, each side
PLATFORM_DEPTH = 3          # Overworld platform cells in front of each face
ROOM_DEPTH, ROOM_HEIGHT = 5, 4
MIN_SIZE, MAX_SIZE = (4, 5), (23, 23)
ARRIVAL_MARGIN = 3
Cell = tuple[int, int, int]
Box = tuple[int, int, int, int, int, int]

_ELEMENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class PortalEnd:
    world: str
    dimension: str
    at: Cell | None
    axis: str
    existing: bool


@dataclass(frozen=True)
class PortalDesign:
    element: str
    seed: int
    size: tuple[int, int]
    overworld: PortalEnd
    nether: PortalEnd
    doorways: tuple[tuple[int, int, int, str], ...]
    style: str
    palette: dict[str, dict[str, int]]
    project: Path
    source: dict = field(default_factory=dict, compare=False)


# ------------------------------------------------------------------ parse
def _mapping(value, key: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object, got {value!r}")  # noqa: TRY004 - the design contract is ValueError
    return value


def _end(data: dict, dimension: str) -> tuple[str, Cell | None, str | None, bool]:
    node = _mapping(data.get(dimension), dimension)
    unknown = sorted(set(node) - END_KEYS)
    if unknown:
        raise ValueError(f"{dimension}.{unknown[0]} is not a known setting")
    world = node.get("world")
    if not isinstance(world, str) or not world:
        raise ValueError(f"{dimension}.world must name the world, got {world!r}")
    at = node.get("at")
    if at is not None:
        if not isinstance(at, (list, tuple)) or len(at) != 3:
            raise ValueError(f"{dimension}.at must be [x, y, z], got {at!r}")
        at = tuple(integer_level(v, f"{dimension}.at") for v in at)
    axis = node.get("axis")
    if axis is not None and axis not in AXES:
        raise ValueError(f"{dimension}.axis must be x or z, got {axis!r}")
    existing = node.get("existing", False)
    if not isinstance(existing, bool):
        raise ValueError(f"{dimension}.existing must be true or false, got {existing!r}")  # noqa: TRY004
    if existing and at is None:
        raise ValueError(f"{dimension}.existing needs {dimension}.at, the frame's bottom outer corner")
    return world, at, axis, existing  # type: ignore[return-value]


def parse_portal(data: dict, project_dir: Path) -> PortalDesign:
    """Validate a portal design dict and fill its defaults.

    Raises:
        ValueError: naming the key of the first invalid value.
    """
    data = _mapping(data, "portal design")
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise ValueError(f"{unknown[0]} is not a known portal design key")
    element = data.get("element")
    if not isinstance(element, str) or not _ELEMENT.match(element):
        raise ValueError(f"element must be a lowercase name, got {element!r}")
    seed = integer_level(data.get("seed", 0), "seed")
    size = data.get("size", list(MIN_SIZE))
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        raise ValueError(f"size must be [width, height], got {size!r}")
    w, h = (integer_level(v, "size") for v in size)
    if not (MIN_SIZE[0] <= w <= MAX_SIZE[0] and MIN_SIZE[1] <= h <= MAX_SIZE[1]):
        raise ValueError(f"size must be from {list(MIN_SIZE)} to {list(MAX_SIZE)}, got {[w, h]}")
    ends = {dim: _end(data, dim) for dim in DIMENSIONS}
    if ends["overworld"][0] == ends["nether"][0]:
        raise ValueError("overworld.world and nether.world must be different worlds")
    if ends["overworld"][1] is None and ends["nether"][1] is None:
        raise ValueError("give overworld.at or nether.at: the other end is computed from it")
    axes = {a for _, _, a, _ in ends.values() if a is not None}
    if len(axes) > 1:
        raise ValueError("overworld.axis and nether.axis must match")
    axis = axes.pop() if axes else "x"
    raw = data.get("doorways", [])
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"doorways must be a list of [x, y, z, facing], got {raw!r}")  # noqa: TRY004
    doorways = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 4 or item[3] not in FACINGS:
            raise ValueError(f"doorways must hold [x, y, z, facing] with facing one of {', '.join(FACINGS)}, "
                             f"got {item!r}")
        doorways.append((*(integer_level(v, "doorways") for v in item[:3]), item[3]))
    style = data.get("style", "nether")
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}, got {style!r}")
    palette = palette_for(style, data.get("palette", {}))
    version = data.get("version", "26.3")
    if not isinstance(version, str) or not version:
        raise ValueError(f"version must be text, got {version!r}")
    made = {dim: PortalEnd(ends[dim][0], dim, ends[dim][1], axis, ends[dim][3]) for dim in DIMENSIONS}
    return PortalDesign(element=element, seed=seed, size=(w, h), overworld=made["overworld"], nether=made["nether"],
                        doorways=tuple(doorways), style=style, palette=palette, project=Path(project_dir),
                        source=data)


def load_portal(path: Path, project_dir: Path | None = None) -> PortalDesign:
    """Read and validate a ``<element>.portal.json`` file (the project defaults to the folder above ``terrain/``)."""
    path = Path(path)
    if project_dir is None:
        project_dir = path.parent.parent if path.parent.name == "terrain" else path.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the portal design {path}: {exc}") from None
    return parse_portal(data, Path(project_dir))


# ------------------------------------------------------------------ maths
def scale(point: Cell, into: str) -> Cell:
    """The block a point maps to in dimension `into`: x and z by 8 (floored into the Nether), y unchanged."""
    x, y, z = point
    if into == "nether":
        return (x // SCALE, y, z // SCALE)
    if into == "overworld":
        return (x * SCALE, y, z * SCALE)
    raise ValueError(f"unknown dimension {into!r}")


def _scale_point(point: tuple[float, float, float], into: str) -> tuple[float, float, float]:
    x, y, z = point
    return (x / SCALE, y, z / SCALE) if into == "nether" else (x * SCALE, y, z * SCALE)


def _end_of(design: PortalDesign, dimension: str) -> PortalEnd:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}")
    return design.overworld if dimension == "overworld" else design.nether


def _other(dimension: str) -> str:
    return "nether" if dimension == "overworld" else "overworld"


def frame_origin(design: PortalDesign, dimension: str) -> Cell:
    """The frame's bottom outer corner (minimum x and z): the end's own ``at`` or the partner's, scaled."""
    end = _end_of(design, dimension)
    if end.at is not None:
        return end.at
    partner = _end_of(design, _other(dimension)).at
    if partner is None:
        raise ValueError("neither end has an at")
    return scale(partner, dimension)


def _at(origin: Cell, axis: str, a: int, p: int, y: int) -> Cell:
    """The cell `a` along the frame, `p` across it (in front of a face) and at level `y`."""
    return (origin[0] + a, y, origin[2] + p) if axis == "x" else (origin[0] + p, y, origin[2] + a)


def _frame_grid(design: PortalDesign, dimension: str) -> list[tuple[int, int, Cell]]:
    origin, axis = frame_origin(design, dimension), _end_of(design, dimension).axis
    w, h = design.size
    return [(i, j, _at(origin, axis, i, 0, origin[1] + j)) for i in range(w) for j in range(h)]


def frame_cells(design: PortalDesign, dimension: str) -> list[Cell]:
    """The obsidian cells of the frame: its outer ring, corners included."""
    w, h = design.size
    return [c for i, j, c in _frame_grid(design, dimension) if i in (0, w - 1) or j in (0, h - 1)]


def opening(design: PortalDesign, dimension: str) -> list[Cell]:
    """The ``nether_portal`` cells inside the frame."""
    w, h = design.size
    return [c for i, j, c in _frame_grid(design, dimension) if 0 < i < w - 1 and 0 < j < h - 1]


def arrival_points(design: PortalDesign, into: str) -> list[tuple[float, float, float]]:
    """Where an entity leaving the other end's opening lands in dimension `into`, unfloored.

    For each opening cell of the source end: its corner, centre and far edge along the opening,
    at mid-height and mid-thickness, scaled into `into`, so a 2-wide opening covers its width.
    """
    source = _other(into)
    axis = _end_of(design, source).axis
    points = set()
    for x, y, z in opening(design, source):
        for t in (0.0, 0.5, 1.0):
            at = (x + t, y + 0.5, z + 0.5) if axis == "x" else (x + 0.5, y + 0.5, z + t)
            points.add(_scale_point(at, into))
    return sorted(points)


def _block_of(point: tuple[float, float, float]) -> Cell:
    return (math.floor(point[0]), math.floor(point[1]), math.floor(point[2]))


def _grow(origin: Cell, radius: int, dimension: str) -> Box:
    lo, hi = LIMITS[dimension]
    return (origin[0] - radius, max(origin[1] - radius, lo), origin[2] - radius,
            origin[0] + radius, min(origin[1] + radius, hi), origin[2] + radius)


def _reach(design: PortalDesign, dimension: str, origin: Cell) -> int:
    """How far a stealing portal can be: the distance to the partner opening, within the search radius."""
    nearest = min((c[0] - origin[0]) ** 2 + (c[1] - origin[1]) ** 2 + (c[2] - origin[2]) ** 2
                  for c in opening(design, dimension))
    return min(math.ceil(math.sqrt(nearest)), RADIUS[dimension])


def _union(boxes: Sequence[Box]) -> Box:
    return (*(min(b[i] for b in boxes) for i in range(3)), *(max(b[i] for b in boxes) for i in range(3, 6)))


def _room_height(design: PortalDesign) -> int:
    return max(ROOM_HEIGHT, design.size[1] - 1)


def _landing_box(design: PortalDesign, dimension: str) -> Box:
    """The frame and landing: everything the end writes (the Nether range of a computed end is open)."""
    ox, oy, oz = frame_origin(design, dimension)
    w, h = design.size
    axis = _end_of(design, dimension).axis
    if dimension == "overworld":
        a, p, top = (-PAD, w - 1 + PAD), PLATFORM_DEPTH, oy + h - 1
    else:
        a, p, top = (-PAD - 1, w + PAD), ROOM_DEPTH + 1, oy + _room_height(design) + 1
    corners = [_at((ox, oy, oz), axis, i, q, y) for i in a for q in (-p, p) for y in (oy, top)]
    box = _union([(*c, *c) for c in corners])
    if dimension == "nether" and design.nether.at is None:
        return (box[0], FIT_Y[0] - 1, box[2], box[3], FIT_Y[1] + 1, box[5])
    return box


def read_boxes(design: PortalDesign) -> dict[str, Box]:
    """Per dimension the box to read: the frame and landing, and each arrival grown past the partner.

    Any portal that could win an arrival point is nearer to it than the partner opening, so it lies
    within that distance (plus 3) of the point.
    """
    out = {}
    for dim in DIMENSIONS:
        boxes = [_landing_box(design, dim)]
        for point in arrival_points(design, dim):
            origin = _block_of(point)
            boxes.append(_grow(origin, _reach(design, dim, origin) + ARRIVAL_MARGIN, dim))
        out[dim] = _union(boxes)
    return out


# ------------------------------------------------------------------ the pair check
def _portal_cells(site: Site) -> np.ndarray:
    cells = [(x, y, z) for (x, z), runs in site.columns.items() for lo, hi, state in runs
             if base_id(state) == PORTAL for y in range(lo, hi + 1)]
    return np.array(cells, dtype=np.int64).reshape(-1, 3)


def _winner(cells: np.ndarray, origin: Cell, radius: int) -> Cell | None:
    """The portal block the game picks: nearest by squared distance, ties to the lower y."""
    if not len(cells):
        return None
    near = cells[(np.abs(cells[:, 0] - origin[0]) <= radius) & (np.abs(cells[:, 2] - origin[2]) <= radius)]
    if not len(near):
        return None
    d2 = ((near - np.array(origin)) ** 2).sum(axis=1)
    best = near[d2 == d2.min()]
    pick = best[np.argmin(best[:, 1])]
    return (int(pick[0]), int(pick[1]), int(pick[2]))


def _contained(box: Box, inner: Box) -> bool:
    return all(box[i] <= inner[i] for i in range(3)) and all(box[i] >= inner[i] for i in range(3, 6))


def pair_check(design: PortalDesign, sites: Mapping[str, Site]) -> dict:
    """Check, per dimension, that every arrival point from the other end finds the partner portal first.

    `sites` holds a read per dimension (``"overworld"``, ``"nether"``). The result is
    ``{"ok", "checks": [...]}`` with one ``{"name", "ok", "detail", "cells"}`` per dimension
    (``pair-overworld``, ``pair-nether``); ``cells`` lists up to ten portal blocks that win an
    arrival point though they are not the partner's.

    Raises:
        ValueError: when a read is missing or does not cover the area the check needs around an
            arrival point (the distance to the partner opening).
    """
    checks = []
    for dim in DIMENSIONS:
        site = sites.get(dim)
        if site is None:
            raise ValueError(f"no read of the {dim}")
        partner = set(opening(design, dim))
        cells = _portal_cells(site)
        thieves: list[Cell] = []
        lost, points = 0, arrival_points(design, dim)
        first = ""
        for point in points:
            origin = _block_of(point)
            need = _grow(origin, _reach(design, dim, origin), dim)
            if not _contained(site.box, need):
                raise ValueError(f"the read of the {dim} covers {list(site.box)}, which does not hold {list(need)} "
                                 f"around the arrival {tuple(round(v, 2) for v in point)}; read that box again")
            win = _winner(cells, origin, RADIUS[dim])
            if win in partner:
                continue
            lost += 1
            if win is not None and win not in thieves:
                thieves.append(win)
            first = first or (f"arrival {tuple(round(v, 2) for v in point)} reaches "
                              + (f"the portal block {win}" if win else "no portal block"))
        ok = not lost
        checks.append({"name": f"pair-{dim}", "ok": ok,
                       "detail": f"{len(points)} arrival points reach the partner portal first" if ok else
                                 f"{lost} of {len(points)} arrival points miss the partner portal: {first}",
                       "cells": [list(c) for c in thieves[:MAX_CELLS]]})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


# ------------------------------------------------------------------ the landings
@dataclass(frozen=True)
class _Dress:
    """What `structures.enclose` and `track.pick` read of a design: the end's dimension, palette and seed."""

    dimension: str
    palette: dict[str, dict[str, int]]
    seed: int
    lights: SimpleNamespace


@dataclass
class _Room:
    bore: set[Cell]
    shell: dict[Cell, str]
    lamps: set[Cell]
    walls: set[Cell]
    standing: list[Cell]        # the first standing cell of every floor position of the room


def _nether_room(design: PortalDesign) -> _Room:
    """The Nether landing: a room round both faces, 4 high, its floor a bottom slab, lamps in every wall."""
    origin, axis = frame_origin(design, "nether"), design.nether.axis
    oy = origin[1]
    w, _ = design.size
    height = _room_height(design)
    stand, roof = oy + 1, oy + height + 1
    skip = set(frame_cells(design, "nether")) | set(opening(design, "nether"))
    bore: set[Cell] = set()
    shell: dict[Cell, str] = {}
    standing: list[Cell] = []
    for a in range(-PAD, w + PAD):
        for p in range(-ROOM_DEPTH, ROOM_DEPTH + 1):
            for y, role in ((oy, "lining"), (stand, "slab"), (roof, "lining")):
                cell = _at(origin, axis, a, p, y)
                if cell not in skip:
                    shell[cell] = role
            bore |= {c for y in range(oy + 2, oy + height + 1) if (c := _at(origin, axis, a, p, y)) not in skip}
            standing.append(_at(origin, axis, a, p, stand))
    walls: set[Cell] = set()
    for y in range(oy, roof + 1):
        walls |= {_at(origin, axis, a, p, y) for a in range(-PAD - 1, w + PAD + 1) for p in (-ROOM_DEPTH - 1, ROOM_DEPTH + 1)}
        walls |= {_at(origin, axis, a, p, y) for a in (-PAD - 1, w + PAD) for p in range(-ROOM_DEPTH, ROOM_DEPTH + 1)}
    shell.update({c: "lining" for c in walls})
    lamps = {c for c in walls if c[1] == stand}
    lamps -= {_at(origin, axis, a, p, stand) for a in (-PAD - 1, w + PAD) for p in (-ROOM_DEPTH - 1, ROOM_DEPTH + 1)}
    room = _Room(bore, shell, lamps, walls, standing)
    for doorway in design.doorways:
        _open_doorway(room, doorway)
    return room


def _open_doorway(room: _Room, doorway: tuple[int, int, int, str]) -> None:
    """Leave a doorway open 2 high through the wall it faces, framed in the edge block.

    The doorway cell is the first open cell: its row and the one above stay air from there out
    through the wall, and the wall cells round the mouth become the edge block.
    """
    x, y, z, facing = doorway
    dx, dz = FACINGS[facing]
    inner = room.bore | set(room.shell)
    path = []
    for k in range(64):
        cell = (x + k * dx, y, z + k * dz)
        if cell not in inner:
            break
        path.append(k)
    mouth = next((k for k in path if (x + k * dx, y, z + k * dz) in room.walls), None)
    if mouth is None:
        raise ValueError(f"doorway {[x, y, z, facing]} does not reach a wall of the landing: it must start "
                         f"inside the room or in the wall, facing the wall it opens")
    opened = {(x + k * dx, y + j, z + k * dz) for k in path for j in (0, 1)}
    for cell in opened:
        room.shell.pop(cell, None)
        room.lamps.discard(cell)
    room.bore |= opened
    px, pz = (0, 1) if dx else (1, 0)
    mx, mz = x + mouth * dx, z + mouth * dz
    ring = {(mx + t * px, y + j, mz + t * pz) for t in (-1, 1) for j in (0, 1)}
    ring |= {(mx + t * px, yy, mz + t * pz) for t in (-1, 0, 1) for yy in (y - 1, y + 2)}
    for cell in ring & room.walls:
        room.shell[cell] = "edge"
        room.lamps.discard(cell)


def _inside_all(site: Site, cells, what: str, design: PortalDesign, dimension: str) -> None:
    for cell in sorted(cells):
        if not inside(site, *cell):
            raise ValueError(f"the {what} cell {cell} lies outside the read of the {dimension}, which covers "
                             f"{list(site.box)}; read {list(read_boxes(design)[dimension])}")


def _frame_layers(design: PortalDesign, dimension: str, site: Site) -> list[tuple[str, LiveWrite]]:
    """The obsidian frame and the portal blocks of the opening, which replace whatever is there.

    Raises:
        RouteError: naming the cell when the frame or opening holds a liquid.
    """
    frame, hole = frame_cells(design, dimension), opening(design, dimension)
    for cell in sorted(frame + hole):
        kind = liquid_kind(site.block(*cell))
        if kind:
            raise RouteError(f"frame cell {cell} holds {kind}")
    state = f"{PORTAL}[axis={_end_of(design, dimension).axis}]"
    return live_layers(site, build={c: FRAME for c in frame}, portal={c: state for c in hole})


def _overworld_layers(design: PortalDesign, site: Site) -> list[tuple[str, LiveWrite]]:
    """A platform 3 deep on both faces at the frame's bottom row, with the space above cleared."""
    origin, axis = frame_origin(design, "overworld"), design.overworld.axis
    oy = origin[1]
    w, h = design.size
    natural = natural_for("overworld")
    skip = set(frame_cells(design, "overworld")) | set(opening(design, "overworld"))
    dress = _Dress("overworld", design.palette, design.seed, SimpleNamespace(block=LANDING_LAMP))
    carve: dict[Cell, str] = {}
    build: dict[Cell, str] = {}
    for a in range(-PAD, w + PAD):
        for p in range(-PLATFORM_DEPTH, PLATFORM_DEPTH + 1):
            cell = _at(origin, axis, a, p, oy)
            if cell not in skip:
                state = site.block(*cell) if inside(site, *cell) else ""
                if state and (base_id(state) in natural or not blocks.full_cube(state)):
                    build[cell] = structures.pick(dress, "platform", *cell)
            for y in range(oy + 1, oy + h):
                above = _at(origin, axis, a, p, y)
                if above not in skip and inside(site, *above) and carvable(site.block(*above), natural):
                    carve[above] = AIR
    return live_layers(site, carve=carve, build=build)


def portal_layers(design: PortalDesign, dimension: str, site: Site) -> list[tuple[str, LiveWrite]]:
    """The writes of one end, in build order: ``carve``, ``build``, ``portal``, ``light``.

    The Overworld end is a platform and the clearance above it; the Nether end is the lined, lit
    room with its doorways. Both carry the frame and the portal blocks. An end that is
    ``existing`` writes nothing.

    Raises:
        ValueError: when the read does not cover the frame and landing.
        RouteError: naming the cell when the frame or the landing holds lava or water.
    """
    end = _end_of(design, dimension)
    if end.existing:
        return []
    frame = frame_cells(design, dimension) + opening(design, dimension)
    if dimension == "overworld":
        _inside_all(site, frame, "frame", design, dimension)
        return [*_overworld_layers(design, site), *_frame_layers(design, dimension, site)]
    room = _nether_room(design)
    _inside_all(site, [*frame, *room.bore, *room.shell], "landing", design, dimension)
    dress = _Dress("nether", design.palette, design.seed, SimpleNamespace(block=LANDING_LAMP))
    lined = structures.enclose(dress, site, room.bore, room.shell, reserved=set(), lamps=room.lamps)
    framed = _frame_layers(design, dimension, site)
    # the lining first, then the frame, the portal blocks and the lamps
    out = [(m, w) for m, w in lined if m in ("carve", "build")]
    out += [(m, w) for m, w in framed if m == "build"]
    out += [(m, w) for m, w in framed if m == "portal"]
    out += [(m, w) for m, w in lined if m == "light"]
    return out


def _lava_in_landing(design: PortalDesign, site: Site) -> Cell | None:
    room = _nether_room(design)
    cells = [*frame_cells(design, "nether"), *opening(design, "nether"), *room.bore, *room.shell]
    return next((c for c in sorted(cells) if inside(site, *c) and liquid_kind(site.block(*c)) == "lava"), None)


def fit_nether(design: PortalDesign, site: Site) -> PortalDesign:
    """The design with its Nether end placed: where `at` was not given, at the scaled y if the
    landing fits there (levels 33 to 120, no lava in the frame or landing), else the nearest y that fits.

    Raises:
        RouteError: naming a lava cell when no level fits.
    """
    if design.nether.at is not None:
        return design
    x, y0, z = frame_origin(design, "nether")
    lo, hi, height = FIT_Y[0], FIT_Y[1], _room_height(design)
    first: Cell | None = None
    for step in range(hi - lo + 1):
        for y in dict.fromkeys((y0 - step, y0 + step)):
            if y < lo or y + height + 1 > hi:
                continue
            trial = replace(design, nether=replace(design.nether, at=(x, y, z)))
            lava = _lava_in_landing(trial, site)
            if lava is None:
                return trial
            first = first or lava
    raise RouteError(f"no Nether level from {lo} to {hi} fits the landing at x {x}, z {z}"
                     + (f": lava at {first}" if first else ""))


# ------------------------------------------------------------------ checks
def _landing_light(design: PortalDesign, site: Site) -> tuple[list[Cell], int]:
    """The open standing cells of the Nether landing with block light below the minimum, and how many were checked."""
    room = _nether_room(design)
    skip = set(frame_cells(design, "nether")) | set(opening(design, "nether"))
    level = blocks.flood(blocks.cell_classes(site)[1], blocks.site_light(site))
    bad, checked = [], 0
    for cell in room.standing:
        if cell in skip:
            continue
        if not inside(site, *cell):
            bad.append(cell)
            continue
        state = site.block(*cell)
        if blocks.full_cube(state) or liquid_kind(state):
            continue
        checked += 1
        if int(level[cell[0] - site.box[0], cell[1] - site.box[1], cell[2] - site.box[2]]) < LANDING_LIGHT:
            bad.append(cell)
    return bad, checked


def check_portal(design: PortalDesign, sites: Mapping[str, Site]) -> dict:
    """The portal checks over a read per dimension: ``{"ok", "checks": [...]}``.

    ``frame`` (every obsidian cell), ``axis`` (every opening cell is ``nether_portal`` with the
    design's axis), ``light`` (the Nether landing's standing cells reach 12; not for an existing
    end) and the two ``pair-`` checks. Block states are compared by parsed properties.

    Raises:
        ValueError: when a read is missing or too small for the pair check.
    """
    for dim in DIMENSIONS:
        if dim not in sites:
            raise ValueError(f"no read of the {dim}")
    frame_bad: list[Cell] = []
    axis_bad: list[Cell] = []
    n_frame = n_axis = 0
    for dim in DIMENSIONS:
        site, axis = sites[dim], _end_of(design, dim).axis
        for cell in frame_cells(design, dim):
            n_frame += 1
            if not inside(site, *cell) or base_id(site.block(*cell)) != FRAME:
                frame_bad.append(cell)
        for cell in opening(design, dim):
            n_axis += 1
            if not inside(site, *cell):
                axis_bad.append(cell)
                continue
            block, props = parse_state(site.block(*cell))
            if block != PORTAL or props.get("axis") != axis:
                axis_bad.append(cell)

    def outcome(name: str, bad: list[Cell], checked: int, problem: str) -> dict:
        return {"name": name, "ok": not bad,
                "detail": f"{len(bad)} of {checked}: {problem}" if bad else f"{checked} checked",
                "cells": [list(c) for c in bad[:MAX_CELLS]]}

    results = [outcome("frame", frame_bad, n_frame, "frame cells that are not obsidian"),
               outcome("axis", axis_bad, n_axis, f"opening cells that are not nether_portal[axis={design.nether.axis}]")]
    if not design.nether.existing:
        bad, checked = _landing_light(design, sites["nether"])
        results.append(outcome("light", bad, checked, f"landing cells with block light below {LANDING_LIGHT}"))
    results += pair_check(design, sites)["checks"]
    return {"ok": all(c["ok"] for c in results), "checks": results}


def _report_path(design: PortalDesign, project: Path) -> Path:
    return Path(project) / "terrain" / f"{design.element}.portal-report.json"


def check_reads(design: PortalDesign, project: Path, reads: Sequence[Path]) -> dict:
    """Check fresh reads of a built portal pair (one read per world), as `check_portal` does.

    A design whose Nether end was fitted by ``terrain.py portal`` is checked at the level the
    build used, from ``terrain/<element>.portal-report.json``.

    Raises:
        ValueError: a missing portal report for a computed Nether end, a read of a world that is
            neither end's, or an end without a read.
    """
    if design.nether.at is None:
        path = _report_path(design, project)
        try:
            at = json.loads(path.read_text(encoding="utf-8"))["ends"]["nether"]["at"]
            design = replace(design, nether=replace(design.nether, at=tuple(int(v) for v in at)))
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError(f"{path.relative_to(project)} is missing or unreadable: run terrain.py portal first "
                             "(the report records the Nether level the build used)") from None
    sites: dict[str, Site] = {}
    for path in reads:
        site = load_site(path)
        dim = next((d for d in DIMENSIONS if _end_of(design, d).world == site.world), None)
        if dim is None:
            raise ValueError(f"the read {path} is of world {site.world!r}, which is neither "
                             f"{design.overworld.world!r} nor {design.nether.world!r}")
        sites[dim] = site
    return check_portal(design, sites)


# ------------------------------------------------------------------ emission
def _why(design: PortalDesign, dimension: str):
    frame = set(frame_cells(design, dimension))
    hole = set(opening(design, dimension))
    kind = "platform" if dimension == "overworld" else "room"

    def why(mode: str, cell: Cell) -> str:
        if mode == "portal" or cell in hole:
            return f"in the opening of the {dimension} portal {design.element}"
        if cell in frame:
            return f"in the frame of the {dimension} portal {design.element}"
        if mode == "carve":
            return f"inside the {kind} space of the {dimension} portal {design.element}"
        if mode == "light":
            return f"at a lamp of the {dimension} portal {design.element}"
        return f"in the {kind} of the {dimension} portal {design.element}"

    return why


def _load_reads(design: PortalDesign, project: Path) -> dict[str, Site]:
    boxes = read_boxes(design)
    folders = {dim: f"site/{design.element}-{dim}" for dim in DIMENSIONS}
    missing = [f"{folders[d]} = box {list(boxes[d])} (world {_end_of(design, d).world})"
               for d in DIMENSIONS if not (project / folders[d]).is_dir()]
    if missing:
        raise ValueError("the portal reads are missing: read " + "; ".join(missing))
    sites = {}
    for dim in DIMENSIONS:
        try:
            site = load_site(project / folders[dim])
        except ValueError as exc:
            raise ValueError(f"{dim} read {folders[dim]}: {exc}") from None
        end = _end_of(design, dim)
        if site.world != end.world:
            raise ValueError(f"{dim} read {folders[dim]} is of world {site.world!r}, but the end is in {end.world!r}")
        if not _contained(site.box, boxes[dim]):
            raise ValueError(f"{dim} read {folders[dim]} covers {list(site.box)}, which does not contain "
                             f"{list(boxes[dim])}; read that box again")
        sites[dim] = site
    return sites


def emit_portal(design: PortalDesign, project: Path, *, first_phase: int, preview: bool = False,
                standalone: bool = False, approve_built: str | None = None, max_columns: int = 128) -> dict:
    """Check a portal pair against its two reads and write the phases of both worlds.

    The Overworld phases come first, then the Nether's, with contiguous ids from `first_phase`,
    named ``<element>-<dimension>-<mode>-<k>``. Reads live in ``site/<element>-overworld`` and
    ``site/<element>-nether``. A Nether end without ``at`` is fitted to its read first (see
    `fit_nether`). The report ``terrain/<element>.portal-report.json`` is written on every run; a
    preview writes nothing else. A write also copies the design to
    ``terrain/<element>.portal.json`` when the file there differs, because the plan's ``transit``
    row points at it.

    Args:
        design: The validated portal design.
        project: The project folder.
        first_phase: The id of the first phase in the host plan.
        preview: Write only the report.
        standalone: Also write a ``plan.toon`` for a pair that is its own project (not with `preview`).
        approve_built: The report's ``built.token``, given only after the user approved every
            player block the pair would replace.
        max_columns: Columns per phase tile.

    Returns:
        ``{"preview", "phases", "bbox", "notes", "report", "quality"}``; ``bbox`` is that of the
        Overworld phases (the Nether's is in ``report["boxes"]``).

    Raises:
        ValueError: `preview` with `standalone`; a missing, unreadable or too small read (naming
            the folder and the box to read), or a read of another world.
        RouteError: lava or water in a frame or landing, or no Nether level that fits.
        VerifyError: a layer breaks the emitter's checks or, outside a preview, the projected pair
            fails its checks or replaces player blocks without the matching token.
    """
    if preview and standalone:
        raise ValueError("--standalone writes plan.toon, which a preview never writes: drop --preview or --standalone")
    first_phase = integer_level(first_phase, "first_phase")
    if first_phase < 1:
        raise ValueError("first_phase must be positive")
    project = Path(project)
    element = design.element
    sites = _load_reads(design, project)
    design = fit_nether(design, sites["nether"])
    boxes = read_boxes(design)
    for dim in DIMENSIONS:
        if not _contained(sites[dim].box, boxes[dim]):
            raise ValueError(f"{dim} read site/{element}-{dim} covers {list(sites[dim].box)}, which does not "
                             f"contain {list(boxes[dim])} (the Nether end is at level "
                             f"{frame_origin(design, 'nether')[1]}); read that box again")
    rows: list[dict] = []
    payloads: list[tuple[Path, dict]] = []
    finals: dict[str, Site] = {}
    touched: list[dict] = []
    for dim in DIMENSIONS:
        site = sites[dim]
        layers = portal_layers(design, dim, site)
        tiles = check_form_layers(site, layers, max_columns=max_columns)
        finals[dim] = blocks.apply_writes(site, layers)
        for item in blocks.touched_blocks(site, layers, _why(design, dim), natural=natural_for(dim)):
            touched.append({**item, "world": site.world})
        counters: dict[str, int] = {}
        for mode, tile in tiles:
            fills = greedy_fills(tile)
            counters[mode] = counters.get(mode, 0) + 1
            name = f"{element}-{dim}-{mode}-{counters[mode]}"
            phase_id = first_phase + len(rows)
            file = f"phases/{phase_id:02d}-{name}.json"
            payloads.append((project / file, {"fills": fills, "liquids": "static", "world": site.world}))
            rows.append({"id": phase_id, "name": name, "file": file, "blocks": int(np.count_nonzero(tile.codes)),
                         "from": [min(f["from"][i] for f in fills) for i in range(3)],
                         "to": [max(f["to"][i] for f in fills) for i in range(3)],
                         "via": "placer", "rollback": "backup", "world": site.world})
    check = check_portal(design, finals)
    token = blocks.built_token(touched)
    by_block: dict[str, int] = {}
    for item in touched:
        by_block[base_id(item["block"])] = by_block.get(base_id(item["block"]), 0) + 1
    built = {"token": token, "count": len(touched), "by_block": by_block,
             "loses_data": sum(1 for item in touched if item.get("loses_data")), "items": touched}
    ends = {dim: {"world": _end_of(design, dim).world, "at": list(frame_origin(design, dim)),
                  "axis": _end_of(design, dim).axis, "existing": _end_of(design, dim).existing}
            for dim in DIMENSIONS}
    report = {"ends": ends, "size": list(design.size), "check": check, "built": built,
              "boxes": [list(boxes[d]) for d in DIMENSIONS],
              "reads": [{"section": d, "box": list(boxes[d]), "out": f"site/{element}-{d}",
                         "world": _end_of(design, d).world} for d in DIMENSIONS]}
    report_path = _report_path(design, project)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    notes = [(f"portal design terrain/{element}.portal.json: {design.size[0]} x {design.size[1]} frame, axis "
              f"{design.overworld.axis}, style {design.style}, seed {design.seed}"),
             "; ".join(f"{d} frame corner {frame_origin(design, d)} in {_end_of(design, d).world}"
                       for d in DIMENSIONS),
             "projected check: " + "; ".join(f"{c['name']} {'ok' if c['ok'] else 'FAILS'}: {c['detail']}"
                                             for c in check["checks"])]
    blocks_text = ", ".join(f"{n} {b}" for b, n in by_block.items())
    if touched:
        notes.append(f"touches {len(touched)} player blocks ({blocks_text}); approval token {token}; "
                     f"list in terrain/{element}.portal-report.json")
    walked = [r for r in rows if r["world"] == design.overworld.world] or rows
    bbox = _union([(*r["from"], *r["to"]) for r in walked]) if walked else boxes["overworld"]
    quality: dict[str, list[dict]] = {"transit": [{"file": f"terrain/{element}.portal.json"}],
                                      "surface_match": [], "seam": []}
    result = {"preview": preview, "phases": rows, "bbox": list(bbox), "notes": notes, "report": report,
              "quality": quality}
    if preview:
        return result
    failed = [c for c in check["checks"] if not c["ok"]]
    if failed:
        raise VerifyError("the portal pair fails its own checks: "
                          + "; ".join(f"{c['name']}: {c['detail']}" for c in failed)
                          + f" (cells in {report_path}). Revise the design")
    if touched and approve_built != token:
        raise VerifyError(f"the pair touches {len(touched)} player blocks ({blocks_text}): show the user each "
                          f"block, where it is and why ({report_path}), and only after their yes rerun with "
                          f"--approve-built {token}")
    design_path = project / "terrain" / f"{element}.portal.json"
    if design.source and (not design_path.exists()
                          or json.loads(design_path.read_text(encoding="utf-8")) != design.source):
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(json.dumps(design.source, indent=2) + "\n", encoding="utf-8")
        notes.append(f"copied the design to terrain/{element}.portal.json, where the plan's transit row points")
    for path, payload in payloads:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    snippet = plan_rows_toon(EmitResult(rows, quality, notes, bbox, None, None))  # type: ignore[arg-type]
    (project / "terrain" / f"{element}.plan-rows.toon").write_text(snippet, encoding="utf-8")
    if standalone:
        centre = [int((bbox[i] + bbox[i + 3]) // 2) for i in range(3)]
        lines = ["plan:", f"  project: {project.resolve().name}", "  skill: system-transit",
                 f"  world: {design.overworld.world}",
                 f"  anchor: {{x: {centre[0]}, y: {centre[1]}, z: {centre[2]}}}",
                 f"  bbox: {{from: {list(bbox[:3])}, to: {list(bbox[3:])}}}",
                 f"  summary: {element} (portal pair)", "  approved: no"]
        (project / "plan.toon").write_text("\n".join(lines) + "\n" + snippet, encoding="utf-8")
    return result
