# Rung 4: controllable clock

## Prompt

Draft; the user may edit.

> Build a redstone clock I can switch on and off with a lever, pulsing about once
> every two seconds.

## Site constraints

None for the base run: a scratch site away from players and other builds,
chosen by the agent or named by the runner, with no facing required.

## Test quantities

Target period: about two seconds. Pulse count: at least 30 pulses.

## Pass criteria

Ashlar only, as in [rung 1](01-sorter.md). Off: at rest, and `check` settles.
With `check --input` on the switch, it reports "cannot settle" for the clock
loop, as expected for an oscillator. On (by the user, or by a test input):
the output changes across repeated reads. With a pulse counter, the period is
within 10% of the target over at least 30 pulses. Switched off, it returns to
rest within one period, and the `rest` check is clean.

## Who tests what

The user's switch, or the agent with a test input and pulse counter if accepted.

## Variants

Once the rung passes, run the variants in the Variants section of
[README.md](README.md): orientation, footprint, recovery A and recovery B.

- **Footprint (draft):** the same prompt with the machine confined to within
  3 × 3 × 2 blocks.
