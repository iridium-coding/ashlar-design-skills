"""Design sparse, trunk-relative trees, preview them and anchor F7 modules on a surface."""

from __future__ import annotations

import json
import math
import os
import random
import re
import runpy
import subprocess
import sys
import tempfile
from dataclasses import dataclass, fields, replace
from functools import cache
from pathlib import Path

import numpy as np
from voxel import Palette, VoxelModel, render_views

from .ashlar_emit import _bounds as phase_bounds
from .ashlar_emit import _table, _write_json
from .live import _WORLD_MAX, _WORLD_MIN
from .plant import GROWABLE, site_planting
from .site import LEAVES, TRUNK, Cell, base_id, integer_level, load_site

_AXIS_WOOD = TRUNK - {"minecraft:mushroom_stem", "minecraft:mangrove_roots"}
_PERSISTENT_LEAVES = frozenset(state for state in LEAVES if state.endswith("_leaves"))

CANOPIES = ("round", "ellipsoid", "conical", "columnar", "umbrella", "weeping", "layered", "sparse", "dead")


@dataclass(frozen=True)
class TreeParams:
    """Lean is horizontal travel per block of rise. Curve is a mid-trunk bow in blocks.

    Taper is the fraction of width lost by the crown. Branch angle is measured
    from vertical. Branch length is a fraction of height and the length ratio
    for successive forks. Canopy radius is the crown or foliage-clump radius.
    """

    wood: str = "minecraft:oak_log"
    leaves: str = "minecraft:oak_leaves"
    height: int = 12
    trunk_width: int = 1
    taper: float = 0.0
    lean: tuple[float, float] = (0.0, 0.0)
    curve: float = 0.0
    branch_levels: int = 2
    branches: int = 4
    branch_angle: float = 40.0
    branch_length: float = 0.6
    canopy: str = "round"
    canopy_radius: float = 4.0
    leaf_density: float = 0.85
    roots: bool = False
    seed: int = 0


PRESETS = {
    "broad-oak": TreeParams(
        height=12,
        trunk_width=2,
        taper=0.75,
        branches=7,
        branch_angle=64,
        branch_length=0.55,
        curve=0.8,
        roots=True,
    ),
    "conifer-spire": TreeParams(
        wood="minecraft:spruce_log",
        leaves="minecraft:spruce_leaves",
        height=21,
        branches=15,
        branch_angle=81,
        branch_length=0.23,
        canopy="conical",
        canopy_radius=4.3,
    ),
    "umbrella-pine": TreeParams(
        wood="minecraft:acacia_log",
        leaves="minecraft:spruce_leaves",
        height=13,
        lean=(0.13, 0),
        curve=1.6,
        branches=6,
        branch_angle=69,
        branch_length=0.50,
        canopy="umbrella",
        canopy_radius=4.2,
    ),
    "weeping-willow": TreeParams(
        wood="minecraft:mangrove_log",
        leaves="minecraft:mangrove_leaves",
        height=13,
        trunk_width=2,
        taper=0.65,
        branches=8,
        branch_angle=70,
        branch_length=0.49,
        canopy="weeping",
        canopy_radius=3.6,
        roots=True,
    ),
    "windswept-cypress": TreeParams(
        wood="minecraft:spruce_log",
        leaves="minecraft:spruce_leaves",
        height=15,
        lean=(0.53, -0.16),
        curve=1.8,
        branches=6,
        branch_angle=46,
        branch_length=0.28,
        canopy="columnar",
        canopy_radius=2.4,
    ),
    "dead-snag": TreeParams(
        wood="minecraft:stripped_dark_oak_log",
        height=12,
        taper=0.75,
        trunk_width=2,
        curve=1.1,
        branches=4,
        branch_angle=58,
        branch_length=0.36,
        canopy="dead",
    ),
    "giant-fantasy": TreeParams(
        wood="minecraft:dark_oak_log",
        leaves="minecraft:flowering_azalea_leaves",
        height=29,
        trunk_width=3,
        taper=0.85,
        curve=2.8,
        lean=(0.08, 0.06),
        branches=12,
        branch_levels=3,
        branch_angle=70,
        branch_length=0.34,
        canopy="layered",
        canopy_radius=5.3,
        roots=True,
    ),
}


