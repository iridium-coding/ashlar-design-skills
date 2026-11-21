# Ashlar design skills — sub-project 3: redstone

- **Date:** 2026-11-19
- **Status:** approved by the user on 2026-11-19 (approach C; merge first, then
  live runs); implemented on `redstone`; PR #2
- **Base:** fork `main` at `db3e8a1` (sub-project 1, PR #1, merged); Chapman's
  `system-redstone` from Release 1.2.0 (`b4bea4a`)
- **Backend:** Ashlar 0.4.9 (`ashlar-mcp` + Paper plugin) on Paper 26.3
- **Sub-projects:** 1 foundation and design skills (merged) · 2 terrain (own
  branch) · 3 redstone (this spec, branch `redstone`)

## 1. Intent

The user wants an agent that takes a natural-language request for a working
redstone machine, designs a correct Java Edition circuit for the actual site,
builds it safely through Ashlar, and verifies as much of its function as
Ashlar's tools allow. Where it cannot verify something, it says so and tells the
user exactly how to check it, instead of claiming the machine works.

Chapman's `system-redstone` holds the Java redstone knowledge: a catalog of
machines, logic patterns, timing, an interview and a design → test → correct
loop. It is written for Chapman's Fabric MCP server, which places blocks with
block updates, can nudge a stalled circuit with a tool call, and verifies
through events, inventory tools and datapack functions. None of that exists
under Ashlar. The six design skills already defer complex redstone to
`system-redstone` "if it is installed".

Progress is measured by a ladder of benchmark machines chosen by the user, from
a two-item sorter to a 3×3 piston door, followed by orientation, footprint and
recovery variants (§9).

### 1.1 Goals

1. Port `system-redstone` to Ashlar for Claude Code and Codex, keeping Chapman's
   Java design knowledge.
2. Build every contraption through `exec-ashlar`: approval gate, player checks,
   snapshots and the console allowlist.
3. Write every redstone component in a valid resting state although Ashlar
   places blocks without physics, and check that offline before any write.
4. Test a machine's function with Ashlar's tools wherever they can drive it,
   and give the user exact manual steps for the rest.
5. Keep "built" and "works" apart in every report (four verdicts, §6.4).
6. Reason about orientation and footprint, so the same request can be built
   facing any way or squeezed into less room.
7. Recover cleanly from a build that stops part way or a machine that fails its
   test.

### 1.2 Non-goals

- Changing Ashlar (for example a tool that flips levers or places blocks with
  updates).
- A tick-by-tick redstone simulator.
- A library of stored, tested schematics.
- Chapman's `build-systems` orchestrator, `system-transit` and `exec-*` skills.
- New console command forms.

### 1.3 Anti-goals (failures even if the machine runs)

- Reporting a machine as working without a passed functional test, or hiding a
  verification gap.
- Passing a benchmark by copying a stored layout instead of designing for the
  prompt and the site.
- Any world write without the user's approval at a gate; any console command
  outside the allowlist; command blocks or `Command` NBT.
- A chunk left force-loaded.
- The Ashlar URL or token, or server-specific facts (server folder names,
  hosts, IPs, player names), in output, logs or commits.

### 1.4 Success criteria for this sub-project

The user chose to merge first and run the live rungs on the merged `main`
(§10.1).

**Before the merge** (the implementation PR):

1. The static and script checks in §11 pass, including upstream's
   `node scripts/validate-plugin.mjs`.
2. Offline dry runs of the rung 1 and rung 2 prompts produce plans that pass
   validation and `redstone_rest.py check` (§11.3).
3. `ashlar_place.py read` works against the live server (read-only).

**After the merge**, in the main workspace, each world write through the gate:

4. With the user's OK, the clone checks out the merged `main` and the
   `system-redstone` links are created (§10).
5. Codex, started in the workspace root, finds `system-redstone`, follows the
   same text and can run both scripts.
6. Rung 0 (calibration, §9.3) has been run, and every surprise has been folded
   into the skill text and the checker before rung 1.
7. Rung 1 (sorter, §9.4) passes all six of its criteria, tested by the agent
   over two batches.
8. Rung 2 (2×2 sticky-piston door, §9.5) passes the user's ten guided cycles
   with no piston left in the wrong state.
9. Every report from these runs shows the four verdicts separately.

Fixes found by the live runs land as follow-up PRs, each on its own branch.
Sub-project 3 is done when all nine hold. Rungs 3–5 and the variants are written
in this sub-project and run after it.

## 2. Findings that shape the design

1. **Ashlar places blocks without physics.** `mc_build` writes block states
   with no block updates. Its connection pass is shape-only: it joins fences,
   panes, walls, bars, stairs and redstone wire to their neighbours. There is
   no option to place with updates (tool schema, read 2026-11-19). Nothing the
   agent writes can start, nudge or trigger a circuit, and a component written
   in the wrong state stays wrong until something else updates it.
2. **Chapman's skill assumes the opposite.** Its "read first" file says
   placement fires neighbour updates, most clocks start on their own, a one-tick
   redstone-block nudge restarts a stalled loop, and `update_flags: 2` stages
   parts dormant. Its verification uses `events_subscribe`/`events_poll`,
   inventory and entity tools, `block_set_state`, `command_execute` and
   datapack functions. Its text names `exec-worker`, `exec-inspect`,
   `exec-plan`, `exec-blueprint`, `exec-reflect`, `survey-site`,
   `server_get_status` and `mcbuilder:registry`, and points at
   `terrain-shape`'s command budget under `${CLAUDE_PLUGIN_ROOT}`.
3. **What the allowlist gives** (`exec-ashlar/reference/commands.md`):
   `item replace block` puts items in a container slot; `data merge block` sets
   block-entity NBT (spawner settings, container `Items`); `data get block`
   reads them; tagged `summon` and `kill`; paired `forceload add`/`remove`.
   `setblock`, `fill`, `clone`, `function`, `schedule` and command blocks are
   forbidden.
4. **Container changes are real updates.** When a command changes a container,
   the game notifies comparators reading it (vanilla `BlockEntity#setChanged`
   calls `updateNeighbourForOutputSignal`), and hoppers move items on their own
   in any ticking chunk. So the agent can start and test machines driven by
   items, but not machines driven by a lever, a button or their own clock.
   Rung 0 confirms this on the server.
5. **Comparator container formula** (Minecraft Wiki, "Redstone Comparator" →
   Fullness of containers, read 2026-11-19): an empty container reads 0;
   otherwise the signal is `floor(1 + (full-stack-equivalent / 64 / slots) ×
   14)`, where each item counts 1 if it stacks to 64, 4 if it stacks to 16 and
   64 if it does not stack. A 5-slot hopper reads 1 with 1–22 items and 2 from
   23. A chest that cannot open (a conductive block above it) reads 0. A
   comparator reads a double chest as all 54 slots.
6. **Chunk ticking** (Minecraft Wiki, "Tick" → Chunk tick, read 2026-11-19):
   force-loaded chunks are ticked like chunks near a player, including random
   ticks (crop growth). Mob spawning still needs a player within 8 chunks. Sugar
   cane needs 16 random ticks per new block, about 18 minutes on average.
7. **`mc_inspect` columns output carries full block states**, for example
   `0,0: 62 water[level=0] | 63-70 air` (read-only check, 2026-11-19), for up
   to 1,024 columns per call, with no cap on distinct states (the ASCII slice is
   capped at 47).
8. **`stamp.py`** rotates and mirrors `facing`, `axis`, rail `shape`,
   `rotation`, `hinge` and `orientation`. It drops the side properties of
   connecting blocks, including `redstone_wire`, because Ashlar recomputes them,
   and keeps `power`. Vertical `facing` (`up`, `down`) passes through.
9. **Ashlar pairs chests.** Adjacent chests with the same facing become double
   chests automatically (`mc_build` orientation rules).
10. **Java update order depends on direction and location.** A circuit that
    relies on it can work facing one way and fail when rotated or mirrored. Only
    a live build shows this.
11. **Paper settings.** Paper's defaults disable piston duplication and
    headless pistons and use the vanilla redstone implementation. A server owner
    can change `redstone-implementation`, which changes dust update order. The
    target server uses the defaults (checked 2026-11-19).
12. **Snapshots are scarce.** Ashlar keeps 20 snapshots, shared by the whole
    server, and the store is full, so every new snapshot evicts another build's
    rollback point. Each failed live attempt is expensive, so catching mistakes
    offline matters.
13. **Chapman's sorter guidance is muddled.** The catalog says the filter
    hopper holds "18 filler items spread one per slot"; the hard rules say "18
    filler items … per filter slot". The standard design for 64-stack items is
    18 of the sorted item in one slot and one filler in each of the other four:
    22 items, signal 1, and the 23rd tips it to 2. The port derives counts from
    the formula (finding 5) instead of quoting a number.

## 3. Decisions

| Topic | Decision |
| --- | --- |
| Approach | C: port the skill, add a test protocol to `exec-ashlar`, add an offline resting-state checker (§4) |
| Placement | Every redstone component is written in its resting state; the agent never tries to nudge a circuit |
| Starting machines | Machines driven by game events start themselves; machines driven by a player input or a clock need the user; every clock has an off switch so it can be placed at rest |
| Test inputs | For machines started by a lever, button, plate or clock, `system-redstone` proposes a small hidden input the agent can drive; the user decides per build (§5.5) |
| Verification | `exec-ashlar test` runs the agent's steps and guides the user's; four separate verdicts; "works" only when every verdict that applies passed (§6) |
| Corrections | Each fix is a new phase through the gate; stop after three failed fix rounds (§6.6) |
| Console | No new forms; test loads are ordinary `item replace block` and `data merge block` commands shown at the gate |
| Benchmarks | Prompts plus pass criteria in `docs/benchmarks/redstone/`, run in fresh sessions; results kept in the workspace, outside the repo (§9) |
| Merge and live runs | Merge first: the implementation PR merges after the static checks and offline dry runs; rungs 0–2 then run live in the main workspace on the merged `main`, and their fixes land as follow-up PRs (§10.1) |
| Done-bar | Rung 0 run; rung 1 passes, tested by the agent over two batches; rung 2 passes the user's ten cycles |
| Clients | Claude Code and Codex, agent-neutral text with labelled lines (sub-project 1 spec §7.5) |

## 4. Approaches considered

| | Approach | Trade-off | Outcome |
| --- | --- | --- | --- |
| A | Text-only port; `system-redstone` runs its own tests | No new code, but the tests would sit outside `exec-ashlar`, which owns the allowlist, force-load pairing and the gate, so they would duplicate those rules or drift from them | Rejected |
| B | Port plus a test protocol in `exec-ashlar` | Smaller. Wrong resting states and broken wiring show up only live, in the rest → run → rest comparison or a failed test, each costing a gate, snapshots on a full store and a rollback | Rejected in favour of C |
| C | B plus an offline resting-state checker | Catches wrong resting states and unreachable wiring before any write, in every rotation. The largest new code, and it models only a slice of Java redstone | **Chosen** |

Also dropped: changing Ashlar so it can flip levers (outside this fork, and the
user wants manual validation reported instead), a tick-by-tick simulator (too
large, and it would drift from the server), and a schematic library (it would
defeat the benchmarks).

## 5. The `system-redstone` skill

### 5.1 Layout

```text
skills/system-redstone/
  SKILL.md                      rewritten for Ashlar
  reference/
    ashlar-redstone.md          new; replaces setblock-redstone-limits.md (§5.4)
    java-redstone.md            edited (§5.8)
    design-patterns.md          edited
    contraptions-farms.md       edited
    contraptions-mechanisms.md  edited
    interview.md                edited
    verification.md             rewritten
    community-sources.md        edited
    checker.md                  new: running redstone_rest.py and reading its report
  scripts/
    redstone_rest.py            new (§8)
```

`reference/setblock-redstone-limits.md` is cut down to a short stub that says
its premise does not hold under Ashlar (finding 1) and points to
`ashlar-redstone.md`. It cannot simply be deleted: Chapman's `exec-inspect`
(line 155) and `exec-reflect` (line 88) link to it by its
`${CLAUDE_PLUGIN_ROOT}` path, `scripts/validate-plugin.mjs` checks that such
paths exist, and editing those two skills is a non-goal (§1.2) that would also
make upstream merges harder. The stub, like every file in the skill, must pass
the static text checks (§11).

### 5.2 Frontmatter

- `name: system-redstone`.
- `description` (under 1,024 characters): designs redstone contraptions for a
  Paper server reached through Ashlar (sorters, piston doors, farms, clocks,
  elevators, music, traps), Java-correct and written at rest, builds them
  through `exec-ashlar`, and tests what Ashlar's tools can drive, reporting
  what still needs the user. Use when the user wants a contraption or working
  machine, or when a design skill hands one off.
- Claude-only extras, which Codex ignores: `model: opus`, `effort: high`, and
  `allowed-tools` listing only the five read-only Ashlar tools, as
  `exec-ashlar` does.
- Codex: `metadata.short-description`.

### 5.3 How a run goes

1. **Preflight:** `mc_status`; read `.minecraft-builder/registry.json`; hand
   off to `exec-ashlar survey <project>` for the site.
2. **Interview** (`reference/interview.md`): Chapman's question bank, plus:
   - the footprint and facing limits the survey found;
   - for a machine started by a lever, button, plate or clock: whether to add
     an agent test input (§5.5);
   - who will be in game for manual steps, and when;
   - for sorters, the item types (prefer items that stack to 64).
3. **Design** from the catalog, the patterns and `ashlar-redstone.md`. Draw the
   machine as one or more modules in local coordinates
   (`exec-ashlar/reference/modules.md`), so the placement rows choose the
   rotation and mirror that fit the site. State the timing budget and, for any
   circuit that reads a container, the item counts derived from the comparator
   formula.
4. **Check:** stamp the placements with `stamp.py`, then run
   `redstone_rest.py check` (§8). Fix and re-run until it reports no
   mismatches. List every part the checker does not model in the plan's
   `notes`, with how it was checked by hand. Run `check --input` for each input
   to confirm it reaches every target. Record the result in `build-log.md`.
5. **Plan:** write `plan.toon` (`exec-ashlar/reference/plan-format.md`). Phases
   go in this order: site prep; machine blocks; attached parts; a `commands`
   phase for setup (container loads such as filter hoppers, spawner NBT). Then
   the `tests` table (§6.1). The notes name the start input, any manual steps
   and what the agent cannot test.
6. **Build:** hand off to `exec-ashlar build <project>`.
7. **Test:** hand off to `exec-ashlar test <project>`.
8. **Report:** the four verdicts with their evidence, any manual steps still
   outstanding, and whether the machine keeps running unattended (it runs only
   while its chunks are loaded).
9. **On a failure:** diagnose with the correction catalog
   (`reference/verification.md`) and `redstone_rest.py check` and `diff`. Write
   a fix phase holding only the changed blocks and hand off to
   `exec-ashlar build` for a new gate, then test again (§6.6). After three
   failed fix rounds, stop and recommend a rollback or a redesign.

### 5.4 Ashlar placement rules (`reference/ashlar-redstone.md`)

**Placement without physics.** Redstone does not update, observers do not fire,
pistons do not move, liquids do not flow unless `liquids: "flow"`, and sand
does not fall. The connection pass sets wire, pane, fence, wall, bar and stair
shapes only, never power.

**Resting states.** Every component is written in its resting state: the state
the game would compute for the finished machine with its inputs as built
(normally off) and its containers as Ashlar leaves them (empty). Nothing
corrects a wrong state until a real update reaches it.

| Component | Resting state to write |
| --- | --- |
| `redstone_wire` | `power` = the level its sources give at rest (0 when nothing is on); sides left to Ashlar |
| `redstone_torch`, `redstone_wall_torch` | `lit=true` unless the block it hangs on is powered |
| `repeater` | `powered` = its input at rest; `locked` = a powered repeater or comparator at its side; `delay` per design |
| `comparator` | `powered` = output above 0 at rest; `mode` per design |
| `lever` | `powered` as the design's input stands (normally `false`) |
| buttons, pressure plates | not pressed |
| `observer` | `powered=false` |
| `piston`, `sticky_piston` | `extended` = powered at rest, directly or by quasi-connectivity; an extended piston has its `piston_head` (`type`, `facing`, `short=false`) in front |
| `hopper` | `enabled=false` when powered at rest, otherwise `true` |
| `dropper`, `dispenser` | `triggered` = powered at rest |
| `redstone_lamp` | `lit` = powered at rest |
| doors, trapdoors, fence gates | `powered` = powered at rest; `open` follows it for machine-driven ones |
| `note_block` | `powered` = powered at rest |

Components outside this table are listed by the checker as unmodelled and
checked by hand.

**Containers and setup.** Containers are loaded after their blocks exist, with
`item replace block` (one slot per command) or `data merge block` (`Items`), in
a `commands` phase inside a paired force-load. These are the machine's first
real updates: comparators reading those containers re-read, so loading a
sorter's filters settles its own comparators. Write the circuit as it rests
with empty containers and let the setup move it. The checker computes both
states (§8.2).

**Starting.** A machine driven by game events (items arriving, crops growing,
mobs) starts itself once it is placed at rest and its chunks tick. A machine
driven by a player input (lever, button, plate) or by its own clock needs the
user's hand. A clock is always built with an off switch, written off, so it has
a resting state; a free-running clock cannot be placed at rest, and the checker
reports it.

**No nudges.** Never try to start or reset a circuit by writing a redstone
block, lever or torch with `mc_build` (it changes nothing), and never place
blocks through the console.

**Pistons.** Never write a piston head without its base, or an extended piston
without its head; Paper removes headless pistons. Quasi-connectivity powers a
piston, dropper or dispenser from power at the block above it; note every place
the design relies on it.

**Chests.** Ashlar pairs same-facing chests that sit side by side. Keep
separate outputs apart with a one-block gap, different facings, or barrels. A
comparator reads a whole double chest. A chest with a conductive block above it
cannot open and reads 0.

**Dust shape.** Ashlar's connection pass decides wire shapes. A lone dust may
come out as a dot, which powers only the block below, where a hand-placed one
would be a cross. Until rung 0 shows what Ashlar does, design so no wire depends
on being a cross with no connections. Rung 0 settles this rule.

**Liquids and plants.** Water next to cane, or water that only has to sit
still, is placed still. A stream that must carry items needs flowing sources
(`liquids: "flow"`, at most 2,000 flowing blocks per call), placed last. Place
soil and water before plants. Physics-off placement does not break an invalid
plant until something updates it, and Ashlar's warnings cover only attached
blocks, so check plant support by hand.

**Orientation and update order.** Prefer designs that do not depend on update
order: no BUD tricks, no same-tick races between pistons. Where a design does
depend on it, say so in the plan notes; the orientation variants test it.

**Chunks.** Redstone, hoppers and growth run only in loaded chunks. Tests hold
a paired force-load (§6.3). Outside tests a machine runs only while a player is
near, or while the server owner keeps its chunks loaded; report this for any
machine meant to run unattended.

**Paper.** Duping (TNT, rails, carpets) and headless pistons are off by
default; never design around them. If unsure whether the server has changed
`redstone-implementation`, ask the user.

### 5.5 Test inputs and fixtures

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

### 5.6 Chapman → Ashlar mapping

| Chapman | In the port |
| --- | --- |
| Placement with updates; clocks start on their own | Placement without physics; resting states (§5.4) |
| One-tick redstone-block nudge; `update_flags: 2` dormant staging | Removed; resting states, plus a start by the user or a test input |
| `initial_trigger` block | Removed; the start input is named in the plan notes and as a `manual` test step |
| `.minecraft-builder/<project>/inspection-recipe.toon` | The `tests` table in `plan.toon` (§6.1) |
| `exec-worker`, `exec-inspect`, `exec-plan`, `exec-blueprint`, `exec-reflect` | `exec-ashlar build`, `test` and `verify`; modules through `stamp.py` |
| `survey-site` | `exec-ashlar survey` |
| `server_get_status` | `mc_status` |
| `block_entity_set_nbt`, `inventory_set_slot`, `player_give_item` | `data merge block`, `item replace block` rows in the approved plan |
| `block_get_state`, `block_scan_region` | `mc_inspect`; `ashlar_place.py read` (§6.7) |
| `inventory_get`, `inventory_count_items`, `block_entity_get_nbt` | `data get block` |
| `entity_query`, `entity_get` | `execute if entity @e[tag=ashlar.<project>,…]`, for the build's tagged entities only |
| `events_subscribe`, `events_poll` | Removed (no event channel); `settle` and `await` reads (§6.1) |
| `function_run`, `schedule_function`, datapacks | Removed (`function` and `schedule` are forbidden) |
| `scoreboard_*` counters | Removed; the pulse counter (§5.5) |
| `content_registry_*`, `level_get_mob_spawns`, `loot_table_generate` | Removed; figures cited from the wiki and confirmed on the server |
| `mcbuilder:registry` | `.minecraft-builder/registry.json` |
| `terrain-shape` command budget under `${CLAUDE_PLUGIN_ROOT}`; 32,768-block and 64×384×64 caps | `exec-ashlar/reference/tools-and-limits.md` |
| `AskUserQuestion` | Labelled lines (Claude Code, Codex, Otherwise) |

### 5.7 Hard rules in `SKILL.md`

- Java-correct: quasi-connectivity, deterministic timing, clean observer
  pulses. No 0-tick tricks, duping or headless pistons.
- Every redstone component is written at rest. Hand off to `exec-ashlar build`
  only after `redstone_rest.py check` is clean, with every unmodelled part
  checked by hand and noted.
- Never call a machine working without a passed functional test. When Ashlar
  cannot drive a machine, say "needs your test" and give the exact steps.
- All world changes go through `exec-ashlar`. Console commands only as
  `exec-ashlar/reference/commands.md` allows; never command blocks or `Command`
  NBT.
- Contraptions run on vanilla redstone. Console commands are only for setup
  and verification.
- Derive container-read item counts from the comparator formula; never quote a
  fixed number.
- Village mechanics belong to `design-village`. A façade or enclosure belongs to
  `design-building`, `design-house` or `design-city`.
- AFK farms: confirm the server permits them.

### 5.8 Other reference edits

- `java-redstone.md`: keep the mechanics and timing; replace Chapman tool names
  with Ashlar equivalents; add the comparator formula and the Paper notes; drop
  "Java-exclusive options" (all Fabric-only).
- `design-patterns.md`: drop the datapack section. Keep gates, memory, edges,
  clocks (each with an off switch), randomness, transmission and the timing
  budget.
- `contraptions-farms.md`, `contraptions-mechanisms.md`: fix the sorter entry
  (finding 13); turn the "ship it pre-loaded" sections into `item replace
  block` and `data merge block` rows in a setup `commands` phase, read back with
  `data get block`; add the chest-pairing rule.
- `interview.md`: the new questions (§5.3); `AskUserQuestion` on a labelled
  line; `survey-site` becomes `exec-ashlar survey`.
- `verification.md`, rewritten:
  - how to write the `tests` table;
  - Chapman's per-type test contracts, recast as what the agent can drive and
    what needs the user;
  - the four verdicts;
  - the correction catalog, with the nudge rows removed and new rows such as:
    a component that never changed state (written in the wrong resting state);
    a comparator reading 0 (a chest under a conductive block); mixed outputs
    (chests paired); an isolated dust drawn as a dot.
- `community-sources.md`: Ashlar tool names; web research through
  `survey-research`.
- `checker.md`: how to run `redstone_rest.py`, read its report, and what it does
  not model.

## 6. Changes to `exec-ashlar`

### 6.1 The `tests` table in `plan.toon`

Each test is a list of steps run in order. Example for a sorter batch:

```toon
tests[9]{test,step,kind,at,detail,expect}:
  batch-1,1,load,104 64 -350,"item replace block 104 64 -350 container.0 with minecraft:cobblestone 40",-
  batch-1,2,load,104 64 -350,"item replace block 104 64 -350 container.1 with minecraft:oak_log 40",-
  batch-1,3,load,104 64 -350,"item replace block 104 64 -350 container.2 with minecraft:dirt 20",-
  batch-1,4,settle,100 60 -352 108 64 -346,containers,timeout 180
  batch-1,5,expect,106 61 -352,container,gained minecraft:cobblestone=40
  batch-1,6,expect,106 61 -349,container,gained minecraft:oak_log=40
  batch-1,7,expect,106 61 -346,container,gained minecraft:dirt=20
  batch-1,8,conserve,100 60 -352 108 64 -346,containers,-
  batch-1,9,rest,100 60 -352 108 64 -346,blocks,baseline
```

(A filter hopper's contents are checked the same way with `holds`, for example
`expect,103 63 -352,container,holds minecraft:cobblestone=18|minecraft:stick=4`.)

And for a lever-driven door:

```toon
tests[8]{test,step,kind,at,detail,expect}:
  cycle,1,manual,101 65 -341,"Flip the lever at 101 65 -341 on, then tell me",-
  cycle,2,settle,98 64 -343 103 67 -336,blocks,timeout 10
  cycle,3,expect,100 65 -340 100 66 -339,block,minecraft:air
  cycle,4,manual,101 65 -341,"Flip the lever at 101 65 -341 off, then tell me",-
  cycle,5,settle,98 64 -343 103 67 -336,blocks,timeout 10
  cycle,6,expect,100 65 -340 100 66 -339,block,minecraft:smooth_stone
  cycle,7,rest,98 64 -343 103 67 -336,blocks,baseline
  cycle,8,repeat,-,steps 1-7,9
```

(Here the wall runs along z at x = 100, the doorway is z = -340 to -339 at
y = 65 to 66, the pistons sit at z = -342 and z = -337, and the lever is on the
wall's east face beside the doorway. Smooth stone fills the doorway when
closed. The first pass and nine repeats give ten cycles.)

| Kind | `at` | `detail` | `expect` | Run by |
| --- | --- | --- | --- | --- |
| `load` | the container | one quoted inventory load command (`item replace block` or `data merge block` with an `Items` payload only) | `-` | agent |
| `settle` | a region | `containers` or `blocks`: what to read | `timeout <seconds>`: repeat the reads until two in a row agree, or fail | agent |
| `await` | a container or cell | `container` or `block` | a condition plus `within <seconds>`, for example `minecraft:sugar_cane>=8 within 3600`: repeat the reads until it holds, or fail | agent |
| `expect` | a container, a cell or a region | `container` or `block` | `container`: either `gained` and the items the container gained since this test's baseline, or `holds` and its exact contents, each as `id=count` joined by `\|` (nothing else may have been gained, or be held); `block`: a block state that every cell must match (unspecified properties are wildcards) | agent |
| `conserve` | a region | `containers` | `-`: for every item, the total across the region's containers equals this test's baseline total plus this test's loads, and no container outside this test's `gained` rows gained anything | agent |
| `rest` | a region | `blocks` | `baseline`: the power properties of the redstone components match this test's baseline | agent |
| `manual` | where the user acts | the exact instruction, quoted | `-`; the next steps read what happened | user |
| `repeat` | `-` | `steps <a>-<b>` | how many additional times to run those earlier steps | — |

A test with a `manual` row is a manual test; any other test is an agent test.
Manual tests use user actions and passive observation. Put any `load` rows in
a separate agent test.
Every `load` command is a world change: validation checks it against
`commands.md`, and the approval gate shows it as it will run.

**Each test has its own baseline.** Before a test's first row, `test` mode
settles the machine's containers and reads the machine (block states and
container contents). `gained`, `conserve` and `rest` are measured against that
reading, so earlier batches, earlier runs and earlier fix rounds leave nothing
for a later test to trip over: batch 2 is checked against the state batch 1
left, and a re-test after a fix starts from wherever the machine stands. The
machine must be at rest when the baseline is read: its power properties match
the loaded rest state, and its internal containers (every container except
this test's `load` targets and `gained` containers) hold what the loaded rest
state says. If not, for example because an earlier failed run left items in a
hopper line, the test stops and tells the user, who clears them in game or
rolls back. The plan never clears containers through the console.

### 6.2 Validation additions (`plan-format.md`)

- Every `tests` row has a known kind and a parsable `expect`. Its `at` is a
  parsable position or region inside the plan's `bbox`, except for `repeat`,
  which uses `-` and names a valid range of earlier steps in the same test.
- Every `load` is in an agent test and matches `item replace block` or
  `data merge block` in `commands.md`. A test `data merge block` may set only
  the inventory `Items` payload. The command's coordinates must equal the
  row's single `at` position inside the `bbox` and identify a planned or
  observed container. Confirm the container is present before executing.
- Every test that drives the machine ends with a `rest` row after expanding
  any `repeat` rows.
- A plan written by `system-redstone` has at least one test for each input, or
  a note saying why the input cannot be tested.
- Plans from other skills may omit `tests`.

### 6.3 `test <project>` mode

Run as `exec-ashlar test <project> [<test>…]`. With test names it runs only
those tests; with `--manual` it runs only the manual tests, so pending manual
steps can be finished, or one failed test re-run, without repeating the rest.

1. Preflight as for every mode. The project's registry status must be `built`.
   For changed test rows or execution scope on a built project, use the
   test-only gate (§6.5).
2. `mc_players`. If anyone is inside the machine's box grown by 2 blocks, stop
   before any agent test or test write and say so. The user may stand further
   away to watch. Manual steps are done by the user, who is expected to be at
   the machine.
3. If agent tests are selected, run `forceload query`, then the paired
   `forceload add` over the approved columns (`commands.md`). Start the
   approved hold budget at the first add attempt. Bound calls and waits so
   cleanup can start by its reserved time. Record each confirmed addition.
4. **At rest check:** `ashlar_place.py read` over the extent covering both the
   machine box and the recorded pre-build background when supplied, including
   the background's modelled cells outside the machine box. Keep force-loads
   and writes within approval. `redstone_rest.py diff --loaded`, with the
   same background if supplied, compares the read with the checker's
   predicted state after setup. Enumerate supported actual containers in the
   test area and any reused by the circuit from the full read. Reconcile them
   with the plan-authored list from `containers`, the setup loads and any
   recorded expectations for reused containers. Read their inventories with
   `data get block`. For manual-only runs or console reads outside the
   approved force-load area, take this inventory evidence while a player keeps
   the chunks loaded. Unknown expected contents the circuit depends on
   prevent an `at_rest` pass (§6.4).
5. Run each agent test's rows in order, each from its own baseline (§6.1). A
   failing row ends that test and records what was seen. Continue only if the
   next test fits before the cleanup reserve.
6. If this run attempted force-loads, start cleanup when it finishes, is
   interrupted or reaches the cutoff. Release only its confirmed additions
   and check the result with `forceload query`. If cleanup cannot be
   confirmed, report the affected chunks and the last result.
7. Guide the manual tests: one instruction at a time, wait for the user's word,
   read, record. Use the chunks the user keeps loaded for these reads. The user
   can stop at any point; the manual verdict then stays `pending`.
8. Record the verdicts and evidence in a `## Test …` section of `build-log.md`
   and in `registry.json`, then report. Retain earlier evidence only for
   unchanged, still-applicable tests. Revised tests and tests affected by a
   fix are `pending` until rerun.

Between reads, wait with whatever the client allows (for example a shell
`sleep`), or simply read again. Send reads in batches of at most 12 (Ashlar
queues at most 16 operations).

### 6.4 Verdicts

Each project in `registry.json` gains a `verdicts` key:

```json
"verdicts": {
  "built": "pass",
  "at_rest": "pass",
  "agent_tested": "pass",
  "manual": "pending",
  "evidence": "build-log.md, Test 2026-11-20 14:05",
  "updated": "2026-11-20T14:20:00Z"
}
```

Each verdict is `pass`, `fail`, `pending` or `n/a`:

| Verdict | Passes when |
| --- | --- |
| `built` | The existing acceptance and `quality_contract` checks pass, and `redstone_rest.py diff` of a full read against the plan finds no cell that differs in block or in any property other than power properties and the ones Ashlar's connection pass sets |
| `at_rest` | The checker was clean before the build, the power properties in the baseline read after setup match the checker's loaded rest state, internal inventories match their expected contents, and every `rest` row passed |
| `agent_tested` | Every agent test passed; `n/a` when the agent can drive nothing |
| `manual` | Every manual test passed; `pending` until the user has done them; `n/a` when there are none |

**Power properties** are the ones a circuit changes at run time: `power`,
`powered`, `lit`, `extended`, `enabled`, `triggered`, `locked`, and `open` on
machine-driven doors, trapdoors and fence gates. **Connection-pass properties**
are the side properties of wire, panes, fences, walls and bars, stair `shape`,
and chest `type`. Splitting them keeps the two verdicts apart: a wrong facing or
a missing block fails `built`; a wrong torch or piston state fails `at_rest`.

The report shows all four. It calls the machine working only when every verdict
that is not `n/a` passed; otherwise it says "built, not yet verified" and lists
what is pending and how to check it. The registry `status` flow is unchanged.

### 6.5 Approval gate additions (`execution.md`)

The gate also shows:

- every test `load` command exactly as it will run;
- the exact chunks each agent test may force-load and its maximum hold time.
  Add only chunks absent from the pre-run query and remove only confirmed
  additions. Include all expanded row timeouts and bounded overhead for
  force-load calls, baseline reads, console steps, verification and cleanup.
  Show the combined budget if tests share a force-load and reserve time to
  release and verify the run's additions;
- any test input or fixture, and where it is;
- the manual steps the user will be asked to do;
- what will remain unverified.

If only the tests or their execution scope change after a build, validate
the revised tests and use a fresh test-only approval for that scope. Show the
revised test evidence requirements. Wait for an explicit yes, update the
approval date and record the approved test scope. Keep the registry status
`built` and run only the approved tests.

### 6.6 Recovery and corrections (`execution.md`)

- **An interrupted block placement** (placer exit 5, an MCP error, the user
  stops it): record the known writes and snapshot ids. Confirm that replaying
  the fills and blocks would produce the same final cells. When it would,
  offer to resume from the start or roll back and ask before either. Resume
  using the original snapshots without taking new ones (`--no-snapshot` for
  the placer, omit `snapshot` for `mc_build`). That keeps the original
  rollback point and avoids spending slots on the half-written state. If any
  original snapshot has been evicted, tell the user at the gate which part
  can no longer be rolled back. If replay could produce a different result,
  for instance with overlapping conditional fills, reconcile the partial
  writes first and show the exact remaining writes, restore or correction at
  a fresh gate.
- **An interrupted `commands` phase:** release the phase's force-loads and
  reconcile each confirmed or uncertain operation against the console log and
  observed state. Use available block, inventory and tagged-entity reads.
  Never replay summons, feature placement or inventory loads wholesale.
  Show the precise remaining commands or recovery actions at a fresh gate
  and wait for approval before continuing.
- **A failed test:** `system-redstone` diagnoses it. The fix is a new phase
  holding only the changed blocks, added to `plan.toon`, validated, and shown at
  a new gate as a list of the cells it changes. Then snapshot, place and test
  again. Mark the tests affected by the fix `pending` until rerun. After three
  failed fix rounds the skill stops and recommends a rollback or a redesign.
- **A test that fails part way** records what it saw. When the run ends or
  reaches its cleanup cutoff, release only its own force-load additions
  within the reserved time. If cleanup cannot be confirmed, report the
  affected chunks.

### 6.7 `ashlar_place.py read`

```text
python3 <skill>/scripts/ashlar_place.py read <x1> <y1> <z1> <x2> <y2> <z2> --out <file.json> [--world <name>]
```

- Read-only. Built on a **shared column reader** that tiles the box into
  `mc_inspect` `format: "columns"` calls of at most 1,024 columns and 200,000
  cells and parses each `x,z: y1-y2 <state> | …` line into per-column runs
  `[(y1, y2, state)]`. Each subcommand writes its own output from the runs:
  `read` flattens them into JSON,
  `{"world": …, "from": […], "to": […], "cells": {"x,y,z": "minecraft:<state>", …}}`,
  which suits machine-sized boxes; the terrain branch's planned backup keeps the
  runs, because a large terrain box is millions of cells. Whichever branch
  lands first owns the shared reader, and the other reuses it.
- Uses the placer's existing connection, config discovery and redaction; never
  prints server values; exits non-zero on any error.

### 6.8 Other `exec-ashlar` edits

- `SKILL.md`: the modes table gains `test <project>`; the build report
  mentions verdicts; the hard rules cover test loads.
- `execution.md`: "Liquids and redstone" rewritten (resting states, start
  inputs, test inputs, no nudges); the gate additions (§6.5); recovery (§6.6).
- `verification.md`: a redstone section with the full-read `diff` for `built`
  and a pointer to `test`.
- `registry.md`: the `verdicts` key.
- `plan-format.md`: the `tests` table and its validation.
- `commands.md`: no new forms; a note that `load` rows are world-changing
  commands shown at the gate, with an example.

## 7. Calibration findings flow back

Rung 0 (§9.3) tests the assumptions in findings 4, 6 and 9 and the dust-shape
rule. It runs after the merge (§10.1). If a result differs from what this spec
assumes, the implementer updates `ashlar-redstone.md`, the checker and this spec
in a follow-up PR before rung 1. If the result breaks the test protocol (for
example, commands do not update comparators, or hoppers stay idle in
force-loaded chunks with nobody near), stop and bring it to the user before
going on.

## 8. The resting-state checker (`redstone_rest.py`)

### 8.1 Commands

```text
python3 <skill>/scripts/redstone_rest.py check <plan.toon> [--input <x> <y> <z>]... [--background <read.json>]
python3 <skill>/scripts/redstone_rest.py diff <plan.toon> <read.json> [--loaded] [--background <pre-build-read.json>]
python3 <skill>/scripts/redstone_rest.py diff <read-a.json> <read-b.json>
python3 <skill>/scripts/redstone_rest.py containers <plan.toon>
```

- Python 3.11 or newer, standard library only, like the placer; runs in Claude
  Code and Codex.
- Reads `plan.toon`, its stamped phase files and the setup
  `item replace block` and `data merge block` rows. It applies phases in order
  and applies their fills before individual blocks. A phase with server-rendered
  `text` requires a hand check and exits 2. Author the lettering as fills or
  blocks when the checker needs to cover every cell.
- `--background` merges a read of the existing site (cells the plan does not
  write), for a machine built against existing blocks. For `check`, unwritten
  cells default to air and the report warns about modelled parts at the edge.
  For a plan `diff`, supply the pre-build read when a conditional fill depends
  on cells whose original states were unknown.
- `diff` against a plan compares every written cell's block and its
  non-power properties, ignoring connection-pass properties (§6.4); this is the
  `built` check. With `--loaded` it instead compares the power properties of
  every modelled component with the loaded rest state; this is the `at_rest`
  check. `diff` of two reads compares the power properties of the modelled
  components in both reads (the `rest` rows).
- `containers` lists the supported containers written by the plan. Use the
  full read to find existing containers for `settle`, `conserve` and the
  baseline.
- `system-redstone` runs `exec-ashlar`'s scripts (`stamp.py`, and
  `ashlar_place.py read` for `--background`) by their sibling path,
  `../exec-ashlar/scripts/` from its own folder, the same way the plan format
  already points at `../design-monument/tools/voxel/`.
