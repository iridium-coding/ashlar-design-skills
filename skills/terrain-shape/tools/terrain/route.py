"""Plan-view routes for transit lines: straight axis legs or an A* search over a heights grid.

``search_cells`` finds a cell path from the line's start to its end through its via points.
Rail and ice move along axes only and pay a corner penalty; road and path move on eight
neighbours and are smoothed. A grid over 250,000 columns is searched coarse first, then
refined at full resolution inside a band around the coarse path.

``fit_profile`` then picks a running level for every cell by dynamic programming over
candidate levels under the mode's grade rules, and ``classify`` classes each cell as
grade, cut, fill, bridge or tunnel, growing short bridges and turning short shallow
tunnels into cuts.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import warnings
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np

from .site import load_heights
from .transit_design import LineDesign, formation_half

COARSE_LIMIT = 250_000
CORNER_PENALTY = 12.0
WATER_PENALTY = 6.0
AVOID_GROW = 2
_AXES = ((1, 0), (0, 1), (-1, 0), (0, -1))
_EIGHT = _AXES + ((1, 1), (-1, 1), (-1, -1), (1, -1))


class RouteError(ValueError):
    """A route cannot be found or an endpoint is unusable."""


@dataclass
class Grid:
    origin: tuple[int, int]
    ground: np.ndarray
    surface: np.ndarray
    top: np.ndarray

    def index(self, x: int, z: int) -> tuple[int, int] | None:
        i, j = x - self.origin[0], z - self.origin[1]
        nx, nz = self.ground.shape
        return (i, j) if 0 <= i < nx and 0 <= j < nz else None


def grid_from_heights(heights: dict) -> Grid:
    """Build a Grid from an F2 heights dict (``origin``, ``size``, flat ``ground``/``surface``/``top``)."""
    nx, nz = (int(v) for v in heights["size"])

    def arr(name: str) -> np.ndarray:
        values = heights[name]
        if len(values) != nx * nz:
            raise ValueError(f"{name} has {len(values)} entries, expected {nx * nz}")
        return np.array([np.nan if v is None else v for v in values], dtype=float).reshape(nx, nz)

    return Grid((int(heights["origin"][0]), int(heights["origin"][1])), arr("ground"), arr("surface"), arr("top"))


def load_grid(path: Path) -> Grid:
    h = load_heights(path)
    return Grid(h["origin"], h["ground"], h["surface"], h["top"])


# ------------------------------------------------------------------ straight
def _corners(cells: list[tuple[int, int]]) -> list[int]:
    out = []
    for i in range(1, len(cells) - 1):
        a, b, c = cells[i - 1], cells[i], cells[i + 1]
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            out.append(i)
    return out


def _axis_leg(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Cells from `a` to `b` along x first, then z (one corner), both ends included."""
    cells = [a]
    x, z = a
    while x != b[0]:
        x += 1 if b[0] > x else -1
        cells.append((x, z))
    while z != b[1]:
        z += 1 if b[1] > z else -1
        cells.append((x, z))
    return cells


def _points(design: LineDesign) -> list[tuple[int, int]]:
    return [(design.start.x, design.start.z), *design.via, (design.end.x, design.end.z)]


def straight_cells(design: LineDesign) -> tuple[list[tuple[int, int]], list[int]]:
    cells: list[tuple[int, int]] = []
    pts = _points(design)
    for a, b in pairwise(pts):
        leg = _axis_leg(a, b)
        cells.extend(leg[1:] if cells else leg)
    return cells, _corners(cells)


# -------------------------------------------------------------------- search
def _blocked_mask(design: LineDesign, grid: Grid) -> np.ndarray:
    blocked = np.isnan(grid.ground)
    nx, nz = grid.ground.shape
    ox, oz = grid.origin
    for x1, z1, x2, z2 in design.avoid:
        xa, xb = max(x1 - AVOID_GROW - ox, 0), min(x2 + AVOID_GROW - ox, nx - 1)
        za, zb = max(z1 - AVOID_GROW - oz, 0), min(z2 + AVOID_GROW - oz, nz - 1)
        if xa <= xb and za <= zb:
            blocked[xa:xb + 1, za:zb + 1] = True
    return blocked


