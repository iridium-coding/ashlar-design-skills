# Checking natural terrain

Translate the 7-block rule, asymmetry, slope, surface mixes and submerged foundation detail into field checks and post-build observations. GATE A runs offline. During verification, use the emitted `quality_contract` rows and fresh ground measurements. Apply the sampling guidance below to individual landforms. For the supported row schema and checks see `../exec-ashlar/reference/plan-format.md` and `../exec-ashlar/reference/verification.md`.

### 1. Silhouette variance — no flat plateaus

For any landform with horizontal extent ≥ 20 blocks, sample 8 surface
points spaced ≥ 5 blocks apart and require Y values to vary by **≥ 3 blocks**
across the sample set. For the plan row, the placer measures population variance of the sampled heights. A landform that comes back with all 8 points at the
same Y is a flat plateau or terrace — refuse.

```toon
silhouette[1]{region_a,region_b,sample_count,min_y_variance}:
  -55 105 -47,55 130 63,8,3
```

### 2. Edge irregularity — the 7-block rule

For every named coastline, ridgeline, or terrain edge, sample 20 consecutive
surface points along the edge and require **no run of more than 7 collinear
blocks** (same X or same Z). This is the 7-block rule in checkable form.

```toon
edge_irregularity[1]{edge_name,from,to,max_collinear_run}:
  headland-west-coast,-55 105 -47,-55 105 63,7
```

### 3. Block-mix ratio — no monoculture

For every "natural" surface fill, count blocks in a representative 10×10×1
area and require **no single block to exceed 70%** of the cells (or the
ratio band the palette specifies — `reference/terrain/palettes.md` § biome).

```toon
block_mix_ratios[1]{region_a,region_b,palette,max_single_ratio}:
  -30 128 -20,-21 128 -11,"minecraft:grass_block,minecraft:coarse_dirt,minecraft:podzol",0.7
```

### 4. Symmetry test — no mirrored mountains

For any "natural" landform, the bounding-box flipped left-right (or top-down
for footprints) must **not** be a pixel-perfect match. Sample 20 random
`(x, z)` points; flip them about the landform's centre line; require Y
values to differ at ≥ 30% of the points.

Record the paired observations in the verification notes.

### 5. Foundation visibility — naturalised below-water faces

If the build includes a foundation/core mass with **any** vertical face
between Y_seabed and Y_seabed + 20, sample the perimeter every 4 blocks at
two depths (seabed + 5, seabed + 15) and require the face to have **at least
3 unique block IDs** along the sample (i.e. it's not a sheer rectangular
wall of one stone block).

Inspect both depths with `mc_inspect` columns and record material counts.

### 6. Water column continuity — no dry shelves

Along any coastline of a built landform, sample 12 surface points just
outside the visible coast and require **water all the way down to the
seabed** — no air or void column above water level.

For a planned basin, use the emitted water_continuity row (region_a, region_b, level). Sample retained water separately.

## Checking the result

Compare expected and surveyed surfaces with the launcher. Inspect shorelines, steep faces and the far side of each silhouette in vertical slices. Document the failing row and measured points, correct the recipe and recheck.

## What to do when a contract row fails

The Cape Aurelia retrospective: half-measures cost more iterations than they
save. On `CORRECTIONS NEEDED`, **fix the root cause**, not the symptom:

- Silhouette variance fails → the heightmap is too flat in that region; raise
  noise amplitude or add a peak, regenerate the tile, re-place.
- Edge irregularity fails → the coastline was carved as a rectangle; widen
  the radial falloff or add an organic-blob inlet, regenerate, re-place.
- Block-mix ratio fails → the palette generator is picking one block too
  often; retune the weights and re-place.
- Foundation visibility fails → apply the talus-skirt rescue from
  `reference/landforms.md`; do not paint over with a single block type.

Then **re-sample after acting** to confirm the fix landed and did not break
a neighbouring contract row. Verify is not optional.
