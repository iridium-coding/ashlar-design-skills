---
name: system-redstone
description: >-
  Designs redstone contraptions for a Paper server reached through Ashlar
  (item sorters, piston doors, farms, clocks, elevators, note-block music,
  traps), Java-correct and written in their resting state, builds them through
  exec-ashlar, and tests what Ashlar's tools can drive, reporting plainly what
  still needs the user. Use when the user wants a contraption or a working
  machine, or when a design skill hands one off.
model: opus
effort: high
allowed-tools: mcp__ashlar__mc_status mcp__ashlar__mc_players mcp__ashlar__mc_survey mcp__ashlar__mc_render mcp__ashlar__mc_inspect
metadata:
  short-description: Design, build and test redstone machines through Ashlar
---

# system-redstone

## When to use

Use for a contraption or working machine, including a redstone interior handed
off by a design skill. Own the machine design, timing and functional test.
`exec-ashlar` handles the site survey, approved build and live tests.

## Connection

Call `mc_status` to confirm the running Java and Paper version. On failure,
retry once after a few seconds. If it still fails, report the connection error.

## Placement under Ashlar

Ashlar places without physics. Its connection pass sets shapes. Write each
component as it rests before setup, load containers after placement, and name
the event or player action that actually starts the machine. Before choosing
a layout, read `reference/ashlar-redstone.md` first.

## Core principle — design for Java mechanics

**Most redstone tutorials, videos, and wiki content are written for Java
Edition** — and this is a Java world, so they apply directly. Use Java
mechanics deliberately: **quasi-connectivity** (pistons/dispensers/droppers
powered from the block one above), **deterministic redstone-tick timing**, and
**clean 1-redstone-tick observer pulses**. Your central job is to translate
intent into a *correct, version-appropriate* Java design before any block is
placed.

Target Java 26.3 on Paper. Confirm version-sensitive details against the running
version and use the timing table in `reference/java-redstone.md`.

## Process

1. **Preflight.** Check the connection, read `.minecraft-builder/registry.json`
   if present, then use `exec-ashlar survey <project>` for the site.
2. **Interview.** Use `reference/interview.md` to agree on footprint, facing,
   throughput, item types, trigger and who will be in game for manual tests.
   Offer a test input for a lever, button, plate or clock.
3. **Design.** Choose a catalog entry or compose the logic patterns. Draw
   modules in local coordinates and rotate or mirror placements to fit the site
   (`../exec-ashlar/reference/modules.md`). State the timing budget and derive
   comparator thresholds from the item counts and stack sizes.
4. **Check.** Draft the phases, setup commands and placements in `plan.toon`.
   Stamp each placement phase. Where the circuit relies on existing blocks
   or conditional fills need original cell states, capture those cells with
   `ashlar_place.py read` before building. Save the read in the local project,
   record its path in the plan notes and pass it to `check` with `--background`.
   Run `redstone_rest.py check`, fix mismatches and structural errors, and
   re-run. A block the checker does not know is listed as unmodelled and
   treated as a non-conductor, so choose power-path blocks the checker knows;
   a mismatch at or next to an unmodelled block is a hand check, never a state
   to write. If the report says `loaded ... cannot settle`, resolve that loop
   before hand-off even if the as-built check exited 0 or 3. Run `check --input`
   with the same background for each input, examine the changes and confirm
   that its signal reaches each intended target. Document every unmodelled
   part and its hand check in the plan notes. Record results in `build-log.md`.
5. **Plan.** Finish `plan.toon` using `../exec-ashlar/reference/plan-format.md`.
   Order phases as site prep, machine blocks, attached parts, then setup in
   a `commands` phase (e.g. filter hopper contents or spawner NBT). Write the
   `tests` table. Name the start input, manual actions, fixtures and limits of
   agent testing in the notes. Re-run the checker if the plan changed.
6. **Build.** Hand the checked plan to `exec-ashlar build <project>` for the
   approval gate, snapshots and build. Supply the saved pre-build read path
   when applicable so the executor can use `--background` for both the built
   plan diff and the loaded-rest plan diff.
7. **Test.** Hand off to `exec-ashlar test <project>` for loaded-baseline reads
   and functional tests. Use `reference/verification.md` for the evidence.
8. **Report.** Give the four verdicts, remaining manual steps and the chunk or
   player requirements for unattended operation.
9. **On failure.** Use the correction catalog, `check` and `diff` to locate the
   fault. Write a fix phase with only the changed blocks. Return to
   `exec-ashlar build` for a new gate and test again. After three failed fix
   rounds, stop and recommend rollback or redesign.

## Test inputs and fixtures

