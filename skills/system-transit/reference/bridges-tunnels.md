# Bridges and tunnels

How a line crosses a gap or goes through an obstacle. The toolkit generates beam
and arch bridges and bored tunnels; showpiece superstructures are
`design-monument` work.

## Bridges

- **Beam**: up to about 16 blocks; a deck on piers every 6 to 8 blocks.
- **Arch**: 16 to 40 blocks per span; a segmental arch from the deck down to the
  springing piers.
- **Block stability**: blocks do not hang. Every deck column is held by a pier or
  arch within the span its type allows (the `deck` check), and a bridge with
  nothing under it is a failure. Truss, suspension and cable-stayed looks are
  decoration over those hidden piers, added by `design-monument`.
- **Piers** stand on solid ground. They may stand in still water only with
  `piers_in_water: true`; the water cells they replace are counted and named in the
  report and the approval covers them. Never in flowing water or lava.
- The deck keeps `water_clearance` above the surface it crosses.
- A drawbridge lift is `system-redstone`.

## Tunnels

- A rectangular or arched bore (rail 3x4, road lanes by 5, path or ice 3x3 or
  more) inside a one-block lining shell, lights set into the lining, framed mouths.
- A bore or lining cell that would meet water or lava is refused. The lining
  replaces natural rock; an existing solid block that is not natural is kept as
  lining and never overwritten; caves the tunnel crosses are sealed by the shell.
- `roof` is the rock kept above the lining; a cut deeper than `max_cut` becomes a
  tunnel only where the rock above keeps it.
- Light by the corridor minimum and cap floors mobs cannot spawn on (see
  [lines.md](lines.md)).
- Underwater crossings are bridges, or a route over or around the water. A
  tunnel that meets water is refused: re-route (add an `avoid` box) or pick another
  level.

## Choosing

A bridge is seen and celebrated; a tunnel is invisible and keeps the land above
intact. Approach cuts at tunnel mouths and abutments at bridge ends are graded
like any cut or fill; larger grading is a `terrain-shape` step.
