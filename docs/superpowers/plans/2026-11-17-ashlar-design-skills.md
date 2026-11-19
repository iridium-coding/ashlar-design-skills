# Ashlar Design Skills (Sub-project 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Chapman's six Minecraft design skills build through the Ashlar MCP server in Claude Code and Codex, by adding a shared `exec-ashlar` executor skill (with a stdio placer and a module stamper), vendoring the voxel toolkit, and editing the design skills and `survey-research` so they no longer depend on Chapman's Fabric pipeline.

**Architecture:** The design skills keep their design knowledge and their interview → blueprint → approval loop, then hand a `plan.toon` plus JSON phase and module files to `exec-ashlar`. That skill owns the survey procedure, plan validation, the approval gate, snapshots, phased placement and verification. Large or generated geometry goes through `scripts/ashlar_place.py`, which starts `ashlar-mcp` the way the client config does and sends paged `mc_build` calls. Repeated elements are module files that `scripts/stamp.py` rotates and mirrors into phase files. Skill text is shared by both clients; client-specific tools appear only on labelled `Claude Code:` / `Codex:` lines with an `Otherwise:` fallback.

**Tech Stack:** Markdown Agent Skills (Claude Code and Codex), Python 3.11+ standard library (`argparse`, `json`, `subprocess`, `threading`, `tomllib`), pytest through `uv run`, numpy and Pillow for the vendored voxel toolkit, Ashlar 0.4.9 MCP tools on Paper 26.3, Node 20+ for upstream's `scripts/validate-plugin.mjs`.

**Spec:** `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md` (committed as `2602a2d`). Executors read the spec and this plan together; where this plan says "spec §N", the content to use is in that section.

## Global Constraints

- **Repository:** `/Users/bsw/Development/Minecraft/ashlar-design-skills`, branch `ashlar`. Run every command from the repository root unless a step says otherwise. The workspace root is `/Users/bsw/Development/Minecraft`.
- **Commits:** every task ends with a commit on `ashlar`. Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push, open a PR or merge unless the task's user gate says the user approved it at that moment.
- **Test commands:**
  - skill text and scripts: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar -q`
  - with the voxel smoke test: add `--with numpy --with pillow`
  - upstream validator: `node scripts/validate-plugin.mjs` → `✓ plugin, marketplace, skills, and agents are valid`
- **Python:** scripts use only the standard library and must run on Python 3.11 or newer (they use `tomllib`). Tests run through `uv`, which picks Python 3.14 on this machine.
- **Ashlar limits** (defaults; this server matches): 500,000 blocks per `mc_build` call; 1,024-chunk footprint per write call; 200,000 cells per read and per snapshot; 20 snapshots kept, oldest evicted; 2,000 flowing liquids per call; 16 queued operations; overworld y −64 to 319.
- **Console allowlist** (spec §5.5), the only `mc_command` forms any skill may use:
  - changes the world: `summon <entity> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}`, `data merge block <x> <y> <z> {…}`, `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}`, `item replace block <x> <y> <z> <slot> with <item> [count]`, `place feature <feature> <x> <y> <z>`, `kill @e[tag=ashlar.<project>…]`
  - read only: `execute if biome <x> <y> <z> <biome>`, `data get block <x> <y> <z> [path]`, `data get entity @e[tag=ashlar.<project>,…,limit=1] [path]`, `execute if entity @e[tag=ashlar.<project>,…]`
  - never `fill`, `setblock`, `clone` or anything else, and never to get around a limit.
- **Project names** are kebab-case `[a-z0-9][a-z0-9-]*`; entity tags are `ashlar` and `ashlar.<project>` (an extra per-entity tag `ashlar.<project>.<name>` is allowed for entities that are read back).
- **Skill text rules** (spec §7, §7.5):
  - Change only text that points at Chapman's pipeline or tools. Styles, rooms, layouts, catalogs and techniques stay as written.
  - Client-specific tool names (`AskUserQuestion`, `request_user_input`, `view_image`, `update_plan`, `TodoWrite`, `WebSearch`, `WebFetch`, `${CLAUDE_SKILL_DIR}`, `mcp__…`) appear only on lines labelled exactly `Claude Code:` or `Codex:` (plus their indented continuation lines), in `skills/exec-ashlar/reference/clients.md`, or in Claude-only frontmatter. Each labelled pair is followed by an `Otherwise:` line.
  - Cross-skill paths are sibling paths (`../exec-ashlar/reference/…`) only. Never write repo-root paths such as `../../reference/…`: they break through the workspace symlinks.
  - Keep each skill's `model` and `effort` frontmatter. Do not use the word "orchestrator" in the eight skills.
  - Server-specific facts (IP, host, player names, this server's world list) never go into the fork.
- **Secrets:** never print, log or commit a value from an MCP server entry's `env` (the Ashlar URL and token). Never read `~/.claude.json` or `~/.codex/config.toml` with commands that echo values.
- **Live world:** only Tasks 15–18 touch the live server. Task 15 is read-only. Tasks 16 and 18 write only after the user approves at that moment, only inside the scratch box recorded in Task 15, and restore it afterwards.
- **Other upstream files:** do not edit Chapman's other skills, agents or tools. The only upstream files this plan changes are the six `design-*` skill folders, `skills/survey-research/SKILL.md`, `skills/TAXONOMY.md`, `README.md` and `CLAUDE.md`.

**User decisions (already made):**
- `mc_command`: "Approved allowlist (Recommended)", with the read-only checks added ("Yes, add read-only checks").
- Generated geometry: "Local placer script (Recommended)".
- Source of truth: "GitHub fork", then "Public fork (Recommended)", named `ashlar-design-skills` (`iridium-coding/ashlar-design-skills`, created 2026-11-17).
- Structure: "Shared exec-ashlar (Recommended)".
- Scope: "Split it (Recommended)": this plan is sub-project 1; terrain (`terrain-shape`, `terrain-landmark`, terrain toolkit) and `system-redstone` are separate sub-projects.
- "I am totally okay with terrain work and complex redstone builds if the agent thinks that is called for."
- Install: global copies removed; the skills are linked into the workspace for Claude Code (`.claude/skills`) and Codex (`.agents/skills`); the workspace is `~/Development/Minecraft`, with the server's own files in a sibling folder.
- "If any Claude-specific or Codex-specific tools would improve performance or efficiency, they can be used, but just ensure they are clearly distinguished within the skill."
- Spec: "Approve and commit" (`2602a2d`).

## Review Focus

These are the inputs the spec implies but that are easy to miss. Each has a pinned test in the task that owns the code.

1. **`ashlar-mcp` crashes or fails and its stderr carries the plugin URL or token** (it logs `connecting to <url>`). Expected: the placer's output shows `***`, never the URL or token. Test: `test_server_crash_redacts_url_and_token` (Task 3).
2. **A phase file mixes a clearing fill, building fills and single blocks, and paging splits it.** Expected: the original order is kept, and every fill page is sent before any block page, as `mc_build` itself does. Test: `test_pages_preserve_order_and_put_fills_first` (Task 2).
3. **An `outline`, `hollow` or `walls` fill is bigger than one call allows.** Expected: refusal with exit 3, because splitting a shell fill changes its shape. Test: `test_shell_fill_over_limit_is_refused` (Task 2).
4. **Negative coordinates.** Expected: chunk counts across 0 are right, and `stamp.py --at=-10,64,-5` works. Tests: `test_chunks_across_zero` (Task 2), `test_cli_negative_origin` (Task 4).
5. **The player list has a `looking at` suffix, players in other worlds, or output it cannot read.** Expected: positions parse; players in other worlds are ignored only when `--world` is given; unreadable output refuses with exit 4. Test: `test_parse_players_variants` (Task 2).

---

## File map

| Path | Task | Responsibility |
| --- | --- | --- |
| `tests/ashlar/conftest.py` | 1 | Puts `skills/exec-ashlar/scripts` on `sys.path` |
| `tests/ashlar/test_skill_text.py` | 1 | Static checks: Chapman leftovers, labelled client-specific names, frontmatter |
| `skills/exec-ashlar/scripts/ashlar_place.py` | 2, 3 | Placer: config discovery, validation, paging, snapshot tiling, MCP stdio client, `check`/`plan`/`place` |
| `tests/ashlar/test_place_core.py` | 2 | Offline placer tests |
| `tests/ashlar/fake_ashlar_mcp.py` | 3 | Scriptable stand-in for `ashlar-mcp` |
| `tests/ashlar/test_place_mcp.py` | 3 | Placer tests against the fake server |
| `skills/exec-ashlar/scripts/stamp.py` | 4 | Module stamping with block-state rotation and mirroring |
| `tests/ashlar/test_stamp.py` | 4 | Stamping tests |
| `skills/exec-ashlar/SKILL.md` and `reference/*.md` | 5 | The executor skill |
| `skills/design-monument/tools/voxel/` | 6 | Vendored voxel toolkit, its README and MIT notice |
| `tests/ashlar/test_voxel_smoke.py` | 6 | Voxel smoke test |
| `skills/survey-research/SKILL.md` | 7 | Labelled search/fetch instructions |
| `skills/design-*/**` | 8–13 | Design-skill edits |
| `skills/TAXONOMY.md`, `README.md`, `CLAUDE.md` | 14 | Fork notes |
| `/Users/bsw/Development/Minecraft/.claude/agents/ashlar-dry-run.md` | 17 | Read-only test agent (workspace, not the fork) |

## Edit catalogue (used by Tasks 8–13)

The design-skill tasks refer to these entries. Each entry gives the exact replacement wording; adapt only line wrapping and the surrounding sentence's grammar. `<x> <y> <z>` and `<project>` stay as literal placeholders in the skill text.

**C2: Connection section.** Replace the whole body of `## Connection` with:

```markdown
## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.
```

**C5: placement hard rule.** Replace the "Never place blocks … `exec-worker` executes it" bullet with:

```markdown
- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it (`build <project>`).
```

**C8: limits paragraph.** Replace the paragraph that begins "For volume limits" or "For the full limit detail" (it ends with a `command-budget.md` path) with:

```markdown
For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
slots), follow the `exec-ashlar` skill's `reference/tools-and-limits.md`
(`../exec-ashlar/reference/tools-and-limits.md`).
```

**C11: site survey wording.** `survey-site` → "the site survey"; "Invoke `survey-site` for site context" → "Run the `exec-ashlar` skill's site survey (`survey <project>`) for site context".

**C12: structured interview questions.** Remove the parenthetical "(use `AskUserQuestion` for the multiple-choice ones)" from the sentence, and add right after that paragraph:

```markdown
- Claude Code: use `AskUserQuestion` for the multiple-choice questions.
- Codex: use `request_user_input` for them if it is listed among your tools.
- Otherwise: ask them in plain text.
```

**C13: blueprint checklists.** "have the `exec-inspect` and `exec-reflect` re-check …" → "re-check … with the `exec-ashlar` skill's verification after the build"; "a fill over 32,768, (or) a structure over 64×384×64" → "a single call over Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`)"; "the actual placement is still a `exec-worker` job" → "the actual placement is the `exec-ashlar` skill's job".

**C14: tree growth.** Replace the sentence that places a sapling with Chapman tools and forces growth (it mentions `/place feature`, bone meal, `player_give_item` or `itemstack_drop_at`) with:

```markdown
grow it with the allowlisted `place feature minecraft:<tree_type> <x> <y> <z>`
console command (listed in the plan's `commands` table, inside a snapshotted
box), or place a sapling with `mc_build` and let it grow.
```

**C15: sign text.** Replace "set sign text with `block_entity_set_nbt`" and its example with:

````markdown
Write plain sign text with `mc_build`'s `sign` object on the sign's `blocks`
entry (`front`/`back`, up to 4 lines, `color`, `glowing`, `waxed`):

```json
{"pos": [<x>, <y>, <z>], "block": "minecraft:oak_wall_sign[facing=south]",
 "sign": {"front": ["The Gilded", "Anvil"], "color": "black", "waxed": true}}
```

For styled JSON text (per-line colours, bold), use the allowlisted
`data merge block <x> <y> <z> {front_text:{messages:[…]}}` with the same SNBT
the example below had, after the sign block exists.
````

Keep the original SNBT payload as the `data merge block` example.

**C16: other block-entity NBT.** `block_entity_set_nbt(pos, nbt='{…}')` → `data merge block <x> <y> <z> {…}` (keep the SNBT exactly), introduced as "the allowlisted `data merge block`". "Verify with `block_entity_get_nbt`" → "Verify with the read-only `data get block <x> <y> <z>`".

**C17: entities.**
- `entity_summon("minecraft:<type>", pos, nbt='{…}')` → `summon minecraft:<type> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}`, introduced as "the allowlisted `summon`"; keep the NBT, append the tags (merge into an existing `Tags` list).
- `entity_set_nbt` → `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}`.
- `entity_get_nbt` → `data get entity @e[tag=ashlar.<project>,…,limit=1]`.
- `entity_query` → `execute if entity @e[tag=ashlar.<project>,…]` (it reports a count).
- `Tags:["mcb_deco"]` → `Tags:["ashlar","ashlar.<project>"]`.

**C18: containers.**
- `inventory_set_slot(pos, slot=N, item={id:"minecraft:<item>",count:C,components:{…}})` → `item replace block <x> <y> <z> container.N with minecraft:<item>[<component>=<value>,…] C`. Each `components` entry becomes a `key=value` pair in the brackets.
- `loot_table_generate(<table>)` followed by `inventory_set_slot` → `data merge block <x> <y> <z> {LootTable:"<table>"}`, introduced as: "give the container a loot table with the allowlisted `data merge block`; the game rolls the contents the first time a player opens it".
- "round-trip with `itemstack_describe` … `server_get_status`" → "read the container back with the read-only `data get block <x> <y> <z> Items`; `mc_status` reports the server version".

**C19: modules instead of structure templates.** Replace build-once/stamp steps that use `exec-blueprint`, `structure_save_from_world`, `exec-worker`, `structure_load_to_world`, `mcb:` names and `mcbuilder`/`data_storage_*` with:

```markdown
2. Define each module **once** as `modules/<element>.json` in local coordinates
   (`../exec-ashlar/reference/modules.md`).
3. **Stamp** it wherever the layout places it: one `placements` row per instance
   in `plan.toon`, with `rotation` (0, 90, 180 or 270, clockwise from above) and
   `mirror` (`none`, `x` for east–west, `z` for north–south). `stamp.py` turns
   the rows into phase files.
5. Record every module and its instances in `.minecraft-builder/registry.json`.
```

Keep the original step 1 and step 4 text, and keep any variation advice (palette tweaks become module variants).

**C20: tool preview.** Replace the `block_transform_preview` sentence with: "Ashlar cannot preview what an axe, hoe or shovel would turn a block into; use the known vanilla results (stripped logs and wood, scraped or unwaxed copper, dirt path, farmland) directly."

**C21: biome.** Replace `level_get_biome_at` calls with: "read the biome during the survey — the `exec-ashlar` skill tests candidates with the read-only `execute if biome <x> <y> <z> <biome>`, or infers it from the surface materials", and replace the code example with `execute if biome 80 64 200 minecraft:cherry_grove`.

**C22: placement tools in prose.** `block_fill_region`, `block_set_state`, `block_fill_batch`, `block_clone_region` → "`mc_build`" (fills with modes `replace`, `keep`, `outline`, `hollow`, `walls`, an optional `filter`, single blocks with exact states, sign text, lettering).

**C24: verification.** "`exec-reflect` verifies …" / "`exec-inspect` …" → "the `exec-ashlar` skill's verification checks … after the build".

**C26: coordination wording in references.** "the orchestrator …" → name the skill the main session runs next, or "the user".

**C27: weathering reference.** `${CLAUDE_PLUGIN_ROOT}/reference/terrain/weathering.md` → "the `terrain-shape` skill's weathering guidance, if it is installed".

**Interim fallback sentence** (spec §7.3), used in the Hand-off sections below: "use the `terrain-shape` skill if it is installed; otherwise add a `site-prep` phase (clearing, levelling, pads, filling holes, soft-edged terraces) and tell the user if the site needs more than that."

---
## Task 1: Static skill-text checks

**Goal:** A pytest module that fails on any Chapman-pipeline reference, any unlabelled client-specific tool name, or bad frontmatter in the eight installed skills. Later tasks use it as their acceptance test.

**Files:**
- Create: `tests/ashlar/conftest.py`
- Create: `tests/ashlar/test_skill_text.py`

**Acceptance Criteria:**
- [ ] `test_leftovers_detects_tools_but_not_minecraft_ids` and `test_labelled_lines_allow_client_names` pass.
- [ ] Per-skill tests are parametrized with underscore ids (`design_house`, `exec_ashlar`, …) so `-k design_house` selects one skill.
- [ ] Running the whole file now fails for the unedited skills and the missing `exec-ashlar` folder (expected until Task 14).

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k "detects or labelled_lines"` → `2 passed`

**Steps:**

- [ ] **Step 1: Create `tests/ashlar/conftest.py`**

```python
"""Test setup: make the exec-ashlar scripts importable."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "exec-ashlar" / "scripts"
sys.path.insert(0, str(SCRIPTS))
```

- [ ] **Step 2: Create `tests/ashlar/test_skill_text.py`**

```python
"""Static checks for the Ashlar-adapted skills (spec §9.1 and §7.5)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SKILLS = ["design-building", "design-city", "design-grounds", "design-house",
          "design-monument", "design-village", "exec-ashlar", "survey-research"]
IDS = [skill.replace("-", "_") for skill in SKILLS]
CLIENTS_FILE = "skills/exec-ashlar/reference/clients.md"

CHAPMAN_TOOLS = [
    "block_fill_region", "block_set_state", "block_fill_batch", "block_clone_region",
    "block_entity_set_nbt", "block_entity_get_nbt", "block_render_region",
    "block_scan_region", "block_scan_summary", "block_get_state", "block_get_top_y",
    "block_transform_preview", "block_fill_columns", "block_fill_columns_strata",
    "structure_save_from_world", "structure_load_to_world", "structure_file_write",
    "entity_summon", "entity_set_nbt", "entity_get_nbt", "entity_query",
    "data_storage_get", "data_storage_set", "level_get_biome_at", "level_get_info",
    "level_get_weather", "command_execute", "player_give_item", "itemstack_drop_at",
    "itemstack_describe", "inventory_set_slot", "server_get_status",
    "schedule_function", "loot_table_generate", "mcp_place",
]
FORBIDDEN = [
    re.compile(r"\b(?:" + "|".join(CHAPMAN_TOOLS) + r")\b"),
    re.compile(r"CLAUDE_PLUGIN_ROOT"),
    re.compile(r"minecraft-mcp-setup"),
    re.compile(r"\bexec-(?:plan|blueprint|worker|inspect|reflect)\b"),
    re.compile(r"\bsurvey-site\b"),
    re.compile(r"32,768"),
    re.compile(r"\bmcb:"),
    re.compile(r"\bmcbuilder\b"),
    re.compile(r"\bsurvey\.toon\b"),
    re.compile(r"\borchestrator\b", re.IGNORECASE),
]
CLIENT_SPECIFIC = re.compile(
    r"AskUserQuestion|request_user_input|\bview_image\b|\bupdate_plan\b|\bTodoWrite\b"
    r"|\bWebSearch\b|\bWebFetch\b|\$\{CLAUDE_SKILL_DIR\}|\bmcp__")
LABELLED = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:Claude Code|Codex):")
NEW_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def leftovers(text: str) -> list[tuple[int, str]]:
    """(line, match) for every Chapman-pipeline reference in `text`."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            match = pattern.search(line)
            if match:
                hits.append((number, match.group(0)))
    return hits


def unlabelled_client_names(text: str, skip_lines: int = 0) -> list[tuple[int, str]]:
    """(line, name) for client-specific names outside labelled lines.

    A labelled line starts with `Claude Code:` or `Codex:` (optionally as a list
    item); its indented continuation lines count as labelled too.
    """
    hits = []
    in_label = False
    for number, line in enumerate(text.splitlines(), 1):
        if LABELLED.match(line):
            in_label = True
        elif not line.strip() or NEW_ITEM.match(line) or not line[:1].isspace():
            in_label = False
        match = CLIENT_SPECIFIC.search(line)
        if match and not in_label and number > skip_lines:
            hits.append((number, match.group(0)))
    return hits


def frontmatter(path: Path) -> tuple[dict, int]:
    """The parsed frontmatter and the number of lines it occupies."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path}: missing YAML frontmatter"
    return yaml.safe_load(match.group(1)) or {}, match.group(0).count("\n")


def _markdown(skill: str) -> list[Path]:
    root = REPO / "skills" / skill
    assert root.is_dir(), f"missing skill folder {root.relative_to(REPO)}"
    return sorted(root.rglob("*.md"))


@pytest.mark.parametrize("skill", SKILLS, ids=IDS)
def test_no_chapman_leftovers(skill: str) -> None:
    problems = [f"{path.relative_to(REPO)}:{number}: {hit}"
                for path in _markdown(skill)
                for number, hit in leftovers(path.read_text(encoding="utf-8"))]
    assert not problems, "Chapman pipeline references left:\n" + "\n".join(problems)


@pytest.mark.parametrize("skill", SKILLS, ids=IDS)
def test_client_specific_names_are_labelled(skill: str) -> None:
    problems = []
    for path in _markdown(skill):
        rel = path.relative_to(REPO).as_posix()
        if rel == CLIENTS_FILE:
            continue
        skip = frontmatter(path)[1] if path.name == "SKILL.md" else 0
        problems += [f"{rel}:{number}: {name}" for number, name in
                     unlabelled_client_names(path.read_text(encoding="utf-8"), skip)]
    assert not problems, "Unlabelled client-specific names:\n" + "\n".join(problems)


@pytest.mark.parametrize("skill", SKILLS, ids=IDS)
def test_frontmatter(skill: str) -> None:
    data, _ = frontmatter(REPO / "skills" / skill / "SKILL.md")
    assert data.get("name") == skill
    description = data.get("description")
    assert isinstance(description, str) and description.strip()
    assert len(description) <= 1024, f"description is {len(description)} characters"


def test_leftovers_detects_tools_but_not_minecraft_ids() -> None:
    assert leftovers("call block_set_state here") == [(1, "block_set_state")]
    assert leftovers("summon minecraft:block_display 1 2 3") == []
    assert leftovers('"entity_tag": "ashlar.demo"') == []
    assert leftovers("run exec-worker\nnothing\nthe Orchestrator") == [
        (1, "exec-worker"), (3, "Orchestrator")]


def test_labelled_lines_allow_client_names() -> None:
    text = ("Ask the user.\n"
            "- Claude Code: use `AskUserQuestion`.\n"
            "  continued with `AskUserQuestion` text\n"
            "- Otherwise: ask in plain text.\n"
            "Use WebFetch here.\n")
    assert unlabelled_client_names(text) == [(5, "WebFetch")]
    assert unlabelled_client_names("allowed-tools: mcp__ashlar__mc_status\n---\nbody", 2) == []
```

- [ ] **Step 3: Run the self-tests**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k "detects or labelled_lines"`
Expected: `2 passed`

- [ ] **Step 4: Confirm the per-skill checks fail on the unedited skills**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_house`
Expected: FAIL, listing lines such as `skills/design-house/SKILL.md:…: exec-worker`. This is the red state that Tasks 7–13 turn green.

- [ ] **Step 5: Commit**

```bash
git add tests/ashlar/conftest.py tests/ashlar/test_skill_text.py
git commit -F - <<'MSG'
test: add static checks for the Ashlar-adapted skills

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["tests/ashlar/conftest.py", "tests/ashlar/test_skill_text.py"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k \"detects or labelled_lines\"", "acceptanceCriteria": ["self-tests pass", "per-skill tests parametrized with underscore ids", "per-skill tests fail on unedited skills"], "modelTier": "mechanical"}
```

---

## Task 2: Placer core (offline)

**Goal:** `ashlar_place.py` with config discovery, secret redaction, phase-file validation, order-preserving paging, snapshot tiling, player and reply parsing, and the offline `plan` command.

**Files:**
- Create: `skills/exec-ashlar/scripts/ashlar_place.py`
- Test: `tests/ashlar/test_place_core.py`

**Acceptance Criteria:**
- [ ] Config lookup order is `~/.claude.json` (top-level, then `projects.<cwd>`), `./.mcp.json`, then `~/.codex/config.toml`; `--config` overrides; `${VAR}` and `${VAR:-default}` expand.
- [ ] `load_build` accepts a bare fills list and rejects `text`, `snapshot`, unknown keys, missing `minecraft:` namespaces, out-of-range y, bool coordinates and unknown fill modes (exit 2).
- [ ] Paging keeps order, puts every fill page before any block page, and keeps each page within the block, chunk and entry limits. Oversized `replace`/`keep` fills split; oversized shell fills are refused (exit 3).
- [ ] `python3 skills/exec-ashlar/scripts/ashlar_place.py plan FILE` prints a JSON summary with `bbox`, `cells`, `chunks`, `y_range`, `pages` and `snapshot_tiles`.

**Verify:** `uv run --no-project --with pytest pytest tests/ashlar/test_place_core.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/ashlar/test_place_core.py`

```python
"""Offline tests for ashlar_place.py."""
import json

import pytest

import ashlar_place as ap


def test_expand_variables():
    assert ap.expand("${A}-${B:-dflt}-${C}", {"A": "1"}) == "1-dflt-"


