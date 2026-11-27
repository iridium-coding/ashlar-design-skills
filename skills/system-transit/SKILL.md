---
name: system-transit
description: >-
  Designs and builds the transit between builds in a Minecraft Java world
  reached through Ashlar: rail lines, roads, footpaths, ice-boat roads, bridges
  and tunnels, matched nether portal pairs and nether hubs. Chooses the network
  topology, finds each route over the real terrain, grades the corridor, lays
  checked track and surface, and tests the ride. Use when the user wants to
  connect two or more sites or asks for a rail line, a road, a highway, a bridge,
  a tunnel or a nether hub between places.
model: opus
effort: high
allowed-tools: mcp__ashlar__mc_status mcp__ashlar__mc_players mcp__ashlar__mc_survey mcp__ashlar__mc_render mcp__ashlar__mc_inspect
metadata:
  short-description: Route, grade, build and ride-test rail, road, path and ice lines and portal pairs through Ashlar
---

# system-transit

You design the network between builds: how a player gets from one base,
village or landmark to another. You choose the topology, then take one link at
a time from a short design file through route search, corridor grading, checked
track and surface, bridges, tunnels, stops and portal pairs. The toolkit does
the geometry and the checks; `exec-ashlar` builds it.

## When to use, and not

Use when two or more sites need a link. Do not use for:

- Streets inside one city or district: `design-city`.
- A station hall or terminal: `design-building` (you supply the line's end and
  the footprint).
- A path through wild scenery with no network: `terrain-shape`; a designed
  garden path: `design-grounds`.
- Junctions, switches, crossings, launch buttons and detector brakes:
  `system-redstone`. Command blocks stay forbidden.
- Truss, suspension or cable-stayed superstructures: `design-monument` on top
  of the deck and hidden piers the line supplies.
- Lines in the End.

## Connection

Run `mc_status`. If Ashlar is unreachable, stop and tell the user. For a
standalone request, start a project in `.minecraft-builder/<project>/`. A line
or portal pair for an existing design project goes in that project's plan,
before the stations and halls that meet it.

## Survey

Run `exec-ashlar survey <project>` using `../exec-ashlar/reference/survey.md`
for the sites and the world. Read `.minecraft-builder/registry.json` for the
existing builds: their boxes are routes' `avoid` boxes and the user's list of
what must not be touched. Record every site's name, dimension and coordinates
and who owns each build; no real names, addresses or coordinates go in the
fork itself.

Interview the user with [interview.md](reference/interview.md): the sites,
whether one is a centre, distances, speed against scenery, era, tolerance for
grading, builds to preserve and the project name.

- Claude Code: use `AskUserQuestion` for choices.
- Codex: use `request_user_input` when available.
- Otherwise: ask in plain text.

Then choose the topology and each link's mode with
[topology.md](reference/topology.md), and settle each link's endpoints, stops,
`via` points and style.

## Design a line

Write the line design as [lines.md](reference/lines.md) describes; it may live anywhere,
and `line` copies it to `terrain/<element>.line.json`, where the `transit` row reads it.
Each link is its own line and its own element. Order the links with the user
(a network is built and checked link by link), then for each link:

1. **Heights.** For an Overworld search route, write a heights file over the
   search box: the box around the endpoints and waypoints, grown by a quarter of
   the link length (at least 64 blocks).

   Run `ashlar_place.py heights --area X1 Z1 X2 Z2 --out .minecraft-builder/<project>/heights.json`
   from `../exec-ashlar/scripts/` as `exec-ashlar` describes.

   A Nether line or any `straight` route needs none: Nether height reads return
   the bedrock roof, so it is classed from the section reads instead.
