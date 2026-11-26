# Ashlar design skills — sub-project 2: terrain

- **Date:** 2026-11-19
- **Status:** approved by the user on 2026-11-19. The user confirmed the drain
  and named-biome amendments on 2026-11-22 (§7.7 and §8.4).
- **Branch:** `terrain`, in the worktree `ashlar-design-skills-terrain`, cut from the
  fork's `main` at `db3e8a1` (the merge of PR #1)
- **Sub-projects:** 1 foundation and design skills (merged) · 2 terrain (this
  spec) · 3 redstone · designed caves later
- **Builds on:** `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md`
  ("spec 1"). Its rules hold here unless this spec changes them, in particular
  §7.5 (shared text with labelled client-specific lines), the `exec-ashlar`
  contract (§5) and the `.minecraft-builder/` project state.

## 1. Purpose

Port four of Chapman's terrain skills — `terrain-shape`, `terrain-landmark`,
`terrain-ecology` and `terrain-integrate` — and his terrain toolkit so that they
build through the Ashlar MCP server via the `exec-ashlar` skill, in Claude Code
and in Codex.

**Why.** The six design skills already send terrain work to `terrain-shape` and
`terrain-landmark` "if it is installed" and otherwise fall back to a simple
`site-prep` phase (clearing, levelling, pads, soft-edged terraces). With this
port an agent can shape natural land when a prompt calls for it — from a hill
behind a village to a mountain range or a named natural wonder — plant it with
vanilla and custom trees, and ground builds into the land around them, under the
same approval gate, rollback and verification as every other Ashlar build.

**Success looks like:**

1. A prompt that calls for terrain produces a recipe verified offline, renders
   the user approves, and a plan that `exec-ashlar` builds, verifies and can roll
   back, at site scale (up to about 128 × 128 blocks) and at landscape scale
   (several hundred blocks a side).
2. Landscape-scale builds do not use up the server's 20 shared snapshot slots.
3. Terrain is planted with vanilla trees grown by the server, and the agent can
   also design its own tree shapes.
4. A biome changes only as a last resort, with the user's separate yes each time.
5. Builds made by the design skills can be grounded into the surrounding land.
6. Claude Code and Codex can both follow every skill.

## 2. Where things stand

**The fork.** PR #1 (sub-project 1) is merged into `main`. It added
`skills/exec-ashlar/` (plan format, approval gate, snapshots, the stdlib placer
`scripts/ashlar_place.py`, `scripts/stamp.py`, the console allowlist with paired
`forceload add`/`remove` and the `minecraft:` prefix, verification and rollback),
adapted the six `design-*` skills and `survey-research`, and copied Chapman's
voxel toolkit into `skills/design-monument/tools/voxel/`. The eight skills are
linked into the workspace's `.claude/skills/` and `.agents/skills/` as relative
symlinks into the clone, so the clone's checked-out branch is what every session
loads; this work therefore happens in a separate worktree.

**Chapman's terrain pieces in the fork, untouched so far:**

- `skills/terrain-{shape,landmark,ecology,integrate,cave}/`, written as forked
  Tier-3 leaves of his orchestrators, calling his Fabric mod's tools.
- `reference/terrain/` (12 files): the shared method (`method.md`,
  `toolkit-api.md`, `non-negotiables.md`, `palettes.md`, `primitives.md`,
  `water.md`, `weathering.md`, `validation.md`, `research.md`) and the per-skill
  methods (`ecology.md`, `integration.md`, `caves.md`).
- `tools/terrain/` (about 4,500 lines of Python): sampler graph, `HeightField`,
  erosion, climate/biomes, blending, masks, materialisation, scatter, renders,
  the offline verify gate ("GATE A"), and `emit.py`, which writes output for his
  builder harness. Dependencies: numpy, scipy, Pillow, optional opensimplex.
  Checked on this machine on 2026-11-19: `uv run --no-project --with numpy
  --with scipy --with pillow --with opensimplex --with pytest` installs them
  (uv chose Python 3.14.8; numpy 2.5.5, scipy 1.18.1, Pillow 13.0.0) and all 96
  of Chapman's toolkit tests pass.

**What Ashlar lacks.** Chapman's pipeline ends in server tools that Ashlar does
not have:

| Chapman step | Chapman's tool | With Ashlar |
| --- | --- | --- |
| Materialise a heightfield, column by column | `block_fill_columns`, `block_fill_columns_strata` | `mc_build` fills, through the placer |
| Paint biomes | `level_fill_biome` | nothing yet; this spec adds `fillbiome` to the allowlist |
| Scatter trees and plants | `level_place_features_batch`, `level_place_feature` | `place feature`, already allowlisted, one console command each |
| Erode terrain in the world | `block_erode_region`, hydraulic erosion jobs | nothing; Chapman's documented offline route works |
| Read surface heights | `block_get_top_y` | `mc_survey` with `matrix: true` |
| Stamp structure templates | `structure_load_to_world` | module files and `stamp.py` |

**Live facts** (read-only checks on 2026-11-19, Ashlar 0.4.9 on Paper 26.3):

- `mc_inspect` with `format: "columns"` returns full block states for every run,
  for example `0,0: 50-62 water[level=0] | 63-110 air`. A columns read is
  therefore an exact record of the blocks in a box, short of block-entity data
  and entities.
- `mc_survey` with `matrix: true` appends rows `z=<n>: h h h …`, x from left to
  right.

**Snapshot arithmetic.** An Ashlar snapshot holds at most 200,000 cells and the
server keeps 20, shared by every build. A 128 × 128 area with 80 blocks of
relief is about 1.31 million cells, or 7 snapshots; a 192 × 192 × 100 area is
about 3.69 million cells, or 19. The store is already full, so every slot a
terrain build takes evicts another build's rollback point.

**Upstream's validator** (`scripts/validate-plugin.mjs`) requires every
`terrain-*` `SKILL.md` body to contain the text `reference/terrain/`, requires
the root `reference/terrain/method.md` and `toolkit-api.md` to exist, and accepts
a reference link if it resolves under any of several roots — so a bare
`reference/terrain/X.md` inside a terrain skill passes even when only the root
copy exists. It has no rule requiring `context: fork` for terrain skills.

## 3. Decisions

"User" marks a decision the user made in the brainstorming; "my call" marks a
choice made while writing this spec, open to correction.

