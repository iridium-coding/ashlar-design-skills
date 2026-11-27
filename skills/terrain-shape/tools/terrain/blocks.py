"""Block helpers shared by caves and transit.

Site grids and masks, block light, the player-block rules (what a layer touches,
what a block write would lose) and the write-layer helpers. Moved out of
``caves`` unchanged so every terrain module uses one copy.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from functools import cache

import numpy as np

from .ashlar_emit import _COVER, _FLUID, _OPEN, _flags
from .live import LiveWrite
from .site import _AIR, NATURAL, Site, base_id

# Block light emitted by full-block sources and common placed or natural lights.
_LIGHT_LEVELS = {
    **{f"minecraft:{n}": 15 for n in (
        "glowstone", "shroomlight", "sea_lantern", "ochre_froglight", "verdant_froglight",
        "pearlescent_froglight", "lantern", "jack_o_lantern", "beacon", "lava", "conduit",
        "end_gateway", "end_portal", "fire")},
    **{f"minecraft:{n}": 14 for n in ("torch", "wall_torch", "end_rod")},
    **{f"minecraft:{n}": 10 for n in (
        "soul_lantern", "soul_torch", "soul_wall_torch", "crying_obsidian", "soul_fire")},
    "minecraft:glow_lichen": 7,
    "minecraft:amethyst_cluster": 5,
    "minecraft:large_amethyst_bud": 4,
    "minecraft:magma_block": 3,
    "minecraft:medium_amethyst_bud": 2,
    "minecraft:small_amethyst_bud": 1,
    "minecraft:sculk_sensor": 1,
    "minecraft:brown_mushroom": 1,
}


def dims(box: tuple[int, ...]) -> tuple[int, int, int]:
    x1, y1, z1, x2, y2, z2 = box
    return x2 - x1 + 1, y2 - y1 + 1, z2 - z1 + 1


def site_flags(site: Site) -> np.ndarray:
    x1, y1, z1 = site.box[:3]
    grid = np.empty(dims(site.box), np.uint16)
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            grid[x - x1, lo - y1:hi - y1 + 1, z - z1] = _flags(state)
    return grid


def site_ids(site: Site) -> tuple[np.ndarray, list[str]]:
    """Per-cell block id codes and the id list, for repeated id lookups."""
    names: list[str] = []
    index: dict[str, int] = {}
    x1, y1, z1, _, _, _ = site.box
    grid = np.empty(dims(site.box), np.uint16)
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            block = base_id(state)
            if block not in index:
                index[block] = len(names)
                names.append(block)
            grid[x - x1, lo - y1:hi - y1 + 1, z - z1] = index[block]
    return grid, names



# Player blocks that are not full cubes. Anything else a player placed counts as one.
_PARTIAL_SUFFIXES = (
    "_stairs", "_slab", "_fence", "_fence_gate", "_wall", "_pane", "_bars", "_door", "_trapdoor",
    "_carpet", "_sign", "_button", "_pressure_plate", "_bed", "candle", "_head", "_skull", "_banner",
    "rail", "torch", "lantern", "chain", "ladder", "lever", "_coral_fan", "flower_pot", "scaffolding",
    "end_rod", "lightning_rod", "bell", "anvil", "cauldron", "hopper", "brewing_stand", "lectern",
    "enchanting_table", "grindstone", "stonecutter", "chest", "campfire", "decorated_pot", "cake",
    "_cluster", "_bud", "repeater", "comparator", "redstone_wire", "tripwire", "tripwire_hook",
    "daylight_detector", "conduit", "sea_pickle", "turtle_egg", "dragon_egg", "pointed_dripstone",
    "heavy_core", "_shelf", "item_frame", "_vines", "vine", "_roots", "glow_lichen", "snow",
)
_LIGHT_THROUGH = frozenset(f"minecraft:{n}" for n in (
    "glass", "ice", "frosted_ice", "beacon", "slime_block", "honey_block"))



@cache
def full_cube(state: str) -> bool:
    """Whether ``state`` fills its cell: walls, floors and ceilings are made of these."""
    block = base_id(state)
    flags = _flags(state)
    if flags & _COVER:
        return True
    if block in _AIR or flags & (_OPEN | _FLUID) or block in NATURAL:
        return False
    if "type=double" in state:
        return True
    return not (block.endswith(_PARTIAL_SUFFIXES) or block.startswith("minecraft:potted_"))


@cache
def lets_light(state: str) -> bool:
    block = base_id(state)
    return (not full_cube(state) or block in _LIGHT_THROUGH or block.endswith("_leaves")
            or (block.endswith("_glass") and block != "minecraft:tinted_glass"))


def cell_classes(site: Site) -> tuple[np.ndarray, np.ndarray]:
    """Per cell: a full cube, and letting light through."""
    full = np.zeros(dims(site.box), bool)
    light = np.zeros(dims(site.box), bool)
    x1, y1, z1 = site.box[:3]
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            sl = (x - x1, slice(lo - y1, hi - y1 + 1), z - z1)
            full[sl] = full_cube(state)
            light[sl] = lets_light(state)
    return full, light


def light_of(state: str) -> int:
    block = base_id(state)
    if block in ("minecraft:cave_vines", "minecraft:cave_vines_plant"):
        return 14 if "berries=true" in state else 0
    if block == "minecraft:redstone_lamp":
        return 15 if "lit=true" in state else 0
    if block in ("minecraft:campfire", "minecraft:soul_campfire"):
        if "lit=false" in state:
            return 0
        return 15 if block == "minecraft:campfire" else 10
    if block.endswith("candle"):
        match = re.search(r"candles=(\d)", state)
        return 3 * int(match.group(1)) if "lit=true" in state and match else 0
    return _LIGHT_LEVELS.get(block, 0)


def face_dilate(mask: np.ndarray) -> np.ndarray:
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[:, :, 1:] |= mask[:, :, :-1]
    out[:, :, :-1] |= mask[:, :, 1:]
    return out


def below(mask: np.ndarray) -> np.ndarray:
    """True where the cell directly below is True."""
    out = np.zeros_like(mask)
    out[:, 1:] = mask[:, :-1]
    return out


def above(mask: np.ndarray) -> np.ndarray:
    """True where the cell directly above is True."""
    out = np.zeros_like(mask)
    out[:, :-1] = mask[:, 1:]
    return out


def beside(mask: np.ndarray) -> np.ndarray:
    """True where a horizontal neighbour is True."""
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, :, 1:] |= mask[:, :, :-1]
    out[:, :, :-1] |= mask[:, :, 1:]
    return out


def mask_write(mask: np.ndarray, site: Site, states: np.ndarray | None, palette: list[str]) -> LiveWrite:
    """A LiveWrite over the bounding box of ``mask``; ``states`` holds palette codes."""
    idx = np.argwhere(mask)
    lo, hi = idx.min(axis=0), idx.max(axis=0) + 1
    sl = tuple(slice(a, b) for a, b in zip(lo, hi, strict=True))
    codes = np.zeros(tuple(hi - lo), np.uint16)
    sub = mask[sl]
    codes[sub] = 1 if states is None else states[sl][sub]
    origin = tuple(int(v) + o for v, o in zip(lo, site.box[:3], strict=True))
    return LiveWrite(origin, codes, palette)


def apply_writes(site: Site, layers) -> Site:
    """The site read as it would look after the layers, for checks and previews."""
    y1, y2 = site.box[1], site.box[4]
    ny = y2 - y1 + 1
    changes: dict[tuple[int, int], dict[int, str]] = {}
    for _, write in layers:
        ox, oy, oz = write.origin
        for i, j, k in np.argwhere(write.codes):
            changes.setdefault((ox + int(i), oz + int(k)), {})[oy + int(j)] = write.palette[write.codes[i, j, k]]
    columns = dict(site.columns)
    for (x, z), cells in changes.items():
        states = [""] * ny
        for lo, hi, state in site.columns[(x, z)]:
            for y in range(lo, hi + 1):
                states[y - y1] = state
        for y, state in cells.items():
            states[y - y1] = state
        runs, start = [], 0
        for i in range(1, ny + 1):
            if i == ny or states[i] != states[start]:
                runs.append((y1 + start, y1 + i - 1, states[start]))
                start = i
        columns[(x, z)] = runs
    return Site(box=site.box, world=site.world, columns=columns)


# Blocks whose contents or text live in a block entity that a block write cannot carry.
_DATA_SUFFIXES = ("chest", "barrel", "shulker_box", "furnace", "smoker", "hopper", "dropper",
                  "dispenser", "brewing_stand", "lectern", "_sign", "_banner", "jukebox",
                  "decorated_pot", "chiseled_bookshelf", "crafter", "campfire", "spawner",
                  "vault", "beehive", "bee_nest", "_head", "_skull", "command_block")


def holds_data(state: str) -> bool:
    """True for a block whose contents, text or owner a block write would lose."""
    return base_id(state).endswith(_DATA_SUFFIXES)


def flood(transparent: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Spread block light: one level lost per step through transparent cells."""
    level = level.astype(np.int8)
    for value in range(15, 1, -1):
        frontier = level == value
        if not frontier.any():
            continue
        spread = face_dilate(frontier) & transparent & (level < value - 1)
        level[spread] = value - 1
    return level


