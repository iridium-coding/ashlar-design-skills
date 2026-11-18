# Ashlar design skills — sub-project 1: foundation and design skills

- **Date:** 2026-11-17
- **Status:** design approved in conversation; revised the same day for
  project-local installs, Codex support and labelled client-specific tools;
  awaiting review
- **Upstream base:** `chapmanjw/minecraft-java-fabric-claude-plugin` Release 1.2.0 (`b4bea4a`, MIT)
- **Backend:** Ashlar 0.4.9 (`ashlar-mcp` + Paper plugin, AGPL-3.0) on Paper 26.3
- **Sub-projects:** 1 (this spec) foundation + design skills · 2 terrain · 3 redstone

## 1. Goal

Make Chapman's six design skills — `design-building`, `design-house`,
`design-city`, `design-village`, `design-grounds`, `design-monument` — work in
Claude Code and Codex with Ashlar as the only world backend. Each skill keeps its design
knowledge and its interview → blueprint → approval loop, and then builds through
Ashlar's nine `mc_*` tools instead of Chapman's Fabric MCP and execution
pipeline.

### Success criteria

1. Each design skill runs end to end — survey, interview, blueprints, approved
   plan, build, verify — with no reference to a Chapman component that is not
   installed. The only named siblings that may be absent are `terrain-shape`,
   `terrain-landmark` and `system-redstone`, and each has a defined interim
   fallback (§7.3).
2. No world write happens before the user approves the plan. Every write phase
   is preceded by a player check and snapshots. Every console command matches
   the allowlist (§5.5) and is listed in the approved plan.
3. Generated geometry (voxel models, stamped modules, pixel art) reaches the
   server through the placer script without the model transcribing it.
4. The adapted skills live in the user's fork and are linked into the
   workspace as project skills for both Claude Code and Codex. The skills CLI
   no longer manages them, so `skills update` cannot replace them, and Chapman
   releases are merged with git.
5. All checks in §9 pass.
6. Codex, started in the workspace root, finds and can follow the same skills
   without a Codex-specific copy of the text.

## 2. Findings that shape the design

**Installed state before this work.** The six skills were global copy-mode
installs from the skills CLI in `~/.claude/skills` and `~/.agents/skills`,
byte-identical to Release 1.2.0 and tracked in the CLI's lock file as
GitHub-backed from Chapman's repo. They were removed on 2026-11-17 (§4).

**What the design skills depend on but did not get.** Every skill hands work to
leaves that were never installed: `survey-site`, `survey-research`, `exec-plan`,
`exec-blueprint`, `exec-worker`, `exec-inspect`, `exec-reflect`,
`terrain-shape`, `terrain-landmark`, `system-redstone`, the
`minecraft-mcp-setup` and `minecraft-builder` agents, files under
`${CLAUDE_PLUGIN_ROOT}`, and (for `design-monument`) the Python voxel toolkit.
Today the skills stop partway.

**Ashlar capabilities.** Nine tools: `mc_status`, `mc_players`, `mc_survey`,
`mc_render` (PNG views: top, facades, slices, heightmap), `mc_build` (fills,
individual blocks with sign text, rendered lettering), `mc_inspect` (stats,
per-column runs, ASCII slices), `mc_snapshot`, `mc_restore`, `mc_command`
(console).

**Ashlar does not provide:** structure templates or clone, entity tools,
block-entity data other than sign text, biome lookup, data storage, datapack
functions, loot-table generation.

**Ashlar behavior that matters:**

| Property | Value (defaults; this server matches) |
| --- | --- |
| Blocks per `mc_build` call | 500,000 |
| Chunk footprint per write call | 1,024 chunks |
| Read volume (`mc_inspect`, side/slice renders) | 200,000 cells |
| Flowing liquids per call (`liquids: "flow"`) | 2,000 |
| Queued operations | 16 |
| Snapshots | 20 slots, oldest evicted first, 200,000 blocks each |
| Allowed worlds | `world.allowed-worlds` (this server: overworld only) |

- `mc_build` runs, in order: snapshot (if requested), fills, text, blocks. If
  the requested snapshot box exceeds the snapshot cap, the whole call fails
  before writing.
- Blocks are written with physics off. A connection pass fixes fences, panes,
  walls and stairs; attached blocks without support come back as warnings.
- Snapshots do not capture block-entity contents (sign text, container items)
  or entities. A restore loses them, including ones that existed before the
  build.
- `mc_render` returns images, so the model can look at the result. Chapman's
  skills were written for a backend where it could not.
- `ashlar-mcp` logs `connecting to <plugin URL>` on stderr.

**Claude Code.** Personal skills (`~/.claude/skills`) override project skills
with the same name, so project copies only load once global copies with the
same names are gone. Project skills are read from `.claude/skills` in the
session's working directory, and symlinked skill folders work. Frontmatter
supports `model`, `effort` and `disable-model-invocation`; `${CLAUDE_SKILL_DIR}`
resolves to the skill's own folder.

