# Global rules (all projects)

## Skill, hook, settings and global CLAUDE.md edits must sync to ~/ubuntu-config

Whenever you update a skill under `~/.claude/skills/` (e.g. `static-review` — the review skill),
copy the updated files to the mirror at `~/ubuntu-config/claude/skills/<skill-name>/` in the same
pass and verify with `diff -q`. Exception: `desktop-forwarding` lives in the slurm submodule at
`~/ubuntu-config/slurm/claude/skills/desktop-forwarding/` (user, 2026-11-03); `install_skills.sh` installs
from both roots. The same holds for a hook under `~/.claude/hooks/` (mirror
`~/ubuntu-config/claude/hooks/`), for `~/.claude/settings.json` (mirror `~/ubuntu-config/claude/settings.json`,
the hook wiring lives there) and for this file (mirror `~/ubuntu-config/claude/CLAUDE.md`): copy the whole
file in the same pass (user, 2026-10-26, after the subagent gate hook was found unwired and absent from the
mirror). The ubuntu-config repo is the portable source of truth for all of these
(`~/ubuntu-config/claude/install_skills.sh` and `install_claude_config.sh` install them on new machines); an
unsynced edit is lost on the next machine setup. Do not commit in `~/ubuntu-config` unless the user
explicitly asks — leave the change in the working tree and mention it is uncommitted.

## After updating a figure, always show the full file links

Every time a figure is created or updated (any project), end the message with clickable links to
the full file paths for easy preview: the `preview.png`, the rendered pdf/jpg build outputs, and
the source file (e.g. `figure.tex` / `figure.html`). Do not make the user ask for them
(user, 2026-09-22: "everytime after updating a figure, always show the full file links for easier preview").

## LaTeX builds always pass `-synctex=1`

