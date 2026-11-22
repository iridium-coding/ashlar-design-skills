"""Terrain recipe persistence — Pillar 1's durable artifact (failure-#4 cure).

A recipe is one JSON document that fully describes a terrain build: the sampler
graph, the Y mapping, erosion params, seeds, and the material spec. Re-sculpting
edits one node and re-evaluates — every other detail is reproduced bit-for-bit,
so a structural fix no longer discards accreted richness.

    recipe = {
      "version": 1,
      "origin": [x, y, z], "nx": 256, "nz": 256, "sea_level": 63, "seed": 7,
      "graph": { ...sampler tree... },
      "erosion": { "thermal": {...}, "hydraulic": {...} },   # optional
      "material": { ...MaterialSpec spec... },               # optional
    }
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .field import HeightField, Centerline
from .site import auto_band, blend_to_existing, ground_for


RECIPE_VERSION = 1


def build_field(recipe: dict, project_dir: Path | None = None) -> HeightField:
    """Evaluate a recipe into a HeightField: graph and/or belt, then erosion.

    The base surface comes from a sampler ``graph`` (``from_graph``) and/or a
    ``belt`` section that sculpts a continuous blended corridor/ring via
    ``HeightField.belt_from_path`` — the durable, recipe-expressible form of the
    fix for failure mode #2 (seams). A recipe may carry both (graph base, belt
    on top), the belt alone (a flat base is created), or the graph alone.

    ``belt`` keys: ``centerline`` (list of ``[x, z]`` grid points), ``closed``,
    ``keypoints`` (each ``{s, peak, rise, base}`` — ``s`` the fractional
    arc-position 0..1), and the cross-section params ``corridor_half``, ``fall``,
    ``interior_level``, ``roughness``, ``roughness_freq``. An optional
    ``micro_relief`` (``{amplitude, octaves, base_freq}``) adds a low whole-field
    FBM so the otherwise-flat corridor/interior gently rolls (keeps the verify
    ziggurat score down and reads as natural ground).

    After erosion, ``pads`` (each ``{center: [x, z] world, half: [hx, hz], level,
    shoulder?}``) are flattened in, then a ``site`` key (``{read, band?}``;
    ``band`` an int or ``"auto"``) blends the outer ring into the existing ground
    read from ``project_dir / site["read"]``."""
    nx, nz = int(recipe["nx"]), int(recipe["nz"])
    sea = float(recipe.get("sea_level", 62))
    seed = int(recipe.get("seed", 0))
    belt = recipe.get("belt")

    if recipe.get("graph"):
        hf = HeightField.from_graph(recipe["graph"], nx, nz, sea_level=sea, seed=seed)
    elif belt:
        # belt-only: belt_from_path overwrites h, so any flat base is fine; use
        # the first keypoint's base so an un-belted cell reads sensibly.
        base0 = sea
        kps = belt.get("keypoints") or []
        if kps:
            base0 = float(kps[0].get("base", sea))
        hf = HeightField(nx, nz, sea_level=sea, base=base0)
    else:
        raise ValueError("recipe needs a 'graph' and/or a 'belt' section")

    if belt:
        cl = Centerline([tuple(p) for p in belt["centerline"]],
                        closed=bool(belt.get("closed", False)))
        keypoints = [(float(k["s"]),
                      {kk: k[kk] for kk in ("peak", "rise", "base") if kk in k})
                     for k in belt["keypoints"]]
        hf.belt_from_path(
            cl, keypoints,
            fall=float(belt.get("fall", 24.0)),
            interior_level=belt.get("interior_level"),
            corridor_half=float(belt.get("corridor_half", 0.0)),
            roughness=float(belt.get("roughness", 0.0)),
            roughness_freq=float(belt.get("roughness_freq", 0.05)),
            seed=seed,
        )
        # a light 1-2-1 blur ramps any single-cell step left by high-frequency
        # roughness or a sharp centerline corner, so the field stays seam-free
        # (the in-world + offline seam checks want a ramp, never a wall).
        smooth = int(belt.get("smooth", 0))
        if smooth:
            hf.smooth(smooth)

    micro = recipe.get("micro_relief")
    if micro:
        hf.add_fbm(float(micro.get("amplitude", 1.5)),
                   octaves=int(micro.get("octaves", 3)),
                   base_freq=float(micro.get("base_freq", 0.03)),
                   seed=seed + 99)

    ero = recipe.get("erosion") or {}
    if "thermal" in ero:
        hf.erode_thermal(**ero["thermal"])
    if "hydraulic" in ero:
        hf.erode_hydraulic(**ero["hydraulic"])
    if "fluvial" in ero:
        hf.carve_rivers_from_flow(**ero["fluvial"])

    pads = recipe.get("pads") or []
    ox, oz = (int(v) for v in (recipe["origin"][0], recipe["origin"][2])) if pads else (0, 0)
    for pad in pads:
        hf.build_pad(center=(float(pad["center"][0]) - ox, float(pad["center"][1]) - oz),
                     half=(float(pad["half"][0]), float(pad["half"][1])),
                     level=float(pad["level"]), shoulder=float(pad.get("shoulder", 9.0)))

    site = recipe.get("site")
    if site:
        if project_dir is None:
            raise ValueError("a recipe with a 'site' needs a project_dir to resolve its read")
        _, _, ground = ground_for(recipe, project_dir)
        band = site.get("band", "auto")
        band = auto_band(hf.h, ground) if band == "auto" else int(band)
        hf = blend_to_existing(hf, ground, band)
    return hf


def save(recipe: dict, path: str) -> None:
    recipe = dict(recipe)
    recipe.setdefault("version", RECIPE_VERSION)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(recipe, fh, indent=2)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        recipe = json.load(fh)
    v = recipe.get("version", 1)
    if v > RECIPE_VERSION:
        raise ValueError(f"recipe version {v} newer than supported {RECIPE_VERSION}")
    return recipe
