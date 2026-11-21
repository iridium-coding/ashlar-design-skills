"""Command contracts from spec §§6.4, 8; circuit sources in redstone_fixtures."""
import json

import pytest

from redstone_fixtures import block, clock_module, door_2x2_module, floor, plan_from_module, sorter_slice_module
from redstone_plan import PlanError, assemble, format_state, load_plan, parse_state
from redstone_rest import list_containers, main, require_python, run_check, run_diff_plan, run_diff_reads


def read_file(path, world):
    path.write_text(json.dumps({"from": [0, 64, 0], "to": [15, 90, 15], "cells": {
        ",".join(map(str, pos)): format_state(state) for pos, state in world.items()}}))
    return path


def tiny_plan(tmp, *blocks, setup=()):
    return plan_from_module(tmp, {"size": [4, 2, 2], "blocks": [block(p, s) for p, s in blocks]}, setup=setup)


def wrong_torch(tmp):
    module, names, setup = sorter_slice_module(22)
    torch = next(b for b in module["blocks"] if tuple(b["pos"]) == names["lock_torch"])
    torch["block"] = torch["block"].replace("lit=true", "lit=false")
    plan, at = plan_from_module(tmp, module, setup=setup)
    return plan, at(names["lock_torch"])


def test_sorter_slice_at_rest_is_clean(tmp_path):
    module, names, setup = sorter_slice_module(22)
    plan, at = plan_from_module(tmp_path, module, setup=setup)
    r = run_check(plan)
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == r.as_built.unmodelled == []
    assert r.loaded_world[at(names["comparator"])].get("powered") == "true"
    assert r.loaded_world[at(names["lock_torch"])].get("lit") == "true"
    assert r.loaded_world[at(names["output_hopper"])].get("enabled") == "false"
    assert at(names["comparator"]) in {p for p, _, _ in r.loaded_changes}


def test_sorter_slice_23_items_unlocks(tmp_path):
    module, names, setup = sorter_slice_module(23)
    plan, at = plan_from_module(tmp_path, module, setup=setup)
    r = run_check(plan)
    assert r.loaded_world[at(names["lock_torch"])].get("lit") == "false"
    assert r.loaded_world[at(names["output_hopper"])].get("enabled") == "true"


def test_sorter_slice_wrong_torch_is_flagged(tmp_path):
    plan, torch = wrong_torch(tmp_path)
    [(pos, written, expected, reason)] = run_check(plan).as_built.mismatches
    assert pos == torch and "lit=false" in written and "lit=true" in expected and reason


def test_door_at_rest_and_lever_on(tmp_path):
    module, names = door_2x2_module()
    plan, at = plan_from_module(tmp_path, module)
    lever = at(names["lever"])
    r = run_check(plan, inputs=[lever])
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == r.input_unsettled[lever] == []
    for p in names["pistons"]:
        assert r.loaded_world[at(p)].get("extended") == "true"
        assert any(pos == at(p) and "extended=false" in after for pos, _, after in r.input_changes[lever])
    assert all(r.loaded_world[at(p)].id == "minecraft:smooth_stone" for p in names["doorway"])


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', ['none', 'x', 'z'])
def test_rotation_and_mirror_give_same_verdicts(tmp_path, rotation, mirror):
    module, names = door_2x2_module()
    plan, at = plan_from_module(tmp_path, module, rotation, mirror)
    lever = at(names["lever"])
    r = run_check(plan, inputs=[lever])
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == []
    changed = {p for p, before, after in r.input_changes[lever] if "sticky_piston" in before and "extended" in after}
    assert changed == {at(p) for p in names["pistons"]}


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', ['none', 'x', 'z'])
@pytest.mark.parametrize('items,lit,enabled', [(22, 'true', 'false'), (23, 'false', 'true')])
def test_sorter_slice_verdicts_survive_rotation_and_mirror(tmp_path, rotation, mirror, items, lit, enabled):
    module, names, setup = sorter_slice_module(items)
    plan, at = plan_from_module(tmp_path, module, rotation, mirror, setup=setup)
    r = run_check(plan)
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == r.as_built.unmodelled == []
    assert r.loaded_world[at(names["lock_torch"])].get("lit") == lit
    assert r.loaded_world[at(names["output_hopper"])].get("enabled") == enabled


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', ['none', 'x', 'z'])
def test_switched_clock_survives_rotation_and_mirror(tmp_path, rotation, mirror):
    module, names = clock_module(True)
    plan, at = plan_from_module(tmp_path, module, rotation, mirror)
    switch = at(names['switch'])
    r = run_check(plan, inputs=[switch])
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == []
    assert at(names['output']) in r.input_unsettled[switch]


