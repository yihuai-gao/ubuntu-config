---
name: visualize
description: Explore a codebase, branch, worktree, diff, dataset or design with parallel research subagents and turn the answers into a locally hosted, figure-first explainer website (inline SVG, animations, toggles; as few words as possible), one section per question, built in parallel by section-builder subagents, screenshot-verified in headless Chromium at desktop and phone widths in light and dark mode. Use when the user asks to "visualize", "explain with figures / animation", "host a website / page to show me", "make an explainer", or wants to understand how some code or data pipeline works and how it differs from something else, especially with a list of questions about a repository or worktree.
argument-hint: "<questions> [repo / worktree / branch / paths]"
---

# Visualize: figure-first explainer website from parallel exploration

The user supplies QUESTIONS and one or more SOURCES (repos, worktrees, branches, diffs, docs, data).
This skill is only the process and the meta requirements; every fact on the page comes from the sources
of the current request. Never reuse content from an earlier site.

Bundled files (copy, do not edit in place):
- `assets/shell.html`: page shell (design tokens, light/dark, nav, components). Section HTML is injected.
- `scripts/build.py`: assembles `index.html` from `site.json` + `shell.html` + `sections/<id>.html`; builds the nav.
- `scripts/preview_section.py`: renders one section (or the whole site) in headless Chromium, desktop 1280 +
  phone 390, optional dark, slices tiles to PNG, prints JS errors and horizontal overflow.
