import json

import pytest

from redstone_plan import (PlanError, Stack, State, assemble, format_state, load_plan,
                           load_read, parse_state, read_toon_table, setup_loads)

AIR = "minecraft:air"


def test_parse_state_roundtrip():
    s = parse_state("repeater[facing=north,delay=2]")
    assert s.id == "minecraft:repeater" and s.get("delay") == "2"
    assert format_state(s) == "minecraft:repeater[delay=2,facing=north]"
    assert format_state(parse_state("minecraft:stone")) == "minecraft:stone"


def test_toon_rows_keep_quoted_commas_and_quotes():
    text = ('commands[1]{phase,seq,command,purpose}:\n'
            '  4,1,"data merge block 1 2 3 {Items:[{Slot:0b,id:\\"minecraft:stone\\",count:18}]}",filters\n')
    row = read_toon_table(text, "commands")[0]
    assert row["command"] == 'data merge block 1 2 3 {Items:[{Slot:0b,id:"minecraft:stone",count:18}]}'
    assert row["purpose"] == "filters"


def write_plan(tmp_path, phases, commands=(), tests=(), phase_files=None):
    lines = ["plan:", "  project: demo", "  world: world",
             "  bbox: {from: [0, 0, 0], to: [9, 9, 9]}",
             f"phases[{len(phases)}]{{id,name,file,blocks,from,to,via}}:"]
    lines += [f"  {p}" for p in phases]
    if commands:
        lines.append(f"commands[{len(commands)}]{{phase,seq,command,purpose}}:")
        lines += [f"  {c}" for c in commands]
    if tests:
        lines.append(f"tests[{len(tests)}]{{phase,seq,command,purpose}}:")
        lines += [f"  {t}" for t in tests]
    (tmp_path / "plan.toon").write_text("\n".join(lines) + "\n")
    for name, data in (phase_files or {}).items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data))
    return tmp_path / "plan.toon"


def box(block, a, b, **extra):
    return {"from": list(a), "to": list(b), "block": block, **extra}


def test_load_plan_reads_header_and_tables(tmp_path):
    path = write_plan(
        tmp_path,
        ["1,base,phases/01.json,9,0 0 0,2 0 2,mcp",
         "2,detail,phases/02.json,1,1 0 1,1 0 1,mcp",
         "3,loads,-,0,5 64 5,5 64 5,commands"],
        commands=['3,1,"forceload add 5 5",chunk'],
        phase_files={"phases/01.json": {}, "phases/02.json": {}})
    plan = load_plan(path)
    assert plan.project == "demo" and plan.world == "world"
    assert plan.bbox == ((0, 0, 0), (9, 9, 9))
    assert [p["via"] for p in plan.phases] == ["mcp", "mcp", "commands"]
    assert plan.commands[0]["command"] == "forceload add 5 5"
    assert plan.tests == []


def test_assemble_applies_phases_fills_then_blocks(tmp_path):
    path = write_plan(
        tmp_path,
        ["1,base,phases/01.json,9,0 0 0,2 0 2,mcp",
         "2,detail,phases/02.json,2,0 0 0,2 0 2,mcp",
         "3,keep,phases/03.json,9,0 0 0,2 0 2,mcp"],
        phase_files={
            "phases/01.json": {"fills": [box("minecraft:stone", (0, 0, 0), (2, 0, 2))]},
            "phases/02.json": {"blocks": [{"pos": [1, 0, 1], "block": "minecraft:dirt"}]},
            "phases/03.json": [box("minecraft:glass", (0, 0, 0), (2, 0, 2), mode="keep")]})
    world = assemble(load_plan(path))
    assert len(world) == 9
    assert world[(1, 0, 1)] == parse_state("dirt")
    assert world[(0, 0, 0)] == parse_state("stone")


def test_assemble_keep_fills_absent_cells(tmp_path):
    path = write_plan(
        tmp_path, ["1,a,phases/01.json,3,0 0 0,2 0 0,mcp"],
        phase_files={"phases/01.json": {"fills": [
            box("minecraft:air", (1, 0, 0), (1, 0, 0)),
            box("minecraft:glass", (0, 0, 0), (2, 0, 0), mode="keep")]}})
    world = assemble(load_plan(path))
    assert world[(1, 0, 0)].id == "minecraft:glass"
    assert world[(0, 0, 0)].id == "minecraft:glass"