| Topic | Decision | Source |
| --- | --- | --- |
| Skills ported | `terrain-shape`, `terrain-landmark`, `terrain-ecology`, `terrain-integrate`; `terrain-cave` later, as its own sub-project | user |
| Scale | Site scale and landscape scale | user |
| Approach | Terrain emits ordinary `exec-ashlar` phases; `exec-ashlar` stays the only executor (§5) | user |
| Rollback for terrain | Local column backups taken by the placer; other phases keep snapshots | user |
| Trees | Vanilla trees through `place feature`, run in bulk by the placer; plus custom trees the agent designs, stamped as modules | user |
| Biomes | `fillbiome` joins the allowlist as a last resort; the agent asks a separate question every time a biome must change; rollback is approximate | user |
| `terrain-integrate` | Included by default (amended 2026-11-25; was "offered, not mandatory"): every design whose footprint meets uneven or disturbed ground carries it, and the user may decline it at the design approval; also after the fact as its own small project | user |
| Commands at the gate | A commands file is summarised by count per feature, not printed line by line | user |
| Trees crossing the box edge | Judged by where the trunk stands: a tree rooted on ground that changes is removed whole, even the part outside the box; a tree rooted on unchanged ground stays whole (§7.5) | user |
| Existing water and lava | Kept by default; drained only with the user's separate yes, asked every time for each body (§7.7) | user |
| Biome changes | Keep the existing biome by default. Paint only the biome named in the user's dedicated approval (§8.4). | user |
| Resume | `build` continues a project left `building` after a failure, after the user's OK | user |
| Where the toolkit lives | Copied into `skills/terrain-shape/tools/terrain/`; the other three skills reach it through `../terrain-shape/` | approved in the design review |
| Project rule | Terrain made for a design skill's build joins that build's plan (one gate, one rollback); a standalone request is its own project | approved in the design review |
| Frontmatter | Drop Chapman's `context: fork` (the skills now talk to the user); keep his `model` and `effort` | approved in the design review |
| Materialisation | Change only the cells that must change, plus a seal band; leave the deep underground as the world has it (§7.5) | my call |
| Large generated lists | Feature commands and tree placements live in their own files, never in `plan.toon` tables (§7.11) | my call |
| Custom trees and overlap | Vegetation modules are placed into air only (`filter: "minecraft:air"`), wood before leaves, so canopies may overlap (§9.2) | my call |
| Survey safety | A terrain survey lists every non-natural block inside the terrain box; the gate repeats it (§8.1) | my call |
| Phase size | Terrain mass is split into phases of at most about 128 × 128 columns | my call |
| Phase order in a combined plan | Site prep and terrain, carve forms, flowing water, the design's own phases, planting, then any biome change (§8.1) | my call |
| Feature and biome ids | Per-version id lists shipped with the toolkit, generated from vanilla game data; species checked at design time (§7.8) | my call |
| Plunge pools | Chapman's "three times the fall height" depth dropped; a few blocks, at most about 12 (§7.7) | my call |

## 4. Goals, non-goals and anti-goals

**Goals**

- The four skills follow Chapman's method (recipe, erosion, mask-driven
  materials, offline verify, renders) and hand an approved plan to `exec-ashlar`.
- The toolkit's output step writes plain `mc_build` phase files, commands files
  and module files that `exec-ashlar` already knows how to check and place.
- Terrain blends into the existing world at its edges.
- Terrain, plants, biome changes and grounding all roll back.
- Shared text plus labelled client lines, as in spec 1 §7.5.

**Non-goals**

- `terrain-cave` and designed underground space (a later sub-project).
- Chapman's builder harness, `build-*` orchestrators, agents and other `exec-*`
  skills.
- Server-side erosion, new Ashlar features, an HTTP transport for the placer.
- Changing game rules or server settings.

**Anti-goals** — the work fails if any of these happen, even when it runs:

- Stacked rectangles, terraced "ziggurats", bare grey walls, or a hard seam where
  new land meets old (Chapman's documented failure modes).
- A biome change proposed as a first instinct, or made without the user's
  separate yes.
- Existing water or lava drained without the user's separate yes for that body.
- A write without a complete rollback point, or snapshots evicted without the
  user being told.
- Terrain written over a player's structure without the user knowing.
- Hundreds of console commands shown one by one at the gate, or sent one by one
  by the model.
- Edits to Chapman's root files (`tools/terrain/`, `reference/terrain/`,
  `skills/terrain-cave/`) that would make upstream merges conflict.

## 5. Approaches considered

1. **Terrain emits ordinary phases (chosen).** The copied toolkit gets an Ashlar
   output step that writes `mc_build` phase files, commands files and modules.
   `exec-ashlar` stays the only executor and gains local backups, a bulk command
   runner, a biome probe and height reads. Phase files stay inspectable `mc_build`
   arguments, and every safety rule from sub-project 1 applies unchanged.
2. **A placer that understands terrain.** The placer takes Chapman's compact
   per-column format and expands it while sending. Files are smaller, but the
   placer must learn heights, palettes, strata and water; its sizing, backups and
   tests grow, and phase files stop being plain `mc_build` arguments.
3. **A separate terrain executor.** A new `exec-terrain` skill owns terrain
   builds end to end. Clean separation, but it duplicates the gate, player checks,
   registry and rollback, and a village on shaped land would run two executors
   with two gates.

## 6. Layout

```text
skills/terrain-shape/
  SKILL.md                         rewritten for Ashlar (§8.2)
  scripts/terrain.py               new: command-line launcher for the toolkit (§7.2)
  tools/terrain/                   copied from tools/terrain/, adapted (§7)
  tools/terrain/LICENSE            Chapman's MIT notice
  tools/terrain/README.md          rewritten for this copy and the Ashlar output step
  reference/terrain/               copied from reference/terrain/ and adapted (§8.6):
                                   method, toolkit-api, non-negotiables, palettes,
                                   primitives, water, weathering, validation, research
  reference/landforms.md           edited
  reference/command-budget.md      rewritten as an Ashlar budget note
  reference/{palettes,water,weathering,non-negotiable-enforcement}.md
                                   stubs, now pointing at reference/terrain/
skills/terrain-landmark/
  SKILL.md                         rewritten (§8.3)
  reference/{wonders,anti-patterns,sequencing}.md   edited
  reference/{primitives,palettes}.md                stubs, now pointing at
                                   ../terrain-shape/reference/terrain/
skills/terrain-ecology/
  SKILL.md                         rewritten (§8.4)
  reference/ecology.md             from reference/terrain/ecology.md, adapted
  reference/custom-trees.md        new: the tree generator and how to design with it
skills/terrain-integrate/
  SKILL.md                         rewritten (§8.5)
  reference/integration.md         from reference/terrain/integration.md, adapted
skills/exec-ashlar/
  scripts/ashlar_place.py          new subcommands (§9.1)
  scripts/stamp.py                 vegetation modules (§9.2)
  reference/*.md                   edited (§9.3–§9.8)
skills/design-{building,city,grounds,house,monument,village}/   small edits (§10)
tests/ashlar/                      extended (§11)
tests/ashlar/terrain/              Chapman's toolkit tests, run against the copy, plus new tests
README.md, CLAUDE.md               fork notes: eight adapted skills become twelve
docs/superpowers/specs/            this spec; docs/superpowers/plans/ its plan
```

Untouched: the root `tools/terrain/` and `reference/terrain/` (upstream's
validator needs the root `method.md` and `toolkit-api.md`), `skills/terrain-cave/`,
and Chapman's other skills, agents and tools.

## 7. The toolkit (`skills/terrain-shape/tools/terrain/`)

### 7.1 The copy

- Copy every module and the `samplers/` package from `tools/terrain/`, with
  Chapman's MIT notice.
- Leave out `place_terrain.py` (his placer), `emit_plan_toon` and its TOON
  writer (his harness format), and the legacy voxel-grid path
  (`to_voxel_model`, `write_terrain_fills`, the `TerrainLayers` it uses), which
  imports a `voxel` package that is not part of this copy. Drop any test that
  only covers removed code.
