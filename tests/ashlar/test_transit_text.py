"""Text tests: the exec-ashlar references and the toolkit API describe the transit workflow."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_transit_row_is_documented():
    assert "`transit{file}`" in read("skills/exec-ashlar/reference/plan-format.md")
    text = read("skills/exec-ashlar/reference/verification.md")
    assert "`transit{file}`" in text and "terrain.py transit-check" in text


def test_tests_table_has_summon_and_entity_await():
    text = read("skills/exec-ashlar/reference/plan-format.md")
    assert "| `summon` |" in text
    assert "`container`, `block` or `entity`" in text
    assert "`<tag> within <seconds>`" in text and "until the entity is within 2 blocks" in text
    test_mode = read("skills/exec-ashlar/SKILL.md").split("## test")[1].split("## rollback")[0]
    assert "kill @e[tag=ashlar.<project>,tag=<test tag>]" in test_mode
    assert "before any force-load is released" in test_mode
    assert "A `summon` row is in an agent test" in text


def test_registry_boxes_are_documented_and_used_for_overlap():
    assert "`boxes`" in read("skills/exec-ashlar/reference/registry.md")
    assert "`boxes`" in read("skills/exec-ashlar/reference/survey.md")


def test_toolkit_api_lists_the_transit_commands():
    text = read("skills/terrain-shape/reference/terrain/toolkit-api.md")
    assert all(f"`{c} DESIGN" in text for c in ("route", "line", "portal", "transit-check"))
    for module in ("transit_design", "route", "transit_preview", "corridor", "track",
                   "structures", "transit_checks", "transit", "portals", "blocks"):
        assert f"`{module}`" in text or f"terrain.{module}`" in text


def test_commands_and_execution_cover_the_ride_test():
    commands = read("skills/exec-ashlar/reference/commands.md")
    assert "`summon` rows" in commands
    assert "every test `load` and `summon` command exactly" in read(
        "skills/exec-ashlar/reference/execution.md")
    assert "`load` or `summon` rows" in commands
    assert "`boxes`" in read("skills/exec-ashlar/reference/execution.md")
    verification = read("skills/exec-ashlar/reference/verification.md")
    assert "`verify/<element>-overworld`" in verification and "`verify/<element>-nether`" in verification


def test_portal_pairs_are_two_builds_with_two_plans_and_entries():
    api = read("skills/terrain-shape/reference/terrain/toolkit-api.md")
    for needed in ("terrain/<element>-overworld.plan-rows.toon", "terrain/<element>-nether.plan-rows.toon",
                   "plan-overworld.toon", "plan-nether.toon", "terrain/<element>.portal-report.json",
                   "terrain/previews/"):
        assert needed in api, needed
    assert "`<element>-overworld`" in read("skills/exec-ashlar/reference/registry.md")
    skill, hub = read("skills/system-transit/SKILL.md"), read("skills/system-transit/reference/nether-hub.md")
    for text in (skill, hub):
        assert "`<element>-overworld`" in text and "`<element>-nether`" in text
        assert "shroomlight" in text
    assert "standing level" in hub and "lanterns" not in hub.split("## Hubs")[0]
    assert "bottom-slab floor and lanterns" not in skill


def test_verification_reads_the_reports_read_boxes_into_exact_folders():
    row = next(line for line in read("skills/exec-ashlar/reference/verification.md").splitlines()
               if line.startswith("| `transit{file}`"))
    assert "line report's `reads`" in row and "--sites <each read folder>" in row
    assert "never a glob such as `verify/<element>-*`" in row
    assert "`--sites verify/<element>-*`" not in row
    assert "the box each section writes" in read("skills/exec-ashlar/reference/registry.md")
    skill = read("skills/system-transit/SKILL.md")
    assert "the box each\nsection writes" in skill and "`reads` entry's box" in skill
    api = read("skills/terrain-shape/reference/terrain/toolkit-api.md")
    assert "`reads` (each section's read box" in api and "(`buried`" in api and "(`carries`)" in api
