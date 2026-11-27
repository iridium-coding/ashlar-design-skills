# Line designs

The line design file `terrain/<element>.line.json` drives `terrain.py route`,
`line` and `transit-check`. Each link is its own line and its own element.

```json
{
  "element": "north-line",
  "seed": 5,
  "world": "world",
  "mode": "rail",
  "from": {"at": [120, 70, -340], "stop": "terminus"},
  "to": {"at": [940, 66, -310], "stop": "terminus"},
  "via": [[400, -360]],
  "heights": "heights.json",
  "avoid": [[300, -380, 340, -340]],
  "style": "stone",
  "limits": {"max_fill": 6, "max_cut": 8, "min_bridge": 4, "min_tunnel": 6}
}
```

| Key | Meaning |
| --- | --- |
| `mode` | `rail`, `road`, `path` or `ice` (a boat road of packed or blue ice) |
| `route` | `search` (default in the Overworld: find the route over the heights file) or `straight` (axis-aligned legs through `via`; the only choice in the Nether) |
| `from`, `to` | endpoint cells at running level, each with an optional `stop`; a null y lets the profile fit it to the ground |
| `via` | optional x/z waypoints the route must pass |
| `heights` | project-relative heights file over the search box (the endpoints and waypoints grown by a quarter of the link length, at least 64 blocks) |
| `avoid` | x/z boxes the route must stay out of; add every registry build box |
| `width`, `lanes` | path width (1-3) or road lanes (1-2, about 4 blocks each); rail and ice have fixed cross sections |
| `style` | material set per mode (`stone`, `wood`, `cobble`, `brick`, `nether`) |
| `profile` | optional fixed levels at chainage points |
| `limits` | `max_fill` 6, `max_cut` 8, `min_bridge` 4, `min_tunnel` 6, `water_clearance` 3, `fill_ratio` 1.5, `cut_ratio` 1 (rock cuts stand at 0.5) |
| `bridges` | `auto`, `beam` or `arch`, pier spacing, railings, `piers_in_water` |
| `tunnels` | bore size, lining, `roof` (rock kept above the lining) |
| `lights` | block, spacing, `min` (default 1 in the Overworld, 12 in the Nether) |
| `boosters` | spacing on the flat and on climbs (rail only) |
| `sections` | `length` along the route, default 96 |
| `version` | block-id list to check against, default `26.3` |

A Nether line sets `"world"` to the Nether world and `"route": "straight"`.

## Route and profile

- The search is A* over the heights file, coarse then refined. Rail moves along x
  or z only with a turn penalty, so it prefers long straights joined by
  single-cell corners; road, path and ice move in eight directions and are then
  smoothed to follow contours. Cost counts distance, slope, cross slope, water,
  and impassable cells: `avoid` boxes with a buffer, surface lava, unread
  columns and cells outside the heights file.
- Profile limits per mode: rail one block of rise or fall per cell, a corner and
  its two neighbours level; road half-block steps; path one block per cell with
  stairs on full steps; ice level end to end, because a boat cannot climb, so a
  change of level is a separate line.
- Over water the running level stays at least `water_clearance` above the surface.
- Stretches are classed at grade, cut, fill, bridge or tunnel. Bridges shorter
  than `min_bridge` become fill and tunnels shorter than `min_tunnel` become cuts
  where the limits allow; otherwise the route is refused with the stretch named.

## Grading

The corridor is graded to the real ground: the target is the ground clipped
between a fill slope and a cut slope that start at the formation edge, with
seeded noise on the slope and toe line so the edges do not run straight. Rock
cuts stand steeper than soil. Bridge and tunnel stretches are not graded, except
approach cuts at tunnel mouths and abutments at bridge ends. Columns the corridor
does not change are protected, and cuttings and embankments wear the local
surface palette. Never leave a line as a straight strip over hills, bare cut
faces, vertical embankments or a corridor boxed into the land.

## Rail rules

- Every rail cell has its exact `shape` (straight, corner, ascending); Ashlar
  places without physics, so nothing auto-turns and nothing fixes a wrong shape.
- Corners are single cells, level with their neighbours; slopes never meet a corner.
- Every powered rail sits on its own `redstone_block` in the ballast and is written
  `powered=true`; none on a corner or beside a junction or another component.
  Powered rails cannot be curves.
- A cart tops out at 8 blocks per second per axis. An unpowered powered rail
  brakes it. The new-minecart experiment is not enabled on the target server.
- Booster spacing is calibrated live. Defaults: every 24 cells on the level, every
  2nd cell on climbs.
- A terminus has no boosters on its last 8 cells and a launch group of 3 on cells
  9 to 11 from the end, so an arriving cart coasts to a stop against the end block
  and a rider presses forward to leave.
- Clearance over the rail is 3 blocks; trees rooted outside the corridor are trimmed.

## Surfaces

- **road**: weighted style blocks, slabs for half-steps and edges, kerbs, lamp posts.
- **path**: dirt path, coarse dirt, gravel or stone by style, irregular width.
- **ice**: a 2-wide lane of packed or blue ice with bottom-slab or wall guards.
  Use packed ice: plain ice melts within 3 blocks of a lantern.
- **stops**: `terminus` (rail), `room` (a lined, lit chamber where a tunnel line
  ends inside a hill) and `open` (the line ends at an existing open cell, such as a
  portal landing's doorway, and adds nothing there). Through-stations wait.

## Spawning

A corridor that spawns mobs is a failure.

- Overworld: block light of 1 or more stops monsters. Rails, bottom slabs, glass,
  plain ice, leaves, trapdoors, scaffolding and copper grates are not spawnable;
  packed ice and blue ice are, so ice lines are lit to the minimum.
- Nether: block light of 12 or more stops zombified piglins, piglins, endermen and
  skeletons, but hoglins (in crimson forests), magma cubes and ghasts spawn at any
  light. The toolkit's 3-wide rail and ice bores are too narrow for them (none fits
  in a 3-wide bore). Wider Nether bores and rooms
  fit them, so keep Nether paths 3 wide or use floors they cannot spawn on (bottom
  slabs). Full blocks are spawnable; bottom slabs and glass are not.
- Lights: lanterns give 15; soul lanterns only 10 and cannot reach the Nether
  minimum. Nether tunnels get lamps in pairs at floor height.
