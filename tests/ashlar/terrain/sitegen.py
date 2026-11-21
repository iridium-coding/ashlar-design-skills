"""Fixture writer shared by the terrain tests: build a small F1 site read.

    site = make_site(path, (0, 50, 0, 7, 80, 7), ground=64,
                     trees=[tree(2, 2, 65)], water={(6, 6): 62},
                     cells={(6, y, 6): "minecraft:dirt" for y in range(50, 59)})

``make_site(path, box, *, ground=64, water=None, cells=None, trees=(), world=None)``
writes the site with ``site.write_site`` and returns the ``Site``. Per column:
stone from the box's y1 up to ``ground - 1``, grass at ``ground``, air above.
``ground`` is an int, or a dict ``{(x, z): y}`` (columns not listed use 64).
``water`` is a dict ``{(x, z): level}``; such a column holds
``minecraft:water[level=0]`` from the box's y1 up to the level and air above
(no stone, no grass). ``cells`` is ``{(x, y, z): state}`` applied after the
columns and the water, overriding them. ``trees`` come from ``tree(...)`` and
are planted last: trunk cells always, leaf cells only where the column is air,
and anything outside the box is dropped.
"""
from __future__ import annotations

from pathlib import Path

from terrain.site import Site, write_site

Box = tuple[int, int, int, int, int, int]
Cells = dict[tuple[int, int, int], str]

AIR = "minecraft:air"
STONE = "minecraft:stone"
GRASS = "minecraft:grass_block[snowy=false]"
WATER = "minecraft:water[level=0]"
LOG = "minecraft:oak_log[axis=y]"
LEAVES = "minecraft:oak_leaves[distance=1,persistent=false]"


def tree(x: int, z: int, base: int, height: int = 5, radius: int = 2) -> dict[str, object]:
    """An oak: a log column from `base` up `height` cells and a leaf blob.

    The blob is every cell with dx^2 + dy^2 + dz^2 <= radius^2 + 1 around the top
    log, for dy in -1..2. Returns a dict that `make_site` plants (leaves only over air)."""
    top = base + height - 1
    trunk: Cells = {(x, y, z): LOG for y in range(base, top + 1)}
    leaves: Cells = {}
    for dx in range(-radius, radius + 1):
        for dz in range(-radius, radius + 1):
            for dy in range(-1, 3):
                if dx * dx + dy * dy + dz * dz <= radius * radius + 1:
                    cell = (x + dx, top + dy, z + dz)
                    if cell not in trunk:
                        leaves[cell] = LEAVES
    return {"trunk": trunk, "leaves": leaves}


def make_site(path: str | Path, box: Box, *, ground: int | dict[tuple[int, int], int] = 64,
              water: dict[tuple[int, int], int] | None = None,
              cells: Cells | None = None, trees=(), world: str | None = None) -> Site:
    x1, y1, z1, x2, y2, z2 = box
    ny = y2 - y1 + 1
    water = water or {}
    column: dict[tuple[int, int], list[str]] = {}
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            states = [AIR] * ny
            if (x, z) in water:
                for y in range(y1, min(water[(x, z)], y2) + 1):
                    states[y - y1] = WATER
            else:
                g = ground.get((x, z), 64) if isinstance(ground, dict) else ground
                for y in range(y1, min(g, y2 + 1)):
                    states[y - y1] = STONE
                if y1 <= g <= y2:
                    states[g - y1] = GRASS
            column[(x, z)] = states

    def put(cell: tuple[int, int, int], state: str, only_air: bool) -> None:
        x, y, z = cell
        if x1 <= x <= x2 and z1 <= z <= z2 and y1 <= y <= y2:
            states = column[(x, z)]
            if not only_air or states[y - y1] == AIR:
                states[y - y1] = state

    for cell, state in (cells or {}).items():
        put(cell, state, False)
    for planted in trees:
        for cell, state in planted["trunk"].items():  # type: ignore[union-attr]
            put(cell, state, False)
        for cell, state in planted["leaves"].items():  # type: ignore[union-attr]
            put(cell, state, True)

    columns: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
    for key, states in column.items():
        runs: list[tuple[int, int, str]] = []
        start = 0
        for i in range(1, ny + 1):
            if i == ny or states[i] != states[start]:
                runs.append((y1 + start, y1 + i - 1, states[start]))
                start = i
        columns[key] = runs
    site = Site(box=box, world=world, columns=columns)
    write_site(path, site)
    return site
