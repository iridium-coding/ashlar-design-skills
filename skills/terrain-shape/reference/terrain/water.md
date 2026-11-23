# Water systems

Lakes, rivers, falls, wetlands, and frozen water. All the non-negotiable rules
apply — irregular outlines, the 7-block rule on every bank and shore.

## Water mechanics in Java Edition

- Fill closed basins to a level surface with still sources in the mass phase. At a box edge, meet existing water at the same level. For a descending river, connect level reaches with a step. Fill a waterfall's plunge pool before its lip sources flow. A few blocks of pool depth usually work, up to about twelve for a large fall. Flowing lips have a separate phase and a backup covering the full possible flow area.
- The infinite-source rule works: a `+` of two adjacent source blocks in a
  flat plane regenerates a source in the adjacent position.
- Preserve the exact waterlogged state when keeping a block (for example `minecraft:stone_bricks[waterlogged=true]`).
- Water cannot exist in the Nether dimension — it evaporates instantly.

## Existing water, lava and wooded shores

Design around the existing body first. Keep surface liquid, including water plants, waterlogged roots and ice on water. Normal solid ground on a changed slope may cover liquid. Never bury a body to avoid a drain decision. Where a bed is lowered, refill only to the top of the unbroken still liquid resting on that bed. An isolated retained water cell, including a suspended source, stays at its measured height unless covered by the planned solid. It does not fill the air gap below it. A separate, disconnected pond stays untouched when another body is drained.

The grading seal skips liquid below the old bed. If regrading exposes it, the same spill checks apply. Move a grade or a voxel form that would overwrite buried liquid.

Trees rooted on changing ground are removed whole, including connected leaves, vines and attachments that overhang the project edge. Trees rooted on unchanged ground stay whole, except where raised terrain covers a cell. When removing a submerged trunk, leave its liquid in the cells joined to still water at the same height or directly beneath it. Do not fill upward through branches to an isolated source. On a wooded bank, set `hold_shores: true` to retain the bank beside the water that will occupy cleared tree cells. Confirm the read includes air above the entire canopy, and include the farthest removed tree cell in bounds and backups. If spill checks fail, raise the local bank, plan connected water at the measured level or hold shores, then preview again.

## A drain requires a separate answer for each body

1. Only when the design needs one, preview `"drain":[{"at":[x,z]}]` using `field`. The seed selects the lowest retained liquid in that column. The whole connected body includes falls and outlets. Dry trunks can connect opposite sides horizontally at the same Y. Refuse partial drains, outer-ring or outside bodies, and bodies that intersect protected columns. A river continuing beyond the box stays.
2. Use the current preview as the drain manifest. For **one body per question**, give its ID, seed and location, liquid kinds, cells, columns, bounds and top Y. Ask whether to drain this exact body in this build. Explicitly say that creatures in it may die and rollback cannot bring them back. Wait for the user's words.
   - Claude Code: use `AskUserQuestion` for the dedicated yes or no.
   - Codex: use `request_user_input` when available.
   - Otherwise: ask in plain text.
3. In the project's `requirements.md`, record the date, project/build, body ID, description and user's exact answer. Without a yes, remove that seed, preserve the body, revise the design and explain what changed. A dry run, a previous build and general design/build approval cannot supply the answer.
4. Match every previewed ID and plan drain note to this build's recorded yes before proceeding. Pass `--drain-approved BODY_ID` once for each approved body on `emit`. A missing, stale, duplicate or unknown ID stops emission without writing output. Discard stale design output from consideration if the recipe changed or emission failed.
5. Repeat the manifest, counts of kept/covered/added/drained liquid, answer and creature consequence at the build gate. With no complete site manifest, current approvals, matching plan notes or complete per-phase rollback point, stop before a world write.
6. Immediately before the **first drain write**, take a fresh, complete F1 site read in the approved world over the entire recipe footprint and its original site-read margin. Cover the whole body, banks, falls and outlets. Keep the original read and backups. Resolve the same seed against the fresh columns with `terrain.site.drain_bodies` and the approved recipe. Compare the resulting manifest to the approved one, including body ID, liquid kinds, cell/column counts, bounds and top Y. Verify the complete rollback point covers the affected phase bounds. An unchanged backup box alone cannot establish that an outlet is still closed. Stop before writing if the read is incomplete, the body now reaches outside, the manifest differs, or rollback coverage has changed. Resolve a changed body with a fresh design and dedicated approval.
7. If execution was interrupted **after** the first drain write, follow `../exec-ashlar/reference/execution.md` for resume or rollback. For an approved resume, use the same emitted bundle and its original rollback points. Reconcile actual cells and recorded progress against the original site and writes already attempted, including partially placed phases. Stop on unexplained differences. A partly drained pond reflects prior writes and cannot stand in for the original body manifest.

## Lakes

- Irregular outline, never rectangular or circular. Any lake wider than ~20
  blocks needs **at least 3 lobes**.
- **Depth gradient:** 1 block at the shore → 4–8 at the center, as a soft bowl
  curve, never a flat floor.
- **Bed:** clay + gravel + sand patches (~60/30/10), with occasional dirt and
  a few seagrass blocks.
- **Shoreline:** alternate sand patches (2–6 wide) with grass-and-coarse-dirt
  patches (3–8) and the occasional gravel beach.

## Rivers

- **Meanders:** the centerline turns at least 15° before any straight segment
  reaches 7 blocks. Width 3–8 for a small river, 8–20 for a major one.
- **Bed:** replace plain clay/gravel with brown dirt, granite, and seagrass;
  texture the banks with coarse dirt and grass paths. (BlueNerd technique.)
- **Oxbow lakes:** a former meander cut off by erosion — a disconnected curved
  water body 4–10 blocks from the active channel.
- **Tributaries:** join the main channel at an acute 30–60° angle, narrower
  than the main river.
- **Headwaters:** a spring emerging from a hillside as a 1×1 source, widening
  over 10–30 blocks.
- **Deltas:** at the mouth, split into 3–6 branches across a triangular fan
  30–80 blocks wide.

## Waterfalls, cascades, rapids

- A single source makes a thin fall; a wide fall needs a line of sources along
  the top edge.
- **Cascades:** 2–5 stepped falls with mossy cobblestone ledges and spillways
  1–2 blocks wide.
- **Rapids:** a river bed broken by cobblestone + gravel humps that breach the
  surface; pointed dripstone above adds a spray feel.

## Wetlands, swamps, bogs

- **Mangrove swamp:** mud, mangrove_roots, muddy_mangrove_roots, mangrove
  logs, lily pads; dominant water depth 1–2 blocks; occasional grass/dirt
  disks.
- **Wet meadow:** grass + tall_grass + sweet_berry_bush with 2×2 water
  puddles.
- **Bog:** podzol + coarse_dirt + dead_bush + brown_mushroom with small water
  pockets — a dark, peaty look.

## Frozen features

- **Ice lakes:** a top layer of ice or packed_ice over normal water, with a
  1–2 block snow margin.
- **Glaciers:** a blue_ice core, packed_ice body, snow_block surface, and
  occasional crevasses (3–6 block slits filled with water or air).
- **Icebergs:** asymmetric masses of blue_ice + packed_ice + snow_block. Roughly
  **7/8 of an iceberg sits below the waterline** — model the submerged volume
  as ~7× the visible part. Pick the ratio once per build and stay consistent.
