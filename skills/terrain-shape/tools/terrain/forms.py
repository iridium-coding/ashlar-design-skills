"""Voxel forms, waterfall sources and the offline gravity check."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from voxel import Palette, VoxelModel

from .live import _WORLD_MAX, _WORLD_MIN, LiveWrite
from .site import _AIR, Box, Cell, Site, base_id, integer_level

_COLORS = (
    "white",
    "orange",
    "magenta",
    "light_blue",
    "yellow",
    "lime",
    "pink",
    "gray",
    "light_gray",
    "cyan",
    "purple",
    "blue",
    "brown",
    "green",
    "red",
    "black",
)
GRAVITY: frozenset[str] = frozenset(
    f"minecraft:{name}"
    for name in (
        "sand",
        "red_sand",
        "gravel",
        "suspicious_sand",
        "suspicious_gravel",
        "anvil",
        "chipped_anvil",
        "damaged_anvil",
        "dragon_egg",
        *(f"{color}_concrete_powder" for color in _COLORS),
    )
)
# Paper 26.3 FallingBlock.isFree uses air, the fire tag and the block state's
# liquid and replaceable properties. The latter match the bundled replaceable
# tag in this version. A fluid state on a waterlogged block does not count.
_FALL_THROUGH = _AIR | frozenset(
    f"minecraft:{name}"
    for name in (
        "water",
        "lava",
        "short_grass",
        "fern",
        "dead_bush",
        "bush",
        "red_shrub",
        "short_dry_grass",
        "tall_dry_grass",
        "seagrass",
        "tall_seagrass",
        "fire",
        "soul_fire",
        "snow",
        "vine",
        "glow_lichen",
        "resin_clump",
        "light",
        "tall_grass",
        "large_fern",
        "structure_void",
        "bubble_column",
        "warped_roots",
        "nether_sprouts",
        "crimson_roots",
        "leaf_litter",
        "hanging_roots",
    )
)
_WORLD_BOX = (-30_000_000, _WORLD_MIN, -30_000_000, 29_999_999, _WORLD_MAX, 29_999_999)


@dataclass
class Form:
    name: str
    model: VoxelModel
    origin: Cell
    mode: str


def _position(value, where: str) -> Cell:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{where} must be three integer coordinates")
    x, y, z = value
    return integer_level(x, where), integer_level(y, where), integer_level(z, where)


def _inside(pos: Cell, box: Box) -> bool:
    return all(lo <= value <= hi for lo, value, hi in zip(box[:3], pos, box[3:]))


def _bounds(origin: Cell, codes: np.ndarray, box: Box, where: str) -> None:
    # Large zero margins may straddle a boundary. Validate only occupied cells.
    for axis, (start, size, lo, hi) in enumerate(
        zip(origin, codes.shape, box[:3], box[3:])
    ):
        if lo <= start and start + size - 1 <= hi:
            continue
        other_axes = tuple(i for i in range(3) if i != axis)
        occupied = np.flatnonzero(codes.any(axis=other_axes))
        if occupied.size and (
            start + int(occupied[0]) < lo or start + int(occupied[-1]) > hi
        ):
            raise ValueError(f"{where}: occupied cells outside {box}")


def _asset(project: Path, entry: dict, key: str) -> Path:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"form {key} must be a project-relative path")
    path = Path(value)
    resolved = (project / path).resolve()
    if path.is_absolute() or not resolved.is_relative_to(project):
        raise ValueError(f"form {key} must stay inside the project directory")
    return resolved


def _check_mode(mode: str) -> None:
    if mode not in ("carve", "build"):
        raise ValueError("form mode must be 'carve' or 'build'")


def _load_palette(path: Path) -> Palette:
    try:
        palette = Palette.from_json(str(path))
    except AttributeError as exc:
        raise ValueError("form palette JSON must be an object") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid form palette: {exc}") from exc
    try:
        air = palette.block_id(0)
    except KeyError:
        air = None
    if air != "minecraft:air":
        raise ValueError("form palette code 0 must be minecraft:air")
    for code in palette.codes():
        if not 1 <= code <= 255:
            raise ValueError(f"form palette code {code} is outside 0..255")
        state = palette.block_id(code)
        if not isinstance(state, str) or not state.startswith("minecraft:"):
            raise ValueError(f"form palette code {code} needs a minecraft: block state")
    return palette


def load_form(entry: dict, project_dir: Path) -> Form:
    """Read the form's standard voxel grid and matching palette."""
    if not isinstance(entry, dict) or not entry:
        raise ValueError("form must be a nonempty object")
    name, mode = entry.get("name"), entry.get("mode")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("form name must be a nonempty string")
    _check_mode(mode)
    origin = _position(entry.get("origin"), f"form {name!r} origin")
    project = project_dir.resolve()
    model_path, palette_path = (
        _asset(project, entry, "model"),
        _asset(project, entry, "palette"),
    )
    try:
        palette = _load_palette(palette_path)
        # Read the original codes before the voxel loader can cast them to uint8.
        with model_path.open("rb") as stream:
            grid = np.load(stream, allow_pickle=False)
        if not isinstance(grid, np.ndarray) or grid.dtype != np.uint8:
            raise ValueError("form grid must contain uint8 codes")
        if grid.ndim != 3 or not all(grid.shape):
            raise ValueError("form grid must have a nonempty 3-D shape")
        missing = set(np.unique(grid)) - {0, *palette.codes()}
        if missing:
            raise ValueError(f"form palette has no entry for code {min(missing)}")
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load assets for form {name!r}: {exc}") from exc
    _bounds(origin, grid, _WORLD_BOX, f"form {name!r} world bounds")
    model = VoxelModel(*grid.shape, palette=palette)
    model.g = grid
    return Form(name, model, origin, mode)


