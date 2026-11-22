# Modules and stamping

Ashlar has no structure templates, so a repeated element is a **module file**
that `scripts/stamp.py` places as many times as needed, turned and mirrored as
the layout requires.

## Module file

`.minecraft-builder/<project>/modules/<name>.json`, in local coordinates with
the minimum corner at `[0, 0, 0]`:

```json
{
  "name": "small-house-a",
  "size": [9, 8, 7],
  "fills": [
    {"from": [0, 0, 0], "to": [8, 0, 6], "block": "minecraft:cobblestone"},
    {"from": [0, 1, 0], "to": [8, 4, 6], "block": "minecraft:spruce_planks", "mode": "walls"}
  ],
  "blocks": [
    {"pos": [4, 1, 0], "block": "minecraft:spruce_door[facing=north,half=lower,hinge=left]"},
    {"pos": [4, 2, 0], "block": "minecraft:spruce_door[facing=north,half=upper,hinge=left]"}
  ]
}
```

- `size` is `[width (x), height (y), depth (z)]`; every coordinate must lie
  inside it.
- Build each module with its front facing north (toward −z), so placement
  rotations read naturally.
- Modules may not contain `text`; put lettering in its own `mcp` phase. A block
  entry with a `sign` object is allowed in a module.
- Palette variants are separate module files (`small-house-a-birch.json`).

## Vegetation modules

A module with `"kind": "vegetation"` is a tree or shrub. Instead of `fills` and
`blocks` it has three parts, `ground`, `wood` and `leaves`, each with its own
`fills` and `blocks`, plus an `anchor` (`[ax, ay, az]`, the trunk base cell).
There are no air cells.

```json
{"name": "oak-a", "size": [7, 9, 7], "kind": "vegetation", "anchor": [3, 0, 3],
 "ground": {"fills": [], "blocks": [{"pos": [3, 0, 3], "block": "minecraft:dirt"}]},
 "wood": {"fills": [], "blocks": []},
 "leaves": {"fills": [], "blocks": []}}
```

- Vegetation placements may overlap each other, never another module.
- Stamping writes the whole phase in this order: every placement's `ground`
  part, then every `wood` part, then every `leaves` part. Wood and leaves are
  fills with `"filter": "minecraft:air"`, so they never replace terrain or
  another tree's wood, and wood never gives way to leaves. Single cells become
  1 x 1 x 1 fills (merged where possible), because `blocks` entries cannot carry
  a filter. `ground` is placed without the filter.
- Rotation and mirroring work as for any module (log `axis` turns).
- A placement's origin comes from the tree's `anchor` and the surface height at
  the trunk, which the terrain skill computes.

## Placement convention

For each placement, `stamp.py`:

1. mirrors the module (`none`; `x` flips east–west; `z` flips north–south);
2. rotates it clockwise as seen from above (`0`, `90`, `180`, `270`);
3. moves it so its minimum corner sits at `origin`.

Block states turn with it: `facing`, sign and banner `rotation`, log `axis`,
stair and rail `shape`, door `hinge`, crafter `orientation`, and the side
properties of vines, lichen and mushroom blocks. Fence, wall, pane, bar and
redstone-wire connections are dropped because Ashlar's connection pass
recomputes them. Chest `type` becomes `single`; Ashlar pairs chests itself.
Placements must not overlap; `stamp.py` refuses overlapping instances (vegetation
placements may overlap each other; see above).

## Running it

Run from the workspace root, with `<skill>` as the `exec-ashlar` skill's folder
(`SKILL.md` explains how to find it in your client):

```bash
python3 <skill>/scripts/stamp.py .minecraft-builder/<project>/modules/small-house-a.json --at=104,64,-358 --rotate 90 --mirror x --out .minecraft-builder/<project>/phases/02-house-a.json
python3 <skill>/scripts/stamp.py --placements .minecraft-builder/<project>/plan.toon --modules .minecraft-builder/<project>/modules --phase 2 --out .minecraft-builder/<project>/phases/02-houses.json
```

Write `--at=X,Y,Z` with the equals sign; a negative X would otherwise be read
as an option. Then check the result with
`python3 <skill>/scripts/ashlar_place.py plan <phase file>`.

## Recording

List every module in `plan.toon` `modules`, every instance in `placements`, and
both in the project's registry entry (`registry.md`), so the build can be
extended or repaired later.
