---
name: static-review
description: Statically review Git working-tree changes, commits, ranges, or selected paths for concrete bugs and release risks. Use for static review, reviewing local changes, or feedback before committing. Report findings, apply verified easy fixes, stage reviewed changes, and suggest a commit message unless the user requests review only.
metadata:
  short-description: Review changes and apply verified easy fixes
---

# Static Review

Review a change set by static inspection, report findings, then apply verified easy fixes and stage the reviewed changes. During analysis, use only read-only Git inspection, file reads, searches, and file/blob-size checks; do not run builds, tests, linters, or formatters. After reporting, run the checks required for the fixes and the repository.

## Codex invocation and scope

Invoke as `$static-review`, optionally followed by a commit, range, or paths, for example `$static-review HEAD~1` or `$static-review projects/cosmos3/cam_uva`. Arguments come from the user's prompt; no template-variable expansion is needed.

Read applicable `AGENTS.md` instructions before reviewing or editing. User instructions such as "review only", "do not edit", or "do not stage" override the default fix-and-stage workflow. Preserve the chosen path scope throughout review, fixes, and staging. Do not treat a request to install or edit this skill as a request to review the repository.

Use the available Codex file and shell tools. For larger divisible reviews, use Codex subagents as described below when available and permitted; otherwise perform the review sequentially and report that limitation. Do not depend on Claude-specific tools or models.

## Target selection (user directive 2026-10-06)

Decide the review target FIRST, in this order, and name the chosen mode in the first line of the report:

1. **Explicit target in the user's prompt**: a commit (`HEAD~1`, a sha, a tag), a range (`main..HEAD`, `abc123^..def456`) or one or more paths. A commit or range is reviewed in *commit mode*; a path list narrows *working-tree mode* to those paths.
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
   Record the initial index and working-tree state so pre-existing changes remain identifiable. For untracked files within the selected scope, list them from `git status` and read each in full. Inspect binaries through their metadata and relevant loaders; do not stage content that could not be reviewed.

   **[commit mode]**:
   ```bash
   git log -1 --format='%h %an %ad%n%s%n%n%b' --date=iso-local HEAD   # or the given commit / range
   git show --stat --format= HEAD
   git diff-tree -p --root -M HEAD                                      # full patch, works for a root commit too
   # a range: git log --oneline <range>; git diff <range> -M
   ```
   Also read the commit message against the patch: a message that claims something the diff does not do (or hides something it does) is a 🟡 finding — it is the record the next reader trusts.

   **Always run the large-file check in this step (user directive 2026-09-19).** Preserve this user's 5 MiB (5,242,880 bytes) non-LFS file limit; it reflects the target GitLab repository's push policy, not a universal GitLab default. Check worktree files, staged blob contents, and blobs in the target commits and unpushed history. A smaller worktree file does not prove that its staged or committed version is safe. The commands below are starting points: substitute the actual target, respect any path scope, and inspect staged blobs separately with `git ls-files --stage` and `git cat-file -s`. Check `git check-attr filter -- <path>` for worktree files and `git check-attr --cached filter -- <path>` for the index. For committed blobs, verify an actual LFS pointer rather than relying on current attributes:
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

2. **Read enough context.** A diff hunk alone is rarely enough. For each changed region, read the surrounding function/class and, when relevant, the callers, callees, and definitions of touched symbols. Do not review hunks in isolation — many real issues live at the boundary between changed and unchanged code. Read files with the available Codex tools; prefer `rg` for searches and use targeted file reads for surrounding code.

   **Delegate divisible reviews (user preference, 2026-10-06; by functionality, user 2026-10-21).** Before reading in depth, sort the changed files by the functionality they implement (a module, subsystem or feature: harness server vs. keeper vs. dashboard vs. tests, for example; a test file travels with the code it tests). When the files clearly span several functionalities, split along those lines and spawn ONE read-only subagent PER FUNCTIONALITY, as many as there are functionalities, all at once (`collaboration.spawn_agent`, when Codex collaboration tools are available and applicable instructions permit delegation), regardless of how small each group is; a group that is one file is still its own subagent. Without a clear functional split, fall back to the size rule: over roughly 4 changed files or 400 diff lines, divide the files into disjoint groups and spawn one subagent per group; under that, review inline. Inherit the current model and reasoning settings; do not request a Claude model or switch accounts. Each prompt must specify the repo path, mode, target, assigned files, categories, tags, and candidate fields: `file`, `line`, `summary`, `failure_scenario`, and fix-effort tag. Subagents never edit or stage. Collect every subagent's candidates, then **verify candidates yourself**: re-read each cited location and label it CONFIRMED, PLAUSIBLE, or REFUTED; drop refuted candidates and merge duplicates. Respect project restrictions, including any applicable prohibitions in `camera-cross-embodiment` or iPhUMI. If delegation is unavailable, complete the review locally and say so.

3. **Analyze.** Look for the categories below.

