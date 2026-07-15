---
name: tmux
description: Spawn and manage Claude Code sessions running inside tmux (the claudeN sessions). Use whenever the user asks to spawn/start/open a new Claude session in tmux, "new cloud session in tmux" (voice-to-text often garbles this as "cloud concession in Temux"), list the running Claude tmux sessions, check what a session is doing, send a prompt to one, or kill/clean up one. Triggers on any mention of tmux together with Claude sessions.
---

# Claude-in-tmux Session Manager

Manage the fleet of Claude Code instances the user keeps running in detached tmux sessions (`claude2`, `claude3`, ... — one window each, all running `claude` in a repo checkout).

## Conventions

- Session names are `claudeN`. To spawn, list existing sessions and pick the next free number — never reuse a live name.
- New sessions start in the current repo directory unless the user names another path. Match the setup of the existing sessions (check with `tmux list-panes -t <name> -F '#{pane_current_command} #{pane_current_path}'`) rather than assuming.
- The command is plain `claude` (no flags) unless the user asks otherwise.

## Spawn a new session

```bash
tmux ls                                   # find existing claudeN names
tmux new-session -d -s claude<N> -c <repo-dir> claude
sleep 3
tmux capture-pane -t claude<N> -p | grep -v '^$' | tail -15   # verify it reached the prompt
```

Verification matters: `new-session` succeeds even if `claude` immediately dies (bad dir, auth issue), so always capture the pane and confirm the input prompt / mode line is visible before reporting success. If the session is gone from `tmux ls` right after creation, the command crashed — rerun `claude` manually in a shell to see the error.

After spawning, tell the user the session name and that they can attach with `tmux attach -t claude<N>`.

## Inspect / interact with a session

- **See what it's doing**: `tmux capture-pane -t <name> -p | tail -40` (add `-S -200` for more scrollback).
- **Send a prompt**: `tmux send-keys -t <name> '<text>'` then a separate `tmux send-keys -t <name> Enter` — sending Enter in the same call can get swallowed by the TUI's paste handling. Wait a few seconds and capture the pane to confirm it was submitted.
- **Kill**: `tmux kill-session -t <name>` — but only when the user asks; capture the pane first and warn if the session appears mid-task.

## Caution: concurrent sessions share the git index

Multiple Claude sessions in the same checkout share `.git/index`. A `git add`/`git reset` in one session changes what another session's job submission packs (submissions snapshot the index). When spawning a session that will touch git state alongside others, remind the user, and prefer `GIT_INDEX_FILE=<tmpfile>` for index-packing operations or a separate worktree for code-writing sessions.
