---
name: exec-ashlar
description: >-
  Surveys Minecraft build sites and builds approved plans on a Paper server
  through the Ashlar MCP tools (mc_status, mc_players, mc_survey, mc_render,
  mc_inspect, mc_snapshot, mc_restore, mc_build, mc_command): site surveys,
  plan validation, an approval gate, snapshots, phased placement (directly or
  through a local placer script for large or generated geometry),
  verification and rollback. Use when a design skill hands off a survey or an
  approved plan, or when the user asks to build, test, verify or roll back a
  planned build through Ashlar.
allowed-tools: mcp__ashlar__mc_status mcp__ashlar__mc_players mcp__ashlar__mc_survey mcp__ashlar__mc_render mcp__ashlar__mc_inspect
metadata:
  short-description: Survey, build, verify and roll back Minecraft builds through Ashlar
---

# exec-ashlar

You run the Ashlar side of a Minecraft build: survey the site, check the plan,
get the user's approval, place the plan in phases under snapshots, verify the
result and record it. The design skill that wrote the plan owns the design;
change nothing about it without asking the user.

## Modes

Run as `<mode> <project>`. Project names are kebab-case
(`[a-z0-9][a-z0-9-]*`) because they become folder names and entity tags.

| Mode | What it does |
| --- | --- |
| `survey <project>` | Survey a site and write `.minecraft-builder/<project>/survey.md` |
| `build <project>` | Validate `plan.toon`, run the approval gate, build, verify, record |
| `verify <project>` | Re-run the acceptance and `quality_contract` checks on a built project |
| `test <project> [<test>…] [--manual]` | Run selected functional tests from the approved plan, with `--manual` for manual tests only |
| `rollback <project>` | Restore the project's snapshots and remove its tagged entities |

## Scripts

`scripts/ashlar_place.py` (the placer) and `scripts/stamp.py` (module
stamping) live in this skill's folder, written `<skill>` below. Run them with
`python3` from the workspace root, where `.minecraft-builder/` lives. They
need Python 3.11 or newer; on an older `python3`, run them as
`uv run --no-project --python 3.11 python <script> ...`.

- Claude Code: `<skill>` is `${CLAUDE_SKILL_DIR}`.
- Codex: `<skill>` is the folder holding this `SKILL.md`.
- Otherwise: `<skill>` is the folder holding this `SKILL.md`.

## Preflight (every mode)

1. Call `mc_status`. If it fails, wait a few seconds and call it once more; if
   it still fails, stop and tell the user. The connection lives in the client's
   MCP settings, not in a skill.
2. Read `.minecraft-builder/registry.json` if it exists
   (`reference/registry.md`).
3. Offer the permission step, once per workspace:
   - Claude Code: the first time this skill runs in a workspace, offer once to
     add `mcp__ashlar__mc_command` to the `ask` list in the workspace's
     `.claude/settings.json` permissions, so every console command needs the
     user's OK; change the settings only on the user's yes.
   - Codex: the first time, tell the user that `mc_command` runs with operator
     rights and that Codex's own approval settings decide whether each call
     needs their OK.
   - Otherwise: tell the user the same.

## survey

Follow `reference/survey.md`, write `survey.md`, and return to the design skill
that asked for it. If `<project>` is already in the registry and the user is
not iterating that same build, stop and ask for another name: a reused name
overwrites the old entry and shares its entity tag.

## build