4. **Report.** Produce the findings (format below). Never modify any files before the report is presented.

   **Codex reporting.** Present the initial findings in a commentary update before editing so the task can continue through the fix pass. Use the Markdown format below unless the host requires a structured review schema; follow that schema when present. Do not call an unavailable findings tool. The final response must remain self-contained and include every unresolved substantial finding.

5. **Auto-apply the easy fixes.** Immediately after presenting the report, apply every CONFIRMED finding tagged **[easy fix]** — bugs, issues, and suggestions alike — to the working tree, unless the user requested review only. Do not edit on a merely PLAUSIBLE finding; resolve its uncertainty or leave it open. Leave every **[substantial]** finding untouched and list them at the end as open discussion points. Details:
   - For a mixed finding ("[easy fix] to guard, [substantial] to fix properly"), apply only the easy guard; the proper fix stays a discussion point.
   - If an easy fix turns out to require design decisions or interface changes mid-edit, stop, reclassify it as [substantial], and say so — never force it through.
   - **Fix in parallel when the review was delegated (user 2026-10-21).** Group the CONFIRMED [easy fix] findings by the same functionality split as the review and, when more than one group has fixes, spawn one implementation subagent per group at once (`collaboration.spawn_agent`, inheriting the current model and reasoning settings), each with a self-contained prompt: the repo path, its findings in full (location, what is wrong, the intended fix), the exact files it may edit (disjoint from every other subagent's), the repo's compile/lint gate for those files, and the instruction to report each finding as fixed, skipped (with the reason) or reclassified [substantial]. Fix subagents never touch files outside their list and never run `git add`, `git commit` or any other index-changing command: the orchestrating session re-reads every edited hunk, runs the gates once more and stages (next bullet). A single group, fixes that would overlap in one file, or an unavailable delegation tool mean the fixes are applied inline.
   - Follow the repo's own landing conventions for edits when present (e.g. this checkout's worktree-first + staged-baseline flow, compile/lint gates on touched files).
   - When a fix changes user-facing text elsewhere (README, docstrings, help strings), update those in the same pass so docs stay consistent with the new behavior.
   - **Stage every file the fix pass touched (user directive 2026-08-28): `git add` each fixed file right after the edits pass their compile/lint/test gate, without being asked.** Staging is part of landing a fix in this checkout ("land" = diff→apply→add); an unstaged fix over an already-staged hunk is easy to lose and shows up as a confusing `MM`. Stage by explicit path (never `git add -A` / `-u` / `.`) and confirm with `git status --short` afterwards. This is staging, NOT committing: `git commit` stays off-limits unless explicitly asked.
   - **[commit mode]** fixes land as NEW uncommitted changes on the current checkout and are staged the same way. When the explicit target is an older commit or range, verify that the defect still exists in the current checkout before applying a fix. Preserve any pre-existing working-tree and index changes; do not switch or reset the checkout to the reviewed revision. Never `git commit --amend`, rebase or otherwise rewrite the reviewed commit; a fix-up is the user's call (offer `git commit --fixup=<sha>` or a plain follow-up commit in the closing note).
   - Close the pass with a short per-finding list of what was applied (finding number → file → one-line description), and state that the fixed files are staged. For each skipped fix, explain why. Report the checks actually run and any validation limitations; do not describe static inspection as runtime validation.

6. **Stage everything in scope that passed review, then recheck (user directive 2026-09-07).** Unless the user requested review only or prohibited staging, After the fix pass, `git add` (explicit paths) EVERY file the review covered and found acceptable — the reviewed-and-clean files as well as the fixed ones, including dashboards, docs, memory notes and untracked files that belong to the change set (an untracked file is a new file: read it in full before staging; a secret-shaped string or a stray artifact is a finding, not something to stage). Then run `git status --short` and look for anything still unstaged (` M`, `MM`, `AM`, `??`): those are changes the review has NOT covered yet (edited by the user or another session mid-review, or skipped) — review them with the same workflow (read, findings, easy fixes, gates), stage them, and re-check. Repeat until no eligible in-scope changes remain unstaged. Explicitly exclude paths outside the selected scope and the generated review report (unless its staging was requested). If another session keeps changing a file, stop retrying that file and report it as live work; do not chase edits indefinitely. Two further exceptions, each reported explicitly instead of staged: a file that must NOT be staged because a finding is still open on it (say which finding), and a file whose unstaged content is another session's live, in-progress edit that would break if frozen now (say whose). Never resolve the loop by discarding, stashing or resetting anyone's changes.
   - **[commit mode]** stage only changes from the fix pass. Explicit commit targets may coexist with a dirty checkout; preserve its initial staged/unstaged boundaries and use patch-level staging when a file also contains unrelated changes. If reviewed fixes cannot be isolated safely, leave them unstaged and explain the overlap. Report new unrelated entries as concurrent work without reviewing or staging them unless asked.
   - **The closing [substantial] discussion-point list must be SELF-CONTAINED (user directive 2026-08-24): restate each open finding in full** — clickable location, what's wrong, the concrete consequence, and the suggested fix — never just a one-line label with the finding number. The final message is what the user reads last; a brief recap forces them to scroll back to the report (or the rendered findings list) to recover the details.

