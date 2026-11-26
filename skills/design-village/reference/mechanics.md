# Java Edition village mechanics

The functional contract. A village that ignores these looks fine and does not
work. All values are **Java Edition** (the version `mc_status` reports) —
re-check after a
game update. The Minecraft Wiki pages for Village mechanics, Iron Golem, Bell,
Villager, Raid, and Cat are the source of truth.

## What makes a village

In Java Edition a village has no fixed center or radius. Every chunk section
(16×16×16) that holds a claimed **bed**, **job-site block** or **bell** counts
as a village center, and the 3×3×3 sections around it are village. Raids,
zombie sieges, cat spawning and golem patrols use those sections. The **bell**
is not required to form a village, but villagers gather and gossip at it, and
gossip is how a village summons iron golems; it also carries the raid warning.
Always include one.

## Villagers, beds, and workstations

### Bed claiming

- A villager claims an **unclaimed bed** it can pathfind to. The **pillow block
  needs 2 air blocks above it**; a slab, trapdoor, or any solid block over
  the pillow prevents the claim.
- A villager that cannot reach its bed unlinks from it with anger particles.
  A villager that has not slept in the last 20 minutes cannot help summon an
  iron golem.
- One villager per bed. Beds in a fully sealed room the villager cannot enter
  will not be claimed.

### Workstation (job-site block) claiming

- A villager claims an **unclaimed job-site block** within roughly **48 blocks**
  (pathfinding distance, not straight-line) during daytime "seek work" ticks.
  In practice, keep workstations within the same building or immediately
  adjacent to where the villager sleeps.
- **One villager per workstation.** Space workstations at least **2 blocks
  apart** — villagers race-claim the nearest unclaimed site; a cluster of
  workstations in one room may leave some villagers jobless if the distances
  are equal.
- **Profession is set when the villager successfully claims its workstation**
  (green sparkle particles). Do not rely on the spawn-time profession; use the
  spawn-then-claim pattern (see `population.md`).
- A villager loses its profession if its workstation is broken or moved out of
  range while it has not yet traded with the player. After a trade has
  occurred the link is permanent.

### Trading and gossip

- **Trading** unlocks higher-tier trades (1 trade per level: Novice → Master).
- **Gossip** is the Java-specific reputation system: villagers share gossip
  about the player (positive for trading/curing, negative for attacking) and
  this affects prices. Curing a zombie villager grants a major positive gossip,
  dramatically reducing that villager's trade prices.
- Gossiping is also when villagers summon iron golems (below). Harming
  villagers spreads negative gossip about the player, and a low reputation
  turns the village's golems hostile to that player.

## Iron golems

Villagers summon golems; the village itself does not. In this skill,
"iron-golem-ready" is the planning rule of thumb in `layouts.md` (≥10
villagers and ≥20 beds, so the conditions below hold comfortably); the list
below is the vanilla mechanism.

A villager summons a golem while **gossiping** with villagers gathered at the
bell, or every 5 seconds while **panicking** (a zombie in view), when:

1. it has slept in a bed in the last 20 minutes;
2. it has not seen an iron golem within 16 blocks in the last 30 seconds, and
   has not been within 10 blocks of another villager's summoning in that time;
3. enough villagers that meet those conditions are within 10 blocks of it,
   itself included: **5** when gossiping, **3** when panicking;
4. a spawn point is found within 8 blocks horizontally and 6 vertically of it:
   the top air or liquid cell of a column, over a block with a solid top, with
   no full block, rail or redstone power in the golem's three cells and no
   water in the upper two. Slabs, fences and carpets do not stop a spawn.

Practical design rules:
- Plan enough villagers that sleep and gather at the bell to gossip in groups
  of 5; workstations are not part of the check.
- Keep the ground within about 8 blocks of the bell and the gathering area
  open, solid and walkable, so a summoned golem has room to stand.
- Do not build the player's house on the bell or its gathering area.
- For **day-one defense**, spawn one golem manually with the allowlisted
  `summon` command near the bell on a clear surface. Tell the user a
  *naturally respawning* golem still needs the conditions above.

## The bell

