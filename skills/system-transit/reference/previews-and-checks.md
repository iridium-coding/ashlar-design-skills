# Previews, checks and verdicts

## Previews

`route --preview` and `line --preview` write PNGs under `terrain/previews/`:

- `<element>-route.png`: the route over a hillshade, coloured by stretch class.
- `<element>-profile.png`: ground, water and the running level along the chainage,
  with bridges and tunnels marked.
- cross sections at the stretch changes, at most 12.

Judge the route map for a line that reads as paint, the profile for steep climbs
and long bridges, and the cross sections for boxed-in corridors and vertical
sides. Show them to the user for design approval. `--preview` writes only
previews and reports; no world phase is written.

## Projected checks

`line` runs these on the planned final state before any write, and emission
refuses a design that fails, naming each:

- **continuity** (rail): every planned rail cell holds the planned rail and shape and joins its neighbours.
- **support**: every rail, lantern, torch and carpet stands on, or a lantern hangs from, a block that holds it.
- **boosters**: every powered rail is `powered=true` over a `redstone_block`, none on a corner or beside a junction.
- **clearance**: planned air over the running surface (rail 2 above the rail cell at least, road and path 3).
- **walk** (road, path): each step changes walking height by at most one block, half a block on roads.
- **light**: every spawnable cell on the formation, on decks and platforms, and on every floor in tunnels, tubes and rooms has block light at least `lights.min`; graded side slopes are ordinary ground and are not lit.
- **deck**: every bridge deck column is held by a pier or arch within the span the type allows.
- **seal**: no tunnel or room interior cell touches water or lava.
- **grade**: the built running surface keeps the profile within a block.
- **portal** (pairs): frame complete, portal blocks present with the axis, and the pair check.

The emitter's own checks run too: liquids, spills, gravity, the site boundary.

## After the build

`transit-check` runs the same checks on fresh reads; the plan's `transit{file}`
row does it for the line. Reads go to `verify/<element>-<section>` (portal:
`verify/<element>-overworld` and `-nether`), never into `site/`. The report names
each failing check and the first failing cell.

## The ride test

Rail only, and only when the line's chunks fit one force-load set. It is an agent
test in the plan: a `summon` row for an empty minecart carrying the test tag on
the first rail with motion along the track, an `await` row with `entity` at the far
stop, and nothing else. `exec-ashlar test` holds the force-loads paired, kills the
test's tagged entities when each test ends and always before it releases the
force-loads. Booster spacing is set so an empty cart runs the line, which also
covers a ridden one. A longer line has no agent ride.

## Verdicts

Report the highest the evidence supports: `built` (placed), `checked` (offline
and `transit-check` pass), `agent_tested` (the ride test passed) and `ridden` (the
user rode it). Ice lines and portal pairs reach `ridden` only through the user.
