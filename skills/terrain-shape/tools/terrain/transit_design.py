"""Transit line designs: ``terrain/<element>.line.json`` parsed and validated.

A line design names two endpoints, optional via points, a mode (rail, road, path
or ice), a route kind (``search`` over a heights file or ``straight``) and the
limits, bridge, tunnel, light and booster rules the route search and the section
emitters follow. ``parse_line`` fills the spec defaults and raises ``ValueError``
naming the offending key.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from .site import integer_level

MODES = ("rail", "road", "path", "ice")
ROUTES = ("search", "straight")
STOPS = ("terminus", "room", "open")
KINDS = ("grade", "cut", "fill", "bridge", "tunnel", "tube")
BRIDGE_KINDS = ("auto", "beam", "arch")
DIMENSIONS = ("overworld", "nether")
ROLES = ("ballast", "surface", "edge", "deck", "pier", "lining", "railing", "guard",
         "lamp_post", "lamp", "end_block", "platform", "ice")
VERSION = "26.3"
TOP_KEYS = frozenset({
    "element", "seed", "world", "dimension", "mode", "route", "from", "to", "via", "heights", "avoid",
    "width", "lanes", "style", "palette", "profile", "limits", "bridges", "tunnels", "lights", "boosters",
    "sections", "version"})

_ELEMENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_BLOCK = re.compile(r"^(?:minecraft:)?[a-z0-9_]+$")


@dataclass(frozen=True)
class Endpoint:
    x: int
    y: int | None
    z: int
    stop: str | None


@dataclass(frozen=True)
class Limits:
    max_fill: int = 6
    max_cut: int = 8
    min_bridge: int = 4
    min_tunnel: int = 6
    water_clearance: int = 3
    fill_ratio: float = 1.5
    cut_ratio: float = 1.0
    rock_cut_ratio: float = 0.5


@dataclass(frozen=True)
class Boosters:
    flat: int = 24
    slope: int = 2


@dataclass(frozen=True)
class Bridges:
    kind: str = "auto"
    pier_spacing: int = 8
    railings: bool = True
    piers_in_water: bool = False


@dataclass(frozen=True)
class Tunnels:
    width: int
    height: int
    roof: int = 3


@dataclass(frozen=True)
class Lights:
    block: str
    spacing: int
    minimum: int


@dataclass(frozen=True)
class LineDesign:
    element: str
    seed: int
    world: str | None
    dimension: str
    mode: str
    route: str
    start: Endpoint
    end: Endpoint
    via: tuple[tuple[int, int], ...]
    heights: Path | None
    avoid: tuple[tuple[int, int, int, int], ...]
    width: int
    lanes: int
    style: str
    palette: dict[str, dict[str, int]]
    profile: tuple[tuple[int, float], ...]
    limits: Limits
    bridges: Bridges
    tunnels: Tunnels
    lights: Lights
    boosters: Boosters
    section_length: int
    version: str
    project: Path
    source: dict


def _p(**roles: dict[str, int]) -> dict[str, dict[str, int]]:
    return {role: {f"minecraft:{b}": w for b, w in blocks.items()} for role, blocks in roles.items()}


STYLES: dict[str, dict[str, dict[str, int]]] = {
    "stone": _p(ballast={"gravel": 3, "cobblestone": 1}, surface={"stone_bricks": 4, "stone": 2},
                edge={"stone_brick_slab": 1}, deck={"stone_bricks": 1}, pier={"stone_bricks": 4, "cobblestone": 1},
                lining={"stone_bricks": 5, "cracked_stone_bricks": 1}, railing={"stone_brick_wall": 1},
                guard={"stone_brick_wall": 1}, lamp_post={"stone_brick_wall": 1}, lamp={"lantern": 1},
                end_block={"stone_bricks": 1}, platform={"smooth_stone": 1}, ice={"packed_ice": 1}),
    "wood": _p(ballast={"gravel": 3, "coarse_dirt": 1}, surface={"spruce_planks": 4, "oak_planks": 1},
               edge={"spruce_slab": 1}, deck={"spruce_planks": 1}, pier={"spruce_log": 1},
               lining={"spruce_planks": 4, "stripped_spruce_log": 1}, railing={"spruce_fence": 1},
               guard={"spruce_fence": 1}, lamp_post={"spruce_fence": 1}, lamp={"lantern": 1},
               end_block={"stripped_spruce_log": 1}, platform={"spruce_planks": 1}, ice={"packed_ice": 1}),
    "cobble": _p(ballast={"gravel": 3, "cobblestone": 2}, surface={"cobblestone": 4, "mossy_cobblestone": 1},
                 edge={"cobblestone_slab": 1}, deck={"cobblestone": 1}, pier={"cobblestone": 3, "mossy_cobblestone": 1},
                 lining={"cobblestone": 5, "mossy_cobblestone": 1}, railing={"cobblestone_wall": 1},
                 guard={"cobblestone_wall": 1}, lamp_post={"cobblestone_wall": 1}, lamp={"lantern": 1},
                 end_block={"cobblestone": 1}, platform={"stone": 1}, ice={"packed_ice": 1}),
    "brick": _p(ballast={"gravel": 3, "stone": 1}, surface={"bricks": 4, "stone_bricks": 1},
                edge={"brick_slab": 1}, deck={"bricks": 1}, pier={"bricks": 1},
                lining={"bricks": 1}, railing={"brick_wall": 1}, guard={"brick_wall": 1},
                lamp_post={"brick_wall": 1}, lamp={"lantern": 1}, end_block={"bricks": 1},
                platform={"stone_bricks": 1}, ice={"packed_ice": 1}),
    "nether": _p(ballast={"netherrack": 3, "blackstone": 1}, surface={"polished_blackstone_bricks": 4, "blackstone": 2},
                 edge={"polished_blackstone_brick_slab": 1}, deck={"polished_blackstone_bricks": 1},
                 pier={"polished_blackstone_bricks": 3, "blackstone": 1},
                 lining={"nether_bricks": 5, "cracked_nether_bricks": 1}, railing={"nether_brick_fence": 1},
                 guard={"nether_brick_fence": 1}, lamp_post={"nether_brick_fence": 1}, lamp={"lantern": 1},
                 end_block={"nether_bricks": 1}, platform={"polished_blackstone": 1}, ice={"packed_ice": 1}),
}


# ------------------------------------------------------------------ validators
def _mapping(value, key: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object, got {value!r}")  # noqa: TRY004 - the design contract is ValueError
    return value


def _int(value, key: str, *, minimum: int | None = None) -> int:
    out = integer_level(value, key)
    if minimum is not None and out < minimum:
        raise ValueError(f"{key} must be at least {minimum}, got {out}")
    return out


def _ratio(value, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{key} must be a non-negative number, got {value!r}")
    return float(value)


def _flag(value, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false, got {value!r}")  # noqa: TRY004 - the design contract is ValueError
    return value


def _choice(value, key: str, options: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in options:
        raise ValueError(f"{key} must be one of {', '.join(options)}, got {value!r}")
    return value


def _block(value, key: str) -> str:
    if not isinstance(value, str) or not _BLOCK.match(value):
        raise ValueError(f"{key} must be a block id, got {value!r}")
    return value if value.startswith("minecraft:") else f"minecraft:{value}"


def _fields(data: dict, key: str, defaults: dict, convert: dict) -> dict:
    """The values of the object `data[key]` over `defaults`; unknown names are refused."""
    given = _mapping(data.get(key, {}), key)
    unknown = sorted(set(given) - set(defaults))
    if unknown:
        raise ValueError(f"{key}.{unknown[0]} is not a known setting")
    out = dict(defaults)
    for name, value in given.items():
        out[name] = convert[name](value, f"{key}.{name}")
    return out


def _endpoint(data: dict, key: str) -> Endpoint:
    node = _mapping(data.get(key), key)
    at = node.get("at")
    if not isinstance(at, (list, tuple)) or len(at) != 3:
        raise ValueError(f"{key}.at must be [x, y|null, z], got {at!r}")
    y = None if at[1] is None else integer_level(at[1], f"{key}.at y")
    stop = node.get("stop")
    if stop is not None:
        stop = _choice(stop, f"{key}.stop", STOPS)
    return Endpoint(integer_level(at[0], f"{key}.at x"), y, integer_level(at[2], f"{key}.at z"), stop)


def _pair(value, key: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{key} must be [x, z], got {value!r}")
    return integer_level(value[0], key), integer_level(value[1], key)


def palette_for(style: str, given) -> dict[str, dict[str, int]]:
    palette = {role: dict(blocks) for role, blocks in STYLES[style].items()}
    for role, blocks in _mapping(given, "palette").items():
        if role not in ROLES:
            raise ValueError(f"palette.{role} is not a role ({', '.join(ROLES)})")
        palette[role] = _weights(blocks, f"palette.{role}")
    return palette


def _weights(value, key: str) -> dict[str, int]:
    """A block id, or a ``{block: weight}`` map, as a normalised weighted-block map."""
    if isinstance(value, str):
        return {_block(value, key): 1}
    weights = _mapping(value, key)
    if not weights:
        raise ValueError(f"{key} needs at least one block")
    return {_block(b, key): _int(w, f"{key} weight", minimum=1) for b, w in weights.items()}


def _default_tunnel(mode: str, lanes: int, width: int) -> tuple[int, int]:
    return {"rail": (3, 4), "road": (4 * lanes + 2, 5), "path": (max(3, width + 2), 3), "ice": (3, 3)}[mode]


# ------------------------------------------------------------------ parse
def parse_line(data: dict, project_dir: Path) -> LineDesign:
    """Validate a line design dict and fill the spec defaults.

    Raises:
        ValueError: naming the key of the first invalid value.
    """
    data = _mapping(data, "line design")
    project = Path(project_dir)
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        hint = " (use sections.length)" if unknown[0] == "section_length" else ""
        raise ValueError(f"{unknown[0]} is not a known line design key{hint}")
    element = data.get("element")
    if not isinstance(element, str) or not _ELEMENT.match(element):
        raise ValueError(f"element must be a lowercase name, got {element!r}")
    seed = _int(data.get("seed", 0), "seed")
    world = data.get("world")
    if world is not None and not isinstance(world, str):
        raise ValueError(f"world must be text, got {world!r}")
    nether_world = world is not None and (world == "nether" or world.endswith("_nether"))
    dimension = _choice(data["dimension"], "dimension", DIMENSIONS) if "dimension" in data \
        else ("nether" if nether_world else "overworld")
    mode = _choice(data.get("mode"), "mode", MODES)
    route = _choice(data.get("route", "search"), "route", ROUTES)

    start, end = _endpoint(data, "from"), _endpoint(data, "to")
    if dimension == "nether" and route != "straight":
        raise ValueError("route must be straight in the Nether")
    if (dimension == "nether" or mode == "ice") and (start.y is None or start.y != end.y):
        raise ValueError(f"endpoints of a {'Nether' if dimension == 'nether' else 'ice'} line "
                             "need the same level (from.at and to.at y)")

    raw_via = data.get("via", [])
    if not isinstance(raw_via, (list, tuple)):
        raise ValueError(f"via must be a list of [x, z], got {raw_via!r}")  # noqa: TRY004 - the design contract is ValueError
    via = tuple(_pair(p, "via") for p in raw_via)
    raw_avoid = data.get("avoid", [])
    if not isinstance(raw_avoid, (list, tuple)):
        raise ValueError(f"avoid must be a list of [x1, z1, x2, z2], got {raw_avoid!r}")  # noqa: TRY004 - the design contract is ValueError
    avoid = []
    for box in raw_avoid:
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError(f"avoid must hold [x1, z1, x2, z2] boxes, got {box!r}")
        x1, z1, x2, z2 = (integer_level(v, "avoid") for v in box)
        avoid.append((min(x1, x2), min(z1, z2), max(x1, x2), max(z1, z2)))

    heights_raw = data.get("heights")
    if heights_raw is None:
        if route == "search":
            raise ValueError("heights is required for route search")
        heights = None
    elif not isinstance(heights_raw, str) or not heights_raw:
        raise ValueError(f"heights must be a file path, got {heights_raw!r}")
    else:
        heights = project / heights_raw

    width = _int(data.get("width", 3), "width", minimum=1)
    if width > 3:
        raise ValueError(f"width must be 1 to 3, got {width}")
    lanes = _int(data.get("lanes", 1), "lanes", minimum=1)
    if lanes not in (1, 2):
        raise ValueError(f"lanes must be 1 or 2, got {lanes}")
    style = _choice(data.get("style", "nether" if dimension == "nether" else "stone"), "style", tuple(STYLES))
    palette = palette_for(style, data.get("palette", {}))

    raw_profile = data.get("profile", [])
    if not isinstance(raw_profile, (list, tuple)):
        raise ValueError(f"profile must be a list of [index, level], got {raw_profile!r}")  # noqa: TRY004 - the design contract is ValueError
    profile = []
    for item in raw_profile:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"profile must hold [index, level] pairs, got {item!r}")
        profile.append((_int(item[0], "profile index", minimum=0), _ratio(item[1], "profile level")))

    convert = {k: (lambda v, key: _int(v, key, minimum=0))
               for k in ("max_fill", "max_cut", "min_bridge", "min_tunnel", "water_clearance")}
    convert.update({k: _ratio for k in ("fill_ratio", "cut_ratio", "rock_cut_ratio")})
    limits = Limits(**_fields(data, "limits", Limits().__dict__, convert))
    bridges = Bridges(**_fields(data, "bridges", Bridges().__dict__, {
        "kind": lambda v, k: _choice(v, k, BRIDGE_KINDS),
        "pier_spacing": lambda v, k: _int(v, k, minimum=1), "railings": _flag, "piers_in_water": _flag}))
    boosters = Boosters(**_fields(data, "boosters", Boosters().__dict__, {
        "flat": lambda v, k: _int(v, k, minimum=1), "slope": lambda v, k: _int(v, k, minimum=1)}))

    tw, th = _default_tunnel(mode, lanes, width)
    convert_tun = {k: (lambda v, key: _int(v, key, minimum=1)) for k in ("width", "height", "roof")}
    convert_tun["lining"] = _weights
    tun = _fields(data, "tunnels", {"width": tw, "height": th, "roof": 3, "lining": None}, convert_tun)
    if tun.pop("lining") is not None:
        palette["lining"] = _weights(data["tunnels"]["lining"], "tunnels.lining")
    nether = dimension == "nether"
    lit = _fields(data, "lights", {"block": "minecraft:shroomlight", "spacing": 4 if nether else 12,
                                   "min": 12 if nether else 1},
                  {"block": _block, "spacing": lambda v, k: _int(v, k, minimum=1),
                   "min": lambda v, k: _int(v, k, minimum=0)})
    if lit["min"] > 15:
        raise ValueError(f"lights.min must be at most 15, got {lit['min']}")
    lit["minimum"] = lit.pop("min")

    section_length = _fields(data, "sections", {"length": 96},
                             {"length": lambda v, k: _int(v, k, minimum=1)})["length"]
    version = data.get("version", VERSION)
    if not isinstance(version, str) or not version:
        raise ValueError(f"version must be text, got {version!r}")

    return LineDesign(
        element=element, seed=seed, world=world, dimension=dimension, mode=mode, route=route,
        start=start, end=end, via=via, heights=heights, avoid=tuple(avoid), width=width, lanes=lanes,
        style=style, palette=palette, profile=tuple(profile), limits=limits, bridges=bridges,
        tunnels=Tunnels(**tun), lights=Lights(**lit), boosters=boosters, section_length=section_length,
        version=version, project=project, source=data)


def load_line(path: Path, project_dir: Path | None = None) -> LineDesign:
    """Read and validate a ``<element>.line.json`` file.

    Args:
        path: The design file.
        project_dir: The project folder; defaults to the folder above ``terrain/``.
    """
    path = Path(path)
    if project_dir is None:
        project_dir = path.parent.parent if path.parent.name == "terrain" else path.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the line design {path}: {exc}") from None
    return parse_line(data, Path(project_dir))


# ------------------------------------------------------------------ geometry
def _points(design: LineDesign) -> list[tuple[int, int]]:
    return [(design.start.x, design.start.z), *design.via, (design.end.x, design.end.z)]


def link_length(design: LineDesign) -> float:
    """Euclidean x/z length of start, the via points in order, then end."""
    pts = _points(design)
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(pts))


def search_box(design: LineDesign) -> tuple[int, int, int, int]:
    """Bounding box ``(x1, z1, x2, z2)`` of start, via and end, grown by ``max(64, link_length // 4)``."""
    pts = _points(design)
    grow = max(64, int(link_length(design) // 4))
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - grow, min(zs) - grow, max(xs) + grow, max(zs) + grow


def formation_half(design: LineDesign) -> float:
    """Half the formation width in cells: rail 1.5, road (4 * lanes + 2) / 2, path width / 2, ice 2."""
    if design.mode == "rail":
        return 1.5
    if design.mode == "road":
        return (4 * design.lanes + 2) / 2
    if design.mode == "path":
        return design.width / 2
    return 2.0
