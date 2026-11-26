# system-transit on Ashlar — design

Sub-project 5 of the Ashlar adaptation. Ports Chapman's `system-transit` (the
network between builds: rail lines, roads, paths, nether hubs, bridges and
tunnels) so it designs and builds through Ashlar with `exec-ashlar`, and adds a
transit toolkit to the terrain toolkit, the way `terrain-cave` added
`terrain.caves` ([cave spec](2026-11-25-ashlar-terrain-cave-design.md),
[terrain spec](2026-11-19-ashlar-terrain-design.md),
[redstone spec](2026-11-19-ashlar-redstone-design.md)).

## Intent

`system-transit` is the last of Chapman's skills without an Ashlar port, so it
completes the fork's feature set. The user asked for builds that are stable,
good-looking and integrated with the land, and found the agent reluctant to
reshape ground around builds. A transit line is the hardest case for both: it
crosses kilometres of real terrain, and a single wrong rail stops a cart. The
user chose approach B (a port plus a transit toolkit) on 2026-11-25.

## Goals

- One link at a time, from a short design file, the toolkit finds a route
  across the real terrain, fits a vertical profile within the mode's grade
  limits, and decides where the line runs at grade, in a cutting, on an
  embankment, on a bridge or in a tunnel.
- The line is built as checked, backed-up `exec-ashlar` phases: the graded
  corridor (cuts and embankments with natural side slopes, through the existing
  terrain emitter), then track, road or path surface, bridges, tunnels, lamps
  and stops.
- Rail is right by construction: every rail cell has its exact `shape`, every
  powered rail sits on its own redstone block, corners are single cells, and
  slopes never meet a corner.
- Matched nether portal pairs, with the pair math done for the user and a check
  that no other portal will steal the link.
- Offline checks before any write and a `transit{file}` quality row after the
  build: continuity, support, boosters, clearance, light, deck support and
  tunnel seals.
- Previews the user approves from: a route map, an elevation profile and cross
  sections.
- The skill text rewritten for Ashlar, Claude Code and Codex alike.

## Non-goals (v1)

- Junctions, switches, crossings and double-track crossovers. Each link is its
  own line; a switched junction is a `system-redstone` job.
- Showpiece bridge superstructures (truss, suspension, cable-stayed). The line
  supplies the deck and the hidden piers that hold it up; the superstructure is
  a `design-monument` job on top.
- Docks, airports and elevators as generated forms. They stay as guidance in
  `reference/water-and-air.md` for the design skills.
- Station buildings and hub halls beyond a plain lined room
  (`design-building`).
- Boarding and braking machinery (launch buttons, detector stops). That is
  `system-redstone`. Command blocks stay forbidden.
- Lines in the End.

## Anti-goals (failures even if the line technically works)

- A line that reads as paint: a straight strip laid over hills, cliffs of
  bare cut face, embankments with vertical sides, or a corridor boxed into the
  land.
- A powered rail that is only `powered=true` on paper (no real source), or a
  rail that floats on air until the next block update knocks it off.
- A route through someone's build, or a player block changed without the
  user's yes.
- A corridor that becomes a mob spawner.
- A bridge deck with nothing under it.
- A tunnel that breaches water or lava, or a portal pair that links to the
  wrong portal.

## Findings that shape the design

1. **Ashlar places blocks without physics** (redstone spec, finding 1). A rail
   keeps exactly the `shape` written, which is good: nothing auto-turns. But
   every shape and every powered rail's `powered` state must be right in the
   plan, and nothing fixes a wrong one later.
2. **A powered rail needs a real source.** A source-less `powered=true` reverts
   on the next update (Chapman, learned live). Rule: every powered rail sits on
   a `redstone_block`.
3. **Minecarts** top out at 8 blocks per second per axis; corners move the cart
   diagonally; an unpowered powered rail brakes hard; uphill costs speed
   (Wiki "Minecart" → Speed, read 2026-11-25). The new-minecart experiment is
   not enabled, so these figures hold. Powered rails cannot be curves, so a
   long arc bleeds speed: rail turns are single-cell corners (Chapman, learned
   live).
