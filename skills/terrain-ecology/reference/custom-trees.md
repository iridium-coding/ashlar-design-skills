# Design a custom tree

Start with the view the tree must hold. A willow at a bend needs branches that hang toward the water and room for a boat underneath. A cypress on an open ridge can lean with the wind and leave the skyline visible between spires. Choose vanilla growth when it gives the requested shape. Design a module for a distinctive species, a repeated silhouette or one hero tree.

## Presets and controls

| Preset | Starting silhouette |
|---|---|
| `broad-oak` | Forked spreading crown, two-wide rooted base |
| `conifer-spire` | Tall tapered spruce with short tiers of branches |
| `umbrella-pine` | Leaning trunk, high boughs and a shallow crown |
| `weeping-willow` | Wide rooted trunk with low hanging leaf curtains |
| `windswept-cypress` | Narrow crown, curved trunk and a strong directional lean |
| `dead-snag` | Weathered stripped trunk and exposed forks |
| `giant-fantasy` | Flared base, roots and distinct layers of flowering foliage |

`terrain.trees.TreeParams` is an immutable dataclass. Start with `PRESETS[name]` and use `dataclasses.replace` to tune it. The following controls describe the generator's accepted values.

| Field | Effect |
|---|---|
| `wood`, `leaves` | Fully qualified vanilla block IDs. Choose an axis-bearing log, wood, stem or hyphae, and a leaf block that supports persistence. Logs align to branch direction. |
| `height` | Trunk height in blocks, 1–384. Allow extra space for forks and foliage above the trunk. |
| `trunk_width` | 1, 2 or 3. Width 2 starts with a 2 × 2 trunk. Width 3 gives a flared 3 × 3 base. |
| `taper` | Fraction of trunk width lost toward the crown, 0–1. At least one trunk cell remains. |
| `lean` | Pair of horizontal slopes (x, z), each −4 to 4, in blocks per block of rise. |
| `curve` | Mid-trunk bow in blocks, −64 to 64. Its horizontal direction comes from the seed. |
| `branch_levels`, `branches` | Fork depth 0–8, and number of primary limbs 0–64. Zero depth or zero limbs gives an unbranched trunk. |
| `branch_angle` | Angle from vertical, 0–90 degrees. Larger values give flatter boughs. |
| `branch_length` | Fraction 0–1. Sets the initial limb length relative to trunk height and scales successive forks relative to their parent. |
| `canopy` | `round`, `ellipsoid`, `conical`, `columnar`, `umbrella`, `weeping`, `layered`, `sparse` or `dead`. The dead form has no leaves. |
| `canopy_radius` | Crown or foliage-clump radius in blocks, 0.5–32. Branches and lean can extend the full tree beyond that radius. |
| `leaf_density` | Probability of retaining each candidate leaf, 0–1. Thinning opens holes. The generator retains leaves joined to wood by at most six face-connected steps. |
| `roots` | Boolean. Adds ground-replacing roots one block below the trunk anchor. Check the entire root spread against terrain, water seals and buried work. |
| `seed` | Integer controlling branch variation, foliage holes and roots. Save each approved variant's parameters and seed. |

## Generate and review

With the launcher and Python path described in the [toolkit API](../../terrain-shape/reference/terrain/toolkit-api.md), both approaches produce the same tree:

```text
terrain.py tree --preset windswept-cypress --set height=16 --set seed=41 --name ridge-cypress --out DIR
```

```python
from dataclasses import replace
from terrain.trees import PRESETS, generate, preview, to_module

params = replace(PRESETS["windswept-cypress"], height=16, seed=41)
tree = generate(params)
views = preview(tree, "ridge-cypress")
module = to_module(tree, "ridge-cypress")
```

The three PNGs end in `_iso.png`, `_side.png` and `_front.png`. Review the branching at full size, gaps and clearance under the crown. Check the lean from the player's approach. Show the previews and the dimensions to the user before accepting the design. Try another seed or reduce the canopy if it closes an intended view.

- Claude Code: open the PNGs with `Read`.
- Codex: open the PNGs with `view_image`.
- Otherwise: share the preview paths and ask the user to open them.

Save the approved `to_module` dictionary as `modules/<name>.json`. This F7 vegetation module carries the local trunk-base `anchor`, size and three sparse parts. It contains no air cells. The stamper writes all ground parts first, then wood, then leaves. Ground can replace existing blocks. Wood and persistent leaves fill air only. Keep protected structures outside the entire transformed footprint, including buried roots. Check player clearance, crown height, buried-root support and box limits before building.

## Scatter a species or anchor a hero

- **Mixed stand.** Use one canopy layout for the whole stand. Assign a seeded fraction of eligible canopy points to the custom species and save their world `[x,z]` pairs. Remove those entries from the vanilla feature list and check all remaining crowns for clearance. The custom module name belongs in the placements file. The vanilla mix accepts only game feature IDs. Preview a few seeds for frequently repeated shapes and distribute approved variants across the stand.
- **Hero tree.** Pick one surveyed trunk cell and save a one-point list. Check the actual rotation and mirror against the approach, water and any path. If the composition depends on a particular lean, choose a placement seed giving the intended orientation and keep it in the plan. Calculate the final origin from that transformed anchor.

Write `POINTS.json` as a nonempty list of distinct integer world pairs, such as `[[40, 20], [46, 31]]`. Use the emitted F6 for designed terrain and the exact site read for existing ground.

```text
terrain.py tree-place --module MODULE.json --points POINTS.json --surface SURFACE.json --phase N --project DIR --seed S
terrain.py tree-place --module MODULE.json --points POINTS.json --site SITE --phase N --project DIR --seed S
```

The underlying `tree_placements(points, surface, origin, module, phase=n, seed=s)` takes world x/z pairs and an x-major integer ground grid. A trunk at `(x,z)` sits at `surface[x-ox,z-oz] + 1`. Mirroring and quarter turns move the minimum corner while keeping that selected anchor fixed. Check the produced F8 placement rows and the stamped phase. The project contains `terrain/<name>.placements.json` and `phases/<NN>-<name>-trees.json` with a placer phase and block backup. `tree-place` preserves the existing F6 skip mask and adds every transformed above-bed wood column. Use the updated project F6 for surface comparison. For a multi-module phase run `<exec-ashlar>/scripts/stamp.py` on the combined placements so wood for every tree precedes leaves throughout the phase. Derive F6 skips from the transformed wood cells in that combined phase.
