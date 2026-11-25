# Verification

Run after the last phase, and for `verify <project>`. Report every check as
passed or failed with its evidence; fix failures and verify again.

## Reading columns

`mc_inspect` with `format: "columns"` returns one line per column, bottom to
top, without the `minecraft:` prefix:

```text
121,-340: 58-63 dirt | 64-64 stone_bricks | 65-71 air
```

At most 1,024 columns per call. For a route, inspect a one-block-wide box along
it, split into pieces for long routes.

Row coordinates: `walkability`, `doors` and `connectivity` points are the feet
cell (the air cell a player stands in, one above the floor block); `acceptance`
is the exact cell holding the block named. For `headroom`, `silhouette` and
`edge_irregularity` only the x/z of the corners matter (the check reads the
columns); the y is at the floor. `block_mix_ratios` regions are full boxes.

A cell is **walkable** when the block under the feet is solid (or a slab,
stair, path, farmland, or carpet on a solid block) and the two cells above are
air or passable (open doors, signs, torches, pressure plates, carpet, rails,
flowers, grass).

## Rows

| Row | How to check |
| --- | --- |
| `acceptance{at,expect}` | `mc_inspect` stats over the single cell; the block must match `expect` (unspecified block-state properties are ignored) |
| `walkability{from,to}` | Inspect columns along the straight line from `from` to `to`. Every step must be walkable, and the walking height may change by at most 1 between neighbouring cells |
| `doors{at,facing,clearance_blocks}` | Inspect the cells on both sides of the door along `facing` for `clearance_blocks` blocks; each must be walkable |
| `headroom{over_region_a,over_region_b,min_clear}` | Inspect columns over the region; above each walking surface there must be at least `min_clear` clear cells |
| `block_mix_ratios{region_a,region_b,palette,max_single_ratio}` | `mc_inspect` stats over the region; drop air; the largest block's share must not exceed `max_single_ratio`, and every palette member must appear |
| `silhouette{region_a,region_b,sample_count,min_y_variance}` | `mc_survey` with `matrix: true` over the region's x/z (or `sample_count` evenly spaced columns along the region's longer horizontal side); the population variance of the top y values must be at least `min_y_variance` |
| `connectivity{site_a,site_b,via}` | Follow the route the plan names for `via` as a polyline and check it like `walkability` |
| `edge_irregularity{edge_name,from,to,max_collinear_run}` | `mc_survey` matrix along the edge; the longest run holding the same x (or z) must not exceed `max_collinear_run` |
| `surface_match{region_a,region_b,file,tolerance,min_ratio}` | Write a fresh heights file over the region (`ashlar_place.py heights`), then run `../terrain-shape/scripts/terrain.py compare <file> <heights> --tolerance <tolerance> --min-ratio <min_ratio>`; it passes when the ratio of matching columns outside the skip mask reaches `min_ratio` |
| `seam{from,to,max_step[,outward]}` | Take a fresh read-only column backup over the edge and the adjacent unchanged columns, from below ground through air above the canopy. Run `../terrain-shape/scripts/terrain.py seam --site <post-build-site> --from X Z --to X Z --outward x\|-x\|z\|-z --max-step <max_step>`. Use the row's direction when supplied. For an ordinary outer seam it points away from the terrain box, and for a protected apron seam it points toward the host. The column read measures ground under water and trees. |
| `cave{file}` | Take a fresh exact read of the cave's box (`ashlar_place.py backup`) with the same margins as its survey, then run `../terrain-shape/scripts/terrain.py cave-check <file> --site <post-build read>`; it passes on exit 0. The report names each failing check (`ceiling`, `span`, `light`, `roof`) and the first failing cell |
| `water_continuity{region_a,region_b,level}` | `mc_inspect` `columns` over sampled columns (at most 1,024 per call), including columns at the region's edge: every column whose bed is below `level` is water from the bed to `level`, with no air gap, and no water cell borders air at the edge |

The terrain toolkit runs as
`uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python ../terrain-shape/scripts/terrain.py <command>`.
`heights` reads `mc_survey` with `matrix: true` in tiles of at most 200,000
cells.

## Look at it

Compare with the approved blueprints (and, for monuments, the reference
renders):

- `mc_render` `top` over the bounding box, for layout and footprint;
- facades `north`, `south`, `east`, `west`, with y limited to the structure
  (side views are volume-priced);
- `slice` with `axis: "y"` at each floor level, for floor plans.

Map colours are approximate and different blocks can share one; check exact
blocks with `mc_inspect` where it matters. `mc_render` does not show entities.

## Looking at terrain

Check terrain at eye level, never from the top alone:

- `mc_render` `top` and `heightmap` over the box, for the overall relief;
- `slice` views along a few x and z lines, as profiles (the shape of the ground
  and the water against it);
- facades of edge strips, to see the seam with the untouched ground (keep each
  within the 200,000-cell side-view limit);
- the terrain toolkit's offline renders, for comparison with what was built;
- for hero terrain, ask the user to look in game and say what they see.

Looking at the offline renders:

- Claude Code: `Read` the PNG files.
- Codex: `view_image` on them.
- Otherwise: report the numbers and ask the user to open the files.

## Planting

The runner's report (commands placed, failed, and unknown feature ids) is the
evidence for planted trees and features: report those counts, list the failures
(a tree with no room to grow is not an error in the run), and do not claim a
count the report does not show. Spot-check a few positions with `mc_inspect`.

