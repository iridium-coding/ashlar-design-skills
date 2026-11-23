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

from .field import Centerline, HeightField
from .site import (
    auto_band,
    blend_to_existing,
    drain_bodies,
    ground_for,
    hold_shores,
    integer_level,
)

RECIPE_VERSION = 1


def build_field(recipe: dict, project_dir: Path | None = None,
                info: dict | None = None) -> HeightField:
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

    A recipe with a ``site`` (``{read, band?}``; ``band`` an int or ``"auto"``, computed
    on the field before pads) blends its outer ring into the existing ground read from
    ``project_dir / site["read"]``, then stamps ``pads`` (each ``{center: [x, z] world,
    half: [hx, hz], level, shoulder?}``; integer ``level``): all shoulders are applied,
    then every footprint is re-stamped at its level. With a site a footprint, or a column
    nearer than ``shoulder`` to one, on the outer ring is an error; pads overlapping at
    different levels are always one. Without a site the pads come right after erosion.
    ``"hold_shores": true`` (site only) then lifts banks of existing liquid outside the
    pad footprints (`site.hold_shores`); ``info``, when given, gets ``held_columns``.
    A site recipe without ``sea_level`` runs with ``hf.sea_level`` set below the lowest
    height (never a water level); with it, ``sea_level`` must be an integer."""
    nx, nz = int(recipe["nx"]), int(recipe["nz"])
    sea = float(recipe.get("sea_level", 62))
    seed = int(recipe.get("seed", 0))
    belt = recipe.get("belt")
    site_cfg = recipe.get("site")
    if "drain" in recipe and not site_cfg and recipe["drain"] != []:
        raise ValueError("drain needs a recipe with a site read")
    pads = _parse_pads(recipe.get("pads") or [])
    if "hold_shores" in recipe:
        if not isinstance(recipe["hold_shores"], bool):
            raise ValueError(f"hold_shores must be true or false, got {recipe['hold_shores']!r}")
        if recipe["hold_shores"] and not site_cfg:
            raise ValueError("hold_shores needs a recipe with a site")
    if site_cfg:
        if project_dir is None:
            raise ValueError("a recipe with a 'site' needs a project_dir to resolve its read")
        if "sea_level" in recipe:
            integer_level(recipe["sea_level"], "sea_level")
        elif belt:
            for i, k in enumerate(belt.get("keypoints") or []):
                if "base" not in k:
                    raise ValueError(f"a site recipe without sea_level needs belt.keypoints[{i}].base")
            if belt.get("interior_level") is None:
                raise ValueError("a site recipe without sea_level needs belt.interior_level")
    no_sea = bool(site_cfg) and "sea_level" not in recipe

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

    if no_sea:
        hf.sea_level = float(np.floor(hf.h.min()) - 8)
    ero = recipe.get("erosion") or {}
    if "thermal" in ero:
        hf.erode_thermal(**ero["thermal"])
    if "hydraulic" in ero:
        hf.erode_hydraulic(**ero["hydraulic"])
    if "fluvial" in ero:
        hf.carve_rivers_from_flow(**ero["fluvial"])

    origin = recipe.get("origin") or [0, 0, 0]
    ox, oz = int(origin[0]), int(origin[2])
    ground_site = None
    drains = []
    if site_cfg:
        ground_site, _surf, ground = ground_for(recipe, project_dir)
        drains = drain_bodies(ground_site, recipe)
        band = site_cfg.get("band", "auto")
        band = auto_band(hf.h, ground) if band == "auto" else int(band)
        hf = blend_to_existing(hf, ground, band)

    footprints = _stamp_pads(hf, pads, ox, oz, on_site=bool(site_cfg))

    held = 0
    if recipe.get("hold_shores"):
        skip = np.any(footprints, axis=0) if footprints else None
        held_h = hold_shores(hf.h, ground_site, origin=(ox, oz), skip=skip,
                             excluded=(cell for body in drains for cell in body.cells))
        held = int(np.count_nonzero(held_h != hf.h))
        hf.h = held_h
    if info is not None:
        info["held_columns"] = held
    if no_sea:
        hf.sea_level = float(np.floor(hf.h.min()) - 8)
    return hf


def _parse_pads(pads: list) -> list[dict]:
    out = []
    for i, pad in enumerate(pads):
        out.append({"center": (float(pad["center"][0]), float(pad["center"][1])),
                    "half": (float(pad["half"][0]), float(pad["half"][1])),
                    "level": integer_level(pad["level"], f"pad {i} level"),
                    "shoulder": float(pad.get("shoulder", 9.0))})
    return out


def _pad_distance(shape, center, half, ox: int, oz: int) -> np.ndarray:
    """HeightField.build_pad's own distance from the footprint, in grid coordinates."""
    x, z = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    dx = np.maximum(np.abs(x - (center[0] - ox)) - half[0], 0.0)
    dz = np.maximum(np.abs(z - (center[1] - oz)) - half[1], 0.0)
    return np.hypot(dx, dz)


def _stamp_pads(hf: HeightField, pads: list[dict], ox: int, oz: int, *,
                on_site: bool) -> list[np.ndarray]:
    """Apply every pad's shoulder, then re-stamp each footprint at its level. Returns the
    footprint masks. Errors: overlap at different levels; with a site, a footprint or a
    column within its shoulder on the outer ring."""
    shape = (hf.nx, hf.nz)
    dists = [_pad_distance(shape, p["center"], p["half"], ox, oz) for p in pads]
    feet = [d == 0.0 for d in dists]
    ring = np.zeros(shape, bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    for i, (p, d) in enumerate(zip(pads, dists)):
        if on_site and (ring & ((d == 0.0) | (d < p["shoulder"]))).any():
            raise ValueError(
                f"pad {i} (center {list(p['center'])}, shoulder {p['shoulder']:g}) reaches the "
                f"edge of the field; keep it at least its shoulder away from the box edge")
        for j in range(i):
            both = feet[i] & feet[j]
            if p["level"] != pads[j]["level"] and both.any():
                cx, cz = (int(v) for v in np.argwhere(both)[0])
                raise ValueError(f"pads {j} and {i} overlap at different levels "
                                 f"({pads[j]['level']} and {p['level']}) at ({cx + ox}, {cz + oz})")
    for p in pads:
        hf.build_pad(center=(p["center"][0] - ox, p["center"][1] - oz), half=p["half"],
                     level=float(p["level"]), shoulder=p["shoulder"])
    for p, foot in zip(pads, feet):
        hf.h[foot] = float(p["level"])
    return feet


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
