# Plan format

A design skill hands `exec-ashlar` three kinds of files in
`.minecraft-builder/<project>/`:

- `plan.toon`: the readable plan (TOON, <https://toonformat.dev/>);
- `phases/NN-<name>.json`: the exact geometry for each phase;
- `modules/<name>.json`: repeated elements in local coordinates (`modules.md`).

## plan.toon

```toon
plan:
  project: oakhollow
  skill: design-village
  world: world
  anchor: {x: 120, y: 64, z: -340}
  bbox: {from: [100, 58, -362], to: [162, 92, -298]}
  summary: hamlet of 4 buildings around a bell plaza
  approved: no
phases[4]{id,name,file,blocks,from,to,via}:
  1,site-prep,phases/01-site-prep.json,18200,100 58 -362,162 66 -298,mcp
  2,houses,phases/02-houses.json,41750,104 63 -358,158 80 -302,placer
  3,details,phases/03-details.json,640,104 63 -358,158 80 -302,mcp
  4,population,-,0,118 64 -336,124 66 -330,commands
materials[2]{role,block}:
  walls,minecraft:spruce_planks
  trim,minecraft:stripped_spruce_log
modules[1]{name,file,size}:
  small-house-a,modules/small-house-a.json,9 8 7
placements[2]{module,origin,rotation,mirror,phase}:
  small-house-a,104 64 -358,0,none,2
  small-house-a,140 64 -330,90,x,2
commands[1]{phase,seq,command,purpose}:
  4,1,"summon minecraft:villager 121 65 -333 {Tags:[\"ashlar\",\"ashlar.oakhollow\"]}",farmer
acceptance[1]{phase,at,expect}:
  2,107 64 -358,minecraft:spruce_door
quality_contract:
  walkability[1]{from,to,note}:
    121 64 -340,107 64 -356,bell to house A door
```

- `plan`: `project` (kebab-case), `skill` (the design skill that wrote it),
  `world` (omit for the server's default world), `anchor`, a `bbox` covering
  every phase, a one-line `summary`, and `approved` (`no` until the user
  approves at the gate, then the date).
- `phases`: one row per phase, in build order. `blocks` is the cell count from
  `ashlar_place.py plan`; `from`/`to` is the phase's box; `via` is one of:
  - `mcp`: you send the phase file with your own `mc_build` call. Only for
    files with at most 200 entries. Lettering (`text`) must be in an `mcp`
    phase because the placer does not accept it.
  - `placer`: `python3 <skill>/scripts/ashlar_place.py place <file> --snapshot …`,
    for anything larger or generated.
  - `commands`: a phase made only of `commands` rows; `file` is `-`.
- `materials`: the palette by role.
- `modules` and `placements`: see `modules.md`. `stamp.py` produces each
  phase's file from its placements before the build.
- `commands`: every console command, in order, exactly as it will run, each
  matching `commands.md`. Commands contain commas and quotes, so wrap each
  command in double quotes and escape its inner double quotes as `\"` (TOON
  quoting).
- `acceptance`: spot checks, one cell each.
- `quality_contract`: the property checks below.

## Phase files

A phase file is exactly the arguments of one `mc_build` call, in absolute
coordinates:

```json
{
  "fills": [{"from": [104, 63, -358], "to": [112, 63, -352], "block": "minecraft:cobblestone"}],
  "blocks": [{"pos": [107, 64, -358], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"}],
  "liquids": "static",
  "connect": true
}
```

- Keys: `fills`, `blocks`, `text` (only in `mcp` phases), `liquids`, `connect`,
  `world`. No `snapshot` key: snapshots are taken separately.
- Block strings carry the `minecraft:` namespace and full block states.
- A bare fills list (`[{"from", "to", "block"}, …]`) is also accepted by the
  placer; the voxel toolkit writes that form.
- Order: `mc_build` places all fills in order, then text, then blocks.
  Anything that must come after a block placement goes in a later phase.

## quality_contract rows

Use every row type that applies. Each is checked after the build
(`verification.md`); a failing row fails the build.

| Row | Fields | Passes when |
| --- | --- | --- |
| `walkability` | `from,to,note` | every step on the straight route has a floor and two clear cells above it, and climbs or drops by at most one block |
| `doors` | `at,facing,clearance_blocks` | both sides of the door have a floor and two clear cells for `clearance_blocks` blocks |
| `headroom` | `over_region_a,over_region_b,min_clear` | every column in the region has at least `min_clear` clear cells above its walking surface |
| `block_mix_ratios` | `region_a,region_b,palette,max_single_ratio` | no single block exceeds `max_single_ratio` of the region's non-air blocks, and every listed palette member is present |
| `silhouette` | `region_a,region_b,sample_count,min_y_variance` | the variance of the top y at `sample_count` evenly spaced columns is at least `min_y_variance` |
| `connectivity` | `site_a,site_b,via` | the named route between the two sites is walkable end to end |
| `edge_irregularity` | `edge_name,from,to,max_collinear_run` | no run of identical x or z along the edge is longer than `max_collinear_run` (terrain) |

Coordinates in rows are `x y z` triples; regions are two corners. If you cannot
write a row because you do not know the answer (is this door reachable?), the
plan is not finished.

## Validation (start of `build`)

Stop and report if any of these fails:

1. `project` is kebab-case and matches the folder name.
2. Every phase file exists and `ashlar_place.py plan` accepts it (except
   `mcp` phases with `text`, which you check by hand); `mcp` phase files have
   at most 200 entries; only `mcp` phases contain `text`.
3. Every coordinate is an integer inside the world's height range.
4. Every `placements` row names a module listed in `modules`.
5. Every `commands` row matches a form in `commands.md`, with the project's
   tags where the form requires them.
6. A `commands` phase with entity commands has a `forceload add` row first and
   the matching `forceload remove` row last. If either is missing, add them
   over the phase's box columns (its `from`/`to` x and z) and show the added
   rows at the approval gate.
7. `quality_contract` has at least one row, and every door, stair and named
   room in the design is covered.
8. The snapshot slots for the whole build are known.
