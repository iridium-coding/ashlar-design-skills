# Console commands

`mc_command` runs a command with full operator rights. Use only these forms,
and only for what Ashlar's other tools cannot do. Commands that change the world
must be listed exactly in the approved plan's `commands` table. The read-only
checks may run whenever surveying or verification needs them.
Verification and rollback may run their own position and entity checks and
`kill @e[tag=ashlar.<project>]` without a plan row, each inside its own paired
force-load (below), unless a player is near the site.

## Allowed forms

| Purpose | Form |
| --- | --- |
| Summon an entity (villagers, golems, animals, armor stands, item frames, display entities) | `summon <entity> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}` |
| Set block-entity NBT (styled sign text, banner patterns, lectern books, decorated pots, heads, loot tables) | `data merge block <x> <y> <z> {…}` |
| Change one of the build's entities | `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}` |
| Put an item in a container slot | `item replace block <x> <y> <z> container.<n> with <item>[<components>] [count]` |
| Grow a tree or other feature | `place feature <feature> <x> <y> <z>` |
| Remove the build's entities | `kill @e[tag=ashlar.<project>…]` |
| Keep chunks loaded for position and entity commands | `forceload add <x1> <z1> [<x2> <z2>]` |
| Release those chunks | `forceload remove <x1> <z1> [<x2> <z2>]` |

Read-only checks:

| Purpose | Form |
| --- | --- |
| Test the biome at a position | `execute if biome <x> <y> <z> <biome>` |
| Read block-entity NBT | `data get block <x> <y> <z> [path]` |
| Read one of the build's entities | `data get entity @e[tag=ashlar.<project>,…,limit=1] [path]` |
| Count the build's entities | `execute if entity @e[tag=ashlar.<project>,…]` |
| List the chunks already force-loaded (main world) | `forceload query` |

## Rules

- Never `fill`, `setblock`, `clone`, `give`, `tp`, `gamerule`, `function`,
  `schedule` or any other command, and never use a console command to get
  around one of Ashlar's limits.
- Never summon command-block minecarts or any entity or block that runs
  commands, and never set `Command` (or `auto`) NBT: those run with operator
  rights.
- Run every console command with the `minecraft:` namespace
  (`minecraft:summon ...`, `minecraft:kill ...`, `minecraft:forceload ...`), so
  a server plugin that registers the same command name cannot take it over (on
  one server a plugin answered an unprefixed `kill`). Plan rows may omit the
  prefix; the approval gate shows each command as it will run, with the prefix.
- Each command is one line. Design-skill examples sometimes wrap long SNBT over
  several lines for reading; join them into one line, keeping every character,
  before listing or running them.
- Every summoned entity carries the tags `ashlar` and `ashlar.<project>`. An
  entity you will read back or change later also gets its own tag, such as
  `ashlar.<project>.farmer1`, so selectors can target it without a position:
  `@e[tag=ashlar.<project>,tag=ashlar.<project>.farmer1,limit=1]`.
- Every selector in `data merge entity`, `data get entity`, `execute if entity`
  and `kill` includes `tag=ashlar.<project>`.
- Every console command that names a position or an entity (`summon`,
  `data merge block`, `data get block`, `item replace block`, `place feature`,
  `execute if biome`, `data merge entity`, `data get entity`,
  `execute if entity`, `kill`) only works in chunks the server keeps loaded,
  which normally needs a player nearby. Far from players, `data get block`
  answers "That position is not loaded"; `summon` succeeds, but
  `execute if entity` cannot see the entity until the chunk is force-loaded.
  Ashlar's own reads and writes do not load chunks for console commands. So
  wrap these commands in `forceload add` over the columns they touch (the
  phase's box, or the position) and `forceload remove` of exactly the same
  columns straight after. Coordinates are block x and z; the command covers
  every chunk containing them, at most 256 chunks per command. The survey's
  biome test is the one exception (`survey.md`).
- Never leave a chunk force-loaded. Every `forceload add` has a matching
  `forceload remove` in the same phase or mode; if a phase stops part way, run
  the remove before reporting.
- Before a `forceload add`, run `forceload query`. If it lists chunks inside
  the area, the server owner already keeps them loaded: leave them out of both
  the add and the remove, and force-load the other chunks one at a time
  (`forceload add <x> <z>` and later `forceload remove <x> <z>`, with any block
  column inside each chunk).
  The query is a read-only check the builder runs itself; do not add it to the
  plan's `commands` table.
- Console commands act in the server's main world (normally `world`, the
  overworld). Use them only when the plan's world is that world. For a plan in
  another world, say at the approval gate that its console steps (entities,
  block-entity NBT, `place feature`, force-loads) would otherwise land in the
  main world, and ask whether to run each one as
  `execute in <dimension> run <command>` (for example `minecraft:the_nether`).
  Without a yes, skip those steps and tell the user what is missing. For an
  `execute in` plan, run `forceload query` and the force-load pair in that
  dimension too (`execute in <dimension> run forceload ...`).
- A `Test failed`, "No entity was found" or "That position is not loaded" from
  a chunk that is not force-loaded and has no player nearby proves nothing: the
  chunk may just be unloaded. Repeat the check inside a force-load.
- `place feature` changes blocks: keep it inside a snapshotted box.
- Write commands without a leading `/`.
- Snapshots do not capture entities or block-entity contents: rollback removes
  entities with `kill` and cannot bring NBT back (`execution.md`).
- In `plan.toon`, wrap each command in double quotes and escape its inner double
  quotes as `\"`, because commands contain commas (see `plan-format.md`).

## Examples

```text
forceload add 112 -344 128 -328
summon minecraft:villager 121 65 -333 {VillagerData:{profession:"minecraft:none",level:1,type:"minecraft:plains"},Tags:["ashlar","ashlar.oakhollow","ashlar.oakhollow.farmer1"]}
data merge block 107 66 -357 {patterns:[{color:"red",pattern:"minecraft:stripe_center"}]}
item replace block 110 64 -352 container.0 with minecraft:iron_sword 1
data merge block 110 64 -351 {LootTable:"minecraft:chests/village/village_weaponsmith"}
place feature minecraft:oak 130 64 -345
execute if entity @e[tag=ashlar.oakhollow,type=minecraft:villager]
kill @e[tag=ashlar.oakhollow]
forceload remove 112 -344 128 -328
```
