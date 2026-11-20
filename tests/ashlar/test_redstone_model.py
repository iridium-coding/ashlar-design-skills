"""Java resting-state rules. Source comments refer to Minecraft Wiki sections."""
import pytest

from redstone_plan import PlanError, Stack, format_state, parse_state
from redstone_model import (
    check_world, container_signal, container_slots, is_conductor, power_diff,
    solve, stack_size, switch_on,
)


O = (0, 0, 0)
N = (0, 0, -1)
S = (0, 0, 1)
E = (1, 0, 0)
W = (-1, 0, 0)
UP = (0, 1, 0)
DOWN = (0, -1, 0)
BLOCK = "redstone_block"
WIRE = "redstone_wire"
LAMP = "redstone_lamp"
TORCH = "redstone_torch"
CROSS = "redstone_wire[north=side,south=side,west=side,east=side]"
CHEST = "chest[facing=north]"


def world(cells):
    return {pos: parse_state(state) for pos, state in cells.items()}


def settled(cells, contents=None):
    result, unsettled = solve(world(cells), contents or {})
    assert unsettled == []
    return result


def stack(count, item="cobblestone"):
    return Stack("minecraft:" + item, count)


def filter_items(total):
    return {0: stack(total - 4), **{i: stack(1, "stick") for i in range(1, 5)}}


@pytest.mark.parametrize("name,expected", [
    ("stone", True), ("dispenser", True), ("dropper", True), ("note_block", True),
    ("redstone_lamp", True), ("target", True), ("barrel", True),
    ("stone_slab[type=double]", True), ("stone_slab[type=top]", False),
    ("air", False), ("glass", False), ("red_stained_glass", False),
    ("oak_stairs", False), ("cobblestone_wall", False), ("oak_fence", False),
    ("glass_pane", False), ("oak_leaves", False), ("glowstone", False),
    ("hopper", False), ("chest", False), ("trapped_chest", False),
    ("piston", False), ("sticky_piston", False), ("piston_head", False),
    ("observer", False), ("redstone_block", False), ("example:stone", None),
    ("example:oak_planks", None), ("minecraft:unknown", None),
])
def test_conductivity(name, expected):
    # R1: Conductivity, Lists of conductive and non-conductive blocks (spec §8.3, 2026-11-19).
    assert is_conductor(parse_state(name)) is expected


def test_torch_unlit_when_its_block_is_powered_by_dust():
    # R2: Redstone Torch, Redstone component; Redstone mechanics, Weakly powered.
    cells = {O: "stone", UP: TORCH + "[lit=true]", W: WIRE, (-2, 0, 0): BLOCK}
    result, report = check_world(world(cells), {})
    assert result[UP].get("lit") == "false"
    assert any(p == UP and reason.startswith("R2") for p, _, _, reason in report.mismatches)


def test_torch_on_redstone_block_is_unlit():
    # R2: Redstone Torch, Redstone component.
    assert settled({O: TORCH, DOWN: BLOCK})[O].get("lit") == "false"


def test_torch_strongly_powers_block_above_but_not_side_blocks():
    # R3: Redstone Torch, Redstone component.
    result = settled({O: TORCH, UP: "stone", (0, 2, 0): WIRE, E: "stone", (2, 0, 0): LAMP})
    assert result[(0, 2, 0)].get("power") == "15"
    assert result[(2, 0, 0)].get("lit") == "false"


@pytest.mark.parametrize("source", ["lever", "stone_button", "oak_button"])
def test_lever_strongly_powers_its_block(source):
    # R4: Lever, Behavior; Button, Redstone component. Vanilla Java wall orientation.
    result = settled({O: source + "[powered=true,face=wall,facing=west]",
                      E: "stone", (2, 0, 0): WIRE, N: LAMP})
    assert result[(2, 0, 0)].get("power") == "15"
    assert result[N].get("lit") == "true"


def test_redstone_block_powers_dust_not_blocks():
    # R5: Block of Redstone, Redstone component.
    result = settled({O: BLOCK, E: WIRE, W: "stone", (-2, 0, 0): WIRE})
    assert result[E].get("power") == "15"
    assert result[(-2, 0, 0)].get("power") == "0"


def test_repeater_reads_input_from_its_facing_side():
    # R6: Redstone Repeater, Signal direction; vanilla Java facing points at input.
    cells = {O: "repeater[facing=north]", N: BLOCK, S: LAMP, E: LAMP}
    result = settled(cells)
    assert result[O].get("powered") == result[S].get("lit") == "true"
    assert result[E].get("lit") == "false"