def _check_point(label: str, x: int, z: int, grid: Grid, blocked: np.ndarray) -> tuple[int, int]:
    idx = grid.index(x, z)
    if idx is None:
        raise RouteError(f"{label} ({x}, {z}) is outside the heights grid")
    if np.isnan(grid.ground[idx]):
        raise RouteError(f"{label} ({x}, {z}) is on a null column")
    if blocked[idx]:
        raise RouteError(f"{label} ({x}, {z}) is inside an avoid box (boxes are grown by {AVOID_GROW})")
    return idx


def _astar(ground: np.ndarray, water: np.ndarray, allowed: np.ndarray, start: tuple[int, int],
           goal: tuple[int, int], axes_only: bool) -> list[tuple[int, int]] | None:
    nx, nz = ground.shape
    g = ground.tolist()
    w = water.tolist()
    ok = allowed.tolist()
    moves = _AXES if axes_only else _EIGHT
    nd = len(moves) + 1  # last direction slot = "no previous direction"
    gx, gz = goal

    def h(i: int, j: int) -> float:
        dx, dz = abs(i - gx), abs(j - gz)
        return dx + dz if axes_only else math.hypot(dx, dz)

    def slope(i: int, j: int, dx: int, dz: int) -> float:
        px, pz = -dz, dx
        ai, aj, bi, bj = i + px, j + pz, i - px, j - pz
        if 0 <= ai < nx and 0 <= aj < nz and 0 <= bi < nx and 0 <= bj < nz:
            ga, gb = g[ai][aj], g[bi][bj]
            if not (math.isnan(ga) or math.isnan(gb)):
                return abs(ga - gb) / 2
        return 0.0

    start_state = (start[0], start[1], nd - 1)
    best = {start_state: 0.0}
    parent: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    heap = [(h(*start), 0, start_state)]
    tick = 0
    while heap:
        _f, _, state = heapq.heappop(heap)
        i, j, d = state
        cost = best[state]
        if _f - h(i, j) > cost + 1e-9:
            continue
        if (i, j) == goal:
            path = [(i, j)]
            while state in parent:
                state = parent[state]
                path.append((state[0], state[1]))
            return path[::-1]
        gv = g[i][j]
        for k, (dx, dz) in enumerate(moves):
            ni, nj = i + dx, j + dz
            if not (0 <= ni < nx and 0 <= nj < nz) or not ok[ni][nj]:
                continue
            if dx and dz and not ok[i + dx][j] and not ok[i][j + dz]:
                continue  # no diagonal squeezing between two blocked cells
            ng = g[ni][nj]
            step = math.hypot(dx, dz) * (1 + 0.5 * abs(ng - gv) + 0.3 * slope(ni, nj, dx, dz))
            if w[ni][nj]:
                step += WATER_PENALTY
            if axes_only and d != nd - 1 and d != k:
                step += CORNER_PENALTY
            nstate = (ni, nj, k if axes_only else nd - 1)
            ncost = cost + step
            if ncost < best.get(nstate, math.inf):
                best[nstate] = ncost
                parent[nstate] = state
                tick += 1
                heapq.heappush(heap, (ncost + h(ni, nj), tick, nstate))
    return None


def _water(grid: Grid) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return grid.surface > grid.ground


