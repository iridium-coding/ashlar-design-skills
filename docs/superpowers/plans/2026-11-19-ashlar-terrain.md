# Ashlar Terrain Skills (Sub-project 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port Chapman's `terrain-shape`, `terrain-landmark`, `terrain-ecology` and `terrain-integrate` skills and his terrain toolkit so they build through `exec-ashlar` on the Ashlar MCP server, in Claude Code and Codex.

**Architecture:** The toolkit is copied into `skills/terrain-shape/tools/terrain/` and gains an Ashlar output step. It reads the live site through the placer (a column read in backup format, plus a heights file), blends the recipe into the existing ground, materialises only the cells that must change, and writes ordinary `mc_build` phase files, commands files (`place feature`, `fillbiome`), vegetation modules and `plan.toon` rows. `exec-ashlar`'s placer gains column backups and restore, height reads, a bulk command runner and a biome probe; `stamp.py` gains vegetation modules; the skill text gains the rules. The four terrain skills are rewritten around this flow, and six design skills get small edits.

**Tech Stack:** Markdown Agent Skills (Claude Code and Codex); Python 3.11+ standard library for `ashlar_place.py` and `stamp.py`; numpy, scipy, Pillow and opensimplex through `uv run` for the toolkit; the voxel toolkit already in `skills/design-monument/tools/voxel/`; pytest; Ashlar 0.4.9 on Paper 26.3; Node 20+ for upstream's `scripts/validate-plugin.mjs`.

**Spec:** `docs/superpowers/specs/2026-11-19-ashlar-terrain-design.md` (committed as `b15a004`). Executors read the spec and this plan together; "spec §N" means that section. Spec 1 is `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md`.

## Global Constraints

- **Repository:** the worktree `/Users/bsw/Development/Minecraft/ashlar-design-skills-terrain`, branch `terrain`. Run commands from there. The workspace root is `/Users/bsw/Development/Minecraft`; `.minecraft-builder/` lives there. Never switch branches in `/Users/bsw/Development/Minecraft/ashlar-design-skills` (its checked-out branch is what the live linked skills load).
- **Commits:** every task ends with a commit on `terrain`. Messages end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push, open a PR or merge without the user's OK given at that moment.
- **Test commands:**
  - placer, stamp and skill text: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar -q --ignore=tests/ashlar/terrain`
  - toolkit: `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain -q`
  - everything: `uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar -q`
  - validator: `node scripts/validate-plugin.mjs` → `✓ plugin, marketplace, skills, and agents are valid`
- **Toolkit launcher:** `uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python skills/terrain-shape/scripts/terrain.py <command>` (in skill text: `<terrain-shape>/scripts/terrain.py`).
- **Python:** `ashlar_place.py` and `stamp.py` stay standard-library only and run on Python 3.11+. The toolkit may use numpy, scipy, Pillow and opensimplex, never anything else.
- **Ashlar limits** (defaults): 500,000 blocks per `mc_build` call; 1,024-chunk footprint per write call; 4,096 entries per placer page; 200,000 cells per read and per snapshot; 1,024 columns per `mc_inspect` columns call; 200,000 x/z cells per `mc_survey`; 20 snapshots kept; 2,000 flowing liquids per call; 16 queued operations; overworld y −64 to 319. Vanilla limits: at most 256 chunks per `forceload` command; `fillbiome` at most 32,768 blocks per command by default.
- **Console allowlist** after this sub-project: spec 1 §5.5's forms, plus `fillbiome <x1> <y1> <z1> <x2> <y2> <z2> <biome>` under the conditions of spec §9.5. Commands files may hold only `place feature` and `fillbiome`.
- **Upstream files:** this plan changes only `skills/terrain-{shape,landmark,ecology,integrate}/`, the listed lines of `skills/design-*/`, `skills/exec-ashlar/`, `skills/TAXONOMY.md`, `README.md`, `CLAUDE.md` and `tests/ashlar/`. Never edit the root `tools/terrain/`, the root `reference/terrain/`, `skills/terrain-cave/`, or Chapman's other skills, agents and tools.
- **Skill text rules** (spec 1 §7.5, spec §8.6): client-specific names only on lines labelled `Claude Code:` or `Codex:` with an `Otherwise:` line; paths relative to the skill folder, cross-skill paths only as siblings (`../terrain-shape/…`, `../exec-ashlar/…`), never repo-root paths; no word "orchestrator"; no server-specific facts (IPs, hosts, player names, this server's site coordinates or world list).
- **Secrets:** never print, log or commit a value from an MCP server entry's `env`; never read `~/.claude.json` or `~/.codex/config.toml` with commands that echo values.
- **Live world:** only Tasks 23–27 contact the live server. Tasks 24 and 25 are read-only. Task 26 writes only after the user's yes at that moment, only inside the scratch area recorded in Task 24, and restores it.
- **Shared column reader:** `column_tiles`, `parse_columns` and `read_columns` (Task 3) are shared with sub-project 3 (`redstone` branch), whose `read` subcommand uses them. Sub-project 3 committed them on `redstone` as `462f592` (not yet merged). If `origin/main` already has them when Task 3 starts, ask the user whether to merge `origin/main` into `terrain` and reuse them; otherwise copy the three functions verbatim from `git show 462f592 -- skills/exec-ashlar/scripts/ashlar_place.py`, so the later merge has nothing to reconcile.

### Shared formats

Every task that reads or writes these uses them exactly. Paths in recipes and plan rows are relative to the project folder `.minecraft-builder/<project>/`.

- **F1 Backup / site read** (a folder): `manifest.json` = `{"version": 1, "box": [x1, y1, z1, x2, y2, z2], "world": str | null, "created": "YYYY-MM-DDTHH:MM:SSZ", "columns": int, "sha256": "<hex of columns.json.gz bytes>", "plugin": str | null, "complete": true}`; `columns.json.gz` = gzip of `{"version": 1, "world": …, "box": […], "columns": {"<x>,<z>": [[y1, y2, "minecraft:<id>[<states>]"], …]}}`, runs bottom to top, contiguous, covering the box's y range exactly. The site read is `.minecraft-builder/<project>/site/`; phase backups are `.minecraft-builder/<project>/backups/<NN>-<phase-name>/`.
- **F2 Heights file:** `{"version": 1, "world": str | null, "origin": [x1, z1], "size": [nx, nz], "ground": [...], "surface": [...], "top": [...]}`; each list has `nx * nz` entries at index `xi * nz + zi`, an int or `null`. `ground` = `mc_survey` type `SOLID`, `surface` = `SOLID_OR_LIQUID_NO_LEAVES`, `top` = `ANY`.
- **F3 Commands file:** `{"version": 1, "kind": "features" | "biomes", "box": [x1, y1, z1, x2, y2, z2], "world": str | null, "commands": ["place feature minecraft:oak 120 65 -340", …]}`. Commands carry no leading `/` and no `minecraft:` prefix on the command name; the runner adds it. File names: `phases/<NN>-<element>-features.commands.json`, `phases/<NN>-<element>-biome.commands.json`.
- **F4 Progress file:** JSON lines `{"index": int, "ok": bool}`, one per command attempted.
- **F5 Biome probe:** `{"version": 1, "world": …, "box": […], "chunks": {"<cx>,<cz>": "minecraft:<biome>" | "unknown"}}`.
- **F6 Expected surface:** `{"version": 1, "origin": [x1, z1], "size": [nx, nz], "top": [...], "skip": [...]}` at index `xi * nz + zi`; `top` is the expected highest solid-or-liquid block ignoring leaves (int or `null`), `skip` is 0 or 1. Written as `terrain/<element>.surface.json`.
- **F7 Vegetation module:** `{"name": str, "size": [w, h, d], "kind": "vegetation", "anchor": [ax, ay, az], "ground": {"fills": [], "blocks": []}, "wood": {"fills": [], "blocks": []}, "leaves": {"fills": [], "blocks": []}}`, local coordinates, minimum corner `[0, 0, 0]`, no air cells; `anchor` is the trunk base cell.
- **F8 Placements JSON:** the list `stamp.py --placements` already reads: `[{"module": str, "origin": [x, y, z], "rotation": 0 | 90 | 180 | 270, "mirror": "none" | "x" | "z", "phase": int}]`.
- **F9 Recipe additions** (Chapman's recipe keys stay): `"element": str`; `"origin": [x1, 0, z1]` and `"nx"`, `"nz"` = the terrain box; `"site": {"read": "site", "band": "auto" | int}`; `"pads": [{"center": [x, z], "half": [hx, hz], "level": y, "shoulder": 9}]` (a design build's footprint, world coordinates); `"water": [{"level": int, "at": [x, z]}]`; `"falls": [{"at": [x, y, z]}]`; `"forms": [{"name": str, "model": "<file>.npy", "palette": "<file>.json", "origin": [x, y, z], "mode": "carve" | "build"}]`; under `"material"`, optional `"strata_top": int`.

**User decisions (already made):**
- "Both sizes" — site scale and landscape scale.
- "Vanilla trees through place feature, though I do want the agent to be capable of designing "custom" trees with different shapes than may be found in vanilla."
- "Add fillbiome to the allowlist, though ensure the agent asks whenever the biome has to be changed (and even then, I do not want that to be the first instinct)."
- "Go with approach 1" — terrain emits ordinary `exec-ashlar` phases.
- "Port ecology and integrate now with your caveats, leave cave for later."
- Design parts 1–3: "Looks great!", "Looks right, go on to part 3", "Write the spec".
- Trees crossing the box edge: "Remove whole trees".
- Spec: "Approve and commit" (`b15a004`). Plan: "Write the plan".
- From sub-project 1, still binding: ask before any push, merge or live-world write; `mc_command` stays allowlist-only (the user declined an "ask" permission); never commit the Ashlar URL, token or server-specific facts.

## Review Focus

The inputs the spec implies that are most likely to bite. Each has a pinned test in the task that owns the code.

1. **Wooded land where trees cross the box edge.** Expected: a tree rooted on changed ground is removed whole, including leaves outside the box; a tree rooted outside keeps every cell, including canopy over the box; nothing else outside the box is written. Test: `test_crossing_trees_removed_whole_or_kept` (Task 9).
2. **A cliff: a high new column next to a much lower neighbour, or a cave pocket just under the new surface.** Expected: the whole visible face is materialised, the seal band fills the pocket, nothing below `b` is written. Test: `test_cliff_faces_and_seal_band` (Task 9).
3. **Negative coordinates and boxes crossing x = 0 or z = 0** in column tiles, force-load chunk tiles and heights indexing. Expected: exact coverage and correct chunk numbers (chunk of x = −1 is −1). Tests: `test_column_tiles_respect_limits_and_cover_box` (Task 3), `test_command_chunks_and_forceload_tiles_across_zero` (Task 5), `test_heights_negative_origin` (Task 4).
4. **The server errors part way through a commands file.** Expected: the open force-load is still removed, progress is saved, the exit code is 5, and a rerun skips the commands already attempted. Test: `test_runner_server_error_still_removes_forceload_and_resumes` (Task 5).
5. **Water touching the box edge where the outside ground is lower than the water level.** Expected: GATE A fails (`water_contained`) unless existing water outside stands at the same level. Test: `test_water_at_edge_must_meet_existing_water` (Task 8).

---

## File map

| Path | Task | Responsibility |
| --- | --- | --- |
| `skills/terrain-shape/tools/terrain/` (copy) | 1 | Chapman's toolkit without his placer, harness output and voxel-grid path |
| `tests/ashlar/terrain/` (copies, `conftest.py`, `test_copy.py`) | 1 | Chapman's toolkit tests against the copy |
| `tests/ashlar/test_skill_text.py` | 2 | Static checks extended to the four terrain skills |
| `skills/exec-ashlar/scripts/ashlar_place.py` | 3, 4, 5 | Column reader, backup, restore, heights, flowing cap, `filter`, commands runner, biome probe and restore |
| `tests/ashlar/fake_ashlar_mcp.py` | 3, 4, 5 | Fake server with a small in-file world |
| `tests/ashlar/test_backup.py`, `test_heights.py`, `test_runner.py` | 3, 4, 5 | Placer tests |
| `skills/exec-ashlar/scripts/stamp.py`, `tests/ashlar/test_stamp.py` | 6 | Vegetation modules |
| `skills/terrain-shape/tools/terrain/site.py` | 7, 8 | Site reads, existing surfaces, trees, natural blocks, boundary blend, water levels |
| `skills/terrain-shape/tools/terrain/verify.py`, `recipe.py` | 8 | `edge_match` and water checks; the recipe `site` key |
| `skills/terrain-shape/tools/terrain/live.py` | 9 | Live materialisation, fills, phase tiles, expected surface |
| `skills/terrain-shape/tools/terrain/forms.py` | 10 | Carve and build-up forms, flow sources, gravity check |
| `skills/terrain-shape/tools/terrain/ashlar_emit.py`, `skills/terrain-shape/scripts/terrain.py` | 11 | Phase files, plan rows, the launcher |
| `skills/terrain-shape/tools/terrain/ids.py`, `data/` | 12, 23 | Feature and biome id lists per Minecraft version |
| `skills/terrain-shape/tools/terrain/plant.py` | 13 | Planting plans, features and biome commands |
| `skills/terrain-shape/tools/terrain/trees.py` | 14 | Custom tree generator |
| `skills/terrain-shape/tools/terrain/apron.py` | 15 | Aprons for `terrain-integrate` |
| `skills/exec-ashlar/SKILL.md`, `reference/*.md` | 16 | Executor rules for backups, runner, biomes, resume, terrain checks |
| `skills/terrain-shape/` text and `reference/terrain/` | 17 | Skill, shared method and API references |
| `skills/terrain-landmark/` | 18 | Skill and references |
| `skills/terrain-ecology/` | 19 | Skill, `ecology.md`, `custom-trees.md` |
| `skills/terrain-integrate/` | 20 | Skill, `integration.md` |
| `skills/design-*/` | 21 | Integrate offer and planting pointers |
| `skills/TAXONOMY.md`, `README.md`, `CLAUDE.md` | 22 | Fork notes |
| `/Users/bsw/Development/Minecraft/.claude/agents/ashlar-terrain-dry-run.md` | 25 | Dry-run agent with a restricted shell (workspace, not the fork) |

---

## Task 1: Copy the terrain toolkit into `terrain-shape`

**Goal:** The toolkit lives in `skills/terrain-shape/tools/terrain/` without Chapman's placer, harness output or voxel-grid path, and Chapman's remaining tests pass against the copy.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/` (copy of `tools/terrain/` minus `tests/`, `place_terrain.py`, `__pycache__/`), `skills/terrain-shape/tools/terrain/LICENSE` (copy of the repo's `LICENSE`), `skills/terrain-shape/tools/terrain/README.md`
- Modify (copy only): `skills/terrain-shape/tools/terrain/emit.py`, `materialize.py`, `__init__.py`
- Create: `tests/ashlar/terrain/conftest.py`, `tests/ashlar/terrain/test_copy.py`, copies of `tools/terrain/tests/test_*.py` except `test_emit_plan_toon.py`
- Modify (copies): `tests/ashlar/terrain/test_belt_recipe.py`, `tests/ashlar/terrain/test_materialize_columns.py`

**Acceptance Criteria:**
- [ ] The copy contains no `place_terrain.py`, no `emit_plan_toon` and no code path that imports `voxel`.
- [ ] `emit_world`, `write_payloads`, `_material_from_spec` and `_belt_region_spec` remain; `materialize` keeps `Layer`, `MaterialSpec`, `resolve_surface`, `to_columns_plan`, `tile_columns_plan`, `write_columns_plan`.
- [ ] 88 copied tests and the 2 new ones pass; the only tests dropped are `test_emit_plan_toon.py` (6), `test_emit_plan_toon_belt_loop_gated` and `test_columns_surface_matches_voxel_top_layer_flat`.
- [ ] The root `tools/terrain/` is unchanged (`git diff --stat tools/` is empty).

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain -q` → `90 passed`

**Steps:**

- [ ] **Step 1: Copy the files**

```bash
mkdir -p skills/terrain-shape/tools tests/ashlar/terrain
cp -R tools/terrain skills/terrain-shape/tools/terrain
rm -rf skills/terrain-shape/tools/terrain/tests skills/terrain-shape/tools/terrain/place_terrain.py
find skills/terrain-shape/tools/terrain -name __pycache__ -prune -exec rm -rf {} +
cp LICENSE skills/terrain-shape/tools/terrain/LICENSE
for f in tools/terrain/tests/test_*.py; do case "$f" in *test_emit_plan_toon.py) ;; *) cp "$f" tests/ashlar/terrain/ ;; esac; done
```

- [ ] **Step 2: Write `tests/ashlar/terrain/conftest.py` and the failing `test_copy.py`**

`conftest.py` puts `skills/terrain-shape/tools` and `skills/design-monument/tools` (the voxel toolkit, used from Task 10 on) at the front of `sys.path`, the way `tools/terrain/tests/conftest.py` does.

```python
COPY = REPO / "skills" / "terrain-shape" / "tools" / "terrain"
GONE = ("emit_plan_toon", "place_terrain", "from voxel", "import voxel",
        "to_voxel_model", "write_terrain_fills", "TerrainLayers")

