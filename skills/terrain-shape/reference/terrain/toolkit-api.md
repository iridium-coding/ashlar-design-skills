# Terrain Toolkit API

From the workspace containing `.minecraft-builder/`, run the launcher from the terrain-shape skill folder. Replace SKILL below with its absolute path. Recipe, model and data paths stored in a project are relative to that project.

- Claude Code: use `${CLAUDE_SKILL_DIR}` as the skill folder.
- Codex: use the folder containing this skill's SKILL.md.
- Otherwise: locate the installed terrain-shape skill folder.

```sh
uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python "$SKILL/scripts/terrain.py" --help
```

Replace `--help` with one of the argument lists below. Arguments in capitals denote your files, numbers and coordinates. The launcher adds this skill's terrain package and the monument skill's voxel package to its Python path.

## Commands

| Arguments after terrain.py | Input and output |
|---|---|
| `ids --version V [--features A,B] [--biomes A,B]` | Check candidate IDs against the selected version list. Run with the version from `mc_status` and disclose any fallback to an older list. |
| `survey --site DIR --box X1 Y1 Z1 X2 Y2 Z2` | Exact site read and inclusive inner terrain box. Reports ranges, tree count and non-natural block counts. A non-natural block returns 1. Review the finding before proceeding. |
| `field RECIPE --project DIR` | Build and verify the live-site field offline. On success save the draft recipe, expected surface (F6), five PNGs and verify report under `terrain/previews/`. Report per-body drain descriptors for review. Produces no executable phases. |
| `emit RECIPE --project DIR --first-phase N [--standalone] [--drain-approved BODY_ID]…` | Recheck and emit terrain mass, forms and flow, canonical `terrain/<element>.*` files including expected surface JSON and `terrain/<element>.plan-rows.toon`. Repeat the flag once per approved ID, for example `--drain-approved FIRST_ID --drain-approved SECOND_ID`. The standalone option writes a complete plan. |
| `compare EXPECTED HEIGHTS [--tolerance N] [--min-ratio R]` | Compare the expected surface with a fresh post-build heights file over every unskipped column. Defaults to exact Y and a 0.98 passing fraction. |
| `seam --site POST_BUILD_F1 --from X Z --to X Z --outward DIR [--max-step N]` | Compare actual ground beneath trees and liquid to the adjacent outward ground. Capture exact columns covering both sides of the edge. DIR is x, -x, z or -z, perpendicular to the edge. Default maximum step is one block. |
| `seam HEIGHTS --from X Z --to X Z --outward DIR [--max-step N]` | Quick screen using post-build ground heights. Ambiguous tree evidence requires a fresh exact site read and the `--site` form above. |

The planting and grading skills use these additional command interfaces. Check the installed launcher's help for availability.

| Arguments after terrain.py | Result |
|---|---|
| `plant (--recipe RECIPE or --site DIR --box X1 Z1 X2 Z2) --project DIR --phase N --mix MIX.json [--version V] [--biome-change ID]` | Use one input mode. Plan features on the designed field or observed soil. Only a separately approved biome ID may produce a biome phase. Show the actual box after expanding x/z to full 16-block chunks and y to full four-block biome cells before asking for that approval. |
| `tree --preset P [--set key=value …] --name N --out DIR` | Generate a vegetation module and preview images. |
| `tree-place --module FILE --points FILE (--surface FILE or --site DIR) --phase N --project DIR` | Use one source of heights to anchor rotated trees. Generate placements and stamp the tree phase. |
| `apron --site DIR --box X1 Z1 X2 Z2 [--protect X1 Z1 X2 Z2 [--pad Y]]… --project DIR --element E --first-phase N [--palette STATS.txt] [--standalone]` | Preview and prepare grading from measured ground, protect footprints, hold shores, report cut/fill and seam profiles. |
| `cave DESIGN --project DIR --first-phase N [--preview] [--standalone]` | Check a cave design (`terrain-cave`) against its site read and write carve, dress, pool and light phases, a features commands file, plan rows, a report and previews; `--preview` writes only the report and previews. |
| `cave-check DESIGN --site POST_BUILD_F1 [--project DIR]` | Check a fresh read of a built cave: ceilings, spans, light and roof. Prints JSON; exits 1 when a check fails. |

## Site recipe

`element` names the files. `origin: [x1, 0, z1]`, `nx` and `nz` describe the inclusive horizontal footprint. Set `site: {"read":"site","band":"auto"}` or give an integer blend width. Use a seeded `graph` or `belt`. A live site without `sea_level` has no blanket sea. Supply all keypoint bases and the interior level in a belt without a sea level.

