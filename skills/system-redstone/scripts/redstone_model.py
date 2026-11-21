#!/usr/bin/env python3
"""Offline Java redstone resting states. No ticks, block motion or world access."""
from __future__ import annotations

import sys

if sys.version_info[:2] < (3, 11):
    print("redstone_model.py needs Python 3.11 or newer; run it with `uv run "
          "--no-project --python 3.11 python redstone_model.py ...`", file=sys.stderr)
    raise SystemExit(2)

from collections import defaultdict, deque
from dataclasses import dataclass, field

from redstone_plan import AIR, PlanError, Pos, Stack, State, format_state

World = dict[Pos, State]
Contents = dict[Pos, dict[int, Stack]]
POWER_PROPS = ("power", "powered", "lit", "extended", "enabled", "triggered", "locked", "open")
HORIZONTAL = {"north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
UP, DOWN = (0, 1, 0), (0, -1, 0)
DIRECTIONS = dict(HORIZONTAL, up=UP, down=DOWN)
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "up": "down", "down": "up"}
AIR_STATE = State(AIR)
POWER_LEVELS = {str(i) for i in range(16)}
WIRE = "redstone_wire"
TORCHES = {"redstone_torch", "redstone_wall_torch"}
DIODES = {"comparator", "repeater"}
PISTONS = {"piston", "sticky_piston"}
EJECTORS = {"dropper", "dispenser"}
CHESTS = {"chest", "trapped_chest"}
CAPACITY = {"chest": 27, "trapped_chest": 27, "barrel": 27, "hopper": 5, "dropper": 9, "dispenser": 9}
GATES = ("_door", "_trapdoor", "_fence_gate")
SWITCHES = ("_button", "_pressure_plate")
WEIGHTED = {"light_weighted_pressure_plate", "heavy_weighted_pressure_plate"}
COMPONENTS = (set(CAPACITY) | TORCHES | DIODES | PISTONS |
              {WIRE, "lever", "redstone_block", "observer", "note_block", "piston_head", "redstone_lamp"})
UNMODELLED = {
    "rail", "powered_rail", "detector_rail", "activator_rail", "tripwire", "tripwire_hook",
    "daylight_detector", "target", "lectern", "sculk_sensor", "calibrated_sculk_sensor",
    "crafter", "cake", "composter", "item_frame", "glow_item_frame", "bell", "trapped_chest",
}


def name(state: State | None) -> str:
    """Keep foreign namespaces distinct, even for a familiar-looking block name."""
    if state is None:
        return "air"
    if state.id.startswith("minecraft:"):
        block = state.id[10:]
        return block if block in KNOWN_BLOCKS else ""
    return ""


def at(pos: Pos, direction: Pos, distance: int = 1) -> Pos:
    return (pos[0] + distance * direction[0], pos[1] + distance * direction[1],
            pos[2] + distance * direction[2])


def neighbours(pos: Pos):
    return (at(pos, step) for step in DIRECTIONS.values())


def facing(state: State) -> str:
    default = {"observer": "south", "hopper": "down"}.get(name(state), "north")
    direction = state.get("facing", default)
    if direction not in DIRECTIONS:
        raise PlanError(f"{state.id}: unknown facing {direction!r}")
    return direction


def sides(state: State) -> tuple[Pos, Pos]:
    if facing(state) in ("north", "south"):
        return HORIZONTAL["west"], HORIZONTAL["east"]
    return HORIZONTAL["north"], HORIZONTAL["south"]


def support(pos: Pos, state: State) -> Pos:
    block = name(state)
    wall_switch = (block == "lever" or block.endswith("_button")) and state.get("face", "wall") == "wall"
    if block == "redstone_wall_torch" or wall_switch:
        return at(pos, DIRECTIONS[facing(state)], -1)
    return at(pos, UP if state.get("face") == "ceiling" else DOWN)


def modelled(block: str) -> bool:
    return block in COMPONENTS


def excluded(block: str) -> bool:
    return block in UNMODELLED or block.endswith(("cauldron", "copper_bulb", "candle_cake"))