## Entities and NBT

- Entity and block-entity checks need the chunks loaded. Unless a player is
  near the site, run them between `forceload add` and `forceload remove` over
  the build's columns (`commands.md`); a failed check outside a force-load
  proves nothing. If a check fails part way, still run the `forceload remove`.
- Count the build's entities: `execute if entity @e[tag=ashlar.<project>]`,
  adding `type=` to count one kind.
- Block-entity details: `data get block <x> <y> <z>` (signs, banners, lecterns,
  containers). It also needs the chunk loaded ("That position is not loaded"
  otherwise), so run it inside the same force-load unless a player is near.
- Villagers: keep the chunks force-loaded through the short wait (with no
  player near, nothing ticks otherwise), then read each one's memories with
  `data get entity @e[tag=ashlar.<project>,tag=ashlar.<project>.<name>,limit=1] Brain.memories` and
  confirm `minecraft:home` (its bed) and `minecraft:job_site` are set.

## Redstone

Before a machine build, confirm that the recorded `redstone_rest.py check`
is clean for the as-built state, that unmodelled parts were checked by hand, and that
the loaded state settles. Even exit 0 or 3 can accompany a `loaded … cannot
settle` result. Record the pre-build site read path in the plan notes when the
machine depends on existing blocks or conditional fills. See the
[checker guide](../../system-redstone/reference/checker.md). For the deliberate
Rung 0 torch, use the [check 5 gate](#rung-0-calibration-check-5).

For `built`, run the usual acceptance and `quality_contract` checks. Read the
full machine box with `ashlar_place.py read`, using the plan's world, and
compare it with the plan:

```text
python3 <skill>/scripts/ashlar_place.py read <x1> <y1> <z1> <x2> <y2> <z2> --out <full-read.json> [--world <name>]
python3 <skill>/../system-redstone/scripts/redstone_rest.py diff <plan.toon> <full-read.json> [--background <pre-build-read.json>]
```

The diff checks the block and every written property except power and
connection-pass properties. A wrong facing or missing block fails `built`.

For `at_rest`, [test mode](../SKILL.md#test) compares the baseline read after
setup with the checker's loaded rest state:

```text
python3 <skill>/../system-redstone/scripts/redstone_rest.py diff <plan.toon> <baseline.json> --loaded [--background <pre-build-read.json>]
```

Pass the same recorded pre-build read to both plan diffs when supplied. The
loaded diff compares component IDs and power properties. Read the extent
covering both the machine box and the supplied pre-build background so the
loaded diff sees the modelled positions outside the box. An unsettled loaded
state has no baseline.

Use the full read to find the actual chests, trapped chests, barrels, hoppers,
droppers and dispensers in the test area, including reused containers the
circuit depends on. The checker's `containers` command lists the supported
containers written by the plan. Compare that list with the observed positions,
read inventories with `data get block`, and check internal container contents
against the setup rows and any recorded expectations for reused containers.
The pre-build background contains block states only. If an existing
container's expected contents affect the circuit and are unknown, report the
position and withhold the `at_rest` pass. If known contents or their effects
fall outside what the checker models, check them by hand and record the
evidence. Keep console reads within loaded chunks and preserve the approved
force-load scope.

Each `rest` row diffs a test's own baseline read against the after read over
the same full region to detect replaced components and changes to modelled
power properties. A pass for `at_rest` requires the pre-build check, a
matching loaded baseline with verified internal inventories and every
applicable `rest` row to pass.

- **Power properties** are `power`, `powered`, `lit`, `extended`, `enabled`,
  `triggered`, `locked`, and `open` on machine-driven doors, trapdoors and
  fence gates.
- **Connection-pass properties** are the side properties of wire, panes,
  fences, walls and bars, stair `shape`, and chest `type`.

Record all four [verdicts](registry.md#verdicts) with their evidence.

### Rung 0 calibration check 5

Only the throwaway `rs-calibration` plan may place check 5's isolated standing
torch on an unpowered support. Run the ordinary pre-build checks. Require
exactly one as-built mismatch. At the fixture's planned world coordinate,
the diagnostic must show
`written minecraft:redstone_torch[lit=false]  expected minecraft:redstone_torch[lit=true]`.
Require zero structural errors, no unsettled positions in the as-built,
loaded or probed circuit, and the usual hand checks for unmodelled parts.
Keep the full diagnostic and exit 1 in the build log. At the ordinary
approval gate show the actual X Y Z, both literal states and why the
mismatch is intentional.
Wait for explicit approval of that preview before placement.

Run the ordinary geometry, inventory and loaded-baseline checks. If the
torch stays unlit, the sole expected `diff --loaded` line at the approved
X Y Z is `minecraft:redstone_torch[lit=true] -> minecraft:redstone_torch[lit=false]`.
Record the coordinates, output and exit code. Only this exact difference
may carry into the baselines for the other calibration tests. They still
require their own full baseline and all ordinary row checks. If the torch
lights, record the observed state and the differing check 5 result. Handle
any other baseline mismatch normally. Record the calibration build's
`at_rest` as `fail` because the as-built check failed, even if the torch
later lights. Record the seven observations before the approved rollback.

## Report

List each check with pass or fail and its evidence (a column line, a count, a
render). The build is done only when every build check passes.
