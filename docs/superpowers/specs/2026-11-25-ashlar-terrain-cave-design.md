# terrain-cave on Ashlar — design

Sub-project 4 of the Ashlar adaptation. Ports Chapman's `terrain-cave`
(designed underground space) to build through Ashlar with `exec-ashlar`,
reusing the terrain toolkit the terrain sub-project ported
([terrain spec](2026-11-19-ashlar-terrain-design.md)).

## Intent

Players want deliberate underground space: a cavern hall for a base, a lush
grotto off an existing cave, a lava tube or ravine as scenery, a passage that
links two places. Vanilla caves are noise; a designed cave has a known
entrance, a route, chambers sized for a purpose and a material story. The user
asked for the port during a quality audit (feature completeness) and handed
over the design ("just dive in"), so every choice below is the builder's call.

## Goals

- A cave design file the agent writes (chambers, passages, ravines, shafts,
  pillars, style, lighting, features, pools) turned offline into checked,
  backed-up Ashlar phases.
- Carving that never breaks the surface by accident, never drains or spills
  water or lava, and never leaves sand or gravel hanging.
- Player blocks may be changed or moved, but only after the user has seen an
  exact list of what, where and why and said yes (user decision, 2026-11-25).
- Existing caves can be adopted as they are — lit, planted and extended —
  so a player's cave base can be improved without reshaping it.
- Dressing that reads as a place: wall, floor and ceiling palettes banded by
  depth, natural ores left showing, vanilla cave features grown in place.
- Spawn-proof by default: lights placed until every floor cell is lit.
- A post-build check for the cave-specific quality rules.

## Non-goals

- Changing the ground surface. Caves are forms-only; grading around a cave
  mouth uses `terrain-integrate`.
- Mines with rails, vaults with doors and other buildings: those stay with
  the design skills (a cave base is a cave plus a `design-house` or
  `design-building` plan inside it).
- Sculk and deep-dark features (a shrieker can summon a warden).
- Flowing underground rivers in v1 (still pools only; flowing water can be
  added later through the existing `falls` machinery).

## Approaches considered

1. **Forms-only emit inside the terrain toolkit (chosen).** A cave generator
   writes carve, dress, pool and light layers as 3-D writes and emits them
   with the same projection, liquid and gravity checks the terrain emitter
   uses, minus the surface mass pass. Reuses column backups, phase files and
   the `commands` runner for features.
2. **A terrain recipe with voxel forms.** Recipes already take `forms` in
   carve mode, but every recipe re-materialises the top `seal` blocks of each
   column in the field, which would repaint the surface above the cave.
3. **Hand-written fills from the skill text.** No offline checks; carving next
   to an aquifer or under gravel would be caught only after the fact.

## Design

### Design file (`terrain/<element>.cave.json`)

`element`, `seed`, `site` (project-relative exact site read covering the cave
plus its surface), and any of:

- `chambers`: `{center, radii, floor?, roughness?}` — noisy ellipsoids; an
  optional flat floor level.
- `passages`: `{points, radius: [start, end], floor?, roughness?}` — swept
  tubes along a 3-D polyline.
- `ravines`: `{points (x, z), top, bottom, width, roughness?}` — tall slots
  that narrow toward the bottom.
- `shafts`: `{at (x, z), from, radius}` — designed openings to the surface
  (entrances, skylights); the only places the roof may be broken.
- `pillars`: `{at (x, z), radius}` — rock left standing through the void.
- `roof` (default 4): minimum rock kept between the void and the surface.
- `style`: `plain`, `dripstone`, `lush` or `deep`; `palette` overrides per
  role (`wall`, `floor`, `ceiling`) as weighted block maps; `dress: false`
  skips dressing.
- `lights`: `{block?, min (default 1), max_count?}` or `false` for a dark
  cave; `features`: per-style defaults, overridable as `{id, on, per_100}`.
