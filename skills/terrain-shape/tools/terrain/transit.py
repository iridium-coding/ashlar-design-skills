"""The transit commands: ``route`` plans a line, ``line`` emits it and ``transit-check`` checks a build.

``emit_line`` works section by section on each section's site read: it grades the corridor
through the terrain emitter (``emit_field``), lays the bridges, tunnels, stops and track on the
graded ground with the emitter's liquid and gravity checks (``check_form_layers``) and lights
each section densely enough. The whole projected line is then checked and the player blocks it
touches are listed; no phase file is written until both pass (the blocks need the report's
token).
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import numpy as np

from . import blocks, corridor, structures, track, transit_checks, verify
from .ashlar_emit import EmitResult, check_form_layers, emit_field, plan_rows_toon
from .emit import VerifyError
from .live import LiveWrite, greedy_fills
from .route import (
    Route,
    Section,
    design_hash,
    load_grid,
    load_route,
    plan_route,
    write_route,
)
from .site import Site, base_id, integer_level, load_site, natural_for
from .transit_design import KINDS, LineDesign, load_line
from .transit_preview import cross_sections, profile_view, route_map

TRANSIT_COMMANDS = {"route", "line", "transit-check"}
MODES = ("carve", "build", "track", "light")
HALVINGS = 4        # a section's lamp spacing halves at most this many times
Cell = tuple[int, int, int]
_BUILT_PARTS = {"bridge": "bridge", "tunnel": "tunnel lining", "tube": "tube"}     # what a build writes by kind


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


# ------------------------------------------------------------------ the route and the reads
def _line_route(design: LineDesign, project: Path) -> Route:
    """The route ``terrain/<element>.route.json``, refused when missing or planned from another design."""
    name = f"terrain/{design.element}.route.json"
    path = Path(project) / name
    if not path.exists():
        raise ValueError(f"{name} is missing: run terrain.py route first")
    found = load_route(path)
    if found.design_hash != design_hash(design):
        raise ValueError(f"{name} was planned from another version of the design: "
                         "the route is stale; run terrain.py route again")
    return found


def _contains(outer: tuple[int, ...], inner: tuple[int, ...]) -> bool:
    return all(outer[k] <= inner[k] for k in range(3)) and all(outer[k] >= inner[k] for k in range(3, 6))


def section_read(project: Path, design: LineDesign, section: Section) -> Site:
    """The site read of one section, ``site/<element>-<name>`` in the project.

    Raises:
        ValueError: naming the section and the read folder when the read is missing or
            unreadable, when its box does not contain the section box, or when it is of
            another world than the line.
    """
    folder = f"site/{design.element}-{section.name}"
    path = Path(project) / folder
    if not path.is_dir():
        raise ValueError(f"section {section.name} has no read: read its box {list(section.box)} into {folder}")
    try:
        site = load_site(path)
    except ValueError as exc:
        raise ValueError(f"section {section.name}, read {folder}: {exc}") from None
    if not _contains(site.box, section.box):
        raise ValueError(f"section {section.name}: the read in {folder} covers {list(site.box)}, which does "
                         f"not contain the section box {list(section.box)}; read that box again")
    if site.world != design.world:
        raise ValueError(f"section {section.name}: the read in {folder} is of world {site.world!r}, "
                         f"but the line runs in {design.world!r}")
    return site


def _classed_from_reads(design: LineDesign) -> bool:
    """A Nether line, or a straight line without heights: its tunnels and tubes come from the reads."""
    return design.dimension == "nether" or (design.route == "straight" and design.heights is None)


# ------------------------------------------------------------------ layers
def _cells(write: LiveWrite) -> dict[Cell, str]:
    ox, oy, oz = write.origin
    return {(ox + int(i), oy + int(j), oz + int(k)): write.palette[write.codes[i, j, k]]
            for i, j, k in np.argwhere(write.codes)}


def _infrastructure(design: LineDesign, route: Route, section: Section, graded: Site,
                    spacing: int) -> tuple[list[tuple[str, LiveWrite]], dict]:
    """The section's bridges, tunnels, stops and track on the graded site: one write per mode.

    Within a mode the structures and stops come first and the track last, so the track's bed
    and rails win where they meet a lining or a deck. Returns the writes in the order carve,
    build, track, light, and the bridge stats.
    """
    bridge, stats = structures.bridge_layers(design, route, section, graded, light_spacing=spacing)
    layers = [*bridge,
              *structures.tunnel_layers(design, route, section, graded, light_spacing=spacing),
              *structures.stop_layers(design, route, section, graded, light_spacing=spacing),
              *track.track_layers(design, route, section, graded, light_spacing=spacing)]
    merged: dict[str, dict[Cell, str]] = {}
    for mode, write in sorted(layers, key=lambda layer: MODES.index(layer[0])):
        merged.setdefault(mode, {}).update(_cells(write))
    out = [(mode, write) for mode, cells in merged.items() if (write := blocks.cells_write(cells)) is not None]
    return out, stats


def _lit(design: LineDesign, route: Route, section: Section, final: Site) -> bool:
    """Whether the section's own projected site passes the light check on its own cells."""
    return transit_checks.check_line(design, route, {section.name: final}, sections=[section.name],
                                     checks=["light"])["ok"]


