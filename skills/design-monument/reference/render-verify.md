# Render-verify: give yourself eyes before you place blocks

The single most valuable habit for any representational or parametric build.
`mc_render` shows what you built, but only after the blocks are in the world,
and every in-world rebuild costs snapshots and time. A wrong **base silhouette**
cannot be rescued by any amount of front-end detailing. So build a model you can
see first, offline: a renderer is cheaper than one wrong in-world rebuild.

This applies to: vehicles, creatures, statues, characters, logos, any
voxelized form, any large figurative mass. It does **not** apply to a flat
pixel-art grid you already laid out on paper — that you can reason about
directly.

## The loop (offline, seconds per iteration)

1. **Author** the form as a parametric `VoxelModel` (numpy grid + primitives).
2. **Render** three orthogonal views to PNG and **look at them**.
3. **Compare** to the reference images. Adjust **one parameter at a time**.
4. **Re-render.** Repeat until the renders genuinely match the references.
5. **Decompose** to a fills file and **place it** with the `exec-ashlar` placer.
6. **Verify** with `mc_render` (below) and compare to the references again.

Different errors surface in different views — always render multiple, never
just one:

- **side** (length × height) — the make-or-break **silhouette**. Stance,
  proportion, roofline, the overall read. Most identity errors show here.
- **front** (width × height) — the face: light bars, headlights, symmetry,
  shoulders.
- **iso** (3/4) — how the masses sit together in three dimensions.

## Looking at the PNGs

- Claude Code: open each PNG with `Read`.
- Codex: open each PNG with `view_image`.
- Otherwise: report the model's numbers (`counts()`, extents) and ask the user
  to open the files.

## The toolkit

Bundled in this skill's folder at `tools/voxel/` (numpy + Pillow through `uv`,
so nothing is installed globally); `tools/voxel/README.md` lists the API. Run an
authoring script from the workspace root with
`uv run --no-project --with numpy --with pillow python r1s.py`. Its shape:

```python
import sys
sys.path.insert(0, "<design-monument>/tools")   # this skill's folder, then tools
from voxel import Palette, VoxelModel, render_views, write_fills_json

pal = Palette.building()                  # concretes, stone, wood, glass, copper…
BODY = pal.code("cyan_concrete")
GLASS = pal.code("light_blue_stained_glass")

m = VoxelModel(nx=184, ny=70, nz=78, palette=pal)   # x=length, y=height, z=width
# anchors are fractions of the extent — define the form by ratios, tune vs render
roof, belt = m.fy(0.78), m.fy(0.45)
m.ellipsoid(center=(m.fx(0.5), belt, m.fz(0.5)), radii=(80, 22, 34), code=BODY)
m.box((m.fx(0.2), belt, m.fz(0.15)), (m.fx(0.8), roof, m.fz(0.85)), GLASS)

render_views(m, "/abs/scratch/r1s")       # r1s_iso.png / r1s_side.png / r1s_front.png
```

- Claude Code: `<design-monument>` is `${CLAUDE_SKILL_DIR}`.
- Codex: `<design-monument>` is the folder holding this skill's `SKILL.md`.
- Otherwise: use the folder holding this skill's `SKILL.md`.

Then look at the three PNGs, judge them against the references, edit the model,
and re-run. Author the shape from **anchors and primitives** (`ellipsoid`,
`cylinder`/cone, `line3d` spine, `mirror_x` for symmetry), not absolute
coordinates — so you can tune a ratio and see the effect, not chase numbers.

## Placing the verified model

Once the renders match, decompose:

```python
summary = write_fills_json(m, "/abs/scratch/r1s_fills.json", origin=(206, 64, 70))
```

`write_fills_json` greedily covers the model with maximal boxes and writes a
list of `{"from":[x,y,z], "to":[x,y,z], "block":"…"}` in **world** coordinates.

**Place it with the placer, not by hand.** A real voxelized form is 1,000–7,200
fills — far too many to transcribe into a tool call reliably. Add the file as a
`via: placer` phase in `plan.toon` and let the `exec-ashlar` skill send it:

```bash
python3 <exec-ashlar>/scripts/ashlar_place.py plan /abs/scratch/r1s_fills.json
python3 <exec-ashlar>/scripts/ashlar_place.py place /abs/scratch/r1s_fills.json --snapshot --label "<project> figure"
```

`<exec-ashlar>` is the `exec-ashlar` skill's folder (`../exec-ashlar` from this
skill's folder). The placer checks for players, snapshots the area, and pages
the fills into `mc_build` calls within Ashlar's limits. If it needs more
snapshots than allowed, split the model along an anatomy seam into separate
fills files and phases. The script and the model `.npy` are the **reusable
artifact** for a large parametric form; record them in the registry.

## Verify the built result

After placing, confirm fidelity *visually*, not by spot-checking coordinates:
render the placed bounding box with `mc_render` from the sides that matter
(`north`, `south`, `east`, `west`, y limited to the figure) and from the `top`.
Use `mc_inspect` stats for a quick solid-count and material check. A matching
count of non-air blocks between the model and the build is strong
block-for-block evidence; a matching *picture* is the real proof the build
reads as its subject.

## Imported meshes are not authoritative

A free downloaded mesh (Printables, Thingiverse, Sketchfab) voxelizes into
*a* shape, not necessarily the **named** subject's shape — a generic crossover
is not an R1S. If you import a mesh (e.g. voxelized via the optional `trimesh`
dependency into a grid), **render its silhouette and check it against the
references before building anything on it.** Render-checking on day one is
cheap; detailing a wrong body for days is not. Hand-authoring a parametric
model usually wins for a specific named subject because you control the
silhouette directly — **but when the user hands you a model file (or a faithful
one exists for the named subject), voxelizing it wins** (it nailed an organic
character on the first try where hand-authoring took ~6 rebuilds). See
`reference/mesh-import.md` for the full import pipeline and the `.3mf` gotchas.

## Scene scale

When the piece shares a scene with another subject (a figure beside a vehicle),
**pin the scale relationship before authoring** — fix the ratio (e.g. figure
height ≈ vehicle roof height) up front, so you don't discover a 4× mismatch
after both are built. Record the ratio in `requirements.md`.
