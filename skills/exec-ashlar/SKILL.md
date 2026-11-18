---
name: exec-ashlar
description: >-
  Surveys Minecraft build sites and builds approved plans on a Paper server
  through the Ashlar MCP tools (mc_status, mc_players, mc_survey, mc_render,
  mc_inspect, mc_snapshot, mc_restore, mc_build, mc_command): site surveys,
  plan validation, an approval gate, snapshots, phased placement (directly or
  through a local placer script for large or generated geometry),
  verification and rollback. Use when a design skill hands off a survey or an
  approved plan, or when the user asks to build, verify or roll back a planned
  build through Ashlar.
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
| `rollback <project>` | Restore the project's snapshots and remove its tagged entities |

## Scripts

`scripts/ashlar_place.py` (the placer) and `scripts/stamp.py` (module
stamping) live in this skill's folder, written `<skill>` below. Run them with
`python3` from the workspace root, where `.minecraft-builder/` lives.

- Claude Code: `<skill>` is `${CLAUDE_SKILL_DIR}`.
- Codex: `<skill>` is the folder holding this `SKILL.md`.
- Otherwise: `<skill>` is the folder holding this `SKILL.md`.

## Preflight (every mode)

1. Call `mc_status`. If it fails, wait a few seconds and call it once more; if
   it still fails, stop and tell the user. The connection lives in the client's
   MCP settings, not in a skill.
2. Read `.minecraft-builder/registry.json` if it exists
   (`reference/registry.md`).

## survey

Follow `reference/survey.md`, write `survey.md`, and return to the design skill
that asked for it.

## build

1. **Validate** `.minecraft-builder/<project>/plan.toon` and every phase file
   against `reference/plan-format.md`. If `placements` rows have no phase file
   yet, produce it with `<skill>/scripts/stamp.py` (`reference/modules.md`).
   Report problems and stop; fix nothing silently.
2. **Size the run.** For each phase file, run
   `python3 <skill>/scripts/ashlar_place.py plan <phase file>` and note its
   box, cells, pages and snapshot tiles. Add up the snapshot slots.
3. **Approval gate** (`reference/execution.md`): show the summary and wait for
   an explicit yes. Then set `approved:` in `plan.toon` to today's date.
4. **Build each phase in order** (`reference/execution.md`): player check,
   snapshots, placement (`mcp`, `placer` or `commands`), fix every
   unsupported-attachment warning, look with `mc_render`, record.
5. **Verify** (`reference/verification.md`). Fix failures and verify again.
   Never report a build done while a check fails.
6. **Report** the bounding box, materials, snapshot ids, and anything the user
   must do in game (for example, flip a redstone start lever).

## verify

Run step 5 of `build` on the recorded project and report each check.

## rollback

Follow the rollback steps in `reference/execution.md`: restore the snapshots
newest first, remove the project's entities with
`kill @e[tag=ashlar.<project>]`, tell the user what a restore cannot bring
back, and set the registry status to `rolled-back`.

## Hard rules

- No world write before the user approves the plan at the gate.
- `mc_players` before every write phase. If anyone is inside the phase's box
  grown by 2 blocks, stop and tell the user; do not build around them.
- Snapshots before every write phase (`reference/execution.md`).
- Console commands only in the forms in `reference/commands.md`. Commands that
  change the world only as listed in the approved plan's `commands` table; the
  read-only checks may run whenever surveying or verification needs them, and
  rollback mode runs its own `kill @e[tag=ashlar.<project>]`.
- Never place blocks with `mc_command`, and never use it to get around a limit.
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
| `reference/plan-format.md` | `plan.toon`, phase files, `quality_contract` rows, validation |
| `reference/execution.md` | Approval gate, phases, ordering, snapshots, liquids, redstone, rollback |
| `reference/verification.md` | Acceptance and `quality_contract` checks with `mc_inspect` and `mc_render` |
| `reference/commands.md` | The console allowlist with exact command forms |
| `reference/modules.md` | Module files and stamping |
| `reference/registry.md` | The `.minecraft-builder` layout and `registry.json` |
| `reference/clients.md` | Claude Code and Codex specific tools, with fallbacks |