- `pads: [{"center":[x,z],"half":[hx,hz],"level":y,"shoulder":9}]` uses world coordinates. Keep pad shoulders within the outer ring.
- `water: [{"at":[x,z],"level":y}]` floods a connected planned basin. Use integer levels. A descending river needs separate level reaches. `falls: [{"at":[x,y,z]}]` marks flowing lip sources. Use an observed sea or basin level only where wanted. `hold_shores: true` holds existing banks.
- `forms: [{"name":"arch","model":"arch.npy","palette":"arch.json","origin":[x,y,z],"mode":"carve"}]` uses project-relative assets. Modes are carve and build. `material.strata_top` anchors strata at an absolute Y.
- `drain: [{"at":[x,z]}]` requests a preview of a complete body in the original site read. A seed, recipe entry or successful preview supplies no approval. See `reference/terrain/water.md`.

## Sampler graph (`terrain.samplers`)

Author terrain shape as a nestable dict/JSON node tree; `from_spec(spec).eval(ctx)` evaluates it. Or
use `HeightField.from_graph(spec, nx, nz, sea_level=, seed=)`.

| Group | Nodes |
|---|---|
| sources | `Constant(value)`, `Noise(frequency, seed)`, `Cellular(frequency, ret=F1/F2/F2F1/inv_F1, jitter, seed)` |
| fractal | `FBM(frequency, octaves, lacunarity, gain, seed)`, `Ridged(... gain, offset, h)` (real Musgrave), `Billow(...)`, `Hybrid(... h, offset)` |
| warp | `DomainWarp(src, amplitude, frequency, levels, seed)` (2-vector) |
| arithmetic | `Add/Sub/Mul/Div/Min/Max(a, b)`, `Blend(a, b, selector, mid, rng)` |
| mutators | `Scale(src, factor)`, `Bias(src, offset)`, `Clamp(src, lo, hi)`, `Linear(src, in_lo, in_hi, out_lo, out_hi)`, `CubicSpline(src, points=[[x,y]...])`, `Posterize(src, steps)`, `Terrace(src, steps, smoothing, mask)` |
| geometry | `Distance(center, radius, inner, sx, sz)` (radial falloff), `ImageDEM(path, zoom)` (DEM), `BeltCoord(which=s/perp)` |

A bare number is sugar for `Constant`. Recipes round-trip via `node.to_spec()`.

## HeightField (`terrain.HeightField`)

- `HeightField(nx, nz, sea_level=62, base=62)` - `.h` is the `(nx,nz)` world-Y array.
- **author:** `from_graph(spec, nx, nz, sea_level=, seed=, centerline=)`, `add_fbm(...)`,
  `radial_falloff(...)`, `carve_lake/carve_river/build_pad(...)`, `belt_from_path(centerline, keypoints, ...)`, `apply_spline_remap(points)`, `from_image(path, ...)`.
- **shape:** `smooth(iterations)`, `gaussian_smooth(sigma, mask=)`, `melt(mask=, strength=, amount=)`,
  `distort(scale, distance, seed)`, `weld(mask, strength=)`, `erode_thermal(...)`,
  `erode_hydraulic(... pad_cells=, height_falloff=, sea_level=)`, `carve_rivers_from_flow(threshold, depth)`, `clamp(min_y, max_y)`.
- **analysis:** `slope_deg()`, `aspect_deg()`, `curvature()`, `dist_to_water()`, `mask_slope(lo, hi)`, `mask_y(op, y)`, `summary()`.
- **io:** `save_npy/load_npy`.
- **close a belt end (`terrain.close_belt_end`):** `close_belt_end(field, centerline, keypoints, end, close_dist=, corridor_half=, fall=, interior_level=, floor=, regen=)` closes one end (`"low"`/`"high"`) of a `belt_from_path` canyon so it blends with the side walls instead of reading as a pasted-in headwall. It pinches the belt's own cross-section shut, re-applies the SAME noise + erosion through the caller's `regen(hf)` callback (identical seeds, global grid coords → the seam phase aligns), and merges with `np.maximum`. Re-run the same materializer over the end window after.

## Masks (`terrain.masks`)
`slope_deg(h)`, `aspect_deg(h)`, `curvature(h)`, `dist_to_water(h, sea)`, and boolean
`mask_slope/mask_y/mask_band/mask_curv/mask_near_water`. Combine with numpy `& | ~`.