- Exit codes: 0 clean; 1 mismatches or structural errors; 2 invalid input;
  3 clean except for unmodelled parts, which are listed.

### 8.2 What `check` computes

1. **As built:** the resting state with the inputs as written and every
   container empty. Every written component must match it.
2. **Loaded:** the resting state after the setup loads. This becomes the
   expected baseline for `diff --loaded` and the test runs. If this circuit
   cannot settle, `check` reports the affected positions and `diff --loaded`
   exits 2 because the loaded baseline is undefined.
3. **With `--input`:** the loaded state with that input switched on (a lever
   powered, a button or plate pressed, a test-input hopper holding one item).
   The report lists every component that changes: pistons extending or
   retracting, hoppers locking or unlocking, lamps and doors.

It also reports structural errors: an extended piston without its head, a head
without its base, a head whose `type` does not match its piston, anything other
than the head in front of an extended piston, and an observer written powered.

### 8.3 What the model covers

- **Components:** the table in §5.4, plus `redstone_block`, buttons, pressure
  plates, and chests, barrels, hoppers, droppers and dispensers as containers.
- **Power:** strong and weak power. Conductive blocks come from a curated table
  seeded from the wiki's "Conductivity" page (see-through is not the test); an
  unknown block next to redstone is reported as unmodelled rather than guessed.
  Levers and buttons strongly power the block they sit on. Torches power
  adjacent dust and components, strongly power the block above, and power
  neither the block they hang on nor any other adjacent block. A block is
  weakly powered only by dust. Repeaters, comparators and powered observers
  strongly power the block in front. Redstone blocks power adjacent components
  and dust but not blocks.
