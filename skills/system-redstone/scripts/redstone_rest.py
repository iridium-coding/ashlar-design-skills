#!/usr/bin/env python3
"""Check Java redstone resting states and compare saved Ashlar reads, offline."""
from __future__ import annotations

import sys


def require_python(version: tuple[int, ...] | None = None) -> None:
    if tuple(version if version is not None else sys.version_info[:2]) < (3, 11):
        print("redstone_rest.py needs Python 3.11 or newer; run it with `uv run "
              "--no-project --python 3.11 python redstone_rest.py ...`", file=sys.stderr)
        raise SystemExit(2)


require_python()

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from redstone_model import (CAPACITY, CHESTS, HORIZONTAL, POWER_PROPS, Contents, Report, World,
                            check_world, modelled, name, power_diff, power_keys, solve, switch_on,
                            validate_state, value)
from redstone_plan import (Plan, PlanError, Pos, Stack, State, format_state, load_plan, load_read,
                           setup_loads, written_cells)

Change = tuple[Pos, str, str]


@dataclass
class CheckResult:
    as_built: Report
    loaded_world: World
    loaded_changes: list[Change]
    input_changes: dict[Pos, list[Change]]
    input_unsettled: dict[Pos, list[Pos]]
    loaded_unsettled: list[Pos] = field(default_factory=list)


def _probe(world: World, contents: Contents, pos: Pos) -> tuple[World, list[Pos]]:
    capacity = CAPACITY.get(name(world.get(pos)))
    if capacity is None:
        return solve(switch_on(world, pos), contents)
    # Command-addressed inventory slots belong to the selected block entity,
    # including when a comparator sums both halves of a double chest.
    slots = contents.get(pos, {})
    for i in range(capacity):
        if i not in slots or slots[i].count <= 0:
            return solve(world, {**contents, pos: {**slots, i: Stack('minecraft:cobblestone', 1)}})
    raise PlanError(f"{pos}: container has no empty slot for the input probe")


def _read_world(path: Path) -> World:
    world, _ = load_read(path)
    for pos, state in world.items():
        validate_state(pos, state)
    return world


def _site(background: Path | None) -> World:
    return _read_world(background) if background is not None else {}


def _check(plan: Plan, inputs: Sequence[Pos], site: World, written: World | None = None) -> CheckResult:
    if written is None:
        written = written_cells(plan, site)
    built, report = check_world(site | written, {})
    # The site supplies circuit context. Only the plan's own writes promise
    # a particular as-built power state.
    report.mismatches = [entry for entry in report.mismatches if entry[0] in written]
    contents = setup_loads(plan)
    if contents:
        loaded, loaded_report = check_world(built, contents)
        loaded_unsettled = loaded_report.unsettled
        report.warnings = list(dict.fromkeys(report.warnings + loaded_report.warnings))
    else:
        loaded, loaded_unsettled = built, report.unsettled
    result = CheckResult(report, loaded, power_diff(built, loaded), {}, {}, loaded_unsettled)
    for pos in sorted(set(inputs)):
        if loaded_unsettled:
            report.warnings.append(f"input {_coords(pos)} skipped: no settled loaded baseline")
            continue
        probed, unsettled = _probe(loaded, contents, pos)
        result.input_changes[pos] = power_diff(loaded, probed)
        result.input_unsettled[pos] = unsettled
    return result


def run_check(plan_path: Path, inputs: Sequence[Pos] = (), background: Path | None = None) -> CheckResult:
    return _check(load_plan(plan_path), inputs, _site(background))


def _ignored_in_built(state: State, key: str) -> bool:
    block = state.id.removeprefix('minecraft:')
    if key in POWER_PROPS:
        return key != 'open' or block.endswith(('_door', '_trapdoor', '_fence_gate'))
    if key in HORIZONTAL:
        return (block in ('redstone_wire', 'iron_bars') or block.endswith(('_pane', '_fence', '_wall', '_bars')))
    if key == 'up':
        return block.endswith('_wall')  # the connection pass recomputes a wall's post
    return ((key == 'shape' and block.endswith('_stairs')) or (key == 'type' and block in CHESTS))


