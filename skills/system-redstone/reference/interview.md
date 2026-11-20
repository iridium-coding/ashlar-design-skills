# The adaptive interview

Pin down the contraption without over-asking. Ask in small grouped batches, skip what is
already clear, and record answers in `requirements.md`.

- Claude Code: use `AskUserQuestion` for multiple-choice questions.
- Codex: use `request_user_input` when available.
- Otherwise: ask directly in chat.

## Question bank

1. **Contraption class** — door / hidden mechanism, item sorter or storage,
   mob farm or spawner collector, crop or animal farm, transport (minecart,
   elevator, ice road), music, decorative redstone, trap or defence.
2. **What it processes / does** — which items, which mobs, which crops; for a
   door, the opening size; for transport, the route and stops.
3. **Throughput / target** — a casual build, or a rate target ("keep up with
   an AFK session")? Throughput drives parallelism and footprint.
4. **Trigger** — button, lever, pressure plate, automatic (observer / clock),
   or hidden.
5. **Site and space** — review the anchor, footprint and facing limits from
   `exec-ashlar survey <project>`. Which sides must stay accessible? Is the
   machine underground, in a base or standalone?
6. **Simulation distance** — for any mob farm, the server's simulation distance. The viable spawn shell depends on it.
7. **Aesthetic** — exposed redstone (functional), or hidden behind a façade
   (then coordinate the enclosure with `design-house` / `design-building`)?
8. **Integration** — standalone, inside a building, or part of a village's
   industrial quarter (coordinate with `design-village`)?
9. **Project name** — the registry slug.

## Conditional follow-ups

- Lever, button, plate or clock → offer the hidden hopper test input for this
  build. Explain the space it needs and how the user can test the real control
  if they decline it. Record the choice.
- Manual steps → who will be in game, and when can they operate the controls?
- Sorter → which exact items and stack sizes? Prefer items that stack to 64.
  Agree on where unmatched items and overflow go.
- Mob / iron / villager farm → confirm the simulation distance and, for
  iron/villager farms, hand the village half to `design-village`.
- The request names a tutorial or creator → check `community-sources.md`;
  Java designs apply directly, but confirm the design's game version against
  the running world (`mc_status`) and ask `survey-research` for a recent
  source if there's any version-drift doubt.
- The request needs a patched-out (0-tick) or exploit (TNT/item duping)
  mechanic → explain it is not reliable on modern Java and offer the
  vanilla-redstone equivalent instead.
- The request is AFK fishing → note it works on Java but many servers patch or
  discourage AFK farms; confirm the server permits it.
- A timing-critical build (music, fast door, clock) → confirm the tempo or
  speed in redstone ticks (Java timing is deterministic, so it will be exact).
- A large farm → ask whether overflow protection (a trash can / overflow
  chest) is wanted.

## Iterate on ideas

The user may arrive with a vague want ("something cool with redstone") or a
firm spec. When it is vague, **suggest options** — name two or three
contraptions from the catalog that fit their world and ask which appeals.
Engineering is collaborative; propose, do not just interrogate.

## Conduct

- Lead with the contraption class and what it does — they shape everything.
- Group questions; never interrogate line by line.
- Restate the design — what it does, footprint, throughput, trigger — before
  resolving the plan, so a misread is cheap to fix.
