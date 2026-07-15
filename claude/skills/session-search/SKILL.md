---
name: session-search
description: Full-text search across Claude Code session transcripts — finds past sessions by message CONTENT, not just title (the built-in session pickers in the CLI and the VSCode/Cursor extension only match titles). Use whenever the user wants to locate or resume a past session/conversation by what was discussed in it, e.g. "find the session where we discussed X", "which chat did I fix Y in", "search my sessions for Z", "when did I talk about W with you", "did we already debug this somewhere", or any request to grep/search Claude Code history or transcripts.
---

# Session Search

Search the contents of past Claude Code sessions (all messages, not just titles) and return session IDs the user can resume.

## How

Run the bundled script (stdlib-only, use system `python3`):

```bash
python3 ~/.claude/skills/session-search/scripts/search_sessions.py TERM [TERM ...]
```

- Multiple terms are ANDed: a session must contain **all** of them (case-insensitive substring), anywhere in its user/assistant message text.
- Defaults to the current project's sessions. Results are sorted newest-first.

Useful flags:

| Flag | Effect |
|---|---|
| `--all-projects` | search every project under `~/.claude/projects/` |
| `--project PATH` | search the sessions of another project directory |
| `--regex 'PATTERN'` | single case-insensitive regex instead of AND-terms |
| `--include-tools` | also match tool inputs/outputs and metadata (file paths, command output) |
| `--thinking` | also search assistant thinking blocks |
| `--limit N` | show more than the default 10 sessions |

## Interpreting output

Each hit prints the session ID, last-modified time, number of matching messages, the session's first user message (as a title), up to 3 snippets with the match marked `«like this»`, and a ready-to-run resume command.

## Answering the user

- Report the most likely session(s) with their title, date, and a snippet — don't just dump raw output if it's long.
- Tell them how to open it:
  - Terminal: `claude --resume <session-id>` (run from the matching project directory).
  - VSCode/Cursor extension: the picker can't jump to an ID, so point them to the session by its title and date shown in the output.
- If terms are too common (many sessions match), suggest adding a second distinguishing term rather than eyeballing dozens of hits. If nothing matches, retry with fewer/shorter terms or `--include-tools` (the phrase may have appeared in command output rather than message text).
