"""Site reads (F1), heights files (F2), existing ground and tree grouping.

The site read is the folder the placer's column reader writes: ``manifest.json``
plus ``columns.json.gz`` (format F1, byte-compatible with ``ashlar_place.write_backup``;
this module does not import the placer). ``surfaces`` derives the existing ground,
water level and top per column; ``find_trees`` groups trunks, leaves and
attachments into trees; ``unnatural_blocks`` counts what players built.

Arrays are ``(nx, nz)`` indexed ``[xi, zi]`` with origin ``(x1, z1)``.

The block-class lists below (TRUNK, LEAVES, ATTACHED, PLANTS, NATURAL) are the
builder's choice, as spec section 15 leaves them. Classes match a block id with or
without its ``[states]``.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache, lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy import ndimage

from .field import HeightField, smoothstep

Box = tuple[int, int, int, int, int, int]
Run = tuple[int, int, str]
Cell = tuple[int, int, int]

# ------------------------------------------------------------ block classes
_OVERWORLD_WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak",
                    "mangrove", "cherry", "pale_oak", "poplar")
_NETHER_WOODS = ("crimson", "warped")


def _mc(*names: str) -> frozenset[str]:
    return frozenset("minecraft:" + n for n in names)


def _wood_blocks(overworld: bool = True, nether: bool = True, stripped: bool = True) -> set[str]:
    out: set[str] = set()
    for w in _OVERWORLD_WOODS if overworld else ():
        for pre in ("", "stripped_") if stripped else ("",):
            out |= {f"minecraft:{pre}{w}_log", f"minecraft:{pre}{w}_wood"}
    for w in _NETHER_WOODS if nether else ():
        for pre in ("", "stripped_") if stripped else ("",):
            out |= {f"minecraft:{pre}{w}_stem", f"minecraft:{pre}{w}_hyphae"}
    return out


# Trunks: every log, wood, stem and hyphae (stripped too), the huge-mushroom stem
# and mangrove roots (part of the tree). Muddy mangrove roots are NOT a trunk: they
# are mud-like ground that fills the swamp floor, so they count as ground.
TRUNK: frozenset[str] = frozenset(_wood_blocks()) | _mc("mushroom_stem", "mangrove_roots")

# Leaves and other canopy blocks that decay or hang off a trunk by distance.
LEAVES: frozenset[str] = frozenset(
    f"minecraft:{w}_leaves" for w in _OVERWORLD_WOODS if w != "poplar") | _mc(
    "red_poplar_leaves", "orange_poplar_leaves", "yellow_poplar_leaves",
    "azalea_leaves", "flowering_azalea_leaves", "brown_mushroom_block",
    "red_mushroom_block", "nether_wart_block", "warped_wart_block", "shroomlight")

# Things that hang on or cling to a tree (and snow lying on it).
ATTACHED: frozenset[str] = _mc(
    "vine", "cave_vines", "cave_vines_plant", "weeping_vines", "weeping_vines_plant",
    "twisting_vines", "twisting_vines_plant", "cocoa", "bee_nest", "glow_lichen",
    "moss_carpet", "pale_moss_carpet", "hanging_roots", "mangrove_propagule", "snow",
    "pale_hanging_moss", "shelf_mushroom")

_FLOWERS = ("dandelion", "poppy", "blue_orchid", "allium", "azure_bluet", "red_tulip",
            "orange_tulip", "white_tulip", "pink_tulip", "oxeye_daisy", "cornflower",
            "lily_of_the_valley", "wither_rose", "torchflower", "torchflower_crop",
            "pitcher_plant", "pitcher_crop", "sunflower", "lilac", "rose_bush", "peony",
            "open_eyeblossom", "closed_eyeblossom", "spore_blossom", "pink_petals",
            "wildflowers", "cactus_flower")
_CORALS = tuple(f"{p}{c}_{k}" for p in ("", "dead_") for c in
                ("tube", "brain", "bubble", "fire", "horn") for k in ("coral", "coral_fan", "coral_wall_fan"))

# Vegetation that never counts as ground (plants, aquatic plants, small fungi, cactus).
PLANTS: frozenset[str] = _mc(
    "short_grass", "grass", "tall_grass", "fern", "large_fern", "short_dry_grass",
    "tall_dry_grass", "dead_bush", "bush", "firefly_bush", "leaf_litter", "sweet_berry_bush",
    "sugar_cane", "bamboo", "bamboo_sapling", "kelp", "kelp_plant", "seagrass",
    "tall_seagrass", "lily_pad", "brown_mushroom", "red_mushroom", "azalea",
    "flowering_azalea", "big_dripleaf", "big_dripleaf_stem", "small_dripleaf", "cactus",
    "sea_pickle", "crimson_fungus", "warped_fungus", "crimson_roots", "warped_roots",
    "nether_sprouts", "pale_oak_sapling", "poplar_sapling", "red_shrub",
    *(f"{w}_sapling" for w in ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak",
                               "cherry")),
    *_FLOWERS, *_CORALS)

_WATER_PLANTS = _mc("kelp", "kelp_plant", "seagrass", "tall_seagrass")
_WATER = _mc("water", "bubble_column")
_LAVA = _mc("lava")
_AIR = _mc("air", "cave_air", "void_air")

_STONES = (
    "stone", "granite", "diorite", "andesite", "deepslate", "tuff", "calcite",
    "dripstone_block", "pointed_dripstone", "bedrock", "obsidian", "magma_block",
    "smooth_basalt", "amethyst_block", "budding_amethyst", "amethyst_cluster",
    "small_amethyst_bud", "medium_amethyst_bud", "large_amethyst_bud", "basalt",
    "sandstone", "red_sandstone", "sculk", "sculk_vein", "sculk_catalyst",
    "sculk_sensor", "sculk_shrieker", "glow_berries", "cobweb")
_ORES = tuple(f"{o}_ore" for o in ("coal", "iron", "copper", "gold", "redstone", "emerald",
                                   "lapis", "diamond")) + tuple(
    f"deepslate_{o}_ore" for o in ("coal", "iron", "copper", "gold", "redstone", "emerald",
                                   "lapis", "diamond"))
_SOILS = (
    "dirt", "grass_block", "podzol", "mycelium", "coarse_dirt", "rooted_dirt", "mud",
    "muddy_mangrove_roots", "clay", "moss_block", "pale_moss_block", "dirt_path", "farmland",
    "sand", "red_sand", "gravel", "suspicious_sand", "suspicious_gravel", "snow_block",
    "ice", "packed_ice", "blue_ice", "powder_snow", "terracotta", "pumpkin", "melon",
    "infested_stone", "infested_deepslate", "infested_cobblestone", "mossy_cobblestone",
    "sponge", "wet_sponge", "frogspawn", "turtle_egg", "water", "lava", "bubble_column",
    "air", "cave_air", "void_air", "glow_lichen")
_TERRACOTTA = tuple(f"{c}_terracotta" for c in
                    ("white", "orange", "yellow", "brown", "red", "light_gray"))
_CORAL_BLOCKS = tuple(f"{p}{c}_coral_block" for p in ("", "dead_") for c in
                      ("tube", "brain", "bubble", "fire", "horn"))

# Every block that occurs naturally in overworld terrain: stone, ores, soils, fluids,
# ice and snow, the vegetation classes above (not stripped logs or nether wood, which
# are players' work or nether-only) and the cave and ocean features.
NATURAL: frozenset[str] = (
    _mc(*_STONES, *_ORES, *_SOILS, *_TERRACOTTA, *_CORAL_BLOCKS)
    | TRUNK - frozenset(_wood_blocks(overworld=False)) - frozenset(
        b for b in _wood_blocks(nether=False) if b.startswith("minecraft:stripped_"))
    | (LEAVES - _mc("nether_wart_block", "warped_wart_block", "shroomlight"))
    | ATTACHED | PLANTS)


def base_id(state: str) -> str:
    """The block id of a state string, without its ``[...]`` part."""
    return state.split("[", 1)[0]


_AIR_K, _WATER_K, _LAVA_K, _TRUNK_K, _LEAF_K, _ATT_K, _PLANT_K, _OTHER_K = range(8)


@lru_cache(maxsize=None)
def _kind(state: str) -> int:
    b = base_id(state)
    if b in _AIR:
        return _AIR_K
    if b in _WATER:
        return _WATER_K
    if b in _LAVA:
        return _LAVA_K
    if b in TRUNK:
        return _TRUNK_K
    if b in LEAVES:
        return _LEAF_K
    if b in ATTACHED:
        return _ATT_K
    if b in PLANTS:
        return _PLANT_K
    return _OTHER_K


# --------------------------------------------------------------------- Site
@dataclass
class Site:
    box: Box
    world: str | None
    columns: dict[tuple[int, int], list[Run]]

    def block(self, x: int, y: int, z: int) -> str:
        x1, y1, z1, x2, y2, z2 = self.box
        if not (x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2):
            raise KeyError((x, y, z))
        for ya, yb, state in self.columns[(x, z)]:
            if ya <= y <= yb:
                return state
        raise KeyError((x, y, z))


@dataclass
class Surfaces:
    origin: tuple[int, int]
    ground: np.ndarray
    water: np.ndarray
    top: np.ndarray


@dataclass
class Tree:
    cells: set[Cell]
    trunk_columns: set[tuple[int, int]]
    base_y: int


def _check_columns(columns: dict[tuple[int, int], list[Run]], box: Box) -> None:
    x1, y1, z1, x2, y2, z2 = box
    if not (x1 <= x2 and y1 <= y2 and z1 <= z2):
        raise ValueError(f"empty box {box}")
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            runs = columns.get((x, z))
            if not runs:
                raise ValueError(f"column {x},{z} is missing")
            at = y1
            for ya, yb, state in runs:
                if ya != at or yb < ya or not isinstance(state, str):
                    raise ValueError(f"column {x},{z}: runs are not contiguous from y {y1}")
                at = yb + 1
            if at != y2 + 1:
                raise ValueError(f"column {x},{z}: runs do not cover y {y1}..{y2}")
    if len(columns) != (x2 - x1 + 1) * (z2 - z1 + 1):
        raise ValueError("columns outside the box")


def load_site(path: str | Path) -> Site:
    """Read and verify an F1 folder: checksum, complete manifest, contiguous full runs."""
    path = Path(path)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        blob = (path / "columns.json.gz").read_bytes()
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: cannot read the site ({exc.__class__.__name__})") from None
    if not isinstance(manifest, dict) or manifest.get("complete") is not True:
        raise ValueError(f"{path}: not a complete site read")
    if hashlib.sha256(blob).hexdigest() != manifest.get("sha256"):
        raise ValueError(f"{path}: columns.json.gz does not match the manifest checksum")
    try:
        payload = json.loads(gzip.decompress(blob))
        box = tuple(int(v) for v in manifest["box"])
        if len(box) != 6 or payload["version"] != 1 or list(box) != payload["box"]:
            raise ValueError("box or version mismatch")
        columns: dict[tuple[int, int], list[Run]] = {}
        for key, runs in payload["columns"].items():
            x, z = key.split(",")
            columns[(int(x), int(z))] = [(int(a), int(b), str(s)) for a, b, s in runs]
        world = payload.get("world")
    except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{path}: malformed site read ({exc.__class__.__name__})") from None
    if len(columns) != manifest.get("columns"):
        raise ValueError(f"{path}: column count does not match the manifest")
    _check_columns(columns, box)  # type: ignore[arg-type]
    return Site(box=box, world=world, columns=columns)  # type: ignore[arg-type]


def write_site(path: str | Path, site: Site) -> None:
    """Write F1 with the same bytes layout as the placer's ``write_backup``."""
    path = Path(path)
    _check_columns(site.columns, site.box)
    x1, _, z1, x2, _, z2 = site.box
    payload = {"version": 1, "world": site.world, "box": list(site.box),
               "columns": {f"{x},{z}": [[a, b, s] for a, b, s in site.columns[(x, z)]]
                           for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)}}
    blob = gzip.compress(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                         .encode("utf-8"), mtime=0)
    manifest = {"version": 1, "box": list(site.box), "world": site.world,
                "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "columns": len(payload["columns"]), "sha256": hashlib.sha256(blob).hexdigest(),
                "plugin": None, "complete": True}
    path.mkdir(parents=True, exist_ok=True)
    temps = [path / ".columns.json.gz.tmp", path / ".manifest.json.tmp"]
    temps[0].write_bytes(blob)
    temps[1].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temps[0].replace(path / "columns.json.gz")
    temps[1].replace(path / "manifest.json")


