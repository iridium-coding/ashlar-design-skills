---
name: terrain-cave
description: >-
  Use when designing deliberate underground space in Minecraft Java: a cavern
  hall, a lush grotto, a dripstone cave, a lava-tube passage, a ravine, a skylit
  chamber, or the cave around an underground base; also to light, green and
  extend an existing cave, such as one a player is turning into a base. Builds
  through Ashlar with the exec-ashlar skill.
model: sonnet
effort: high
metadata:
  short-description: Carve, dress and light designed caves without disturbing the surface above.
---

# Design a cave

A designed cave has a known entrance, a route, chambers sized for a purpose and
a material story. Vanilla caves are noise; this skill carves on purpose and
leaves the ground surface alone except where a shaft opens it.

Run `mc_status`. If Ashlar is unreachable, stop and tell the user. For a
standalone request, start a project in `.minecraft-builder/<project>/`. For a
cave base, use the design skill's project and plan and put the cave phases
before its build.

## Survey

Run `exec-ashlar survey <project>` using `../exec-ashlar/reference/survey.md`.
Take an exact site read of the cave box with an eight-block horizontal margin,
from at least four blocks below the lowest planned floor up through the air
above the surface: the roof check needs the surface, and the dressing and
gravity checks need the rock around the void. Run
`terrain.py survey --site DIR --box X1 Y1 Z1 X2 Y2 Z2` on the cave box. Record
existing caves, water and lava, sand or gravel above the planned ceiling, ores
and every non-natural block. If the box holds a player build, stop for the
user's decision.

Ask what the cave is for (a base hall, scenery, a passage between two places),
where its entrance is, its rough size, its look (plain, dripstone, lush or
deep) and whether it should be lit against mob spawns or left wild and dark.
For a cave that already exists, ask what to keep, what to add (light,
greenery, pools, new chambers or passages) and which builds in it are the
player's.

- Claude Code: use `AskUserQuestion` for choices.
- Codex: use `request_user_input` when available.
- Otherwise: ask in plain text.

## Design and review

Write `terrain/<element>.cave.json` as [caves.md](reference/caves.md)
describes: chambers, passages, ravines, shafts (the only openings to the
surface), pillars, pools, roof, style, lights and features. To work on a cave
that is already there, adopt it with `existing` (a point inside it and a box):
its open space is kept exactly as it is, lit (counting the lanterns and torches
already in it), planted and joined to any new shapes. Leave `dress` at `new` so
its walls keep their look unless the user wants them repainted. Size each chamber
for its purpose: a base hall needs a flat `floor` and at least 4 blocks of
headroom; scenery wants height and variety. Keep wide chambers within
`limits.max_span` with pillars. Run the launcher as the
[toolkit API](../terrain-shape/reference/terrain/toolkit-api.md) shows.

Preview with `terrain.py cave DESIGN --project DIR --first-phase N --preview`.
Read the projected check in its notes (ceiling, span, light, roof), the void
and roof-trim counts, any connection to existing open space, and the plan and
section images under `terrain/previews/`.

- Claude Code: use `Read` on the PNG files.
- Codex: use `view_image` on the PNG files.
- Otherwise: give the report's measurements and ask the user to open the files.

A refusal names the cell and its cause: water or lava the void would drain,
spill or cut into, sand or gravel the carve would leave hanging, or a site read
too small for the cave.

The report's `built` list names every player block the plan changes: where it
is, what it is and why (inside a new passage, under a pool, moved by the
design). `loses_data` marks a chest, sign or other block whose contents or
text would be lost. Show the user that whole list in plain words — group it by
block, give the positions and the reason, and say outright which contents
would be lost — and ask whether to go ahead. A block they want kept can go in
`moves` (to a new spot) or the shape can be changed. Only after their yes, emit
with `--approve-built TOKEN` using the report's token; a changed design gets a
new list and a new token. Move or reshape the
cave, keep more roof or add a pillar, then preview again. Never read a refusal
as a reason to remove existing water. Emission also refuses a design whose
projected check fails: change the design, and raise its `limits` only with the
user's OK.

Get **design approval** on the previews, bounds, void size, roof trim, lights,
pools, features and any connection to existing caves. Then emit with
`terrain.py cave DESIGN --project DIR --first-phase N` (add `--standalone` for
its own plan). Merge the rows in `terrain/<element>.plan-rows.toon` into the
host plan: the carve, dress, pool and light phases, then the features commands
phase, before the host's own build. Hand off to `exec-ashlar build <project>`
for **separate build approval**; every phase rolls back from a column backup.

Where a shaft opens the surface or an entrance meets a hillside, treat the
mouth as a footprint: include `terrain-integrate` (planned mode) for the ground
around it in the same design, unless the user declines it at approval.

Rooms, furniture, storage, farms and other functional areas inside the cave are
the design skills' work: `design-house` (its cave-conversion notes) for a base,
`design-grounds` for paths, terraces and gardens, `system-redstone` for farms
and machines. Run this skill first for the cave's light and greenery, then
theirs in the same project.

## After the build

Verify the `cave` quality row: take a fresh exact read of the cave box and run
`terrain.py cave-check DESIGN --site DIR`. It passes when ceilings vary, no span
is too wide, every floor cell is lit (for a lit cave) and the roof holds.
Review the plan and sections again and ask the user for an in-game look. A
`place feature` command that finds no fitting surface places nothing; report
how many features were placed. To change the cave, edit the design and emit an
iteration with fresh backups. A full rollback restores phases newest first.

## Non-negotiables

1. Leave the surface alone: keep `roof` blocks of rock above the void outside
   shafts.
2. Never drain, spill into or cut through existing water or lava.
3. Never leave sand, gravel or concrete powder over the void.
4. Never change a player's block until the user has seen what, where and why,
   and said yes.
5. No flat ceilings or wide unsupported spans: vary the ceiling, leave pillars.
6. Light the cave unless the user wants it wild.
7. Never place sculk features: a shrieker can summon a warden.
