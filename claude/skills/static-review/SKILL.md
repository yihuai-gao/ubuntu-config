---
name: static-review
description: Statically review the current git repo's pending changes — read the diff and surrounding code, report potential bugs, correctness issues, and improvement opportunities, then automatically apply every [easy fix] finding (leaving [substantial] ones for discussion) and propose a commit message. Default target is everything uncommitted (staged, unstaged, untracked); when the working tree is clean it reviews the LAST COMMIT (HEAD) instead; an explicit commit, range or path argument overrides both. Use when the user asks to review uncommitted/local/working-tree changes, "review my changes", "static review", "look over my diff", "review the last commit", or wants feedback before committing or pushing. The analysis itself is pure static reading — no builds or tests are run.
argument-hint: "[<commit>|<rev-range>|<path> ...]"
---

# Static Review

Review a change set in the current git repository by reading code only, then auto-apply the easy fixes. During the ANALYSIS phase no commands are run beyond `git` inspection — no builds, tests, linters, or formatters; after the report, the [easy fix] findings are applied to the working tree (followed by compile/lint checks of the touched files where the repo's conventions call for them).

## Target selection (user directive 2026-10-06)

Decide the review target FIRST, in this order, and name the chosen mode in the first line of the report:

1. **Explicit argument** (`$ARGUMENTS`): a commit (`HEAD~1`, a sha, a tag), a range (`main..HEAD`, `abc123^..def456`) or one or more paths. A commit or range is reviewed in *commit mode*; a path list narrows *working-tree mode* to those paths.
2. **Working-tree mode (default)** when anything is uncommitted: unstaged modifications, staged modifications, or untracked files (ignored files do not count).
3. **Commit mode fallback**: when the working tree is clean, review the last commit, `HEAD`. Say so explicitly ("the working tree is clean; reviewing the last commit `<short sha> <subject>`") so the user knows no pending edit was overlooked.

```bash
# empty output = clean tree -> commit mode on HEAD
git status --porcelain --untracked-files=all
```

In commit mode the change set is the commit's patch against its parent (a root commit against the empty tree); the same categories, tags, fix pass, staging loop and commit message apply, with the differences marked **[commit mode]** below.

## Workflow

1. **Gather the changes.**

   Working-tree mode:
   ```bash
   git status
   git diff            # unstaged
   git diff --staged   # staged
   ```
   For untracked files, list them from `git status` and read each in full.

   **[commit mode]**:
   ```bash
   git log -1 --format='%h %an %ad%n%s%n%n%b' --date=iso-local HEAD   # or the given commit / range
   git show --stat --format= HEAD
   git diff-tree -p --root -M HEAD                                      # full patch, works for a root commit too
   # a range: git log --oneline <range>; git diff <range> -M
   ```
   Also read the commit message against the patch: a message that claims something the diff does not do (or hides something it does) is a 🟡 finding — it is the record the next reader trusts.

   **Always run the large-file check in this step (user directive 2026-09-19)** — the GitLab server refuses the WHOLE push when any file is over 5 MiB (5,242,880 bytes) and not a Git LFS pointer, and by then the blob sits inside commits that must be rewritten:
   ```bash
   # working-tree mode: every changed / staged / untracked file over 5 MiB (bytes, largest first)
   { git diff --name-only -z; git diff --staged --name-only -z; git ls-files -z --others --exclude-standard; } \
     | sort -zu | xargs -0 -r stat -c '%s %n' 2>/dev/null | awk '$1 > 5242880' | sort -rn
   # commit mode: every blob the reviewed commit adds or changes that is over 5 MiB (size, path)
   git diff-tree -r --root --no-commit-id --name-only -z HEAD | xargs -0 -r git ls-tree -r -l HEAD -- \
     | awk -F'\t' '{split($1,a," "); if (a[4]+0 > 5242880) print a[4], $2}'
   # both modes: blobs already inside UNPUSHED commits (the push is refused even if the working tree is fixed)
   git rev-list --objects HEAD --not --remotes | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | awk '$1=="blob" && $2 > 5242880'
   ```
   In the cam_uva checkout the same check is one call: `/usr/bin/python3 projects/cosmos3/cam_uva/scripts/ops/check_large_files.py --worktree` (exit 1 = findings; drop `--worktree` in commit mode).

2. **Read enough context.** A diff hunk alone is rarely enough. For each changed region, read the surrounding function/class and, when relevant, the callers, callees, and definitions of touched symbols. Do not review hunks in isolation — many real issues live at the boundary between changed and unchanged code. Read files with whatever the session's tool guidance prefers (the Read tool, or `sed -n` / `cat` in Bash-first mode).

   **Fan out when the change set is divisible (global rule, 2026-10-06; by functionality, user 2026-10-21).** Before reading in depth, sort the changed files by the functionality they implement (a module, subsystem or feature: harness server vs. keeper vs. dashboard vs. tests, for example; a test file travels with the code it tests). When the files clearly span several functionalities, split along those lines and launch ONE read-only `Agent` subagent PER FUNCTIONALITY, as many as there are functionalities, all in a single message (`model: "opus"`, the current account, no account question), regardless of how small each group is; a group that is one file is still its own subagent. Without a clear functional split, fall back to the size rule: over roughly 4 changed files or 400 diff lines, split the files into disjoint groups and launch one subagent per group; under that, review inline. Each subagent gets a self-contained prompt: the repo path, the mode and target, its file list, the categories and tags below, and the instruction to return candidate findings as `file`, `line`, `summary`, `failure_scenario`, fix-effort tag. Subagents never edit. Collect every subagent's candidates, then run the **verify pass yourself** in the orchestrating session: re-read the cited code for every candidate and mark it CONFIRMED, PLAUSIBLE or REFUTED; drop REFUTED candidates and merge duplicates before reporting. Project rules that forbid subagents for a tree (cam_uva: `camera-cross-embodiment`, iPhUMI) still win.

3. **Analyze.** Look for the categories below.

4. **Report.** Produce the findings (format below). Never modify any files before the report is presented.

   **Harness rendering (latest harness).** When the `ReportFindings` tool is available in the session, call it ONCE with every verified finding ranked most-severe first (`file`, `line`, `summary` prefixed with its fix-effort tag, `short_summary`, `category`, `failure_scenario`, `verdict` CONFIRMED / PLAUSIBLE; `level` = the effort the review ran at) so the host UI renders the list, and do NOT repeat the findings as text. The text message then carries only the header line (mode, target, file and finding counts), the **Summary** section and the tally. Without the tool (an older harness, or inside a subagent) print the full markdown format below instead. Either way the final message of the turn still carries the self-contained [substantial] list of step 6.

5. **Auto-apply the easy fixes.** Immediately after presenting the report, apply every finding tagged **[easy fix]** — bugs, issues, and suggestions alike — to the working tree, without waiting to be asked. Leave every **[substantial]** finding untouched and list them at the end as open discussion points. Details:
   - For a mixed finding ("[easy fix] to guard, [substantial] to fix properly"), apply only the easy guard; the proper fix stays a discussion point.
   - If an easy fix turns out to require design decisions or interface changes mid-edit, stop, reclassify it as [substantial], and say so — never force it through.
   - **Fix in parallel when the review was fanned out (user 2026-10-21).** Group the [easy fix] findings by the same functionality split as the review and, when more than one group has fixes, launch one implementation `Agent` subagent per group in a single message (`model: "fable"`, the current account), each with a self-contained prompt: the repo path, its findings in full (location, what is wrong, the intended fix), the exact files it may edit (disjoint from every other subagent's), the repo's compile/lint gate for those files, and the instruction to report each finding as fixed, skipped (with the reason) or reclassified [substantial]. Fix subagents never touch files outside their list and never run `git add`, `git commit` or any other index-changing command: the orchestrating session re-reads every edited hunk, runs the gates once more and stages (next bullet). A single group, or fixes that would overlap in one file, are applied inline.
   - Follow the repo's own landing conventions for edits when present (e.g. this checkout's worktree-first + staged-baseline flow, compile/lint gates on touched files).
   - When a fix changes user-facing text elsewhere (README, docstrings, help strings), update those in the same pass so docs stay consistent with the new behavior.
   - **Stage every file the fix pass touched (user directive 2026-08-28): `git add` each fixed file right after the edits pass their compile/lint/test gate, without being asked.** Staging is part of landing a fix in this checkout ("land" = diff→apply→add); an unstaged fix over an already-staged hunk is easy to lose and shows up as a confusing `MM`. Stage by explicit path (never `git add -A` / `-u` / `.`) and confirm with `git status --short` afterwards. This is staging, NOT committing: `git commit` stays off-limits unless explicitly asked.
   - **[commit mode]** the fixes land as NEW uncommitted changes on top of the reviewed commit and are staged the same way. Never `git commit --amend`, rebase or otherwise rewrite the reviewed commit; a fix-up is the user's call (offer `git commit --fixup=<sha>` or a plain follow-up commit in the closing note).
   - Close the pass with a short per-finding list of what was applied (finding number → file → one-line description), and state that the fixed files are staged. When the report went through `ReportFindings`, call it again with the same findings and an `outcome` on each (`fixed`, `skipped`, `no_change_needed`) instead of re-listing them as text; the per-finding text list is then only for skipped items (one line each, with the reason).

6. **Stage everything that passed review, then loop until nothing is unstaged (user directive 2026-09-07).** After the fix pass, `git add` (explicit paths) EVERY file the review covered and found acceptable — the reviewed-and-clean files as well as the fixed ones, including dashboards, docs, memory notes and untracked files that belong to the change set (an untracked file is a new file: read it in full before staging; a secret-shaped string or a stray artifact is a finding, not something to stage). Then run `git status --short` and look for anything still unstaged (` M`, `MM`, `AM`, `??`): those are changes the review has NOT covered yet (edited by the user or another session mid-review, or skipped) — review them with the same workflow (read, findings, easy fixes, gates), stage them, and re-check. Repeat until `git status --short` shows no unstaged or untracked entry; the review is not finished while any remain. Two exceptions, each reported explicitly instead of staged: a file that must NOT be staged because a finding is still open on it (say which finding), and a file whose unstaged content is another session's live, in-progress edit that would break if frozen now (say whose). Never resolve the loop by discarding, stashing or resetting anyone's changes.
   - **[commit mode]** the tree was clean at the start, so the only files to stage are the fix pass's; an entry that appears mid-review belongs to someone else's live work and is reported, not reviewed, unless the user asks.
   - **The closing [substantial] discussion-point list must be SELF-CONTAINED (user directive 2026-08-24): restate each open finding in full** — clickable location, what's wrong, the concrete consequence, and the suggested fix — never just a one-line label with the finding number. The final message is what the user reads last; a brief recap forces them to scroll back to the report (or the rendered findings list) to recover the details.

7. **Generate a commit message.** After the staging loop of step 6 ends clean (or after the user asks for fixes of substantial findings), finish by directly generating a commit message — do not wait to be asked. Default format (user directive 2026-08-17): ONE short imperative summary line of AT MOST 50 characters — at that length it cannot enumerate everything, so name the dominant theme(s) of the FULL uncommitted change set (the original reviewed changes plus the applied fixes, not just the fixes) and drop the rest; expand toward the `commit-message` skill's longer one-sentence style only when the user explicitly asks for a longer message. Present it in a code block, and do NOT run `git commit` unless explicitly asked.
   - **[commit mode]** the message describes the staged fix pass only (the reviewed commit already has its message). When the fix pass applied nothing, there is nothing to commit: say so and skip the message.

8. **Thorough review requested → also save the report (global rule).** When the user asked for a thorough review, audit or written report, write the complete report to a markdown file at the project's report location (cam_uva: `projects/cosmos3/cam_uva/docs/<topic>_<MMDD>.md`; otherwise `<repo root>/docs/reviews/<topic>_<MMDD>.md`) and end the reply with its absolute path as a clickable link. Do not `git add` the report unless asked. A plain `/static-review` does not write a file.

## What to look for

**Correctness & bugs**
- Logic errors, off-by-one, inverted conditions, wrong operator
- Null/None/undefined dereferences; unhandled `Optional` / empty-collection cases
- Incorrect or missing error handling; swallowed exceptions
- Resource leaks (files, sockets, locks, GPU memory, db connections not closed)
- Concurrency: race conditions, shared mutable state, non-atomic updates
- Off-nominal paths: early returns, edge inputs, boundary values
- API/contract mismatches: wrong argument order, type, or count vs the definition
- Mutated function defaults, aliasing bugs, unintended shared references
- Moved or extracted code that dropped a guard; a config default silently flipped; setup/teardown asymmetry in tests

**Consistency with the codebase**
- Diverging from established patterns, naming, or idioms in nearby code
- Reinventing a helper that already exists in the repo
- Config/constant drift (a value changed in one place but not its siblings)
- A CLAUDE.md / rules-file convention the change breaks (name the rule)

**cam_uva self-containment (only when reviewing code under `cam_uva`)**
- All code inside `cam_uva` must be self-contained: it must NOT import from the `imaginaire` codebase.
- Flag any `import imaginaire...` or `from imaginaire... import ...` (and any indirect dependency that pulls in `imaginaire`) in changed `cam_uva` files as a 🔴 correctness issue.
- Suggestion: vendor/copy the needed functionality into `cam_uva`, or replace it with a self-contained equivalent.

**Oversized files (GitLab 5 MiB push limit — user directive 2026-09-19)**
- Any changed, staged, untracked or committed-in-target file **over 5 MiB (5,242,880 bytes)** that is not tracked by Git LFS (`git check-attr filter -- <path>` ≠ `lfs`) is a 🔴 finding, ALWAYS — the server rejects the entire push (`remote: GitLab: File "…" is larger than the allowed size of 5 MiB`), and once committed the blob has to be rewritten out of every unpushed commit. **Never stage such a file** (Workflow step 6 exception: finding still open), and the review does not end "clean" / does not propose a commit message while one remains.
- A file between **4 MiB and 5 MiB** that is generated and grows with the data (tables, manifests, lock files, notebooks with outputs) is a 🟡 finding: it will cross the limit on the next regeneration.
- A blob over the limit that is already in an unpushed commit (including the commit under review in commit mode) is a 🔴 **[substantial]** finding even when the working tree no longer holds it: report the commit(s) and the exact history-rewrite needed; never rewrite history yourself without explicit approval.
- Fixes, in order of preference: shrink the encoding (compact JSON `separators=(",", ":")` instead of `indent=`, fewer float digits, drop derivable fields, gzip/parquet for tabular data) and make the GENERATOR write that form and refuse an output over the limit, so a regeneration cannot regress; move the artifact out of git (HF / GCS / shared disk) and commit a pointer; Git LFS only when the repo already uses LFS for that file type. Re-encoding an existing data file in place is an [easy fix] only when the loader parses it identically; changing the format or location is [substantial].

**Security & safety**
- Injection (SQL/shell/path), unsafe deserialization, eval of untrusted input
- Hardcoded secrets/credentials/tokens
- Missing input validation on external/user data

**Robustness & maintainability**
- Dead code, unreachable branches, leftover debug prints / commented-out blocks
- Magic numbers/strings that should be named
- Overly broad `except` / catch-all error handling
- Missing or misleading docstrings/comments where logic is non-obvious
- Tests: changed behavior without corresponding test updates

**Improvements (lower priority, label as suggestions)**
- Simplifications, readability, reducing duplication
- Performance: avoidable allocations, N+1 patterns, redundant work in loops
- Better names, clearer structure

## Output format

Group findings by severity. Skip empty groups. Reference exact locations as clickable links (`[file.py:42](path/file.py#L42)`). Every finding states a concrete failure scenario (inputs or state → wrong output, crash or cost), not a generic worry.

**Fix-effort classification:** every finding (bugs, issues, AND suggestions) must carry a fix-effort tag:
- **[easy fix]** — a localized change: a few lines in one or two spots, no design decisions, no interface/contract changes, negligible re-validation (e.g. add a guard, clone a tensor, fix an off-by-one, correct a docstring).
- **[substantial]** — requires meaningful design or cross-cutting work: touching multiple call sites or layers, changing an interface/data layout/contract, rethinking an algorithm, or needing non-trivial re-validation (e.g. new tests, GPU runs, re-benchmarking) before it can be trusted.

Base the classification on the *smallest correct* fix, not the most thorough one; if the minimal fix is easy but the proper fix is substantial, say so (e.g. "[easy fix] to guard, [substantial] to fix properly"). The tag is load-bearing: everything marked [easy fix] gets auto-applied in Workflow step 5, so classify conservatively — when in doubt, mark [substantial].

```
## Static Review — <working tree | last commit <sha> "<subject>" | <range>> — N files, M findings

### 🔴 Bugs / correctness
1. [file.py:120](path/file.py#L120) — **[easy fix]** <what's wrong and why it matters>
   Suggestion: <concrete fix>

### 🟡 Issues / risks
2. [file.py:88](path/file.py#L88) — **[substantial]** <what's wrong and why it matters>
   Suggestion: <concrete fix>

### 🟢 Suggestions / improvements
...

### Summary
<1–3 sentence overall assessment + anything that looks intentional but worth confirming; include a one-line tally, e.g. "4 easy fixes, 2 substantial">
```

With `ReportFindings` available, the numbered groups above move into the tool call (one finding per entry, `category` = `correctness` / `risk` / `suggestion` / `large-file` / `security` / `convention`, `summary` starting with the tag) and the text keeps the header line and the Summary section only.

## Rules

- **Read-only analysis; edits only in the fix pass.** Inspect with `git` and file reads; never run tests or builds as part of the review. The only file edits are the automatic [easy fix] pass of Workflow step 5 (plus any follow-up fixes the user explicitly requests for [substantial] findings) — never edit before the report is presented, never auto-apply a [substantial] finding, always stage the files a fix pass edited and then every reviewed file, loop on whatever is still unstaged until `git status --short` is clean (Workflow step 6), and always end with the commit message (Workflow step 7).
- **The reviewed commit is never rewritten.** In commit mode no `--amend`, rebase, reset or history edit — fixes are new staged changes, and the commit message of step 7 is for them.
- **No file over 5 MiB is ever staged or passed as reviewed.** The large-file check of Workflow step 1 runs in EVERY review, including each pass of the step-6 loop; an oversized file (or an oversized blob in an unpushed commit) is always reported as 🔴, never waved through because it is "just data" or "generated".
- **Be specific.** Every finding cites a concrete location and explains the concrete consequence — no generic advice.
- **No false alarms.** Verify a concern against the actual surrounding code before reporting it (the verify pass of step 2 when subagents produced it). If unsure whether something is a real problem, say so explicitly and explain the condition under which it would be.
- **Prioritize.** Lead with correctness bugs; keep style nits brief and clearly separated.
- **Respect intent.** If a change looks deliberate but unusual, flag it as a question rather than asserting it's wrong.
- **Don't trust any comment at all.** Always assume the comment doesn't exist / is incorrect when reviewing the code — judge the code purely by what it does, never by what a comment claims it does. Additionally, double check whether the code is consistent with any comments in the updated files, and flag every comment (including docstrings, and in commit mode the commit message) that contradicts the actual behavior of the code.