- `references/research_prompt.md`: template for an exploration subagent.
- `references/builder_spec.md`: the contract every section builder follows (copied into the run's scratch dir).

## Meta requirements (the user's standing preferences)

1. **Figures first, minimal words.** Every question is answered by a figure (inline SVG; animation where motion
   explains: data flowing, bytes read, frames transformed, poses moving; toggles for before/after, flag on/off,
   family selectors). Text = labels inside figures + a caption of at most 2 lines. No paragraphs, no bullet walls.
   Tables only for truly tabular comparisons, terse cells.
2. **Answer every asked question, then add more.** A final "More questions worth asking" section with 12-16
   collapsible cards, each a mini figure + one line, covering what the user should have asked (switch on/off
   states, what is untested, inconsistencies between doc and code, failure behaviour, hidden assumptions).
3. **Evidence on every figure:** a `.src` line with `path:line`. Mark anything inferred or estimated with the
   `est.` chip. Every number is measured/read or marked estimated. No invented numbers.
4. **Show ALL aspects when asked for differences**: an exhaustive comparison matrix, grouped and filterable.
5. **Hosted locally, never as an Artifact** (unless the user asks otherwise), on the report hub: one server on
   `http://127.0.0.1:8802/` (`/home/yihuai/reports/hub/`), every site at its own subpath `/s/<slug>/`. Never a
   second server per site.
6. **Also save the full written report** as markdown (the global report rule: project report dir, `<topic>_<MMDD>.md`,
   absolute path in the reply); the site links to nothing private outside the machine.
7. **Parallel subagents**: exploration by Opus subagents, section building by Fable subagents, all spawned in one
   message per wave. Each gets a self-contained prompt. Project rules that forbid subagents in an area still win.
8. Phone width (390 px) works: no horizontal page scroll; dense diagrams use `.fig.wide` (scroll inside their box).
9. Times are local (Pacific for this user); file links in the final reply are absolute paths.
10. **Always current, never stacked.** Updating a topic = rebuilding the SAME site in place (same slug, same URL):
    stale sections, figures and numbers are deleted and replaced, never kept beside the new ones, and never a second
    site for the same topic. The hub hides superseded rounds by default; the markdown rounds stay as the audit trail.

11. **Headings state the finding or the todo, never the topic, never a question.** The page title, every section `h2`,
    every `h3.q`, nav label, overview card and `details>summary` line is a short statement (under ~70 chars) of the most
    important fact of that block: verdict, number, blocker or action. Banned: topic labels ("What exists today",
    "Overview"), narrative colon titles ("The whole story in one picture: ..."), question headings ("Is every mirror
    ready?"). Write "Nothing built yet: 0 of 8 plan items exist", "oci-jhb Lustre misses 3 datasets, HF and gcp-iad
    complete". The headings alone must give the main idea of the report; the "More questions" section becomes
    "N further findings: <the most important one>" with each card summary stating the answer (user 2026-10-16).

12. **TODOs and pending decisions come first, each expanded.** Section 1 of every site (before the overview) is the
    "todo / decisions" section: every open todo and pending decision, ordered by urgency, heading = the item itself.
    Each gets its own figure or animation (what the choice changes, before/after, the files or data it touches, cost of
    each option), the facts that decide it, a marked recommended option, and the consequence of leaving it open. One
    collapsed line per item is not enough. No open items: the first heading says so (user 2026-10-16).

## Process

### 0. Scope (1-2 minutes, no subagents yet)
- Identify the exact sources: `git worktree list`, branch, merge base (`git merge-base HEAD origin/main`),
  `git diff <base> --stat` plus `git status --short` (uncommitted work counts). Name them on the page.
- If the target is ambiguous (several candidate worktrees or repos), resolve it from names and recency;
  ask (AskUserQuestion) only when it stays ambiguous.
- Split the user's questions into 3-5 independent research topics (one per question is typical; add one for
  "what changed in this branch" when a diff is involved).

### 1. Explore (parallel Opus subagents, read-only)
- One `general-purpose` subagent per topic, `model: "opus"`, built from `references/research_prompt.md`.
- Each returns a dense structured report with `file:line` evidence, sample shapes / schemas, a step list for a
  flow diagram, and a final comparison table where relevant. They write nothing except scratch notes.
- While they run, set up the site (step 2). Do not duplicate their reading.
- Save each returned report verbatim-dense to `<scratch>/report_<X>_<topic>.md`, so builders read files, not prompts.

### 2. Site skeleton (orchestrator)
- Site dir: the project's report/docs dir when it has one (`<docs>/<topic>_explainer_<MMDD>/`), else
  `<repo>/docs/reviews/<topic>_explainer_<MMDD>/`, else `~/reports/<project>/<topic>_explainer_<MMDD>/`.
- Copy `assets/shell.html` and `scripts/build.py` there; write `site.json`:
  `{"title": "<2-4 word name>", "brand": "<short nav brand>", "footer_html": "<sources, snapshot time, est. legend>",
    "sections": ["todo", "overview", "<id1>", ..., "more-qa"]}` ("todo" = the todos / pending decisions section, always first).
- Assign each recurring concept a color token in a legend that goes into the builder spec (shell offers
  `--c1..--c5` + `--ok --warn --hold`, each with `-bg`). Same concept = same color on every section.
- Copy `references/builder_spec.md` to `<scratch>/site_spec.md` and fill its placeholders (site dir, scratch dir,
  preview command, color legend, the user's exact wording of the requirements).
- Test the preview pipeline once on a dummy section (see Chromium notes), then delete the dummy.
- Register the site on the hub instead of starting a server: `/home/yihuai/reports/hub/bin/hub register <site dir>`
  (symlinks it to `/s/<slug>/` and rebuilds the root page), then `/home/yihuai/reports/hub/bin/hub serve` (idempotent:
  starts the detached server only when nothing listens on 8802); verify with `curl -sI http://127.0.0.1:8802/s/<slug>/`.
  Sections are rebuilt in place, so the URL is stable while builders work. Site dirs under the hub's scanned roots
  (cam_uva `docs/`, camx `docs/reviews/`, `~/reports/<project>/`) are also found by a plain `bin/hub rebuild`.

### 3. Build sections (parallel Fable subagents)
- One builder per section, `model: "fable"`, all in one message. Prompt = section id, number, a provisional title that the
  builder must rewrite into a statement of the finding once it knows it (meta requirement 11), which
  report files to read, the user's question verbatim, a numbered list of suggested sub-questions each with a
  suggested figure (centrepiece animation first), and "write ONLY sections/<id>.html".
- The "todo" builder reads ALL reports and gets every open item the research found; it builds one expanded block per
  item (figure + deciding facts + recommended option + cost of leaving it open), ordered by urgency.
- The orchestrator writes the overview section itself: snapshot line, 3-4 stat tiles, ONE diagram
  connecting every section (its heading states the overall verdict, never "the whole story"), a "where did the change go" bar chart when a diff is involved, and one-line answer
  cards linking to each section.
- The "More questions" builder reads ALL reports.
- When a builder reports a reusable layout fix (e.g. a grid overflow), move it into the shared shell and tell
  the running builders (SendMessage).

### 4. Integrate and verify (orchestrator)
- `python3 build.py`; check duplicate element ids and unscoped section CSS; render the whole site with
  `preview_section.py <site> ALL --out <scratch>/preview` (desktop + phone, light + dark): zero JS errors, no horizontal overflow.
- Look at tiles yourself (Read the PNGs): overlapping labels, clipped text, unreadable dark-mode colors.
- Spot-check numbers against the code (recompute 2-3 worked examples / byte ranges / allocations).
- **Drift check before delivery**: if the source is a live worktree, compare file mtimes and `git status` against
  the research time. Another session may be editing it. Re-verify every changed fact, send precise re-sync
  instructions to the affected builders (resume them by SendMessage so they keep context), pin the page to a
  snapshot time, and add a "live" chip + timeline when facts moved during the build.
- Append an "updates after the research pass" section to the markdown report for anything that changed.

### 5. Deliver
Reply in at most ~15 lines: the hub URL of the site (`http://127.0.0.1:8802/s/<slug>/`) and of the rendered report
(`/r/<slug>/`), one line per section stating its finding, the 3-6 most important findings (switches that are off,
untested paths, inconsistencies), and absolute links to `index.html`, the shell/sections/build sources and the markdown
report. The hub server is shared: never stop it for one site. Nothing is `git add`ed.

## Headless Chromium notes (this machine)
- Binary: `~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell`.
  It needs `LD_LIBRARY_PATH=/data/yihuai/miniforge3/envs/headless-libs/lib` (libnspr4/libnss3 are not system-wide).
- PIL is in `/data/yihuai/miniforge3/envs/cam-uva/bin/python` (not in `/usr/bin/python3`); run the preview with it.
- `--virtual-time-budget` freezes CSS transitions/animations at an early frame: use `--wait-ms` for a later frame,
  and give every animation a reduced-motion end state that renders correctly (that is what reviewers see).
- `--screenshot` only captures the window, so the script measures `scrollHeight` via `--dump-dom` first.

## Pitfalls seen before
- Live worktrees change under you (stream counts, fixed bugs, new commits): always run the drift check.
- Research reports can mis-cite paths; builders re-verify line refs against the files and correct them.
- `.grid` children need `min-width:0` or a table inside a card widens the phone page (already in the shell).
- Wide SVGs become unreadable at 390 px: use `.fig.wide`.
- Long labels inside fixed SVG boxes overflow: shorten labels rather than shrinking fonts below 12.
