# Designed caves: method and design file

Designed underground space — show caves, cavern halls, ravines, lava tubes and
the surroundings of a cave base — as opposed to the random caves the world
already has. You author the void, then dress and light it. The terrain
toolkit's `terrain.caves` module, run through `terrain.py cave`, turns the
design into checked phases.

## What makes a cave read as designed

- **A route.** An entrance the player finds, a sequence of spaces and a reason
  to keep going: a narrow passage that opens into a hall, a skylight that pulls
  the eye, water at the low point.
- **Sized chambers.** A base hall is wide with a flat floor and 4+ blocks of
  headroom; a scenic cavern is taller than it is wide in places; a passage is
  2–4 blocks across.
- **Varied ceilings.** Domes with bumps, never a flat lid. Chambers get ceiling
  relief by default; spans wider than `limits.max_span` get pillars.
- **A material story.** Rock banded by depth (deepslate kinds below y 0), a
  floor that differs from the walls, ores left showing in the walls, features
  grown where they would grow: dripstone on ceilings, lichen on walls, moss on
  damp floors.

## Design file (`terrain/<element>.cave.json`)

```json
{
  "element": "west-grotto",
  "seed": 11,
  "site": "site",
  "style": "lush",
  "chambers": [{"center": [34, 40, 34], "radii": [16, 8, 13]}],
  "passages": [{"points": [[50, 38, 34], [62, 42, 46], [62, 46, 60]], "radius": [3, 2.5]}],
  "ravines": [{"points": [[8, 20], [22, 30]], "top": 50, "bottom": 30, "width": 5}],
  "shafts": [{"at": [40, 28], "from": 44, "radius": 2}],
  "pillars": [{"at": [30, 36], "radius": 2.5}],
  "pools": [{"at": [34, 33, 34], "level": 34}],
  "roof": 4,
  "lights": {"min": 1},
  "limits": {"max_span": 24}
}
```

All coordinates are world coordinates.

