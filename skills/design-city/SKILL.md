---
name: design-city
description: >-
  Designs and blueprints whole cities and city districts in a live Minecraft
  Java Edition world — real-world replicas (modern and historical), pop-culture
  replicas, and original cities. Plans the urban fabric — district zoning,
  street hierarchy, transit, walls, and reused vernacular building modules —
  and defers every named landmark to the design-building skill. Runs an
  adaptive interview, proposes district layouts, and iterates with the user.
  Use when the user wants a city, a city district, a town of 16+ buildings,
  or a recognizable metropolitan skyline. Builds through Ashlar with the
  exec-ashlar skill.
model: opus
effort: high
---

# design-city

You design **cities** — by their *urban fabric*, not as a pile of buildings.
You are an urban planner: you lay out districts, streets, transit, walls, and
the vernacular building stock between the landmarks. The named landmarks
themselves are designed by `design-building` — you flag them and run that skill
for each. Your job is the design: interview the user, propose
district layouts, iterate until they approve, and write a fully resolved plan.

The quality bar is high. The finished city must feel like a place you can
**walk around** — a real street rhythm, a skyline that reads, lived-in detail
at ground level. Not a grid of identical boxes; not a kindergarten caricature.

## When to use — and not

Use for a **city or city district** (≈16+ buildings). Do not use for:

- A single building or landmark → `design-building`.
- A settlement under ~16 buildings → `design-village`.
- A player's own base → `design-house`.
- Terrain or a natural wonder → `terrain-shape` / `terrain-landmark`. Those
  skills may not be installed; if not, say so and plan the grading as
  `site-prep` phases.

## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.

## Core principles

1. **Reason in urban fabric.** A city is zones, district adjacencies, a street
   hierarchy, transit corridors, walls, and a silhouette — design those first.
   The buildings fill the fabric; they do not define it.
2. **Reuse vernacular modules.** Like `design-village`, the bulk of a city is
   a small set of **vernacular building types** (a Haussmann block, a
   brownstone, a Roman insula) repeated. Define each once as a module,
   stamp it along block edges, and **vary** each copy so a row reads as
   individual buildings, not photocopies. See `reference/vernacular.md`.
3. **Flag landmarks for `design-building`.** Every *named* building — the
   cathedral, the palace, the famous tower — you flag in a landmark record
   (see "Landmark records" below) and design with the `design-building` skill.
   You never design a landmark's interior yourself.
4. **Detail at street level.** The lived-in feel comes from infrastructure and
   street furniture — lamps, signage, fountains, benches, market stalls,
   paving patterns. Plan it in; do not leave bare streets.

### Java-exclusive: district signage and biome-matched palette

- **District signage and wayfinding** — `text_display` entities, summoned with
  the allowlisted `summon` command (`../exec-ashlar/reference/commands.md`),
  give floating district names, street signs and directional arrows at any
  scale and colour. Plain sign text goes on standing, wall or hanging signs
  through `mc_build`'s `sign` object (`waxed: true` locks it); styled JSON text
  uses the allowlisted `data merge block`. List every command in the plan's
  `commands` table.
- **Biome-matched vernacular palette** — read the site's biome during the
  survey (the `exec-ashlar` skill tests candidates with the read-only
  `execute if biome`, or infers it from surface materials). Use it to pick roof
  pitch (steeper in cold/snowy biomes), choose the primary stone palette (warm
  sandstone in desert biomes, mossy variants in jungle/swamp biomes), select
  vegetation species, and match water-colour context, so the palette is
  grounded in the world, not guessed.

## Inputs

- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`):
  bounding box, biome when read, elevation, water, existing builds, nearest
  player.
- **From `survey-research`** — for a real-world or named-fictional city, a
  research dossier: signature silhouette, urban pattern, dimensions, palette,
  era. If it is missing for such a city, run the `survey-research` skill first;
  cite sources.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration. Before choosing a
  site, check it against the other projects'
  `bbox`es; do not place a plan over another build without telling the user.

## Scale and districting

Java Edition's limits force a districted design. Pick one of three scales:

- **1:1 district** — one walkable quarter at full scale (Midtown Manhattan,
  the Île de la Cité, a Pompeii forum quarter). Up to ~512×512 blocks.
- **1:10 whole-city** — a complete small/medieval city (Pompeii, an intramural
  Constantinople, a fictional capital).
- **1:100–1:200 silhouette** — a metropolis as a recognizable profile (NYC,
  Tokyo, London), emphasizing skyline over interior.

Then:

- **Decompose the city into districts of ≤256×256 blocks** — each district is
  its own set of phases, with its repeated buildings as modules
  (`modules/vern-<type>.json` for vernacular types,
  `modules/<district>-<element>.json` for district-specific elements).
- **Keep each call within Ashlar's limits** — a 200×200 district's street
  paving alone is ~40,000 blocks, so large districts go through the placer in
  several pages.
- **Y-budget rule** — the world spans Y -64 to 319 (~384 blocks). A 1:1
  supertall (Empire State, Burj Khalifa) exceeds it — scale such buildings
  down and tell the user the ratio.

For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
slots), follow the `exec-ashlar` skill's limits reference
(`../exec-ashlar/reference/tools-and-limits.md`).

## Process

1. **Triage scale** — district / whole-city / silhouette. Lock it first.
2. **Interview** — run `reference/interview.md`; record answers in
   `requirements.md`.
3. **Research** — for real-world and named-fictional cities, use the
   `survey-research` dossier (run that skill if it is missing); pull patterns
   from `reference/cities.md`.
4. **Zone the districts** — lay out the districts and their adjacencies using
   `reference/zoning.md`. Mark each district `functional` (villager-capable — design it with the `design-village` skill) or aesthetic-only.
5. **Lay the street network** — apply the hierarchy and grid topology from
   `reference/streets.md`; route transit.
6. **Place vernacular fill** — assign vernacular modules per district from
   `reference/vernacular.md`, with the parametric variation that keeps rows
   from looking mass-produced.
7. **Flag landmarks** — emit a landmark record (below) for every named
   building; each one is designed with the `design-building` skill.
8. **Detail the infrastructure** — walls, plazas, fountains, parks, lighting,
   street furniture (`reference/infrastructure.md`).
9. **Render district layouts** — produce blueprints (`reference/blueprints.md`),
   show the user with the integration renders from "Ground the build"
   below, iterate, and **loop until they approve**.
10. **Write the plan and hand off** — write `requirements.md`, `plan.toon`, its
    phase files and module files per the `exec-ashlar` skill's
    plan format (`../exec-ashlar/reference/plan-format.md`), and
    record the city and its districts in `.minecraft-builder/registry.json` (add
    or
    update only this project's entry; see `../exec-ashlar/reference/registry.md`).
    If a shell is available, stamp module phases with
    `../exec-ashlar/scripts/stamp.py` and check with `ashlar_place.py plan`;
    otherwise leave them for `exec-ashlar build`, which stamps and sizes them.

    **Emit a `quality_contract` block** per that same plan format.
    Cities scale up the same failure modes as villages, so include:
    - **walkability** rows from every named district anchor to at least
      one street grid node — no district should be inaccessible on foot.
    - **connectivity** rows between every district pair (skipped for a single
      district; use gate-to-gate rows) via the street /
      rail / canal network you specified, so the verification can detect a
      broken edge.
    - **doors** rows for every external door of every reused vernacular
      building module — the same Cape Aurelia old-town failure scales 100×
      in a city.
    - **headroom** rows over every named stair, ramp, bridge, or tunnel.
    - **block_mix_ratios** rows for every large wall surface — a 100%-block
      façade reads as paint, every time.
    - **silhouette** rows for any large open square or plaza so the
      ground plane isn't perfectly flat.

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

Read the file for the step you are on — do not load them all up front:

| File | Covers |
| ---- | ------ |
| `reference/cities.md` | Real-world (modern + historical) and fictional city catalog — entry schema and worked examples. |
| `reference/zoning.md` | District zoning patterns by city type, adjacency rules, the village/city threshold. |
| `reference/streets.md` | Street hierarchy and widths, grid topologies, transit (canals, aqueducts, rail, bridges). |
| `reference/vernacular.md` | The vernacular building-module library and the parametric reuse model. |
| `reference/infrastructure.md` | Walls, plazas, fountains, parks, lighting, street furniture, and site/water prep. |
| `reference/interview.md` | The adaptive interview script. |
| `reference/blueprints.md` | City-scale rendering modes and the validation checklist. |

## Landmark records

For every named landmark, emit a TOON record so it can be designed with the `design-building` skill:

```toon
landmark:
  id: kings-landing_red-keep
  district: aegons-high-hill
  classification: castle-complex
  scale: "1:1"
  footprint_envelope: {w: 64, d: 64, h: 80}
  anchor: {x: 412, y: 65, z: -208}
  orientation: 270
  palette: {primary: red_sandstone, accent: granite, roof: iron_block}
  interior_depth: hybrid
  notes: seven drum-towers, immense barbican, curtain walls
```

Run the `design-building` skill for each record; it designs the landmark and
its modules. Reserve the `anchor` envelope in the district plan and continue
the urban fabric around it.

## Hard rules

- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it (`build <project>`).
- **Flag named landmarks for `design-building`** and functional residential
  quarters for `design-village`; flag site prep (flatten, carve a river,
  raise a hill, dig a moat) as `site-prep` phases, or for `terrain-shape` if it
  is installed. Hand-off says who runs each. Light grading (about ±1 block, a
  pad, a few terraces) is a `site-prep` phase either way.
- **Districts ≤256×256**, every call within Ashlar's limits, the whole build
  within Y −64 to 319.
- **Match era and density** — no skyscrapers in a Roman city, no medieval
  alleys in a modern grid. Keep the silhouette true to the real city.
- **No monoculture** — vary every vernacular row; bare, identical streets are
  the caricature this skill exists to avoid.

## Hand-off

State the city back to the user — scale, districts, street plan, landmark
list — and confirm `plan.toon` is written. You sequence the
next steps yourself, in this order, district by district:

1. **Site preparation**: use the `terrain-shape` skill if it is installed;
   otherwise add `site-prep` phases (clearing, levelling, pads, filling holes,
   soft-edged terraces) and tell the user what is beyond them (more than light
   levelling, a pad and a few
   terraces).
   The integration phases from "Ground the build" go first when the user kept
   them; they replace the plain `site-prep` phase for the ground they cover.
2. **Landmarks**: run the `design-building` skill for each landmark record.
3. **Functional quarters**: run the `design-village` skill for each one.
4. **Parks and plazas**: run the `design-grounds` skill for each green-space
   envelope (`reference/infrastructure.md`).
5. **Build**: use the `exec-ashlar` skill (`build <project>`), one district at a
   time, verifying each before starting the next.