def test_copy_has_no_chapman_placement_paths():
    hits = [f"{p.relative_to(REPO)}: {word}" for p in COPY.rglob("*.py")
            for word in GONE if word in p.read_text(encoding="utf-8")]
    assert not hits, hits

def test_copy_has_license_and_readme():
    assert "MIT License" in (COPY / "LICENSE").read_text(encoding="utf-8")
    assert "ashlar_emit" in (COPY / "README.md").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run the toolkit tests and see the failures**

Run: the toolkit test command. Expected: `test_copy.py` fails, and `test_belt_recipe.py` / `test_materialize_columns.py` fail on the removed paths once Step 4 lands.

- [ ] **Step 4: Prune the copy and the copied tests**

- `emit.py`: delete `emit_plan_toon`, `_to_toon`, `_toon_table`, `_toon_scalar`, `_toon_cell`, `_needs_quote`, `_quote`, `_columns_steps`, `_tile_columns_plan`, `_fallback_tile`, `_slice_plan`, `_bbox_xz`, `_offline_token`, `_scatter_to_placements`, `_is_blended`, `_graph_mentions`; rewrite the module docstring to say the Ashlar output lives in `ashlar_emit.py`.
- `materialize.py`: delete `_RGB`, `TerrainLayers`, `_choice_field`, `to_voxel_model`, `write_terrain_fills`; fix the module docstring.
- `__init__.py`: drop those names from the imports and `__all__`; replace the docstring example with one that uses `recipe.build_field`, `render_views` and (by name) `ashlar_emit.emit_ashlar`.
- `tests/ashlar/terrain/test_belt_recipe.py`: delete `test_emit_plan_toon_belt_loop_gated`.
- `tests/ashlar/terrain/test_materialize_columns.py`: delete `test_columns_surface_matches_voxel_top_layer_flat` and `TerrainLayers`, `to_voxel_model` from its import.
- `README.md`: a short note — what the copy is, that it came from Chapman's `tools/terrain/` under the MIT license, what was left out, the `uv run` launcher command, and that `ashlar_emit.py` (Task 11) is the Ashlar output step.

- [ ] **Step 5: Run the toolkit tests** — Expected: `90 passed`.

- [ ] **Step 6: Commit**

```bash
git add skills/terrain-shape/tools tests/ashlar/terrain
git commit -m "feat(terrain-shape): copy Chapman's terrain toolkit without his placer and harness output"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/", "tests/ashlar/terrain/"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain -q", "acceptanceCriteria": ["no place_terrain, emit_plan_toon or voxel imports in the copy", "emit_world and MaterialSpec paths kept", "88 copied + 2 new tests pass", "root tools/terrain unchanged"], "modelTier": "mechanical"}
```

---

## Task 2: Static checks for the terrain skills

**Goal:** `tests/ashlar/test_skill_text.py` covers the four terrain skills: Chapman leftovers, labelled client names, frontmatter, and reference links that resolve inside the skill folder.

**Files:**
- Modify: `tests/ashlar/test_skill_text.py`

**Acceptance Criteria:**
- [ ] `SKILLS` gains `terrain-shape`, `terrain-landmark`, `terrain-ecology`, `terrain-integrate` (ids `terrain_shape` …).
- [ ] New forbidden names: `level_fill_biome`, `level_place_feature`, `level_place_features_batch`, `block_erode_region`, `block_erode_hydraulic_start`, `block_erode_hydraulic_status`, `block_erode_hydraulic_result`, `block_replace_in_region`, `level_get_mob_spawns`, `structure_create_from_blocks`, `structure_list`, `place_terrain`, `emit_plan_toon`; patterns `\bbuild-(?:natural-world|settlement|structure|systems)\b`, `\bGATE B\b`, `\bharness\b`.
- [ ] `\bterrain-cave\b` is forbidden inside the four terrain skills only.
- [ ] `32,768` is no longer flagged on a line that contains `fillbiome`.
- [ ] `test_reference_links_resolve_in_skill_folder[<skill>]` fails for any path in a terrain skill's Markdown that does not exist relative to the skill folder.
- [ ] The per-skill tests for the eight sub-project 1 skills and all self-tests pass; the terrain-skill tests fail until Tasks 17–20.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k "not terrain_"` → all pass

**Steps:**

- [ ] **Step 1: Write the failing self-tests**

```python
def test_leftovers_detects_cave_and_harness_names() -> None:
    assert leftovers("use level_place_features_batch") == [(1, "level_place_features_batch")]
    assert leftovers("the harness lint") == [(1, "harness")]
    assert leftovers("run build-natural-world") == [(1, "build-natural-world")]
    assert leftovers("GATE B runs") == [(1, "GATE B")]
    assert leftovers("see terrain-cave", cave_forbidden=True) == [(1, "terrain-cave")]
    assert leftovers("see terrain-cave") == []

def test_32768_allowed_only_with_fillbiome() -> None:
    assert leftovers("fills of 32,768 blocks") == [(1, "32,768")]
    assert leftovers("fillbiome: at most 32,768 blocks") == []

def test_skill_paths_found_and_resolved() -> None:
    text = ("Read `reference/terrain/method.md` and `../terrain-shape/reference/terrain/palettes.md`;\n"
            "run `<terrain-shape>/scripts/terrain.py` and `../exec-ashlar/scripts/ashlar_place.py`.")
    assert skill_paths(text) == ["reference/terrain/method.md",
                                 "../terrain-shape/reference/terrain/palettes.md",
                                 "<terrain-shape>/scripts/terrain.py",
                                 "../exec-ashlar/scripts/ashlar_place.py"]
