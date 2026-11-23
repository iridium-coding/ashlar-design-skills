# Weathering, detail & composition

The final pass — and the largest visual-quality multiplier per block of
effort. Shaped, palettized terrain still looks flat until it is weathered.

## Surface speckling / noise

Break up any uniform surface with 5–15% variant noise:

- Use seeded palette choices in the material masks, or generate sparse, seeded vegetation-module variants offline. Stamp the chosen variants into the planting phase. Vary the seed and block mix between patches to layer noise.

### Match the variation frequency to the slope

Surface variation and erosion detail must be **low-frequency** (features ≥
~15–20 blocks) unless the face is near-vertical. On a near-vertical wall,
high-frequency noise reads as bumpy rock and is fine; on a gentle slope the
same high-freq variation terraces into vertical pins and streaks (a "dripping
curtain" / "vertical drip" look), and separately it explodes into thousands of
1-block fills.

- **Never per-column random tops or per-column ridged gullies on a slope.** Two
  ways this goes wrong are per-column `rng.normal` heights and per-column ridged
  gully/notch carving — both shatter a ramp into vertical streaks. High-freq is
  OK on a cliff; low-freq only on a ramp.
- Same root cause as the "real strata are roughly horizontal with low-frequency
  undulation, never per-column random" note in
  `reference/terrain/research.md` — keep the jitter smooth
  and low-frequency, not per-column.

## Detail-block library — use sparsely, never uniformly

Scatter these in **clusters**, not evenly:

- `rooted_dirt` — rare, in grass.
- `moss_block`, `moss_carpet` — shaded and damp areas.
- `azalea`, `flowering_azalea` — near water.
- `tall_grass`, `fern`, `large_fern` — understory.
- `grass` (short) tufts — on coarse dirt and edges.
- `dead_bush` — dry zones.
- Lone saplings — "first growth".
- Fallen logs — `oak` / `spruce` logs laid on their side, 3–6 long, near
  forest edges.
- `glow_lichen` — on vertical stone.
- `vine`, `cave_vines`, `hanging_roots` — on overhangs and under rooted_dirt.
- `pointed_dripstone` — cliff edges and cave ceilings.
- `sculk` patches — ancient, ruined areas.

## Vegetation distribution rules

- **Cluster, never sprinkle.** Plants "get lonely" — group them in 3–7 with
  2–8 blocks between clusters. Single plants are rare in dense biomes.
- **Density gradients.** High near water (>40% ground cover) → low on exposed
  slopes (<5%).
- **Edge bleed.** Forest edges scatter grass tufts 4–12 blocks outward into
  open ground.
- **Bare patches.** 5–15% of any "grass" region should be coarse dirt, podzol,
  or exposed stone — pristine uniform grass reads as paint.
- **Double-layer.** Always ≥2 substrate blocks under the surface.

## Trees

Grow ordinary trees using a version-checked vanilla feature matched to the biome. The planting skill writes `place feature <id> <x> <y> <z>` into a feature commands file for the placer. Use valid soil (dirt, grass, podzol or mud for mangroves), the light and headroom the species needs, and groups of 3–7 with irregular gaps. The 7-block rule applies to tree lines too. Vary species, age and spacing within each stand.

For a hero baobab, giant sequoia or a shape vanilla cannot grow, use `terrain-ecology` to generate a seeded custom vegetation module. Preview the profile and vary seeds and rotations across a stand. Deadfall and partial decay use seeded offline module variants.

Keep trees short and away from mountain feet — oversized trees dwarf the
topography and kill the sense of scale.

## Composition principles

Terrain is seen, not just built — compose it for the viewer.

- **Foreground / midground / background.** Detail-dense features 20–80 blocks
  from viewing positions; simplified features 80–200; silhouette-only beyond
  200 — far terrain needs a dramatic outline, not block detail.
- **One hero feature** per scene (the tallest mountain, the biggest fall).
  Subordinate features at roughly 1:0.6:0.4 scale. Let ridgelines and rivers
  guide the eye toward it.
- **Rule of thirds.** Place focal points about 1/3 across the visual field —
  for a 200×200 scene, the hero peak near (66,66) or (134,134), not center.
- **Negative space.** Reserve 20–40% of a scene as open space — sky, water,
  plain, valley floor. Quiet zones make the dense areas read as impressive.
- **Decay level.** When the user wants ruins or age, raise weathering density:
  more moss, cracked variants, `sculk` patches, fallen logs, vine drape, and
  seeded decay variants for placed modules.
