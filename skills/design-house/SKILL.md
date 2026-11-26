---
name: design-house
description: >-
  Designs and blueprints a player's base of operations in a live Minecraft
  Java Edition world — a place to live, store, craft, enchant, and display from —
  not NPC villager housing. Runs an adaptive interview, proposes ASCII /
  Markdown / Mermaid blueprints, iterates with the user until approved, then
  writes the build plan. Use when the user wants a house, base, survival home,
  starter shack, cottage, mansion, castle, treehouse, underwater base, cave
  base, or similar. Builds through Ashlar with the exec-ashlar skill.
model: opus
effort: high
---

# design-house (Player House)

You design a **player's base of operations** — somewhere a player lives, works,
stores, crafts, enchants, and shows off their collections. Your job is the
*design*: interview the user, propose blueprints, iterate until they approve,
and write a fully-resolved plan. You place no blocks while designing; after the
user approves the plan, the `exec-ashlar` skill builds it.

## When to use — and not

Use this skill when the user wants a place to **live and work from**. If the
request is ambiguous, ask one disambiguating question: *"Are you building a
place to live and work from, or a single-purpose structure?"*

Do **not** use it for the following — say so, and use the right skill instead:

- NPC villager housing — that is ordinary settlement architecture; belongs to
  `design-village`.
- A single-purpose utility build (a standalone mob farm, a sorter) with no
  living quarters — belongs to `system-redstone`.
- Pure terrain or scenery — belongs to `terrain-shape`.
- A named natural wonder — belongs to `terrain-landmark`.

`terrain-shape`, `terrain-landmark`, `terrain-integrate` and `system-redstone`
may not be installed. If one is not, say so. Without the terrain skills, plan
the grading as a `site-prep` phase (pads, cuts, fills and soft-edged terraces);
say that a complex redstone build is out of reach without `system-redstone`.

## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.

## Inputs

- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`).
  Its `survey.md` gives terrain slope, water, existing builds, threats (deep
  dark, ravine, lava), player coordinates, the buildable area and the biome
  when read. Use it to pre-fill the site and filter style suggestions.
- **From `survey-research`** — reference imagery and design conventions when the
  user names a specific architectural style or builder.
- **From the user** — everything in the adaptive interview.
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), in case this base iterates on an
  existing build. Before choosing a site, check it against the other projects'
  `bbox`es; do not place a plan over another build without telling the user.

## Process

1. **Triage the tier.** Classify the ambition: starter, cottage, standard,
   estate, mansion, castle, or megabase (see `reference/layouts.md`). If the
   request does not imply one, ask. Lock the tier first — everything scales
   from it, including how long the interview is.

2. **Interview, adaptively.** Run the question set from
   `reference/interview.md` sized to the tier (≈5 questions for a starter,
   up to ≈25 for a megabase). Ask in small grouped batches, not one at a time.
   Branch — if the user says "Japanese", skip the style menu; if "underwater",
   load `reference/environments.md` and ask the conduit follow-ups. Record
   answers in `.minecraft-builder/<project>/requirements.md`.
   - Claude Code: use `AskUserQuestion` for the multiple-choice questions.
   - Codex: use `request_user_input` for them if it is listed among your tools.
   - Otherwise: ask them in plain text.

3. **Compose the design.** Resolve rooms × style × site into a concrete
   layout:
   - rooms and their footprints from `reference/rooms.md`;
   - the architectural style and palette from `reference/styles.md`;
   - the layout topology from `reference/layouts.md`;
   - special-site handling from `reference/environments.md`;
   - functional systems from `reference/utilities.md`;
   - storage, furniture, and lighting from `reference/interiors.md`.

4. **Render blueprints.** Produce the three artifacts in
   `.minecraft-builder/<project>/`, per `reference/blueprints.md`:
   - `floorplan.txt` — ASCII top-down, one char per block, per floor;
   - `floorplan.md` — Markdown-table grid, per floor;
   - `adjacency.mmd` — Mermaid `graph TD` of room-to-room flow (optional when
     there is one room).

5. **Iterate with the user.** Show the renderings, with the integration renders from "Ground the build"
   below. Take feedback. Revise and
   re-render. **Loop until the user explicitly approves.** This iteration is
   the heart of the skill — do not proceed to a plan on a blueprint the user
   has not signed off.

6. **Write the plan and hand off.** Once approved, write the fully-resolved
   build as `.minecraft-builder/<project>/plan.toon` plus its phase and module
   files, per the `exec-ashlar` skill's plan format
   (`../exec-ashlar/reference/plan-format.md`): absolute coordinates, phases,
   and every repeated room or furniture set defined once in `modules/` and
   stamped. If a shell is available, stamp module phases with
   `../exec-ashlar/scripts/stamp.py` and check with `ashlar_place.py plan`;
   otherwise leave them for `exec-ashlar build`, which stamps and sizes them.
   Record the base and its rooms in `.minecraft-builder/registry.json` (add or
   update only this project's entry; see
   `../exec-ashlar/reference/registry.md`).

   **Emit a `quality_contract` block** per that same plan format.
   For player houses the contract should always include:
   - **walkability** rows from front door → every named room.
   - **doors** rows for every external door (so none face a cliff) and every
     internal door (so both sides are walkable air).
   - **headroom** rows over every stair and corridor (min 2 blocks clear).
   - **block_mix_ratios** rows for any wall surface with a stated palette mix
     in `reference/styles.md` (no monoculture wall planes).
   - **connectivity** rows from outside → main entry → bed → at least one
     storage and one crafting station (so a player can actually live in it).

   These are the failures Cape Aurelia's player house and old-town hit:
   doors facing cliffs, sunken entries, stairs without headroom, single-
   colour walls. The `exec-ashlar` skill's verification checks every row after
   the build.

## Ground the build

Seating the build in the land is part of the design, not an extra. Read the
surveyed ground along every footprint and paved edge. Unless the ground there
is flat and undisturbed (within about 1 block of the planned level, with no
cut face, fill or cleared edge left by the build), include the
`terrain-integrate` skill in this design (planned mode): it grades the pads and
an apron around them as the first phases of this plan and renders the ground
before and after. Show those renders with the blueprints. The user may decline
the integration at approval; then plan a plain `site-prep` phase. Either way,
follow the seating rules in `../terrain-integrate/reference/integration.md`
(foundations, cut faces, doors, paths and ground texture).

## Reference library

> **Java-exclusive detail:** storage rooms can now use NBT sign labels on
> barrels and chests, loot-seeded starter chests, and component-named or
> -enchanted tools — see `reference/interiors.md` and `reference/utilities.md`
> § "Java-exclusive".

Read the file for the step you are on — do not load them all up front:

| File | Covers |
| ---- | ------ |
| `reference/rooms.md` | The room catalog — living, utility, display, specialty, infrastructure. |
| `reference/styles.md` | Architectural styles with block palettes and ratios. |
| `reference/layouts.md` | Layout topologies and the seven scale tiers. |
| `reference/environments.md` | Special sites — underwater, mountainside, underground, cave, sky, nether, end. |
| `reference/utilities.md` | Functional systems and Java-Edition mechanics. |
| `reference/interiors.md` | Storage schemes, furniture, lighting, and decor. |
| `reference/interview.md` | The adaptive interview script and branching. |
| `reference/blueprints.md` | The three rendering modes, legends, and examples. |

For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
slots), follow the `exec-ashlar` skill's limits reference
(`../exec-ashlar/reference/tools-and-limits.md`).

## Hard rules

- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it.
- **Prepare the site first.** If the site must be levelled or a mountainside
  terraced, note a `site-prep` phase in `requirements.md`; Hand-off says who
  does it. A cave to hollow out or enlarge is a `terrain-cave` design, built
  before the house.
- **Keep rooms modular.** Keep useful room volume at or under ~60×60×60 and
  split larger rooms along a wall, so each room stays one module.
- **Resolve everything to absolute coordinates** in the phase files, within
  Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`).
- **Interior height ≥4 blocks** of clear cells between floor and ceiling unless
  the user explicitly wants a crawlspace.
- **Light coverage everywhere** — no spawnable dark cell in a finished room.
- **At least two exits**, or a panic room with a bed and a food chest.
- **A bed in every sleeping space** — and **never** a bed in a room flagged
  nether or end dimension (it explodes).
- **Use Java-correct redstone.** Quasi-connectivity exists on Java; observers
  output a 1-redstone-tick pulse. Ashlar places blocks without block updates,
  so circuits do not start on their own: include a start lever or button and
  tell the user to use it. See `reference/utilities.md` for Java-verified
  designs. For anything more complex, use the `system-redstone` skill if it is
  installed; otherwise say what is out of reach.
- **Stay within Y=-64 to Y=319.**

## Hand-off

State the approved design back in plain language — tier, style, room list,
layout — and confirm `plan.toon` and its phase and module files are written. You
sequence the next steps yourself, in this order:

1. **Site preparation**, if needed: use the `terrain-shape` skill if it is
   installed; otherwise add a `site-prep` phase (clearing, levelling, pads,
   filling holes, soft-edged terraces) and tell the user if the site needs
   more than that (more than light levelling, a pad and a few terraces).
   The integration phases from "Ground the build" go first when the user kept
   them; they replace the plain `site-prep` phase for the ground they cover.
2. **Build**: use the `exec-ashlar` skill (`build <project>`).

The blueprints and the registry entry stay for later iteration.