def _why(design: LineDesign, route: Route) -> Callable[[str, Cell], str]:
    """Why a layer changes a cell: what goes there, at the chainage of the nearest route cell."""
    xz = np.asarray(route.cells, dtype=float)
    line = design.mode

    def why(mode: str, cell: Cell) -> str:
        i = int(np.argmin(np.hypot(xz[:, 0] - cell[0], xz[:, 1] - cell[2])))
        kind, at = route.kinds[i], f"at chainage {i}"
        if mode == "grade":
            return f"in the ground graded for the {line} ({kind}) {at}"
        if mode == "carve":
            return f"inside the {line} {'bore' if kind in ('tunnel', 'tube') else 'clearance'} {at}"
        if mode == "build":
            return f"in the {line} {_BUILT_PARTS.get(kind, 'bed')} {at}"
        if mode == "track":
            return f"on the {line} line {at}"
        return f"at a lamp of the {line} line {at}"

    return why


# ------------------------------------------------------------------ emission
@dataclass
class LineResult:
    rows: list[dict]
    quality: dict[str, list[dict]]
    notes: list[str]
    bbox: tuple[int, ...]
    report: dict
    previews: list[Path]


@dataclass
class _Planned:
    section: Section
    plan: corridor.CorridorPlan
    grading: EmitResult | None      # the grading checked as a preview; None when nothing is graded
    final: Site                     # the section's projected site
    spacing: int                    # the lamp spacing that lit it
    stats: dict
    touched: list[dict]
    first: int                      # the id of the section's first phase (its first grading phase)
    ids: list[int]                  # the section's phase ids, from its grading phases on