- Keep the sampler graph, `HeightField`, erosion, climate, blending, masks,
  `MaterialSpec` materialisation, scatter, renders and `verify.py` as they are,
  except for the additions below.

### 7.2 Running it

From the workspace root (where `.minecraft-builder/` lives):

```text
uv run --no-project --with numpy --with scipy --with pillow --with opensimplex \
  python <terrain-shape>/scripts/terrain.py <command> [options]
```

`<terrain-shape>` is the `terrain-shape` skill's folder (`${CLAUDE_SKILL_DIR}`
in Claude Code; the folder holding its `SKILL.md` otherwise, as in spec 1
§7.5). The other three skills reach it as `../terrain-shape`, relative to their
own folder. The launcher puts `<terrain-shape>/tools` on `sys.path`, and
`<design-monument>/tools` too for commands that use the voxel toolkit (tree
previews, carve forms). Its commands cover at least: build a field from a
recipe and the heights file, verify, render, emit Ashlar phases, plan planting,
generate a custom tree, design an apron (integrate), and compare a built surface
with the expected one. The command names are the builder's.

### 7.3 Inputs from the live world

- **Heights file**, written by `ashlar_place.py heights` (§9.1) over the terrain
  box plus a margin of at least 16 blocks: per column, the ground (`SOLID`: the
  bed under water), the surface (`SOLID_OR_LIQUID_NO_LEAVES`) and the top (`ANY`:
  including leaves, the highest block to clear). A loader turns it into a
  `HeightField` of the existing ground. Tree trunks read as tall spikes in the
  ground and surface grids; the loader filters them (for example a small median
  filter where the top exceeds the ground by a tree's height) so edges blend to
  the real ground.
- **Site read**, written by the placer's shared column reader (§9.1) at design
  time: the exact blocks of the terrain box plus 8 blocks on every side, from the
  lowest seal depth to the highest top. The toolkit finds the existing trees in
  it (§7.5) and the survey finds non-natural blocks in it (§8.1). It is not the
  rollback point; the backup is taken again immediately before each phase writes.
- **Survey facts** from `exec-ashlar survey` (`survey.md`): the surface materials,
  existing water levels, block entities, other builds, and the non-natural blocks
  inside the box (§8.1).

### 7.4 Meeting the existing ground

- Every recipe for a live site is evaluated over the terrain box. The outermost
  ring of columns must equal the existing surface within one block, and the field
  blends from its own shape to the existing surface over a band whose width grows
  with the height difference (Chapman's guidance: about 14 blocks or more for a
  46-block difference). Use the existing blend tools (`pad_crop_smooth` with edge
  heights, `weld`, `sparse_convolution_blend`) or a new boundary node; the
  builder chooses.
- GATE A (`verify.py`) gains an `edge_match` check over that ring. A failed edge
  match fails the gate like any other check.
- Water that reaches the box edge must meet existing water at the same level, or
  the basin must be closed inside the box.
- When a design skill's build sits inside the terrain, its footprint becomes a pad
  at the build's datum inside the recipe (`HeightField.build_pad`), so pad and
  land are one continuous field.

### 7.5 Materialising for a live world (the Ashlar output step)

Chapman's column tool filled every column from a floor under the lowest surface.
In a live world that wipes ores, caves and aquifers under the whole area and
makes backups needlessly large. The port changes only what must change (my
call). For each column, with old ground `g`, old top `t`, new surface `s`, water
level `w` (if any) and `n` the lowest new surface among its four neighbours:

- **Solid** from `b = min(g, s, n) − seal` up to `s`: deep rock (stone, or
  strata bands by absolute y), then `subsurface_depth` blocks of subsurface, then
  the surface block from the mask-driven palette. `seal` defaults to 4. Taking
  `n` into account materialises every face a player can see from a lower
  neighbour; the seal closes cave pockets just under the new surface.
- **Water** from `s + 1` to `w` where `s < w` inside a closed basin.
- **Air** from `max(s, w) + 1` to `t` where `t` is higher, which clears lowered
  ground, plants and overhangs. It does not clear existing water or lava, which
  follow §7.7; existing trees follow the rule below.
- Everything below `b` stays as the world has it.

**Existing trees** (the user's decision). From the site read, the toolkit groups
logs, wood and huge-mushroom stems into trunks, and gives each leaf, cap block and
attachment (vines, cocoa, bee nests, snow on leaves) to the nearest trunk it
connects to, the way vanilla measures leaf distance. Each tree is then judged by
where its trunk meets the ground:

- **Rooted on ground that changes** (any trunk column whose new surface differs
  from the old one): every cell of the tree becomes air, or the liquid it stood
  in (§7.7), including cells outside the terrain box. Writes therefore reach past the box edge by up to a tree's
  reach (about 8 blocks sideways), but only into that tree's own cells.
- **Rooted on ground that does not change** (outside the box, or on the
  unchanged outer ring): the tree stays whole. The air rule skips its cells, so
  `t` above means the old top without them; only new solid ground (a raised
  surface) may replace them.

The project's `bbox`, the phase boxes and their backups include the removed
trees' cells. No other cell outside the terrain box is ever written.

The column stacks are merged into fills (a greedy box cover or similar; the
builder chooses). Decoding the fills back into columns must reproduce the stacks
exactly; a test checks it. The output is split into phases of at most about
128 × 128 columns (my call), so each phase can be backed up, placed, looked at
and rolled back as a unit; the placer pages each phase within Ashlar's limits.
Strata, belt regions and the layered material forms work as in Chapman's
`MaterialSpec`.

### 7.6 Shapes a heightfield cannot hold

Arches, sea arches, waterline notches, overhangs, undercut slot canyons, thin
spires and columnar basalt are authored as 3-D forms with the voxel toolkit
already copied into `design-monument` (no second copy), rendered offline, and
emitted as follow-on fill phases after the terrain mass: air fills for carved
forms, block fills for built-up forms. `terrain-landmark/reference/sequencing.md`
decides the order (carve-first forms are cut from the placed mass; build-up forms
are added outward; water comes last). An offline check refuses any gravity block
(sand, red sand, gravel, concrete powder, and so on) left directly above air,
because Ashlar places them without physics and the next block update would drop
them.

### 7.7 Water

- Lakes and seas are level. A descending river is a chain of level reaches with
  a step between each; flowing water appears only at steps and waterfalls.
- Flowing sources (step lips, waterfall lips) go in their own small phase with
  `liquids: "flow"`, within Ashlar's 2,000 flowing blocks per call (the placer
  enforces it, §9.1). Everything else is placed still.
- A waterfall's plunge pool is dug and filled with still water in the terrain
  phases, before the lip sources start flowing. Chapman's `sequencing.md` asks
  for a pool at least three times the fall height deep so the falls do not
  spread sideways; with the pool already full of still water that reason does
  not apply, and taken literally it would dig a 75-block pit under a 25-block
  Niagara. The depth becomes a look choice: a few blocks, deeper for big falls,
  at most about 12 (my call). `sequencing.md` is edited to say this and why —
  the one place this port changes Chapman's design knowledge.
- GATE A gains water checks on planned water: every water cell is contained (no
  still water next to air or to an open box edge), and no basin has a dry shelf
  below its level.
- **Existing water and lava stay** (the user's decision; the mechanics are the
  plan author's). Liquid above the old ground is left as it is unless new ground
  covers it. That includes water plants, waterlogged plants and roots, and ice
  lying on water. Where a bed is lowered, or a removed tree stood in the liquid,
  the opened cells are filled with that liquid, up to the still surface that
  rests on the bed. Planned water may raise a level, never lower one. An offline
  check refuses, before any file is written, a write that puts liquid beside or
  above open space where the site had no such contact. `hold_shores` (always on
  for aprons, optional in a recipe) keeps banks from being lowered.
- **Draining happens only with the user's yes** (the user's decision). It is
  never a first instinct, nor a fix for a failed spill check: design around the
  water first, and never raise ground over a body to avoid asking. When a design
  needs a drain, ask a separate question every time, one per body, naming the
  liquid, the place and the size, and saying that creatures in it may die and
  that a rollback does not bring them back. Record the answer in
  `requirements.md`; a yes covers that body in that build only. A body is all
  its connected liquid, falls and outlets included. One that reaches the box's
  outer ring cannot be drained, because it would flow back in.

### 7.8 Plants

`terrain-ecology` plans planting over the designed field (or over the existing
ground, from the heights file). Its outputs:

- **Vanilla features:** a commands file of `place feature <id> <x> <y> <z>` lines
  (y is the surface plus one) for the placer's runner. Species are chosen per
  biome from Chapman's `BIOME_CONTENT` (or the agent's own mix), placed by
  variable-density Poisson with no trees on cliffs or under water, more near
  water, and only on surfaces they can grow on.