4. **Portal linking** (Wiki "Nether Portal" → Portal search, read 2026-11-25):
   the destination is the entry point ÷ 8 (Overworld → Nether) or × 8, Y
   unchanged; the game picks the nearest portal by 3-D Euclidean distance,
   Y included, within 128 blocks in the Overworld and 16 in the Nether. This
   server's Paper config keeps those values (`portal-search-radius: 128`,
   vanilla dimension scaling on; read 2026-11-25).
5. **Mob spawning** (Wiki "Mob spawning", read 2026-11-25): Overworld monsters
   need block light 0, so block light ≥ 1 stops them; Nether monsters spawn at
   block light 11 or less, so a Nether corridor needs block light ≥ 12 or
   floors they cannot spawn on. Hostile mobs need a full solid top surface
   (bottom slabs do not count) and cannot spawn on glass, plain ice,
   leaves, trapdoors, scaffolding or copper grates; rails stop spawns in their
   own cell. Packed ice and blue ice are spawnable.
6. **The terrain emitter can grade a corridor.** `materialize_live` and
   `emit_field` take a designed surface, a `protect` mask of columns to leave
   untouched (no surface repaint outside the corridor) and voxel `forms`
   (carve or build), and run the liquid, spill and gravity checks, column
   backups, tiling, expected-surface (`surface_match`) and `seam` rows. The
   cave port showed forms-only layers through `check_form_layers`; transit
   needs the surface pass too, so it uses `emit_field`.
7. **`Centerline`** (terrain toolkit) gives every column its distance along a
   polyline and its signed offset from it, the natural coordinates for a road
   cross section. `belt_from_path` and pads are close but grade to fixed
   levels, not to a sloping formation clipped against the real ground.
8. **`exec-ashlar` already checks** walkability, polyline routes
   (`connectivity{via}`), headroom and doors, and its `test` mode (from the
   redstone port) runs tagged test entities under paired force-loads. Chapman's
   skill names about ten tools the fork does not have (`exec-worker`,
   `exec-blueprint`, `exec-inspect`, `survey-site`, the registry storage,
   `continuity.py`, structure sleeves, `text_display` spawn ops, `block-nbt`
   ops, `level_get_mob_spawns`).
9. **Reads are box-shaped and bounded** (200,000 cells per read, 1,024 columns
   per `columns` call). A long diagonal route has a huge bounding box, so the
   line works in sections, each with its own exact read.

## Approaches considered

| | Approach | Trade-off | Outcome |
| --- | --- | --- | --- |
| A | Text port plus a rail-continuity check | Smallest; every route, profile and rail shape is laid by hand, so quality varies and curves and slopes go wrong | Rejected |
| B | Port plus a transit toolkit: route search, profile, corridor grading through the terrain emitter, generated infrastructure, portals, checks and previews | Largest new code; consistent, checked lines that fit the land | **Chosen by the user** |
| C | Text port plus a track generator, its check and portal math; routing and grading by hand | Middle size; the land fit is still manual, which is the user's main complaint | Rejected |

## Design

### Commands (`terrain.py`)

| Command | Does |
| --- | --- |
| `route DESIGN --project DIR [--preview]` | Finds the route and profile over the heights file, classes every stretch (grade, cut, fill, bridge, tunnel), splits the line into sections and writes `terrain/<element>.route.json` with the section read boxes, previews and a report |
| `line DESIGN --project DIR --first-phase N [--preview] [--standalone] [--approve-built TOKEN]` | Reads the route and each section's site read, builds the corridor surface and the forms, runs the projected checks and writes the phases, plan rows, report and previews |
| `portal DESIGN --project DIR --first-phase N [--preview] [--standalone]` | Computes or checks a portal pair, lists the boxes to read, and (with both reads) writes the frame and landing phases for each world |
| `transit-check DESIGN --sites DIR… [--project DIR]` | Checks fresh post-build reads of a line or portal pair; prints JSON; exits 1 on a failure |