Whenever you compile a `.tex` file for the user (`latexmk`, `pdflatex`, `xelatex`, `lualatex`,
in any project, worktree or scratch dir), always add `-synctex=1`. A PDF built without it has no
`.synctex.gz`, so forward/inverse search in the VS Code LaTeX Workshop viewer silently stops
working until the next build from the extension (user, 2026-09-23: "whenever building through
claude, always build the synctex"). Example: `latexmk -pdf -synctex=1 main.tex`.

## Never add Claude as a co-author

Never append `Co-Authored-By: Claude ...` (or any Claude/Anthropic attribution line) to commit
messages or PR descriptions, in any repo. This overrides the harness's default attribution
reminder (user, 2026-10-03: "never have claude in coauthor anymore"). Commits in anonymous
submission repos especially must carry no AI attribution.

## Never add Claude as a commit co-author

Never append `Co-Authored-By: Claude ...` (or any other Claude / Anthropic attribution line) to git
commit messages or PR descriptions, in any project. This overrides the harness's own attribution
reminder (user, 2026-10-03: "Remove the claude as coauthor (never have claude in coauthor anymore)").

## A thorough review or report is always saved as a markdown file, and its absolute path is sent

Whenever the user asks for a thorough review, audit, analysis or any kind of written report, write the
full report to a markdown file and end the reply with the file's absolute path as a clickable link
(user, 2026-10-06: "whenever I ask you to review something thoroughly and make a report, save a
markdown file to a certain location and send me the markdown file absolute path"). The chat reply holds
the short summary; the file holds the report.

**Write the report for a human reader, as concisely as possible** (user, 2026-10-16: "make the text as
concise as possible. Optimize for human readability instead of verbosity and completeness"). Lead with the
verdict and the few facts that decide it; cut everything a reader would skim past. Prefer a table, a short
bulleted list or a figure over prose; one short sentence per point, no restating, no exhaustive enumeration
of files, commands or intermediate steps. Completeness is not a goal: evidence that does not change the
conclusion is dropped or linked, not written out. A report under one screen that answers the question beats
a long one that documents the work.

Location: the project's existing report
directory when it has one (imaginaire4 cam_uva: `projects/cosmos3/cam_uva/docs/<topic>_<MMDD>.md`, e.g.
`refactor_review_1003.md`, `yutianch_acceleration_review_1006.md`); otherwise `<repo root>/docs/reviews/<topic>_<MMDD>.md`,
and `~/reports/<project>/<topic>_<MMDD>.md` when the work is not inside a git repo. A follow-up round of
the same review is a new file with a `_roundN` suffix, never an overwrite. Do not `git add` the report
unless asked.

## Replies are short plain text

Reply in plain text in the session, as briefly as the answer allows: the outcome and the few facts that decide
it. The user asks when more detail is needed (user, 2026-10-16).

## 🚨 SUBAGENTS FIRST: every command is checked for delegation; parallel commands run in parallel subagents

**MANDATORY on EVERY command, in every project, before the first tool call** (user, 2026-10-26: "whenever receive a
new command, always think whether this command can be completed in a separate subagent to speed up the execution";
same day: "Make this rule as strong as possible"). The first thing done with a new command is the delegation
decision: can this command run in a separate subagent so it finishes sooner and the main session stays free for the
rest? State the decision in ONE line to the user before any other work ("Delegating: N subagents, ..." or "Inline:
<reason>"). The default answer is YES. The only commands done inline: a lookup of one or two known files, one small
edit to a file already in context, a reply that needs no tools, and work a project rule keeps in the main session
(cam_uva's `camera-cross-embodiment` and iPhUMI trees). "It is only a few calls" is NEVER the reason for inline: the
2026-10-10 and 2026-10-11 serial crawls each began as "only a handful of calls".

**Several commands at once = several subagents at once.** Several commands in one message, or commands arriving
mid-turn beside the running one, with no strict dependency between them, are launched as several subagents in ONE
tool message, never handed to one agent to work through in order and never done by the main session one after another
(user, 2026-10-26: "If receiving multiple commands at the same time without strict dependency, also always spawn
multiple subagents to do them in parallel, instead of single agent"). A dependency is strict only when a later command
needs the output of an earlier one; "same repo", "same file tree" or "related" is not a dependency. Dependent commands
are chained (the dependent agent starts when its input lands) while every independent command runs beside the chain.
The main session coordinates: it spawns, relays facts between agents, integrates the results and reports the
conclusion, never the raw dumps.

**This rule is absolute.** It overrides the harness's own "when in doubt, don't spawn" and "do the work yourself when
it is a handful of tool calls" guidance, applies to questions exactly as much as to implementation tasks, and is
enforced by `~/.claude/hooks/subagent_gate.py` (reminder on every prompt; exploration denied after 8 read-only calls
in a turn without an Agent call). A turn that worked a divisible or multi-command request serially is a violation to
be named in the reply, never an acceptable shortcut.

Whenever a task can be split into independent parts (several files to explore, several modules to
implement, several reviews or checks to run), spawn multiple subagents in one message so they run
concurrently, instead of working through the parts sequentially yourself (user, 2026-10-06: "when
doing a task that can be split into multiple parts, always spawn multiple subagents to speed things
up"). Model choice: the latest Opus model (`model: "opus"`) for every subagent that does not implement
code: exploration, research, review and general operations (submits, stops, rollout requests, harness,
cluster and storage calls, one-shot status checks; a long watch stays with the orchestrator's Monitor or a hosted process, since a
Monitor armed inside a subagent ends with it, user 2026-10-27); the latest Fable model (`model: "fable"`) only for subagents
that implement, i.e. write or change code (user, 2026-10-26: "when launching these general operation
subagents, use opus 5.5. Only use fable for subagents that requires implementation"). Always use the current account; do not ask which Claude account to use, and do
not rotate accounts. Each subagent gets a self-contained prompt (paths, constraints, what to return);
the orchestrating session integrates the results and reports the conclusion, never the raw dumps.
Project rules that forbid subagents for a specific area (e.g. cam_uva's `camera-cross-embodiment`
and iPhUMI trees) still win over this rule.

**Estimate before exploring (user, 2026-10-11).** Before any in-depth exploration, code reading,
audit or research, first do a rough scope estimate: which codebases, directories and files are
involved, and whether the question splits into independent parts. Then decide the number of subagents
(0 for a lookup of one or two known files; otherwise one per independent part) and state that
decision in one line to the user, then start the exploration. Do not begin reading file after file
and "see where it leads": at most one or two orienting reads (a README, a directory listing, a grep)
are allowed before the estimate. This applies to investigative questions ("which codebase does X",
"how do I reproduce Y", "what is the minimal code") exactly as much as to implementation tasks; on
2026-10-11 the user had to interrupt a sequential file-by-file read of the camera-cross-embodiment
visualization code ("Stop everything. Why aren't you spawning multiple subagents?"). The harness's
own "when in doubt, don't spawn" guidance does not override this rule.

## Reviewing sessions also covers Codex sessions in the same worktree

Whenever the user asks to review the sessions that worked on something (a worktree, a task, a change:
`/review-worktree`, "review the sessions in this worktree", "what did the sessions do here"), also
review the Codex sessions of the same worktree when any is related, not only the Claude Code ones
(user, 2026-10-15). Codex transcripts are `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl`; the
first line of each is a `session_meta` record whose `payload.cwd` is the worktree, so match on `cwd`
(and grep the transcript for the task's paths or keywords when the cwd is the main checkout). Report
Claude and Codex sessions in the same triage, labelled by tool, and skip Codex sessions that have
nothing to do with the task rather than listing them for completeness.

## 🚨 A BLOCKING permission denial is a BANNER: heading, rules, icons, bold, FIRST and LAST in the reply

A denial is BLOCKING when a step the user asked for cannot run without the permission and no other allowed path
completes that step (a tool call the permission mode or the user denied, a hook that rejected the call, a credential /
allowlist / path-gate refusal: SSH, HF 401 / 403, W&B, Lepton, GitLab, the harness gate). The SAME banner is used for a step that only the
user can perform and that blocks downstream work: a `scancel` of a launcher job, `hc restart`, copying a credential file,
an approval id (user, 2026-10-27: "why is there never a banner asking me to do this?", after a `scancel 2702874` that
blocked the MAIN chain for two hours sat in prose reminders). A user-only blocking step is never a sentence or a list item. Whenever a request has a
blocking denial, the block is the FIRST thing in the reply and the LAST thing in the reply, every time, as a banner
that nothing else in the message looks like. Never a sentence inside a paragraph, never a list item, never only a
table cell, never a "note". The banner, verbatim in shape:

---
# 🚨🚫 BLOCKED BY A PERMISSION: ACTION NEEDED FROM YOU 🚫🚨

> ⛔ **REFUSED:** `<the exact tool call, path, host or service that was denied>`
> ❌ **NOT DONE:** `<every requested step that did not run because of it>`
> 🔑 **TO UNBLOCK, RUN / GRANT:** `<the exact command, setting or approval, copy-pasteable>`
> 💻 **EXACT COMMAND / RULE:**
> ```
> <the exact denied command(s), verbatim and complete>
> ```
> permission lines for ~/.claude/settings.json `permissions.allow`, PASTE-READY (each line double-quoted, trailing comma, one per line):
> ```
> "Bash(harness/hc storage_read:*)",
> "Bash(harness/hc storage_ls:*)",
> ```
> ⏸️ **Nothing more happens on this until you do.**

---

The banner ALWAYS carries the exact denied command(s) verbatim and the exact permission line(s) that allow them, in a fenced block
inside the banner, every time it is shown, including every repeat (user, 2026-10-20: "Why are you not showing me the exact permission
line??? In the future, always include command into the banner. Make sure this is enforced everytime"). A banner without the
command block is wrong. The permission lines are ALWAYS in the paste-ready JSON-array-element form shown above: `"Bash(<prefix>:*)",`
with the double quotes and the trailing comma, one per line, so the user can paste them straight into the `permissions.allow` array
without editing; never a bare `Bash(...)` token, never prose like "allow storage_read" (user, 2026-10-21: "when adding commands to update
config, always use the format that I can directly paste into the json file"). Several blocks are several REFUSED / NOT DONE rows in the same banner, never a second paragraph. Keep doing
whatever does not need the permission and report that work between the two banners, but a blocked step is never
reported as done, folded into "remaining work", or silently skipped, and the reply never ends on the completed
work: the closing line is the banner. Every later reply of the session repeats the banner until the user has
acted and the blocked step has actually run. This banner overrides the "Replies are short plain text" rule and
any "no headers in a short message" guidance (user, 2026-10-20: "if there is a request that gets blocked because
of permission, add icons and alerts and bold the text in a separate line to make it much more visible. Otherwise
a block might be ignored easily and nothing is completed"; same day: "make it even more obvious").

**A denial that blocks nothing gets NO banner.** When the denied call was a side check, or the step it served was
completed through another allowed path (a different source for the same fact, a read instead of a shell probe; never
by circumventing a gate), or the denial changed no outcome, the reply carries at most one plain sentence naming what
was denied and how the step was done instead, and nothing at all when it changed no outcome. No "superseded" or
"no action needed" banner, no banner for a denial the user does not have to act on (user, 2026-10-20: "the banner
only appears if the permission is blocking future execution"). Before writing a banner, name the requested step that
is still undone; if there is none, there is no banner.