- **Feature and biome ids** come from lists shipped with the toolkit, one pair
  per Minecraft version (configured-feature ids and biome ids), generated once
  from the vanilla game data of that version (my call). No Ashlar tool or
  allowlisted command can list them, and `place feature` cannot test an id
  without growing the feature. Chapman's lists were written for another version,
  and names such as `minecraft:pine` or `minecraft:birch_tall` may not exist, so
  `BIOME_CONTENT` and every species mix are checked against the list for the
  server's version (from `mc_status`) at design time; unknown ids are dropped or
  replaced before the user approves the design. A version with no list uses the
  nearest older one, and the design approval says so. The runner's report of
  rejected ids remains the backstop. The builder generates the lists for the
  server's current version and asks the user before downloading anything.
- **Custom trees:** module files from the generator (§7.9), a placements JSON,
  and the vegetation phase file stamped from them at design time (§9.2).
- **Ground cover, rocks and deadfall:** features or small vegetation modules;
  Chapman's random-decay trick (structure integrity) becomes several seeded module
  variants generated offline.
- **Biomes:** Chapman's `BiomeField` still picks palettes and species. Only after
  the user's separate yes (§8.4) does its biome plan become `fillbiome` commands:
  chunk-aligned boxes, each within the server's block limit for commands (32,768
  blocks by default, for example 16 × 16 × 128), in their own commands file.

### 7.9 The custom tree generator (`terrain/trees.py`)

- Parameters: wood and leaf blocks (any vanilla wood), trunk height, trunk width
  (1, 2 × 2 or a flared 3 × 3 base), taper, lean and curve, branching (levels,
  count, angles, length falloff), canopy shape (round, ellipsoid, conical,
  columnar, umbrella, weeping, layered, sparse or dead), leaf density and holes,
  optional roots, and a seed. The same seed gives the same tree.
- A small preset library (for example a broad oak, a conifer spire, an umbrella
  pine, a weeping willow, a windswept cypress, a dead snag and a giant fantasy
  tree), so the agent can start from a preset and vary it.
- Output: a module file in `exec-ashlar`'s format with `"kind": "vegetation"`, an
  `anchor` (the trunk base cell, which sits on the surface), and `wood`,
  `leaves` and optional `ground` (roots) parts. Logs carry the right `axis`;
  branches run along their axis; leaves carry `persistent=true` so they never
  decay; there are no air cells. Every leaf lies within six blocks of wood, so
  the canopy reads as attached.
- Preview renders through the voxel toolkit, which the agent looks at and shows
  the user before a tree goes into a plan.

### 7.10 Checks and renders

- `render_views` keeps its five PNGs (hillshade, relief, profile, slope,
  eye-level). The integrate apron adds before-and-after pairs and a profile across
  the seam.
- The output step writes `terrain/<element>.surface.json`: the expected top of
  every column after the build, with a mask of columns to skip around planned tree
  trunks (vanilla and custom).
- GATE A's report and its token go into the plan's notes.

### 7.11 Plan rows

The output step writes the phase files, commands files, module files and a
placements JSON under the project folder, and returns the `plan.toon` rows to add
(phases, modules, `quality_contract` rows and notes) as a ready TOON snippet. For
a standalone terrain project it writes the whole `plan.toon`. Long generated
lists — feature commands and tree placements — stay in their own files and never
go into `plan.toon` tables (my call), so a human can still read the plan.

## 8. The four skills

### 8.1 What all four share

- **Frontmatter.** `name` matches the folder; the description is concrete about
  when to use the skill and ends with "Builds through Ashlar with the exec-ashlar
  skill."; Chapman's `model` and `effort` stay (`sonnet` with `high` for shape and
  landmark, `sonnet` with `medium` for ecology and integrate); `context: fork` is
  removed; `metadata.short-description` is added for Codex; `allowed-tools`, if
  present, lists only the read-only Ashlar tools (spec 1 §7.5).
- **Connection.** Run `mc_status`; if Ashlar is unreachable, stop and tell the
  user.
- **Survey.** Use `exec-ashlar survey <project>` plus the terrain additions in
  its `survey.md` (§9.3): the heights file, the site read, existing water levels,
  and every non-natural block inside the terrain box, found in the site read
  (anything outside a natural-block list kept in the toolkit: planks, glass,
  wool, rails, doors, beds and so on). A village or player structure inside the
  box stops the design until the user says what to do. The gate repeats the
  finding.
- **Project rule.** Called for a design skill's build, a terrain skill adds its
  phases to that build's plan. A standalone request is its own project.
- **Phase order in a combined plan** (my call): site preparation and terrain mass
  first, then carve and build-up forms, then flowing-water sources, then the
  design skill's own phases, then planting (custom trees, vanilla features, ground
  cover; planting after the buildings means the air filter keeps trees out of
  them), then a biome change, with entities after all blockwork as
  `execution.md` already requires.
- **Two approvals.** The user first approves the design (renders and a summary:
  box, relief, cells changed, palette, water, existing liquid kept, covered and
  added, any drains, planting counts, custom trees, the phases); only then does `exec-ashlar build` run its own approval gate. No world
  write happens before that gate.
- **Looking at offline renders:**
  - Claude Code: `Read` the PNG files.
  - Codex: `view_image` on them.
  - Otherwise: report the numbers from the verify report and ask the user to open
    the files.
- **Interview questions:**
  - Claude Code: `AskUserQuestion` for multiple-choice questions.
  - Codex: `request_user_input` if it is listed among your tools.
  - Otherwise: plain text.
- **Hand-off.** Skills hand off by name (spec 1 §7.5). Terrain and landmark hand
  off to `terrain-ecology` for planting, then the plan goes to `exec-ashlar build`.
- **Re-sculpting** edits the recipe and re-emits; it never discards detail. A
  rebuild of the same project is an iteration: new phases get new rollback
  points, and a full rollback restores everything newest first.
