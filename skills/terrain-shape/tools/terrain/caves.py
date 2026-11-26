"""Designed caves: a cave design turned into checked, backed-up Ashlar phases.

A design file (the terrain-cave skill's ``reference/caves.md`` documents it)
names chambers, passages, ravines, shafts and pillars. The generator carves a
void from them inside an exact site read, dresses the natural rock around the
void, fills pools, sets lights into the rock until every floor cell is lit,
and plans vanilla cave features as ``place feature`` commands. ``emit_cave``
runs the layers through the terrain emitter's liquid and gravity checks
(``check_form_layers``) and writes phase files that roll back from column
backups. ``check_cave`` verifies a fresh read of the finished cave.

The ground surface is never repainted: only cells inside the void, the rock
face around it, pools and light cells change. Shafts are the only designed
openings to the surface.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import distance_transform_edt, label

# The emitter's block classification (_flags and its bits) is shared, not copied.
from .ashlar_emit import _COVER, _FLUID, _OPEN, EmitResult, _flags, check_form_layers, plan_rows_toon
from .emit import VerifyError
from .forms import GRAVITY
from .live import LiveWrite, greedy_fills
from .plant import Feature, features_file
from .site import _AIR, NATURAL, Site, base_id, integer_level, load_site, surfaces

STYLES = ("plain", "dripstone", "lush", "deep")
ROLES = ("wall", "floor", "ceiling", "deep")
FEATURE_ROLES = ("wall", "floor", "ceiling")
DEEP_Y = 0  # vanilla deepslate starts at y 0
FEATURE_REACH = (8, 16, 16)  # backup reach of cave features: sideways, up, down

_ELEMENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_STYLE_PALETTES: dict[str, dict[str, dict[str, int]]] = {
    "plain": {
        "wall": {"stone": 6, "andesite": 2, "tuff": 1, "cobblestone": 1},
        "floor": {"stone": 4, "andesite": 2, "coarse_dirt": 1, "gravel": 1},
        "ceiling": {"stone": 6, "andesite": 2, "tuff": 1},
        "deep": {"deepslate": 6, "cobbled_deepslate": 2, "tuff": 2},
    },
    "dripstone": {
        "wall": {"dripstone_block": 5, "stone": 3, "tuff": 2},
        "floor": {"dripstone_block": 4, "tuff": 2, "stone": 2},
        "ceiling": {"dripstone_block": 6, "stone": 2},
        "deep": {"dripstone_block": 4, "deepslate": 4, "tuff": 2},
    },
    "lush": {
        "wall": {"stone": 5, "moss_block": 3, "andesite": 1, "clay": 1},
        "floor": {"moss_block": 6, "clay": 1, "rooted_dirt": 1},
        "ceiling": {"moss_block": 4, "stone": 4},
        "deep": {"deepslate": 5, "moss_block": 3, "tuff": 2},
    },
    "deep": {
        "wall": {"deepslate": 5, "tuff": 3, "smooth_basalt": 1, "calcite": 1},
        "floor": {"cobbled_deepslate": 4, "deepslate": 3, "tuff": 2},
        "ceiling": {"deepslate": 6, "tuff": 3, "calcite": 1},
        "deep": {"deepslate": 5, "cobbled_deepslate": 2, "tuff": 3},
    },
}
_STYLE_LIGHTS = {
    "plain": "minecraft:shroomlight",
    "dripstone": "minecraft:ochre_froglight",
    "lush": "minecraft:shroomlight",
    "deep": "minecraft:sea_lantern",
}
_STYLE_FEATURES: dict[str, list[tuple[str, str, float]]] = {
    "plain": [("glow_lichen", "wall", 1.0)],
    "dripstone": [
        ("pointed_dripstone", "ceiling", 3.0),
        ("dripstone_cluster", "floor", 0.8),
        ("large_dripstone", "floor", 0.3),
        ("glow_lichen", "wall", 0.8),
    ],
    "lush": [
        ("moss_patch_ceiling", "ceiling", 1.5),
        ("cave_vine", "ceiling", 2.5),
        ("spore_blossom", "ceiling", 0.4),
        ("moss_patch", "floor", 1.5),
        ("clay_pool_with_dripleaves", "floor", 0.5),
        ("glow_lichen", "wall", 0.6),
    ],
    "deep": [("glow_lichen", "wall", 2.0), ("pointed_dripstone", "ceiling", 0.8)],
}
# Features that must never be placed by this skill, with the reason.
_BANNED_FEATURES = {
    "minecraft:sculk_patch_deep_dark": "a sculk shrieker can summon a warden",
    "minecraft:sculk_patch_ancient_city": "a sculk shrieker can summon a warden",
    "minecraft:sculk_vein": "sculk spreads toward a warden-summoning shrieker",
    "minecraft:rooted_azalea_tree": "it grows an azalea tree on the surface above the cave",
}
# Features that grow only on some blocks (`can_be_placed_on` in the 26.3 worldgen
# data), on a wall or ceiling face, never a floor. Their spots must touch one after
# dressing, and they run before moss patches and vines can cover that rock.
_GROWS_ON = {
    "minecraft:glow_lichen": frozenset(f"minecraft:{n}" for n in (
        "stone", "andesite", "diorite", "granite", "dripstone_block", "calcite", "tuff",
        "deepslate", "sulfur", "cinnabar")),
}
# Natural rock and soil the dress pass may repaint. Ores, amethyst, obsidian,
# bedrock, sand and anything a player built stay as they are.
DRESSABLE = frozenset(
    "minecraft:" + name
    for name in (
        "stone", "granite", "diorite", "andesite", "tuff", "calcite", "deepslate",
        "dirt", "coarse_dirt", "rooted_dirt", "gravel", "clay", "dripstone_block",
        "smooth_basalt", "moss_block", "cobblestone", "mossy_cobblestone",
    )
)
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


# ------------------------------------------------------------------ the design
@dataclass(frozen=True)
class Chamber:
    center: tuple[int, int, int]
    radii: tuple[float, float, float]
    floor: int | None = None
    roughness: float = 0.25
    relief: float | None = None  # ceiling bumps in blocks; None = a third of the height radius

    @property
    def ceiling_relief(self) -> float:
        return max(1.5, self.radii[1] / 3) if self.relief is None else self.relief


@dataclass(frozen=True)
class Passage:
    points: tuple[tuple[int, int, int], ...]
    radius: tuple[float, float]
    roughness: float = 0.2


@dataclass(frozen=True)
class Ravine:
    points: tuple[tuple[int, int], ...]
    top: int
    bottom: int
    width: float
    roughness: float = 0.25


@dataclass(frozen=True)
class Shaft:
    at: tuple[int, int]
    start: int
    radius: float


@dataclass(frozen=True)
class Pillar:
    at: tuple[int, int]
    radius: float


@dataclass(frozen=True)
class Pool:
    at: tuple[int, int, int]
    level: int


@dataclass(frozen=True)
class ExistingCave:
    at: tuple[int, int, int]
    box: tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class Move:
    start: tuple[int, int, int]
    end: tuple[int, int, int]


@dataclass(frozen=True)
class FeatureSpec:
    id: str
    on: str
    per_100: float


@dataclass(frozen=True)
class LightSpec:
    enabled: bool = True
    block: str = "minecraft:shroomlight"
    minimum: int = 1
    max_count: int = 400
    hang: str | None = "minecraft:lantern[hanging=true]"

    @property
    def level(self) -> int:
        return _light_of(self.block)


@dataclass
class CaveDesign:
    element: str
    seed: int
    site: Path
    chambers: list[Chamber] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    ravines: list[Ravine] = field(default_factory=list)
    shafts: list[Shaft] = field(default_factory=list)
    pillars: list[Pillar] = field(default_factory=list)
    pools: list[Pool] = field(default_factory=list)
    existing: list[ExistingCave] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)
    roof: int = 4
    style: str = "plain"
    palette: dict[str, dict[str, int]] = field(default_factory=dict)
    dress: str = "new"
    lights: LightSpec = field(default_factory=LightSpec)
    features: list[FeatureSpec] = field(default_factory=list)
    limits: dict[str, float] = field(default_factory=dict)
    version: str = "26.3"
    source: dict = field(default_factory=dict)


def _ints(value: Any, n: int, where: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != n:
        raise ValueError(f"{where} must be {n} integers")
    return tuple(integer_level(v, where) for v in value)


def _number(value: Any, where: str, *, low: float = 0.0, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} must be a number")
    if value < low or (high is not None and value > high):
        bound = f"between {low} and {high}" if high is not None else f"at least {low}"
        raise ValueError(f"{where} must be {bound}")
    return float(value)


def _state(name: str, where: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"(minecraft:)?[a-z0-9_]+(\[[a-z0-9_=,]*\])?", name):
        raise ValueError(f"{where} must be a block id such as minecraft:stone")
    return name if name.startswith("minecraft:") else f"minecraft:{name}"


def _weights(value: Any, where: str) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{where} must map block ids to positive weights")
    out = {}
    for name, weight in value.items():
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            raise ValueError(f"{where} weight for {name!r} must be a positive integer")
        out[_state(name, where)] = weight
    return out


def _light_of(state: str) -> int:
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


def parse_design(data: dict, project_dir: Path) -> CaveDesign:
    """Validate a cave design dict and resolve it against a project folder.

    Args:
        data: The parsed design file.
        project_dir: The project folder; ``site`` is relative to it.

    Returns:
        The validated design.

    Raises:
        ValueError: Naming the first invalid field.
    """
    if not isinstance(data, dict):
        raise ValueError("a cave design must be a JSON object")
    element = data.get("element")
    if not isinstance(element, str) or not _ELEMENT.fullmatch(element):
        raise ValueError("element must be kebab-case, such as west-grotto")
    seed = integer_level(data.get("seed", 0), "seed")
    site = data.get("site")
    if not isinstance(site, str) or not site or Path(site).is_absolute():
        raise ValueError("site must be the project-relative path of the exact site read")
    project = Path(project_dir)
    if not (project / site).resolve().is_relative_to(project.resolve()):
        raise ValueError("site must stay inside the project folder")

    chambers = []
    for i, c in enumerate(data.get("chambers", [])):
        where = f"chambers[{i}]"
        if not isinstance(c, dict) or "radii" not in c:
            raise ValueError(f"{where} needs center and radii")
        radii = tuple(_number(r, f"{where}.radii", low=1.0) for r in _list(c["radii"], 3, f"{where}.radii"))
        floor = c.get("floor")
        relief = c.get("relief")
        chambers.append(Chamber(_ints(c.get("center"), 3, f"{where}.center"), radii,
                                None if floor is None else integer_level(floor, f"{where}.floor"),
                                _number(c.get("roughness", 0.25), f"{where}.roughness", high=0.6),
                                None if relief is None else _number(relief, f"{where}.relief", high=radii[1])))
    passages = []
    for i, p in enumerate(data.get("passages", [])):
        where = f"passages[{i}]"
        if not isinstance(p, dict):
            raise ValueError(f"{where} must be an object")
        points = _list(p.get("points"), None, f"{where}.points")
        if len(points) < 2:
            raise ValueError(f"{where}.points needs at least two points")
        radius = tuple(_number(r, f"{where}.radius", low=1.0) for r in _list(p.get("radius"), 2, f"{where}.radius"))
        passages.append(Passage(tuple(_ints(pt, 3, f"{where}.points") for pt in points), radius,
                                _number(p.get("roughness", 0.2), f"{where}.roughness", high=0.6)))
    ravines = []
    for i, r in enumerate(data.get("ravines", [])):
        where = f"ravines[{i}]"
        if not isinstance(r, dict):
            raise ValueError(f"{where} must be an object")
        points = _list(r.get("points"), None, f"{where}.points")
        if len(points) < 2:
            raise ValueError(f"{where}.points needs at least two points")
        top, bottom = integer_level(r.get("top"), f"{where}.top"), integer_level(r.get("bottom"), f"{where}.bottom")
        if top <= bottom:
            raise ValueError(f"{where}.top must be above its bottom")
        ravines.append(Ravine(tuple(_ints(pt, 2, f"{where}.points") for pt in points), top, bottom,
                              _number(r.get("width"), f"{where}.width", low=1.0),
                              _number(r.get("roughness", 0.25), f"{where}.roughness", high=0.6)))
    existing = []
    for i, e in enumerate(_objects(data.get("existing", []), "existing")):
        at = _ints(e.get("at"), 3, f"existing[{i}].at")
        raw = _ints(e.get("box"), 6, f"existing[{i}].box")
        box = (min(raw[0], raw[3]), min(raw[1], raw[4]), min(raw[2], raw[5]),
               max(raw[0], raw[3]), max(raw[1], raw[4]), max(raw[2], raw[5]))
        if not all(box[k] <= at[k] <= box[k + 3] for k in range(3)):
            raise ValueError(f"existing[{i}].at must lie inside its box")
        existing.append(ExistingCave(at, box))
    if not (chambers or passages or ravines or existing):
        raise ValueError("a design needs at least one chamber, passage, ravine or existing cave")
    moves = [Move(_ints(m.get("from"), 3, f"moves[{i}].from"), _ints(m.get("to"), 3, f"moves[{i}].to"))
             for i, m in enumerate(_objects(data.get("moves", []), "moves"))]
    if any(m.start == m.end for m in moves):
        raise ValueError("a move must change the block's position")
    shafts = [Shaft(_ints(s.get("at"), 2, f"shafts[{i}].at"), integer_level(s.get("from"), f"shafts[{i}].from"),
                    _number(s.get("radius", 1.5), f"shafts[{i}].radius", low=1.0))
              for i, s in enumerate(_objects(data.get("shafts", []), "shafts"))]
    pillars = [Pillar(_ints(p.get("at"), 2, f"pillars[{i}].at"), _number(p.get("radius"), f"pillars[{i}].radius", low=1.0))
               for i, p in enumerate(_objects(data.get("pillars", []), "pillars"))]
    pools = [Pool(_ints(p.get("at"), 3, f"pools[{i}].at"), integer_level(p.get("level"), f"pools[{i}].level"))
             for i, p in enumerate(_objects(data.get("pools", []), "pools"))]

    roof = data.get("roof", 4)
    if isinstance(roof, bool) or not isinstance(roof, int) or roof < 0:
        raise ValueError("roof must be a non-negative whole number of blocks")
    style = data.get("style", "plain")
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}")
    palette = {role: dict(_STYLE_PALETTES[style][role]) for role in ROLES}
    palette = {role: {f"minecraft:{k}": v for k, v in weights.items()} for role, weights in palette.items()}
    overrides = data.get("palette", {})
    if not isinstance(overrides, dict) or set(overrides) - set(ROLES):
        raise ValueError(f"palette may only set {', '.join(ROLES)}")
    for role, weights in overrides.items():
        palette[role] = _weights(weights, f"palette.{role}")

    raw_lights = data.get("lights", {})
    if raw_lights is False:
        lights = LightSpec(enabled=False)
    elif isinstance(raw_lights, dict):
        block = _state(raw_lights.get("block", _STYLE_LIGHTS[style]), "lights.block")
        minimum = raw_lights.get("min", 1)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or not 0 <= minimum <= 14:
            raise ValueError("lights.min must be a whole number from 0 to 14")
        max_count = integer_level(raw_lights.get("max_count", 400), "lights.max_count")
        raw_hang = raw_lights.get("hang", "minecraft:lantern[hanging=true]")
        hang = None if raw_hang is False else _state(raw_hang, "lights.hang")
        lights = LightSpec(True, block, minimum, max_count, hang)
        if lights.level <= minimum:
            raise ValueError(f"lights.block {block} is not bright enough for lights.min {minimum}")
    else:
        raise ValueError("lights must be an object or false")

    version = data.get("version", "26.3")
    if not isinstance(version, str):
        raise ValueError("version must be a string such as 26.3")
    raw_features = data.get("features")
    if raw_features is None:
        specs = [FeatureSpec(f"minecraft:{fid}", on, per) for fid, on, per in _STYLE_FEATURES[style]]
    else:
        specs = []
        for i, f in enumerate(_objects(raw_features, "features")):
            fid = f.get("id")
            if not isinstance(fid, str) or not fid:
                raise ValueError(f"features[{i}].id must be a feature id")
            fid = fid if fid.startswith("minecraft:") else f"minecraft:{fid}"
            on = f.get("on")
            if on not in FEATURE_ROLES:
                raise ValueError(f"features[{i}].on must be one of {', '.join(FEATURE_ROLES)}")
            specs.append(FeatureSpec(fid, on, _number(f.get("per_100", 1.0), f"features[{i}].per_100", high=50.0)))
    _check_features(specs, version)

    limits = {"max_span": 24, "ceiling_std": 0.75, "flat_run": 14}
    raw_limits = data.get("limits", {})
    if not isinstance(raw_limits, dict) or set(raw_limits) - set(limits):
        raise ValueError(f"limits may only set {', '.join(limits)}")
    for key, value in raw_limits.items():
        limits[key] = _number(value, f"limits.{key}", low=0.0)
    dress = {True: "new", False: "none"}.get(data.get("dress", "new"), data.get("dress", "new"))
    if dress not in ("new", "all", "none"):
        raise ValueError('dress must be "new" (rock around carved cells), "all" or "none"')
    return CaveDesign(element, seed, project / site, chambers, passages, ravines, shafts, pillars, pools,
                      existing, moves, roof, style, palette, dress, lights, specs, limits, version, dict(data))


def _list(value: Any, n: int | None, where: str) -> list:
    if not isinstance(value, (list, tuple)) or (n is not None and len(value) != n):
        raise ValueError(f"{where} must be a list" + (f" of {n} numbers" if n else ""))
    return list(value)


def _objects(value: Any, where: str) -> list[dict]:
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValueError(f"{where} must be a list of objects")
    return value


def _check_features(specs: list[FeatureSpec], version: str) -> None:
    from .ids import load_ids

    known, _, used = load_ids(version)
    for spec in specs:
        if spec.id in _BANNED_FEATURES:
            raise ValueError(f"feature {spec.id} is not allowed: {_BANNED_FEATURES[spec.id]}")
        if spec.id not in known:
            raise ValueError(f"unknown feature id {spec.id} in the {used} feature list")


def load_design(path: Path, project_dir: Path | None = None) -> CaveDesign:
    """Read and validate a design file.

    Args:
        path: The ``<element>.cave.json`` file.
        project_dir: The project folder; defaults to the folder above ``terrain/``.

    Returns:
        The validated design.
    """
    path = Path(path)
    if project_dir is None:
        project_dir = path.parent.parent if path.parent.name == "terrain" else path.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the cave design {path}: {exc}") from None
    return parse_design(data, Path(project_dir))


# ------------------------------------------------------------------ noise
def _hash(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    """A deterministic value in [0, 1) per integer lattice point."""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791)
    h = h ^ np.int64(seed * 2654435761 % (1 << 31))
    h = (h ^ (h >> 13)) * np.int64(1274126177)
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0x1000000)


def _noise3(x: np.ndarray, y: np.ndarray, z: np.ndarray, seed: int, freq: float = 0.18) -> np.ndarray:
    """Two octaves of smooth value noise in [-1, 1] at world coordinates."""
    total = np.zeros(np.broadcast(x, y, z).shape)
    amp_sum = 0.0
    for octave, amp in ((1.0, 1.0), (2.0, 0.5)):
        f = freq * octave
        px, py, pz = x * f, y * f, z * f
        x0, y0, z0 = np.floor(px), np.floor(py), np.floor(pz)
        tx, ty, tz = px - x0, py - y0, pz - z0
        sx, sy, sz = (t * t * (3 - 2 * t) for t in (tx, ty, tz))
        acc = 0.0
        for dx in (0, 1):
            wx = sx if dx else 1 - sx
            for dy in (0, 1):
                wy = sy if dy else 1 - sy
                for dz in (0, 1):
                    wz = sz if dz else 1 - sz
                    acc = acc + wx * wy * wz * _hash(x0 + dx, y0 + dy, z0 + dz, seed + int(octave))
        total = total + amp * (acc * 2 - 1)
        amp_sum += amp
    return total / amp_sum


# ------------------------------------------------------------------ geometry
def _grid(box: tuple[int, ...], lo: tuple[int, int, int], hi: tuple[int, int, int]):
    """World coordinate arrays for the part of [lo, hi] inside ``box``, and its slice."""
    x1, y1, z1, x2, y2, z2 = box
    a = (max(lo[0], x1), max(lo[1], y1), max(lo[2], z1))
    b = (min(hi[0], x2), min(hi[1], y2), min(hi[2], z2))
    if any(p > q for p, q in zip(a, b, strict=True)):
        return None, None
    xs = np.arange(a[0], b[0] + 1)[:, None, None]
    ys = np.arange(a[1], b[1] + 1)[None, :, None]
    zs = np.arange(a[2], b[2] + 1)[None, None, :]
    sl = (slice(a[0] - x1, b[0] - x1 + 1), slice(a[1] - y1, b[1] - y1 + 1), slice(a[2] - z1, b[2] - z1 + 1))
    return (xs, ys, zs), sl


def _shape(box: tuple[int, ...], lo, hi, inside) -> tuple[np.ndarray | None, tuple | None]:
    coords, sl = _grid(box, lo, hi)
    if coords is None:
        return None, None
    return inside(*coords), sl


def chamber_mask(c: Chamber, box: tuple[int, ...], seed: int) -> np.ndarray:
    """Cells of a noisy ellipsoid chamber, over the whole ``box``."""
    out = np.zeros(_dims(box), bool)
    reach = [int(np.ceil(r * (1 + c.roughness))) + 1 for r in c.radii]
    reach[1] += int(np.ceil(c.ceiling_relief))
    lo = tuple(p - r for p, r in zip(c.center, reach, strict=True))
    hi = tuple(p + r for p, r in zip(c.center, reach, strict=True))

    def inside(x, y, z):
        # Lift or lower the upper half by a column noise so the ceiling never runs flat.
        bumps = np.clip(2.2 * _noise3(x, 0 * y, z, seed + 5, freq=0.25), -1.0, 1.0)  # use the full range
        lift = np.where(y > c.center[1], c.ceiling_relief * bumps, 0.0)
        d = np.sqrt(((x - c.center[0]) / c.radii[0]) ** 2 + ((y - c.center[1] - lift) / c.radii[1]) ** 2
                    + ((z - c.center[2]) / c.radii[2]) ** 2)
        cells = d + c.roughness * _noise3(x, y, z, seed) < 1.0
        if c.floor is not None:
            cells &= np.broadcast_to(y >= c.floor, cells.shape)
        return cells

    cells, sl = _shape(box, lo, hi, inside)
    if cells is not None:
        out[sl] |= cells
    return out


def passage_mask(p: Passage, box: tuple[int, ...], seed: int) -> np.ndarray:
    """Cells of a tube swept along a 3-D polyline, radius eased start to end."""
    out = np.zeros(_dims(box), bool)
    pts = np.array(p.points, float)
    seg = np.diff(pts, axis=0)
    lengths = np.linalg.norm(seg, axis=1)
    total = float(lengths.sum()) or 1.0
    start = np.concatenate([[0.0], np.cumsum(lengths)[:-1]])
    big = max(p.radius) * (1 + p.roughness) + 1
    for a, d, length, s0 in zip(pts[:-1], seg, lengths, start, strict=True):
        b = a + d
        lo = tuple(int(np.floor(min(a[i], b[i]) - big)) for i in range(3))
        hi = tuple(int(np.ceil(max(a[i], b[i]) + big)) for i in range(3))

        def inside(x, y, z, a=a, d=d, length=length, s0=s0):
            rel = (x - a[0], y - a[1], z - a[2])
            t = np.clip((rel[0] * d[0] + rel[1] * d[1] + rel[2] * d[2]) / max(length * length, 1e-9), 0, 1)
            dist = np.sqrt((rel[0] - t * d[0]) ** 2 + (rel[1] - t * d[1]) ** 2 + (rel[2] - t * d[2]) ** 2)
            frac = (s0 + t * length) / total
            radius = p.radius[0] + (p.radius[1] - p.radius[0]) * frac
            return dist < radius * (1 + p.roughness * _noise3(x, y, z, seed + 11))

        cells, sl = _shape(box, lo, hi, inside)
        if cells is not None:
            out[sl] |= cells
    return out


def ravine_mask(r: Ravine, box: tuple[int, ...], seed: int) -> np.ndarray:
    """Cells of a tall slot along a 2-D path, narrowing toward its bottom."""
    out = np.zeros(_dims(box), bool)
    pts = np.array(r.points, float)
    half = r.width / 2 * (1 + r.roughness) + 1
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        d = b - a
        length2 = max(float(d @ d), 1e-9)
        lo = (int(np.floor(min(a[0], b[0]) - half)), r.bottom, int(np.floor(min(a[1], b[1]) - half)))
        hi = (int(np.ceil(max(a[0], b[0]) + half)), r.top, int(np.ceil(max(a[1], b[1]) + half)))

        def inside(x, y, z, a=a, d=d, length2=length2):
            t = np.clip(((x - a[0]) * d[0] + (z - a[1]) * d[1]) / length2, 0, 1)
            dist = np.sqrt((x - a[0] - t * d[0]) ** 2 + (z - a[1] - t * d[1]) ** 2)
            frac = (y - r.bottom) / max(r.top - r.bottom, 1)
            width = r.width / 2 * (0.35 + 0.65 * frac)
            return dist < width * (1 + r.roughness * _noise3(x, y, z, seed + 23))

        cells, sl = _shape(box, lo, hi, inside)
        if cells is not None:
            out[sl] |= cells
    return out


def _column_disc(at: tuple[int, int], radius: float, box: tuple[int, ...]) -> np.ndarray:
    x1, _, z1, x2, _, z2 = box
    xs = np.arange(x1, x2 + 1)[:, None]
    zs = np.arange(z1, z2 + 1)[None, :]
    return (xs - at[0]) ** 2 + (zs - at[1]) ** 2 < radius * radius


def _dims(box: tuple[int, ...]) -> tuple[int, int, int]:
    x1, y1, z1, x2, y2, z2 = box
    return x2 - x1 + 1, y2 - y1 + 1, z2 - z1 + 1


def envelope(design: CaveDesign, box: tuple[int, ...]) -> np.ndarray:
    """The design's shapes over ``box`` before any site rule (roof, built blocks)."""
    shape = np.zeros(_dims(box), bool)
    for i, c in enumerate(design.chambers):
        shape |= chamber_mask(c, box, design.seed + 101 * i)
    for i, p in enumerate(design.passages):
        shape |= passage_mask(p, box, design.seed + 211 * i)
    for i, r in enumerate(design.ravines):
        shape |= ravine_mask(r, box, design.seed + 307 * i)
    for p in design.pillars:
        shape &= ~_column_disc(p.at, p.radius, box)[:, None, :]
    return shape


