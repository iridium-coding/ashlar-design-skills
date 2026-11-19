# Site survey

Run when a design skill asks for `survey <project>`, before it designs.

## Procedure

1. **Locate the site.**
   - Relative to a player ("here", "in front of me"): call `mc_players` and use
     that player's position, the block in front, or the block they look at.
   - Given coordinates or an earlier build: use them.
   - Neither: ask the user.
2. **Check for overlap.** Read `.minecraft-builder/registry.json`
   (`registry.md`). For every other project that is not `rolled-back`, compare
   its `bbox` with the site's x/z box. If the boxes overlap, say so and name the
   project; choose another site or ask the user before you design on it. If
   `<project>` itself is already in the registry and the user is not iterating
   that same build, stop and ask for another name: a reused name overwrites the
   old entry and shares its entity tag.
3. **Survey the ground** with `mc_survey` over the site plus a margin of at
   least 16 blocks on every side (around the planned footprint, or around the
   whole site box when the footprint is not chosen yet). Note min/max/median
   height, surface materials, water and lava, and the largest flat zone with
   its y. `mc_survey` heights are the y of the top solid block; the walking
   cell is one above (grass reported at 64 means feet at 65).
4. **Look at it** with a top-view `mc_render` over the same area, and with
   facade views (`north`, `south`, `east`, `west`, y limited to the structure)
   of anything already standing on the site.
5. **Check existing structures and block entities** with `mc_inspect`
   (`stats`) over the planned footprint to see what is there. Locate signs,
   chests, barrels, banners, lecterns, shulker boxes and other block entities
   with `mc_inspect` `columns` (or a `slice`), which give coordinates; `stats`
   does not. Tile the survey area into reads of at most 200,000 cells each. A
   restore would empty these block entities, so the approval gate must mention
   them.
6. **Biome**, only when the palette depends on it. Infer the biome from the
   surface materials. Run `execute if biome <x> <y> <z> <biome>`
   (`commands.md`) only when a player is near the site: console commands fail
   in unloaded chunks ("That position is not loaded"), and no force-load runs
   before the plan is approved. (`mc_command` is not pre-approved in this
   skill's `allowed-tools`; if it is unavailable, record "not read" and infer
   from surface materials.)
7. **Players**: note how many players are online and how close the nearest is
   (no names).
8. **Other worlds**: before designing for the Nether or the End, call
   `mc_survey` with that world's name over a small area. If Ashlar refuses the
   world, tell the user the build cannot be placed there.

## survey.md

Write `.minecraft-builder/<project>/survey.md`:

```markdown
# Survey: <project>

- Date: <YYYY-MM-DD>
- World: <name, or "default">
- Site (x/z): <x1> <z1> → <x2> <z2>
- Overlapping builds: <project and box, or "none">
- Build volume: <x/z box and the y range the design needs, or "as the plan">
- Footprint: <chosen footprint, or "not chosen">
- Ground: min <y>, max <y>, median <y>; <slope notes>
- Largest flat zone: <x1> <z1> → <x2> <z2> at y <y>
- Surface: <main materials>
- Water and lava: <where, or "none">
- Existing structures: <what and where, or "none">
- Block entities a restore would empty: <list with coordinates, or "none">
- Biome: <id and how it was read, or "not read">
- Players near the site: <count online and the nearest distance, no names, or "none">
- Notes for the design: <site preparation, hazards, views>
```