def block_light(transparent: np.ndarray, sources: list[tuple[int, int, int, int]],
                box: tuple[int, ...]) -> np.ndarray:
    """Block light over ``box`` from ``(x, y, z, level)`` sources."""
    seeds = np.zeros(transparent.shape, np.int8)
    for x, y, z, value in sources:
        i = (x - box[0], y - box[1], z - box[2])
        seeds[i] = max(seeds[i], value)
    return flood(transparent, seeds)


def site_light(site: Site, skip: np.ndarray | None = None) -> np.ndarray:
    """Seed levels of every light source in the read (cells in ``skip`` excluded)."""
    seeds = np.zeros(dims(site.box), np.int8)
    x1, y1, z1 = site.box[:3]
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            value = light_of(state)
            if value:
                seeds[x - x1, lo - y1:hi - y1 + 1, z - z1] = value
    if skip is not None:
        seeds[skip] = 0
    return seeds


def built_token(items: list[dict]) -> str | None:
    """A short digest of the touched player blocks; approval names this exact list."""
    if not items:
        return None
    blob = json.dumps(sorted((i["cell"], i["block"], i["action"]) for i in items), separators=(",", ":"))
    return "built-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


def cells_write(cells: Mapping[tuple[int, int, int], str]) -> LiveWrite | None:
    """One LiveWrite over the bounding box of ``cells``; None when there are none."""
    if not cells:
        return None
    pts = np.array(list(cells), dtype=np.int64)
    lo, hi = pts.min(axis=0), pts.max(axis=0) + 1
    palette = ["skip"]
    codes = np.zeros(tuple(hi - lo), np.uint16)
    for cell, state in cells.items():
        if state not in palette:
            palette.append(state)
        codes[tuple(np.array(cell) - lo)] = palette.index(state)
    return LiveWrite(tuple(int(v) for v in lo), codes, palette)


