"""Plan-view routes for transit lines: straight axis legs or an A* search over a heights grid.

``search_cells`` finds a cell path from the line's start to its end through its via points.
Rail and ice move along axes only and pay a corner penalty; road and path move on eight
neighbours and are smoothed. A grid over 250,000 columns is searched coarse first, then
refined at full resolution inside a band around the coarse path.
"""
from __future__ import annotations

import heapq
import math
import warnings
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np

from .site import load_heights
from .transit_design import LineDesign

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
