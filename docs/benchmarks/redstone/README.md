# Redstone benchmarks

A ladder of prompt-plus-criteria files for the Ashlar redstone skill. Each rung
file holds the request as the user would type it, the fixed test quantities and
numbered pass criteria. A rung file never holds coordinates, layouts or
schematics, so a run cannot copy an answer. The prompts are drafts; the user may
edit them.

## Ladder

| Rung | File | Machine | Who tests | In the done bar |
| --- | --- | --- | --- | --- |
| 0 | [00-calibration.md](00-calibration.md) | Throwaway calibration build (7 checks) | The implementer, via an ordinary plan | Yes: runs first, after the merge |
| 1 | [01-sorter.md](01-sorter.md) | Two-item sorter with overflow | The agent, for everything | Yes |
| 2 | [02-door-2x2.md](02-door-2x2.md) | 2×2 sticky-piston door | The user flips the lever; the agent confirms each state | Yes |
| 3 | [03-cane-farm.md](03-cane-farm.md) | Observer sugar cane farm | The agent, during a long `await` | No |
| 4 | [04-clock.md](04-clock.md) | Controllable clock | The user's switch, or the agent with a test input and pulse counter if accepted | No |
| 5 | [05-door-3x3.md](05-door-3x3.md) | 3×3 piston door | As in rung 2 | No |

The done bar is rung 0 run, rung 1 passing (tested by the agent over two
batches) and rung 2 passing the user's ten cycles. They run in that order, in
the main workspace, after the merge. Rungs 3 to 5 are not part of the done bar.

## Run protocol

1. Start a fresh session (Claude Code or Codex) in the workspace root and paste
   only the prompt. The agent must not read `docs/benchmarks/` during a run;
   the skill never points there, and the runner checks the transcript.
2. The agent surveys and picks a scratch site away from players and other
   builds (no `bbox` overlap in `registry.json`), or uses a site the runner
   names.
3. The runner approves or refuses at each gate, as for any build.
4. After the report, record the result in
   `.minecraft-builder/benchmarks/redstone-results.md` in the workspace, not the
   repo: date, rung, variant, client and model, the server and Ashlar versions
   from `mc_status`, the four verdicts, each criterion with its evidence,
   snapshots used, fix rounds and notes.
5. Roll the machine back with `exec-ashlar rollback <project>` once the result
   is recorded, unless the runner keeps it.

## Variants

Once a rung passes:

- **Orientation:** the same prompt with the machine facing each other
  direction, and a mirrored layout. Same criteria.
- **Footprint:** the same prompt with a tighter space limit (each rung file
  names one). It passes if the machine meets the same criteria, or if the agent
  explains clearly why it cannot fit, with the smallest space it would need.
- **Recovery A, stopped build:** the runner stops a build after its first phase,
  by refusing the next gate or ending the session. A fresh session must find the
  project in the registry, report what was built, and resume or roll back
  cleanly when asked.
- **Recovery B, planted fault:** after a pass, the runner breaks one component
  in game (for example removes a torch or turns a repeater). For an agent-tested
  rung, the agent must find the fault through a failed test and fix it through a
  gate within three fix rounds.

## Results format

Results go in the workspace file
`.minecraft-builder/benchmarks/redstone-results.md`, outside the repo. The runner
creates it on the first run and appends one row per run to this table:

| date | rung | variant | client | model | server version | Ashlar version | built | at rest | agent tested | manual | criteria | snapshots used | fix rounds | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Column notes:

- **date**: the run date, `YYYY-MM-DD`.
- **rung**: `0` to `5`.
- **variant**: `base`, `orientation`, `mirrored`, `footprint`, `recovery-A` or
  `recovery-B`.
- **client** and **model**: for example Claude Code or Codex, and the model name.
- **server version** and **Ashlar version**: read from `mc_status`.
- **built**, **at rest**, **agent tested**, **manual**: the four verdicts
  (`pass`, `fail` or `n/a`).
- **criteria**: each numbered criterion with its evidence, for example
  `1 pass (gate log); 2 pass (check clean)`.
- **snapshots used**: the number of snapshots taken or restored.
- **fix rounds**: the number of fix rounds after the first build.
- **notes**: anything else.