# R1: curated from Minecraft Wiki, Conductivity (Java lists; read 2026-11-20), and
# fixture palettes. The wiki says every variant of a listed conductive family
# (bricks, smooth, polished, cracked, chiseled, pillar) also conducts. A block
# the wiki does not show stays out of the table, so it is listed as unmodelled.
FULL_BLOCKS = set("""
stone cobblestone mossy_cobblestone smooth_stone stone_bricks mossy_stone_bricks
cracked_stone_bricks chiseled_stone_bricks bricks dirt grass_block coarse_dirt
rooted_dirt podzol moss_block clay sand red_sand gravel sandstone red_sandstone
granite andesite diorite polished_granite polished_andesite polished_diorite
deepslate cobbled_deepslate polished_deepslate deepslate_bricks deepslate_tiles
blackstone basalt netherrack nether_bricks obsidian bedrock end_stone quartz_block
smooth_quartz iron_block gold_block diamond_block emerald_block netherite_block
coal_block lapis_block copper_block slime_block terracotta barrel note_block
redstone_lamp dropper dispenser target
""".split())
NON_CONDUCTORS = set("""
air cave_air void_air glass tinted_glass glass_pane glowstone sea_lantern
water lava ice hopper chest trapped_chest piston sticky_piston piston_head
observer redstone_block lever redstone_torch redstone_wall_torch redstone_wire
repeater comparator torch wall_torch sugar_cane scaffolding iron_bars
""".split())


def variants(materials, suffixes):
    return {f"{material}_{suffix}" for material in materials for suffix in suffixes}


# Finite families verified against Java 26.3 Blocks / BlockItemIds. Unfamiliar
# namespaces and names stay outside the model even when they end in "_button".
TREES = set("oak spruce birch jungle acacia dark_oak mangrove cherry pale_oak poplar".split())
WOODS = TREES | {"crimson", "warped", "bamboo"}
COLORS = set("white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black".split())
COPPER = {f"{wax}{age}copper" for wax in ("", "waxed_")
          for age in ("", "exposed_", "weathered_", "oxidized_")}
COMPONENTS |= (
    variants(WOODS, ("door", "trapdoor", "fence_gate", "pressure_plate", "button"))
    | variants(COPPER | {"iron"}, ("door", "trapdoor"))
    | variants(("stone", "polished_blackstone"), ("pressure_plate", "button")) | WEIGHTED
)
FULL_BLOCKS |= (
    variants(WOODS, ("planks",))
    | variants(TREES | {"stripped_" + tree for tree in TREES}, ("log", "wood"))
    | variants(COLORS, ("wool", "concrete", "concrete_powder", "terracotta", "glazed_terracotta"))
)
FULL_BLOCKS |= set("""
tuff polished_tuff tuff_bricks chiseled_tuff chiseled_tuff_bricks calcite dripstone_block
amethyst_block purpur_block purpur_pillar packed_ice blue_ice
smooth_sandstone cut_sandstone chiseled_sandstone smooth_red_sandstone cut_red_sandstone
chiseled_red_sandstone
polished_blackstone polished_blackstone_bricks cracked_polished_blackstone_bricks
chiseled_polished_blackstone gilded_blackstone
chiseled_deepslate cracked_deepslate_bricks cracked_deepslate_tiles
mud mud_bricks packed_mud prismarine prismarine_bricks dark_prismarine end_stone_bricks
quartz_bricks quartz_pillar chiseled_quartz_block
cracked_nether_bricks chiseled_nether_bricks red_nether_bricks
soul_sand soul_soil chiseled_bookshelf mangrove_roots muddy_mangrove_roots
bamboo_block stripped_bamboo_block bamboo_mosaic
ochre_froglight verdant_froglight pearlescent_froglight
""".split())
FULL_BLOCKS |= (
    variants(("crimson", "warped"), ("stem", "hyphae"))
    | variants(("stripped_crimson", "stripped_warped"), ("stem", "hyphae"))
)
COPPER_BLOCKS = {f"{wax}{age}{shape}" for wax in ("", "waxed_")
                 for age, shape in [("", "copper_block"), ("exposed_", "copper"), ("weathered_", "copper"),
                                    ("oxidized_", "copper")]}
COPPER_SHAPES = {f"{wax}{age}{shape}" for wax in ("", "waxed_") for age in ("", "exposed_", "weathered_", "oxidized_")
                 for shape in ("cut_copper", "chiseled_copper")}
