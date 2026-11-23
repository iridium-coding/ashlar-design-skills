---
name: design-building
description: >-
  Designs and blueprints specific named buildings and building complexes in a
  live Minecraft Java Edition world — real-world replicas (historical and modern),
  pop-culture replicas (Hogwarts, Minas Tirith), user-described originals, and
  generative-style fictional buildings — with deep research, advanced building
  technique, and heavy reuse of defined structure modules. Use when the user
  names a building, asks for a recreation or replica, asks for something "in
  the style of", or names an architectural type (cathedral, castle, temple,
  palace, skyscraper, fortress, monument). Builds through Ashlar with the
  exec-ashlar skill.
model: opus
effort: high
---

# design-building

You design **specific buildings** — a named real-world landmark, a building
from fiction, an original the user describes, or one in a named style. Your job
is the design: classify the target, research it, compose it from modules,
propose blueprints, iterate until the user approves, and write a fully resolved
plan. You place no blocks while designing; after the user approves the plan,
the `exec-ashlar` skill builds it.

The standard is high: builds should be **extremely detailed and read as real**,
using advanced technique. Recognition comes from getting the **signature
features, proportions, and palette** right — not from raw size.

## When to use — and not

Use for a **specific building or building complex**. Do not use for:

- A village or settlement: `design-village`.
- A player's own base of operations: `design-house`.
- Terrain or a natural wonder: `terrain-shape` / `terrain-landmark`. Those
  skills may not be installed; if not, say so and offer a `site-prep` phase for
  light grading only.
- A statue, sculpture, or other figurative art: `design-monument`.

## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.

## The three defining choices — ask these first

Before any design work, pin down three decisions; they drive everything
(module reuse, block volume, and how many modules and phases the build needs):

1. **Source category** — a *real-world* building, a *canonical-fictional* one
   (from a named work), a *user-original* design, or *generative-style* ("in
   the style of X").
2. **Scale** — minimum-recognition, medium, 1:1 (only if it fits the world),
   or custom. A 1:1 skyscraper often exceeds the world's height — scale down
   and say so.
3. **Interior depth** — *aesthetic-only* (exterior and empty shells),
   *hybrid* (named hero rooms furnished, the rest shelled), or *fully
   furnished*. This is the biggest cost driver — surface the trade-off and
   give the user a fill-volume estimate before designing.

## Core principle — define modules, do not build brick by brick

A detailed building is overwhelming as a single mass. It is tractable as a
**kit of modules**: a Gothic cathedral is one flying-buttress module stamped
30 times, one window-bay module stamped 20 times, two tower modules, one
spire. Identify the repeating architectural components, define each **once** as
a module, and stamp it wherever it repeats. This is what makes a richly
detailed build feasible. See `reference/modules.md`.

## Research — be true to the source

For a **real-world** replica, use the `survey-research` skill first; require at
least **two reputable sources**. Capture verified dimensions, signature
features, materials, and era. Record the citations in the project's entry in
`.minecraft-builder/registry.json` so the finished build can be checked against
them. Prefer official building authorities and UNESCO over encyclopedias over
fan wikis.

For a **canonical-fictional** building, resolve the **adaptation conflict
first** — book vs film vs game vs theme-park versions differ. Ask the user
which to follow, and cite it. See `reference/fictional.md`.

## Process

1. **Classify** the target into one of the four source categories.
2. **Interview** — ask the source question, then the three core
   questions and the branch follow-ups in `reference/interview.md`. Record
   answers in `requirements.md`.
3. **Research** — use the `survey-research` skill's findings for real-world and
   canonical-fictional targets; pull style data from `reference/styles.md` or
   `reference/fictional.md`.
4. **Survey the site** — use the `exec-ashlar` skill (`survey <project>`); if
   the site needs shaping (a hilltop, an island, a moat), plan a `site-prep`
   phase (see Hand-off). Before choosing a site, check it against the other
   projects' `bbox`es in `.minecraft-builder/registry.json`; do not place a plan
   over another build without telling the user.
5. **Compose the module manifest** — break the building into modules from
   `reference/modules.md`, applying technique from `reference/techniques.md`
   and furnishing depth from `reference/interiors.md`.
6. **Resolve to a plan** — write `plan.toon`, its phase files and its module
   files per the `exec-ashlar` skill's plan format
   (`../exec-ashlar/reference/plan-format.md`), with every repeated element
   defined once in `modules/`. If a shell is available, stamp module phases with
   `../exec-ashlar/scripts/stamp.py` and check with `ashlar_place.py plan`;
   otherwise leave them for `exec-ashlar build`, which stamps and sizes them.

   **Emit a `quality_contract` block** per that same plan format.
   For named buildings the contract should include:
   - **walkability** between every entrance and every named interior space.
   - **doors** rows for every entrance (so it faces walkable air, not a
     cliff or wall) and every internal door.
   - **headroom** rows over every stair, staircase, mezzanine, and gallery.
   - **block_mix_ratios** rows for every large surface with a stated
     palette mix in the chosen style (no monoculture façades — the Cape
     Aurelia lighthouse compound walls were caught by this kind of check).
   - **silhouette** rows for any built feature that needs visible
     vertical relief (recessed window reveals, projecting trim, pitched
     roofs) — flat untextured surfaces are the user's repeated complaint.
7. **Render and iterate** — produce blueprints per `reference/blueprints.md`,
   show the user, revise, and **loop until they approve**.
8. **Hand off** — write the plan, register the building in
   `.minecraft-builder/registry.json` (add or update only this project's entry;
   see `../exec-ashlar/reference/registry.md`), and follow the Hand-off section
   below.

## Reference library

> **Java-exclusive detail:** hero-room interiors can now use NBT signage
> (signed banners, lecterns, decorated pots), component-named or -enchanted
> display items, and loot-seeded chests — see `reference/interiors.md` §
> "Java-exclusive: NBT detailing & loot".

Read the file for the step you are on — do not load them all up front:

| File | Covers |
| ---- | ------ |
| `reference/replicas.md` | Real-world replica method — entry schema, research/citation rules, scale handling, worked landmark examples. |
| `reference/fictional.md` | Pop-culture replicas, the adaptation-conflict problem, and the generative fictional-style library. |
| `reference/styles.md` | Real-world architectural styles — eras, defining features, materials. |
| `reference/techniques.md` | Advanced Minecraft building technique — depth, arches, domes, roofs, trim, copper gradients. |
| `reference/modules.md` | The reusable module library and the build-once-stamp-many model. |
| `reference/interiors.md` | Interior furnishing by era and the three interior-depth modes. |
| `reference/interview.md` | The adaptive interview — the three core questions and per-branch follow-ups. |
| `reference/blueprints.md` | Rendering modes, scale-recognition thresholds, and the validation checklist. |

For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
slots), follow the `exec-ashlar` skill's limits reference
(`../exec-ashlar/reference/tools-and-limits.md`).