@dataclass
class Tree:
    wood: dict[Cell, str]
    leaves: dict[Cell, str]
    ground: dict[Cell, str]
    anchor: Cell


def _validate(p):
    if not isinstance(p.wood, str) or p.wood not in _AXIS_WOOD:
        raise ValueError("wood must be a vanilla log, wood, stem or hyphae with an axis")
    if not isinstance(p.leaves, str) or p.leaves not in _PERSISTENT_LEAVES:
        raise ValueError("leaves must be a vanilla leaf block with a persistent state")
    if p.canopy not in CANOPIES or type(p.roots) is not bool:
        raise ValueError("invalid canopy or roots setting")
    if not isinstance(p.lean, (tuple, list)) or len(p.lean) != 2:
        raise ValueError("lean must contain two horizontal slopes [x, z]")
    # Bound recursion and raster sizes for user-authored parameter files.
    for key, lo, hi in (
        ("height", 1, 384),
        ("trunk_width", 1, 3),
        ("branch_levels", 0, 8),
        ("branches", 0, 64),
    ):
        value = getattr(p, key)
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f"{key} must be an integer between {lo} and {hi}")
    for value, key, lo, hi in (
        (p.taper, "taper", 0, 1),
        (p.leaf_density, "leaf_density", 0, 1),
        (p.branch_angle, "branch_angle", 0, 90),
        (p.branch_length, "branch_length", 0, 1),
        (p.canopy_radius, "canopy_radius", 0.5, 32),
        (p.curve, "curve", -64, 64),
        *((slope, "lean", -4, 4) for slope in p.lean),
    ):
        if type(value) not in (int, float) or not lo <= value <= hi:
            raise ValueError(f"{key} must be a finite number between {lo} and {hi}")
    if type(p.seed) is not int:
        raise ValueError("seed must be an integer")


def _limb(wood, start, end, material):
    """Traverse crossed voxel faces in order. Each log follows its incoming face."""
    delta = tuple(b - a for a, b in zip(start, end))
    crossings = sorted(
        ((step + 0.5) / abs(d), axis) for axis, d in enumerate(delta) for step in range(abs(d))
    )
    cell = list(start)
    for _, axis in crossings:
        cell[axis] += 1 if delta[axis] > 0 else -1
        wood.setdefault(tuple(cell), f"{material}[axis={'xyz'[axis]}]")