**Codex.** Repo-scoped skills are read from `.agents/skills` in every directory
between the project root and Codex's working directory, and directory symlinks
are followed. The frontmatter parser reads only `name`, `description` and
`metadata.short-description` and ignores other keys, so Claude-only fields are
harmless. Codex configures MCP servers in `~/.codex/config.toml`
(`[mcp_servers.<name>]` with `command`, `args`, `env`); this machine has an
`ashlar` entry there too.

**skills CLI.** `skills update` checks GitHub-backed lock entries; when a skill's
upstream folder hash changes it deletes and re-copies that skill into every
detected agent directory. Lock entries are per skill name, not per agent.
Project installs target `.claude/skills` (Claude Code) and `.agents/skills`
(Codex).

**Local tooling.** Python 3.15 without numpy or Pillow; `uv` 0.13.8; Node 26;
the `trafilatura` CLI.

## 3. Decisions

| Topic | Decision |
| --- | --- |
| Backend | Ashlar only: `mc_*` tools plus the local placer script |
| Console commands | Fixed allowlist (§5.5); every command that changes the world is listed in the approved plan; never used to place blocks or to get around a limit |
| Generated geometry | Local placer script that drives `ashlar-mcp` over stdio |
| Source of truth | Public GitHub fork `iridium-coding/ashlar-design-skills` (created 2026-11-17), cloned into the workspace |
| Install | Project skills only: relative symlinks from the workspace's `.claude/skills/` and `.agents/skills/` into the clone; global copies removed |
| Agents | Claude Code first; Codex supported through agent-neutral skill text, keeping Claude-only frontmatter extras because Codex ignores them |
| Structure | One shared executor skill, `exec-ashlar`, plus targeted edits to the design skills |
| Scope | This spec covers sub-project 1. Terrain (`terrain-shape`, `terrain-landmark`, terrain references and toolkit) and redstone (`system-redstone`) are sub-projects 2 and 3, each with its own spec, planned after this one is merged |
| Terrain and redstone use | In scope whenever the agent judges the prompt calls for them |

## 4. Repository, workspace and install

- **Fork:** `iridium-coding/ashlar-design-skills`, public, created 2026-11-17
  with `main` at `b4bea4a`.
- **Workspace** (`~/Development/Minecraft`):

  ```text
  Minecraft/
    ashlar-design-skills/   the clone: origin = fork, upstream = Chapman (push disabled)
    <server folder>/        the Paper server's files, backups and related tools
    .claude/skills/<name>   -> ../../ashlar-design-skills/skills/<name>   (Claude Code)
    .agents/skills/<name>   -> ../../ashlar-design-skills/skills/<name>   (Codex)
    .minecraft-builder/     project state (§5.7), created on first use
  ```

- **Branches:** work happens on `ashlar`, branched from `b4bea4a`. A PR from
  `ashlar` into the fork's `main` is reviewed and merged after §9 passes. Every
  push and the merge need the user's go-ahead at the time. If upstream moves
  meanwhile, merge it as a separate step.
- **Changed or added in the fork:**
  - `skills/design-{building,city,grounds,house,monument,village}/` — edited (§7)
  - `skills/exec-ashlar/` — new (§5, §6)
  - `skills/survey-research/SKILL.md` — fetch fallback (§7.4)
  - `skills/design-monument/tools/voxel/` — vendored toolkit (§6.3)
  - `skills/TAXONOMY.md` — lists `exec-ashlar`. Upstream's
    `scripts/validate-plugin.mjs` needs no change: it checks names, prefixes and
    tier rules, not tool names, and `exec-ashlar` has the required `exec-` prefix
  - `tests/ashlar/` — tests (§9), outside skill folders
  - `docs/superpowers/specs/` and `docs/superpowers/plans/` — this spec and its plan
  - `README.md` and `CLAUDE.md` — a short note at the top of each: the fork
    adapts the design skills to Ashlar (so `mc_*` names are intended there),
    which skills are adapted, and how to link them into a workspace
- All other Chapman skills, agents and tools stay untouched, so upstream merges
  stay clean.
- **Install:** the skills are linked, not copied. The six design skills and
  `survey-research` were linked on 2026-11-17; `exec-ashlar` is linked when it
  exists. Edits in the clone are live for both agents at once, and whatever
  branch is checked out in the clone is what the agents see. The global copies
  were removed with `npx skills remove … -g`, so the skills CLI no longer
  tracks these names and `skills update` cannot overwrite them.
- **Sessions start in the workspace root.** Claude Code reads project skills
  from its working directory. Codex scans from the project root down to its
  working directory, and because the workspace is not a git repo, its root is
  wherever Codex starts.