2. **Route.** Run `terrain.py route DESIGN --project DIR --preview` as the
   [toolkit API](../terrain-shape/reference/terrain/toolkit-api.md) shows. Read the
   report (kinds, maximum cut and fill, the bridge and tunnel runs, the section
   list) and the previews under `terrain/previews/` as
   [previews-and-checks.md](reference/previews-and-checks.md) explains.

   - Claude Code: use `Read` on the PNG files.
   - Codex: use `view_image` on the PNG files.
   - Otherwise: give the report's measurements and ask the user to open the files.

   A refusal names the stretch (a bridge or tunnel shorter than its minimum
   that the limits cannot absorb, water or lava in the way, a box outside the
   heights file). Change the route, the limits or the endpoints; never read a
   refusal as a reason to remove water.
3. **Section reads.** The route report lists one read per section: `box`, `out`
   and `world`. Take each exact read with
   `ashlar_place.py backup --box X1 Y1 Z1 X2 Y2 Z2 --out .minecraft-builder/<project>/site/<element>-sNN`
   (add `--world` for the Nether). Run `terrain.py survey --site DIR --box …` on a
   section only to see its non-natural blocks. A section that holds someone's
   build is not yours to cross: add an `avoid` box and run `route` again, and ask
   about touching it only when no other route exists.
4. **Line preview.** Run
   `terrain.py line DESIGN --project DIR --first-phase N --preview`. It checks the
   whole line on the planned final state and writes the report, previews and
   projected checks. Read the notes, the stretch kinds, the displaced-water count,
   `unsupported_tube` and the `built` list. Iterate on the design and preview
   again until the checks pass; emission refuses a design whose projected checks
   fail, naming each. Raise `limits` only with the user's OK.

## Player blocks and approval

The report's `built` list names every player block the line would change: where
it is, what it is and why, with `loses_data` for a chest, sign or other block
whose contents or text would be lost. Show the user that whole list in plain
words, group it by block with positions and reasons, and ask whether to go
ahead. A block they want kept means an `avoid` box and a new route. Only after
their yes, pass the report's token as `--approve-built TOKEN`; a changed design
gets a new list and a new token. A line with an empty `built` list needs no
token.

Get **design approval** on the route map, the profile, the cross sections, the
stretch kinds, any bridge piers in water (only with `piers_in_water: true`, still
water only, the displaced cells counted in the report), any grading beyond the
limits, the lights and the stops. Approval of a design is not approval of the
build.

## Portal pairs and hubs

Where a link goes through the Nether, or a hub is wanted, write
`terrain/<element>.portal.json` as [nether-hub.md](reference/nether-hub.md)
describes. Route and approve the spoke lines first: each doorway the landing
needs is known only then, and the spokes end at it (`stop: open`).

Run `terrain.py portal DESIGN --project DIR --first-phase N --preview`. While
reads are missing it lists the boxes to read around both arrival areas, into
`site/<element>-overworld` and `site/<element>-nether`. Take them (with
`--world` for each) and run it again: it checks the pair, including the arrival
spread, and any other portal that would steal the link, then writes the frame
and landing phases for both worlds. Player blocks and the token work as for a
line. The Nether landing gets a bottom-slab floor and lanterns. A piglin stays
neutral only to a player wearing a piece of golden armour; placed gold blocks do
not calm it.

## Emit and build

When the design is approved, emit by running `terrain.py line DESIGN --project
DIR --first-phase N` (add `--approve-built TOKEN` if the list is not empty, and
`--standalone` for a plan of its own; `--standalone` and `--preview` cannot be
combined), then `terrain.py portal` the same way for a portal pair. Merge the
rows in `terrain/<element>.plan-rows.toon` into the host plan; they are the plan,
not the per-section `terrain/<element>-sNN.*` files the emitter leaves beside
them. Each section's phases (surface, forms, stops, lights) roll back from a
column backup. Number the phases so the line's come before the stations and
halls that meet it. For rail, also put the ride test in the plan now (see After the
build), so the build approval covers it.