def _skeleton(p, rng):
    wood, spine, tips = {}, [], []
    bow = rng.uniform(0, math.tau)
    for y in range(p.height):
        t = y / max(1, p.height - 1)
        bend = math.sin(t * math.pi) * p.curve
        x = round(y * p.lean[0] + math.cos(bow) * bend)
        z = round(y * p.lean[1] + math.sin(bow) * bend)
        center = (x, y, z)
        width = max(1, round(p.trunk_width * (1 - p.taper * t)))
        if p.trunk_width == 3 and y >= max(1, p.height // 5):
            width = min(width, 2)
        start = -(width // 2) if width == 3 else 0
        for dx in range(start, start + width):
            for dz in range(start, start + width):
                wood[(x + dx, y, z + dz)] = f"{p.wood}[axis=y]"
        if spine:
            _limb(wood, spine[-1], center, p.wood)
        spine.append(center)

    def fork(start, heading, inclination, length, level):
        run = length * math.sin(inclination)
        end = (
            start[0] + round(run * math.cos(heading)),
            start[1] + round(length * math.cos(inclination)),
            start[2] + round(run * math.sin(heading)),
        )
        _limb(wood, start, end, p.wood)
        if level == p.branch_levels or length * p.branch_length < 1.5:
            tips.append(end)
            return
        for side in (-1, 1):
            fork(
                end,
                heading + side * rng.uniform(0.36, 0.90),
                max(0, inclination - rng.uniform(0.10, 0.40)),
                length * p.branch_length * rng.uniform(0.82, 1),
                level + 1,
            )

    phase = rng.uniform(0, math.tau)
    low, high = {
        "conical": (0.22, 0.88),
        "columnar": (0.38, 0.86),
        "layered": (0.28, 0.81),
        "umbrella": (0.69, 0.84),
        "weeping": (0.54, 0.74),
        "dead": (0.29, 0.83),
    }.get(p.canopy, (0.42, 0.75))
    for i in range(p.branches if p.branch_levels and p.branch_length else 0):
        u = (i + rng.uniform(0.15, 0.85)) / p.branches
        if p.canopy == "layered":
            # Whorls at three distinct heights leave daylight between the tiers.
            u = min(2, int(3 * u)) * 0.46 + rng.uniform(0, 0.07)
        start = spine[round((p.height - 1) * (low + u * (high - low)))]
        heading = phase + i * 2.399963 + rng.uniform(-0.20, 0.20)
        if p.canopy == "columnar" and any(p.lean):
            heading = math.atan2(p.lean[1], p.lean[0]) + 1.35 * math.sin(heading)
        length = p.height * p.branch_length * rng.uniform(0.84, 1.04)
        if p.canopy in ("conical", "layered"):
            length *= 1 - 0.67 * u
        inclination = math.radians(max(0, min(90, p.branch_angle + rng.uniform(-5, 5))))
        fork(start, heading, inclination, length, 1)
    return wood, spine, tips


def _clump(cells, center, horizontal, vertical):
    cx, cy, cz = center
    radius = math.ceil(horizontal)
    for dy in range(-math.floor(vertical), math.floor(vertical) + 1):
        y = cy + dy
        if y <= 0:
            continue
        cross = (1 - (dy / vertical) ** 2) * horizontal**2
        for dx in range(-radius, radius + 1):
            span = cross - dx * dx
            if span < 0:
                continue
            dz_max = math.floor(math.sqrt(span))
            for dz in range(-dz_max, dz_max + 1):
                cells.add((cx + dx, y, cz + dz))


def _foliage(p, wood, spine, tips, rng):
    if p.canopy == "dead" or not p.leaf_density:
        return {}
    candidates = set()
    r = p.canopy_radius
    if p.canopy == "conical":
        base = max(1, p.height // 4)
        for y in range(base, p.height + 2):
            x, _, z = spine[min(y, p.height - 1)]
            fraction = (p.height + 1 - y) / max(1, p.height + 1 - base)
            radius = 0.55 + r * fraction
            if (y - base) % 3 == 2:
                radius *= 0.72
            _clump(candidates, (x, y, z), radius, 0.51)
        for center in tips:
            _clump(candidates, center, max(1, r * 0.33), 0.8)
    else:
        wide, tall = {
            "round": (1, 0.83),
            "ellipsoid": (1.18, 0.61),
            "umbrella": (1.12, 0.33),
            "weeping": (1, 0.53),
            "layered": (1, 0.38),
            "sparse": (0.6, 0.44),
            "columnar": (0.7, 1.43),
        }[p.canopy]
        for center in [*tips, spine[-1]]:
            scale = rng.uniform(0.84, 1.07)
            _clump(candidates, center, r * wide * scale, max(0.65, r * tall * scale))
    # Thin before the six-face distance walk so no hole can sever a surviving leaf.
    candidates = {v for v in sorted(candidates) if rng.random() < p.leaf_density}
    if p.canopy == "weeping":
        underside = {}
        for x, y, z in candidates:
            underside[x, z] = min(underside.get((x, z), y), y)
        for (x, z), y in sorted(underside.items()):
            if rng.random() < 0.46 * p.leaf_density and any(
                (x + dx, z + dz) not in underside for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2))
            ):
                for drop in range(1, rng.randint(3, 6) + 1):
                    if y - drop > 0:
                        candidates.add((x, y - drop, z))
        # Long curtains sprout directly from outer boughs. Starting beside
        # wood lets even the bottom of a five-block strand stay supported.
        for x, y, z in tips:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if rng.random() < 0.63 * p.leaf_density:
                    drop = rng.randint(3, 5)
                    candidates.update((x + dx, yy, z + dz) for yy in range(max(1, y - drop), y + 1))
    candidates.difference_update(wood)
    leaves = {}
    layer = wood.keys()
    for _ in range(6):
        following = set()
        for x, y, z in layer:
            for v in (
                (x + 1, y, z),
                (x - 1, y, z),
                (x, y + 1, z),
                (x, y - 1, z),
                (x, y, z + 1),
                (x, y, z - 1),
            ):
                if v in candidates:
                    following.add(v)
                    candidates.remove(v)
        leaves.update(dict.fromkeys(following, f"{p.leaves}[persistent=true]"))
        layer = following
    return leaves


def generate(params: TreeParams) -> Tree:
    """Build with the trunk base at (0,0,0); optional buried roots lie at y=-1."""
    _validate(params)
    rng = random.Random(params.seed)
    wood, spine, tips = _skeleton(params, rng)
    leaves = _foliage(params, wood, spine, tips, rng)
    ground = {}
    if params.roots:
        phase = rng.uniform(0, math.tau)
        for i in range(3 + params.trunk_width):
            angle = phase + i * math.tau / (3 + params.trunk_width) + rng.uniform(-0.24, 0.24)
            length = rng.uniform(1.5, 2.5) + params.trunk_width
            end = (round(length * math.cos(angle)), -1, round(length * math.sin(angle)))
            _limb(ground, (0, -1, 0), end, params.wood)
        ground[0, -1, 0] = f"{params.wood}[axis=y]"
    return Tree(wood, leaves, ground, (0, 0, 0))


def _bounds(tree):
    axes = tuple(zip(*tree.wood, *tree.leaves, *tree.ground))
    return tuple(map(min, axes)), [max(axis) - min(axis) + 1 for axis in axes]


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("module name must be a single filename stem of letters, digits, '_' or '-'")
    return value


def to_module(tree: Tree, name: str) -> dict:
    """Normalize all three parts together. The stamper merges adjacent cells into fills."""
    low, size = _bounds(tree)

    def local(pos):
        return [v - lo for v, lo in zip(pos, low)]

    module = {"name": _name(name), "kind": "vegetation", "size": size, "anchor": local(tree.anchor)}
    for part in ("ground", "wood", "leaves"):
        module[part] = {
            "fills": [],
            "blocks": [
                {"pos": local(pos), "block": state} for pos, state in sorted(getattr(tree, part).items())
            ],
        }
    return module


def _color(state, part):
    if part != "leaves":
        return (103, 74, 48)
    for species, color in (
        ("spruce", (51, 90, 73)),
        ("cherry", (224, 150, 174)),
        ("pale_oak", (153, 163, 143)),
        ("red_poplar", (162, 63, 35)),
        ("orange_poplar", (199, 103, 36)),
        ("yellow_poplar", (211, 164, 46)),
        ("flowering_azalea", (106, 137, 68)),
        ("mangrove", (79, 117, 56)),
    ):
        if species in state:
            return color
    return (89, 136, 63)


def preview(tree: Tree, prefix: str) -> list[str]:
    """Write isometric, side and front PNGs through the sibling voxel renderer."""
    low, size = _bounds(tree)
    model = VoxelModel(*size, Palette())
    for part in ("ground", "wood", "leaves"):
        for pos, state in getattr(tree, part).items():
            model.g[tuple(v - lo for v, lo in zip(pos, low))] = model.pal.add(state, _color(state, part))
    return render_views(model, prefix, iso_a=5, iso_vh=5, ortho_px=6)


@cache
def _stamp_geometry():
    # Reuse exactly the standalone stamper's mirror-then-turn and size convention.
    path = Path(__file__).resolve().parents[3] / "exec-ashlar" / "scripts" / "stamp.py"
    return runpy.run_path(str(path))


def _check_tree_module(module, stamp):
    if not isinstance(module, dict) or module.get("kind") != "vegetation":
        raise ValueError("tree placement requires an F7 vegetation module")
    has_anchor = False
    try:
        stamp["_check_vegetation"](module)
        anchor = module["anchor"]
        for part in ("ground", "wood", "leaves"):
            body = module.get(part, {})
            for kind in ("blocks", "fills"):
                entries = body.get(kind, [])
                if not isinstance(entries, list):
                    raise TypeError(f"F7 {part}.{kind} must be a list")
                for entry in entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("block"), str):
                        raise TypeError(f"F7 {part} entry requires a block state")
                    lo, hi = (
                        (entry.get("pos"), entry.get("pos"))
                        if kind == "blocks"
                        else (entry.get("from"), entry.get("to"))
                    )
                    for point in (lo, hi):
                        stamp["_inside"](point, module["size"], f"F7 {part}.{kind}")
                    bid, pairs = stamp["parse_state"](entry["block"])
                    states = dict(pairs)
                    if bid in {
                        "minecraft:air",
                        "minecraft:cave_air",
                        "minecraft:void_air",
                        "air",
                        "cave_air",
                        "void_air",
                    }:
                        raise ValueError("F7 cannot contain air")
                    if part == "wood":
                        if bid not in _AXIS_WOOD or states.get("axis") not in ("x", "y", "z"):
                            raise ValueError("F7 wood requires axis-bearing wood with its axis")
                        if min(lo[1], hi[1]) < anchor[1]:
                            raise ValueError("F7 trunk anchor must lie at the lowest wood height")
                        if all(min(a, b) <= v <= max(a, b) for a, b, v in zip(lo, hi, anchor)):
                            has_anchor = True
                    if part == "leaves" and (
                        bid not in _PERSISTENT_LEAVES or states.get("persistent") != "true"
                    ):
                        raise ValueError("F7 leaves require persistent=true on a vanilla leaf block")
    except stamp["StampError"] as exc:
        raise ValueError(str(exc)) from exc
    if not has_anchor:
        raise ValueError("F7 anchor must lie on a wood cell")


