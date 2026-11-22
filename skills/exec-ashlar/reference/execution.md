# Execution

## Approval gate

Before the first write, show the user:

- the project, world and bounding box;
- the phases in order, each with its cell count, its `via`, and the snapshot
  tiles it needs;
- the total snapshot slots needed (`backup` phases need none), and what they evict. Call `mc_snapshot` with
  `action: "list"` and count the stored snapshots. If stored + needed is more
  than 20, the oldest (stored + needed - 20) snapshots are evicted, oldest
  first. Name each one (id, label, age), say they belong to other builds'
  rollback points, and offer to split the build, wait, or accept. Also, if the
  build needs more than 20 slots, its own oldest phases' snapshots are evicted
  before it ends, so those phases cannot be rolled back; say so. Count one slot
  for each snapshot-rollback `commands` phase that runs `place feature`. For a
  snapshot phase whose snapshots would evict other builds' rollback points,
  offer to switch it to a column backup;
- per `backup` phase: its box, the number of column reads and the estimated
  disk size, instead of snapshot slots;
- per commands file: its path (so the user can open it), the count per form and
  per feature id, the force-load tiles with their chunk counts, and what
  happens when a tree fails to grow (the runner continues and lists it; exit
  6). Not every line;
- a biome change: the user's recorded yes, the box, and its approximate
  rollback. The probe records one biome per chunk, so the reset is at chunk
  resolution, and chunks the probe cannot identify keep the new biome; if any
  chunk is `unknown` at build time the biome phase stops for the user;
- the non-natural blocks found inside the terrain box (from the site read);
- how many existing trees will be removed whole, and the farthest any write
  reaches outside the terrain box;
- an estimated duration for big jobs;
- any other registry project whose `bbox` overlaps this build's box (a build
  over another build overwrites it);
- every ordinary console command in a `commands` phase, exactly as it will
  run, with the `minecraft:` prefix;
- each `commands` phase's exact eligible force-load chunks in the approved
  world or dimension. The gate authorizes adding only eligible chunks absent
  from the pre-phase query and removing only the phase's confirmed additions;
- every test `load` command exactly as it will run;
- the exact chunks each agent test may force-load and its maximum hold time.
  Add only chunks the pre-run query shows are absent and remove only
  confirmed additions. Include the expanded row timeouts and bounded time
  for force-load calls, baseline reads, console steps, verification and
  cleanup. Show the combined budget when tests share a force-load, with
  enough time reserved to remove and verify the run's additions;
- any test input or fixture, and where it is;
- the manual steps the user will be asked to do;
- what will remain unverified;
- for a plan outside the server's main world: that its console steps need
  `execute in <dimension> run`, and whether the user agreed;
- what a rollback cannot restore: entities, sign text and container contents,
  including any block entities the survey found inside the build area;
- the players online and how close they are;
- anything the user must do in game afterwards (a redstone start lever).

Wait for an explicit yes. Then set `approved:` in `plan.toon` to today's date
and the registry status to `building`.

## Test-only approval

If a built project's test rows or their execution scope change and all build
phases stay the same, validate the revised tests and show their scope at a
fresh gate. Include the exact commands, eligible chunks, hold budget, user
steps and the results that need a new test. Wait for an explicit yes, update
`approved:` in `plan.toon` and record the approved test scope in
`build-log.md`. Keep the registry status `built` and run only the approved
tests.

## Sizing backup phases

For each `backup` phase, from its box: the column reads are
`ceil(columns / 1,024)` or more when the box is taller than 195 blocks (each
read covers at most 200,000 cells), and the disk size is estimated from the
column count (the runs compress well; say it is an estimate). Show both at the
gate. `ashlar_place.py backup` and `place --backup` do the reading; a backup is
complete only when its `manifest.json` says so.

## Each phase

1. **Players**: call `mc_players`. If anyone is inside the phase's box grown by
   2 blocks, stop and tell the user. Do not build around them.
