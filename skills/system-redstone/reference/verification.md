# Verification and correction

Write functional tests in the project's `plan.toon`. Name each input, its
coordinates, the observable result and a timeout based on the timing budget.
Hand off the approved plan to `exec-ashlar build <project>` and then
`exec-ashlar test <project>`. Record readings and verdicts in `build-log.md`.

## Authoring the tests table

Each row has a test name, consecutive step number, kind, position or box,
detail and expectation. For example, this test drives a pre-built sorter
with a small batch and checks that it returned to rest:

```toon
tests[5]{test,step,kind,at,detail,expect}:
  cobble,1,load,4 65 0,"item replace block 4 65 0 container.0 with minecraft:cobblestone 12",-
  cobble,2,settle,0 60 0 8 66 4,containers,timeout 30
  cobble,3,expect,8 61 4,container,gained minecraft:cobblestone=12
  cobble,4,conserve,0 60 0 8 66 4,containers,-
  cobble,5,rest,0 60 0 8 66 4,blocks,baseline
```

- **Baseline.** Start each test with settled container contents and a full
  read of the machine at loaded rest. Internal containers, excluding this
  test's inputs and receiving outputs, must hold the planned setup contents.
  If a failed test leaves items in transit, stop and report the affected
  containers. The user can clear stray items in game or choose rollback.
  Snapshots restore block states only. Report any inventory the user needs to
  recover or reload.
- **Drive.** Use a `load` targeting an available container slot. Only approved
  `item replace block` or `data merge block` inventory loads may drive a test.
  For a physical control or player observation, write a `manual` row with its
  coordinates, an exact instruction in quotes and `-` for the expectation.
  A test with any manual row is a manual test.
- **Wait.** A `settle` row reads `containers` or `blocks` in a box until two
  consecutive reads agree, within `timeout <seconds>`. An `await` row polls a
  condition, e.g. `minecraft:sugar_cane>=8 within 3600` at the output.
- **Inspect.** An `expect` checks `block` properties in a cell or box, or
  `container` contents as an exact `holds` or `gained` list. Join counts
  with a pipe, e.g. `holds minecraft:cobblestone=41|minecraft:stick=4`.
  Derive those counts for the actual slice and use distinct filler that cannot
  arrive in the item stream. `conserve` accounts for every item across the
  box against baseline plus loads, including unintended destinations.
  `rest` compares component power properties to this test's baseline.
- **Repeat.** For repeated trials, use `repeat,-,steps <first>-<last>,<count>`
  and record each cycle. Use separate tests when the agent can exercise a
  fixture independently of the user's real control.

Confirm that the full read covers the planned cells, the test box covers the
whole route, and every load appears in the approval gate. See the
[plan format](../../exec-ashlar/reference/plan-format.md) and
[execution procedure](../../exec-ashlar/reference/execution.md).

## Per-type test contracts

| Machine | Agent can check | Needs the user |
| --- | --- | --- |
| Door | Drive the accepted hopper input, read every doorway cell open, then verify the closed blocks and return to baseline. Repeat the agreed cycles. | Operate the actual lever, button or plate. Without the fixture, guide each open/close cycle and read both positions. |
| Sorter | Feed target and unmatched items. Check gains in each output and overflow, exact filter contents, conservation and rest after each batch. | Player-facing loading access when requested. |
| Crop farm | Await harvest in the collection chest with the chunks ticking. Check crop support, collection, piston rest and continued growth. Allow for random ticks. | Any required planting, harvesting or actual player control specified by the design. |
| Mob farm | Compare collected drops to the baseline over a measured interval. | Stand at the AFK spot for natural spawning or within the spawner's activation range. Confirm the expected mob and rate. |
| Clock | Drive an accepted enable fixture. Load a dropper counter, measure collected items over a known interval, then verify it stops and stays at rest. | Operate the real switch. Observe pulse order or precise timing if the fixture cannot resolve it. |
| Minecart | Read rail states, switch positions and the terminal positions of the build's tagged test entities. | Ride the route, report detector order, elapsed time and any stall. Clear rail obstructions by hand. |
| Elevator | Check shaft continuity, source blocks and arrival of the build's tagged test entity where applicable. | Ride the elevator to verify direction, travel time and usable entry and exit. |
| Note-block music | Check instrument supports, pitches, repeater delays and final states. | Trigger and listen for sequence, pitch and tempo. Static samples can miss short pulses. |

Sugar cane needs 16 random ticks for a new block, averaging about 18 minutes
at default Java rates. Size the crop test's sample and timeout accordingly.
[Minecraft Wiki, sugar cane farming](https://minecraft.wiki/w/Sugar_Cane#Farming)

## Four verdicts

| Verdict | Evidence required for a pass |
| --- | --- |
| `built` | Acceptance and quality checks pass and `diff` of a full read against the plan finds the right blocks and written non-power properties, excluding connection-pass properties (wire, pane, fence, wall and bar sides, a wall's `up`, stair shape, chest type). |
| `at_rest` | Pre-build checker passed for modelled parts, exceptions were checked by hand, the loaded baseline matches `diff --loaded`, and every `rest` row passed. |
| `agent_tested` | Every agent test passed. Use `n/a` when there is no agent-driven test. |
| `manual` | Every manual test passed. Use `pending` for outstanding actions and `n/a` if there are none. |

Use `fail` for a failed check and `pending` for an outstanding one. Include
all four verdicts and their readings in the hand-off. Call the machine working
only when every applicable verdict passed, including a functional test. If it
needs the user's test, give the exact outstanding step and expected result.

## Correction catalog

| Symptom | Diagnosis and correction |
| --- | --- |
| A component never changes | Check its as-built written state, source and loaded baseline using `check` and `diff`. Correct its resting properties and real input path. |
| Clock never starts | Confirm the chunks tick, the off switch enables the loop and the fixture or user supplied its designed start event. |
| Piston or door corner fails | Check direct power, quasi-connectivity, base/head pairing, clearance, movable blocks and the worst-case timing path. Check actual door blocks separately from piston power. |
| Comparator reads 0 | Check the exact source inventory, rear facing and whether a conductive block above a chest prevents it opening. |
| Outputs are mixed | Adjacent same-facing chests may have paired. Separate them, change facings or use barrels. Also check filter thresholds and signal isolation under backup. |
| Filter skips an item or leaks | Check item identities, stack sizes, all five filter slots and the derived unlock threshold. Inspect input routing and adjacent slices. |
| Hopper fails to pull | Trace stray power that locks it, often from a torch on an adjacent block. |
| Side output of isolated dust never powers | Read the wire's sides. A dot powers only below it. Route a real wire connection to the intended side. |
| A path arrives early or late | Sum repeater delays on both paths and align them. Verify pulse length and motion in the actual orientation. |
| No mob drops | Check light, the player's spawn shell and simulation distance or spawner activation range. Hand village-mechanics failures to `design-village`. |
| Cart stops | Check rail orientation, a sustained power source at each booster and physical obstructions. Have the user clear stray carts or mobs. Re-test with a rider. |

Record the first failing row and its evidence. Re-run the offline checker,
write a fix phase for only the changed blocks, and obtain a fresh gate through
`exec-ashlar build`. Repeat the tests after the correction. Stop after three
failed fix rounds and recommend a rollback or redesign.