def tree_placements(
    points: list[tuple[int, int]],
    surface: np.ndarray,
    origin: tuple[int, int],
    module: dict,
    *,
    phase: int,
    seed: int,
) -> list[dict]:
    """Use world x/z points and integer block elevations on an x-major surface."""
    stamp = _stamp_geometry()
    _check_tree_module(module, stamp)
    name = _name(module.get("name"))
    phase = integer_level(phase, "phase")
    if phase < 1:
        raise ValueError("phase must be positive")
    rng = random.Random(integer_level(seed, "seed"))
    ox, oz = (integer_level(v, "surface origin") for v in origin)
    surface = np.asarray(surface)
    if surface.ndim != 2:
        raise ValueError("surface must be a two-dimensional x/z grid")
    rows = []
    size = module["size"]
    for point in points:
        x, z = (integer_level(v, "tree point") for v in point)
        if not (0 <= x - ox < surface.shape[0] and 0 <= z - oz < surface.shape[1]):
            raise ValueError(f"tree point {(x, z)} is outside the surface")
        y = integer_level(surface[x - ox, z - oz], "surface height") + 1
        rotation = rng.choice((0, 90, 180, 270))
        mirror = rng.choice(("none", "x", "z"))
        ax, ay, az = stamp["transform_point"](module["anchor"], size, rotation, mirror, [0, 0, 0])
        corner = [x - ax, y - ay, z - az]
        x1, y1, z1, x2, y2, z2 = stamp["footprint"](size, rotation, corner)
        if not (
            -30_000_000 <= x1 <= x2 < 30_000_000
            and -30_000_000 <= z1 <= z2 < 30_000_000
            and _WORLD_MIN <= y1 <= y2 <= _WORLD_MAX
        ):
            raise ValueError(f"tree at {(x, y, z)} extends outside world bounds")
        rows.append(
            {"module": name, "origin": corner, "rotation": rotation, "mirror": mirror, "phase": phase}
        )
    return rows


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _publish(files, *, update=None):
    """Link new artifacts without clobbering existing files, then switch the checked F6."""
    for src, dest in files:
        if dest.exists() and src.read_bytes() != dest.read_bytes():
            raise ValueError(f"existing artifact differs: {dest}")
    added = []
    try:
        for src, dest in files:
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src, dest)
                added.append(dest)
            except FileExistsError:
                if src.read_bytes() != dest.read_bytes():
                    raise ValueError(f"existing artifact differs: {dest}")
        if update:
            src, dest, before = update
            dest.parent.mkdir(parents=True, exist_ok=True)
            if before is None:
                os.link(src, dest)
            elif dest.read_bytes() != before:
                raise ValueError(f"expected surface changed during tree placement: {dest}")
            elif src.read_bytes() != before:
                os.replace(src, dest)
    except (OSError, ValueError):
        for path in reversed(added):
            path.unlink()
        raise


