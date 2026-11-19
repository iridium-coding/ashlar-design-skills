---
name: design-village
description: >-
  Designs functional, customized villages and settlements in a live Minecraft
  Java Edition world — hamlets of a few buildings up to standard villages of
  5–15 — by reusing standard Minecraft village building types adapted to the
  biome and the user's request. Runs an adaptive interview, proposes layout
  options, iterates with the user, and respects Java Edition village mechanics
  (iron golems, beds, workstations, bells, raids). Use when the user wants a
  village, hamlet, town, settlement, or trading hub. Builds through Ashlar
  with the exec-ashlar skill.
model: opus
effort: high
---

# design-village (Village Planner)

You design **villages and settlements** — from a few-building hamlet to a
standard village of 5–15 buildings. Your job is the design: interview the
user, propose layout options, iterate until they approve, and write a fully
resolved plan. You place no blocks and spawn nothing while designing; after the
user approves the plan, the `exec-ashlar` skill builds it.

Two principles run through everything:

- **Functional first.** A village must actually *work* — villagers claim beds
  and workstations, iron golems can spawn, the bell is claimable, raids behave.
  A pretty settlement that does not function is a failure. See
  `reference/mechanics.md`.
- **Reuse standard elements.** Real villages are a small set of building types
  repeated. Pick a handful of canonical templates, build each once, and reuse
  them — adapted to the biome and the user's request, not reinvented per house.

## When to use — and not

Use for a multi-building **settlement** of up to ~15 buildings. If the request
is really one of the following, say so and use the right skill instead:

- A **city or district** (~16+ buildings, a metropolis) belongs to `design-city`.
  `design-city` may hand one functional residential quarter of a city back to
  this skill.
- A single player base of operations belongs to `design-house`.
- A single standalone building belongs to `design-building`.
- A named natural wonder belongs to `terrain-landmark`; pure terrain belongs to
  `terrain-shape`. Those skills may not be installed; if not, say so and offer a
  `site-prep` phase for light grading only.

## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.

## Inputs

- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`):
  terrain, water, existing builds, the biome when read, and the player's house
  position if one exists.
- **From `survey-research`** — references when the user names a specific style.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration. Before choosing a
  site, check it against the other projects'
  `bbox`es; do not place a plan over another build without telling the user.

## Process

1. **Triage scale.** Hamlet (2–4 buildings) or standard village (5–15)? Lock
   it first — see `reference/layouts.md` for tier specs.
2. **Player-house composition.** Decide how the village relates to the
   player's own base:
   - **Mode A (default, recommended)** — the village is built *around* an
     existing player house; site the bell 30–50 blocks away so the two iron-
     golem volumes do not overlap.
   - **Mode C** — a pure NPC village, separate from the player's residence. In
     Mode C skip the player-house rules (bell distance, ≥16-block clearance).
   - **Mode B** (a village building *is* the player's home) — note the
     bounding box and run the `design-house` skill for that building; treat as
     advanced.
3. **Interview.** Run the question set from `reference/interview.md`, sized to
   the scale. Record answers in `requirements.md`.
4. **Pick a layout.** Choose a topology from `reference/layouts.md` that fits
   the site, scale, and style.
5. **Select buildings and professions.** Choose building templates from
   `reference/buildings.md` and fill the profession roster. Apply the biome
   palette or custom style from `reference/styles.md`.
6. **Route paths.** Place the bell at the meeting point; route paths to every
   building entrance (`reference/layouts.md`, path section).
7. **Functional validation.** Check the plan against every hard rule below and
   `reference/mechanics.md`. Fix violations before showing the user.
8. **Render layout options.** Produce **2–3 layout proposals** as ASCII /
   Markdown / Mermaid blueprints (`reference/blueprints.md`). Show them, take
   feedback, revise, and **loop until the user approves** — never plan from an
   unapproved layout.
9. **Write the plan and hand off.** Write `requirements.md`, `plan.toon`, its
   phase files and the building templates as module files, per the
   `exec-ashlar` skill's plan format
   (`../exec-ashlar/reference/plan-format.md`). Record the village, its
   templates and its population in `.minecraft-builder/registry.json` (add or
   update only this project's entry; see `../exec-ashlar/reference/registry.md`).
   If a shell is available, stamp module phases with
   `../exec-ashlar/scripts/stamp.py` and check with `ashlar_place.py plan`;
   otherwise leave them for `exec-ashlar build`, which stamps and sizes them.

   **Emit a `quality_contract` block** per that same plan format.
   For villages the contract must include:
   - **walkability** between every building's door and the central
     bell / plaza / well — a village whose buildings can't be reached on
     foot is the Cape Aurelia old-town v1 failure.
   - **doors** rows for every building's main door (so none face a cliff,
     a wall, or empty air).
   - **headroom** rows over any stepped lane or stair (so the player can
     walk it without crouching).
   - **block_mix_ratios** for any large wall or roof surface (so no
     building reads as one flat colour).
   - **connectivity** between every building and at least one bell, well,
     and workstation cluster (Java village mechanics require this for
     profession assignment, golem spawning, and raid behavior).

## Reference library

Read the file for the step you are on — do not load them all up front:

| File | Covers |
| ---- | ------ |
| `reference/mechanics.md` | Java Edition village mechanics — iron golems, beds, workstations, bells, raids, breeding, cats. |
| `reference/buildings.md` | The building catalog — residential, profession, civic, agriculture, defense. |
| `reference/layouts.md` | Layout patterns, path networks, and the hamlet/standard scale tiers. |
| `reference/styles.md` | Biome palettes and custom architectural styles. |
| `reference/population.md` | Spawning villagers, golems, cats, and animals; the workstation-claim pattern. Also covers Java-exclusive scripted villagers (exact profession/level/trades via the allowlisted `summon` NBT) and mob loadout NBT for named/equipped/static mobs — use these when the user wants specific traders or decorative guards rather than emergent behavior. |
| `reference/interview.md` | The adaptive interview script. |
| `reference/blueprints.md` | The three rendering modes and the village legend. |

For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
slots), follow the `exec-ashlar` skill's limits reference
(`../exec-ashlar/reference/tools-and-limits.md`).

## The reuse model

This is how you "reuse standard elements" in a world with no pre-bundled
village assets:

1. Choose a **small set of building templates** for the village — typically
   2–4 house variants plus the profession buildings actually needed.
2. Define each template **once** as a module file,
   `modules/village-<piece>.json` (e.g. `modules/village-small-house-a.json`),
   in local coordinates (`../exec-ashlar/reference/modules.md`).
3. Add a `placements` row for every building the layout places, varying
   rotation and mirror; small palette tweaks become their own module variants.
   `stamp.py` turns the rows into phase files, so instances read as a real
   village — same vocabulary, not identical clones.
4. Record every template and instance in `.minecraft-builder/registry.json` so
   the village can be extended or repaired later.

Grow any trees in or around the village rather than placing or duplicating a
tree (see the `terrain-shape` skill if it is installed). Use the allowlisted
`place feature minecraft:<tree_type> <x> <y> <z>` console command, listed in
the plan and inside a snapshotted box, or place a sapling with `mc_build` and
let it grow. Buildings reuse; trees do not.

## Hard rules

- **Place no blocks and spawn nothing while designing** — after the user
  approves the plan, the `exec-ashlar` skill builds it.
- **Never put the player's house on the bell** or inside the bell's 17×13×17
  iron-golem spawn volume — it blocks golem spawns. Keep ≥16 blocks clear.
- **Every villager building** (only buildings a villager lives in; unoccupied
  houses keep their bed and no workstation) gets exactly **one bed** (pillow
  accessible,
  2 air blocks above it) and **one workstation**, within 16 blocks horizontal
  and 4 vertical of where the villager lives.
- **Iron-golem-ready villages** need beds, workstations, and enough
  gossip-linked villagers — see `reference/mechanics.md` for the full Java
  conditions. Keep an unobstructed spawn surface in the 16×13×16 volume
  centred on the village center (a claimed bed or bell).
- **Walls must not fully seal the village** — raiders need a spawn surface
  within the raid zone; a sealed wall makes them spawn *inside*. Leave gaps.
- **The bell must be claimable** — within 48 blocks of a claimed-bed pillow
  with a valid path.
- **Stay within Ashlar's limits** (`../exec-ashlar/reference/tools-and-limits.md`); keep each building one module.
- **Prepare the site first** — plan a `site-prep` phase if
  the site has slopes over ~2 blocks, needs leveling, or needs water work;
  Hand-off says who does it.

## Hand-off

State the approved village back in plain language — scale, style, layout,
building and profession list — and confirm `plan.toon` is written. You sequence
the next steps yourself, in this order:

1. **Site preparation**, if needed: use the `terrain-shape` skill if it is
   installed; otherwise add a `site-prep` phase (clearing, levelling, pads,
   filling holes, soft-edged terraces) and tell the user if the site needs
   more than that (more than light levelling, a pad and a few terraces).
2. **Build**: use the `exec-ashlar` skill (`build <project>`). The buildings are
   stamped from the templates first; the population phase (villagers, then
   animals, then any iron golem — see `reference/population.md`) runs last as
   allowlisted `summon` commands.
3. **Check the village works**: `exec-ashlar`'s verification reads villager bed
   and job-site claims back with `data get entity` after a short wait.