- **Verify at eye level, never from the top alone.** Offline: the slope and
  eye-level renders. In the world: `mc_render` top and heightmap views of the box,
  vertical `slice` views along a few x and z lines (profiles), and facades of edge
  strips within Ashlar's 200,000-cell side-view limit. For hero terrain, ask the
  user to look in game.

### 8.2 `terrain-shape`

Naturalistic land: mountains, valleys, hills, rivers, lakes, coasts, islands,
plateaus, and reshaping land around a build.

1. Connection and survey (§8.1).
2. A short interview when the request is standalone (landform, size, feel, what
   it should be seen from). Called by a design skill, it takes that design's
   datum, footprint and palette instead.
3. Write the recipe as one continuous sampler graph that meets the existing
   ground (§7.4), with erosion (thermal, then hydraulic with `pad_cells`) and a
   mask-driven `MaterialSpec`.
4. Run GATE A; on a failure, fix the recipe, never the blocks.
5. Look at the renders; iterate.
6. Get the user's design approval (§8.1).
7. Hand off to `terrain-ecology` for planting (it may decide on no planting).
8. Emit the phases and plan rows (§7.11) and hand off to `exec-ashlar build`.

Chapman's six non-negotiables stay as written: one continuous field, no
ziggurats, a mask-driven surface, verify at eye level, erosion, a saved recipe.

### 8.3 `terrain-landmark`

Recognisable natural wonders (Grand Canyon, Niagara, Uluru, Halong Bay, Bryce,
Devils Tower and the like). Everything in §8.2, plus:

- **Composition first.** Before any recipe work, propose the wonder, its 2–4
  signature features, the scale against the minimum recognition footprint in
  `wonders.md`, the palette, and one or two alternatives; the user confirms.
- **Research** a named wonder with `survey-research`; its citations go into the
  registry entry's `citations`.
- **Signatures are checked.** Each signature becomes a measurable check where
  possible (visible band count on canyon walls, aspect ratio within ±10–20 % of
  the target, a horseshoe brink's curve), run offline with GATE A and recorded in
  the verify report, plus in-world `acceptance` cells (for example the band block
  expected at a wall sample) and the existing `silhouette` and
  `block_mix_ratios` rows. A signature that cannot be measured is named at the
  design approval as "checked by eye".
- **Carve and build-up forms** go through §7.6, in the order `sequencing.md`
  gives.
- Reference stubs point at `../terrain-shape/reference/terrain/`.

### 8.4 `terrain-ecology`

The planting design: plant communities, species mixes, density and ecotones,
canopy first, then understory, then ground cover, matched to the palette. Also
the home of custom trees and of the biome decision.

- **Inputs:** the designed field and recipe from `terrain-shape` or
  `terrain-landmark`, or — for planting existing land — the heights file.
- **Outputs:** §7.8: the features commands file, custom-tree modules and their
  stamped vegetation phase, and (only after a yes) the biome commands file; plus
  a one-line summary of species and density.
- **Custom trees.** When the user wants trees vanilla does not grow, or a hero
  tree, design them with the generator (§7.9), show the previews, and use them
  alone or as one species in a mix. `reference/custom-trees.md` explains the
  parameters and presets.
- **Phase order:** custom trees, then vanilla features, then ground cover, then
  any biome change last (so it is the first thing rolled back and easy to drop at
  the gate).
- **The biome rule.** The skill text says, in this order:
  1. The world's existing biome is the default. Choose palettes, species and
     water so the terrain works in it.
  2. Consider a change only when the look depends on something only a biome gives
     (snowfall and snow cover; grass, foliage and water colour; fog and sky; mob
     spawning) and the user asked for terrain that should read that way.
     Keep the existing biome for site preparation and grading. The elevation
     model's biome labels guide offline design and never choose what to paint.
  3. Ask a dedicated question every time. Have the user name the biome.
     Verify its ID against the running Minecraft version and show the exact
     chunk-aligned box, the purpose, and the approximate rollback (one
     recorded biome per chunk). Wait for that dedicated approval.
  4. Record the approved ID and box in `requirements.md`. Every biome
     command paints that ID. Without a yes, build with the existing biome
     and tell the user what will look different.
  5. Tell the user that biome colours appear once players' chunks reload.

### 8.5 `terrain-integrate`

Grounds a build into the land around it so it reads as belonging there: an
apron of eroded ground around the build's footprint (the protected region,
which never changes), recoloured to match the surrounding blocks. Also makes
existing land that looks artificial look natural.

- **Planned mode** (with a design skill's site prep). The design skill passes
  the footprint regions and their pad heights. The skill reads the heights file
  and the surrounding palette (`mc_inspect` stats of a ring just outside the
  apron, near the surface), designs pads and aprons as one field offline (thermal
  plus light hydraulic erosion weighted by a smoothstep taper across an apron of
  8–24 columns, wider for bigger steps; rock on newly steepened faces; water
  re-flooded; the build's palette blended into the surrounding one across the
  taper), and returns site-prep phases that go first in the host plan.
- **After the fact.** For a build that already stands, or to naturalise existing
  land, the skill reads the live heights, designs the apron, and builds it as its
  own project named `<host>-ground`, whose registry entry has `grounds: "<host>"`.
  The protected region is the host's bounding box; the output step guarantees no
  cell inside it changes (a test checks it).
- **Dry run first.** Before the design approval the user sees before-and-after
  renders, a profile across the seam, and the height changes (largest, mean,
  columns moved). Any column moving more than 6 blocks (my default) needs the
  user's explicit OK.
- Existing water and lava follow §7.7, with shores held. `terrain-integrate`
  never drains.
- Chapman's note on carving a ledge into a wall (a sloped-back bench; all clears
  before all ledge fills) stays as design knowledge.
- The output step and `quality_contract` rows are the same as terrain's, with a
  `seam` row for every protected edge.

### 8.6 Edits to the reference text

The rule from spec 1 §7 holds: change only text that points at Chapman's
pipeline or tools; keep design knowledge as written.