def _destination(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"output path must stay inside {root}: {relative}")
    return path


def write_tree(preset: str, overrides: list[str], name: str, output: Path) -> list[Path]:
    """Produce the F7 JSON and three previews; overrides are key=JSON or bare block/profile names."""
    _name(name)
    if preset not in PRESETS:
        raise ValueError(f"unknown tree preset {preset!r}")
    changes = {}
    keys = {f.name for f in fields(TreeParams)}
    for item in overrides:
        key, sep, raw = item.partition("=")
        if not sep or key not in keys or key in changes:
            raise ValueError(f"expected one key=value for a known tree parameter: {item!r}")
        if key in ("wood", "leaves", "canopy") and not raw.startswith('"'):
            changes[key] = raw
        else:
            try:
                changes[key] = json.loads(raw)
            except ValueError as exc:
                raise ValueError(f"{key} requires a JSON value; use [x,z] for lean") from exc
    tree = generate(replace(PRESETS[preset], **changes))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        folder = Path(temp)
        module = folder / f"{name}.json"
        _write_json(module, to_module(tree, name))
        sources = [module, *(Path(p) for p in preview(tree, str(folder / name)))]
        targets = [_destination(output, src.name) for src in sources]
        _publish(list(zip(sources, targets)))
    return targets


def _f6_grids(data):
    def pair(key):
        v = data.get(key)
        if not isinstance(v, list) or len(v) != 2 or any(type(n) is not int for n in v):
            raise ValueError(f"invalid F6 {key}")
        return tuple(v)

    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("expected an F6 version 1 surface")
    origin = pair("origin")
    shape = pair("size")
    top, skip = data.get("top"), data.get("skip")
    if (
        min(shape) < 1
        or not isinstance(top, list)
        or not isinstance(skip, list)
        or len(top) != math.prod(shape)
        or len(skip) != len(top)
        or any(v is not None and (type(v) is not int or not _WORLD_MIN <= v <= _WORLD_MAX) for v in top)
        or any(type(v) is not int or v not in (0, 1) for v in skip)
    ):
        raise ValueError("invalid F6 dimensions, elevations or skip bits")
    return origin, np.array(top, dtype=float).reshape(shape), np.array(skip, dtype=bool).reshape(shape)