def test_clock_with_switch_settles_until_switched_on(tmp_path, capsys):
    module, names = clock_module(True)
    plan, at = plan_from_module(tmp_path, module)
    switch = at(names['switch'])
    r = run_check(plan, inputs=[switch])
    assert r.as_built.mismatches == r.as_built.structural == r.as_built.unsettled == []
    assert at(names['output']) in r.input_unsettled[switch]
    assert main(['check', str(plan), '--input', *map(str, switch)]) == 0
    assert 'cannot settle' in capsys.readouterr().out


def test_free_running_clock_cannot_settle(tmp_path):
    module, names = clock_module(False)
    plan, at = plan_from_module(tmp_path, module)
    assert at(names['output']) in run_check(plan).as_built.unsettled
    assert main(['check', str(plan)]) == 1


def test_loaded_oscillator_has_no_baseline(tmp_path, capsys):
    module, names = clock_module(True)
    # A loaded hopper feeds a comparator into the inhibit torch's support.
    module['blocks'].extend([block((2, 0, 1), 'comparator[facing=east]'), block((3, 0, 1), 'hopper')])
    plan, at = plan_from_module(tmp_path, module, setup=[((3, 0, 1), 0, 'minecraft:dirt', 1)])
    observed = read_file(tmp_path / 'read.json', assemble(load_plan(plan)))
    assert at(names['output']) in run_check(plan).loaded_unsettled
    assert main(['check', str(plan)]) == 0
    assert 'loaded' in capsys.readouterr().out
    assert main(['diff', str(plan), str(observed), '--loaded']) == 2
    assert 'cannot settle' in capsys.readouterr().err


def test_containers_lists_every_container_sorted(tmp_path, capsys):
    module, names, _ = sorter_slice_module(22)
    plan, at = plan_from_module(tmp_path, module, 90, 'z')
    expected = sorted((at(names[k]), 'minecraft:' + ('chest' if k == 'chest' else 'hopper'))
                      for k in ['line_hopper', 'filter_hopper', 'output_hopper', 'chest'])
    assert list_containers(plan) == expected
    assert main(['containers', str(plan)]) == 0
    assert capsys.readouterr().out.splitlines() == [f'{x} {y} {z} {block_id}' for (x, y, z), block_id in expected]


def test_cli_check_exit_codes(tmp_path, capsys):
    module, _, setup = sorter_slice_module(22)
    plan, _ = plan_from_module(tmp_path, module, setup=setup)
    assert main(['check', str(plan)]) == 0
    assert capsys.readouterr().out.startswith('check fixture: 0 mismatches, 0 structural, 0 unsettled, 0 unmodelled\n')
    plan, _ = wrong_torch(tmp_path)
    assert main(['check', str(plan)]) == 1
    assert ' because ' in capsys.readouterr().out
    assert main(['check', str(tmp_path / 'missing')]) == 2
    assert 'missing' in capsys.readouterr().err
    plan, _ = tiny_plan(tmp_path, ((0, 0, 0), 'rail'), ((1, 0, 0), 'redstone_wire'))
    assert main(['check', str(plan)]) == 3
    assert 'check minecraft:rail by hand' in capsys.readouterr().out