1. **Validate** `.minecraft-builder/<project>/plan.toon` and every phase file
   against `reference/plan-format.md`. If `<project>` is already in the
   registry and the user is not iterating that same build, stop and ask for
   another name (a reused name overwrites the old entry and shares its entity
   tag). If `placements` rows have no phase file
   yet, produce it with `<skill>/scripts/stamp.py` (`reference/modules.md`).
   For a redstone plan, confirm the pre-build checker evidence in
   [verification.md](reference/verification.md#redstone).
   Report problems and stop; fix nothing silently.
2. **Size the run.** For each phase file, run
   `python3 <skill>/scripts/ashlar_place.py plan <phase file>` and note its
   box, cells, pages and snapshot tiles. Add up the snapshot slots, counting
   one more for each `commands` phase that runs `place feature` (its
   snapshotted box). Then call
   `mc_snapshot` with `action: "list"` so the gate can say which existing
   snapshots would be evicted.
3. **Approval gate** (`reference/execution.md`): show the summary and wait for
   an explicit yes. Then set `approved:` in `plan.toon` to today's date.
4. **Build each phase in order** (`reference/execution.md`): player check,
   snapshots, placement (`mcp`, `placer` or `commands`), fix every
   unsupported-attachment warning, look with `mc_render`, record.
   If a phase stops part way, follow the
   [resume procedure](reference/execution.md#resuming-and-fixing).
5. **Verify** (`reference/verification.md`). Fix failures and verify again.
   Never report a build done while a check fails.
6. **Report** the bounding box, materials, snapshot ids, and anything the user
   must do in game (for example, flip a redstone start lever). For a redstone
   build, report all four verdicts (`built`, `at_rest`, `agent_tested`,
   `manual`). Call the machine working only when every verdict that is not
   `n/a` passed; otherwise say "built, not yet verified" and list what is
   pending and how to check it.

## verify

Run step 5 of `build` on the recorded project and report each check.

## test

Run as `exec-ashlar test <project> [<test>…]`. With test names it runs only
those tests; with `--manual` it runs only the manual tests, so pending manual
steps can be finished, or one failed test re-run, without repeating the rest.
With both, run only the named manual tests.

1. Preflight as for every mode. The project's registry status must be `built`.
   Run only the approved plan. Send changes that affect world writes back
   through the [approval gate](reference/execution.md#approval-gate). Use the
   [test-only gate](reference/execution.md#test-only-approval) when only the
   tests or their execution scope change.
2. `mc_players`. If anyone is inside the machine's box grown by 2 blocks, stop
   before any agent test or test write and say so. The user may stand further
   away to watch. Manual steps are done by the user, who is expected to be at
   the machine.
3. If agent tests are selected, run `forceload query`, then the paired
   `forceload add` over the approved columns
   ([commands.md](reference/commands.md)). Use the approved hold budget
   starting at the first add attempt. Bound calls and waits so cleanup can
   start by its reserved time. Record each confirmed addition.
4. **At rest check:** run `python3 <skill>/scripts/ashlar_place.py read` over
   the extent covering both the machine box and any recorded pre-build
   background, including its modelled cells outside the machine box. Keep
   force-loads and writes within the approved scope.
   `python3 <skill>/../system-redstone/scripts/redstone_rest.py diff <plan.toon> <read.json> --loaded`
   compares the read with the checker's predicted state after setup. Supply
   the recorded `--background <pre-build-read.json>` when provided. Enumerate
   the supported containers in the observed test area and any reused by the
   circuit from the full read. Reconcile them with the authored container
   list and setup inventories as described in
   [verification.md](reference/verification.md#redstone). Use `data get block`
   for inventory evidence. For a manual-only run or a console read outside
   the approved force-load area, take that evidence while a player keeps
   the chunks loaded. Unknown expected contents the circuit depends on
   prevent an `at_rest` pass.
5. Run each agent test's rows in order, each from its own
   [baseline](reference/plan-format.md#tests). Before a `load`, confirm the
   observed container at its approved coordinates. A failing row ends that
   test and records what was seen. Continue only if the next test fits before
   the cleanup reserve.
6. If this run attempted force-loads, start cleanup when it finishes, is
   interrupted or reaches the cutoff. Release only its confirmed additions
   and check the result with `forceload query`. If cleanup cannot be
   confirmed, report the affected chunks and the last result.
7. Guide the manual tests, each from its own baseline: one instruction at a
   time, wait for the user's word, read, record. Use the chunks the user keeps
   loaded for these passive reads. The user can stop at any point; the manual
   verdict then stays `pending`.
8. Record the verdicts and evidence in a `## Test …` section of `build-log.md`
   and in [`registry.json`](reference/registry.md#registryjson), then report as
   in [build step 6](#build). Retain earlier evidence only for
   unchanged, still-applicable tests. Revised tests and tests affected by a
   fix stay `pending` until rerun. Follow the
   [fix procedure](reference/execution.md#resuming-and-fixing) for failures.

Between reads, wait with whatever the client allows (for example a shell
`sleep`), or simply read again. Send reads in batches of at most 12 (Ashlar
queues at most 16 operations).

## rollback

Follow the rollback steps in `reference/execution.md`. First call
`mc_players`; if anyone is inside any restored box grown by 2 blocks, stop and
tell the user. Show the user the snapshots to be restored (ids, labels, boxes)
and any recorded snapshots that were evicted, and wait for an explicit yes.
Then restore the snapshots newest first, remove the project's entities with
`kill @e[tag=ashlar.<project>]` inside a paired force-load, tell the user what
a restore cannot bring back, and set the registry status to `rolled-back`.

## Hard rules

- No world write before the user approves the plan at the gate.
- `mc_players` before every write phase. If anyone is inside the phase's box
  grown by 2 blocks, stop and tell the user; do not build around them.
- Snapshots before every write phase (`reference/execution.md`).
- Console commands only in the forms in `reference/commands.md`. Commands that
  change the world only as listed in the approved plan's `commands` table or
  its `tests` table for test `load` rows. The read-only checks may run
  whenever surveying or verification needs them, with paired force-loads
  as described in `reference/commands.md`. Rollback mode runs its own
  `kill @e[tag=ashlar.<project>]`.
- Use the `minecraft:` prefix for console commands. Keep the columns
  touched by position and entity commands loaded as described in
  `reference/commands.md`. Pair every `forceload add` with its matching
  `forceload remove`. Never leave a chunk force-loaded: release only the
  additions this run confirmed, and preserve any chunk that was loaded before.
- A test `load` may only target a slot, or for `data merge` a container, that
  the latest baseline or container read shows empty. Otherwise stop and report;
  never overwrite items.
- Never place blocks with `mc_command`, and never use it to get around a limit.
- Never clear containers through the console.
- Stay within Ashlar's limits (`reference/tools-and-limits.md`); split the work
  into more calls or phases instead.
- Never print, log or commit the Ashlar URL or token, or any other value from
  the MCP server's environment.

## Tracking progress

- Claude Code: track the phases with your task or todo tool.
- Codex: track the phases with `update_plan`.
- Otherwise: keep a checklist in `build-log.md`.

`reference/clients.md` has the full list of client-specific tools.

## Reference library

Read the file for the step you are on:

| File | Covers |
| --- | --- |
| `reference/tools-and-limits.md` | The nine Ashlar tools, limits, block-state orientation rules, warnings and caveats |
| `reference/survey.md` | The survey procedure and the `survey.md` format |
| `reference/plan-format.md` | `plan.toon`, phase files, `quality_contract` and `tests` rows, validation |
| `reference/execution.md` | Approval gate, phases, ordering, snapshots, liquids, redstone, rollback |
| `reference/verification.md` | Acceptance, `quality_contract` and redstone checks |
| `reference/commands.md` | The console allowlist with exact command forms |
| `reference/modules.md` | Module files and stamping |
| `reference/registry.md` | The `.minecraft-builder` layout and `registry.json` |
| `reference/clients.md` | Claude Code and Codex specific tools, with fallbacks |
