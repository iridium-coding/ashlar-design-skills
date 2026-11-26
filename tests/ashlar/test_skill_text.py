"""Static checks for the Ashlar-adapted skills (spec §9.1 and §7.5)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SKILLS = ["design-building", "design-city", "design-grounds", "design-house",
          "design-monument", "design-village", "exec-ashlar", "survey-research",
          "system-redstone", "terrain-shape", "terrain-landmark", "terrain-ecology",
          "terrain-integrate", "terrain-cave"]
IDS = [skill.replace("-", "_") for skill in SKILLS]
TERRAIN_SKILLS = {"terrain-shape", "terrain-landmark", "terrain-ecology", "terrain-integrate",
                  "terrain-cave"}
CLIENTS_FILE = "skills/exec-ashlar/reference/clients.md"
VOXEL_TOOLKIT = "skills/design-monument/tools/voxel/"
TERRAIN_TOOLKIT = "skills/terrain-shape/tools/terrain/"
CAVE = re.compile(r"\bterrain-cave\b")

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
    "events_subscribe", "events_poll", "events_unsubscribe", "function_run",
    "function_list", "function_get_definition", "inventory_get", "inventory_count_items",
    "entity_get", "datapack_enable", "datapack_list_enabled", "level_get_mob_spawns",
    "schedule_function", "loot_table_generate", "mcp_place",
    "level_fill_biome", "level_place_feature", "level_place_features_batch",
    "block_erode_region", "block_erode_hydraulic_start", "block_erode_hydraulic_status",
    "block_erode_hydraulic_result", "block_replace_in_region",
    "structure_create_from_blocks", "structure_list", "place_terrain", "emit_plan_toon",
]
FORBIDDEN = [
    re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(CHAPMAN_TOOLS) + r")\b"),
    re.compile(r"\bscoreboard_"),
    re.compile(r"CLAUDE_PLUGIN_ROOT"),
    re.compile(r"minecraft-mcp-setup"),
    re.compile(r"\bexec-(?:plan|blueprint|worker|inspect|reflect)\b"),
    re.compile(r"\bsurvey-site\b"),
    re.compile(r"\bbuild-(?:natural-world|settlement|structure|systems)\b"),
    re.compile(r"\bGATE B\b"),
    re.compile(r"\bharness\b"),
    re.compile(r"32,768"),
    re.compile(r"\bmcb:"),
    re.compile(r"\bmcbuilder\b"),
    re.compile(r"\bsurvey\.toon\b"),
    re.compile(r"\borchestrator\b", re.IGNORECASE),
    re.compile(r"\bloot_table_[a-z_]+"),
    re.compile(r"\bcontent_registry_[a-z_]+"),
    re.compile(r"\(capability [A-E]\b"),
]
# Patterns that can wrap across a line break, matched on the whole text.
WRAPPED_FORBIDDEN = [
    re.compile(r"\benhancement\s+spec\b"),
    re.compile(r"\bpre-build\s+(?:terraform|steps?)\b"),
    re.compile(r"\bseparate\s+coordinator\b"),
    # a world top of 320 (the top block is 319), as "-64 to 320", "Y=320" or "above Y 320"
    re.compile(r"(?:[-\u2212]64\s+to\s+(?:Y\s*=?\s*)?|\bY\s*=?\s*)320\b"),
]
# Chapman's Fabric placer is named only in the voxel toolkit's own README.
FABRIC = re.compile(r"\bFabric\b")
CLIENT_SPECIFIC = re.compile(
    r"AskUserQuestion|request_user_input|\bview_image\b|\bupdate_plan\b|\bTodoWrite\b"
    r"|\bWebSearch\b|\bWebFetch\b|\$\{CLAUDE_SKILL_DIR\}|\bmcp__")
LABELLED = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:Claude Code|Codex):")
NEW_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def leftovers(text: str, allow_fabric: bool = False,
              cave_forbidden: bool = False) -> list[tuple[int, str]]:
    """(line, match) for every Chapman-pipeline reference in `text`."""
    patterns = FORBIDDEN if allow_fabric else FORBIDDEN + [FABRIC]
    if cave_forbidden:
        patterns = patterns + [CAVE]
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in patterns:
            match = pattern.search(line)
            # the vanilla fillbiome cap (32,768) is a valid number on a fillbiome line
            if match and not (match.group(0) == "32,768" and "fillbiome" in line):
                hits.append((number, match.group(0)))
    for pattern in WRAPPED_FORBIDDEN:
        for match in pattern.finditer(text):
            hits.append((text.count("\n", 0, match.start()) + 1, match.group(0)))
    return sorted(hits)


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


SKILL_PATH = re.compile(
    r"(?<![\w/.-])((?:<terrain-shape>/|\.\./[a-z0-9-]+/)?(?:reference|scripts|tools)/[\w./-]+\.(?:md|py|json))")


def skill_paths(text: str) -> list[str]:
    """Every skill-folder file path cited in `text`, in order."""
    return [match.group(1) for match in SKILL_PATH.finditer(text)]


def _markdown(skill: str) -> list[Path]:
    root = REPO / "skills" / skill
    assert root.is_dir(), f"missing skill folder {root.relative_to(REPO)}"
    return sorted(root.rglob("*.md"))


@pytest.mark.parametrize("skill", SKILLS, ids=IDS)
def test_no_chapman_leftovers(skill: str) -> None:
    problems = []
    for path in _markdown(skill):
        rel = path.relative_to(REPO).as_posix()
        for number, hit in leftovers(
                path.read_text(encoding="utf-8"),
                allow_fabric=VOXEL_TOOLKIT in rel or TERRAIN_TOOLKIT in rel):
            problems.append(f"{rel}:{number}: {hit!r}")
    assert not problems, "Chapman pipeline references left:\n" + "\n".join(problems)


TERRAIN_IDS = sorted(TERRAIN_SKILLS)


@pytest.mark.parametrize("skill", TERRAIN_IDS, ids=[s.replace("-", "_") for s in TERRAIN_IDS])
def test_reference_links_resolve_in_skill_folder(skill: str) -> None:
    problems = []
    for path in _markdown(skill):
        rel = path.relative_to(REPO).as_posix()
        for cited in skill_paths(path.read_text(encoding="utf-8")):
            if cited.startswith("<terrain-shape>/"):
                target = REPO / "skills" / "terrain-shape" / cited[len("<terrain-shape>/"):]
            else:
                target = REPO / "skills" / skill / cited
            if not target.is_file():
                problems.append(f"{rel}: {cited}")
    assert not problems, "Unresolved skill-folder paths:\n" + "\n".join(problems)


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
    assert leftovers("allowed-tools: mcp__minecraft-java__block_set_state") == [(1, "block_set_state")]


def test_leftovers_detects_redstone_tool_names() -> None:
    assert leftovers("call events_poll") == [(1, "events_poll")]
    assert leftovers("use scoreboard_* here") == [(1, "scoreboard_")]


def test_labelled_lines_allow_client_names() -> None:
    text = ("Ask the user.\n"
            "- Claude Code: use `AskUserQuestion`.\n"
            "  continued with `AskUserQuestion` text\n"
            "- Otherwise: ask in plain text.\n"
            "Use WebFetch here.\n")
    assert unlabelled_client_names(text) == [(5, "WebFetch")]
    assert unlabelled_client_names("allowed-tools: mcp__ashlar__mc_status\n---\nbody", 2) == []


def test_leftovers_detects_design_skill_wording() -> None:
    assert leftovers("call `loot_table_list` here") == [(1, "loot_table_list")]
    assert leftovers("`minecraft:chests/village/village_temple` and LootTable") == []
    assert leftovers("use content_registry_is_compostable") == [
        (1, "content_registry_is_compostable")]
    assert leftovers("See the enhancement spec") == [(1, "enhancement spec")]
    assert leftovers("the enhancement\nspec says") == [(1, "enhancement\nspec")]
    assert leftovers("### Signs with text (capability A)") == [(1, "(capability A")]
    assert leftovers("### Signs with text") == []
    assert leftovers("note a `pre-build terraform` step") == [(1, "pre-build terraform")]
    assert leftovers("note a `pre-build\nterraform` step") == [(1, "pre-build\nterraform")]
    assert leftovers("a terrain-shape pre-build step") == [(1, "pre-build step")]
    assert leftovers("two pre-build steps") == [(1, "pre-build steps")]
    assert leftovers("plan a `site-prep` phase") == []
    assert leftovers("No separate coordinator runs the next steps") == [
        (1, "separate coordinator")]
    assert leftovers("No separate\ncoordinator runs") == [(1, "separate\ncoordinator")]
    assert leftovers("You sequence the next steps yourself, in this order") == []


def test_leftovers_fabric_only_in_the_voxel_toolkit() -> None:
    assert leftovers("(1.21.x / Fabric)") == [(1, "Fabric")]
    assert leftovers("without its Fabric placer", allow_fabric=True) == []
    assert leftovers("a woven fabric banner") == []


def test_leftovers_world_top_is_319() -> None:
    assert leftovers("(-64 to 320)") == [(1, "-64 to 320")]
    assert leftovers("Y -64 to 320 (~384 blocks)") == [(1, "-64 to 320")]
    assert leftovers("Stay within Y=-64 to Y=320.") == [(1, "-64 to Y=320")]
    assert leftovers("an element above Y 320.") == [(1, "Y 320")]
    assert leftovers("Y\u221264 to 320") == [(1, "\u221264 to 320")]
    assert leftovers("The world spans Y -64 to 319") == []
    assert leftovers("a 320-block axis, 3200 blocks") == []


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
