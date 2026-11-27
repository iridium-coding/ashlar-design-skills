"""The ``terrain.py route`` command: plan a transit line's route, write its files and previews."""
from __future__ import annotations

import json
from itertools import groupby
from pathlib import Path

from .route import Route, load_grid, plan_route, write_route
from .transit_design import KINDS, LineDesign, load_line
from .transit_preview import cross_sections, profile_view, route_map

TRANSIT_COMMANDS = {"route"}


def _runs(route: Route, kind: str) -> list[list[float]]:
    out, i = [], 0
    for k, grp in groupby(route.kinds):
        n = len(list(grp))
        if k == kind:
            depth = []
            for j in range(i, i + n):
                g = route.ground[j]
                depth.append(0.0 if g is None else route.levels[j] - (g + 1))
            worst = max(depth) if kind == "bridge" else -min(depth)
            out.append([i, i + n - 1, max(worst, 0.0)])
        i += n
    return out


def _report(route: Route) -> dict:
    offsets = [lv - (g + 1) for lv, g in zip(route.levels, route.ground, strict=True) if g is not None]
    return {
        "length": len(route.cells),
        "kinds": {k: route.kinds.count(k) for k in KINDS if k in route.kinds},
        "max_cut": max([0.0, *(-d for d in offsets)]),
        "max_fill": max([0.0, *offsets]),
        "bridges": _runs(route, "bridge"),
        "tunnels": _runs(route, "tunnel"),
        "reads": [{"section": s.name, "box": list(s.box), "out": f"site/{route.element}-{s.name}",
                   "world": s.world} for s in route.sections],
    }


def run_route(design: LineDesign, project: Path, *, preview: bool = False) -> dict:
    """Plan the route, write ``terrain/<element>.route.json``, its report and the previews.

    `preview` is accepted for symmetry with the other commands; the route writes no world phases.
    """
    project = Path(project)
    grid = load_grid(design.heights) if design.heights is not None else None
    route = plan_route(design, grid)
    folder = project / "terrain"
    folder.mkdir(parents=True, exist_ok=True)
    route_path = folder / f"{design.element}.route.json"
    write_route(route, route_path)
    report = _report(route)
    (folder / f"{design.element}.route-report.json").write_text(json.dumps(report, indent=1) + "\n",
                                                                 encoding="utf-8")
    previews_dir = folder / "previews"
    previews = [route_map(design, grid, route, previews_dir / f"{design.element}-route.png"),
                profile_view(route, previews_dir / f"{design.element}-profile.png"),
                *cross_sections(route, previews_dir, element=design.element)]
    return {"route": str(route_path), "report": report, "previews": [str(p) for p in previews]}


def add_transit_parsers(commands) -> None:
    """Register the transit commands on the launcher's subcommands."""
    cmd = commands.add_parser("route", help="plan a transit line's route, sections and previews")
    cmd.add_argument("design", type=Path)
    cmd.add_argument("--project", type=Path, required=True)
    cmd.add_argument("--preview", action="store_true", help="accepted; the route writes no world phases")


def run_transit(args) -> int:
    """Run a transit command; print JSON; return the exit status."""
    design = load_line(args.design, args.project)
    if args.command == "route":
        print(json.dumps(run_route(design, args.project, preview=args.preview), indent=2))
        return 0
    raise ValueError(f"unknown transit command {args.command}")
