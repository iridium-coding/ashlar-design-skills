# Site survey

Run when a design skill asks for `survey <project>`, before it designs.

## Procedure

1. **Locate the site.**
   - Relative to a player ("here", "in front of me"): call `mc_players` and use
     that player's position, the block in front, or the block they look at.
   - Given coordinates or an earlier build: use them.
   - Neither: ask the user.
2. **Survey the ground** with `mc_survey` over the site plus a margin of at
   least 16 blocks on every side. Note min/max/median height, surface
   materials, water and lava, and the largest flat zone with its y.
3. **Look at it** with a top-view `mc_render` over the same area, and with
   facade views (`north`, `south`, `east`, `west`, y limited to the structure)
   of anything already standing on the site.
4. **Check existing structures and block entities** with `mc_inspect`
   (`stats`) over the planned footprint. List any signs, chests, barrels,
   banners, lecterns, shulker boxes or other block entities: a restore would
   empty them, so the approval gate must mention them.
5. **Biome**, only when the palette depends on it: infer it from the surface
   materials, or test candidates with the read-only
   `execute if biome <x> <y> <z> <biome>` (`commands.md`).
6. **Players**: note who is online and how close they are to the site.
7. **Other worlds**: before designing for the Nether or the End, call
   `mc_survey` with that world's name over a small area. If Ashlar refuses the
   world, tell the user the build cannot be placed there.

## survey.md

Write `.minecraft-builder/<project>/survey.md`:

```markdown
# Survey: <project>

- Date: <YYYY-MM-DD>
- World: <name, or "default">
- Site (x/z): <x1> <z1> → <x2> <z2>
- Ground: min <y>, max <y>, median <y>; <slope notes>
- Largest flat zone: <x1> <z1> → <x2> <z2> at y <y>
- Surface: <main materials>
- Water and lava: <where, or "none">
- Existing structures: <what and where, or "none">
- Block entities a restore would empty: <list with coordinates, or "none">
- Biome: <id and how it was read, or "not read">
- Players near the site: <names and distances, or "none">
- Notes for the design: <site preparation, hazards, views>
```
