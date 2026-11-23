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
  2,107 65 -358,minecraft:spruce_door
quality_contract:
  walkability[1]{from,to,note}:
    121 65 -340,107 65 -356,bell to house A door
```

- `plan`: `project` (kebab-case), `skill` (the design skill that wrote it),
  `world` (omit for the server's default world), `anchor`, a `bbox` covering
  every phase, a one-line `summary`, `notes` (optional list of one-line
  statements: seams, persistence rules, hand-offs), and `approved` (`no` until
  the user approves at the gate, then the date).
- `phases`: one row per phase, in build order. `blocks` is the cell count from
  `ashlar_place.py plan`; `from`/`to` is the phase's box; `via` is one of:
  - `mcp`: you send the phase file with your own `mc_build` call. Only for
    files with at most 200 entries. Lettering (`text`) must be in an `mcp`
    phase because the placer does not accept it. A phase of fills and blocks
    you wrote by hand uses `mcp`; a phase with more than 200 entries, or any
    stamped module phase, uses `placer`.
  - `placer`: `python3 <skill>/scripts/ashlar_place.py place <file> --snapshot …`,
    for anything larger or generated.
  - `commands`: a phase made only of `commands` rows; `file` is `-`.

  For a module-based phase that has not been stamped yet, write the intended
  `file` path and a hand estimate in `blocks`; `build` step 1 stamps it and step
  2 replaces the estimate with the placer's cell count.
- `materials`: the palette by role.
- `modules` and `placements`: see `modules.md`. `stamp.py` produces each
  phase's file from its placements before the build.
- `commands`: every console command for a phase, in order, each matching
  [commands.md](commands.md). Write the command in its bare or `minecraft:`-
  prefixed form. Apply the approved dimension wrapper at execution so the
  redstone checker can read setup loads directly from this table. Commands
  contain commas and quotes, so wrap each command in double quotes and escape
  its inner double quotes as `\"` (TOON quoting). A
  table with no rows (`commands`, `modules`, `placements`) may be omitted; write
  `commands[0]:` only if you want it explicit.
