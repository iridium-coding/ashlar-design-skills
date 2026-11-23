---
name: design-monument
description: >-
  Designs and blueprints monuments, sculptures, and build-art in a live
  Minecraft Java Edition world — giant statues, organic creatures and dragons,
  abstract sculpture, pixel art and murals, large 3D text and logos. Produces
  solid or shell-only figurative forms with no habitable interiors, using
  pixel-grid image mapping, organic-curve construction, palette-gradient
  mapping, and armor-stand detailing. Use when the user wants a statue,
  sculpture, monument, memorial, mural, pixel art, logo, giant text, or a
  large creature. Builds through Ashlar with the exec-ashlar skill.
model: opus
effort: high
---

# design-monument (Monument Builder)

You design **figurative and representational art** — statues, creatures,
abstract sculpture, pixel art, logos, giant text. Your output is a **solid or
shell-only form** with no habitable interior. Your job is the design:
classify the piece, research it, build it from the right technique, propose
blueprints, iterate until the user approves, and write a fully resolved plan.

This is a distinct discipline from its neighbours:

- `design-building` makes **buildings** — they have rooms and interiors.
- `terrain-landmark` makes **natural geology** — uncarved, naturalistic.
- `design-monument` (you) makes a **figure** — a representational shape, with
  no program inside it.

## When to use — and not

Use for a statue, sculpture, monument, memorial, mural, pixel art, mosaic,
logo, giant 3D text, or a large creature. Do not use for:

- A building with rooms → `design-building` (it owns a monument's
  habitable pedestal or viewing platform).
- Natural terrain or a natural wonder → `terrain-landmark` / `terrain-shape`.
- A redstone-animated sculpture (a moving mobile, a fountain) → `system-redstone`.

`terrain-shape`, `terrain-landmark` and `system-redstone` may not be installed.
If one is not, say so. In place of the terrain skills, offer a `site-prep` phase
for light grading only; say that a complex redstone build is out of reach
without `system-redstone`.

## Connection

Build tools come from the Ashlar MCP server (`mc_status`, `mc_players`,
`mc_survey`, `mc_render`, `mc_inspect`, `mc_snapshot`, `mc_restore`,
`mc_build`, `mc_command`). If one fails because the server is unreachable,
call `mc_status` once more after a few seconds; if it still fails, stop and
tell the user. The connection lives in the client's MCP settings, not in a
skill.

## Core principle

A monument reads when its **silhouette, proportion, and palette** are right —
not from raw size. A blocky 30-block figure with a true silhouette and a
weathered-copper gradient reads as the Statue of Liberty; a featureless
60-block mass does not.

Six techniques carry the work — pick the ones the piece needs:

1. **Pixel-grid image mapping** — quantize a reference image to a Minecraft
   block palette and lay it as a flat or low-relief grid. See
   `reference/pixel-art.md`.
2. **Organic-curve construction** — voxel spheres, stair-stepped curves, slab
   cascades for cloth, S-curves for limbs and coils. See
   `reference/sculpting.md`.
3. **Voxelization** — turning a 3D form into a block grid, algorithmically or
   from an imported model, authored as a parametric model you **render and
   verify before placing**. See `reference/render-verify.md` and
   `reference/sculpting.md`.
4. **Palette-gradient mapping** — copper oxidation for weathered bronze,
   marble blends, stone tones. See `reference/palettes.md`.
5. **Armor-stand detailing** — fine decorative elements and posed figures.
   See `reference/armor-stands.md`.
6. **Display entities** *(Java-exclusive)* — `text_display` for 3D floating
   text and logos, `block_display` for blocks at arbitrary scale/rotation/
   translation (sub-block detail, impossible angles, giant single-block
   forms), `item_display` for museum/pedestal items, and glowing tinted accent
   geometry on any of them. Bedrock cannot do this. See
   `reference/display-entities.md`.

## Render-verify first — never iterate a representational build blind

For any voxelized or parametric piece (a vehicle, creature, character, statue,
giant logo), **author a model you can see and verify it against the references
before placing a single block.** A wrong silhouette cannot be fixed by
detailing, and every in-world rebuild costs snapshots and time — so the cheap
iteration happens offline, on a render. The bundled `voxel` toolkit
(`tools/voxel/` in this skill's folder) authors a parametric numpy model,
renders three orthogonal views to PNG, then decomposes the verified model into
world fills that the `exec-ashlar` skill's placer sends to the server. After
building, confirm with `mc_render` facades and a top view — a visual pass, not
spot-checked coordinates. This is mandatory for representational forms. A simple
geometric piece written
as a few fills (an obelisk, a plinth, a plain column) is exempt: write the fills
directly and verify with `mc_render` after placing. The full recipe, the
toolkit, how to view the PNGs in your client, and the
"imported meshes are not authoritative" guardrail are in
**`reference/render-verify.md`**.

## Inputs

- **From `survey-research`** — reference images and cited real-world or
  canonical dimensions for any named monument or creature. For a named piece,
  run that skill first and record the citations in the registry so the build
  can be checked against them.
- **From the site survey** — the `exec-ashlar` skill's `survey <project>`: the
  site, space, and viewing angles.
- **From the user** — the adaptive interview (`reference/interview.md`).
- **From earlier builds** — `.minecraft-builder/registry.json`
  (`../exec-ashlar/reference/registry.md`), for iteration. Before choosing a
  site, check it against the other projects'
  `bbox`es; do not place a plan over another build without telling the user.

## Scale and the Java envelope

- The world spans Y −64 to 319. Most real monuments fit at 1:1; the very
  tallest (a 240 m statue) do not — offer a reduced scale, or split the base
  off to a `site-prep` phase or a `design-building` plinth, so the figure stays
  at 1:1.
- A large monument is built in tiles along natural anatomy seams (a waist, a
  neck, a limb joint), each its own phase or module, so every phase's
  snapshots stay within Ashlar's per-snapshot cap.
- For Ashlar's limits (blocks per call, chunk footprint, read volume, snapshot
  slots), follow the `exec-ashlar` skill's limits reference
  (`../exec-ashlar/reference/tools-and-limits.md`).

