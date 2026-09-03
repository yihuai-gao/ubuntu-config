---
name: static-review
description: Statically review all uncommitted changes in the current git repo — read the diff and surrounding code, report potential bugs, correctness issues, and improvement opportunities, then automatically apply every [easy fix] finding (leaving [substantial] ones for discussion) and propose a commit message. Use when the user asks to review uncommitted/local/working-tree changes, "review my changes", "static review", "look over my diff", or wants feedback before committing. The analysis itself is pure static reading — no builds or tests are run.
---

# Static Review

Review uncommitted changes in the current git repository by reading code only, then auto-apply the easy fixes. During the ANALYSIS phase no commands are run beyond `git` inspection — no builds, tests, linters, or formatters; after the report, the [easy fix] findings are applied to the working tree (followed by compile/lint checks of the touched files where the repo's conventions call for them).

## Scope

"Uncommitted changes" means everything not yet committed:
- Unstaged modifications (working tree vs index)
- Staged modifications (index vs HEAD)
- Untracked files (newly added, not yet `git add`ed)

## Workflow

1. **Gather the changes.** Run these to see the full picture:
   ```bash
   git status
   git diff            # unstaged
   git diff --staged   # staged
   ```
   For untracked files, list them from `git status` and read each in full with the Read tool.

2. **Read enough context.** A diff hunk alone is rarely enough. For each changed region, Read the surrounding function/class and, when relevant, the callers, callees, and definitions of touched symbols. Do not review hunks in isolation — many real issues live at the boundary between changed and unchanged code.

3. **Analyze.** Look for the categories below.

4. **Report.** Produce a structured findings list (format below). Never modify any files before the report is presented.

5. **Auto-apply the easy fixes.** Immediately after presenting the report, apply every finding tagged **[easy fix]** — bugs, issues, and suggestions alike — to the working tree, without waiting to be asked. Leave every **[substantial]** finding untouched and list them at the end as open discussion points. Details:
   - For a mixed finding ("[easy fix] to guard, [substantial] to fix properly"), apply only the easy guard; the proper fix stays a discussion point.
   - If an easy fix turns out to require design decisions or interface changes mid-edit, stop, reclassify it as [substantial], and say so — never force it through.
   - Follow the repo's own landing conventions for edits when present (e.g. this checkout's worktree-first + staged-baseline flow, compile/lint gates on touched files).
   - When a fix changes user-facing text elsewhere (README, docstrings, help strings), update those in the same pass so docs stay consistent with the new behavior.
   - **Stage every file the fix pass touched (user directive 2026-08-28): `git add` each fixed file right after the edits pass their compile/lint/test gate, without being asked.** Staging is part of landing a fix in this checkout ("land" = diff→apply→add); an unstaged fix over an already-staged hunk is easy to lose and shows up as a confusing `MM`. Stage ONLY the files the fix pass edited — never sweep in unrelated working-tree changes (memory notes, dashboards, another session's edits) — and confirm with `git status --short` afterwards. This is staging, NOT committing: `git commit` stays off-limits unless explicitly asked.
   - Close the pass with a short per-finding list of what was applied (finding number → file → one-line description), and state that the fixed files are staged.
   - **The closing [substantial] discussion-point list must be SELF-CONTAINED (user directive 2026-08-24): restate each open finding in full** — clickable location, what's wrong, the concrete consequence, and the suggested fix — never just a one-line label with the finding number. The final message is what the user reads last; a brief recap forces them to scroll back to the report to recover the details.

6. **Generate a commit message.** After the auto-fix pass (or after the user asks for fixes of substantial findings), finish by directly generating a commit message — do not wait to be asked. Default format (user directive 2026-08-17): ONE short imperative summary line of AT MOST 50 characters — at that length it cannot enumerate everything, so name the dominant theme(s) of the FULL uncommitted change set (the original reviewed changes plus the applied fixes, not just the fixes) and drop the rest; expand toward the `commit-message` skill's longer one-sentence style only when the user explicitly asks for a longer message. Present it in a code block, and do NOT run `git commit` unless explicitly asked.

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

**Consistency with the codebase**
- Diverging from established patterns, naming, or idioms in nearby code
- Reinventing a helper that already exists in the repo
- Config/constant drift (a value changed in one place but not its siblings)

**cam_uva self-containment (only when reviewing code under `cam_uva`)**
- All code inside `cam_uva` must be self-contained: it must NOT import from the `imaginaire` codebase.
- Flag any `import imaginaire...` or `from imaginaire... import ...` (and any indirect dependency that pulls in `imaginaire`) in changed `cam_uva` files as a 🔴 correctness issue.
- Suggestion: vendor/copy the needed functionality into `cam_uva`, or replace it with a self-contained equivalent.

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

Group findings by severity. Skip empty groups. Reference exact locations as clickable links (`[file.py:42](path/file.py#L42)`).

**Fix-effort classification:** every finding (bugs, issues, AND suggestions) must carry a fix-effort tag:
- **[easy fix]** — a localized change: a few lines in one or two spots, no design decisions, no interface/contract changes, negligible re-validation (e.g. add a guard, clone a tensor, fix an off-by-one, correct a docstring).
- **[substantial]** — requires meaningful design or cross-cutting work: touching multiple call sites or layers, changing an interface/data layout/contract, rethinking an algorithm, or needing non-trivial re-validation (e.g. new tests, GPU runs, re-benchmarking) before it can be trusted.

Base the classification on the *smallest correct* fix, not the most thorough one; if the minimal fix is easy but the proper fix is substantial, say so (e.g. "[easy fix] to guard, [substantial] to fix properly"). The tag is load-bearing: everything marked [easy fix] gets auto-applied in Workflow step 5, so classify conservatively — when in doubt, mark [substantial].

```
## Static Review — N files, M findings

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

## Rules

- **Read-only analysis; edits only in the fix pass.** Inspect with `git` and Read; never run tests or builds as part of the review. The only file edits are the automatic [easy fix] pass of Workflow step 5 (plus any follow-up fixes the user explicitly requests for [substantial] findings) — never edit before the report is presented, never auto-apply a [substantial] finding, always stage the files a fix pass edited (and only those), and always end a fix pass with the commit message (Workflow step 6).
- **Be specific.** Every finding cites a concrete location and explains the concrete consequence — no generic advice.
- **No false alarms.** Verify a concern against the actual surrounding code before reporting it. If unsure whether something is a real problem, say so explicitly and explain the condition under which it would be.
- **Prioritize.** Lead with correctness bugs; keep style nits brief and clearly separated.
- **Respect intent.** If a change looks deliberate but unusual, flag it as a question rather than asserting it's wrong.
- **Don't trust any comment at all.** Always assume the comment doesn't exist / is incorrect when reviewing the code — judge the code purely by what it does, never by what a comment claims it does. Additionally, double check whether the code is consistent with any comments in the updated files, and flag every comment (including docstrings) that contradicts the actual behavior of the code.
