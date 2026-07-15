---
name: star-session
description: Star/bookmark Claude Code sessions and browse the starred list for quick lookup later. Use whenever the user says "star this session", "bookmark this chat", "favorite this conversation", "save this session so I can find it later", "mark this session as important", "show my starred sessions", "list my bookmarked chats", "unstar X", or wants to resume "that starred session about Y". Also use when the user wants to star a PAST session they describe by content ("star the session where we fixed the NCCL crash").
---

# Star Session

Maintain a personal starred list of Claude Code sessions in `~/.claude/starred-sessions.json`, so important conversations can be found instantly instead of scrolling the session picker or grepping transcripts. Starring only records a pointer (session id, title, project) — it never modifies or deletes transcripts.

All operations go through the bundled stdlib-only script (use system `python3`):

```bash
python3 ~/.claude/skills/star-session/scripts/star_sessions.py <star|list|unstar> ...
```

## Star the current session

```bash
python3 ~/.claude/skills/star-session/scripts/star_sessions.py star --label "short memorable name"
```

With no session id, the script reads `$CLAUDE_CODE_SESSION_ID` from the environment, so this works from inside any running session. Always pass `--label`: the label is what makes the starred list scannable, and the user's own words for the session beat the auto-extracted title. Derive it from what the session is about (or from the user's phrasing, e.g. "star this as the launcher-refactor chat" → `--label "launcher refactor"`). If the user gave no hint, pick a concise description of the session's main topic yourself.

Re-starring an existing session is safe — it updates the label/metadata in place rather than duplicating.

## Star a past session

If the user identifies the session by content ("star the one where we debugged X"), find its id first — the `session-search` skill exists for exactly this:

```bash
python3 ~/.claude/skills/session-search/scripts/search_sessions.py TERM [TERM ...] [--all-projects]
```

Then star the id it reports (a unique prefix is enough):

```bash
python3 ~/.claude/skills/star-session/scripts/star_sessions.py star 8869950b --label "..."
```

If several search hits look plausible, show the user the candidates (title + date) and ask which one, rather than starring a guess.

## List starred sessions

```bash
python3 ~/.claude/skills/star-session/scripts/star_sessions.py list            # everything, newest star first
python3 ~/.claude/skills/star-session/scripts/star_sessions.py list --project /path/to/repo
```

Each entry shows the label, title (session summary if one exists, else first user message), project directory, and a ready-to-run resume command. Relay results readably; for resuming, note:

- Terminal: `claude --resume <session-id>`, run from that entry's project directory.
- VSCode/Cursor extension: the picker can't jump to an id — point the user at the session's label/title and date instead.

Entries whose transcript file has been deleted are flagged `transcript file no longer exists`; mention that to the user and offer to unstar them.

## Unstar

```bash
python3 ~/.claude/skills/star-session/scripts/star_sessions.py unstar <id-prefix-or-exact-label>
```

Removes only the bookmark, never the transcript. If the reference is ambiguous the script lists the candidates — show them to the user and ask.