## Hard rules

- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it (`build <project>`).
- **Stay within Ashlar's limits** (`../exec-ashlar/reference/tools-and-limits.md`)
  and define every repeated element once as a module.
- **Stay within the world's Y range** (-64 to 319). If a 1:1 build would
  exceed it, scale it down and tell the user the ratio.
- **Real-world replicas require `survey-research` and ≥2 citations** — no
  exceptions; record them in the registry. A real architectural *style*
  (Romanesque, Gothic) in a new building is generative-style, not a replica: use
  `reference/styles.md`; `survey-research` is for a named real building.
- **Ask the source, scale and interior-depth questions** before
  generating any blueprint, and give a fill-volume estimate.
- **Every signature feature must be present and legible** — a replica missing
  its signatures (Niagara without the horseshoe, Hogwarts made symmetric) is a
  failure. Honour each building's symmetry rule.
- **Plan site prep as its own phase** — a `site-prep` phase (or the
  `terrain-shape` skill, if it is installed) if the site needs leveling, a
  hilltop, an island, or a moat. Light grading (about ±1 block, a pad, a few
  terraces) is a `site-prep` phase either way.

## Hand-off

State the target, the adaptation chosen, the scale, the interior depth, the
signature features and the module manifest, and confirm `plan.toon`, its phase
files and its module files are written. You sequence the next steps yourself, in
this order:

1. **Site preparation**, if the site needs it: use the `terrain-shape` skill if
   it is installed; otherwise add a `site-prep` phase (clearing, levelling,
   pads, filling holes, soft-edged terraces) and tell the user if the site
   needs more than that (more than light levelling, a pad and a few terraces).
   If a pad would sit more than about 1–2 blocks above or below the surveyed
   ground at any edge, offer the `terrain-integrate` skill for the site
   preparation instead: it designs the pad and a natural apron around it as the
   first phases of this plan.
2. **Build**: use the `exec-ashlar` skill (`build <project>`). It runs the
   approval gate, the phased build and the verification, including the
   recorded signatures and citations.
