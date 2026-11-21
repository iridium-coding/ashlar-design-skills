# terrain (Ashlar copy)

This is a copy of the `terrain` toolkit from John Chapman's `tools/terrain/` in
this repository, used by the `terrain-shape` skill. It is licensed under the MIT
License (see `LICENSE`). Heightfield authoring, offline render-verify and the
block_fill_columns materialisation come from the original; the Ashlar copy
keeps only those parts.

Left out of the copy: Chapman's tests (the Ashlar tests live in
`tests/ashlar/terrain/`), `place_terrain.py`, the harness-plan output
(`emit_plan_toon` and its TOON writer), and the legacy voxel-grid path
(`to_voxel_model`, `write_terrain_fills`, `TerrainLayers`), which imported the
`voxel` toolkit.

Run the toolkit through the skill launcher:

    uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python skills/terrain-shape/scripts/terrain.py <command>

`emit_world` returns the verified payloads (columns, biomes, scatter). The
Ashlar output step, `ashlar_emit.py` (Task 11 of the terrain plan), turns them
into Ashlar placer commands.
