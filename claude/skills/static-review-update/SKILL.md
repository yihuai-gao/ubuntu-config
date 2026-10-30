---
name: static-review-update
description: Validate a set of review comments against the current code, then fix the valid ones. Input is the comments themselves — pasted text (an MR review, a Slack thread, a CodeRabbit / Greptile / Copilot review, a colleague's notes), a file, a GitLab MR reference (!iid or URL, its open threads), or the open [substantial] list of a previous /static-review. Every comment is checked by parallel read-only subagents (one per functionality) and gets a verdict with quoted code as evidence — VALID, VALID DIFFERENT FIX, INVALID, STALE, UNDECIDABLE STATICALLY or QUESTION; the orchestrator re-verifies every verdict, reports, then fixes every valid comment the best-practice way with parallel implementation subagents, gates and stages the files, drafts paste-ready replies to the reviewer and proposes a commit message. Use when the user invokes /static-review-update, says "address / go through / apply the review comments", "are these review comments right", "fix what the reviewer (or CodeRabbit) flagged", "handle the MR feedback", or pastes reviewer comments and asks what to do about them. Validation is static reading; nothing is posted to the MR.
argument-hint: "[<pasted comments>|<file with comments>|!<mr-iid>|<mr-url>]"
---

# Static Review Update (validate review comments, then fix the valid ones)

Take a set of review comments about this repository's code, decide for EACH comment whether it is right about the code as it is now, then fix every valid comment the way the codebase's own best practice dictates. Validation and fixing both fan out across parallel subagents; the orchestrating session verifies every verdict and every edit itself. Companion of `static-review` (which produces its own findings): this skill works from someone else's findings.

## Input: where the comments come from

Decide the source FIRST and name it in the first line of the report, in this order:

1. **Pasted text** — the comment list in `$ARGUMENTS` or a `<pasted_content>` block of the same message.
2. **A file path** — `.md`, `.txt`, `.json`; read it in full.
3. **A GitLab MR reference** (`!1234`, an MR URL) — the open (unresolved) discussion threads of that MR, fetched through the `gitlab-mr` skill or the GitLab MCP tools (`gitlab_get_merge_request`, its discussions; the Greptile / CodeRabbit suggestion tools when the user names them). Keep each thread's id so the replies of step 7 can be matched back.
4. **A previous `/static-review` of this conversation** — its open [substantial] list, only when the user says so ("the remaining findings", "the substantial ones").
5. **Nothing recognizable** — ask with `AskUserQuestion` (paste / file / MR / previous static-review); never guess.

**Normalize** every comment into one record before anything else. The record list is the contract for the whole run and is printed first in short form (id, location, claim) so the user sees what was parsed:

| field | content |
|---|---|
| `id` | `C1`, `C2`, … in input order (the reviewer's own numbering kept beside it when there is one) |
| `source` | reviewer name or tool; thread id when from an MR |
| `location` | file and line / hunk / symbol as cited, **re-resolved against the current tree** (lines drift: match by the quoted code or the symbol and record the current line) |
| `claim` | what the comment says is wrong, one sentence, verbatim where the wording matters |
| `proposed_fix` | the reviewer's suggestion, or "none" |
| `kind` | bug / risk / convention / style / test / question |

A comment that bundles several independent points is split (`C3a`, `C3b`); two comments about the same lines stay in one group so one validator sees their interaction. Cited code that no longer exists is noted on the record (candidate STALE), never dropped.

## Workflow

1. **Establish the code under review.** Which tree the comments were made against (the working tree, a commit, an MR source branch): `git status --short`, `git log -3 --oneline`, and for an MR the source branch / sha the MR tool reports. If the checkout is NOT on that code, say so and stop with the exact `git` command the user would run — never switch branches, stash or check out yourself.

2. **Validate — by functionality, one read-only subagent per group, all in one message.** Sort the records by the functionality their code implements (a module, subsystem or feature; a test travels with the code it tests), never by comment count. Launch ONE read-only `Agent` subagent PER GROUP in a single message (`model: "opus"`, the current account, no account question), regardless of group size — a group of one comment is still its own subagent. Project rules that forbid subagents for a tree (cam_uva: `camera-cross-embodiment`, iPhUMI) win: validate those inline.

   Each validator's prompt is self-contained and **carries the comments verbatim, never the orchestrator's guess at the verdict** (an agent handed a hypothesis returns it confirmed). It holds: the repo path; the code under review (mode, branch / sha); its records in full; the verdict vocabulary, the evidence rule and the fix-effort tags below; the instruction to try BOTH to confirm and to refute every comment, to read the surrounding function / class plus callers and callees and the project's rule files (`CLAUDE.md`, `.claude/rules/*`) before deciding, and to run only read-only inspection (`git`, `grep`, `sed -n`, `python -m py_compile`, an import check) — never an edit, never a test that writes, never a GPU; and the return format: one block per comment with `id`, `verdict`, `evidence` (the decisive lines quoted with `file:line`), `failure_scenario` (VALID only: inputs or state → wrong output, crash or cost), `best_fix` (what to change and why it is the best practice here, naming the rule or the nearby idiom it follows), `fix_effort`, `conflicts_with` (another comment's id when the two fixes are incompatible).

   **Verdict vocabulary** (one per comment; the name says what is true of the code):
   - **VALID** — the concern is real on the current code and the proposed fix is the right one.
   - **VALID, DIFFERENT FIX** — the concern is real, but the reviewer's fix is wrong, incomplete or against the codebase's conventions; `best_fix` says what to do instead and why.
   - **INVALID** — the concern does not hold; `evidence` quotes the exact code (a guard, a caller contract, a type, a test) that refutes it and names what the comment misread.
   - **STALE** — the cited code no longer exists or was already fixed; the validator states whether the same concern applies to the replacement code (if so, it is VALID at the new location, not STALE).
   - **UNDECIDABLE STATICALLY** — only a run (GPU, cluster, data, a long test) can settle it; `evidence` names the cheapest check that would. Not fixed by this skill.
   - **QUESTION** — the comment asks rather than claims; the validator answers from the code with evidence. A fix only when the answer exposes a defect (then it is also VALID).

   **Evidence rule:** every verdict quotes the decisive lines (`file:line`). A verdict without quoted code goes back to its validator (`SendMessage`) instead of being accepted. A comment's own text, a docstring or a code comment is never evidence — only what the code does.

   **Fix-effort tag** (same meaning as in `static-review`): **[easy fix]** = a localized change, no design decision, no interface change, negligible re-validation; **[substantial]** = cross-cutting work, an interface / data-layout / contract change, or non-trivial re-validation. Classify on the smallest correct fix.

3. **Verify every verdict yourself.** Re-read the cited code for every record and mark the validator's verdict kept or overturned (say which, with the evidence, when overturned); merge duplicates; resolve `conflicts_with` pairs by evidence. Two VALID comments whose fixes are incompatible, or a VALID [substantial] comment whose fix needs a decision the comment leaves open (which interface, which default), go into ONE `AskUserQuestion` round (multiple choice, one question per decision) before any edit. Everything else proceeds without asking.

4. **Report before editing anything.** Print the validation report (format below). Never modify a file before the report is presented. When the `ReportFindings` tool is available, call it ONCE with the VALID and VALID, DIFFERENT FIX records as findings (`summary` prefixed with the comment id and the fix-effort tag, `verdict` CONFIRMED for a kept verdict whose code you re-read, PLAUSIBLE otherwise) so the host UI renders them; the INVALID / STALE / UNDECIDABLE / QUESTION rows stay in the text table, since the tool takes only findings.

5. **Fix every valid comment — in parallel, by functionality.** Right after the report (and after the AskUserQuestion round when there was one), fix every VALID and VALID, DIFFERENT FIX record, [easy fix] and [substantial] alike: the user asked for the valid comments to be fixed, so a [substantial] one is fixed too, with whatever re-validation it still needs stated honestly at the end. Only a fix whose design decision the user has not made (step 3) waits. Group the fixes by the same functionality split as step 2 with DISJOINT file sets; when more than one group has fixes, launch one implementation `Agent` subagent per group in a single message (`model: "fable"`, the current account); a single group, or fixes that would overlap in one file, are applied inline.

   When the repo's rules require edits in a worktree (cam_uva: `git worktree add --detach /home/yihuai/video-gen/repositories/worktrees/cam-uva-<task> HEAD`), create ONE worktree for the whole fix pass, point every fixer at it, and land its diff on the main checkout in step 6.

   Each fixer's prompt is self-contained: the repo (or worktree) path; its records in full (location, the claim, the verified `best_fix` — the orchestrator's verified plan, not the reviewer's literal words when they differ); the exact files it may edit; the compile / lint gate for those files (`python -m py_compile`, `ruff check`, the project's cheap CPU tests for the touched module when the repo has them); and the reporting contract: each record returned as fixed (file, what changed), skipped (the reason) or reclassified (a fix that turns out to need a design decision stops and reports instead of forcing it through).

   **Best practice means, in this order:** the project's rule files (`CLAUDE.md`, `.claude/rules/*`, a `coding-guidelines` skill when present); the idiom the surrounding code already uses; the language's standard practice. Concretely: fix the cause, not the symptom the comment points at; one source of truth per knob (the replaced one is deleted, no shim, no alias); no stub, fake or hard-coded data; a changed behaviour updates its tests, docstrings and user-facing text in the same pass, and a VALID "no test covers this" comment lands a test in the repo's test layout; a check that must hold at run time is a `raise`, never an `assert`; nothing beyond the comment's scope is touched (an adjacent problem noticed on the way is reported as a new finding, not fixed silently).

   Fixers never touch files outside their list and never run `git add`, `git commit` or any other index-changing command.

