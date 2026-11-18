# Pixel art, murals, text, and logos

Turning a 2D image — a sprite, a painting, a logo, a glyph — into a block
grid. The technique is **quantize, grid, lay**.

## Pixel-grid image mapping

1. **Get the source image** — the `survey-research` can fetch a reference (a game
   sprite, a logo, a flag). Note its pixel dimensions.
2. **Choose the output size** — one image pixel maps to one block. Upscale a
   small sprite by an integer factor (a 16×16 sprite × 3 = 48×48) so edges
   stay crisp. Add a 1-block border if it wants framing.
3. **Quantize to a block palette.** Map each pixel's colour to the nearest
   block in a chosen palette. **Solid-colour blocks** are what make pixel art
   read — `concrete` (the most saturated), `wool`, `terracotta`, and `glazed
   terracotta` for patterned accents. Build the palette deliberately: pick the
   ~8–24 blocks that cover the image's colours, not every block.
4. **Dither or not.** A clean sprite or logo with flat colours quantizes
   crisply — **no dithering**. A photograph or painting with gradients reads
   better with dithering (alternating two near blocks to suggest an
   in-between tone). Say which you used.
5. **Lay it as a grid.** A quantized image *is* a block grid — the most direct
   way to build it is to generate the grid as a phase file with a
   short script — one fill per run of same-colour pixels in a row — and send it
   with the `exec-ashlar` placer (`via: placer`). If the same art repeats, make
   it a module and stamp it (`../exec-ashlar/reference/modules.md`). Use
   hand-written phase-file entries only for a small or simple grid. A flat mural is one block deep.

## Flat vs. relief

- **Flat** (1 block deep) — the default; reads cleanly head-on.
- **Low relief** (raise some regions 1 block) — gives parallax shadow at an
  angle; good for a logo or an emblem. Raise the foreground elements.
- **Orientation** — a wall mural stands vertical; a floor mosaic lies flat and
  reads from above. Quantize the same way; choose the plane.

## Scale and tiling

A mural whose box exceeds Ashlar's per-snapshot cap
(`../exec-ashlar/reference/tools-and-limits.md`) is split into tiles on a clean
grid line, with the offsets recorded. Its phase file stays well within Ashlar's
per-call limit (a flat mural rarely approaches it).

## Text and logos

- **Block alphabets** — design (or reuse) a glyph grid: 5×7 is the compact
  minimum; 7×9 and larger give serifs and weight. Keep glyph height and
  spacing consistent across a word.
- **3D extruded text** — give letters depth (3–6 blocks) for a freestanding
  sign; pitch or bevel the faces for a logo.
- **Hillside letters** (a Hollywood-sign style) — tall freestanding letters on
  a slope, each its own structure, spaced along the contour.
- **Logos** — treat as pixel art with a tight palette; a simple flat logo is
  often cleaner than a relief one.
- **Banners** — for small heraldic devices, layered banner patterns can carry
  a logo at a fraction of the block count; for large logos, use the block
  grid.

## Common mistakes

- Too small — fine detail in a sprite is lost below a certain block size;
  upscale until the features read.
- Palette too wide — using a near-match block for every pixel makes mud; a
  tight, deliberate palette reads sharper.
- Dithering a flat sprite — adds noise to something that was already clean.
