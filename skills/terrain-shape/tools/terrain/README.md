# terrain (Ashlar copy)

This is a copy of John Chapman's terrain toolkit, used by the `terrain-shape`
skill. The original is MIT licensed (see `LICENSE`, which this copy keeps).
Heightfield authoring, offline render-verify and the column materialisation come
from the original; this copy keeps only those parts.

Left out of the copy: Chapman's own tests, his placement script, his plan
writer for his own builder, and the legacy voxel-grid output path, which
depended on the `voxel` toolkit. The Ashlar tests for this copy live beside the
repository's other Ashlar tests.

Run the toolkit through the skill launcher:

    uv run --no-project --with numpy --with scipy --with pillow --with opensimplex python <terrain-shape>/scripts/terrain.py <command>

`emit_world` returns the verified payloads (columns, biomes, scatter). The
Ashlar output step, `ashlar_emit.py`, writes `mc_build` phase files and plan
rows; the `exec-ashlar` skill places them.