- **Dust:** Java connection rules: dust points at adjacent power components on
  any side (comparators included), at repeaters only along their axis, at
  observers only from behind, and at dust one block higher or lower, unless a
  conductive block sits above the lower dust. It does not point at pistons or
  other mechanism components (that exception is Bedrock-only). Power steps
  down to lower dust only from dust sitting on a conductive block: dust on
  glass, slabs or other non-conductive blocks takes power from lower dust but
  passes none down (Java). One connection makes a line pointing both ways; two
  or more make the matching corner or junction. A lone dust is a cross in
  vanilla and a dot only if toggled. Until rung 0 says otherwise, the checker
  assumes Ashlar's connection pass behaves like vanilla's shape update: a lone
  wire written with no sides (as every stamped module wire is, because
  `stamp.py` drops them) stays a dot, and one written with all four sides stays
  a cross. A dot powers only the block below. Power drops by 1 per dust. Dust
  weakly powers the block it sits on and the blocks it points into.
- **Comparators:** compare and subtract modes; the rear input from a signal, a
  container's fullness (finding 5), or a container behind one conductive block,
  except that a block between them powered to 15 makes the comparator read 15;
  side inputs from dust, repeaters, comparators and redstone blocks.
- **Repeaters:** powered and locked states; delay does not matter at rest.
- **Quasi-connectivity:** a piston, dropper or dispenser is also powered when
  the position above it receives power.
