"""Plan layered vegetation and emit offline feature and named-biome commands."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import ashlar_emit, scatter
from .emit import _material_from_spec
from .field import HeightField
from .forms import load_form
from .live import _WORLD_MAX, _WORLD_MIN, _levels, expected_surface
from .materialize import MaterialSpec, resolve_surface
from .recipe import build_field
from .site import (
    _AIR,
    ATTACHED,
    LEAVES,
    PLANTS,
    TRUNK,
    base_id,
    drain_bodies,
    ground_for,
    integer_level,
    liquid_levels,
    surface_y,
    surfaces,
    water_levels,
)


@dataclass(frozen=True)
class Feature:
    id: str
    x: int
    y: int
    z: int
    layer: str


GROWABLE = frozenset(
    f"minecraft:{name}"
    for name in (
        "grass_block",
        "dirt",
        "coarse_dirt",
        "podzol",
        "rooted_dirt",
        "moss_block",
        "mud",
        "mycelium",
        "pale_moss_block",
    )
)
_VEGETATION = TRUNK | LEAVES | PLANTS | ATTACHED
LAYER_SPACING = {"canopy": (3.0, 12.0), "understory": (2.0, 6.0), "ground": (1.0, 3.0)}
_RESOURCE_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+")
_XZ_MIN, _XZ_MAX = -30_000_000, 29_999_999


def _resource_id(value, kind):
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise ValueError(f"invalid {kind} ID {value!r}, expected namespace:path")
    return value


def _validate_mix(mix, known):
    if not isinstance(mix, dict):
        raise TypeError("feature mix must map layers to species weights")
    for layer, choices in mix.items():
        if layer not in LAYER_SPACING or not isinstance(choices, dict):
            raise ValueError(f"invalid feature layer or mix for {layer!r}")
        total = 0.0
        for fid, weight in choices.items():
            _resource_id(fid, "feature")
            if fid not in known:
                raise ValueError(f"unknown feature ID {fid!r} for the selected Minecraft version")
            if (
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not np.isfinite(weight)
                or weight < 0
            ):
                raise ValueError(f"invalid weight for feature {fid!r}")
            total += weight
        if choices and (not np.isfinite(total) or total <= 0):
            raise ValueError(f"feature weights for {layer!r} must have a positive finite sum")


def _slope_density(heights):
    if min(heights.shape) < 2:
        raise ValueError("measuring planting slope requires observed neighbouring heights on both axes")
    land = HeightField(*heights.shape, sea_level=-np.inf)
    land.h = surface_y(heights)
    return np.nan_to_num(scatter.density_map(land), nan=0.0)


def _planting_density(hf, surface_ids, water, slope_density):
    sy = surface_y(hf.h)
    if not np.isfinite(sy).all() or not np.all((_WORLD_MIN <= sy) & (sy <= _WORLD_MAX)):
        raise ValueError("planting requires finite world block heights on the field grid")
    shape = sy.shape
    blocks = np.asarray(surface_ids)
    if blocks.shape != shape or min(shape) < 1:
        raise ValueError("surface blocks must match the non-empty planting field")
    if water is None:
        wet = sy < hf.sea_level
    elif np.asarray(water).dtype == bool:
        wet = np.asarray(water)
        if wet.shape != shape:
            raise ValueError("water mask must match the planting field")
    else:
        wet = _levels(water, shape, "water") > sy

    # Slope is measured on blocks the build actually places. A cropped site
    # supplies densities computed with its observed one-block ground halo.
    density = _slope_density(sy) if slope_density is None else np.array(slope_density, dtype=float)
    if density.shape != shape or not np.all((0 <= density) & (density <= 1)):
        raise ValueError("slope density must match the field and contain finite values from 0 to 1")
    if wet.any():
        distance = ndimage.distance_transform_edt(~wet)
        density *= 0.65 + 0.35 * np.exp(-distance / 12.0)
    else:
        density *= 0.65
    growable = np.fromiter(
        (isinstance(b, str) and base_id(b) in GROWABLE for b in blocks.flat), dtype=bool, count=blocks.size
    ).reshape(shape)
    density[wet | ~growable | (sy == _WORLD_MAX)] = 0
    return density, sy


def _disk(radius, *, strict=False):
    offsets = np.arange(-radius, radius + 1) ** 2
    distance_sq = offsets[:, None] + offsets[None, :]
    return distance_sq < radius**2 if strict else distance_sq <= radius**2


def _mark_disk(mask, x, z, disk):
    radius = disk.shape[0] // 2
    x0, z0 = x - radius, z - radius
    x1, z1 = max(0, x0), max(0, z0)
    x2, z2 = min(mask.shape[0], x + radius + 1), min(mask.shape[1], z + radius + 1)
    if x1 < x2 and z1 < z2:
        mask[x1:x2, z1:z2] |= disk[x1 - x0 : x2 - x0, z1 - z0 : z2 - z0]


def plan_features(
    hf: HeightField,
    surface_ids: np.ndarray,
    mix: dict[str, dict[str, float]],
    *,
    origin: tuple[int, int],
    seed: int,
    known: frozenset[str],
    water: np.ndarray | None = None,
    slope_density: np.ndarray | None = None,
) -> list[Feature]:
    """Sample higher layers first. Water may be a wet mask or a NaN-dry level grid."""
    _validate_mix(mix, known)
    density, sy = _planting_density(hf, surface_ids, water, slope_density)
    ox, oz = (integer_level(v, "origin") for v in origin)
    occupied = np.zeros(density.shape, dtype=bool)
    features = []
    for i, (layer, (r_min, r_max)) in enumerate(LAYER_SPACING.items()):
        choices = mix.get(layer)
        if not choices:
            continue
        disk = _disk(int(r_min), strict=True)
        blocked = ndimage.binary_dilation(occupied, structure=disk)
        layer_density = np.where(blocked, 0.0, density)
        candidates = scatter.poisson(layer_density, r_min=r_min, r_max=r_max, seed=seed + i)
        points = []
        for x, z in candidates:
            # Poisson rounds continuous samples to blocks. Check the actual block
            # again for wet ground, a forbidden slope, a neighbour, or an edge.
            if 0 <= x < hf.nx and 0 <= z < hf.nz and density[x, z] > 0 and not blocked[x, z]:
                occupied[x, z] = True
                _mark_disk(blocked, x, z, disk)
                points.append((x, z))
        species = scatter.assign_species(points, choices, seed=seed + 100 + i)
        features.extend(
            Feature(fid, ox + x, int(sy[x, z]) + 1, oz + z, layer) for (x, z), fid in zip(points, species)
        )
    return features


def features_file(features: list[Feature], *, world: str | None, reach: tuple[int, ...] = (8, 32)) -> dict:
    """Build an F3 with the backup box grown by the chosen species' reach."""
    if not features:
        raise ValueError("an empty feature list has no backup box")
    sideways, up, down = feature_reach(reach)
    coords = []
    commands = []
    for f in features:
        fid = _resource_id(f.id, "feature")
        x, y, z = (integer_level(n, "feature coordinate") for n in (f.x, f.y, f.z))
        if not (_XZ_MIN <= x <= _XZ_MAX and _WORLD_MIN <= y <= _WORLD_MAX and _XZ_MIN <= z <= _XZ_MAX):
            raise ValueError("feature position outside world bounds")
        coords.append((x, y, z))
        commands.append(f"place feature {fid} {x} {y} {z}")
    xs, ys, zs = zip(*coords)
    box = [
        max(_XZ_MIN, min(xs) - sideways),
        max(_WORLD_MIN, min(ys) - down),
        max(_XZ_MIN, min(zs) - sideways),
        min(_XZ_MAX, max(xs) + sideways),
        min(_WORLD_MAX, max(ys) + up),
        min(_XZ_MAX, max(zs) + sideways),
    ]
    return {"version": 1, "kind": "features", "world": world, "box": box, "commands": commands}