def test_cli_diff_plan_built_ignores_power_and_connection_props(tmp_path, capsys):
    plan, at = tiny_plan(tmp_path, ((0, 0, 0), 'redstone_wire[power=0]'), ((1, 0, 0), 'repeater[delay=2]'))
    phase = tmp_path / 'circuit.json'
    data = json.loads(phase.read_text())
    data['blocks'][0]['block'] = 'redstone_wire[power=0,east=side]'
    phase.write_text(json.dumps(data))
    world = assemble(load_plan(plan))
    wire, repeater = at((0, 0, 0)), at((1, 0, 0))
    world[wire] = parse_state('redstone_wire[power=12,east=up]')
    observed = read_file(tmp_path / 'read.json', world)
    assert main(['diff', str(plan), str(observed)]) == 0
    world[repeater] = parse_state('repeater[delay=4]')
    read_file(observed, world)
    assert main(['diff', str(plan), str(observed)]) == 1
    assert 'delay=4' in capsys.readouterr().out
    del world[repeater]
    assert run_diff_plan(plan, read_file(observed, world), False) == [(repeater, 'minecraft:repeater[delay=2]', 'not read')]


def test_cli_diff_loaded_reports_a_wrong_torch(tmp_path, capsys):
    module, names, setup = sorter_slice_module(23)
    plan, at = plan_from_module(tmp_path, module, setup=setup)
    world = run_check(plan).loaded_world
    observed = read_file(tmp_path / 'read.json', world)
    assert main(['diff', str(plan), str(observed), '--loaded']) == 0
    torch = at(names['lock_torch'])
    world[torch] = world[torch].with_props(lit='true')
    read_file(observed, world)
    assert main(['diff', str(plan), str(observed), '--loaded']) == 1
    assert 'lit=false' in capsys.readouterr().out
    del world[torch]
    assert run_diff_plan(plan, read_file(observed, world), True)[0][2] == 'not read'


def test_cli_diff_reads_reports_power_changes(tmp_path, capsys):
    first = {(0, 64, 0): parse_state('redstone_wire[power=3]'), (1, 64, 0): parse_state('lever[powered=true]')}
    a = read_file(tmp_path / 'a.json', first)
    b = read_file(tmp_path / 'b.json', {(0, 64, 0): first[(0, 64, 0)].with_props(power='2')})
    assert main(['diff', str(a), str(b)]) == 1
    assert 'power=2' in capsys.readouterr().out
    assert [p for p, _, _ in run_diff_reads(a, b)] == [(0, 64, 0)]
    assert main(['diff', str(a), str(a)]) == 0


def test_independent_inputs_start_from_loaded_world(tmp_path):
    # Each test hopper reaches 23 if empty space accepts a single item. Fill
    # slots 0..3, proving the probe adds in slot 4 and preserves the setup.
    slots = [((0, 0, 0), n, 'minecraft:cobblestone', count) for n, count in enumerate([19, 1, 1, 1])]
    plan, at = tiny_plan(tmp_path, ((0, 0, 0), 'hopper'), ((1, 0, 0), 'comparator[facing=west]'),
                         ((2, 0, 0), 'redstone_wire'), ((3, 0, 1), 'stone_button'), setup=slots)
    hopper, wire, button = map(at, [(0, 0, 0), (2, 0, 0), (3, 0, 1)])
    r = run_check(plan, inputs=[button, hopper])
    assert r.loaded_world[wire].get('power') == '1'
    assert any(p == wire and 'power=2' in after for p, _, after in r.input_changes[hopper])
    assert all(p != button for p, _, _ in r.input_changes[hopper])
    assert all(p != wire for p, _, _ in r.input_changes[button])
    full = slots + [((0, 0, 0), 4, 'minecraft:stick', 1)]
    plan, _ = tiny_plan(tmp_path, ((0, 0, 0), 'hopper'), setup=full)
    with pytest.raises(PlanError, match='empty slot'):
        run_check(plan, inputs=[hopper])


def test_no_input_probe_for_stone(tmp_path):
    plan, _ = tiny_plan(tmp_path, ((0, 0, 0), 'stone'))
    assert main(['check', str(plan), '--input', '0', '64', '0']) == 2


