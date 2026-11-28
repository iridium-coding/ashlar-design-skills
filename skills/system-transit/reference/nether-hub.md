# The nether hub and portal pairs

One block in the Nether is eight in the Overworld, so a short Nether line
replaces a long Overworld journey: 1 km of Nether line covers 8 km.

## Portal math (Java)

- Overworld to Nether: x and z become `floor(value / 8)`; Nether to Overworld:
  `value * 8`. Y is unchanged. An Overworld portal at (3600, 70, 0) pairs to a
  Nether portal at (450, 70, 0).
- The game searches a square of 128 blocks radius (Overworld) or 16 (Nether),
  full height, around the converted point and takes the nearest portal block by
  3-D distance with Y included (ties go to the lower Y).
- With no portal in range the game builds one within 16 blocks horizontally.
  Building both ends and passing the pair check prevents that. Never rely on a
  game-generated portal.
- An entity can step through anywhere in the opening, so the arrival area is the
  opening scaled to the other world: a 2-wide Nether opening spreads its arrivals
  over 16 Overworld blocks. The pair passes when, for every arrival point, the
  partner portal is nearer (3-D, Y included) than every other portal block in the
  read, and inside the search radius. A portal shared by two Overworld sites needs
  those sites far enough apart for the spread.
- The server keeps the vanilla radius and scaling (`portal-search-radius: 128`).

## The portal design

`terrain/<element>.portal.json` gives one end (new, or an existing portal the user
names); the other is computed, its y chosen in a safe pocket (an enclosed landing
above the lava sea and below the roof).

```json
{
  "element": "east-gate",
  "overworld": {"world": "world", "at": [3600, 70, 0], "axis": "x"},
  "nether": {"world": "world_nether"},
  "size": [4, 5],
  "doorways": []
}
```

`terrain.py portal` lists the boxes to read around both arrival areas, then with
both reads writes per world an obsidian frame, `nether_portal` blocks with the axis
(placed without physics, so no lighting step) and a landing: a platform in the
Overworld, an enclosed, lit room in the Nether. The Nether landing gets a
bottom-slab floor and shroomlight in the walls (and as the floor in front of each
portal face), so nothing spawns on it and every spawnable cell is lit to 12. A
doorway's `y` is the first open cell, the standing level (frame `at.y + 1` or
higher): a lower one would cut through the floor and is refused. A doorway opens
3 high under a lintel (the room is 4 high inside), so one whose opening would reach
the roof is refused too.

The Overworld platform stands on dry ground unless the design sets
`platform_in_water: true`: then it may stand in still water (never flowing water
or lava), the water cells it replaces are counted in the report's
`displaced_water`, and the approval covers them.

A pair is two builds, one per world: `portal` writes
`terrain/<element>-overworld.plan-rows.toon` and `terrain/<element>-nether.plan-rows.toon`,
and each is built with its own `exec-ashlar build` and recorded as its own registry
entry (`<element>-overworld`, `<element>-nether`).

## Hubs

A hub is a portal landing whose `doorways` the spoke lines end at (`stop: open`).
Route the spokes first so the doorways are known before the landing is built.
Spokes never overwrite built blocks. Pick the hub centre in clear Nether between
the lava sea and the roof, convert it for its Overworld home, and give each site's
spoke its own portal pair. Label each doorway with a sign naming the destination.

## Nether lines

A Nether line runs level between the lava sea and the roof on `straight` legs.
There is no ground to grade: the line classes each cell from the section reads. A
bore in rock is a tunnel, a bore through open air is a tube (an enclosed deck on
piers or hung from the rock), and lava in the bore or its lining shell is a
refusal naming the cell; choose another level or leg. See [lines.md](lines.md) for
Nether spawning: lanterns, lamps in pairs at floor height, bottom-slab floors, and
why hoglins, magma cubes and ghasts are not stopped by light.

## Piglins

Adult piglins are neutral only to a player wearing at least one piece of golden
armour. Placed gold blocks do not calm them, and breaking a gold block angers
piglins within about 16 blocks. Tell the user to wear gold when crossing.

## When a nether hub is right

5 or more scattered sites, pairs more than a few thousand blocks apart, and
speed-first projects. It is wrong when the journey is the point or the sites are
close enough that an Overworld link is simpler than two portals and a line.