- `pools`: `{at, level}` — still water in a floor hollow.
- `limits`: `max_span` (default 24), `ceiling_std` (default 0.75),
  `flat_run` (default 14). Measured over 48 generated chambers (radii 6–18,
  12 seeds each): flat runs stayed at or below 12 and spreads at or above 0.85,
  while a flat-roofed room scores a spread of 0 and a run as wide as the room.

### Generator (`terrain/caves.py`)

1. **Void.** Seeded 3-D value noise roughens every shape. Pillars are removed
   from the void. Cells within `roof` of the measured surface are trimmed
   except inside shafts; the trim count is reported. A void that meets built
   (unnatural) blocks is refused.
2. **Dress.** Solid cells face-adjacent to the void, if natural rock or soil,
   take the role palette (ceiling, wall, floor), with depth bands (deepslate
   kinds below y 0). Ores and other blocks stay. Gravity blocks are used only
   on a solid support.
3. **Pools.** Void cells connected to `at` at or below `level` become still
   water; the emitter's open-face check refuses a pool that would spill.
4. **Lights.** A block-light flood (one level lost per step through the void)
   finds the darkest standable floor cell; a light block is set into the
   ceiling above it; repeat until every floor cell reaches `min`.
5. **Features.** Positions per role and density become `place feature`
   commands in a features commands file (backup box grown by the feature
   reach), checked against the bundled 26.3 feature ids.

### Existing caves and player blocks (added 2026-11-25)

- `existing: [{at, box}]` adopts the open space connected to `at` inside the
  box and below the ground surface. Adopted cells are never carved; they join
  the cave for lighting, features, pools and the light check.
- Player blocks count as full cubes unless their id names a partial shape
  (stairs, slabs, fences, doors, lanterns, carpets…); glass and leaves let
  light through. The emitter's table knows only natural blocks.
- Lighting starts from the light already in the read, so a player's lanterns
  count. Under a built ceiling with no natural rock to hold a light block, a
  hanging lantern (`lights.hang`) goes in the air under the ceiling when two
  clear cells stay above the floor.
- `moves: [{from, to}]` re-places a block (state only; block-entity contents
  and text stay behind and are flagged); two-block doors, plants and beds move
  only with both halves.
- `dress` defaults to `new`: only rock touching carved cells is repainted, so an
  adopted cave keeps its look.
- Features stay at least 4 blocks from any player block.
- Every player block a layer changes is recorded with its position, action
  (`carve`, `move`, `pool`) and reason, plus `loses_data` for containers, signs
  and the like. The list gets a token (`built-…`, a digest of the exact list);
  writing the phases requires `--approve-built TOKEN`, given after the user's
  yes. A changed design yields a new list and token. This replaces the first
  version's refusal to cut built blocks, at the user's request.

### Emission

`emit_cave` projects the layers in order — carve, move, dress, pools, lights — tile
by tile through the terrain emitter's checks (liquid drain/overwrite, buried
liquid, spills into openings, water/lava contact, gravity) and writes:
`phases/NN-<element>-{carve,dress,pool,light}-k.json` (via `placer`,
rollback `backup`), the features commands phase (via `commands`, rollback
`backup`), `terrain/<element>.plan-rows.toon` (phases, notes and quality
rows), previews (plan and section PNGs) and a report.

### Verification

A new `cave{file}` quality row: take a fresh exact read of the cave box and
run `terrain.py cave-check` against the design. It passes when ceilings vary
(standard deviation and longest flat run), no unsupported span exceeds
`max_span`, every standable floor cell has block light ≥ `min` (unless the
design is dark), and the roof keeps `roof` blocks outside shafts.

### Skill

`skills/terrain-cave/SKILL.md` and `reference/caves.md` rewritten for Ashlar:
survey (an exact site read deep enough for the cave and up through the
surface), design, `terrain.py cave --preview`, the approval with previews
and the report, `exec-ashlar build`, and verification. Cave mouths are
offered to `terrain-integrate` like any other footprint.

## Left to the builder

Exact palettes per style, noise octaves, feature densities and preview
colours; the light-level table for existing emitters in the post-build check.