### The line design file (`terrain/<element>.line.json`)

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
| `from`, `to` | endpoint cells at running level (rail cell, road surface or ice), each with an optional `stop`; a null y lets the profile fit it to the ground |
| `via` | optional x/z waypoints the route must pass |
| `heights` | project-relative heights file (`ashlar_place.py heights`) over the search box: the box around the endpoints and waypoints, grown by a quarter of the link length (at least 64 blocks) |
| `avoid` | x/z boxes the route must stay out of, with the registry's build boxes added by the skill |
| `width`, `lanes` | path width (1–3) or road lanes (1–2, about 4 blocks each); rail and ice have fixed cross sections |
| `style` | material set per mode (for example `stone`, `wood`, `cobble`, `brick`, `nether`) |
| `profile` | optional fixed levels at chainage points; otherwise the toolkit fits it |
| `limits` | `max_fill` (embankment height before a bridge, default 6), `max_cut` (cut depth before a tunnel, default 8), `min_bridge` (4), `min_tunnel` (6), `water_clearance` (running level above a water surface it crosses, default 3), `fill_ratio` (horizontal per vertical on embankments, default 1.5), `cut_ratio` (1 in soil; rock cuts stand at 0.5) |
| `bridges` | `auto`, `beam` or `arch`, pier spacing, railings, `piers_in_water` (see below) |
| `tunnels` | bore size, lining, `roof` (rock kept above the lining) |
| `lights` | block, spacing, `min` (default 1 in the Overworld, 12 in the Nether) |
| `boosters` | spacing on the flat and on climbs (rail only) |
| `sections` | `length` along the route (default 96) |
| `version` | block-id list to check against, default `26.3` |

A Nether line sets `"world": "world_nether"` (or the server's Nether world
name) and `"route": "straight"`: height reads in the Nether return the bedrock
roof, so there is no heights search there (see Nether lines below).

### Route (plan view)

- A grid search (A*) over the heights file, coarse first (down-sampled) and
  then refined in a band around the coarse path, so a 2 km link stays fast.
- Moves: rail moves along x or z only, with a turn penalty, so it prefers long
  straights joined by single-cell corners; road, path and ice move in eight
  directions, and the road and path centre lines are then smoothed so they
  follow the contours.
- Cost per step: distance, plus slope along the step, plus cross slope (a line
  across a steep side-slope needs big cuts and fills), plus water (a crossing
  costs per block of width), plus impassable cells: `avoid` boxes with a buffer,
  surface lava, unread (null) columns and cells outside the heights file.
- Waypoints split the search into legs.
- `straight` routes skip the search: axis-aligned legs from `from` through
  each `via` point to `to`, joined by single-cell corners.

### Profile (elevation)

- A dynamic program along the route's chainage over candidate levels picks the
  running level at every cell, minimising cut and fill (weighted by the cross
  section each costs) plus bridge and tunnel costs, subject to the mode's
  rules:
  - rail: at most one block of rise or fall per cell; a corner cell and its
    two neighbours are level; climbs carry boosters at the climb spacing;
  - road: half-block steps (slab resolution), at most one half-step per cell;
  - path: at most one block per cell, with stairs on full steps;
  - ice: level end to end, because a boat cannot climb; both endpoints must
    share the running level, and a change of level is a separate line.
- Over water the running level stays at least `water_clearance` above the
  surface.
- Endpoints and any fixed `profile` points are hard constraints.
- Stretches are classed: at grade (within a block of the ground), cut, fill,
  bridge (the fill would exceed `max_fill`, or the line crosses water or air),
  tunnel (the cut would exceed `max_cut` and the rock above the bore keeps
  `roof`). Bridges shorter than `min_bridge` become fill and tunnels shorter
  than `min_tunnel` become cuts where the limits allow; otherwise the route is
  refused with the stretch named.

### Nether lines

A Nether line runs level at the running level the design gives (between the
lava sea and the roof), along its straight legs. There is no ground to grade,
so `line` classes every cell from the section reads instead of the heights:
a bore in rock is tunnel, a bore through open air is a tube (an enclosed deck
with walls and a roof on piers or hung from the rock), and lava in the bore or
its lining shell is a refusal that names the cell, so the skill picks another
level or leg. The same classing applies to any `straight` line underground in
the Overworld.