def test_assemble_shell_modes(tmp_path):
    lo, hi = (0, 0, 0), (2, 2, 2)
    path = write_plan(
        tmp_path,
        ["1,w,phases/w.json,1,0 0 0,2 2 2,mcp"],
        phase_files={"phases/w.json": {"fills": [box("minecraft:stone", lo, hi, mode="walls")]}})
    world = assemble(load_plan(path))
    assert (1, 1, 1) not in world and (1, 0, 1) not in world
    assert world[(0, 1, 0)].id == "minecraft:stone" and (1, 1, 0) in world
    assert (1, 2, 1) not in world

    path = write_plan(
        tmp_path, ["1,o,phases/o.json,1,0 0 0,2 2 2,mcp"],
        phase_files={"phases/o.json": {"fills": [box("minecraft:stone", lo, hi, mode="outline")]}})
    world = assemble(load_plan(path))
    assert (1, 0, 1) in world and (1, 2, 1) in world and (1, 1, 1) not in world
    assert len(world) == 26

    path = write_plan(
        tmp_path, ["1,h,phases/h.json,1,0 0 0,2 2 2,mcp"],
        phase_files={"phases/h.json": {"fills": [
            box("minecraft:stone", lo, hi, mode="replace"),
            box("minecraft:stone", lo, hi, mode="hollow")]}})
    world = assemble(load_plan(path))
    assert world[(1, 1, 1)].id == AIR and world[(1, 0, 1)].id == "minecraft:stone"


def test_assemble_filter_matches_unspecified_props_as_wildcards(tmp_path):
    path = write_plan(
        tmp_path, ["1,a,phases/01.json,3,0 0 0,2 0 0,mcp"],
        phase_files={"phases/01.json": {
            "blocks": [],
            "fills": [
                box("minecraft:oak_stairs[facing=east,half=top]", (0, 0, 0), (0, 0, 0)),
                box("minecraft:oak_stairs[facing=west,half=bottom]", (1, 0, 0), (1, 0, 0)),
                box("minecraft:spruce_planks", (2, 0, 0), (2, 0, 0)),
                box("minecraft:oak_stairs[facing=south]", (0, 0, 0), (2, 0, 0),
                    filter="minecraft:oak_stairs"),
                box("minecraft:glass", (0, 0, 0), (2, 0, 0),
                    filter="minecraft:oak_stairs[facing=north]"),
                box("minecraft:diamond_block", (0, 0, 0), (3, 0, 0),
                    filter="minecraft:air")]}})
    world = assemble(load_plan(path))
    assert world[(0, 0, 0)] == world[(1, 0, 0)] == parse_state("oak_stairs[facing=south]")
    assert world[(2, 0, 0)].id == "minecraft:spruce_planks"
    assert world[(3, 0, 0)].id == "minecraft:diamond_block"


def test_assemble_filter_checks_named_props(tmp_path):
    path = write_plan(
        tmp_path, ["1,a,phases/01.json,2,0 0 0,1 0 0,mcp"],
        phase_files={"phases/01.json": {"fills": [
            box("minecraft:oak_stairs[facing=east]", (0, 0, 0), (0, 0, 0)),
            box("minecraft:oak_stairs[facing=west]", (1, 0, 0), (1, 0, 0)),
            box("minecraft:stone", (0, 0, 0), (1, 0, 0),
                filter="minecraft:oak_stairs[facing=west]")]}})
    world = assemble(load_plan(path))
    assert world[(0, 0, 0)].id == "minecraft:oak_stairs"
    assert world[(1, 0, 0)].id == "minecraft:stone"


def test_assemble_skips_commands_phases_and_background_fills_unwritten(tmp_path):
    path = write_plan(
        tmp_path,
        ["1,a,phases/01.json,1,0 0 0,0 0 0,mcp", "2,c,-,0,0 0 0,0 0 0,commands"],
        phase_files={"phases/01.json": {"blocks": [{"pos": [0, 0, 0], "block": "minecraft:stone"}]}})
    bg = {(0, 0, 0): parse_state("dirt"), (5, 5, 5): parse_state("dirt")}
    world = assemble(load_plan(path), bg)
    assert world[(0, 0, 0)].id == "minecraft:stone"
    assert world[(5, 5, 5)].id == "minecraft:dirt"