| Chapman's instruction | Replacement |
| --- | --- |
| `block_fill_columns`, `block_fill_columns_strata`, `block_fill_region`, `block_fill_batch` | The Ashlar output step (§7.5) and `mc_build` fills through the placer |
| `level_fill_biome` | `fillbiome` through the placer's runner, only after the user's yes (§8.4) |
| `level_place_feature`, `level_place_features_batch` | `place feature` in a commands file run by the placer (§9.1) |
| `structure_save_from_world`, `structure_load_to_world` (weathering, deadfall) | Module files, `stamp.py`, seeded variants |
| `block_erode_region`, hydraulic erosion jobs | The offline route: heights file, toolkit erosion, renders, fills |
| `block_get_top_y`, `block_scan_region`, `block_get_state` | `mc_survey` (`matrix: true`, or the placer's `heights`), `mc_inspect` |
| `level_get_biome_at`, `level_get_mob_spawns` | `execute if biome` (allowlisted), or inference from the survey |
| `${CLAUDE_PLUGIN_ROOT}/reference/terrain/…`, `${CLAUDE_PLUGIN_ROOT}/tools/terrain` | Paths relative to the skill folder (`reference/terrain/…` in `terrain-shape`, `../terrain-shape/reference/terrain/…` elsewhere) |
| `exec-worker`, `exec-plan`, `exec-inspect`, `exec-reflect`, `exec-blueprint`, the harness and its lint | `exec-ashlar` build, verification and its gate |
| `build-*` orchestrators, "return to the orchestrator", the coherence context | "Hand-off" (spec 1 §7.1); the main session sequences the skills |
| `mcb:<project>_…` templates | `modules/<name>.json` |
| GATE B (mandatory integration after every build) | The offered `terrain-integrate` step (§8.5, §10) |
| `terrain-cave` | Removed, or "designed caves are not available yet" |
| Chapman's limits (65,536 columns, 32,768-block fills, 8,192-entry batches, 256 force-loaded chunks per dimension) | Ashlar's limits in `exec-ashlar/reference/tools-and-limits.md` |

A link from one terrain skill to another's file is written relative to the skill
folder (`../terrain-shape/reference/terrain/method.md`); a bare
`reference/terrain/…` link appears only inside `terrain-shape`, where the copy
lives. Every `terrain-*` `SKILL.md` still contains the text `reference/terrain/`,
which upstream's validator requires.

## 9. What `exec-ashlar` gains

### 9.1 New placer subcommands

`ashlar_place.py` stays stdlib-only (Python 3.11+), keeps its config discovery,
redaction and exit codes (0 ok, 2 invalid input, 3 refused by a limit or rule,
4 player in the area, 5 server error), and gains:

```text
ashlar_place.py backup   --box X1 Y1 Z1 X2 Y2 Z2 --out DIR [--world W] [--log PATH]
ashlar_place.py restore  DIR [--world W] [--player-margin 2] [--log PATH]
ashlar_place.py place    FILE (--snapshot [--label L] | --backup DIR | --no-snapshot) [...]
ashlar_place.py heights  --area X1 Z1 X2 Z2 --out FILE [--world W]
ashlar_place.py commands FILE [--check] [--progress PATH] [--world W] [--log PATH]
ashlar_place.py biome-probe   --box X1 Y1 Z1 X2 Y2 Z2 --out FILE [--candidates LIST] [--world W]
ashlar_place.py biome-restore PROBE --out FILE
```

The builder may rename or regroup them, and may move the shared MCP client,
config lookup and redaction into a module beside the script if it grows past
about 1,000 lines.

**Shared with sub-project 3.** The redstone spec (branch `redstone`) adds an
`ashlar_place.py read` subcommand that reads a box the same way. The two
branches share one column reader: it tiles the box, calls `mc_inspect`
`format: "columns"`, and parses each line into per-column runs
`(y1, y2, state)`. Each subcommand writes its own output — `read` a flat
cell map for small boxes, `backup` the runs, compressed, with a manifest.
Whichever branch merges first owns the reader; the other reuses it. Terrain uses
it twice: for the design-time site read (§7.3), written in the backup's run
format, and for the backups themselves.

- **`backup`.** Reads the box with `mc_inspect` `format: "columns"` in tiles of at
  most 1,024 columns and 200,000 cells (fewer columns when the box is taller than
  195 blocks), and writes a manifest (box, world, time, column count, a checksum,
  the Ashlar version) and the compressed column runs (gzip from the standard
  library) to `DIR`. It checks that every column is present and covers the box's
  full height, and that the restore fills it would produce pass the placer's own
  validation and paging. Only then is the backup complete; an incomplete backup
  is an error, and nothing is written.
- **`restore`.** Checks players, turns the runs back into fills (adding the
  `minecraft:` namespace, which `mc_inspect` leaves off), and places them with
  `liquids: "static"` and `connect: false`, so every block state — water levels,
  leaf distances, stair shapes, fence connections — comes back as recorded. It
  loses what a snapshot loses: entities, sign text and container contents.
  Placing the same backup twice gives the same result.
- **`place --backup DIR`.** Takes the backup immediately before writing (after the
  player check), then places the phase; it refuses to place if the backup is not
  complete.
- **`heights`.** Calls `mc_survey` with `matrix: true` in tiles of at most 200,000
  cells, once each for `SOLID`, `SOLID_OR_LIQUID_NO_LEAVES` and `ANY`, ignores the
  image, and writes one JSON file: origin, size and the three grids (row-major,
  `null` where a column has no surface).
- **`commands`.** Runs a commands file. Only two forms are accepted:
  `place feature <id> <x> <y> <z>` and `fillbiome <x1> <y1> <z1> <x2> <y2> <z2>
  <biome>`, with namespaced ids; anything else is exit 2. `--check` validates
  offline: the forms, integer coordinates, every position inside the file's box,
  and a `fillbiome` volume within the block limit. A run:
  1. adds the `minecraft:` prefix to each command (`minecraft:place …`);
  2. runs `forceload query` and leaves already-loaded chunks alone, as
     `commands.md` requires;
  3. groups the commands into tiles of at most 256 chunks, including a one-chunk
     margin so trees can grow across chunk edges;
  4. for each tile: checks players (a player inside the tile's box grown by the
     margin stops the run before that tile), adds the force-load, runs the tile's
     commands one at a time, and removes the force-load — always, even after a
     failure; a removal that fails is reported loudly with its chunks;
  5. records each command's result, continues after a command fails (a tree with
     no room to grow), and writes a progress file so a resumed run skips commands
     already done;
  6. exits non-zero with its own exit code when commands failed, listing them.
  For a plan outside the server's main world, it wraps each command in
  `execute in <dimension> run`, only when the user agreed at the gate (the rule
  in `commands.md` today).
- **`biome-probe`.** Read-only apart from its paired force-loads: for each chunk
  in the box it tests likely biomes with `execute if biome` at the surface (the
  previous chunk's biome first, then the survey's, then the rest of the shipped
  biome list for the server's version, §7.8) and writes the biome per chunk, or
  `unknown`.
- **`biome-restore`.** Offline: turns a probe into the `fillbiome` commands file
  that paints each chunk back, chunk-aligned and split vertically to stay within
  the block limit.
- **Flowing liquids.** When a phase sets `liquids: "flow"`, the placer keeps the
  liquid blocks in every page at or under Ashlar's 2,000 per call, splitting fills
  as needed, and `plan` reports the count.
- **`filter`.** A fill's `filter`, when present, must be a `minecraft:` block
  state string.

### 9.2 `stamp.py`: vegetation modules

- A module with `"kind": "vegetation"` may overlap other vegetation placements
  (never other modules). Its parts are stamped as fills with
  `filter: "minecraft:air"`, in this order for the whole phase: every placement's
  `ground` part (roots, placed without the filter), then every `wood` part, then
  every `leaves` part. Wood therefore never gives way to leaves, and nothing
  replaces terrain or another tree's wood.
- Single cells become 1 × 1 × 1 fills (merged where possible), because `blocks`
  entries cannot carry a filter.
- Rotation and mirroring work as for any module (log `axis` turns).
- A placement's origin comes from the tree's `anchor` and the surface height at
  the trunk, which the output step computes.

### 9.3 Plan format and survey (`plan-format.md`, `survey.md`)

- **Phases** may carry a `rollback` column: `snapshot`, `backup`, or `biome` (a
  `fillbiome` phase, rolled back from its probe). Terrain phases use `backup`.
  Without the column a phase behaves exactly as today, so existing plans are
  unchanged.
- **A `commands` phase may name a commands file** in its `file` column; the
  placer's runner runs it. With `file` set to `-`, the phase uses rows of the
  `commands` table, run by the model, as today.
- **New `quality_contract` rows:**

  | Row | Fields | Passes when |
  | --- | --- | --- |
  | `surface_match` | `region_a,region_b,file,tolerance,min_ratio` | at least `min_ratio` of the region's columns (outside the file's skip mask) have a built top within `tolerance` of the expected top in `file` |
  | `seam` | `from,to,max_step` | along the edge from `from` to `to`, the height step between the outermost changed column and the first unchanged column outside is at most `max_step` |
  | `water_continuity` | `region_a,region_b,level` | every sampled column whose bed is below `level` holds water from the bed up to `level`, with no air gap, and no water cell borders air at the region's edge |

