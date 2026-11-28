"""Corridor grading: shape the ground along a transit line and hand it to the terrain emitter.

Inside the formation the top block sits at ``floor(level) - 1``; beyond it a cut slope climbs
(and a fill slope descends) to meet the natural ground. Seeded noise on the slope ratio and
the toe line keeps the edges uneven. Each cross-section is graded from the formation edge out
to its catch point, the first column where the slope plane meets the ground; the ground beyond
is left alone, however it rises or falls. Only grade, cut and fill cells are graded; bridge,
tunnel and tube columns, columns beyond the section and columns the grading leaves unchanged are
protected, so the emitter keeps its liquid, gravity and seam checks and repaints nothing else.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

import numpy as np

from . import blocks
from .apron import _SURFACE
from .ashlar_emit import seam_ground
from .field import Centerline, HeightField
from .live import LiveWrite, materialize_live
from .materialize import MaterialSpec
from .noise import ValueNoise2D
from .route import Route, Section
from .site import Site, base_id, surfaces
from .transit_design import LineDesign, formation_half

GRADED = ("grade", "cut", "fill")
ROCK = frozenset("minecraft:" + b for b in ("stone", "deepslate", "andesite", "diorite", "granite", "tuff"))
FREQUENCY = 0.15
RATIO_NOISE = 0.25
TOE_NOISE = 1.5
EXTEND = 4          # cells of centerline kept past each section end
RING = 6            # width of the unchanged ring sampled for the surface palette
MAX_SINGLE = 0.85   # heaviest surface block; the emitter's monoculture check allows 92%
SUPPORT = {"minecraft:sand": "minecraft:sandstone", "minecraft:red_sand": "minecraft:red_sandstone",
           "minecraft:snow_block": "minecraft:stone"}
SOIL_SUPPORT = "minecraft:coarse_dirt"  # what any other top shows in its faces; plain dirt under coarse dirt
ROCK_SUPPORT = {"minecraft:stone": "minecraft:andesite"}    # any other rock shows stone


@dataclass
class CorridorPlan:
    field: HeightField
    protect: np.ndarray
    spec: MaterialSpec
    cut_cells: int
    fill_cells: int
    # Kept for outer_seam_rows: which columns changed and which way is outward from the line.
    changed: np.ndarray | None = None
    outward: np.ndarray | None = None
    origin: tuple[int, int] = (0, 0)


def _state_at(runs, y: int) -> str | None:
    for lo, hi, state in runs:
        if lo <= y <= hi:
            return state
    return None


def _centerline(route: Route, section: Section):
    """Centerline through the route's cells around the section and the route index of each vertex."""
    n = len(route.cells)
    lo, hi = max(section.start - EXTEND, 0), min(section.end + EXTEND, n - 1)
    idx = list(range(lo, hi + 1))
    pts = [(float(route.cells[i][0]), float(route.cells[i][1])) for i in idx]
    if lo == 0:
        a, b = route.cells[0], route.cells[min(1, n - 1)]
        step = (float(a[0] - b[0]), float(a[1] - b[1]))
        for k in range(1, EXTEND + 1):
            idx.insert(0, -k)
            pts.insert(0, (a[0] + step[0] * k, a[1] + step[1] * k))
    if hi == n - 1:
        a, b = route.cells[n - 1], route.cells[max(n - 2, 0)]
        step = (float(a[0] - b[0]), float(a[1] - b[1]))
        for k in range(1, EXTEND + 1):
            idx.append(n - 1 + k)
            pts.append((a[0] + step[0] * k, a[1] + step[1] * k))
    return Centerline(pts), np.array(idx, dtype=float), np.array(pts)


def _surface_weights(site: Site, ground: np.ndarray, changed: np.ndarray) -> dict[str, float] | None:
    """Normalised counts of the top blocks of the unchanged columns near the changed ground."""
    from scipy import ndimage

    ring = ndimage.binary_dilation(changed, iterations=RING) & ~changed
    if not ring.any():
        ring = ~changed
    x1, _, z1 = site.box[:3]
    counts: Counter[str] = Counter()
    under: dict[str, Counter[str]] = {}
    for i, j in np.argwhere(ring):
        g = ground[i, j]
        if not math.isfinite(g):
            continue
        runs = site.columns[(x1 + int(i), z1 + int(j))]
        state = _state_at(runs, int(g))
        if state is None or base_id(state) not in _SURFACE:
            continue
        block = base_id(state)
        counts[block] += 1
        below = _state_at(runs, int(g) - 1)
        if below is not None and base_id(below) in _SURFACE and base_id(below) != block:
            under.setdefault(block, Counter())[base_id(below)] += 1
    selected = counts.most_common(4)
    if not selected:
        return None
    total = sum(n for _, n in selected)
    weights = {block: n / total for block, n in selected}
    top, share = max(weights.items(), key=lambda kv: kv[1])
    if share > MAX_SINGLE:
        # A cut or fill face shows the layer under the surface, so the cap's remainder goes to it.
        weights[top] = MAX_SINGLE
        support = _support(top, under.get(top))
        weights[support] = weights.get(support, 0.0) + share - MAX_SINGLE
    return weights