# ------------------------------------------------------------------ site grids
def _site_flags(site: Site) -> np.ndarray:
    x1, y1, z1, x2, y2, z2 = site.box
    grid = np.empty(_dims(site.box), np.uint16)
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            grid[x - x1, lo - y1:hi - y1 + 1, z - z1] = _flags(state)
    return grid


def _site_ids(site: Site) -> tuple[np.ndarray, list[str]]:
    """Per-cell block id codes and the id list, for repeated id lookups."""
    names: list[str] = []
    index: dict[str, int] = {}
    x1, y1, z1, _, _, _ = site.box
    grid = np.empty(_dims(site.box), np.uint16)
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            block = base_id(state)
            if block not in index:
                index[block] = len(names)
                names.append(block)
            grid[x - x1, lo - y1:hi - y1 + 1, z - z1] = index[block]
    return grid, names


def _transparent(flags: np.ndarray) -> np.ndarray:
    """Cells that are not a full cube in the emitter's natural-block table."""
    return flags & _COVER == 0


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
def _full_cube(state: str) -> bool:
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
def _lets_light(state: str) -> bool:
    block = base_id(state)
    return (not _full_cube(state) or block in _LIGHT_THROUGH or block.endswith("_leaves")
            or (block.endswith("_glass") and block != "minecraft:tinted_glass"))


