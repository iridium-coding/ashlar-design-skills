"""Materialise a terrain field against a site read, preserving existing surface liquid."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import numpy as np

from .field import HeightField
from .materialize import MaterialSpec, resolve_surface
from .site import (
    ATTACHED,
    LEAVES,
    PLANTS,
    TRUNK,
    Cell,
    DrainBody,
    Site,
    base_id,
    drain_bodies,
    find_trees,
    integer_level,
    is_still,
    liquid_kind,
    liquid_levels,
    surface_y,
    surfaces,
    water_levels,
    water_run_flags,
)

_AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
_WORLD_MIN, _WORLD_MAX = -64, 319


@dataclass
class LiveWrite:
    origin: tuple[int, int, int]
    codes: np.ndarray
    palette: list[str]
    removed_trees: int = 0
    reach: int = 0
    liquid_top: np.ndarray | None = None
    kept_trunks: set[tuple[int, int]] = field(default_factory=set)
    liquid: dict[str, int] = field(default_factory=lambda: {"kept": 0, "covered": 0, "added": 0})


def _levels(values, shape, name):
    if values is None:
        return np.full(shape, np.nan)
    levels = np.asarray(values, dtype=float)
    present = levels[~np.isnan(levels)]
    if (
        levels.shape != shape
        or not np.isfinite(present).all()
        or not ((present == np.rint(present)) & (present >= _WORLD_MIN) & (present <= _WORLD_MAX)).all()
    ):
        raise ValueError(f"{name} must contain world block levels or NaN on the field grid")
    return levels


def _bottoms(site, surf, ox, oz, target, ground, seal):
    """Face depths use actual neighbouring ground in the site margin where available."""
    x1, _, z1, x2, _, z2 = site.box
    nx, nz = target.shape
    padded = np.pad(ground, 1, mode="edge")
    if ox > x1:
        padded[0, 1:-1] = surf.ground[ox - x1 - 1, oz - z1 : oz - z1 + nz]
    if ox + nx <= x2:
        padded[-1, 1:-1] = surf.ground[ox - x1 + nx, oz - z1 : oz - z1 + nz]
    if oz > z1:
        padded[1:-1, 0] = surf.ground[ox - x1 : ox - x1 + nx, oz - z1 - 1]
    if oz + nz <= z2:
        padded[1:-1, -1] = surf.ground[ox - x1 : ox - x1 + nx, oz - z1 + nz]
    if not np.isfinite(padded).all():
        raise ValueError("read lower to find the neighbouring ground")
    padded[1:-1, 1:-1] = target
    lowest = np.minimum.reduce(
        [target, ground, padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]]
    )
    return np.maximum(lowest.astype(int) - seal, _WORLD_MIN)


def _planned_levels(water, hf, recipe, levels, crop, origin, surface):
    planned = _levels(water, hf.h.shape, "water").copy()
    still = levels.level[crop]
    explicit = np.isfinite(planned)
    if not explicit.any():
        return planned, explicit
    # The explicit floods are independent of the blanket sea, even at the same level.
    if recipe and "sea_level" in recipe:
        entries = water_levels(hf, {k: v for k, v in recipe.items() if k != "sea_level"})
        explicit &= np.isfinite(entries) | (planned != recipe["sea_level"])
    conflict = explicit & (planned < still)
    if conflict.any():
        i, j = np.argwhere(conflict)[0]
        x, z = int(i) + origin[0], int(j) + origin[1]
        raise ValueError(f"water level {planned[i, j]:g} below existing level {still[i, j]:g} at {(x, z)}")
    # An explicit flood promises water even when all mass-layer codes would be skips.
    lava = explicit & (levels.kind[crop] == "lava") & (surface < still) & (planned >= still)
    if lava.any():
        i, j = np.argwhere(lava)[0]
        cell = (int(i) + origin[0], int(still[i, j]), int(j) + origin[1])
        raise ValueError(f"water level {planned[i, j]:g} would claim retained lava at {cell}")
    planned[~explicit & (planned <= still)] = np.nan
    return planned, explicit


def _top_without_kept(runs, x, z, kept):
    for lo, hi, state in reversed(runs):
        if base_id(state) not in _AIR:
            while hi >= lo and (x, hi, z) in kept:
                hi -= 1
            if hi >= lo:
                return hi
    return runs[0][0] - 1


def _check_planned_water_at_lava(site, write, x, z, col, water_code, ground, excluded):
    """A planned source may not replace retained lava or introduce a vertical reaction."""
    bottom = write.origin[1]
    for yi in np.flatnonzero(col == water_code):
        y = bottom + int(yi)
        old = liquid_kind(site.block(x, y, z))
        if y > ground and old == "lava" and (x, y, z) not in excluded:
            raise ValueError(f"planned water would replace surface lava at {(x, y, z)}")
        for other in (y - 1, y + 1):
            if not site.box[1] <= other <= site.box[4]:
                continue
            original = liquid_kind(site.block(x, other, z))
            oi = other - bottom
            code = col[oi] if 0 <= oi < len(col) else 0
            final = liquid_kind(write.palette[code]) if code else original
            if final == "lava" and (old != "water" or original != "lava"):
                raise ValueError(f"planned water at {(x, y, z)} would touch lava at {(x, other, z)}")


def materialize_live(
    hf: HeightField,
    spec: MaterialSpec,
    site: Site,
    recipe: dict | None,
    *,
    water: np.ndarray | None = None,
    protect: np.ndarray | None = None,
    seal: int = 4,
    drains: tuple[DrainBody, ...] | list[DrainBody] = (),
) -> LiveWrite:
    seal = integer_level(seal, "seal")
    depth = integer_level(spec.subsurface_depth, "subsurface_depth")
    if depth < 0 or seal <= depth:
        raise ValueError("seal must exceed the non-negative subsurface depth")
    x1, y1, z1, x2, y2, z2 = site.box
    nx, nz = hf.nx, hf.nz
    if recipe is None:
        ox, oz = x1, z1
        if (nx, nz) != (x2 - x1 + 1, z2 - z1 + 1):
            raise ValueError("without a recipe the field must match the site box")
    else:
        ox = integer_level(recipe["origin"][0], "origin x")
        oz = integer_level(recipe["origin"][2], "origin z")
        if (recipe.get("nx", nx), recipe.get("nz", nz)) != (nx, nz):
            raise ValueError("recipe shape differs from field")
    if not (x1 <= ox <= ox + nx - 1 <= x2 and z1 <= oz <= oz + nz - 1 <= z2):
        raise ValueError("field outside the site read")
    sy = surface_y(hf.h)
    if sy.shape != (nx, nz) or not ((sy >= _WORLD_MIN) & (sy <= _WORLD_MAX)).all():
        raise ValueError("field must contain finite surfaces within world height")
    sy = sy.astype(int)
    protected = np.zeros(sy.shape, bool) if protect is None else np.asarray(protect)
    if protected.shape != sy.shape or protected.dtype != np.bool_:
        raise ValueError("protect must be a boolean mask matching the field")
    # Verify saved descriptors by identity and content. Seeds only locate a body.
    current = drain_bodies(site, recipe or {}, protect=protected)
    supplied = {body.id: body.cells for body in drains}
    if len(drains) != len(current) or any(supplied.get(body.id) != body.cells for body in current):
        raise ValueError("drain descriptors do not match the complete bodies in the current site and recipe")
    excluded = {cell for body in drains for cell in body.cells}
    if any(base_id(runs[-1][2]) not in _AIR for runs in site.columns.values()):
        raise ValueError("read higher: the site must end in air")
    surf = surfaces(site)
    crop = np.s_[ox - x1 : ox - x1 + nx, oz - z1 : oz - z1 + nz]
    ground = surf.ground[crop]
    if not np.isfinite(ground).all():
        raise ValueError("read lower to find the ground")
    sy = np.where(protected, ground.astype(int), sy)
    bottoms = _bottoms(site, surf, ox, oz, sy, ground, seal)

    def inside(x, z):
        return ox <= x < ox + nx and oz <= z < oz + nz

    kept, removed, trunks = set(), set(), set()
    removed_count = 0
    for tree in find_trees(site):
        if any(
            inside(x, z) and sy[x - ox, z - oz] != ground[x - ox, z - oz] for x, z in tree.trunk_columns
        ):
            removed_count += 1
            for x, y, z in tree.cells:
                if inside(x, z) and protected[x - ox, z - oz]:
                    kept.add((x, y, z))
                else:
                    removed.add((x, y, z))
        else:
            kept.update(tree.cells)
            trunks.update(tree.trunk_columns)

    levels = liquid_levels(site, removed=removed, surf=surf, excluded=excluded)
    planned, explicit = _planned_levels(water, hf, recipe, levels, crop, (ox, oz), sy)
    # A surviving branch or cap affects the NO_LEAVES read just as a vertical trunk does.
    # Root columns alone still decide whether a tree is felled.
    trunks.update(
        (x, z)
        for x, y, z in kept
        if inside(x, z) and y > sy[x - ox, z - oz] and not base_id(site.block(x, y, z)).endswith("_leaves")
    )
    tops = np.array(
        [
            [_top_without_kept(site.columns[x, z], x, z, kept) for z in range(oz, oz + nz)]
            for x in range(ox, ox + nx)
        ]
    )
    active = ~protected
    lower = int(bottoms[active].min()) if active.any() else y1
    upper = int(np.fmax(np.maximum(sy, tops), planned)[active].max()) if active.any() else lower
    if excluded:
        # Kept waterlogged canopy cells may be higher than the top without the tree.
        upper = max(upper, max(y for _, y, _ in excluded))
    min_x, min_z, max_x, max_z = ox, oz, ox + nx - 1, oz + nz - 1
    for x, y, z in removed:
        min_x, lower, min_z = min(min_x, x), min(lower, y), min(min_z, z)
        max_x, upper, max_z = max(max_x, x), max(upper, y), max(max_z, z)
    if active.any() and lower - 1 < y1 and lower != _WORLD_MIN:
        raise ValueError(f"read lower: need at least y {max(lower - 1, _WORLD_MIN)}")
    if lower < y1 or upper > y2:
        raise ValueError("read higher or lower to contain the terrain writes")

    codes = np.zeros((max_x - min_x + 1, upper - lower + 1, max_z - min_z + 1), np.uint16)
    palette = ["skip", "minecraft:air"]
    indices = {state: i for i, state in enumerate(palette)}

    def index(state):
        if ":" not in state:
            state = "minecraft:" + state
        if state not in indices:
            if len(palette) > np.iinfo(codes.dtype).max:
                raise ValueError("too many distinct block states")
            indices[state] = len(palette)
            palette.append(state)
        return indices[state]

    reach = max(ox - min_x, oz - min_z, max_x - (ox + nx - 1), max_z - (oz + nz - 1))
    write = LiveWrite(
        (min_x, lower, min_z), codes, palette, removed_count, reach, np.full(sy.shape, np.nan), trunks
    )
    surface, sub = resolve_surface(hf, spec)
    deep = np.full(upper - lower + 1, index(spec.stone), np.uint16)
    band_top = integer_level(
        ((recipe or {}).get("material") or {}).get("strata_top", int(sy.max())), "strata_top"
    )
    for state, thickness in spec.strata or ():
        thickness = integer_level(thickness, "strata thickness")
        if thickness <= 0:
            raise ValueError("strata thickness must be positive")
        lo, hi = max(band_top - thickness + 1, lower), min(band_top, upper)
        if lo <= hi:
            deep[lo - lower : hi - lower + 1] = index(state)
        band_top -= thickness

    @cache
    def still_at(x, y, z):
        if not (x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2):
            return None
        if (x, y, z) in excluded or y <= surf.ground[x - x1, z - z1]:
            return None
        runs = site.columns[x, z]
        for (lo, hi, state), watery in zip(runs, water_run_flags(runs)):
            if lo <= y <= hi and is_still(state):
                return "water" if watery else liquid_kind(state)
        return None

    def tree_replacement(cell, w, level, kind):
        x, y, z = cell
        own = liquid_kind(site.block(*cell))
        joined = levels.joined.get(cell)
        replacement = "water" if y <= w else joined
        if replacement is None and y <= level:
            replacement = kind
        if replacement is None:
            if own:
                raise ValueError(
                    f"removing the waterlogged tree cell at {cell} would drain it; "
                    "keep the tree or adjust the layout"
                )
            return "minecraft:air"
        kinds = {own, replacement, joined}
        if joined:
            # T8 supplies one kind per join. Check its incoming edges for another kind:
            # a mixed source or two differently attributed branches are ambiguous.
            for neighbour in ((x - 1, y, z), (x + 1, y, z), (x, y, z - 1), (x, y, z + 1), (x, y + 1, z)):
                kinds.add(still_at(*neighbour))
                kinds.add(levels.joined.get(neighbour))
        if "water" in kinds and "lava" in kinds:
            raise ValueError(
                f"removed tree cell at {cell} would mix water and lava; keep the tree or adjust the layout"
            )
        return "minecraft:" + (own or replacement)

    for i, j in np.ndindex(sy.shape):
        x, z = ox + i, oz + j
        b, s, g, w = bottoms[i, j], sy[i, j], ground[i, j], planned[i, j]
        level, kind = levels.level[x - x1, z - z1], levels.kind[x - x1, z - z1]
        col = codes[x - min_x, :, z - min_z]
        if active[i, j]:
            # Copy the absolute-y rock bands first, then the area's own materials.
            col[b - lower : s - lower + 1] = deep[b - lower : s - lower + 1]
            col[max(b, s - depth) - lower : s - lower] = index(sub[i, j])
            col[s - lower] = index(surface[i, j])
        runs = site.columns[x, z]
        top = tops[i, j] if np.isnan(w) else max(tops[i, j], int(w))
        for (lo, hi, state), watery in zip(runs, water_run_flags(runs)):
            lava = liquid_kind(state) == "lava"
            retained = watery or lava
            if active[i, j] and retained:
                # Leave buried liquid in place inside the seal. If it occupies
                # the proposed bed itself, the emitter must reject that grade.
                first = max(lo, b)
                last = min(hi, int(g), s - 1)
                if first <= last:
                    col[first - lower : last - lower + 1] = 0
            # L describes only the uppermost still kind. A lower original run can
            # also occupy space promised to an explicit flood, even when left as skip.
            if lava and explicit[i, j]:
                overlap_top = int(min(hi, w))
                conflict_y = next((y for y in range(overlap_top, int(max(lo, g + 1, s + 1)) - 1, -1)
                                   if (x, y, z) not in excluded), None)
                if conflict_y is not None:
                    raise ValueError(f"water level {w:g} would replace surface lava at {(x, conflict_y, z)}")
            if active[i, j] and retained:
                covered = range(int(max(lo, g + 1)), int(min(hi, s)) + 1)
                write.liquid["covered"] += (sum((x, y, z) not in excluded for y in covered)
                                            if excluded else len(covered))
            # Kept leaves may be retained above t. They count but do not raise NO_LEAVES.
            stop = hi if retained else min(hi, top)
            for y in range(max(lo, s + 1), stop + 1):
                cell = (x, y, z)
                if retained and y <= g:
                    # Lowering a bed may expose a buried source. Keep its
                    # original state and let the contact checks assess the cut.
                    if base_id(state) not in LEAVES:
                        write.liquid_top[i, j] = y
                    continue
                existing = retained and y > g and cell not in excluded
                replacement = None
                if cell in excluded:
                    if cell in kept:
                        replacement = state.replace("waterlogged=true", "waterlogged=false")
                    else:
                        replacement = "minecraft:water" if y <= w else "minecraft:air"
                elif active[i, j] and cell not in kept:
                    if cell in removed:
                        replacement = tree_replacement(cell, w, level, kind)
                    elif existing and (y <= level or np.isnan(w) or y > w):
                        pass
                    elif y <= w:
                        replacement = "minecraft:water"
                    elif y <= level:
                        replacement = "minecraft:" + kind
                    elif y <= top:
                        replacement = "minecraft:air"
                if replacement is not None:
                    col[y - lower] = index(replacement)
                if existing and replacement is None:
                    write.liquid["kept"] += 1
                    if base_id(state) not in LEAVES:
                        write.liquid_top[i, j] = y
                elif replacement in ("minecraft:water", "minecraft:lava"):
                    write.liquid["added"] += 1
                    write.liquid_top[i, j] = y

        if active[i, j] and np.isfinite(w) and "minecraft:water" in indices:
            _check_planned_water_at_lava(site, write, x, z, col, indices["minecraft:water"], g, excluded)

    for cell in sorted(removed):
        x, y, z = cell
        if not inside(x, z):
            state = tree_replacement(
                cell, np.nan, levels.level[x - x1, z - z1], levels.kind[x - x1, z - z1]
            )
            codes[x - min_x, y - lower, z - min_z] = index(state)
            if state != "minecraft:air":
                write.liquid["added"] += 1
    return write


def greedy_fills(write: LiveWrite) -> list[dict]:
    """Disjoint cuboids, grown along z, x and y in deterministic scan order."""
    grid = write.codes.copy()
    ox, oy, oz = write.origin
    nx, ny, nz = grid.shape
    fills = []
    for x in range(nx):
        for y in range(ny):
            for z in np.flatnonzero(grid[x, y]):
                z = int(z)
                code = grid[x, y, z]
                if not code:  # consumed by a box earlier in this row
                    continue
                ex, ey, ez = x + 1, y + 1, z + 1
                while ez < nz and grid[x, y, ez] == code:
                    ez += 1
                while ex < nx and (grid[ex, y, z:ez] == code).all():
                    ex += 1
                while ey < ny and (grid[x:ex, ey, z:ez] == code).all():
                    ey += 1
                grid[x:ex, y:ey, z:ez] = 0
                fills.append(
                    {
                        "from": [ox + x, oy + y, oz + z],
                        "to": [ox + ex - 1, oy + ey - 1, oz + ez - 1],
                        "block": write.palette[code],
                    }
                )
    return fills


def split_columns(write: LiveWrite, max_columns: int = 128) -> list[LiveWrite]:
    """Tile only the placement data. Summary metadata belongs to the complete write."""
    size = integer_level(max_columns, "max_columns")
    if size < 1:
        raise ValueError("max_columns must be positive")
    ox, oy, oz = write.origin
    nx, _, nz = write.codes.shape
    tiles = []
    for x in range(0, nx, size):
        for z in range(0, nz, size):
            codes = write.codes[x : x + size, :, z : z + size]
            if codes.any():
                tiles.append(LiveWrite((ox + x, oy, oz + z), codes, write.palette))
    return tiles


def decode(fills: list[dict]) -> dict[Cell, str]:
    cells = {}
    for fill in fills:
        x1, y1, z1 = fill["from"]
        x2, y2, z2 = fill["to"]
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                for z in range(z1, z2 + 1):
                    cells[x, y, z] = fill["block"]
    return cells


_SOLID, _TREE, _OPEN, _WATER, _LAVA = range(5)


@cache
def _contact_class(state):
    block = base_id(state)
    fluid = liquid_kind(state)
    if fluid == "lava":
        return _LAVA
    if fluid == "water" or "waterlogged=true" in state:
        return _WATER
    if block in _AIR or block in PLANTS or block in ATTACHED:
        return _OPEN
    if block in TRUNK or block in LEAVES:
        return _TREE
    return _SOLID  # Ice is a retained surface but cannot flow.


def liquid_violations(writes, site: Site, falls=()) -> list[dict]:
    """Compare directed fluid-to-open contacts before/after the complete placement."""
    x1, y1, z1, x2, y2, z2 = site.box
    origin = (x1, y1, z1)
    before = np.empty((x2 - x1 + 1, y2 - y1 + 1, z2 - z1 + 1), dtype=np.uint8)
    for (x, z), runs in site.columns.items():
        column = before[x - x1, :, z - z1]
        for lo, hi, state in runs:
            column[lo - y1 : hi - y1 + 1] = _contact_class(state)
    after = before.copy()
    for write in [writes] if isinstance(writes, LiveWrite) else writes:
        offset = tuple(a - b for a, b in zip(write.origin, origin))
        if any(d < 0 or d + n > limit for d, n, limit in zip(offset, write.codes.shape, after.shape)):
            # An empty margin in a caller's grid is harmless. Actual writes need a read.
            for idx in zip(*np.nonzero(write.codes)):
                pos = tuple(i + d for i, d in zip(idx, offset))
                if any(p < 0 or p >= limit for p, limit in zip(pos, after.shape)):
                    raise ValueError("write outside the site read")
                after[pos] = _contact_class(write.palette[write.codes[idx]])
        else:
            target = after[tuple(slice(d, d + n) for d, n in zip(offset, write.codes.shape))]
            classes = np.array([_contact_class(st) for st in write.palette], dtype=np.uint8)
            np.copyto(target, classes[write.codes], where=write.codes != 0)

    exempt = {tuple(f["at"] if isinstance(f, dict) else f) for f in falls}
    found = []

    def report(mask, starts, delta, contact):
        for coords in zip(*np.nonzero(mask)):
            i, j, k = (int(v) + s for v, s in zip(coords, starts))
            cell = (i + x1, j + y1, k + z1)
            if cell not in exempt:
                neighbour = tuple(c + d for c, d in zip(cell, delta)) if delta else None
                found.append(
                    {
                        "cell": cell,
                        "kind": "lava" if after[i, j, k] == _LAVA else "water",
                        "level": cell[1],
                        "neighbour": neighbour,
                        "contact": contact,
                    }
                )

    for axis, step in ((0, -1), (0, 1), (2, -1), (2, 1), (1, -1)):
        source = [slice(None)] * 3
        neighbour = source.copy()
        source[axis] = slice(1, None) if step < 0 else slice(None, -1)
        neighbour[axis] = slice(None, -1) if step < 0 else slice(1, None)
        a, b = tuple(source), tuple(neighbour)
        added = (after[a] >= _WATER) & (after[b] == _OPEN) & ((before[a] < _WATER) | (before[b] != _OPEN))
        starts = [0, 0, 0]
        starts[axis] = int(step < 0)
        delta = [0, 0, 0]
        delta[axis] = step
        report(added, starts, delta, "below" if axis == 1 else "beside")

    # A liquid excavated from solid needs an observed neighbour on all flow faces.
    edge = np.zeros(after.shape, bool)
    edge[0, :, :] = edge[-1, :, :] = edge[:, :, 0] = edge[:, :, -1] = True
    if y1 > _WORLD_MIN:
        edge[:, 0, :] = True
    report(edge & (after >= _WATER) & (before == _SOLID), (0, 0, 0), None, "outside the read")
    return sorted(found, key=lambda row: (row["cell"], row["contact"], row["neighbour"]))


def expected_surface(
    hf: HeightField,
    water: np.ndarray | None,
    kept_trunks: set[tuple[int, int]],
    origin: tuple[int, int],
    *,
    retained: np.ndarray | None = None,
) -> dict:
    top = surface_y(hf.h)
    for name, levels in (("water", water), ("retained", retained)):
        if levels is not None:
            top = np.fmax(top, _levels(levels, top.shape, name))
    if not np.isfinite(top).all():
        raise ValueError("non-finite expected surface")
    ox, oz = origin
    nx, nz = top.shape
    skip = np.zeros(top.shape, np.uint8)
    for x, z in kept_trunks:
        if ox <= x < ox + nx and oz <= z < oz + nz:
            skip[x - ox, z - oz] = 1
    return {
        "version": 1,
        "origin": [ox, oz],
        "size": [nx, nz],
        "top": top.astype(int).ravel().tolist(),
        "skip": skip.ravel().tolist(),
    }
