#!/usr/bin/env python3
"""Run the offline terrain toolkit from any working directory."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.util import find_spec
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SKILL / "tools"), str(SKILL.parent / "design-monument" / "tools")]


def _survey(args):
    site = load_site(args.site)
    box = args.box
    if any(not site.box[i] <= box[i] <= box[i + 3] <= site.box[i + 3] for i in range(3)):
        raise ValueError("survey box must be inside the site read")
    counts = unnatural_blocks(site, box)
    crop = np.s_[
        box[0] - site.box[0] : box[3] - site.box[0] + 1, box[2] - site.box[2] : box[5] - site.box[2] + 1
    ]
    surf = surfaces(site)
    for field in ("ground", "water", "top"):
        values = getattr(surf, field)[crop]
        valid = values[np.isfinite(values)]
        print(f"{field}: {int(valid.min())}..{int(valid.max())}" if valid.size else f"{field}: none")
    trees = sum(
        any(all(box[i] <= c[i] <= box[i + 3] for i in range(3)) for c in tree.cells)
        for tree in find_trees(site)
    )
    print(f"trees: {trees}")
    print("non-natural blocks:", json.dumps(counts, sort_keys=True))
    return int(bool(counts))


def _compare(args):
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    measured = load_heights(args.heights)
    if expected.get("version") != 1 or not 0 <= args.min_ratio <= 1 or args.tolerance < 0:
        raise ValueError("compare requires F6, nonnegative tolerance, and min-ratio between 0 and 1")
    nx, nz = expected["size"]
    if min(nx, nz) < 1 or len(expected["skip"]) != nx * nz or len(expected["top"]) != nx * nz:
        raise ValueError("invalid expected surface dimensions")
    skip = np.asarray(expected["skip"]).reshape(nx, nz)
    if not np.isin(skip, [0, 1]).all():
        raise ValueError("invalid skip mask")
    top = np.asarray(expected["top"], dtype=float).reshape(nx, nz)
    x, z = (a - b for a, b in zip(expected["origin"], measured["origin"]))
    actual = measured["surface"]
    if x < 0 or z < 0 or x + nx > actual.shape[0] or z + nz > actual.shape[1]:
        raise ValueError("heights must cover the entire expected surface")
    actual = actual[x : x + nx, z : z + nz]
    matches = (np.abs(top - actual) <= args.tolerance) | (np.isnan(top) & np.isnan(actual))
    tested = int((skip == 0).sum())
    if not tested:
        raise ValueError("no unskipped columns to compare")
    passed = int(np.count_nonzero(matches & (skip == 0)))
    print(f"{passed}/{tested} columns match ({passed / tested:.2%})")
    return int(passed / tested < args.min_ratio)


def _seam(args):
    if (args.site is None) == (args.heights is None):
        raise ValueError("seam needs one post-build --site F1 or one positional F2 heights file")
    if args.site is not None:
        site = load_site(args.site)
        if any(base_id(runs[-1][2]) not in _AIR for runs in site.columns.values()):
            raise ValueError("read higher: post-build seam site must end in air")
        measured = None
    else:
        measured = load_heights(args.heights)
        grid = measured["ground"]
        ox, oz = measured["origin"]
    steps = {"x": (1, 0), "-x": (-1, 0), "z": (0, 1), "-z": (0, -1)}
    dx, dz = steps[args.outward]
    x, z = args.start
    ex, ez = args.end
    if args.max_step < 0 or (dx and x != ex) or (dz and z != ez):
        raise ValueError("seam must run perpendicular to outward, with a nonnegative max-step")

    def height(x, z):
        if measured is None:
            return seam_ground(site, x, z)
        if not (ox <= x < ox + grid.shape[0] and oz <= z < oz + grid.shape[1]):
            raise ValueError(f"seam point {(x, z)} outside heights")
        value = grid[x - ox, z - oz]
        if not np.isfinite(value):
            raise ValueError(f"missing seam height at {(x, z)}")
        top = measured["top"][x - ox, z - oz]
        surface = measured["surface"][x - ox, z - oz]
        if not (np.isfinite(top) and np.isfinite(surface)) or top != surface or surface < value:
            raise ValueError(
                f"ambiguous seam ground at {(x, z)}; use --site POST_BUILD_F1 to resolve vegetation"
            )
        return value

    worst = max(
        abs(height(i, j) - height(i + dx, j + dz))
        for i in range(min(x, ex), max(x, ex) + 1)
        for j in range(min(z, ez), max(z, ez) + 1)
    )
    evidence = (
        "post-build site"
        if args.site
        else "F2 ground screen; use --site POST_BUILD_F1 where trunks may be present"
    )
    print(f"largest seam step {worst:g} (maximum {args.max_step}; {evidence})")
    return int(worst > args.max_step)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    survey = commands.add_parser("survey")
    survey.add_argument("--site", type=Path, required=True)
    survey.add_argument("--box", nargs=6, type=int, required=True)
    for command in ("field", "emit"):
        p = commands.add_parser(command)
        p.add_argument("recipe", type=Path)
        p.add_argument("--project", type=Path, required=True)
        if command == "emit":
            p.add_argument("--first-phase", type=int, required=True)
            p.add_argument("--standalone", action="store_true")
            p.add_argument("--drain-approved", action="append", default=[], metavar="BODY_ID")
    compare = commands.add_parser("compare")
    compare.add_argument("expected", type=Path)
    compare.add_argument("heights", type=Path)
    compare.add_argument("--tolerance", type=int, default=0)
    compare.add_argument("--min-ratio", type=float, default=0.98)
    seam = commands.add_parser("seam")
    seam.add_argument("heights", type=Path, nargs="?", help="F2 ground screen for unobstructed columns")
    seam.add_argument("--site", type=Path, help="post-build F1 site read covering both sides of the seam")
    seam.add_argument("--from", dest="start", nargs=2, type=int, required=True)
    seam.add_argument("--to", dest="end", nargs=2, type=int, required=True)
    seam.add_argument("--outward", choices=("x", "-x", "z", "-z"), required=True)
    seam.add_argument("--max-step", type=int, default=1)
    # argparse otherwise mistakes the documented '--outward -x' for another flag.
    tokens = list(sys.argv[1:] if argv is None else argv)
    for i in range(len(tokens) - 1):
        if tokens[i] == "--outward" and tokens[i + 1] in {"-x", "-z"}:
            tokens[i : i + 2] = ["--outward=" + tokens[i + 1]]
            break
    args = parser.parse_args(tokens)
    try:
        if args.command == "survey":
            return _survey(args)
        if args.command == "compare":
            return _compare(args)
        if args.command == "seam":
            return _seam(args)
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        if args.command == "field":
            result = preview_field(recipe, args.project)
        else:
            result = emit_ashlar(
                recipe,
                args.project,
                first_phase=args.first_phase,
                standalone=args.standalone,
                drain_approved=args.drain_approved,
            )
        print(result.report)
        print(*result.notes, sep="\n")
        return 0
    except (ValueError, VerifyError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


DEPENDENCIES = ("numpy", "scipy", "PIL", "opensimplex")
if any(find_spec(package) is None for package in DEPENDENCIES):
    sys.exit(
        "Run: uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python "
        + str(Path(__file__).resolve())
        + " <command>"
    )

import numpy as np
from terrain.ashlar_emit import emit_ashlar, preview_field, seam_ground
from terrain.emit import VerifyError
from terrain.site import (
    _AIR,
    base_id,
    find_trees,
    load_heights,
    load_site,
    surfaces,
    unnatural_blocks,
)

if __name__ == "__main__":
    sys.exit(main())
