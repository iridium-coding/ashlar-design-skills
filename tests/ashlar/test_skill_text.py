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
    re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(CHAPMAN_TOOLS) + r")\b"),
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
    assert leftovers("allowed-tools: mcp__minecraft-java__block_set_state") == [(1, "block_set_state")]


def test_labelled_lines_allow_client_names() -> None:
    text = ("Ask the user.\n"
            "- Claude Code: use `AskUserQuestion`.\n"
            "  continued with `AskUserQuestion` text\n"
            "- Otherwise: ask in plain text.\n"
            "Use WebFetch here.\n")
    assert unlabelled_client_names(text) == [(5, "WebFetch")]
    assert unlabelled_client_names("allowed-tools: mcp__ashlar__mc_status\n---\nbody", 2) == []