def _support(top: str, under: Counter[str] | None) -> str:
    """The block a cut or fill face shows under the surface block `top`, never `top` itself.

    The commonest other block found under it, else the family table (`SUPPORT`), else another
    rock for a rock top, else coarse dirt (plain dirt under a coarse dirt top).
    """
    if under:
        return under.most_common(1)[0][0]
    if top in SUPPORT:
        return SUPPORT[top]
    if top in ROCK:
        return ROCK_SUPPORT.get(top, "minecraft:stone")
    return SOIL_SUPPORT if top != SOIL_SUPPORT else "minecraft:dirt"


def corridor_plan(design: LineDesign, route: Route, section: Section, site: Site) -> CorridorPlan:
    x1, y1, z1, x2, _, z2 = site.box
    nx, nz = x2 - x1 + 1, z2 - z1 + 1
    ground = surfaces(site).ground
    known = np.isfinite(ground)
    base = np.where(known, ground, float(y1))
    X, Z = np.meshgrid(np.arange(x1, x2 + 1, dtype=float), np.arange(z1, z2 + 1, dtype=float), indexing="ij")

    line, idx, pts = _centerline(route, section)
    s, perp = line.query(X, Z)
    cum = line.cumlen
    # The distance to the line. `perp` is the offset from the nearest segment's own line, which reads 0
    # beyond a vertex along a segment's extension (past the outside of a corner); there the nearest
    # point is the vertex itself.
    across = np.hypot(X - np.interp(s, cum, pts[:, 0]), Z - np.interp(s, cum, pts[:, 1]))
    near = np.rint(np.interp(s, cum, idx)).astype(int)
    levels = np.array([route.levels[min(max(int(i), 0), len(route.levels) - 1)] for i in idx])
    level = np.interp(s, cum, levels)
    kinds = np.array(route.kinds + ["off"], dtype=object)
    in_section = (near >= section.start) & (near <= section.end)
    graded = in_section & np.isin(kinds[np.clip(near, 0, len(route.kinds))], GRADED) & known

    f = np.floor(level) - 1
    noise = ValueNoise2D(design.seed)
    n_ratio = noise.sample(X * FREQUENCY, Z * FREQUENCY) * 2 - 1
    n_toe = ValueNoise2D(design.seed + 101).sample(X * FREQUENCY, Z * FREQUENCY) * 2 - 1
    half = formation_half(design)
    reach = np.maximum(across + TOE_NOISE * n_toe - half, 0.0)

    lim = design.limits
    fill_ratio = lim.fill_ratio * (1 + RATIO_NOISE * n_ratio)
    soil_ratio = lim.cut_ratio * (1 + RATIO_NOISE * n_ratio)
    rock_ratio = lim.rock_cut_ratio * (1 + RATIO_NOISE * n_ratio)
    rock = np.zeros((nx, nz), bool)
    for i, j in np.argwhere(graded & (base > f)):
        state = _state_at(site.columns[(x1 + int(i), z1 + int(j))], int(f[i, j]))
        rock[i, j] = state is not None and base_id(state) in ROCK
    cut_ratio = np.where(rock, rock_ratio, soil_ratio)
    lo = f - reach / fill_ratio
    hi = f + reach / cut_ratio
    slope = np.rint(np.minimum(np.maximum(base, lo), hi))
    # Each cross-section (the columns nearest one route cell, on one side) is graded out to its
    # catch point: the nearest column beyond the formation the slope leaves as it is.
    beyond = across > half
    key = (near - near.min()) * 2 + (perp > 0)
    catch = np.full(int(key.max()) + 1, np.inf)
    daylight = graded & beyond & (slope == base)
    np.minimum.at(catch, key[daylight], across[daylight])
    target = np.where(graded & (~beyond | (across < catch[key])), slope, base)

    changed = graded & (target != base)
    protect = ~changed
    field = HeightField(nx, nz, sea_level=float(np.floor(target.min())) - 8)
    field.h = target.astype(float)
    weights = _surface_weights(site, base, changed)
    spec = MaterialSpec.natural(field, surface=weights)
    spec.seed = design.seed

    # Outward axis direction of each column: the side of the line it lies on, along its normal.
    tangent = np.diff(pts, axis=0)
    tangent = tangent / np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-9)[:, None]
    mid = (cum[:-1] + cum[1:]) / 2
    tx, tz = np.interp(s, mid, tangent[:, 0]), np.interp(s, mid, tangent[:, 1])
    sign = np.where(perp >= 0, 1.0, -1.0)
    nxv, nzv = -tz * sign, tx * sign
    outward = np.where(np.abs(nxv) >= np.abs(nzv), np.where(nxv >= 0, 0, 1), np.where(nzv >= 0, 2, 3))
    return CorridorPlan(field, protect, spec, int((target < base)[changed].sum()),
                        int((target > base)[changed].sum()), changed, outward, (x1, z1))


