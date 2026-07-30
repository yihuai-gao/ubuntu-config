---
name: static-review
description: Statically review all uncommitted changes in the current git repo — read the diff and surrounding code, then report potential bugs, correctness issues, and improvement opportunities. Use when the user asks to review uncommitted/local/working-tree changes, "review my changes", "static review", "look over my diff", or wants feedback before committing. Pure static analysis — does NOT run builds, tests, linters, or any tools.
---

# Static Review

Review uncommitted changes in the current git repository by reading code only. No commands are run beyond `git` inspection — no builds, tests, linters, or formatters.

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

4. **Report.** Produce a structured findings list (format below). Do not modify any files unless the user explicitly asks for fixes afterward.

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

```
## Static Review — N files, M findings

### 🔴 Bugs / correctness
1. [file.py:120](path/file.py#L120) — <what's wrong and why it matters>
   Suggestion: <concrete fix>

### 🟡 Issues / risks
...

### 🟢 Suggestions / improvements
...

### Summary
<1–3 sentence overall assessment + anything that looks intentional but worth confirming>
```

## Rules

- **Read-only.** Inspect with `git` and Read. Never edit files, never run tests/linters/builds. If the user wants fixes, offer to apply them in a follow-up.
- **Be specific.** Every finding cites a concrete location and explains the concrete consequence — no generic advice.
- **No false alarms.** Verify a concern against the actual surrounding code before reporting it. If unsure whether something is a real problem, say so explicitly and explain the condition under which it would be.
- **Prioritize.** Lead with correctness bugs; keep style nits brief and clearly separated.
- **Respect intent.** If a change looks deliberate but unusual, flag it as a question rather than asserting it's wrong.
- **Don't trust any comment at all.** Always assume the comment doesn't exist / is incorrect when reviewing the code — judge the code purely by what it does, never by what a comment claims it does. Additionally, double check whether the code is consistent with any comments in the updated files, and flag every comment (including docstrings) that contradicts the actual behavior of the code.