def _classes(site: Site) -> tuple[np.ndarray, np.ndarray]:
    """Per cell: a full cube, and letting light through."""
    full = np.zeros(_dims(site.box), bool)
    light = np.zeros(_dims(site.box), bool)
    x1, y1, z1 = site.box[:3]
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            sl = (x - x1, slice(lo - y1, hi - y1 + 1), z - z1)
            full[sl] = _full_cube(state)
            light[sl] = _lets_light(state)
    return full, light


def _face_dilate(mask: np.ndarray) -> np.ndarray:
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[:, :, 1:] |= mask[:, :, :-1]
    out[:, :, :-1] |= mask[:, :, 1:]
    return out


def _below(mask: np.ndarray) -> np.ndarray:
    """True where the cell directly below is True."""
    out = np.zeros_like(mask)
    out[:, 1:] = mask[:, :-1]
    return out


def _above(mask: np.ndarray) -> np.ndarray:
    """True where the cell directly above is True."""
    out = np.zeros_like(mask)
    out[:, :-1] = mask[:, 1:]
    return out


def _beside(mask: np.ndarray) -> np.ndarray:
    """True where a horizontal neighbour is True."""
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, :, 1:] |= mask[:, :, :-1]
    out[:, :, :-1] |= mask[:, :, 1:]
    return out


