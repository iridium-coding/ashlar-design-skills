# Grounding a build with an apron

A vertical lip, trench or abrupt change in materials can make a build look dropped onto the land. An apron grades that edge into the surrounding ground and uses the surveyed surface palette. Use the [terrain method](../../terrain-shape/reference/terrain/method.md) for survey, materialisation and verification.

## Survey and plan

- Capture fresh heights and the exact site read per the [Ashlar survey](../../exec-ashlar/reference/survey.md). Include enough room inside the grading box for the taper and enough margin outside it to sample both sides of each outer edge. Read through the deepest seal and above foliage. Resolve existing structures and other non-natural blocks before grading.
- Sample a narrow ring immediately outside the grading box, near the measured ground. Take `mc_inspect` with `format: "stats"` over strips or smaller tiles at the local surface height. Save the block-frequency text for `--palette`. Combine disjoint samples by retaining their count rows so the toolkit can sum counts by base block and weight the most common natural surface materials.
- Make the footprint, pad levels and surrounding grade meet in one field. The default apron width is twice the largest step at the footprint edge, with a minimum of 8 and a maximum of 24 columns. Thermal erosion and light hydraulic erosion soften the slope with a smoothstep taper toward the surveyed outer ring. The outer ring keeps its surveyed height. Carry the surveyed soil or grass onto gentle grades, use the site's sediment at wet edges and expose rock on steep faces. In a host plan, pass the host's ground-edge materials as a weighted JSON object to `--host-palette`. For example, `'{"minecraft:grass_block": 3, "minecraft:coarse_dirt": 1}'`. The seeded surface mix applies the host palette near the footprint and tapers to the sampled palette across the apron.
- Existing water and lava are retained. Where a bed is lowered, fill the newly open bed up to its retained still level with the same liquid. Shore holding applies outside the fixed footprints and pads. Review those fixed areas where the plan meets a bank and revise the layout if the shore and the seam conflict. Apron grading leaves the biome in place and has no drain step. See [water and shores](../../terrain-shape/reference/terrain/water.md).

## Offline launcher

```text
apron --site DIR --box X1 Z1 X2 Z2 [--protect X1 Z1 X2 Z2 [--pad Y]]… --project DIR --element E --first-phase N [--palette STATS.txt] [--host-palette JSON] [--preview] [--standalone]
```

Run this subcommand through `<terrain-shape>/scripts/terrain.py` using the launcher prefix in the [toolkit API](../../terrain-shape/reference/terrain/toolkit-api.md). `--site` takes the exact site read, including the margin beyond the inclusive grading box.

- **Planned.** Repeat `--protect` for the footprint rectangles. Supply `--pad Y` with each rectangle that has a planned level. The apron meets that level, while every original cell in the protected columns is excluded from the apron fills. The host plan owns the actual grade of those columns. Intentional pads supplied to `design_apron` outside protection can be graded by the terrain phase. Put the generated site-prep phases first in the host plan.
- **After the fact.** Supply `--protect` for the standing build's bounding box and use its measured ground. Set `--standalone` for `<host>-ground` and record `grounds: "<host>"` on that project's registry entry.
- **Naturalise.** Omit `--protect` and `--pad` to soften coarse placement or artificial-looking worldgen throughout the box while holding its outer ring and shores. Use `--standalone` for an independent site.

## Review and verify

Use `--preview` for the before-and-after renders and seam profile under `terrain/previews/`. Show them before asking for design approval. Report `delta.max`, `delta.mean` and `delta.moved` for the apron work. The toolkit compares rounded target heights against measured ground, counts protected columns as zero movement and averages the absolute change across the box. When `needs_ok` is true (a rounded absolute change greater than 6 blocks in any writable column), obtain the user's explicit OK for that change during design approval.

Hand the approved local outputs to `exec-ashlar build`, which uses the standard terrain rows and rollback. Include a `seam` row in the `quality_contract` with `max_step: 1` for each protected edge and the outer box edges. In the host plan, place verification for a planned pad against its apron after the host establishes its pad height. Use a fresh exact site read spanning both sides of each edge.

```text
seam --site POST_BUILD_F1 --from X Z --to X Z --outward DIR --max-step N
```

Use the endpoints and `outward` value in each emitted apron seam row. It points from the writable apron toward the host at a protected edge and away from the grading box at an outer edge. The check measures ground under vegetation or liquid. Read disputed columns, check retained liquid and inspect the finished seam in profile. See [Ashlar verification](../../exec-ashlar/reference/verification.md).

## Sloped-back bench

Cut a ledge for a path or wall-base rail as a bench whose wall recedes about 0.85 blocks horizontally for every block of height above the ledge. The higher rock stays supported and the canyon or valley side stays open for the view.

Put all carve and clear fills before any ledge or rail fills in the Ashlar plan. A wider clear at the next cell can erase a placed ledge at a jog or turn. Verify the result with a vertical `mc_render` slice through the path and check continuity along narrow runs. The profile shows the receding wall and any overhang.