def test_repeater_locked_by_powered_side_repeater():
    # R6: Redstone Repeater, Signal locking. No other source touches either lamp.
    cells = {O: "repeater[facing=north,powered=true]", E: "repeater[facing=east,powered=true]",
             (2, 0, 0): BLOCK, N: LAMP, S: LAMP}
    result = settled(cells)
    assert result[O].get("locked") == result[S].get("lit") == "true"
    assert result[N].get("lit") == "false"


def test_comparator_reads_hopper_fullness_22_and_23():
    # R7/R8: Redstone Comparator, Read blocks and Fullness of containers.
    cells = {O: "comparator[facing=north]", N: "hopper", S: WIRE}
    for count, strength in [(22, 1), (23, 2)]:
        loads = {N: filter_items(count)}
        assert container_signal(world(cells), loads, N) == strength
        result = settled(cells, loads)
        assert result[O].get("powered") == "true"
        assert result[S].get("power") == str(strength)
        assert "output" not in dict(result[O].props)


def test_comparator_reads_through_conductor_unless_block_powered_15():
    # R7: Redstone Comparator, Read blocks, Java Edition exception.
    hopper = (0, 0, -2)
    cells = {O: "comparator[facing=north]", N: "stone", hopper: "hopper", S: WIRE}
    loads = {hopper: filter_items(23)}
    assert settled(cells, loads)[S].get("power") == "2"
    cells[(0, 1, -1)] = "lever[face=floor,powered=true]"
    assert settled(cells, loads)[S].get("power") == "15"


@pytest.mark.parametrize("mode,side,output", [("compare", 4, 10), ("subtract", 4, 6),
                                              ("compare", 11, 0), ("subtract", 11, 0)])