| Key | Meaning |
| --- | --- |
| `element` | kebab-case name for the files |
| `seed` | seed for the shape noise, dressing and feature spots; keep it to edit the same cave later |
| `site` | project-relative exact site read (the survey's column read) |
| `chambers` | `center`, `radii` (x, y, z), optional `floor` (a flat floor level), `roughness` (0–0.6, default 0.25) and `relief` (ceiling bumps in blocks, default a third of the height radius, at least 1.5) |
| `passages` | `points` (x, y, z polyline, at least two), `radius` (start and end), optional `roughness` (default 0.2) |
| `ravines` | `points` (x, z polyline), `top`, `bottom`, `width` (at the top; narrows toward the bottom), optional `roughness` |
| `shafts` | `at` (x, z), `from` (y where the shaft starts), `radius`: carved up through the surface block — the only places the roof may open |
| `pillars` | `at` (x, z), `radius`: rock left standing through every shape |
| `pools` | `at` (a cave cell) and `level`: still water in the connected hollow up to that level |
| `existing` | `at` (an open cell inside a cave that is already there) and `box` (six numbers): the open space connected to `at` inside the box and below the ground surface is adopted as it is — nothing in it is carved |
| `moves` | `from` and `to` (cells): the block at `from` is written at `to` and `from` cleared, before dressing; a door, tall plant or bed moves only with both halves by the same offset |
| `roof` | rock kept between the void and the surface outside shafts, default 4 |
| `style` | `plain`, `dripstone`, `lush` or `deep`: dressing palettes, light block and default features |
| `palette` | optional weighted block maps per role (`wall`, `floor`, `ceiling`, `deep` for every role below y 0) |
| `dress` | `new` (default): repaint only rock touching carved cells, so an adopted cave keeps its look; `all`: the whole cave's rock face; `none` (or `false`) |
| `lights` | `false` for a dark cave, or `block`, `min` (lowest block light on any floor cell, default 1, which stops hostile spawns), `max_count` and `hang` (default a hanging lantern; `false` to never hang one) |
| `features` | optional list of `{id, on, per_100}` (`on`: `wall`, `floor` or `ceiling`; `per_100`: features per 100 cells of that surface) replacing the style's defaults |
| `limits` | `max_span` (24), `ceiling_std` (0.75), `flat_run` (14) for the checks |
| `version` | feature-id list to check against, default `26.3` |

## Styles

| Style | Walls, floor, ceiling | Light | Default features |
| --- | --- | --- | --- |
| `plain` | stone, andesite, tuff; a stone and coarse-dirt floor | shroomlight | glow lichen |
| `dripstone` | dripstone block with stone and tuff | ochre froglight | pointed dripstone on ceilings, dripstone clusters and large dripstone on floors, glow lichen |
| `lush` | moss and stone walls, a moss floor with clay, moss on ceilings | shroomlight | moss and cave vines on ceilings, spore blossoms, moss and clay pools with dripleaves on floors, glow lichen |
| `deep` | deepslate, tuff, smooth basalt, calcite | sea lantern | glow lichen, sparse pointed dripstone |

Dressing repaints only natural rock and soil. Ores, amethyst, obsidian,
bedrock, sand and anything a player built stay as they are. A
gravity block (gravel) goes only where the block below stays solid. Sculk
features and the rooted azalea tree (it grows a tree on the surface above) are
refused.

## What the generator does

1. **Void.** Each shape is roughened with seeded 3-D noise; pillars are removed
   from it. Cells closer than `roof` to the surface are trimmed outside shafts
   (the report counts them). Adopted caves join the void without being carved.
   A shape that reaches the edge of the site read is refused.
2. **Moves, dress, pools, lights.** Moved blocks go to their new places. The
   rock face takes the style's palette by role and depth. Pools fill their
   hollow. Starting from the light already there (a player's lanterns count),
   lights go one at a time over the darkest floor cell: into the natural rock
   above it, else into the rock below it, else as a hanging lantern under a
   built ceiling where two clear cells stay above the floor, until every floor
   cell a mob could stand on reaches `lights.min`. Player blocks count as full
   cubes except known partial shapes (stairs, slabs, fences, doors, lanterns,
   carpets and the like); glass and leaves let light through.
3. **Checks.** The layers are projected in order — carve, dress, pool, light —
   through the same checks as terrain: no drained, spilled, overwritten or cut
   water or lava, no new water/lava contact and no gravity block left over a
   fall-through cell, checked after every phase because a build can pause
   between phases.
4. **Features.** Spaced spots in the open air of each surface, at least 4
   blocks from any player block, become `place feature` commands in a commands
   file, backed up with a reach of 8 blocks sideways and 16 up and down.
5. **Player blocks.** Every player block a layer changes is listed in the
   report's `built` section with its position, the action (`carve`, `move`,
   `pool`) and why, plus `loses_data` for contents or text a block write cannot
   carry. The list has a token; writing the phases needs that token, given after
   the user's yes (`--approve-built TOKEN`).

## Outputs

`terrain.py cave DESIGN --project DIR --first-phase N` writes, in the project:

- `phases/NN-<element>-carve-1.json`, `-dress-1`, `-pool-1`, `-light-1` (tiles
  of 128 × 128 columns; via `placer`, rollback `backup`);
- `terrain/<element>.features.json` (a features commands file; via `commands`,
  rollback `backup`);
- `terrain/<element>.plan-rows.toon` (notes, phase rows and the `cave` quality
  row), `terrain/<element>.cave-report.json`, and previews under
  `terrain/previews/` (`<element>-plan.png`, `-section-x.png`, `-section-z.png`).

`--preview` writes only the previews and the report. Without it, the command
refuses a design whose projected check fails (see below), naming each failing
check, and then refuses to touch player blocks without `--approve-built` and
the report's token. `--standalone` also writes `plan.toon` for a cave that is its own
project.

## Checks after the build

`terrain.py cave-check DESIGN --site POST_BUILD_READ` prints a JSON report and
exits 1 when a check fails:

- **ceiling** (per chamber): the spread of ceiling heights is at least
  `ceiling_std` and no straight run of one ceiling height is longer than
  `flat_run` blocks;
- **span**: no level of the cave is wider than `max_span` between rock;
- **light** (lit caves): every floor cell a mob could stand on, adopted caves
  included, reaches `lights.min`, from every light source in the read, including
  lanterns and torches the user added;
- **roof**: every column outside the shafts keeps `roof` blocks of rock.

The light model loses one level per block through every block that is not a
full cube; treat a marginal result as a reason to look in game.

## Improving a cave that is already there

Adopt it with `existing`: pick an open cell inside it and a box around the part
to work on. The box keeps the adoption from running on through a whole cave
system. Then add what the user wants:

- light only: `lights` and nothing else; the existing lanterns count;
- greenery: a `style` (`lush` for moss, vines, spore blossoms and dripleaf
  pools) or explicit `features`;
- water: `pools` in its hollows;
- more room: chambers or passages that join it;
- moved player blocks: `moves`, with the confirmation above.

The ceiling, span and roof checks apply to carved shapes only; the light check
covers the whole cave.

## A cave that hosts a build

Size the chamber for the build, give it a flat `floor`, and build the base with
its design skill in the same project after the cave phases. Seat the base in the
cave: foundations reach the cave floor, and the floor around them is dressed,
not left as a box carved around the building.