def standable(open_cells: np.ndarray, solid: np.ndarray | None = None) -> np.ndarray:
    """Open cells with open headroom above and a solid block below."""
    solid = ~open_cells if solid is None else solid
    return open_cells & _above(open_cells) & _below(solid)


# ------------------------------------------------------------------ carving
def existing_region(design: CaveDesign, site: Site) -> np.ndarray:
    """Open cells of each adopted existing cave, as the site read shows them.

    From each entry's ``at``, the cells connected to it through open space
    (anything that is not a full block or a liquid) inside the entry's box and
    below the ground surface of their column. Cells under open sky are not
    part of a cave.

    Raises:
        ValueError: A box leaves the site read, or ``at`` is not such a cell.
    """
    region = np.zeros(_dims(site.box), bool)
    if not design.existing:
        return region
    flags = _site_flags(site)
    full, _ = _classes(site)
    candidate = ~full & (flags & _FLUID == 0)
    ground = surfaces(site).ground
    ys = np.arange(site.box[1], site.box[4] + 1)[None, :, None]
    with np.errstate(invalid="ignore"):
        candidate &= ys < ground[:, None, :]
    x1, y1, z1, x2, y2, z2 = site.box
    for i, cave in enumerate(design.existing):
        bx1, by1, bz1, bx2, by2, bz2 = cave.box
        if not (x1 < bx1 and y1 < by1 and z1 < bz1 and bx2 < x2 and by2 < y2 and bz2 < z2):
            raise ValueError(f"read wider: existing[{i}].box must lie inside the site read with a one-block margin")
        inside = np.zeros_like(candidate)
        inside[bx1 - x1:bx2 - x1 + 1, by1 - y1:by2 - y1 + 1, bz1 - z1:bz2 - z1 + 1] = True
        labels, _ = label(candidate & inside)
        at = tuple(v - o for v, o in zip(cave.at, site.box[:3], strict=True))
        if not labels[at]:
            raise ValueError(f"existing[{i}].at {cave.at} must be an open cell of the cave, below the surface")
        region |= labels == labels[at]
    return region


@dataclass
class CaveSpace:
    """Where the cave is: carved cells, adopted existing cells and their union."""

    void: np.ndarray
    carved: np.ndarray
    region: np.ndarray
    shafts: np.ndarray
    report: dict


def cave_space(design: CaveDesign, site: Site) -> CaveSpace:
    """Carved shapes (roof rule applied outside shafts) plus adopted existing caves.

    Raises:
        ValueError: The design holds no space, or the site read is too small.
    """
    box = site.box
    for (x, z), runs in site.columns.items():
        if base_id(runs[-1][2]) not in _AIR:
            raise ValueError(f"read higher: column {x},{z} does not reach the air above the surface")
    shape = envelope(design, box)
    ground = surfaces(site).ground
    shafts = np.zeros(ground.shape, bool)
    ys = np.arange(box[1], box[4] + 1)[None, :, None]
    for s in design.shafts:
        disc = _column_disc(s.at, s.radius, box)
        shafts |= disc
        column_top = np.where(np.isfinite(ground), ground, box[4])[:, None, :]
        shape |= disc[:, None, :] & (ys >= s.start) & (ys <= column_top)
    allowed = ys < np.where(np.isfinite(ground), ground, np.inf)[:, None, :] - design.roof
    allowed |= shafts[:, None, :]
    trimmed = int(np.count_nonzero(shape & ~allowed))
    carved = shape & allowed
    region = existing_region(design, site)
    void = carved | region
    if not void.any():
        raise ValueError("the design holds no cave inside the site read; check its coordinates and the roof")
    if carved[0].any() or carved[-1].any() or carved[:, :, 0].any() or carved[:, :, -1].any():
        raise ValueError("read wider: the cave reaches the side of the site read")
    if carved[:, 0].any():
        raise ValueError("read lower: the cave reaches the bottom of the site read")
    flags = _site_flags(site)
    ids, names = _site_ids(site)
    air = np.array([n in _AIR for n in names])[ids]
    existing_open = _transparent(flags) & (flags & _FLUID == 0) & ~void
    # Shafts open to the surface by design; count only other connections.
    meets = int(np.count_nonzero(carved & ~shafts[:, None, :] & _face_dilate(existing_open)))
    idx = np.argwhere(void)
    lo, hi = idx.min(axis=0), idx.max(axis=0)
    report = {
        "cells": int(void.sum()),
        "carve_cells": int(np.count_nonzero(carved & ~air)),
        "existing_cells": int(region.sum()),
        "roof_trimmed": trimmed,
        "bbox": [int(lo[i]) + box[i] for i in range(3)] + [int(hi[i]) + box[i] for i in range(3)],
        "meets_existing_open": meets,
    }
    return CaveSpace(void, carved, region, shafts, report)


def void_mask(design: CaveDesign, site: Site) -> tuple[np.ndarray, dict]:
    """The cave's cells over the site box (carved and adopted) and a report."""
    space = cave_space(design, site)
    return space.void, space.report


def _write(mask: np.ndarray, site: Site, states: np.ndarray | None, palette: list[str]) -> LiveWrite:
    """A LiveWrite over the bounding box of ``mask``; ``states`` holds palette codes."""
    idx = np.argwhere(mask)
    lo, hi = idx.min(axis=0), idx.max(axis=0) + 1
    sl = tuple(slice(a, b) for a, b in zip(lo, hi, strict=True))
    codes = np.zeros(tuple(hi - lo), np.uint16)
    sub = mask[sl]
    codes[sub] = 1 if states is None else states[sl][sub]
    origin = tuple(int(v) + o for v, o in zip(lo, site.box[:3], strict=True))
    return LiveWrite(origin, codes, palette)


def carve_write(carved: np.ndarray, site: Site) -> LiveWrite | None:
    """Air for every carved cell that is not already air; None when nothing is carved."""
    ids, names = _site_ids(site)
    air = np.array([n in _AIR for n in names])[ids]
    cells = carved & ~air
    return _write(cells, site, None, ["skip", "minecraft:air"]) if cells.any() else None


