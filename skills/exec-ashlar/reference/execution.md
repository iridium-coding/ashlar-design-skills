# Execution

## Approval gate

Before the first write, show the user:

- the project, world and bounding box;
- the phases in order, each with its cell count, its `via`, and the snapshot
  tiles it needs;
- the total snapshot slots needed, and what they evict. Call `mc_snapshot` with
  `action: "list"` and count the stored snapshots. If stored + needed is more
  than 20, the oldest (stored + needed - 20) snapshots are evicted, oldest
  first. Name each one (id, label, age), say they belong to other builds'
  rollback points, and offer to split the build, wait, or accept. Also, if the
  build needs more than 20 slots, its own oldest phases' snapshots are evicted
  before it ends, so those phases cannot be rolled back; say so. Count one slot
  for each `commands` phase that runs `place feature`;
- any other registry project whose `bbox` overlaps this build's box (a build
  over another build overwrites it);
- every console command, exactly as it will run, with the `minecraft:` prefix;
- every force-load the `commands` phases add and remove, and which chunks;
- for a plan outside the server's main world: that its console steps need
  `execute in <dimension> run`, and whether the user agreed;
- what a rollback cannot restore: entities, sign text and container contents,
  including any block entities the survey found inside the build area;
- the players online and how close they are;
- anything the user must do in game afterwards (a redstone start lever).

Wait for an explicit yes. Then set `approved:` in `plan.toon` to today's date
and the registry status to `building`.

## Each phase

1. **Players**: call `mc_players`. If anyone is inside the phase's box grown by
   2 blocks, stop and tell the user. Do not build around them.
2. **Snapshots**:
   - `placer` phases: the placer takes them (`--snapshot`).
   - `mcp` phases: tile the phase box into boxes of at most 200,000 cells
     (`ashlar_place.py plan` reports the tile count) and call `mc_snapshot`
     with `action: "create"` for each, labelled with the project and phase. For
     a single small box, `mc_build`'s own `snapshot: true` does the same.
   - `commands` phases: snapshot the box only when a command changes blocks
     (`place feature`).
   Record every snapshot id in `build-log.md` and the registry.
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
   - `commands`: one `mc_command` call per row, in order, exactly as written,
     with the `minecraft:` prefix added. A phase with console commands that name
     a position or an entity starts with its `forceload add` row and ends with
     the matching `forceload remove` row (`commands.md`); if the phase stops
     part way, run the remove before reporting.
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
  call.
- Redstone does not update when placed. Every contraption needs a start lever
  or button; tell the user what to flip.

## Rollback

0. `mc_players`. If anyone is inside any box to be restored, grown by 2
   blocks, stop and tell the user.
1. Show the user the snapshots to be restored (ids, labels, boxes) and any
   recorded snapshots that were evicted and cannot be restored. Wait for an
   explicit yes. Then `mc_restore` each recorded snapshot, newest phase first.
2. Remove the build's entities: `forceload add` over the columns the plan's
   entity phases used, `kill @e[tag=ashlar.<project>]`, confirm with
   `execute if entity @e[tag=ashlar.<project>]` (`Test failed`), then
   `forceload remove` the same columns. If any of these calls fails, still run
   the `forceload remove` before reporting.
3. Tell the user that sign text and container contents inside restored boxes
   are gone, including ones that were there before the build, which phases'
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