- **Settling:** iterate from the written states (inputs and outputs as
  written), so a latch keeps the stable state it was written in, until nothing
  changes. If it does not settle within a fixed number of rounds, or repeats a
  state, report "cannot settle" and name the loop's parts: that is an
  oscillator.
- **Item stack sizes:** a small table (16 for ender pearls, eggs, snowballs,
  signs and the like; 1 for tools, minecarts and other unstackables); an
  unknown item counts as 64, with a warning.

Rules checked against the Minecraft Wiki on 2026-11-19, to seed the tests'
citations:

| Rule | Wiki page → section |
| --- | --- |
| A lone dust is a cross, a dot only when toggled; a dot powers only the block below; in Java dust does not point at pistons, and a non-conductive block passes no power down; a conductive block above the lower dust cuts a step | Redstone Dust → Redstone component (the piston and glass exceptions there are Bedrock-only) |
| Reshaping dust after placement does not update its neighbours (the BUD effect) | Redstone Dust → Redstone component |
| A block is weakly powered only by dust; weak power activates components but not dust | Redstone mechanics → Weakly powered |
| A torch strongly powers the block above, powers adjacent components, and turns off when its block is powered | Redstone Torch → Redstone component; Redstone mechanics → Weakly powered |
| A redstone block powers adjacent components and dust, not blocks | Block of Redstone → Redstone component |
| Pistons, droppers and dispensers are also activated by power at the block above them; that activation can wait for a block update | Redstone mechanics → Quasi-connectivity |
| Container fullness formula; double chests read as 54 slots; a chest that cannot open reads 0; reading through a block powered to 15 gives 15 | Redstone Comparator → Read blocks, Fullness of containers |
| Sugar cane adds a block after 16 random ticks (about 18 minutes on Java), even in the dark | Sugar Cane → Farming |
| Force-loaded chunks get random ticks; mob spawning needs a player within 8 chunks | Tick → Chunk tick |