2. **Rollback point**, by the phase's `rollback` column (absent: `snapshot`):
   - `backup` phases: `place --backup <folder>` takes the backup after its
     player check and before writing (an `mcp` phase runs `backup` first, then
     its own `mc_build`). The folder is
     `.minecraft-builder/<project>/backups/<NN>-<phase-name>/`. The placer
     refuses (exit 3) if the folder already holds a complete backup, or if the
     backup cannot be completed; nothing is written then. Record the folder.
   - `biome` phases: run `biome-probe` over the phase's box immediately before
     the phase and record the probe file. Stop for the user if any chunk is
     `unknown`.
   - `placer` phases: the placer takes snapshots (`--snapshot`).
   - `mcp` phases: tile the phase box into boxes of at most 200,000 cells
     (`ashlar_place.py plan` reports the tile count) and call `mc_snapshot`
     with `action: "create"` for each, labelled with the project and phase. For
     a single small box, `mc_build`'s own `snapshot: true` does the same.
   - `commands` phases: take the rollback point only when a command changes
     blocks (`place feature`). Its box is the feature positions grown by the
     reach of the largest tree it plants (default: 8 blocks sideways and 32
     up); that box is the phase's `from`/`to`.
   Record every snapshot id, backup folder and probe file in `build-log.md`
   and the registry.