# ------------------------------------------------------------------ moves
_TWO_BLOCK_HALF = {"half=lower": 1, "half=upper": -1}
_FACING = {"north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
# Blocks whose contents or text live in a block entity that a block write cannot carry.
_DATA_SUFFIXES = ("chest", "barrel", "shulker_box", "furnace", "smoker", "hopper", "dropper",
                  "dispenser", "brewing_stand", "lectern", "_sign", "_banner", "jukebox",
                  "decorated_pot", "chiseled_bookshelf", "crafter", "campfire", "spawner",
                  "vault", "beehive", "bee_nest", "_head", "_skull", "command_block")


def holds_data(state: str) -> bool:
    """True for a block whose contents, text or owner a block write would lose."""
    return base_id(state).endswith(_DATA_SUFFIXES)


def _partner(state: str, cell: tuple[int, int, int]) -> tuple[int, int, int] | None:
    """The other half of a two-block door, tall plant or bed, or None."""
    for key, dy in _TWO_BLOCK_HALF.items():
        if key in state:
            return (cell[0], cell[1] + dy, cell[2])
    match = re.search(r"facing=(north|south|east|west)", state)
    if base_id(state).endswith("_bed") and match:
        dx, _, dz = _FACING[match.group(1)]
        sign = 1 if "part=foot" in state else -1
        return (cell[0] + sign * dx, cell[1], cell[2] + sign * dz)
    return None


def move_write(design: CaveDesign, site: Site, carved: np.ndarray) -> LiveWrite | None:
    """Each moved block written at its new place, and air where it stood.

    A source inside a carved shape is rescued from the carve: its state is
    read from the site before carving.

    Raises:
        ValueError: A move leaves the site read, repeats a target, or moves one
            half of a two-block door, plant or bed without the other.
    """
    if not design.moves:
        return None
    targets: dict[tuple[int, int, int], str] = {}
    sources: set[tuple[int, int, int]] = set()
    pairs = {m.start: m.end for m in design.moves}
    for i, m in enumerate(design.moves):
        for cell, name in ((m.start, "from"), (m.end, "to")):
            if not all(lo <= c <= hi for lo, c, hi in zip(site.box[:3], cell, site.box[3:], strict=True)):
                raise ValueError(f"moves[{i}].{name} {cell} is outside the site read")
        if m.end in targets:
            raise ValueError(f"moves[{i}].to {m.end} is already the target of another move")
        state = site.block(*m.start)
        partner = _partner(state, m.start)
        if partner is not None:
            delta = tuple(b - a for a, b in zip(m.start, m.end, strict=True))
            want = tuple(p + d for p, d in zip(partner, delta, strict=True))
            if pairs.get(partner) != want:
                raise ValueError(f"moves[{i}] moves half of the {base_id(state)} at {m.start}; "
                                 f"move its other half at {partner} by the same offset")
        targets[m.end] = state
        sources.add(m.start)
    cells = np.zeros(_dims(site.box), bool)
    codes = np.zeros(cells.shape, np.uint16)
    palette = ["skip", "minecraft:air"]
    x1, y1, z1 = site.box[:3]
    for cell in sources - set(targets):
        i = (cell[0] - x1, cell[1] - y1, cell[2] - z1)
        if not carved[i]:
            cells[i], codes[i] = True, 1
    for cell, state in targets.items():
        i = (cell[0] - x1, cell[1] - y1, cell[2] - z1)
        if state not in palette:
            palette.append(state)
        cells[i], codes[i] = True, palette.index(state)
    return _write(cells, site, codes, palette) if cells.any() else None


# ------------------------------------------------------------------ dressing
def _pick(weights: dict[str, int], u: np.ndarray) -> np.ndarray:
    """Weighted choice per cell from uniform values ``u``; returns indexes into weights."""
    cum = np.cumsum(list(weights.values()), dtype=float)
    return np.searchsorted(cum / cum[-1], u, side="right").clip(0, len(weights) - 1)


def dress_write(design: CaveDesign, site: Site, void: np.ndarray,
                carved: np.ndarray | None = None) -> LiveWrite | None:
    """Repaint the natural rock face around the cave, by role and depth.

    ``dress`` ``"new"`` (the default) repaints only rock touching carved cells,
    so an adopted cave keeps its look; ``"all"`` repaints the whole cave's face.
    Ceilings sit over the cave, floors under it, walls beside it; below
    ``DEEP_Y`` the ``deep`` palette replaces all three. A gravity block is used
    only where the cell below stays solid.
    """
    if design.dress == "none":
        return None
    if carved is None:
        carved = cave_space(design, site).carved
    target = carved if design.dress == "new" else void
    full, _ = _classes(site)
    solid = full & ~void
    ids, names = _site_ids(site)
    dressable = np.array([n in DRESSABLE for n in names])[ids]
    shell = _face_dilate(target) & solid & dressable
    if not shell.any():
        return None
    ceiling = shell & _below(void)
    floor = shell & _above(void) & ~ceiling  # the rest of the shell is wall
    x1, y1, z1 = site.box[:3]
    idx = np.argwhere(shell)
    wx, wy, wz = idx[:, 0] + x1, idx[:, 1] + y1, idx[:, 2] + z1
    u = _hash(wx, wy, wz, design.seed + 7)
    palette = ["skip"]
    index: dict[str, int] = {}
    codes = np.zeros(shell.shape, np.uint16)
    roles = np.where(ceiling[shell], 0, np.where(floor[shell], 1, 2))
    deep = wy < DEEP_Y
    support = solid[idx[:, 0], np.maximum(idx[:, 1] - 1, 0), idx[:, 2]] & (idx[:, 1] > 0)
    for n, (x, y, z) in enumerate(idx):
        role = "deep" if deep[n] else ("ceiling", "floor", "wall")[roles[n]]
        weights = design.palette[role]
        names_role = list(weights)
        state = names_role[int(_pick(weights, u[n:n + 1])[0])]
        if base_id(state) in GRAVITY and not support[n]:
            fallback = [s for s in names_role if base_id(s) not in GRAVITY]
            if not fallback:
                continue
            state = fallback[0]
        if state not in index:
            index[state] = len(palette)
            palette.append(state)
        codes[x, y, z] = index[state]
    written = codes != 0
    if not written.any():
        return None
    return _write(written, site, codes, palette)


# ------------------------------------------------------------------ pools
def pool_mask(design: CaveDesign, site: Site, void: np.ndarray) -> np.ndarray:
    """Still water in each pool's connected hollow, up to its level."""
    water = np.zeros(void.shape, bool)
    ys = np.arange(site.box[1], site.box[4] + 1)[None, :, None]
    for pool in design.pools:
        region = void & (ys <= pool.level)
        labels, _ = label(region)
        at = tuple(v - o for v, o in zip(pool.at, site.box[:3], strict=True))
        if not all(0 <= a < n for a, n in zip(at, void.shape, strict=True)) or not region[at]:
            raise ValueError(f"pool at {pool.at} must be a cave cell at or below its level {pool.level}")
        water |= labels == labels[at]
    return water


# ------------------------------------------------------------------ light
def _flood(transparent: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Spread block light: one level lost per step through transparent cells."""
    level = level.astype(np.int8)
    for value in range(15, 1, -1):
        frontier = level == value
        if not frontier.any():
            continue
        spread = _face_dilate(frontier) & transparent & (level < value - 1)
        level[spread] = value - 1
    return level


def block_light(transparent: np.ndarray, sources: list[tuple[int, int, int, int]],
                box: tuple[int, ...]) -> np.ndarray:
    """Block light over ``box`` from ``(x, y, z, level)`` sources."""
    seeds = np.zeros(transparent.shape, np.int8)
    for x, y, z, value in sources:
        i = (x - box[0], y - box[1], z - box[2])
        seeds[i] = max(seeds[i], value)
    return _flood(transparent, seeds)


def _site_light(site: Site, skip: np.ndarray | None = None) -> np.ndarray:
    """Seed levels of every light source in the read (cells in ``skip`` excluded)."""
    seeds = np.zeros(_dims(site.box), np.int8)
    x1, y1, z1 = site.box[:3]
    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            value = _light_of(state)
            if value:
                seeds[x - x1, lo - y1:hi - y1 + 1, z - z1] = value
    if skip is not None:
        seeds[skip] = 0
    return seeds


def _floors(flags: np.ndarray, spawn_on: np.ndarray, cave: np.ndarray, carved: np.ndarray,
            water: np.ndarray) -> np.ndarray:
    """Cave cells a mob could stand in: open, open above, an opaque full block below."""
    passable = ((flags & _OPEN) != 0) | carved
    passable &= ~water
    return cave & passable & _above(passable) & _below(spawn_on & ~carved)


def light_cells(design: CaveDesign, site: Site, void: np.ndarray, *, carved: np.ndarray | None = None,
                water: np.ndarray | None = None) -> list[tuple[int, int, int, str]]:
    """Lights placed until every floor cell reaches ``lights.min``, as ``(x, y, z, state)``.

    Counts every light already in the read (a player's lanterns too). Takes the
    darkest floor cell and sets a light block into the natural rock above it,
    else into natural rock below it, else hangs ``lights.hang`` in the air under
    a built ceiling when two clear cells stay above the floor.

    Raises:
        ValueError: When ``lights.max_count`` lights cannot light the floor.
    """
    if not design.lights.enabled or design.lights.minimum == 0:
        return []
    carved = cave_space(design, site).carved if carved is None else carved
    water = np.zeros(void.shape, bool) if water is None else water
    flags = _site_flags(site)
    full, lets_light = _classes(site)
    trans = lets_light | carved
    ids, names = _site_ids(site)
    cover = full & ~carved
    rock = np.array([n in NATURAL for n in names])[ids] & cover
    floor_rock = np.array([n in DRESSABLE for n in names])[ids] & cover
    air = np.array([n in _AIR for n in names])[ids] | carved
    floor = _floors(flags, full & ~lets_light, void, carved, water)
    level = _flood(trans, _site_light(site, skip=carved))
    skipped = np.zeros(void.shape, bool)
    placed: list[tuple[tuple[int, int, int], str]] = []
    nx, ny, nz = void.shape
    while True:
        dark = floor & (level < design.lights.minimum) & ~skipped
        if not dark.any():
            break
        if len(placed) >= design.lights.max_count:
            raise ValueError(
                f"{len(placed)} lights still leave {int(dark.sum())} dark floor cells; "
                "raise lights.max_count, lower lights.min or brighten lights.block")
        rank = np.where(dark, level, 99)
        x, y, z = (int(v) for v in np.unravel_index(int(np.argmin(rank)), rank.shape))
        top = y + 1
        while top < ny and trans[x, top, z]:
            top += 1
        if top < ny and rock[x, top, z]:
            spot, state = (x, top, z), design.lights.block
        elif y > 0 and floor_rock[x, y - 1, z]:
            spot, state = (x, y - 1, z), design.lights.block
        elif design.lights.hang and top < ny and cover[x, top, z] and top - 1 >= y + 2 and air[x, top - 1, z]:
            spot, state = (x, top - 1, z), design.lights.hang
        else:
            skipped[x, y, z] = True
            continue
        placed.append((spot, state))
        if state == design.lights.block:
            trans[spot] = rock[spot] = floor_rock[spot] = False
        air[spot] = False
        power = _light_of(state)
        lo = [max(0, c - power) for c in spot]
        hi = [min(n, c + power + 1) for c, n in zip(spot, (nx, ny, nz), strict=True)]
        win = tuple(slice(a, b) for a, b in zip(lo, hi, strict=True))
        seeds = np.zeros(trans[win].shape, np.int8)
        seeds[tuple(c - a for c, a in zip(spot, lo, strict=True))] = power
        level[win] = np.maximum(level[win], _flood(trans[win], seeds))
    x1, y1, z1 = site.box[:3]
    return [(x + x1, y + y1, z + z1, state) for (x, y, z), state in placed]


# ------------------------------------------------------------------ features
def feature_plan(design: CaveDesign, site: Site, void: np.ndarray, water: np.ndarray,
                 lights: list[tuple[int, int, int, str]], *, carved: np.ndarray | None = None,
                 clearance: int = 3) -> list[Feature]:
    """Spaced feature spots per role: air cells of the cave beside its surface.

    ``site`` is the cave after its layers, so a spot sees the dressed rock.
    Spots within ``clearance`` blocks of a player block are left out, so
    features do not grow over builds. A feature in ``_GROWS_ON`` only gets
    spots with a wall or ceiling face it grows on, and is planned first.
    """
    carved = cave_space(design, site).carved if carved is None else carved
    full, _ = _classes(site)
    solid = full & ~carved
    ids, names = _site_ids(site)
    air = np.array([n in _AIR for n in names])[ids] | carved
    built = np.array([n not in NATURAL for n in names])[ids] & ~carved
    x1, y1, z1 = site.box[:3]
    for x, y, z, state in lights:
        i = (x - x1, y - y1, z - z1)
        air[i] = False
        if state == design.lights.block:
            solid[i] = True
        else:
            built[i] = True
    near = built.copy()
    for _ in range(clearance):
        near = _face_dilate(near)
    dry = void & ~water & air & ~near
    spots = {
        "ceiling": dry & _above(solid),
        "floor": dry & _below(solid) & _above(dry),
    }
    spots["wall"] = dry & _beside(solid) & ~spots["ceiling"] & ~spots["floor"]
    rng = np.random.default_rng(design.seed)
    out: list[Feature] = []
    for spec in design.features:
        mask = spots[spec.on]
        if spec.id in _GROWS_ON:
            hosts = np.array([n in _GROWS_ON[spec.id] for n in names])[ids] & solid
            mask = mask & (_beside(hosts) | _above(hosts))
        cells = np.argwhere(mask)
        if not len(cells) or spec.per_100 <= 0:
            continue
        want = max(1, int(round(spec.per_100 * len(cells) / 100)))
        chosen: list[np.ndarray] = []
        for i in rng.permutation(len(cells)):
            cell = cells[i]
            if all(np.abs(cell - c).max() >= 3 for c in chosen):
                chosen.append(cell)
                if len(chosen) == want:
                    break
        out.extend(Feature(spec.id, int(c[0]) + x1, int(c[1]) + y1, int(c[2]) + z1, spec.on) for c in chosen)
    out.sort(key=lambda f: f.id not in _GROWS_ON)  # stable: the rest keep their order
    return out


# ------------------------------------------------------------------ results
@dataclass
class CaveResult:
    rows: list[dict]
    quality: dict[str, list[dict]]
    notes: list[str]
    bbox: tuple[int, int, int, int, int, int]
    report: dict
    previews: list[Path]


@dataclass
class CavePlan:
    space: CaveSpace
    layers: list[tuple[str, LiveWrite]]
    water: np.ndarray
    lights: list[tuple[int, int, int, str]]
    touched: list[dict]


def _shape_names(design: CaveDesign, box: tuple[int, ...]) -> tuple[np.ndarray, list[str]]:
    """Per cell, the index (1-based) of the first shape holding it, and the shape names."""
    grid = np.zeros(_dims(box), np.int16)
    names: list[str] = []
    masks = [(f"chamber {i}", chamber_mask(c, box, design.seed + 101 * i)) for i, c in enumerate(design.chambers)]
    masks += [(f"passage {i}", passage_mask(p, box, design.seed + 211 * i)) for i, p in enumerate(design.passages)]
    masks += [(f"ravine {i}", ravine_mask(r, box, design.seed + 307 * i)) for i, r in enumerate(design.ravines)]
    masks += [(f"shaft {i}", _column_disc(s.at, s.radius, box)[:, None, :]
               & (np.arange(box[1], box[4] + 1)[None, :, None] >= s.start)) for i, s in enumerate(design.shafts)]
    for name, mask in masks:
        names.append(name)
        grid[(grid == 0) & mask] = len(names)
    return grid, names


def _touched(design: CaveDesign, site: Site, layers: list[tuple[str, LiveWrite]]) -> list[dict]:
    """Every player block a layer changes, with where it is and why."""
    ids, names = _site_ids(site)
    built = np.array([n not in NATURAL for n in names])[ids]
    x1, y1, z1 = site.box[:3]
    shapes, shape_names = _shape_names(design, site.box) if any(m == "carve" for m, _ in layers) else (None, [])
    moved_to = {m.end: m for m in design.moves}
    moved_from = {m.start: m for m in design.moves}
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
            if base_id(old) in NATURAL or new == old:
                current[cell] = new
                continue
            if mode == "carve":
                where = shapes[cell[0] - x1, cell[1] - y1, cell[2] - z1] if shapes is not None else 0
                why = f"inside {shape_names[where - 1]}" if where else "inside the carved cave"
                if cell in moved_from:
                    why += f"; moved to {moved_from[cell].end}"
            elif mode == "move" and cell in moved_from and cell not in moved_to:
                why = f"moved to {moved_from[cell].end}"
            elif mode == "move":
                why = f"replaced by the block moved from {moved_to[cell].start}"
            elif mode == "pool":
                why = "flooded by a pool"
            else:
                why = f"changed by the {mode} phase"
            item = {"cell": list(cell), "block": old, "action": mode, "why": why}
            if holds_data(old):
                item["loses_data"] = True
            items.append(item)
            current[cell] = new
    return items


def built_token(items: list[dict]) -> str | None:
    """A short digest of the touched player blocks; approval names this exact list."""
    if not items:
        return None
    blob = json.dumps(sorted((i["cell"], i["block"], i["action"]) for i in items), separators=(",", ":"))
    return "built-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


def plan_cave(design: CaveDesign, site: Site) -> CavePlan:
    """Lay out every layer in build order — carve, move, dress, pool, light — and what they touch."""
    space = cave_space(design, site)
    layers: list[tuple[str, LiveWrite]] = []
    carve = carve_write(space.carved, site)
    if carve is not None:
        layers.append(("carve", carve))
    move = move_write(design, site, space.carved)
    if move is not None:
        layers.append(("move", move))
    after = _apply(site, layers) if layers else site
    dress = dress_write(design, after, space.void, space.carved)
    if dress is not None:
        layers.append(("dress", dress))
    water = pool_mask(design, after, space.void)
    if water.any():
        layers.append(("pool", _write(water, site, None, ["skip", "minecraft:water"])))
    lights = light_cells(design, after, space.void, carved=space.carved, water=water)
    if lights:
        cells = np.zeros(space.void.shape, bool)
        codes = np.zeros(space.void.shape, np.uint16)
        palette = ["skip"]
        for x, y, z, state in lights:
            if state not in palette:
                palette.append(state)
            i = (x - site.box[0], y - site.box[1], z - site.box[2])
            cells[i], codes[i] = True, palette.index(state)
        layers.append(("light", _write(cells, site, codes, palette)))
    return CavePlan(space, layers, water, lights, _touched(design, site, layers))


def _apply(site: Site, layers) -> Site:
    """The site read as it would look after the layers, for checks and previews."""
    x1, y1, z1, x2, y2, z2 = site.box
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


def final_states(design: CaveDesign, site: Site, void: np.ndarray | None = None, *, lit: bool = True) -> Site:
    """The site after every layer (lights only when ``lit``); ``void`` is ignored."""
    layers = plan_cave(design, site).layers
    if not lit:
        layers = [layer for layer in layers if layer[0] != "light"]
    return _apply(site, layers)


# ------------------------------------------------------------------ checks
def _runs(row: np.ndarray) -> int:
    best = run = 0
    prev = None
    for value in row:
        if np.isnan(value):
            prev, run = None, 0
            continue
        run = run + 1 if value == prev else 1
        prev = value
        best = max(best, run)
    return best


def _ceilings(cells: np.ndarray, trans: np.ndarray, y1: int) -> np.ndarray:
    """Per column, the y of the last open cell above the region's top cell (NaN where empty)."""
    nx, ny, nz = cells.shape
    heights = np.full((nx, nz), np.nan)
    has = cells.any(axis=1)
    top = ny - 1 - np.argmax(cells[:, ::-1, :], axis=1)
    for x, z in np.argwhere(has):
        y = int(top[x, z])
        while y + 1 < ny and trans[x, y + 1, z]:
            y += 1
        heights[x, z] = y + y1
    return heights


def check_cave(design: CaveDesign, site: Site) -> dict:
    """Check a site read of a finished cave against the design's quality rules.

    The carved shapes get the shape checks (``ceiling`` per chamber, ``span``,
    ``roof``); the whole cave, adopted parts included, gets ``light`` when the
    design is lit. Each entry has ``ok`` and ``detail``.
    """
    box = site.box
    flags = _site_flags(site)
    full, trans = _classes(site)
    shaped = envelope(design, box) & ~full & (flags & _FLUID == 0)
    for s in design.shafts:
        shaped &= ~(_column_disc(s.at, s.radius, box)[:, None, :]
                    & (np.arange(box[1], box[4] + 1)[None, :, None] >= s.start))
    region = existing_region(design, site) if design.existing else np.zeros_like(shaped)
    cave = shaped | region
    if not cave.any():
        return {"ok": False, "checks": [{"name": "void", "ok": False,
                                         "detail": "no open cells inside the design's shapes or existing caves"}]}
    checks = []
    for i, c in enumerate(design.chambers):
        cells = chamber_mask(c, box, design.seed + 101 * i) & shaped
        if not cells.any():
            checks.append({"name": "ceiling", "ok": False, "detail": f"chamber {i} has no open cells"})
            continue
        heights = _ceilings(cells, trans, box[1])
        values = heights[np.isfinite(heights)]
        std = float(values.std())
        flat = max(max((_runs(row) for row in heights), default=0),
                   max((_runs(col) for col in heights.T), default=0))
        ok = std >= design.limits["ceiling_std"] and flat <= design.limits["flat_run"]
        checks.append({"name": "ceiling", "ok": ok,
                       "detail": f"chamber {i}: ceiling height spread {std:.2f} "
                                 f"(min {design.limits['ceiling_std']}), longest flat run {flat} "
                                 f"(max {int(design.limits['flat_run'])})"})
    if shaped.any():
        span = 0.0
        for y in range(shaped.shape[1]):
            layer = shaped[:, y, :]
            if layer.any():
                span = max(span, float(distance_transform_edt(layer).max()) * 2)
        checks.append({"name": "span", "ok": span <= design.limits["max_span"],
                       "detail": f"widest unsupported span {span:.0f} blocks "
                                 f"(max {int(design.limits['max_span'])})"})
    if design.lights.enabled and design.lights.minimum > 0:
        level = _flood(trans, _site_light(site))
        floor = _floors(flags, full & ~trans, cave, np.zeros_like(cave), np.zeros_like(cave))
        dark = floor & (level < design.lights.minimum)
        detail = f"{int(dark.sum())} of {int(floor.sum())} floor cells below light {design.lights.minimum}"
        if dark.any():
            first = tuple(int(v) + o for v, o in zip(np.argwhere(dark)[0], box[:3], strict=True))
            detail += f", first at {first}"
        checks.append({"name": "light", "ok": bool(floor.any() and not dark.any()), "detail": detail})
    if shaped.any():
        ground = surfaces(site).ground
        shafts = np.zeros(ground.shape, bool)
        for s in design.shafts:
            shafts |= _column_disc(s.at, s.radius, box)
        has = shaped.any(axis=1) & ~shafts & np.isfinite(ground)
        top = box[1] + shaped.shape[1] - 1 - np.argmax(shaped[:, ::-1, :], axis=1)
        with np.errstate(invalid="ignore"):
            thin = has & (ground - 1 - top < design.roof)
        checks.append({"name": "roof", "ok": not thin.any(),
                       "detail": f"{int(thin.sum())} columns with less than {design.roof} blocks of roof"})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


# ------------------------------------------------------------------ previews
_COLOURS = {
    "rock": (110, 110, 110), "void": (30, 30, 34), "dress": (150, 122, 90), "water": (58, 110, 232),
    "light": (255, 211, 77), "air": (201, 231, 255), "outside": (60, 60, 60),
}


def _previews(design: CaveDesign, site: Site, void, layers, folder: Path) -> list[Path]:
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    after = _apply(site, layers)
    flags = _site_flags(after)
    trans = _transparent(flags)
    water = flags & _FLUID != 0
    kinds = {mode: np.zeros(void.shape, bool) for mode, _ in layers}
    for mode, write in layers:
        ox, oy, oz = (o - b for o, b in zip(write.origin, site.box[:3], strict=True))
        sx, sy, sz = write.codes.shape
        kinds[mode][ox:ox + sx, oy:oy + sy, oz:oz + sz] |= write.codes != 0
    scale = 6
    paths = []
    # Plan: void columns shaded by ceiling height, lights and pools on top.
    has = void.any(axis=1)
    top = void.shape[1] - 1 - np.argmax(void[:, ::-1, :], axis=1)
    lo, hi = top[has].min(), top[has].max()
    img = np.zeros((void.shape[2], void.shape[0], 3), np.uint8)
    img[:] = _COLOURS["outside"]
    shade = ((top - lo) / max(hi - lo, 1) * 160 + 60).astype(np.uint8)
    for x, z in np.argwhere(has):
        img[z, x] = (shade[x, z] // 3, shade[x, z] // 2, shade[x, z])
    for x, z in np.argwhere(kinds.get("pool", np.zeros_like(void)).any(axis=1)):
        img[z, x] = _COLOURS["water"]
    for x, z in np.argwhere(kinds.get("light", np.zeros_like(void)).any(axis=1)):
        img[z, x] = _COLOURS["light"]
    path = folder / f"{design.element}-plan.png"
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(path)
    paths.append(path)
    # Sections through the middle of the void, x then z.
    idx = np.argwhere(void)
    mid = (idx.min(axis=0) + idx.max(axis=0)) // 2
    for axis, name in ((0, "x"), (2, "z")):
        take = (lambda a: a[mid[0], :, :]) if axis == 0 else (lambda a: a[:, :, mid[2]])
        t, w, d, li, v = (take(m) for m in (trans, water, kinds.get("dress", np.zeros_like(void)),
                                            kinds.get("light", np.zeros_like(void)), void))
        sec = np.zeros(t.shape + (3,), np.uint8)
        sec[:] = _COLOURS["rock"]
        sec[t] = _COLOURS["air"]
        sec[v & t] = _COLOURS["void"]
        sec[d] = _COLOURS["dress"]
        sec[w] = _COLOURS["water"]
        sec[li] = _COLOURS["light"]
        if axis == 2:  # an (x, y) cut; an x cut is already (y, z)
            sec = sec.transpose(1, 0, 2)
        sec = sec[::-1]  # rows = y, top first
        path = folder / f"{design.element}-section-{name}.png"
        Image.fromarray(np.ascontiguousarray(sec)).resize(
            (sec.shape[1] * scale, sec.shape[0] * scale), Image.NEAREST).save(path)
        paths.append(path)
    return paths


# ------------------------------------------------------------------ emit
def emit_cave(design: CaveDesign, project_dir: Path, *, first_phase: int, preview: bool = False,
              standalone: bool = False, max_columns: int = 128, approve_built: str | None = None) -> CaveResult:
    """Check the cave against its site read and write its phases.

    Args:
        design: The validated design.
        project_dir: The project folder (``phases/`` and ``terrain/`` go here).
        first_phase: The id of the first phase in the host plan.
        preview: Write only previews and the report, no phase files.
        standalone: Also write a ``plan.toon`` for a cave that is its own project.
        max_columns: Columns per phase tile.
        approve_built: The report's ``built.token``, given only after the user has
            seen and approved every player block the cave touches.

    Returns:
        Phase rows, quality rows, notes, the bounding box, the report and the previews.

    Raises:
        ValueError: An invalid design or site read.
        VerifyError: A layer would drain, spill or overwrite liquid or leave a gravity block
            hanging, or (outside a preview) the projected cave fails its quality checks.
    """
    first_phase = integer_level(first_phase, "first_phase")
    if first_phase < 1:
        raise ValueError("first_phase must be positive")
    project = Path(project_dir)
    site = load_site(design.site)
    plan = plan_cave(design, site)
    void, void_report, layers, water, lights = (plan.space.void, plan.space.report, plan.layers,
                                                plan.water, plan.lights)
    tiles = check_form_layers(site, layers, max_columns=max_columns)
    after = _apply(site, layers)
    features = feature_plan(design, after, void, water, lights, carved=plan.space.carved)
    quality_report = check_cave(design, after)
    rows: list[dict] = []
    payloads: list[tuple[Path, dict]] = []
    counters: dict[str, int] = {}
    boxes = []
    for mode, tile in tiles:
        fills = greedy_fills(tile)
        lo = [min(f["from"][i] for f in fills) for i in range(3)]
        hi = [max(f["to"][i] for f in fills) for i in range(3)]
        counters[mode] = counters.get(mode, 0) + 1
        name = f"{design.element}-{mode}-{counters[mode]}"
        file = f"phases/{first_phase + len(rows):02d}-{name}.json"
        payload: dict[str, Any] = {"fills": fills, "liquids": "static"}
        if site.world is not None:
            payload["world"] = site.world
        payloads.append((project / file, payload))
        rows.append({"id": first_phase + len(rows), "name": name, "file": file,
                     "blocks": int(np.count_nonzero(tile.codes)), "from": lo, "to": hi,
                     "via": "placer", "rollback": "backup"})
        boxes.append((*lo, *hi))
    features_spec = None
    if features:
        features_spec = features_file(features, world=site.world, reach=FEATURE_REACH)
        file = f"terrain/{design.element}.features.json"
        box = features_spec["box"]
        rows.append({"id": first_phase + len(rows), "name": f"{design.element}-features", "file": file,
                     "blocks": len(features_spec["commands"]), "from": box[:3], "to": box[3:],
                     "via": "commands", "rollback": "backup"})
        boxes.append(tuple(box))
    bbox = tuple(min(b[i] for b in boxes) for i in range(3)) + tuple(max(b[i] for b in boxes) for i in range(3, 6))
    quality = {"cave": [{"file": f"terrain/{design.element}.cave.json"}]}
    hung = sum(1 for light in lights if light[3] != design.lights.block)
    token = built_token(plan.touched)
    by_block: dict[str, int] = {}
    for item in plan.touched:
        by_block[base_id(item["block"])] = by_block.get(base_id(item["block"]), 0) + 1
    built = {"token": token, "count": len(plan.touched), "by_block": by_block,
             "loses_data": sum(1 for i in plan.touched if i.get("loses_data")), "items": plan.touched}
    report = {"void": void_report, "lights": len(lights), "hanging_lights": hung, "pool_cells": int(water.sum()),
              "features": len(features), "built": built, "check": quality_report}
    notes = [
        f"cave design terrain/{design.element}.cave.json, style {design.style}, seed {design.seed}",
        f"{void_report['cells']:,} void cells; {void_report['roof_trimmed']:,} trimmed to keep {design.roof} "
        f"blocks of roof outside shafts",
        f"{len(lights) - hung} light blocks ({design.lights.block}), {hung} hanging lights, "
        f"{int(water.sum())} pool cells, {len(features)} features",
        "projected check: " + "; ".join(f"{c['name']} {'ok' if c['ok'] else 'FAILS'}: {c['detail']}"
                                        for c in quality_report["checks"]),
    ]
    if void_report["existing_cells"]:
        notes.append(f"adopts {void_report['existing_cells']:,} cells of existing cave as they are")
    if plan.touched:
        notes.append(f"touches {len(plan.touched)} player blocks ({', '.join(f'{n} {b}' for b, n in by_block.items())}); "
                     f"approval token {token}; list in terrain/{design.element}.cave-report.json")
    if void_report["meets_existing_open"]:
        notes.append(f"the cave opens into existing open space at {void_report['meets_existing_open']} cells")
    terrain = project / "terrain"
    previews = _previews(design, site, void, layers, terrain / "previews")
    report_dir = terrain / "previews" if preview else terrain
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{design.element}.cave-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = CaveResult(rows, quality, notes, bbox, report, previews)
    if preview:
        return result
    failed = [c for c in quality_report["checks"] if not c["ok"]]
    if failed:
        raise VerifyError(
            "the design fails its own checks: "
            + "; ".join(f"{c['name']}: {c['detail']}" for c in failed)
            + ". Revise the design (pillars, relief, lights) or, with the user's OK, set its limits")
    if plan.touched and approve_built != token:
        raise VerifyError(
            f"the cave touches {len(plan.touched)} player blocks "
            f"({', '.join(f'{n} {b}' for b, n in by_block.items())}): show the user each block, where it is "
            f"and why ({report_path}), and only after their yes rerun with --approve-built {token}")
    for path, payload in payloads:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    if features_spec is not None:
        (terrain / f"{design.element}.features.json").write_text(
            json.dumps(features_spec, indent=2) + "\n", encoding="utf-8")
    design_path = terrain / f"{design.element}.cave.json"
    if not design_path.exists() or json.loads(design_path.read_text(encoding="utf-8")) != design.source:
        design_path.write_text(json.dumps(design.source, indent=2) + "\n", encoding="utf-8")
    snippet = plan_rows_toon(EmitResult(rows, quality, notes, bbox, None, None))  # type: ignore[arg-type]
    (terrain / f"{design.element}.plan-rows.toon").write_text(snippet, encoding="utf-8")
    if standalone:
        lines = ["plan:", f"  project: {project.resolve().name}", "  skill: terrain-cave"]
        if site.world is not None:
            lines.append(f"  world: {site.world}")
        centre = [int((bbox[i] + bbox[i + 3]) // 2) for i in range(3)]
        lines += [f"  anchor: {{x: {centre[0]}, y: {centre[1]}, z: {centre[2]}}}",
                  f"  bbox: {{from: {list(bbox[:3])}, to: {list(bbox[3:])}}}",
                  f"  summary: {design.element} ({design.style} cave)", "  approved: no"]
        (project / "plan.toon").write_text("\n".join(lines) + "\n" + snippet, encoding="utf-8")
    return result


# ------------------------------------------------------------------ command line
def add_cave_parsers(commands) -> None:
    """Register ``cave`` and ``cave-check`` on the launcher's subcommands."""
    cave = commands.add_parser("cave", help="check a cave design and write its phases (or only previews)")
    cave.add_argument("design", type=Path)
    cave.add_argument("--project", type=Path, required=True)
    cave.add_argument("--first-phase", type=int, required=True)
    cave.add_argument("--preview", action="store_true", help="write previews and the report only")
    cave.add_argument("--standalone", action="store_true", help="also write plan.toon")
    cave.add_argument("--approve-built", metavar="TOKEN",
                      help="the report's built.token, after the user approved every touched player block")
    check = commands.add_parser("cave-check", help="check a fresh site read of a built cave")
    check.add_argument("design", type=Path)
    check.add_argument("--site", type=Path, required=True)
    check.add_argument("--project", type=Path)


def run_cave(args) -> int:
    """Run ``cave`` or ``cave-check``; print JSON; return the exit status."""
    design = load_design(args.design, args.project)
    if args.command == "cave-check":
        report = check_cave(design, load_site(args.site))
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    result = emit_cave(design, args.project, first_phase=args.first_phase,
                       preview=args.preview, standalone=args.standalone, approve_built=args.approve_built)
    print(json.dumps({"preview": args.preview, "phases": result.rows, "bbox": list(result.bbox),
                      "notes": result.notes, "report": result.report,
                      "previews": [str(p) for p in result.previews]}, indent=2))
    return 0