### 8.4 What it does not model

Timing and pulse lengths, delay-dependent order, piston movement and block
pushing, update order and BUD states, observers firing, entities, randomness,
scheduled ticks, comparators reading non-containers (cake, cauldrons, item
frames and the like), sculk, copper bulbs, crafters, rails, tripwire, daylight
detectors, target blocks and lecterns. Any of these next to the modelled circuit
is listed as "check by hand", never guessed.

### 8.5 Report

A summary line, then:

- mismatches as `x y z  written <state>  expected <state>  because <reason>`;
- structural errors;
- loops that cannot settle;
- unmodelled parts;
- with `--input`, the changes.

### 8.6 Tests

`tests/ashlar/test_redstone_rest.py`: at least one test per rule, each with a
comment citing its source (wiki page and section, with the date read). Fixtures:

- one sorter slice: 22 items read 1, torch lit, output hopper locked; 23 items
  turn the torch off;
- a 2×2 door at rest and with its lever on;
- a clock with an off switch (settles when off; cannot settle when on) and
  without one (cannot settle);
- quasi-connectivity;
- each piston-head error;
- rotation: the same module stamped at 0, 90, 180 and 270 degrees and mirrored
  gives the same verdicts.

## 9. Benchmarks

### 9.1 Location and file format

`docs/benchmarks/redstone/README.md` holds the ladder, the run protocol and the
results format. Each rung has its own file: `00-calibration.md`,
`01-sorter.md`, `02-door-2x2.md`, `03-cane-farm.md`, `04-clock.md`,
`05-door-3x3.md`. A rung file holds:

- **Prompt:** the request as the user would type it.
- **Site constraints:** footprint limits and facing, if any.
- **Test quantities:** fixed item types and counts.
- **Pass criteria:** numbered and observable.
- **Who tests what:** agent or user.
- **Variants** (§9.9).

A rung file never holds coordinates, layouts or schematics. The prompts below
are drafts; the user may edit them.

### 9.2 Run protocol

1. Start a fresh session (Claude Code or Codex) in the workspace root and paste
   only the prompt. The agent must not read `docs/benchmarks/` during a run;
   the skill never points there, and the runner checks the transcript.
2. The agent surveys and picks a scratch site away from players and other
   builds (no `bbox` overlap in `registry.json`), or uses a site the runner
   names.
3. The runner approves or refuses at each gate, as for any build.
4. After the report, record the result in
   `.minecraft-builder/benchmarks/redstone-results.md` in the workspace, not the
   repo: date, rung, variant, client and model, the server and Ashlar versions
   from `mc_status`, the four verdicts, each criterion with its evidence,
   snapshots used, fix rounds and notes.
5. Roll the machine back with `exec-ashlar rollback <project>` once the result
   is recorded, unless the runner keeps it.

### 9.3 Rung 0: calibration

A throwaway build, written by the implementer as an ordinary plan (it tests
Ashlar, not the agent's reasoning), placed in a scratch area away from players.
It checks:

| # | Check | Expected | If different |
| --- | --- | --- | --- |
| 1 | A lone dust, and dust with one and two connections, after Ashlar's connection pass | Record the lone dust's shape (dot or cross); lines point into the block they power | Update the dust rule in §5.4 and the checker |
| 2 | A comparator behind a hopper, with dust after it; `item replace block` 23 items into the hopper | The comparator outputs 2 and the dust re-powers | Stop and bring it to the user (§7) |
| 3 | A hopper chain inside a force-load with nobody within 128 blocks; load 10 items into the top hopper | All 10 reach the chest within about 10 s | Stop and bring it to the user (§7) |
| 4 | An extended sticky piston with its head, a torch, a repeater and a lamp written in states consistent with their power | They read back unchanged after 60 s | Note what Paper changes |
| 5 | A torch written `lit=false` on an unpowered block (deliberately wrong) | It stays unlit, and `check` flags it | Record it |
| 6 | Two same-facing chests side by side; two barrels side by side | The chests pair, the barrels stay separate | Update the chest rule |
| 7 | A hopper written `enabled=false` under a lit torch, with items above it | It moves nothing | Record it |

Rung 0 writes to the world, so it goes through the gate like any build, and it
is rolled back afterwards.

### 9.4 Rung 1: two-item sorter with overflow

- **Prompt (draft):** "Build a compact item sorter fed from one input chest.
  Cobblestone goes to one chest, oak logs to another, and anything else ends up
  in an overflow chest."
- **Test quantities:** batch 1: 40 cobblestone, 40 oak logs, 20 dirt.
  Batch 2: 64 cobblestone, 17 oak logs, 33 dirt. Both are loaded into the input
  chest with `item replace block` rows from the approved plan.
- **Pass criteria:**
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
- **Who tests:** the agent, for everything. Manual: `n/a`.

### 9.5 Rung 2: 2×2 sticky-piston door

- **Prompt (draft):** "Build a 2×2 sticky-piston door in a wall, opened and
  closed by a lever beside it."
- **Pass criteria:**
  1. Ashlar only, as in rung 1.
  2. At rest, closed: `check` clean; with `check --input` on the lever, every
     piston that should move does.
  3. **Ten guided cycles:** after each flip, the agent reads the door. Open:
     the four doorway cells are air and the pistons are in their open states.
     Closed: the four door blocks are back in place and the pistons are in their
     rest states.
  4. After ten cycles, the `rest` check is clean: no door block missing,
     displaced or dropped, and no piston extended without its block.
- **Who tests:** the user flips the lever; the agent confirms each state. If the
  user accepted a test input, the agent also runs ten cycles itself, but this
  rung still needs the user's ten cycles.

### 9.6 Rung 3: observer sugar cane farm

- **Prompt (draft):** "Build an automatic sugar cane farm that harvests with
  observers and pistons and collects into a chest."
- **Pass criteria:** Ashlar only and at rest, as above. Then, with the chunks
  force-loaded or the user nearby, the chest receives at least 8 cane within the
  test's timeout (about an hour). No stalk grows past the cut height. Between
  harvests the pistons are retracted, and the `rest` check is clean.
- **Who tests:** the agent, during a long `await`.

### 9.7 Rung 4: controllable clock

- **Prompt (draft):** "Build a redstone clock I can switch on and off with a
  lever, pulsing about once every two seconds."
- **Pass criteria:** Ashlar only, as above. Off: at rest, and `check` settles.
  With `check --input` on the switch, it reports "cannot settle" for the clock
  loop, as expected for an oscillator. On (by the user, or by a test input):
  the output changes across repeated reads. With a pulse counter, the period is
  within 10% of the target over at least 30 pulses. Switched off, it returns to
  rest within one period, and the `rest` check is clean.
- **Who tests:** the user's switch, or the agent with a test input and pulse
  counter if accepted.

### 9.8 Rung 5: 3×3 piston door

- **Prompt (draft):** "Build a 3×3 piston door, flush with the wall when
  closed, opened and closed by a lever."
- **Pass criteria:** as in rung 2, with all nine doorway cells clear when open
  and all nine blocks back when closed, over ten cycles. The plan notes say
  whether the design depends on update order.

### 9.9 Variants, once a rung passes

- **Orientation:** the same prompt with the machine facing each other
  direction, and a mirrored layout. Same criteria.
- **Footprint:** the same prompt with a tighter space limit (each rung file
  names one). It passes if the machine meets the same criteria, or if the agent
  explains clearly why it cannot fit, with the smallest space it would need.
- **Recovery A, stopped build:** the runner stops a build after its first phase,
  by refusing the next gate or ending the session. A fresh session must find the
  project in the registry, report what was built, and resume or roll back
  cleanly when asked.
- **Recovery B, planted fault:** after a pass, the runner breaks one component
  in game (for example removes a torch or turns a repeater). For an agent-tested
  rung, the agent must find the fault through a failed test and fix it through a
  gate within three fix rounds.

## 10. Install, docs and housekeeping

### 10.1 Order: merge first, then live runs

The user chose this order over a temporary lab workspace:

1. Implement on `redstone`; pass the static and script checks and the offline
   dry runs (§11.1–11.4).
2. Open the implementation PR and merge it, each step only with the user's OK.
3. With the user's OK, check out the merged `main` in the clone and create the
   `system-redstone` links (below). From then on every session in the
   workspace loads the new `system-redstone` and `exec-ashlar`.
4. Run rung 0, then rung 1, then rung 2 in the main workspace (§11.5).
5. Land each fix the live runs need as a follow-up PR on its own branch, with
   the same checks.

Until step 3, nothing in the workspace sees the branch's skills, so the
offline dry runs follow the worktree's skill files by path (§11.3).

### 10.2 Links, docs and housekeeping

- **Workspace links**, outside the repo:
  `.claude/skills/system-redstone` and `.agents/skills/system-redstone`, each
  pointing to `../../ashlar-design-skills/skills/system-redstone`. They expose
  whatever branch the clone has checked out, so create them only once the clone
  has the ported skill checked out, and with the user's OK. A link made earlier
  would serve Chapman's unported skill, and the design skills would start
  handing contraptions to it.
- `CLAUDE.md` fork note: nine skills target Ashlar, `system-redstone` among
  them; the test command is unchanged.
- `skills/TAXONOMY.md` and `README.md`: say the fork's `system-redstone` targets
  Ashlar.
- `tests/ashlar/test_skill_text.py`: add `system-redstone` to `SKILLS`, so the
  Chapman-name and labelled-line checks apply to it; add the Chapman tool names
  from finding 2 that the current list lacks.
- The design skills' "if `system-redstone` is installed" lines stay as they
  are; they still read correctly once it is installed.
- The terrain branch edits the same `SKILLS` list and fork note, and may add a
  column backup subcommand to `ashlar_place.py` that reads columns the same way
  `read` does. The two should share one column-reading routine: whichever
  branch lands first owns it, and the other reuses it. Whichever branch merges
  second rebases and resolves the conflicts.
- No version bump or CHANGELOG entry (sub-project 1 made none).

## 11. Testing and verification

1. **Static:** `test_skill_text.py` over the nine skills (Chapman names,
   frontmatter, labelled lines), and `node scripts/validate-plugin.mjs`.
2. **Scripts:** `test_redstone_rest.py` (§8.6); `ashlar_place.py read` against
   the fake MCP server (tiling, parsing states with brackets and runs, errors,
   no server values in output). All existing tests stay green:
   `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q`.
3. **Dry runs** (no world writes, before the merge): run `system-redstone` up
   to its gate on the rung 1 and rung 2 prompts. The workspace's skill links
   still serve the clone's old skills at this point, so the dry run follows the
   worktree's `skills/system-redstone/SKILL.md` and
   `skills/exec-ashlar/SKILL.md` by path, the documented fallback for a skill
   that is not installed (`exec-ashlar/reference/clients.md`). In Claude Code,
   the workspace's read-only `ashlar-dry-run` agent drives it; it has no shell,
   so the main session then runs `stamp.py` and `redstone_rest.py check` on the
   plan it wrote (both offline). The plans must pass validation and `check`.
   If the terrain branch's shell-capable dry-run variant lands first, it may be
   reused once its allowed commands also cover `stamp.py` and
   `redstone_rest.py`, and still exclude every world-changing command (`place`,
   `restore`, anything that force-loads).
4. **Live, read-only:** `ashlar_place.py read` on a small area.
5. **Live writes**, after the merge (§10.1), each through the gate, asked first
   because players may be online: rung 0, then rung 1, then rung 2 (§9), in
   fresh sessions in the main workspace.

## 12. Out of scope

- The non-goals in §1.2.
- Running rungs 3–5 and the variants (written now, run later).
- Changes to the user's permission settings.
- The `wss://` migration and an HTTP transport for the placer.

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| The checker's model is wrong: false "clean" results or false alarms | One test per rule with a cited source; rung 0; every live run cross-checks it with `diff --loaded` and the `rest` rows; unmodelled parts are listed, never guessed |
| Rung 0 contradicts an assumption the test protocol needs | Stop and bring it to the user before rung 1 (§7) |
| A design depends on update order and fails when rotated | The skill prefers order-independent designs and notes dependencies; the orientation variants test it |
| Each live run evicts other builds' rollback points | The gate names what is evicted; space the runs; roll benchmarks back when recorded |
| Long force-load holds (cane farm) | Bounded by the test's timeout, always paired, released on failure |
| A test input left in a build is used by a player | Hidden placement; listed in the plan notes |
| Manual tests depend on the user being available | The `manual` verdict stays `pending`; it is never assumed |
| The agent misreads `data get block` output | Counts are small, and `conserve` catches mistakes; a parser can come later |
| Merge conflicts with the terrain branch | Small, in shared lists; the second branch rebases |
| Merging first makes skills that have not yet run live what every workspace session loads | Rung 0 runs before any real contraption build; until rungs 1–2 pass, reports say the skill is unproven live; fixes land promptly as follow-up PRs |

## 14. Left to the builder

- Exact `tests` syntax beyond §6.1 (for example how a `repeat` nests), default
  timeouts and the wait between reads.
- Whether `read` writes air cells, and the JSON details.
- The checker's internals, the breadth of its conductive-block and stack-size
  tables beyond the benchmark parts, the report wording, and an optional
  `--json` output.
- Wording and structure of the reference files, within §5.
- Rung 0's exact layout.