def load_heights(path: str | Path) -> dict:
    """Read an F2 heights file: ``{"origin": (x1, z1), "ground", "surface", "top"}``,
    arrays ``(nx, nz)`` of float with NaN for null; ``F2[xi * nz + zi] -> arr[xi, zi]``."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        nx, nz = (int(v) for v in data["size"])
        origin = (int(data["origin"][0]), int(data["origin"][1]))
        out: dict = {"origin": origin}
        for name in ("ground", "surface", "top"):
            values = data[name]
            if len(values) != nx * nz:
                raise ValueError(f"{name} has {len(values)} entries, expected {nx * nz}")
            flat = np.array([np.nan if v is None else v for v in values], dtype=float)
            out[name] = flat.reshape(nx, nz)
    except (OSError, KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"{path}: malformed heights file ({exc.__class__.__name__})") from None
    return out


# ----------------------------------------------------------------- surfaces
def is_water_state(state: str) -> bool:
    """Water-like cell: water, bubble column, a water plant (kelp, seagrass) or any
    non-ground block with ``waterlogged=true`` (mangrove roots, corals, coral fans).
    A waterlogged ground-class block (stairs, slabs) is not water-like. Ice is handled
    per column by `water_run_flags`."""
    k = _kind(state)
    if k == _WATER_K:
        return True
    if k == _PLANT_K and base_id(state) in _WATER_PLANTS:
        return True
    return k in (_TRUNK_K, _LEAF_K, _ATT_K, _PLANT_K) and "waterlogged=true" in state


def water_run_flags(runs: list[Run]) -> list[bool]:
    """Per run of one column (bottom to top): does it count as water? A run is water
    if `is_water_state`, or if it is ``minecraft:ice`` lying directly on a water run
    (ice over ice over water included). Ice on solid, packed and blue ice are ground."""
    flags: list[bool] = []
    for i, (_ya, _yb, state) in enumerate(runs):
        flags.append(is_water_state(state)
                     or (base_id(state) == "minecraft:ice" and i > 0 and flags[i - 1]))
    return flags


def surfaces(site: Site) -> Surfaces:
    """Existing ground (highest block that is not air, fluid, trunk, leaves, attachment
    or plant), water surface (where water lies above the ground) and top (highest
    non-air block, trees included) per column."""
    x1, _, z1, x2, _, z2 = site.box
    shape = (x2 - x1 + 1, z2 - z1 + 1)
    ground = np.full(shape, np.nan)
    water = np.full(shape, np.nan)
    top = np.full(shape, np.nan)
    for (x, z), runs in site.columns.items():
        xi, zi = x - x1, z - z1
        g = t = w = None
        flags = water_run_flags(runs)
        for i in range(len(runs) - 1, -1, -1):
            ya, yb, state = runs[i]
            k = _kind(state)
            if k == _AIR_K:
                continue
            if t is None:
                t = yb
            if flags[i]:
                if w is None:
                    w = yb
                continue
            if k != _OTHER_K:  # lava, trunk, leaves, attachment, plant
                continue
            g = yb
            break
        if t is not None:
            top[xi, zi] = t
        if g is not None:
            ground[xi, zi] = g
        if w is not None and (g is None or w > g):
            water[xi, zi] = w
    return Surfaces(origin=(x1, z1), ground=ground, water=water, top=top)


# -------------------------------------------------------------------- trees
_N6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
_N26 = tuple((a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)
             if (a, b, c) != (0, 0, 0))
_ATTACH_TOP = _mc("snow", "moss_carpet", "pale_moss_carpet")
_ATTACH_HANGING = _mc("vine", "cave_vines", "cave_vines_plant", "weeping_vines",
                      "weeping_vines_plant", "pale_hanging_moss", "mangrove_propagule")


def _attach_kind(block_id: str) -> str:
    """How an attachment joins a tree: lies on top of a cell, hangs, or clings to a side."""
    if block_id in _ATTACH_TOP:
        return "top"
    return "hanging" if block_id in _ATTACH_HANGING else "side"


LEAF_REACH = 6  # vanilla leaf distance: a leaf survives within 6 steps of a log


def find_trees(site: Site) -> list[Tree]:
    """Group trunks (26-connected log cells) into trees; give each leaf to the trunk
    reachable through 6-connected leaves in the fewest steps (at most 6; ties go to the
    lower base_y, then the smaller first cell) and each attachment to the tree whose
    cells it touches. Trees are ordered by (base_y, first trunk cell)."""
    trunks: set[Cell] = set()
    leaves: set[Cell] = set()
    attached: dict[Cell, str] = {}
    for (x, z), runs in site.columns.items():
        for ya, yb, state in runs:
            k = _kind(state)
            if k == _TRUNK_K:
                target = trunks
            elif k == _LEAF_K:
                target = leaves
            elif k == _ATT_K:
                attached.update(((x, y, z), base_id(state)) for y in range(ya, yb + 1))
                continue
            else:
                continue
            target.update((x, y, z) for y in range(ya, yb + 1))

    components: list[list[Cell]] = []
    seen: set[Cell] = set()
    for start in sorted(trunks):
        if start in seen:
            continue
        seen.add(start)
        comp, stack = [], [start]
        while stack:
            c = stack.pop()
            comp.append(c)
            for dx, dy, dz in _N26:
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in trunks and n not in seen:
                    seen.add(n)
                    stack.append(n)
        components.append(sorted(comp))
    components.sort(key=lambda comp: (min(c[1] for c in comp), comp[0]))

    owner: dict[Cell, int] = {}
    dist: dict[Cell, int] = {}
    for rank, comp in enumerate(components):
        for c in comp:
            owner[c] = rank
            dist[c] = 0

    frontier = list(owner)
    for step in range(1, LEAF_REACH + 1):
        found: dict[Cell, int] = {}
        for c in frontier:
            rank = owner[c]
            for dx, dy, dz in _N6:
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in leaves and n not in owner:
                    found[n] = min(rank, found.get(n, rank))
        for n, rank in found.items():
            owner[n] = rank
            dist[n] = step
        frontier = list(found)
        if not frontier:
            break

    # Attachments join by type and never through one another, except a hanging chain:
    # on-top types need a trunk/leaf cell directly below; side types need one 6-adjacent;
    # hanging types need one 6-adjacent or an assigned hanging cell directly above.
    # Cells go top-down so a chain is one pass. Ties: (distance, trunk rank).
    solid = dict(owner)  # trunk and leaf cells only
    hanging_owner: dict[Cell, tuple[int, int]] = {}
    for c in sorted(attached, key=lambda cell: (-cell[1], cell)):
        kind = _attach_kind(attached[c])
        best: tuple[int, int] | None = None
        if kind == "top":
            below = (c[0], c[1] - 1, c[2])
            if below in solid:
                best = (dist[below], solid[below])
        else:
            for dx, dy, dz in _N6:
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in solid:
                    key = (dist[n], solid[n])
                    if best is None or key < best:
                        best = key
            if kind == "hanging":
                above = hanging_owner.get((c[0], c[1] + 1, c[2]))
                if above is not None and (best is None or above < best):
                    best = above
        if best is not None:
            owner[c] = best[1]
            dist[c] = best[0] + 1
            if kind == "hanging":
                hanging_owner[c] = (best[0] + 1, best[1])

    cells: list[set[Cell]] = [set() for _ in components]
    for c, rank in owner.items():
        cells[rank].add(c)
    trees = []
    for rank, comp in enumerate(components):
        base = min(c[1] for c in comp)
        trees.append(Tree(cells=cells[rank],
                          trunk_columns={(c[0], c[2]) for c in comp if c[1] == base},
                          base_y=base))
    return trees


# ------------------------------------------------------------- non-natural
def unnatural_blocks(site: Site, box: Box) -> dict[str, int]:
    """Count the cells inside `box` (clipped to the site) whose block id is not in
    NATURAL, by id without states."""
    x1 = max(box[0], site.box[0]); y1 = max(box[1], site.box[1]); z1 = max(box[2], site.box[2])
    x2 = min(box[3], site.box[3]); y2 = min(box[4], site.box[4]); z2 = min(box[5], site.box[5])
    counts: dict[str, int] = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            for ya, yb, state in site.columns[(x, z)]:
                n = min(yb, y2) - max(ya, y1) + 1
                if n > 0:
                    b = base_id(state)
                    if b not in NATURAL:
                        counts[b] = counts.get(b, 0) + n
    return counts


# ------------------------------------------------- meeting the existing ground
def _ring_distance(nx: int, nz: int) -> np.ndarray:
    xi, zi = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
    return np.minimum(np.minimum(xi, zi), np.minimum(nx - 1 - xi, nz - 1 - zi))


def auto_band(h: np.ndarray, ground: np.ndarray) -> int:
    """Blend width: max(8, ceil(0.3 * largest |h - ground| over the 8 outermost
    rings)), at most min(nx, nz) // 2."""
    nx, nz = h.shape
    outer = _ring_distance(nx, nz) < 8
    diff = float(np.max(np.abs(h - ground)[outer]))
    return int(min(max(8, math.ceil(0.3 * diff)), min(nx, nz) // 2))


def blend_to_existing(hf: HeightField, ground: np.ndarray, band: int) -> HeightField:
    """Return a new field equal to `ground` on the outer ring and to `hf` more than
    `band` rings in: w = smoothstep(0, band, d), h = ground * (1 - w) + h * w."""
    d = _ring_distance(hf.nx, hf.nz)
    w = smoothstep(0.0, float(band), d.astype(float))
    out = HeightField(hf.nx, hf.nz, sea_level=hf.sea_level)
    out.h = ground * (1.0 - w) + hf.h * w
    return out


def ground_for(recipe: dict, project_dir: Path) -> tuple[Site, Surfaces, np.ndarray]:
    """Load the recipe's site read and crop its ground to the recipe grid."""
    site = load_site(Path(project_dir) / recipe["site"]["read"])
    surf = surfaces(site)
    nx, nz = int(recipe["nx"]), int(recipe["nz"])
    gx, gz = int(recipe["origin"][0]), int(recipe["origin"][2])
    sx1, _, sz1, sx2, _, sz2 = site.box
    if gx < sx1 or gz < sz1 or gx + nx - 1 > sx2 or gz + nz - 1 > sz2:
        raise ValueError(f"recipe grid x {gx}..{gx + nx - 1}, z {gz}..{gz + nz - 1} is not "
                         f"inside the site read x {sx1}..{sx2}, z {sz1}..{sz2}")
    ox, oz = gx - sx1, gz - sz1
    ground = surf.ground[ox:ox + nx, oz:oz + nz].copy()
    if np.isnan(ground).any():
        xi, zi = (int(v) for v in np.argwhere(np.isnan(ground))[0])
        raise ValueError(f"no solid block in the site read at x {gx + xi}, z {gz + zi}")
    return site, surf, ground


def surface_y(h) -> np.ndarray:
    """The block y a field height builds as: ``np.rint`` (half to even), NaN kept. Every
    comparison of a field height with a block level (floods, water and edge checks,
    hold_shores, planting) goes through this one helper."""
    return np.rint(np.asarray(h, dtype=float))


def integer_level(value, name: str) -> int:
    """`value` as an int; bool, non-numbers and non-integral numbers are a ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) \
            or not float(value).is_integer():
        raise ValueError(f"{name} must be an integer, got {value!r}")
    return int(value)


def _label_below(sy: np.ndarray, level: float):
    return ndimage.label(sy < level)    # 4-connected by default


def water_levels(hf: HeightField, recipe: dict) -> np.ndarray:
    """(nx, nz) planned water level or NaN. Basins flood first: each ``water`` entry
    claims the 4-connected columns (heights through `surface_y`) below its level from its
    `at` cell (world x, z); two floods meeting at different levels are an error, in any
    order. Then ``sea_level`` fills the unclaimed columns below it. A basin at another
    level may not reach the open sea (columns below sea_level connected to the outer
    ring); write the sea as a ``water`` entry instead. Levels must be integers (``sea_level``
    too when the recipe has a ``site``). Never fed with retained (existing) liquid."""
    sy = surface_y(hf.h)
    nx, nz = sy.shape
    ox, oz = int(recipe["origin"][0]), int(recipe["origin"][2])
    sea = None
    if "sea_level" in recipe:
        sea = (integer_level(recipe["sea_level"], "sea_level") if recipe.get("site")
               else float(recipe["sea_level"]))
    claims = np.full(sy.shape, np.nan)
    for entry in recipe.get("water") or []:
        level = integer_level(entry["level"], "water level")
        ax, az = int(entry["at"][0]) - ox, int(entry["at"][1]) - oz
        if not (0 <= ax < nx and 0 <= az < nz):
            raise ValueError(f"water at {tuple(entry['at'])} is outside the grid")
        if not sy[ax, az] < level:
            raise ValueError(f"water at {tuple(entry['at'])}: ground {sy[ax, az]:g} "
                             f"is not below level {level}")
        labels, _ = _label_below(sy, level)
        region = labels == labels[ax, az]
        clash = region & ~np.isnan(claims) & (claims != level)
        if clash.any():
            cx, cz = (int(v) for v in np.argwhere(clash)[0])
            raise ValueError(
                f"water at {tuple(entry['at'])} (level {level}) meets a flood at level "
                f"{claims[cx, cz]:g} at ({cx + ox}, {cz + oz}); put a sill (columns at or above "
                f"the higher level) between them or give both the same level")
        claims[region] = level
    if sea is None:
        return claims
    labels, _ = _label_below(sy, sea)
    ring = np.zeros(sy.shape, bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    open_labels = np.unique(labels[ring & (labels > 0)])
    open_sea = np.isin(labels, open_labels) & (labels > 0)
    clash = open_sea & ~np.isnan(claims) & (claims != sea)
    if clash.any():
        cx, cz = (int(v) for v in np.argwhere(clash)[0])
        raise ValueError(
            f"a water entry at level {claims[cx, cz]:g} reaches the open sea (level {sea:g}) "
            f"at ({cx + ox}, {cz + oz}); write the sea as a `water` entry at its own level "
            f"instead of relying on sea_level")
    levels = claims.copy()
    levels[(sy < sea) & np.isnan(claims)] = sea
    return levels


# ----------------------------------------------------------- existing liquid
_LEVEL_RE = re.compile(r"level=(\d+)")
_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def liquid_kind(state: str) -> str | None:
    """``"water"`` for a water-like state (see `is_water_state`), ``"lava"`` for lava,
    else None. Ice is not decided by its state alone: see `is_retained`."""
    if _kind(state) == _LAVA_K:
        return "lava"
    return "water" if is_water_state(state) else None


def is_retained(state: str, below_is_water: bool = False) -> bool:
    """Does the cell count as existing surface liquid (when it lies above the column's
    ground)? Water, bubble columns, water plants, waterlogged non-ground blocks and lava
    always; ``minecraft:ice`` only with ``below_is_water=True`` (it lies on a water run)."""
    return liquid_kind(state) is not None or (
        below_is_water and base_id(state) == "minecraft:ice")


def is_still(state: str) -> bool:
    """A retained state that is not flowing: water and lava need ``level`` absent or 0
    (a source); every other retained state (bubble column, plants, waterlogged blocks,
    ice) is still."""
    if _kind(state) in (_WATER_K, _LAVA_K):
        m = _LEVEL_RE.search(state)
        return m is None or int(m.group(1)) == 0
    return True


@dataclass(frozen=True)
class DrainBody:
    """One complete component of retained cells, identified independently of its seed."""
    id: str
    seed: tuple[int, int]
    cells: dict[Cell, str]

    @property
    def bbox(self) -> Box:
        xs, ys, zs = zip(*self.cells)
        return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.cells.values())))

    @property
    def columns(self) -> set[tuple[int, int]]:
        return {(x, z) for x, _, z in self.cells}


def drain_bodies(site: Site, recipe: dict, *, protect: np.ndarray | None = None) -> list[DrainBody]:
    """Resolve recipe seeds against the original read; dry trunks bridge only at equal y."""
    entries = recipe.get("drain", [])
    if not isinstance(entries, list) or any(not isinstance(entry, dict) or entry.keys() != {"at"}
                                            for entry in entries):
        raise ValueError("drain must be a list of {at: [x, z]} entries")
    if not entries:
        return []
    ox = integer_level(recipe["origin"][0], "origin x")
    oz = integer_level(recipe["origin"][2], "origin z")
    nx, nz = integer_level(recipe["nx"], "nx"), integer_level(recipe["nz"], "nz")
    x1, _, z1, x2, _, z2 = site.box
    if not (x1 <= ox <= ox + nx - 1 <= x2 and z1 <= oz <= oz + nz - 1 <= z2):
        raise ValueError("drain grid outside the site read")
    if protect is not None:
        protect = np.asarray(protect)
        if protect.dtype != np.bool_ or protect.shape != (nx, nz):
            raise ValueError("protect must be a boolean mask matching the field")
    _check_columns(site.columns, site.box)
    if any(base_id(runs[-1][2]) not in _AIR for runs in site.columns.values()):
        raise ValueError("read higher: the site must end in air")
    ground = surfaces(site).ground

    @cache
    def spans(x, z):
        # Classify only columns the search visits. Each retained span is above g.
        g = ground[x - x1, z - z1]
        lowest = site.box[1] if np.isnan(g) else int(g) + 1
        runs = site.columns[x, z]
        out = []
        for (lo, hi, state), wet in zip(runs, water_run_flags(runs)):
            if hi < lowest:
                continue
            if wet:
                kind = "water"
            elif _kind(state) == _LAVA_K:
                kind = "lava"
            elif _kind(state) == _TRUNK_K:
                kind = "trunk"
            else:
                continue
            out.append((max(lo, lowest), hi, kind))
        return out

    bodies = []
    resolved = set()
    for entry in entries:
        at = entry["at"]
        if not isinstance(at, (list, tuple)) or len(at) != 2:
            raise ValueError("drain at must be [x, z]")
        sx, sz = seed = (integer_level(at[0], "drain x"), integer_level(at[1], "drain z"))
        if not (ox <= sx < ox + nx and oz <= sz < oz + nz):
            raise ValueError(f"drain seed {seed} outside terrain grid")
        start = next((((sx, lo, sz), k) for lo, _, k in spans(sx, sz) if k != "trunk"), None)
        if start is None:
            raise ValueError(f"drain seed {seed} has no retained liquid above ground")
        if start[0] in resolved:
            continue
        cells: dict[Cell, str] = {}
        seen = {start[0]}
        stack = [start]
        while stack:
            cell, kind = stack.pop()
            x, y, z = cell
            if np.isnan(ground[x - x1, z - z1]):
                raise ValueError(f"read lower: drain reaches a column with unknown ground at {cell}")
            if x in (x1, x2) or z in (z1, z2):
                raise ValueError(f"drain reaches the site read edge at {cell}")
            if kind != "trunk":
                if not (ox < x < ox + nx - 1 and oz < z < oz + nz - 1):
                    raise ValueError(f"drain body reaches the terrain outer ring or leaves the box at {cell}")
                if protect is not None and protect[x - ox, z - oz]:
                    raise ValueError(f"drain body reaches protected column {(x, z)}")
                cells[cell] = kind
            for dx, dy, dz in _N6:
                neighbour = (x + dx, y + dy, z + dz)
                if neighbour in seen or (dy and kind == "trunk"):
                    continue
                other = next((k for lo, hi, k in spans(x + dx, z + dz) if lo <= y + dy <= hi), None)
                if other is not None and not (dy and other == "trunk"):
                    seen.add(neighbour)
                    stack.append((neighbour, other))
        records = "\n".join(f"{x},{y},{z},{k}" for (x, y, z), k in sorted(cells.items()))
        body_id = hashlib.sha256(records.encode("utf-8")).hexdigest()[:12]
        if any(body.id == body_id for body in bodies):
            raise ValueError(f"distinct drain bodies have the same short id {body_id}")
        bodies.append(DrainBody(body_id, seed, cells))
        resolved.update(cells)
    return bodies


@dataclass
class LiquidLevels:
    """Existing surface liquid per column of the site box, arrays ``(nx, nz)``.

    ``level`` L: top of the unbroken run of still retained cells starting at ground+1
    (NaN if none). ``kind``: ``"water"``/``"lava"``/None, the kind at L. ``top``: the
    highest retained cell above the ground, still or not (NaN if none). ``joined``:
    removed-tree cells that count as still, mapped to their liquid kind."""
    level: np.ndarray
    kind: np.ndarray
    top: np.ndarray
    joined: dict[tuple[int, int, int], str]


def _ground_int(surf: Surfaces, xi: int, zi: int, y1: int) -> int:
    g = surf.ground[xi, zi]
    return y1 - 1 if np.isnan(g) else int(g)


def liquid_levels(site: Site, removed: Iterable[Cell] = (),
                  surf: Surfaces | None = None, *, excluded: Iterable[Cell] = ()) -> LiquidLevels:
    """Retained liquid per column (above the ground only), with `removed` tree cells
    joined into still liquid: a removed cell above its column's ground that touches a
    still or joined cell horizontally at the same y, or lies directly below one (downward
    only, never upward), counts as still with that liquid, repeated until stable. Cells
    in `excluded` neither retain liquid nor join or seed the removed-tree flood."""
    if surf is None:
        surf = surfaces(site)
    x1, y1, z1, x2, y2, z2 = site.box
    shape = (x2 - x1 + 1, z2 - z1 + 1)
    level = np.full(shape, np.nan)
    kind = np.full(shape, None, dtype=object)
    top = np.full(shape, np.nan)
    excluded = set(excluded)
    excluded_y: dict[tuple[int, int], list[int]] = {}
    for x, y, z in excluded:
        excluded_y.setdefault((x, z), []).append(y)
    for ys in excluded_y.values():
        ys.sort()
    items: dict[tuple[int, int], list[tuple[int, int, str, bool]]] = {}
    for (x, z), runs in site.columns.items():
        xi, zi = x - x1, z - z1
        g = _ground_int(surf, xi, zi, y1)
        flags = water_run_flags(runs)
        col = []
        for (ya, yb, state), is_water in zip(runs, flags):
            k = "water" if is_water else ("lava" if _kind(state) == _LAVA_K else None)
            lo = max(ya, g + 1)
            if k is not None and lo <= yb:
                ys = excluded_y.get((x, z), ())
                for y in ys[bisect_left(ys, lo):bisect_right(ys, yb)]:
                    if lo < y:
                        col.append((lo, y - 1, k, is_still(state)))
                    lo = y + 1
                if lo <= yb:
                    col.append((lo, yb, k, is_still(state)))
        if col:
            items[(x, z)] = col
            top[xi, zi] = max(c[1] for c in col)

    def still_kind(x: int, z: int, y: int) -> str | None:
        for lo, hi, k, st in items.get((x, z), ()):
            if st and lo <= y <= hi:
                return k
        return None

    pending = {(int(c[0]), int(c[1]), int(c[2])) for c in removed
               if x1 <= c[0] <= x2 and y1 <= c[1] <= y2 and z1 <= c[2] <= z2}
    pending = {c for c in pending if c not in excluded and c[1] > _ground_int(surf, c[0] - x1, c[2] - z1, y1)}
    joined: dict[Cell, str] = {}
    queue: list[Cell] = []
    for x, y, z in pending:
        k = still_kind(x, z, y + 1)          # directly below a still cell
        for dx, dz in _N4:
            if k is not None:
                break
            k = still_kind(x + dx, z + dz, y)  # or beside one at the same y
        if k is not None:
            joined[(x, y, z)] = k
            queue.append((x, y, z))
    while queue:
        x, y, z = queue.pop()
        k = joined[(x, y, z)]
        for n in ((x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1), (x, y - 1, z)):
            if n in pending and n not in joined:   # beside, or directly below (never above)
                joined[n] = k
                queue.append(n)
    joined_by_col: dict[tuple[int, int], dict[int, str]] = {}
    for (x, y, z), k in joined.items():
        joined_by_col.setdefault((x, z), {})[y] = k

    for key in items.keys() | joined_by_col.keys():
        x, z = key
        xi, zi = x - x1, z - z1
        g = _ground_int(surf, xi, zi, y1)
        col = items.get(key, ())
        jy = joined_by_col.get(key, {})
        cur, k_at = g + 1, None
        while True:
            for lo, hi, k, st in col:
                if st and lo <= cur <= hi:
                    cur, k_at = hi + 1, k
                    break
            else:
                if cur in jy:
                    k_at = jy[cur]
                    cur += 1
                else:
                    break
        if cur > g + 1:
            level[xi, zi] = cur - 1
            kind[xi, zi] = k_at
    return LiquidLevels(level=level, kind=kind, top=top, joined=joined)


def hold_shores(h: np.ndarray, site: Site, *, origin: tuple[int, int],
                skip: np.ndarray | None = None, excluded: Iterable[Cell] = ()) -> np.ndarray:
    """A copy of grid heights `h` lifted so existing liquid keeps a bank. `origin` is the
    grid's world (x1, z1); `skip` a boolean mask of columns to leave alone (pad
    footprints). The outer ring is never changed. For each interior column (existing
    liquid from ``liquid_levels(site)``, no removed trees; heights through `surface_y`):
    liquid with no still level: raised to the ground; dry and 4-adjacent to liquid:
    raised to min(ground, highest neighbouring top), a neighbour's top being the higher of
    its retained ``top`` and any of its cells that would join still liquid if every tree
    were removed. Cells in `excluded` belong to complete bodies selected for drainage."""
    out = np.array(h, dtype=float)
    nx, nz = out.shape
    sx1, _, sz1, sx2, _, sz2 = site.box
    ox, oz = int(origin[0]) - sx1, int(origin[1]) - sz1
    if ox < 0 or oz < 0 or int(origin[0]) + nx - 1 > sx2 or int(origin[1]) + nz - 1 > sz2:
        raise ValueError(f"grid at {tuple(origin)} size {nx}x{nz} is not inside the site read")
    surf = surfaces(site)
    excluded = set(excluded)
    ll = liquid_levels(site, surf=surf, excluded=excluded)
    felled = liquid_levels(site, removed=[c for t in find_trees(site) for c in t.cells],
                           surf=surf, excluded=excluded)
    jtop = np.full(ll.top.shape, np.nan)
    for (x, y, z) in felled.joined:
        jtop[x - sx1, z - sz1] = np.fmax(jtop[x - sx1, z - sz1], y)
    sl = (slice(ox, ox + nx), slice(oz, oz + nz))
    g, top, lvl = surf.ground[sl], ll.top[sl], ll.level[sl]
    liquid = ~np.isnan(top)
    padded = np.full((nx + 2, nz + 2), np.nan)
    padded[1:-1, 1:-1] = np.fmax(top, jtop[sl])    # retained top, or what felling joins
    nbr = np.fmax(np.fmax(padded[2:, 1:-1], padded[:-2, 1:-1]),
                  np.fmax(padded[1:-1, 2:], padded[1:-1, :-2]))
    target = np.where(liquid, np.where(np.isnan(lvl), g, np.nan), np.minimum(g, nbr))
    interior = np.ones((nx, nz), bool)
    interior[0, :] = interior[-1, :] = interior[:, 0] = interior[:, -1] = False
    move = interior & ~np.isnan(target) & (surface_y(out) < target)
    if skip is not None:
        move &= ~np.asarray(skip, dtype=bool)
    out[move] = target[move]
    return out
