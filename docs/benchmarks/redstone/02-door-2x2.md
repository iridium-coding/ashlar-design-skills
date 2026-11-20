# Rung 2: 2×2 sticky-piston door

## Prompt

Draft; the user may edit.

> Build a 2×2 sticky-piston door in a wall, opened and closed by a lever beside
> it.

## Site constraints

None for the base run beyond a wall to build into: a scratch site away from
players and other builds, chosen by the agent or named by the runner. The
machine faces whichever way the wall faces.

## Test quantities

Ten guided lever cycles (open, then closed, ten times). No items.

## Pass criteria

1. Ashlar only, as in [rung 1](01-sorter.md).
2. At rest, closed: `check` clean; with `check --input` on the lever, every
   piston that should move does.
3. **Ten guided cycles:** after each flip, the agent reads the door. Open:
   the four doorway cells are air and the pistons are in their open states.
   Closed: the four door blocks are back in place and the pistons are in their
   rest states.
4. After ten cycles, the `rest` check is clean: no door block missing,
   displaced or dropped, and no piston extended without its block.

## Who tests what

The user flips the lever; the agent confirms each state. If the
user accepted a test input, the agent also runs ten cycles itself, but this
rung still needs the user's ten cycles.

## Variants

Once the rung passes, run the variants in the Variants section of
[README.md](README.md): orientation, footprint, recovery A and recovery B.

- **Footprint (draft):** the same prompt with all redstone on one side of the
  wall, within 3 blocks of it.