FULL_BLOCKS |= COPPER_BLOCKS | COPPER_SHAPES
ORES = "coal copper diamond emerald gold iron lapis redstone".split()
FULL_BLOCKS |= variants(ORES + ["deepslate_" + ore for ore in ORES] + ["nether_gold", "nether_quartz"], ("ore",))
WALL_MATERIALS = set("""
andesite blackstone brick cinnabar cinnabar_brick cobbled_deepslate cobblestone deepslate_brick
deepslate_tile diorite end_stone_brick granite mossy_cobblestone mossy_stone_brick mud_brick
nether_brick polished_blackstone polished_blackstone_brick polished_cinnabar polished_deepslate
polished_sulfur polished_tuff prismarine red_nether_brick red_sandstone resin_brick sandstone
stone_brick sulfur sulfur_brick tuff tuff_brick
""".split())
STAIR_MATERIALS = (WALL_MATERIALS | WOODS | set("""
bamboo_mosaic dark_prismarine polished_andesite polished_diorite polished_granite prismarine_brick
purpur quartz smooth_quartz smooth_red_sandstone smooth_sandstone stone
""".split()) | variants(COLORS, ("wool", "concrete"))
                   | {prefix.replace("copper", "cut_copper") for prefix in COPPER})
SLABS = variants(STAIR_MATERIALS | {"cut_red_sandstone", "cut_sandstone", "petrified_oak", "smooth_stone"}, ("slab",))
NON_CONDUCTORS |= (
    variants(WALL_MATERIALS, ("wall",)) | variants(STAIR_MATERIALS, ("stairs",))
    | variants(WOODS | {"nether_brick"}, ("fence",))
    | variants(COLORS, ("stained_glass", "stained_glass_pane"))
    | variants((TREES - {"poplar"}) | {"red_poplar", "orange_poplar", "yellow_poplar",
                                       "azalea", "flowering_azalea"}, ("leaves",))
    | (COMPONENTS - FULL_BLOCKS)
)
KNOWN_BLOCKS = COMPONENTS | FULL_BLOCKS | NON_CONDUCTORS | SLABS | UNMODELLED


def is_conductor(state: State | None) -> bool | None:
    block = name(state)
    if block in SLABS:
        return state.get("type") == "double"
    if block in NON_CONDUCTORS:
        return False
    if block in FULL_BLOCKS:
        return True
    return None


def conducts(state: State | None) -> bool:
    # R17: the manual-check boundary takes precedence over physical conductivity.
    return not excluded(name(state)) and is_conductor(state) is True


def holds_wire(state: State | None) -> bool:
    block = name(state)
    return conducts(state) or block in {"glass", "tinted_glass", "glowstone", "hopper",
                                         "redstone_block", "observer", "piston", "sticky_piston",
                                         "sea_lantern"} or block.endswith("_stained_glass") or (
        block.endswith(("_slab", "_stairs")) and
        (state.get("type") == "top" or state.get("half") == "top")
    )


# R18: vanilla item stack limits. Content imports retain item IDs, not components.
LIMIT_16 = {"ender_pearl", "egg", "blue_egg", "brown_egg", "snowball", "bucket", "honey_bottle",
            "armor_stand", "written_book"}
LIMIT_1 = set("""
saddle potion splash_potion lingering_potion writable_book enchanted_book
totem_of_undying elytra trident bow crossbow shield fishing_rod shears flint_and_steel
mace brush carrot_on_a_stick warped_fungus_on_a_stick leather_horse_armor turtle_helmet
wolf_armor bundle shulker_box minecart mushroom_stew rabbit_stew beetroot_soup
""".split())
COMMON_ITEMS = set("""
stick cobblestone dirt oak_log iron_ingot gold_ingot copper_ingot diamond emerald coal charcoal
redstone redstone_torch repeater comparator redstone_block hopper dropper dispenser chest
barrel piston sticky_piston sugar_cane sugar paper book wheat wheat_seeds carrot potato
stone smooth_stone stone_bricks sand gravel glass torch oak_planks string rotten_flesh
gunpowder arrow bone bone_meal slime_ball quartz bamboo iron_nugget gold_nugget observer
""".split())