```

- [ ] **Step 2: Run them** — Expected: FAIL (`cave_forbidden` and `skill_paths` undefined).

- [ ] **Step 3: Implement**

- Extend `CHAPMAN_TOOLS` and `FORBIDDEN` as listed; add `TERRAIN_SKILLS = {"terrain-shape", "terrain-landmark", "terrain-ecology", "terrain-integrate"}` and `CAVE = re.compile(r"\bterrain-cave\b")`.
- `leftovers(text: str, allow_fabric: bool = False, cave_forbidden: bool = False) -> list[tuple[int, str]]`: skip a `32,768` hit on a line containing `fillbiome`; add `CAVE` when `cave_forbidden`. `test_no_chapman_leftovers` passes `cave_forbidden=skill in TERRAIN_SKILLS` and `allow_fabric` for paths under `skills/design-monument/tools/voxel/` or `skills/terrain-shape/tools/terrain/` (the copied README may name Chapman's Fabric mod).
- `skill_paths(text: str) -> list[str]`: every match of `(?<![\w/.-])((?:<terrain-shape>/|\.\./[a-z0-9-]+/)?(?:reference|scripts|tools)/[\w./-]+\.(?:md|py|json))`, in order.
- `test_reference_links_resolve_in_skill_folder(skill)`, parametrized over `sorted(TERRAIN_SKILLS)`: for every Markdown file in the skill, each `skill_paths` entry resolves (`<terrain-shape>/` → `skills/terrain-shape/`, otherwise relative to `skills/<skill>/`) to an existing file.

- [ ] **Step 4: Run the Verify command** — Expected: pass (terrain-skill cases deselected).

- [ ] **Step 5: Commit**

```bash
git add tests/ashlar/test_skill_text.py
git commit -m "test: extend the static skill checks to the four terrain skills"
```

```json:metadata
{"files": ["tests/ashlar/test_skill_text.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k \"not terrain_\"", "acceptanceCriteria": ["four terrain skills scanned", "new Chapman names and terrain-cave (terrain skills only) flagged", "32,768 allowed on fillbiome lines", "skill-folder link resolution test", "existing cases pass"], "modelTier": "mechanical"}
```

---

## Task 3: Column reader, backups and restore in the placer

**Goal:** `ashlar_place.py` reads boxes column by column, writes complete backups (F1), restores them exactly, and places a phase behind a backup.

**Files:**
- Modify: `skills/exec-ashlar/scripts/ashlar_place.py`
- Modify: `tests/ashlar/fake_ashlar_mcp.py`
- Create: `tests/ashlar/test_backup.py`

**Interfaces (added to `ashlar_place.py`):**

```python
Columns = dict[tuple[int, int], list[tuple[int, int, str]]]
def column_tiles(box: Box, max_columns: int = 1024, max_cells: int = 200_000) -> list[Box]
def parse_columns(text: str) -> Columns          # adds "minecraft:" when an id has no namespace
def read_columns(client: McpClient, box: Box, world: str | None) -> Columns
def check_complete(columns: Columns, box: Box) -> None      # PlacerError(EXIT_REFUSED)
def restore_build(columns: Columns, world: str | None) -> dict[str, Any]   # mc_build args
def write_backup(out: Path, box: Box, world: str | None, columns: Columns, plugin: str | None) -> dict[str, Any]
def load_backup(path: Path) -> tuple[dict[str, Any], Columns]   # PlacerError(EXIT_INPUT) on a bad checksum or incomplete runs
def take_backup(client: McpClient, box: Box, world: str | None, out: Path, limits: Limits) -> dict[str, Any]
```

CLI: `backup --box X1 Y1 Z1 X2 Y2 Z2 --out DIR [--world W] [--log PATH]`; `restore DIR [--world W] [--player-margin 2] [--log PATH]`; `place` gains `--backup DIR` in the group with `--snapshot` / `--no-snapshot`.

**Acceptance Criteria:**
- [ ] Column tiles cover the box exactly once, each with at most 1,024 columns and 200,000 cells, for negative coordinates too.
- [ ] `parse_columns` reads Ashlar's format, including negative y (`-64--1 deepslate`) and block states.
- [ ] `backup` writes F1 only after every column is present and covers the full height, and after the restore fills pass the placer's validation and paging; otherwise exit 3 and nothing is written in `--out`.
- [ ] `restore` checks players (exit 4), then places fills with `liquids: "static"` and `connect: false`; after `place --backup` and `restore`, a fresh backup equals the original column for column.
- [ ] `place --backup DIR` takes the backup after the player check and before the first `mc_build`, and refuses (exit 3) if `DIR` already holds a complete backup.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_backup.py tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q` → all pass

**Steps:**

- [ ] **Step 1: Give the fake server a world**

`fake_ashlar_mcp.py` gains `FAKE_WORLD` (path to JSON `{"ground": 63, "cells": {"x,y,z": "minecraft:…"}, "biomes": {"cx,cz": "minecraft:…"}, "forceloaded": [[cx, cz]]}`). Below `ground` a cell is `minecraft:stone`, else `minecraft:air`, unless `cells` says otherwise. The world is loaded at start and written back after every call that changes it.
- `mc_build` applies `fills` (replace; `filter` restricts to cells whose current id matches the filter's id), then `blocks`; replies as today.
- `mc_inspect` with `format: "columns"` replies with a header line, then `x,z: y1-y2 id | …` lines for the box, ids without the namespace, merging equal neighbours. `FAKE_DROP_COLUMN="x,z"` leaves that column out.
- `mc_status` stays `Plugin version: 0.4.9`.

- [ ] **Step 2: Write the failing tests** (`tests/ashlar/test_backup.py`, reusing `config`, `run`, `calls` from `test_place_mcp.py` by import)

```python
def test_parse_columns_handles_negative_y_and_states():
    text = ("Region (default) x=[5..5] y=[-64..10] z=[-3..-3] …\n"
            "5,-3: -64--1 deepslate | 0-0 oak_stairs[facing=north,half=bottom] | 1-10 air")
    assert ap.parse_columns(text) == {(5, -3): [
        (-64, -1, "minecraft:deepslate"),
        (0, 0, "minecraft:oak_stairs[facing=north,half=bottom]"),
        (1, 10, "minecraft:air")]}

def test_column_tiles_respect_limits_and_cover_box():
    box = (-40, 0, -40, 39, 299, 39)
    tiles = ap.column_tiles(box)
    seen = Counter((x, z) for t in tiles for x in range(t[0], t[3] + 1) for z in range(t[2], t[5] + 1))
    assert set(seen.values()) == {1} and len(seen) == 80 * 80
    assert all((t[3] - t[0] + 1) * (t[5] - t[2] + 1) <= 1024 for t in tiles)
    assert all(ap.volume(t) <= 200_000 for t in tiles)

def test_backup_writes_manifest_and_columns(tmp_path): ...       # columns == 4*4, sha256 matches the .gz bytes, complete is true
def test_backup_refuses_incomplete_read(tmp_path): ...           # FAKE_DROP_COLUMN → returncode 3, out dir empty
def test_load_backup_rejects_bad_checksum(tmp_path): ...         # flip a byte → PlacerError code 2
def test_place_backup_then_restore_round_trip(tmp_path): ...     # backup A; place --backup; restore; backup B; B.columns == A.columns
def test_place_backup_reads_before_any_build(tmp_path): ...      # call order: mc_players, mc_status, mc_inspect…, mc_build…
def test_place_backup_refuses_to_overwrite_a_backup(tmp_path): ...  # second place --backup same DIR → 3, no mc_build
def test_restore_uses_static_liquids_and_no_connect():
    args = ap.restore_build({(0, 0): [(60, 62, "minecraft:water[level=0]"), (63, 70, "minecraft:air")]}, None)
    assert args["liquids"] == "static" and args["connect"] is False
def test_restore_refuses_when_player_inside(tmp_path): ...       # FAKE_PLAYERS inside → 4, no mc_build
```

- [ ] **Step 3: Run them** — Expected: FAIL (`column_tiles` undefined).

- [ ] **Step 4: Implement**

- `column_tiles`, `parse_columns`, `read_columns`: copy them verbatim from `redstone`'s `462f592` (see Global Constraints) rather than writing new ones. As committed there: `column_tiles` keeps the full y range and splits in x, and also in z when one full-depth x strip exceeds the cap; `parse_columns` skips the `Region (default) …` header, reads data lines `^(-?\d+),(-?\d+): (.+)$` with runs `^(-?\d+)-(-?\d+) (\S+)$` split on ` | `, adds `minecraft:` when missing, and raises `PlacerError(EXIT_SERVER)` on a run it cannot parse; `read_columns` makes one `mc_inspect` per tile with `format: "columns"`, passes `world` only when it is not `None`, and stops on the first `isError` reply with `PlacerError(…, EXIT_SERVER)`, redacted. Only if `462f592` is unreachable, write them to this description.
- `check_complete`: every column of the box is present, its runs are contiguous, and they start at the box's y1 and end at its y2.
- `restore_build`: one fill per run, merging runs with equal `(z, y1, y2, state)` at consecutive x; `liquids: "static"`, `connect: false`, plus `world` when given.
- Factor the checks inside `load_build` into `validate_build(data: dict[str, Any], limits: Limits, where: str) -> dict[str, Any]`; `load_build` reads the file and calls it.
- `take_backup`: `mc_status` (record the plugin version), `read_columns`, `check_complete`, `validate_build(restore_build(…))` and `make_pages`, then `write_backup` (write to a temporary name and rename, so an interrupted backup never looks complete).
- `cmd_place` with `--backup DIR`: refuse if `DIR/manifest.json` exists with `"complete": true`; after the player check, `take_backup` over the union of the page boxes; then pages as today; the report gains `"backup": DIR`.
- `cmd_restore`: `load_backup`, player check over the box, pages from `restore_build` through `make_pages`, report as `place` does.

- [ ] **Step 5: Run the Verify command** — Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/fake_ashlar_mcp.py tests/ashlar/test_backup.py
git commit -m "feat(exec-ashlar): column backups and exact restore in the placer"
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/fake_ashlar_mcp.py", "tests/ashlar/test_backup.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_backup.py tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q", "acceptanceCriteria": ["column tiles exact and within limits incl. negative coordinates", "parse_columns reads negative y and states", "incomplete backup writes nothing (exit 3)", "restore static, no connect, player check", "place --backup round trip equals original", "existing placer tests still pass"], "modelTier": "standard"}
```

---

## Task 4: Height reads, flowing cap and `filter` checks

**Goal:** The placer writes heights files (F2), keeps flowing liquids under Ashlar's per-call cap, and validates fill filters.

**Files:**
- Modify: `skills/exec-ashlar/scripts/ashlar_place.py`
- Modify: `tests/ashlar/fake_ashlar_mcp.py`
- Create: `tests/ashlar/test_heights.py`
- Modify: `tests/ashlar/test_place_core.py`

**Interfaces:**

```python
def parse_matrix(text: str) -> tuple[int, dict[int, list[int | None]]]   # (top-left x, {z: row})
def read_heights(client: McpClient, area: tuple[int, int, int, int], world: str | None) -> dict[str, Any]   # F2
# Limits gains max_flowing: int = 2000 (CLI --max-flowing); plan_summary gains "liquid_cells"
```

CLI: `heights --area X1 Z1 X2 Z2 --out FILE [--world W]`.

**Acceptance Criteria:**
- [ ] `parse_matrix` takes the top-left x from the matrix header and each row's z from its `z=<n>:` label; tokens that are not integers become `None`.
- [ ] `heights` tiles the area into reads of at most 200,000 x/z cells, calls `mc_survey` with `matrix: true` once per tile for each of `SOLID`, `SOLID_OR_LIQUID_NO_LEAVES` and `ANY`, and writes F2 with index `xi * nz + zi`.
- [ ] A phase with `liquids: "flow"` pages so no page holds more than 2,000 water or lava cells; `plan` reports `liquid_cells`.
- [ ] A fill whose `filter` is not a `minecraft:` block state string is invalid input (exit 2).

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_heights.py tests/ashlar/test_place_core.py -q` → all pass

**Steps:**

- [ ] **Step 1: Fake server** — `mc_survey` with `matrix: true` computes, from the fake world, the highest cell per column by type (`SOLID`: not air, water, lava or `*_leaves`; `SOLID_OR_LIQUID_NO_LEAVES`: not air or `*_leaves`; `ANY`: not air) and replies with a summary line, a `Height matrix (… top-left = x=<x1> z=<z1>):` line and `z=<z>: h h h …` rows.

- [ ] **Step 2: Write the failing tests**

```python
def test_parse_matrix_reads_rows_and_origin():
    text = ("Area x=[-5..-3] z=[-3..-2] (3x2). Surface y: …\n"
            "Height matrix (z rows top-to-bottom, x columns left-to-right, top-left = x=-5 z=-3):\n"
            "z=-3: 62 63 -\nz=-2: 64 64 64")
    assert ap.parse_matrix(text) == (-5, {-3: [62, 63, None], -2: [64, 64, 64]})

def test_heights_negative_origin(tmp_path): ...      # area -5,-3..4,2 over the fake world; F2 size [10, 6]; ground at index 0 == 62
def test_heights_tiles_large_areas(tmp_path): ...    # area 500x500: every mc_survey call ≤ 200,000 cells; 3 types per tile
def test_flowing_pages_stay_under_cap():             # (test_place_core.py) 3,000 water cells with liquids flow → every page ≤ 2,000 liquid cells
def test_filter_must_be_a_block_state(tmp_path):     # (test_place_core.py) filter "air" → PlacerError code 2
```

- [ ] **Step 3: Run them** — Expected: FAIL.

- [ ] **Step 4: Implement** `parse_matrix`, `read_heights` (tile the x/z area by rows of z so each tile has ≤ 200,000 cells), `cmd_heights`; in `make_pages`, when `build.get("liquids") == "flow"`, split liquid fills over `max_flowing` and add the page's liquid-cell count to the pack limit; in `load_build`, validate `filter` with `_block`.

- [ ] **Step 5: Run the Verify command** — Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/fake_ashlar_mcp.py tests/ashlar/test_heights.py tests/ashlar/test_place_core.py
git commit -m "feat(exec-ashlar): height reads, a flowing-liquid page cap and filter checks"
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/fake_ashlar_mcp.py", "tests/ashlar/test_heights.py", "tests/ashlar/test_place_core.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_heights.py tests/ashlar/test_place_core.py -q", "acceptanceCriteria": ["matrix parsed with header x and row z", "heights tiled within 200,000 cells, three types, F2 index xi*nz+zi", "flow pages within 2,000 liquid cells", "bad filter is exit 2"], "modelTier": "standard"}
```

---

## Task 5: Commands runner, biome probe and biome restore

**Goal:** The placer runs commands files (F3) with paired force-loads, player checks and resumable progress, probes biomes per chunk (F5), and writes biome-restore commands.

**Files:**
- Modify: `skills/exec-ashlar/scripts/ashlar_place.py`
- Modify: `tests/ashlar/fake_ashlar_mcp.py`
- Create: `tests/ashlar/test_runner.py`

**Interfaces:**

```python
EXIT_PARTIAL = 6        # the run finished but some commands failed
COMMAND_FORMS: dict[str, re.Pattern[str]]   # "place feature" and "fillbiome", exact forms below
def load_commands(path: Path, limits: Limits, max_biome_blocks: int = 32_768) -> dict[str, Any]
def command_chunks(command: str) -> set[tuple[int, int]]     # place feature: its chunk plus a one-chunk margin
def forceload_tiles(chunks: set[tuple[int, int]], max_chunks: int = 256) -> list[tuple[int, int, int, int]]
def parse_forceload_query(text: str) -> set[tuple[int, int]]
def run_commands(client: McpClient, commands: dict[str, Any], *, progress: Path | None,
                 world: str | None, dimension: str | None, player_margin: int) -> dict[str, Any]
```

Forms (anything else is exit 2):
- `^place feature (?P<id>[a-z0-9_.-]+:[a-z0-9_./-]+) (?P<x>-?\d+) (?P<y>-?\d+) (?P<z>-?\d+)$`
- `^fillbiome (?P<x1>-?\d+) (?P<y1>-?\d+) (?P<z1>-?\d+) (?P<x2>-?\d+) (?P<y2>-?\d+) (?P<z2>-?\d+) (?P<id>[a-z0-9_.-]+:[a-z0-9_./-]+)$`

CLI: `commands FILE [--check] [--progress PATH] [--world W] [--dimension DIM] [--player-margin 2] [--log PATH]`; `biome-probe --box X1 Y1 Z1 X2 Y2 Z2 --heights FILE --biomes FILE --out FILE [--candidates A,B] [--world W]`; `biome-restore PROBE --out FILE [--max-biome-blocks 32768]`.

**Acceptance Criteria:**
- [ ] `--check` (and every run) refuses other commands, bad coordinates, positions outside the file's box and `fillbiome` volumes over the limit, with exit 2 and no server contact.
- [ ] A run adds the `minecraft:` prefix, runs `minecraft:forceload query` first, never adds or removes a chunk the server already force-loads (other chunks of that tile are then force-loaded one at a time), and pairs every `forceload add` with the same `forceload remove`.
- [ ] Each tile checks players first; a player inside the tile's box grown by the margin stops the run with exit 4, with no force-load left.
- [ ] A reply without `isError` that starts with a failure phrase (`Failed`, `Unknown`, `Incorrect`, `Invalid`, `That position is not loaded`, `Too many blocks`) is a failed command: recorded, the run continues, exit 6 at the end. An `isError` reply or a client error stops the run: the tile's force-load is still removed (a failed removal is reported with its chunks), progress is kept, exit 5.
- [ ] With `--progress`, a rerun skips every command already recorded.
- [ ] `--dimension DIM` runs each command as `minecraft:execute in DIM run …`.
- [ ] `biome-probe` tests, per chunk at the surface height from the heights file, the previous chunk's biome, then `--candidates`, then the rest of the biomes file, and writes F5 (`unknown` when none passes), inside paired force-loads.
- [ ] `biome-restore` writes an F3 `biomes` file: one `fillbiome` per chunk column of the probe box, split vertically so each stays within the limit (16 × 16 × 128 = 32,768), skipping and listing `unknown` chunks.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_runner.py tests/ashlar/test_place_mcp.py -q` → all pass

**Steps:**

- [ ] **Step 1: Fake server** — `mc_command` handles `minecraft:forceload add|remove <x1> <z1> [<x2> <z2>]` (block coordinates → chunk set), `minecraft:forceload query` (`No force loaded chunks were found in minecraft:overworld` or `There are N force loaded chunks in minecraft:overworld at: [cx, cz], …`), `minecraft:place feature …` (`Placed feature <id> at x, y, z`; `FAKE_FAIL_FEATURE=n` makes the n-th reply `Failed to place feature`), `minecraft:fillbiome …` (sets `biomes` for the chunks touched; replies `N biome entries set …`), `minecraft:execute if biome x y z <id>` (`Test passed` / `Test failed` from `biomes`, default `minecraft:plains`). `FAKE_ERROR_COMMAND=n` makes the n-th `place feature`/`fillbiome` reply `isError` with `Error: plugin unreachable`. The fake records the force-loaded set in `FAKE_WORLD`.

- [ ] **Step 2: Write the failing tests**

```python
def test_load_commands_accepts_only_the_two_forms(tmp_path): ...   # setblock, a short place feature, fillbiome 16x16x129, a position outside box → each exit 2
def test_command_chunks_and_forceload_tiles_across_zero():
    assert ap.command_chunks("place feature minecraft:oak -1 64 -1") == {
        (cx, cz) for cx in (-2, -1, 0) for cz in (-2, -1, 0)}
    tiles = ap.forceload_tiles({(cx, cz) for cx in range(-20, 20) for cz in range(-3, 3)})
    assert all((t[2] - t[0] + 1) * (t[3] - t[1] + 1) <= 256 for t in tiles)
    assert {(cx, cz) for t in tiles for cx in range(t[0], t[2] + 1) for cz in range(t[1], t[3] + 1)} \
        >= {(cx, cz) for cx in range(-20, 20) for cz in range(-3, 3)}
def test_runner_prefixes_and_pairs_forceloads(tmp_path): ...        # call log: query, players, add, place…, remove (same coords as add)
def test_runner_skips_already_loaded_chunks(tmp_path): ...          # preloaded chunk never in an add or remove
def test_runner_records_failed_tree_and_continues(tmp_path): ...    # FAKE_FAIL_FEATURE=2 → exit 6, later commands ran, report lists index 2
def test_runner_server_error_still_removes_forceload_and_resumes(tmp_path): ...  # FAKE_ERROR_COMMAND=3 → exit 5, last call a remove; rerun with the same --progress skips 1–2 and completes
def test_runner_stops_before_a_tile_with_a_player(tmp_path): ...    # player in tile 2 → exit 4, tile 1 done, adds == removes
def test_runner_wraps_execute_in_for_another_dimension(tmp_path): ...
def test_biome_probe_orders_candidates_and_marks_unknown(tmp_path): ...
def test_biome_restore_tiles_chunks_within_limit(tmp_path): ...     # probe box y 0..299 → 3 commands per chunk, each ≤ 32,768 blocks, x1 % 16 == 0 and x2 % 16 == 15
```

- [ ] **Step 3: Run them** — Expected: FAIL.

- [ ] **Step 4: Implement** the interfaces above. Group commands by tile in file order of their first command; per tile: `mc_players` check, `forceload add` (block coordinates of the tile's chunk corners: `cx*16`, `cz*16`, `cx2*16+15`, `cz2*16+15`), the commands one at a time with a progress line each, then `forceload remove` in a `finally`. `parse_forceload_query` returns the set of `[cx, cz]` pairs and the empty set for the "No force loaded" reply. The report lists tiles, force-loads added and removed, counts by command form and feature id, failed commands with redacted replies, and any force-load left behind.

- [ ] **Step 5: Run the Verify command** — Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/fake_ashlar_mcp.py tests/ashlar/test_runner.py
git commit -m "feat(exec-ashlar): bulk runner for place feature and fillbiome, biome probe and restore"
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/fake_ashlar_mcp.py", "tests/ashlar/test_runner.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_runner.py tests/ashlar/test_place_mcp.py -q", "acceptanceCriteria": ["only the two forms; --check offline", "prefix, query, paired force-loads, preloaded chunks untouched", "per-tile player check exit 4", "failed command continues exit 6; server error removes force-load exit 5", "progress resume", "probe order and unknown; restore tiles within 32,768"], "modelTier": "standard"}
```

---

## Task 6: Vegetation modules in `stamp.py`

**Goal:** `stamp.py` stamps F7 vegetation modules: overlapping trees allowed, wood and leaves placed into air only, ground parts first.

**Files:**
- Modify: `skills/exec-ashlar/scripts/stamp.py`
- Modify: `tests/ashlar/test_stamp.py`

**Acceptance Criteria:**
- [ ] Vegetation placements may overlap each other; a vegetation placement that overlaps a non-vegetation placement is an error.
- [ ] The output for a phase is: every placement's `ground` part (as stamped, no filter), then every `wood` part, then every `leaves` part; `wood` and `leaves` cells are fills with `"filter": "minecraft:air"`; single cells become 1 × 1 × 1 fills, merged along x where block and neighbours match.
- [ ] Rotation and mirroring transform vegetation parts like any module (log `axis` turns at 90° and 270°).
- [ ] A vegetation module without `anchor` or with an unknown part key is an error.
- [ ] Every existing stamp test still passes.

**Verify:** `uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
TREE = {"name": "t", "size": [3, 4, 3], "kind": "vegetation", "anchor": [1, 0, 1],
        "ground": {"fills": [], "blocks": []},
        "wood": {"fills": [{"from": [1, 0, 1], "to": [1, 2, 1], "block": "minecraft:oak_log[axis=y]"}], "blocks": []},
        "leaves": {"fills": [{"from": [0, 3, 0], "to": [2, 3, 2], "block": "minecraft:oak_leaves[persistent=true]"}],
                   "blocks": [{"pos": [1, 2, 0], "block": "minecraft:oak_leaves[persistent=true]"}]}}

def test_vegetation_overlap_allowed_and_ordered(tmp_path): ...   # two TREEs 1 block apart → no error; all wood fills precede all leaves fills
def test_vegetation_parts_carry_the_air_filter(tmp_path): ...    # wood/leaves fills filter == "minecraft:air"; ground fills have no filter; output "blocks" empty
def test_vegetation_cannot_overlap_a_building(tmp_path): ...     # TREE overlapping a plain module → StampError
def test_vegetation_rotation_turns_log_axis():                   # a branch log axis=x at rotation 90 → axis=z
def test_vegetation_module_needs_anchor_and_parts():             # missing anchor, or a "roots" key → StampError
```

- [ ] **Step 2: Run them** — Expected: FAIL.

- [ ] **Step 3: Implement** in `stamp_all` and `stamp`: detect `kind == "vegetation"`, validate the keys, transform each part with the existing `stamp` logic, skip the overlap check between two vegetation placements, and assemble the three part lists in order. Add `_cells_to_fills(blocks) -> list[dict]` for the 1 × 1 × 1 conversion with x-run merging.

- [ ] **Step 4: Run the Verify command** — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/exec-ashlar/scripts/stamp.py tests/ashlar/test_stamp.py
git commit -m "feat(exec-ashlar): vegetation modules in stamp.py"
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/stamp.py", "tests/ashlar/test_stamp.py"], "verifyCommand": "uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q", "acceptanceCriteria": ["vegetation overlap allowed, not with buildings", "ground then wood then leaves; air filter on wood and leaves", "rotation turns log axis", "anchor and part keys validated", "existing tests pass"], "modelTier": "mechanical"}
```

---

## Task 7: Site reads, surfaces and trees (`site.py`)

**Goal:** The toolkit loads F1 site reads and F2 heights files, derives the existing ground, water and top per column, groups existing trees, and flags non-natural blocks.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/site.py`
- Create: `tests/ashlar/terrain/sitegen.py` (fixture writer shared by later tasks)
- Create: `tests/ashlar/terrain/test_site.py`

**Interfaces:**

```python
@dataclass
class Site:
    box: tuple[int, int, int, int, int, int]
    world: str | None
    columns: dict[tuple[int, int], list[tuple[int, int, str]]]
    def block(self, x: int, y: int, z: int) -> str          # KeyError outside the box

@dataclass
class Surfaces:
    origin: tuple[int, int]            # (x1, z1) of the arrays
    ground: np.ndarray                 # (nx, nz) highest solid non-vegetation block, NaN if none
    water: np.ndarray                  # water surface y where water lies over the ground, else NaN
    top: np.ndarray                    # highest non-air block, trees included

@dataclass
class Tree:
    cells: set[tuple[int, int, int]]
    trunk_columns: set[tuple[int, int]]
    base_y: int

def load_site(path: str | Path) -> Site                  # checks sha256 and completeness
def write_site(path: str | Path, site: Site) -> None     # F1, same bytes layout as the placer's write_backup
def load_heights(path: str | Path) -> dict[str, np.ndarray | tuple]   # {"origin", "ground", "surface", "top"} arrays (nx, nz), NaN for null
def surfaces(site: Site) -> Surfaces
def find_trees(site: Site) -> list[Tree]
def unnatural_blocks(site: Site, box: tuple[int, int, int, int, int, int]) -> dict[str, int]
TRUNK: frozenset[str]; LEAVES: frozenset[str]; ATTACHED: frozenset[str]; PLANTS: frozenset[str]; NATURAL: frozenset[str]
```

**Acceptance Criteria:**
- [ ] `write_site` then `load_site` round-trips; a changed byte fails the checksum (`ValueError`).
- [ ] `surfaces` ignores logs, leaves, attachments and plants when finding the ground, reports water above the bed, and keeps trees in `top`.
- [ ] `find_trees` makes one tree per connected trunk (26-connected), gives each leaf to the nearest trunk through leaves (6-connected, at most 6 steps, as vanilla leaf distance) and attachments to the tree they touch; `trunk_columns` are the trunk's lowest cells.
- [ ] `unnatural_blocks` counts blocks outside `NATURAL` (planks, glass, wool, doors, beds, rails …) inside the box.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_site.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write `sitegen.py`** — `make_site(path, box, *, ground=64, water=None, cells=None, trees=()) -> Site` builds a site whose columns are stone below `ground`, grass at `ground`, air above (water runs up to `water` where given), applies `cells`, plants simple trees (`tree(x, z, base, height=5, radius=2)`: oak log column plus a leaf blob) and writes it with `site.write_site`.

- [ ] **Step 2: Write the failing tests**

```python
def test_load_site_round_trip_and_checksum(tmp_path): ...
def test_surfaces_ignore_trees_and_read_water(tmp_path):
    s = surfaces(make_site(tmp_path / "s", (0, 50, 0, 7, 80, 7), ground=64,
                           trees=[tree(2, 2, 65)], water={(6, 6): 62},
                           cells={(6, y, 6): "minecraft:dirt" for y in range(50, 59)}))
    assert s.ground[2, 2] == 64 and s.top[2, 2] > 68
    assert s.ground[6, 6] == 58 and s.water[6, 6] == 62
def test_find_trees_groups_trunks_and_leaves(tmp_path): ...       # two trees, touching canopies → 2 trees; each leaf in the nearer one; a vine joins its tree
def test_unnatural_blocks_flags_planks(tmp_path): ...             # oak_planks counted; stone, short_grass, oak_log not
```

- [ ] **Step 3: Run them** — Expected: FAIL.

- [ ] **Step 4: Implement** `site.py`. Block classes match ids with or without states (`minecraft:oak_log[axis=y]` is a trunk). `TRUNK`: ids ending `_log`, `_wood`, `_stem`, `_hyphae`, plus `minecraft:mushroom_stem`, `minecraft:mangrove_roots`; `LEAVES`: ids ending `_leaves`, plus the huge-mushroom blocks and wart blocks; `ATTACHED`: vines, cocoa, bee nests, glow lichen, moss carpets, hanging roots, propagules, snow layers; `PLANTS`: grass, ferns, flowers, bushes, saplings, crops-like natural plants. The builder completes the lists (spec §15).

- [ ] **Step 5: Run the Verify command** — Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/terrain-shape/tools/terrain/site.py tests/ashlar/terrain/sitegen.py tests/ashlar/terrain/test_site.py
git commit -m "feat(terrain): site reads, existing surfaces and tree grouping"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/site.py", "tests/ashlar/terrain/sitegen.py", "tests/ashlar/terrain/test_site.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_site.py -q", "acceptanceCriteria": ["F1 round trip with checksum", "ground ignores vegetation; water and top read", "trees grouped by trunk with nearest-trunk leaves", "unnatural blocks counted"], "modelTier": "standard"}
```

---

## Task 8: Meeting the existing ground, and new GATE A checks

**Goal:** Recipes with a `site` key blend into the existing ground at the box edge, water plans come from `sea_level` and `water` basins, and `verify` checks the edge and the water.

**Files:**
- Modify: `skills/terrain-shape/tools/terrain/site.py`
- Modify: `skills/terrain-shape/tools/terrain/recipe.py`
- Modify: `skills/terrain-shape/tools/terrain/verify.py`
- Create: `tests/ashlar/terrain/test_edges_and_water.py`

**Interfaces:**

```python
# site.py
def auto_band(h: np.ndarray, ground: np.ndarray) -> int     # max(8, ceil(0.3 * max |h - ground| over the 8 outermost rings)), at most min(nx, nz) // 2
def blend_to_existing(hf: HeightField, ground: np.ndarray, band: int) -> HeightField   # w = smoothstep(0, band, d); h = ground * (1 - w) + h * w; d = rings from the edge (0 on the outer ring)
def ground_for(recipe: dict, project_dir: Path) -> tuple[Site, Surfaces, np.ndarray]   # site, its surfaces, ground cropped to the recipe grid
def water_levels(hf: HeightField, recipe: dict) -> np.ndarray   # (nx, nz) level or NaN
# recipe.py
def build_field(recipe: dict, project_dir: Path | None = None) -> HeightField   # after erosion: pads (HeightField.build_pad, world → grid coordinates), then the blend when recipe["site"] is set
# verify.py
def verify(hf, spec=None, recipe=None, *, ground=None, water=None, existing_water=None, ...) -> Report
```

`water_levels`: every column with `h < sea_level` gets `sea_level` (Chapman's rule); each `water` entry floods, from its `at` cell (world x, z), the 4-connected columns with `h < level`, setting `level`.

**Acceptance Criteria:**
- [ ] With a site, the field's outer ring equals the existing ground within one block, and the field is unchanged deeper than `band` rings in.
- [ ] `auto_band` gives 14 for a 46-block difference and never less than 8.
- [ ] `verify(..., ground=…)` adds `edge_match` (outer-ring `max |round(h) − ground| ≤ 1`).
- [ ] `verify(..., water=…, existing_water=…)` adds `water_contained` (every water column's 4-neighbours inside the grid hold water at the same level or stand at or above it; on the outer ring, existing water stands at the same level) and `no_dry_shelf` (no dry column below a neighbour's water level next to it).
- [ ] A basin seeded on one side of a ridge leaves the other side dry.
- [ ] A recipe pad is flat at its level across its footprint and blends into the field over its shoulder.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_recipe_pads_are_flat_and_blended(tmp_path): ...        # pad level 70 over a rolling field → every footprint column 70
def test_blend_matches_ring_and_keeps_interior(tmp_path): ...   # flat ground 64, a cone up to 164 → ring within 1 of 64; centre unchanged
def test_auto_band_grows_with_difference():
    h = np.full((64, 64), 110.0); g = np.full((64, 64), 64.0)
    assert auto_band(h, g) == 14 and auto_band(g + 1, g) == 8
def test_recipe_with_site_blends_after_erosion(tmp_path): ...
def test_edge_match_fails_without_blend(tmp_path): ...
def test_water_at_edge_must_meet_existing_water(tmp_path): ...  # basin touching the edge: outside dry and lower → water_contained fails; outside water at the same level → passes
def test_basin_flood_fill_stays_in_its_basin(): ...
```

- [ ] **Step 2: Run them** — Expected: FAIL.

- [ ] **Step 3: Implement** the interfaces. `build_field` keeps its old behaviour when `site` is absent; `project_dir` resolves `site.read`. `existing_water` is `Surfaces.water` cropped to the grid.

- [ ] **Step 4: Run the Verify command** — Expected: all pass, Chapman's copied tests included.

- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/site.py skills/terrain-shape/tools/terrain/recipe.py skills/terrain-shape/tools/terrain/verify.py tests/ashlar/terrain/test_edges_and_water.py
git commit -m "feat(terrain): blend into the existing ground; edge and water checks in GATE A"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/site.py", "skills/terrain-shape/tools/terrain/recipe.py", "skills/terrain-shape/tools/terrain/verify.py", "tests/ashlar/terrain/test_edges_and_water.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain -q", "acceptanceCriteria": ["ring within 1 of existing ground; interior unchanged", "auto_band 14 for 46, min 8", "edge_match, water_contained, no_dry_shelf checks", "basins flood only their own side", "copied tests still pass"], "modelTier": "standard"}
```

---

## Task 9: Live materialisation and fills (`terrain/live.py`)

**Goal:** A verified field becomes the exact cells to write in the live world (spec §7.5), split into phase tiles and merged into fills, plus the expected-surface file.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/live.py`
- Create: `tests/ashlar/terrain/test_live.py`

**Interfaces:**

```python
@dataclass
class LiveWrite:
    origin: tuple[int, int, int]      # world (x, y, z) of codes[0, 0, 0]
    codes: np.ndarray                 # uint16 (nx, ny, nz); 0 = leave as is, 1 = air
    palette: list[str]                # palette[0] == "skip", palette[1] == "minecraft:air"
    removed_trees: int = 0
    reach: int = 0                    # farthest written column outside the terrain box, in blocks

def materialize_live(hf: HeightField, spec: MaterialSpec, site: Site, recipe: dict | None, *,
                     water: np.ndarray | None = None, protect: np.ndarray | None = None, seal: int = 4) -> LiveWrite
                     # recipe gives origin and material.strata_top; None → origin from the site's box
def greedy_fills(write: LiveWrite) -> list[dict]          # exact cover of every code > 0
def split_columns(write: LiveWrite, max_columns: int = 128) -> list[LiveWrite]   # x/z tiles, empty ones dropped
def decode(fills: list[dict]) -> dict[tuple[int, int, int], str]   # test helper, later fills win
def expected_surface(hf: HeightField, water: np.ndarray | None, kept_trunks: set[tuple[int, int]],
                     origin: tuple[int, int]) -> dict   # F6
```

Rules (spec §7.5): `g` ground, `t` top without kept trees, `s = round(h)`, `w` water level, `n` lowest new surface among the 4 neighbours (outside the grid: the existing ground), `b = min(g, s, n) − seal`. Column bottom to top: deep rock `b … s − depth − 1` (strata bands by absolute y from `material.strata_top`, default `max(s)`, else `spec.stone`), subsurface `s − depth … s − 1`, surface `s`, water `s + 1 … w`, air `max(s, w) + 1 … t`. Trees: rooted on a changed column (`s ≠ g` at any trunk column) → every cell air unless inside new solid; otherwise kept (cells left 0). `protect` columns (Task 15) are left 0 entirely. `seal > spec.subsurface_depth` or `ValueError`.

**Acceptance Criteria:**
- [ ] Each rule above holds on synthetic sites, including strata by absolute y and water between surface and level.
- [ ] Cells below `b` and kept-tree cells are never written; removed trees are cleared whole, outside the box too, and `reach` reports the farthest such column.
- [ ] `decode(greedy_fills(w))` equals the cells with code > 0, and no fill covers a code-0 cell.
- [ ] `split_columns` tiles are at most 128 × 128 columns and together hold every written cell once.
- [ ] `expected_surface` gives `max(s, w)` per column and skips kept trunk columns.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_live.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_raised_ground_fills_from_old_ground_minus_seal(tmp_path): ...   # flat 64, s = 70: rows 60..66 stone, 67..69 dirt, 70 grass, < 60 untouched
def test_lowered_ground_clears_air_to_old_top(tmp_path): ...             # s = 58 under ground 64: 54..58 solid, 59..64 air
def test_cliff_faces_and_seal_band(tmp_path): ...                         # s = 80 beside s = 60 → solid from 56; a pocket at 62 under unchanged ground 64 filled
def test_crossing_trees_removed_whole_or_kept(tmp_path): ...              # tree rooted inside on changed ground with leaves 2 blocks outside → all air, reach == 2; tree rooted outside with leaves over the box → untouched
def test_water_fills_between_surface_and_level(tmp_path): ...
def test_strata_bands_by_absolute_y(tmp_path): ...
def test_greedy_fills_decode_exactly(): ...                               # random LiveWrite with 0s → exact
def test_split_columns_respects_size(): ...                               # 300 x 20 write → tiles ≤ 128 x 128
def test_expected_surface_marks_water_and_skips_kept_trunks(tmp_path): ...
def test_seal_must_exceed_subsurface_depth(tmp_path): ...
```

- [ ] **Step 2: Run them** — Expected: FAIL.

- [ ] **Step 3: Implement.** Surface and subsurface ids come from `materialize.resolve_surface(hf, spec)`. The grid spans the terrain box grown to cover removed trees, from `min(b)` to the highest of `t`, `s`, `w`. `greedy_fills` covers each code with boxes (the voxel toolkit's `_greedy_boxes` in `skills/design-monument/tools/voxel/decompose.py` shows one way); fills carry `minecraft:` block strings, `minecraft:air` for code 1.

- [ ] **Step 4: Run the Verify command** — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/live.py tests/ashlar/terrain/test_live.py
git commit -m "feat(terrain): materialise only the cells that must change in a live world"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/live.py", "tests/ashlar/terrain/test_live.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_live.py -q", "acceptanceCriteria": ["seal band, faces, water, strata rules", "nothing below b; kept trees untouched; crossing trees removed whole with reach", "fills decode exactly; no fill on skip cells", "tiles <= 128x128 cover every cell once", "expected surface with skips"], "modelTier": "standard"}
```

---

## Task 10: Carve forms, flowing sources, gravity check

**Goal:** Shapes a heightfield cannot hold become follow-on phases from voxel models, waterfall lips become a flowing-water phase, and no gravity block is left over air or liquid.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/forms.py`
- Create: `tests/ashlar/terrain/test_forms.py`

**Interfaces:**

```python
@dataclass
class Form:
    name: str
    model: "voxel.VoxelModel"         # from skills/design-monument/tools/voxel
    origin: tuple[int, int, int]
    mode: str                          # "carve" | "build"

def load_form(entry: dict, project_dir: Path) -> Form        # F9 "forms" entry: VoxelModel.load_npy + Palette.from_json
def form_write(form: Form) -> LiveWrite                       # carve: occupied voxels → air; build: their block ids
def flow_build(falls: list[dict]) -> dict                     # {"blocks": [{"pos": [x, y, z], "block": "minecraft:water"}…], "liquids": "flow"}
def gravity_violations(writes: list[LiveWrite], site: Site) -> list[tuple[int, int, int, str]]
GRAVITY: frozenset[str]   # sand, red sand, gravel, suspicious sand and gravel, the 16 concrete powders
```

**Acceptance Criteria:**
- [ ] A carve form writes air exactly where its model is occupied; a build form writes its blocks.
- [ ] `gravity_violations` applies the writes in order over the site and lists every gravity block with air, water or lava directly below.
- [ ] `flow_build` marks `liquids: "flow"` and only water sources.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_forms.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** — `test_carve_form_writes_air_only_where_occupied`, `test_build_form_writes_its_blocks`, `test_gravity_check_finds_sand_over_a_carved_arch` (sand surface, an arch carved under it → one violation per sand cell over the opening), `test_flow_build_marks_flow`.
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces.
- [ ] **Step 4: Run the Verify command** — Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/forms.py tests/ashlar/terrain/test_forms.py
git commit -m "feat(terrain): carve and build-up forms, flowing sources, gravity check"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/forms.py", "tests/ashlar/terrain/test_forms.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_forms.py -q", "acceptanceCriteria": ["carve writes air where occupied; build writes blocks", "gravity blocks over air or liquid listed", "flow build marks flow"], "modelTier": "standard"}
```

---

## Task 11: The Ashlar output step and the launcher

**Goal:** `emit_ashlar` turns a recipe into phase files, plan rows, the expected-surface file and renders, and `scripts/terrain.py` runs it and the other toolkit commands from the workspace root.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/ashlar_emit.py`
- Create: `skills/terrain-shape/scripts/terrain.py`
- Create: `tests/ashlar/terrain/test_emit.py`

**Interfaces:**

```python
@dataclass
class EmitResult:
    phases: list[dict]                 # {"id", "name", "file", "blocks", "from", "to", "via", "rollback"}
    quality: dict[str, list[dict]]     # quality_contract rows by type
    notes: list[str]
    bbox: tuple[int, int, int, int, int, int]
    surface_file: Path
    report: "verify.Report"

def emit_field(hf: HeightField, spec: MaterialSpec, site: Site, project_dir: Path, *, element: str,
               first_phase: int, recipe: dict | None = None, water: np.ndarray | None = None, forms: list[Form] = (),
               protect: np.ndarray | None = None, standalone: bool = False, max_columns: int = 128) -> EmitResult
def emit_ashlar(recipe: dict, project_dir: Path, *, first_phase: int, standalone: bool = False) -> EmitResult
def plan_rows_toon(result: EmitResult) -> str
```

`emit_ashlar`: `site.ground_for` → `recipe.build_field` → spec (`emit._material_from_spec`, or `MaterialSpec.natural`) → `site.water_levels` → `verify` with `ground`, `water`, `existing_water` (raise `emit.VerifyError`, writing nothing, on failure) → `emit_field`. `emit_field` writes, under `project_dir`: `phases/<NN>-<element>-mass-<k>.json` (`{"fills": […]}`), `phases/<NN>-<element>-carve-<k>.json` / `-build-<k>.json`, `phases/<NN>-<element>-flow.json`, `terrain/<element>.recipe.json`, `terrain/<element>.surface.json`, `terrain/<element>.verify.txt`, `terrain/<element>_{hillshade,relief,profile,slope,eye}.png`, `terrain/<element>.plan-rows.toon`; with `standalone`, also `plan.toon` (`project` = folder name, `skill` = `recipe.get("skill", "terrain-shape")`, `anchor`, `bbox`, `summary` = `recipe.get("summary")`, `approved: no`). It refuses (`VerifyError`) when `gravity_violations` is non-empty.

Rows: every mass, carve and build phase `via: placer`, `rollback: backup`; the flow phase `via: mcp` when it has at most 200 entries, else `placer`, `rollback: backup`. Quality rows: `surface_match` (`file: terrain/<element>.surface.json`, `tolerance: 0`, `min_ratio: 0.98`) over the box; four `seam` rows along the box edges (`max_step: 1`); `silhouette` (`sample_count: 9`, `min_y_variance: 3`); `edge_irregularity` (`max_collinear_run: 7`); a `water_continuity` row per water level present. Notes: the recipe path, `GATE A <verify.offline_token(report)>`, `removed trees: N, farthest write M blocks outside the box`.

Launcher commands: `survey --site DIR --box X1 Y1 Z1 X2 Y2 Z2` (prints the non-natural block counts from `site.unnatural_blocks`, the number of trees, and the ground, water and top ranges; exit 1 when a non-natural block is found — `exec-ashlar`'s terrain survey uses it), `field RECIPE --project DIR` (build, verify, render; exit 1 on a failed gate), `emit RECIPE --project DIR --first-phase N [--standalone]`, `compare EXPECTED HEIGHTS [--tolerance 0] [--min-ratio 0.98]` (exit 1 below the ratio), `seam HEIGHTS --from X Z --to X Z --outward x|-x|z|-z --max-step 1`. The launcher puts `<its folder>/../tools` and `<its folder>/../../design-monument/tools` on `sys.path` and prints a one-line `uv run` hint if numpy, scipy, Pillow or opensimplex is missing.

**Acceptance Criteria:**
- [ ] A 24 × 24 hill recipe over a sitegen site emits phase files that `ashlar_place.py plan` accepts, rows with the `rollback` column, the surface file, renders and the verify report.
- [ ] A recipe that fails GATE A, or leaves a gravity block over air, writes no phase file.
- [ ] `compare` and `seam` pass and fail on hand-made heights files as specified.
- [ ] The launcher runs from any working directory.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_emit.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** — `test_emit_writes_phases_rows_and_surface_file` (runs `ashlar_place.py plan` on each phase with `sys.executable`), `test_survey_cli_flags_planks`, `test_emit_refuses_on_gate_failure`, `test_emit_refuses_gravity_blocks_over_air`, `test_standalone_writes_plan_toon`, `test_plan_rows_toon_has_rollback_column`, `test_compare_and_seam_cli`, `test_launcher_runs_from_another_directory`.
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces and the launcher (argparse subcommands; later tasks add `plant`, `tree`, `tree-place`, `apron`, `ids`).
- [ ] **Step 4: Run the Verify command** — Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/ashlar_emit.py skills/terrain-shape/scripts/terrain.py tests/ashlar/terrain/test_emit.py
git commit -m "feat(terrain): Ashlar output step and toolkit launcher"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/ashlar_emit.py", "skills/terrain-shape/scripts/terrain.py", "tests/ashlar/terrain/test_emit.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_emit.py -q", "acceptanceCriteria": ["phase files accepted by the placer's plan", "rows with rollback column, quality rows and notes", "gate or gravity failure writes nothing", "compare and seam CLI", "launcher works from any directory"], "modelTier": "standard"}
```

---

## Task 12: Feature and biome id lists (`terrain/ids.py`)

**Goal:** The toolkit loads per-version id lists, falls back to the nearest older version, and checks species and biomes against them.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/ids.py`, `skills/terrain-shape/tools/terrain/data/README.md`
- Create: `tests/ashlar/terrain/test_ids.py`

**Interfaces:**

```python
DATA: Path   # <toolkit>/data; one folder per version: data/<version>/features.json and biomes.json,
             # each {"version": str, "source": str, "ids": [sorted ids]}
def available_versions(data_dir: Path = DATA) -> list[str]     # sorted by numeric version tuple
def load_ids(version: str, data_dir: Path = DATA) -> tuple[frozenset[str], frozenset[str], str]   # (features, biomes, version used)
def check_ids(ids: Iterable[str], known: frozenset[str]) -> tuple[list[str], list[str]]           # (known, unknown)
def checked_biome_content(features: frozenset[str]) -> tuple[dict, list[str]]                     # BIOME_CONTENT without unknown features, and those dropped
```

Launcher: `ids --version V [--features A,B] [--biomes A,B]` prints the version used and any unknown ids; exit 1 when any is unknown.

**Acceptance Criteria:**
- [ ] `load_ids("26.3")` with only `1.21.4` and `26.1` present uses `26.1`; a version older than every list raises `ValueError`.
- [ ] `check_ids` splits known from unknown, keeping order.
- [ ] `data/README.md` says how lists are generated (Task 23) and that a missing version falls back to the nearest older one.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_ids.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (`test_nearest_older_version_is_used`, `test_too_old_version_raises`, `test_check_ids_splits_known_and_unknown`, `test_checked_biome_content_drops_unknown`) using a temporary data folder.
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces; version strings compare as integer tuples (`"1.21.4"` < `"26.1"` < `"26.3"`).
- [ ] **Step 4: Run the Verify command** — Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/ids.py skills/terrain-shape/tools/terrain/data/README.md tests/ashlar/terrain/test_ids.py
git commit -m "feat(terrain): per-version feature and biome id lists"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/ids.py", "skills/terrain-shape/tools/terrain/data/README.md", "tests/ashlar/terrain/test_ids.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_ids.py -q", "acceptanceCriteria": ["nearest older version fallback; too old raises", "known/unknown split", "BIOME_CONTENT filtered", "data README"], "modelTier": "mechanical"}
```

---

## Task 13: Planting plans and biome commands (`plant.py`)

**Goal:** `terrain-ecology` can plan layered vanilla planting over a field, write F3 features files, mark trunks in the expected surface, and, only when asked, write chunk-aligned biome commands.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/plant.py`
- Modify: `skills/terrain-shape/scripts/terrain.py`
- Create: `tests/ashlar/terrain/test_plant.py`

**Interfaces:**

```python
@dataclass
class Feature:
    id: str; x: int; y: int; z: int; layer: str      # layer: "canopy" | "understory" | "ground"

GROWABLE: frozenset[str]   # grass_block, dirt, coarse_dirt, podzol, rooted_dirt, moss_block, mud …
LAYER_SPACING = {"canopy": (3.0, 12.0), "understory": (2.0, 6.0), "ground": (1.0, 3.0)}   # (r_min, r_max)
def plan_features(hf: HeightField, surface_ids: np.ndarray, mix: dict[str, dict[str, float]], *,
                  origin: tuple[int, int], seed: int, known: frozenset[str],
                  water: np.ndarray | None = None) -> list[Feature]
def features_file(features: list[Feature], *, world: str | None, reach: tuple[int, int] = (8, 32)) -> dict   # F3 "features"; box = points grown by 8 sideways, 32 up, 2 down
def biome_commands(labels: np.ndarray, *, origin: tuple[int, int], y_range: tuple[int, int],
                   limit: int = 32_768) -> list[str]     # chunk-aligned; majority label per chunk; ≤ limit / 256 high per command
def mark_trunks(surface: dict, points: Iterable[tuple[int, int]], radius: int = 2) -> dict           # F6 skip mask
```

`plan_features` runs canopy, then understory, then ground cover, using `scatter.density_map` (no trees on steep ground or under water, a boost near water) and `scatter.poisson` per layer with `LAYER_SPACING`; later layers keep `r_min` away from earlier points; points land only on `GROWABLE` surfaces; `y = surface + 1`. Any id in `mix` not in `known` raises `ValueError` naming it.

Launcher: `plant (--recipe RECIPE | --site DIR --box X1 Z1 X2 Z2) --project DIR --phase N --mix MIX.json [--version V] [--biome-change]`. A recipe plants the designed field (surface ids from `resolve_surface`); `--site` plants existing land (ground and surface blocks from the site read, so it uses the site read where spec §8.4 says heights file — the exact surface blocks are needed). It writes `phases/<NN>-<element>-features.commands.json`, updates the surface file, and prints the phase row (`via: commands`, `file` = the commands file, `rollback: backup`, `from`/`to` = the file's box). Only with `--biome-change` does it also write `phases/<NN+1>-<element>-biome.commands.json` and its row (`rollback: biome`).

**Acceptance Criteria:**
- [ ] No feature on a slope over the cliff threshold, under water, or on a non-growable surface.
- [ ] Canopy features come first in the file; layer spacing holds.
- [ ] An unknown id is refused before anything is written.
- [ ] The features file's box contains every feature grown by the reach.
- [ ] Biome commands are chunk-aligned (`x1 % 16 == 0`, `x2 % 16 == 15`) and each covers at most 32,768 blocks.
- [ ] Without `--biome-change`, no biome file is written.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_plant.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** — `test_no_trees_on_cliffs_or_water`, `test_layers_keep_spacing_and_order`, `test_unknown_feature_ids_are_refused`, `test_features_file_box_includes_reach`, `test_biome_commands_are_chunk_aligned_and_within_limit`, `test_mark_trunks_skips_radius`, `test_plant_cli_writes_biome_file_only_when_asked`.
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces and the `plant` command.
- [ ] **Step 4: Run the Verify command** — Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/plant.py skills/terrain-shape/scripts/terrain.py tests/ashlar/terrain/test_plant.py
git commit -m "feat(terrain): layered planting plans, features files and biome commands"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/plant.py", "skills/terrain-shape/scripts/terrain.py", "tests/ashlar/terrain/test_plant.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_plant.py -q", "acceptanceCriteria": ["no trees on cliffs, water or non-growable ground", "canopy first, spacing per layer", "unknown ids refused", "features box includes reach", "biome commands chunk-aligned within 32,768", "biome file only with --biome-change"], "modelTier": "standard"}
```

---

## Task 14: The custom tree generator (`terrain/trees.py`)

**Goal:** The agent can design trees vanilla does not grow — from presets or its own parameters — preview them, and place them as F7 vegetation modules.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/trees.py`
- Modify: `skills/terrain-shape/scripts/terrain.py`
- Create: `tests/ashlar/terrain/test_trees.py`

**Interfaces:**

```python
CANOPIES = ("round", "ellipsoid", "conical", "columnar", "umbrella", "weeping", "layered", "sparse", "dead")

@dataclass
class TreeParams:
    wood: str = "minecraft:oak_log"; leaves: str = "minecraft:oak_leaves"
    height: int = 12; trunk_width: int = 1            # 1, 2 or 3 (a flared 3 x 3 base)
    taper: float = 0.0; lean: tuple[float, float] = (0.0, 0.0); curve: float = 0.0
    branch_levels: int = 2; branches: int = 4; branch_angle: float = 40.0; branch_length: float = 0.6
    canopy: str = "round"; canopy_radius: float = 4.0; leaf_density: float = 0.85
    roots: bool = False; seed: int = 0

PRESETS: dict[str, TreeParams]   # at least broad-oak, conifer-spire, umbrella-pine, weeping-willow, windswept-cypress, dead-snag, giant-fantasy

@dataclass
class Tree:
    wood: dict[tuple[int, int, int], str]
    leaves: dict[tuple[int, int, int], str]
    ground: dict[tuple[int, int, int], str]
    anchor: tuple[int, int, int]

def generate(params: TreeParams) -> Tree
def to_module(tree: Tree, name: str) -> dict                         # F7
def preview(tree: Tree, prefix: str) -> list[str]                   # PNGs through the voxel toolkit's render
def tree_placements(points: list[tuple[int, int]], surface: np.ndarray, origin: tuple[int, int],
                    module: dict, *, phase: int, seed: int) -> list[dict]   # F8; rotation and mirror from the seed
```

Launcher: `tree --preset P [--set key=value …] --name N --out DIR` (module + previews); `tree-place --module FILE --points FILE (--surface F6-FILE | --site DIR) --phase N --project DIR` (the surface height comes from the expected-surface file for designed terrain or from the site read for existing land; writes `terrain/<name>.placements.json`, then runs `../exec-ashlar/scripts/stamp.py --placements … --modules … --phase N --out phases/<NN>-<name>-trees.json` with `sys.executable`, and prints the phase row: `via: placer`, `rollback: backup`).

**Acceptance Criteria:**
- [ ] The same parameters and seed give the same tree; every preset generates.
- [ ] No air cells; every leaf is at most 6 steps from wood through leaves (6-connected); logs carry `axis` matching their direction (horizontal branches `x` or `z`); leaves carry `persistent=true`; the anchor is the lowest trunk cell.
- [ ] `to_module` output stamps through `stamp.py` (Task 6) into air-filtered fills.
- [ ] `tree_placements` put the rotated anchor at `(x, surface + 1, z)`.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_trees.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** — `test_same_seed_same_tree`, `test_every_preset_generates_a_valid_tree` (all rules above per preset), `test_branch_logs_follow_their_axis`, `test_module_round_trips_through_stamp`, `test_tree_placements_put_anchor_on_surface` (for each rotation).
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement.** Grow the trunk as a tapered, leaning, curving column; recurse branches by level with seeded angles and length falloff, drawing wood along each segment; shape the canopy around branch tips and the crown by `canopy` (weeping: hanging strands; layered: separated tiers; dead: no leaves); thin leaves by `leaf_density` without breaking the 6-step rule; `roots` adds `ground` cells around the base. The shapes must read as natural trees in the previews.
- [ ] **Step 4: Run the Verify command** — Expected: all pass. Render every preset with `preview` into the scratchpad and look at the PNGs; adjust until each reads as its name.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/trees.py skills/terrain-shape/scripts/terrain.py tests/ashlar/terrain/test_trees.py
git commit -m "feat(terrain): custom tree generator with presets, previews and placements"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/trees.py", "skills/terrain-shape/scripts/terrain.py", "tests/ashlar/terrain/test_trees.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_trees.py -q", "acceptanceCriteria": ["deterministic per seed; every preset valid", "no air; leaves within 6 of wood; axis and persistent states; anchor at trunk base", "module stamps into air-filtered fills", "placements put anchor on the surface", "previews read as their preset"], "modelTier": "frontier"}
```

---

## Task 15: Aprons for `terrain-integrate` (`terrain/apron.py`)

**Goal:** The toolkit designs pads and eroded aprons around protected footprints (planned and after-the-fact modes) or naturalises land with no footprint, and reports how far the ground moves.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/apron.py`
- Modify: `skills/terrain-shape/scripts/terrain.py`
- Create: `tests/ashlar/terrain/test_apron.py`

**Interfaces:**

```python
@dataclass
class ApronResult:
    field: HeightField
    protect: np.ndarray                # bool (nx, nz)
    delta: dict                        # {"max": float, "mean": float, "moved": int}
    needs_ok: bool                     # True when any column moves more than 6 blocks

def design_apron(site: Site, box2d: tuple[int, int, int, int], *, protect: list[tuple[int, int, int, int]] = (),
                 pads: dict[tuple[int, int, int, int], int] | None = None, apron: int | None = None,
                 seed: int = 0) -> ApronResult
def surrounding_palette(stats_text: str, *, top: int = 4) -> dict[str, float]   # from mc_inspect stats output
```

Start from the existing ground; set pad columns to their pad height (planned mode); erode (thermal, then light hydraulic) weighted by `1 − smoothstep(0, apron, d)` (d = columns from the protected edge); keep protected columns and the outer ring fixed. `apron` defaults to `min(24, max(8, 2 × the largest step at the protected edge))`.

Launcher: `apron --site DIR --box X1 Z1 X2 Z2 [--protect X1 Z1 X2 Z2 [--pad Y]]… --project DIR --element E --first-phase N [--palette STATS.txt] [--standalone]` → calls `ashlar_emit.emit_field` with `protect`, `MaterialSpec.natural(field, surface=palette)`, before-and-after renders and a profile across the seam in `terrain/`, and prints the delta and `needs_ok`.

**Acceptance Criteria:**
- [ ] No emitted fill touches a protected column.
- [ ] In planned mode the field meets each pad at its height at the protected edge, and the outer ring equals the existing ground.
- [ ] The delta stats are right on a known step; `needs_ok` is true above 6 blocks.
- [ ] With no protected region, the whole box is naturalised and the outer ring is unchanged.
- [ ] The emitted quality rows add a `seam` row along every protected edge (`max_step: 1`), besides the box-edge rows.

**Verify:** `uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_apron.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** — `test_protected_region_never_written`, `test_planned_pads_meet_aprons`, `test_delta_stats_and_threshold`, `test_naturalise_without_protect`, `test_surrounding_palette_parses_stats`.
- [ ] **Step 2: Run them** — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces and the `apron` command.
- [ ] **Step 4: Run the Verify command** — Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/apron.py skills/terrain-shape/scripts/terrain.py tests/ashlar/terrain/test_apron.py
git commit -m "feat(terrain): pads and eroded aprons for terrain-integrate"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/apron.py", "skills/terrain-shape/scripts/terrain.py", "tests/ashlar/terrain/test_apron.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar/terrain/test_apron.py -q", "acceptanceCriteria": ["protected columns never written", "pads meet aprons; ring unchanged", "delta stats and 6-block threshold", "naturalise without protect", "palette parsed from stats"], "modelTier": "standard"}
```

---

## Task 16: `exec-ashlar` skill text

**Goal:** `exec-ashlar`'s `SKILL.md` and references describe backups, the runner, biome changes, resume, the new plan columns and rows, and terrain verification, as spec §9 says.

**Files:**
- Modify: `skills/exec-ashlar/SKILL.md`, `skills/exec-ashlar/reference/{plan-format,execution,commands,verification,registry,survey,tools-and-limits,modules,clients}.md`

**Acceptance Criteria:**
- [ ] `SKILL.md`: the Scripts section lists the new subcommands; `build` covers backup phases, commands files, the biome probe and resume; `rollback` covers backups and biome probes newest first and the `<host>-ground` offer; hard rules add "no write without a complete rollback point" and the `fillbiome` conditions.
- [ ] `plan-format.md`: the optional `rollback` column (`snapshot`, `backup`, `biome`; absent = today's behaviour), commands files in a `commands` phase's `file`, the rows `surface_match`, `seam`, `water_continuity` (spec §9.3 table), the notes, and the validation additions.
- [ ] `execution.md`: the gate items of spec §9.4 (backup sizes, commands-file counts, the biome change and its approximate rollback, non-natural blocks, removed trees and farthest write, duration, players); the features-phase backup box (8 sideways, 32 up); the resume rule word for word in substance with spec §9.4 (original rollback point kept, `--no-snapshot` re-place, evicted-snapshot note, progress skip); rollback order.
- [ ] `commands.md`: the `fillbiome` form with its five conditions (spec §9.5), the runner, and `execute if biome` for the probe.
- [ ] `verification.md`: how to check the three new rows with `heights`, `terrain.py compare` and `seam`, and `mc_inspect` columns; how to look at terrain (top, heightmap, vertical slices, edge strips, offline renders, the user's in-game look); the runner report as planting evidence.
- [ ] `registry.md`: phase `rollback`, `backup`, `biome_probe`; project `grounds` and `terrain`.
- [ ] `survey.md`: the terrain section (heights file over the box plus 16 blocks, site read over the box plus 8 blocks, water levels, non-natural blocks and trees from `../terrain-shape/scripts/terrain.py survey`; stop on a structure).
- [ ] `tools-and-limits.md`: column reads for backups, the `fillbiome` limit, the flowing cap as the placer enforces it, the heights source.
- [ ] `modules.md`: vegetation modules (F7) and the stamping order.
- [ ] `clients.md`: no new client tools needed; unchanged unless a labelled line is added.
- [ ] Static checks for `exec_ashlar` pass; the validator passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar && node scripts/validate-plugin.mjs` → pass, then `✓ plugin, marketplace, skills, and agents are valid`

**Steps:**

- [ ] **Step 1: Edit each file** to say what the criteria list, in the existing style (short rules, tables where the file already uses them). Spec §9.1–§9.8 holds the content; Tasks 3–6 fix the command names and exit codes (6 = some commands failed).
- [ ] **Step 2: Run the Verify command** — Expected: pass.
- [ ] **Step 3: Commit**

```bash
git add skills/exec-ashlar
git commit -m "docs(exec-ashlar): backups, the commands runner, biome changes, resume and terrain checks"
```

```json:metadata
{"files": ["skills/exec-ashlar/SKILL.md", "skills/exec-ashlar/reference/plan-format.md", "skills/exec-ashlar/reference/execution.md", "skills/exec-ashlar/reference/commands.md", "skills/exec-ashlar/reference/verification.md", "skills/exec-ashlar/reference/registry.md", "skills/exec-ashlar/reference/survey.md", "skills/exec-ashlar/reference/tools-and-limits.md", "skills/exec-ashlar/reference/modules.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["every spec §9 item present in its file", "resume rule matches spec §9.4", "fillbiome form with its conditions", "static checks and validator pass"], "modelTier": "standard"}
```

---

## Task 17: `terrain-shape` text and shared references

**Goal:** `terrain-shape` follows spec §8.1–§8.2 and §8.6, and the shared method and API references live in its `reference/terrain/`.

**Files:**
- Modify: `skills/terrain-shape/SKILL.md`, `skills/terrain-shape/reference/landforms.md`, `skills/terrain-shape/reference/command-budget.md`, the stubs `skills/terrain-shape/reference/{palettes,water,weathering,non-negotiable-enforcement}.md`
- Create: `skills/terrain-shape/reference/terrain/{method,toolkit-api,non-negotiables,palettes,primitives,water,weathering,validation,research}.md` (copies of the root `reference/terrain/` files, adapted)

**Acceptance Criteria:**
- [ ] Frontmatter: `name: terrain-shape`; a concrete description ending "Builds through Ashlar with the exec-ashlar skill."; `model: sonnet`, `effort: high`; no `context: fork`; `metadata.short-description`.
- [ ] The body has: connection; the project rule (called for a design skill's build, add phases to that build's plan; a standalone request is its own project); the terrain survey (site read, heights file, `terrain.py survey` for non-natural blocks); a short standalone interview with labelled `AskUserQuestion` / `request_user_input` / plain-text lines; the design-skill input (datum, footprint as a pad, palette); recipe authoring with the F9 keys; GATE A; renders with labelled viewing lines; the user's design approval; the hand-off to `terrain-ecology`, then emit and `exec-ashlar build`; phase order in a combined plan; re-sculpting; verify at eye level; Chapman's six non-negotiables.
- [ ] `reference/terrain/method.md` gives the Ashlar pipeline (site read → recipe → blend → erosion → GATE A → renders → approval → planting → emit → `exec-ashlar`); `toolkit-api.md` documents `site`, `live`, `forms`, `ashlar_emit`, `ids`, `plant`, `trees`, `apron` and every launcher command; the other copies change only per the spec §8.6 table.
- [ ] `command-budget.md` becomes a short Ashlar budget note pointing at `../exec-ashlar/reference/tools-and-limits.md`; the stubs point at `reference/terrain/<file>`.
- [ ] Static checks for `terrain_shape` pass (leftovers, labels, frontmatter, links); the validator passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_shape && node scripts/validate-plugin.mjs` → pass

**Steps:**

- [ ] **Step 1: Copy the shared references** — `cp reference/terrain/{method,toolkit-api,non-negotiables,palettes,primitives,water,weathering,validation,research}.md skills/terrain-shape/reference/terrain/`.
- [ ] **Step 2: Run the Verify command** — Expected: FAIL (Chapman names in the copies and the skill).
- [ ] **Step 3: Rewrite `SKILL.md` and adapt the references** per the criteria and spec §8.6; keep design knowledge as written.
- [ ] **Step 4: Run the Verify command** — Expected: pass.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape
git commit -m "feat(terrain-shape): build through Ashlar; shared terrain references"
```

```json:metadata
{"files": ["skills/terrain-shape/SKILL.md", "skills/terrain-shape/reference/"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_shape && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["frontmatter rules", "flow per spec 8.1-8.2 with labelled client lines", "method and toolkit-api describe the Ashlar pipeline and new API", "copies changed only per 8.6", "static checks and validator pass"], "modelTier": "standard"}
```

---

## Task 18: `terrain-landmark` skill text

**Goal:** `terrain-landmark` follows spec §8.3 on top of `terrain-shape`'s flow.

**Files:**
- Modify: `skills/terrain-landmark/SKILL.md`, `skills/terrain-landmark/reference/{wonders,anti-patterns,sequencing,primitives,palettes}.md`

**Acceptance Criteria:**
- [ ] Frontmatter as in Task 17 (`model: sonnet`, `effort: high`).
- [ ] The composition proposal comes before any recipe work and the user confirms it; research through `survey-research`, citations in the registry; signatures as measurable checks plus `acceptance` cells, `silhouette` and `block_mix_ratios`, with unmeasurable ones named "checked by eye" at the design approval; carve and build-up forms via the recipe's `forms` key in `sequencing.md` order.
- [ ] `sequencing.md` replaces the plunge-pool rule with spec §7.7's (a few blocks, at most about 12, and why) and its structure-capture weathering step with module variants.
- [ ] `anti-patterns.md` points at `exec-ashlar` verification instead of Chapman's reflect step; the stubs point at `../terrain-shape/reference/terrain/<file>`.
- [ ] Static checks for `terrain_landmark` pass; the validator passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_landmark && node scripts/validate-plugin.mjs` → pass

**Steps:**

- [ ] **Step 1: Run the Verify command** — Expected: FAIL.
- [ ] **Step 2: Rewrite and edit** per the criteria.
- [ ] **Step 3: Run the Verify command** — Expected: pass.
- [ ] **Step 4: Commit**

```bash
git add skills/terrain-landmark
git commit -m "feat(terrain-landmark): build through Ashlar"
```

```json:metadata
{"files": ["skills/terrain-landmark/SKILL.md", "skills/terrain-landmark/reference/"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_landmark && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["composition first, research, signature checks", "plunge-pool rule replaced with reason", "stubs and references point inside the fork", "static checks and validator pass"], "modelTier": "standard"}
```

---

## Task 19: `terrain-ecology` skill text

**Goal:** `terrain-ecology` follows spec §8.4: layered planting, custom trees and the biome rule.

**Files:**
- Modify: `skills/terrain-ecology/SKILL.md`
- Create: `skills/terrain-ecology/reference/ecology.md` (from the root `reference/terrain/ecology.md`, adapted), `skills/terrain-ecology/reference/custom-trees.md`

**Acceptance Criteria:**
- [ ] Frontmatter as in Task 17 with `model: sonnet`, `effort: medium`; the body links `../terrain-shape/reference/terrain/method.md` (the validator needs `reference/terrain/` in the body).
- [ ] Inputs, outputs and phase order as spec §8.4; the id check against the server's version (`terrain.py ids`), saying when a fallback version is used.
- [ ] Chapman's "grow, never place" becomes: vanilla trees are grown with `place feature`; custom trees are designed deliberately with the generator and shown as previews before use.
- [ ] The biome rule's five steps, in order, as spec §8.4 words them; the dedicated question uses labelled client lines; the answer is recorded in `requirements.md`; `terrain.py plant --biome-change` only after a yes.
- [ ] `custom-trees.md` covers every `TreeParams` field, the presets, previews, mixing custom trees into a scatter and placing a hero tree.
- [ ] `ecology.md` keeps Chapman's planting principles, plants existing land from the site read (`terrain.py plant --site`), and turns his rocks-and-deadfall trick (structure integrity) into seeded vegetation-module variants authored with the voxel toolkit.
- [ ] Static checks for `terrain_ecology` pass; the validator passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_ecology && node scripts/validate-plugin.mjs` → pass

**Steps:**

- [ ] **Step 1: Run the Verify command** — Expected: FAIL.
- [ ] **Step 2: Write** the skill and the two references per the criteria.
- [ ] **Step 3: Run the Verify command** — Expected: pass.
- [ ] **Step 4: Commit**

```bash
git add skills/terrain-ecology
git commit -m "feat(terrain-ecology): planting, custom trees and the biome rule through Ashlar"
```

```json:metadata
{"files": ["skills/terrain-ecology/SKILL.md", "skills/terrain-ecology/reference/ecology.md", "skills/terrain-ecology/reference/custom-trees.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_ecology && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["inputs, outputs, phase order", "id check with fallback note", "grow-vs-design rule updated", "biome rule five steps with dedicated question and record", "custom-trees reference complete", "static checks and validator pass"], "modelTier": "standard"}
```

---

## Task 20: `terrain-integrate` skill text

**Goal:** `terrain-integrate` follows spec §8.5: planned mode, after-the-fact projects, naturalising, and the dry run before approval.

**Files:**
- Modify: `skills/terrain-integrate/SKILL.md`
- Create: `skills/terrain-integrate/reference/integration.md` (from the root `reference/terrain/integration.md`, adapted)

**Acceptance Criteria:**
- [ ] Frontmatter as in Task 17 with `model: sonnet`, `effort: medium`; the body links `../terrain-shape/reference/terrain/method.md`.
- [ ] Planned mode (inputs from the design skill, site-prep phases first in the host plan), after-the-fact `<host>-ground` projects with `grounds: "<host>"`, naturalising with no protected region; `terrain.py apron` usage; the surrounding palette from `mc_inspect` stats of a ring.
- [ ] Before the design approval: before-and-after renders, a profile across the seam and the delta stats; more than 6 blocks needs the user's explicit OK.
- [ ] The sloped-back bench note stays; Chapman's server erosion tools are gone; "GATE B" becomes "offered, not mandatory".
- [ ] Static checks for `terrain_integrate` pass; the validator passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_integrate && node scripts/validate-plugin.mjs` → pass

**Steps:**

- [ ] **Step 1: Run the Verify command** — Expected: FAIL.
- [ ] **Step 2: Write** the skill and `integration.md` per the criteria.
- [ ] **Step 3: Run the Verify command** — Expected: pass.
- [ ] **Step 4: Commit**

```bash
git add skills/terrain-integrate
git commit -m "feat(terrain-integrate): aprons and naturalising through Ashlar"
```

```json:metadata
{"files": ["skills/terrain-integrate/SKILL.md", "skills/terrain-integrate/reference/integration.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k terrain_integrate && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["planned, after-the-fact and naturalise modes", "dry run and 6-block OK", "bench note kept; no server erosion", "static checks and validator pass"], "modelTier": "standard"}
```

---

## Task 21: Design-skill edits

**Goal:** The six design skills offer `terrain-integrate` for site prep when a pad sits off the ground, and send naturalistic planting and custom trees to `terrain-ecology` (spec §10).

**Files:**
- Modify: `skills/design-building/SKILL.md`, `skills/design-city/SKILL.md`, `skills/design-grounds/SKILL.md`, `skills/design-house/SKILL.md`, `skills/design-monument/SKILL.md`, `skills/design-village/SKILL.md`, `skills/design-house/reference/interiors.md`, `skills/design-grounds/reference/elements.md`, `skills/design-city/reference/infrastructure.md`, `skills/design-village/reference/styles.md`

**Acceptance Criteria:**
- [ ] In each design skill's Hand-off site-preparation step (the step that starts "**Site preparation**", "**Grading**" or "**Siblings first**"), this sentence follows the existing `site-prep` text: "If a pad would sit more than about 1–2 blocks above or below the surveyed ground at any edge, offer the `terrain-integrate` skill for the site preparation instead: it designs the pad and a natural apron around it as the first phases of this plan."
- [ ] Each planting passage — `design-village/SKILL.md` ("Grow any trees in or around the village …"), `design-house/reference/interiors.md` ("**Grounds and gardens**"), `design-grounds/reference/elements.md` (the naturalistic clump), `design-city/reference/infrastructure.md` ("Street trees …"), `design-village/reference/styles.md` ("Grow trees and bushes …") — gains: "For naturalistic planting, or for trees vanilla does not grow, use the `terrain-ecology` skill." `design-village/SKILL.md` and `styles.md` point there instead of `terrain-shape` for trees.
- [ ] Nothing else changes in these files (`git diff` shows only these sentences).
- [ ] Static checks for the six design skills pass.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_ && grep -l "terrain-integrate" skills/design-*/SKILL.md | wc -l` → pass, then `6`

**Steps:**

- [ ] **Step 1: Make the edits** listed above.
- [ ] **Step 2: Run the Verify command** — Expected: pass and `6`.
- [ ] **Step 3: Commit**

```bash
git add skills/design-*
git commit -m "docs(design-*): offer terrain-integrate for site prep; point planting at terrain-ecology"
```

```json:metadata
{"files": ["skills/design-building/SKILL.md", "skills/design-city/SKILL.md", "skills/design-grounds/SKILL.md", "skills/design-house/SKILL.md", "skills/design-monument/SKILL.md", "skills/design-village/SKILL.md", "skills/design-house/reference/interiors.md", "skills/design-grounds/reference/elements.md", "skills/design-city/reference/infrastructure.md", "skills/design-village/reference/styles.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_ && grep -l terrain-integrate skills/design-*/SKILL.md | wc -l", "acceptanceCriteria": ["integrate sentence in six hand-offs", "ecology sentence in five planting passages", "diff limited to these sentences", "static checks pass"], "modelTier": "mechanical"}
```

---

## Task 22: Fork notes and the full offline check

**Goal:** `README.md`, `CLAUDE.md` and `skills/TAXONOMY.md` describe the twelve adapted skills, and every offline check passes.

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `skills/TAXONOMY.md`

**Acceptance Criteria:**
- [ ] `README.md`'s fork note names the four terrain skills, adds them to the link loop, and mentions the toolkit's `uv` command.
- [ ] `CLAUDE.md`'s fork note lists twelve skills, the toolkit location, and the full test command with scipy and opensimplex.
- [ ] `TAXONOMY.md` gets one line saying the four terrain skills are Ashlar-adapted in this fork and `terrain-cave` is not.
- [ ] The full suite and the validator pass.

**Verify:** `uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar -q && node scripts/validate-plugin.mjs` → all pass, then `✓ plugin, marketplace, skills, and agents are valid`

**Steps:**

- [ ] **Step 1: Edit the three files.**
- [ ] **Step 2: Run the Verify command** — Expected: pass.
- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md skills/TAXONOMY.md
git commit -m "docs: fork notes for the Ashlar terrain skills"
```

```json:metadata
{"files": ["README.md", "CLAUDE.md", "skills/TAXONOMY.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with scipy --with pillow --with opensimplex pytest tests/ashlar -q && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["README note and link loop list twelve skills", "CLAUDE.md note and test command", "TAXONOMY line", "full suite and validator pass"], "modelTier": "mechanical"}
```

---

## Task 23: Id lists for the server's Minecraft version

**Goal:** `data/<version>/features.json` and `biomes.json` exist for the server's current Minecraft version, generated from vanilla game data with the user's OK, and the toolkit's species lists use only valid ids.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `skills/terrain-shape/tools/terrain/data/<version>/features.json`, `skills/terrain-shape/tools/terrain/data/<version>/biomes.json`
- Modify: `skills/terrain-shape/tools/terrain/climate.py` (`BIOME_CONTENT` ids)

**Acceptance Criteria:**
- [ ] The Minecraft version comes from `mc_status` (read-only).
- [ ] The user chose the source and approved the download before anything was fetched: the `<version>-summary` data of `misode/mcmeta` on GitHub (its registry summary lists every registry's ids), or Mojang's vanilla server jar for that version run through its data generator (`java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --server --reports`).
- [ ] Both files follow the Task 12 format, with `source` naming where they came from; `minecraft:oak` and `minecraft:plains` are in them.
- [ ] Every feature in `BIOME_CONTENT` exists in the list; ids that did not (for example `minecraft:birch_tall`, if absent) are replaced with the closest valid id and listed in the commit message.
- [ ] Nothing server-specific is committed.

**Verify:** `uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python -c "import sys; sys.path.insert(0, 'skills/terrain-shape/tools'); from terrain import ids, climate; f, b, v = ids.load_ids('<version>'); bad = sorted({x for c in climate.BIOME_CONTENT.values() for x in c['features']} - f); print(v, bad or 'all known')"` → `<version> all known`

**Steps:**

- [ ] **Step 1:** Read the version with `mc_status`.
- [ ] **Step 2:** Ask the user which source to use, naming the file, its origin and its approximate size; download nothing without a yes.
- [ ] **Step 3:** Extract the two id lists into the Task 12 format.
- [ ] **Step 4:** Fix `BIOME_CONTENT`; run the Verify command and the toolkit tests.
- [ ] **Step 5: Commit**

```bash
git add skills/terrain-shape/tools/terrain/data skills/terrain-shape/tools/terrain/climate.py
git commit -m "feat(terrain): feature and biome ids for Minecraft <version>"
```

```json:metadata
{"files": ["skills/terrain-shape/tools/terrain/data/", "skills/terrain-shape/tools/terrain/climate.py"], "verifyCommand": "uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python -c <load_ids and BIOME_CONTENT check from the Verify line>", "acceptanceCriteria": ["version read from mc_status", "user approved source and download first", "lists in Task 12 format with source", "BIOME_CONTENT ids all valid", "nothing server-specific committed"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```

---

## Task 24: Live read-only checks and the scratch area

**Goal:** The new read paths work against the live server, and a scratch area for Task 26 is chosen and recorded outside the fork.

**Files:**
- Create (workspace, not the fork): `/Users/bsw/Development/Minecraft/.minecraft-builder/terrain-selftest/survey.md`, `heights.json`, `site/`
- Modify (only if a parser disagrees with live output): `skills/exec-ashlar/scripts/ashlar_place.py` and its tests, with sanitised fixtures

**Acceptance Criteria:**
- [ ] `ashlar_place.py check` prints the plugin version and no URL, IP or token.
- [ ] `heights` over a small area that includes negative coordinates matches a direct `mc_survey` read of the same area column for column.
- [ ] `backup` of a small box completes, and its columns match a direct `mc_inspect` columns read.
- [ ] `minecraft:forceload query` (read-only) parses with `parse_forceload_query`.
- [ ] A scratch area of at least 64 × 64 is chosen with the `exec-ashlar` survey: natural ground, no players near, no registry overlap, no non-natural blocks, some trees at one edge; its survey, heights file and site read are written under `.minecraft-builder/terrain-selftest/`.
- [ ] No world-changing tool was called.

**Verify:** `cd /Users/bsw/Development/Minecraft && test -f .minecraft-builder/terrain-selftest/site/manifest.json && python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py check 2>&1 | grep -cE 'wss?://|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+'` → `0`

**Steps:**

- [ ] **Step 1:** Run `check`, `heights`, `backup` and the forceload query; compare with direct reads.
- [ ] **Step 2:** If a parser disagrees, fix it with a regression test built from the captured text with coordinates replaced, and commit (`fix(exec-ashlar): …`).
- [ ] **Step 3:** Survey and record the scratch area.

```json:metadata
{"files": [], "verifyCommand": "cd /Users/bsw/Development/Minecraft && test -f .minecraft-builder/terrain-selftest/site/manifest.json && python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py check 2>&1 | grep -cE 'wss?://|[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+:[0-9]+'", "acceptanceCriteria": ["check without secrets", "heights and backup match direct reads", "forceload query parsed", "scratch area recorded outside the fork", "no world-changing call"], "modelTier": "standard"}
```

---

## Task 25: Terrain dry runs

**Goal:** Each of the four terrain skills runs from a small prompt up to the `exec-ashlar` approval gate in a read-only subagent, and its output is valid.

**Files:**
- Create (workspace): `/Users/bsw/Development/Minecraft/.claude/agents/ashlar-terrain-dry-run.md`
- Modify (only to fix problems found): files under `skills/terrain-*/`, `skills/exec-ashlar/`

**Acceptance Criteria:**
- [ ] The agent has `Read, Write, Edit, Glob, Grep, Bash` and the five read-only Ashlar tools; it follows the skills from the worktree (`/Users/bsw/Development/Minecraft/ashlar-design-skills-terrain/skills/<skill>/SKILL.md`, with `<terrain-shape>` and `<skill>` resolved there), answers interview questions itself and records them, treats designs as approved, and stops at `exec-ashlar build`'s gate. Its Bash use is limited to the toolkit launcher and the placer's `plan`, `heights`, `backup` and `commands --check`; never `place`, `restore`, `biome-probe` or `commands` without `--check`.
- [ ] Four dry runs in the scratch area: `terrain-shape` (a hill with a lake), `terrain-landmark` (a small mesa with hoodoos), `terrain-ecology` (plant part of the existing land, with one custom tree), `terrain-integrate` (naturalise a small patch).
- [ ] Every phase file passes `ashlar_place.py plan`; every commands file passes `commands --check`; plan rows and quality rows are present; no Chapman component is referenced; the biome question is not asked for these prompts; no world-changing tool is called.
- [ ] Problems found are fixed and committed, with all offline checks still passing.

**Verify:** `cd /Users/bsw/Development/Minecraft && bash -c 'shopt -s nullglob; for f in .minecraft-builder/dryrun-terrain-*/phases/*.json; do case "$f" in *.commands.json) python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py commands "$f" --check >/dev/null || echo "FAIL $f";; *) python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py plan "$f" >/dev/null || echo FAIL $f;; esac; done; echo checked'` → `checked` with no `FAIL` lines

**Steps:**

- [ ] **Step 1:** Write the agent file.
- [ ] **Step 2:** Run the four dry runs (projects `dryrun-terrain-shape`, `-landmark`, `-ecology`, `-integrate`).
- [ ] **Step 3:** Check the outputs; fix the skills where needed; commit (`fix(terrain-*): …`).

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.claude/agents/ashlar-terrain-dry-run.md"], "verifyCommand": "cd /Users/bsw/Development/Minecraft && bash -c 'shopt -s nullglob; for f in .minecraft-builder/dryrun-terrain-*/phases/*.json; do case \"$f\" in *.commands.json) python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py commands \"$f\" --check >/dev/null || echo \"FAIL $f\";; *) python3 ashlar-design-skills-terrain/skills/exec-ashlar/scripts/ashlar_place.py plan \"$f\" >/dev/null || echo FAIL $f;; esac; done; echo checked'", "acceptanceCriteria": ["agent with restricted shell", "four dry runs reach the gate", "phase and commands files valid; rows present; no Chapman references; no biome question; no writes", "fixes committed with checks passing"], "modelTier": "standard"}
```

---

## Task 26: Live write test in the scratch area

**Goal:** A small terrain build with planting is placed, verified and rolled back through the new path, and the area ends exactly as it started.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create (workspace): `/Users/bsw/Development/Minecraft/.minecraft-builder/terrain-selftest/` (plan, phases, backups, build log, evidence)

**Acceptance Criteria:**
- [ ] The user approved at the `exec-ashlar` gate before any write; players were checked before every phase.
- [ ] Built with the worktree's skills: a hill with a small pond of about 48 × 48 (backups), three to five vanilla trees through the runner, and two custom trees; if the user agrees to a separate biome question, one chunk column's biome is changed after a probe.
- [ ] Every `quality_contract` row passes with its evidence recorded; `mc_render` views were looked at.
- [ ] Rollback restores newest first (biome, then backups); a fresh `backup` of the build box matches the pre-build site read column for column; a fresh probe matches the first; no force-load remains (`forceload query`).
- [ ] Anything that failed is fixed in the fork and committed, with offline checks passing.

**Verify:** `cd /Users/bsw/Development/Minecraft/.minecraft-builder/terrain-selftest && python3 -c "import gzip, json; a = json.load(gzip.open('site/columns.json.gz'))['columns']; b = json.load(gzip.open('after/columns.json.gz'))['columns']; print('restored' if all(b[k] == a[k] for k in b) else 'DIFF')"` → `restored`

**Steps:**

- [ ] **Step 1:** Ask the user to start the test; design the hill (`terrain-shape`) and the planting (`terrain-ecology`) in project `terrain-selftest`.
- [ ] **Step 2:** Run `exec-ashlar build terrain-selftest` from the worktree; wait for the gate's yes.
- [ ] **Step 3:** Verify every row; look at the renders.
- [ ] **Step 4:** Roll back after the user's yes; read the box again into `after/` and run the Verify command; check `forceload query`.
- [ ] **Step 5:** Fix and commit anything that failed.

```json:metadata
{"files": [], "verifyCommand": "cd /Users/bsw/Development/Minecraft/.minecraft-builder/terrain-selftest && python3 -c \"import gzip, json; a = json.load(gzip.open('site/columns.json.gz'))['columns']; b = json.load(gzip.open('after/columns.json.gz'))['columns']; print('restored' if all(b[k] == a[k] for k in b) else 'DIFF')\"", "acceptanceCriteria": ["user approved before any write", "hill, pond, vanilla and custom trees built with backups", "every quality row passed with evidence", "rollback restores the area exactly; probe matches; no force-load left", "failures fixed and committed"], "modelTier": "frontier", "userGate": true, "tags": ["user-gate"]}
```

---

## Task 27: Push, pull request and links

**Goal:** With the user's OK, `terrain` is pushed and a PR into the fork's `main` is open; after the user merges, the four skills are linked for both clients.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Workspace links (after the merge): `/Users/bsw/Development/Minecraft/.claude/skills/terrain-{shape,landmark,ecology,integrate}`, `/Users/bsw/Development/Minecraft/.agents/skills/terrain-{shape,landmark,ecology,integrate}`

**Acceptance Criteria:**
- [ ] If `origin/main` moved (for example sub-project 3 merged), the user agreed to merge it into `terrain`; conflicts are resolved with one shared column reader, one resume rule and the combined skill count; all offline checks pass afterwards.
- [ ] With the user's yes, `terrain` is pushed to `origin` and a PR into `main` exists (never to upstream).
- [ ] After the user merges and says so: each link is `../../ashlar-design-skills/skills/<name>` and resolves; the clone has `main` checked out only if the user agreed; the user confirms both clients list the twelve skills.

**Verify:** `gh pr list --repo iridium-coding/ashlar-design-skills --head terrain --json url,baseRefName --jq '.[] | .baseRefName + " " + .url'` → `main https://github.com/iridium-coding/ashlar-design-skills/pull/<n>`

**Steps:**

- [ ] **Step 1:** Check `origin/main`; ask before merging it in; resolve and re-run the offline checks.
- [ ] **Step 2:** Ask before pushing; push; open the PR with the attribution line.
- [ ] **Step 3:** After the user merges: ask before linking and before changing the clone's branch; link; confirm.

```json:metadata
{"files": [], "verifyCommand": "gh pr list --repo iridium-coding/ashlar-design-skills --head terrain --json url,baseRefName --jq '.[] | .baseRefName + \" \" + .url'", "acceptanceCriteria": ["main merged in only with the user's OK; conflicts resolved; checks pass", "pushed and PR into main with the user's OK", "links resolve after merge; user confirms both clients"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```
