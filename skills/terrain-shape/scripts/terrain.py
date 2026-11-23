#!/usr/bin/env python3
"""Run the offline terrain toolkit from any working directory."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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


def _ids(args):
    features, biomes, used = load_ids(args.version)
    print(f"ID lists: {used}" + (f" (fallback for {args.version})" if used != args.version else ""))
    missing = []
    for kind, value, known in (("feature", args.features, features), ("biome", args.biomes, biomes)):
        if value is not None:
            found, unknown = check_ids((s.strip() for s in value.split(",")), known)
            print(f"known {kind} IDs: {', '.join(found) or 'none'}")
            if unknown:
                print(f"unknown {kind} IDs: {', '.join(unknown)}")
                missing.extend(unknown)
    return int(bool(missing))


def _plant(args):
    if args.phase < 1:
        raise ValueError("phase number must be positive")
    versions = available_versions()
    if not versions:
        raise ValueError("no bundled game version lists")
    version = args.version or versions[-1]
    known, biomes, used = load_ids(version)
    print(f"ID lists: {used}" + (f" (fallback for {version})" if used != version else ""))
    if args.version is None:
        print("Using latest bundled list; pass --version from mc_status for a specific server.")
    named_biome = args.biome_change if args.biome_change is not None else args.biome_preview
    if named_biome is not None and named_biome not in biomes:
        raise ValueError(f"unknown biome ID {named_biome!r} in the {used} list")
    if args.biome_only and named_biome is None:
        raise ValueError("--biome-only requires --biome-change ID or --biome-preview ID")
    if not args.biome_only and args.mix is None:
        raise ValueError("planting requires --mix")
    slope_density = None
    recipe_dimension = None
    if args.site:
        if args.box is None or args.drain_approved:
            raise ValueError("site planting requires --box; drain receipts apply only to recipes")
        element = _label(args.element or "planting")
        site = load_site(args.site)
        hf, blocks, wet, surface, slope_density = site_planting(
            site, args.box, measure_slope=not args.biome_only
        )
        world, seed = site.world, 0
    else:
        if args.box is not None or args.element is not None:
            raise ValueError("recipe planting uses the recipe's element and box")
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        element = _label(recipe["element"])
        hf, blocks, wet, surface, world = recipe_planting(recipe, args.project, args.drain_approved)
        seed = recipe.get("seed", 0)
        recipe_dimension = recipe.get("dimension")
    dimension = args.dimension
    if dimension is not None:
        dimension = _resource_id(dimension, "dimension")
        if recipe_dimension and recipe_dimension.removeprefix("minecraft:") != dimension.removeprefix(
            "minecraft:"
        ):
            raise ValueError("--dimension must match the recipe dimension")
    elif recipe_dimension not in (None, "overworld", "minecraft:overworld"):
        raise ValueError(
            "non-default recipe dimension requires a deliberate --dimension and an actual F1 world"
        )
    if dimension and not world and dimension != "minecraft:overworld":
        raise ValueError("non-default --dimension needs an actual captured F1 world")
    if dimension:
        print(
            f"World {world or 'server default'}, console dimension {dimension}; "
            f"use --dimension {dimension} only after approval at the executor gate."
        )
    elif world:
        print(
            f"World {world}; confirm it is the console default at the executor gate. "
            "For another dimension, regenerate with --dimension ID."
        )
    origin = tuple(surface["origin"])
    biome_file = None
    if named_biome is not None:
        tops = [y for y in surface["top"] if y is not None]
        if not tops:
            raise ValueError("a biome footprint needs at least one observed surface")
        y_range = (max(-64, min(tops) - 8), min(319, max(tops) + 4))
        commands = biome_commands(named_biome, origin=origin, size=(hf.nx, hf.nz), y_range=y_range)
        box = _bounds([tuple(map(int, cmd.split()[1:7])) for cmd in commands])
        biome_file = {"version": 1, "kind": "biomes", "world": world, "box": list(box), "commands": commands}
        print(
            f"biome {named_biome} in world {world or 'server default'} from {_point(box[:3])} to {_point(box[3:])}; "
            "rollback approximates the original biome per chunk"
        )
        if args.biome_preview is not None:
            return 0

        if dimension and dimension != "minecraft:overworld":
            raise ValueError("the biome rollback probe cannot target a non-default dimension")
    files_to_write, rows = [], []
    if not args.biome_only:
        mix = json.loads(args.mix.read_text(encoding="utf-8"))
        reach = vegetation_reach(mix, known, args.reach)
        features = plan_features(
            hf,
            blocks,
            mix,
            origin=origin,
            seed=args.seed if args.seed is not None else seed,
            known=known,
            water=wet,
            slope_density=slope_density,
        )
        surface_path = args.project / "terrain" / f"{element}.surface.json"
        if surface_path.exists():
            saved = json.loads(surface_path.read_text(encoding="utf-8"))
            if any(saved.get(key) != surface[key] for key in ("version", "origin", "size", "top")):
                raise ValueError(f"existing {surface_path.name} does not match the fitted site or recipe")
            saved = mark_trunks(saved, ())
            surface["skip"] = [int(a or b) for a, b in zip(surface["skip"], saved["skip"])]
        surface = mark_feature_trunks(surface, features, reach)
        feature_file = features_file(features, world=world, reach=reach) if features else None
        phases = [
            ("features", args.phase, feature_file, "backup"),
            ("biome", args.phase + 1, biome_file, "biome"),
        ]
    else:
        phases = [("biome", args.phase, biome_file, "biome")]
    for suffix, phase, payload, rollback in phases:
        name = f"{element}-{suffix}"
        file = f"phases/{phase:02d}-{name}.commands.json"
        path = args.project / file
        if path.exists():
            if payload is None or json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError(
                    f"existing phase file {file} conflicts with this plan; choose a fresh phase number"
                )
        elif payload is not None:
            files_to_write.append((path, payload))
        if payload is None:
            continue
        for other in path.parent.glob(f"{phase:02d}-*.json"):
            if other != path and not other.name.endswith(".probe.json"):
                raise ValueError(f"phase {phase} is occupied by existing file {other.name}")
        box = payload["box"]
        rows.append(
            {
                "id": phase,
                "name": name,
                "file": file,
                "blocks": len(payload["commands"]),
                "from": box[:3],
                "to": box[3:],
                "via": "commands",
                "rollback": rollback,
            }
        )
    for path, data in files_to_write:
        path.parent.mkdir(exist_ok=True, parents=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    if not args.biome_only:
        surface_path.parent.mkdir(exist_ok=True, parents=True)
        _write_json(surface_path, surface)
        print(f"feature backup reach: {reach[0]} sideways, {reach[1]} up, {reach[2]} down")
        counts = Counter(f.id for f in features)
        print(
            f"{len(features)} features across {hf.nx * hf.nz} columns: "
            + (", ".join(f"{fid} {n}" for fid, n in sorted(counts.items())) or "none")
        )
    if dimension:
        print(
            "  notes[1]: "
            + json.dumps(
                f"world {world or 'server default'}; executor gate must approve "
                f"--dimension {dimension} for command execution and forceload"
            )
        )
    print(*_table("phases", rows), sep="\n")
    return 0


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
    ids = commands.add_parser("ids", help="check IDs against a bundled game version")
    ids.add_argument("--version", required=True)
    ids.add_argument("--features", metavar="ID,ID")
    ids.add_argument("--biomes", metavar="ID,ID")
    plant = commands.add_parser("plant", help="plan layered vegetation on fitted or surveyed terrain")
    inputs = plant.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--recipe", type=Path)
    inputs.add_argument("--site", type=Path)
    plant.add_argument("--box", type=int, nargs=4, metavar=("X1", "Z1", "X2", "Z2"))
    plant.add_argument("--project", type=Path, required=True)
    plant.add_argument("--element", help="site planting element (default: planting)")
    plant.add_argument("--phase", type=int, required=True)
    plant.add_argument("--mix", type=Path)
    plant.add_argument(
        "--biome-only",
        action="store_true",
        help="emit or preview only the named biome at --phase, preserving planting files",
    )
    plant.add_argument(
        "--dimension", help="console dimension for an identified F1 world and executor approval"
    )
    plant.add_argument("--version")
    plant.add_argument("--seed", type=int)
    plant.add_argument(
        "--reach",
        type=int,
        nargs="+",
        metavar="BLOCKS",
        help="verified feature reach: SIDE UP [DOWN], defaults to 8 32 2",
    )
    plant.add_argument("--drain-approved", action="append", default=[], metavar="BODY_ID")
    biomes = plant.add_mutually_exclusive_group()
    biomes.add_argument("--biome-preview", metavar="ID", help="show the proposed box without writing files")
    biomes.add_argument("--biome-change", metavar="ID", help="generate only the separately approved biome")
    add_tree_parsers(commands)
    add_apron_parser(commands)
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
        if args.command == "ids":
            return _ids(args)
        if args.command == "plant":
            return _plant(args)
        if args.command in {"tree", "tree-place"}:
            return run_tree(args)
        if args.command == "apron":
            return run_apron(args)
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
from terrain.apron import add_apron_parser, run_apron
from terrain.ashlar_emit import (
    _bounds,
    _label,
    _point,
    _table,
    _write_json,
    emit_ashlar,
    preview_field,
    seam_ground,
)
from terrain.emit import VerifyError
from terrain.ids import available_versions, check_ids, load_ids
from terrain.plant import (
    _resource_id,
    biome_commands,
    features_file,
    mark_feature_trunks,
    mark_trunks,
    plan_features,
    recipe_planting,
    site_planting,
    vegetation_reach,
)
from terrain.site import (
    _AIR,
    base_id,
    find_trees,
    load_heights,
    load_site,
    surfaces,
    unnatural_blocks,
)
from terrain.trees import add_tree_parsers, run_tree

if __name__ == "__main__":
    sys.exit(main())
