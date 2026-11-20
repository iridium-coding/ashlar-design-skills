# Rung 5: 3×3 piston door

## Prompt

Draft; the user may edit.

> Build a 3×3 piston door, flush with the wall when closed, opened and closed by
> a lever.

## Site constraints

None for the base run beyond a wall to build into: a scratch site away from
players and other builds, chosen by the agent or named by the runner. The
machine faces whichever way the wall faces.

## Test quantities

Ten guided lever cycles (open, then closed, ten times). No items.

## Pass criteria

As in [rung 2](02-door-2x2.md), with all nine doorway cells clear when open
and all nine blocks back when closed, over ten cycles. The plan notes say
whether the design depends on update order.

## Who tests what

As in [rung 2](02-door-2x2.md): the user flips the lever; the agent confirms each
state, and the user's ten cycles are still required.

## Variants

Once the rung passes, run the variants in the Variants section of
[README.md](README.md): orientation, footprint, recovery A and recovery B.

- **Footprint (draft):** the same prompt with all wiring below the floor, at
  most 4 blocks deep.