### Corridor surface (grading)

For each section, a designed surface over the section box: the existing ground
everywhere, except inside the corridor, where (using `Centerline` distance `s`
and offset `d`) the target is the ground clipped between a fill slope and a cut
slope that both start at the formation edge:

```
lo(s, d) = formation(s) - (|d| - half(s)) / fill_ratio   # embankment
hi(s, d) = formation(s) + (|d| - half(s)) / cut_ratio    # cutting
target   = clip(ground, lo, hi)    # equals formation(s) inside the formation
```

Seeded noise on the slope ratio and the toe line keeps the edges from running
straight; rock cuts may stand steeper than soil cuts. Bridge and tunnel
stretches are not graded (their columns are protected), except the approach
cuts at tunnel mouths and the abutments at bridge ends, which are graded like
any cut or fill. Columns the corridor does not change are protected, so their
surface is not repainted. Surface materials on the graded ground come from the
site's surrounding palette (`apron.surrounding_palette`) through a
`MaterialSpec`, so cuttings and embankments wear the local grass, dirt, sand
or stone.

### Infrastructure forms

Generated in memory (or as project assets) per section and emitted with the
surface by `emit_field`:

- **rail**: a ballast bed (3 wide, by style) at formation level; rails one
  above with exact shapes (straight, corner, ascending); powered rails on
  straights at the booster spacing, closer on climbs, each on its own
  `redstone_block` in the ballast and written `powered=true`; no powered rail
  on a corner or beside a junction; clearance cut to 3 blocks over the rail
  (leaves and logs of trees rooted outside the corridor are trimmed).
- **road**: a surface of the style's weighted blocks, slabs for half-steps
  and at the edges, kerbs, and lamp posts at the light spacing; width varies
  by a block along the edges where the style allows.
- **path**: dirt path, coarse dirt, gravel or stone by style, irregular width,
  stairs on full steps.
- **ice**: a 2-wide lane of packed or blue ice with bottom-slab or wall guards,
  bottom-slab walkways where there is room, and lights to the corridor's
  minimum (finding 5: packed and blue ice are spawnable).
- **bridges**: `beam` (deck on piers every 6–8 blocks) or `arch` (a segmental
  arch per span, 16–40 blocks, built from the deck down to the springing
  piers), railings by style. Piers stand on solid ground. They may stand in
  still water only with `piers_in_water: true`; the water cells they replace
  are counted and named in the report and the approval covers them. Never in
  flowing water or lava.
- **tunnels**: a rectangular or arched bore (rail 3×4, road lanes × 5, path or
  ice 3×3 or more) inside a one-block lining shell, lights set into the lining,
  and framed mouths. A bore or lining cell that would meet water or lava is
  refused, like the cave checks; the lining replaces natural rock, an existing
  solid block that is not natural is kept as lining (never overwritten), and
  existing caves the tunnel crosses are sealed by the shell.
- **stops**: `terminus` (rail: a level end against an end block with no
  boosters on its last 8 cells, so an arriving cart coasts to a stop at the
  block and a rider presses forward to leave; a level platform beside it),
  `room` (a lined, lit end chamber where a tunnel line ends inside a hill) and
  `open` (the line ends at an existing open cell, such as a portal landing's
  doorway, and adds nothing there). Through-stations wait for a later version.
- **lights**: lamp posts in the open, lights in tunnel linings and under bridge
  decks where they light the deck; the spacing is computed, then confirmed by
  the light check.

### Portals (`terrain/<element>.portal.json`)

```json
{
  "element": "east-gate",
  "overworld": {"world": "world", "at": [3600, 70, 0], "axis": "x"},
  "nether": {"world": "world_nether"},
  "size": [4, 5]
}
```

- One end is given (new or an existing portal the user names); the other is
  computed: x and z ÷ 8 (or × 8), the y chosen in a safe pocket (Nether: an
  enclosed landing above the lava sea and below the roof).
- `portal` lists the boxes to read around both arrival areas. An entity can
  step through anywhere in the portal's opening, so the arrival area is the
  opening scaled to the other world (a 2-wide Nether opening spreads over 16
  blocks in the Overworld). The pair passes when, for every arrival point, the
  partner portal is nearer (3-D, Y included) than every other portal block in
  the read, and inside the search radius.
