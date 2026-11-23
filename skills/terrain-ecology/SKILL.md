---
name: terrain-ecology
description: >-
  Use when planting existing or designed Minecraft Java terrain, choosing a plant community,
  or designing custom trees. Builds through Ashlar with the exec-ashlar skill.
model: sonnet
effort: medium
metadata:
  short-description: Design plant communities and preview custom trees.
---

# Plant a landscape

Start with the designed field and recipe from `terrain-shape` or `terrain-landmark`. For existing land, use the survey heights and an exact site read for soil, retained water, trees and structures. Use the host build's project, datum, palette and protected footprint, or start a standalone planting project with `exec-ashlar survey <project>`. Check the running version with `mc_status`. Retry once if disconnected, then stop if the connection remains unavailable. Record the literal destination world from the survey and resolve any structures or overlapping builds before design. See `../terrain-shape/reference/terrain/method.md` for the terrain workflow and `../terrain-shape/reference/terrain/toolkit-api.md` for the local launcher.

## Design the planting

1. Walk the site on the survey images. Identify the canopy stands, glades, damp banks and open ground. Blend the species mix and density across their edges. Use `reference/ecology.md` to plan canopy first, then understory, then ground cover. Preserve paths, sightlines, shore access, existing trees and player builds over the **whole growth footprint**. Bare rock or an open meadow may need no trees.
2. Grow vanilla trees with `place feature`. Check every proposed ID with `terrain.py ids --version V --features A,B`. Resolve unknown entries before approval. If the toolkit falls back to the nearest older list, name both versions at design approval. Check the feature's vegetation type, substrates and full reach in the running version's game data. Choose a bounded alternative if the reach is unknown. For a hero tree or a shape vanilla does not grow, design it with the generator in `reference/custom-trees.md` and show its previews before including it.
3. Design the ecology **before terrain emission**. Show the user the mix and counts by layer, density, spacing, protected areas, custom-tree views, world, growth bounds, version evidence and phase order. Record the approved design and a one-line species/density summary in the project. Give any proposed biome change its own decision below.

## Biome decision

1. Keep the world's existing biome by default. Choose the palette, species and water to suit it.
2. Consider changing it only when the user requested a look or behaviour that depends on snowfall and snow cover, grass/foliage/water colour, fog, sky or mob spawning. Keep the existing biome for grading and site preparation. A procedural `BiomeField` label guides offline palette and species choices only. Never use it to propose or select a biome to paint.
3. Ask the user to **name the exact biome ID**. Verify it with `terrain.py ids --version V --biomes ID` and resolve any fallback against the running version. Use `plant --biome-only --biome-preview ID` to preview the box without writing phases. Resolve any default-world label against the survey. Show the literal world and exact inclusive six-coordinate box after expansion to complete 16 × 16 chunks in x/z and four-block biome cells in y. Explain the purpose and that rollback restores one recorded biome per chunk across the affected height, so local and vertical variation can be lost. Ask separately, “Do you approve changing this expanded box to the biome you named?” Include the literal world, coordinates, purpose and ID in that question and wait for the answer.

   - Claude Code: use `AskUserQuestion` for the dedicated biome decision.
   - Codex: use `request_user_input` when available.
   - Otherwise: ask in plain text.

4. Record the answer in `requirements.md`, including the approved ID, world and exact box for a yes. Then use `plant --biome-only --biome-change ID --phase N` with the dedicated final phase number. Check that every `fillbiome` paints that single ID and that the command boxes together match the approved volume. Without a yes, build with the existing biome and tell the user which requested effects will look different.
5. Tell the user that biome colours appear once players' chunks reload.

## Write the approved phases

For designed terrain, emit the approved mass first, then write the planting and update its final `terrain/<element>.surface.json` (F6). A later mass emission regenerates that file. Reapply planting skips after any re-emission. Order the ecology phases **custom trees → vanilla canopy and understory → ground cover → any separately approved biome change last**. The feature file can contain all three vanilla layers in order. Put additional stamped ground details before the biome phase. Its position makes the biome change the first ecology phase rolled back.

Save the custom modules, placements and stamped vegetation phase, the features commands file and, when approved, the separate biome commands file. Merge their phase rows and bounds into the project plan. Verify the final surface mask covers the projected vanilla wood footprint and every stamped custom wood column above the bed. Return the species/density summary with the plan to `exec-ashlar build <project>` for separate build approval and per-phase backups. After planting, check the stands at eye level, measure the remaining clearances and inspect the runner's placement failures before accepting the result.
