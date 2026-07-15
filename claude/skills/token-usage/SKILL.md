---
name: token-usage
description: Calculate total Claude Code token usage and API-equivalent cost across ALL sessions since a given time — especially "since the last token credit reset". Use whenever the user asks how many tokens they've used, what their sessions cost, token/cost breakdown per model or per project, "how much have I burned since the reset", "usage since Monday", or anything about aggregating token consumption across Claude Code session transcripts. Also use to store/update the user's credit reset schedule.
---

# Token Usage & Cost Since Reset

Sums token usage (input, output, cache read, cache write 5m/1h) per model across
every Claude Code session transcript in `~/.claude/projects/*/*.jsonl`, and prices
it with the public API rates. This measures API-equivalent cost — what the usage
would have cost at list price — which is the standard way to quantify subscription
usage.

## How to run

Always use the system python (never a repo venv):

```bash
/usr/bin/python3 ~/.claude/skills/token-usage/scripts/token_usage.py --since 7d
```

Determining the window, in order of preference:

1. **User names a time** ("since Tuesday 6pm", "last 3 days") → pass `--since`
   with an ISO datetime (naive = local time) or relative form (`36h`, `7d`, `2w`).
2. **User says "since the last reset" and an anchor is stored** → run with no
   `--since`; the script computes the most recent reset boundary from
   `reset_config.json` (anchor + repeating period, default weekly).
3. **No anchor stored** → the script exits with guidance. Ask the user for their
   reset time (Claude Code shows it in `/usage`), then store it once so future
   runs are automatic:

```bash
/usr/bin/python3 ~/.claude/skills/token-usage/scripts/token_usage.py \
  --set-reset '2026-07-09T18:00' --period-hours 168
```

Weekly limits use `--period-hours 168`; the 5-hour session window is `--period-hours 5`.

## Useful flags

- Per-session list is printed **by default** — one row per session (cost, requests,
  output/cache-read tokens, start time, first-user-message label), sorted by cost
  descending so the most expensive session is on top. Add `--sort time` for
  chronological order, or `--no-by-session` to suppress the list.
- `--by-project` — per-project token breakdown (which repo/session dir burned the most)
- `--json` — machine-readable output for further analysis
- The default table is sorted by cost, highest first, with a TOTAL row.

## Interpreting results for the user

- Report the **total cost and total tokens first**, then the per-model split.
- Cache reads dominate token counts in agentic sessions but are cheap (0.1x input
  rate); output tokens usually dominate cost. Point this out if the user is
  surprised by a huge "tokens" number.
- Subagent transcripts (`agent-*.jsonl`) live in the same directories and are
  included automatically.
- Streamed responses appear multiple times in transcripts; the script dedupes by
  message id, so request counts are true API-call counts.

## Accuracy notes / limits

- Pricing table lives at the top of `scripts/token_usage.py` (per-MTok input/output;
  cache read = 0.1x, 5m write = 1.25x, 1h write = 2x input). If the script warns
  about an unknown model, add a row there — check current rates via the claude-api
  skill rather than from memory.
- Transcripts only exist for sessions run on this machine; usage from other
  devices or claude.ai is not visible here.
- Deleted/cleaned-up transcripts are gone from the count; treat results as a
  lower bound if `~/.claude/projects` was pruned inside the window.