def run_diff_plan(plan_path: Path, read_path: Path, loaded: bool, background: Path | None = None) -> list[Change]:
    plan = load_plan(plan_path)
    actual = _read_world(read_path)
    site = _site(background)
    expected = written_cells(plan, site, require_known_conditions=True)
    if loaded:
        result = _check(plan, (), site, expected)
        if result.loaded_unsettled:
            raise PlanError('loaded circuit cannot settle; no resting baseline for diff --loaded')
        expected = {p: s for p, s in result.loaded_world.items() if power_keys(name(s))}
    changes = []
    for pos, state in sorted(expected.items()):
        validate_state(pos, state)
        other = actual.get(pos)
        if other is None:
            changes.append((pos, format_state(state), 'not read'))
            continue
        if loaded:
            differs = any(value(state, key) != value(other, key) for key in power_keys(name(state)))
        else:
            differs = any(other.get(k) != v for k, v in state.props if not _ignored_in_built(state, k))
        if state.id != other.id or differs:
            changes.append((pos, format_state(state), format_state(other)))
    return changes


def run_diff_reads(a: Path, b: Path) -> list[Change]:
    first, second = _read_world(a), _read_world(b)
    common = (p for p in first.keys() & second.keys() if modelled(name(first[p])) and modelled(name(second[p])))
    changes = []
    for pos in sorted(common):
        before, after = first[pos], second[pos]
        keys = set(power_keys(name(before))) | set(power_keys(name(after)))
        if any(value(before, key) != value(after, key) for key in keys):
            changes.append((pos, format_state(before), format_state(after)))
    return changes


def list_containers(plan_path: Path) -> list[tuple[Pos, str]]:
    containers = []
    for pos, state in sorted(written_cells(load_plan(plan_path)).items()):
        validate_state(pos, state)
        if name(state) in CAPACITY:
            containers.append((pos, state.id))
    return containers


def _coords(pos: Pos) -> str:
    return ' '.join(map(str, pos))


def _print_check(project: str, result: CheckResult) -> int:
    report = result.as_built
    print(f'check {project}: {len(report.mismatches)} mismatches, {len(report.structural)} structural, '
          f'{len(report.unsettled)} unsettled, {len(report.unmodelled)} unmodelled')
    for pos, written, expected, reason in report.mismatches:
        print(f'{_coords(pos)}  written {written}  expected {expected}  because {reason}')
    for pos, message in report.structural:
        print(f'{_coords(pos)}  structural  {message}')
    for pos in report.unsettled:
        print(f'{_coords(pos)}  cannot settle')
    for pos, message in report.unmodelled:
        print(f'{_coords(pos)}  unmodelled  {message}')
    for message in report.warnings:
        print(f'warning  {message}')
    if result.loaded_unsettled:
        for pos in result.loaded_unsettled:
            print(f'loaded  {_coords(pos)}  cannot settle')
    else:
        for pos, before, after in result.loaded_changes:
            print(f'loaded  {_coords(pos)}  {before} -> {after}')
    for input_pos, changes in result.input_changes.items():
        print(f'input {_coords(input_pos)}')
        for pos in result.input_unsettled[input_pos]:
            print(f'  {_coords(pos)}  cannot settle')
        for pos, before, after in changes:
            print(f'  {_coords(pos)}  {before} -> {after}')
    if report.mismatches or report.structural or report.unsettled:
        return 1
    return 3 if report.unmodelled else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='check as-built, loaded and optional input states')
    check.add_argument('plan', type=Path)
    check.add_argument('--input', nargs=3, type=int, action='append', default=[], metavar=('X', 'Y', 'Z'))
    check.add_argument('--background', type=Path, metavar='READ.json')
    diff = commands.add_parser('diff', help='compare a plan with a saved read, or compare two reads')
    diff.add_argument('first', type=Path, metavar='PLAN_OR_READ')
    diff.add_argument('second', type=Path, metavar='READ')
    diff.add_argument('--loaded', action='store_true', help='compare a plan after setup loads')
    diff.add_argument('--background', type=Path, metavar='PRE_BUILD_READ.json')
    containers = commands.add_parser('containers', help='list written container positions and block ids')
    containers.add_argument('plan', type=Path)
    ns = parser.parse_args(argv)
    try:
        if ns.command == 'check':
            plan = load_plan(ns.plan)
            return _print_check(plan.project, _check(plan, [tuple(p) for p in ns.input], _site(ns.background)))
        if ns.command == 'containers':
            for pos, block_id in list_containers(ns.plan):
                print(f'{_coords(pos)} {block_id}')
            return 0
        if ns.first.suffix == '.json':
            if ns.loaded or ns.background:
                raise PlanError('--loaded and --background require a plan as the first argument')
            changes = run_diff_reads(ns.first, ns.second)
        else:
            changes = run_diff_plan(ns.first, ns.second, ns.loaded, ns.background)
        for pos, before, after in changes:
            print(f'{_coords(pos)}  {before} -> {after}')
        return int(bool(changes))
    except (PlanError, OSError, UnicodeError) as exc:
        print(f'redstone_rest: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