def test_find_server_order(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    (home / ".codex").mkdir(parents=True)
    cwd.mkdir()
    (home / ".codex" / "config.toml").write_text(
        '[mcp_servers.ashlar]\ncommand = "npx"\nargs = ["-y", "ashlar-mcp", "--stdio"]\n'
        '[mcp_servers.ashlar.env]\nMC_PLUGIN_URL = "ws://198.51.100.7:8159"\n',
        encoding="utf-8")
    entry = ap.find_server("ashlar", None, cwd, home, {})
    assert entry.command == "npx" and entry.args == ["-y", "ashlar-mcp", "--stdio"]
    assert entry.env == {"MC_PLUGIN_URL": "ws://198.51.100.7:8159"}
    assert entry.source.endswith("config.toml")
    (cwd / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"ashlar": {"command": "node", "args": ["mcp.js"]}}}), encoding="utf-8")
    assert ap.find_server("ashlar", None, cwd, home, {}).command == "node"
    (home / ".claude.json").write_text(json.dumps({"projects": {str(cwd): {
        "mcpServers": {"ashlar": {"type": "stdio", "command": "proj-cmd"}}}}}), encoding="utf-8")
    assert ap.find_server("ashlar", None, cwd, home, {}).command == "proj-cmd"
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": "${CMD:-fallback}", "env": {"T": "${TOKEN}"}}}}),
        encoding="utf-8")
    entry = ap.find_server("ashlar", None, cwd, home, {"TOKEN": "abc"})
    assert entry.command == "fallback" and entry.env == {"T": "abc"}


def test_find_server_errors(tmp_path):
    with pytest.raises(ap.PlacerError) as err:
        ap.find_server("ashlar", None, tmp_path, tmp_path, {})
    assert err.value.code == ap.EXIT_INPUT
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"mcpServers": {"ashlar": {"type": "http", "url": "https://x"}}}),
                      encoding="utf-8")
    with pytest.raises(ap.PlacerError) as err:
        ap.find_server("ashlar", str(config), tmp_path, tmp_path, {})
    assert "not a stdio server" in str(err.value)


def test_redact_hides_secrets_and_urls():
    out = ap.redact("connecting to ws://203.0.113.9:8159 token=tok-SECRET-123",
                    ["tok-SECRET-123", "ws://203.0.113.9:8159"])
    assert "203.0.113.9" not in out and "tok-SECRET-123" not in out and "***" in out


def test_load_build_rules(tmp_path):
    limits = ap.Limits()

    def write(obj):
        path = tmp_path / "b.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    ok = ap.load_build(write([{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}]),
                       limits)
    assert ok["fills"][0]["block"] == "minecraft:stone" and ok["blocks"] == []
    bad = [
        {"text": [{"text": "HI", "pos": [0, 64, 0], "block": "minecraft:stone"}]},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}], "snapshot": True},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone"}], "extra": 1},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "stone"}]},
        {"fills": [{"from": [0, 400, 0], "to": [1, 64, 1], "block": "minecraft:stone"}]},
        {"blocks": [{"pos": [0, True, 0], "block": "minecraft:stone"}]},
        {"fills": [{"from": [0, 64, 0], "to": [1, 64, 1], "block": "minecraft:stone", "mode": "spiral"}]},
        {"fills": [], "blocks": []},
    ]
    for obj in bad:
        with pytest.raises(ap.PlacerError) as err:
            ap.load_build(write(obj), limits)
        assert err.value.code == ap.EXIT_INPUT, obj


def test_chunks_across_zero():
    assert ap.chunks((-1, 0, -1, 0, 0, 0)) == 4
    assert ap.chunks((0, 0, 0, 15, 0, 15)) == 1
    assert ap.chunks((-16, 0, 0, -1, 0, 0)) == 1


def test_split_fill_covers_same_cells_within_limits():
    limits = ap.Limits(max_blocks=1000)
    pieces = ap.split_fill({"from": [0, 0, 0], "to": [29, 9, 9], "block": "minecraft:stone"}, limits)
    volumes = [ap.volume(ap.box_of(p["from"], p["to"])) for p in pieces]
    assert sum(volumes) == 3000 and max(volumes) <= 1000


def test_shell_fill_over_limit_is_refused():
    with pytest.raises(ap.PlacerError) as err:
        ap.split_fill({"from": [0, 0, 0], "to": [29, 9, 9], "block": "minecraft:stone",
                       "mode": "hollow"}, ap.Limits(max_blocks=1000))
    assert err.value.code == ap.EXIT_REFUSED


def test_pages_preserve_order_and_put_fills_first():
    build = {"fills": [
        {"from": [0, 64, 0], "to": [9, 73, 9], "block": "minecraft:air"},
        {"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"},
        {"from": [0, 65, 0], "to": [0, 66, 0], "block": "minecraft:oak_log"}],
        "blocks": [{"pos": [1, 65, 1], "block": "minecraft:torch"},
                   {"pos": [2, 65, 1], "block": "minecraft:torch"}],
        "connect": True}
    pages = ap.make_pages(build, ap.Limits(max_blocks=1000))
    kinds = ["fills" if "fills" in p.args else "blocks" for p in pages]
    assert kinds == ["fills", "fills", "blocks"]
    flat = [f["block"] for p in pages if "fills" in p.args for f in p.args["fills"]]
    assert flat == ["minecraft:air", "minecraft:stone", "minecraft:oak_log"]
    assert all(p.cells <= 1000 and p.args["connect"] is True for p in pages)


def test_entry_limit_splits_pages():
    blocks = [{"pos": [i, 64, 0], "block": "minecraft:stone"} for i in range(5)]
    pages = ap.make_pages({"fills": [], "blocks": blocks}, ap.Limits(max_ops=2))
    assert [len(p.args["blocks"]) for p in pages] == [2, 2, 1]


def test_tiles_respect_cap_and_cover_box():
    box = (0, 60, 0, 99, 79, 99)
    assert ap.tile(box, 200_000) == [box]
    big = (0, 60, 0, 199, 79, 99)
    tiles = ap.tile(big, 200_000)
    assert len(tiles) == 2 and all(ap.volume(t) <= 200_000 for t in tiles)
    assert sum(ap.volume(t) for t in tiles) == ap.volume(big)


def test_parse_players_variants():
    text = ("Alex  world  pos x=10 y=64 z=-5  facing north (block in front: 10,64,-6)  survival"
            "  looking at minecraft:stone at 10,63,-6 (up face)\n"
            "Sam  world_nether  pos x=100 y=70 z=100  facing east (block in front: 101,70,100)  creative")
    players = ap.parse_players(text)
    assert players == [("Alex", "world", 10, 64, -5), ("Sam", "world_nether", 100, 70, 100)]
    assert ap.players_inside(players, (0, 60, -10, 20, 80, 0), 2, None) == ["Alex"]
    assert ap.players_inside(players, (98, 60, 98, 99, 80, 99), 2, "world") == []
    assert ap.players_inside(players, (98, 60, 98, 99, 80, 99), 2, None) == ["Sam"]
    assert ap.parse_players("No players online.") == []
    with pytest.raises(ap.PlacerError) as err:
        ap.parse_players("something unexpected")
    assert err.value.code == ap.EXIT_PLAYER


def test_snapshot_id_and_warnings():
    reply = ('Snapshot snap-20261117-1-ab created for world "world", volume 9, at t.\n'
             'Call mc_restore({"id":"snap-20261117-1-ab"}) to restore this region later.')
    assert ap.snapshot_id(reply) == "snap-20261117-1-ab"
    text = ("Fills: done\nWARNINGS (blocks that would fall):\n"
            "  minecraft:torch at 1,64,1 - unsupported\n  minecraft:ladder at 2,64,1 - unsupported")
    assert ap.warnings_of(text) == ["minecraft:torch at 1,64,1 - unsupported",
                                    "minecraft:ladder at 2,64,1 - unsupported"]
    assert ap.warnings_of("Fills: done") == []