7. **Generate a commit message.** After the staging loop of step 6 ends clean (or after the user asks for fixes of substantial findings), finish by directly generating a commit message — do not wait to be asked. Default format (user directive 2026-08-17): ONE short imperative summary line of AT MOST 50 characters — at that length it cannot enumerate everything, so name the dominant theme(s) of the FULL uncommitted change set (the original reviewed changes plus the applied fixes, not just the fixes) and drop the rest; use a longer message only when the user explicitly requests one. With an explicit path scope, describe the reviewed changes only; do not imply unrelated staged changes passed review. Present it in a code block, and do NOT run `git commit` unless explicitly asked.
   - **[commit mode]** the message describes the staged fix pass only (the reviewed commit already has its message). When the fix pass applied nothing, there is nothing to commit: say so and skip the message.

8. **Thorough review requested → also save the report (global rule).** When the user asked for a thorough review, audit or written report, write the complete report to a markdown file at the project's report location (cam_uva: `projects/cosmos3/cam_uva/docs/<topic>_<MMDD>.md`; otherwise `<repo root>/docs/reviews/<topic>_<MMDD>.md`) and end the reply with its absolute path as a clickable link. Do not `git add` the report unless asked. A plain `$static-review` does not write a report file. Honor an explicit report destination and leave the report unstaged unless asked.

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
- An applicable AGENTS.md or project rules-file convention the change breaks (name the rule)

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

Group findings by severity. Skip empty groups. Reference exact locations as clickable links (`[file.py:42](/absolute/path/file.py:42)`). Every finding states a concrete failure scenario (inputs or state → wrong output, crash or cost), not a generic worry.

**Fix-effort classification:** every finding (bugs, issues, AND suggestions) must carry a fix-effort tag:
- **[easy fix]** — a localized change: a few lines in one or two spots, no design decisions, no interface/contract changes, negligible re-validation (e.g. add a guard, clone a tensor, fix an off-by-one, correct a docstring).
- **[substantial]** — requires meaningful design or cross-cutting work: touching multiple call sites or layers, changing an interface/data layout/contract, rethinking an algorithm, or needing non-trivial re-validation (e.g. new tests, GPU runs, re-benchmarking) before it can be trusted.

Base the classification on the *smallest correct* fix, not the most thorough one; if the minimal fix is easy but the proper fix is substantial, say so (e.g. "[easy fix] to guard, [substantial] to fix properly"). The tag is load-bearing: everything marked [easy fix] gets auto-applied in Workflow step 5, so classify conservatively — when in doubt, mark [substantial].

```
## Static Review — <working tree | last commit <sha> "<subject>" | <range>> — N files, M findings

### 🔴 Bugs / correctness
1. [file.py:120](/absolute/path/file.py:120) — **[easy fix]** <what's wrong and why it matters>
   Suggestion: <concrete fix>

### 🟡 Issues / risks
2. [file.py:88](/absolute/path/file.py:88) — **[substantial]** <what's wrong and why it matters>
   Suggestion: <concrete fix>

### 🟢 Suggestions / improvements
...

### Summary
<1–3 sentence overall assessment + anything that looks intentional but worth confirming; include a one-line tally, e.g. "4 easy fixes, 2 substantial">
```

If the host requires structured findings, map these fields to its actual schema. Keep severity separate from fix effort, use exact changed-line locations, and include uncertainty and the concrete failure scenario.

## Rules

- **Read-only analysis; edits only after findings.** Do not run tests or builds during analysis. After reporting, apply confirmed easy fixes and any substantial fixes explicitly authorized by the user, then validate the changes. Follow the user's review-only/no-staging overrides and the scope, exclusions, and stopping conditions of step 6. Save a report when requested under step 8. Suggest a commit message when step 7 applies; never commit without explicit instruction.
- **The reviewed commit is never rewritten.** In commit mode no `--amend`, rebase, reset or history edit — fixes are new staged changes, and the commit message of step 7 is for them.
- **No file over 5 MiB is ever staged or passed as reviewed.** The large-file check of Workflow step 1 runs in EVERY review, including each pass of the step-6 loop; an oversized file (or an oversized blob in an unpushed commit) is always reported as 🔴, never waved through because it is "just data" or "generated".
- **Be specific.** Every finding cites a concrete location and explains the concrete consequence — no generic advice.
- **No false alarms.** Verify a concern against the actual surrounding code before reporting it (the verify pass of step 2 when subagents produced it). If unsure whether something is a real problem, say so explicitly and explain the condition under which it would be.
- **Prioritize.** Lead with correctness bugs; keep style nits brief and clearly separated.
- **Respect intent.** If a change looks deliberate but unusual, flag it as a question rather than asserting it's wrong.
- **Don't trust any comment at all.** Always assume the comment doesn't exist / is incorrect when reviewing the code — judge the code purely by what it does, never by what a comment claims it does. Additionally, double check whether the code is consistent with any comments in the updated files, and flag every comment (including docstrings, and in commit mode the commit message) that contradicts the actual behavior of the code.
