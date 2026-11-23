"""Design a ground transition around host footprints, or erode an entire site."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .ashlar_emit import _FULL, emit_field, seam_ground
from .erosion import hydraulic, thermal
from .field import HeightField, smoothstep
from .materialize import Layer, MaterialSpec
from .render import render_hillshade
from .site import (
    ATTACHED,
    LEAVES,
    PLANTS,
    TRUNK,
    Site,
    base_id,
    hold_shores,
    integer_level,
    liquid_levels,
    load_site,
    surface_y,
    surfaces,
)

Rect = tuple[int, int, int, int]


@dataclass
class ApronResult:
    field: HeightField
    protect: np.ndarray
    delta: dict
    needs_ok: bool
    held_columns: int = 0
    host_weight: np.ndarray | None = None


def _rect(bounds, name):
    if len(bounds) != 4:
        raise ValueError(f"{name} needs x1 z1 x2 z2")
    x1, z1, x2, z2 = (integer_level(v, name) for v in bounds)
    if x1 > x2 or z1 > z2:
        raise ValueError(f"{name} corners are reversed")
    return x1, z1, x2, z2


def _crop(inner, outer):
    x1, z1, x2, z2 = inner
    ox, oz, ex, ez = outer
    if not (ox <= x1 <= x2 <= ex and oz <= z1 <= z2 <= ez):
        raise ValueError(f"{inner} must be inside {outer}")
    return np.s_[x1 - ox : x2 - ox + 1, z1 - oz : z2 - oz + 1]


# Each slice pair aligns a column with one of its four neighbours.
_NEIGHBOURS = (
    (np.s_[1:, :], np.s_[:-1, :]),
    (np.s_[:-1, :], np.s_[1:, :]),
    (np.s_[:, 1:], np.s_[:, :-1]),
    (np.s_[:, :-1], np.s_[:, 1:]),
)


def _shoulder(ground, anchors, padded, fixed, width):
    """Transition from the nearest footprint, with a walkable first step."""
    lo = np.full_like(ground, -np.inf)
    hi = np.full_like(ground, np.inf)
    step = 0
    for outside, inside in _NEIGHBOURS:
        edge = ~fixed[outside] & fixed[inside]
        diff = abs(ground[outside] - anchors[inside])
        step = max(step, diff.max(where=edge, initial=0))
        # Planned aprons meet their pad exactly. Existing uneven ground may
        # step by one at a seam shared with more than one protected column.
        allowance = (~padded[inside]).astype(int)
        np.maximum(lo[outside], anchors[inside] - allowance, where=edge, out=lo[outside])
        np.minimum(hi[outside], anchors[inside] + allowance, where=edge, out=hi[outside])
    if np.any(lo > hi):
        raise ValueError("adjacent footprints require incompatible heights on a shared seam")
    if width is None:
        width = min(24, max(8, 2 * step))
    distance, nearest = ndimage.distance_transform_edt(~fixed, return_indices=True)
    weight = 1 - smoothstep(0, width, distance)
    start = ground + weight * (anchors[tuple(nearest)] - ground)
    return start, weight, lo, hi, 1 - smoothstep(1, max(2, width), distance)


def design_apron(
    site: Site,
    box2d: Rect,
    *,
    protect: Sequence[Rect] = (),
    pads: dict[Rect, int] | None = None,
    apron: int | None = None,
    seed: int = 0,
) -> ApronResult:
    """Return the combined host design and the literal no-write mask.

    Where a planned pad intersects protection, its design height belongs to
    the host. Delta statistics count actual rounded terrain-phase movement,
    averaged across the full box (protected columns contribute zero).
    """
    box = _rect(box2d, "box")
    x1, _, z1, x2, _, z2 = site.box
    crop = _crop(box, (x1, z1, x2, z2))
    ground = surfaces(site).ground[crop]
    if not np.isfinite(ground).all():
        raise ValueError("read lower to find ground throughout the apron")
    if min(ground.shape) < 3:
        raise ValueError("an apron needs at least 3 columns on both axes")
    if apron is not None:
        apron = integer_level(apron, "apron")
        if apron < 1:
            raise ValueError("apron width must be positive")
    protected = np.zeros(ground.shape, bool)
    for rect in protect:
        protected[_crop(_rect(rect, "protect"), box)] = True
    padded = np.zeros(ground.shape, bool)
    anchors = ground.copy()
    for rect, level in (pads or {}).items():
        region = _crop(_rect(rect, "pad"), box)
        level = integer_level(level, "pad height")
        if not -64 <= level <= 319:
            raise ValueError("pad height outside world limits")
        if np.any(padded[region] & (anchors[region] != level)):
            raise ValueError("overlapping pads have different heights")
        anchors[region] = level
        padded[region] = True
    fixed = protected | padded
    ring = np.ones(ground.shape, bool)
    ring[1:-1, 1:-1] = False
    if (fixed & ring).any():
        raise ValueError("footprints on the outer ring need a larger terrain box")

    has_footprint = bool(fixed.any())
    if has_footprint:
        start, weight, lo, hi, host_weight = _shoulder(ground, anchors, padded, fixed, apron)
    else:
        start, weight, host_weight = ground, 1.0, None
    # Run both erosion processes on the same terrain, retaining the disturbance
    # only within the taper. Neither the host nor the old ring can drift.
    eroded = thermal(start, iterations=12)
    eroded = hydraulic(eroded, droplets=max(1, ground.size // 8), seed=seed, max_steps=16)
    h = start + weight * (eroded - start)
    if has_footprint:
        h = np.clip(h, lo, hi)
        h[fixed] = anchors[fixed]
    h[ring] = ground[ring]
    held = hold_shores(h, site, origin=box[:2], skip=fixed)
    rounded = surface_y(held)
    if has_footprint and ((rounded < lo) | (rounded > hi)).any():
        raise ValueError("a shore or fixed outer ring conflicts with the footprint seam")
    if host_weight is not None:
        host_weight[ring] = 0
    field = HeightField(*ground.shape, sea_level=float(np.floor(held.min()) - 8))
    field.h = held
    change = np.where(protected, 0, abs(rounded - ground))
    delta = {
        "max": float(change.max()),
        "mean": float(change.mean()),
        "moved": int(np.count_nonzero(change)),
    }
    return ApronResult(
        field,
        protected,
        delta,
        delta["max"] > 6,
        int(np.count_nonzero(rounded != surface_y(h))),
        host_weight,
    )


@dataclass(frozen=True)
class Seam:
    """A line on the apron with a direction pointing into the untouched land."""

    start: tuple[int, int]
    end: tuple[int, int]
    outward: str


_DIRECTIONS = {"x": (1, 0), "-x": (-1, 0), "z": (0, 1), "-z": (0, -1)}


def _boundary_paths(mask, ox, oz):
    """Runs of exposed faces only, including concave corners of a rectangle union."""
    for label, (dx, dz) in _DIRECTIONS.items():
        shifted = np.roll(mask, (-dx, -dz), axis=(0, 1))
        lines = ~mask & shifted
        # No protected columns occur on the ring, so roll cannot wrap an edge.
        if dz:
            lines = lines.T
        for i in np.flatnonzero(lines.any(axis=1)):
            toggles = np.flatnonzero(np.diff(lines[i], prepend=False, append=False))
            for a, stop in toggles.reshape(-1, 2):
                b = stop - 1
                if dx:
                    yield Seam((ox + int(i), oz + int(a)), (ox + int(i), oz + int(b)), label)
                else:
                    yield Seam((ox + int(a), oz + int(i)), (ox + int(b), oz + int(i)), label)


def apron_seams(result: ApronResult, site: Site, box2d: Rect, *, after_host=False) -> list[Seam]:
    """Verify projected bed-to-bed steps, returning the four box edges then host edges.

    The F1 read must include a one-column margin on every side. In a combined
    host plan, after_host=True credits its future pad heights on protected
    columns. A standalone terrain phase can claim only measured protected beds.
    """
    x, z, ex, ez = _rect(box2d, "box")
    if result.field.h.shape != (ex - x + 1, ez - z + 1):
        raise ValueError("box does not match the designed field")
    paths = [
        Seam((x, z), (x, ez), "-x"),
        Seam((ex, z), (ex, ez), "x"),
        Seam((x, z), (ex, z), "-z"),
        Seam((x, ez), (ex, ez), "z"),
    ]
    paths.extend(_boundary_paths(result.protect, x, z))
    rounded = surface_y(result.field.h)
    original = surfaces(site).ground
    for path in paths:
        dx, dz = _DIRECTIONS[path.outward]
        for i in range(path.start[0], path.end[0] + 1):
            for j in range(path.start[1], path.end[1] + 1):
                px, pz = i + dx, j + dz
                if x <= px <= ex and z <= pz <= ez:
                    host = rounded[px - x, pz - z]
                    observed = original[px - site.box[0], pz - site.box[2]]
                    virtual = after_host and host != observed
                else:
                    virtual = False
                far = host if virtual else seam_ground(site, px, pz)
                near = rounded[i - x, j - z]
                if abs(far - near) > 1:
                    raise ValueError(
                        f"projected seam at {(i, j)} toward {path.outward} steps from "
                        f"{near:g} to {far:g}; maximum is 1"
                    )
    return paths


# Ground surfaces appropriate for a natural transition, independent of the
# wider 'occurs in nature' set (which includes fluids, plants, and cave features).
_SURFACE = frozenset(
    "minecraft:" + s
    for s in [
        "grass_block",
        "dirt",
        "coarse_dirt",
        "podzol",
        "mycelium",
        "rooted_dirt",
        "mud",
        "clay",
        "moss_block",
        "pale_moss_block",
        "sand",
        "red_sand",
        "gravel",
        "stone",
        "granite",
        "diorite",
        "andesite",
        "deepslate",
        "tuff",
        "calcite",
        "dripstone_block",
        "sandstone",
        "red_sandstone",
        "basalt",
        "smooth_basalt",
        "blackstone",
        "netherrack",
        "soul_sand",
        "soul_soil",
        "crimson_nylium",
        "warped_nylium",
        "end_stone",
        "snow_block",
        "ice",
        "packed_ice",
        "blue_ice",
        "terracotta",
        "white_terracotta",
        "orange_terracotta",
        "yellow_terracotta",
        "brown_terracotta",
        "red_terracotta",
        "light_gray_terracotta",
    ]
)
_STATS = re.compile(r"^\s*(\d+)\s+\d+(?:\.\d+)?%\s+(minecraft:[a-z0-9_]+(?:\[[^\]]+\])?)\s*$")


def surrounding_palette(stats_text: str, *, top: int = 4) -> dict[str, float]:
    """Normalize counts for the most common natural terrain in an Ashlar stats read."""
    top = integer_level(top, "top")
    if top < 1:
        raise ValueError("top must be positive")
    counts = Counter()
    for line in stats_text.splitlines():
        match = _STATS.fullmatch(line)
        if match:
            count, state = match.groups()
            block = base_id(state)
            if block in _SURFACE and int(count) > 0:
                counts[block] += int(count)
    selected = counts.most_common(top)
    if not selected:
        raise ValueError("stats contain no natural surface terrain")
    total = sum(n for _, n in selected)
    return {block: n / total for block, n in selected}


_HOST_SURFACES = _FULL - TRUNK - LEAVES - PLANTS - ATTACHED


def apron_material(result, site, box, surrounding=None, host=None, *, seed=0):
    """Dither host ground into the sampled surface, leaving wet areas and cliffs to their own materials."""
    spec = MaterialSpec.natural(result.field, surface=surrounding)
    spec.seed = seed
    if host is None:
        return spec
    if result.host_weight is None:
        raise ValueError("a host palette needs a grading footprint")
    if not isinstance(host, dict) or not host:
        raise ValueError("host palette must be a JSON object of block IDs and positive weights")
    for block, weight in host.items():
        if (
            block not in _HOST_SURFACES
            or not isinstance(weight, (float, int))
            or isinstance(weight, bool)
            or not math.isfinite(weight)
            or weight <= 0
        ):
            raise ValueError(
                f"host palette needs confirmed solid blocks and positive finite weights: {block}"
            )
    if not math.isfinite(sum(host.values())):
        raise ValueError("host palette weights must have a finite sum")
    surf = surfaces(site)
    wet_top = liquid_levels(site, surf=surf).top
    x1, _, z1, x2, _, z2 = site.box
    # Keep the site's surface mix at retained liquids and the immediate shore.
    shores = ndimage.binary_dilation(np.isfinite(wet_top))[_crop(box, (x1, z1, x2, z2))]
    # Sample the transition independently of the random draw for each palette.
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])
    host_cells = rng.random(result.field.h.shape) < result.host_weight
    spec.layers.append(Layer(mask=host_cells & ~shores, palette=host, subsurface=spec.subsurface))
    return spec


class _FootprintAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        footprints = list(getattr(namespace, self.dest, ()) or ())
        if option_string == "--protect":
            footprints.append((tuple(values), None))
        else:
            if not footprints or footprints[-1][1] is not None:
                raise argparse.ArgumentError(self, "each --pad needs its own preceding --protect")
            footprints[-1] = (footprints[-1][0], values)
        setattr(namespace, self.dest, footprints)


def add_apron_parser(commands):
    p = commands.add_parser("apron", help="grade around protected footprints or naturalise captured land")
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--box", required=True, type=int, nargs=4, metavar=("X1", "Z1", "X2", "Z2"))
    p.add_argument(
        "--protect",
        action=_FootprintAction,
        dest="footprints",
        type=int,
        nargs=4,
        metavar=("X1", "Z1", "X2", "Z2"),
        help="repeat for each literal no-write footprint",
    )
    p.add_argument(
        "--pad",
        action=_FootprintAction,
        dest="footprints",
        type=int,
        metavar="Y",
        help="planned host grade for the preceding protected footprint",
    )
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--element", required=True)
    p.add_argument("--first-phase", required=True, type=int)
    p.add_argument("--palette", type=Path, help="surrounding surface frequencies from Ashlar stats")
    p.add_argument(
        "--host-palette", metavar="JSON", help="inline JSON object of solid ground block weights"
    )
    p.add_argument("--apron", type=int, metavar="WIDTH", help="override the measured apron width")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--preview", action="store_true", help="write approval views without phase files")
    p.add_argument("--standalone", action="store_true")


def _profile(before, after, paths, box, output):
    """Plot both physical profiles on one fixed scale crossing the first host seam."""
    x, z, _, _ = box
    if len(paths) > 4:
        seam = paths[4]
        axis = 0 if "x" in seam.outward else 1
        other = 1 - axis
        position = (seam.start[other] + seam.end[other]) // 2 - (x, z)[other]
        mark = seam.start[axis] - (x, z)[axis]
    else:
        # Without a host, cross the column with the largest actual change.
        axis = 0
        mark, position = np.unravel_index(np.argmax(abs(after - before)), after.shape)
    old, new = [np.take(v, position, axis=1 - axis) for v in (before, after)]
    low, high = min(old.min(), new.min()), max(old.max(), new.max())
    img = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(img)

    def points(line):
        return [
            (34 + 580 * i / (len(line) - 1), 200 - 155 * (v - low) / max(1, high - low))
            for i, v in enumerate(line)
        ]

    guide = points(old)[mark][0]
    draw.line((guide, 39, guide, 204), fill="#cbd5e1", width=2)
    draw.line(points(old), fill="#8c4922", width=4)
    draw.line(points(new), fill="#197368", width=2)
    draw.text(
        (12, 9),
        f"{'X' if axis == 0 else 'Z'} profile at {'Z' if axis == 0 else 'X'} = {int(position) + (z if axis == 0 else x)}",
        fill="black",
    )
    draw.text(
        (12, 218), f"Before (brown)   Apron phase (green)   Height range {low:g} to {high:g}", fill="black"
    )
    img.save(output)


def run_apron(args):
    site = load_site(args.site)
    box = tuple(args.box)
    footprints = args.footprints or ()
    protect = [rect for rect, _ in footprints]
    pads = {}
    for rect, level in footprints:
        if level is not None:
            if rect in pads and pads[rect] != level:
                raise ValueError("duplicate pad footprint has different levels")
            pads[rect] = level
    result = design_apron(site, box, protect=protect, pads=pads, seed=args.seed, apron=args.apron)
    surrounding = surrounding_palette(args.palette.read_text(encoding="utf-8")) if args.palette else None
    host = json.loads(args.host_palette) if args.host_palette is not None else None
    if args.host_palette is not None and not isinstance(host, dict):
        raise ValueError("host palette must be a JSON object")
    spec = apron_material(result, site, box, surrounding, host, seed=args.seed)
    x1, _, z1, x2, _, z2 = site.box
    ground = surfaces(site).ground[_crop(box, (x1, z1, x2, z2))]
    before = HeightField(*ground.shape, sea_level=result.field.sea_level)
    before.h = ground
    actual = HeightField(*ground.shape, sea_level=result.field.sea_level)
    actual.h = np.where(result.protect, ground, result.field.h)
    virtual = result.protect & (surface_y(result.field.h) != ground)
    if args.standalone and virtual.any():
        raise ValueError("a protected planned pad needs host grading; use a host plan or omit --pad")
    seams = apron_seams(result, site, box, after_host=not args.standalone)

    def point(p):
        return (p[0], round(actual.h[p[0] - box[0], p[1] - box[1]]), p[1])

    seam_rows = [
        {"from": point(seam.start), "to": point(seam.end), "max_step": 1, "outward": seam.outward}
        for seam in seams
    ]
    notes = [f"apron delta: {json.dumps(result.delta)}; needs_ok={str(result.needs_ok).lower()}"]
    if virtual.any():
        notes.append(
            f"host owns grading of {int(virtual.sum())} protected pad columns; check these seams after the host establishes its pad heights"
        )
    recipe = {
        "skill": "terrain-integrate",
        "element": args.element,
        "origin": [box[0], 0, box[1]],
        "nx": actual.nx,
        "nz": actual.nz,
        "apron": {
            "box": list(box),
            "site": os.path.relpath(args.site.resolve(), args.project.resolve()),
            "protect": [list(rect) for rect in protect],
            "pads": [{"box": list(r), "level": y} for r, y in pads.items()],
            "width": args.apron,
            "seed": args.seed,
            "surrounding_palette": surrounding,
            "host_palette": host,
        },
    }
    emitted = emit_field(
        actual,
        spec,
        site,
        args.project,
        element=args.element,
        first_phase=args.first_phase,
        recipe=recipe,
        water=None,
        protect=result.protect,
        standalone=args.standalone,
        seam_rows=seam_rows,
        extra_notes=tuple(notes),
        held_columns=result.held_columns,
        preview=args.preview,
        require_relief=False,
    )
    folder = emitted.surface_file.parent
    prefix = folder / args.element
    render_hillshade(before, str(prefix) + "_before.png")
    # The comparison and the profile depict actual rounded apron writes.
    actual.h = surface_y(actual.h)
    render_hillshade(actual, str(prefix) + "_after.png")
    _profile(before.h, actual.h, seams, box, str(prefix) + "_seam-profile.png")
    print(emitted.report)
    print(*emitted.notes, sep="\n")
    print(
        f"Before, after and seam profile: {prefix}_before.png, {prefix}_after.png, {prefix}_seam-profile.png"
    )
    return 0
