# Ashlar tools and limits

Written for Ashlar 0.4.9 (plugin and `ashlar-mcp`) on Paper 26.3. When
`mc_status` reports a newer plugin version, re-check these limits against
Ashlar's README before relying on them.

## The nine tools

| Tool | Use it for | Writes? |
| --- | --- | --- |
| `mc_status` | Connection, plugin and server versions, build queue length | no |
| `mc_players` | Online players: world, block position, facing, the block in front, the block they look at | no |
| `mc_survey` | Surface heights over an x/z area: a heightmap image plus min/max/median height, surface materials and the largest flat zone; `matrix: true` adds per-block heights | no |
| `mc_render` | PNG views: `top`, `north`/`south`/`east`/`west` facades, `slice`, `heightmap` | no |
| `mc_inspect` | Exact blocks: `stats` (counts), `columns` (bottom-to-top runs per column), or an ASCII `slice` | no |
| `mc_snapshot` | `create` a restore point for a box, or `list` stored snapshots | stores a snapshot |
| `mc_restore` | Put a snapshot's box back exactly as captured | yes |
| `mc_build` | `fills` (modes `replace`, `keep`, `outline`, `hollow`, `walls`; optional `filter`), `blocks` (with optional `sign` text), `text` (lettering) | yes |
| `mc_command` | One console command with full operator rights; only the forms in `commands.md` | depends |

## Limits

Ashlar's defaults. A server can change them, and a call over a limit is
rejected before anything changes: split and retry rather than guess.

| Limit | Default |
| --- | --- |
| Blocks per `mc_build` call | 500,000 |
| Chunk footprint per write call | 1,024 chunks (a 512 × 512 area) |
| Cells per `mc_inspect` call and per side/slice `mc_render` | 200,000 |
| Area per `mc_survey` call and per top/heightmap `mc_render` | 200,000 x/z cells |
| Columns per `mc_inspect` `format: "columns"` call | 1,024 (also the unit of a column backup's reads: at most 1,024 columns and 200,000 cells per call, fewer columns when the box is taller than 195 blocks) |
| Distinct block types in an `mc_inspect` ASCII slice | 47 (narrow the region if a slice has more) |
| Flowing liquids per call (`liquids: "flow"`) | 2,000; the placer pages so no page holds more than 2,000 water or lava cells (`--max-flowing`) |
| `fillbiome` blocks per command (vanilla) | 32,768 by default; the command's error says if the server differs |
| Queued operations | 16 |
| Snapshots kept | 20, oldest evicted first, shared by everything on the server |
| Cells per snapshot | 200,000 |
| World height (overworld) | y −64 to 319 |
| Worlds | only those in the plugin's `world.allowed-worlds` |

## Behaviour to plan around

- The heights file's source is `mc_survey` with `matrix: true`, read for
  `SOLID`, `SOLID_OR_LIQUID_NO_LEAVES` and `ANY` in tiles of at most 200,000
  cells. A column backup's source is `mc_inspect` `columns`.
- `mc_build` runs, in order: the snapshot (if `snapshot: true`), all fills, all
  text, then all blocks. If the snapshot box exceeds the snapshot cap, the
  whole call fails before writing.
- Blocks are written with physics off: sand does not fall, water and lava stay
  put (unless `liquids: "flow"`), and redstone does not update.
- A connection pass afterwards joins fences, panes, walls, bars, stairs and
  redstone wire to their neighbours.
- Attached blocks without support (torches, ladders, signs, doors, carpets…)
  come back under `WARNINGS`; fix them before calling a phase done.
- Fill modes: `replace` (default) overwrites everything; `keep` fills only air;
  `outline` places the 1-block shell on all six faces; `hollow` places that
  shell and clears the inside; `walls` places only the four vertical sides (a
  1-high `walls` fill is a ring) and leaves the inside untouched, so clear
  natural terrain inside with an air fill first. `filter` restricts a fill to
  cells matching a block state (`filter: "minecraft:air"` builds only into empty
  space; unspecified properties are wildcards).
- Snapshots do not keep sign text, container contents or entities. A restore
  empties signs and containers in its box, including ones that were there
  before the build.
- `mc_render` shows blocks, not entities, and map colours are approximate.
- `mc_render` and `mc_survey` return images you can look at directly.
- At most 16 operations queue at once. Parallel calls beyond that fail with
  "operation queue is full": send reads in batches of at most 12, or read a
  slice or a `columns` listing instead of many single cells.

## Block-state orientation

From `mc_build`'s own rules:

- Attached blocks (ladder, wall torch, wall sign, wall banner, wall-mounted
  lever or button): `facing` points away from the supporting block. A ladder on
  a room's west wall is `ladder[facing=east]`.
- Doors: the panel sits flush with the face opposite `facing`. Place
  `half=lower` at y and `half=upper` at y+1 with the same other properties;
  `hinge` chooses the swing side.
- Stairs: the tall half is on the `facing` side; `half=top` is upside down.
- Beds: `part=foot` at the position, `part=head` one block toward `facing`.
- Chests and furnaces: `facing` is the side the front is on. Adjacent chests
  with the same facing pair automatically; write `type=single`.
- Slabs: `type=bottom|top|double`.
- Torches: `torch` stands on the block below; on a wall use
  `wall_torch[facing=<away from the wall>]` in the air block beside it.
- Signs: put the text in the `sign` object of a `blocks` entry (`front`/`back`,
  up to 4 lines of 64 characters, `color`, `glowing`, `waxed`), in the air
  block in front of the wall for wall signs. `sign` is
  `{"front": ["line 1", "line 2"], "back": [...], "color": "black",
  "glowing": false, "waxed": true}`: `front`/`back` are arrays of up to 4
  strings, `color`, `glowing` and `waxed` apply to the whole sign, and the
  entry's block must be a sign.
- Leaves that must not decay: `persistent=true`.