# Java 26.3 ItemIds and Items registrations, restricted to the supported families.
LIMIT_16 |= variants(WOODS, ("sign", "hanging_sign")) | variants(COLORS, ("banner",))
TOOL_MATERIALS = "wooden stone copper iron golden diamond netherite".split()
ARMOR_MATERIALS = "leather copper chainmail iron golden diamond netherite".split()
MOUNT_METALS = "copper iron golden diamond netherite".split()
DISCS = "13 cat blocks bounce chirp creator creator_music_box far lava_chicken mall mellohi stal strad ward 11 wait otherside relic 5 pigstep precipice tears".split()
LIMIT_1 |= (
    variants(TOOL_MATERIALS, ("sword", "spear", "pickaxe", "axe", "hoe", "shovel"))
    | variants(ARMOR_MATERIALS, ("helmet", "chestplate", "leggings", "boots"))
    | variants(MOUNT_METALS, ("horse_armor", "nautilus_armor"))
    | variants(TREES, ("boat", "chest_boat"))
    | variants(COLORS, ("shulker_box", "bundle"))
    | variants(("chest", "hopper", "furnace", "tnt", "command_block"), ("minecart",))
    | variants("water lava milk powder_snow pufferfish salmon cod tropical_fish axolotl sulfur_cube tadpole".split(),
               ("bucket",))
    | {"music_disc_" + disc for disc in DISCS}
    | {"bamboo_raft", "bamboo_chest_raft", "spyglass"}
)


def stack_size(item: str) -> tuple[int, bool]:
    item = item.removeprefix("minecraft:")
    if item in LIMIT_16:
        return 16, True
    if item in LIMIT_1:
        return 1, True
    return 64, item in COMMON_ITEMS or item in FULL_BLOCKS


def chest_pair(world: World, pos: Pos) -> list[Pos]:
    state = world[pos]
    if name(state) in CHESTS:
        for step in sides(state):
            other = at(pos, step)
            partner = world.get(other)
            if partner and partner.id == state.id and facing(partner) == facing(state):
                return [pos, other]
    return [pos]


def container_slots(world: World, pos: Pos) -> int | None:
    slots = CAPACITY.get(name(world.get(pos)))
    if slots is None:
        return None
    return slots * len(chest_pair(world, pos))