def _union(boxes: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(min(b[i] for b in boxes) for i in range(3)) + tuple(max(b[i] for b in boxes) for i in range(3, 6))


def emit_line(design: LineDesign, project: Path, *, first_phase: int, preview: bool = False,
              standalone: bool = False, approve_built: str | None = None, max_columns: int = 128) -> LineResult:
    """Check a line against its section reads and write its phases, plan rows, report and previews.

    Per section, in route order: the corridor grading phases (``<element>-sNN-mass-k``), then the
    carve, build, track and light phases of its structures, stops and track, with contiguous ids
    from `first_phase`. The lamps start at ``lights.spacing`` and the spacing halves (at most
    ``HALVINGS`` times) until the section's own light check passes. A section with nothing to
    grade has no grading phases and so no ``surface_match`` row; its ``seam`` rows are absent too.

    The report ``terrain/<element>.line-report.json`` and the previews are written on every run,
    so a refused write keeps them (the refusal points at the report). A preview writes nothing
    else: phase files and plan rows of an earlier run stay in place. A write also copies the
    design to ``terrain/<element>.line.json`` when the file there differs, because the plan's
    ``transit`` row points at it (a note says so).

    Args:
        design: The validated line design.
        project: The project folder (``site/``, ``terrain/`` and ``phases/`` live here).
        first_phase: The id of the first phase in the host plan.
        preview: Write only the report (``terrain/<element>.line-report.json``) and previews.
        standalone: Also write a ``plan.toon`` for a line that is its own project (not with
            `preview`).
        approve_built: The report's ``built.token``, given only after the user has seen and
            approved every player block the line touches.
        max_columns: Columns per phase tile.

    Raises:
        ValueError: `preview` with `standalone`; a missing or stale route; a missing section read,
            a read that does not contain its section box or a read of another world (naming the
            section and folder).
        VerifyError: A layer breaks the emitter's checks or, outside a preview, the projected
            line fails its checks or touches player blocks without the matching token.
        RouteError: A structure that cannot be built (a pier in water, lava in a bore).
    """
    if preview and standalone:
        raise ValueError("--standalone writes plan.toon, which a preview never writes: drop --preview or --standalone")
    first_phase = integer_level(first_phase, "first_phase")
    if first_phase < 1:
        raise ValueError("first_phase must be positive")
    project = Path(project)
    element = design.element
    terrain = project / "terrain"
    route = _line_route(design, project)
    reads = {s.name: section_read(project, design, s) for s in route.sections}
    if _classed_from_reads(design):
        for s in route.sections:
            route.kinds[s.start:s.end + 1] = structures.nether_kinds(design, route, s, reads[s.name])
    natural, why = natural_for(design.dimension), _why(design, route)
    rows: list[dict] = []
    payloads: list[tuple[Path, dict]] = []
    planned: list[_Planned] = []
    seen: set[Cell] = set()
    for s in route.sections:
        site = reads[s.name]
        graded, mass, plan = corridor.graded_site(design, route, s, site)
        start = len(rows)
        grading = None
        if mass is not None:
            # Checked as a preview here; written only once the whole line passes (below). The
            # terrace check is off: it would judge the existing ground the corridor runs through.
            grading = emit_field(plan.field, plan.spec, site, project, element=f"{element}-{s.name}",
                                 first_phase=first_phase + start, protect=plan.protect,
                                 require_relief=False, check_terraces=False,
                                 seam_rows=corridor.outer_seam_rows(design, route, s, plan),
                                 max_columns=max_columns, preview=True)
            rows.extend(grading.phases)
        spacing, halvings = design.lights.spacing, 0
        layers, stats = _infrastructure(design, route, s, graded, spacing)
        final = blocks.apply_writes(graded, layers)
        while halvings < HALVINGS and spacing > 1 and not _lit(design, route, s, final):
            spacing, halvings = max(1, spacing // 2), halvings + 1
            layers, stats = _infrastructure(design, route, s, graded, spacing)
            final = blocks.apply_writes(graded, layers)
        tiles = check_form_layers(graded, layers, max_columns=max_columns)
        changes = [("grade", mass), *layers] if mass is not None else layers
        touched = []
        for item in blocks.touched_blocks(site, changes, why, natural=natural):
            # Once per cell, under the first layer (and section) that changes it: a later entry for
            # the cell would name the block an earlier layer of this line put there.
            if tuple(item["cell"]) not in seen:
                seen.add(tuple(item["cell"]))
                touched.append(item)
        counters: dict[str, int] = {}
        for mode, tile in tiles:
            fills = greedy_fills(tile)
            counters[mode] = counters.get(mode, 0) + 1
            name = f"{element}-{s.name}-{mode}-{counters[mode]}"
            phase_id = first_phase + len(rows)
            file = f"phases/{phase_id:02d}-{name}.json"
            payload: dict = {"fills": fills, "liquids": "static"}
            if site.world is not None:
                payload["world"] = site.world
            payloads.append((project / file, payload))
            rows.append({"id": phase_id, "name": name, "file": file, "blocks": int(np.count_nonzero(tile.codes)),
                         "from": [min(f["from"][i] for f in fills) for i in range(3)],
                         "to": [max(f["to"][i] for f in fills) for i in range(3)],
                         "via": "placer", "rollback": "backup"})
        planned.append(_Planned(s, plan, grading, final, spacing, stats, touched, first_phase + start,
                                [row["id"] for row in rows[start:]]))

    finals = {p.section.name: p.final for p in planned}
    check = transit_checks.check_line(design, route, finals)
    touched = [item for p in planned for item in p.touched]
    token = blocks.built_token(touched)
    by_block: dict[str, int] = {}
    for item in touched:
        by_block[base_id(item["block"])] = by_block.get(base_id(item["block"]), 0) + 1
    built = {"token": token, "count": len(touched), "by_block": by_block,
             "loses_data": sum(1 for item in touched if item.get("loses_data")), "items": touched}
    displaced = sum(p.stats["displaced_water"] for p in planned)
    unsupported = sum(p.stats["unsupported_tube"] for p in planned)
    sections = []
    for p in planned:
        s, kinds = p.section, route.kinds[p.section.start:p.section.end + 1]
        sections.append({"name": s.name, "start": s.start, "end": s.end, "box": list(s.box),
                         "read": f"site/{element}-{s.name}", "kinds": {k: kinds.count(k) for k in KINDS if k in kinds},
                         "cut_columns": p.plan.cut_cells, "fill_columns": p.plan.fill_cells,
                         "light_spacing": p.spacing, "piers": p.stats["piers"], "phases": p.ids,
                         "touched": len(p.touched)})
    # `route` and `kinds` record the classes the build used (Nether lines class them from the
    # reads), so transit-check checks the built line against the same ones.
    report = {"sections": sections, "check": check, "built": built, "boxes": [list(s.box) for s in route.sections],
              "displaced_water": displaced, "unsupported_tube": unsupported, "route": route.design_hash,
              "kinds": list(route.kinds)}
    report_path = terrain / f"{element}.line-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    owner = {i: finals[s.name] for s in route.sections for i in range(s.start, s.end + 1)}
    previews = cross_sections(route, terrain / "previews", element=f"{element}-line", site_of=owner.__getitem__)

    notes = [(f"line design terrain/{element}.line.json: {design.mode} line, style {design.style}, seed "
              f"{design.seed}, {len(route.cells)} cells in {len(route.sections)} sections")]
    for p, entry in zip(planned, sections, strict=True):
        graded_text = (f"{p.plan.cut_cells} cut and {p.plan.fill_cells} fill columns graded, "
                       f"GATE A {verify.offline_token(p.grading.report)}" if p.grading is not None else "no grading")
        notes.append(f"{entry['name']} (cells {entry['start']}-{entry['end']}): "
                     f"{', '.join(f'{n} {k}' for k, n in entry['kinds'].items())}; {graded_text}; "
                     f"lamps every {p.spacing} cells")
    notes.append("projected check: " + "; ".join(f"{c['name']} {'ok' if c['ok'] else 'FAILS'}: {c['detail']}"
                                                 for c in check["checks"]))
    blocks_text = ", ".join(f"{n} {b}" for b, n in by_block.items())
    if touched:
        notes.append(f"touches {len(touched)} player blocks ({blocks_text}); approval token {token}; "
                     f"list in terrain/{element}.line-report.json")
    if displaced:
        notes.append(f"piers displace {displaced} still water cells (bridges.piers_in_water)")
    if unsupported:
        notes.append(f"{unsupported} tube piers found no ground within {structures.TUBE_REACH} blocks below "
                     "and were left out")
    design_path = terrain / f"{element}.line.json"
    copy_design = not preview and (not design_path.exists()
                                   or json.loads(design_path.read_text(encoding="utf-8")) != design.source)
    if copy_design:
        notes.append(f"copied the design to terrain/{element}.line.json, where the plan's transit row points")
    boxes = [(*row["from"], *row["to"]) for row in rows]
    boxes += [p.grading.bbox for p in planned if p.grading is not None]
    bbox = _union(boxes or [s.box for s in route.sections])
    quality: dict[str, list[dict]] = {"transit": [{"file": f"terrain/{element}.line.json"}],
                                      "surface_match": [], "seam": []}

    def gather(results: list[EmitResult]) -> None:
        for result in results:
            quality["surface_match"] += result.quality["surface_match"]
            quality["seam"] += result.quality["seam"]

    if preview:
        gather([p.grading for p in planned if p.grading is not None])
        return LineResult(rows, quality, notes, bbox, report, previews)
    failed = [c for c in check["checks"] if not c["ok"]]
    if failed:
        raise VerifyError("the line fails its own checks: " + "; ".join(f"{c['name']}: {c['detail']}" for c in failed)
                          + f" (cells in {report_path}). Revise the design (route, profile, limits or lights)")
    if touched and approve_built != token:
        raise VerifyError(f"the line touches {len(touched)} player blocks ({blocks_text}): show the user each "
                          f"block, where it is and why ({report_path}), and only after their yes rerun with "
                          f"--approve-built {token}")

    if copy_design:
        design_path.write_text(json.dumps(design.source, indent=2) + "\n", encoding="utf-8")
    written = []
    for p in planned:
        if p.grading is None:
            continue
        result = emit_field(p.plan.field, p.plan.spec, reads[p.section.name], project,
                            element=f"{element}-{p.section.name}", first_phase=p.first,
                            protect=p.plan.protect, require_relief=False, check_terraces=False,
                            seam_rows=p.grading.quality["seam"], max_columns=max_columns)
        if result.phases != p.grading.phases:
            raise RuntimeError(f"section {p.section.name}: the grading phases changed between the check and the write")
        written.append(result)
    gather(written)
    for path, payload in payloads:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    snippet = plan_rows_toon(EmitResult(rows, quality, notes, bbox, None, None))  # type: ignore[arg-type]
    (terrain / f"{element}.plan-rows.toon").write_text(snippet, encoding="utf-8")
    if standalone:
        lines = ["plan:", f"  project: {project.resolve().name}", "  skill: system-transit"]
        if design.world is not None:
            lines.append(f"  world: {design.world}")
        centre = [int((bbox[i] + bbox[i + 3]) // 2) for i in range(3)]
        lines += [f"  anchor: {{x: {centre[0]}, y: {centre[1]}, z: {centre[2]}}}",
                  f"  bbox: {{from: {list(bbox[:3])}, to: {list(bbox[3:])}}}",
                  f"  summary: {element} ({design.style} {design.mode} line)", "  approved: no"]
        (project / "plan.toon").write_text("\n".join(lines) + "\n" + snippet, encoding="utf-8")
    return LineResult(rows, quality, notes, bbox, report, previews)


# ------------------------------------------------------------------ checking a build
def _built_kinds(design: LineDesign, project: Path, found: Route) -> list[str]:
    """The stretch kinds a line classed from its reads was built with, from its line report.

    The fresh reads cannot class it again: every carved bore would read as an open tube.
    """
    name = f"terrain/{design.element}.line-report.json"
    path = Path(project) / name
    if not path.exists():
        raise ValueError(f"{name} is missing: run terrain.py line first (the report records the tunnel and "
                         "tube classes the build used)")
    report = json.loads(path.read_text(encoding="utf-8"))
    kinds = report.get("kinds")
    if (report.get("route") != found.design_hash or not isinstance(kinds, list)
            or len(kinds) != len(found.cells) or not set(kinds) <= set(KINDS)):
        raise ValueError(f"{name} was written for another route: run terrain.py line again")
    return kinds


def check_reads(design: LineDesign, project: Path, reads: Sequence[Path]) -> dict:
    """Check fresh reads of a built line; each read stands for every section whose box it contains.

    A Nether line, or a straight line without heights, is checked with the tunnel and tube
    classes its build used, from ``terrain/<element>.line-report.json``.

    Raises:
        ValueError: A missing or stale route; for a line classed from its reads, a missing line
            report or one written for another route; a read of another world, a read that
            contains no section box, or a section that no read contains.
    """
    found = _line_route(design, project)
    if _classed_from_reads(design):
        found.kinds = _built_kinds(design, project, found)
    sites: dict[str, Site] = {}
    for path in reads:
        site = load_site(path)
        if site.world != design.world:
            raise ValueError(f"the read {path} is of world {site.world!r}, but the line runs in {design.world!r}")
        held = [s for s in found.sections if _contains(site.box, s.box)]
        if not held:
            raise ValueError(f"the read {path} covers {list(site.box)}, which contains no section box of "
                             f"{design.element}")
        for s in held:
            sites.setdefault(s.name, site)
    missing = [s for s in found.sections if s.name not in sites]
    if missing:
        raise ValueError("no read contains section " + ", ".join(f"{s.name} {list(s.box)}" for s in missing))
    return transit_checks.check_line(design, found, sites)


# ------------------------------------------------------------------ command line
def add_transit_parsers(commands) -> None:
    """Register the transit commands on the launcher's subcommands."""
    cmd = commands.add_parser("route", help="plan a transit line's route, sections and previews")
    cmd.add_argument("design", type=Path)
    cmd.add_argument("--project", type=Path, required=True)
    cmd.add_argument("--preview", action="store_true", help="accepted; the route writes no world phases")
    line = commands.add_parser("line", help="check a transit line against its section reads and write its phases "
                                            "(or only the report and previews)")
    line.add_argument("design", type=Path)
    line.add_argument("--project", type=Path, required=True)
    line.add_argument("--first-phase", type=int, required=True)
    output = line.add_mutually_exclusive_group()
    output.add_argument("--preview", action="store_true", help="write the report and previews only")
    output.add_argument("--standalone", action="store_true", help="also write plan.toon (not with --preview)")
    line.add_argument("--approve-built", metavar="TOKEN",
                      help="the report's built.token, after the user approved every touched player block")
    check = commands.add_parser("transit-check", help="check fresh post-build reads of a transit line")
    check.add_argument("design", type=Path)
    check.add_argument("--sites", type=Path, nargs="+", required=True, metavar="DIR")
    check.add_argument("--project", type=Path)


def run_transit(args) -> int:
    """Run a transit command; print JSON; return the exit status."""
    design = load_line(args.design, args.project)
    if args.command == "route":
        print(json.dumps(run_route(design, args.project, preview=args.preview), indent=2))
        return 0
    if args.command == "line":
        result = emit_line(design, args.project, first_phase=args.first_phase, preview=args.preview,
                           standalone=args.standalone, approve_built=args.approve_built)
        print(json.dumps({"preview": args.preview, "phases": result.rows, "bbox": list(result.bbox),
                          "notes": result.notes, "report": result.report,
                          "previews": [str(p) for p in result.previews]}, indent=2))
        return 0
    if args.command == "transit-check":
        report = check_reads(design, design.project, args.sites)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    raise ValueError(f"unknown transit command {args.command}")
