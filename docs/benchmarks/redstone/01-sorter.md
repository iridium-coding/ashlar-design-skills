# Rung 1: two-item sorter with overflow

## Prompt

Draft; the user may edit.

> Build a compact item sorter fed from one input chest. Cobblestone goes to one
> chest, oak logs to another, and anything else ends up in an overflow chest.

## Site constraints

None for the base run: a scratch site away from players and other builds,
chosen by the agent or named by the runner, with no facing required.

## Test quantities

Batch 1: 40 cobblestone, 40 oak logs, 20 dirt.
Batch 2: 64 cobblestone, 17 oak logs, 33 dirt. Both are loaded into the input
chest with `item replace block` rows from the approved plan.

## Pass criteria

1. **Ashlar only:** the build log shows every write passed a gate, every
   phase had snapshots, and every console command matched the allowlist and
   was listed in the approved plan.
2. **At rest:** `check` was clean before the build, and the baseline read
   after setup matches the loaded rest state.
3. **Injection:** both batches were loaded only by the plan's `load` rows.
4. **Sorting:** after each batch settles, the cobblestone chest has gained
   exactly that batch's cobblestone, the oak chest exactly its oak logs and
   the overflow chest exactly its dirt, and no other container has gained
   anything. For every item, the totals across the machine changed by exactly
   the batch: no loss and no duplication.
5. **Filters and rest:** each filter hopper holds exactly its loaded filter
   contents after each batch (`holds`), and the `rest` check after each batch
   is clean.
6. **Repeatability:** batch 2 passes the same checks with no manual redstone
   updates or repairs between batches.

## Who tests what

The agent, for everything. Manual: `n/a`.

## Variants

Once the rung passes, run the variants in the Variants section of
[README.md](README.md): orientation, footprint, recovery A and recovery B.

- **Footprint (draft):** the same prompt with the machine confined to within
  6 × 4 × 5 blocks (x × z × y).