def container_signal(world: World, contents: Contents, pos: Pos) -> int:
    block = name(world.get(pos))
    if block not in CAPACITY:
        return 0
    halves = chest_pair(world, pos)
    if block in CHESTS and any(conducts(world.get(at(p, UP))) for p in halves):
        return 0
    units = 0
    for p in halves:
        for slot, stack in contents.get(p, {}).items():
            if 0 <= slot < CAPACITY[block] and stack.count > 0:
                size, _ = stack_size(stack.item)
                units += min(stack.count, size) * (64 // size)
    return 1 + units * 14 // (64 * CAPACITY[block] * len(halves)) if units else 0


def on(state: State, prop: str) -> bool:
    default = prop == "enabled" or prop == "lit" and name(state) in TORCHES
    return state.get(prop, str(default).lower()) == "true"


def power(state: State) -> int:
    text = state.get("power", "0")
    if text not in POWER_LEVELS:
        raise PlanError(f"{state.id}: expected power 0..15, got {text!r}")
    return int(text)


def dust_shape(world: World, pos: Pos, state: State) -> dict[str, str]:
    result = dict.fromkeys(HORIZONTAL, "none")
    for direction, step in HORIZONTAL.items():
        p = at(pos, step)
        other = world.get(p)
        block = name(other)
        if (holds_wire(other) and name(world.get(at(p, UP))) == WIRE
                and not conducts(world.get(at(pos, UP)))):
            partial_side = block == "hopper" or block.endswith("_slab") and other.get("type") != "double"
            result[direction] = "side" if partial_side else "up"
        elif (block in TORCHES | {WIRE, "lever", "redstone_block", "comparator"}
              or block.endswith(SWITCHES)
              or block == "repeater" and direction in (facing(other), OPPOSITE[facing(other)])
              or block == "observer" and direction == facing(other)
              or not conducts(other) and name(world.get(at(p, DOWN))) == WIRE):
            result[direction] = "side"
    connected = [d for d in HORIZONTAL if result[d] != "none"]
    if len(connected) == 1:
        result[OPPOSITE[connected[0]]] = "side"
    elif not connected and all(state.get(d) == "side" for d in HORIZONTAL):
        return dict.fromkeys(HORIZONTAL, "side")
    return result


class Signals:
    """Directional signal lookups for one round, including comparator block-entity output."""

    def __init__(self, world: World, analog: dict[Pos, int]):
        self.world = world
        self.analog = analog

    def signal_toward(self, src: Pos, toward: Pos) -> int:
        state = self.world.get(src, AIR_STATE)
        block = name(state)
        if block == "redstone_block":
            return 15
        if block in TORCHES:
            return 15 if on(state, "lit") and toward != support(src, state) else 0
        if block in WEIGHTED:
            return power(state)
        if block == "lever" or block.endswith(SWITCHES):
            return 15 if on(state, "powered") else 0
        if block in DIODES or block == "observer":
            if at(src, DIRECTIONS[facing(state)], -1) != toward:
                return 0
            if block == "comparator":
                return self.analog[src]
            return 15 if on(state, "powered") else 0
        if block == WIRE:
            if at(src, DOWN) == toward:
                return power(state)
            for direction, step in HORIZONTAL.items():
                if at(src, step) == toward and state.get(direction, "none") != "none":
                    return power(state)
        return 0

    def strong_into(self, pos: Pos) -> int:
        strongest = 0
        for src in neighbours(pos):
            state = self.world.get(src, AIR_STATE)
            block = name(state)
            if (block in TORCHES and at(src, UP) == pos
                    or (block == "lever" or block.endswith(SWITCHES)) and support(src, state) == pos
                    or block in DIODES or block == "observer"):
                strongest = max(strongest, self.signal_toward(src, pos))
        return strongest

    def weak_into(self, pos: Pos) -> int:
        return max((self.signal_toward(p, pos) for p in neighbours(pos)
                    if name(self.world.get(p)) == WIRE), default=0)

    def received_from(self, src: Pos, toward: Pos) -> int:
        if conducts(self.world.get(src)):
            return max(self.strong_into(src), self.weak_into(src))
        return self.signal_toward(src, toward)

    def component_signal(self, pos: Pos, exclude=()) -> bool:
        return any(self.received_from(p, pos) for p in neighbours(pos) if p not in exclude)

    def diode_rear(self, pos: Pos, state: State) -> int:
        rear = at(pos, DIRECTIONS[facing(state)])
        src = self.world.get(rear, AIR_STATE)
        if name(src) == WIRE:
            return power(src)
        return self.received_from(rear, pos)

    def diode_side(self, pos: Pos, state: State) -> int:
        strongest = 0
        for step in sides(state):
            p = at(pos, step)
            other = self.world.get(p, AIR_STATE)
            block = name(other)
            if block in DIODES:
                strongest = max(strongest, self.signal_toward(p, pos))
            elif name(state) == "comparator":
                if block == WIRE:
                    strongest = max(strongest, power(other))
                elif block == "redstone_block":
                    return 15
        return strongest

    def comparator(self, pos: Pos, state: State, contents: Contents) -> int:
        step = DIRECTIONS[facing(state)]
        rear = at(pos, step)
        beyond = at(rear, step)
        level = self.diode_rear(pos, state)
        if name(self.world.get(rear)) in CAPACITY:
            level = container_signal(self.world, contents, rear)
        elif (level < 15 and conducts(self.world.get(rear))
              and name(self.world.get(beyond)) in CAPACITY):
            level = container_signal(self.world, contents, beyond)
        side = self.diode_side(pos, state)
        if state.get("mode") == "subtract":
            return max(0, level - side)
        return level if level >= side else 0


def settle_dust(world: World, wires: list[Pos], signals: Signals) -> dict[Pos, State]:
    """Seed the wires from external power, then propagate over directed one-level steps."""
    strength = {}
    destinations = defaultdict(list)
    pending = deque()
    for p in wires:
        level = 0
        for src in neighbours(p):
            state = world.get(src)
            if conducts(state):
                level = max(level, signals.strong_into(src))
            elif name(state) != WIRE:
                level = max(level, signals.signal_toward(src, p))
        strength[p] = level
        if level:
            pending.append(p)
        for step in HORIZONTAL.values():
            side = at(p, step)
            if name(world.get(side)) == WIRE:
                destinations[side].append(p)
            if conducts(world.get(side)):
                # Higher wire sends down only over a conductor.
                src = at(side, UP)
                if name(world.get(src)) == WIRE and not conducts(world.get(at(p, UP))):
                    destinations[src].append(p)
            else:
                # Lower wire sends up past our support, including glass and top slabs.
                src = at(side, DOWN)
                if name(world.get(src)) == WIRE and holds_wire(world.get(at(p, DOWN))):
                    destinations[src].append(p)
    while pending:
        src = pending.popleft()
        for p in destinations[src]:
            if strength[src] - 1 > strength[p]:
                strength[p] = strength[src] - 1
                pending.append(p)
    return {p: world[p].with_props(power=str(strength[p]), **dust_shape(world, p, world[p]))
            for p in wires}


def derived(pos: Pos, state: State, signals: Signals, written: State,
            contents: Contents, analog: dict[Pos, int]) -> State:
    block = name(state)
    if block in TORCHES:
        powered = signals.received_from(support(pos, state), pos)
        return state.with_props(lit=str(not powered).lower())
    if block == "repeater":
        locked = signals.diode_side(pos, state) > 0
        powered = on(written, "powered") if locked else signals.diode_rear(pos, state) > 0
        return state.with_props(locked=str(locked).lower(), powered=str(powered).lower())
    if block == "comparator":
        analog[pos] = signals.comparator(pos, state, contents)
        return state.with_props(powered=str(analog[pos] > 0).lower())
    if block in PISTONS | EJECTORS:
        exclude = (at(pos, DIRECTIONS[facing(state)]),) if block in PISTONS else ()
        active = (signals.component_signal(pos, exclude)
                  or signals.component_signal(at(pos, UP), exclude=(pos,)))
        key = "extended" if block in PISTONS else "triggered"
        return state.with_props(**{key: str(active).lower()})

    active = signals.component_signal(pos)
    if block == "hopper":
        return state.with_props(enabled=str(not active).lower())
    if block == "redstone_lamp":
        return state.with_props(lit=str(active).lower())
    if block.endswith("_door"):
        lower = state.get("half", "lower") == "lower"
        other = at(pos, UP if lower else DOWN)
        partner = signals.world.get(other)
        if (partner and partner.id == state.id and
                partner.get("half", "lower") == ("upper" if lower else "lower")):
            active = active or signals.component_signal(other)
    if block.endswith(GATES) and (active or on(state, "powered")):
        setting = str(active).lower()
        return state.with_props(powered=setting, open=setting)
    # A manually opened, unpowered gate or door can rest open.
    return state.with_props(powered=str(active).lower())


def validate_state(pos: Pos, state: State) -> None:
    """Check written values used by the model; other Java block properties pass through."""
    if not state.props:
        return
    block = name(state)
    domains = {}
    if modelled(block):
        for key in power_keys(block):
            domains[key] = POWER_LEVELS if key == "power" else ("true", "false")
    if block in PISTONS | EJECTORS | {"observer", "piston_head", "barrel"}:
        domains["facing"] = DIRECTIONS
    elif block == "hopper":
        domains["facing"] = (*HORIZONTAL, "down")
    elif block in DIODES | CHESTS | {"redstone_wall_torch", "lever"} or block.endswith(("_button", *GATES, "_stairs")):
        domains["facing"] = HORIZONTAL
    if block == "lever" or block.endswith("_button"):
        domains["face"] = ("floor", "ceiling", "wall")
    if block == WIRE:
        domains.update(dict.fromkeys(HORIZONTAL, ("none", "up", "side")))
    if block == "comparator":
        domains["mode"] = ("compare", "subtract")
    elif block == "piston_head":
        domains["type"] = ("normal", "sticky")
        domains["short"] = ("true", "false")
    elif block.endswith("_slab"):
        domains["type"] = ("bottom", "top", "double")
    elif block.endswith(("_stairs", "_trapdoor")):
        domains["half"] = ("bottom", "top")
    elif block.endswith("_door"):
        domains["half"] = ("lower", "upper")
    for key, text in state.props:
        if key in domains and text not in domains[key]:
            raise PlanError(f"{pos}: invalid {state.id} property {key}={text}")


def initial_analog(world: World, comparators: list[Pos], contents: Contents, max_rounds: int) -> dict[Pos, int]:
    """Infer missing Java block-entity strengths from the frozen written circuit."""
    analog = {}
    powered = []
    for pos in comparators:
        state = world[pos]
        analog[pos] = 0
        if on(state, "powered"):
            powered.append(pos)
            front = world.get(at(pos, DIRECTIONS[facing(state)], -1))
            analog[pos] = max(1, power(front)) if name(front) == WIRE else 1

    # Connected comparators can depend on one another. Hold written wires/inputs
    # fixed while resolving their strengths; normal rounds then evolve all parts.
    for _ in range(min(len(powered), max_rounds)):
        signals = Signals(world, analog)
        # The written powered bit guarantees at least one until the first update.
        inferred = {pos: max(1, signals.comparator(pos, world[pos], contents)) for pos in powered}
        if all(analog[pos] == level for pos, level in inferred.items()):
            break
        analog.update(inferred)
    return analog


def solve(world: World, contents: Contents, max_rounds: int = 64) -> tuple[World, list[Pos]]:
    wires = []
    parts = []
    comparators = []
    for pos, state in world.items():
        block = name(state)
        validate_state(pos, state)
        if block == WIRE:
            wires.append(pos)
        elif (block in TORCHES | DIODES | PISTONS | EJECTORS | {"hopper", "note_block", "redstone_lamp"}
              or block.endswith(GATES)):
            parts.append(pos)
        if block == "comparator":
            comparators.append(pos)
    positions = wires + parts
    current = world.copy()
    for p in positions:
        state = current[p]
        defaults = {key: value(state, key) for key in power_keys(name(state)) if state.get(key) is None}
        if defaults:
            current[p] = state.with_props(**defaults)
    for p in wires:
        current[p] = current[p].with_props(**dust_shape(world, p, world[p]))
    analog = initial_analog(current, comparators, contents, max_rounds)

    def snapshot():
        return tuple((current[p], analog.get(p)) for p in positions)

    key = snapshot()
    history = [key]
    seen = {key: 0}
    for _ in range(max_rounds):
        # Dust reaches its network fixed point for these drivers. Every component
        # samples the previous round before either set of changes becomes visible.
        signals = Signals(current, analog)
        next_dust = settle_dust(current, wires, signals)
        next_analog = analog.copy()
        changes = {p: derived(p, current[p], signals, world[p], contents, next_analog) for p in parts}
        current.update(next_dust)
        current.update(changes)
        analog = next_analog
        key = snapshot()
        if key == history[-1]:
            return current, []
        if key in seen:
            cycle = history[seen[key]:]
            return current, sorted(p for i, p in enumerate(positions)
                                   if any(state[i] != key[i] for state in cycle))
        seen[key] = len(history)
        history.append(key)
    if len(history) == 1:
        return current, sorted(positions)
    # Without a full period, a part may change only on an earlier phase.
    return current, sorted(p for i, p in enumerate(positions) if any(state[i] != key[i] for state in history))


@dataclass
class Report:
    mismatches: list[tuple[Pos, str, str, str]] = field(default_factory=list)
    structural: list[tuple[Pos, str]] = field(default_factory=list)
    unsettled: list[Pos] = field(default_factory=list)
    unmodelled: list[tuple[Pos, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def structural_errors(world: World) -> list[tuple[Pos, str]]:
    errors = []
    paired = set()
    for pos, state in world.items():
        block = name(state)
        if block == "observer" and on(state, "powered"):
            errors.append((pos, "R9: an observer must be unpowered at rest"))
        if block not in PISTONS or not on(state, "extended"):
            continue
        front = at(pos, DIRECTIONS[facing(state)])
        head = world.get(front, AIR_STATE)
        kind = "sticky" if block == "sticky_piston" else "normal"
        if name(head) != "piston_head":
            errors.append((pos, "R14: extended piston has no head in front"))
        else:
            paired.add(front)
            if (facing(head) != facing(state) or head.get("type", "normal") != kind
                    or on(head, "short")):
                errors.append((front, f"R14: expected {kind} piston head facing {facing(state)} with short=false"))
    for pos, state in world.items():
        if name(state) == "piston_head" and pos not in paired:
            errors.append((pos, "R14: head has no matching extended base"))
    return sorted(errors)


def power_keys(block: str) -> tuple[str, ...]:
    if block == WIRE or block in WEIGHTED:
        return ("power",)
    if block in TORCHES or block == "redstone_lamp":
        return ("lit",)
    if block == "repeater":
        return ("powered", "locked")
    if block == "hopper":
        return ("enabled",)
    if block in PISTONS:
        return ("extended",)
    if block in EJECTORS:
        return ("triggered",)
    if block.endswith(GATES):
        return ("powered", "open")
    if block in {"comparator", "observer", "lever", "note_block"} or block.endswith(SWITCHES):
        return ("powered",)
    return ()


def value(state: State, prop: str) -> str | None:
    explicit = state.get(prop)
    if explicit is not None:
        return explicit
    if prop not in power_keys(name(state)):
        return None
    return "0" if prop == "power" else str(on(state, prop)).lower()


def power_diff(before: World, after: World) -> list[tuple[Pos, str, str]]:
    result = []
    for pos in sorted(before.keys() | after.keys()):
        a, b = before.get(pos, AIR_STATE), after.get(pos, AIR_STATE)
        if a != b and (modelled(name(a)) or modelled(name(b))):
            if any(value(a, key) != value(b, key) for key in POWER_PROPS):
                result.append((pos, format_state(a), format_state(b)))
    return result


def reason(state: State) -> str:
    block = name(state)
    if block in TORCHES:
        return "R2: torch lit state follows power at its support"
    if block == "repeater":
        return "R6: rear input and directional side lock determine repeater state"
    if block == "comparator":
        return "R7: rear and side inputs determine comparator output"
    if block == WIRE:
        return "R11: wire strength follows sources and dust attenuation"
    if block in PISTONS | EJECTORS:
        return "R13: direct or quasi-connectivity power determines activation"
    return "R15: resting activation follows the component signal"


def check_world(world: World, contents: Contents) -> tuple[World, Report]:
    settled, unsettled = solve(world, contents)
    report = Report(structural=structural_errors(world), unsettled=unsettled)
    for pos, written, expected in power_diff(world, settled):
        report.mismatches.append((pos, written, expected, reason(world[pos])))
    unmodelled = {}
    for pos, state in sorted(world.items()):
        if not modelled(name(state)):
            continue
        missing = False
        for p in neighbours(pos):
            other = world.get(p)
            if other is None:
                missing = True
            elif excluded(name(other)) or is_conductor(other) is None:
                desc = "trapped chest output" if name(other) == "trapped_chest" else other.id
                unmodelled[p] = f"R17: check {desc} by hand"
        if missing:
            x, y, z = pos
            report.warnings.append(f"{x} {y} {z}: neighbour not written by the plan; treated as air; "
                                   "pass --background to include the site")
    report.unmodelled = sorted(unmodelled.items())
    # A mismatch beside an unmodelled block may come from treating it as a non-conductor.
    report.mismatches = [
        (pos, written, expected,
         reason + "".join(f" (next to unmodelled {p[0]} {p[1]} {p[2]}; check by hand)"
                          for p in neighbours(pos) if p in unmodelled))
        for pos, written, expected, reason in report.mismatches]
    for p, slots in sorted(contents.items()):
        for slot, stack in sorted(slots.items()):
            if not stack_size(stack.item)[1]:
                report.warnings.append(f"{p[0]} {p[1]} {p[2]} slot {slot}: unknown item {stack.item}; "
                                       "assumed stack size 64")
    return settled, report


def switch_on(world: World, pos: Pos) -> World:
    state = world.get(pos, AIR_STATE)
    block = name(state)
    if block != "lever" and not block.endswith(SWITCHES):
        raise PlanError(f"{pos}: expected a lever, button or pressure plate, got {state.id}")
    copy = world.copy()
    if block in WEIGHTED:
        copy[pos] = state.with_props(power=str(max(1, power(state))))
    else:
        copy[pos] = state.with_props(powered="true")
    return copy
