# Rung 0: calibration

A throwaway build, written by the implementer as an ordinary plan (it tests
Ashlar, not the agent's reasoning), placed in a scratch area away from players.
It checks:

| # | Check | Expected | If different |
| --- | --- | --- | --- |
| 1 | Two lone wires, one written with no sides (as stamped modules write them) and one written with all four sides, plus dust with one and two connections, after Ashlar's connection pass | Record which shape each lone wire ends up with (dot or cross); lines point into the block they power | Update the dust rule in spec §5.4 and the checker |
| 2 | A comparator behind a hopper, with dust after it; `item replace block` 23 items into the hopper | The comparator outputs 2 and the dust re-powers | Stop and bring it to the user (see [How results flow back](#how-results-flow-back)) |
| 3 | A hopper chain inside a force-load with nobody within 128 blocks; load 10 items into the top hopper | All 10 reach the chest within about 10 s | Stop and bring it to the user (see [How results flow back](#how-results-flow-back)) |
| 4 | An extended sticky piston with its head, a torch, a repeater and a lamp written in states consistent with their power | They read back unchanged after 60 s | Note what Paper changes |
| 5 | A torch written `lit=false` on an unpowered block (deliberately wrong) | It stays unlit, and `check` flags it | Record it |
| 6 | Two same-facing chests side by side; two barrels side by side | The chests pair, the barrels stay separate | Update the chest rule |
| 7 | A hopper written `enabled=false` under a lit torch, with items above it | It moves nothing | Record it |

Rung 0 writes to the world, so it goes through the gate like any build, and it
is rolled back afterwards.

## Prompt

None. The implementer writes this build as an ordinary plan; no prompt is pasted
into a fresh session.

## Pass criteria

Each check passes when the "Expected" column of the table above holds for that
row. A check whose result differs is not a failure of the run; it is a finding,
and the "If different" column says what happens next. In summary:

1. **Check 1:** the shape each lone wire ends up with (dot or cross) is recorded
   for both the no-sides and the all-four-sides wire, and lines point into the
   block they power. Otherwise, update the dust rule and the checker.
2. **Check 2:** the comparator outputs 2 and the dust re-powers. Otherwise, stop
   and bring it to the user.
3. **Check 3:** all 10 items reach the chest within about 10 s. Otherwise, stop
   and bring it to the user.
4. **Check 4:** the piston, torch, repeater and lamp read back unchanged after
   60 s. Otherwise, note what Paper changes.
5. **Check 5:** the wrong torch stays unlit and `check` flags it. Otherwise,
   record it.
6. **Check 6:** the chests pair and the barrels stay separate. Otherwise, update
   the chest rule.
7. **Check 7:** the disabled hopper moves nothing. Otherwise, record it.

The rung is complete when all seven checks have a recorded result and the build
has been rolled back.

## How results flow back

Rung 0 tests the assumptions in findings 4, 6 and 9 and the dust-shape
rule. It runs after the merge. If a result differs from what the spec
assumes, the implementer updates `ashlar-redstone.md`, the checker and the spec
in a follow-up PR before rung 1. If the result breaks the test protocol (for
example, commands do not update comparators, or hoppers stay idle in
force-loaded chunks with nobody near), stop and bring it to the user before
going on.

Record the run in `.minecraft-builder/benchmarks/redstone-results.md` in the
format given in [README.md](README.md).
