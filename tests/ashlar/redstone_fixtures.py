"""Independently laid-out Java circuits for exercising the stamped-plan checker."""
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from ashlar_place import box_of, volume
import stamp
from redstone_plan import Pos

Local = tuple[int, int, int]
Load = tuple[Local, int, str, int]


def block(pos: Local, state: str) -> dict:
    return {"pos": list(pos), "block": "minecraft:" + state}


def floor(a: Local, b: Local) -> dict:
    return {"from": list(a), "to": list(b), "block": "minecraft:stone"}


def sorter_slice_module(filter_items: int) -> tuple[dict, dict[str, Local], list[Load]]:
    # Minecraft Wiki, Tutorial:Hopper §Item sorter (2026-11-20). Shorten the
    # dust run for 22 -> 23 total items; the overflow-protected version uses 41+4.
    names = {"line_hopper": (0, 4, 1), "filter_hopper": (0, 3, 1), "comparator": (1, 3, 1),
             "lock_torch": (0, 1, 1), "output_hopper": (0, 2, 1), "chest": (0, 2, 0)}
    module = {"size": [4, 5, 2], "fills": [floor((1, 2, 1), (2, 2, 1))], "blocks": [
        block(names["line_hopper"], "hopper[facing=south,enabled=true]"),
        block(names["filter_hopper"], "hopper[facing=east,enabled=true]"),
        block(names["comparator"], "comparator[facing=west,mode=compare,powered=false]"),
        block((2, 3, 1), "redstone_wire[power=0]"), block((3, 2, 1), "redstone_wire[power=0]"),
        block((3, 1, 1), "stone"), block((2, 0, 1), "stone"),
        block((2, 1, 1), "repeater[facing=east,delay=1,powered=false,locked=false]"),
        block((1, 1, 1), "stone"), block(names["lock_torch"], "redstone_wall_torch[facing=west,lit=true]"),
        block(names["output_hopper"], "hopper[facing=north,enabled=false]"),
        block(names["chest"], "chest[facing=north,type=single]")]}
    hopper = names["filter_hopper"]
    loads = [(hopper, 0, "minecraft:cobblestone", filter_items - 4)]
    loads.extend((hopper, slot, "minecraft:stick", 1) for slot in range(1, 5))
    return module, names, loads


def door_2x2_module() -> tuple[dict, dict[str, Local | list[Local]]]:
    # Minecraft Wiki, Redstone circuits/Piston §Piston gate designs (2026-11-20).
    # The torch drives the lower piston and the solid block behind the upper one.
    lever = (3, 1, 1)
    blocks = [block(lever, "lever[face=floor,facing=south,powered=false]")]
    blocks.extend(block((x, 1, 0), "redstone_wire[power=0]") for x in range(8))
    pistons, doorway = [], []
    for x, step, direction in [(0, 1, "east"), (7, -1, "west")]:
        blocks.extend([block((x, 1, 1), "redstone_wire[power=0]"), block((x, 1, 2), "stone"),
                       block((x, 2, 2), "redstone_torch[lit=true]"), block((x, 3, 2), "stone")])
        for y in (2, 3):
            piston, head, panel = ((x + n * step, y, 2) for n in (1, 2, 3))
            pistons.append(piston)
            doorway.append(panel)
            blocks.extend([block(piston, f"sticky_piston[facing={direction},extended=true]"),
                           block(head, f"piston_head[facing={direction},type=sticky,short=false]"),
                           block(panel, "smooth_stone")])
    return ({"size": [8, 4, 3], "fills": [floor((0, 0, 0), (7, 0, 2))], "blocks": blocks},
            {"lever": lever, "pistons": pistons, "doorway": doorway})


def clock_module(with_switch: bool) -> tuple[dict, dict[str, Local]]:
    # Minecraft Wiki, Redstone circuits/Clock §§Redstone Torch loop and
    # Torch-repeater clock (2026-11-20). The second torch inhibits the feedback.
    switch, output = (1, 0, 0), (2, 2, 1)
    blocks = [block((1, 2, 1), "stone"),
              block(output, f"redstone_wall_torch[facing=east,lit={str(not with_switch).lower()}]"),
              block((1, 2, 2), "repeater[facing=south,delay=3,powered=false]")]
    for x, z in [(3, 1), (3, 2), (3, 3), (2, 3), (1, 3)]:
        blocks.append(block((x, 2, z), "redstone_wire[power=0]"))
    if with_switch:
        blocks.extend([block((1, 0, 1), "stone"), block((1, 1, 1), "redstone_torch[lit=true]"),
                       block(switch, "lever[face=wall,facing=north,powered=false]")])
    module = {"size": [4, 3, 4], "fills": [floor((1, 1, 2), (3, 1, 3)), floor((3, 1, 1), (3, 1, 1))],
              "blocks": blocks}
    return module, {"switch": switch, "output": output}


def plan_from_module(tmp: Path, module: dict, rotation: int = 0, mirror: str = "none",
                     setup: Sequence[Load] = ()) -> tuple[Path, Callable[[Local], Pos]]:
    tmp.mkdir(parents=True, exist_ok=True)
    origin = [0, 64, 0]
    phase = stamp.stamp(module, origin, rotation, mirror)
    (tmp / "circuit.json").write_text(json.dumps(phase))
    x, y, z, ex, ey, ez = stamp.footprint(module["size"], rotation, origin)
    cells = len(phase["blocks"]) + sum(volume(box_of(f["from"], f["to"])) for f in phase["fills"])
    plan = tmp / "plan.toon"
    lines = ["plan:", "  project: fixture", "  world: world",
             f"  bbox: {{from: [{x}, {y}, {z}], to: [{ex}, {ey}, {ez}]}}",
             "phases[2]{id,name,file,blocks,from,to,via}:",
             f"  1,circuit,circuit.json,{cells},{x} {y} {z},{ex} {ey} {ez},placer",
             f"  2,loads,-,0,{x} {y} {z},{ex} {ey} {ez},commands",
             f"commands[{len(setup)}]{{phase,seq,command,purpose}}:"]

    def at(pos: Local) -> Pos:
        x, y, z = stamp.transform_point(list(pos), module["size"], rotation, mirror, origin)
        return x, y, z

    for seq, (pos, slot, item, count) in enumerate(setup, 1):
        px, py, pz = at(pos)
        lines.append(f'  2,{seq},"item replace block {px} {py} {pz} container.{slot} with {item} {count}",load')
    plan.write_text("\n".join(lines) + "\n")
    return plan, at