- **Notes** carry the recipe path, the GATE A token, the feature-id version
  check, the placements JSON path, and a pointer to the biome yes in
  `requirements.md` when there is one.
- **Validation** (start of `build`) adds: every commands file passes
  `commands --check`; a `fillbiome` file needs the recorded yes; every drain
  in the notes needs the recorded yes for that body and build; every
  `surface_match` file exists; every `backup` phase's box is known.
- **Survey** (`survey.md`) gains a terrain section: write the heights file over
  the box plus a 16-block margin and the site read over the box plus 8 blocks
  (§7.3); note existing water levels; list every non-natural block inside the
  terrain box from the site read, and stop for the user's decision if a structure
  is there.

### 9.4 Approval gate, phases and resume (`execution.md`)

The gate adds, for terrain builds:

- per backup phase: its box, the number of reads and the estimated disk size,
  instead of snapshot slots; for snapshot phases whose snapshots would evict
  other builds' rollback points, the offer to switch them to backups;
- per commands file: the count per form and per feature id, the force-load tiles
  and their chunk counts, and what happens when a tree fails to grow — not every
  line; the file path, so the user can open it;
- a biome change again, with the recorded yes, the box, and its approximate
  rollback (chunk resolution; chunks the probe cannot identify keep the new
  biome — if any are unknown at build time the biome phase stops for the user);
- existing water and lava kept, covered and added, and each drain again with
  its recorded yes;
- the non-natural blocks found inside the box;
- how many existing trees will be removed whole, and the farthest any write
  reaches outside the terrain box;
- an estimated duration for big jobs, and the players online.

Sizing (build step 2) adds, for each backup phase, the number of column reads
and the estimated backup size, computed from the phase's box.

Each phase follows today's steps, with backups taken by `place --backup` (or
`backup` before an `mcp` phase's own `mc_build`), commands files run by the
runner, and the biome probe run immediately before a biome phase, its file
recorded in the registry. A `place feature` commands phase takes a backup before
the runner starts, over the box of its feature positions grown by the reach of
the largest tree it plants (my default: 8 blocks sideways and 32 up), and that
box is the phase's `from`/`to`.

**Resume.** If `build` finds the project `building` (a phase stopped part way),
it shows which phases are recorded as placed, asks the user whether to resume or
roll back, and on a resume continues from the first phase not recorded as placed.
The interrupted phase keeps the rollback point taken before its first write (its
backup, snapshots or biome probe) and is placed again from the start (fills are
idempotent); no new rollback point is taken for it (the placer runs it with
`--no-snapshot`), because one taken after a partial write would record the
partial state. The resume gate says if any of the phase's original snapshots has
been evicted since. A resumed commands file skips the commands its progress file
marks done. The redstone spec's recovery section (its §6.6) uses the same rule,
agreed with that session on 2026-11-19, so `execution.md` ends up with one.

**Rollback** restores newest first: biome phases from their probes, backup phases
with `restore`, snapshot phases with `mc_restore`, then entities as today.
Before it starts, the user sees the list, including the backups' sizes and the
approximate biome reset. Rolling back a host that has a `<host>-ground` project
first offers to roll back the grounding project.

### 9.5 Console allowlist (`commands.md`)

- New form: `fillbiome <x1> <y1> <z1> <x2> <y2> <z2> <biome>` — only in a
  commands file of an approved plan, only inside the plan's terrain box, only
  after the user's separate yes recorded in `requirements.md`, only after a
  biome probe of the same box, and in chunk-aligned boxes within the server's
  block limit for commands (32,768 blocks by default; the command's error says if
  the server uses another).
- `place feature` and `fillbiome` in commands files run through the placer's
  runner, which applies the force-load, prefix and player rules itself.
- The read-only `execute if biome` form also serves the biome probe, inside its
  paired force-loads.

### 9.6 Verification (`verification.md`)

- How to check the three new rows: `surface_match` with a fresh `heights` read and
  the toolkit's compare command; `seam` from a heights read of a band across each
  edge; `water_continuity` with `mc_inspect` columns over sampled columns (at most
  1,024 per call).
- How to look at terrain (§8.1): top and heightmap views, vertical slices as
  profiles, edge-strip facades, the offline renders for comparison, and the user's
  in-game look for hero terrain.
- Planting: the runner's report (placed, failed, unknown ids) is the evidence.

### 9.7 Registry (`registry.md`)

A phase entry may record `rollback`, `backup` (the backup folder, relative to the
project), and `biome_probe` (the probe file). A project may carry `grounds`
(after-the-fact integrate) and a `terrain` key (recipe, surface file, placements
file). Unknown keys are kept, as today.

### 9.8 Limits (`tools-and-limits.md`)

Adds: column reads as the backup source (1,024 columns and 200,000 cells per
call); the `fillbiome` block limit; the flowing-liquid cap as the placer enforces
it; `mc_survey`'s matrix as the source of the heights file.

## 10. Edits to the design skills

- **Site preparation.** Where a design skill plans site prep, it adds: if a pad
  would sit more than about 1–2 blocks above or below the surveyed ground at any
  edge, offer the `terrain-integrate` skill for the site prep (planned mode);
  otherwise plan the simple `site-prep` phase as today.
  *Amended 2026-11-25 (user decision):* integration is included by default.
  Each design skill has a "Ground the build" section: unless the ground along a
  footprint or paved edge is flat and undisturbed (within about 1 block of the
  planned level, with no cut face, fill or cleared edge), the design includes
  `terrain-integrate` (planned mode) and shows its renders with the blueprints;
  the user may decline it at approval. The seating rules (flush foundations,
  retaining walls, door sills, contour paths, ground texture) live in
  `terrain-integrate/reference/integration.md`. New landforms stay with
  `terrain-shape` and `terrain-landmark`.
