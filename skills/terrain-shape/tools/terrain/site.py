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
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

Box = tuple[int, int, int, int, int, int]
Run = tuple[int, int, str]
Cell = tuple[int, int, int]

# ------------------------------------------------------------ block classes
_OVERWORLD_WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak",
                    "mangrove", "cherry", "pale_oak")
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
    f"minecraft:{w}_leaves" for w in _OVERWORLD_WOODS) | _mc(
    "azalea_leaves", "flowering_azalea_leaves", "brown_mushroom_block",
    "red_mushroom_block", "nether_wart_block", "warped_wart_block", "shroomlight")

# Things that hang on or cling to a tree (and snow lying on it).
ATTACHED: frozenset[str] = _mc(
    "vine", "cave_vines", "cave_vines_plant", "weeping_vines", "weeping_vines_plant",
    "twisting_vines", "twisting_vines_plant", "cocoa", "bee_nest", "glow_lichen",
    "moss_carpet", "pale_moss_carpet", "hanging_roots", "mangrove_propagule", "snow",
    "pale_hanging_moss")

_FLOWERS = ("dandelion", "poppy", "blue_orchid", "allium", "azure_bluet", "red_tulip",
            "orange_tulip", "white_tulip", "pink_tulip", "oxeye_daisy", "cornflower",
            "lily_of_the_valley", "wither_rose", "torchflower", "torchflower_crop",
            "pitcher_plant", "pitcher_crop", "sunflower", "lilac", "rose_bush", "peony",
            "open_eyeblossom", "closed_eyeblossom", "spore_blossom", "pink_petals",
            "wildflowers", "cactus_flower")
_CORALS = tuple(f"{p}{c}_{k}" for p in ("", "dead_") for c in
                ("tube", "brain", "bubble", "fire", "horn") for k in ("coral", "coral_fan"))

# Vegetation that never counts as ground (plants, aquatic plants, small fungi, cactus).
PLANTS: frozenset[str] = _mc(
    "short_grass", "grass", "tall_grass", "fern", "large_fern", "short_dry_grass",
    "tall_dry_grass", "dead_bush", "bush", "firefly_bush", "leaf_litter", "sweet_berry_bush",
    "sugar_cane", "bamboo", "bamboo_sapling", "kelp", "kelp_plant", "seagrass",
    "tall_seagrass", "lily_pad", "brown_mushroom", "red_mushroom", "azalea",
    "flowering_azalea", "big_dripleaf", "big_dripleaf_stem", "small_dripleaf", "cactus",
    "sea_pickle", "crimson_fungus", "warped_fungus", "crimson_roots", "warped_roots",
    "nether_sprouts", "pale_oak_sapling",
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
        for ya, yb, state in reversed(runs):
            k = _kind(state)
            if k == _AIR_K:
                continue
            if t is None:
                t = yb
            if k == _WATER_K or (k == _PLANT_K and base_id(state) in _WATER_PLANTS):
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
LEAF_REACH = 6  # vanilla leaf distance: a leaf survives within 6 steps of a log


def find_trees(site: Site) -> list[Tree]:
    """Group trunks (26-connected log cells) into trees; give each leaf to the trunk
    reachable through 6-connected leaves in the fewest steps (at most 6; ties go to the
    lower base_y, then the smaller first cell) and each attachment to the tree whose
    cells it touches. Trees are ordered by (base_y, first trunk cell)."""
    trunks: set[Cell] = set()
    leaves: set[Cell] = set()
    attached: set[Cell] = set()
    for (x, z), runs in site.columns.items():
        for ya, yb, state in runs:
            k = _kind(state)
            if k == _TRUNK_K:
                target = trunks
            elif k == _LEAF_K:
                target = leaves
            elif k == _ATT_K:
                target = attached
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

    pending = set(attached)
    while pending:
        found = {}
        for c in pending:
            best: tuple[int, int] | None = None
            for dx, dy, dz in _N6:
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in owner:
                    key = (dist[n], owner[n])
                    if best is None or key < best:
                        best = key
            if best is not None:
                found[c] = best
        if not found:
            break
        for c, (d, rank) in found.items():
            owner[c] = rank
            dist[c] = d + 1
        pending -= set(found)

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