def form_write(form: Form) -> LiveWrite:
    """Translate model occupancy into a carve or build write at the form origin."""
    _check_mode(form.mode)
    origin = _position(form.origin, f"form {form.name!r} origin")
    grid = form.model.g
    _bounds(origin, grid, _WORLD_BOX, f"form {form.name!r} world bounds")
    if form.mode == "carve":
        return LiveWrite(
            origin, (grid != 0).astype(np.uint8), ["skip", "minecraft:air"]
        )

    palette = ["skip"] * (int(grid.max(initial=0)) + 1)
    for code in np.unique(grid):
        if not code:
            continue
        try:
            state = form.model.pal.block_id(int(code))
        except KeyError:
            raise ValueError(
                f"form {form.name!r} has no palette entry for code {code}"
            ) from None
        if not isinstance(state, str) or not state.startswith("minecraft:"):
            raise ValueError(
                f"form {form.name!r} palette code {code} needs a minecraft: block state"
            )
        palette[code] = state
    return LiveWrite(origin, grid.copy(), palette)


def flow_build(falls: list[dict], *, site: Site | None = None) -> dict:
    """Return a phase payload containing only the specified waterfall source blocks."""
    blocks = []
    for i, fall in enumerate(falls):
        where = f"falls[{i}].at"
        pos = _position(fall.get("at") if isinstance(fall, dict) else None, where)
        if not _inside(pos, _WORLD_BOX):
            raise ValueError(f"{where} {pos} is outside world bounds")
        if site is not None and not _inside(pos, site.box):
            raise ValueError(f"{where} {pos} is outside the site read")
        blocks.append({"pos": list(pos), "block": "minecraft:water"})
    return {"blocks": blocks, "liquids": "flow"}


def gravity_violations(
    writes: list[LiveWrite], site: Site
) -> list[tuple[int, int, int, str]]:
    """Check the final state, including original blocks left above a changed support."""
    x1, y1, z1, x2, y2, z2 = site.box
    bottom = (x1, y1, z1)
    shape = (x2 - x1 + 1, y2 - y1 + 1, z2 - z1 + 1)
    final = np.empty(shape, dtype=np.uint16)
    bottom_written = np.zeros((shape[0], shape[2]), dtype=bool)
    # Keep the exact block state for diagnostics. IDs 0/1 are support/open.
    states = ["", ""]

    @cache
    def classify(state: str) -> int:
        block = base_id(state)
        if block in GRAVITY:
            states.append(state)
            return len(states) - 1
        return int(block in _FALL_THROUGH)

    for (x, z), runs in site.columns.items():
        for lo, hi, state in runs:
            final[x - x1, lo - y1 : hi - y1 + 1, z - z1] = classify(state)
    for write in writes:
        _bounds(write.origin, write.codes, site.box, "write outside the site read")
        offset = tuple(start - lo for start, lo in zip(write.origin, bottom))
        start = tuple(max(0, d) for d in offset)
        stop = tuple(
            min(limit, d + size)
            for d, size, limit in zip(offset, write.codes.shape, shape)
        )
        if any(a >= b for a, b in zip(start, stop)):
            continue
        target = tuple(slice(a, b) for a, b in zip(start, stop))
        source = tuple(slice(a - d, b - d) for a, b, d in zip(start, stop, offset))
        codes = write.codes[source]
        classes = np.array(
            [classify(state) for state in write.palette], dtype=final.dtype
        )
        # Apply the palette a plane at a time to bound the temporary arrays.
        for dest, plane in zip(final[target], codes):
            np.copyto(dest, classes[plane], where=plane != 0)
        if start[1] == 0:
            bottom_written[target[0], target[2]] |= codes[:, 0, :] != 0

    gravity = final >= 2
    unchecked = gravity[:, 0, :] & bottom_written
    if y1 > _WORLD_MIN and unchecked.any():
        i, k = (int(v) for v in np.argwhere(unchecked)[0])
        raise ValueError(f"read lower to check gravity below {(x1 + i, y1, z1 + k)}")
    gravity[:, 1:, :] &= final[:, :-1, :] == 1
    if y1 != _WORLD_MIN:
        gravity[:, 0, :] = False
    return [
        (x + x1, y + y1, z + z1, states[final[x, y, z]])
        for x, y, z in np.argwhere(gravity).tolist()
    ]