def test_cli_background_respects_existing_blocks(tmp_path):
    plan, at = tiny_plan(tmp_path, ((1, 0, 0), 'redstone_lamp[lit=true]'))
    phase = tmp_path / 'circuit.json'
    data = json.loads(phase.read_text())
    data['fills'] = [{'from': [0, 64, 0], 'to': [0, 64, 0], 'block': 'stone', 'mode': 'keep'}]
    phase.write_text(json.dumps(data))
    background = read_file(tmp_path / 'site.json', {at((0, 0, 0)): parse_state('redstone_block')})
    assert main(['check', str(plan)]) == 1
    assert main(['check', str(plan), '--background', str(background)]) == 0


@pytest.mark.parametrize('command', ['check', 'diff', 'containers', 'reads'])
def test_invalid_supported_state_returns_2(tmp_path, command):
    plan, at = tiny_plan(tmp_path, ((0, 0, 0), 'redstone_wire[power=20]'))
    observed = read_file(tmp_path / 'bad.json', {at((0, 0, 0)): parse_state('redstone_wire[power=20]')})
    args = {'check': ['check', str(plan)], 'diff': ['diff', str(plan), str(observed)],
            'containers': ['containers', str(plan)], 'reads': ['diff', str(observed), str(observed)]}
    assert main(args[command]) == 2


def test_server_rendered_text_requires_a_hand_check(tmp_path, capsys):
    plan, _ = tiny_plan(tmp_path)
    (tmp_path / 'circuit.json').write_text(json.dumps({'text': [{'text': 'A'}]}))
    observed = read_file(tmp_path / 'read.json', {})
    assert main(['diff', str(plan), str(observed)]) == 2
    assert 'text' in capsys.readouterr().err


def test_python_guard(capsys):
    with pytest.raises(SystemExit) as exc:
        require_python((3, 10))
    assert exc.value.code == 2 and 'redstone_rest.py' in capsys.readouterr().err


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('condition', [{'mode': 'keep'}, {'filter': 'air'}])
def test_conditional_diff_needs_prebuild_read(tmp_path, capsys, loaded, condition):
    plan, at = tiny_plan(tmp_path, ((1, 0, 0), 'redstone_lamp[lit=true]'))
    phase = tmp_path / 'circuit.json'
    data = json.loads(phase.read_text())
    data['fills'] = [{'from': [0, 64, 0], 'to': [0, 64, 0], 'block': 'redstone_block', **condition}]
    phase.write_text(json.dumps(data))
    pre = read_file(tmp_path / 'pre.json', {at((0, 0, 0)): parse_state('air')})
    post = read_file(tmp_path / 'post.json', {at((0, 0, 0)): parse_state('redstone_block'),
                                              at((1, 0, 0)): parse_state('redstone_lamp[lit=true]')})
    args = ['diff', str(plan), str(post)] + (['--loaded'] if loaded else [])
    assert main(args) == 2
    assert '--background' in capsys.readouterr().err
    assert main(args + ['--background', str(pre)]) == 0
    # An existing stone skips the fill. The unloaded lamp must consequently be off.
    read_file(pre, {at((0, 0, 0)): parse_state('stone')})
    assert bool(run_diff_plan(plan, post, loaded, background=pre)) == loaded


def test_unconditional_writes_resolve_conditional_diff(tmp_path):
    plan, at = tiny_plan(tmp_path, ((1, 0, 0), 'dirt'))
    phase = tmp_path / 'circuit.json'
    data = json.loads(phase.read_text())
    data['fills'] = [{'from': [0, 64, 0], 'to': [0, 64, 0], 'block': 'stone'},
                     {'from': [0, 64, 0], 'to': [1, 64, 0], 'block': 'glass', 'filter': 'stone'}]
    phase.write_text(json.dumps(data))
    read = read_file(tmp_path / 'post.json', {at((0, 0, 0)): parse_state('glass'), at((1, 0, 0)): parse_state('dirt')})
    assert run_diff_plan(plan, read, False) == []


