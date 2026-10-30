---
name: review-worktree
description: Deeply review Git worktree lifecycle, remaining changes, update times, remote coverage, and Codex session ownership. Use for $review-worktree, /review-worktree, worktree inventory, abandoned work, or cleanup candidates. Reports are read-only; this is not a static code review or permission to merge or delete.
---

# Review worktrees with Codex sessions

Review the current repository's Git worktrees and explain the concrete work that
still needs each checkout. Deep analysis is the default on every invocation:
inventory and activity labels are inputs, not a completed review. Determine which
changes are already committed, superseded, worth integrating, or candidates for
archival and removal, and connect each recommendation to evidence.
Use this workflow for both `$review-worktree` and the text `/review-worktree`.
Do not substitute `static-review` for this skill.

## Report

Run the bundled script relative to this skill directory:

```bash
python3 scripts/review_worktree.py --workspace /absolute/path/to/repository --live-remotes --json > /tmp/worktree-review.json
python3 scripts/review_worktree.py --workspace /absolute/path/to/repository --context /absolute/path/to/worktree
```

The default and `list` requests are read-only. Capture the JSON to a temporary
file and summarize selected fields; do not flood the conversation with ignored
paths or full session transcripts. Omit `--live-remotes` only for an explicitly
offline request or after reporting a connection failure. Live queries do not
fetch, push, or update remote-tracking refs.

Map `hours=N` to `--hours N`; the default window is a rolling 24 hours, not
"yesterday" on the calendar. It prioritizes investigation; it is not an expiry
deadline or a veto against analyzing recent work. Honor an explicitly named workspace.
Report the actual main worktree from Git, even when invoked from a linked
worktree. The helper uses `git --no-optional-locks` and never edits, stages,
commits, removes worktrees, or resumes sessions.

Present a compact table with worktree, branch, last content update, last workspace
use/reference, session status, remaining work, and a concrete disposition. Give
the timestamp/timezone of the snapshot and abbreviated session IDs/titles where
useful; put full evidence in the saved JSON. Separate "retained: unique config
cache needs tests" from "retained: owner is currently editing it." Include counts
for retained, merge candidates, archive/remove candidates, unresolved cases, and
live-verified versus cached remote matches. After any requested action, report
actual outcomes and a fresh remaining count. Attribute concurrent changes to
other activity only when observed; do not claim their removals as your own.

Include session-data, process-inspection, and Git errors; incomplete evidence is
not proof that a worktree is disposable. A meaningful unresolved result names
the specific missing evidence and next check, not merely "unmerged; investigate."
An empty worktree inventory is a complete report, not a reason to review code.

## Deep analysis on every invocation

1. **Separate the clocks.** Report content updates (latest commit and changed
   file mtime), checkout/reflog times, index activity, workspace use, and path
   references separately. A read-only review or cached index refresh is not a
   code update. A recovery commit can be newer than the original work; label it.
   Neither a recent timestamp nor a loaded tab proves an unfinished task.

2. **Establish actual ownership.** Read session context for candidates whose
   disposition depends on an unfinished task or an apparently loaded owner.
   A tool input mentioning another checkout, including `git -C ... diff`, is
   reference evidence, not proof of ownership. Structured workspace/execution
   cwd is stronger evidence, but review the task and latest actions before
   treating it as a reason to retain. Deduplicate thread IDs across rollouts.
   Check process cwd/open-file references. A sleeping terminal shell with no
   children and only a cwd reference is an idle-shell candidate, not an active
   job; this does not establish Codex liveness. Do not kill processes. When
   explicitly authorized retirement includes such a checkout, recheck the
   shell and explain that its terminal will need to `cd` elsewhere.

3. **Compare the actual work.** Identify the main worktree and its exact branch
   and HEAD; do not silently substitute the branch named `main` or `origin/main`.
   Inspect unique commits and both staged and unstaged changes. Compare changed
   paths with committed main **and** its current working copy; a match only in
   uncommitted main is not landed work. Distinct staged content must be preserved
   even if the working file matches main. Inspect renames/deletions, modes,
   symlinks, ignored outputs, and submodules before recommending cleanup.

4. **Resolve the residual differences.** Read relevant diffs, nearby code,
   commit history, and task context. For files apparently superseded, identify
   the concrete newer implementation/fix. For a worktree containing a broad
   copied baseline, distinguish that baseline from its own remaining change.
   Overlap with a sibling checkout is only a lead: compare content and identify
   which copy is authoritative. Do not call two changes equivalent based on
   filenames, diff size, similar titles, or patch counts alone. Identify focused
   merge candidates and their required validation; avoid merging an entire old
   branch merely to retire its checkout. Inspect recent work too: 140 changed
   files can contain 139 already-integrated copies and one useful remaining fix.

5. **Verify recoverability and remote coverage.** Check the configured upstream
   and same-named remote branches with a bounded live query. Distinguish an exact
   tip match, differing tips, missing branch, no upstream, and unavailable remote.
   Failed DNS/auth/network checks leave live status unknown even when cached refs
   match. A remote tip covers commits, not staged, unstaged, untracked, or ignored
   data. A remote-backed checkout may still be in use; a local-only branch may
   still be recoverable through retained refs and a verified bundle.

