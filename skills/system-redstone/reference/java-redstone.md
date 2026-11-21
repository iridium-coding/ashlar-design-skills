# Java redstone fundamentals

Java redstone is deterministic and well-documented, and most tutorials, videos,
and wiki diagrams are written for Java — so they apply directly here. This file
is the reference layer. Target **Java 26.3 on Paper** —
several behaviours are version-sensitive (flagged below); confirm the running
version with `mc_status` and re-check after a game update.

## Java mechanics you can rely on

- **Quasi-connectivity (QC) exists.** A Java piston, dispenser, or dropper is
  powered not only by direct power but also by a power source in the block
  *diagonally up* / "one block above" — the classic QC behaviour. Most Java
  piston-door, BUD, and many flying-machine designs depend on it and work here.
  Use it deliberately; document where a circuit relies on it so verification can
  account for it.
- **Deterministic redstone timing.** Java redstone runs on redstone ticks of 2
  game ticks (0.1 s). Repeater and comparator delays, pulse lengths, and
  observer pulses are reproducible — circuits that depend on exact timing port
  faithfully from Java sources.
- **Observer pulses are a clean 1 redstone tick.** A Java observer emits a
  reliable 1-redstone-tick (2-game-tick) pulse when the block it watches
  changes. Long observer chains are stable — there is no edition-specific drift
  bug to design around. Still pad with repeaters when summing a long worst-case
  path.
- **Repeater locking and comparator subtract/compare modes** behave to the Java
  standard — repeater locking (a powered repeater into the side of another),
  comparator subtraction mode, and comparator measurement of container fullness
  all work as the wiki documents for Java.
- **BUD behaviour is achievable** — either with an observer (the clean modern
  way) or with a QC-driven block-update detector. Prefer the observer.

## Mechanics to NOT rely on — patched out or exploit-grade

Do not design around these; reject and re-design any contraption that needs
them:

- **0-tick tricks.** Avoid update-order-dependent piston tricks and obsolete
  0-tick crop farms. Use an observer-piston harvester for sugar cane.
- **TNT duping / sand-and-gravel duping / rail duping.** These are **bugs /
  exploits**, not supported mechanics; they can be patched at any update and may
  be disabled on a server. Do not recommend duping as part of a reliable design.
  If a user explicitly asks, flag it as an exploit that may break, and offer a
  non-duping equivalent (e.g. a real cobblestone/stone generator + auto-miner
  for bulk blocks).
- **Headless pistons and piston duplication** are disabled by default on
  Paper. Its default redstone implementation is vanilla. If a circuit depends
  on dust update order, confirm the world's `redstone-implementation`.
  [Paper world configuration](https://docs.papermc.io/paper/reference/world-configuration/#misc_redstone-implementation)
  and [global configuration](https://docs.papermc.io/paper/reference/global-configuration/#unsupported-settings_allow-piston-duplication).

## Version-sensitive — verify against the running version

These are real Java mechanics, but their exact figures or availability move
between releases. State the assumption in the design and verify in-world:

- **The Crafter** (auto-crafting block) exists from 1.21 onward — fine on
  26.3. Check its behaviour in a compactor by hand.
- **Bubble-column and elevator speeds**, mob-spawn light thresholds, and
  iron-golem spawn volume are tuned across versions — see the timing table and
  re-check on the running version.
- **Trial spawners / vaults / the Mace** and other recent content shift between
  snapshots; verify availability before designing around them.

## Timing reference (Java)

| Quantity | Java value |
| -------- | ---------- |
| Game tick | 0.05 s (20/s) |
| Redstone tick | 2 game ticks (0.1 s) |
| Repeater delay | 1–4 redstone ticks, selectable (2–8 game ticks) |
| Piston activation | near-instant when directly powered; movement ~1.5 game ticks |
| Observer pulse | a clean 1 redstone tick (2 game ticks) |
| Hopper transfer | 1 item per 8 game ticks (2.5 items/s) |
| Hopper item-collection cooldown | extra 8 game ticks after picking up a dropped item |
| Minecart top speed | 8 m/s straight; faster diagonal |
| Powered-rail flat spacing | ~1 powered rail per 30–38 blocks for an occupied cart; 1–3 in a row launch from rest |
| Note block | 25 pitches (F♯3–F♯5), 16 instruments set by the block underneath |
| Bubble column (soul sand, up) / (magma, down) | soul sand lifts, magma pulls down — verify exact m/s on the running version |
| Hostile-mob light gate | spawns at block-light level 0 (modern Java) — design for full darkness |
| Animal light gate | spawns on grass at light level 9+ |
| Mob-spawn shell | spherical shell ~24–128 blocks from the player; outside 24, inside the simulation distance |

> Flagged for review: the exact bubble-column m/s figures and the modern
> hostile-spawn light threshold (block-light 0 vs the older 0–7 range) are
> version-sensitive — verify on the running world rather than quoting a
> figure blind.

## Comparator fullness

An empty container reads 0. Otherwise its signal equals
`floor(1 + 14 × sum(count / max_stack_size for each stack) / slots)`.
A 5-slot hopper of 64-stack items reads 1 for 1–22 items and 2 starting at
23. A 16-stack item contributes four times as much fullness as a 64-stack
item, and an unstackable item counts as one full slot. A comparator reads a
double chest over 54 slots. A chest obstructed by a conductive block above
reads 0. Keep independent same-facing chest outputs a block apart or use
barrels. [Minecraft Wiki, Redstone Comparator](https://minecraft.wiki/w/Redstone_Comparator#Fullness_of_containers)

## Other Java facts to design around

- **Container setup** uses allowlisted commands in an approved setup phase.
  Read the actual contents with `data get block` during verification.
- **Randomness** — a vanilla dropper selects a random occupied slot. To encode
  different outcomes, distinguish the items downstream, for example by
  comparator strength for stackable and unstackable items in a receiving hopper.
- **Hopper filtering** behaves to the Java standard — comparator-read filter
  hoppers are reliable; design item streams so matching items reach the right
  filter slot.
- **Iron golem spawning** depends on the village (beds, villagers, the spawn
  volume) — that is `design-village`'s job; you build only the farm hardware
  (spawn platform, water funnel, kill chute, hopper collector).
- **Simulation distance** gates which chunks tick and where mob farms spawn.
  Qualifying force-loaded chunks receive random ticks, including crop growth.
  Natural mob spawning still needs a nearby player (within eight chunks).
  Check both player proximity and the actual simulation distance. [Mojang,
  Java 1.21.5 simulation distance changes](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-5)
- **AFK fishing works on Java** (a clock-triggered fishing-rod-use farm). It is
  a valid Java design — but note many servers discourage or patch AFK farms, so
  verify the server permits it before recommending it.
