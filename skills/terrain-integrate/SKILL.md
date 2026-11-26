---
name: terrain-integrate
description: >-
  Use with any Minecraft Java design whose footprint meets uneven or disturbed
  ground (included by default; the user may decline), when an existing build
  meets the land at a hard edge, or when existing terrain looks artificially
  graded.
  Builds through Ashlar with the exec-ashlar skill.
model: sonnet
effort: medium
metadata:
  short-description: Grade aprons around builds and naturalise existing terrain.
---

# Ground builds into the surrounding terrain

Integration is on by default. A design skill includes it whenever the ground along a footprint or paved edge is not flat and undisturbed (more than about 1 block from the planned level, or a cut face, fill or cleared edge), and the user may decline it at the design approval. Use it after the fact when an existing build needs an apron. Read the [terrain method](../terrain-shape/reference/terrain/method.md) and the [apron reference](reference/integration.md), including its [seating rules](reference/integration.md#seating-a-build).

## Choose the project

| Mode | Inputs and hand-off |
| --- | --- |
| Planned | Take the footprint rectangles, pad heights and palette from the design skill. Fit the pads and aprons to one field. Put the site-prep phases first in the host plan and assign any grading inside protected columns to the host. |
| After the fact | Survey the standing build and protect its bounding box. Use a standalone `<host>-ground` project with `grounds: "<host>"` in its registry entry. |
| Naturalise | Survey the existing ground and omit the protected region when landscaping without a footprint. Use a standalone project for a hostless site. |

## Dry run before approval

1. Survey through `exec-ashlar`. Capture fresh heights and an exact site read over the apron and its margins. Sample the palette in a shallow ring just outside the apron using `mc_inspect` with `format: "stats"`.
2. Run `terrain.py apron` offline with the site read, the intended bounds and the sampled stats. Every protected column is excluded from the apron writes. A coincident planned pad gives the apron its target height and the host grades that pad. The apron preserves existing water, lava and the biome.
3. Show the before-and-after renders, a profile across the seam and the delta stats (largest absolute change, mean absolute change and columns moved). If any column in the apron phases moves more than 6 blocks after rounding, obtain the user's explicit OK for that movement as part of design approval.
4. Give the approved phases, quality rows and preview evidence to `exec-ashlar build` for its execution gate. Verify each protected edge and the outer edges from fresh exact columns. Check planned pad seams after the host grades its protected pads.

For a path or rail cut into a wall, use the [sloped-back bench](reference/integration.md#sloped-back-bench). Plan all clears ahead of the ledge fills.
