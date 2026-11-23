# Plant communities

Design a stand from its ground upwards, then allocate space from the canopy down. At the edge of a wood, leave gaps between the last mature trees and carry shrubs and grasses into the meadow. On a damp bank, increase density on the growable dry side of the waterline. Keep exposed slopes, paths and agreed views open. Record the seed, weighted species mix and density per stand so an iteration can reproduce the layout.

## Choose species and bound their growth

Read `mc_status` for the running Minecraft version. Start from `BIOME_CONTENT` or a local species mix that fits the soil, tint and requested character. Check the fully qualified IDs, for example `terrain.py ids --version 26.3 --features minecraft:oak,minecraft:birch,minecraft:bush,minecraft:grass`. The bundled lists come from vanilla game data. The CLI can use the nearest older available list. Record both the running and selected versions and tell the user about a fallback. Confirm candidates against game data for the running version. If no suitable list exists, ask before downloading data to generate one.

The registry includes geodes, lakes and other landscape features. Inspect the matching vanilla feature definition, including any delegated feature, generator offsets, foliage, roots, decorators and substrate changes. Record the source version and a conservative sideways, upward and downward write distance from the command point. Check the entire resulting box against the surveyed area, protected ground and nearby builds. Omit or replace a species whose vegetation behaviour or bounds cannot be established. A live `place feature` call grows the feature and cannot serve as an ID probe.

For example, the **26.3** vanilla definitions of `oak` and `birch` specify straight trunks with maximum heights of 6 and 7 respectively, a blob foliage placer with radius 2, a below-trunk provider and empty decorator lists. The `bush` and `grass` definitions place simple vegetation blocks. These facts come from `data/minecraft/worldgen/feature` in that release's game archive. Repeat the check for the actual server version, including how the placers use those parameters. A mix for a light deciduous wood could be:

```json
{
  "canopy": {"minecraft:oak": 3, "minecraft:birch": 1},
  "understory": {"minecraft:bush": 1},
  "ground": {"minecraft:grass": 1}
}
```

Weights choose species *within* a layer. Variable-density Poisson sampling sets the spacing. In `terrain.plant.LAYER_SPACING` the minimum and maximum spacing parameters in blocks are 3–12 for canopy, 2–6 for understory and 1–3 for ground cover. The slope mask thins the stand as ground steepens and reaches zero at 32 degrees. Riparian ground receives a density boost. Later layers leave a gap around earlier planting points. Review the modeled crowns, access and species-specific growth conditions as well as point spacing.

## Plan on actual ground

For existing land, take both the survey heights and the exact site read. In the exact columns find the supporting block, overhead space, occupied trees, water and lava. The `plant --site` input is the exact column-read directory. Heights alone cannot distinguish stone from dirt or a tree-covered column from usable ground. For designed land, use the terrain recipe's final fitted field, resolved surface materials, planned and retained liquid. Any liquid above the final ground excludes that column. Allow planting on a drained bed only where the recipe actually removes those liquid cells through an individually approved drain and the resolved bed supports that species. A drain approval names one entire connected body in that build. Keep every other body's liquid in the mask. Reserve the full flowing reach of planned falls as well as their source cells. See `../terrain-shape/reference/terrain/water.md`.

Use the matching command after approval and terrain mass emission. DIR is the existing project, SITE the exact read, V the running version. Use the same mix and seed as the design. SIDE, UP and DOWN are verified reaches for the largest growth in the file. In site mode `--element NAME` is optional and defaults to `planting`. In recipe mode use the recipe's element and repeat `--drain-approved BODY_ID` once per approved, planned body.

```text
terrain.py plant --site SITE --box X1 Z1 X2 Z2 --project DIR --element NAME --phase N --mix MIX.json --version V --seed S --reach SIDE UP DOWN
terrain.py plant --recipe RECIPE --project DIR --phase N --mix MIX.json --version V --seed S --reach SIDE UP DOWN
```

`--reach SIDE UP [DOWN]` uses minimum CLI margins of 8 blocks sideways, 32 up and 2 down. For the verified standard vegetation the CLI can supply these defaults. Other supported species require an explicit reach. Supply a larger bound for any species that can exceed those distances. The phase's backup, player-clearance check and approval must cover the expanded box. Use the phase row's `from` and `to` coordinates. When using the Python API for a custom mix, first call `vegetation_reach(mix, feature_ids, (side, up, down))` to apply the same verification and minimum margins. Ground cover shares the ordered feature file when it is part of the same mix.

For offline design, `terrain.plant.plan_features(hf, surface_ids, mix, origin=(ox, oz), seed=s, known=feature_ids, water=wet)` returns ordered `Feature(id, x, y, z, layer)` records. Pass a boolean wet grid, or the highest final liquid levels with NaN for dry columns. The planner tests the rounded ground height, growable surface and wet/slope masks and places each point at ground + 1. Review supports per species, exclusions around objects, and points in the transition between stands. Keep the approved points. If points must be reserved for custom trees or culled around a path, partition this single list offline. Convert only the remaining vanilla rows with `features_file(features, world=world, reach=(side, up, down))`. This also lets separate phases retain spacing established in the shared design. Omit an empty feature phase.

The feature output is `phases/<NN>-<element>-features.commands.json`, with `place feature <id> <x> <y> <z>` lines and a block backup. Vanilla growth can vary even with identical planned points. After mass emission, use the mask produced by `plant`, or use `mark_trunks` on the edited feature list with a verified wood footprint for each species. Use the actual projected wood columns for stamped trees, including branches beyond the anchor. Preserve the existing skip bits and leave ground-cover-only areas measurable.

## Named biome phase

Follow the five-step decision in the skill. After the user names an ID, use `plant --biome-only --biome-preview ID` with the same recipe or site box to show the proposed bounds. The vertical span starts at minimum final top minus eight and ends at maximum top plus four, clipped to world limits. It includes every touched 16 × 16 horizontal chunk and whole four-block vertical cell. For example, raw corners `(-1,62,15)` and `(1,65,17)` expand to `(-16,60,0)` and `(15,67,31)`. Use the literal world and expanded corners in the dedicated question.

After recording approval, use `--biome-only --biome-change ID --phase N` with the same bounds and a dedicated final phase number. This writes `phases/<NN>-<element>-biome.commands.json` and preserves the accepted vegetation points and F6 mask. Inspect the union of the emitted boxes and their single ID against the approval. Use biome rollback and record the per-chunk probe before painting. The present probe workflow supports the default command dimension. Keep the current biome when the required dimension cannot be probed and restored.

## Rocks, deadfall and weathering

At the foot of a scree slope, intersect steep and concave masks, then use seeded Poisson sampling to space small rocks across the pockets. Lay fallen wood along the ground under mature stands and keep crossings clear. Author a few sparse vegetation modules with the voxel toolkit. Keep each boulder's supporting core or log's continuous spine. Use a recorded seed to retain roughly 80–95% of optional outer chips, moss or twigs. Mix several variants and seeded rotations across the stand. Check support after thinning and inspect a preview of the placed mix. Stamp only the selected cells, with above-ground detail in the air-filtered wood part and any intentional ground replacement in the ground part. See [vegetation modules](../../exec-ashlar/reference/modules.md) and [weathering](../../terrain-shape/reference/terrain/weathering.md).