def graded_site(design: LineDesign, route: Route, section: Section,
                site: Site) -> tuple[Site, LiveWrite | None, CorridorPlan]:
    plan = corridor_plan(design, route, section, site)
    if plan.protect.all():
        return site, None, plan
    write = materialize_live(plan.field, plan.spec, site, None, protect=plan.protect)
    return blocks.apply_writes(site, [("corridor", write)]), write, plan


# ------------------------------------------------------------------ seams
_DIRECTIONS = ("x", "-x", "z", "-z")


def outer_seam_rows(design: LineDesign, route: Route, section: Section, plan: CorridorPlan, final: Site,
                    occupied: Collection[tuple[int, int]] = frozenset()) -> tuple[list[dict], int]:
    """Seam rows where the graded ground meets the natural ground, measured on the projected `final`.

    On each side, the outermost changed column whose outward neighbour is unchanged meets the
    natural ground. A row runs along x or z at one across coordinate, perpendicular to its
    outward direction as ``terrain.py seam`` requires (a row of one column is allowed), over such
    columns where neither the column nor its outward neighbour is one the line stands on
    (`occupied`: its formation, kerbs, lamps, platforms and decks). Each row's ``max_step`` is the
    largest step ``seam_ground`` finds on `final` along it (at least 1). A point whose ground
    cannot be certified there (an unknown shape on top, or a neighbour outside the read) is left
    out; their count comes back with the rows. The ends of the section are not seamed: the next
    section grades the same ground.
    """
    changed, outward = plan.changed, plan.outward
    if changed is None or outward is None or not changed.any():
        return [], 0
    ox, oz = plan.origin
    nx, nz = changed.shape
    rows: list[dict] = []
    dropped = 0
    for code, name in enumerate(_DIRECTIONS):
        along_x = name in ("z", "-z")        # the seam runs along x when it faces z
        step = 1 if name[0] != "-" else -1
        dx, dz = (step, 0) if not along_x else (0, step)
        best: dict[int, int] = {}
        for i, j in np.argwhere(changed & (outward == code)):
            ni, nj = i + dx, j + dz
            if not (0 <= ni < nx and 0 <= nj < nz) or changed[ni, nj]:
                continue
            x, z = ox + int(i), oz + int(j)
            if (x, z) in occupied or (x + dx, z + dz) in occupied:
                continue
            key, val = (x, z) if along_x else (z, x)
            if key not in best or (val - best[key]) * step > 0:
                best[key] = val
        runs: list[list[tuple[int, int, int]]] = [[]]   # (key, across value, step) of each row
        for key in sorted(best):
            val = best[key]
            x, z = (key, val) if along_x else (val, key)
            try:
                found = abs(seam_ground(final, x, z) - seam_ground(final, x + dx, z + dz))
            except ValueError:
                dropped += 1
                runs.append([])
                continue
            run = runs[-1]
            if run and (key != run[-1][0] + 1 or val != run[-1][1]):
                runs.append(run := [])
            run.append((key, val, found))
        rows += [_seam_row(run, along_x, name) for run in runs if run]
    return rows, dropped


def _seam_row(run: list[tuple[int, int, int]], along_x: bool, outward: str) -> dict:
    """The seam row over a run of ``(along, across, step)`` points at one across coordinate."""
    (k0, v, _), (k1, _, _) = run[0], run[-1]
    a, b = ([k0, v], [k1, v]) if along_x else ([v, k0], [v, k1])
    return {"from": a, "to": b, "max_step": max(1, *(t for _, _, t in run)), "outward": outward}