- It writes, per world, an obsidian frame, `nether_portal` blocks with the
  axis (placed without physics, so no lighting step is needed) and a landing:
  a platform in the Overworld, an enclosed, lit room in the Nether. The
  landing has a framed doorway for each line the design lists (`doorways`), so
  a nether hub is a portal landing whose doorways the spoke lines end at
  (`stop: open`). The skill routes the spokes first, so the doorways are known
  before the landing is built.
- Chapman's "gold blocks beside each portal keep piglins neutral" is dropped
  unless the Wiki confirms it at implementation (piglins stay neutral to a
  player wearing gold armour).

### Player blocks

As in `terrain-cave`: every player block a line or portal would change is
listed with position, action and reason, plus `loses_data` for containers
and signs; the list gets a token and emission needs `--approve-built TOKEN`
after the user's yes. The route search also treats every non-natural block
found in a section read as a reason to reroute; the skill re-runs `route` with
an `avoid` box before asking the user to approve touching a build.

### Checks

Projected before any write (on the planned final state) and again after the
build (`transit-check` on fresh reads):

- **continuity** (rail): every planned rail cell holds the planned rail with
  the planned shape, and each joins its neighbours;
- **support**: every rail, lantern, torch and carpet stands on (or a lantern
  hangs from) a block that holds it;
- **boosters**: every powered rail is `powered=true` over a `redstone_block`,
  none on a corner, none beside a junction or another redstone component;
- **clearance**: the planned air over the running surface (rail 2 above the
  rail cell at least, road and path 3);
- **walk** (road and path): each step changes the walking height by at most
  one block, half a block on roads;
- **light**: every spawnable cell on the formation (the running surface, its
  walkways and shoulders), on bridge decks and platforms, and on every floor
  in tunnels, tubes and rooms has block light ≥ `lights.min`, using the cave
  light model; the graded side slopes are ordinary ground and are not lit;
- **deck**: every bridge deck column is held by a pier or arch within the
  span the type allows;
- **seal**: no tunnel or room interior cell touches water or lava;
- **grade**: the built running surface keeps the profile within a block;
- **portal** (pairs): frame complete, portal blocks present with the axis, and
  the pair check above on fresh reads.

The emitter's own checks run as usual: liquids, spills, gravity, the site
boundary. Emission refuses a design whose projected checks fail, naming each.

### Outputs

- `terrain/<element>.route.json`, `.route-report.json`, previews
  `<element>-route.png` (route over a hillshade, coloured by stretch class),
  `<element>-profile.png` (ground, water and the running level along the
  chainage, with bridges and tunnels marked) and a few cross sections at the
  stretch changes (at most 12).
- `phases/NN-<element>-sNN-…` per section (surface, forms, stops, lights;
  via `placer`, rollback `backup`), `terrain/<element>.plan-rows.toon` with the
  phases, notes and quality rows (`transit`, `surface_match`, and `seam` rows
  along the corridor's outer edges only, never at the internal section
  boundaries, which are graded by the neighbouring section), and
  `terrain/<element>.line-report.json`.
- `--preview` writes only previews and reports.
- The registry entry keeps the usual overall `bbox` and adds `boxes` (the
  section boxes); `exec-ashlar`'s overlap check uses `boxes` when present, so
  a long diagonal line does not overlap every build inside its bounding box.

### Verification and tests

- The `transit{file}` row in `exec-ashlar` (plan format and verification
  references): take fresh exact reads of every section box and run
  `transit-check`.
- An agent ride test for rail through `exec-ashlar test`: summon a tagged empty
  minecart at the start with motion along the track inside paired force-loads
  of every chunk of the line, wait, read its position, and kill it. It runs
  only when the line's chunks fit one force-load set; otherwise the user's
  ride is the only ride verdict. Booster spacing is set so an empty cart runs
  the line, which also covers a ridden one. Verdicts follow the redstone
  model: `built`, `checked`, `agent_tested`, `ridden`.
