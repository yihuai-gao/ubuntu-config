---
name: review-worktree
description: Review every git worktree of the current workspace together with the Claude Code sessions that work(ed) in it, and triage each one — (1) actively updating → keep it, nudge the live session if it went idle, or spawn a subagent that loads the context and keeps working if the session was killed; (2) already merged into the main worktree → delete it (with a backup); (3) superseded → list it with the reason and wait for the user's decision. Use when the user invokes /review-worktree, says "review / triage / clean up the worktrees", "which worktrees are still active", "delete the merged worktrees", "what happened to the worktree sessions", or asks which worktree a Claude session is working in.
---

# Review Worktree (worktree ⇄ session triage)

Inventories `git worktree list` of the workspace, finds the Claude Code sessions
whose transcripts reference each worktree path, and classifies every non-main
worktree. The script is the detector + git actuator; everything that touches a
live session (SendMessage, tmux, subagent) is done by Claude following this file.

```bash
python3 ~/.claude/skills/review-worktree/review_worktree.py            # report (human)
python3 ~/.claude/skills/review-worktree/review_worktree.py --json     # same, machine-readable
python3 ~/.claude/skills/review-worktree/review_worktree.py --context <worktree-path>   # context bundle for a subagent
python3 ~/.claude/skills/review-worktree/review_worktree.py --delete-merged              # remove every `merged` worktree
python3 ~/.claude/skills/review-worktree/review_worktree.py --delete <path> [<path>..]   # remove specific ones (after the user decides)
```

Run from the workspace root (or pass `--workspace PATH`). Runtime ≈ 5 s per
workspace; it greps every transcript under `~/.claude/projects/` — sessions
from OTHER workspaces that worked in a worktree are found too (common: a
worktree created from a sibling repo's session).

## Categories and the action per row

| category | action | what Claude does |
|---|---|---|
| active | `keep` | a live session is **busy** in it — do nothing, report it |
| active | `attend` | live session is **waiting** (registry `waitingFor`, usually "permission prompt"). A SendMessage cannot click a prompt: tell the user which tab (peer name, or `tmux capture-pane -t <tmux>` if tmux-hosted) needs their click and what it is waiting on |
| active | `nudge` | live session is **idle** but touched the worktree inside the window. First run `--context <path>` and read the tail: confirm it was working there and did not already finish/hand off. Then ONE SendMessage to the row's `peer` naming the worktree path and what it was doing ("you were working in <path> on <task>; continue from where you left off"). tmux-hosted → `tmux send-keys -t <name> '<text>'` then a separate `Enter`. Re-run the script after ~1 min: the row flips to `keep` (busy) = success |
| active | `subagent` | the worker session is **dead** (process gone) but the worktree was touched inside the window. Spawn an `Agent` (general-purpose, `run_in_background: true`) whose prompt is the full `--context <path>` output plus: "Continue this task. Work ONLY inside <path> (use absolute paths / `git -C <path>`; the subagent cannot change its cwd). Do not touch the main worktree. Report what you completed and what remains." Mention to the user that `/resume-all --include <sid>` would instead revive the original session with its full context if they prefer |
| merged | `delete` / `prune` | every changed file is already in main (identical to main's working file, or committed verbatim to main since the worktree's base) and every commit is patch-equivalent in main — or the directory is already gone. Run `--delete-merged` **without asking** (invoking the skill is the ask); report the backup dir |
| superseded | `ask` | anything else. Present the table + reasons and **stop — the user decides**. Never delete these on your own. On a decision: `--delete <path> ...` (still backs up) or leave it |

Backups (before any removal): `~/.local/state/claude-review-worktree/backups/<name>-<ts>/`
with `tracked.patch` (staged+unstaged vs HEAD), `untracked.tar.gz`, `commits.bundle`
(commits not in main) and `info.txt`. A branch checked out in a deleted worktree is
`git branch -d`'d (safe delete only — fails loudly if unmerged).

## Argument mapping for `/review-worktree <args>`

| user says | do |
|---|---|
| (nothing) | run the report, then act on every row per the table above: keep/attend/nudge/subagent/delete immediately, list `superseded` and wait |
| `list` / "just show" | report only, no actions |
| `hours=N` | `--hours N` (recency window for "active"; default 24) |
| `delete <name>` | `--delete <path>` for that worktree (any category) |
| `context <name>` | print `--context <path>` to the user |
| `--workspace <path>` / another repo named | pass it through |

## How the classifier decides (so you can sanity-check a row)

- **Sessions**: `grep -rlF <worktree-path> ~/.claude/projects --include=*.jsonl`
  (main transcripts and `<sid>/subagents/*.jsonl`). A session is a **worker** if
  it has `"cwd":"<path>"` rows (it `cd`'d / EnterWorktree'd there) or ≥ 5
  mentions (it ran `git -C`, read/edited files there); fewer = **mention** only
  (ignored for classification). A session whose transcript invoked
  `review_worktree.py` and has no cwd rows is a **reviewer** (an earlier run of
  this skill quoting every path in its output) — also ignored. The calling session is auto-excluded (ppid walk
  against `~/.claude/sessions/*.json`; also `--exclude-sid`).
- **Liveness**: registry entry whose pid+starttime still match a claude process;
  `status` busy | idle | waiting (+ `waitingFor`). The registry `cwd` is only the
  STARTUP cwd — never use it to map a session to a worktree.
- **Landed**: a changed file counts as in-main if its bytes equal the main
  worktree's working file (main may hold it uncommitted), or equal a blob main
  committed for that path since the worktree's base (`landed_hist`: main took it
  verbatim, then evolved it). Commits: `git cherry` patch-equivalence.
- **Superseded reasons** collected: worker dead / none ("orphan": transcripts
  older than the cleanup period are gone), `N/M files not in main`, `main changed
  K of those files after the base (B commits behind)`, `main has its own version
  of files this worktree adds`, `all its unlanded files are also changed in
  <sibling worktree> (newer → likely superseded by it)`.
- **Window**: `--hours` (default 24) decides "recent" for idle/dead sessions and
  for file mtimes; a `busy` live worker is active regardless.

## Caveats

- `.claude/worktrees/<name>` (EnterWorktree default) and hand-made
  `git worktree add` paths anywhere (other disks included) are all covered —
  the source of truth is `git worktree list --porcelain` of the main repo.
- `__pycache__`, `*.pyc`, `.pytest_cache`, `*.synctex.gz` are ignored when
  counting changes.
- Content comparison is against the MAIN worktree's working tree, not a branch;
  "merged" therefore also covers changes the user copied into main by hand.
- A worktree whose files are all landed but whose session is still busy stays
  `active` — deletion waits for the session to finish.
- Two live processes on one session id (duplicate tabs) show as the same sid;
  message only one peer.