## Sibling coordination

A monument is often half of a collaboration. Name the seam explicitly in your
plan — which skill owns each part and where they meet — and sequence them as
Hand-off describes:

- **Carved into a cliff** (Mt. Rushmore, Bamiyan, Leshan) — `terrain-landmark`
  (or `terrain-shape`), if installed, makes the cliff; you make the figure
  carved into it.
- **Figure on a built pedestal** (Statue of Liberty, Christ the Redeemer) —
  `design-building` makes the pedestal if it is habitable; you make the
  figure; the two meet at a shared anchor coordinate.
- **Figure on an earth plinth** — `terrain-shape` (if installed) raises the
  plinth;
  otherwise a `site-prep` phase does.
- **Animated** (a fountain, a rotating mobile) — `system-redstone` (if
  installed) adds the
  redstone.

When the seam is a *group* of named masses the terrain sibling raises (several
buttes, temples, or spires in one formation), specify each as a **distinct mass
in the heightfield** — separated centers, contrasting profiles (broad mesa vs
narrow spire vs tri-lobed dome), saddles baked between them, varied summit
heights — and materialized in one pass. Say so in the plan and hand
`terrain-shape`/`terrain-landmark` (if installed) the per-mass centers and
profiles. Do not
let the sibling `np.maximum`-merge them into one broad mass on the theory you'll
separate them later by carving notches: post-hoc carving gives only modest
separation and tends to read as artificial slots.

Record the shared anchor coordinate in `.minecraft-builder/registry.json` so
whichever sibling skill runs next can use it.

## Process

1. **Classify** the piece — pixel art / statue / organic creature / abstract /
   text-logo.
2. **Interview** — `reference/interview.md`; record answers in
   `requirements.md`.
3. **Research** — use the `survey-research` skill's reference images and dimensions for a named monument or creature.
4. **Resolve scale** against the Java envelope; decide tiling.
5. **Select palette and technique** (`reference/palettes.md` and the technique
   files). The main mass is blocks; choose **display entities**
   (`reference/display-entities.md`) where they beat blockwork — 3D floating
   text and logos, fine detail below 1-block resolution, blocks at impossible
   angles or scaled up into giant single-block forms, and glowing tinted
   accent geometry. They are a late decoration phase, like armor stands.
6. **Coordinate siblings** — note in the plan any cliff, pedestal, or plinth a sibling skill owns and the shared anchor where it meets your figure (see Hand-off).
7. **Design into the plan** — write `plan.toon`, its phase files and module
   files per the `exec-ashlar` skill's plan format
   (`../exec-ashlar/reference/plan-format.md`). If a shell is available, stamp
   module phases with
   `../exec-ashlar/scripts/stamp.py` and check with `ashlar_place.py plan`;
   otherwise leave them for `exec-ashlar build`, which stamps and sizes them. A
   pixel-art grid or a voxelized
   form is a **generated grid**: write it as a phase file (a fills list) with a
   script, never as thousands of hand-written entries (more than 200 entries,
   the `mcp`
   phase cap in `plan-format.md`, means a generated grid and `via: placer`), and
   send it with the placer (`via: placer`). For a **large parametric form** (a
   vehicle, a
   creature), the reusable artifact is the **authoring script + the model
   `.npy`** (see `reference/render-verify.md`); record their location in the
   registry.

   When a tile repeats mirrored or turned (a left/right pair of wings, four
   faces of an obelisk), make it a module and add `placements` rows with
   `rotation` (0, 90, 180 or 270, clockwise from above) and `mirror` (`none`,
   `x` for east–west, `z` for north–south); `stamp.py` produces the phase file
   (`../exec-ashlar/reference/modules.md`). For weathered or scattered
   fragments, bake the decay into the module (remove the blocks you want
   missing) — Ashlar has no random-integrity placement.

   Queue **armor-stand detailing and display-entity decoration**
   (`reference/display-entities.md`) as the last phase, after all blockwork,
   as allowlisted `summon` commands, so fills don't disturb the entities.

   **Emit a `quality_contract` block** per that same plan format.
   For monuments and sculptures the contract should include:
   - **silhouette** rows asserting the outline is legible from the
     intended viewing distance (sample surface points; height variance
     must match the design).
   - **block_mix_ratios** rows for every named gradient or weathered
     surface (no monoculture cast of a bronze that's meant to read as
     oxidized).
   - **walkability** rows for any plinth, pedestal, or base the user is
     meant to approach.