def test_loaded_diff_needs_no_read_for_a_power_source_without_tracked_properties(tmp_path):
    plan, at = tiny_plan(tmp_path, ((1, 0, 0), 'redstone_lamp[lit=true]'))
    pre = read_file(tmp_path / 'pre.json', {at((0, 0, 0)): parse_state('redstone_block')})
    post = read_file(tmp_path / 'post.json', {at((1, 0, 0)): parse_state('redstone_lamp[lit=true]')})
    assert not run_diff_plan(plan, post, True, background=pre)


def test_built_diff_checks_static_properties_per_block_type(tmp_path):
    cases = [('glass_pane[north=true]', 'glass_pane[north=false]', False),
             ('oak_fence[east=true]', 'oak_fence[east=false]', False),
             ('cobblestone_wall[west=tall]', 'cobblestone_wall[west=none]', False),
             ('cobblestone_wall[up=true]', 'cobblestone_wall[up=false]', False),
             ('vine[up=true]', 'vine[up=false]', True),
             ('iron_bars[south=true]', 'iron_bars[south=false]', False),
             ('oak_stairs[shape=inner_left,facing=west]', 'oak_stairs[shape=straight,facing=east]', True),
             ('chest[type=single,facing=east]', 'chest[type=left,facing=east]', False),
             ('rail[shape=east_west]', 'rail[shape=north_south]', True),
             ('oak_leaves[persistent=true]', 'oak_leaves[persistent=false]', True),
             ('vine[east=true]', 'vine[east=false]', True),
             ('barrel[open=false]', 'barrel[open=true]', True)]
    plan, _ = tiny_plan(tmp_path)
    rows = [{'pos': [x, 64, 0], 'block': a} for x, (a, _, _) in enumerate(cases)]
    (tmp_path / 'circuit.json').write_text(json.dumps({'blocks': rows}))
    observed = read_file(tmp_path / 'post.json', {(x, 64, 0): parse_state(b) for x, (_, b, _) in enumerate(cases)})
    assert [p[0] for p, *_ in run_diff_plan(plan, observed, False)] == [x for x, (_, _, d) in enumerate(cases) if d]


def test_oscillating_baseline_skips_probes_and_preserves_check_verdict(tmp_path, capsys):
    module, _ = clock_module(False)
    module['blocks'].append(block((0, 0, 0), 'lever[face=floor,powered=false]'))
    plan, at = plan_from_module(tmp_path, module)
    pos = at((0, 0, 0))
    assert main(['check', str(plan), '--input', *map(str, pos)]) == 1
    output = capsys.readouterr().out
    assert 'input 0 64 0' in output and 'no settled loaded baseline' in output


def test_invalid_text_encoding_is_a_cli_input_error(tmp_path):
    path = tmp_path / 'plan.toon'
    path.write_bytes(b'\xff')
    assert main(['check', str(path)]) == 2


def test_loaded_diff_checks_powered_background_component(tmp_path):
    plan, at = tiny_plan(tmp_path, ((0, 0, 0), 'redstone_block'))
    source, lamp = at((0, 0, 0)), at((1, 0, 0))
    pre = read_file(tmp_path / 'pre.json', {lamp: parse_state('redstone_lamp[lit=false]')})
    post = tmp_path / 'post.json'
    read_file(post, {source: parse_state('redstone_block'), lamp: parse_state('redstone_lamp[lit=false]')})
    assert run_diff_plan(plan, post, True, background=pre) == [
        (lamp, 'minecraft:redstone_lamp[lit=true]', 'minecraft:redstone_lamp[lit=false]')]
    read_file(post, {source: parse_state('redstone_block')})
    assert run_diff_plan(plan, post, True, background=pre) == [(lamp, 'minecraft:redstone_lamp[lit=true]', 'not read')]
    read_file(post, {lamp: parse_state('redstone_lamp[lit=true]')})
    assert run_diff_plan(plan, post, True, background=pre) == []


