"""The terrain toolkit — author a heightfield from a recipe, *render-verify it
offline*, then emit verified payloads (columns, biomes, scatter). The 2.5-D
counterpart of the ``voxel`` toolkit.

    from terrain import recipe, render_views

    hf = recipe.build_field(spec)                 # spec: a recipe dict (see recipe.py)
    render_views(hf, "/abs/scratch/island")       # Read the 3 PNGs, then tune
    # emit: ashlar_emit.emit_ashlar writes the mc_build phase files and plan rows
    # that the exec-ashlar skill places
"""
from .noise import ValueNoise2D, fbm
from .field import HeightField, Centerline, smoothstep
from .erosion import hydraulic, thermal
from .render import render_hillshade, render_relief, render_profile, render_views
from .materialize import (MaterialSpec, Layer, to_columns_plan, write_columns_plan,
                          resolve_surface)
from .close import close_belt_end
from .erosion import hydraulic, thermal, fluvial_rivers, flow_accumulation
from .render import render_slope, render_eye_level
from . import masks, blend, verify, recipe, climate, scatter, emit
from .climate import BiomeField
from .samplers import from_spec as sampler_from_spec

# Blended multi-region terrain — one continuous field, never butted segments:
#     loop = Centerline([(20,20),(140,20),(140,108),(20,108)], closed=True)
#     hf.belt_from_path(loop, [(0.0, dict(base=64, peak=40, rise=28)),   # red rock
#                              (0.25,dict(base=66, peak=70, rise=20)),   # alpine
#                              (0.5, dict(base=64, peak=34, rise=30)),   # forest
#                              (0.75,dict(base=66, peak=70, rise=20))],  # alpine
#                       corridor_half=4, interior_level=66)             # protect the rail

__all__ = [
    "ValueNoise2D", "fbm",
    "HeightField", "Centerline", "smoothstep",
    "hydraulic", "thermal",
    "render_hillshade", "render_relief", "render_profile", "render_views",
    # new mask-driven, block_fill_columns materialisation (Pillar 2)
    "MaterialSpec", "Layer", "to_columns_plan", "write_columns_plan", "resolve_surface",
    "close_belt_end",
    # new subsystems
    "masks", "blend", "verify", "recipe", "climate", "scatter", "emit",
    "BiomeField", "fluvial_rivers", "flow_accumulation",
    "render_slope", "render_eye_level", "sampler_from_spec",
]