## Blend (`terrain.blend`) - the seam fix
`box_blur_blend(label_grid, height_fns, radius)`, `sparse_convolution_blend(shape, seeds, height_fns, k)`, `weld(h, band_mask, strength)`, `pad_crop_smooth(h, sigma, pad, edge_heights)`. Blend radius must scale with the height delta across the seam (a ~46-block delta needs radius ~14+).

## Erosion (`terrain.erosion`)
`hydraulic(h, droplets, ..., pad_cells, height_falloff, sea_level)`, `thermal(h, iterations, talus, factor)`, `flow_accumulation(h)`, `fluvial_rivers(h, threshold, depth, sea_level)`.

## Climate (`terrain.BiomeField`)
Use `BiomeField(hf, seed=, latitude=)`, `.climate()`, `.assign(boundary_jitter=)` and `.palette_for(biome_id)` for offline palettes and planting. `BIOME_CONTENT` maps biome to surface mixes, feature IDs and density. A field's elevation labels never select a world biome to paint.

## Scatter (`terrain.scatter`)
`density_map(hf, prefer_flat, near_water, height_band, base, avoid_steep_deg)`, `poisson(density, r_min, r_max, seed, k)` (variable-density blue noise), `assign_species(points, weights, seed)`, `scatter_for_biomes(hf, biome_field, origin, seed)` -> `[(x,y,z,"feature",id), ...]`.

## Materialize (`terrain.materialize`)
- `MaterialSpec(layers, base, subsurface, subsurface_depth, stone, water, strata, seed)` with
  `MaterialSpec.natural(hf, surface=, snow_y=, cliff_slope=, beach=)` for a sensible default.
- `Layer(mask, palette, subsurface)` - first match wins; `.slant = [(min_slope_deg, palette)]` rocks cliffs.

## Live terrain modules

- `terrain.site` loads the exact column read with `load_site` and the three height grids with `load_heights`. `surfaces`, `find_trees` and `unnatural_blocks` describe measured ground, trees and potential structures. `ground_for` and `blend_to_existing` join the field to the site. `water_levels` plans floods. `liquid_levels` finds retained liquid resting on the bed. `drain_bodies` resolves complete seeded bodies.
- `terrain.recipe.build_field(recipe, project_dir)` applies graph/belt, erosion, blend, pads and optional shore hold. `terrain.live.materialize_live` resolves changes to solid, liquid and trees. `split_columns` tiles the changes and `greedy_fills` merges identical states. `liquid_violations` checks newly exposed liquid and `expected_surface` accounts for retained liquid as well as ground.
- `terrain.caves` turns a cave design into layers: `parse_design`/`load_design`, `void_mask`, `dress_write`, `pool_mask`, `light_cells`, `feature_plan`, `emit_cave` and `check_cave`. `terrain.ashlar_emit.check_form_layers` runs any forms-only layers through the terrain checks without repainting the surface.
- `terrain.forms.load_form` reads voxel arrays and palettes. `form_write` emits carved air or built solid cells. `flow_build` collects flowing sources, and `gravity_violations` checks unsupported material after the planned edits.
- `terrain.verify.verify` returns a Report. GATE A checks shape and materials, the site boundary and planned water. `terrain.render.render_views` writes hillshade, relief, profile, slope and eye-level PNGs. Judge the last two from the intended approach.
- `terrain.ashlar_emit.preview_field(recipe, project_dir)` runs the design checks. `emit_ashlar(recipe, project_dir, first_phase=…, standalone=…, drain_approved=…)` writes checked files. `emit_field` accepts an already designed field, and `plan_rows_toon` formats the result. The emit checks include gravity and new spill contacts after the planned phases.
- `terrain.ids.load_ids` returns feature IDs, biome IDs and the version used. Check the running server version, use `check_ids` and disclose any nearest-older list before approval.
- `terrain.plant` plans vanilla features by growable substrate, spacing, density and height. Feature files contain place commands. `mark_trunks` masks trunk sites for surface comparison. `biome_commands` takes one approved, version-checked ID and tiles only that ID inside the approved box.
- `terrain.trees` generates seeded trunk and canopy geometry, writes an anchored vegetation module and renders previews. `tree_placements` aligns the rotated trunk base with the ground.
- `terrain.apron.design_apron` grades the edge of a protected footprint or naturalises an existing site. `surrounding_palette` derives surface weights from the inspected surrounding ring. Shores stay held and the apron workflow preserves existing liquid.
