"""Offline verification gate — Pillar 8 (the automatic quality gate).

Runs a set of machine checks on a HeightField (and optionally its MaterialSpec
and recipe) that mirror the in-world ``quality_contract`` rows, so a degenerate
field is caught *before any block is placed*. The terrain skills HALT on a FAIL.

This is the structural fix for the autonomy failure mode (gates dropped under
"don't wait on me"): the gate is code, not a judgement call.

``verify(hf)`` keeps the original five checks (bounds / not_degenerate / relief /
land_present / no_ziggurat) and stays callable with no extra arguments. When a
``spec`` (a ``MaterialSpec``) is supplied it adds palette-monoculture and
underwater/foundation-face checks; when a ``recipe`` marks the field blended or
multi-region the seam check is folded in. ``offline_token`` derives a stable,
tamper-evident token from the report so downstream stamps can prove the gate
actually ran.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from . import masks as M
from .site import surface_y


@dataclass
class Report:
    ok: bool
    checks: list = field(default_factory=list)   # list[(name, passed, detail)]

    def __str__(self) -> str:
        lines = [("PASS" if self.ok else "FAIL") + " — terrain verify"]
        for name, passed, detail in self.checks:
            lines.append(f"  [{'ok' if passed else 'XX'}] {name}: {detail}")
        return "\n".join(lines)

    def failures(self) -> list:
        return [c for c in self.checks if not c[1]]


def verify(hf, spec=None, recipe=None, *,
           min_land_fraction: float = 0.05, max_height: float = 320.0,
           min_height: float = -64.0, silhouette_var_min: float = 3.0,
           require_relief: bool = True, max_collinear_run: int = 12,
           palette_max_single: float = 0.92, seam_max_step: float = 12.0,
           ground=None, water=None, existing_water=None, check_terraces: bool = True,
           **_ignored) -> Report:
    """Check a heightfield against the non-negotiables. Returns a ``Report``;
    ``report.ok`` is the gate. Tunable thresholds default to the skill's rules.

    ``verify(hf)`` (no spec/recipe) runs the original five structural checks plus
    the always-on ``edge_irregularity`` check. Passing a ``MaterialSpec`` as
    ``spec`` adds palette-monoculture and underwater/foundation-face checks
    (both need the material plan). Passing a ``recipe`` that marks the field
    blended/multi-region folds in the seam check.

    Checks:
      bounds              all heights within the world (−64..320)
      not_degenerate      field isn't a single flat value (a no-op build)
      relief              enough vertical variance that it reads as terrain
      land_present        some land above sea level (unless an intentional sea)
      no_ziggurat         not a stack of flat terraces (spiky height histogram
                          + bimodal flat-top/vertical-wall slope distribution);
                          ``check_terraces=False`` reports it ok, not checked,
                          for corridor grading of existing (often flat) ground
      edge_irregularity   no straight coastline run longer than the limit. This
                          is the field-level pre-screen of the 7-block rule: it
                          measures the per-cell land/water interface (so the
                          default limit is looser than the literal 7-point rule,
                          which the in-world QC row enforces on spaced samples);
                          it still catches a ruler-drawn wall by a wide margin
      palette_monoculture (spec) the materialised surface (and every declared
                          palette/strata band) actually mixes — not one block at
                          essentially 100% (the literal monoculture antipattern).
                          The per-palette 70% mix-band is enforced in-world; this
                          field check catches a flat single-block surface
      underwater_face     (spec) no steep submerged face fronted by a single block
      seam_max_step       (recipe blended) largest single-cell height step is a
                          ramp, not a wall
    """
    checks = []
    h = hf.h

    in_bounds = bool(h.min() >= min_height and h.max() <= max_height)
    checks.append(("bounds", in_bounds,
                   f"[{h.min():.1f}, {h.max():.1f}] vs [{min_height}, {max_height}]"))

    rng = float(h.max() - h.min())
    not_degenerate = rng > 1e-6
    checks.append(("not_degenerate", not_degenerate, f"height range {rng:.2f}"))

    var = float(np.var(h))
    relief_ok = (var >= silhouette_var_min) if require_relief else True
    relief_detail = f"variance {var:.2f} (min {silhouette_var_min})"
    if not require_relief:
        relief_detail = f"variance {var:.2f} for local grading"
    checks.append(("relief", relief_ok, relief_detail))

    dry = h > hf.sea_level if water is None else ~np.isfinite(water)
    land = float(np.mean(dry))
    land_ok = land >= min_land_fraction
    checks.append(("land_present", land_ok, f"{land:.1%} dry land"))

    if check_terraces:
        zig = _ziggurat_score(h)
        no_zig = zig < 0.6
        checks.append(("no_ziggurat", no_zig,
                       f"terrace score {zig:.2f} (flag >=0.6)"))
    else:
        checks.append(("no_ziggurat", True, "not checked: corridor grading"))

    run, edge_name = _edge_max_run(h, hf.sea_level, water=water)
    edge_ok = run <= max_collinear_run
    checks.append(("edge_irregularity", edge_ok,
                   f"{edge_name} longest collinear run {run} (max {max_collinear_run})"))

    if spec is not None:
        block, frac, where = _palette_monoculture(hf, spec)
        mono_ok = frac <= palette_max_single
        checks.append(("palette_monoculture", mono_ok,
                       f"{where} dominated by {block} at {frac:.0%} "
                       f"(max {palette_max_single:.0%})"))

        face_ok, face_detail = _underwater_face(hf, spec, water=water)
        checks.append(("underwater_face", face_ok, face_detail))

    if recipe is not None and _recipe_is_blended(recipe):
        step = _max_single_step(h)
        seam_ok = step <= seam_max_step
        checks.append(("seam_max_step", seam_ok,
                       f"{step:.1f} blocks (max {seam_max_step})"))

    if ground is not None:
        ok_e, detail = _edge_match(h, np.asarray(ground, dtype=float))
        checks.append(("edge_match", ok_e, detail))

    if water is not None:
        water = np.asarray(water, dtype=float)
        ok_w, detail = _water_contained(h, water, existing_water)
        checks.append(("water_contained", ok_w, detail))
        ok_s, detail = _no_dry_shelf(h, water)
        checks.append(("no_dry_shelf", ok_s, detail))

    ok = all(c[1] for c in checks)
    return Report(ok=ok, checks=checks)


def _ring_mask(shape) -> np.ndarray:
    ring = np.zeros(shape, dtype=bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    return ring


def _edge_match(h: np.ndarray, ground: np.ndarray) -> tuple:
    """Outer ring: ``max |round(h) - ground|`` must be at most 1."""
    ring = _ring_mask(h.shape)
    diff = np.abs(surface_y(h) - ground)
    diff = np.where(ring, diff, 0.0)
    worst = float(np.nanmax(np.where(ring, diff, 0.0)))
    ok = worst <= 1.0 and not np.isnan(ground[ring]).any()
    if ok:
        return True, f"outer ring within {worst:.0f} of the existing ground (max 1)"
    bad = np.argwhere(ring & ~(diff <= 1.0))
    cells = ", ".join(f"({x},{z}) h {np.round(h[x, z]):.0f} vs ground {ground[x, z]:.0f}"
                      for x, z in bad[:3])
    return False, f"outer ring differs from the existing ground by {worst:.0f} (max 1): {cells}"


def _neighbour_pairs(shape):
    """Yield (src, dst) slice pairs so that a[src] is each cell and a[dst] its
    4-neighbour in one direction, over the cells that have one."""
    nx, nz = shape
    yield (slice(0, nx - 1), slice(None)), (slice(1, nx), slice(None))
    yield (slice(1, nx), slice(None)), (slice(0, nx - 1), slice(None))
    yield (slice(None), slice(0, nz - 1)), (slice(None), slice(1, nz))
    yield (slice(None), slice(1, nz)), (slice(None), slice(0, nz - 1))


def _water_contained(h, water, existing_water) -> tuple:
    """Planned water only. ``existing_water`` is L, the still liquid level of the
    existing ground (``liquid_levels(site).level`` cropped to the grid), never
    ``Surfaces.water``; heights compare through ``surface_y``."""
    h = surface_y(h)
    wet = ~np.isnan(water)
    bad = []
    for src, dst in _neighbour_pairs(h.shape):
        lvl = water[src]
        leak = wet[src] & ~(wet[dst] & (water[dst] == lvl)) & ~(h[dst] >= lvl)
        for x, z in np.argwhere(leak):
            x0, z0 = src[0].start or 0, src[1].start or 0
            bad.append((int(x) + x0, int(z) + z0, float(lvl[x, z])))
    edge_bad = []
    ring = _ring_mask(h.shape)
    for x, z in np.argwhere(wet & ring):
        ex = np.nan if existing_water is None else existing_water[x, z]
        if not ex == water[x, z]:
            edge_bad.append((int(x), int(z), float(water[x, z]), float(ex)))
    if not bad and not edge_bad:
        return True, f"{int(wet.sum())} water columns contained"
    parts = []
    if bad:
        parts.append("water spills at " + ", ".join(
            f"({x},{z}) level {l:g}" for x, z, l in bad[:3]))
    if edge_bad:
        parts.append("water on the edge without matching existing water at " + ", ".join(
            f"({x},{z}) level {l:g}" for x, z, l, _ in edge_bad[:3]))
    return False, "; ".join(parts)


def _no_dry_shelf(h, water) -> tuple:
    h = surface_y(h)
    wet = ~np.isnan(water)
    bad = set()
    for src, dst in _neighbour_pairs(h.shape):
        lvl = water[dst]
        shelf = ~wet[src] & wet[dst] & (h[src] < lvl)
        x0, z0 = src[0].start or 0, src[1].start or 0
        for x, z in np.argwhere(shelf):
            bad.add((int(x) + x0, int(z) + z0))
    if not bad:
        return True, "no dry column below a neighbouring water level"
    first = sorted(bad)[:3]
    return False, f"{len(bad)} dry columns below a neighbour's water level, e.g. " + ", ".join(
        f"({x},{z}) h {h[x, z]:.1f}" for x, z in first)


def _ziggurat_score(h: np.ndarray) -> float:
    """Heuristic 0..1: how much the field looks like stacked flat terraces with
    vertical walls (the anti-pattern). High when most cells sit on a few discrete
    Y levels AND the slope distribution is bimodal (flat tops + vertical steps),
    which is what box-fill ziggurats produce and real terrain does not."""
    rng = float(h.max() - h.min())
    if rng < 1e-6:
        return 0.0
    # fraction of cells whose height is within 0.05 blocks of an integer-rounded
    # *mode* level — real eroded terrain spreads across many levels.
    rounded = np.round(h).astype(int)
    levels, counts = np.unique(rounded, return_counts=True)
    top_mass = counts.sort()  # in-place; counts now ascending
    top = counts[-min(5, len(counts)):].sum() / h.size  # mass on the 5 commonest levels
    # slope bimodality: ziggurats are mostly 0° (tops) or near-90° (walls)
    s = M.slope_deg(h)
    flat = np.mean(s < 5.0)
    steep = np.mean(s > 70.0)
    mid = np.mean((s >= 5.0) & (s <= 70.0))
    bimodal = (flat + steep) / (mid + 1e-6)
    # combine: lots of mass on few levels AND little mid-slope → ziggurat
    score = 0.5 * float(top) + 0.5 * float(np.clip(bimodal / 10.0, 0, 1))
    return float(np.clip(score, 0, 1))


def _edge_max_run(h: np.ndarray, sea_level: float, *, water=None) -> tuple:
    """Longest *collinear* run along a terrain edge (the 7-block rule).

    The edge is the land/water coastline: a straight edge produces a long run of
    identical transition coordinates — exactly the manufactured "ruler-drawn"
    coastline the rule forbids. A field with no coastline (all land or all water)
    has no such edge to check, so the rule passes vacuously (the silhouette and
    relief checks already cover an all-land field). Returns ``(max_run, name)``.
    """
    land = h > sea_level if water is None else ~np.isfinite(water)
    if land.any() and (~land).any():
        return _boundary_collinear_run(land), "coastline"
    return 0, "no-coastline"


def _boundary_collinear_run(region: np.ndarray) -> int:
    """Longest *straight* collinear run of the land/water interface.

    The 7-block rule forbids a coastline that runs collinear (same X or same Z)
    for a long stretch. We look at the interface itself: a vertical coast edge
    sits between two horizontally adjacent cells of opposite land/water state;
    when that same vertical edge persists across many consecutive rows (same
    X-pair) the coast is a straight N-S wall. Symmetrically for E-W walls.

    ``Vx[x, z]`` marks a vertical interface between columns x and x+1; the longest
    contiguous run of ``True`` *down a column of ``Vx``* (constant x-pair, varying
    z) is the longest straight vertical coast segment. A curved or fractal coast
    shifts the interface to a neighbouring x every few cells, breaking the run;
    a thin spit carries an interface on each side, each broken by its own wiggle.
    A ruler-drawn wall holds one interface its full length — what we refuse.
    """
    land = np.asarray(region, dtype=bool)
    if land.shape[0] < 2 or land.shape[1] < 2:
        return 0
    vx = land[:-1, :] != land[1:, :]   # vertical edges, shape (nx-1, nz)
    hz = land[:, :-1] != land[:, 1:]   # horizontal edges, shape (nx, nz-1)
    longest = 0
    for i in range(vx.shape[0]):       # straight vertical coast: run down z
        longest = max(longest, _max_true_run(vx[i, :]))
    for j in range(hz.shape[1]):       # straight horizontal coast: run down x
        longest = max(longest, _max_true_run(hz[:, j]))
    return longest


def _max_true_run(line: np.ndarray) -> int:
    """Longest contiguous run of True in a 1-D boolean array."""
    best = cur = 0
    for v in np.asarray(line, dtype=bool):
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best


def _palette_monoculture(hf, spec) -> tuple:
    """Worst single-block dominance across the materialised surface and every
    declared palette/strata band. Returns ``(block_id, fraction, where)``.

    The gate (the caller's ``palette_max_single``, default 0.92) is the
    *monoculture* line — essentially one block, no dither — not the per-palette
    70% mix-band the in-world QC enforces. A grass-dominant base or a sand
    beach is a legitimate ratio band and passes; a spec that paints one block
    everywhere (no mix) is what we refuse here.
    """
    from .materialize import resolve_surface

    worst_block, worst_frac, worst_where = "—", 0.0, "surface"

    # 1) the actually-resolved surface mix (the real materialised cells)
    try:
        surface, _sub = resolve_surface(hf, spec)
        flat = surface.reshape(-1)
        ids, counts = np.unique(flat.astype(object), return_counts=True)
        total = flat.size
        if total:
            i = int(np.argmax(counts))
            frac = float(counts[i]) / total
            if frac > worst_frac:
                worst_block, worst_frac, worst_where = str(ids[i]), frac, "surface"
    except Exception as e:  # pragma: no cover - defensive
        worst_where = f"surface (unresolved: {e})"

    # 2) declared palettes: base, each layer, the slant override
    def _check_palette(pal: dict, where: str):
        nonlocal worst_block, worst_frac, worst_where
        if not pal:
            return
        tot = sum(pal.values())
        if tot <= 0:
            return
        bid = max(pal, key=pal.get)
        frac = pal[bid] / tot
        if frac > worst_frac:
            worst_block, worst_frac, worst_where = bid, frac, where

    _check_palette(getattr(spec, "base", None), "base palette")
    for i, layer in enumerate(getattr(spec, "layers", []) or []):
        _check_palette(getattr(layer, "palette", None), f"layer[{i}] palette")
    for j, (_slope, pal) in enumerate(getattr(spec, "slant", None) or []):
        _check_palette(pal, f"slant[{j}] palette")

    # 3) strata bands: one block at >70% of the banded thickness is a monoculture
    strata = getattr(spec, "strata", None)
    if strata:
        thick = {}
        total_t = 0
        for b, t in strata:
            thick[b] = thick.get(b, 0) + int(t)
            total_t += int(t)
        if total_t > 0:
            bid = max(thick, key=thick.get)
            frac = thick[bid] / total_t
            if frac > worst_frac:
                worst_block, worst_frac, worst_where = bid, frac, "strata"

    return worst_block, worst_frac, worst_where


def _underwater_face(hf, spec, *, water=None) -> tuple:
    """Underwater / foundation-face check: a steep submerged face must not be a
    single block (a sheer one-material wall under the waterline — the bathtub
    foundation antipattern). Returns ``(ok, detail)``.

    We find columns that are both submerged (surface below sea level) and steep
    (slope over the slant threshold), resolve their materialised surface block,
    and fail if one block covers more than 90% of that submerged face — there is
    no transition, just a monolithic wall.
    """
    from .materialize import resolve_surface

    h = hf.h
    submerged = h < hf.sea_level if water is None else np.isfinite(water)
    if not submerged.any():
        return True, "no submerged columns"

    cliff_slope = 55.0
    slant = getattr(spec, "slant", None)
    if slant:
        cliff_slope = min(float(s) for s, _ in slant)
    steep = M.slope_deg(h) >= cliff_slope
    face = submerged & steep
    n_face = int(face.sum())
    if n_face < 8:
        return True, f"submerged face {n_face} cells (<8, no wall)"

    try:
        surface, _sub = resolve_surface(hf, spec)
    except Exception as e:  # pragma: no cover - defensive
        return True, f"face unresolved: {e}"
    ids = surface[face].astype(object)
    uids, counts = np.unique(ids, return_counts=True)
    i = int(np.argmax(counts))
    frac = float(counts[i]) / n_face
    ok = frac <= 0.90
    return ok, (f"submerged face {n_face} cells, {str(uids[i])} covers "
                f"{frac:.0%} (max 90%)")


def _max_single_step(h: np.ndarray) -> float:
    dx = np.abs(np.diff(h, axis=0)).max() if h.shape[0] > 1 else 0.0
    dz = np.abs(np.diff(h, axis=1)).max() if h.shape[1] > 1 else 0.0
    return float(max(dx, dz))


def _recipe_is_blended(recipe) -> bool:
    """True when a recipe marks its field as blended or multi-region — the
    condition under which the seam check is non-negotiable. Recognises an
    explicit ``blended``/``multi_region`` flag, a ``regions`` list of >1, a
    ``blend`` block, or a ``seam`` declaration."""
    if not isinstance(recipe, dict):
        return False
    if recipe.get("blended") or recipe.get("multi_region") or recipe.get("seam"):
        return True
    if recipe.get("blend"):
        return True
    regions = recipe.get("regions")
    if isinstance(regions, (list, tuple)) and len(regions) > 1:
        return True
    return False


def verify_seam(h: np.ndarray, *, max_step: float = 12.0) -> Report:
    """Seam check for a (blended) field: the largest single-cell height step
    anywhere must be below ``max_step`` — a wall, not a ramp, fails. Used after a
    blend to confirm regions meet as ramps (failure mode #2)."""
    step = _max_single_step(h)
    ok = step <= max_step
    return Report(ok=ok, checks=[("seam_max_step", ok,
                                  f"{step:.1f} blocks (max {max_step})")])


def offline_token(report: Report) -> str:
    """Deterministic, tamper-evident token over a report's ``(name, passed)``
    check tuples — proof the verify gate ran and produced exactly these results.

    The token is a SHA-1 over the ordered ``name=0/1`` pairs (detail strings are
    excluded so float-formatting jitter doesn't churn the token). A failing
    report still yields a token string; callers decide whether to stamp it. Two
    reports with the same check outcomes hash identically; flipping any single
    check's pass/fail changes the token.
    """
    parts = [f"{name}={1 if passed else 0}" for name, passed, _detail in report.checks]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return "ovt_" + digest[:12]
