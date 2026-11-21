"""Turn a verified terrain recipe into payloads for the Ashlar placement path.

``emit_world`` runs the whole pipeline for a recipe and returns a dict of ready
payloads:
  columns   → a block_fill_columns(_strata) plan (the bulk mass)
  biomes    → a list of level_fill_biome rectangles
  scatter   → a list of (x,y,z,kind,id) placements for the batch feature tool
  verify    → the offline verify Report (the gate; emit_world raises if it fails
              unless allow_unverified=True)

``write_payloads`` writes those payloads to JSON next to a prefix. The Ashlar
output step, which turns them into placer commands, lives in ``ashlar_emit.py``.
"""
from __future__ import annotations

import json

from .recipe import build_field
from .materialize import MaterialSpec, to_columns_plan
from .climate import BiomeField
from .scatter import scatter_for_biomes
from . import verify as _verify


class VerifyError(RuntimeError):
    pass


def emit_world(recipe: dict, *, allow_unverified: bool = False) -> dict:
    """Evaluate a recipe → field, run the verify gate, then emit columns + biomes
    + scatter payloads. ``recipe`` extends the build recipe (see recipe.py) with
    optional ``material`` (a MaterialSpec spec) and ``scatter``/``biomes`` flags."""
    hf = build_field(recipe)
    origin = recipe.get("origin", [0, 0, 0])
    ox, oz = int(origin[0]), int(origin[-1])
    dim = recipe.get("dimension", "minecraft:overworld")

    # material spec: explicit, or a natural default from masks. Built BEFORE the
    # gate so verify sees it — the spec drives the palette-monoculture and
    # underwater-face checks, and a blended/multi-region recipe folds in the seam
    # check. (Previously emit ran verify(hf) bare, so those checks never ran on
    # the emit path despite the gate advertising them — closed here.)
    mat = recipe.get("material")
    if mat:
        spec = _material_from_spec(mat, hf, recipe=recipe)
    else:
        snow_y = recipe.get("snow_y")
        spec = MaterialSpec.natural(hf, snow_y=snow_y)
        if recipe.get("strata"):
            spec.strata = [(s["block"], int(s["thickness"])) for s in recipe["strata"]]

    report = _verify.verify(hf, spec=spec, recipe=recipe)
    if not report.ok and not allow_unverified:
        raise VerifyError(str(report))

    columns = to_columns_plan(hf, spec, origin=(ox, oz), dimension=dim)

    biomes = None
    scatter = None
    if recipe.get("biomes", True):
        bf = BiomeField(hf, seed=int(recipe.get("seed", 0)))
        biomes = bf.to_biome_fill_plan(origin=(ox, oz))
        if recipe.get("scatter", True):
            scatter = scatter_for_biomes(hf, bf, origin=(ox, oz),
                                         seed=int(recipe.get("seed", 0)))

    return {"field": hf, "verify": report, "columns": columns,
            "biomes": biomes, "scatter": scatter}


def _material_from_spec(mat: dict, hf, recipe: dict | None = None) -> MaterialSpec:
    """Build a MaterialSpec from a recipe's ``material`` block.

    Three forms are supported. A ``belt_regions`` list selects the per-arc form
    (``_belt_region_spec``): each region's palette is keyed to a position along
    the belt centerline, so the colour morphs region→region around a blended
    loop the way the shape does (red rock → granite → alpine → forest). The
    simple declarative form ``{surface, snow_y, cliff_slope, beach, strata}``
    builds the default masks + a global steep-face slant (good for grass/rock
    terrain).

    A *layered* form is selected when any of ``snow_palette`` / ``cliff_palette``
    / ``lake_floor`` is given. It expresses the whole surface as an ordered,
    mask-driven ``Layer`` stack (first match wins per column) and **drops** the
    global slant override, so snow/ice can clad a steep horn above the snowline
    instead of being repainted to rock everywhere it is steep — the realistic
    glacial story. Order: lake floor (submerged) → snow/ice (above ``snow_y``) →
    rock cliffs (steep, below the snowline) → base flank mix. The lake-floor mix
    keeps the submerged face multi-block so the GATE-A underwater_face check
    still passes."""
    from .materialize import Layer
    from . import masks as M

    if "belt_regions" in mat:
        return _belt_region_spec(mat, hf, recipe)

    layered = any(k in mat for k in ("snow_palette", "cliff_palette", "lake_floor"))

    if not layered:
        spec = MaterialSpec.natural(
            hf,
            surface=mat.get("surface"),
            snow_y=mat.get("snow_y"),
            cliff_slope=mat.get("cliff_slope", 50.0),
            beach=mat.get("beach", True),
        )
        if mat.get("strata"):
            spec.strata = [(s["block"], int(s["thickness"])) for s in mat["strata"]]
        return spec

    sea = hf.sea_level
    snow_y = mat.get("snow_y")
    cliff_slope = float(mat.get("cliff_slope", 50.0))
    steep = M.mask_slope(hf.h, lo=cliff_slope)
    submerged = M.mask_y(hf.h, "<", sea)

    layers = []
    # 1) turquoise / custom lake floor — every submerged column.
    lake = mat.get("lake_floor")
    if lake:
        layers.append(Layer(mask=submerged, palette=dict(lake),
                            subsurface="minecraft:gravel"))
    # 2) snow / ice cap — high ground, above any submerged/lake cells. Clads the
    #    horns even where steep (glacial horns are snow- and ice-covered).
    snow_pal = mat.get("snow_palette")
    if snow_pal and snow_y is not None:
        snow_mask = M.mask_y(hf.h, ">", snow_y) & ~submerged
        layers.append(Layer(mask=snow_mask, palette=dict(snow_pal),
                            subsurface="minecraft:dirt"))
    # 3) rock cliffs — steep faces below the snowline (and above water).
    cliff_pal = mat.get("cliff_palette")
    if cliff_pal:
        cliff_mask = steep & ~submerged
        if snow_y is not None:
            cliff_mask = cliff_mask & M.mask_y(hf.h, "<=", snow_y)
        layers.append(Layer(mask=cliff_mask, palette=dict(cliff_pal),
                            subsurface="minecraft:stone"))

    spec = MaterialSpec(layers=layers, base=mat.get("surface"),
                        subsurface=mat.get("subsurface", "minecraft:dirt"))
    spec.slant = []                       # ordered layers do the slant's job
    if mat.get("strata"):
        spec.strata = [(s["block"], int(s["thickness"])) for s in mat["strata"]]
    return spec