def test_comparator_compare_and_subtract(mode, side, output):
    # R7: Redstone Comparator, Compare signal strength / Subtract signal strength.
    # Two five-slot containers provide independent analog inputs.
    cells = {O: f"comparator[facing=north,mode={mode}]", N: "hopper", S: WIRE,
             E: "comparator[facing=east]", (2, 0, 0): "hopper"}
    def load_for(level):
        amount = ((level - 1) * 320 + 13) // 14
        return {i: stack(min(64, amount - 64 * i)) for i in range((amount + 63) // 64)}
    result = settled(cells, {N: load_for(10), (2, 0, 0): load_for(side)})
    assert result[S].get("power") == str(output)
    assert result[O].get("powered") == str(output > 0).lower()


def test_container_signal_stack_sizes_and_double_chest():
    # R8/R18: Redstone Comparator, Fullness of containers; inventory stack limits.
    for name, item, strength in [("hopper", "ender_pearl", 1), ("dropper", "minecart", 2)]:
        assert container_signal(world({O: name}), {O: {0: stack(1, item)}}, O) == strength
    four = {i: stack(64) for i in range(4)}
    single = world({O: CHEST, N: CHEST})
    pair = world({O: CHEST, E: CHEST})
    assert container_slots(single, O) == 27
    assert container_signal(single, {O: four}, O) == 3
    assert container_slots(pair, E) == 54
    assert container_signal(pair, {O: four}, E) == 2


def test_chest_under_conductor_reads_zero():
    # R8: Redstone Comparator, Fullness of containers; either half must be accessible.
    pair = world({O: CHEST, E: CHEST, UP: "stone"})
    assert container_signal(pair, {E: {0: stack(64)}}, E) == 0


def test_observer_written_powered_is_structural_error():
    # R9: Observer, Redstone behavior; vanilla Java 'facing' watches the front.
    cells = {O: "observer[facing=up,powered=true]", DOWN: "stone", (0, -2, 0): WIRE}
    result, report = check_world(world(cells), {})
    assert [p for p, _ in report.structural] == [O]
    assert result[(0, -2, 0)].get("power") == "15"


def test_dust_line_powers_block_it_points_into_and_below():
    # R10/R11: Redstone Dust, Redstone component; Redstone mechanics, Weakly powered.
    result = settled({O: WIRE, W: BLOCK, E: "stone", (2, 0, 0): LAMP,
                      DOWN: "stone", (0, -2, 0): LAMP, S: LAMP})
    for p in [(2, 0, 0), (0, -2, 0)]:
        assert result[p].get("lit") == "true"
    assert result[S].get("lit") == "false"
    assert result[O].get("east") == result[O].get("west") == "side"


def test_lone_dust_dot_vs_cross():
    # R10: Redstone Dust, Redstone component; spec §5.4 Ashlar lone-wire assumption.
    for wire, lit in [(WIRE, "false"), (CROSS, "true")]:
        result = settled({O: wire, UP: BLOCK, E: LAMP, DOWN: LAMP})
        assert result[O].get("power") == "15"
        assert result[E].get("lit") == lit
        assert result[DOWN].get("lit") == "true"


def test_dust_does_not_connect_to_piston_side():
    # R10: Redstone Dust, Redstone component, Java piston exception.
    result = settled({O: WIRE, W: BLOCK, S: "piston[facing=south]"})
    assert result[O].get("south") == "none"


@pytest.mark.parametrize("support,down", [("stone", "14"), ("glass", "0")])
def test_dust_steps_down_only_from_conductive_block(support, down):
    # R10/R11: Redstone Dust, Redstone component, one-way upward glass step in Java.
    top = (1, 1, 0)
    cells = {O: WIRE, E: support, top: WIRE}
    assert settled({**cells, (2, 1, 0): BLOCK})[O].get("power") == down
    assert settled({**cells, W: BLOCK})[top].get("power") == "14"


def test_conductive_block_above_cuts_step():
    # R10/R11: Redstone Dust, Redstone component.
    cells = {O: WIRE, E: "stone", (1, 1, 0): WIRE, UP: "stone"}
    assert settled({**cells, W: BLOCK})[(1, 1, 0)].get("power") == "0"
    assert settled({**cells, (2, 1, 0): BLOCK})[O].get("power") == "0"


def test_weakly_powered_block_activates_lamp_but_not_dust():
    # R11/R12: Redstone mechanics, Weakly powered.
    result = settled({W: BLOCK, O: WIRE, E: "stone", (2, 0, 0): WIRE, (1, 0, 1): LAMP})
    assert result[(2, 0, 0)].get("power") == "0"
    assert result[(1, 0, 1)].get("lit") == "true"


def test_piston_quasi_connectivity_from_block_above():
    # R13: Redstone mechanics, Quasi-connectivity.
    assert settled({O: "piston[facing=east]", (0, 1, 1): "lever[powered=true]"})[O].get("extended") == "true"


def test_piston_not_powered_through_its_front_face():
    # R13: Piston, Activation; vanilla Java front is pos + facing.
    assert settled({O: "piston[facing=east]", E: BLOCK})[O].get("extended") == "false"


def test_dropper_triggered_by_quasi_connectivity():
    # R13: Redstone mechanics, Quasi-connectivity.
    assert settled({O: "dropper", (0, 1, 1): BLOCK})[O].get("triggered") == "true"


@pytest.mark.parametrize("cells", [
    {O: "piston[facing=east,extended=true]", E: "stone"},
    {E: "piston_head[facing=east,type=normal,short=false]"},
    {O: "sticky_piston[facing=east,extended=true]", E: "piston_head[facing=east,type=normal,short=false]"},
])
def test_piston_head_structural_errors(cells):
    # R14: Piston, Block states; vanilla Java head position, type and facing.
    assert len(check_world(world(cells), {})[1].structural) == 1


def test_hopper_locked_when_powered():
    # R15: Hopper, Redstone component; redstone disables transfers.
    assert settled({O: "hopper", N: BLOCK})[O].get("enabled") == "false"


def test_door_powered_from_upper_half_and_open_when_powered():
    # R15: Door, Behavior; power at either half opens both.
    result = settled({O: "oak_door[half=lower]", UP: "oak_door[half=upper]", (0, 2, 0): BLOCK})
    for p in (O, UP):
        assert result[p].get("open") == result[p].get("powered") == "true"


@pytest.mark.parametrize("a,b", [(True, False), (False, True), (True, True)])
def test_rs_latch_keeps_written_state(a, b):
    # R16: Redstone circuits/Memory, RS-NOR latches. Each torch powers the other support.
    cells = {O: "stone", (4, 0, 3): "stone",
             S: f"redstone_wall_torch[facing=south,lit={str(a).lower()}]",
             (4, 0, 2): f"redstone_wall_torch[facing=north,lit={str(b).lower()}]"}
    for on, path in [(a, [(0, 0, 2), (0, 0, 3), (1, 0, 3), (2, 0, 3), (3, 0, 3)]),
                     (b, [(4, 0, 1), (4, 0, 0), (3, 0, 0), (2, 0, 0), (1, 0, 0)])]:
        for i, p in enumerate(path):
            cells[p] = f"redstone_wire[power={15 - i if on else 0}]"
    _, report = check_world(world(cells), {})
    if a != b:
        assert report.mismatches == report.structural == report.unsettled == []
    else:
        assert report.unsettled or report.mismatches


def test_torch_loop_cannot_settle():
    # R16: Redstone Torch, Redstone component; feedback in this untimed resting-state model.
    cells = {O: "stone", E: "redstone_wall_torch[facing=east]", (1, 1, 0): "stone", UP: WIRE,
             (30, 0, 0): "redstone_lamp[lit=true]"}
    result, report = check_world(world(cells), {})
    assert set(report.unsettled) == {E, UP}
    assert result[(30, 0, 0)].get("lit") == "false"


def test_unknown_neighbour_is_reported_unmodelled():
    # R17: Conductivity, Lists; spec §8.1 and §8.4 explicitly distinguish unknowns and air.
    cells = {O: WIRE, N: "powered_rail", E: "target", (2, 0, 0): LAMP,
             (3, 0, 0): "example:block", (1, 1, 0): "lever[face=floor,powered=true]"}
    result, report = check_world(world(cells), {})
    assert {p for p, _ in report.unmodelled} == {N, E, (3, 0, 0)}
    assert result[(2, 0, 0)].get("lit") == "false"
    assert result[O].get("power") == "0"


def test_unwritten_neighbours_warn_once_and_explicit_air_is_quiet():
    # R17: spec §8.1, plan author's 2026-11-20 edge warning ruling.
    _, report = check_world(world({O: LAMP}), {})
    assert report.unmodelled == []
    assert report.warnings == ["0 0 0: neighbour not written by the plan; treated as air; pass --background to include the site"]
    cells = {p: "air" for p in [W, E, S, N, UP, DOWN]}
    assert check_world(world({O: LAMP, **cells}), {})[1].warnings == []


def test_unknown_item_counts_as_64_with_warning():
    # R18: Redstone Comparator, Fullness of containers; §8.3 unknown-stack fallback.
    loads = {O: {0: stack(23, "not_in_table")}}
    cells = world({O: "hopper"})
    assert stack_size("minecraft:not_in_table") == (64, False)
    assert container_signal(cells, loads, O) == 2
    assert any("not_in_table" in s and "64" in s for s in check_world(cells, loads)[1].warnings)


@pytest.mark.parametrize("item,size", [("oak_sign", 16), ("blue_banner", 16), ("bucket", 16),
                                       ("honey_bottle", 16), ("armor_stand", 16), ("water_bucket", 1),
                                       ("writable_book", 1), ("chest_minecart", 1), ("trident", 1),
                                       ("enchanted_book", 1), ("oak_chest_boat", 1), ("stick", 64)])
def test_stack_size_families(item, size):
    # R18: Redstone Comparator, Fullness of containers; individual items' stack limits.
    assert stack_size("minecraft:" + item) == (size, True)


@pytest.mark.parametrize("switch", ["lever", "stone_button", "oak_pressure_plate"])
def test_switch_on_and_power_diff_preserve_input(switch):
    # R4/R15: Lever / Pressure Plate, Behavior; model interface for check --input.
    before = world({O: switch + "[powered=false]", E: "redstone_lamp[lit=false]"})
    switched = switch_on(before, O)
    assert before[O].get("powered") == "false"
    after, unstable = solve(switched, {})
    assert unstable == []
    assert power_diff(before, after) == [
        (pos, format_state(before[pos]), format_state(after[pos])) for pos in (O, E)
    ]


def test_written_book_stack_limit_and_weighted_plate_state():
    # R18/R4: Java 26.3 Items.WRITABLE_BOOK and WRITTEN_BOOK, WeightedPressurePlateBlock.
    assert stack_size("minecraft:written_book") == (16, True)
    assert stack_size("minecraft:writable_book") == (1, True)
    activated = switch_on(world({O: "heavy_weighted_pressure_plate[power=0]", E: WIRE}), O)
    result, unstable = solve(activated, {})
    assert unstable == []
    assert result[O].get("powered") is None
    assert result[O].get("power") == result[E].get("power") == "1"


@pytest.mark.parametrize("east,north,expected", [
    ("observer[facing=east]", "repeater[facing=east]", {"east", "west"}),
    ("observer[facing=west]", "repeater[facing=north]", {"north", "south"}),
    ("comparator[facing=north]", "repeater[facing=north]", {"east", "north"}),
])
def test_directional_dust_connections(east, north, expected):
    # R10: Redstone Dust, Redstone component; vanilla Java observer/repeater facing.
    result = settled({O: WIRE, E: east, N: north})[O]
    assert {d for d in ("east", "west", "north", "south") if result.get(d) == "side"} == expected


@pytest.mark.parametrize("block,prop,expected", [
    ("note_block", "powered", "true"), ("spruce_fence_gate", "open", "true"),
    ("iron_trapdoor", "open", "true"), ("hopper", "enabled", "false"),
])
def test_component_signal_through_conductor(block, prop, expected):
    # R12/R15: Redstone mechanics, Activating mechanisms and Strongly powered.
    result = settled({O: block, E: "stone", (2, 0, 0): "stone_button[face=wall,facing=east,powered=true]"})
    assert result[O].get(prop) == expected


def test_explicit_defaults_and_shapes_are_ignored_by_power_diff():
    # R10/R16: Redstone Dust, Placement; Ashlar connects shape separately from power.
    before = world({O: WIRE, S: LAMP})
    after = world({O: CROSS.replace("[", "[power=0,"), S: "redstone_lamp[lit=false]"})
    assert power_diff(before, after) == []


def test_max_rounds_keeps_changing_positions_and_excludes_static_blocks():
    # R16: spec §8.3 bounded settling; Redstone Repeater, Signal repeating.
    cells = {O: "repeater[facing=north,powered=false,locked=false]",
             S: "repeater[facing=north,powered=false,locked=false]", N: BLOCK}
    _, unsettled = solve(world(cells), {}, max_rounds=1)
    assert unsettled == [O]


def test_trapped_chest_fullness_is_modelled_but_output_needs_manual_check():
    # R8/R17: Redstone Comparator, Fullness of containers; spec §8.4 manual-check boundary.
    cells = world({N: "trapped_chest", O: "comparator[facing=north]", S: WIRE})
    result, report = check_world(cells, {N: {0: stack(64)}})
    assert result[S].get("power") == "1"
    assert [p for p, _ in report.unmodelled] == [N]


def test_implicit_default_is_already_at_rest_with_one_round():
    # R16: §8.2 uses written Java states, including implicit default properties.
    result, unstable = solve(world({O: LAMP}), {}, max_rounds=1)
    assert result[O].get("lit") == "false"
    assert unstable == []


def test_transient_source_does_not_leave_closed_gate_open_at_rest():
    # R15: Door, Behavior. When a transient redstone signal ends the gate closes.
    cells = {O: "spruce_fence_gate[powered=false,open=false]", E: "repeater[facing=east,powered=true]"}
    result = settled(cells)
    assert result[O].get("powered") == result[O].get("open") == "false"
    assert settled({O: "spruce_fence_gate[open=true]"})[O].get("open") == "true"


@pytest.mark.parametrize("state", ["redstone_wire[power=no]", "heavy_weighted_pressure_plate[power=16]"])
def test_invalid_written_power_raises_plan_error_even_without_neighbours(state):
    # R11/R18 input boundary: Java blockstate power is an integer from zero through fifteen.
    with pytest.raises(PlanError, match="power"):
        solve(world({O: state}), {})


def test_double_slab_climbs_like_a_full_block():
    # R1/R10: Redstone Dust, Placement; a double slab has a full side face.
    cells = {O: WIRE, E: "smooth_stone_slab[type=double]", (1, 1, 0): WIRE}
    assert settled(cells)[O].get("east") == "up"


def test_new_dust_and_diode_sample_previous_round():
    # R16: spec §8.3 settling, with synchronous rounds as defined by R16.
    cells = {O: WIRE, W: BLOCK, E: "repeater[facing=west,powered=false]"}
    result, unsettled = solve(world(cells), {}, max_rounds=1)
    assert result[O].get("power") == "15"
    assert result[E].get("powered") == "false"
    assert unsettled == [O]


def test_written_analog_feedback_keeps_its_fixed_point():
    # R7/R16: Redstone Comparator, Subtract signal strength. Rear 10 - side 4 = 6.
    bend = (1, 0, 1)
    cells = world({N: "hopper", O: "comparator[facing=north,mode=subtract,powered=true]",
                   S: "redstone_wire[power=6]", bend: "redstone_wire[power=5]", E: "redstone_wire[power=4]"})
    loads = {N: {0: stack(64), 1: stack(64), 2: stack(64), 3: stack(14)}}
    assert container_signal(cells, loads, N) == 10
    result, report = check_world(cells, loads)
    assert report.unsettled == report.mismatches == []
    assert [result[p].get("power") for p in (S, bend, E)] == ["6", "5", "4"]


@pytest.mark.parametrize("invalid", [
    "lever[powered=no]", "redstone_torch[lit=1]", "comparator[mode=typo]",
    "repeater[facing=up]", "observer[facing=typo]", "oak_button[face=north]",
    "redstone_wire[west=true]", "piston_head[type=moving]", "piston_head[short=1]",
    "stone_slab[type=left]", "stone_stairs[half=upper]", "oak_door[half=top]",
    "hopper[facing=up]",
])
def test_invalid_interpreted_properties_raise_plan_error(invalid):
    # Vanilla Java block-state domains for modelled properties; Task 4 returns exit 2.
    with pytest.raises(PlanError):
        check_world(world({O: invalid}), {})


@pytest.mark.parametrize("valid", [
    "lever[face=ceiling]", "piston[facing=down]", "hopper[facing=down]", "observer[facing=up]",
    "oak_stairs[half=top]", "stone_slab[type=double]", "piston_head[short=false,type=normal]",
    "redstone_wire[west=up]", "comparator", "oak_door[half=upper]",
])
def test_valid_interpreted_properties_and_defaults(valid):
    # Vanilla Java block states include vertical observers/pistons and horizontal-only diodes.
    check_world(world({O: valid}), {})


def test_unqualified_observer_has_vanilla_south_facing():
    # R9/R10: the Java 26.3 ObserverBlock constructor registers SOUTH.
    cells = {N: WIRE, (1, 0, -1): BLOCK, (-1, 0, -1): LAMP}
    implicit = settled({**cells, O: "observer"})
    explicit = settled({**cells, O: "observer[facing=south]"})
    assert implicit[N] == explicit[N]
    assert implicit[(-1, 0, -1)].get("lit") == explicit[(-1, 0, -1)].get("lit") == "false"


@pytest.mark.parametrize("item", ["spyglass", "iron_nautilus_armor", "golden_nautilus_armor", "diamond_nautilus_armor",
                                 "netherite_nautilus_armor", "copper_nautilus_armor"])
def test_single_stack_tools_and_nautilus_armor(item):
    # R8/R18: Java 26.3 Items.SPYGLASS and Item.Properties.nautilusArmor call stacksTo(1).
    assert stack_size("minecraft:" + item) == (1, True)
    assert container_signal(world({O: "dropper"}), {O: {0: stack(1, item)}}, O) == 2


@pytest.mark.parametrize("item", ["mithril_nautilus_armor", "mithril_sword", "magic_boat", "unknown_sign"])
def test_unregistered_item_keeps_unknown_size_fallback(item):
    # R18: Java 26.3 ItemIds; an unfamiliar item needs the documented warning.
    assert stack_size("minecraft:" + item) == (64, False)


@pytest.mark.parametrize("block", ["nonexistent_button[powered=true]", "future_trapdoor", "fake_planks", "unknown_slab[type=double]"])
def test_unknown_vanilla_names_reported_without_guessing_from_suffix(block):
    # R1/R17: Conductivity, finite Java block families; outside the table requires a hand check.
    cells = world({O: LAMP, E: block})
    result, report = check_world(cells, {})
    assert is_conductor(cells[E]) is None
    assert result[O].get("lit") == "false"
    assert [p for p, _ in report.unmodelled] == [E]


def test_bounded_feedback_includes_oscillator_parts_from_all_observed_rounds():
    # R16: spec §8.3; component changes occur on different phases of the feedback loop.
    cells = {O: "stone", E: "redstone_wall_torch[facing=east]", (1, 1, 0): "stone", UP: WIRE}
    _, unstable = solve(world(cells), {}, max_rounds=3)
    assert set(unstable) == {E, UP}


def test_written_powered_comparator_supplies_first_round_before_depowering():
    # R7/R16: Java comparator powered=true means positive output; R16 samples written states first.
    cells = world({O: "comparator[facing=north,powered=true]", S: "redstone_lamp[lit=false]"})
    first, unsettled = solve(cells, {}, max_rounds=1)
    assert first[S].get("lit") == "true"
    assert first[O].get("powered") == "false"
    assert set(unsettled) == {O, S}
    final, unsettled = solve(cells, {})
    assert final[S].get("lit") == "false"
    assert unsettled == []