def _read_points(path):
    raw = _read_json(path)
    if not isinstance(raw, list) or not raw:
        raise ValueError("points must be a nonempty JSON list of world [x,z] pairs")
    points = []
    for pair in raw:
        if not isinstance(pair, list) or len(pair) != 2 or any(type(v) is not int for v in pair):
            raise ValueError("each tree point must be a pair of integer world coordinates [x,z]")
        points.append(tuple(pair))
    if len(set(points)) != len(points):
        raise ValueError("duplicate tree point")
    return points


def _mask_stamped_wood(fills, origin, top, skip):
    """Mark each intersected F6 column whose highest stamped log stands above its bed."""
    ox, oz = origin
    for fill in fills:
        if base_id(fill["block"]) not in _AXIS_WOOD:
            continue
        x0, _, z0 = fill["from"]
        x1, y1, z1 = fill["to"]
        if not (ox <= x0 <= x1 < ox + top.shape[0] and oz <= z0 <= z1 < oz + top.shape[1]):
            raise ValueError("expected surface must cover every transformed wood column")
        area = np.s_[x0 - ox : x1 - ox + 1, z0 - oz : z1 - oz + 1]
        skip[area] |= (top[area] < y1) | ~np.isfinite(top[area])


def place_trees(
    module_path: Path,
    points_path: Path,
    project: Path,
    *,
    phase: int,
    seed: int = 0,
    surface_path: Path | None = None,
    site_path: Path | None = None,
) -> tuple[dict, Path]:
    """Stamp a tree phase and atomically update the project's matching F6 after all checks."""
    if (surface_path is None) == (site_path is None):
        raise ValueError("tree-place needs exactly one of --surface or --site")
    module_bytes = Path(module_path).read_bytes()
    module = json.loads(module_bytes)
    if not isinstance(module, dict):
        raise TypeError("expected an F7 vegetation module")
    name = _name(module.get("name"))
    points = _read_points(points_path)
    project = Path(project).resolve()
    world = None
    if site_path is not None:
        site = load_site(site_path)
        box = site.box
        field, blocks, levels, surface, _ = site_planting(
            site, (box[0], box[2], box[3], box[5]), measure_slope=False
        )
        for x, z in points:
            i, j = x - box[0], z - box[2]
            if not (0 <= i < field.nx and 0 <= j < field.nz):
                raise ValueError(f"tree point {(x, z)} outside site")
            state = blocks[i, j]
            if not isinstance(state, str) or base_id(state) not in GROWABLE or levels[i, j] > field.h[i, j]:
                raise ValueError(f"tree point {(x, z)} requires a dry, known, growable bed")
        elevations = field.h
        world = site.world
        surface_name = f"{name}.surface.json"
    else:
        surface_path = Path(surface_path)
        surface = _read_json(surface_path)
        elevations = None
        surface_name = (
            surface_path.name if surface_path.name.endswith(".surface.json") else f"{name}.surface.json"
        )
    origin, top, skip = _f6_grids(surface)
    placements = tree_placements(
        points, top if elevations is None else elevations, origin, module, phase=phase, seed=seed
    )
    surface_dest = _destination(project, Path("terrain") / surface_name)
    places_dest = _destination(project, Path("terrain") / f"{name}.placements.json")
    phase_file = f"phases/{phase:02d}-{name}-trees.json"
    phase_dest = _destination(project, phase_file)
    project.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=project) as temp:
        folder = Path(temp)
        mods = folder / "modules"
        mods.mkdir()
        staged_module = mods / f"{name}.json"
        staged_module.write_bytes(module_bytes)
        places_file = folder / "placements.json"
        _write_json(places_file, placements)
        phase_temp = folder / "phase.json"
        stamped = subprocess.run(
            [
                sys.executable,
                _stamp_geometry()["__file__"],
                "--placements",
                str(places_file),
                "--modules",
                str(mods),
                "--phase",
                str(phase),
                "--out",
                str(phase_temp),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if stamped.returncode:
            raise ValueError(f"cannot stamp tree module: {stamped.stderr.strip()}")
        payload = _read_json(phase_temp)
        fills = payload["fills"]
        if (
            not fills
            or payload["blocks"]
            or any(
                base_id(f["block"]) in {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
                for f in fills
            )
        ):
            raise ValueError("tree phase must contain non-air fills")
        if world is not None:
            payload["world"] = world
        _write_json(phase_temp, payload)
        module_dest = _destination(project, Path("modules") / f"{name}.json")
        files = [(staged_module, module_dest), (places_file, places_dest), (phase_temp, phase_dest)]
        replay = all(dest.exists() and dest.read_bytes() == src.read_bytes() for src, dest in files)
        before = surface_dest.read_bytes() if surface_dest.exists() else None
        if before is not None:
            saved = json.loads(before)
            if any(saved.get(k) != surface[k] for k in ("version", "origin", "size", "top")):
                raise ValueError(f"existing expected surface differs: {surface_dest}")
            skip |= _f6_grids(saved)[2]
        if not replay and any(skip[x - origin[0], z - origin[1]] for x, z in points):
            raise ValueError("tree point falls on an existing F6 skip or protected column")
        _mask_stamped_wood(fills, origin, top, skip)
        updated = folder / "surface.json"
        _write_json(updated, {**surface, "skip": skip.astype(int).ravel().tolist()})
        boxes = [(*f["from"], *f["to"]) for f in fills]
        low_x, low_y, low_z, hi_x, hi_y, hi_z = phase_bounds(boxes)
        count = sum(math.prod(b - a + 1 for a, b in zip(box[:3], box[3:])) for box in boxes)
        row = {
            "id": phase,
            "name": f"{name}-trees",
            "file": phase_file,
            "blocks": count,
            "from": [low_x, low_y, low_z],
            "to": [hi_x, hi_y, hi_z],
            "via": "placer",
            "rollback": "backup",
        }
        _publish(files, update=(updated, surface_dest, before))
    return row, surface_dest


def add_tree_parsers(commands):
    """Register the two offline tree commands on the terrain launcher's subparser collection."""
    tree = commands.add_parser("tree", help="generate a custom tree module and three rendered previews")
    tree.add_argument("--preset", required=True, choices=tuple(PRESETS))
    tree.add_argument(
        "--set",
        dest="overrides",
        nargs="+",
        action="extend",
        default=[],
        metavar="KEY=VALUE",
        help="e.g. height=15 lean=[0.3,-0.1] roots=true seed=8",
    )
    tree.add_argument("--name", required=True)
    tree.add_argument("--out", type=Path, required=True)
    place = commands.add_parser("tree-place", help="stamp a tree at surveyed world x/z points")
    place.add_argument("--module", type=Path, required=True)
    place.add_argument("--points", type=Path, required=True, help="JSON list of distinct world [x,z] pairs")
    inputs = place.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--surface", type=Path, help="designed terrain F6 expected surface")
    inputs.add_argument("--site", type=Path, help="F1 existing-ground read")
    place.add_argument("--phase", type=int, required=True)
    place.add_argument("--seed", type=int, default=0, help="placement rotation and mirror seed (default 0)")
    place.add_argument("--project", type=Path, required=True)


def run_tree(args):
    """Dispatch a parsed tree command and print a TOON phase row for placement."""
    if args.command == "tree":
        print(*write_tree(args.preset, args.overrides, args.name, args.out), sep="\n")
    elif args.command == "tree-place":
        row, surface = place_trees(
            args.module,
            args.points,
            args.project,
            phase=args.phase,
            seed=args.seed,
            surface_path=args.surface,
            site_path=args.site,
        )
        print(f"expected surface: {surface}")
        print(*_table("phases", [row]), sep="\n")
    else:
        raise ValueError(f"unknown tree command {args.command!r}")
    return 0
