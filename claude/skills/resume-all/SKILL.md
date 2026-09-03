---
name: resume-all
description: Identify all Claude Code sessions that were open in VSCode for the current workspace and resume every dead one (each in a detached tmux session) — for recovering after a machine shutdown, reboot, or vscode-server crash. Use when the user invokes /resume-all, says "resume all my sessions", "bring back my claude sessions", "recover my vscode sessions", "the machine rebooted / shut down, restore the sessions", or asks which sessions were open before a crash. ALSO use for live-but-stuck sessions: "resume the jobs/sessions that are running but not active", paused because the usage/session limit was reached, an API error, an interruption, or a restart mid-turn — detected with `--stalled` and nudged (compact + continue) via SendMessage.
---

# Resume All (VSCode session recovery)

Recovers the fleet of Claude Code sessions that were open (VSCode extension
tabs, tmux) for the **current workspace** after a shutdown/reboot/crash killed
them. Each dead session is resumed with `claude --resume <id>` (same session
id — no fork) inside its own detached tmux session `ccr-<first 8 of id>`.

## Architecture (behaviors verified 2026-08-24, claude 2.1.241)

- Every interactive claude process registers `~/.claude/sessions/<pid>.json`
  on startup and removes it on graceful exit — **including SIGTERM**, which is
  what a normal OS shutdown sends. Only SIGKILL/crash/OOM leaves the entry,
  and **any newly starting claude sweeps dead entries within seconds**, so the
  registry alone cannot survive until the user runs this skill.
- Therefore a minutely tick (`resume_all.py --tick`) mirrors the live-session
  set into `~/.local/state/claude-resume-all/state.json` (outside claude's
  reach). On the first tick after a boot — resolve also runs a tick inline —
  sessions live at the last pre-boot tick are marked killed-by-shutdown;
  a dead registry entry seen mid-uptime (SIGKILL case) is marked immediately.
- Resolve resumes each killed session for this cwd, skipping any session id
  that is live anywhere (registry pid+starttime check, plus a /proc scan for
  `--resume <id>` — this auto-excludes the session running the skill).
  Success is verified by the resumed process re-registering under the same
  session id; then the sid is consumed from state so it cannot be
  double-resumed later.

## One-time setup per machine

```bash
bash ~/.claude/skills/resume-all/install_timer.sh
```

Idempotent. Installs + starts a systemd user timer (`claude-resume-all.timer`).
If the user D-Bus is unreachable (long-uptime SSH box with a torn-down
`/run/user/<uid>`), it still enables the timer for the next boot and starts a
detached `setsid` tick loop covering the current uptime — rerun the installer
after a reboot if `systemctl --user status claude-resume-all.timer` shows it
inactive. `resume_all.py` prints a WARNING when it detects the tick is not
running; react to it.

## Usage

Run from the workspace root (the session's cwd):

```bash
python3 ~/.claude/skills/resume-all/resume_all.py --dry-run   # list only
python3 ~/.claude/skills/resume-all/resume_all.py             # resume all dead
```

Argument mapping when invoked as `/resume-all <args>`:

| user says | run |
|---|---|
| (nothing) | first `--dry-run`, show the list, then run for real **without asking** (invoking the skill is the ask) — unless the list looks wrong, then show it and ask |
| `list` / "which sessions" | `--dry-run` only |
| `continue` / "and keep working" | add `--kick "Continue from where you left off."` |
| explicit session ids | add `--include <id> ...` |
| nothing found but user insists sessions were open (e.g. tick was never installed before the shutdown) | `--logs --dry-run` — mines IDE extension-host logs; over-inclusive (includes cleanly closed tabs), so show the list, let the user pick, resume picks via `--include` |
| `hours=N` | `--hours N` (gates `--logs`) |

| "resume the jobs that are running but not active / paused / limit reached / interrupted" | **stalled-live mode** (below) |

Other flags: `--workspace PATH` (recover another workspace), `--tick`
(snapshot mode, used by the timer).

## Stalled LIVE sessions (usage limit / API error / interruption)

Dead-process recovery above does nothing for a session whose process is alive
but idle because it hit the usage limit ("You've hit your session limit ·
resets 5pm (TZ)"), got an API error, was interrupted, or was restarted
mid-turn and never answered the last prompt. Detect those with:

```bash
python3 ~/.claude/skills/resume-all/resume_all.py --stalled --json   # list
python3 ~/.claude/skills/resume-all/resume_all.py --stalled --nudge  # act
```

Rules (verified 2026-08-25): a live session counts as stalled only if its
transcript has been untouched ≥ 2 min (moving transcript = working), and the
tail shows one of: `limit` (last substantive assistant text is the limit
banner — later "Continue" kicks that only yield "No response requested." do
not clear it; the `resets …` clause is parsed and the row is `wait` until
that time has passed), `api-error`, `interrupted` (`[Request interrupted by
user…]` last), `unanswered` (plain user prompt with no reply).

Acting — **default: `/compact` first, then the continue nudge** (user
preference 2026-08-25):
- tmux-hosted stalled sessions: `--nudge` sends both via `tmux send-keys`.
- VSCode-hosted ones (the usual case; no tmux) cannot be typed into from a
  script. The row carries the SendMessage peer name (`imaginaire4-…-xx`);
  for each `NUDGE` row send **two** SendMessage calls in order: first
  `/compact`, then a continue message that names what it was doing (take
  the title / last assistant text from the transcript tail so it re-checks
  any background monitors the limit killed). `wait` rows: report the reset
  time, do not message.
- Re-run `--stalled` afterwards: a nudged session's transcript starts moving
  within a minute, so it drops off the list — that is the success check.
- Duplicate live processes on one session id (two peer names → same sid in
  `~/.claude/sessions/*.json`) are flagged in the output header of resolve;
  message only one of them and tell the user to close the other.

## After running

- Report the table (id8, last-active, status, title) plus: attach with
  `tmux attach -t ccr-<id8>`; resumed sessions are also messageable local
  peers (ListAgents / SendMessage).
- **Warn**: if the user reopens one of these in the VSCode extension UI, the
  tmux copy must be killed first (`tmux kill-session -t ccr-<id8>`) — two
  live processes appending to one session id interleave writes.
- Failures print the tmux pane tail and are NOT consumed from state, so a
  rerun retries them.

## Notes

- Without `--kick`, resumed sessions sit idle with full context restored —
  safe default. `--kick` makes every one start acting immediately; only on
  explicit request (`/resume-all continue`).
- `ccr-*` tmux names are deliberately distinct from the `claudeN` fleet (see
  the `tmux` skill).
- Killed-but-unresumed sessions are remembered for 7 days, across reboots.
- `--stalled` cannot itself message VSCode tabs; only Claude (SendMessage)
  can. The script is the detector + tmux actuator; SKILL.md is the actuator
  for everything else.
- `entrypoint: claude-vscode` in registry/transcripts is unreliable for
  telling VSCode sessions from tmux ones (tmux servers inherit the env var);
  identification keys on cwd + process liveness instead, so tmux sessions in
  this workspace are recovered too — that is desirable for shutdown recovery.