For a machine started by a lever, button, plate or clock, `system-redstone`
proposes a **test input** at the interview, and the gate shows it if the user
accepts. It is a hopper the agent loads with `item replace block`, emptying into
a sink barrel, read by a comparator. The comparator's signal (boosted by a
repeater where needed) joins the machine's input line through a diode, so the
lever and the test input cannot feed back into each other. The signal holds for
about 0.4 s per item (a hopper moves one item per 8 game ticks), up to 5 × 64
items. It is hidden where a player will not use it by accident, for example
under the floor. With it, the agent can run the machine's tests itself; the
user still flips the real input once (a `manual` step).

**Pulse counter** (optional, for clocks): the clock fires a dropper that moves
one item per pulse into a hopper and a chest. The agent loads the dropper, reads
the chest twice with a known wall-clock gap, and estimates the period. The
estimate is approximate because of server lag and read latency.

Test inputs and fixtures are part of the design. They go through the checker,
the gate and the snapshots like any other blocks, and the plan notes list them,
so a later reader knows what they are.

## Scripts

Run from the workspace root containing `.minecraft-builder/`, with Python
3.11 or newer. For an older system Python, use
`uv run --no-project --python 3.11 python <script> ...`.

- Claude Code: `<skill>` is `${CLAUDE_SKILL_DIR}`.
- Codex: `<skill>` is the folder holding this `SKILL.md`.
- Otherwise: `<skill>` is the folder holding this `SKILL.md`.

```text
python3 <skill>/../exec-ashlar/scripts/stamp.py --placements <plan.toon> --modules <modules-dir> --phase <number> --out <phase.json>
python3 <skill>/../exec-ashlar/scripts/ashlar_place.py read X1 Y1 Z1 X2 Y2 Z2 --out <read.json> --world <world>
python3 <skill>/scripts/redstone_rest.py check <plan.toon> [--input X Y Z]... [--background <pre-build-read.json>]
python3 <skill>/scripts/redstone_rest.py diff <plan.toon> <read.json> [--loaded] [--background <pre-build-read.json>]
python3 <skill>/scripts/redstone_rest.py diff <read-a.json> <read-b.json>
python3 <skill>/scripts/redstone_rest.py containers <plan.toon>
```

## Reference library

| File | When to use it |
| --- | --- |
| [ashlar-redstone.md](reference/ashlar-redstone.md) | **Read first.** Placement, resting states, starting and chunk ticking |
| [java-redstone.md](reference/java-redstone.md) | Java mechanics, timing, comparator formula and Paper settings |
| [design-patterns.md](reference/design-patterns.md) | Gates, edges, memory, clocks and signal transmission |
| [contraptions-farms.md](reference/contraptions-farms.md) | Sorters, farms, throughput and loading containers |
| [contraptions-mechanisms.md](reference/contraptions-mechanisms.md) | Doors, transport, note blocks and other machines |
| [interview.md](reference/interview.md) | Requirements and optional test inputs |
| [checker.md](reference/checker.md) | Commands, inputs, reports, exit codes and model limits |
| [verification.md](reference/verification.md) | Test contracts, verdicts and corrections |
| [community-sources.md](reference/community-sources.md) | Finding version-appropriate Java designs |
| [setblock-redstone-limits.md](reference/setblock-redstone-limits.md) | Superseded placement reference |

## Hard rules

- Java-correct: quasi-connectivity, deterministic timing, clean observer
  pulses. No 0-tick tricks, duping or headless pistons.
- Every redstone component is written at rest. Hand off to `exec-ashlar build`
  only after `redstone_rest.py check` is clean for as-built modelled parts,
  the loaded baseline settles, and every unmodelled part is checked by hand
  and noted.
- Never call a machine working without a passed functional test. When Ashlar
  cannot drive a machine, say "needs your test" and give the exact steps.
- All world changes go through `exec-ashlar`. Console commands only as
  `../exec-ashlar/reference/commands.md` allows; never command blocks or `Command`
  NBT.
- Contraptions run on vanilla redstone. Console commands are only for setup
  and verification.
- Derive container-read item counts from the comparator formula; never quote a
  fixed number.
- Village mechanics belong to `design-village`. A façade or enclosure belongs to
  `design-building`, `design-house` or `design-city`.
- AFK farms: confirm the server permits them.

## Tracking progress

- Claude Code: track the phases with your task or todo tool.
- Codex: track the phases with `update_plan` when available.
- Otherwise: keep a checklist in `build-log.md`.

## Report

Give the footprint, facing, expected throughput and materials. Report `built`,
`at_rest`, `agent_tested` and `manual` individually with the corresponding
observations from `build-log.md`. Use `pass`, `fail`, `pending` or `n/a` as
defined in `reference/verification.md`. Call it working only when a functional
test passed and every applicable verdict passed. When a manual test is pending,
give its exact control, coordinates, action and expected result. Return those
results to the requesting design skill and identify any village or enclosure
hand-off.