- Offline tests (synthetic sites, as in `test_caves.py`): route around an
  avoid box and across a valley; profile limits per mode; corners level; rail
  shapes and ascending directions; booster placement; cut and fill slopes
  clipped to the ground; bridges and tunnels chosen at the limits; piers in
  water refused without the flag; tunnel seal refusals; Nether classing
  (tunnel, tube, lava refusal); ice lines held level; light checks in both
  dimensions; portal pair math, the arrival spread and a stealing portal;
  lining that keeps built blocks; the player-block token; the CLI.

### Skill and references

`skills/system-transit/SKILL.md` and its references rewritten for Ashlar
(names from finding 8 removed): survey (sites, the registry, a heights file
over the search area), the interview, topology and modes (kept, corrected),
`route --preview` per link, the section reads, `line --preview`, the design
gate with the previews and reports, emission, `exec-ashlar build`, the
`transit` row, the ride test and the user's ride. Seams stay: stations and
hub halls to `design-building`, superstructures to `design-monument`,
junctions, launchers and brakes to `system-redstone`, the last stretch into a
base to the design skills. `terrain-integrate` is included by default for the
stops and landings that meet builds. Text rules from §7.5 of the sub-project 1
spec apply (labelled `Claude Code:`/`Codex:`/`Otherwise:` lines).

Other edits: `toolkit-api.md`, `exec-ashlar` plan-format and verification
references, README, TAXONOMY, CLAUDE.md, `test_skill_text.py`, and the
workspace links after merge.

### Live calibration (after merge, each run with the user's yes at the time)

1. A rail line of about 150 blocks in the overworld scratch area with a climb,
   a corner, a short bridge, a short tunnel and two termini; agent ride test,
   then the user's ride; then roll back unless the user keeps it. This sets the
   booster spacing on the flat and on climbs.
2. A portal pair and a short Nether ice tunnel from the Nether landing; the
   user's boat ride; roll back.

Findings flow back as follow-up PRs, as in the redstone and cave ports.

## Decisions

| Topic | Decision | By |
| --- | --- | --- |
| Approach | B: port plus transit toolkit | user, 2026-11-25 |
| Player blocks | May be changed only after the user sees what, where and why and says yes (token) | user, 2026-11-25 (cave rule, applied here) |
| Grading | Corridor grading is part of the line (default-on integration) | user, 2026-11-25 (integration rule) |
| Scope | v1 covers rail, road, path and ice lines, beam and arch bridges, tunnels, stops, portal pairs; the non-goals wait | builder (mine) |
| Sections | Lines work in sections of about 96 blocks, each with its own read and phases | builder |
| Grading engine | `emit_field` with a protect mask and generated forms | builder |
| Boosters | Each powered rail on its own `redstone_block`; spacing from live calibration | builder |
| Turns | Rail: single-cell corners, level at and beside the corner | builder |
| Stations | Termini work without redstone: an arriving cart coasts to a stop against the end block, a rider presses forward to leave | builder |
| Nether routing | Straight legs at a fixed level, classed from the 3-D reads (tunnel, tube, lava refusal) | builder |
| Nether hubs | A portal landing with doorways; spoke lines end at them and never overwrite built blocks | builder |
| Piers in water | Only with `piers_in_water: true`, still water only, displaced cells counted and approved | builder |
| Nether light | Block light ≥ 12 on every spawnable cell, or floors mobs cannot spawn on | builder |
| Agent ride test | Empty tagged cart, only when the line fits one force-load set | builder |

## Left to the builder

- Exact costs, coarse-grid factor, smoothing and noise parameters; style
  palettes; pier spacing within the stated range; arch profiles.
- Whether forms are passed to `emit_field` in memory or as project assets.
- Whether the cave light model moves to a shared module or is imported.
- How section boundaries overlap so continuity is checked across them.
- Whether `ashlar_place.py backup` gains a multi-box mode for section reads, or
  the skill loops over the boxes `route` lists.
- The force-load set limit for the agent ride test, within `exec-ashlar`'s
  runner rules, and whether its `test` mode can hold force-loads across a
  wait or needs that added (force-loads stay paired and are always released).