Record the line report's `boxes` in the project's registry entry (the section
boxes, as inclusive `[x1, y1, z1, x2, y2, z2]` lists), beside the usual overall
`bbox`, so `exec-ashlar`'s overlap check uses them and a long diagonal line does
not collide with every build inside its bounding box. Read the file, change only
this project's entry and write the whole file back.

Stops and landings that meet builds are footprints: include `terrain-integrate`
(planned mode) for the ground around them in the same design, unless the user
declines it at approval. Hand off to `exec-ashlar build <project>` for its own
**separate build approval**.

## After the build

1. **`transit` row.** The row comes from `terrain/<element>.plan-rows.toon`. `exec-ashlar verify` takes fresh exact reads of every
   `boxes` entry into `verify/<element>-<section>` (for a portal, `verify/<element>-overworld`
   and `-nether`) and runs `terrain.py transit-check`. Never write these reads
   into `site/`: a re-run of `line` would class the built bores as tubes.
2. **Ride test (rail).** For a line whose chunks fit one force-load set, the plan's
   agent test is a `summon` of a tagged empty minecart on the rail with
   motion along it, `await … entity` at the far stop, nothing else. `exec-ashlar
   test` holds paired force-loads and kills the test's tagged entities before it
   releases them. A longer line has no agent ride; the user's ride is its only
   ride verdict. See [previews-and-checks.md](reference/previews-and-checks.md).
3. **The user's ride.** Ask the user to ride the line end to end, with a boat on
   ice lines. Report a verdict as `built`, `checked`, `agent_tested` or
   `ridden` and no higher than the evidence. Booster spacing is calibrated live;
   if the cart stalls, say where, adjust `boosters` and emit an iteration with
   fresh backups.
4. Post-build reads never go into `site/`; to change the line, edit the design
   and emit an iteration. A full rollback restores phases newest first.

## Seams

- Station halls, terminals, control towers → `design-building`.
- Truss, suspension or cable-stayed superstructures, sculpture on a bridge →
  `design-monument`.
- Junctions, switched crossovers, launch buttons, detector brakes, elevator
  activators and drawbridge lifts → `system-redstone`.
- The last stretch into a base or village → `design-house` / `design-village`;
  city streets → `design-city`; greenways and plazas → `design-grounds`.
- Mountain passes or larger grading than the corridor's → `terrain-shape`.
- Docks, airports and elevators are guidance in
  [water-and-air.md](reference/water-and-air.md); the line does not generate them.

## Reference library

Read the file for the step you are on; do not load them all up front.

| File | Covers |
| ---- | ------ |
| `reference/interview.md` | The adaptive interview. |
| `reference/topology.md` | Topologies, route-finding and mode selection. |
| `reference/lines.md` | The line design file, modes, rail and spawning rules, grading, bridges, tunnels, stops. |
| `reference/nether-hub.md` | Portal pairs, the arrival spread, landings with doorways, Nether lines. |
| `reference/bridges-tunnels.md` | Bridge and tunnel choice, piers, seals, water. |
| `reference/previews-and-checks.md` | Previews, projected and post-build checks, verdicts, the ride test. |
| `reference/water-and-air.md` | Docks, airports, elevators and their seams. |

## Non-negotiables

1. No world write without the user's yes at the time; the design is approved
   before emission and the build is approved separately.
2. Never change a player's block until the user has seen what, where and why,
   and said yes (`--approve-built`).
3. Never route through a build without the player-block approval; route around it.
4. Every powered rail sits on its own `redstone_block`; corners are single cells,
   level with their neighbours; slopes never meet a corner.
5. Never put a pier in flowing water or lava, or a tunnel or bore cell against
   water or lava.
6. Both ends of a portal pair are built and the pair check passes; never rely on
   a game-generated portal.
7. Light every spawnable cell to the corridor's minimum; in the Nether use
   lanterns (soul lanterns give only 10).
8. Never claim a ride you did not see: the verdict follows the evidence.
9. Keep server-specific facts (addresses, hosts, player names, real coordinates,
   a world list) out of the fork; they live only in the user's project.