- **Claiming** — a bell within 48 blocks of a claimed bed's pillow, with a
  path a villager can walk, is claimed in the afternoon (green particles) and
  becomes the village's gathering site, where villagers mingle and gossip.
- **Ringing** — sends every villager within 32 blocks to the nearest bed
  within 32 blocks. If a raider is within 32 blocks, every raider within 48
  blocks glows for 3 seconds; other hostile mobs are not marked.
- **Raids** — when a raid starts, a villager runs to ring the bell. Place it
  centrally, with every bed within 32 blocks, so one ring reaches everyone.

## Raids

- A player with **Bad Omen** (from drinking an **Ominous Bottle**, which raid
  captains drop) who enters the village sections gets **Raid Omen** instead;
  the raid starts 30 seconds later. Its center is the average position of the
  claimed beds, job sites and bells within 64 blocks of the player.
- Waves: **3 / 5 / 7** on Easy / Normal / Hard, plus a bonus wave when the
  Bad Omen level is above I.
- **Raiders spawn on the top surface outside every village section**, on a
  block mobs can spawn on (not glass), less than 96 blocks above or below the
  center. The game tries far from the center first and moves inward; when
  nothing outside qualifies, waves appear beside the center. **Leave spawnable
  ground outside the walls** — a sealed or glassed-off village pulls waves
  inside. Walls slow ravagers; they do not stop a raid.
- Defeating all waves grants the **Hero of the Village** effect, giving
  discounted trades from all villagers.

## Breeding and willingness

Villagers breed when **willing** — the willingness condition in Java is:

- The villager has enough food in its inventory: **3 bread, 12 carrots, 12
  potatoes, or 12 beetroots** (any combination meeting the internal hunger
  threshold).
- There is at least one **unclaimed bed** (with 2 air blocks above the pillow)
  that the baby can claim.
- The villager is not in a "cooldown" from a recent breeding event.

A **breeding-ready** village design therefore needs:
- A **farmer villager** with a composter who actively harvests and throws food
  to other villagers (the Java food-sharing loop).
- **Spare unclaimed beds** above the current villager count — at least 1 free
  bed per baby slot desired.
- Enough food available in the village (a working crop farm, or the player can
  throw food to villagers to trigger willingness manually).

## Cats

- **Cats** spawn near a player who is in or close to the village, at a spot
  within 48 blocks of at least **4 claimed beds**, while fewer than **5 cats**
  are within a 97×17×97 box around it. Untamed village cats can despawn.
- To seed cats immediately, spawn `minecraft:cat` near the meeting area with
  the allowlisted `summon` command.

## Wandering traders

- A **wandering trader** spawns now and then near a player; if that player is
  within 48 blocks of a bell, it spawns within 48 blocks of the bell instead.
  It brings two trader llamas.
- Leave a few blocks of clearance near the bell and main paths so its llamas
  do not get stuck on fences or doorways.

## Scripted villagers vs. emergent profession assignment

The spawn-then-claim pattern described in `population.md` is the default: the
game assigns a profession organically when a villager claims its workstation.
For **specific traders with fixed trade lists** (a named quest merchant, a
player-economy shop), use the scripted allowlisted `summon` NBT approach documented
in `population.md` instead — the two techniques are complementary, not
exclusive. Most villages mix both: organic workers for atmosphere, scripted
merchants for deliberate player-facing shops.

## Java-specific notes to plan around

- **Pillager outposts** in Java do *not* spawn inside villages the way they
  can on Bedrock — the generation rules prevent overlap. No special outpost
  warning is needed during site selection (unlike Bedrock).
- **Abandoned villages** in Java have cobwebs and zombie villagers, but the
  mechanical rules are the same as a normal village once repaired.
- Villagers climb one block at a time (a full block, slab or stair step) and
  avoid long drops; a 2-block rise on a route stops them. Give every route on
  a slope stairs or slab steps, or grade it in a `site-prep` phase (or with
  `terrain-shape`, if installed).
- **Villager sleeping and golem spawning require loaded chunks.** Keep the
  village inside a player's view distance or a force-loaded ticking area;
  operations on unloaded chunks will fail or not tick.