def _coarsen(grid: Grid, blocked: np.ndarray, f: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nx, nz = grid.ground.shape
    cx, cz = -(-nx // f), -(-nz // f)

    def pad(a: np.ndarray, fill) -> np.ndarray:
        out = np.full((cx * f, cz * f), fill, dtype=a.dtype)
        out[:nx, :nz] = a
        return out

    def blocks(a: np.ndarray) -> np.ndarray:
        return a.reshape(cx, f, cz, f)

    g = pad(grid.ground, np.nan)
    s = pad(grid.surface, np.nan)
    pad_null = pad(np.zeros((nx, nz), dtype=bool), True)  # padded cells are not real columns
    any_null = blocks(np.isnan(g) & ~pad_null).any(axis=(1, 3))
    real = blocks(~pad_null).any(axis=(1, 3))
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-null blocks have no mean
        gm = np.nanmean(blocks(g), axis=(1, 3))
        sm = np.nanmean(blocks(s), axis=(1, 3))
    gm = np.where(any_null | ~real, np.nan, gm)
    cblocked = blocks(pad(blocked, False)).any(axis=(1, 3)) | any_null | ~real
    return gm, np.where(np.isnan(sm), gm, sm), ~cblocked


def _leg_path(a: tuple[int, int], b: tuple[int, int], grid: Grid, blocked: np.ndarray, water: np.ndarray,
              axes_only: bool, what: str) -> list[tuple[int, int]]:
    nx, nz = grid.ground.shape
    allowed = ~blocked
    columns = nx * nz
    if columns > COARSE_LIMIT:
        f = math.ceil(math.sqrt(columns / COARSE_LIMIT))
        cg, cs, callowed = _coarsen(grid, blocked, f)
        ca, cb = (a[0] // f, a[1] // f), (b[0] // f, b[1] // f)
        for cell in (ca, cb):  # forced-open endpoint blocks need a finite ground
            callowed[cell] = True
            if np.isnan(cg[cell]):
                real = grid.ground[cell[0] * f:(cell[0] + 1) * f, cell[1] * f:(cell[1] + 1) * f]
                cg[cell] = cs[cell] = np.nanmean(real)
        coarse = _astar(cg, cs > cg, callowed, ca, cb, axes_only)
        if coarse is None:
            raise RouteError(f"no route {what}: null columns, avoid boxes or the grid edge block every path")
        half = 2 * f + 16
        band = np.zeros((nx, nz), dtype=bool)
        for ci, cj in coarse:
            i, j = ci * f + f // 2, cj * f + f // 2
            band[max(i - half, 0):i + half + 1, max(j - half, 0):j + half + 1] = True
        allowed = allowed & band
    path = _astar(grid.ground, water, allowed, a, b, axes_only)
    if path is None:
        raise RouteError(f"no route {what}: null columns, avoid boxes or the grid edge block every path")
    return path


def _chaikin(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [points[0]]
    for (x0, z0), (x1, z1) in pairwise(points):
        out.append((0.75 * x0 + 0.25 * x1, 0.75 * z0 + 0.25 * z1))
        out.append((0.25 * x0 + 0.75 * x1, 0.25 * z0 + 0.75 * z1))
    out.append(points[-1])
    return out


def _rasterise(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    cells = [(round(points[0][0]), round(points[0][1]))]
    for x, z in points[1:]:
        tx, tz = round(x), round(z)
        cx, cz = cells[-1]
        while (cx, cz) != (tx, tz):
            cx += (tx > cx) - (tx < cx)
            cz += (tz > cz) - (tz < cz)
            cells.append((cx, cz))
    return cells


def _smooth(path: list[tuple[int, int]], allowed: np.ndarray) -> list[tuple[int, int]]:
    if len(path) < 3:
        return path
    pts: list[tuple[float, float]] = [(float(i), float(j)) for i, j in path]
    for _ in range(2):
        pts = _chaikin(pts)
    smooth = _rasterise(pts)
    nx, nz = allowed.shape
    if smooth[0] != path[0] or smooth[-1] != path[-1]:
        return path
    if not all(0 <= i < nx and 0 <= j < nz and allowed[i, j] for i, j in smooth):
        return path
    return smooth


def search_cells(design: LineDesign, grid: Grid) -> tuple[list[tuple[int, int]], list[int]]:
    blocked = _blocked_mask(design, grid)
    water = _water(grid)
    axes_only = design.mode in ("rail", "ice")
    labelled = [("from", *_points(design)[0])]
    labelled += [("via", x, z) for x, z in design.via]
    labelled.append(("to", design.end.x, design.end.z))
    idx = [_check_point(label, x, z, grid, blocked) for label, x, z in labelled]
    path: list[tuple[int, int]] = []
    for n, (a, b) in enumerate(pairwise(idx)):
        what = f"from ({labelled[n][1]}, {labelled[n][2]}) to ({labelled[n + 1][1]}, {labelled[n + 1][2]})"
        leg = _leg_path(a, b, grid, blocked, water, axes_only, what)
        if not axes_only:
            leg = _smooth(leg, ~blocked)
        path.extend(leg[1:] if path else leg)
    ox, oz = grid.origin
    cells = [(i + ox, j + oz) for i, j in path]
    return cells, (_corners(cells) if axes_only else [])


# ------------------------------------------------------------------- profile
BRIDGE_COST = 56.0  # flat per bridge cell so a deck stays level; under a rail fill at max_fill (72)
TUNNEL_COST = 60.0
SMOOTHING = 0.2
RAIL_CLIMB_COST = 5.0  # per block of rail rise or fall: climbs carry a booster every 2nd cell
TERMINUS_CELLS = 11    # a rail terminus's 8 quiet cells and its 3-cell launch group run level
LEVEL_RANGE = (-60, 315)
_GRADE_RULE = {"rail": "a rail moves at most 1 block per cell, runs level through a corner and over the "
                       f"{TERMINUS_CELLS} cells at a terminus, and a dip bottoms out over at least 2 level cells",
               "road": "a road moves at most half a block per cell",
               "path": "a path moves at most 1 block per cell",
               "ice": "an ice line stays level"}


def _unit(design: LineDesign) -> float:
    """The level step: half blocks (slabs) for a road, whole blocks otherwise."""
    return 0.5 if design.mode == "road" else 1.0


def _cover(design: LineDesign) -> int:
    """How far below ``ground + 1`` a level must be for the bore, its lining and ``roof`` rock to fit."""
    return design.tunnels.height + 1 + design.tunnels.roof


def _where(cells: list[tuple[int, int]], i: int) -> str:
    x, z = cells[i]
    return f"cell {i} ({x}, {z})"


def _route_heights(cells: list[tuple[int, int]], grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    """Ground and surface under each cell; a null surface reads as the ground."""
    xz = np.asarray(cells, dtype=int).reshape(-1, 2)
    i, j = xz[:, 0] - grid.origin[0], xz[:, 1] - grid.origin[1]
    nx, nz = grid.ground.shape
    inside = (i >= 0) & (i < nx) & (j >= 0) & (j < nz)
    if not inside.all():
        raise RouteError(f"{_where(cells, int(np.argmin(inside)))} is outside the heights grid")
    ground = grid.ground[i, j]
    if np.isnan(ground).any():
        raise RouteError(f"{_where(cells, int(np.argmax(np.isnan(ground))))} is on a null column")
    surface = grid.surface[i, j]
    return ground, np.where(np.isnan(surface), ground, surface)


def _fixed_levels(design: LineDesign, cells: list[tuple[int, int]], unit: float) -> dict[int, float]:
    """Hard levels by chainage index: endpoints with a y, then the design's profile points."""
    n = len(cells)
    wanted: list[tuple[str, int, float]] = []
    if design.start.y is not None:
        wanted.append(("from", 0, design.start.y))
    if design.end.y is not None:
        wanted.append(("to", n - 1, design.end.y))
    wanted += [("profile", index, level) for index, level in design.profile]
    fixed: dict[int, float] = {}
    for what, index, level in wanted:
        if index >= n:
            raise RouteError(f"{what} point at chainage {index} is past the route's last cell {n - 1}")
        where = _where(cells, index)
        if not (level / unit).is_integer():
            raise RouteError(f"{what} level {level:g} at {where} is not a multiple of {unit:g}")
        if not LEVEL_RANGE[0] <= level <= LEVEL_RANGE[1]:
            raise RouteError(f"{what} level {level:g} at {where} is outside {LEVEL_RANGE[0]}..{LEVEL_RANGE[1]}")
        if index in fixed and fixed[index] != level:
            raise RouteError(f"{what} level {level:g} at {where} conflicts with level {fixed[index]:g}")
        fixed[index] = float(level)
    return fixed


def _candidates(design: LineDesign, ground: np.ndarray, surface: np.ndarray, fixed: dict[int, float],
                unit: float) -> np.ndarray:
    """Candidate levels in steps of `unit`, from below the deepest bore to above the highest deck."""
    lim, tun = design.limits, design.tunnels
    lo = float(ground.min()) - lim.max_cut - tun.height - tun.roof - 2
    hi = float(surface.max()) + lim.max_fill + lim.water_clearance + 2
    if fixed:
        lo, hi = min(lo, *fixed.values()), max(hi, *fixed.values())
    lo = max(math.floor(lo / unit) * unit, LEVEL_RANGE[0])
    hi = min(math.ceil(hi / unit) * unit, LEVEL_RANGE[1])
    return lo + unit * np.arange(round((hi - lo) / unit) + 1)


def _cell_costs(design: LineDesign, levels: np.ndarray, ground: np.ndarray, surface: np.ndarray) -> np.ndarray:
    """Cost of each candidate level (columns) at each cell (rows); inf over water without clearance."""
    lim = design.limits
    width = 2 * formation_half(design)
    d = levels[None, :] - (ground[:, None] + 1)
    fill, cut = np.maximum(d, 0), np.maximum(-d, 0)
    cost = fill * (width + fill * lim.fill_ratio) + cut * (width + cut * lim.cut_ratio)
    cost = np.where(d > lim.max_fill, BRIDGE_COST, cost)
    cost = np.where((d < -lim.max_cut) & (-d >= _cover(design)), TUNNEL_COST, cost)
    water = (surface > ground)[:, None]
    clear = levels[None, :] >= (surface + 1 + lim.water_clearance)[:, None]
    return np.where(water, np.where(clear, BRIDGE_COST, np.inf), cost)


def _unreachable(design: LineDesign, cells: list[tuple[int, int]], i: int, fixed: dict[int, float],
                 ground: np.ndarray, surface: np.ndarray) -> RouteError:
    where, rule = _where(cells, i), _GRADE_RULE[design.mode]
    if i in fixed:
        before = [j for j in fixed if j < i]
        if before:
            j = max(before)
            return RouteError(f"cannot reach level {fixed[i]:g} at {where} from level {fixed[j]:g} "
                              f"at {_where(cells, j)}: {rule}")
        return RouteError(f"cannot reach level {fixed[i]:g} at {where}: {rule}")
    if surface[i] > ground[i]:
        wc = design.limits.water_clearance
        return RouteError(f"cannot reach level {surface[i] + 1 + wc:g} at {where} over water at surface "
                          f"{surface[i]:g} (water_clearance {wc}): {rule}")
    return RouteError(f"cannot reach any level at {where}: {rule}")


def _level_only(design: LineDesign, n: int, corners: list[int]) -> np.ndarray:
    """``level_only[i]``: no change of level from cell i - 1 to cell i.

    Ice runs level end to end. A rail corner and its two neighbours share a level, and so do
    the ``TERMINUS_CELLS`` cells at a rail terminus, so its platform is level and a rider can
    leave a terminus at the bottom of a climb.
    """
    level_only = np.full(n, design.mode == "ice")
    if design.mode == "rail":
        for c in corners:
            level_only[c:c + 2] = True
        if design.start.stop == "terminus":
            level_only[1:TERMINUS_CELLS] = True
        if design.end.stop == "terminus":
            level_only[max(n - TERMINUS_CELLS + 1, 0):] = True
    return level_only


_FALL, _LEVEL, _RISE = 0, 1, 2   # the step into a cell; a candidate index moves by state - 1
_PREFER = (_LEVEL, _RISE, _FALL)  # on equal cost: staying level, then a rise, then a fall


def _cheapest(best: np.ndarray, states: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Per candidate, the least cost over `states` of `best` and the state it came from (ties: ``_PREFER``)."""
    cost = np.full(best.shape[1], np.inf)
    came = np.full(best.shape[1], _LEVEL, dtype=np.int8)
    for s in (s for s in _PREFER if s in states):
        better = best[s] < cost
        cost[better] = best[s][better]
        came[better] = s
    return cost, came


def _solve(design: LineDesign, cells: list[tuple[int, int]], corners: list[int], costs: np.ndarray,
           levels: np.ndarray, fixed: dict[int, float], ground: np.ndarray, surface: np.ndarray,
           unit: float) -> np.ndarray:
    """Least-cost level path through `costs` with steps of at most one candidate (none where level).

    The program keeps, for every candidate level, the best path arriving by a fall, level or by
    a rise. A rail never rises straight out of a fall: one rail cannot ascend toward both its
    neighbours, so a dip bottoms out over at least two level cells (a one-cell crest is fine).
    """
    n, k_count = costs.shape
    level_only = _level_only(design, n, corners)
    rail = design.mode == "rail"
    move = (SMOOTHING + (RAIL_CLIMB_COST if rail else 0.0)) * unit
    every = (_FALL, _LEVEL, _RISE)
    best = np.full((3, k_count), np.inf)  # best[s, k]: least cost to (i, k), arriving by step state s
    best[_LEVEL] = costs[0]
    back = np.zeros((n, 3, k_count), dtype=np.int8)  # back[i, s, k]: the step state at cell i - 1
    if not np.isfinite(best).any():
        raise _unreachable(design, cells, 0, fixed, ground, surface)
    for i in range(1, n):
        new = np.full((3, k_count), np.inf)
        stay, came = _cheapest(best, every)
        new[_LEVEL], back[i, _LEVEL] = stay + costs[i], came
        if not level_only[i]:
            up, up_came = _cheapest(best, (_LEVEL, _RISE) if rail else every)
            new[_RISE, 1:], back[i, _RISE, 1:] = up[:-1] + move + costs[i, 1:], up_came[:-1]
            new[_FALL, :-1], back[i, _FALL, :-1] = stay[1:] + move + costs[i, :-1], came[1:]
        best = new
        if not np.isfinite(best).any():
            raise _unreachable(design, cells, i, fixed, ground, surface)
    low = best.min(axis=0)
    k = int(np.argmin(low))
    s = next(s for s in _PREFER if best[s, k] == low[k])
    path = np.empty(n, dtype=int)
    path[-1] = k
    for i in range(n - 1, 0, -1):
        s, k = int(back[i, s, k]), k - (s - 1)
        path[i - 1] = k
    return levels[path]


def _level_line(design: LineDesign, n: int) -> tuple[list[float], list[str]]:
    y = design.start.y
    if y is None or design.end.y != y:
        raise RouteError("a line without heights runs level: from and to need the same level (at y)")
    for index, level in design.profile:
        if level != y:
            raise RouteError(f"a line without heights runs level at {y}; "
                             f"profile level {level:g} at chainage {index} differs")
    return [float(y)] * n, ["tunnel"] * n


def fit_profile(design: LineDesign, cells: list[tuple[int, int]], corners: list[int],
                grid: Grid | None) -> tuple[list[float], list[str]]:
    """Running levels and stretch kinds along a route's cells.

    Levels follow the conventions of ``levels[i]`` (rail cell y, road surface top in half
    blocks, path and ice in whole blocks). A dynamic program over candidate levels minimises
    cut and fill (weighted by the formation width and slope ratios), bridge and tunnel costs,
    a small cost per level change (plus boosters on rail climbs, ``RAIL_CLIMB_COST``),
    under the mode's grade rules: rail and path move at most a block per cell, a rail
    corner and its neighbours share a level, so do the ``TERMINUS_CELLS`` cells at a rail
    terminus, a rail dip bottoms out over at least two level cells, a road moves in half
    blocks, ice stays level.
    Endpoints with a y and the design's profile points are hard constraints; a null endpoint
    y is fitted. With no grid (a straight underground or Nether line) every cell runs at the
    endpoints' shared level and is a tunnel until the section reads class it.

    Raises:
        RouteError: a fixed level cannot be reached (naming the cell), a cell is off the
            grid or on a null column, or a short tunnel too deep to cut cannot grow.
    """
    if not cells:
        raise RouteError("the route has no cells")
    if grid is None:
        return _level_line(design, len(cells))
    ground, surface = _route_heights(cells, grid)
    unit = _unit(design)
    fixed = _fixed_levels(design, cells, unit)
    levels = _candidates(design, ground, surface, fixed, unit)
    costs = _cell_costs(design, levels, ground, surface)
    for i, level in fixed.items():
        k = round((level - levels[0]) / unit)
        keep = costs[i, k]
        if not np.isfinite(keep):
            need = surface[i] + 1 + design.limits.water_clearance
            raise RouteError(f"cannot reach level {level:g} at {_where(cells, i)} over water at surface "
                             f"{surface[i]:g}: it needs level {need:g} or more (water_clearance)")
        costs[i] = np.inf
        costs[i, k] = keep
    fitted = [float(v) for v in _solve(design, cells, corners, costs, levels, fixed, ground, surface, unit)]
    return fitted, classify(design, fitted, ground.tolist(), surface.tolist())


# ------------------------------------------------------------------ classify
def _run_from(kinds: list[str], kind: str, start: int) -> tuple[int, int] | None:
    """The whole run of `kind` holding the first such cell at or after `start`."""
    n = len(kinds)
    a = start
    while a < n and kinds[a] != kind:
        a += 1
    if a == n:
        return None
    b = a
    while a > 0 and kinds[a - 1] == kind:
        a -= 1
    while b + 1 < n and kinds[b + 1] == kind:
        b += 1
    return a, b


def _grow(a: int, b: int, length: int, n: int, ok) -> tuple[int, int]:
    """Widen ``[a, b]`` a cell at a time, alternating sides, onto cells `ok` allows, up to `length`."""
    left = True
    while b - a + 1 < length:
        can_left, can_right = a > 0 and ok(a - 1), b < n - 1 and ok(b + 1)
        if not (can_left or can_right):
            break
        if can_left and (left or not can_right):
            a -= 1
        else:
            b += 1
        left = not left
    return a, b


def _merge_tunnels(design: LineDesign, kinds: list[str], depth: np.ndarray) -> None:
    lim, cover, n = design.limits, _cover(design), len(kinds)

    def covered(j: int) -> bool:
        return kinds[j] != "bridge" and depth[j] >= cover

    i = 0
    while (run := _run_from(kinds, "tunnel", i)) is not None:
        a, b = run
        if b - a + 1 < lim.min_tunnel:
            deepest = float(depth[a:b + 1].max())
            if deepest <= 2 * lim.max_cut:
                kinds[a:b + 1] = ["cut"] * (b - a + 1)
            else:
                ga, gb = _grow(a, b, lim.min_tunnel, n, covered)
                if gb - ga + 1 < lim.min_tunnel:
                    raise RouteError(
                        f"tunnel at cells {a}-{b} is {b - a + 1} long, under min_tunnel {lim.min_tunnel}; "
                        f"its {deepest:g}-block cut is deeper than 2 * max_cut ({2 * lim.max_cut}) and "
                        "the cover does not allow a longer bore")
                kinds[ga:gb + 1] = ["tunnel"] * (gb - ga + 1)
                b = gb
        i = b + 1


def _merge_bridges(design: LineDesign, kinds: list[str]) -> None:
    lim, n = design.limits, len(kinds)

    def open_cell(j: int) -> bool:
        return kinds[j] != "tunnel"

    i = 0
    while (run := _run_from(kinds, "bridge", i)) is not None:
        a, b = run
        if b - a + 1 < lim.min_bridge:
            a, b = _grow(a, b, lim.min_bridge, n, open_cell)
            kinds[a:b + 1] = ["bridge"] * (b - a + 1)
        i = b + 1


def classify(design: LineDesign, levels: list[float], ground: list[float], surface: list[float]) -> list[str]:
    """Class each cell from its level `d = level - (ground + 1)`, then merge short stretches.

    bridge: over water (``surface > ground``) or ``d > max_fill``; tunnel: ``d < -max_cut``
    with room for the bore and ``roof`` above it; grade: ``|d| <= 1``; fill: ``d > 1``;
    cut: ``d < -1``. A tunnel shorter than ``min_tunnel`` becomes a cut when its deepest cut
    is at most ``2 * max_cut``, else grows to ``min_tunnel`` where the cover allows. A bridge
    shorter than ``min_bridge`` grows to it, alternating sides, inside the route.

    Raises:
        RouteError: naming a short tunnel stretch too deep to cut that cannot grow.
    """
    if not len(levels) == len(ground) == len(surface):
        raise ValueError(f"levels, ground and surface differ in length: "
                         f"{len(levels)}, {len(ground)}, {len(surface)}")
    lim = design.limits
    g = np.asarray(ground, dtype=float)
    d = np.asarray(levels, dtype=float) - (g + 1)
    with np.errstate(invalid="ignore"):
        water = np.asarray(surface, dtype=float) > g
    kinds = np.full(len(d), "grade", dtype=object)
    kinds[d > 1] = "fill"
    kinds[d < -1] = "cut"
    kinds[(d < -lim.max_cut) & (-d >= _cover(design))] = "tunnel"
    kinds[water | (d > lim.max_fill)] = "bridge"
    out = [str(k) for k in kinds]
    _merge_tunnels(design, out, -d)
    _merge_bridges(design, out)
    return out


# ------------------------------------------------------------------ sections
@dataclass
class Section:
    name: str
    start: int
    end: int
    box: tuple[int, int, int, int, int, int]
    world: str | None


@dataclass
class Route:
    element: str
    mode: str
    world: str | None
    dimension: str
    design_hash: str
    cells: list[tuple[int, int]]
    levels: list[float]
    kinds: list[str]
    ground: list[float | None]
    surface: list[float | None]
    corners: list[int]
    sections: list[Section]


HASH_KEYS = ("element", "world", "mode", "route", "from", "to", "via", "avoid", "profile", "limits",
             "width", "lanes")
Y_MIN, Y_MAX = -64, 319


def design_hash(design: LineDesign) -> str:
    """sha256[:12] of the route-relevant keys of the design file."""
    part = {k: design.source[k] for k in HASH_KEYS if k in design.source}
    return hashlib.sha256(json.dumps(part, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def make_sections(design: LineDesign, route: Route, grid: Grid | None) -> list[Section]:
    """Split a route into sections of ``section_length`` cells, each with its read box.

    With a heights grid, a box's floor lies 6 below the lowest ground under the whole box (or
    below the line, if that is lower), so every column of the read reaches its ground.
    """
    lim, tun = design.limits, design.tunnels
    reach = math.ceil(formation_half(design) + max(lim.max_fill * lim.fill_ratio,
                                                   lim.max_cut * lim.cut_ratio, tun.width) + 8)
    n, length = len(route.cells), design.section_length
    sections = []
    for k in range((n + length - 1) // length):
        a, b = k * length, min((k + 1) * length, n) - 1
        xs = [c[0] for c in route.cells[a:b + 1]]
        zs = [c[1] for c in route.cells[a:b + 1]]
        x1, x2, z1, z2 = min(xs) - reach, max(xs) + reach, min(zs) - reach, max(zs) + reach
        levels = route.levels[a:b + 1]
        if grid is None:
            y1, y2 = math.floor(min(levels)) - 6, math.ceil(max(levels)) + tun.height + 6
        else:
            ia, ja = x1 - grid.origin[0], z1 - grid.origin[1]
            nx, nz = grid.top.shape
            area = np.s_[max(ia, 0):max(min(x2 - grid.origin[0] + 1, nx), 0),
                         max(ja, 0):max(min(z2 - grid.origin[1] + 1, nz), 0)]
            under = grid.ground[area]
            under = under[~np.isnan(under)]
            low = min([float(under.min()) if under.size else math.inf, *(math.floor(v) - 1 for v in levels)])
            y1 = math.floor(low) - 6
            window = grid.top[area]
            window = window[~np.isnan(window)]
            top = float(window.max()) if window.size else -math.inf
            y2 = math.ceil(max(top + 2, max(levels) + tun.height + tun.roof + 2))
        sections.append(Section(f"s{k + 1:02d}", a, b,
                                (x1, max(y1, Y_MIN), z1, x2, min(y2, Y_MAX), z2), design.world))
    return sections


def plan_route(design: LineDesign, grid: Grid | None) -> Route:
    """Cells, profile, stretch kinds, ground and surface, corners and sections of a line."""
    cells, corners = straight_cells(design) if design.route == "straight" else search_cells(design, grid)
    levels, kinds = fit_profile(design, cells, corners, grid)
    ground: list[float | None] = [None] * len(cells)
    surface: list[float | None] = [None] * len(cells)
    if grid is not None:
        g, s = _route_heights(cells, grid)
        ground, surface = [float(v) for v in g], [float(v) for v in s]
    out = Route(design.element, design.mode, design.world, design.dimension, design_hash(design),
                list(cells), [float(v) for v in levels], list(kinds), ground, surface, list(corners), [])
    out.sections = make_sections(design, out, grid)
    return out


def write_route(route: Route, path: Path) -> None:
    Path(path).write_text(json.dumps(asdict(route), indent=1) + "\n", encoding="utf-8")


def load_route(path: Path) -> Route:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["cells"] = [tuple(c) for c in data["cells"]]
    data["sections"] = [Section(**{**s, "box": tuple(s["box"])}) for s in data["sections"]]
    return Route(**data)
