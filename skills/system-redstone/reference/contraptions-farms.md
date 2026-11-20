# Catalog — sorters, collectors, and farms

The production machines. Each entry: what it is, the Java-specific points, and a
footprint hint. Confirm rates and version-sensitive figures against current Java
sources (`community-sources.md`) for anything not standard.

## Item sorters

- **Basic 1-row hopper sorter** — one item type, one output. A comparator
  reads the filter hopper. A torch locks the output hopper until a matching
  item raises the comparator signal. Reserve the first slot for the target,
  and put one 64-stack filler that will never arrive in the stream in each
  of the other four slots. Derive the target count from the circuit's unlock
  strength using `floor(1 + 14 × total / 320)` for 64-stack items in a hopper.
  In the classic overflow-protected tile, 41 target + 4 filler = 45 (signal 2).
  The next item gives 46 (signal 3). Even a backed-up slice caps at 64 + 4
  (signal 3), so it cannot unlock its neighbours. In an isolated slice wired
  for strength 2, the checker's smaller example is 18 target + 4 filler = 22
  (signal 1), then 23 (signal 2). Check adjacent slices under backup before
  tiling this variant. Footprint ~1×5×4 for the basic row.
  [Minecraft Wiki, hopper sorter overflow protection](https://minecraft.wiki/w/Tutorial:Hopper#Overflow_protection)
- **Multi-row universal sorter** — one row per item type, side by side. Space
  filter rows so a neighbouring row's comparator cannot misread; add a 1-block
  isolation gap if rows interfere.
- **Overflow protection** — route unfiltered items to a labelled overflow chest
  (or a lava trash can if loss is intended). For separate output inventories,
  leave a one-block gap between same-facing chests, turn them differently or
  use barrels. Ashlar automatically pairs adjacent, same-facing chests.
- **Compactor** — auto-crafts 9 ingots → a block (or reverses it). On 1.21+ the
  vanilla **`minecraft:crafter`** (auto-crafting block, observer- or
  comparator-triggered) is the clean way; a hopper-into-a-crafter feed is the
  modern Java compactor. Verify the Crafter is available on the running version.

## Mob-spawner collectors

- **Drop-tube collector** — for a dungeon spawner: a dark water-flow platform
  funnels mobs into a 1-wide drop column; fall damage or a chute brings them to
  a hopper floor under the collection chest. Light only *outside* the spawn box.
  Footprint compact, vertical.
- **XP / drops split** — a switchable floor lets the player either collect drops
  via hoppers or take XP and the kill themselves.

## Mob farms

- **General mob farm** — a dark spawning platform within the spherical spawn
  shell (~24–128 blocks from an AFK spot, outside 24 and inside the simulation
  distance); water streams funnel mobs to a kill chute and a hopper collector.
  Rate scales with simulation distance — design to the world's setting. Modern
  Java spawns hostiles at block-light level 0, so the platform must be fully
  dark. Before sizing a farm, check the mob's Java biome, light and
  structure requirements, then observe drops with a player at the AFK spot.
- **Specific spawners** — zombie / skeleton / cave-spider / blaze XP farms off a
  natural spawner; drowned, guardian (ocean monument), witch hut; enderman
  platform in the End; slime-chunk farm.
- **Iron / villager farms** — you build the spawn platform, water funnel, kill
  chute, and hopper collector; **`design-village` builds the village** (beds,
  villagers, the spawn rules that produce iron golems). Hand off the village
  half.

## Crop farms

- **Observer-piston harvester** — an observer watches a crop block; when it
  matures the observer fires a piston that breaks it; water carries the drop to
  a hopper line. The pattern covers sugar cane, bamboo, kelp, cactus,
  pumpkin/melon, sweet berries, nether wart, cocoa. (Use this for sugar cane —
  do **not** rely on patched-out 0-tick harvesting.)
- **Tilled-crop farms** (wheat, carrot, potato, beetroot) — usually a villager
  farmer harvests and a hopper minecart collects; coordinate the villager with
  `design-village`.
- **Tree farms** — observer-piston harvested per species; on Java a dispenser of
  bone meal plus a saw/piston line is a common automatic design.
- **Animal farms** — breeders and cookers (a hopper-fed egg thrower, a lava or
  campfire cooker) for chicken, cow, pig, sheep.

## Auto-processing

- **Auto-smelter** — a furnace bank fed by an input hopper, a separate fuel
  hopper, and an output hopper to a chest. Three furnaces in parallel ≈ 18
  items/min. Furnaces keep smelting XP until the player collects the output — a
  useful XP source. Add overflow protection if input can outpace smelting. Size
  fuel and compost inputs from the running version's burn times and composting
  chances, then measure the actual output.
- **Auto-brewer** — dispenser-fed brewing stands in a chain.

## Ship a farm pre-loaded

Load containers after their blocks exist. For example, these rows of a setup
`commands` phase seed an auto-smelter's fuel hopper:

```toon
commands[3]{phase,seq,command,purpose}:
  4,1,"forceload add 8 3",load setup chunk
  4,2,"item replace block 8 65 3 container.0 with minecraft:coal 64",seed fuel hopper
  4,3,"forceload remove 8 3",release setup chunk
```

Use the same pattern for a bone-meal dispenser or a breeder's feed dropper.
For a spawner-based design, an approved `data merge block` row can set the
mob, spawn count, range and delay bounds to suit the collector. Confirm the
NBT for the running version with `data get block`, and verify merged values or
initial inventory with the same command inside a paired force-load. The
functional test measures what the operating farm delivers.

## Throughput budgeting

A hopper moves 2.5 items/s. If several harvested streams converge on one sorter
row faster than that, the row backs up — run rows in parallel or widen the pipe.
State the expected throughput and check it against the hopper rate in the
design.