- **Planting.** Where a design skill plants naturalistic vegetation (for example
  design-village's paragraph on growing trees), point to `terrain-ecology`.
  Formal, deliberately placed planting stays in the design skill.
- The "if it is installed" wording may stay.

## 11. Testing and verification

1. **Static checks** (`tests/ashlar/test_skill_text.py`):
   - The four terrain skills join the scanned list.
   - The forbidden list grows to cover every Chapman tool, executor, orchestrator
     and harness name the terrain text uses: at least `level_fill_biome`,
     `level_place_feature`, `level_place_features_batch`, `block_erode_region`,
     the hydraulic erosion job tools, `block_replace_in_region`,
     `level_get_mob_spawns`, `structure_create_from_blocks`, `structure_list`,
     `place_terrain`, `emit_plan_toon`, the `build-*` orchestrator names, and
     `terrain-cave` inside the four skills.
   - `32,768` stays forbidden except on a line that mentions `fillbiome`.
   - Every reference link in the four skills resolves relative to the skill's own
     folder — stricter than upstream's validator, which also accepts the root copy.
   - Sibling names `terrain-ecology` and `terrain-integrate` join the allowed ones.
   - Client-specific names only on labelled lines; frontmatter valid; upstream's
     `node scripts/validate-plugin.mjs` passes.
2. **Toolkit tests** (`tests/ashlar/terrain/`), run with
   `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex`:
   - Chapman's tests run against the copy, minus those for removed code.
   - The output step: decoding the fills reproduces the column stacks exactly,
     including the seal band, water and cleared air; cells below `b` are never
     written; phases stay within the size rule.
   - Existing trees: a tree rooted on changed ground just inside the edge is
     removed whole, canopy outside the box included; a tree rooted outside the
     box keeps every cell, including canopy over the box; nothing else outside
     the box is written.
   - Existing liquid: kept by default (river, lava, ice, waterlogged cells); a
     new spill is refused; a drain needs its approval and is refused when the
     body reaches the outer ring.
   - Edge match, water containment, the gravity-block check, and the heights-file
     loader (from a fixture of `mc_survey` matrix text, with trunk spikes).
   - The tree generator: same seed, same tree; no air cells; every leaf within six
     blocks of wood; logs oriented; `persistent=true`; the anchor on the trunk base.
   - Integrate: no cell inside the protected region changes.
   - The emitted plan rows pass `exec-ashlar`'s validation.
3. **Placer and stamp tests** (`tests/ashlar/`, against the fake server, which
   learns `mc_inspect` columns, `mc_survey` matrices and console replies for
   `place feature`, `fillbiome`, `forceload` and `execute if biome`):
   - backup tiling (columns and cells), run parsing with block states, the
     completeness check, and a backup-then-restore round trip;
   - the runner: allowlist, `--check`, prefixing, `forceload query` handling,
     tiles within 256 chunks, removal after a failure, per-tile player checks,
     progress and resume, failure reporting, redaction;
   - heights tiling and parsing; biome probe order and `unknown`; biome-restore
     tiling;
   - the flowing-liquid cap and `filter` validation;
   - `stamp.py` vegetation overlap, part order and the air filter, for every
     rotation and mirror.
4. **Live, read-only:** a `heights` read and a `backup` of a small area (a backup
   only reads).
5. **Live write test** (asked first, in a scratch area away from players and
   builds, chosen from a survey):
   - a hill with a small pond of about 48 × 48, built with backups;
   - three to five vanilla trees through the runner and two custom trees;
   - optionally a biome change on one chunk column (asked separately);
   - verification of every row;
   - rollback; a fresh backup read of the box must match the original column for
     column, and a fresh biome probe must match the first one.
6. **Dry runs:** each of the four skills on a small prompt, in a read-only
   subagent stopping at the approval gate: it surveys through Ashlar, writes
   valid phases and plan rows, keeps commands in the allowlist, asks the biome
   question only when warranted, and never points at a missing Chapman component.
   The existing `ashlar-dry-run` agent (in the workspace's `.claude/agents/`) has
   no shell, and the terrain skills need one for the toolkit and the placer's
   `heights`. Add a terrain variant with Bash, told to run only the toolkit
   launcher and the placer's `plan`, `heights`, `backup` and `commands --check` —
   never `place`, `restore`, `biome-probe` (it force-loads) or `commands` without
   `--check`.

## 12. Install and documentation

- After the merge, and with the user's OK, link `terrain-shape`,
  `terrain-landmark`, `terrain-ecology` and `terrain-integrate` into the
  workspace's `.claude/skills/` and `.agents/skills/` like the other eight, and
  check that both clients list them.
- The fork notes at the top of `README.md` and `CLAUDE.md` go from eight adapted
  skills to twelve, and mention the toolkit's location and its `uv` command.
- The live skills follow the clone's checked-out branch; after this merges, the
  clone should have `main` checked out (spec 1 §10).

## 13. Out of scope

- `terrain-cave` and designed underground space.
- Chapman's harness, orchestrators, agents and other `exec-*` skills.
- Server-side erosion, new Ashlar features, an HTTP transport, the `wss://`
  migration.
- Game rule or server setting changes.

## 14. Risks

| Risk | Mitigation |
| --- | --- |
| The copied toolkit misses Chapman's later fixes | Re-copying is a deliberate step; the copied tests run after every re-copy |
| Feature ids differ between Minecraft versions | Checked against the server's version before use; the runner reports rejected ids |
| A backup is incomplete or unreadable when needed | The backup is checked before any write; no complete backup, no write |
| Backups do not keep entities, sign text or container contents | Same as snapshots; the survey lists block entities and the gate warns |
| Animals or dropped items inside the box are buried or left floating | The gate says so; terrain boxes avoid farms and builds |
| Draining kills creatures in the water, which a rollback cannot restore | Only with the user's separate yes, which names that loss; backups restore the liquid itself |
| A biome rollback is approximate | The user hears it before agreeing; chunks the probe cannot identify stop the biome phase |
| Sand and gravel fall at the next block update | Never left above air (offline check) |
| Stepped still water starts to flow when something updates it | Rivers are level reaches; flow only at steps and falls |
| Landscape builds load the server for minutes | The gate shows the estimate and who is online; phases are sequential |
| A force-load is left behind after a failure | The runner removes force-loads in every case and reports any removal that fails |
| A player's structure inside the box | The terrain survey lists non-natural blocks and stops for the user |
| Removing a crossing tree writes outside the terrain box | Only that tree's own cells; the gate shows the count and the farthest reach; backups and the project `bbox` include them |
| Removing a tree with a bee nest loses its bees (block-entity data) | The survey lists bee nests with the other block entities; the gate warns |
| The vegetation filter leaves a gap where an existing block blocks a branch | Accepted; the canopy simply misses that cell |
| Sub-project 3 edits the same `exec-ashlar` files (placer, `execution.md`, `plan-format.md`, `verification.md`, `registry.md`, the static test, the fork notes) | One shared column reader; one resume rule; the branch that merges second rebases and fixes the skill counts |

## 15. Left to the builder

- The fill-merging algorithm and the exact phase size within the rule in §7.5.
- How the boundary blend is implemented (§7.4) and how trunk spikes are filtered.
- Exactly which blocks count as trunk, leaves and attachments when grouping
  existing trees (§7.5), and the margin used for very large trees.
- Command names for the launcher (§7.2) and the placer (§9.1), file formats for
  backups, heights, probes, commands files and the expected-surface file.
- The natural-block list, the biome candidate order, and the duration estimate.
- The tree generator's parameter names and preset list.
- How each landmark signature is measured.
- Whether `ground` cover is placed as features or as blocks.
- An optional pause between placer pages for busy servers.
- Splitting `ashlar_place.py` into a module and a script if it grows too large.
