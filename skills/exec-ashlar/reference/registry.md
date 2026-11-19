# Project state and registry

All project files live under `.minecraft-builder/` in the workspace root, the
folder the client was started in. Start Minecraft sessions from the same folder
so there is one history.

```text
.minecraft-builder/
  registry.json
  <project>/
    requirements.md     interview answers (design skill)
    survey.md           site survey (exec-ashlar survey mode)
    research.md         research notes, with research.toon (survey-research)
    floorplan.txt …     blueprints, in the design skill's own formats
    plan.toon           the plan (plan-format.md)
    phases/             one mc_build arguments file per phase
    modules/            module files (modules.md)
    build-log.md        what was placed, snapshot ids, warnings, checks
    placer.log          JSON reports from the placer
```

## registry.json

```json
{
  "version": 1,
  "projects": {
    "oakhollow": {
      "skill": "design-village",
      "world": "world",
      "anchor": [120, 64, -340],
      "bbox": {"from": [100, 58, -362], "to": [162, 92, -298]},
      "status": "planned",
      "entity_tag": "ashlar.oakhollow",
      "modules": ["small-house-a"],
      "phases": [
        {"id": 1, "name": "site-prep", "snapshots": ["snap-20261117-210400-ab12"],
         "cells": 18200, "placed_at": "2026-11-17T21:04:00Z"}
      ],
      "commands_run": ["summon minecraft:villager 121 65 -333 {Tags:[\"ashlar\",\"ashlar.oakhollow\"]}"],
      "citations": [],
      "updated": "2026-11-17T21:30:00Z"
    }
  }
}
```

- `status` goes `planned` → `building` → `built`, or `rolled-back`.
- Write the entry when the plan is written (`planned`), after every phase
  (append the phase with its snapshot ids), and at the end.
- Update the registry by **read, change, write**: read the whole file
  immediately before each write, add or replace only `projects.<project>`, keep
  every other project and key exactly as read, and write the full file back.
  Never rebuild the file from this project alone.
- If the file does not exist when you read it, create it as
  `{"version": 1, "projects": {}}` and add your entry. If a write fails or the
  file changed meanwhile, read again and redo the change.
- `citations` holds the sources for replicas, so the build can be checked
  against them.
- A project may carry extra keys the design skill needs (for example `rooms`,
  `districts`, `population`, `shared_anchors`); keep unknown keys when
  updating.
- Never store server addresses or tokens.

Design skills may add keys such as `rooms` (design-house), `districts`
(design-city), `population` (design-village: planned villagers) and
`shared_anchors` (design-monument sibling seams); executors ignore them. A
planned entry may have `"modules": []` and `"phases": []`. `updated` is the
current UTC time if you can read it, otherwise the date.
