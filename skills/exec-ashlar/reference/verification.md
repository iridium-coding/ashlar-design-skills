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

## Look at it

Compare with the approved blueprints (and, for monuments, the reference
renders):

- `mc_render` `top` over the bounding box, for layout and footprint;
- facades `north`, `south`, `east`, `west`, with y limited to the structure
  (side views are volume-priced);
- `slice` with `axis: "y"` at each floor level, for floor plans.

Map colours are approximate and different blocks can share one; check exact
blocks with `mc_inspect` where it matters. `mc_render` does not show entities.

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

## Report

List each check with pass or fail and its evidence (a column line, a count, a
render). The build is done only when every check passes.
