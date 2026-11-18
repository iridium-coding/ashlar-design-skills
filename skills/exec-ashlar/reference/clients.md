# Client-specific tools

Every step in these skills works with Ashlar's tools, a shell and file access.
Where a client has a better tool, skills name it on a labelled line:

```markdown
- Claude Code: use `AskUserQuestion` for the multiple-choice questions.
- Codex: use `request_user_input` for them if it is listed among your tools.
- Otherwise: ask them in plain text.
```

Follow the shared text plus your own client's line. If your client's tool is
missing, use the `Otherwise:` line.

| Capability | Claude Code | Codex | Otherwise |
| --- | --- | --- | --- |
| Structured interview questions | `AskUserQuestion` | `request_user_input`, if it is listed | plain-text questions |
| Viewing offline PNGs (voxel renders) | `Read` on the file | `view_image` | report the numbers from `mc_inspect` and ask the user to open the file |
| Web research (`survey-research`) | `WebSearch`, `WebFetch` | its web search tool, if enabled; `trafilatura -u <url>` in the shell | `trafilatura -u <url>` |
| Tracking a long build | the task or todo tool | `update_plan` | a checklist in `build-log.md` |
| Finding a skill's folder for scripts | `${CLAUDE_SKILL_DIR}` | the folder holding the skill's `SKILL.md` | the folder holding the skill's `SKILL.md` |
| Handing off to a skill | the Skill tool, or `/exec-ashlar` | `$exec-ashlar`, or open its `SKILL.md` | open its `SKILL.md` |

Images from Ashlar's `mc_render` and `mc_survey` arrive as tool results in both
clients, so they need no special handling.

## Frontmatter

- Claude Code uses `model`, `effort` and `allowed-tools`; Codex ignores them.
  `allowed-tools` lists only the read-only Ashlar tools
  (`mcp__ashlar__mc_status`, `mcp__ashlar__mc_players`,
  `mcp__ashlar__mc_survey`, `mcp__ashlar__mc_render`,
  `mcp__ashlar__mc_inspect`), never `mc_build`, `mc_snapshot`, `mc_restore` or
  `mc_command`.
- Codex shows `metadata.short-description` in its skill list; Claude Code
  ignores it.
- Tool names in shared text have no client prefix: `mc_build`, not
  `mcp__ashlar__mc_build`.