def test_setup_loads_item_replace_and_data_merge(tmp_path):
    cmds = [
        '3,1,"item replace block 5 64 5 container.0 with minecraft:cobblestone 18",a',
        '3,2,"/item replace block 5 64 5 container.1 with minecraft:stick[custom_name=\\"F, x\\"]",b',
        '3,3,"minecraft:data merge block 6 64 6 {Items:[{Slot:0b,id:\\"minecraft:stone\\",count:5},'
        '{Slot:3b,id:\\"minecraft:dirt\\",Count:2b,components:{\\"minecraft:custom_name\\":\\"count:9\\"}}]}",c',
        '3,4,"forceload add 5 5",skipped',
    ]
    path = write_plan(tmp_path, ["3,loads,-,0,5 64 5,6 64 6,commands"], commands=cmds)
    assert setup_loads(load_plan(path)) == {
        (5, 64, 5): {0: Stack("minecraft:cobblestone", 18), 1: Stack("minecraft:stick", 1)},
        (6, 64, 6): {0: Stack("minecraft:stone", 5), 3: Stack("minecraft:dirt", 2)}}


def test_setup_loads_ignores_test_rows_and_non_commands_phases(tmp_path):
    path = write_plan(
        tmp_path,
        ["1,a,phases/01.json,0,0 0 0,0 0 0,mcp", "2,c,-,0,0 0 0,0 0 0,commands"],
        commands=['1,1,"item replace block 1 1 1 container.0 with minecraft:stone",x'],
        tests=['2,1,"item replace block 1 1 1 container.0 with minecraft:stone",load'],
        phase_files={"phases/01.json": {}})
    assert setup_loads(load_plan(path)) == {}


@pytest.mark.parametrize("command", [
    "item replace block ~ 64 5 container.0 with minecraft:stone",
    "item replace block 5 64 5 container.0 with",
    "data merge block 1 2 ^ {Items:[]}",
    "data merge block 1 2 3 {Items:[{Slot:0b,count:1}]}",
])
def test_setup_loads_bad_rows_name_file_and_line(tmp_path, command):
    path = write_plan(tmp_path, ["3,loads,-,0,0 0 0,0 0 0,commands"],
                      commands=[f'3,1,"{command}",x'])
    with pytest.raises(PlanError) as err:
        setup_loads(load_plan(path))
    assert "plan.toon" in str(err.value) and ":8" in str(err.value)


def test_load_read_parses_cells(tmp_path):
    f = tmp_path / "read.json"
    f.write_text(json.dumps({
        "world": None, "from": [0, 64, 0], "to": [1, 64, 0],
        "cells": {"0,64,0": "minecraft:lever[face=wall,facing=north,powered=false]",
                  "1,64,0": "minecraft:air"}}))
    cells, bbox = load_read(f)
    assert bbox == ((0, 64, 0), (1, 64, 0))
    assert cells[(0, 64, 0)] == State(
        "minecraft:lever", (("face", "wall"), ("facing", "north"), ("powered", "false")))
    assert cells[(1, 64, 0)].id == AIR


def test_bad_state_raises_plan_error():
    with pytest.raises(PlanError):
        parse_state("stone[facing")
    with pytest.raises(PlanError):
        parse_state("stone[facing]")


def test_bad_inputs_name_file_and_line(tmp_path):
    bad = tmp_path / "plan.toon"
    bad.write_text("plan:\n  project: demo\n")
    with pytest.raises(PlanError, match="plan.toon"):
        load_plan(bad)
    with pytest.raises(PlanError, match="missing.toon"):
        load_plan(tmp_path / "missing.toon")

    path = write_plan(tmp_path, ["1,a,phases/01.json,1,0 0 0,0 0 0,mcp"],
                      phase_files={"phases/01.json": {"blocks": [
                          {"pos": [0, 0, 0], "block": "minecraft:stone[facing"}]}})
    with pytest.raises(PlanError, match="01.json"):
        assemble(load_plan(path))

    r = tmp_path / "read.json"
    r.write_text("{not json")
    with pytest.raises(PlanError, match="read.json"):
        load_read(r)


