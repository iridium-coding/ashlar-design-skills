---
name: terrain-landmark
description: >-
  Use when designing a recognisable natural wonder in Minecraft Java, such as
  the Grand Canyon, Niagara, Uluru, Halong Bay, Bryce Canyon or Devils Tower.
  Builds through Ashlar with the exec-ashlar skill.
model: sonnet
effort: high
metadata:
  short-description: Design natural wonders with recognisable signatures and proportions.
---

# Design a natural landmark

Make the wonder recognisable through **2–4 signature features at credible
relative proportions**. Banded walls, a meandering river and perpendicular side
canyons make the Grand Canyon recognisable at Minecraft scale.

Follow `terrain-shape` for connection, survey, project rules, offline review,
design approval, planting, emission and build hand-off. Start with `mc_status`
and stop if Ashlar is unreachable. Run `exec-ashlar survey <project>` and the
terrain site read. If the box contains a village or player structure, stop for
the user's decision. Use the host project and plan when part of another build.
Read the [shared method](../terrain-shape/reference/terrain/method.md) and apply
all six `terrain-shape` non-negotiables.

## Confirm the composition before writing a recipe

For a named wonder, hand off to `survey-research` for independent evidence of
dimensions, proportions, materials and signature features. Use its research
files to prepare the proposal. Put the sources in the project's `citations`
when writing the [registry entry](../exec-ashlar/reference/registry.md).

Propose the wonder, its **2–4 signatures**, the footprint and proportions
against the [recognition floor](reference/wonders.md), the
[palette](reference/palettes.md) and one or two alternatives. Flag any proposed
exception to the recognition floor. Wait for the user's confirmation before
authoring the recipe.

## Compose the field and forms

Combine two to five reusable [primitives](reference/primitives.md) into one
continuous sampler graph. The same `hoodoo-spire` using `Cellular(inv_F1)`
serves Bryce and Cappadocia. The same `karst-tower` serves Halong and Guilin.
For visible strata, use `MaterialSpec` strata bands with `material.strata_top`
anchored at world Y so the band sequence carries through the cut walls.
Set `"skill": "terrain-landmark"` in a standalone recipe.

Use recipe `forms` for 3-D carves and build-ups that a heightfield cannot hold.
Author and render voxel assets offline with the `design-monument` voxel toolkit.
Set `name`, project-relative `model` and `palette` paths, world `origin` and
`mode` (`carve` or `build`) as described in the
[toolkit API](../terrain-shape/reference/terrain/toolkit-api.md#site-recipe).
Follow [build sequencing](reference/sequencing.md) for the mass, forms,
weathering and flowing sources.

Keep and design around existing water and lava. If the design needs a drain,
follow the [per-body approval and manifest procedure](../terrain-shape/reference/terrain/water.md).
Keep the existing biome for grading. `terrain-ecology` handles any biome change
through separate approval for the biome named by the user.

## Verify the signatures

For each signature, define a test with a region or viewpoint, a target and a
tolerance before previewing. Measure visible strata count on a wall profile,
width-to-height ratio within the chosen 10–20% tolerance, or the planned curve
of a horseshoe brink. Run those tests offline alongside GATE A from
`terrain.py field`. Review the slope and eye-level views of the terrain mass.
When the composition or a signature depends on a 3-D form, prepare and review
a [combined scene or section](reference/sequencing.md#preview-a-3-d-signature)
before asking for design approval. Add the target, observed value, verdict and
evidence path to `terrain/previews/<element>.verify.txt` after the command runs.
Revise the recipe and repeat if a check fails. At design approval, name each
signature that could not be measured and mark it **checked by eye**.

Get `terrain-shape`'s design approval on the renders, measurements and scope.
Hand off to `terrain-ecology` for planting and account for its output before
final design approval. Emit through `terrain-shape` and keep the current
signature results in `terrain/<element>.verify.txt`. Alongside the generated plan
rows, write `acceptance` cells with the phase, exact coordinates and expected
block (for example, a band block in a cut wall). Use `silhouette` and
`block_mix_ratios` rows under `quality_contract` for the relevant profiles and
material regions. See the [plan format](../exec-ashlar/reference/plan-format.md).

Hand off to `exec-ashlar build <project>` for separate build approval before
world writes. Check the built signatures, including eye-level views, using the
[signature checklist](reference/anti-patterns.md) and `exec-ashlar` verification.
Ask for an in-game look at hero terrain. Correct a failed signature by editing
the saved recipe and re-emitting through the same approval flow.
