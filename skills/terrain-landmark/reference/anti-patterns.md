# Anti-patterns — the signature checklist

Use this checklist to check a finished landmark for missing signature features
and wrong proportions. Each applicable item is a yes/no check in
[`exec-ashlar` verification](../../exec-ashlar/reference/verification.md).

## Strata and colour

- **Too few strata bands.** Real badlands and canyons show 5–10 distinguishable
  layers. A 2-band Grand Canyon reads as a generic cliff. → ≥5 bands, each 5–7
  blocks.
- **Wrong colour sequence.** The Grand Canyon runs red/orange on top to grey/
  dark at the bottom. Reversing the order reads as alien. → Match the palette
  preset's stated top-to-bottom order.

## Silhouette and proportion

- **Symmetric where it should be asymmetric (and vice versa).** Every volcano
  is asymmetric — bias one slope 15–25% wider — **except Mt. Fuji**, which must
  be symmetric. → Check the wonder's entry.
- **Wrong aspect ratio.** Uluru is ~3:1 wider than tall; built taller than wide
  it reads as a mesa. Devils Tower is tall and narrow. → Honour the ratio in
  `wonders.md`.
- **Wrong silhouette.** Devils Tower without vertical column striations is a
  generic plug. A tepui or mesa with tapered (not vertical) cliffs is just a
  hill.
- **A group of named masses reads as one lump.** For a wonder that is several
  named landmarks (Kata-Tjuta domes, Twelve Apostles, a line of buttes), each
  mass must be legibly distinct: separated centres, varied summit heights, a
  baked saddle between neighbours, contrasting profiles (broad mesa vs narrow
  spire vs tri-lobed dome). Two `np.maximum`-merged broad masses read as a single
  butte, and post-hoc carving of notches to split them reads as artificial slots.
  → author each mass distinct in the heightfield (see `sequencing.md`); a merged
  group sends the build back to the composer, not to a carve pass.

## Signature features

- **Missing the key feature.** Niagara without the horseshoe is just a curtain.
  Iguazu without the Devil's Throat is a stepped weir. A karst tower without
  the waterline notch is just a pillar. → Every signature identified in the
  composer's step 1 must be present and legible.

## Scale

- **Below the recognition floor.** Devils Tower at 20 tall is a plinth; a Grand
  Canyon at 30 long is a ditch. → Enforce the minimum footprint from
  `wonders.md`.

## Surface and material

- **Uniform block faces.** A flat 30-block cliff with no Y-variation reads as a
  wall. → Apply a light seeded surface-chipping variant, retaining at least
  95% of the face. See [weathering](sequencing.md#weathering-passes).
- **Wrong water colour.** Crater Lake is deep blue, Ijen turquoise, Havasu
  blue-green — the colour is the block *under* the water, never the water
  itself. → Set the floor block, not the water.
- **Concrete-powder where stability matters.** White Sands dunes need powder
  (gravity); Salar de Uyuni needs solid concrete. Mixing them collapses the
  build on chunk reload.
- **Vegetation grown over bare rock.** Grass creeping over a rock landmark
  breaks it. → Use `coarse_dirt` / `rooted_dirt` substrate near rock.
- **Wrong vegetation context.** Match plants to the real biome — cactus only in
  desert, spruce for alpine/pine, jungle growth on karst tops.

## Evidence after the build

Compare the built landmark with the approved signatures and this checklist.
Check `acceptance` cells and the `silhouette` and `block_mix_ratios` rows. Use
profiles and eye-level views for signatures approved as checked by eye. Report
each signature as pass or fail with coordinates and the observation or render.
For a failed signature, revise the saved recipe in `terrain-landmark` and
re-emit through the approval flow.
