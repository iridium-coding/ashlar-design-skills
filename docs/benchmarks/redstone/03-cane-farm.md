# Rung 3: observer sugar cane farm

## Prompt

Draft; the user may edit.

> Build an automatic sugar cane farm that harvests with observers and pistons
> and collects into a chest.

## Site constraints

None for the base run: a scratch site away from players and other builds,
chosen by the agent or named by the runner, with no facing required.

## Test quantities

At least 8 cane in the chest within the test's timeout (about an hour), with the
chunks force-loaded or the user nearby.

## Pass criteria

Ashlar only and at rest, as in [rung 1](01-sorter.md). Then, with the chunks
force-loaded or the user nearby, the chest receives at least 8 cane within the
test's timeout (about an hour). No stalk grows past the cut height. Between
harvests the pistons are retracted, and the `rest` check is clean.

## Who tests what

The agent, during a long `await`.

## Variants

Once the rung passes, run the variants in the Variants section of
[README.md](README.md): orientation, footprint, recovery A and recovery B.

- **Footprint (draft):** the same prompt with the machine confined to within
  7 × 3 blocks of floor.
