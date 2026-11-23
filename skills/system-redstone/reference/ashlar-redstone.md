# Ashlar placement rules for redstone

**Placement without physics.** Redstone does not update, observers do not fire,
pistons do not move, liquids do not flow unless `liquids: "flow"`, and sand
does not fall. The connection pass sets wire, pane, fence, wall, bar and stair
shapes only, never power.

**Resting states.** Every component is written in its resting state: the state
the game would compute for the finished machine with its inputs as built
(normally off) and its containers as Ashlar leaves them (empty). Nothing
corrects a wrong state until a real update reaches it.

| Component | Resting state to write |
| --- | --- |
| `redstone_wire` | `power` = the level its sources give at rest (0 when nothing is on); sides left to Ashlar |
| `redstone_torch`, `redstone_wall_torch` | `lit=true` unless the block it hangs on is powered |
| `repeater` | `powered` = its input at rest; `locked` = a powered repeater or comparator at its side; `delay` per design |
| `comparator` | `powered` = output above 0 at rest; `mode` per design |
| `lever` | `powered` as the design's input stands (normally `false`) |
| buttons, pressure plates | not pressed |
| `observer` | `powered=false` |
| `piston`, `sticky_piston` | `extended` = powered at rest, directly or by quasi-connectivity; an extended piston has its `piston_head` (`type`, `facing`, `short=false`) in front |
| `hopper` | `enabled=false` when powered at rest, otherwise `true` |
| `dropper`, `dispenser` | `triggered` = powered at rest |
| `redstone_lamp` | `lit` = powered at rest |
| doors, trapdoors, fence gates | `powered` = powered at rest; `open` follows it for machine-driven ones |
| `note_block` | `powered` = powered at rest |

Components outside this table are listed by the checker as unmodelled and
checked by hand.

**Containers and setup.** Containers are loaded after their blocks exist, with
`item replace block` (one slot per command) or `data merge block` (`Items`), in
a `commands` phase inside a paired force-load. Write the circuit as it rests
with empty containers. Verify the actual inventory and comparator output
after loading. The checker computes the expected states
(see [checker.md](checker.md)). In the live Rung 0 run on Ashlar 0.4.9 and
Paper 26.3 build 257, the locked hopper held all 23 items but the comparator
and first dust stayed at signal 0. Stop on an unexplained output difference
before relying on the load to drive another test or calling the machine at rest.

**Starting.** A machine driven by game events (items arriving, crops growing,
mobs) starts itself once it is placed at rest and its chunks tick. A machine
driven by a player input (lever, button, plate) or by its own clock needs the
user's hand. A clock is always built with an off switch, written off, so it has
a resting state; a free-running clock cannot be placed at rest, and the checker
reports it.

**No nudges.** Never try to start or reset a circuit by writing a redstone
block, lever or torch with `mc_build` (it changes nothing), and never place
blocks through the console.

**Pistons.** Never write a piston head without its base, or an extended piston
without its head; Paper removes headless pistons. Quasi-connectivity powers a
piston, dropper or dispenser from power at the block above it; note every place
the design relies on it.

**Chests.** Ashlar pairs same-facing chests that sit side by side. Keep
separate outputs apart with a one-block gap, different facings, or barrels. A
comparator reads a whole double chest. A chest with a conductive block above it
cannot open and reads 0.

**Dust shape.** In Rung 0 on Ashlar 0.4.9 and Paper 26.3 build 257, an
isolated wire with sides omitted read back as a dot, and one written with all
four sides kept its cross. The connected wires formed lines and powered the
receiving lamp. Since the stamper omits wire sides, give dust a real
connection where lateral power matters.

**Liquids and plants.** Water next to cane, or water that only has to sit
still, is placed still. A stream that must carry items needs flowing sources
(`liquids: "flow"`, at most 2,000 flowing blocks per call), placed last. Place
soil and water before plants. Physics-off placement does not break an invalid
plant until something updates it, and Ashlar's warnings cover only attached
blocks, so check plant support by hand.

**Orientation and update order.** Prefer designs that do not depend on update
order: no BUD tricks, no same-tick races between pistons. Where a design does
depend on it, say so in the plan notes; the orientation variants test it.

**Chunks.** Redstone, hoppers and growth run only in loaded chunks. Tests hold
a paired force-load (see [execution](../../exec-ashlar/reference/execution.md)). Outside tests a
machine runs only while a player is near, or while the server owner keeps its chunks loaded; report this for any
machine meant to run unattended.

**Paper.** Duping (TNT, rails, carpets) and headless pistons are off by
default; never design around them. If unsure whether the server has changed
`redstone-implementation`, ask the user.

## Facing a module in Java

Use the local, unrotated coordinates. The placement row supplies rotation
and mirror. `pos + facing` is one block in the direction named by `facing`.

| Block | What its facing means |
| --- | --- |
| Repeater or comparator | Input at `pos + facing`, output at `pos − facing`. |
| Observer | Watches `pos + facing`, outputs at `pos − facing`. |
| Piston | Extends into `pos + facing`. |
| Hopper | Pushes into `pos + facing`, horizontally or down. |
| Lever or button | `face=floor` attaches below, `face=ceiling` above, and `face=wall` to `pos − facing`. |
| Redstone torch | A wall torch hangs on `pos − facing`. A standing torch sits on the block below. |
| Door | Write `half=lower` at y and `half=upper` at y+1. |