def biome_commands(
    biome: str,
    *,
    origin: tuple[int, int],
    size: tuple[int, int],
    y_range: tuple[int, int],
    limit: int = 32_768,
) -> list[str]:
    """Paint the named biome, expanding to touched chunks and complete 4-block biome cells."""
    _resource_id(biome, "biome")
    ox, oz = (integer_level(n, "origin") for n in origin)
    nx, nz = (integer_level(n, "size") for n in size)
    lo, hi = (integer_level(n, "y range") for n in y_range)
    limit = integer_level(limit, "fillbiome block limit")
    if (
        min(nx, nz) < 1
        or not _WORLD_MIN <= lo <= hi <= _WORLD_MAX
        or not _XZ_MIN <= ox <= ox + nx - 1 <= _XZ_MAX
        or not _XZ_MIN <= oz <= oz + nz - 1 <= _XZ_MAX
    ):
        raise ValueError("biome box must be ordered, non-empty and within world bounds")
    quart_slab = limit // (16 * 16 * 4)
    if quart_slab < 1:
        raise ValueError("fillbiome limit must allow a 16 x 4 x 16 biome slab (1024 blocks)")
    commands = []
    for cx in range(ox // 16, (ox + nx - 1) // 16 + 1):
        for cz in range(oz // 16, (oz + nz - 1) // 16 + 1):
            x, z = cx * 16, cz * 16
            for qy in range(lo // 4, hi // 4 + 1, quart_slab):
                top = min(qy + quart_slab, hi // 4 + 1) * 4 - 1
                commands.append(f"fillbiome {x} {qy * 4} {z} {x + 15} {top} {z + 15} {biome}")
    return commands


def mark_trunks(surface: dict, points: Iterable[tuple[int, int]], radius: int = 2) -> dict:
    """Copy F6, adding verification skips within a block radius of each world point."""
    radius = integer_level(radius, "trunk skip radius")
    if radius < 0:
        raise ValueError("trunk skip radius cannot be negative")
    ox, oz = surface["origin"]
    nx, nz = (integer_level(n, "surface size") for n in surface["size"])
    existing = np.asarray(surface["skip"])
    if (
        min(nx, nz) < 1
        or existing.shape != (nx * nz,)
        or not np.isin(existing, [0, 1]).all()
        or len(surface["top"]) != nx * nz
        or surface["version"] != 1
    ):
        raise ValueError("invalid expected surface dimensions, version or skip mask")
    skip = existing.astype(bool).reshape(nx, nz)
    disk = _disk(radius)
    for x, z in points:
        _mark_disk(skip, x - ox, z - oz, disk)
    return {**surface, "skip": skip.astype(int).ravel().tolist()}


def mark_feature_trunks(surface, features, reach):
    """Skip narrow upright trunks locally; branches, fallen logs, roots and
    decorators can change solid heights throughout the declared horizontal reach."""
    narrow = {"minecraft:oak", "minecraft:birch", "minecraft:spruce"}
    surface = mark_trunks(surface, ((f.x, f.z) for f in features if f.id in narrow))
    nx, nz = surface["size"]
    ox, oz = surface["origin"]
    mask = np.asarray(surface["skip"]).reshape(nx, nz)
    radius = feature_reach(reach)[0]
    for f in features:
        if f.id in _OTHER_VEGETATION:
            x, z = f.x - ox, f.z - oz
            x1, x2 = max(0, x - radius), min(nx, x + radius + 1)
            z1, z2 = max(0, z - radius), min(nz, z + radius + 1)
            if x1 < x2 and z1 < z2:
                mask[x1:x2, z1:z2] = 1
    return {**surface, "skip": mask.ravel().tolist()}


def feature_reach(values):
    if len(values) not in (2, 3):
        raise ValueError("feature reach needs sideways and up, optionally followed by down")
    reach = tuple(integer_level(n, "feature reach") for n in values)
    if min(reach) < 0:
        raise ValueError("feature reach cannot be negative")
    return reach if len(reach) == 3 else (*reach, 2)


# Verified vegetation in the bundled 26.3 game data. A valid registry entry may
# also generate ores, lava lakes or structures, which do not belong in a planting mix.
_DEFAULT_VEGETATION = frozenset(
    "minecraft:" + name
    for name in [
        "oak",
        "birch",
        "spruce",
        "bush",
        "berry_bush",
        "brown_mushroom",
        "red_mushroom",
        "dry_grass",
        "firefly_bush",
        "flower_cherry",
        "flower_default",
        "flower_flower_forest",
        "flower_meadow",
        "flower_pale_garden",
        "flower_plain",
        "flower_swamp",
        "grass",
        "grass_jungle",
        "large_fern",
        "leaf_litter",
        "red_shrub",
        "sunflower",
        "taiga_grass",
        "tall_grass",
        "wildflower",
        "dead_bush",
    ]
)
_OTHER_VEGETATION = frozenset(
    "minecraft:" + name
    for name in [
        "acacia",
        "azalea_tree",
        "birch_tall",
        "birch_bees_0002",
        "birch_bees_0002_leaf_litter",
        "birch_bees_002",
        "birch_bees_005",
        "birch_leaf_litter",
        "cherry",
        "cherry_bees_005",
        "dark_oak",
        "dark_oak_leaf_litter",
        "fancy_oak",
        "fancy_oak_bees",
        "fancy_oak_bees_0002_leaf_litter",
        "fancy_oak_bees_002",
        "fancy_oak_bees_005",
        "fancy_oak_leaf_litter",
        "jungle_bush",
        "jungle_tree",
        "jungle_tree_no_vine",
        "mangrove",
        "mega_jungle_tree",
        "mega_pine",
        "mega_spruce",
        "oak_bees_0002_leaf_litter",
        "oak_bees_002",
        "oak_bees_005",
        "oak_leaf_litter",
        "orange_poplar",
        "orange_poplar_leaf_litter",
        "pale_oak",
        "pale_oak_bonemeal",
        "pale_oak_creaking",
        "pine",
        "red_poplar",
        "red_poplar_leaf_litter",
        "super_birch_bees",
        "super_birch_bees_0002",
        "swamp_oak",
        "tall_mangrove",
        "yellow_poplar",
        "yellow_poplar_leaf_litter",
        "bamboo_no_podzol",
        "bamboo_some_podzol",
        "fallen_birch_tree",
        "fallen_jungle_tree",
        "fallen_oak_tree",
        "fallen_poplar_tree",
        "fallen_spruce_tree",
        "fallen_super_birch_tree",
        "huge_red_mushroom",
        "huge_brown_mushroom",
    ]
)


def vegetation_reach(mix, known, reach):
    _validate_mix(mix, known)
    ids = {fid for choices in mix.values() for fid in choices}
    unsupported = ids - _DEFAULT_VEGETATION - _OTHER_VEGETATION
    if unsupported:
        raise ValueError(f"unverified vegetation features: {', '.join(sorted(unsupported))}")
    if reach is None and ids - _DEFAULT_VEGETATION:
        raise ValueError(
            "verify species reach, including roots and decorators, and supply --reach SIDE UP DOWN"
        )
    values = feature_reach((8, 32, 2) if reach is None else reach)
    if any(n < default for n, default in zip(values, (8, 32, 2))):
        raise ValueError("CLI backup reach must cover at least 8 sideways, 32 up and 2 down")
    return values


def site_planting(site, box, *, measure_slope=True):
    """Ground, observed soil, wet columns and an F6 for an existing stand."""
    x1, z1, x2, z2 = box
    if not (site.box[0] <= x1 <= x2 <= site.box[3] and site.box[2] <= z1 <= z2 <= site.box[5]):
        raise ValueError("planting box must be ordered and inside the captured site")
    bed = surfaces(site)
    crop = np.s_[x1 - site.box[0] : x2 - site.box[0] + 1, z1 - site.box[2] : z2 - site.box[2] + 1]
    ground = bed.ground[crop]
    levels = liquid_levels(site, surf=bed).top[crop]
    hf = HeightField(*ground.shape)
    hf.h = np.nan_to_num(ground, nan=site.box[1])
    surface = expected_surface(hf, levels, set(), (x1, z1))
    blocks = np.full(ground.shape, None, dtype=object)
    top = bed.top[crop]
    for (i, j), g in np.ndenumerate(ground):
        x, z = x1 + i, z1 + j
        runs = site.columns[x, z]
        if base_id(runs[-1][2]) not in _AIR and site.box[4] < _WORLD_MAX:
            raise ValueError(f"read higher to see the planting surface at {(x, z)}")
        # The F6 contract excludes leaves, while the planting bed excludes trunks too.
        index = i * hf.nz + j
        surface["top"][index] = None
        for _, hi, state in reversed(runs):
            flags = ashlar_emit._flags(state)
            if flags & ashlar_emit._UNKNOWN_HEIGHT:
                surface["skip"][index] = 1
            if flags & ashlar_emit._SURFACE:
                surface["top"][index] = hi
                break
        if np.isfinite(g) and top[i, j] == g:
            blocks[i, j] = site.block(x, int(g), z)
        elif np.isfinite(g) and surface["top"][index] != g and not np.isfinite(levels[i, j]):
            surface["skip"][index] = 1
    # The halo makes the derivative at a crop edge match the measured site,
    # including single-column crops and crops touching the outer survey ring.
    xi, zi = x1 - site.box[0], z1 - site.box[2]
    a, b = max(0, xi - 1), max(0, zi - 1)
    measured = bed.ground[a : xi + hf.nx + 1, b : zi + hf.nz + 1]
    slope_density = (
        _slope_density(measured)[xi - a : xi - a + hf.nx, zi - b : zi - b + hf.nz] if measure_slope else None
    )
    return hf, blocks, levels, surface, slope_density


def _final_block(site, layers, x, y, z):
    for _, write in reversed(layers):
        pos = (x - write.origin[0], y - write.origin[1], z - write.origin[2])
        if all(0 <= i < n for i, n in zip(pos, write.codes.shape)):
            code = write.codes[pos]
            if code:
                return write.palette[code]
    return site.block(x, y, z)


def recipe_planting(recipe, project, approvals):
    """Use the final fitted mass, overlaid forms and retained/planned liquid for this recipe."""
    ashlar_emit._check_recipe(recipe)
    origin = (integer_level(recipe["origin"][0], "origin x"), integer_level(recipe["origin"][2], "origin z"))
    site = None
    if not recipe.get("site") and recipe.get("dimension") not in (None, "minecraft:overworld", "overworld"):
        raise ValueError(
            "a non-default recipe dimension requires a captured F1 world and explicit --dimension"
        )
    if recipe.get("site"):
        read = Path(recipe["site"]["read"])
        if read.is_absolute() or not (project / read).resolve().is_relative_to(project.resolve()):
            raise ValueError("site read must be relative to the project")
        site, _, _ = ground_for(recipe, project)
    bodies = drain_bodies(site, recipe) if site else []
    ashlar_emit._check_approvals(bodies, approvals)
    hf = build_field(recipe, project)
    water = water_levels(hf, recipe)
    if recipe.get("material"):
        material = _material_from_spec(recipe["material"], hf, recipe, water=water)
    else:
        material = MaterialSpec.natural(hf, snow_y=recipe.get("snow_y"))
        if recipe.get("strata"):
            material.strata = [(s["block"], s["thickness"]) for s in recipe["strata"]]
    if site is None:
        if recipe.get("forms") or recipe.get("falls"):
            raise ValueError("planting over forms or falls needs a captured site")
        blocks, _ = resolve_surface(hf, material)
        return hf, blocks, water, expected_surface(hf, water, set(), origin), None
    forms = [load_form(f, project) for f in recipe.get("forms", [])]
    _, layers, flow, _, surface, _, _ = ashlar_emit._prepare(
        hf, material, site, recipe, water, forms, None, bodies, 128
    )
    water = np.fmax(water, layers[0][1].liquid_top)
    blocks = np.full(hf.h.shape, None, dtype=object)
    sources = {tuple(b["pos"]) for b in flow["blocks"]}
    for index, y in enumerate(surface["top"]):
        if y is None or surface["skip"][index]:
            continue
        i, j = divmod(index, hf.nz)
        x, z = origin[0] + i, origin[1] + j
        if (x, y, z) in sources:
            water[i, j] = y
            continue
        state = _final_block(site, layers, x, y, z)
        block = base_id(state)
        # Stable terrain, including a non-growable built form, contributes to
        # neighbouring slopes. A retained trunk or liquid is not the terrain bed.
        if (
            block not in _VEGETATION
            and not (ashlar_emit._flags(state) & ashlar_emit._FLUID)
            and not water[i, j] >= y
            and round(hf.h[i, j]) != y
        ):
            hf.h[i, j] = y
        if block in GROWABLE and y < site.box[4] and base_id(_final_block(site, layers, x, y + 1, z)) in _AIR:
            blocks[i, j] = state
    return hf, blocks, water, surface, site.world