3. **Place**:
   - `mcp`: one `mc_build` call with the phase file's contents.
   - `placer`:
     `python3 <skill>/scripts/ashlar_place.py place <file> --snapshot --label "<project> phase <n>" --log .minecraft-builder/<project>/placer.log`,
     adding `--world <name>` when the plan names a world. Exit 4: a player is
     in the area, or the player list could not be read. Exit 2: the phase file
     is invalid. Exit 3: the file needs more snapshots than allowed, or a
     shell fill (`outline`, `hollow`, `walls`) is too large to split; split it
     into smaller phase files or fills. Exit 5: the server failed part way; the
     report lists the pages already written and the snapshot ids.
   - `commands` with a commands file: run
     `python3 <skill>/scripts/ashlar_place.py commands <file> --progress .minecraft-builder/<project>/phases/<file>.progress --log .minecraft-builder/<project>/placer.log`,
     adding `--world <name>`, and `--dimension <dim>` only when the user agreed
     at the gate. The runner applies the prefix, force-load and player rules
     itself ([commands.md](commands.md#the-runner)). Exit 6: the run finished
     but some commands failed; the report lists them. Exit 5 also covers a
     force-load it could not remove: release those chunks first. Exit 4: a
     player is in a tile.
   - `commands` with `file` set to `-`: run ordinary rows in order, one exact approved
     `mc_command` per row, with the `minecraft:` prefix and any approved
     dimension wrapper. Use `forceload query` before adding chunks. Use the
     approved range when every eligible chunk is absent. If the range
     contains pre-existing loads, split it into per-chunk commands for the
     missing eligible chunks only ([commands.md](commands.md#rules)).
     Log each call before sending it and record its response or uncertainty.
     At phase end or interruption, remove only this phase's confirmed
     additions. Check the result with `forceload query` and report any
     unresolved chunks. Return to the approval gate before changing the
     commands, eligible chunk set or dimension.
4. **Warnings**: every line under `WARNINGS` is an attached block without
   support. Fix them with another `mc_build` call before moving on.
5. **Look**: `mc_render` top view, plus the facade the phase changed most.
6. **Record**: append the phase to `build-log.md` and the registry.

## Ordering rules

- Clear with air first, then structure, then attached blocks (torches, ladders,
  signs, doors, carpets, banners) once what they attach to exists.
- Later phases never undo earlier ones.
- Block-entity data (`data merge block`, `item replace block`) comes after its
  block exists, and runs inside a paired `forceload add` / `forceload remove`
  over its columns.
- Entities (`summon`) come last, after all blockwork, so fills do not disturb
  them, inside a paired `forceload add` / `forceload remove` over their
  columns.

## Liquids and redstone

- Water and lava are placed still. Use `liquids: "flow"` only for a few source
  blocks (a fountain head, a waterfall source): at most 2,000 flowing blocks per
  call. The placer enforces the cap: it pages so no page holds more than 2,000
  water or lava cells (`--max-flowing`), and `plan` reports `liquid_cells`.
- Ashlar places redstone without physics. Write each component in its resting
  state with inputs as built (normally off) and containers empty. Load setup
  containers in a `commands` phase so their comparators receive real updates.
  The connection pass sets shape properties.
- A machine driven by game events starts once its chunks tick. A machine
  driven by a player input or its own clock needs the user. Build clocks with
  an off switch set to off. Show any approved test input at the gate and tell
  the user which real input to operate.
- Never nudge or reset a circuit by writing redstone blocks, levers or torches
  with `mc_build`. Never place blocks through the console. See the
  [Ashlar redstone placement rules](../../system-redstone/reference/ashlar-redstone.md).

## Resuming and fixing

- **A project found `building`** (a phase stopped part way): show which phases
  are recorded as placed, ask the user whether to resume or roll back, and on
  a resume continue from the first phase not recorded as placed. This section
  is the one resume rule; the bullets below apply it per phase kind.
- **An interrupted block placement** (placer exit 5, an MCP error, the user
  stops it): record the known writes and snapshot ids. Confirm that replaying
  the fills and blocks would produce the same final cells. When it would,
  offer to resume from the start or roll back and ask before either. Resume
  using the original rollback point without taking a new one (`--no-snapshot`
  for the placer, omit `snapshot` for `mc_build`). A point taken after a
  partial write records the partial state, so the interrupted phase keeps the
  one taken before its first write (its backup, snapshots or biome probe) and
  is placed again from the start. `place --backup` refuses to overwrite a
  complete backup, so never rerun it with `--backup` on the same folder. The
  resume gate says if any of the phase's original snapshots has been evicted
  since, and which part can no longer be rolled back. If replay could produce a different result,
  for instance with overlapping conditional fills, reconcile the partial
  writes first and show the exact remaining writes, restore or correction at
  a fresh gate.
- **An interrupted `commands` phase:** release this phase's confirmed
  force-load additions. Reconcile each confirmed or uncertain operation
  against the console log and observed state. Use the available block,
  inventory and tagged-entity reads.
  Never replay summons, feature placement or inventory loads wholesale.
  A runner commands file resumes with the same `--progress` file: the runner
  skips every command already attempted, and still reports (exit 6) commands
  that failed in an earlier run. That is the reconcile step for feature
  placement. A progress file from a different commands file is refused. The
  runner always pairs its force-load adds with removes, even after a failure;
  if it reports a force-load it could not remove (exit 5), release that first.
  A resumed biome phase reuses its original probe file and never probes again
  after a partial `fillbiome`: the probe taken before the first write is the
  only record of the old biomes.
  Show the precise remaining commands or recovery actions at a fresh gate
  and wait for approval before continuing.
- **A failed test:** [`system-redstone`](../../system-redstone/SKILL.md)
  [diagnoses it](../../system-redstone/reference/verification.md#correction-catalog).
  The fix is a new phase holding only the changed blocks, added to `plan.toon`,
  validated, and shown at a new gate as a list of the cells it changes. Then
  snapshot, place and test again. Mark the tests affected by the fix
  `pending` until rerun. After three failed fix rounds the skill stops and
  recommends a rollback or a redesign.
- **A test that fails part way** records what it saw. When the run ends or
  reaches its cleanup cutoff, release only its own force-load additions
  within the reserved time. If cleanup cannot be confirmed, report the
  affected chunks.

## Rollback

0. `mc_players`. If anyone is inside any box to be restored, grown by 2
   blocks, stop and tell the user.
1. Show the user the rollback points to be restored: snapshots (ids, labels,
   boxes), backup folders with their sizes, biome probes with the approximate
   biome reset (chunk resolution; chunks the probe marked `unknown` are
   skipped and keep the new biome), and any recorded snapshots that were
   evicted and cannot be restored. Wait for an explicit yes. Then restore
   newest phase first: biome phases with `biome-restore <probe> --out <file>`
   and the runner on that file; backup phases with
   `python3 <skill>/scripts/ashlar_place.py restore <folder>` (placing the same
   backup twice gives the same result); snapshot phases with `mc_restore`.
   If the project is a host with a `<host>-ground` project, offer to roll the
   grounding project back first.
2. Remove the build's entities: `forceload add` over the columns the plan's
   entity phases used, `kill @e[tag=ashlar.<project>]`, confirm with
   `execute if entity @e[tag=ashlar.<project>]` (`Test failed`), then
   `forceload remove` the same columns. If any of these calls fails, still run
   the `forceload remove` before reporting.
3. Tell the user that sign text and container contents inside restored boxes
   are gone (a backup restores every block state exactly but loses what a
   snapshot loses), including ones that were there before the build, which phases'
   snapshots were evicted and could not be restored, and that entities which
   wandered outside the force-loaded columns may survive the `kill`.
4. Set the registry status to `rolled-back`.

## build-log.md

Append one section per phase:

```markdown
## Phase 2: houses (2026-11-17 21:10)
- via: placer; cells: 41750; pages: 1
- snapshots: snap-20261117-…
- warnings: none
- look: the top view matches the layout
```
