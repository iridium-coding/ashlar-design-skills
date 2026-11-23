# Build sequencing

Mixing carve-first and build-up-first is the single most common landmark
failure. Each [primitive](primitives.md) is tagged with its method. Use the
field for continuous terrain and the recipe's `forms` entries for 3-D geometry.
The emitter places the terrain mass, then the carve entries, then the build
entries. Within each mode it keeps recipe order, so list primary forms before
secondary forms of the same mode.

## Carve-first

Place a **solid substrate mass first**, then cut the form out of it with
air-fills. The cut walls inherit the substrate's stratigraphy — which is the
whole point for anything where you see *into* the rock.

Carve-first primitives: canyons, slot canyons, side canyons, cenotes, fjords,
lava tubes, sea arches, caldera bowls.

For these: build the `canyon-strata-stack` (or stone mass) completely, *then*
carve. Never carve into a hollow or unbanded mass — the walls will be wrong.

## Build-up-first

Add material **outward from the base or centre**. The outer shell is what
receives the weathering pass, so it must be the last solid geometry placed.

Build-up-first primitives: volcanoes, monoliths, inselbergs, hoodoos, mesas,
sea stacks, karst towers, dunes, travertine terraces, icebergs, granite domes,
columnar basalt.

## Preview a 3-D signature

`terrain.py field` draws its PNGs from the mass heightfield. The F6 expected
surface records only column tops for form geometry. For a signature that
depends on a 3-D form, build a combined scene or section offline before design
approval:

1. Load the existing F1 site with `terrain.site.load_site` and decode the block
   runs over the region or section needed for the signature.
2. Use the same field, material, water, drain and protection inputs as the
   GATE A preview. Overlay the mass from `terrain.live.materialize_live`,
   followed by the results of `terrain.forms.form_write` for each form loaded
   with `terrain.forms.load_form`. Apply all carves first, then all build-ups,
   in recipe order within each mode. Place each write at its world `origin`,
   leave code zero unchanged and decode each other cell through that write's
   palette, including explicit air writes.
3. Render the combined block scene as a `VoxelModel` with `voxel.render_views`
   ([render guide](../../design-monument/reference/render-verify.md)), or save
   a labelled block section if it shows the whole signature. For an undercut,
   a slice can show the open recess below intact rock and its depth. Keep the
   view with the GATE A previews. Record its coordinates or viewpoint and the
   measurement in the signature check.

## Still basins before flowing lips

Place **flowing lip sources** after all surrounding geometry is in place.

- Shape the plunge pool and fill its sealed basin with still water in the
  terrain mass phase. A few blocks of depth is usually enough. Use up to about
  12 blocks for a large fall. The pool is already full when the fall starts.
  The banks and outlet govern sideways spread, so choose the depth for the
  visible pool profile.
- Fill large still bodies to a level surface with still water. Use only lip
  sources in the later `liquids: "flow"` phase. The placer caps each call at
  2,000 flowing cells.
- Use the emitter's conservative flow box for the phase bounds and back up
  the full box before placing lip sources. It accounts for sideways spread,
  renewed spread after a drop and formation of new sources. Read or redesign
  the site if possible flow reaches beyond the measured area. Follow the
  [shared water rules](../../terrain-shape/reference/terrain/water.md) for
  existing liquid and drains.

## Weathering passes

Design weathering on the exposed shell, after the main geometry is defined
and before decoration.

1. Model the form clean and smooth.
2. Author a weathering patch as seeded variants in `modules/<name>.json`.
   For a weathered overlay, keep about 30–70% of the candidate detail blocks.
   Derive the seed from the project, primitive and instance index and save the
   chosen variants so the result can be rebuilt.
3. Use [`stamp.py`](../../exec-ashlar/reference/modules.md) offline to position
   the chosen variants. Incorporate the positioned edits into the recipe's
   voxel assets so previews and checks cover the placed shell. Chips in the
   substrate are carve masks. Bake chips in added forms into the build asset,
   since carve entries run before build entries. Verify support and water
   containment on the resulting geometry.

Exception: **do not weather ordered formations** — a Bryce hoodoo field reads
as carved and orderly, not eroded.

## Decoration last

Pointed dripstone, vines, glow lichen, moss carpet, flowering azalea, and
saplings go on after the geometry and water phases. Use `coarse_dirt` /
`rooted_dirt` as the substrate next to rock to block grass spread.

## Lighting tricks

Light placed *behind* translucent blocks gives effects vanilla cannot
otherwise: `glowstone` behind orange terracotta for a Bryce sunset glow; a
sea lantern or ochre froglight beneath blue ice for a glacier glow; `magma_block`
as ambient floor light in a lava tube. Plan these into the build, not as an
afterthought.

## Multi-mass groups: author distinct in the field

When a wonder is several named masses (Kata-Tjuta domes, Twelve Apostles, a line
of buttes), give each its own mass in the heightfield *before* materializing —
separated centres, varied summit heights, a saddle baked into the field between
neighbours, and contrasting profiles (broad mesa vs narrow spire vs tri-lobed
dome) — then materialize once. Do not `np.maximum`-merge two broad masses into a
single blob and try to split them afterward by carving notches: the merge reads
as one butte, and the post-hoc slots read as artificial. Separation lives in the
recipe, not in a corrective carve.

## Standard landmark build order

1. Substrate and strata stack or core mass, including sealed still-water
   basins. Author distinct masses in the field for a multi-mass group.
2. Carve forms, primary cuts before secondary cuts, including the exposed
   substrate's chipping masks.
3. Build-up forms, primary additions before secondary additions such as talus
   skirts or satellite stacks, with weathering modelled into exposed shells.
4. Flowing lip sources.
5. Decoration and lighting.