8. **Render and iterate** — for a voxelized/parametric piece, run the
   **render-verify loop** (`reference/render-verify.md`): author the model,
   render three orthogonal views, compare to references, tune one parameter at
   a time, and re-render until they match — *then* show the user the renders
   alongside the usual blueprints (`reference/blueprints.md`). For non-voxel
   pieces, produce blueprints directly. Either way, revise and **loop until the
   user approves**.
   - If the user provides (or a faithful one already exists for the *named*
     subject) a 3D model file, **voxelize it instead of hand-authoring** — it
     captures proportions you'd otherwise guess; see `reference/mesh-import.md`.
   - For a **posed character** — clothing on a leaning body, raised arms, a
     cape — see `reference/figures.md` (body/limb labeling, vertex posing, arc
     garments).
9. **Hand off** — write the plan, register the monument in
   `.minecraft-builder/registry.json` (add or update only this project's entry;
   see `../exec-ashlar/reference/registry.md`), and follow Hand-off below.

## Reference library

Read the file for the step you are on — do not load them all up front:

| File | Covers |
| ---- | ------ |
| `reference/render-verify.md` | The render-before-you-place loop: author a parametric model, render 3 views, iterate vs. references, decompose to fills, place them with the exec-ashlar placer, check with `mc_render`. Toolkit API + the imported-mesh guardrail. |
| `reference/mesh-import.md` | Voxelizing a user-provided/real 3D model (`.3mf`/`.obj`/`.stl`) when one exists for the named subject — the pipeline, `.3mf` slicer gotchas, optional deps, and the render-it-first guardrail. |
| `reference/figures.md` | Posed characters — labeling voxels body-vs-limb by nearest mesh vertex, posing by rotating limb vertices, arc (not slab) garments, padded grids for accessories, and re-costuming one base for a themed series. |
| `reference/catalog.md` | Real-world monuments, pop-culture creatures, abstract and land art — schema and examples. |
| `reference/pixel-art.md` | Pixel-grid image mapping and the pixel-art, mural, text, and logo guidance. |
| `reference/sculpting.md` | Organic-curve construction and voxelization technique. |
| `reference/palettes.md` | Palette-gradient mapping — copper oxidation, marble, stone, skin and metal families. |
| `reference/armor-stands.md` | Armor-stand detailing — Java NBT poses, equipment, decorative patterns. |
| `reference/display-entities.md` | Java-exclusive display entities — `block_display` / `item_display` / `text_display`: transformation (scale/rotation/translation), billboard, glow, 3D text and logos, sub-block detail, giant blocks, museum items. |
| `reference/interview.md` | The adaptive interview decision tree. |
| `reference/blueprints.md` | Rendering modes and the validation checklist. |

## Hard rules

- **Place no blocks while designing.** After the user approves the plan, the
  `exec-ashlar` skill builds it (`build <project>`).
- **No habitable interiors** — solid or hollow shell only. A shell is required
  for any monument whose solid volume is impractical. A viewing platform
  inside the figure belongs to `design-building` — flag it and run that skill for it.
- **Tile large forms along anatomy seams** so every phase stays within Ashlar's limits; stay within Y −64 to 319.
- **Get the silhouette right** — a monument that does not read as its subject
  is a failure, however clean the blockwork.
- **Render-verify before placing** — for any voxelized/parametric form, author
  and render the model and confirm it against the references *before* any
  in-world placement, and check the built result with `mc_render`. Never
  iterate a representational build blind. (`reference/render-verify.md`)
- **No `/random`** — bake any variation into the design; console commands only as `../exec-ashlar/reference/commands.md` allows.
- **Defer** the pedestal, the cliff, the plinth, and any animation — name the
  sibling skill that owns each in the plan (see Hand-off).

## Hand-off

State the piece back to the user — subject, technique, scale, palette, tile
plan — and confirm `plan.toon` is written. You sequence the
next steps yourself, in this order:

1. **Siblings first**: any cliff, plinth or pedestal. Use the `terrain-shape`
   or `terrain-landmark` skill if it is installed; otherwise add a `site-prep`
   phase (clearing, levelling, pads, filling holes, soft-edged terraces) and
   tell the user if the site needs more than that (more than light levelling, a
   pad and a few terraces). A habitable pedestal goes to
   the `design-building` skill. They meet the figure at the recorded anchor.
   If a pad would sit more than about 1–2 blocks above or below the surveyed
   ground at any edge, offer the `terrain-integrate` skill for the site
   preparation instead: it designs the pad and a natural apron around it as the
   first phases of this plan.
2. **Build**: use the `exec-ashlar` skill (`build <project>`). Voxelized forms
   go through the placer; armor stands and display entities run last as
   allowlisted `summon` commands.
3. For a display-heavy piece (3D text, logos, glowing accents), ask the user to
   look at the first placed display in game before the rest are summoned.
