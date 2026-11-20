# Community sources

Redstone content overwhelmingly targets **Java Edition** — which is what this
world runs — so most tutorials, videos, and wiki diagrams apply directly. The
real risk is not edition mismatch but **version drift**: redstone behaviour,
spawn rules, and mechanics shift between releases. This is who to trust and how
to verify against the running version.

## Trust for Java

- **The Minecraft Wiki** (minecraft.wiki) — a community-maintained
  source for mechanics, timing, and block behaviour. Each block/tutorial page
  documents the Java behaviour and notes the version a change landed in. Prefer
  it over the Fandom mirror, which carries outdated figures.
- **Java-focused redstone creators** — the major redstone YouTubers and the
  technical-Minecraft community build and test on Java, so their item-sorter,
  farm, door, and flying-machine tutorials are catalog-eligible. Note the game
  version each design was demonstrated on.
- **The Open Redstone Engineers (ORE) community** and other technical-Java
  references — strong for logic-circuit and computational redstone primitives.
- **The Minecraft Wiki's tutorial namespace** — the "Tutorials/" pages
  (mechanisms, farming, redstone) are vetted Java designs.
- **Mojang changelogs / official snapshots** — authoritative for what changed
  in a given version (e.g. changes to crop growth, Crafter additions).

## Verify against the running version

- **Confirm the world's version first** with `mc_status`. A design
  proven on an older version may behave differently on Java 26.3.
- **Version-sensitive areas** to double-check before relying on them:
  spawn-light thresholds, mob-spawn shell distances, bubble-column speeds,
  iron-golem spawn volume, powered-rail spacing, and any contraption that
  exploits a specific tick quirk.
- **Reject patched-out and exploit mechanics** even when a tutorial shows them:
  0-tick farms (removed years ago) and TNT/item duping (bugs that may be patched
  or server-disabled). Re-derive from `design-patterns.md` with a reliable
  mechanic instead.
- **Prefer recent sources.** Ask `survey-research` for material verified on a recent
  Java version and note the version a design was confirmed on.
- When a project’s `build-log.md` records a passed functional test on a given
  Java version, reuse that proven pattern — but re-verify
  it if the world's version has since changed.

## Sourcing rules

- **Cite a source and its game version for every catalog entry.** A Minecraft
  Wiki page (with the version note) or a named creator's current video.
- **Reject** a design whose only source relies on a patched-out or exploit
  mechanic — re-derive it from `design-patterns.md` instead.
- **Any tutorial that does not state its version** — note the uncertainty and
  verify the load-bearing timing/mechanic in-world before trusting it.

## When in doubt — test it live

Java's determinism means you can verify a mechanic directly: design a minimal
module, check its resting state offline, then include its test in the plan.
Use `exec-ashlar build` for approval and placement and `exec-ashlar test` for
the observations in `verification.md`. A switchable observer clock, a single
sorter row or a one-piston door can isolate a version-sensitive mechanic.