def test_filter_defaults_do_not_become_built_diff_requirements(tmp_path):
    plan, at = tiny_plan(tmp_path)
    first, second = at((0, 0, 0)), at((1, 0, 0))
    fills = [{'from': first, 'to': second, 'block': 'repeater'},
             {'from': second, 'to': second, 'block': 'stone', 'filter': 'repeater[delay=1]'}]
    (tmp_path / 'circuit.json').write_text(json.dumps({'fills': fills}))
    observed = read_file(tmp_path / 'post.json', {first: parse_state('repeater[delay=4]'), second: parse_state('stone')})
    assert run_diff_plan(plan, observed, False) == []


def test_sparse_prebuild_read_does_not_imply_default_properties(tmp_path):
    plan, at = tiny_plan(tmp_path)
    pos = at((0, 0, 0))
    fill = {'from': pos, 'to': pos, 'filter': 'repeater[delay=1]', 'block': 'stone'}
    (tmp_path / 'circuit.json').write_text(json.dumps({'fills': [fill]}))
    pre = read_file(tmp_path / 'pre.json', {pos: parse_state('repeater')})
    post = read_file(tmp_path / 'post.json', {pos: parse_state('stone')})
    with pytest.raises(PlanError, match='complete state'):
        run_diff_plan(plan, post, False, background=pre)


@pytest.mark.parametrize('initial,conditional,final_filter,converges', [
    ('repeater', 'repeater[delay=2]', 'repeater', True),
    ('repeater', 'comparator', 'repeater', False),
    (None, 'repeater[delay=2]', 'repeater', False),
])
def test_later_filter_can_resolve_an_ambiguous_write(tmp_path, initial, conditional, final_filter, converges):
    plan, at = tiny_plan(tmp_path)
    pos = at((0, 0, 0))
    fills = [{'from': pos, 'to': pos, 'filter': 'repeater[delay=1]', 'block': conditional},
             {'from': pos, 'to': pos, 'filter': final_filter, 'block': 'stone'}]
    (tmp_path / 'circuit.json').write_text(json.dumps({'fills': fills}))
    pre = read_file(tmp_path / 'pre.json', {pos: parse_state(initial)} if initial else {})
    post = read_file(tmp_path / 'post.json', {pos: parse_state('stone')})
    if converges:
        assert run_diff_plan(plan, post, False, background=pre) == []
        read_file(post, {pos: parse_state('repeater')})
        assert run_diff_plan(plan, post, False, background=pre) == [(pos, 'minecraft:stone', 'minecraft:repeater')]
    else:
        with pytest.raises(PlanError, match='conditional fill|cannot evaluate filter'):
            run_diff_plan(plan, post, False, background=pre)


def torch_circuit(tmp, support):
    # lever -> dust -> repeater -> support block carrying a wall torch written unlit
    module = {"size": [5, 2, 1], "fills": [floor((0, 0, 0), (4, 0, 0))], "blocks": [
        block((0, 1, 0), 'lever[face=floor,facing=north,powered=true]'),
        block((1, 1, 0), 'redstone_wire[power=15,east=side,west=side]'),
        block((2, 1, 0), 'repeater[facing=west,delay=1,powered=true,locked=false]'),
        {"pos": [3, 1, 0], "block": support if ':' in support else 'minecraft:' + support},
        block((4, 1, 0), 'redstone_wall_torch[facing=east,lit=false]')]}
    return plan_from_module(tmp, module)


@pytest.mark.parametrize('support', ['stone', 'tuff', 'polished_blackstone_bricks', 'purpur_block'])
def test_common_conductors_power_a_torch_support(tmp_path, support):
    plan, _ = torch_circuit(tmp_path, support)
    r = run_check(plan)
    assert r.as_built.mismatches == [] and r.as_built.unmodelled == []


def test_unmodelled_support_annotates_the_mismatch(tmp_path, capsys):
    plan, _ = torch_circuit(tmp_path, 'example:block')
    r = run_check(plan)
    assert r.as_built.unmodelled
    [(pos, _, _, reason)] = r.as_built.mismatches or [(None, None, None, '')]
    assert 'next to unmodelled' in reason and 'check by hand' in reason
    assert main(['check', str(plan)]) == 1
    assert 'check by hand)' in capsys.readouterr().out