6. **Verify the edits, gate, land, stage.** Re-read every edited hunk against its record (does the edit do what `best_fix` said, and nothing else); run the gates once more yourself on every touched file; run the 5 MiB large-file check of `static-review` (no file over 5,242,880 bytes is ever staged). A worktree fix pass is landed as a diff (`git diff` in the worktree, `git apply` in the main checkout), the landed files verified identical, and the worktree removed in the same turn. Then `git add` each fixed file by explicit path (never `-A` / `-u` / `.`) and confirm with `git status --short`. Staging is landing, not committing: `git commit` only when explicitly asked. When the report went through `ReportFindings`, call it again with an `outcome` per record (`fixed`, `skipped`, `no_change_needed`).

7. **Draft the replies to the reviewer.** One paste-ready line or two per comment, grouped by verdict: fixed ("Fixed in `path` — what changed"; for a DIFFERENT FIX, why the other fix was chosen); not changed, with the refutation and the quoted evidence (INVALID); already addressed (STALE); what would settle it (UNDECIDABLE); the answer (QUESTION). Comments from an MR carry their thread id. **Never post a reply, resolve a thread or approve anything unless the user asks**; the `gitlab-mr` skill does that on request.

8. **Commit message.** When anything was staged, end with ONE imperative summary line of at most 50 characters in a code block, naming the dominant theme of the staged change set; do not run `git commit`. Nothing staged → say so and skip the message.