def test_background_is_the_initial_state_for_keep_and_filters(tmp_path):
    path = write_plan(tmp_path, ['1,a,p.json,3,0 0 0,2 0 0,mcp'], phase_files={'p.json': {'fills': [
        box('stone', (0, 0, 0), (2, 0, 0), mode='keep'),
        box('gold_block', (0, 0, 0), (2, 0, 0), filter='dirt')]}})
    bg = {(0, 0, 0): parse_state('dirt'), (1, 0, 0): parse_state('glass')}
    assert assemble(load_plan(path), bg) == {(0, 0, 0): parse_state('gold_block'),
                                             (1, 0, 0): parse_state('glass'), (2, 0, 0): parse_state('stone')}
    assert bg[(0, 0, 0)] == parse_state('dirt')


@pytest.mark.parametrize('nbt,expected', [('{Items:[]}', {}),
    ('{Items:[{Slot:1b,id:stick,count:2}]}', {1: Stack('minecraft:stick', 2)}),
    ('{CustomName:Label}', {0: Stack('minecraft:dirt', 1)})])
def test_data_merge_replaces_the_whole_items_list(tmp_path, nbt, expected):
    path = write_plan(tmp_path, ['2,loads,-,0,0 0 0,0 0 0,commands'], commands=[
        '2,1,"item replace block 0 0 0 container.0 with minecraft:dirt",first',
        f'2,2,"data merge block 0 0 0 {nbt}",second'])
    assert setup_loads(load_plan(path)).get((0, 0, 0), {}) == expected


def test_filters_match_java_defaults_without_adding_authored_properties(tmp_path):
    path = write_plan(tmp_path, ['1,a,p.json,4,0 0 0,2 0 0,mcp'], phase_files={'p.json': {'fills': [
        box('repeater', (0, 0, 0), (2, 0, 0)),
        box('stone', (0, 0, 0), (0, 0, 0), filter='repeater[delay=1,facing=north,locked=false,powered=false]'),
        box('stone', (1, 0, 0), (1, 0, 0), filter='repeater[delay=2]')]}})
    assert assemble(load_plan(path)) == {(0, 0, 0): parse_state('stone'), (1, 0, 0): parse_state('repeater'),
                                         (2, 0, 0): parse_state('repeater')}


def test_filter_unknown_default_needs_an_explicit_property(tmp_path):
    path = write_plan(tmp_path, ['1,a,p.json,2,0 0 0,0 0 0,mcp'], phase_files={'p.json': {'fills': [
        box('beehive', (0, 0, 0), (0, 0, 0)),
        box('stone', (0, 0, 0), (0, 0, 0), filter='beehive[honey_level=1]')]}})
    with pytest.raises(PlanError, match='(?=.*explicit)(?=.*honey_level)'):
        assemble(load_plan(path))


def test_known_filter_mismatch_resolves_another_omitted_property(tmp_path):
    path = write_plan(tmp_path, ['1,a,p.json,2,0 0 0,0 0 0,mcp'], phase_files={'p.json': {'fills': [
        box('beehive[facing=west]', (0, 0, 0), (0, 0, 0)),
        box('stone', (0, 0, 0), (0, 0, 0), filter='beehive[honey_level=0,facing=north]')]}})
    assert assemble(load_plan(path))[(0, 0, 0)] == parse_state('beehive[facing=west]')


def test_keep_recognises_air_materials_while_filters_match_exact_ids(tmp_path):
    path = write_plan(tmp_path, ['1,a,p.json,4,0 0 0,3 0 0,mcp'], phase_files={'p.json': {'fills': [
        box('glass', (0, 0, 0), (1, 0, 0), mode='keep'),
        box('gold_block', (2, 0, 0), (3, 0, 0), mode='keep', filter='cave_air')]}})
    bg = {(x, 0, 0): parse_state('void_air' if x % 2 else 'cave_air') for x in range(4)}
    world = assemble(load_plan(path), bg)
    assert [world[(x, 0, 0)].id for x in range(4)] == [
        'minecraft:glass', 'minecraft:glass', 'minecraft:gold_block', 'minecraft:void_air']