def _belt_region_spec(mat: dict, hf, recipe: dict | None) -> MaterialSpec:
    """Per-arc material for a blended belt loop: each region's palette is keyed
    to a position ``s`` along the belt centerline.

    ``mat["belt_regions"]`` is a list of ``{s, surface, subsurface?, cliff?,
    snow_y?, snow?}``. Every grid cell is assigned to the region whose ``s`` is
    nearest in *circular* arc-distance (so a closed loop wraps cleanly), giving
    colour zones that mirror the shape keypoints. Within a region the layer
    order is snow (above ``snow_y``) → cliff (steep, below the snowline) →
    surface, so a red-rock wall reads as red rock and an alpine horn keeps its
    snow cap. The region masks partition the grid, so the global ``slant`` is
    dropped (the per-region cliff layers do its job) — the same reasoning as the
    layered glacial form. The centerline is rebuilt from ``recipe["belt"]``."""
    import numpy as np
    from .materialize import Layer
    from . import masks as M
    from .field import Centerline

    belt = (recipe or {}).get("belt") or {}
    if not belt.get("centerline"):
        raise VerifyError("belt_regions material needs recipe['belt']['centerline']")
    cl = Centerline([tuple(p) for p in belt["centerline"]],
                    closed=bool(belt.get("closed", False)))
    nx, nz = hf.nx, hf.nz
    X, Z = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
    s, _perp = cl.query(X, Z)
    sf = (s / cl.length) if cl.length else np.zeros_like(s)

    regions = mat["belt_regions"]
    centers = np.array([float(r["s"]) for r in regions])
    diff = np.abs(sf[..., None] - centers[None, None, :])        # (nx, nz, R)
    circ = np.minimum(diff, 1.0 - diff)                          # wrap on [0, 1)
    nearest = np.argmin(circ, axis=-1)                           # (nx, nz)

    cliff_slope = float(mat.get("cliff_slope", 50.0))
    steep = M.mask_slope(hf.h, lo=cliff_slope)
    above_water = ~M.mask_y(hf.h, "<", hf.sea_level)

    layers: list = []
    for ri, r in enumerate(regions):
        region = nearest == ri
        snow_y = r.get("snow_y")
        if snow_y is not None and r.get("snow"):
            snow_mask = region & M.mask_y(hf.h, ">", snow_y) & above_water
            layers.append(Layer(mask=snow_mask, palette=dict(r["snow"]),
                                subsurface=r.get("snow_subsurface", "minecraft:dirt")))
        if r.get("cliff"):
            cliff_mask = region & steep & above_water
            if snow_y is not None:
                cliff_mask = cliff_mask & M.mask_y(hf.h, "<=", snow_y)
            layers.append(Layer(mask=cliff_mask, palette=dict(r["cliff"]),
                                subsurface=r.get("cliff_subsurface",
                                                 r.get("subsurface", "minecraft:stone"))))
        layers.append(Layer(mask=region, palette=dict(r["surface"]),
                            subsurface=r.get("subsurface", "minecraft:dirt")))

    spec = MaterialSpec(layers=layers,
                        base=mat.get("surface") or dict(regions[0]["surface"]),
                        subsurface=mat.get("subsurface", "minecraft:dirt"))
    spec.slant = []                       # the per-region cliff layers do its job
    if mat.get("strata"):
        spec.strata = [(s2["block"], int(s2["thickness"])) for s2 in mat["strata"]]
    return spec


def write_payloads(payloads: dict, prefix: str) -> dict:
    """Write columns/biomes/scatter payloads to JSON files next to ``prefix``.
    Returns the file paths. (The field/verify objects are not serialised here.)"""
    paths = {}
    if payloads.get("columns"):
        p = f"{prefix}_columns.json"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payloads["columns"], fh)
        paths["columns"] = p
    if payloads.get("biomes"):
        p = f"{prefix}_biomes.json"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payloads["biomes"], fh)
        paths["biomes"] = p
    if payloads.get("scatter"):
        p = f"{prefix}_scatter.json"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump([list(t) for t in payloads["scatter"]], fh)
        paths["scatter"] = p
    return paths
