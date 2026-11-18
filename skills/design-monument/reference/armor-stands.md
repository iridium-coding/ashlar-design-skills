# Armor-stand detailing

Armor stands add **fine detail** a block grid cannot — held items, posed
accent figures, floating decorative elements. They are placed as a **late
decoration phase**, after the monument's blockwork is built.

## Java armor-stand facts

- Java armor stands **do not show arms by default**; pass `ShowArms:1b` in
  the SNBT to enable them when the stand needs to hold items visibly.
- Java armor stands support **fully free NBT pose rotation** via the `Pose`
  compound — each limb rotation is a list of three floats (X/Y/Z Euler
  angles in degrees). There are no preset named poses; compose any pose you
  need with the fields below.
- Key SNBT fields:
  - `ShowArms:1b` — show arms (required to display held items visually).
  - `NoBasePlate:1b` — remove the base plate (cleaner for decorative stands).
  - `Invisible:1b` — hide the stand itself; the held/worn items float.
  - `Small:1b` — use the small-stand variant (about half scale).
  - `NoGravity:1b` — prevents the stand from falling.
  - `Pose:{…}` — per-limb rotation; available keys: `Head`, `Body`,
    `LeftArm`, `RightArm`, `LeftLeg`, `RightLeg`; each is a list of three
    floats, e.g. `Head:[0f,-20f,0f]`.
  - `HandItems:[{…},{…}]` — items in the main-hand and off-hand slots.
  - `ArmorItems:[feet,legs,chest,head]` — equipment in armour slots (order
    is feet → head).
  - `Tags:["ashlar","ashlar.<project>"]` — tags so stands can be found and adjusted later.
- A mob head in the helmet slot is a common detailing trick.

## In the plan

- Spawn armor stands with the allowlisted
  `summon minecraft:armor_stand <x> <y> <z> {…}` at the decoration phase,
  passing all SNBT in the command's NBT compound.
- Tag them (`Tags:["ashlar","ashlar.<project>"]`) so they can be counted with
  `execute if entity` and removed by tag.
- Use the allowlisted `data merge entity` if a spawned stand's pose or
  equipment needs changing after the fact.

## Useful pose recipes

| Role | Head | RightArm | LeftArm | Body |
|------|------|----------|---------|------|
| Attention / guard | `[0f,0f,0f]` | `[-10f,0f,0f]` | `[-10f,0f,0f]` | `[0f,0f,0f]` |
| Salute | `[0f,0f,0f]` | `[-90f,-20f,0f]` | `[-10f,0f,0f]` | `[0f,0f,0f]` |
| Brandish (weapon raised) | `[0f,0f,0f]` | `[-120f,0f,-20f]` | `[-10f,0f,0f]` | `[0f,0f,0f]` |
| Walking | `[0f,0f,0f]` | `[-30f,0f,0f]` | `[30f,0f,0f]` | `[0f,0f,0f]` |
| Seated | `[0f,0f,0f]` | `[-10f,0f,0f]` | `[-10f,0f,0f]` | `[0f,0f,0f]` (position the stand at seat height) |
| Floating item | use `Invisible:1b`, `NoBasePlate:1b`, pose as needed | | | |

Angles are suggestions — adjust to taste for the specific design.

## Detailing patterns

- **Held detail** — an armor stand (`ShowArms:1b`) holding a banner, a tool,
  a weapon, or an item supplies a crisp small element (a flagpole banner, a
  statue's staff or sword) at a scale the block grid cannot.
- **Accent figures** — a ring of posed stands around a monument: guards,
  warriors, figures in motion — small human-scale figures that give a giant
  monument scale and context.
- **Equestrian accents** — use a raised `RightArm` / `LeftArm` and
  appropriate item; true mount-and-rider needs two entities positioned
  carefully.
- **Floating elements** — an `Invisible:1b`, `NoBasePlate:1b` stand holds an
  item in mid-air (jewels on a treasure pile, a held orb, hovering runes).
- **Mob heads** — player or mob heads on stands or as standalone blocks add
  faces and character.

## Rules

- Armor-stand decoration is the **last phase** — after all blockwork, so the
  stands are not disturbed by fills.
- Keep counts reasonable — armor stands are entities and a large crowd has a
  cost; use them for *accent*, not bulk.
- A monument's main form is always **blocks**; armor stands only finish it.
