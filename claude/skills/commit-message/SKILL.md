---
name: commit-message
description: Review the current pending changes (staged, or all uncommitted if nothing is staged) and generate a single one-sentence commit message that matches this repo's commit style. Use whenever the user asks for a commit message, asks "what should I call this commit", wants to summarize the current diff for a commit, or invokes /commit-message. This skill only proposes the message — it does not commit unless the user explicitly asks.
---

# Commit Message Generator

Generate one concise, one-sentence commit message describing the current pending changes.

## Workflow

1. **Determine what would be committed.** Check staged changes first:
   ```bash
   git diff --cached --stat
   ```
   - If there are staged changes, describe only those (that is what `git commit` would pick up).
   - If nothing is staged, fall back to all uncommitted changes: `git diff --stat` plus untracked files from `git status --short`.

2. **Read the actual diff, not just filenames.** Run `git diff --cached` (or `git diff`) and skim it. The message must reflect what the change *does*, not which files it touches. For large diffs, read the stat output first, then inspect the few files with the biggest or most meaningful changes to find the intent (new feature, fix, refactor, config change).

3. **Match the repo's existing style.** Check recent history:
   ```bash
   git log --oneline -10
   ```
   Follow whatever style the recent log actually shows — e.g. conventional-commit prefixes (`fix:`, `feat(scope):`) if the log uses them, or plain capitalized imperative sentences with no trailing period (`Fix data loader view & refactor launcher`) if it doesn't. When the log is empty or inconsistent, default to the plain imperative style.

4. **Write one sentence.** Rules:
   - Imperative mood ("Add", "Fix", "Refactor", not "Added" or "Adds").
   - Lead with the most significant change; if the diff has 2–3 distinct themes, join them with `&` or `and` as the log style does. Don't enumerate every file.
   - Keep it under ~72 characters when possible.
   - No period at the end, no body, no bullet list — a single subject line.

5. **Output.** Present the message on its own line (in a code block so it's easy to copy), followed by a one-line note of what it covers if the diff was ambiguous (e.g. "based on staged changes only; N files unstaged"). Do **not** run `git commit` unless the user explicitly asked to commit.

## Examples

**Diff:** new `launcher_lepton.py` + `launcher_slurm.py` split out of `launcher.py`, plus small callback fixes
**Message:** `Split launcher into Lepton and Slurm backends & fix callbacks`

**Diff:** one-line bug fix in dataset sharding logic
**Message:** `Fix token-based shard assignment off-by-one`

**Diff:** config value changes across several trainer yamls
**Message:** `Update trainer configs for longer validation cadence`