def test_cli_plan_prints_summary(tmp_path, capsys):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({
        "fills": [{"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"}],
        "blocks": [{"pos": [0, 65, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    assert ap.main(["plan", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["cells"] == 101 and summary["snapshot_tiles"] == 1
    assert summary["bbox"] == {"from": [0, 64, 0], "to": [9, 65, 9]}
    assert [page["kind"] for page in summary["pages"]] == ["fills", "blocks"]


def test_cli_plan_reports_invalid_input(tmp_path, capsys):
    path = tmp_path / "b.json"
    path.write_text("[]", encoding="utf-8")
    assert ap.main(["plan", str(path)]) == ap.EXIT_INPUT
    assert "nothing to place" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_place_core.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ashlar_place'`

- [ ] **Step 3: Create `skills/exec-ashlar/scripts/ashlar_place.py`**

```python
#!/usr/bin/env python3
"""Send generated Minecraft geometry to a Paper server through Ashlar.

Starts the `ashlar-mcp` server the same way the client config does (Claude
Code `~/.claude.json`, a project `.mcp.json`, or Codex `~/.codex/config.toml`),
speaks MCP over stdio, and sends a phase file as paged `mc_build` calls after a
player check and snapshots.

  ashlar_place.py check  [--server NAME] [--config PATH]
  ashlar_place.py plan   FILE [limit options]
  ashlar_place.py place  FILE (--snapshot [--label L] | --no-snapshot)
                         [--world W] [--player-margin 2] [--max-snapshots 15]
                         [--log PATH] [--server NAME] [--config PATH] [limit options]

A phase file is an `mc_build` arguments object (`fills`, `blocks`, `liquids`,
`connect`, `world`) or a bare list of fills. Exit codes: 0 ok, 2 invalid input,
3 refused by a limit or snapshot rule, 4 player in the area (or an unreadable
player list), 5 server error. Nothing printed ever contains a value from the
server entry's `env`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_INPUT, EXIT_REFUSED, EXIT_PLAYER, EXIT_SERVER = 0, 2, 3, 4, 5
SHELL_MODES = {"outline", "hollow", "walls"}
FILL_MODES = {"replace", "keep"} | SHELL_MODES
TOP_KEYS = {"fills", "blocks", "liquids", "connect", "world"}

Box = tuple[int, int, int, int, int, int]


class PlacerError(Exception):
    """A failure with the exit code the command line should return."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Limits:
    max_blocks: int = 500_000
    max_chunks: int = 1024
    max_ops: int = 4096
    snapshot_volume: int = 200_000
    min_y: int = -64
    max_y: int = 319


@dataclass
class Page:
    args: dict[str, Any]
    box: Box
    cells: int


# ------------------------------------------------------------------- config

@dataclass
class ServerEntry:
    command: str
    args: list[str]
    env: dict[str, str]
    source: str


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_URL = re.compile(r"\b(?:wss?|https?)://\S+")


def expand(value: str, environ: dict[str, str]) -> str:
    """Expand ${VAR} and ${VAR:-default} from `environ`."""
    def repl(match: re.Match[str]) -> str:
        default = match.group(2) if match.group(2) is not None else ""
        return environ.get(match.group(1), default)
    return _VAR.sub(repl, value)


def _lookup(path: Path, name: str, cwd: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        return (tomllib.loads(text).get("mcp_servers") or {}).get(name)
    data = json.loads(text)
    servers = data.get("mcpServers") or {}
    if name in servers:
        return servers[name]
    project = (data.get("projects") or {}).get(str(cwd)) or {}
    return (project.get("mcpServers") or {}).get(name)


def find_server(name: str, config: str | None, cwd: Path, home: Path,
                environ: dict[str, str]) -> ServerEntry:
    """Find the stdio MCP server entry called `name`."""
    if config:
        candidates = [Path(config)]
        if not candidates[0].is_file():
            raise PlacerError(f"config file not found: {config}", EXIT_INPUT)
    else:
        candidates = [home / ".claude.json", cwd / ".mcp.json",
                      home / ".codex" / "config.toml"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = _lookup(path, name, cwd)
        except ValueError as exc:  # JSONDecodeError and TOMLDecodeError
            raise PlacerError(f"cannot parse {path} ({exc.__class__.__name__})",
                              EXIT_INPUT) from None
        if raw is None:
            continue
        if not isinstance(raw, dict) or not raw.get("command"):
            raise PlacerError(f"server {name!r} in {path} is not a stdio server "
                              "(no 'command')", EXIT_INPUT)
        return ServerEntry(
            command=expand(str(raw["command"]), environ),
            args=[expand(str(a), environ) for a in raw.get("args") or []],
            env={str(k): expand(str(v), environ)
                 for k, v in (raw.get("env") or {}).items()},
            source=str(path),
        )
    raise PlacerError(f"no MCP server named {name!r} in: "
                      + ", ".join(str(c) for c in candidates), EXIT_INPUT)


def redact(text: str, secrets: list[str]) -> str:
    """Replace every secret value, and any URL, with ***."""
    for secret in sorted({s for s in secrets if len(s) >= 4}, key=len, reverse=True):
        text = text.replace(secret, "***")
    return _URL.sub("***", text)


# ----------------------------------------------------------------- geometry

def box_of(a: list[int], b: list[int]) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]),
            max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]))


def volume(box: Box) -> int:
    return (box[3] - box[0] + 1) * (box[4] - box[1] + 1) * (box[5] - box[2] + 1)


def chunks(box: Box) -> int:
    """16x16 chunk columns the box's x/z footprint touches."""
    return ((box[3] >> 4) - (box[0] >> 4) + 1) * ((box[5] >> 4) - (box[2] >> 4) + 1)


def union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes))


def halve(box: Box) -> tuple[Box, Box]:
    """Split a box in two across its longest axis."""
    sizes = [box[3] - box[0], box[4] - box[1], box[5] - box[2]]
    axis = sizes.index(max(sizes))
    mid = (box[axis] + box[axis + 3]) // 2
    first, second = list(box), list(box)
    first[axis + 3] = mid
    second[axis] = mid + 1
    return tuple(first), tuple(second)  # type: ignore[return-value]


def tile(box: Box, cap: int) -> list[Box]:
    """Cover `box` with boxes of at most `cap` cells."""
    if volume(box) <= cap:
        return [box]
    first, second = halve(box)
    return tile(first, cap) + tile(second, cap)


# -------------------------------------------------------------------- input

def _coords(value: Any, where: str, limits: Limits) -> None:
    if (not isinstance(value, list) or len(value) != 3
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
        raise PlacerError(f"{where}: expected [x, y, z] integers", EXIT_INPUT)
    if not limits.min_y <= value[1] <= limits.max_y:
        raise PlacerError(f"{where}: y={value[1]} is outside "
                          f"{limits.min_y}..{limits.max_y}", EXIT_INPUT)


def _block(value: Any, where: str) -> None:
    if not isinstance(value, str) or not value.startswith("minecraft:"):
        raise PlacerError(f"{where}: expected a 'minecraft:' block state string",
                          EXIT_INPUT)


def load_build(path: Path, limits: Limits) -> dict[str, Any]:
    """Read and validate a phase file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlacerError(f"cannot read {path}: {exc}", EXIT_INPUT) from None
    if isinstance(data, list):
        data = {"fills": data}
    if not isinstance(data, dict):
        raise PlacerError(f"{path}: expected an mc_build object or a list of fills",
                          EXIT_INPUT)
    if "text" in data:
        raise PlacerError(f"{path}: 'text' (lettering) is not accepted here; "
                          "place it with the client's own mc_build call", EXIT_INPUT)
    if "snapshot" in data:
        raise PlacerError(f"{path}: remove 'snapshot' and use --snapshot instead",
                          EXIT_INPUT)
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise PlacerError(f"{path}: unknown keys {unknown}", EXIT_INPUT)
    fills, blocks = data.get("fills") or [], data.get("blocks") or []
    if not fills and not blocks:
        raise PlacerError(f"{path}: nothing to place", EXIT_INPUT)
    for i, fill in enumerate(fills):
        where = f"fills[{i}]"
        if not isinstance(fill, dict):
            raise PlacerError(f"{where}: expected an object", EXIT_INPUT)
        _coords(fill.get("from"), f"{where}.from", limits)
        _coords(fill.get("to"), f"{where}.to", limits)
        _block(fill.get("block"), f"{where}.block")
        if fill.get("mode", "replace") not in FILL_MODES:
            raise PlacerError(f"{where}.mode: must be one of {sorted(FILL_MODES)}",
                              EXIT_INPUT)
    for i, block in enumerate(blocks):
        where = f"blocks[{i}]"
        if not isinstance(block, dict):
            raise PlacerError(f"{where}: expected an object", EXIT_INPUT)
        _coords(block.get("pos"), f"{where}.pos", limits)
        _block(block.get("block"), f"{where}.block")
    return {**data, "fills": fills, "blocks": blocks}


# ------------------------------------------------------------------- paging

def split_fill(fill: dict[str, Any], limits: Limits) -> list[dict[str, Any]]:
    """Split a fill that is too big for one call; shell fills cannot be split."""
    box = box_of(fill["from"], fill["to"])
    if volume(box) <= limits.max_blocks and chunks(box) <= limits.max_chunks:
        return [fill]
    mode = fill.get("mode", "replace")
    if mode in SHELL_MODES:
        raise PlacerError(f"a '{mode}' fill over the per-call limit cannot be split "
                          "without changing its shape; split it into separate fills "
                          "in the phase file", EXIT_REFUSED)
    pieces: list[dict[str, Any]] = []
    for half in halve(box):
        pieces += split_fill({**fill, "from": list(half[:3]), "to": list(half[3:])},
                             limits)
    return pieces


def _pack(items: list[tuple[dict[str, Any], Box]],
          limits: Limits) -> list[list[tuple[dict[str, Any], Box]]]:
    """Order-preserving packing within the block, chunk and entry limits."""
    groups: list[list[tuple[dict[str, Any], Box]]] = []
    current: list[tuple[dict[str, Any], Box]] = []
    cells = 0
    merged: Box | None = None
    for item, box in items:
        size = volume(box)
        grown = box if merged is None else union([merged, box])
        if current and (cells + size > limits.max_blocks
                        or chunks(grown) > limits.max_chunks
                        or len(current) >= limits.max_ops):
            groups.append(current)
            current, cells, grown = [], 0, box
        current.append((item, box))
        cells += size
        merged = grown
    if current:
        groups.append(current)
    return groups


def make_pages(build: dict[str, Any], limits: Limits) -> list[Page]:
    """Pages in mc_build's own order: every fill page before any block page."""
    shared = {k: build[k] for k in ("liquids", "connect", "world") if k in build}
    fills = [(piece, box_of(piece["from"], piece["to"]))
             for fill in build["fills"] for piece in split_fill(fill, limits)]
    blocks = [(block, box_of(block["pos"], block["pos"])) for block in build["blocks"]]
    pages: list[Page] = []
    for kind, items in (("fills", fills), ("blocks", blocks)):
        for group in _pack(items, limits):
            pages.append(Page(args={**shared, kind: [item for item, _ in group]},
                              box=union([box for _, box in group]),
                              cells=sum(volume(box) for _, box in group)))
    return pages


def plan_summary(build: dict[str, Any], limits: Limits,
                 path: Path) -> tuple[dict[str, Any], list[Page], list[Box]]:
    """Pages, snapshot tiles and a JSON-ready summary for one phase file."""
    pages = make_pages(build, limits)
    whole = union([page.box for page in pages])
    tiles = tile(whole, limits.snapshot_volume)
    summary = {
        "file": str(path),
        "bbox": {"from": list(whole[:3]), "to": list(whole[3:])},
        "cells": sum(page.cells for page in pages),
        "chunks": chunks(whole),
        "y_range": [whole[1], whole[4]],
        "pages": [{"kind": "fills" if "fills" in page.args else "blocks",
                   "entries": len(page.args.get("fills") or page.args.get("blocks")),
                   "cells": page.cells} for page in pages],
        "snapshot_tiles": len(tiles),
    }
    return summary, pages, tiles


# ------------------------------------------------------- players and replies

PLAYER_LINE = re.compile(r"^(?P<name>\S+)\s+(?P<world>\S+)\s+pos x=(?P<x>-?\d+) "
                         r"y=(?P<y>-?\d+) z=(?P<z>-?\d+)")
SNAPSHOT_ID = re.compile(r"^Snapshot (\S+) created")


def parse_players(text: str) -> list[tuple[str, str, int, int, int]]:
    """Parse mc_players text; refuse anything unexpected."""
    if text.strip() == "No players online.":
        return []
    players = []
    for line in text.strip().splitlines():
        match = PLAYER_LINE.match(line.strip())
        if not match:
            raise PlacerError("cannot read the mc_players output; refusing to build",
                              EXIT_PLAYER)
        players.append((match["name"], match["world"], int(match["x"]),
                        int(match["y"]), int(match["z"])))
    return players


def players_inside(players: list[tuple[str, str, int, int, int]], box: Box,
                   margin: int, world: str | None) -> list[str]:
    """Names of players inside `box` grown by `margin` (same world when given)."""
    x1, y1, z1, x2, y2, z2 = box
    return [name for name, player_world, x, y, z in players
            if (world is None or player_world == world)
            and x1 - margin <= x <= x2 + margin
            and y1 - margin <= y <= y2 + margin
            and z1 - margin <= z <= z2 + margin]


def snapshot_id(text: str) -> str:
    match = SNAPSHOT_ID.match(text.strip())
    if not match:
        raise PlacerError("unexpected mc_snapshot reply: " + text[:200], EXIT_SERVER)
    return match.group(1)


def warnings_of(text: str) -> list[str]:
    """The indented lines of mc_build's WARNINGS section."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("WARNINGS"):
            return [w.strip() for w in lines[i + 1:] if w.startswith("  ")]
    return []


# ---------------------------------------------------------------------- cli

def _add_limits(parser: argparse.ArgumentParser) -> None:
    defaults = Limits()
    parser.add_argument("--max-blocks", type=int, default=defaults.max_blocks)
    parser.add_argument("--max-chunks", type=int, default=defaults.max_chunks)
    parser.add_argument("--max-ops", type=int, default=defaults.max_ops)
    parser.add_argument("--snapshot-volume", type=int, default=defaults.snapshot_volume)
    parser.add_argument("--min-y", type=int, default=defaults.min_y)
    parser.add_argument("--max-y", type=int, default=defaults.max_y)


def _limits(ns: argparse.Namespace) -> Limits:
    return Limits(ns.max_blocks, ns.max_chunks, ns.max_ops, ns.snapshot_volume,
                  ns.min_y, ns.max_y)


def cmd_plan(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.file)
    summary, _, _ = plan_summary(load_build(path, limits), limits, path)
    print(json.dumps(summary, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashlar_place.py",
        description="Send generated Minecraft geometry through Ashlar.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="validate a phase file offline")
    plan.add_argument("file")
    _add_limits(plan)
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    handlers = {"plan": cmd_plan}
    try:
        return handlers[ns.cmd](ns)
    except PlacerError as exc:
        print(f"ashlar_place: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_place_core.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
chmod +x skills/exec-ashlar/scripts/ashlar_place.py
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/test_place_core.py
git commit -F - <<'MSG'
feat(exec-ashlar): add the placer's offline core and plan command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/test_place_core.py"], "verifyCommand": "uv run --no-project --with pytest pytest tests/ashlar/test_place_core.py -q", "acceptanceCriteria": ["config lookup order and expansion", "load_build validation rules", "order-preserving paging with fills first and limits respected; shell fills refused", "plan command prints JSON summary"], "modelTier": "mechanical"}
```

---

## Task 3: Placer MCP client, `check` and `place`

**Goal:** Add the MCP stdio client and the `check` and `place` commands to `ashlar_place.py`, tested against a scriptable fake server.

**Files:**
- Modify: `skills/exec-ashlar/scripts/ashlar_place.py` (imports, new client section, `build_parser`, `main`)
- Create: `tests/ashlar/fake_ashlar_mcp.py`
- Test: `tests/ashlar/test_place_mcp.py`

**Acceptance Criteria:**
- [ ] `check` prints the `mc_status` text and the config source path, never an env value.
- [ ] `place` runs `mc_players`, then every snapshot tile, then the pages in order; prints a JSON report with snapshot ids, warnings and per-page results; appends it to `--log`.
- [ ] A player inside the area gives exit 4 with no snapshot or build calls; a failing page gives exit 5 with `pages_done` showing how far it got; too many snapshot tiles gives exit 3 before the server starts; omitting both `--snapshot` and `--no-snapshot` gives exit 2.
- [ ] When the server dies, stderr shows `***` and never the URL or token.

**Verify:** `uv run --no-project --with pytest pytest tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q` → all pass

**Steps:**

- [ ] **Step 1: Create `tests/ashlar/fake_ashlar_mcp.py`**

```python
#!/usr/bin/env python3
"""Stand-in for ashlar-mcp in tests: newline-delimited JSON-RPC over stdio.

Environment knobs:
  FAKE_LOG         append one JSON line per tools/call: {"name": ..., "arguments": ...}
  FAKE_PLAYERS     mc_players reply text (default "No players online.")
  FAKE_FAIL_BUILD  1-based number of the mc_build call that returns isError
  FAKE_WARN        when set, every mc_build reply has a WARNINGS section
Like the real server it logs "connecting to <MC_PLUGIN_URL>" on stderr.
"""
import json
import os
import sys


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def text(body, error=False):
    return {"content": [{"type": "text", "text": body}], "isError": error}


def main():
    print(f"[fake] connecting to {os.environ.get('MC_PLUGIN_URL', '')}",
          file=sys.stderr, flush=True)
    builds = snapshots = 0
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        rid, method = message["id"], message.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-ashlar", "version": "0"}}})
            continue
        if method != "tools/call":
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": "no such method"}})
            continue
        name = message["params"]["name"]
        arguments = message["params"].get("arguments", {})
        if os.environ.get("FAKE_LOG"):
            with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"name": name, "arguments": arguments}) + "\n")
        if name == "mc_status":
            result = text("Plugin version: 0.4.9\nServer: fake")
        elif name == "mc_players":
            result = text(os.environ.get("FAKE_PLAYERS", "No players online."))
        elif name == "mc_snapshot":
            snapshots += 1
            sid = f"snap-test-{snapshots}"
            result = text(f'Snapshot {sid} created for world "world", volume 1, at now.\n'
                          f'Call mc_restore({{"id":"{sid}"}}) to restore this region later.')
        elif name == "mc_build":
            builds += 1
            send({"jsonrpc": "2.0", "method": "notifications/progress",
                  "params": {"progressToken": builds, "progress": 1}})
            if str(builds) == os.environ.get("FAKE_FAIL_BUILD"):
                result = text("Error: boom", error=True)
            else:
                body = "Fills: ok"
                if os.environ.get("FAKE_WARN"):
                    body += ("\nWARNINGS (blocks that would fall):\n"
                             "  minecraft:torch at 1,64,1 - unsupported")
                result = text(body)
        else:
            result = text(f"unknown tool {name}", error=True)
        send({"jsonrpc": "2.0", "id": rid, "result": result})


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing tests** in `tests/ashlar/test_place_mcp.py`

```python
"""ashlar_place.py against a fake ashlar-mcp server."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLACER = REPO / "skills" / "exec-ashlar" / "scripts" / "ashlar_place.py"
FAKE = Path(__file__).with_name("fake_ashlar_mcp.py")
URL, TOKEN = "ws://203.0.113.9:8159", "tok-SECRET-123"


def config(tmp_path, **fake_env):
    env = {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN,
           "FAKE_LOG": str(tmp_path / "calls.jsonl"), **fake_env}
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": [str(FAKE)], "env": env}}}),
        encoding="utf-8")
    return path


def run(*args):
    return subprocess.run([sys.executable, str(PLACER), *args],
                          capture_output=True, text=True, timeout=60)


def calls(tmp_path):
    log = tmp_path / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def build_file(tmp_path):
    path = tmp_path / "phase.json"
    path.write_text(json.dumps({
        "fills": [{"from": [0, 64, 0], "to": [9, 73, 9], "block": "minecraft:air"},
                  {"from": [0, 64, 0], "to": [9, 64, 9], "block": "minecraft:stone"}],
        "blocks": [{"pos": [1, 65, 1], "block": "minecraft:torch"}]}), encoding="utf-8")
    return path


def assert_no_secrets(proc):
    for stream in (proc.stdout, proc.stderr):
        assert "203.0.113.9" not in stream and TOKEN not in stream


def test_check_reports_status_without_secrets(tmp_path):
    proc = run("check", "--config", str(config(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert "Plugin version: 0.4.9" in proc.stdout
    assert_no_secrets(proc)


def test_place_snapshots_then_pages_in_order(tmp_path):
    log = tmp_path / "report.log"
    proc = run("place", str(build_file(tmp_path)), "--snapshot", "--label", "t",
               "--max-blocks", "1000", "--log", str(log),
               "--config", str(config(tmp_path, FAKE_WARN="1")))
    assert proc.returncode == 0, proc.stderr
    names = [c["name"] for c in calls(tmp_path)]
    assert names == ["mc_players", "mc_snapshot", "mc_build", "mc_build", "mc_build"]
    builds = [c["arguments"] for c in calls(tmp_path) if c["name"] == "mc_build"]
    assert [list(b) for b in builds] == [["fills"], ["fills"], ["blocks"]]
    snapshot = [c["arguments"] for c in calls(tmp_path) if c["name"] == "mc_snapshot"][0]
    assert snapshot == {"action": "create", "from": [0, 64, 0], "to": [9, 73, 9], "label": "t 1/1"}
    report = json.loads(proc.stdout)
    assert report["snapshots"] == ["snap-test-1"] and report["pages_done"] == 3
    assert "minecraft:torch at 1,64,1 - unsupported" in report["warnings"]
    assert json.loads(log.read_text(encoding="utf-8")) == report
    assert_no_secrets(proc)


def test_place_refuses_when_player_inside(tmp_path):
    players = "Alex  world  pos x=5 y=65 z=5  facing north (block in front: 5,65,4)  survival"
    proc = run("place", str(build_file(tmp_path)), "--snapshot",
               "--config", str(config(tmp_path, FAKE_PLAYERS=players)))
    assert proc.returncode == 4
    assert [c["name"] for c in calls(tmp_path)] == ["mc_players"]
    assert "Alex" in proc.stderr


def test_place_reports_partial_progress_on_failure(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--no-snapshot", "--max-blocks", "1000",
               "--config", str(config(tmp_path, FAKE_FAIL_BUILD="2")))
    assert proc.returncode == 5
    report = json.loads(proc.stdout)
    assert report["pages_done"] == 1 and "page 2/3" in report["error"]
    assert_no_secrets(proc)


def test_server_crash_redacts_url_and_token(tmp_path):
    crash = ("import os, sys; sys.stderr.write('connecting to ' + os.environ['MC_PLUGIN_URL']"
             " + ' token ' + os.environ['MC_PLUGIN_TOKEN'] + '\\n'); sys.exit(1)")
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": {"ashlar": {
        "type": "stdio", "command": sys.executable, "args": ["-c", crash],
        "env": {"MC_PLUGIN_URL": URL, "MC_PLUGIN_TOKEN": TOKEN}}}}), encoding="utf-8")
    proc = run("check", "--config", str(path))
    assert proc.returncode == 5
    assert "***" in proc.stderr
    assert_no_secrets(proc)


def test_place_needs_a_snapshot_choice(tmp_path):
    proc = run("place", str(build_file(tmp_path)), "--config", str(config(tmp_path)))
    assert proc.returncode == 2


def test_place_refuses_too_many_snapshots_before_starting_server(tmp_path):
    path = tmp_path / "big.json"
    path.write_text(json.dumps([{"from": [0, 0, 0], "to": [399, 99, 99],
                                 "block": "minecraft:stone"}]), encoding="utf-8")
    proc = run("place", str(path), "--snapshot", "--max-snapshots", "2",
               "--config", str(config(tmp_path)))
    assert proc.returncode == 3
    assert calls(tmp_path) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_place_mcp.py -q`
Expected: FAIL (`invalid choice: 'check'` / `'place'` from argparse, exit code 2)

- [ ] **Step 4: Replace the import block of `ashlar_place.py`** (from `import argparse` through `from typing import Any`) with:

```python
import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tomllib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
```

- [ ] **Step 5: Insert the client section** right before the `# ---…--- cli` divider line:

```python
# ------------------------------------------------------------------- client

class McpClient:
    """Minimal MCP client for one stdio server process."""

    def __init__(self, entry: ServerEntry, start_timeout: float = 120.0,
                 call_timeout: float = 600.0) -> None:
        self.secrets = list(entry.env.values())
        self.call_timeout = call_timeout
        self._stderr: deque[str] = deque(maxlen=40)
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        try:
            self.proc = subprocess.Popen(
                [entry.command, *entry.args], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, **entry.env}, text=True, encoding="utf-8",
                bufsize=1)
        except OSError as exc:
            raise PlacerError(f"cannot start the MCP server ({exc.__class__.__name__})",
                              EXIT_SERVER) from None
        self._out = threading.Thread(target=self._pump_stdout, daemon=True)
        self._err = threading.Thread(target=self._pump_stderr, daemon=True)
        self._out.start()
        self._err.start()
        try:
            self._request("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "ashlar-place", "version": "1"}}, start_timeout)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except PlacerError:
            self.close()
            raise

    def _pump_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _pump_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip("\n"))

    def stderr_tail(self) -> str:
        return redact("\n".join(self._stderr), self.secrets)

    def _died(self, what: str) -> PlacerError:
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        self._err.join(timeout=2)
        return PlacerError(f"{what}:\n{self.stderr_tail()}", EXIT_SERVER)

    def _send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except OSError:
            raise self._died("the MCP server exited early") from None

    def _request(self, method: str, params: dict[str, Any],
                 timeout: float) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method,
                    "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlacerError(f"timed out waiting for {method}", EXIT_SERVER)
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise self._died("the MCP server exited")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue  # notifications and anything that is not our reply
            if "error" in message:
                detail = str((message.get("error") or {}).get("message"))
                raise PlacerError(f"{method} failed: {redact(detail, self.secrets)}",
                                  EXIT_SERVER)
            return message.get("result") or {}

    def call(self, tool: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Call a tool; return its text and whether it reported an error."""
        result = self._request("tools/call", {"name": tool, "arguments": arguments},
                               self.call_timeout)
        text = "\n".join(item.get("text", "") for item in result.get("content") or []
                         if isinstance(item, dict) and item.get("type") == "text")
        return redact(text, self.secrets), bool(result.get("isError"))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# --------------------------------------------------------- check and place

def _server(ns: argparse.Namespace) -> ServerEntry:
    return find_server(ns.server, ns.config, Path.cwd(), Path.home(), dict(os.environ))


def cmd_check(ns: argparse.Namespace) -> int:
    entry = _server(ns)
    client = McpClient(entry)
    try:
        text, is_error = client.call("mc_status", {})
    finally:
        client.close()
    print(f"server entry {ns.server!r} from {entry.source}")
    print(text)
    return EXIT_SERVER if is_error else EXIT_OK


def _emit(report: dict[str, Any], log: str | None) -> None:
    text = json.dumps(report, indent=2)
    print(text)
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def cmd_place(ns: argparse.Namespace) -> int:
    limits = _limits(ns)
    path = Path(ns.file)
    build = load_build(path, limits)
    _, pages, tiles = plan_summary(build, limits, path)
    world = ns.world or build.get("world")
    if ns.world:
        for page in pages:
            page.args["world"] = ns.world
    if ns.snapshot and len(tiles) > ns.max_snapshots:
        raise PlacerError(f"this file needs {len(tiles)} snapshots (limit "
                          f"{ns.max_snapshots}); split it into smaller phase files",
                          EXIT_REFUSED)
    entry = _server(ns)
    report: dict[str, Any] = {"file": str(path), "pages_total": len(pages),
                              "pages_done": 0, "snapshots": [], "warnings": [],
                              "results": [], "error": None}
    client = McpClient(entry)
    try:
        text, is_error = client.call("mc_players", {})
        if is_error:
            raise PlacerError("mc_players failed: " + text, EXIT_SERVER)
        whole = union([page.box for page in pages])
        inside = players_inside(parse_players(text), whole, ns.player_margin, world)
        if inside:
            raise PlacerError("players inside the build area: " + ", ".join(inside),
                              EXIT_PLAYER)
        for i, box in enumerate(tiles if ns.snapshot else [], 1):
            args: dict[str, Any] = {"action": "create", "from": list(box[:3]),
                                    "to": list(box[3:]),
                                    "label": f"{ns.label} {i}/{len(tiles)}"}
            if world:
                args["world"] = world
            text, is_error = client.call("mc_snapshot", args)
            if is_error:
                raise PlacerError("mc_snapshot failed: " + text, EXIT_SERVER)
            report["snapshots"].append(snapshot_id(text))
        for i, page in enumerate(pages, 1):
            text, is_error = client.call("mc_build", page.args)
            if is_error:
                raise PlacerError(f"mc_build failed on page {i}/{len(pages)}: {text}",
                                  EXIT_SERVER)
            report["pages_done"] = i
            report["warnings"] += warnings_of(text)
            report["results"].append({"page": i, "result": [
                line for line in text.splitlines()
                if line and not line.startswith(("WARNINGS", "  "))][:5]})
    except PlacerError as exc:
        report["error"] = str(exc)
        _emit(report, ns.log)
        raise
    finally:
        client.close()
    _emit(report, ns.log)
    return EXIT_OK
```

- [ ] **Step 6: Replace `build_parser` and `main`** with:

```python
def _add_server(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server", default="ashlar",
                        help="MCP server name in the client config (default ashlar)")
    parser.add_argument("--config", help="read this config file instead")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashlar_place.py",
        description="Send generated Minecraft geometry through Ashlar.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="connect and run mc_status")
    _add_server(check)

    plan = sub.add_parser("plan", help="validate a phase file offline")
    plan.add_argument("file")
    _add_limits(plan)

    place = sub.add_parser("place", help="snapshot and place a phase file")
    place.add_argument("file")
    _add_limits(place)
    _add_server(place)
    choice = place.add_mutually_exclusive_group(required=True)
    choice.add_argument("--snapshot", action="store_true")
    choice.add_argument("--no-snapshot", action="store_true")
    place.add_argument("--label", default="ashlar_place")
    place.add_argument("--world")
    place.add_argument("--player-margin", type=int, default=2)
    place.add_argument("--max-snapshots", type=int, default=15)
    place.add_argument("--log")
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "plan": cmd_plan, "place": cmd_place}
    try:
        return handlers[ns.cmd](ns)
    except PlacerError as exc:
        print(f"ashlar_place: {exc}", file=sys.stderr)
        return exc.code
```

- [ ] **Step 7: Run all placer tests**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add skills/exec-ashlar/scripts/ashlar_place.py tests/ashlar/fake_ashlar_mcp.py tests/ashlar/test_place_mcp.py
git commit -F - <<'MSG'
feat(exec-ashlar): add the placer's MCP client, check and place commands

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/ashlar_place.py", "tests/ashlar/fake_ashlar_mcp.py", "tests/ashlar/test_place_mcp.py"], "verifyCommand": "uv run --no-project --with pytest pytest tests/ashlar/test_place_mcp.py tests/ashlar/test_place_core.py -q", "acceptanceCriteria": ["check prints status and config source without env values", "place order: players, snapshots, pages; JSON report and --log", "exit 4/5/3/2 cases", "server crash output redacted"], "modelTier": "standard"}
```

---

## Task 4: Module stamping (`stamp.py`)

**Goal:** `stamp.py` places module files at an origin with rotation and mirroring, transforming coordinates and block states, from the command line or from a `plan.toon` placements table.

**Files:**
- Create: `skills/exec-ashlar/scripts/stamp.py`
- Test: `tests/ashlar/test_stamp.py`

**Acceptance Criteria:**
- [ ] Coordinates: mirror first, then rotate clockwise from above, then translate so the minimum corner sits at the origin; four quarter turns are the identity.
- [ ] Block states: `facing`, `rotation`, `axis`, stair `shape`, rail `shape`, `hinge`, `orientation`, directional booleans on non-connecting blocks; connection properties dropped on fences, walls, panes, bars and redstone wire; chest `type` normalized to `single`.
- [ ] Modules with `text` or out-of-bounds coordinates are rejected; overlapping placements are rejected; `--phase` filters TOON placements.
- [ ] `stamp.py m.json --at=-10,64,-5` works with a negative origin.

**Verify:** `uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/ashlar/test_stamp.py`

```python
"""Tests for stamp.py."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import stamp as st

STAMP = Path(__file__).resolve().parents[2] / "skills" / "exec-ashlar" / "scripts" / "stamp.py"


def test_rotation_maps_corners_clockwise():
    size = [3, 1, 2]
    assert st.transform_point([2, 0, 0], size, 90, "none", [0, 0, 0]) == [1, 0, 2]
    assert st.transform_point([0, 0, 0], size, 90, "none", [0, 0, 0]) == [1, 0, 0]
    assert st.transform_point([0, 0, 0], size, 180, "none", [0, 0, 0]) == [2, 0, 1]
    assert st.transform_point([0, 0, 1], size, 270, "none", [10, 64, -5]) == [11, 64, -3]
    assert st.transform_point([0, 0, 0], size, 0, "x", [0, 0, 0]) == [2, 0, 0]
    assert st.transform_point([0, 0, 0], size, 0, "z", [0, 0, 0]) == [0, 0, 1]


def test_four_quarter_turns_are_identity():
    state = "minecraft:oak_stairs[facing=north,half=bottom,shape=inner_left]"
    turned = state
    for _ in range(4):
        turned = st.transform_state(turned, 90, "none")
    assert turned == state


@pytest.mark.parametrize("state,rotation,mirror,expected", [
    ("minecraft:oak_stairs[facing=north,half=bottom,shape=straight]", 90, "none",
     "minecraft:oak_stairs[facing=east,half=bottom,shape=straight]"),
    ("minecraft:oak_stairs[facing=north,shape=inner_left]", 0, "x",
     "minecraft:oak_stairs[facing=north,shape=inner_right]"),
    ("minecraft:oak_stairs[facing=north,shape=outer_right]", 0, "z",
     "minecraft:oak_stairs[facing=south,shape=outer_left]"),
    ("minecraft:oak_door[facing=east,half=lower,hinge=left]", 0, "x",
     "minecraft:oak_door[facing=west,half=lower,hinge=right]"),
    ("minecraft:oak_sign[rotation=4]", 90, "none", "minecraft:oak_sign[rotation=8]"),
    ("minecraft:oak_sign[rotation=4]", 0, "x", "minecraft:oak_sign[rotation=12]"),
    ("minecraft:oak_sign[rotation=2]", 0, "z", "minecraft:oak_sign[rotation=6]"),
    ("minecraft:oak_log[axis=x]", 90, "none", "minecraft:oak_log[axis=z]"),
    ("minecraft:oak_log[axis=y]", 90, "none", "minecraft:oak_log[axis=y]"),
    ("minecraft:rail[shape=north_south]", 90, "none", "minecraft:rail[shape=east_west]"),
    ("minecraft:rail[shape=ascending_east]", 90, "none", "minecraft:rail[shape=ascending_south]"),
    ("minecraft:rail[shape=south_east]", 90, "none", "minecraft:rail[shape=south_west]"),
    ("minecraft:oak_fence[east=true,north=false,south=false,waterlogged=false,west=true]", 90,
     "none", "minecraft:oak_fence[waterlogged=false]"),
    ("minecraft:cobblestone_wall[east=low,north=none,south=none,up=true,west=tall]", 90,
     "none", "minecraft:cobblestone_wall[up=true]"),
    ("minecraft:vine[east=false,north=true,south=false,up=false,west=false]", 90, "none",
     "minecraft:vine[south=false,east=true,west=false,up=false,north=false]"),
    ("minecraft:chest[facing=south,type=left]", 0, "none", "minecraft:chest[facing=south,type=single]"),
    ("minecraft:crafter[orientation=north_up,triggered=false]", 90, "none",
     "minecraft:crafter[orientation=east_up,triggered=false]"),
    ("minecraft:observer[facing=up]", 90, "none", "minecraft:observer[facing=up]"),
    ("minecraft:oak_wall_sign[facing=north]", 180, "none", "minecraft:oak_wall_sign[facing=south]"),
])
def test_block_state_transforms(state, rotation, mirror, expected):
    assert st.transform_state(state, rotation, mirror) == expected


def test_stamp_module_normalises_boxes_and_keeps_signs():
    module = {"name": "hut", "size": [3, 2, 2],
              "fills": [{"from": [0, 0, 0], "to": [2, 0, 1], "block": "minecraft:stone",
                         "filter": "minecraft:air"}],
              "blocks": [{"pos": [2, 1, 0], "block": "minecraft:oak_wall_sign[facing=north]",
                          "sign": {"front": ["Hi"]}}]}
    out = st.stamp(module, [100, 64, 100], 90, "none")
    assert out["fills"] == [{"from": [100, 64, 100], "to": [101, 64, 102],
                             "block": "minecraft:stone", "filter": "minecraft:air"}]
    assert out["blocks"] == [{"pos": [101, 65, 102],
                              "block": "minecraft:oak_wall_sign[facing=east]",
                              "sign": {"front": ["Hi"]}}]


def test_stamp_rejects_text_and_out_of_bounds():
    with pytest.raises(st.StampError):
        st.stamp({"size": [1, 1, 1], "text": [{}]}, [0, 0, 0], 0, "none")
    with pytest.raises(st.StampError):
        st.stamp({"size": [2, 2, 2], "blocks": [{"pos": [2, 0, 0], "block": "minecraft:stone"}]},
                 [0, 0, 0], 0, "none")
    with pytest.raises(st.StampError):
        st.stamp({"size": [2, 2, 2]}, [0, 0, 0], 45, "none")


def test_placements_from_plan_toon(tmp_path):
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "hut.json").write_text(json.dumps(
        {"size": [3, 2, 2], "fills": [{"from": [0, 0, 0], "to": [2, 1, 1],
                                       "block": "minecraft:stone"}]}), encoding="utf-8")
    plan = tmp_path / "plan.toon"
    plan.write_text(
        "plan:\n  project: t\n"
        "placements[3]{module,origin,rotation,mirror,phase}:\n"
        "  hut,0 64 0,0,none,2\n  hut,10 64 0,90,x,2\n  hut,1 64 1,0,none,3\n"
        "acceptance[0]{phase,at,expect}:\n", encoding="utf-8")
    rows = st.read_placements(plan, 2)
    assert [r["origin"] for r in rows] == [[0, 64, 0], [10, 64, 0]]
    assert len(st.stamp_all(rows, tmp_path / "modules")["fills"]) == 2
    with pytest.raises(st.StampError):
        st.stamp_all(st.read_placements(plan, None), tmp_path / "modules")


def test_cli_negative_origin(tmp_path):
    module = tmp_path / "m.json"
    module.write_text(json.dumps({"size": [1, 1, 1], "blocks": [
        {"pos": [0, 0, 0], "block": "minecraft:torch"}]}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(STAMP), str(module), "--at=-10,64,-5"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["blocks"][0]["pos"] == [-10, 64, -5]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stamp'`

- [ ] **Step 3: Create `skills/exec-ashlar/scripts/stamp.py`**

```python
#!/usr/bin/env python3
"""Stamp module files (local coordinates) into world-coordinate phase files.

A module has `size` [w, h, d] and `fills`/`blocks` in local coordinates with
its minimum corner at [0, 0, 0]. Each placement mirrors the module first
(`x` flips east-west, `z` flips north-south), then rotates it clockwise as seen
from above (0, 90, 180 or 270), then moves it so its minimum corner sits at the
origin. Block states turn with it.

  stamp.py MODULE.json --at=X,Y,Z [--rotate 0|90|180|270] [--mirror none|x|z] [--out FILE]
  stamp.py --placements PLAN.toon|PLACEMENTS.json --modules DIR [--phase N] --out FILE

Write `--at=X,Y,Z` with the equals sign so a negative X is not read as an option.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CLOCKWISE = {"north": "east", "east": "south", "south": "west", "west": "north"}
MIRRORS: dict[str, dict[str, str]] = {
    "none": {}, "x": {"east": "west", "west": "east"},
    "z": {"north": "south", "south": "north"}}
SIDES = ("north", "east", "south", "west")
STAIR_SHAPES = {"straight", "inner_left", "inner_right", "outer_left", "outer_right"}
CONNECTING_SUFFIXES = ("_fence", "_wall", "_pane")
CONNECTING_IDS = {"minecraft:iron_bars", "minecraft:redstone_wire"}
PLACEMENTS_HEADER = re.compile(
    r"^placements\[\d+\]\{module,origin,rotation,mirror,phase\}:\s*$")

Box = tuple[int, int, int, int, int, int]


class StampError(Exception):
    """Invalid module or placement."""


def parse_state(state: str) -> tuple[str, list[tuple[str, str]]]:
    match = re.fullmatch(r"([^\[\]]+)(?:\[(.*)\])?", state.strip())
    if not match:
        raise StampError(f"bad block state: {state!r}")
    props: list[tuple[str, str]] = []
    if match.group(2):
        for part in match.group(2).split(","):
            key, sep, value = part.partition("=")
            if not sep:
                raise StampError(f"bad property {part!r} in {state!r}")
            props.append((key.strip(), value.strip()))
    return match.group(1).strip(), props


def format_state(block_id: str, props: list[tuple[str, str]]) -> str:
    if not props:
        return block_id
    return block_id + "[" + ",".join(f"{k}={v}" for k, v in props) + "]"


def turn(direction: str, rotation: int, mirror: str) -> str:
    """Mirror, then rotate, one horizontal direction; other values pass through."""
    if direction not in CLOCKWISE:
        return direction
    direction = MIRRORS[mirror].get(direction, direction)
    for _ in range(rotation // 90):
        direction = CLOCKWISE[direction]
    return direction


def _rail_shape(value: str, rotation: int, mirror: str) -> str:
    if value.startswith("ascending_"):
        return "ascending_" + turn(value[len("ascending_"):], rotation, mirror)
    first, _, second = value.partition("_")
    ends = {turn(first, rotation, mirror), turn(second, rotation, mirror)}
    if ends == {"north", "south"}:
        return "north_south"
    if ends == {"east", "west"}:
        return "east_west"
    return (("north" if "north" in ends else "south") + "_"
            + ("east" if "east" in ends else "west"))


def transform_state(state: str, rotation: int, mirror: str) -> str:
    """Rotate and mirror one block state string."""
    block_id, props = parse_state(state)
    connecting = block_id.endswith(CONNECTING_SUFFIXES) or block_id in CONNECTING_IDS
    out: list[tuple[str, str]] = []
    for key, value in props:
        if key in SIDES:
            if not connecting:  # Ashlar's connection pass recomputes connecting blocks
                out.append((turn(key, rotation, mirror), value))
        elif key == "facing":
            out.append((key, turn(value, rotation, mirror)))
        elif key == "rotation" and value.isdigit():
            r = int(value)
            if mirror == "x":
                r = (16 - r) % 16
            elif mirror == "z":
                r = (8 - r) % 16
            out.append((key, str((r + 4 * (rotation // 90)) % 16)))
        elif key == "axis" and value in ("x", "z") and rotation in (90, 270):
            out.append((key, "z" if value == "x" else "x"))
        elif key == "shape" and value in STAIR_SHAPES:
            if mirror != "none" and value != "straight":
                kind, side = value.split("_")
                value = f"{kind}_{'right' if side == 'left' else 'left'}"
            out.append((key, value))
        elif key == "shape" and any(side in value for side in SIDES):
            out.append((key, _rail_shape(value, rotation, mirror)))
        elif key == "hinge" and mirror != "none":
            out.append((key, "right" if value == "left" else "left"))
        elif key == "type" and block_id.endswith("chest") and value in ("left", "right"):
            out.append((key, "single"))
        elif key == "orientation":
            out.append((key, "_".join(turn(part, rotation, mirror)
                                      for part in value.split("_"))))
        else:
            out.append((key, value))
    return format_state(block_id, out)


def transform_point(point: list[int], size: list[int], rotation: int, mirror: str,
                    origin: list[int]) -> list[int]:
    x, y, z = point
    width, _, depth = size
    if mirror == "x":
        x = width - 1 - x
    elif mirror == "z":
        z = depth - 1 - z
    for _ in range(rotation // 90):
        x, z = depth - 1 - z, x
        width, depth = depth, width
    return [x + origin[0], y + origin[1], z + origin[2]]


def footprint(size: list[int], rotation: int, origin: list[int]) -> Box:
    width, height, depth = size
    if rotation in (90, 270):
        width, depth = depth, width
    return (origin[0], origin[1], origin[2],
            origin[0] + width - 1, origin[1] + height - 1, origin[2] + depth - 1)


def _inside(point: Any, size: list[int], where: str) -> None:
    if (not isinstance(point, list) or len(point) != 3
            or not all(isinstance(v, int) and 0 <= v < s for v, s in zip(point, size))):
        raise StampError(f"{where}: {point!r} is outside the module size {size}")


def stamp(module: dict[str, Any], origin: list[int], rotation: int,
          mirror: str) -> dict[str, list[dict[str, Any]]]:
    """Place one module instance; returns {"fills": [...], "blocks": [...]}."""
    if rotation not in (0, 90, 180, 270):
        raise StampError(f"rotation must be 0, 90, 180 or 270, not {rotation}")
    if mirror not in MIRRORS:
        raise StampError(f"mirror must be none, x or z, not {mirror!r}")
    if "text" in module:
        raise StampError("modules may not contain 'text'; put lettering in its own phase")
    size = module.get("size")
    if (not isinstance(size, list) or len(size) != 3
            or not all(isinstance(v, int) and v > 0 for v in size)):
        raise StampError("module 'size' must be three positive integers [w, h, d]")
    fills = []
    for i, fill in enumerate(module.get("fills", [])):
        _inside(fill.get("from"), size, f"fills[{i}].from")
        _inside(fill.get("to"), size, f"fills[{i}].to")
        a = transform_point(fill["from"], size, rotation, mirror, origin)
        b = transform_point(fill["to"], size, rotation, mirror, origin)
        placed = {**fill, "from": [min(p, q) for p, q in zip(a, b)],
                  "to": [max(p, q) for p, q in zip(a, b)],
                  "block": transform_state(fill["block"], rotation, mirror)}
        if "filter" in fill:
            placed["filter"] = transform_state(fill["filter"], rotation, mirror)
        fills.append(placed)
    blocks = []
    for i, block in enumerate(module.get("blocks", [])):
        _inside(block.get("pos"), size, f"blocks[{i}].pos")
        blocks.append({**block,
                       "pos": transform_point(block["pos"], size, rotation, mirror, origin),
                       "block": transform_state(block["block"], rotation, mirror)})
    return {"fills": fills, "blocks": blocks}


def _overlaps(a: Box, b: Box) -> bool:
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


def read_placements(path: Path, phase: int | None) -> list[dict[str, Any]]:
    """Read placements from a JSON list or from a plan.toon placements table."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        rows = json.loads(text)
    else:
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines)
                      if PLACEMENTS_HEADER.match(line)), None)
        if start is None:
            raise StampError(f"{path}: no placements table")
        rows = []
        for line in lines[start + 1:]:
            if not line.strip() or not line[0].isspace():
                break
            cells = [cell.strip() for cell in line.strip().split(",")]
            if len(cells) != 5:
                raise StampError(f"{path}: bad placements row {line.strip()!r}")
            module, origin, rotation, mirror, row_phase = cells
            rows.append({"module": module, "origin": [int(v) for v in origin.split()],
                         "rotation": int(rotation), "mirror": mirror,
                         "phase": int(row_phase)})
    if phase is not None:
        rows = [row for row in rows if row.get("phase") == phase]
    return rows


def stamp_all(placements: list[dict[str, Any]], modules_dir: Path) -> dict[str, list]:
    """Stamp every placement into one phase file; placements may not overlap."""
    out: dict[str, list] = {"fills": [], "blocks": []}
    placed: list[tuple[Box, str]] = []
    cache: dict[str, dict[str, Any]] = {}
    for row in placements:
        name = row["module"]
        if name not in cache:
            cache[name] = json.loads((modules_dir / f"{name}.json").read_text(encoding="utf-8"))
        module = cache[name]
        box = footprint(module["size"], row["rotation"], row["origin"])
        for other, other_name in placed:
            if _overlaps(box, other):
                raise StampError(f"{name} at {row['origin']} overlaps {other_name}")
        placed.append((box, f"{name} at {row['origin']}"))
        part = stamp(module, row["origin"], row["rotation"], row.get("mirror", "none"))
        out["fills"] += part["fills"]
        out["blocks"] += part["blocks"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stamp.py",
                                     description="Stamp module files into phase files.")
    parser.add_argument("module", nargs="?", help="module JSON file")
    parser.add_argument("--at", help="origin X,Y,Z (write --at=X,Y,Z)")
    parser.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    parser.add_argument("--mirror", default="none", choices=("none", "x", "z"))
    parser.add_argument("--placements", help="plan.toon or a JSON list of placements")
    parser.add_argument("--modules", help="folder holding <module>.json files")
    parser.add_argument("--phase", type=int, help="only placements for this phase")
    parser.add_argument("--out", help="write the phase file here instead of stdout")
    ns = parser.parse_args(argv)
    try:
        if ns.placements:
            if not ns.modules or not ns.out:
                parser.error("--placements needs --modules and --out")
            result = stamp_all(read_placements(Path(ns.placements), ns.phase),
                               Path(ns.modules))
        else:
            if not ns.module or not ns.at:
                parser.error("give MODULE.json and --at=X,Y,Z, or --placements")
            origin = [int(v) for v in ns.at.split(",")]
            if len(origin) != 3:
                raise StampError("--at needs three integers X,Y,Z")
            module = json.loads(Path(ns.module).read_text(encoding="utf-8"))
            result = stamp(module, origin, ns.rotate, ns.mirror)
    except (StampError, OSError, ValueError, KeyError) as exc:
        print(f"stamp: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=1)
    if ns.out:
        Path(ns.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
chmod +x skills/exec-ashlar/scripts/stamp.py
git add skills/exec-ashlar/scripts/stamp.py tests/ashlar/test_stamp.py
git commit -F - <<'MSG'
feat(exec-ashlar): add module stamping with block-state rotation and mirroring

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/exec-ashlar/scripts/stamp.py", "tests/ashlar/test_stamp.py"], "verifyCommand": "uv run --no-project --with pytest pytest tests/ashlar/test_stamp.py -q", "acceptanceCriteria": ["coordinate convention mirror-rotate-translate; four turns identity", "block-state rules incl. connecting props dropped and chest type single", "text/out-of-bounds/overlap rejected; --phase filter", "negative origin via --at="], "modelTier": "mechanical"}
```

---
## Task 5: The `exec-ashlar` skill

**Goal:** Write `skills/exec-ashlar/SKILL.md` and its nine reference files, so a design skill can hand off a survey or an approved plan and Claude Code or Codex can build it through Ashlar.

**Files:**
- Create: `skills/exec-ashlar/SKILL.md`
- Create: `skills/exec-ashlar/reference/tools-and-limits.md`, `survey.md`, `plan-format.md`, `execution.md`, `verification.md`, `commands.md`, `modules.md`, `registry.md`, `clients.md`

**Acceptance Criteria:**
- [ ] The files contain the text below verbatim (wrapping may differ).
- [ ] `pytest tests/ashlar/test_skill_text.py -k exec_ashlar` passes: no Chapman leftovers, client-specific names only on labelled lines or in `clients.md`, valid frontmatter.
- [ ] `node scripts/validate-plugin.mjs` still passes.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar && node scripts/validate-plugin.mjs` → `3 passed` and `✓ plugin, marketplace, skills, and agents are valid`

**Steps:**

- [ ] **Step 1: Run the static checks to see them fail**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar`
Expected: FAIL with `missing skill folder skills/exec-ashlar`

- [ ] **Step 2: Create `skills/exec-ashlar/SKILL.md`**

````markdown
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
- Console commands only in the forms in `reference/commands.md`, and only the
  exact commands listed in the approved plan.
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
````

- [ ] **Step 3: Create `skills/exec-ashlar/reference/tools-and-limits.md`**

````markdown
# Ashlar tools and limits

Written for Ashlar 0.4.9 (plugin and `ashlar-mcp`) on Paper 26.3. When
`mc_status` reports a newer plugin version, re-check these limits against
Ashlar's README before relying on them.

## The nine tools

| Tool | Use it for | Writes? |
| --- | --- | --- |
| `mc_status` | Connection, plugin and server versions, build queue length | no |
| `mc_players` | Online players: world, block position, facing, the block in front, the block they look at | no |
| `mc_survey` | Surface heights over an x/z area: a heightmap image plus min/max/median height, surface materials and the largest flat zone; `matrix: true` adds per-block heights | no |
| `mc_render` | PNG views: `top`, `north`/`south`/`east`/`west` facades, `slice`, `heightmap` | no |
| `mc_inspect` | Exact blocks: `stats` (counts), `columns` (bottom-to-top runs per column), or an ASCII `slice` | no |
| `mc_snapshot` | `create` a restore point for a box, or `list` stored snapshots | stores a snapshot |
| `mc_restore` | Put a snapshot's box back exactly as captured | yes |
| `mc_build` | `fills` (modes `replace`, `keep`, `outline`, `hollow`, `walls`; optional `filter`), `blocks` (with optional `sign` text), `text` (lettering) | yes |
| `mc_command` | One console command with full operator rights; only the forms in `commands.md` | depends |

## Limits

Ashlar's defaults. A server can change them, and a call over a limit is
rejected before anything changes: split and retry rather than guess.

| Limit | Default |
| --- | --- |
| Blocks per `mc_build` call | 500,000 |
| Chunk footprint per write call | 1,024 chunks (a 512 × 512 area) |
| Cells per `mc_inspect` call and per side/slice `mc_render` | 200,000 |
| Area per `mc_survey` call and per top/heightmap `mc_render` | 200,000 x/z cells |
| Columns per `mc_inspect` `format: "columns"` call | 1,024 |
| Distinct block types in an `mc_inspect` ASCII slice | 47 (narrow the region if a slice has more) |
| Flowing liquids per call (`liquids: "flow"`) | 2,000 |
| Queued operations | 16 |
| Snapshots kept | 20, oldest evicted first, shared by everything on the server |
| Cells per snapshot | 200,000 |
| World height (overworld) | y −64 to 319 |
| Worlds | only those in the plugin's `world.allowed-worlds` |

## Behaviour to plan around

- `mc_build` runs, in order: the snapshot (if `snapshot: true`), all fills, all
  text, then all blocks. If the snapshot box exceeds the snapshot cap, the
  whole call fails before writing.
- Blocks are written with physics off: sand does not fall, water and lava stay
  put (unless `liquids: "flow"`), and redstone does not update.
- A connection pass afterwards joins fences, panes, walls, bars, stairs and
  redstone wire to their neighbours.
- Attached blocks without support (torches, ladders, signs, doors, carpets…)
  come back under `WARNINGS`; fix them before calling a phase done.
- Snapshots do not keep sign text, container contents or entities. A restore
  empties signs and containers in its box, including ones that were there
  before the build.
- `mc_render` shows blocks, not entities, and map colours are approximate.
- `mc_render` and `mc_survey` return images you can look at directly.

## Block-state orientation

From `mc_build`'s own rules:

- Attached blocks (ladder, wall torch, wall sign, wall banner, wall-mounted
  lever or button): `facing` points away from the supporting block. A ladder on
  a room's west wall is `ladder[facing=east]`.
- Doors: the panel sits flush with the face opposite `facing`. Place
  `half=lower` at y and `half=upper` at y+1 with the same other properties;
  `hinge` chooses the swing side.
- Stairs: the tall half is on the `facing` side; `half=top` is upside down.
- Beds: `part=foot` at the position, `part=head` one block toward `facing`.
- Chests and furnaces: `facing` is the side the front is on. Adjacent chests
  with the same facing pair automatically; write `type=single`.
- Slabs: `type=bottom|top|double`.
- Torches: `torch` stands on the block below; on a wall use
  `wall_torch[facing=<away from the wall>]` in the air block beside it.
- Signs: put the text in the `sign` object of a `blocks` entry (`front`/`back`,
  up to 4 lines of 64 characters, `color`, `glowing`, `waxed`), in the air
  block in front of the wall for wall signs.
- Leaves that must not decay: `persistent=true`.
````

- [ ] **Step 4: Create `skills/exec-ashlar/reference/survey.md`**

````markdown
# Site survey

Run when a design skill asks for `survey <project>`, before it designs.

## Procedure

1. **Locate the site.**
   - Relative to a player ("here", "in front of me"): call `mc_players` and use
     that player's position, the block in front, or the block they look at.
   - Given coordinates or an earlier build: use them.
   - Neither: ask the user.
2. **Survey the ground** with `mc_survey` over the site plus a margin of at
   least 16 blocks on every side. Note min/max/median height, surface
   materials, water and lava, and the largest flat zone with its y.
3. **Look at it** with a top-view `mc_render` over the same area, and with
   facade views (`north`, `south`, `east`, `west`, y limited to the structure)
   of anything already standing on the site.
4. **Check existing structures and block entities** with `mc_inspect`
   (`stats`) over the planned footprint. List any signs, chests, barrels,
   banners, lecterns, shulker boxes or other block entities: a restore would
   empty them, so the approval gate must mention them.
5. **Biome**, only when the palette depends on it: infer it from the surface
   materials, or test candidates with the read-only
   `execute if biome <x> <y> <z> <biome>` (`commands.md`).
6. **Players**: note who is online and how close they are to the site.
7. **Other worlds**: before designing for the Nether or the End, call
   `mc_survey` with that world's name over a small area. If Ashlar refuses the
   world, tell the user the build cannot be placed there.

## survey.md

Write `.minecraft-builder/<project>/survey.md`:

```markdown
# Survey: <project>

- Date: <YYYY-MM-DD>
- World: <name, or "default">
- Site (x/z): <x1> <z1> → <x2> <z2>
- Ground: min <y>, max <y>, median <y>; <slope notes>
- Largest flat zone: <x1> <z1> → <x2> <z2> at y <y>
- Surface: <main materials>
- Water and lava: <where, or "none">
- Existing structures: <what and where, or "none">
- Block entities a restore would empty: <list with coordinates, or "none">
- Biome: <id and how it was read, or "not read">
- Players near the site: <names and distances, or "none">
- Notes for the design: <site preparation, hazards, views>
```
````

- [ ] **Step 5: Create `skills/exec-ashlar/reference/plan-format.md`**

````markdown
# Plan format

A design skill hands `exec-ashlar` three kinds of files in
`.minecraft-builder/<project>/`:

- `plan.toon`: the readable plan (TOON, <https://toonformat.dev/>);
- `phases/NN-<name>.json`: the exact geometry for each phase;
- `modules/<name>.json`: repeated elements in local coordinates (`modules.md`).

## plan.toon

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

- `plan`: `project` (kebab-case), `skill` (the design skill that wrote it),
  `world` (omit for the server's default world), `anchor`, a `bbox` covering
  every phase, a one-line `summary`, and `approved` (`no` until the user
  approves at the gate, then the date).
- `phases`: one row per phase, in build order. `blocks` is the cell count from
  `ashlar_place.py plan`; `from`/`to` is the phase's box; `via` is one of:
  - `mcp`: you send the phase file with your own `mc_build` call. Only for
    files with at most 200 entries. Lettering (`text`) must be in an `mcp`
    phase because the placer does not accept it.
  - `placer`: `python3 <skill>/scripts/ashlar_place.py place <file> --snapshot …`,
    for anything larger or generated.
  - `commands`: a phase made only of `commands` rows; `file` is `-`.
- `materials`: the palette by role.
- `modules` and `placements`: see `modules.md`. `stamp.py` produces each
  phase's file from its placements before the build.
- `commands`: every console command, in order, exactly as it will run, each
  matching `commands.md`.
- `acceptance`: spot checks, one cell each.
- `quality_contract`: the property checks below.

## Phase files

A phase file is exactly the arguments of one `mc_build` call, in absolute
coordinates:

```json
{
  "fills": [{"from": [104, 63, -358], "to": [112, 63, -352], "block": "minecraft:cobblestone"}],
  "blocks": [{"pos": [107, 64, -358], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"}],
  "liquids": "static",
  "connect": true
}
```

- Keys: `fills`, `blocks`, `text` (only in `mcp` phases), `liquids`, `connect`,
  `world`. No `snapshot` key: snapshots are taken separately.
- Block strings carry the `minecraft:` namespace and full block states.
- A bare fills list (`[{"from", "to", "block"}, …]`) is also accepted by the
  placer; the voxel toolkit writes that form.
- Order: `mc_build` places all fills in order, then text, then blocks.
  Anything that must come after a block placement goes in a later phase.

## quality_contract rows

Use every row type that applies. Each is checked after the build
(`verification.md`); a failing row fails the build.

| Row | Fields | Passes when |
| --- | --- | --- |
| `walkability` | `from,to,note` | every step on the straight route has a floor and two clear cells above it, and climbs or drops by at most one block |
| `doors` | `at,facing,clearance_blocks` | both sides of the door have a floor and two clear cells for `clearance_blocks` blocks |
| `headroom` | `over_region_a,over_region_b,min_clear` | every column in the region has at least `min_clear` clear cells above its walking surface |
| `block_mix_ratios` | `region_a,region_b,palette,max_single_ratio` | no single block exceeds `max_single_ratio` of the region's non-air blocks, and every listed palette member is present |
| `silhouette` | `region_a,region_b,sample_count,min_y_variance` | the variance of the top y at `sample_count` evenly spaced columns is at least `min_y_variance` |
| `connectivity` | `site_a,site_b,via` | the named route between the two sites is walkable end to end |
| `edge_irregularity` | `edge_name,from,to,max_collinear_run` | no run of identical x or z along the edge is longer than `max_collinear_run` (terrain) |

Coordinates in rows are `x y z` triples; regions are two corners. If you cannot
write a row because you do not know the answer (is this door reachable?), the
plan is not finished.

## Validation (start of `build`)

Stop and report if any of these fails:

1. `project` is kebab-case and matches the folder name.
2. Every phase file exists and `ashlar_place.py plan` accepts it (except
   `mcp` phases with `text`, which you check by hand); `mcp` phase files have
   at most 200 entries; only `mcp` phases contain `text`.
3. Every coordinate is an integer inside the world's height range.
4. Every `placements` row names a module listed in `modules`.
5. Every `commands` row matches a form in `commands.md`, with the project's
   tags where the form requires them.
6. `quality_contract` has at least one row, and every door, stair and named
   room in the design is covered.
7. The snapshot slots for the whole build are known.
````

- [ ] **Step 6: Create `skills/exec-ashlar/reference/execution.md`**

````markdown
# Execution

## Approval gate

Before the first write, show the user:

- the project, world and bounding box;
- the phases in order, each with its cell count, its `via`, and the snapshot
  tiles it needs;
- the total snapshot slots needed. Ashlar keeps 20 for the whole server. If the
  build needs more than 15, say that the oldest phases' snapshots will be
  evicted before the build ends, so those phases cannot be rolled back;
- every console command, exactly as it will run;
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
     in the area. Exit 3: the file needs more snapshots than allowed; split it
     into smaller phase files. Exit 5: the server failed part way; the report
     lists the pages already written and the snapshot ids.
   - `commands`: one `mc_command` call per row, in order, exactly as written.
4. **Warnings**: every line under `WARNINGS` is an attached block without
   support. Fix them with another `mc_build` call before moving on.
5. **Look**: `mc_render` top view, plus the facade the phase changed most.
6. **Record**: append the phase to `build-log.md` and the registry.

## Ordering rules

- Clear with air first, then structure, then attached blocks (torches, ladders,
  signs, doors, carpets, banners) once what they attach to exists.
- Later phases never undo earlier ones.
- Block-entity data (`data merge block`, `item replace block`) comes after its
  block exists.
- Entities (`summon`) come last, after all blockwork, so fills do not disturb
  them.

## Liquids and redstone

- Water and lava are placed still. Use `liquids: "flow"` only for a few source
  blocks (a fountain head, a waterfall source): at most 2,000 flowing blocks per
  call.
- Redstone does not update when placed. Every contraption needs a start lever
  or button; tell the user what to flip.

## Rollback

1. `mc_restore` each recorded snapshot, newest phase first.
2. Remove the build's entities with `kill @e[tag=ashlar.<project>]`.
3. Tell the user that sign text and container contents inside restored boxes
   are gone, including ones that were there before the build, and which phases'
   snapshots were evicted and could not be restored.
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
````

- [ ] **Step 7: Create `skills/exec-ashlar/reference/verification.md`**

````markdown
# Verification

Run after the last phase, and for `verify <project>`. Report every check as
passed or failed with its evidence; fix failures and verify again.

## Reading columns

`mc_inspect` with `format: "columns"` returns one line per column, bottom to
top, without the `minecraft:` prefix:

```text
121,-340: 58-63 dirt | 64-64 stone_bricks | 65-71 air
```

At most 1,024 columns per call. For a route, inspect a one-block-wide box along
it, split into pieces for long routes.

A cell is **walkable** when the block under the feet is solid (or a slab,
stair, path, farmland, or carpet on a solid block) and the two cells above are
air or passable (open doors, signs, torches, pressure plates, carpet, rails,
flowers, grass).

## Rows

| Row | How to check |
| --- | --- |
| `acceptance{at,expect}` | `mc_inspect` stats over the single cell; the block must match `expect` (unspecified block-state properties are ignored) |
| `walkability{from,to}` | Inspect columns along the straight line from `from` to `to`. Every step must be walkable, and the walking height may change by at most 1 between neighbouring cells |
| `doors{at,facing,clearance_blocks}` | Inspect the cells on both sides of the door along `facing` for `clearance_blocks` blocks; each must be walkable |
| `headroom{over_region_a,over_region_b,min_clear}` | Inspect columns over the region; above each walking surface there must be at least `min_clear` clear cells |
| `block_mix_ratios{region_a,region_b,palette,max_single_ratio}` | `mc_inspect` stats over the region; drop air; the largest block's share must not exceed `max_single_ratio`, and every palette member must appear |
| `silhouette{region_a,region_b,sample_count,min_y_variance}` | `mc_survey` with `matrix: true` over the region's x/z (or columns at `sample_count` evenly spaced points); the variance of the top y values must be at least `min_y_variance` |
| `connectivity{site_a,site_b,via}` | Follow the route the plan names for `via` as a polyline and check it like `walkability` |
| `edge_irregularity{edge_name,from,to,max_collinear_run}` | `mc_survey` matrix along the edge; the longest run holding the same x (or z) must not exceed `max_collinear_run` |

## Look at it

Compare with the approved blueprints (and, for monuments, the reference
renders):

- `mc_render` `top` over the bounding box, for layout and footprint;
- facades `north`, `south`, `east`, `west`, with y limited to the structure
  (side views are volume-priced);
- `slice` with `axis: "y"` at each floor level, for floor plans.

Map colours are approximate and different blocks can share one; check exact
blocks with `mc_inspect` where it matters. `mc_render` does not show entities.

## Entities and NBT

- Count the build's entities: `execute if entity @e[tag=ashlar.<project>]`,
  adding `type=` to count one kind.
- Block-entity details: `data get block <x> <y> <z>` (signs, banners, lecterns,
  containers).
- Villagers: after a short wait, read each one's memories with
  `data get entity @e[tag=ashlar.<project>,tag=ashlar.<project>.<name>,limit=1] Brain.memories` and
  confirm `minecraft:home` (its bed) and `minecraft:job_site` are set.

## Report

List each check with pass or fail and its evidence (a column line, a count, a
render). The build is done only when every check passes.
````

- [ ] **Step 8: Create `skills/exec-ashlar/reference/commands.md`**

````markdown
# Console commands

`mc_command` runs a command with full operator rights. Use only these forms,
only for what Ashlar's other tools cannot do, and only the exact commands listed
in the approved plan's `commands` table.

## Allowed forms

| Purpose | Form |
| --- | --- |
| Summon an entity (villagers, golems, animals, armor stands, item frames, display entities) | `summon <entity> <x> <y> <z> {…,Tags:["ashlar","ashlar.<project>"]}` |
| Set block-entity NBT (styled sign text, banner patterns, lectern books, decorated pots, heads, loot tables) | `data merge block <x> <y> <z> {…}` |
| Change one of the build's entities | `data merge entity @e[tag=ashlar.<project>,…,limit=1] {…}` |
| Put an item in a container slot | `item replace block <x> <y> <z> container.<n> with <item>[<components>] [count]` |
| Grow a tree or other feature | `place feature <feature> <x> <y> <z>` |
| Remove the build's entities | `kill @e[tag=ashlar.<project>…]` |

Read-only checks:

| Purpose | Form |
| --- | --- |
| Test the biome at a position | `execute if biome <x> <y> <z> <biome>` |
| Read block-entity NBT | `data get block <x> <y> <z> [path]` |
| Read one of the build's entities | `data get entity @e[tag=ashlar.<project>,…,limit=1] [path]` |
| Count the build's entities | `execute if entity @e[tag=ashlar.<project>,…]` |

## Rules

- Never `fill`, `setblock`, `clone`, `give`, `tp`, `gamerule`, `function`,
  `schedule` or any other command, and never use a console command to get
  around one of Ashlar's limits.
- Every summoned entity carries the tags `ashlar` and `ashlar.<project>`. An
  entity you will read back or change later also gets its own tag, such as
  `ashlar.<project>.farmer1`, so selectors can target it without a position:
  `@e[tag=ashlar.<project>,tag=ashlar.<project>.farmer1,limit=1]`.
- Every selector in `data merge entity`, `data get entity`, `execute if entity`
  and `kill` includes `tag=ashlar.<project>`.
- `place feature` changes blocks: keep it inside a snapshotted box.
- Write commands without a leading `/`.
- Snapshots do not capture entities or block-entity contents: rollback removes
  entities with `kill` and cannot bring NBT back (`execution.md`).

## Examples

```text
summon minecraft:villager 121 65 -333 {VillagerData:{profession:"minecraft:farmer",level:1,type:"minecraft:plains"},Tags:["ashlar","ashlar.oakhollow","ashlar.oakhollow.farmer1"]}
data merge block 107 66 -357 {patterns:[{color:"red",pattern:"minecraft:stripe_center"}]}
item replace block 110 64 -352 container.0 with minecraft:iron_sword 1
data merge block 110 64 -351 {LootTable:"minecraft:chests/village/village_weaponsmith"}
place feature minecraft:oak 130 64 -345
execute if entity @e[tag=ashlar.oakhollow,type=minecraft:villager]
kill @e[tag=ashlar.oakhollow]
```
````

- [ ] **Step 9: Create `skills/exec-ashlar/reference/modules.md`**

````markdown
# Modules and stamping

Ashlar has no structure templates, so a repeated element is a **module file**
that `scripts/stamp.py` places as many times as needed, turned and mirrored as
the layout requires.

## Module file

`.minecraft-builder/<project>/modules/<name>.json`, in local coordinates with
the minimum corner at `[0, 0, 0]`:

```json
{
  "name": "small-house-a",
  "size": [9, 8, 7],
  "fills": [
    {"from": [0, 0, 0], "to": [8, 0, 6], "block": "minecraft:cobblestone"},
    {"from": [0, 1, 0], "to": [8, 4, 6], "block": "minecraft:spruce_planks", "mode": "walls"}
  ],
  "blocks": [
    {"pos": [4, 1, 0], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"},
    {"pos": [4, 2, 0], "block": "minecraft:spruce_door[facing=north,half=upper,hinge=left]"}
  ]
}
```

- `size` is `[width (x), height (y), depth (z)]`; every coordinate must lie
  inside it.
- Build each module with its front facing north (toward −z), so placement
  rotations read naturally.
- Modules may not contain `text`; put lettering in its own `mcp` phase.
- Palette variants are separate module files (`small-house-a-birch.json`).

## Placement convention

For each placement, `stamp.py`:

1. mirrors the module (`none`; `x` flips east–west; `z` flips north–south);
2. rotates it clockwise as seen from above (`0`, `90`, `180`, `270`);
3. moves it so its minimum corner sits at `origin`.

Block states turn with it: `facing`, sign and banner `rotation`, log `axis`,
stair and rail `shape`, door `hinge`, crafter `orientation`, and the side
properties of vines, lichen and mushroom blocks. Fence, wall, pane, bar and
redstone-wire connections are dropped because Ashlar's connection pass
recomputes them. Chest `type` becomes `single`; Ashlar pairs chests itself.
Placements must not overlap; `stamp.py` refuses overlapping instances.

## Running it

Run from the workspace root, with `<skill>` as the `exec-ashlar` skill's folder
(`SKILL.md` explains how to find it in your client):

```bash
python3 <skill>/scripts/stamp.py .minecraft-builder/<project>/modules/small-house-a.json --at=104,64,-358 --rotate 90 --mirror x --out .minecraft-builder/<project>/phases/02-house-a.json
python3 <skill>/scripts/stamp.py --placements .minecraft-builder/<project>/plan.toon --modules .minecraft-builder/<project>/modules --phase 2 --out .minecraft-builder/<project>/phases/02-houses.json
```

Write `--at=X,Y,Z` with the equals sign; a negative X would otherwise be read
as an option. Then check the result with
`python3 <skill>/scripts/ashlar_place.py plan <phase file>`.

## Recording

List every module in `plan.toon` `modules`, every instance in `placements`, and
both in the project's registry entry (`registry.md`), so the build can be
extended or repaired later.
````

- [ ] **Step 10: Create `skills/exec-ashlar/reference/registry.md`**

````markdown
# Project state and registry

All project files live under `.minecraft-builder/` in the workspace root, the
folder the client was started in. Start Minecraft sessions from the same folder
so there is one history.

```text
.minecraft-builder/
  registry.json
  <project>/
    requirements.md     interview answers (design skill)
    survey.md           site survey (exec-ashlar survey mode)
    research.md         research notes, with research.toon (survey-research)
    floorplan.txt …     blueprints, in the design skill's own formats
    plan.toon           the plan (plan-format.md)
    phases/             one mc_build arguments file per phase
    modules/            module files (modules.md)
    build-log.md        what was placed, snapshot ids, warnings, checks
    placer.log          JSON reports from the placer
```

## registry.json

```json
{
  "version": 1,
  "projects": {
    "oakhollow": {
      "skill": "design-village",
      "world": "world",
      "anchor": [120, 64, -340],
      "bbox": {"from": [100, 58, -362], "to": [162, 92, -298]},
      "status": "planned",
      "entity_tag": "ashlar.oakhollow",
      "modules": ["small-house-a"],
      "phases": [
        {"id": 1, "name": "site-prep", "snapshots": ["snap-20261117-210400-ab12"],
         "cells": 18200, "placed_at": "2026-11-17T21:04:00Z"}
      ],
      "commands_run": ["summon minecraft:villager 121 65 -333 {Tags:[\"ashlar\",\"ashlar.oakhollow\"]}"],
      "citations": [],
      "updated": "2026-11-17T21:30:00Z"
    }
  }
}
```

- `status` goes `planned` → `building` → `built`, or `rolled-back`.
- Write the entry when the plan is written (`planned`), after every phase
  (append the phase with its snapshot ids), and at the end.
- `citations` holds the sources for replicas, so the build can be checked
  against them.
- If the file does not exist, create it as `{"version": 1, "projects": {}}`.
- Never store server addresses or tokens.
````

- [ ] **Step 11: Create `skills/exec-ashlar/reference/clients.md`**

````markdown
# Client-specific tools

Every step in these skills works with Ashlar's tools, a shell and file access.
Where a client has a better tool, skills name it on a labelled line:

```markdown
- Claude Code: use `AskUserQuestion` for the multiple-choice questions.
- Codex: use `request_user_input` for them if it is listed among your tools.
- Otherwise: ask them in plain text.
```

Follow the shared text plus your own client's line. If your client's tool is
missing, use the `Otherwise:` line.

| Capability | Claude Code | Codex | Otherwise |
| --- | --- | --- | --- |
| Structured interview questions | `AskUserQuestion` | `request_user_input`, if it is listed | plain-text questions |
| Viewing offline PNGs (voxel renders) | `Read` on the file | `view_image` | report the numbers from `mc_inspect` and ask the user to open the file |
| Web research (`survey-research`) | `WebSearch`, `WebFetch` | its web search tool, if enabled; `trafilatura -u <url>` in the shell | `trafilatura -u <url>` |
| Tracking a long build | the task or todo tool | `update_plan` | a checklist in `build-log.md` |
| Finding a skill's folder for scripts | `${CLAUDE_SKILL_DIR}` | the folder holding the skill's `SKILL.md` | the folder holding the skill's `SKILL.md` |
| Handing off to a skill | the Skill tool, or `/exec-ashlar` | `$exec-ashlar`, or open its `SKILL.md` | open its `SKILL.md` |

Images from Ashlar's `mc_render` and `mc_survey` arrive as tool results in both
clients, so they need no special handling.

## Frontmatter

- Claude Code uses `model`, `effort` and `allowed-tools`; Codex ignores them.
  `allowed-tools` lists only the read-only Ashlar tools
  (`mcp__ashlar__mc_status`, `mcp__ashlar__mc_players`,
  `mcp__ashlar__mc_survey`, `mcp__ashlar__mc_render`,
  `mcp__ashlar__mc_inspect`), never `mc_build`, `mc_snapshot`, `mc_restore` or
  `mc_command`.
- Codex shows `metadata.short-description` in its skill list; Claude Code
  ignores it.
- Tool names in shared text have no client prefix: `mc_build`, not
  `mcp__ashlar__mc_build`.
````

- [ ] **Step 12: Run the checks**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar && node scripts/validate-plugin.mjs`
Expected: `3 passed` and `✓ plugin, marketplace, skills, and agents are valid`

- [ ] **Step 13: Commit**

```bash
git add skills/exec-ashlar/SKILL.md skills/exec-ashlar/reference
git commit -F - <<'MSG'
feat(exec-ashlar): add the executor skill and its reference library

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/exec-ashlar/SKILL.md", "skills/exec-ashlar/reference/tools-and-limits.md", "skills/exec-ashlar/reference/survey.md", "skills/exec-ashlar/reference/plan-format.md", "skills/exec-ashlar/reference/execution.md", "skills/exec-ashlar/reference/verification.md", "skills/exec-ashlar/reference/commands.md", "skills/exec-ashlar/reference/modules.md", "skills/exec-ashlar/reference/registry.md", "skills/exec-ashlar/reference/clients.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k exec_ashlar && node scripts/validate-plugin.mjs", "acceptanceCriteria": ["files match the plan text", "static checks for exec_ashlar pass", "upstream validator passes"], "modelTier": "standard"}
```

---

## Task 6: Vendor the voxel toolkit into `design-monument`

**Goal:** Copy Chapman's voxel toolkit (without its Fabric placer and rail checks) into the `design-monument` skill with its MIT notice and an Ashlar-oriented README, and prove it renders and produces fills the placer accepts.

**Files:**
- Create: `skills/design-monument/tools/voxel/{__init__,model,palette,render,decompose}.py` (copies of `tools/voxel/…`)
- Create: `skills/design-monument/tools/voxel/LICENSE` (copy of the repo's `LICENSE`)
- Create: `skills/design-monument/tools/voxel/README.md`
- Test: `tests/ashlar/test_voxel_smoke.py`

**Acceptance Criteria:**
- [ ] The five Python files are byte-identical to `tools/voxel/`; `mcp_place.py` and `continuity.py` are not copied.
- [ ] The smoke test builds a tiny model, renders three non-empty PNGs, writes fills, and `ashlar_place.py plan` reports as many cells as the model's solid voxels.
- [ ] `pytest -k design_monument` reports no leftovers from the new README (other monument files are fixed in Task 13).

**Verify:** `uv run --no-project --with pytest --with numpy --with pillow pytest tests/ashlar/test_voxel_smoke.py -q` → `1 passed`

**Steps:**

- [ ] **Step 1: Write the failing test** in `tests/ashlar/test_voxel_smoke.py`

```python
"""Smoke test for the vendored voxel toolkit plus the placer's plan command."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("PIL")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills" / "design-monument" / "tools"))
PLACER = REPO / "skills" / "exec-ashlar" / "scripts" / "ashlar_place.py"


def test_tiny_model_renders_and_plans(tmp_path):
    from voxel import Palette, VoxelModel, render_views, write_fills_json

    palette = Palette.building()
    model = VoxelModel(nx=6, ny=4, nz=5, palette=palette)
    model.box((0, 0, 0), (5, 0, 4), palette.code("stone"))
    model.box((1, 1, 1), (4, 3, 3), palette.code("oak_planks"))
    paths = render_views(model, str(tmp_path / "tiny"))
    assert len(paths) == 3 and all(Path(p).stat().st_size > 0 for p in paths)
    fills = tmp_path / "tiny_fills.json"
    summary = write_fills_json(model, str(fills), origin=(100, 64, 100))
    assert summary["fills"] >= 2
    proc = subprocess.run([sys.executable, str(PLACER), "plan", str(fills)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["cells"] == summary["solid_voxels"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --no-project --with pytest --with numpy --with pillow pytest tests/ashlar/test_voxel_smoke.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'voxel'`

- [ ] **Step 3: Copy the toolkit and the license**

```bash
mkdir -p skills/design-monument/tools/voxel
cp tools/voxel/__init__.py tools/voxel/model.py tools/voxel/palette.py tools/voxel/render.py tools/voxel/decompose.py skills/design-monument/tools/voxel/
cp LICENSE skills/design-monument/tools/voxel/LICENSE
for f in __init__ model palette render decompose; do cmp "tools/voxel/$f.py" "skills/design-monument/tools/voxel/$f.py"; done
```

Expected: no output from `cmp` (identical files).

- [ ] **Step 4: Create `skills/design-monument/tools/voxel/README.md`**

````markdown
# voxel: render-verify toolkit

Copied from Chapman's `minecraft-java-fabric-claude-plugin` (`tools/voxel`,
Release 1.2.0, MIT; see `LICENSE`), without its Fabric placer and rail checks.
The fills it writes go to the Ashlar placer in the `exec-ashlar` skill.

Author a form as a parametric numpy model, render it to PNGs you can look at,
iterate against references, then decompose it into world fills.

## Running

numpy and Pillow come from `uv`, so nothing is installed into the global
Python. From the workspace root:

```bash
uv run --no-project --with numpy --with pillow python my_model.py
```

In the script, put this folder's parent on `sys.path`, where `<design-monument>`
is the `design-monument` skill's folder:

```python
import sys
sys.path.insert(0, "<design-monument>/tools")
from voxel import Palette, VoxelModel, render_views, write_fills_json
```

## API

| Name | Does |
| --- | --- |
| `Palette.building()` | Starter palette: the 16 concretes, stone, wood, glass, glow, metals, the copper series; `add(id, rgb)` adds more; `code("stone")` gives a block's code |
| `VoxelModel(nx, ny, nz, palette)` | Empty grid (x = length, y = height, z = width) |
| `fx`, `fy`, `fz` | A fraction of an extent → an index, so forms are defined by ratios |
| `box`, `ellipsoid`, `cylinder`, `line3d` | Primitives |
| `fill_where`, `replace`, `clear`, `mirror_x` | Edits |
| `counts`, `solid_count`, `save_npy`, `load_npy` | Inspection and persistence |
| `render_views(model, prefix)` | Writes `<prefix>_iso.png`, `<prefix>_side.png`, `<prefix>_front.png` and returns the paths |
| `write_fills_json(model, path, origin)` | Greedy box decomposition (boxes up to 32,000 blocks) into `[{"from", "to", "block"}]` in world coordinates; returns a summary with `fills`, `solid_voxels`, `per_block`, `bbox` |

## Placing

`<exec-ashlar>` is the `exec-ashlar` skill's folder, a sibling of
`design-monument`:

```bash
python3 <exec-ashlar>/scripts/ashlar_place.py plan fills.json
python3 <exec-ashlar>/scripts/ashlar_place.py place fills.json --snapshot --label "<project> figure"
```
````

- [ ] **Step 5: Run the smoke test**

Run: `uv run --no-project --with pytest --with numpy --with pillow pytest tests/ashlar/test_voxel_smoke.py -q`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add skills/design-monument/tools tests/ashlar/test_voxel_smoke.py
git commit -F - <<'MSG'
feat(design-monument): vendor the voxel toolkit for Ashlar placement

Copied from tools/voxel (MIT) without mcp_place.py and continuity.py;
fills go to the exec-ashlar placer.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-monument/tools/voxel/__init__.py", "skills/design-monument/tools/voxel/model.py", "skills/design-monument/tools/voxel/palette.py", "skills/design-monument/tools/voxel/render.py", "skills/design-monument/tools/voxel/decompose.py", "skills/design-monument/tools/voxel/LICENSE", "skills/design-monument/tools/voxel/README.md", "tests/ashlar/test_voxel_smoke.py"], "verifyCommand": "uv run --no-project --with pytest --with numpy --with pillow pytest tests/ashlar/test_voxel_smoke.py -q", "acceptanceCriteria": ["five toolkit files identical to tools/voxel", "smoke test renders and plans", "README has no Chapman leftovers"], "modelTier": "mechanical"}
```

---

## Task 7: `survey-research` with labelled search and fetch tools

**Goal:** Make `survey-research` usable from both clients: its description and output note no longer name Chapman's pipeline, and its tool-order section uses labelled Claude Code / Codex lines with fallbacks.

**Files:**
- Modify: `skills/survey-research/SKILL.md` (description lines 3–8; line 83; the `### Tool order` section, lines 38–63)

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k survey_research` passes.
- [ ] The research method, output files (`research.md`, `research.toon`) and everything outside the three edits are unchanged.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k survey_research` → `3 passed`

**Steps:**

- [ ] **Step 1: Run the check to see it fail**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k survey_research`
Expected: FAIL (`exec-plan`, `exec-blueprint`, unlabelled `WebFetch`/`WebSearch`)

- [ ] **Step 2: Edit the description.** In the frontmatter `description`, replace:

```text
build request references a real or historical thing and the exec-plan or
  exec-blueprint skill needs accurate proportions, layouts, materials, or
  details. Part of the minecraft-builder workflow.
```

with:

```text
build request references a real or historical thing and a design skill
  needs accurate proportions, layouts, materials, or details. Used by the
  design skills before they build through Ashlar.
```

- [ ] **Step 3: Edit the output note.** Replace "numbers the `exec-plan` and `exec-blueprint` skills consume directly" with "numbers the design skills consume directly".

- [ ] **Step 4: Replace the whole `### Tool order — extract out-of-context, don't dump pages in` section** (from that heading up to, not including, `## Translate to Minecraft`) with:

```markdown
### Tool order — extract out-of-context, don't dump pages in

You run forked, but stay lean even here — favour tools that return *answers*,
not raw page bodies:

1. **Pointed extraction first, for every fact you need.** Ask one page a narrow
   question — *"From this page, give the overall length, nave height, tower
   height, and primary façade materials of Notre-Dame de Paris, with the
   figures and their source."* — so whole articles stay out of your context.
   - Claude Code: use `WebFetch` with that question as the prompt; only the
     answer comes back. It is lossy by design — if it answers "not mentioned",
     re-ask before giving up.
   - Codex: run `trafilatura -u <url>` in the shell and filter it
     (`| grep -iE '<terms>'` or `| head -c 4000`) so only the relevant lines
     come back.
   - Otherwise: run `trafilatura -u <url>` with a filter, as above.
2. **Exact numbers from structured endpoints.** For hard dimensions, use a
   structured source — the Wikipedia REST summary
   (`https://en.wikipedia.org/api/rest_v1/page/summary/<Title>`) or a Wikidata
   entity (`https://www.wikidata.org/wiki/Special:EntityData/<Qid>.json`,
   properties P2048/P2043/P2046 for height/length/area). These are tiny and
   authoritative — ideal for the `research.toon` numbers.
   - Claude Code: point `WebFetch` at the endpoint and ask for the values.
   - Codex: `curl -s <endpoint>` piped to `python3 -c` to print only the
     properties you need.
   - Otherwise: `curl -s <endpoint>`, as for Codex.
3. **Search for discovery** (finding the right pages and titles). Search by
   exact name plus "dimensions" or "height (architecture)", prefer the
   Wikipedia or official page, then extract as in step 1.
   - Claude Code: use `WebSearch`. It is US-only, so non-US landmarks may rank
     poorly.
   - Codex: use your web search tool if it is enabled.
   - Otherwise: start from the Wikipedia REST summary, or ask the user for a
     source.
4. **Raw-page fetch is a last resort.** Only pull a full page into context when
   extraction genuinely cannot get what you need (an anti-bot wall, an oddly
   structured source); otherwise note the gap rather than dumping the page.
```

- [ ] **Step 5: Run the check**

Run: `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k survey_research`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add skills/survey-research/SKILL.md
git commit -F - <<'MSG'
feat(survey-research): label client-specific search and fetch tools

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/survey-research/SKILL.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k survey_research", "acceptanceCriteria": ["static checks pass for survey_research", "only the description, output note and tool-order section change"], "modelTier": "mechanical"}
```

---
## Tasks 8–13: shared instructions for the design-skill edits

Each of Tasks 8–13 edits one design skill. For every task:

- Line numbers refer to the files at `b4bea4a` (Chapman Release 1.2.0). Read each file before editing, and edit by matching text, not by line number.
- "Replace X with Y" blocks give exact text. Catalogue entries (C2…C27) are in the Edit catalogue above.
- When a reference line is part of a longer sentence or list item, change only the Chapman-specific words and keep the rest of the sentence and its meaning. Design knowledge (styles, rooms, layouts, catalogs, techniques, Cape Aurelia lessons) stays unchanged.
- Step order: run the skill's static check to see it fail; make the `SKILL.md` edits; make the reference edits; run the check to see it pass; review `git diff` to confirm only the intended hunks changed; commit.

---

## Task 8: Adapt `design-building`

**Goal:** `design-building` designs named buildings exactly as before and hands surveys and approved plans to `exec-ashlar`, with no Chapman pipeline references.

**Files:**
- Modify: `skills/design-building/SKILL.md`
- Modify: `skills/design-building/reference/blueprints.md`, `interiors.md`, `interview.md`, `modules.md`, `techniques.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_building` passes.
- [ ] `git diff --stat` shows changes only under `skills/design-building/`, and every hunk is one of the edits listed below.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_building` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL listing `exec-worker`, `CLAUDE_PLUGIN_ROOT`, `mcb:` and others.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace:

```text
  palace, skyscraper, fortress, monument). Part of the minecraft-builder
  workflow.
```

with:

```text
  palace, skyscraper, fortress, monument). Builds through Ashlar with the
  exec-ashlar skill.
```

Edit 2. Replace `plan. You do not place blocks — `exec-worker` does.` with:

```markdown
plan. You place no blocks while designing; after the user approves the plan,
the `exec-ashlar` skill builds it.
```

Edit 3. Replace the `## Connection` section body with C2.

Edit 4. Replace `(module reuse, block volume, structure count, which leaves the orchestrator sequences):` with `(module reuse, block volume, and how many modules and phases the build needs):`

Edit 5. Replace:

```text
spire. Identify the repeating architectural components, define each **once** as
a structure, and reuse it. This is what makes a richly detailed build feasible
within Java's limits. See `reference/modules.md`.
```

with:

```markdown
spire. Identify the repeating architectural components, define each **once** as
a module, and stamp it wherever it repeats. This is what makes a richly
detailed build feasible. See `reference/modules.md`.
```

Edit 6. Replace the paragraph that starts `For a **real-world** replica, the orchestrator runs the `survey-research` leaf` (through `over fan wikis.`) with:

```markdown
For a **real-world** replica, use the `survey-research` skill first; require at
least **two reputable sources**. Capture verified dimensions, signature
features, materials, and era. Record the citations in the project's entry in
`.minecraft-builder/registry.json` so the finished build can be checked against
them. Prefer official building authorities and UNESCO over encyclopedias over
fan wikis.
```

Edit 7. Replace process step 3 with:

```markdown
3. **Research** — use the `survey-research` skill's findings for real-world and
   canonical-fictional targets; pull style data from `reference/styles.md` or
   `reference/fictional.md`.
```

Edit 8. Replace process step 4 with:

```markdown
4. **Survey the site** — use the `exec-ashlar` skill (`survey <project>`); if
   the site needs shaping (a hilltop, an island, a moat), note a `pre-build
   terraform` step (see Hand-off).
```

Edit 9. Replace the first paragraph of process step 6 and the `quality_contract` line under it:

```text
6. **Resolve to a plan** — write pre-tiled phases and steps into `plan.toon`;
   split any element over 64×384×64 into multiple named structures (canonical
   colon form `mcb:<project>_<element>`).

   **Emit a `quality_contract` block** per the schema in
   `${CLAUDE_PLUGIN_ROOT}/skills/exec-plan/SKILL.md`.
```

with:

```markdown
6. **Resolve to a plan** — write `plan.toon`, its phase files and its module
   files per the `exec-ashlar` skill's `reference/plan-format.md`
   (`../exec-ashlar/reference/plan-format.md`), with every repeated element
   defined once in `modules/`.

   **Emit a `quality_contract` block** per that same plan format.
```

Keep the bullet list of contract rows that follows.

Edit 10. Replace process step 8 with:

```markdown
8. **Hand off** — write the plan, register the building in
   `.minecraft-builder/registry.json`, and follow the Hand-off section below.
```

Edit 11. Replace the paragraph `For volume limits, … command-budget.md**.` with C8.

Edit 12. Replace the hard rule `- **Never place blocks** — you produce a plan; `exec-worker` executes it.` with C5.

Edit 13. Replace:

```text
- **Pre-tile fills** to ≤32,768 blocks; **split** any element over 64×384×64
  into multiple `mcb:<project>_<element>` structures.
```

with:

```markdown
- **Stay within Ashlar's limits** (`../exec-ashlar/reference/tools-and-limits.md`)
  and define every repeated element once as a module.
```

Edit 14. Replace the whole `## Return to the orchestrator` section with:

```markdown
## Hand-off

State the target, the adaptation chosen, the scale, the interior depth, the
signature features and the module manifest, and confirm `plan.toon`, its phase
files and its module files are written. No separate coordinator runs the next
steps in this setup, so you sequence them:

1. **Site preparation**, if the site needs it: use the `terrain-shape` skill if
   it is installed; otherwise add a `site-prep` phase (clearing, levelling,
   pads, filling holes, soft-edged terraces) and tell the user if the site
   needs more than that.
2. **Build**: use the `exec-ashlar` skill (`build <project>`). It runs the
   approval gate, the phased build and the verification, including the
   recorded signatures and citations.
```

- [ ] **Step 3: Edit the references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/blueprints.md` | 60 | C13: "again for the `exec-reflect` afterwards" → "again with the `exec-ashlar` skill's verification after the build" |
| `reference/blueprints.md` | 76–77 | C13: replace the fill/structure caps with "a single call over Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`)" |
| `reference/interiors.md` | 66–90 | C15 for the sign example (keep its SNBT as the `data merge block` example); "Verify with `block_entity_get_nbt`" → C16 verify wording |
| `reference/interiors.md` | 86–126 | C16 for the banner (`patterns`), lectern (`Book`), decorated pot (`sherds`) and player head (`profile`) examples |
| `reference/interiors.md` | 133–145 | C17: item frames via the allowlisted `summon minecraft:glow_item_frame <x> <y> <z> {Facing:1,…,Tags:["ashlar","ashlar.<project>"]}` (or `data merge entity` after the fact) |
| `reference/interiors.md` | 146–166 | C18: `inventory_set_slot`/`player_give_item` with components → `item replace block … with minecraft:<item>[<components>] <count>`; the `itemstack_describe`/`server_get_status` round-trip → C18 verify wording |
| `reference/interiors.md` | 175–190 | C18: loot tables → `data merge block <x> <y> <z> {LootTable:"minecraft:chests/stronghold_library"}` |
| `reference/interview.md` | 5 | C12 |
| `reference/interview.md` | 63 | C11: "Run the `exec-ashlar` skill's site survey (`survey <project>`) for site context" |
| `reference/modules.md` | 5 | Remove "within Java's 32,768-block fill limit" and keep the sentence grammatical |
| `reference/modules.md` | 25–35 | C19 (steps 2, 3 and 5; keep steps 1 and 4 and any variation advice) |
| `reference/modules.md` | 75 | Replace the 32,768 tiling note with "within Ashlar's limits (the placer pages larger phase files)" and drop the `exec-worker` mention |
| `reference/techniques.md` | 83–88 | Replace the paragraph with the text below |

New paragraph for `reference/techniques.md` lines 83–88:

```markdown
Compose with `mc_build`: fills (modes `replace`, `keep`, `outline`, `hollow`,
`walls`, with an optional `filter`), single blocks with exact states, sign text
and lettering. Stamp a module (`modules.md`) for anything repeated. There is no
WorldEdit in this setup. Block-entity NBT goes through the allowlisted
`data merge block` (`../exec-ashlar/reference/commands.md`). Keep each call
within Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`).
```

- [ ] **Step 4: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 5: Review the diff.** `git diff --stat` lists only `skills/design-building/` files; `git diff` shows only the edits above.

- [ ] **Step 6: Commit**

```bash
git add skills/design-building
git commit -F - <<'MSG'
feat(design-building): build through exec-ashlar instead of Chapman's pipeline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-building/SKILL.md", "skills/design-building/reference/blueprints.md", "skills/design-building/reference/interiors.md", "skills/design-building/reference/interview.md", "skills/design-building/reference/modules.md", "skills/design-building/reference/techniques.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_building", "acceptanceCriteria": ["static checks pass for design_building", "diff limited to design-building and the listed edits"], "modelTier": "standard"}
```

---

## Task 9: Adapt `design-house`

**Goal:** `design-house` keeps its interview, room catalog and blueprints, and hands surveys and approved plans to `exec-ashlar`, with Ashlar's placement behaviour reflected in its redstone and NBT guidance.

**Files:**
- Modify: `skills/design-house/SKILL.md`
- Modify: `skills/design-house/reference/blueprints.md`, `environments.md`, `interiors.md`, `interview.md`, `layouts.md`, `utilities.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_house` passes.
- [ ] The `AskUserQuestion` instruction appears only as labelled lines with an `Otherwise:` fallback.
- [ ] `git diff --stat` shows changes only under `skills/design-house/`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_house` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace `  base, or similar. Part of the minecraft-builder workflow.` with `  base, or similar. Builds through Ashlar with the exec-ashlar skill.`

Edit 2. Replace `and write a fully-resolved plan. You do not place blocks — the `exec-worker` does.` with:

```markdown
and write a fully-resolved plan. You place no blocks while designing; after the
user approves the plan, the `exec-ashlar` skill builds it.
```

Edit 3. Replace:

```text
Do **not** use it for the following — return to the orchestrator, which routes
the request to the right leaf:
```

with:

```markdown
Do **not** use it for the following — say so, and use the right skill instead:
```

Edit 4. Replace the `## Connection` section body with C2.

Edit 5. Replace the `## Inputs` list with:

```markdown
- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`).
  Its `survey.md` gives terrain slope, water, existing builds, threats (deep
  dark, ravine, lava), player coordinates, the buildable area and the biome
  when read. Use it to pre-fill the site and filter style suggestions.
- **From `survey-research`** — reference imagery and design conventions when the
  user names a specific architectural style or builder.
- **From the user** — everything in the adaptive interview.
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), in case this base iterates on an
  existing build.
```

Edit 6. Replace process step 2 with:

```markdown
2. **Interview, adaptively.** Run the question set from
   `reference/interview.md` sized to the tier (≈5 questions for a starter,
   up to ≈25 for a megabase). Ask in small grouped batches, not one at a time.
   Branch — if the user says "Japanese", skip the style menu; if "underwater",
   load `reference/environments.md` and ask the conduit follow-ups. Record
   answers in `.minecraft-builder/<project>/requirements.md`.
   - Claude Code: use `AskUserQuestion` for the multiple-choice questions.
   - Codex: use `request_user_input` for them if it is listed among your tools.
   - Otherwise: ask them in plain text.
```

Edit 7. Replace the first paragraph of process step 6 and its `quality_contract` line:

```text
6. **Write the plan and return.** Once approved, write the fully-resolved
   build into `.minecraft-builder/<project>/plan.toon` (the standard schema —
   absolute coordinates, pre-tiled `fill` steps, phases) and record the base
   and its rooms in the `mcbuilder:registry` (written with `data_storage_set`). Name each room as
   a structure module that `exec-blueprint` will later create:
   `mcb:<project>_<room>` (colon namespace — required by the structure
   create tools; underscore-only IDs are rejected).

   **Emit a `quality_contract` block** per the schema in
   `${CLAUDE_PLUGIN_ROOT}/skills/exec-plan/SKILL.md`.
```

with:

```markdown
6. **Write the plan and hand off.** Once approved, write the fully-resolved
   build as `.minecraft-builder/<project>/plan.toon` plus its phase and module
   files, per the `exec-ashlar` skill's `reference/plan-format.md`
   (`../exec-ashlar/reference/plan-format.md`): absolute coordinates, phases,
   and every repeated room or furniture set defined once in `modules/` and
   stamped. Record the base and its rooms in `.minecraft-builder/registry.json`.

   **Emit a `quality_contract` block** per that same plan format.
```

Keep the contract bullet list. Then replace `colour walls. The contract is `exec-inspect`'s hook to catch them` and the line after it (`automatically.`) with:

```markdown
colour walls. The `exec-ashlar` skill's verification checks every row after
the build.
```

Edit 8. Replace the paragraph `For volume limits, … command-budget.md`**.` with C8.

Edit 9. Replace the hard rules from `- **Never place blocks.**` through the `- **Pre-tile fills** …` bullet (four bullets) with:

```markdown
- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it.
- **Prepare the site first.** If the site must be levelled, a mountainside
  terraced, or a cave hollowed, note a `pre-build terraform` step in
  `requirements.md`; Hand-off says who does it.
- **Keep rooms modular.** Keep useful room volume at or under ~60×60×60 and
  split larger rooms along a wall, so each room stays one module.
- **Resolve everything to absolute coordinates** in the phase files, within
  Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`).
```

Edit 10. Replace the redstone hard rule (`- **Use Java-correct redstone.** …` through `to `system-redstone`.`) with:

```markdown
- **Use Java-correct redstone.** Quasi-connectivity exists on Java; observers
  output a 1-redstone-tick pulse. Ashlar places blocks without block updates,
  so circuits do not start on their own: include a start lever or button and
  tell the user to use it. See `reference/utilities.md` for Java-verified
  designs. For anything more complex, use the `system-redstone` skill if it is
  installed; otherwise say what is out of reach.
```

Edit 11. Replace the whole `## Return to the orchestrator` section with:

```markdown
## Hand-off

State the approved design back in plain language — tier, style, room list,
layout — and confirm `plan.toon` and its phase and module files are written. No
separate coordinator runs the next steps in this setup, so you sequence them:

1. **Site preparation**, if needed: use the `terrain-shape` skill if it is
   installed; otherwise add a `site-prep` phase (clearing, levelling, pads,
   filling holes, soft-edged terraces) and tell the user if the site needs
   more than that.
2. **Build**: use the `exec-ashlar` skill (`build <project>`).

The blueprints and the registry entry stay for later iteration.
```

- [ ] **Step 3: Edit the references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/blueprints.md` | 92 | C13: "the actual placement is still a `exec-worker` job" → "the actual placement is the `exec-ashlar` skill's job" |
| `reference/environments.md` | after the intro paragraph (line 4) | Add the paragraph below |
| `reference/interiors.md` | 53 | C20 |
| `reference/interiors.md` | 63–69 | C14 for the tree-growth sentence; C27 for the weathering reference |
| `reference/interiors.md` | 76–90 | C15 for the sign example; C16 verify wording |
| `reference/interiors.md` | 94–120 | C16 for the lectern (`Book`), pot (`sherds`) and head (`profile`) examples |
| `reference/interiors.md` | 122–139 | C18: `inventory_set_slot` with components → `item replace block`; the round-trip → C18 verify wording |
| `reference/interview.md` | 5–6 | C12; "the survey-site" → "the site survey" |
| `reference/interview.md` | 14 | C11: "the survey-site. Surface anything unusual the survey-site flagged" → "the site survey. Surface anything unusual the survey flagged" |
| `reference/layouts.md` | 55 | C11: "The `survey-site` site and `environments.md`" → "The site survey and `environments.md`" |
| `reference/utilities.md` | 16 (whole bullet) | Replace the bullet that begins "**`block_set_state` placement notifies neighbours**" with the bullet below |
| `reference/utilities.md` | 81 | "give exec-plan a footprint" → "give the plan a footprint" |
| `reference/utilities.md` | 87–88 | "becomes rooms and steps in `plan.toon`. Give the `exec-plan`/`exec-worker` a concrete block list" → "becomes rooms and phases in `plan.toon`. Give each one a concrete block list" |
| `reference/utilities.md` | 97–105 | C15 for the sign label example |
| `reference/utilities.md` | 111–123 | C18: loot table → `data merge block <x> <y> <z> {LootTable:"minecraft:chests/village/village_weaponsmith"}` |
| `reference/utilities.md` | 135–151 | C18: tool chest items → `item replace block`; "(`server_get_status`) before finalising the SNBT in `plan.toon`" → "(`mc_status` reports it) before finalising the item syntax in `plan.toon`" |

New paragraph for `reference/environments.md`:

```markdown
Ashlar builds only in worlds listed in its `world.allowed-worlds`. Before
designing a Nether or End base, have the `exec-ashlar` skill check that the
world is allowed (its survey, step 7); if it is not, say the base cannot be
built there.
```

New bullet for `reference/utilities.md` line 16:

```markdown
- **Ashlar places blocks without block updates.** Circuits, clocks and
  observers do not start on their own after placement. Give every contraption
  a start lever or button, and tell the user to use it once the build is done.
```

- [ ] **Step 4: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 5: Review the diff.** Only `skills/design-house/` files, only the edits above.

- [ ] **Step 6: Commit**

```bash
git add skills/design-house
git commit -F - <<'MSG'
feat(design-house): build through exec-ashlar instead of Chapman's pipeline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-house/SKILL.md", "skills/design-house/reference/blueprints.md", "skills/design-house/reference/environments.md", "skills/design-house/reference/interiors.md", "skills/design-house/reference/interview.md", "skills/design-house/reference/layouts.md", "skills/design-house/reference/utilities.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_house", "acceptanceCriteria": ["static checks pass for design_house", "AskUserQuestion only on labelled lines with Otherwise fallback", "diff limited to design-house"], "modelTier": "standard"}
```

---

## Task 10: Adapt `design-city`

**Goal:** `design-city` plans districts, streets, vernacular modules and landmark records as before, runs `design-building` and `design-village` itself for flagged elements, and builds district by district through `exec-ashlar`.

**Files:**
- Modify: `skills/design-city/SKILL.md`
- Modify: `skills/design-city/reference/blueprints.md`, `infrastructure.md`, `interview.md`, `vernacular.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_city` passes.
- [ ] `git diff --stat` shows changes only under `skills/design-city/`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_city` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace:

```text
  or a recognizable metropolitan skyline. Part of the minecraft-builder
  workflow.
```

with:

```text
  or a recognizable metropolitan skyline. Builds through Ashlar with the
  exec-ashlar skill.
```

Edit 2. Replace:

```text
themselves are designed by `design-building` — you flag them for the
orchestrator to route. Your job is the design: interview the user, propose
```

with:

```markdown
themselves are designed by `design-building` — you flag them and run that skill
for each. Your job is the design: interview the user, propose
```

Edit 3. Replace the `## Connection` section body with C2.

Edit 4. In core principle 2, replace `Define each once as a structure, stamp it along block edges` with `Define each once as a module, stamp it along block edges`.

Edit 5. Replace core principle 3 with:

```markdown
3. **Flag landmarks for `design-building`.** Every *named* building — the
   cathedral, the palace, the famous tower — you flag in a landmark record
   (see "Landmark records" below) and design with the `design-building` skill.
   You never design a landmark's interior yourself.
```

Edit 6. Replace the two bullets under `### Java-exclusive: district signage and biome-matched palette` with:

```markdown
- **District signage and wayfinding** — `text_display` entities, summoned with
  the allowlisted `summon` command (`../exec-ashlar/reference/commands.md`),
  give floating district names, street signs and directional arrows at any
  scale and colour. Plain sign text goes on standing, wall or hanging signs
  through `mc_build`'s `sign` object (`waxed: true` locks it); styled JSON text
  uses the allowlisted `data merge block`. List every command in the plan's
  `commands` table.
- **Biome-matched vernacular palette** — read the site's biome during the
  survey (the `exec-ashlar` skill tests candidates with the read-only
  `execute if biome`, or infers it from surface materials). Use it to pick roof
  pitch (steeper in cold/snowy biomes), choose the primary stone palette (warm
  sandstone in desert biomes, mossy variants in jungle/swamp biomes), select
  vegetation species, and match water-colour context, so the palette is
  grounded in the world, not guessed.
```

Edit 7. Replace the `## Inputs` list with:

```markdown
- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`):
  bounding box, biome when read, elevation, water, existing builds, nearest
  player.
- **From `survey-research`** — for a real-world or named-fictional city, a
  research dossier: signature silhouette, urban pattern, dimensions, palette,
  era. If it is missing for such a city, run the `survey-research` skill first;
  cite sources.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration.
```

Edit 8. In `## Scale and districting`, replace the first two bullets after "Then:" with:

```markdown
- **Decompose the city into districts of ≤256×256 blocks** — each district is
  its own set of phases, with its repeated buildings as modules
  (`modules/<district>-<element>.json`).
- **Keep each call within Ashlar's limits** — a 200×200 district's street
  paving alone is ~40,000 blocks, so large districts go through the placer in
  several pages.
```

Keep the Y-budget bullet. Replace the paragraph `For the full limit detail … command-budget.md`.` with C8.

Edit 9. Replace process step 3 with:

```markdown
3. **Research** — for real-world and named-fictional cities, use the
   `survey-research` dossier (run that skill if it is missing); pull patterns
   from `reference/cities.md`.
```

Edit 10. In process step 4, replace `(villager-capable —\n   flag it for the orchestrator to route to `design-village`)` with `(villager-capable — design it with the `design-village` skill)`.

Edit 11. Replace process step 7 with:

```markdown
7. **Flag landmarks** — emit a landmark record (below) for every named
   building; each one is designed with the `design-building` skill.
```

Edit 12. Replace the first paragraph of process step 10 and its `quality_contract` line:

```text
10. **Write the plan and hand off** — write `requirements.md` and `plan.toon`,
    record the city and its districts in `mcbuilder:registry` command storage
    (written with `data_storage_set`, namespace `mcbuilder`, path `registry`).
    Structure names follow the canonical colon form `mcb:<project>_<element>`.

    **Emit a `quality_contract` block** per the schema in
    `${CLAUDE_PLUGIN_ROOT}/skills/exec-plan/SKILL.md`.
```

with:

```markdown
10. **Write the plan and hand off** — write `requirements.md`, `plan.toon`, its
    phase files and module files per the `exec-ashlar` skill's
    `reference/plan-format.md` (`../exec-ashlar/reference/plan-format.md`), and
    record the city and its districts in `.minecraft-builder/registry.json`.

    **Emit a `quality_contract` block** per that same plan format.
```

In the contract bullets that follow, replace `so `exec-inspect` can detect a broken edge` with `so the verification can detect a broken edge`.

Edit 13. In `## Landmark records`, replace `emit a TOON record so the orchestrator can route it\nto `design-building`:` with `emit a TOON record so it can be designed with the `design-building` skill:`, and replace the sentence after the example that begins `The orchestrator routes each record to `design-building`` with:

```markdown
Run the `design-building` skill for each record; it designs the landmark and
its modules. Reserve the `anchor` envelope in the district plan and continue
the urban fabric around it.
```

Edit 14. In `## Hard rules`: replace the never-place bullet with C5; replace `The orchestrator routes each.` with `Hand-off says who runs each.`; replace `- **Districts ≤256×256**, fills pre-tiled to ≤32,768 blocks, every element\n  within 64×384×64, the whole build within Y -64 to 320.` with:

```markdown
- **Districts ≤256×256**, every call within Ashlar's limits, the whole build
  within Y −64 to 319.
```

Edit 15. Replace the whole `## Return to the orchestrator` section with:

```markdown
## Hand-off

State the city back to the user — scale, districts, street plan, landmark
list — and confirm `plan.toon` is written. No separate coordinator runs the
next steps in this setup, so you sequence them, district by district:

1. **Site preparation**: use the `terrain-shape` skill if it is installed;
   otherwise add `site-prep` phases (clearing, levelling, pads, filling holes,
   soft-edged terraces) and tell the user what is beyond them.
2. **Landmarks**: run the `design-building` skill for each landmark record.
3. **Functional quarters**: run the `design-village` skill for each one.
4. **Build**: use the `exec-ashlar` skill (`build <project>`), one district at a
   time, verifying each before starting the next.
```

- [ ] **Step 3: Edit the references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/blueprints.md` | 47 | C13: "have the `exec-inspect` and `exec-reflect` re-check it" → "re-check it with the `exec-ashlar` skill's verification after the build" |
| `reference/blueprints.md` | 68 | C13: "district fill over 32,768, a structure over 64×384×64" → "a single call over Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`)" |
| `reference/infrastructure.md` | 60–63 | C14 |
| `reference/infrastructure.md` | 76 | "prepares the site before the `exec-worker` places any block" → "prepares the site (if it is installed) before any block is placed" |
| `reference/interview.md` | 4–5 | C12; "the survey-site already settled" → "the site survey already settled" |
| `reference/interview.md` | 18 | C11: "the survey-site" → "the site survey" |
| `reference/vernacular.md` | 13–20 | C19 (module names `modules/vern-<type>.json`; keep the variant advice) |

- [ ] **Step 4: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 5: Review the diff.** Only `skills/design-city/` files, only the edits above.

- [ ] **Step 6: Commit**

```bash
git add skills/design-city
git commit -F - <<'MSG'
feat(design-city): build through exec-ashlar instead of Chapman's pipeline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-city/SKILL.md", "skills/design-city/reference/blueprints.md", "skills/design-city/reference/infrastructure.md", "skills/design-city/reference/interview.md", "skills/design-city/reference/vernacular.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_city", "acceptanceCriteria": ["static checks pass for design_city", "diff limited to design-city"], "modelTier": "standard"}
```

---

## Task 11: Adapt `design-village`

**Goal:** `design-village` keeps its functional-village rules and layouts, stamps building templates as modules, and expresses population as allowlisted `summon` commands that `exec-ashlar` runs and verifies.

**Files:**
- Modify: `skills/design-village/SKILL.md`
- Modify: `skills/design-village/reference/buildings.md`, `interview.md`, `mechanics.md`, `population.md`, `styles.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_village` passes.
- [ ] Every summon example in `population.md` carries `Tags:["ashlar","ashlar.<project>"]`, and villagers that are read back also carry a per-entity tag.
- [ ] `git diff --stat` shows changes only under `skills/design-village/`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_village` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace:

```text
  village, hamlet, town, settlement, or trading hub. Part of the
  minecraft-builder workflow.
```

with:

```text
  village, hamlet, town, settlement, or trading hub. Builds through Ashlar
  with the exec-ashlar skill.
```

Edit 2. Replace `resolved plan. You do not place blocks or spawn entities — the `exec-worker` does.` with:

```markdown
resolved plan. You place no blocks and spawn nothing while designing; after the
user approves the plan, the `exec-ashlar` skill builds it.
```

Edit 3. Replace:

```text
Use for a multi-building **settlement** of up to ~15 buildings. If the request
is really one of the following, return to the orchestrator and say so — the
orchestrator owns routing to the right leaf:
```

with:

```markdown
Use for a multi-building **settlement** of up to ~15 buildings. If the request
is really one of the following, say so and use the right skill instead:
```

and replace `  The orchestrator may route one functional residential quarter of a city back\n  to this skill.` with `  `design-city` may hand one functional residential quarter of a city back to\n  this skill.`

Edit 4. Replace the `## Connection` section body with C2.

Edit 5. Replace the `## Inputs` list with:

```markdown
- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`):
  terrain, water, existing builds, the biome when read, and the player's house
  position if one exists.
- **From `survey-research`** — references when the user names a specific style.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration.
```

Edit 6. Replace the Mode B bullet with:

```markdown
   - **Mode B** (a village building *is* the player's home) — note the
     bounding box and run the `design-house` skill for that building; treat as
     advanced.
```

Edit 7. Replace the first paragraph of process step 9 and its `quality_contract` line:

```text
9. **Write the plan and return.** Write `requirements.md` and `plan.toon`,
   record the village in `mcbuilder:registry` command storage (written with
   `data_storage_set`, namespace `mcbuilder`, path `registry`), and list the
   building templates and population for the rest of the pipeline. Structure
   names follow the canonical colon form `mcb:<project>_<element>`.

   **Emit a `quality_contract` block** per the schema in `exec-plan/SKILL.md`.
```

with:

```markdown
9. **Write the plan and hand off.** Write `requirements.md`, `plan.toon`, its
   phase files and the building templates as module files, per the
   `exec-ashlar` skill's `reference/plan-format.md`
   (`../exec-ashlar/reference/plan-format.md`). Record the village, its
   templates and its population in `.minecraft-builder/registry.json`.

   **Emit a `quality_contract` block** per that same plan format.
```

Edit 8. Replace the paragraph `For volume limits, … command-budget.md`**.` with C8.

Edit 9. Replace the whole `## The reuse model` section with:

```markdown
## The reuse model

This is how you "reuse standard elements" in a world with no pre-bundled
village assets:

1. Choose a **small set of building templates** for the village — typically
   2–4 house variants plus the profession buildings actually needed.
2. Define each template **once** as a module file,
   `modules/village-<piece>.json` (e.g. `modules/village-small-house-a.json`),
   in local coordinates (`../exec-ashlar/reference/modules.md`).
3. Add a `placements` row for every building the layout places, varying
   rotation and mirror; small palette tweaks become their own module variants.
   `stamp.py` turns the rows into phase files, so instances read as a real
   village — same vocabulary, not identical clones.
4. Record every template and instance in `.minecraft-builder/registry.json` so
   the village can be extended or repaired later.

Grow any trees in or around the village rather than placing or duplicating a
tree (see the `terrain-shape` skill if it is installed). Use the allowlisted
`place feature minecraft:<tree_type> <x> <y> <z>` console command, listed in
the plan and inside a snapshotted box, or place a sapling with `mc_build` and
let it grow. Buildings reuse; trees do not.
```

Edit 10. In `## Hard rules`: replace the first bullet with:

```markdown
- **Place no blocks and spawn nothing while designing** — after the user
  approves the plan, the `exec-ashlar` skill builds it.
```

Replace `- **Pre-tile fills** to ≤32,768 blocks; keep each building within 64×384×64.` with `- **Stay within Ashlar's limits** (`../exec-ashlar/reference/tools-and-limits.md`); keep each building one module.` Replace the site-prep bullet with:

```markdown
- **Prepare the site first** — note a `pre-build terraform` step in the plan if
  the site has slopes over ~2 blocks, needs leveling, or needs water work;
  Hand-off says who does it.
```

Edit 11. Replace the whole `## Return to the orchestrator` section with:

```markdown
## Hand-off

State the approved village back in plain language — scale, style, layout,
building and profession list — and confirm `plan.toon` is written. No separate
coordinator runs the next steps in this setup, so you sequence them:

1. **Site preparation**, if needed: use the `terrain-shape` skill if it is
   installed; otherwise add a `site-prep` phase (clearing, levelling, pads,
   filling holes, soft-edged terraces) and tell the user if the site needs
   more than that.
2. **Build**: use the `exec-ashlar` skill (`build <project>`). The buildings are
   stamped from the templates first; the population phase (villagers, then
   animals, then any iron golem — see `reference/population.md`) runs last as
   allowlisted `summon` commands.
3. **Check the village works**: `exec-ashlar`'s verification reads villager bed
   and job-site claims back with `data get entity` after a short wait.
```

- [ ] **Step 3: Edit the references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/buildings.md` | 22 | "placing with `block_set_state`" → "placing with `mc_build`" |
| `reference/buildings.md` | 85–98 | C18: loot table via `data merge block <x> <y> <z> {LootTable:"minecraft:chests/village/village_weaponsmith"}`; the two `inventory_set_slot` lines become `item replace block <x> <y> <z> container.0 with minecraft:iron_sword 1` and `item replace block <x> <y> <z> container.1 with minecraft:iron_ingot 5` |
| `reference/interview.md` | 5–6 | C12; "the survey-site" → "the site survey" |
| `reference/interview.md` | 14 | C11: "survey-site." → "site survey." |
| `reference/mechanics.md` | 84, 142, 156 | C17: "with `entity_summon`" → "with the allowlisted `summon` command" |
| `reference/population.md` | 10–11 | Replace the sentence with: "Population is expressed in `plan.toon` as `commands` rows: allowlisted `summon` commands (`../exec-ashlar/reference/commands.md`) in a final `commands` phase, after every bed, workstation and bell they depend on has been placed." |
| `reference/population.md` | 24, 41, 51, 53, 61 | C17: `entity_summon` → the allowlisted `summon` |
| `reference/population.md` | 31, 133 | C24: "The `exec-reflect` verifies claims" → "The `exec-ashlar` skill's verification checks claims"; "Hand the `exec-reflect` a check" → "Hand the `exec-ashlar` skill's verification a check" |
| `reference/population.md` | 67 and 108 | C17 for the villager and zombie examples; add a per-entity tag such as `ashlar.<project>.trader1` to the villager |
| `reference/population.md` | 88–89 | "with `server_get_status`, then … `entity_get_nbt`" → "with `mc_status`, then do a round-trip: summon the villager, read it back with the read-only `data get entity @e[tag=ashlar.<project>,tag=ashlar.<project>.trader1,limit=1] Offers`, and confirm the trades loaded correctly" |
| `reference/population.md` | 91 | "use `entity_set_nbt` with the" → "use the allowlisted `data merge entity @e[tag=ashlar.<project>,tag=ashlar.<project>.trader1,limit=1]` with the" |
| `reference/population.md` | 104 | "`entity_summon` (or `entity_set_nbt` on an existing mob)" → "The allowlisted `summon` (or `data merge entity` on an existing tagged mob)" |
| `reference/styles.md` | 54–58 | C14 |

- [ ] **Step 4: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 5: Review the diff.** Only `skills/design-village/` files, only the edits above.

- [ ] **Step 6: Commit**

```bash
git add skills/design-village
git commit -F - <<'MSG'
feat(design-village): build and populate through exec-ashlar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-village/SKILL.md", "skills/design-village/reference/buildings.md", "skills/design-village/reference/interview.md", "skills/design-village/reference/mechanics.md", "skills/design-village/reference/population.md", "skills/design-village/reference/styles.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_village", "acceptanceCriteria": ["static checks pass for design_village", "summon examples carry ashlar tags; read-back villagers carry a per-entity tag", "diff limited to design-village"], "modelTier": "standard"}
```

---

## Task 12: Adapt `design-grounds`

**Goal:** `design-grounds` keeps its garden traditions and geometry rules, stamps repeating units as modules, and sequences its dependency seams itself before building through `exec-ashlar`.

**Files:**
- Modify: `skills/design-grounds/SKILL.md`
- Modify: `skills/design-grounds/reference/blueprints.md`, `elements.md`, `interview.md`, `styles.md`, `water.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_grounds` passes.
- [ ] `git diff --stat` shows changes only under `skills/design-grounds/`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_grounds` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace `  Part of the minecraft-builder workflow.` with `  Builds through Ashlar with the exec-ashlar skill.`

Edit 2. Replace the `## Connection` section body with C2.

Edit 3. In core principle 3, replace `state this in the plan so the `exec-worker`\n   does not place decaying leaves.` with `state this in the plan so no decaying leaves are placed.`

Edit 4. Replace core principle 4 with:

```markdown
4. **Reuse the repeating unit.** A parterre quarter, a maze cell, an allée
   tree — define it once as a module (`modules/<element>.json`) and stamp it,
   like the other design skills.
```

Edit 5. Replace the `## Inputs` list with:

```markdown
- **From `survey-research`** — for a named garden or tradition, reference
  imagery and cited dimensions; persist the dossier to the project folder.
- **From the site survey** — use the `exec-ashlar` skill (`survey <project>`),
  or a delegated envelope from `design-city`.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration.
```

Edit 6. Replace process step 6 with:

```markdown
6. **Coordinate dependencies** — note the seams for roofed structures,
   statuary, animated water, and site grading, so each owning skill runs in
   the right order (see Hand-off).
```

Edit 7. Replace the first paragraph of process step 8 and its `quality_contract` line:

```text
8. **Write the plan and return** — `requirements.md`, `plan.toon`, and the
   registry entry. Structure names follow the canonical colon form
   `mcb:<project>_<element>`.

   **Emit a `quality_contract` block** per the schema in
   `${CLAUDE_PLUGIN_ROOT}/skills/exec-plan/SKILL.md`.
```

with:

```markdown
8. **Write the plan and hand off** — `requirements.md`, `plan.toon` with its
   phase and module files per the `exec-ashlar` skill's
   `reference/plan-format.md` (`../exec-ashlar/reference/plan-format.md`), and
   the registry entry.

   **Emit a `quality_contract` block** per that same plan format.
```

Edit 8. Replace the paragraph `For volume limits, … command-budget.md`.` with C8.

Edit 9. In `## Dependency seams`, replace:

```text
A garden is rarely built alone — this is the most coordination-heavy design
skill. You are a Tier-3 leaf: you do not call sibling leaves. Name each seam in
the plan and return it to the orchestrator, which sequences the leaf that owns
it:
```

with:

```markdown
A garden is rarely built alone — this is the most coordination-heavy design
skill. Name each seam in the plan; Hand-off says how each owning skill is run:
```

and replace `- **Delegated envelopes** — the orchestrator may hand you a plaza or park` with `- **Delegated envelopes** — another design skill may hand you a plaza or park`.

Edit 10. In `## Hard rules`: replace the never-place bullet with C5; replace the pre-tile bullet with:

```markdown
- **Split large gardens into modules and phases** within Ashlar's limits — and
  **put every seam on an axis of symmetry or a path/hedge line**, never through
  the middle of a parterre or basin.
```

replace `- **No `/random` or `/data`** — pre-bake any irregular pattern` (keep the rest of that bullet) with `- **No `/random`** — pre-bake any irregular pattern`, and add at the end of that bullet: `Console commands only as `../exec-ashlar/reference/commands.md` allows.`; replace `  mark each seam in the plan and let the orchestrator route the owning leaf.` with `  mark each seam in the plan; Hand-off says who does each.`

Edit 11. Replace the whole `## Return` section with:

```markdown
## Hand-off

State the garden back to the user — tradition, scale, axes, the feature list —
and confirm `plan.toon` is written. No separate coordinator runs the next steps
in this setup, so you sequence the dependency seams, typically:

1. **Grading**: use the `terrain-shape` skill if it is installed; otherwise add
   a `site-prep` phase that gives a flat, true datum (clearing, levelling,
   filling holes, soft-edged terraces) and tell the user if the site needs more
   than that.
2. **Roofed structures and statuary**: run the `design-building` and
   `design-monument` skills for them.
3. **Build the garden**: use the `exec-ashlar` skill (`build <project>`), with
   verification after each phase.
4. **Animated water**: use the `system-redstone` skill if it is installed;
   otherwise leave the static basins and tell the user.
```

- [ ] **Step 3: Edit the references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/blueprints.md` | 47 | C13: `exec-inspect`/`exec-reflect` re-check → the `exec-ashlar` skill's verification after the build |
| `reference/blueprints.md` | 66–67 | C13: "a fill over 32,768, a structure over …" → "a single call over Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`)" |
| `reference/elements.md` | 4 | "it once as a `mcb:<project>_<element>` structure and stamp it." → "it once as a module (`modules/<element>.json`) and stamp it." |
| `reference/elements.md` | 10 | "set via `block_set_state` properties" → "written into the `mc_build` block state" |
| `reference/interview.md` | 4 | C12 |
| `reference/styles.md` | 92–98 | C21 |
| `reference/water.md` | 53 | C22: "Use `block_fill_region` with" → "Use `mc_build` with" |

- [ ] **Step 4: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 5: Review the diff.** Only `skills/design-grounds/` files, only the edits above.

- [ ] **Step 6: Commit**

```bash
git add skills/design-grounds
git commit -F - <<'MSG'
feat(design-grounds): build through exec-ashlar instead of Chapman's pipeline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-grounds/SKILL.md", "skills/design-grounds/reference/blueprints.md", "skills/design-grounds/reference/elements.md", "skills/design-grounds/reference/interview.md", "skills/design-grounds/reference/styles.md", "skills/design-grounds/reference/water.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_grounds", "acceptanceCriteria": ["static checks pass for design_grounds", "diff limited to design-grounds"], "modelTier": "standard"}
```

---

## Task 13: Adapt `design-monument`

**Goal:** `design-monument` keeps its six techniques and render-verify discipline, renders and places voxel forms through the vendored toolkit and the Ashlar placer, and summons armor stands and display entities with allowlisted, tagged commands.

**Files:**
- Modify: `skills/design-monument/SKILL.md`
- Modify: `skills/design-monument/reference/armor-stands.md`, `blueprints.md`, `display-entities.md`, `interview.md`, `mesh-import.md`, `palettes.md`, `pixel-art.md`, `render-verify.md`, `sculpting.md`

**Acceptance Criteria:**
- [ ] `pytest tests/ashlar/test_skill_text.py -k design_monument` passes (including `tools/voxel/README.md`).
- [ ] `render-verify.md` uses labelled lines for viewing PNGs and for the skill-folder path.
- [ ] `git diff --stat` shows changes only under `skills/design-monument/`.

**Verify:** `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_monument` → `3 passed`

**Steps:**

- [ ] **Step 1: See the check fail.** Run the Verify command; expected FAIL.

- [ ] **Step 2: Edit `SKILL.md`.**

Edit 1 (description). Replace `  large creature. Part of the minecraft-builder workflow.` with `  large creature. Builds through Ashlar with the exec-ashlar skill.`

Edit 2. Replace the `## Connection` section body with C2.

Edit 3. Replace the paragraph under `## Render-verify first — never iterate a representational build blind` with:

```markdown
For any voxelized or parametric piece (a vehicle, creature, character, statue,
giant logo), **author a model you can see and verify it against the references
before placing a single block.** A wrong silhouette cannot be fixed by
detailing, and every in-world rebuild costs snapshots and time — so the cheap
iteration happens offline, on a render. The bundled `voxel` toolkit
(`tools/voxel/` in this skill's folder) authors a parametric numpy model,
renders three orthogonal views to PNG, then decomposes the verified model into
world fills that the `exec-ashlar` skill's placer sends to the server. After
building, confirm with `mc_render` facades and a top view — a visual pass, not
spot-checked coordinates. This is mandatory for representational forms; the
full recipe, the toolkit, how to view the PNGs in your client, and the
"imported meshes are not authoritative" guardrail are in
**`reference/render-verify.md`**.
```

Edit 4. Replace the `## Inputs` list with:

```markdown
- **From `survey-research`** — reference images and cited real-world or
  canonical dimensions for any named monument or creature. For a named piece,
  run that skill first and record the citations in the registry so the build
  can be checked against them.
- **From the site survey** — the `exec-ashlar` skill's `survey <project>`: the
  site, space, and viewing angles.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration.
```

Edit 5. In `## Scale and the Java envelope`, change `The world spans Y -64 to 320.` to `The world spans Y −64 to 319.`, and replace the second and third bullets with:

```markdown
- A large monument is built in tiles along natural anatomy seams (a waist, a
  neck, a limb joint), each its own phase or module, so every phase's
  snapshots stay within Ashlar's per-snapshot cap.
- For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
  slots), follow the `exec-ashlar` skill's `reference/tools-and-limits.md`
  (`../exec-ashlar/reference/tools-and-limits.md`).
```

Edit 6. In `## Sibling coordination`, replace:

```text
A monument is often half of a collaboration. You don't route to siblings — the
orchestrator sequences them — but name the seam explicitly in your plan so the
orchestrator knows which leaf owns each part and where they meet:
```

with:

```markdown
A monument is often half of a collaboration. Name the seam explicitly in your
plan — which skill owns each part and where they meet — and sequence them as
Hand-off describes:
```

and replace `Record the shared anchor coordinate in the `mcbuilder:registry` so the\norchestrator can hand it to whichever sibling it sequences next.` with `Record the shared anchor coordinate in `.minecraft-builder/registry.json` so\nwhichever sibling skill runs next can use it.`

Edit 7. Replace process step 3 with `3. **Research** — use the `survey-research` skill's reference images and dimensions for a named monument or creature.`; replace process step 6 with `6. **Coordinate siblings** — note in the plan any cliff, pedestal, or plinth a sibling skill owns and the shared anchor where it meets your figure (see Hand-off).`

Edit 8. Replace process step 7 (from `7. **Design into the plan**` through its `quality_contract` line, keeping the contract bullets that follow) with:

```markdown
7. **Design into the plan** — write `plan.toon`, its phase files and module
   files per the `exec-ashlar` skill's `reference/plan-format.md`
   (`../exec-ashlar/reference/plan-format.md`). A pixel-art grid or a voxelized
   form is a **generated grid**: write it as a phase file (a fills list) with a
   script, never as thousands of hand-written entries, and send it with the
   placer (`via: placer`). For a **large parametric form** (a vehicle, a
   creature), the reusable artifact is the **authoring script + the model
   `.npy`** (see `reference/render-verify.md`); record their location in the
   registry.

   When a tile repeats mirrored or turned (a left/right pair of wings, four
   faces of an obelisk), make it a module and add `placements` rows with
   `rotation` (0, 90, 180 or 270, clockwise from above) and `mirror` (`none`,
   `x` for east–west, `z` for north–south); `stamp.py` produces the phase file
   (`../exec-ashlar/reference/modules.md`). For weathered or scattered
   fragments, bake the decay into the module (remove the blocks you want
   missing) — Ashlar has no random-integrity placement.

   Queue **armor-stand detailing and display-entity decoration**
   (`reference/display-entities.md`) as the last phase, after all blockwork,
   as allowlisted `summon` commands, so fills don't disturb the entities.

   **Emit a `quality_contract` block** per that same plan format.
```

Edit 9. Replace process step 9 with `9. **Hand off** — write the plan, register the monument in `.minecraft-builder/registry.json`, and follow Hand-off below.`

Edit 10. In the reference table, replace the `reference/render-verify.md` row's description with: `The render-before-you-place loop: author a parametric model, render 3 views, iterate vs. references, decompose to fills, place them with the exec-ashlar placer, check with `mc_render`. Toolkit API + the imported-mesh guardrail.`

Edit 11. In `## Hard rules`: replace the never-place bullet with C5; replace `  inside the figure belongs to `design-building` — flag it for the orchestrator.` with `  inside the figure belongs to `design-building` — flag it and run that skill for it.`; replace the pre-tile bullet with `- **Tile large forms along anatomy seams** so every phase stays within Ashlar's limits; stay within Y −64 to 319.`; in the render-verify bullet replace `and scan-render the built result to confirm it` with `and check the built result with `mc_render``; replace the `/random`/`/data` bullet with `- **No `/random`** — bake any variation into the design; console commands only as `../exec-ashlar/reference/commands.md` allows.`; replace `  sibling leaf that owns each in the plan so the orchestrator can sequence it.` with `  sibling skill that owns each in the plan (see Hand-off).`

Edit 12. Replace the whole `## Return to the orchestrator` section with:

```markdown
## Hand-off

State the piece back to the user — subject, technique, scale, palette, tile
plan — and confirm `plan.toon` is written. No separate coordinator runs the
next steps in this setup, so you sequence them:

1. **Siblings first**: any cliff, plinth or pedestal. Use the `terrain-shape`
   or `terrain-landmark` skill if it is installed; otherwise add a `site-prep`
   phase (clearing, levelling, pads, filling holes, soft-edged terraces) and
   tell the user if the site needs more than that. A habitable pedestal goes to
   the `design-building` skill. They meet the figure at the recorded anchor.
2. **Build**: use the `exec-ashlar` skill (`build <project>`). Voxelized forms
   go through the placer; armor stands and display entities run last as
   allowlisted `summon` commands.
3. For a display-heavy piece (3D text, logos, glowing accents), ask the user to
   look at the first placed display in game before the rest are summoned.
```

- [ ] **Step 3: Replace `reference/render-verify.md`** with:

````markdown
# Render-verify: give yourself eyes before you place blocks

The single most valuable habit for any representational or parametric build.
`mc_render` shows what you built, but only after the blocks are in the world,
and every in-world rebuild costs snapshots and time. A wrong **base silhouette**
cannot be rescued by any amount of front-end detailing. So build a model you can
see first, offline: a renderer is cheaper than one wrong in-world rebuild.

This applies to: vehicles, creatures, statues, characters, logos, any
voxelized form, any large figurative mass. It does **not** apply to a flat
pixel-art grid you already laid out on paper — that you can reason about
directly.

## The loop (offline, seconds per iteration)

1. **Author** the form as a parametric `VoxelModel` (numpy grid + primitives).
2. **Render** three orthogonal views to PNG and **look at them**.
3. **Compare** to the reference images. Adjust **one parameter at a time**.
4. **Re-render.** Repeat until the renders genuinely match the references.
5. **Decompose** to a fills file and **place it** with the `exec-ashlar` placer.
6. **Verify** with `mc_render` (below) and compare to the references again.

Different errors surface in different views — always render multiple, never
just one:

- **side** (length × height) — the make-or-break **silhouette**. Stance,
  proportion, roofline, the overall read. Most identity errors show here.
- **front** (width × height) — the face: light bars, headlights, symmetry,
  shoulders.
- **iso** (3/4) — how the masses sit together in three dimensions.

## Looking at the PNGs

- Claude Code: open each PNG with `Read`.
- Codex: open each PNG with `view_image`.
- Otherwise: report the model's numbers (`counts()`, extents) and ask the user
  to open the files.

## The toolkit

Bundled in this skill's folder at `tools/voxel/` (numpy + Pillow through `uv`,
so nothing is installed globally); `tools/voxel/README.md` lists the API. Run an
authoring script from the workspace root with
`uv run --no-project --with numpy --with pillow python r1s.py`. Its shape:

```python
import sys
sys.path.insert(0, "<design-monument>/tools")   # this skill's folder, then tools
from voxel import Palette, VoxelModel, render_views, write_fills_json

pal = Palette.building()                  # concretes, stone, wood, glass, copper…
BODY = pal.code("cyan_concrete")
GLASS = pal.code("light_blue_stained_glass")

m = VoxelModel(nx=184, ny=70, nz=78, palette=pal)   # x=length, y=height, z=width
# anchors are fractions of the extent — define the form by ratios, tune vs render
roof, belt = m.fy(0.78), m.fy(0.45)
m.ellipsoid(center=(m.fx(0.5), belt, m.fz(0.5)), radii=(80, 22, 34), code=BODY)
m.box((m.fx(0.2), belt, m.fz(0.15)), (m.fx(0.8), roof, m.fz(0.85)), GLASS)

render_views(m, "/abs/scratch/r1s")       # r1s_iso.png / r1s_side.png / r1s_front.png
```

- Claude Code: `<design-monument>` is `${CLAUDE_SKILL_DIR}`.
- Codex: `<design-monument>` is the folder holding this skill's `SKILL.md`.
- Otherwise: use the folder holding this skill's `SKILL.md`.

Then look at the three PNGs, judge them against the references, edit the model,
and re-run. Author the shape from **anchors and primitives** (`ellipsoid`,
`cylinder`/cone, `line3d` spine, `mirror_x` for symmetry), not absolute
coordinates — so you can tune a ratio and see the effect, not chase numbers.

## Placing the verified model

Once the renders match, decompose:

```python
summary = write_fills_json(m, "/abs/scratch/r1s_fills.json", origin=(206, 64, 70))
```

`write_fills_json` greedily covers the model with maximal boxes and writes a
list of `{"from":[x,y,z], "to":[x,y,z], "block":"…"}` in **world** coordinates.

**Place it with the placer, not by hand.** A real voxelized form is 1,000–7,200
fills — far too many to transcribe into a tool call reliably. Add the file as a
`via: placer` phase in `plan.toon` and let the `exec-ashlar` skill send it:

```bash
python3 <exec-ashlar>/scripts/ashlar_place.py plan /abs/scratch/r1s_fills.json
python3 <exec-ashlar>/scripts/ashlar_place.py place /abs/scratch/r1s_fills.json --snapshot --label "<project> figure"
```

`<exec-ashlar>` is the `exec-ashlar` skill's folder (`../exec-ashlar` from this
skill's folder). The placer checks for players, snapshots the area, and pages
the fills into `mc_build` calls within Ashlar's limits. If it needs more
snapshots than allowed, split the model along an anatomy seam into separate
fills files and phases. The script and the model `.npy` are the **reusable
artifact** for a large parametric form; record them in the registry.

## Verify the built result

After placing, confirm fidelity *visually*, not by spot-checking coordinates:
render the placed bounding box with `mc_render` from the sides that matter
(`north`, `south`, `east`, `west`, y limited to the figure) and from the `top`.
Use `mc_inspect` stats for a quick solid-count and material check. A matching
count of non-air blocks between the model and the build is strong
block-for-block evidence; a matching *picture* is the real proof the build
reads as its subject.

## Imported meshes are not authoritative

A free downloaded mesh (Printables, Thingiverse, Sketchfab) voxelizes into
*a* shape, not necessarily the **named** subject's shape — a generic crossover
is not an R1S. If you import a mesh (e.g. voxelized via the optional `trimesh`
dependency into a grid), **render its silhouette and check it against the
references before building anything on it.** Render-checking on day one is
cheap; detailing a wrong body for days is not. Hand-authoring a parametric
model usually wins for a specific named subject because you control the
silhouette directly — **but when the user hands you a model file (or a faithful
one exists for the named subject), voxelizing it wins** (it nailed an organic
character on the first try where hand-authoring took ~6 rebuilds). See
`reference/mesh-import.md` for the full import pipeline and the `.3mf` gotchas.

## Scene scale

When the piece shares a scene with another subject (a figure beside a vehicle),
**pin the scale relationship before authoring** — fix the ratio (e.g. figure
height ≈ vehicle roof height) up front, so you don't discover a 4× mismatch
after both are built. Record the ratio in `requirements.md`.
````

- [ ] **Step 4: Edit the other references.**

| File | Lines | Edit |
| --- | --- | --- |
| `reference/armor-stands.md` | 32–37 | C17: "Spawn armor stands with the **`entity_summon`** tool (`entity_type: "minecraft:armor_stand"`)" → "Spawn armor stands with the allowlisted `summon minecraft:armor_stand <x> <y> <z> {…}`"; `Tags:["mcb_deco"]` … `entity_query` → `Tags:["ashlar","ashlar.<project>"]` so they can be counted with `execute if entity` and removed by tag; `entity_set_nbt` → the allowlisted `data merge entity` |
| `reference/blueprints.md` | 34 | C13: `exec-inspect`/`exec-reflect` re-check → the `exec-ashlar` skill's verification after the build |
| `reference/blueprints.md` | 47–48 | C13: "a fill over 32,768, or a structure over …" → "a single call over Ashlar's limits (`../exec-ashlar/reference/tools-and-limits.md`)" |
| `reference/display-entities.md` | 4 | "summoned with `entity_summon`" → "summoned with the allowlisted `summon` command" |
| `reference/display-entities.md` | 21–22 | C17: tags → `Tags:["ashlar","ashlar.<project>"]`; "found again with `entity_query` and adjusted with `entity_set_nbt`" → "counted with `execute if entity`, adjusted with `data merge entity`, and removed by tag" |
| `reference/display-entities.md` | 31–32 | "round-trip it with `itemstack_describe` on the running version (`server_get_status` reports the version). Pass …" → "read the entity back with `data get entity` on the running version (`mc_status` reports the version)." (drop the `include_values` sentence) |
| `reference/display-entities.md` | 92–94 | "**Because the agent cannot see the world**" → "**Because `mc_render` shows blocks, not entities**"; `entity_get_nbt` → `data get entity` |
| `reference/display-entities.md` | 102 | `entity_set_nbt` → `data merge entity` |
| `reference/display-entities.md` | 108–120 | Replace the looping-animation paragraph (it mentions `schedule_function`, datapack functions and `exec-plan`) with: "Ashlar cannot run or schedule datapack functions, so looping animations are out of reach. Keep displays static, or, only if the user asks, re-apply allowlisted `data merge entity` updates by hand while the session is open." |
| `reference/display-entities.md` | 127, 170, 216 | C17 for the `text_display`, `block_display` and `item_display` examples |
| `reference/display-entities.md` | 256 | `entity_get_nbt` → `data get entity` |
| `reference/display-entities.md` | 264–268 | "Summon every display with `entity_summon`" → "Summon every display with the allowlisted `summon`"; "`spawn` steps in `plan.toon`" → "`commands` rows in `plan.toon`" |
| `reference/display-entities.md` | 271 | `entity_set_nbt` → the allowlisted `data merge entity` |
| `reference/interview.md` | 4 | C12 |
| `reference/interview.md` | 20 | C11: "anchor coordinates from the survey-site" → "anchor coordinates from the site survey" |
| `reference/mesh-import.md` | 30 | Replace the `pip install` line with `uv run --no-project --with numpy --with pillow --with trimesh --with scipy --with networkx --with lxml python my_import.py` |
| `reference/mesh-import.md` | 45 | Replace with `sys.path.insert(0, "<design-monument>/tools")   # this skill's folder, then tools (see render-verify.md)` |
| `reference/mesh-import.md` | 85 | "place via `mcp_place.py` exactly as in `render-verify.md`" → "place it with the `exec-ashlar` placer exactly as in `render-verify.md`" |
| `reference/palettes.md` | 42 | C20 |
| `reference/pixel-art.md` | 22–30 | Replace the structure-capture method (scratch area, `structure_save_from_world`, `structure_load_to_world`, `structure_file_write`) with: "generate the grid as a phase file with a short script — one fill per run of same-colour pixels in a row — and send it with the `exec-ashlar` placer (`via: placer`). If the same art repeats, make it a module and stamp it (`../exec-ashlar/reference/modules.md`)."; "`fill` / `set` rows in `plan.toon`" → "hand-written phase-file entries" |
| `reference/pixel-art.md` | 44 | "runs pre-tiled within the 32,768-block cap" → "stays well within Ashlar's per-call limit" |
| `reference/sculpting.md` | 20 | "Resolve each primitive to a set of `fill`/`set` steps in `plan.toon`." → "Resolve each primitive to fills and blocks in a phase file (or generate it with the voxel toolkit)." |
| `reference/sculpting.md` | 51–54 | "(`${CLAUDE_PLUGIN_ROOT}/tools/voxel`)" → "(`tools/voxel/` in this skill's folder)"; "world fills for one `block_fill_batch`" → "world fills that the `exec-ashlar` placer sends" |

- [ ] **Step 5: See the check pass.** Run the Verify command; expected `3 passed`.

- [ ] **Step 6: Review the diff.** Only `skills/design-monument/` files, only the edits above.

- [ ] **Step 7: Commit**

```bash
git add skills/design-monument
git commit -F - <<'MSG'
feat(design-monument): render-verify and place through exec-ashlar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/design-monument/SKILL.md", "skills/design-monument/reference/armor-stands.md", "skills/design-monument/reference/blueprints.md", "skills/design-monument/reference/display-entities.md", "skills/design-monument/reference/interview.md", "skills/design-monument/reference/mesh-import.md", "skills/design-monument/reference/palettes.md", "skills/design-monument/reference/pixel-art.md", "skills/design-monument/reference/render-verify.md", "skills/design-monument/reference/sculpting.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q -k design_monument", "acceptanceCriteria": ["static checks pass for design_monument incl. tools/voxel/README.md", "render-verify uses labelled lines for PNG viewing and skill folder", "diff limited to design-monument"], "modelTier": "standard"}
```

---
## Task 14: Repository integration and workspace link

**Goal:** Record `exec-ashlar` in the taxonomy, add the fork notes to `README.md` and `CLAUDE.md`, link `exec-ashlar` into the workspace for both clients, and get every offline check green.

**Files:**
- Modify: `skills/TAXONOMY.md` (add one row and one sentence)
- Modify: `README.md` (note after the logo block)
- Modify: `CLAUDE.md` (note after the first heading's intro line)
- Create (workspace, not the repo): `/Users/bsw/Development/Minecraft/.claude/skills/exec-ashlar` and `/Users/bsw/Development/Minecraft/.agents/skills/exec-ashlar` (relative symlinks)

**Acceptance Criteria:**
- [ ] `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q` passes in full.
- [ ] `node scripts/validate-plugin.mjs` prints `✓ plugin, marketplace, skills, and agents are valid`.
- [ ] Both workspace links for `exec-ashlar` resolve to `ashlar-design-skills/skills/exec-ashlar/SKILL.md`.

**Verify:** `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q && node scripts/validate-plugin.mjs && test -f /Users/bsw/Development/Minecraft/.claude/skills/exec-ashlar/SKILL.md && test -f /Users/bsw/Development/Minecraft/.agents/skills/exec-ashlar/SKILL.md && echo links-ok` → all tests pass, validator ✓, `links-ok`

**Steps:**

- [ ] **Step 1: Add the taxonomy row.** In `skills/TAXONOMY.md`, insert after the `exec-reflect` row:

```markdown
| exec-ashlar | exec | 3 | inherit / inline | Surveys, builds, verifies and rolls back plans through the Ashlar MCP (ashlar-design-skills fork) |
```

and add this sentence right after the table:

```markdown
The ashlar-design-skills fork adds `exec-ashlar` and adapts the six `design-*`
skills and `survey-research` to build through Ashlar; see the fork's README.
```

- [ ] **Step 2: Add the README note.** In `README.md`, insert after the closing `</p>` of the logo block:

````markdown
> **This fork** ([iridium-coding/ashlar-design-skills](https://github.com/iridium-coding/ashlar-design-skills))
> adapts the six `design-*` skills and `survey-research` to build through the
> [Ashlar](https://github.com/rcwalter24/ashlar) MCP server on a Paper server,
> and adds the `exec-ashlar` skill. Chapman's other skills are unchanged and not
> needed. To use the adapted skills in a workspace with Claude Code and Codex,
> clone this repo into the workspace as `ashlar-design-skills/`, then from the
> workspace root:
>
> ```bash
> mkdir -p .claude/skills .agents/skills
> for s in design-building design-city design-grounds design-house design-monument design-village exec-ashlar survey-research; do
>   ln -sfn "../../ashlar-design-skills/skills/$s" ".claude/skills/$s"
>   ln -sfn "../../ashlar-design-skills/skills/$s" ".agents/skills/$s"
> done
> ```
>
> Start Claude Code or Codex from the workspace root. The design and the rules
> for these skills are in `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md`.
````

- [ ] **Step 3: Add the CLAUDE.md note.** In `CLAUDE.md`, insert after the line `This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.`:

```markdown
> **Fork note (ashlar-design-skills):** the six `design-*` skills,
> `survey-research` and the new `exec-ashlar` skill target the **Ashlar** MCP
> server (`mc_status`, `mc_players`, `mc_survey`, `mc_render`, `mc_inspect`,
> `mc_snapshot`, `mc_restore`, `mc_build`, `mc_command`), not the
> `minecraft-java` surface described below, so Ashlar's `mc_*` names are
> intended in those eight skills. The rest of this file describes Chapman's
> original skills. Check the eight with
> `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q`;
> their text rules are in §7.5 of
> `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md`.
```

- [ ] **Step 4: Link `exec-ashlar` into the workspace**

```bash
cd /Users/bsw/Development/Minecraft
for a in .claude .agents; do ln -sfn ../../ashlar-design-skills/skills/exec-ashlar "$a/skills/exec-ashlar"; done
readlink .claude/skills/exec-ashlar .agents/skills/exec-ashlar
cd /Users/bsw/Development/Minecraft/ashlar-design-skills
```

Expected: both links print `../../ashlar-design-skills/skills/exec-ashlar`.

- [ ] **Step 5: Run the Verify command.** Expected: all tests pass, validator ✓, `links-ok`.

- [ ] **Step 6: Commit**

```bash
git add skills/TAXONOMY.md README.md CLAUDE.md
git commit -F - <<'MSG'
docs: note the Ashlar adaptation in the taxonomy, README and CLAUDE.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

```json:metadata
{"files": ["skills/TAXONOMY.md", "README.md", "CLAUDE.md"], "verifyCommand": "uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q && node scripts/validate-plugin.mjs && test -f /Users/bsw/Development/Minecraft/.claude/skills/exec-ashlar/SKILL.md && test -f /Users/bsw/Development/Minecraft/.agents/skills/exec-ashlar/SKILL.md && echo links-ok", "acceptanceCriteria": ["full offline test suite passes", "upstream validator passes", "exec-ashlar linked for Claude Code and Codex"], "modelTier": "mechanical"}
```

---

## Task 15: Live read-only checks and the scratch area

**Goal:** Confirm the placer talks to the live server without exposing secrets, and pick and record a scratch area for the write tests, without changing the world.

**Files:**
- Create (workspace): `/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/survey.md`
- Create (workspace): `/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/sample.json`

**Acceptance Criteria:**
- [ ] `ashlar_place.py check` prints `Plugin version:` and nothing matching `ws://`, `wss://` or an `IP:port`.
- [ ] `survey.md` records a scratch box of at least 48 × 8 × 16 on flat natural ground, at least 64 blocks from every online player, with no block entities and no player-made blocks in it, plus a top-view look.
- [ ] `ashlar_place.py plan` accepts a sample phase file inside that box.
- [ ] No world-changing tool was called (`mc_build`, `mc_snapshot` create, `mc_restore`, `mc_command`).

**Verify:** `cd /Users/bsw/Development/Minecraft && python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py check 2>&1 | grep -cE 'wss?://|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+'` → `0`, and the same command without the `grep` shows `Plugin version:`

**Steps:**

- [ ] **Step 1: Connection check.** From `/Users/bsw/Development/Minecraft`, run `python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py check`. Expected: `server entry 'ashlar' from /Users/bsw/.claude.json` and the `mc_status` text (`Plugin version: 0.4.9`, Paper 26.3). Then run the Verify command; expected `0`.

- [ ] **Step 2: Find a scratch area** with read-only tools, following `skills/exec-ashlar/reference/survey.md`:
  1. `mc_players`: note every player's position. Never put player names or coordinates in the fork.
  2. Pick a candidate 64 × 64 area at least 64 blocks from every player. `mc_survey` it; look for a flat zone at least 48 × 16.
  3. `mc_render` top view over the candidate; reject it if it shows paths, farms, buildings or anything player-made.
  4. `mc_inspect` stats over the chosen box from ground level to ground + 7. It must contain only natural blocks (dirt, grass, stone, sand, plants, air).
  5. If no candidate passes, ask the user for a spot.

- [ ] **Step 3: Write `survey.md`** in the format from `reference/survey.md`, with the box as `from`/`to` corners and ground y, for project `ashlar-selftest`.

- [ ] **Step 4: Plan a sample.** Write `sample.json`: a single `minecraft:stone` fill one block above ground covering the box's first 5 × 1 × 5 corner. Run `python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py plan .minecraft-builder/ashlar-selftest/sample.json`. Expected: a JSON summary with `cells` 25 and `snapshot_tiles` 1. Do not place it.

- [ ] **Step 5: Record** the box and the check results at the top of `.minecraft-builder/ashlar-selftest/build-log.md`. Nothing to commit: these files live in the workspace, not the fork.

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/survey.md", "/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/sample.json"], "verifyCommand": "cd /Users/bsw/Development/Minecraft && python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py check 2>&1 | grep -cE 'wss?://|[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+:[0-9]+'", "acceptanceCriteria": ["check prints Plugin version with no URL or IP:port", "survey.md records a qualifying scratch box", "plan accepts the sample", "no world-changing tool called"], "modelTier": "standard"}
```

---

## Task 16: Live write test in the scratch area

**Goal:** With the user's approval, prove stamping, the placer, snapshots, tagged entity commands and restore work on the live server, and leave the scratch area exactly as it was.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create (workspace): `/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/modules/selftest-hut.json`
- Create (workspace): `/Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest/plan.toon`, `phases/01-huts.json`, `pre-stats.txt`, `post-stats.txt`

**Acceptance Criteria:**
- [ ] The user explicitly approved the box, the five stamped huts and the four console commands before any write.
- [ ] Every `blocks` entry in `phases/01-huts.json` reads back from `mc_inspect` with the same block and properties: the door, stairs, wall torch and log in each rotation and in the mirror.
- [ ] `execute if entity @e[tag=ashlar.ashlar-selftest]` reports count 1 after the summon and fails after the `kill`.
- [ ] After `mc_restore` of every snapshot id in the placer report, `post-stats.txt` equals `pre-stats.txt`.

**Verify:** `cd /Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest && diff pre-stats.txt post-stats.txt && echo restored` → `restored`

**Steps:**

- [ ] **Step 1: Write the test module** `modules/selftest-hut.json`:

```json
{
  "name": "selftest-hut",
  "size": [5, 4, 5],
  "fills": [
    {"from": [0, 0, 0], "to": [4, 0, 4], "block": "minecraft:cobblestone"},
    {"from": [0, 1, 0], "to": [4, 3, 4], "block": "minecraft:oak_planks", "mode": "walls"},
    {"from": [1, 1, 1], "to": [3, 3, 3], "block": "minecraft:air"}
  ],
  "blocks": [
    {"pos": [2, 1, 0], "block": "minecraft:oak_door[facing=north,half=lower,hinge=left]"},
    {"pos": [2, 2, 0], "block": "minecraft:oak_door[facing=north,half=upper,hinge=left]"},
    {"pos": [1, 1, 3], "block": "minecraft:oak_stairs[facing=north,half=bottom,shape=straight]"},
    {"pos": [3, 2, 1], "block": "minecraft:wall_torch[facing=south]"},
    {"pos": [0, 3, 2], "block": "minecraft:oak_log[axis=x]"}
  ]
}
```

- [ ] **Step 2: Write `plan.toon`** with five placements spaced 8 blocks apart along x from the box's corner `(X, G, Z)`, where G is the ground y from `survey.md`: rotations 0, 90, 180, 270 with mirror `none`, then rotation 0 with mirror `x`. Add the four commands, with the stand at the middle of the box one block above ground:

```toon
commands[4]{phase,seq,command,purpose}:
  2,1,summon minecraft:armor_stand <x> <y> <z> {NoGravity:1b,Tags:["ashlar","ashlar.ashlar-selftest"]},tagged entity
  2,2,execute if entity @e[tag=ashlar.ashlar-selftest],expect count 1
  2,3,kill @e[tag=ashlar.ashlar-selftest],remove it
  2,4,execute if entity @e[tag=ashlar.ashlar-selftest],expect test failed
```

- [ ] **Step 3: Stamp and size.** From `/Users/bsw/Development/Minecraft`:

```bash
python3 ashlar-design-skills/skills/exec-ashlar/scripts/stamp.py --placements .minecraft-builder/ashlar-selftest/plan.toon --modules .minecraft-builder/ashlar-selftest/modules --phase 1 --out .minecraft-builder/ashlar-selftest/phases/01-huts.json
python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py plan .minecraft-builder/ashlar-selftest/phases/01-huts.json
```

Expected: `snapshot_tiles` is 1 and the box lies inside the scratch box.

- [ ] **Step 4: Ask the user (gate).** Show the box, the five huts, the cell count, the snapshot count and the four commands; say nothing is written until they approve. Stop here until the user explicitly approves.

- [ ] **Step 5: Record the pre-test state.** `mc_inspect` stats over the scratch box (ground − 1 to ground + 7); save the text to `pre-stats.txt`.

- [ ] **Step 6: Place.** `python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py place .minecraft-builder/ashlar-selftest/phases/01-huts.json --snapshot --label "ashlar-selftest phase 1" --log .minecraft-builder/ashlar-selftest/placer.log`. Expected: exit 0, one snapshot id, `pages_done` equal to `pages_total`. Fix any `WARNINGS` with an `mc_build` call before continuing.

- [ ] **Step 7: Check every block entry.** For each `blocks` entry in `phases/01-huts.json`, call `mc_inspect` over that single cell and compare the block and its properties with the entry. All must match. Also look at the result with `mc_render` (`top` and `north`).

- [ ] **Step 8: Run the four commands** with `mc_command`, in order. Expected replies: `Summoned new Armor Stand`, `Test passed, count: 1`, `Killed Armor Stand`, `Test failed`.

- [ ] **Step 9: Restore.** `mc_restore` every snapshot id from `placer.log`. Then `mc_inspect` stats over the same box as Step 5; save to `post-stats.txt`. Run the Verify command; expected `restored`.

- [ ] **Step 10: Record** the results in `build-log.md`. Nothing to commit (workspace files).

```json:metadata
{"files": [], "verifyCommand": "cd /Users/bsw/Development/Minecraft/.minecraft-builder/ashlar-selftest && diff pre-stats.txt post-stats.txt && echo restored", "acceptanceCriteria": ["user approved before any write", "every stamped block entry reads back identically", "tagged entity counted 1 then gone after kill", "post-restore stats equal pre-test stats"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```

---

## Task 17: Skill dry runs

**Goal:** Run each design skill on a small prompt up to its approval gate in a subagent that cannot change the world, and check it surveys through Ashlar, writes the plan format correctly, and never points at a missing Chapman piece.

**Files:**
- Create (workspace): `/Users/bsw/Development/Minecraft/.claude/agents/ashlar-dry-run.md`
- Create (workspace): `.minecraft-builder/dryrun-<skill>/…` written by the subagents

**Acceptance Criteria:**
- [ ] Each of the six dry runs wrote `requirements.md`, `survey.md` and `plan.toon` (with phase files) under `.minecraft-builder/dryrun-<skill>/`.
- [ ] Every phase file passes `ashlar_place.py plan`; every `commands` row matches `skills/exec-ashlar/reference/commands.md`; every `plan.toon` has a non-empty `quality_contract`.
- [ ] No subagent report names a skill, tool or file that does not exist, and none called a world-changing tool.
- [ ] Problems found are fixed in the skill text, with the Task 1 checks still passing, and committed.

**Verify:** `cd /Users/bsw/Development/Minecraft && for f in .minecraft-builder/dryrun-*/phases/*.json; do python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py plan "$f" >/dev/null || echo "FAIL $f"; done; echo checked` → `checked` with no `FAIL` lines

**Steps:**

- [ ] **Step 1: Create the read-only test agent** `/Users/bsw/Development/Minecraft/.claude/agents/ashlar-dry-run.md`:

```markdown
---
name: ashlar-dry-run
description: Test agent that runs one Ashlar design skill up to its approval gate without changing the Minecraft world. Use only when asked to dry-run a design skill.
tools: Read, Write, Edit, Glob, Grep, Skill, mcp__ashlar__mc_status, mcp__ashlar__mc_players, mcp__ashlar__mc_survey, mcp__ashlar__mc_render, mcp__ashlar__mc_inspect
---

You are testing a Minecraft design skill in /Users/bsw/Development/Minecraft.
Run the skill you are given for the project you are given. Answer its interview
questions yourself from the prompt and sensible defaults, and record them in
requirements.md. Treat each blueprint and plan as approved once you have
presented it. Stop when the skill hands off to `exec-ashlar build`; do not build.
You cannot change the world; if a step needs a tool you do not have, note it and
carry on.

Report: the files you wrote, every tool you called, every instruction that
pointed at a skill, tool or file that does not exist, and anything unclear.
```

Agent definitions load when a session starts. If `ashlar-dry-run` is not offered as a subagent type, stop and ask the user to start a new session in `~/Development/Minecraft`, then continue from Step 2.

- [ ] **Step 2: Dispatch six dry runs** with subagent type `ashlar-dry-run`, one per skill, using the scratch box from Task 15:
  - `design-house`, project `dryrun-house`: "a 7 × 7 spruce starter cottage with a bed, a crafting table and a chest".
  - `design-building`, project `dryrun-building`: "a small Romanesque chapel, about 9 × 15, aesthetic-only interior".
  - `design-village`, project `dryrun-village`: "a hamlet of 3 plains houses and a bell, Mode C, with one farmer".
  - `design-city`, project `dryrun-city`: "one 48 × 48 medieval market district with two vernacular house types".
  - `design-grounds`, project `dryrun-grounds`: "a 21 × 21 French formal parterre with a central round basin".
  - `design-monument`, project `dryrun-monument`: "a 12-block stone obelisk on a 5 × 5 plinth with an inscription sign".

- [ ] **Step 3: Check each run.** Run the Verify command. For each `plan.toon`, compare its `commands` rows with `commands.md` and confirm `quality_contract` has rows. Read each subagent report for missing-reference notes and unexpected tool calls. Confirm with `mc_snapshot` `action: "list"` that no new snapshots appeared.

- [ ] **Step 4: Fix and re-run.** For every problem traced to skill text, edit the skill in the fork, rerun `uv run --no-project --with pytest --with pyyaml pytest tests/ashlar/test_skill_text.py -q`, and rerun that skill's dry run.

- [ ] **Step 5: Commit** any skill fixes:

```bash
git add skills
git commit -F - <<'MSG'
fix: address issues found in the design-skill dry runs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

Skip the commit if nothing needed fixing, and say so in the task report.

```json:metadata
{"files": ["/Users/bsw/Development/Minecraft/.claude/agents/ashlar-dry-run.md"], "verifyCommand": "cd /Users/bsw/Development/Minecraft && for f in .minecraft-builder/dryrun-*/phases/*.json; do python3 ashlar-design-skills/skills/exec-ashlar/scripts/ashlar_place.py plan \"$f\" >/dev/null || echo \"FAIL $f\"; done; echo checked", "acceptanceCriteria": ["six dry runs wrote requirements, survey and plan", "phase files pass plan; commands match the allowlist; quality_contract present", "no missing references and no world-changing calls", "skill fixes committed with checks passing"], "modelTier": "standard"}
```

---

## Task 18: End-to-end build of a small house

**Goal:** With the user's approval at the gate, build one small house from `design-house` through `exec-ashlar` in the scratch area, verify every contract row, then roll it back and confirm the area is restored.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create (workspace): `.minecraft-builder/selftest-house/…` (written by the skills), `pre-stats.txt`, `post-stats.txt`

**Acceptance Criteria:**
- [ ] `design-house` ran in the main session for project `selftest-house` inside the scratch box, and the user approved the blueprint and, at `exec-ashlar`'s gate, the build.
- [ ] Every acceptance and `quality_contract` row passed, with evidence recorded in `build-log.md`.
- [ ] `exec-ashlar rollback selftest-house` restored the area: `post-stats.txt` equals `pre-stats.txt`, and the registry status is `rolled-back`.

**Verify:** `cd /Users/bsw/Development/Minecraft/.minecraft-builder/selftest-house && diff pre-stats.txt post-stats.txt && grep -q '"status": "rolled-back"' ../registry.json && echo restored` → `restored`

**Steps:**

- [ ] **Step 1: Record the pre-test state.** `mc_inspect` stats over the scratch box (ground − 1 to ground + 10); save to `.minecraft-builder/selftest-house/pre-stats.txt`.

- [ ] **Step 2: Design.** Use the `design-house` skill for project `selftest-house`: "a starter tier 7 × 7 spruce cottage inside the scratch box from `.minecraft-builder/ashlar-selftest/survey.md`, with a bed, a crafting table, a chest, a lit interior and one door". Show the user the blueprints and get their approval.

- [ ] **Step 3: Build.** Follow the skill's hand-off into `exec-ashlar build selftest-house`. At the approval gate, show the summary and wait for the user's explicit yes before any write.

- [ ] **Step 4: Verify.** Let `exec-ashlar` run every acceptance and `quality_contract` row and record the evidence in `build-log.md`. Fix and re-verify until all pass.

- [ ] **Step 5: Roll back.** Ask the user before rolling back; then run `exec-ashlar rollback selftest-house`. Save `mc_inspect` stats over the same box to `post-stats.txt`. Run the Verify command; expected `restored`.

- [ ] **Step 6: Fix and commit** any skill-text problems found along the way, as in Task 17 Step 5.

```json:metadata
{"files": [], "verifyCommand": "cd /Users/bsw/Development/Minecraft/.minecraft-builder/selftest-house && diff pre-stats.txt post-stats.txt && grep -q '\"status\": \"rolled-back\"' ../registry.json && echo restored", "acceptanceCriteria": ["design-house ran with user approval of blueprint and build gate", "every acceptance and quality_contract row passed with evidence", "rollback restored the area and registry status is rolled-back"], "modelTier": "frontier", "userGate": true, "tags": ["user-gate"]}
```

---

## Task 19: Install check, push and pull request

**Goal:** Confirm both clients see the eight project skills, then, with the user's approval, push `ashlar` and open a pull request into the fork's `main`.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none in the repo.

**Acceptance Criteria:**
- [ ] All 16 workspace links resolve; no `design-*` copies or skills-CLI lock entries exist globally.
- [ ] The user confirmed that a new Claude Code session started in `~/Development/Minecraft` lists the eight skills, and that Codex started there lists them too.
- [ ] With the user's approval, `ashlar` is pushed to `origin` and a PR into `iridium-coding/ashlar-design-skills` `main` exists. Nothing is pushed to `upstream` and no PR targets Chapman's repo.

**Verify:** `gh pr list --repo iridium-coding/ashlar-design-skills --head ashlar --json url,baseRefName --jq '.[] | .baseRefName + " " + .url'` → `main https://github.com/iridium-coding/ashlar-design-skills/pull/…`

**Steps:**

- [ ] **Step 1: Local install checks**

```bash
cd /Users/bsw/Development/Minecraft
for l in .claude/skills/* .agents/skills/*; do [ -f "$l/SKILL.md" ] || echo "BROKEN $l"; done; echo links-checked
ls -d ~/.claude/skills/design-* ~/.agents/skills/design-* 2>/dev/null || echo no-global-copies
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.local/state/skills/.skill-lock.json'))); print([k for k in d['skills'] if k.startswith(('design-','exec-ashlar','survey-research'))] or 'no-lock-entries')"
```

Expected: `links-checked` with no `BROKEN` lines, `no-global-copies`, `no-lock-entries`.

- [ ] **Step 2: Ask the user to check both clients.** Ask them to start a new Claude Code session in `~/Development/Minecraft` and confirm the eight skills appear (type `/` to see them), and to start `codex` there and confirm the same (for example with `/skills`). Wait for their answer.

- [ ] **Step 3: Ask for approval to push and open the PR.** Show `git log --oneline b4bea4a..ashlar`. Stop until the user approves.

- [ ] **Step 4: Push and open the PR** against the fork, never upstream:

```bash
cd /Users/bsw/Development/Minecraft/ashlar-design-skills
gh repo set-default iridium-coding/ashlar-design-skills
git push -u origin ashlar
gh pr create --repo iridium-coding/ashlar-design-skills --base main --head ashlar \
  --title "Adapt the design skills to Ashlar (sub-project 1)" \
  --body-file - <<'MSG'
Adds the `exec-ashlar` skill (survey, plan format, approval gate, snapshots, phased placement, verification, rollback, a stdio placer and module stamping), vendors the voxel toolkit into `design-monument`, and adapts the six `design-*` skills and `survey-research` to build through Ashlar in Claude Code and Codex.

Design: `docs/superpowers/specs/2026-11-17-ashlar-design-skills-design.md`. Plan: `docs/superpowers/plans/2026-11-17-ashlar-design-skills.md`.

Checks: `uv run --no-project --with pytest --with pyyaml --with numpy --with pillow pytest tests/ashlar -q`, `node scripts/validate-plugin.mjs`, a live write test and an end-to-end house build in a scratch area, both restored.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
MSG
```

- [ ] **Step 5: Run the Verify command.** Expected: `main` and the PR URL. Merging is the user's call; after they merge, run `git switch main && git pull` in the clone so the workspace links serve `main`.

```json:metadata
{"files": [], "verifyCommand": "gh pr list --repo iridium-coding/ashlar-design-skills --head ashlar --json url,baseRefName --jq '.[] | .baseRefName + \" \" + .url'", "acceptanceCriteria": ["16 workspace links resolve; no global copies or lock entries", "user confirmed both clients list the eight skills", "ashlar pushed to origin and PR into the fork's main exists; nothing to upstream"], "modelTier": "standard", "userGate": true, "tags": ["user-gate"]}
```