- **Upstream releases:** `git merge upstream/main` on a branch in the clone (or
  GitHub's "Sync fork" followed by a pull); rerun the §9.1 checks after every
  merge.

## 5. The `exec-ashlar` skill

### 5.1 Layout

```text
skills/exec-ashlar/
  SKILL.md
  reference/
    tools-and-limits.md   # the nine tools, limits, orientation rules, warnings, caveats
    survey.md             # survey procedure and survey.md format
    plan-format.md        # plan.toon schema, phase JSON, quality_contract rows
    execution.md          # gate, ordering, snapshots, players, liquids, rollback
    verification.md       # acceptance and quality_contract checks with mc_inspect/mc_render
    commands.md           # console allowlist with exact command forms
    modules.md            # module JSON, stamping conventions
    registry.md           # .minecraft-builder layout and registry.json schema
    clients.md            # client-specific tools for Claude Code and Codex, with fallbacks (§7.5)
  scripts/
    ashlar_place.py
    stamp.py
```

`SKILL.md` frontmatter: `name: exec-ashlar`; a description that triggers when a
design skill hands off a survey or an approved plan, or when the user asks to
build, verify or roll back a planned build through Ashlar. No `model` or
`effort` override (the session's settings apply). `allowed-tools` pre-approves
the read-only Ashlar tools in Claude Code (§7.5).

### 5.2 Modes and workflow

Design skills hand off to `exec-ashlar` by name with a mode and a project name,
for example "use the `exec-ashlar` skill: `build <project>`". In Claude Code
that is a Skill tool call; in Codex the model opens the skill. Project names
are kebab-case (`[a-z0-9-]+`) because they become folder names and entity tags.

1. **Preflight** (every mode): `mc_status` for connection, versions and queue
   length; read `.minecraft-builder/registry.json`. If Ashlar is unreachable,
   retry `mc_status` once after a few seconds, then stop and tell the user. The
   connection is configured in `~/.claude.json`; there is no setup skill.
2. **Survey mode** (replaces `survey-site`):
   - `mc_players` when the request is relative to a player;
   - `mc_survey` over the site plus a margin; top-view `mc_render`; facades of
     anything already standing there;
   - `mc_inspect` stats on existing structures, including block entities (signs,
     chests, banners, lecterns) whose contents a restore would lose;
   - biome only when the palette depends on it, through `/execute if biome`.
   Output: `.minecraft-builder/<project>/survey.md` with bounding box, ground
   level, the largest flat zone, water and lava, existing structures, block
   entities at risk, nearby players and the biome if read.
3. **Plan validation** (start of build mode): check the plan against
   `plan-format.md` — absolute integer coordinates, Y within the world's range,
   every phase file present and within limits, snapshot slots needed, every
   command matching the allowlist, a non-empty `quality_contract`.
4. **Approval gate:** show the bounding box, total blocks, phases, every console
   command, snapshot slots needed, what a rollback cannot restore (entities,
   sign text, container contents, and any block entities found by the survey)
   and nearby players. Write nothing until the user explicitly approves. On
   approval set `approved:` in `plan.toon` to the date.
5. **Build, per phase:**
   - player check (§5.4);
   - snapshots (§5.4);
   - place: small hand-written phases through the model's own `mc_build` call
     with the phase file's contents; large or generated phases through
     `ashlar_place.py place`;
   - resolve every unsupported-attachment warning before moving on;
   - quick `mc_render` look; append to `build-log.md`.
   Entity and NBT steps run after all block phases, tagged per §5.5.
6. **Verify:** acceptance spot checks and every `quality_contract` row (§5.6),
   plus `mc_render` facades and top view compared with the approved blueprints.
   Fix and re-verify; do not report done with a failing row.
7. **Record and report:** update `registry.json`; the final report gives the
   bounding box, materials, snapshot ids and anything left for the user to do
   (for example flipping a redstone start lever).
8. **Rollback mode:** `mc_restore` snapshots in reverse phase order, then
   `/kill @e[tag=ashlar.<project>]`; tell the user what restores could not
   bring back. Mark the project `rolled-back`.

### 5.3 Plan format

`plan.toon` is the readable plan. It keeps Chapman's file name and TOON tables
so the design skills' references change little:

```toon
plan:
  project: oakhollow
  skill: design-village
  world: world
  anchor: {x: 120, y: 64, z: -340}
  bbox: {from: [100, 58, -362], to: [162, 92, -298]}
  summary: hamlet of 4 buildings around a bell plaza
  approved: no
phases[4]{id,name,file,blocks,from,to,via}:
  1,site-prep,phases/01-site-prep.json,18200,100 58 -362,162 66 -298,mcp
  2,houses,phases/02-houses.json,41750,104 63 -358,158 80 -302,placer
  3,details,phases/03-details.json,640,104 63 -358,158 80 -302,mcp
  4,population,-,0,118 64 -336,124 66 -330,commands
materials[2]{role,block}:
  walls,minecraft:spruce_planks
  trim,minecraft:stripped_spruce_log
modules[1]{name,file,size}:
  small-house-a,modules/small-house-a.json,9 8 7
placements[2]{module,origin,rotation,mirror,phase}:
  small-house-a,104 64 -358,0,none,2
  small-house-a,140 64 -330,90,x,2
commands[1]{phase,seq,command,purpose}:
  4,1,summon minecraft:villager 121 65 -333 {Tags:["ashlar","ashlar.oakhollow"]},farmer
acceptance[1]{phase,at,expect}:
  2,107 64 -358,minecraft:spruce_door
quality_contract:
  walkability[1]{from,to,note}:
    121 64 -340,107 64 -356,bell to house A door
```

- **Phase files** (`phases/NN-name.json`) hold exact `mc_build` arguments —
  `fills`, `blocks` (including `sign` objects), `text`, `liquids`, `connect`,
  optional `world` — in absolute coordinates. A bare fills list
  (`[{"from","to","block"}]`, the voxel toolkit's output) is also accepted by
  the placer.
- **`via`** is `mcp` (the model calls `mc_build` with the file's contents),
  `placer` (`ashlar_place.py place`) or `commands` (a phase made only of
  allowlisted console commands, with no phase file). `mcp` is allowed only for
  phase files with at most 200 entries; larger or generated files use `placer`.
  Lettering (`text`) is not accepted by the placer, so it goes in its own small
  `mcp` phase.
- **Ordering:** a phase file has `mc_build`'s semantics — all fills in order,
  then text, then blocks. Anything that must come after a block placement goes
  in a later phase.
- **Module files** are defined in §6.2. `placements` rows are expanded by
  `stamp.py` into a phase file.
- **`quality_contract`** keeps Chapman's row types: `walkability`, `doors`,
  `headroom`, `block_mix_ratios`, `silhouette`, `connectivity`, and
  `edge_irregularity` for terrain.

### 5.4 Execution rules

- **Player check:** call `mc_players` before every write phase. If any player
  is inside the phase's box expanded by 2 blocks, stop and tell the user. Do
  not build around them.
- **Snapshots:** tile each phase's bounding box into boxes of at most the
  snapshot cap (200,000 blocks) and snapshot each one before writing. The gate
  reports the total slots needed. Ashlar keeps 20, shared with every other
  snapshot on the server; if a build needs more than 15, warn that the oldest
  phases will become unrecoverable. Record every id in `registry.json`.
- **Ordering inside a phase:** clear with air first, then structure, then
  attached blocks (torches, ladders, signs, doors, carpets) once their supports
  exist. Phases never undo earlier phases.
- **Liquids:** static unless the phase opts into `liquids: "flow"` for a few
  source blocks (at most 2,000 flowing per call).
- **Worlds:** build only in worlds in `world.allowed-worlds`. Before designing
  for another dimension, confirm Ashlar accepts it with a read (`mc_survey` with
  `world`); if it does not, say the build cannot be placed.
- **Redstone:** blocks are placed without updates. Plans include a start
  trigger (lever or button) and say what the user must flip.
- **Pre-existing block entities:** if the survey found signs, chests or other
  block entities inside a phase box, the gate says a restore will empty them.

### 5.5 Console allowlist

| Kind | Allowed command forms |
| --- | --- |
| Change the world | `summon <entity> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}` |
| | `data merge block <x> <y> <z> {…}` |
| | `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}` |
| | `item replace block <x> <y> <z> <slot> with <item> [count]` |
| | `place feature <feature> <x> <y> <z>` (tree growth; inside a snapshotted box) |
| | `kill @e[tag=ashlar.<project>…]` |
| | `forceload add <x1> <z1> [<x2> <z2>]` |
| | `forceload remove <x1> <z1> [<x2> <z2>]` |
| Read only | `execute if biome <x> <y> <z> <biome>` |
| | `data get block <x> <y> <z> [path]` |
| | `data get entity @e[tag=ashlar.<project>,…,limit=1] [path]` |
| | `execute if entity @e[tag=ashlar.<project>,…]` |

- Never `fill`, `setblock`, `clone`, `give`, `tp`, `gamerule` or any other
  command, and never as a way around a limit.
- Added 2026-11-18 after the live write test (user decision: "Allow paired
  forceload (Recommended)"): entity commands run inside a paired
  `forceload add`/`forceload remove` over the columns they touch, so they work
  with no player nearby; no chunk is left force-loaded.
- Every summoned entity carries `ashlar` and `ashlar.<project>`. The prefix
  keeps the project tag from colliding with other datapacks' tags.
- Every world-changing command appears in `plan.toon` `commands` and in the
  approval gate.
- Skill text is not a security boundary. The spec recommends, and the
  implementation offers, setting `mcp__ashlar__mc_command` to "ask" in the
  user's Claude Code permissions. That change is made only with the user's
  go-ahead.

### 5.6 Verification

| Row or check | Ashlar procedure |
| --- | --- |
| `acceptance{at,expect}` | `mc_inspect` stats over the single cell |
| `walkability{from,to}` | `mc_inspect` `format: columns` along the route (≤1,024 columns per call): solid or slab/stair floor, two air cells above, step height ≤ 1 |
| `doors{at,facing,clearance_blocks}` | columns in front of and behind the door for the clearance distance: floor plus two air cells on both sides |
| `headroom{region,min_clear}` | columns over the region: air run above the walking surface ≥ `min_clear` |
| `block_mix_ratios{region,palette,max_single_ratio}` | `mc_inspect` stats (air excluded): no block above the ratio; every listed palette member present |
| `silhouette{region,sample_count,min_y_variance}` | `mc_survey` with `matrix: true`, or columns at the sample points; variance of top Y |
| `connectivity{site_a,site_b,via}` | walkability along the named route's polyline |
| `edge_irregularity` (terrain) | `mc_survey` matrix along the edge: longest run of identical X or Z |
| Visual | `mc_render` north/south/east/west facades (Y limited to the structure), top view, `y` slices for floor plans; compared with the blueprints (and reference renders for monuments) |
| Entities and NBT | `execute if entity` counts; `data get block` for NBT details; `data get entity …` for villager bed and job-site memories |

### 5.7 Project state

Relative to the session's working directory (Chapman's convention):

```text
.minecraft-builder/
  registry.json
  <project>/
    requirements.md   survey.md   research.md   research.toon
    floorplan.txt   floorplan.md   adjacency.mmd   (or the skill's own blueprint files)
    plan.toon   phases/   modules/   build-log.md
```

`registry.json`:

```json
{
  "version": 1,
  "projects": {
    "oakhollow": {
      "skill": "design-village",
      "world": "world",
      "anchor": [120, 64, -340],
      "bbox": {"from": [100, 58, -362], "to": [162, 92, -298]},
      "status": "planned | building | built | rolled-back",
      "entity_tag": "ashlar.oakhollow",
      "modules": ["small-house-a"],
      "phases": [
        {"id": 1, "name": "site-prep", "snapshots": ["snap-…"], "blocks": 18200, "placed_at": "2026-…"}
      ],
      "commands_run": ["summon minecraft:villager …"],
      "updated": "2026-…"
    }
  }
}
```

The registry is per working directory. Running Minecraft sessions from one
folder keeps a single history.

## 6. Scripts

All scripts need only Python's standard library (3.11 or newer, for `tomllib`),
except the voxel toolkit, which runs through `uv run --with numpy --with pillow`
so nothing is installed into the global Python. Skills give script paths
relative to the skill folder (§7.5).

### 6.1 `ashlar_place.py`

```text
ashlar_place.py check  [--server NAME] [--config PATH]
ashlar_place.py plan   FILE [limits]
ashlar_place.py place  FILE (--snapshot [--label L] | --no-snapshot) [--world W]
                       [--player-margin 2] [--max-snapshots 15] [--log PATH] [limits]
limits: --max-blocks 500000 --max-chunks 1024 --snapshot-volume 200000 --min-y -64 --max-y 319
```

- **Config:** use `--config PATH` if given. Otherwise read `~/.claude.json` →
  `mcpServers.<name>` (default `ashlar`), then
  `projects.<cwd>.mcpServers.<name>`, then `./.mcp.json`, then Codex's
  `~/.codex/config.toml` → `[mcp_servers.<name>]` (parsed with `tomllib`). Only
  stdio entries (`command`, `args`, `env`) are supported; `${VAR}` and
  `${VAR:-default}` in values are expanded from the environment.
- **Secrets:** the child process gets `os.environ` plus the entry's `env`.
  Nothing the script prints or logs may contain an env value. The child's
  stderr is never forwarded raw; on failure the script shows its tail with every
  env value replaced by `***`.
- **Protocol:** MCP over stdio, newline-delimited JSON-RPC 2.0: `initialize`,
  `notifications/initialized`, then `tools/call`. Notifications are ignored;
  responses are matched by id. Timeouts: 120 s for startup (npx may download),
  600 s per call.
- **Input:** an `mc_build` arguments object or a bare fills list. Block strings
  must carry the `minecraft:` namespace, coordinates must be integers, and Y
  must lie within the limits. `text` entries are rejected (lettering goes
  through the model's own `mc_build`).
- **`plan`** (offline): validate and report the bounding box, block count,
  chunk footprint, Y range, pages and snapshot tiles. No server contact.
- **Paging:** order-preserving. Fills too large for one call are split along
  their longest axis. Consecutive operations are packed into pages until the
  next one would exceed the block or chunk limit. All fill pages are sent
  before any block page, matching `mc_build`'s own fills-then-blocks order.
- **`place`:**
  1. Refuse without `--snapshot` or `--no-snapshot`.
  2. Run the player check with `mc_players` (`<name>  <world>  pos x=… y=… z=…`
     lines, or `No players online.`). Refuse if a player is inside a page box
     expanded by the margin, or if the output cannot be parsed.
  3. With `--snapshot`, tile the page boxes to the snapshot cap and snapshot each
     tile with `mc_snapshot`. Refuse if more than `--max-snapshots` tiles are
     needed.
  4. Send each page as an `mc_build` call and stop at the first error.
  5. Print a JSON summary: pages done and failed, blocks changed, snapshot ids,
     Ashlar warnings. `--log` appends the same summary to a file.
- **Exit codes:** 0 success · 2 invalid input · 3 refused by a limit or snapshot
  rule · 4 player in the area · 5 server error mid-run (the summary lists the
  pages already written and the snapshot ids for rollback).

### 6.2 `stamp.py` and module files

Module file (local coordinates, minimum corner at `[0, 0, 0]`):

```json
{"name": "small-house-a", "size": [9, 8, 7],
 "fills": [{"from": [0,0,0], "to": [8,0,6], "block": "minecraft:cobblestone"}],
 "blocks": [{"pos": [4,1,0], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"}]}
```

```text
stamp.py MODULE.json --at X,Y,Z [--rotate 0|90|180|270] [--mirror none|x|z] [--out FILE]
stamp.py --placements PLAN_OR_JSON --modules DIR --out FILE
```

- **Convention:** mirror first, then rotate clockwise as seen from above, then
  translate so the result's minimum corner sits at the origin. `--mirror x`
  flips east–west; `--mirror z` flips north–south. 90° clockwise maps
  `(x, z) → (d − 1 − z, x)` for a module `w` wide and `d` deep, and north →
  east → south → west.
- **Block states:**
  - rotate `facing` (horizontal values only), sign/banner/head `rotation` (+4
    per 90°), `axis` (x ↔ z at 90° and 270°), rail `shape`, the horizontal part
    of `orientation`, and the keys of directional booleans on non-connecting
    blocks (vines, glow lichen, sculk veins, mushroom blocks, fire);
  - on mirror, also swap `hinge` and the left/right stair shapes;
  - drop connection properties (`north`/`east`/`south`/`west`) on fences,
    walls, panes, bars and redstone wire, because Ashlar's connection pass
    recomputes them;
  - normalize chest `type` to `single` (Ashlar pairs chests itself).
- Modules may not contain `text`. Overlapping instances are an error. The output
  is a phase file (fills, then blocks) ready for the placer.

### 6.3 Voxel toolkit

- Copy Chapman's `tools/voxel/{__init__,model,palette,render,decompose}.py` to
  `skills/design-monument/tools/voxel/` with Chapman's MIT notice. Leave out
  `mcp_place.py` (Chapman's placer) and `continuity.py` (rail checks).
- `write_fills_json` already emits `[{"from","to","block"}]`, which the placer
  accepts unchanged.
- Run with `uv run --with numpy --with pillow python …`. Mesh import adds
  `--with trimesh --with scipy --with networkx --with lxml`.
- Pixel art uses the same path: a generated fills file sent through the placer.
- Chapman's voxel section of `tools/README.md` becomes
  `tools/voxel/README.md`, rewritten for these paths and the Ashlar placer.

## 7. Edits to the design skills

The rule: change only text that points at Chapman's pipeline or tools. Design
knowledge — styles, rooms, layouts, catalogs, techniques — stays as written.
Server-specific facts are discovered at runtime, never written into the skills.

### 7.1 Each `SKILL.md`

| Upstream | Replacement |
| --- | --- |
| Description ends "Part of the minecraft-builder workflow." | "Builds through Ashlar with the exec-ashlar skill." Trigger wording, `model` and `effort` unchanged |
| "Connection: … run the `minecraft-mcp-setup` agent" | Run `mc_status`; if Ashlar is unreachable, stop and tell the user |
| Inputs from `survey-site` (`survey.toon`) | `exec-ashlar survey <project>` and its `survey.md` |
| Inputs from `survey-research` | Unchanged (installed from the fork) |
| `mcbuilder:registry`, `data_storage_get/set` | `.minecraft-builder/registry.json` |
| "Never place blocks — `exec-worker` does" | "Place no blocks while designing; after the user approves the plan, build it with `exec-ashlar build <project>`" |
| Pre-tile fills to ≤32,768 blocks; split elements over 64×384×64 into structures; `${CLAUDE_PLUGIN_ROOT}/…/command-budget.md` | Ashlar limits in `exec-ashlar/reference/tools-and-limits.md` |
| `mcb:<project>_<element>` structure templates | `modules/<element>.json` stamped with `stamp.py` |
| `quality_contract` "per the schema in exec-plan" | Per `exec-ashlar/reference/plan-format.md` |
| "Return to the orchestrator" | "Hand-off": there is no orchestrator. The main session sequences siblings itself — finish and approve this design, run the sibling design skill for each flagged element, then `exec-ashlar` phase by phase |

### 7.2 Reference files

About 35 reference files need at least one edit; most are one to three lines.

| Upstream instruction | Replacement |
| --- | --- |
| `block_fill_region`, `block_set_state`, `block_fill_batch` | `mc_build` fills and blocks |
| Sign text via `block_entity_set_nbt` | `mc_build` `sign` object |
| Banner patterns, lectern books, decorated pots, heads via `block_entity_set_nbt` | `data merge block` (allowlist) |
| `inventory_set_slot`, `player_give_item`, `itemstack_*` | `item replace block` for containers; `data get block` to check |
| `entity_summon`, `entity_set_nbt`, `entity_get_nbt`, `entity_query` | `summon` / `data merge entity` / `data get entity` / `execute if entity`, with the project tags |
| `structure_save_from_world`, `structure_load_to_world`, `structure_file_write` | Modules and `stamp.py` |
| `level_get_biome_at` | `execute if biome`, or inference from the survey |
| `block_render_region`, `block_scan_region`, `block_scan_summary`, `block_get_state` | `mc_render`, `mc_inspect` |
| `block_transform_preview`, `schedule_function` and datapack functions, `loot_table_generate` | Marked unavailable with Ashlar, with the closest alternative |
| "You cannot see the world" (monument render-verify) | The model can, through `mc_render`; offline renders remain the cheap first loop |
| `block_set_state` notifies neighbours, so clocks self-start (house utilities) | Ashlar places without updates; include a start trigger |
| Nether and End sites (house environments) | Note that Ashlar builds only in `world.allowed-worlds` |
| `exec-inspect`, `exec-reflect` checks | `exec-ashlar` verification |
| Monument and grounds hard rule "No `/random` or `/data`" | "No `/random`; bake variation into the design; `/data` only as the allowlist permits" |

Notes about unavailable features describe the capability ("previewing what an
axe does to a block"), not Chapman's tool name, so the §9.1 check can stay
strict.

References to `survey-research`, `terrain-shape`, `terrain-landmark` and
`system-redstone` stay, because those skills exist in the fork and will be
installed (now, or after sub-projects 2 and 3).

### 7.3 Interim fallback for terrain and redstone

Until sub-projects 2 and 3 are installed, each design skill says:

- If `terrain-shape` or `terrain-landmark` is not installed, plan simple site
  preparation (clearing, levelling, pads, filling holes, soft-edged terraces) as
  a `site-prep` phase, and tell the user when the design really needs more.
- If `system-redstone` is not installed, stay with the simple Java designs in
  the skill's own references and say when a contraption needs more.

### 7.4 `survey-research`

Its search and fetch instructions become labelled lines (§7.5). Claude Code
uses `WebSearch` and `WebFetch`. Codex uses its web search tool when it is
enabled, and `trafilatura -u <url>` in the shell to read pages. Any other
client uses `trafilatura`. Output files and the research method stay unchanged.

### 7.5 Shared text with labelled client-specific tools

Every step must work in any client that has the Ashlar tools, a shell and file
access. Where a client-specific tool genuinely helps, a skill may use it, but
only as a labelled alternative with a fallback, never as the only instruction:

```markdown
Ask the user in small batches.
- Claude Code: use `AskUserQuestion` for multiple-choice questions.
- Codex: use `request_user_input` if it is listed among your tools.
- Otherwise: ask in plain text.
```

Rules:

- Labels are exactly `Claude Code:`, `Codex:` and `Otherwise:`. Each client
  follows the shared text plus its own line, and uses the `Otherwise:` line
  when its own tool is missing.
- Shared text names tools without client prefixes (`mc_build`, not
  `mcp__ashlar__mc_build`).
- Skills hand off by name ("use the `exec-ashlar` skill"). In Codex the user can
  also type `$exec-ashlar`.
- Script paths in shared text are relative to the skill folder
  (`scripts/ashlar_place.py`); `${CLAUDE_SKILL_DIR}` appears only on a
  `Claude Code:` line.
- Claude-only frontmatter is kept or added because Codex ignores it: `model`,
  `effort`, and `allowed-tools` listing only the read-only Ashlar tools
  (`mcp__ashlar__mc_status`, `…mc_players`, `…mc_survey`, `…mc_render`,
  `…mc_inspect`). Never pre-approve `mc_build`, `mc_snapshot`, `mc_restore` or
  `mc_command`.
- Codex-only frontmatter may be added because Claude Code ignores it:
  `metadata.short-description` for Codex's skill list.
- `exec-ashlar/reference/clients.md` holds the full mapping once. Skills carry
  labelled lines only where the choice matters.

Where client-specific tools are used:

| Capability | Claude Code | Codex | Otherwise |
| --- | --- | --- | --- |
| Structured interview questions | `AskUserQuestion` | `request_user_input`, if listed | plain-text questions |
| Looking at offline PNGs (voxel renders) | `Read` on the file | `view_image` | report the numbers from `mc_inspect` and ask the user to open the file |
| Web research (`survey-research`) | `WebSearch`, `WebFetch` | web search tool if enabled; `trafilatura -u <url>` | `trafilatura -u <url>` |
| Progress through a long build | the client's task or todo tool | `update_plan` | a checklist in `build-log.md` |
| Skill hand-off | Skill tool, or `/exec-ashlar` | `$exec-ashlar`, or open the skill's `SKILL.md` | open the skill's `SKILL.md` |

Images returned by Ashlar's own `mc_render` and `mc_survey` arrive as tool
results, so they need no client-specific handling.

## 8. Out of scope for sub-project 1

- Porting `terrain-shape`, `terrain-landmark`, `reference/terrain/` and the
  terrain toolkit (sub-project 2), and `system-redstone` (sub-project 3).
- Chapman's other skills (`build-*`, `exec-*`, `setup-*`, `terrain-cave`,
  `terrain-ecology`, `terrain-integrate`, `system-transit`), its agents and its
  builder harness.
- An HTTP transport for the placer, and the `wss://` migration.
- Codex-only features beyond agent-neutral skill text and the placer's Codex
  config support.
- Changes to the user's permission settings, other than the offered
  `mc_command` "ask" rule.

## 9. Testing and verification

1. **Static checks** (`tests/ashlar/test_skill_text.py`): scan every Markdown
   file in the eight installed skills for Chapman backend leftovers, using an
   explicit list of Chapman's MCP tool names taken from upstream (for example
   `block_fill_region`, `block_set_state`, `block_entity_set_nbt`,
   `structure_load_to_world`, `entity_summon`, `data_storage_set`,
   `level_get_biome_at`, `command_execute`) rather than prefixes, because
   prefixes would flag legitimate names such as `minecraft:block_display` or
   the registry's `entity_tag`. Also flag `${CLAUDE_PLUGIN_ROOT}`,
   `minecraft-mcp-setup`, `exec-plan`, `exec-blueprint`, `exec-worker`,
   `exec-inspect`, `exec-reflect`, `survey-site` and `32,768`. The sibling
   names `terrain-shape`, `terrain-landmark` and `system-redstone` are allowed.
   Client-specific names (`AskUserQuestion`, `request_user_input`,
   `view_image`, `update_plan`, `TodoWrite`, `WebSearch`, `WebFetch`,
   `${CLAUDE_SKILL_DIR}`, `mcp__…`) may appear only on lines labelled
   `Claude Code:` or `Codex:`, in `exec-ashlar/reference/clients.md`, or in
   Claude-only frontmatter (§7.5). Validate frontmatter: the YAML parses,
   `name` matches the folder, the description is present and under 1,024
   characters. Also run upstream's `node scripts/validate-plugin.mjs`.
2. **Script tests** (`uv run --with pytest pytest tests/ashlar`):
   - paging and snapshot tiling;
   - input validation;
   - config discovery against fixture configs (Claude `~/.claude.json`,
     `.mcp.json` and Codex `config.toml`), asserting no env value ever appears
     in stdout, stderr or logs;
   - the MCP exchange against a fake stdio server, including stderr redaction;
   - `stamp.py` for every rotation and mirror, covering coordinates and each
     block-state rule;
   - a voxel smoke test with numpy and Pillow: build a tiny model, render the
     views, write fills, run `ashlar_place.py plan`.
3. **Live, read-only:** `ashlar_place.py check`; `ashlar_place.py plan` on a
   sample.
4. **Live write test** (asked first, because players may be online), in a
   scratch area chosen from a survey, away from everyone:
   - stamp a small module in all four rotations and one mirror through the
     placer with snapshots;
   - summon a tagged armor stand, count it with `execute if entity`, then `kill`
     it by tag;
   - check the result with `mc_render` and `mc_inspect`;
   - restore every snapshot and confirm the area matches its pre-test state.
5. **Skill dry runs:** run each design skill on a small prompt in a fresh
   subagent limited to read-only Ashlar tools and file tools, stopping at the
   approval gate. Check that it surveys through Ashlar, writes `plan.toon` and
   phase JSON in the §5.3 format, keeps commands inside the allowlist and never
   points at a missing Chapman component. Then build one small house end to end
   in the scratch area with the user's approval, and restore it.
6. **Install check:** every link in the workspace's `.claude/skills` and
   `.agents/skills` resolves to a skill folder in the clone; no global copies or
   skills-CLI lock entries for these names remain; Claude Code started in the
   workspace lists the eight skills, and so does Codex.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Chapman edits the same lines in a later release | Edits limited to pipeline text; rerun the §9.1 check after every merge |
| Ashlar adds features (snapshots that keep block entities, structure generators, per-token scopes) | `tools-and-limits.md` records the version it describes; revisit on upgrade |
| The placer bypasses per-call MCP approval | Approval gate, required snapshot flag, player check, snapshots; the user can restrict Bash permissions |
| Token or URL exposure | Never printed; child stderr redacted; tests assert it |
| Large builds evict their own snapshots | Slot count at the gate; refusal above `--max-snapshots` |
| Restore empties pre-existing signs and chests | Survey lists them; gate warns |
| Players inside a build area | Player check before every write phase |
| A session started outside the workspace root does not see the skills | Documented in the fork's README and the project memory: start Claude Code and Codex in the workspace root |
| Switching branches in the clone changes the live skills | Build and test from `ashlar` until it is merged, then keep `main` checked out |