- `acceptance`: spot checks, one cell each.
- `quality_contract`: the property checks below.
- `tests`: ordered functional test steps (see [tests](#tests)). Plans from
  other skills may omit this table.

## Phase files

A phase file is exactly the arguments of one `mc_build` call, in absolute
coordinates:

```json
{
  "fills": [{"from": [104, 64, -358], "to": [112, 64, -352], "block": "minecraft:cobblestone"}],
  "blocks": [{"pos": [107, 65, -358], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"}],
  "liquids": "static",
  "connect": true
}
```

- Keys: `fills`, `blocks`, `text` (only in `mcp` phases), `liquids`, `connect`,
  `world`. No `snapshot` key: snapshots are taken separately.
- Block strings carry the `minecraft:` namespace and full block states.
- A bare fills list (`[{"from", "to", "block"}, …]`) is also accepted by the
  placer; the `design-monument` voxel toolkit
  (`../design-monument/tools/voxel/`) writes that form.
- Order: `mc_build` places all fills in order, then text, then blocks.
  Anything that must come after a block placement goes in a later phase.

## quality_contract rows

Use every row type that applies. A row type with nothing to check (no stairs:
no `headroom`; one district: no inter-district `connectivity`) is omitted; the
plan still needs at least one row, and every door, stair and named room
covered. Each is checked after the build (`verification.md`); a failing row
fails the build.

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

Row coordinates: `walkability`, `doors` and `connectivity` points are the
**feet cell** (the air cell a player stands in, one above the floor block);
`acceptance` is the exact cell holding the block named. For `headroom`,
`silhouette` and `edge_irregularity` only the x/z of the corners matter (the
check reads the columns); give y at the floor. `block_mix_ratios` regions are
full boxes.

In a TOON row, write a list inside one cell with `|` (for example palette
`minecraft:oak_planks|minecraft:spruce_planks|minecraft:stone_bricks`); never a
comma. Write a `via` route as waypoints joined by ` > ` (for example
`121 65 -340 > 118 65 -348 > 107 65 -356`); the check follows it as a polyline.
Write a `silhouette`'s `sample_count` evenly spaced columns along the region's
longer horizontal side, and use the population variance of the top y.
`doors.facing` is the door block's own `facing` value; the check walks both
sides along that axis.

## tests

Each test is a list of steps run in order. Example for a sorter batch:

```toon
tests[9]{test,step,kind,at,detail,expect}:
  batch-1,1,load,104 64 -350,"item replace block 104 64 -350 container.0 with minecraft:cobblestone 40",-
  batch-1,2,load,104 64 -350,"item replace block 104 64 -350 container.1 with minecraft:oak_log 40",-
  batch-1,3,load,104 64 -350,"item replace block 104 64 -350 container.2 with minecraft:dirt 20",-
  batch-1,4,settle,100 60 -352 108 64 -346,containers,timeout 180
  batch-1,5,expect,106 61 -352,container,gained minecraft:cobblestone=40
  batch-1,6,expect,106 61 -349,container,gained minecraft:oak_log=40
  batch-1,7,expect,106 61 -346,container,gained minecraft:dirt=20
  batch-1,8,conserve,100 60 -352 108 64 -346,containers,-
  batch-1,9,rest,100 60 -352 108 64 -346,blocks,baseline
```

(A filter hopper's contents are checked the same way with `holds`, for example
`expect,103 63 -352,container,holds minecraft:cobblestone=18|minecraft:stick=4`.)

And for a lever-driven door:

```toon
tests[8]{test,step,kind,at,detail,expect}:
  cycle,1,manual,101 65 -341,"Flip the lever at 101 65 -341 on, then tell me",-
  cycle,2,settle,98 64 -343 103 67 -336,blocks,timeout 10
  cycle,3,expect,100 65 -340 100 66 -339,block,minecraft:air
  cycle,4,manual,101 65 -341,"Flip the lever at 101 65 -341 off, then tell me",-
  cycle,5,settle,98 64 -343 103 67 -336,blocks,timeout 10
  cycle,6,expect,100 65 -340 100 66 -339,block,minecraft:smooth_stone
  cycle,7,rest,98 64 -343 103 67 -336,blocks,baseline
  cycle,8,repeat,-,steps 1-7,9
```

(Here the wall runs along z at x = 100, the doorway is z = -340 to -339 at
y = 65 to 66, the pistons sit at z = -342 and z = -337, and the lever is on the
wall's east face beside the doorway. Smooth stone fills the doorway when
closed. The first pass and nine repeats give ten cycles.)

| Kind | `at` | `detail` | `expect` | Run by |
| --- | --- | --- | --- | --- |
| `load` | the container | one quoted inventory load command (`item replace block` or `data merge block` with an `Items` payload only) | `-` | agent |
| `settle` | a region | `containers` or `blocks`: what to read | `timeout <seconds>`: repeat the reads until two in a row agree, or fail | agent |
| `await` | a container or cell | `container` or `block` | a condition plus `within <seconds>`, for example `minecraft:sugar_cane>=8 within 3600`: repeat the reads until it holds, or fail | agent |
| `expect` | a container, a cell or a region | `container` or `block` | `container`: either `gained` and the items the container gained since this test's baseline, or `holds` and its exact contents, each as `id=count` joined by `\|` (nothing else may have been gained, or be held); `block`: a block state that every cell must match (unspecified properties are wildcards) | agent |
| `conserve` | a region | `containers` | `-`: for every item, the total across the region's containers equals this test's baseline total plus this test's loads, and no container outside this test's `gained` rows gained anything | agent |
| `rest` | a region | `blocks` | `baseline`: components with modelled power properties have the same block IDs and power states as in this test's baseline | agent |
| `manual` | where the user acts | the exact instruction, quoted | `-`; the next steps read what happened | user |
| `repeat` | `-` | `steps <a>-<b>` | how many additional times to run those earlier steps | — |

A test with a `manual` row is a manual test; any other test is an agent test.
Manual tests use user actions and passive observation. Put any `load` rows in
a separate agent test.
Every `load` command is a world change: validation checks it against
`commands.md`, and the approval gate shows it as it will run.

**Each test has its own baseline.** Before a test's first row, `test` mode
settles the machine's containers and reads the machine (block states and
container contents). `gained`, `conserve` and `rest` are measured against that
reading, so earlier batches, earlier runs and earlier fix rounds leave nothing
for a later test to trip over: batch 2 is checked against the state batch 1
left, and a re-test after a fix starts from wherever the machine stands. The
machine must be at rest when the baseline is read: its power properties match
the loaded rest state, and its internal containers (every container except
this test's `load` targets and `gained` containers) hold what the loaded rest
state says. If not, for example because an earlier failed run left items in a
hopper line, the test stops and tells the user, who clears them in game or
rolls back. The plan never clears containers through the console.
The sole calibration baseline exception is the approved [Rung 0 check 5
torch](verification.md#rung-0-calibration-check-5).

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
6. A `commands` phase with any console command that names a position or an
   entity (`commands.md`) has a `forceload add` row first and the matching
   `forceload remove` row last. A `commands` phase's `from`/`to` is the box
   around its entities and positions (used for the `mc_players` check and the
   force-load columns). This is the one check that repairs instead of
   stopping: if either row is missing, add them over the phase's box columns
   (its `from`/`to` x and z), one pair per tile of at most 256 chunks, and show
   the added rows at the approval gate. Do not add `forceload query` to the
   table; the builder runs it itself.
7. `quality_contract` has at least one row, and every door, stair and named
   room in the design is covered.
8. The snapshot slots for the whole build are known.
9. Every `tests` row has a known kind and a parsable `expect`. Its `at` is a
   parsable position or region inside the plan's `bbox`, except for `repeat`,
   which uses `-` and names a valid range of earlier steps in the same test.
10. Every `load` is in an agent test and matches `item replace block` or
    `data merge block` in `commands.md`. A test `data merge block` may set only
    the inventory `Items` payload, and that list must be non-empty (an empty
    `Items` would clear the container). The command's coordinates must equal the
    row's single `at` position inside the `bbox` and identify a planned or
    observed container. Confirm the container is present before executing.
11. Every test that drives the machine ends with a `rest` row after expanding
    any `repeat` rows.
12. A plan written by `system-redstone` has at least one test for each input, or
    a note saying why the input cannot be tested.
