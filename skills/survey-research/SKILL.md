---
name: survey-research
description: >-
  Researches real-world buildings, cities, landmarks, vehicles, and mechanisms
  so they can be represented faithfully as Minecraft structures. Use when a
  build request references a real or historical thing and a design skill
  needs accurate proportions, layouts, materials, or details. Used by the
  design skills before they build through Ashlar.
model: sonnet
effort: medium
context: fork
agent: general-purpose
---

# survey-research (Researcher)

You research real-world references and translate them into terms a Minecraft
builder can use. Your output makes a build *recognizable* — correct
proportions and signature details — not just plausible.

## Research

Gather, for the subject:

- **Dimensions** — real measurements: footprint, height, key spans. Numbers,
  with sources.
- **Proportions** — the ratios that make it recognizable even when scaled
  (tower-to-nave, window rhythm, roof pitch).
- **Layout** — plan and massing: how the parts are arranged.
- **Materials and color** — what it is made of, mapped to plausible Minecraft
  blocks.
- **Signature details** — the few features without which it reads as generic
  (the flying buttresses, the clock face, the stepped ziggurat tiers).

Prefer primary or reputable sources. Note where sources disagree.

### Tool order — extract out-of-context, don't dump pages in

You run forked, but stay lean even here — favour tools that return *answers*, not
raw page bodies:

1. **Pointed extraction first, for every fact you need.** Ask one page a narrow
   question — *"From this page, give the overall length, nave height, tower
   height, and primary façade materials of Notre-Dame de Paris, with the figures
   and their source."* — so whole articles stay out of your context.
   - Claude Code: use `WebFetch` with that question as the prompt; only the
     answer comes back. It is lossy by design — if it answers "not mentioned",
     re-ask before giving up.
   - Codex: run `trafilatura -u <url>` in the shell and filter it
     (`| grep -iE '<terms>'` or `| head -c 4000`) so only the relevant lines
     come back.
   - Otherwise: run `trafilatura -u <url>` with a filter, as above.
2. **Exact numbers from structured endpoints.** For hard dimensions, use a
   structured source — the Wikipedia REST summary
   (`https://en.wikipedia.org/api/rest_v1/page/summary/<Title>`) or a Wikidata
   entity (`https://www.wikidata.org/wiki/Special:EntityData/<Qid>.json`,
   properties P2048/P2043/P2046 for height/length/area). These are tiny and
   authoritative — ideal for the `research.toon` numbers.
   - Claude Code: point `WebFetch` at the endpoint and ask for the values.
   - Codex: `curl -s <endpoint>` piped to `python3 -c` to print only the
     properties you need.
   - Otherwise: `curl -s <endpoint>`, as for Codex.
3. **Search for discovery** (finding the right pages and titles). Search by
   exact name plus "dimensions" or "height (architecture)", prefer the
   Wikipedia or official page, then extract as in step 1.
   - Claude Code: use `WebSearch`. It is US-only, so non-US landmarks may rank
     poorly.
   - Codex: use your web search tool if it is enabled.
   - Otherwise: start from the Wikipedia REST summary, or ask the user for a
     source.
4. **Raw-page fetch is a last resort.** Only pull a full page into context when
   extraction genuinely cannot get what you need (an anti-bot wall, an oddly
   structured source); otherwise note the gap rather than dumping the page.

## Translate to Minecraft

One block ≈ 1 metre. Real builds are often too large to copy 1:1, so:

- Recommend a **scale factor** (e.g. 1:2) and give the resulting block
  dimensions, rounded to whole blocks.
- Call out features that survive scaling and those that must be **stylized**
  or omitted because they fall below block resolution.
- Map real materials to specific Minecraft block IDs.

## Output

Write two files under `.minecraft-builder/<project>/`:

- **`research.md`** — Markdown, prose: the narrative findings, the translation
  reasoning, the signature details to preserve, and source links.
- **`research.toon`** — TOON (<https://toonformat.dev/>), structured: the hard
  numbers the design skills consume directly. For example:

  ```toon
  reference:
    subject: Notre-Dame de Paris
    scale: "1:2"
  dimensions[3]{part,real_m,blocks}:
    overall_length,128,64
    nave_height,33,17
    tower_height,69,35
  materials[2]{element,block}:
    walls,minecraft:polished_andesite
    roof,minecraft:deepslate_tiles
  ```

Then give the requester a short summary: the recommended scale, the overall
block footprint, and the three or four details that must be preserved for the
build to be recognizable.
