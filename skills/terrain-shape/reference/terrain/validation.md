# Terrain validation

Run GATE A on the measured site. After construction use the rows and methods in `../exec-ashlar/reference/verification.md`.

1. **No ziggurat.** Review the placed profile and eye-level view. A compound slope changes gradient through its section. Rectangular plateaus with vertical risers need a different field.
2. **No seam.** Use the emitted boundary rows. Run `seam --site POST_BUILD_F1` with the row endpoints and outward direction against fresh exact columns spanning both sides. Check all edges. See `reference/terrain/toolkit-api.md`.
3. **No bare walls.** Inspect the slope map and sample steep columns. Exposed faces should show the designed rock palette and strata.
4. **Detail preserved.** Edit the saved recipe when re-sculpting. Compare the new output against the approved extent and retained features.
5. **Placement confirmed.** Compare fresh post-build heights to the emitted surface file. Reconcile placer and feature-runner counts and investigate missed columns or failed placements.
6. **Gates and ground.** Check the verify report, token, design approval, build gate and rollback evidence. Offer an integration pass if a footprint edge needs grading.

## Verify at eye-level, NEVER top-down alone

The parks-grand-loop lesson: top-down renders showed "done" while the vertical faces a player sees
were bare gray walls. For any ride-through / walk-through terrain, the acceptance renders are
**profile, eye-level and slope**. Top-down is valid only for flat-pattern checks (mosaics, road networks).
A user visual checkpoint is required under autonomy for hero terrain.

One projection hides vertical faces, remote openings and texture seams. In the Zion build an overhang above a wall rail, a far-side alcove and a smooth endcap were visible from the player's position. Use `mc_render` top and heightmap on the full box, vertical slices along several x and z lines and facades of 1–3 block edge strips within the 200,000-cell side-view limit. Read the wall-and-bench profile from the track. Ask the user for an in-game look at hero terrain.

## Underwater faces

Sample **below** sea level too — pad walls, foundation faces, the seabed profile. Cape Aurelia's
rectangular corestone passed inspection because only above-water was sampled; underwater it was a
sheer 80-block rectangle. Coastal/underwater terrain must include below-sea samples in its
`quality_contract`.

## Quality contract

Use the emitted surface_match, seam, silhouette and edge_irregularity rows plus water_continuity for planned basins. Add applicable material mix rows using the placer's schema. Inspect asymmetry and foundation visibility at the sample points in `reference/terrain/non-negotiables.md` and record the observed results.
