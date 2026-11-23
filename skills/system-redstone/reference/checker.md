# Checking a stamped machine

Run the checker offline from the workspace root, using Python 3.11 or newer.
`<skill>` is the folder holding the redstone skill. Supply the path to the
project's `plan.toon`. Stamp its module phases first, with the output filenames
in the plan. Each phase applies its fills before its individual blocks.

```text
python3 <skill>/../exec-ashlar/scripts/stamp.py --placements <plan.toon> --modules <modules-dir> --phase 2 --out <phase.json>
python3 <skill>/scripts/redstone_rest.py check <plan.toon>
python3 <skill>/scripts/redstone_rest.py check <plan.toon> --input 4 65 0 --input 8 64 0 --background <pre-build-read.json>
python3 <skill>/scripts/redstone_rest.py diff <plan.toon> <full-read.json> [--background <pre-build-read.json>]
python3 <skill>/scripts/redstone_rest.py diff <plan.toon> <full-read.json> --loaded [--background <pre-build-read.json>]
python3 <skill>/scripts/redstone_rest.py diff <baseline.json> <after.json>
python3 <skill>/scripts/redstone_rest.py containers <plan.toon>
```

## Checks and reads

- **As built.** With the inputs as written and the containers empty, `check`
  settles Java power and compares the plan's components to that state. It
  checks piston base/head pairs (including facing and type) and observers.
- **Loaded.** The checker applies setup-phase `item replace block` and
  `data merge block` inventory loads and computes the expected resting power.
  Settlement starts from the prior state so a stable latch can hold its value.
- **Input probes.** Each `--input X Y Z` independently switches on the selected
  lever, button or plate, or adds one cobblestone in an empty slot of a
  supported container, from the same loaded baseline. Check which target
  pistons, hoppers, lamps or doors change. An unsettled input run can be
  expected for a running clock. Diagnose any unintended oscillation.
- **Existing surroundings.** Capture the site before building with
  `python3 <skill>/../exec-ashlar/scripts/ashlar_place.py read X1 Y1 Z1 X2 Y2 Z2 --out <pre-build-read.json> --world <world>`.
  Include neighbouring blocks that affect the circuit. With `--background`,
  planned writes overlay the saved site. Otherwise unknown neighbours count as
  air and edge components can produce warnings. Site reads hold block states,
  not inventory contents.
- **Geometry (`diff`).** Supply a full post-build read. The checker compares
  the block ID and written non-power properties at each written cell, ignoring
  the connection pass (wire, pane, fence, wall and bar sides, a wall's `up`,
  stair shape and chest type). For a conditional fill whose result depends on an unknown
  original cell, a plan diff requires `--background` covering that cell.
  A post-build read cannot supply the original state.
- **Loaded rest (`diff --loaded`).** Compares component IDs and power
  properties against the loaded model. If setup cannot settle, the baseline
  is undefined and this command exits 2. Read inventories separately with
  `data get block`.
- **Return to rest.** Use two full reads of the same box. At each cell observed
  in both reads, the diff reports a block ID change if either block has
  modelled power properties. For an unchanged ID it compares only those
  properties. A cell omitted from a partial read is unobserved; a cell read
  as air is an observation. Keep the geometry check alongside it.
- **Inventories.** `containers` prints one `X Y Z minecraft:block_id` line for
  each supported container written by the plan, to identify baseline, settle
  and conservation reads.
- **Lettering.** A phase with server-rendered `text` needs a hand check and
  exits 2. Author the lettering as fills or blocks for complete checker coverage.

## Reading the report

`check` prints a summary of as-built mismatches, structural errors, unsettled
positions and unmodelled parts, then details in these forms:

```text
X Y Z  written <state>  expected <state>  because <reason>
X Y Z  structural  <problem>
X Y Z  cannot settle
X Y Z  unmodelled  <reason>
warning  <message>
loaded  X Y Z  <before> -> <after>
loaded  X Y Z  cannot settle
input X Y Z
  X Y Z  <before> -> <after>
  X Y Z  cannot settle
```

A block the checker does not know is listed as unmodelled and treated as a
non-conductor, so a power path through it can give a wrong expected state.
Build torch supports, repeater and comparator targets and the blocks under and
beside dust from blocks the checker knows. A mismatch that ends with
`(next to unmodelled X Y Z; check by hand)` may come from that assumption:
check it by hand or swap the block, and never write the suggested state
blindly.

A loaded circuit that cannot settle skips input probes. Read these lines even
on exit 0. A clean as-built circuit can still oscillate after setup. Warnings
also identify unknown item stack sizes assumed to be 64. Verify the actual
stack size before trusting a comparator threshold. `diff` lists differences as
`X Y Z  <before> -> <after>`, with `not read` for a missing plan position.

| Exit | Meaning |
| --- | --- |
| 0 | Clean as-built check, no diff, or a successful container listing. Inspect loaded and input results separately. |
| 1 | As-built mismatch, structural error or as-built circuit that cannot settle, or a diff found differences. |
| 2 | Invalid input or unavailable baseline, including conditional fills without the necessary pre-build data, unstamped/missing phase files, or server-rendered text requiring a hand check. |
| 3 | As-built check is otherwise clean but lists unmodelled parts. Check each by hand and document it in the plan notes. |

## What it does not model

Timing and pulse lengths, delay-dependent order, piston movement and block
pushing, update order and BUD states, observers firing, entities, randomness,
scheduled ticks, comparators reading non-containers (cake, cauldrons, item
frames and the like), sculk, copper bulbs, crafters, rails, tripwire, daylight
detectors, target blocks and lecterns. Any of these next to the modelled circuit
is listed as "check by hand", never guessed.

Record timing and other design assumptions even when the checker cannot
detect them from block IDs. Live Rung 0 on Ashlar 0.4.9 and Paper 26.3 build
257 confirmed the checker's two isolated-wire cases. The wire with omitted
sides became a dot, and the explicit four-sided wire kept its cross. Give
the dust a real connection where lateral power matters.

The loaded simulation assumes an inventory change reaches the comparator.
In that run, loading 23 items into the locked hopper succeeded, and its
comparator stayed at 0. Use the actual inventory and output readback as
evidence. The offline prediction for a settled circuit is still 2.