9. **Report file.** When the user asked for a thorough pass or a written report, or when there are more than 10 comments (the chat cannot hold the evidence), write the full validation report (every record with its evidence, fix and reply) to the project's report location (cam_uva: `projects/cosmos3/cam_uva/docs/<topic>_<MMDD>.md`; otherwise `<repo root>/docs/reviews/<topic>_<MMDD>.md`; outside a git repo `~/reports/<project>/<topic>_<MMDD>.md`) and end the reply with its absolute path as a clickable link. Do not `git add` the report unless asked.

## Output format

Every location is a clickable link at the CURRENT line (`[file.py:42](path/file.py#L42)`). Tables over prose; one row per comment, the evidence as one short quote. The final message is self-contained: the Open list restates each item in full (location, claim, what would settle it), never a bare id.

```
## Review-comment validation — <source> — N comments: V valid (E easy, S substantial), D invalid, T stale, U undecidable, Q questions

| # | location | verdict | evidence | fix |
|---|---|---|---|---|
| C1 | [a.py:120](a.py#L120) | VALID [easy fix] | `x = buf[i+1]`, `i` reaches `len(buf)-1` | guard the last index |
| C2 | [b.py:40](b.py#L40) | INVALID | `if cfg is None: return` at b.py:37 | — |
| C3 | [c.py:88](c.py#L88) | VALID, DIFFERENT FIX [substantial] | <quote> | <best fix, why not the proposed one> |

### Verification notes
<verdicts overturned vs. the validators, duplicates merged, conflicts and how they were resolved, questions put to the user>

### Fix pass
C1 → [a.py:120](a.py#L120) — <what changed>
C3 → <fixed / skipped: reason / waiting on decision>
Staged: <files>. Gates: <what ran, result>. Not re-validated: <what a [substantial] fix still needs, e.g. a GPU run>.

### Replies to the reviewer (paste-ready)
- C1 (thread <id>): Fixed in `a.py` — ...
- C2: Not changed — <refutation with the quoted code>

### Open
<every UNDECIDABLE record and every fix waiting on a decision, each with location, claim and what settles it>

<commit message in a code block>
```

## Rules

- **Validate before fixing, report before editing.** No file changes until the validation report is on screen; a comment is fixed only on a verified VALID verdict.
- **Independent validation.** Validators get the comments and the code, never a suggested verdict; every verdict carries quoted code; a reviewer's seniority, a tool's confidence score or a comment's tone is not evidence.
- **Both directions.** Every comment is checked for the way it could be right AND the way it could be wrong; "the reviewer is probably right" and "the reviewer is probably wrong" are both hypotheses to disprove.
- **Best practice over the literal suggestion.** The fix is what the codebase's rules and idioms call for; when that differs from the reviewer's proposal, the difference is stated in the report and in the reply draft, never applied silently.
- **Scope.** Only the valid comments are fixed; anything else noticed is reported (under Open, or handed to `/static-review`), never a silent extra edit.
- **No history changes.** Never `git commit`, `--amend`, rebase, reset, stash, switch or push; staging by explicit path is the only index operation, and nothing over 5 MiB is staged.
- **Nothing posted outward.** Replies to an MR, thread resolutions or approvals happen only on the user's explicit request.
- **Project rules win.** A rule file of the repo (worktree-first editing, no subagents in a tree, YAML-only defaults, `raise` not `assert`, test layout) overrides the generic steps above.