6. **Make a disposition.** For each linked worktree, recommend retain for a
   named active task, integrate a named change then retire, archive/drop a
   superseded experiment, or perform a specific unresolved check. Explain why
   it still needs a working directory. Do not stop at helper categories, age,
   a missing transcript, an unknown lock, or an open terminal. These are
   evidence to investigate, not permanent retention rules or deletion proof.

## Interpret helper categories

- `main` / `current` / `locked`: retain the main, current, or locked worktree.
- `active`: a loaded session has workspace evidence. Read context to confirm
  current ownership and whether its task is unfinished; protect genuine work
  in progress. Reference-only sessions do not establish activity in that tree.
- `recent`: content, checkout/index, or workspace evidence is within the window.
  Inspect the separate clocks and remaining diffs; this is not proof that the
  work is unfinished or that the directory must be kept.
- `merged`: Git proves HEAD is an ancestor of main and the index and working
  tree are clean, with no untracked or ignored files. This is a cleanup candidate,
  not an instruction to delete it during a report.
- `landed`: patches or local content appear in main, but ancestry, the index,
  or local files still need examination. Never equate this with safe deletion;
  the helper cannot decide whether different code has been superseded.
- `unmerged`: unique commits or local changes remain. Overlap with another
  worktree is a lead for investigation, not proof it was superseded.
- `missing` / `unknown`: report the missing directory or inspection error.

Session records come from `${CODEX_HOME:-$HOME/.codex}`: rollout JSONL files,
the optional read-only thread database for titles, and thread writer locks.
The script separates structured cwd evidence from tool-input path references;
text quoted in user messages, assistant prose, or tool results is not ownership
evidence. It excludes the invoking `CODEX_THREAD_ID` and its own inventory tool
calls. Codex may not retain transcripts for all sessions: no match means
"no local Codex evidence", not "abandoned".

A held writer lock means a session is loaded, not necessarily generating.
`loaded; unfinished turn` can include a user-input wait. `not loaded` is a
snapshot, not evidence of a crash. A session without a readable lock has unknown
liveness. Do not replace these statuses with guesses based on process names,
timestamps alone, or Claude's session registry.

## Requested follow-up actions

For a resume request, read the context and identify the unfinished task first.
Use collaboration tools only for agents actually listed in this conversation's
agent tree. A Codex thread UUID is not a collaboration agent ID. For an independent
existing session, provide its ID and `codex resume <id>`; do not start a competing
worker or claim that you sent a message to an unrelated tab.

For an explicit cleanup request, recheck each named candidate immediately before
removal. Protect current, main, locked, and genuinely in-use worktrees. Resolve
uncertainty with the deep checks above instead of repeatedly asking for approval
already given. Follow the user's chosen age/scope and merge-versus-drop policy;
do not infer deletion or merge authorization from invoking this review skill.
If a choice would discard unique work outside that authorized scope, finish
the concrete comparison and ask which work to retain. State the exact blocker
and this skill's applicable rule when work must remain unfinished.

Inspect submodules and ignored files. Back up tracked changes with
binary staged and unstaged patches, untracked and ignored files, and unique
commits in a verified Git bundle before any authorized removal that could lose
data. Stop on a backup failure. Use ordinary `git worktree remove` for a verified
clean candidate; never fall back to `--force`, `rm -rf`, blanket pruning, or
branch deletion to get past a refusal. Report backup paths and actual outcomes.
An authorized dirty-worktree retirement may first save reviewed local files in
an isolated archival snapshot, verify the bundle and file archive, and only then
make that checkout clean for ordinary removal. Preserve original staged and
unstaged patches separately. Never sweep unrelated main-tree edits into an
archive commit, overwrite concurrent work, or commit credentials. Archiving a
snapshot is not merging it, and a recoverable archive is not proof that the work
was already integrated. Do not invent broad Git mutations to bypass a refusal.

For authorized integration, work from the current target, port only the needed
change, follow repository instructions, run relevant checks, and recheck the
source and target before retiring the source. Keep the user's existing changes
intact. Report what was merged, dropped, archived, or left unresolved separately.

## Discovery

The installed copy belongs in `$CODEX_HOME/skills/review-worktree`. This source
copy in `ubuntu-config/codex/skills/review-worktree` is compatible with the
repository's Codex skill installer. If a newly installed skill is absent from
the picker, use Codex's **Force reload skills** command (or reload the extension).
A successful `--help` invocation does not validate Codex skill discovery; check
`skills/list` with `forceReload: true` when diagnosing a stale skill list.

When maintaining this skill, update its `ubuntu-config/codex/skills/review-worktree`
source and installed copy together, preserving unrelated repository changes.
Run `PYTHONPATH=scripts python3 -m unittest discover -s tests -v` and validate
the skill metadata. Exercise the helper on a real read-only inventory; tests
must cover ownership versus references, staged data, committed versus working
main, timestamps, process references, and live versus cached remote state.
