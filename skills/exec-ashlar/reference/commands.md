# Console commands

`mc_command` runs a command with full operator rights. Use only these forms,
and only for what Ashlar's other tools cannot do. Commands that change the world
must be listed exactly in the approved plan's `commands` table. The read-only
checks may run whenever surveying or verification needs them, and rollback mode
runs `kill @e[tag=ashlar.<project>]` without a plan row.

## Allowed forms

| Purpose | Form |
| --- | --- |
| Summon an entity (villagers, golems, animals, armor stands, item frames, display entities) | `summon <entity> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}` |
| Set block-entity NBT (styled sign text, banner patterns, lectern books, decorated pots, heads, loot tables) | `data merge block <x> <y> <z> {…}` |
| Change one of the build's entities | `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}` |
| Put an item in a container slot | `item replace block <x> <y> <z> container.<n> with <item>[<components>] [count]` |
| Grow a tree or other feature | `place feature <feature> <x> <y> <z>` |
| Remove the build's entities | `kill @e[tag=ashlar.<project>…]` |

Read-only checks:

| Purpose | Form |
| --- | --- |
| Test the biome at a position | `execute if biome <x> <y> <z> <biome>` |
| Read block-entity NBT | `data get block <x> <y> <z> [path]` |
| Read one of the build's entities | `data get entity @e[tag=ashlar.<project>,…,limit=1] [path]` |
| Count the build's entities | `execute if entity @e[tag=ashlar.<project>,…]` |

## Rules

- Never `fill`, `setblock`, `clone`, `give`, `tp`, `gamerule`, `function`,
  `schedule` or any other command, and never use a console command to get
  around one of Ashlar's limits.
- Every summoned entity carries the tags `ashlar` and `ashlar.<project>`. An
  entity you will read back or change later also gets its own tag, such as
  `ashlar.<project>.farmer1`, so selectors can target it without a position:
  `@e[tag=ashlar.<project>,tag=ashlar.<project>.farmer1,limit=1]`.
- Every selector in `data merge entity`, `data get entity`, `execute if entity`
  and `kill` includes `tag=ashlar.<project>`.
- `place feature` changes blocks: keep it inside a snapshotted box.
- Write commands without a leading `/`.
- Snapshots do not capture entities or block-entity contents: rollback removes
  entities with `kill` and cannot bring NBT back (`execution.md`).
- In `plan.toon`, wrap each command in double quotes and escape its inner double
  quotes as `\"`, because commands contain commas (see `plan-format.md`).

## Examples

```text
summon minecraft:villager 121 65 -333 {VillagerData:{profession:"minecraft:farmer",level:1,type:"minecraft:plains"},Tags:["ashlar","ashlar.oakhollow","ashlar.oakhollow.farmer1"]}
data merge block 107 66 -357 {patterns:[{color:"red",pattern:"minecraft:stripe_center"}]}
item replace block 110 64 -352 container.0 with minecraft:iron_sword 1
data merge block 110 64 -351 {LootTable:"minecraft:chests/village/village_weaponsmith"}
place feature minecraft:oak 130 64 -345
execute if entity @e[tag=ashlar.oakhollow,type=minecraft:villager]
kill @e[tag=ashlar.oakhollow]
```