def touched_blocks(site: Site, layers: Sequence[tuple[str, LiveWrite]],
                   why: Callable[[str, tuple[int, int, int]], str], *,
                   natural: frozenset[str] = NATURAL) -> list[dict]:
    """Every player block a layer changes; ``why(mode, cell)`` gives each one's reason."""
    ids, names = site_ids(site)
    built = np.array([n not in natural for n in names])[ids]
    x1, y1, z1 = site.box[:3]
    current: dict[tuple[int, int, int], str] = {}
    items: list[dict] = []
    for mode, write in layers:
        ox, oy, oz = write.origin
        sx, sy, sz = write.codes.shape
        region = built[ox - x1:ox - x1 + sx, oy - y1:oy - y1 + sy, oz - z1:oz - z1 + sz]
        cand = (write.codes != 0) & region
        cells = {(ox + int(i), oy + int(j), oz + int(k)) for i, j, k in np.argwhere(cand)}
        cells |= {c for c in current if all(o <= v < o + n for v, o, n in
                                            zip(c, write.origin, write.codes.shape, strict=True))
                  and write.codes[c[0] - ox, c[1] - oy, c[2] - oz]}
        for cell in sorted(cells):
            new = write.palette[write.codes[cell[0] - ox, cell[1] - oy, cell[2] - oz]]
            old = current.get(cell) or site.block(*cell)
            if base_id(old) in natural or new == old:
                current[cell] = new
                continue
            item = {"cell": list(cell), "block": old, "action": mode, "why": why(mode, cell)}
            if holds_data(old):
                item["loses_data"] = True
            items.append(item)
            current[cell] = new
    return items
