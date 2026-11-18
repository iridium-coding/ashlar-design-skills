# voxel: render-verify toolkit

Copied from Chapman's `minecraft-java-fabric-claude-plugin` (`tools/voxel`,
Release 1.2.0, MIT; see `LICENSE`), without its Fabric placer and rail checks.
The fills it writes go to the Ashlar placer in the `exec-ashlar` skill.

Author a form as a parametric numpy model, render it to PNGs you can look at,
iterate against references, then decompose it into world fills.

## Running

numpy and Pillow come from `uv`, so nothing is installed into the global
Python. From the workspace root:

```bash
uv run --no-project --with numpy --with pillow python my_model.py
```

In the script, put this folder's parent on `sys.path`, where `<design-monument>`
is the `design-monument` skill's folder:

```python
import sys
sys.path.insert(0, "<design-monument>/tools")
from voxel import Palette, VoxelModel, render_views, write_fills_json
```

## API

| Name | Does |
| --- | --- |
| `Palette.building()` | Starter palette: the 16 concretes, stone, wood, glass, glow, metals, the copper series; `add(id, rgb)` adds more; `code("stone")` gives a block's code |
| `VoxelModel(nx, ny, nz, palette)` | Empty grid (x = length, y = height, z = width) |
| `fx`, `fy`, `fz` | A fraction of an extent → an index, so forms are defined by ratios |
| `box`, `ellipsoid`, `cylinder`, `line3d` | Primitives |
| `fill_where`, `replace`, `clear`, `mirror_x` | Edits |
| `counts`, `solid_count`, `save_npy`, `load_npy` | Inspection and persistence |
| `render_views(model, prefix)` | Writes `<prefix>_iso.png`, `<prefix>_side.png`, `<prefix>_front.png` and returns the paths |
| `write_fills_json(model, path, origin)` | Greedy box decomposition (boxes up to 32,000 blocks) into `[{"from", "to", "block"}]` in world coordinates; returns a summary with `fills`, `solid_voxels`, `per_block`, `bbox` |

## Placing

`<exec-ashlar>` is the `exec-ashlar` skill's folder, a sibling of
`design-monument`:

```bash
python3 <exec-ashlar>/scripts/ashlar_place.py plan fills.json
python3 <exec-ashlar>/scripts/ashlar_place.py place fills.json --snapshot --label "<project> figure"
```
