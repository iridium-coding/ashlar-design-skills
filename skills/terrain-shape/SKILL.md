---
name: terrain-shape
description: >-
  Use when shaping or re-sculpting natural Minecraft Java terrain, including mountains,
  valleys, hills, rivers, lakes, coasts, islands, plateaus or the ground under a build.
  Builds through Ashlar with the exec-ashlar skill.
model: sonnet
effort: high
metadata:
  short-description: Shape natural terrain around the measured land and water.
---

# Shape natural terrain

Run `mc_status`. If Ashlar is unreachable, stop and tell the user. For a standalone request, start a project in `.minecraft-builder/<project>/`. For a design skill's build, use its project, datum, footprint as a pad, palette and plan. Add the terrain phases to that plan.

Run `exec-ashlar survey <project>` using `../exec-ashlar/reference/survey.md`. Capture heights over the terrain box plus at least 16 blocks and an exact site read with an eight-block horizontal margin, from the lowest seal through air above the tallest canopy. Check the top of the exact columns; extend a read that clips foliage. Run `terrain.py survey --site DIR --box X1 Y1 Z1 X2 Y2 Z2` on the actual terrain box. Record surface materials, liquid levels, trees, block entities and non-natural blocks. If the box contains a village or player structure, stop for the user's decision. Inspect ambiguous blocks and the approaches players use.

For standalone work, ask which landform, extent, character and viewing position the user wants. For a recognisable named wonder, hand the composition of its signature forms to `terrain-landmark`. For designed space underground (a cavern hall, a grotto, a passage or ravine below the surface), use `terrain-cave`. For a joint build, resolve any missing dimensions against its footprint.

- Claude Code: use `AskUserQuestion` for choices.
- Codex: use `request_user_input` when available.
- Otherwise: ask in plain text.

## Author and review

Write `terrain/<element>.recipe.json` as one continuous sampler graph. Set `element`, world `origin: [x1, 0, z1]`, `nx`, `nz`, `site.read` and `site.band`. Add `pads`, seeded `water` basins, `falls`, carve/build `forms` and `material.strata_top` where called for. Use a mask-driven MaterialSpec. See `reference/terrain/method.md` for the field, shore and approval rules, `reference/terrain/toolkit-api.md` for invocation and recipe keys, and `reference/landforms.md` for shape examples.

Design around existing water and lava first. Keep isolated water, its shore and trees according to the measured site. For a necessary drain, follow the dedicated per-body question and manifest checks in `reference/terrain/water.md`. Keep the existing biome for grading. Biome labels guide the palette and planting only.

Run `terrain.py field RECIPE --project DIR` for GATE A. Review the current files under `terrain/previews/`. Correct a failed check in the recipe and repeat. Review hillshade, relief and profile along with slope and eye-level views.

- Claude Code: use `Read` on the PNG files.
- Codex: use `view_image` on the PNG files.
- Otherwise: give the verify report's measurements and ask the user to open the files.

Get **design approval** on the renders, world and bounds, relief, changed cells, palette, planned water, liquid kept/covered/added, any drains, trees removed and reach, planting counts, custom-tree previews and phase order. Identify pending planting choices. Hand off to `terrain-ecology` with the field and recipe. A bare landform may need no planting. Show any revised counts, previews or scope and get approval of the final design before emission.

Emit with `terrain.py emit RECIPE --project DIR --first-phase N` (add `--standalone` for its own plan). For each approved drain, append `--drain-approved BODY_ID` once, for example `--drain-approved FIRST_ID --drain-approved SECOND_ID` for two approved bodies. Merge the phase and quality rows from `terrain/<element>.plan-rows.toon` with the host plan. Order site preparation and terrain mass, carve/build forms, flowing sources, host build, custom trees, vanilla features, ground cover, any separately approved biome phase, then entities. Hand off to `exec-ashlar build <project>` for **separate build approval** and fresh per-phase rollback points before any world write.

After building, verify the measured surface and seams, top and heightmap views, vertical x/z slices and edge-strip facades. Ask for an in-game look at hero terrain. Re-sculpt by editing the saved recipe and re-emitting as an iteration with fresh backups. A full rollback restores phases newest first.

## Six non-negotiables

1. Use one continuous field. Blend neighbouring shapes with a belt or sparse convolution.
2. No ziggurats. Materialise the heightfield into column stacks.
3. Drive the surface with masks for cliffs, snow, beaches and material mixes.
4. Verify at eye level. Review slope and eye-level views even when the top looks right.
5. Erode thermally, then hydraulically with `pad_cells`, before materialising.
6. Save the recipe, including the seeds, so a later edit preserves detail.
