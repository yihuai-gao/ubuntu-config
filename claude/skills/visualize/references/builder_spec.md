# Section build spec (copy to <scratch>/site_spec.md, fill the <...>, give its path to every builder)

Site dir: <site dir>
Shell (READ IT FIRST, do not edit): shell.html in that dir. It defines the CSS tokens and classes.
Write ONLY your own file: sections/<id>.html. Do not touch other files. Code repos are read-only.

## The user's requirement (most important)
"<the user's own words, e.g. always use figures or animation and use as few words as possible>"
- Every question is answered by a FIGURE first (inline SVG; animated where motion explains something: data
  flowing, bytes being read, frames transforming, a pose moving). Text = labels inside the figure + a caption of at
  most 2 lines.
- No paragraphs. No walls of bullets. Tables only where the comparison is truly tabular; terse cells.
- Under each figure: `<div class="src">path:line · path:line</div>` (paths relative to <path root>). Anything
  inferred or estimated gets `<span class="chip est">est.</span>`. Never invent numbers; illustrative values are
  labelled illustrative.

## Fragment format
```html
<section class="sec" id="<id>" data-nav="<2-3 word nav label>">
  <h2><span class="num">N</span> Statement of the section's main finding or todo, under ~70 chars</h2>
  <p class="lede">one line</p>
  <h3 class="q">Statement of this block's finding (never a question, never a topic label)</h3>
  <div class="fig"> <svg viewBox="0 0 1000 360" role="img" aria-label="..."> ... </svg> </div>
  <div class="cap">short caption</div><div class="src">path:line</div>
  ...
  <style> /* section-scoped: prefix every selector with #<id> */ </style>
  <script> (function(){ const root=document.getElementById('<id>'); /* query only inside root */ })(); </script>
</section>
```

## Rules
- The "todo" section (always first on the page) holds every open todo and pending decision, one expanded block each:
  heading = the item, a figure or animation of what the choice changes (before/after, options, files or data touched,
  cost), the deciding facts, the recommended option marked with a chip, and the consequence of leaving it open.
- Headings carry the information: `h2`, `h3.q`, `data-nav` and every `details>summary` state the finding, the number,
  the blocker or the action ("0 of 8 plan items exist", "oci-jhb misses 3 datasets"). Never a topic label ("What exists
  today"), never a narrative colon title ("The whole story: ..."), never a question ("Is every mirror ready?"). The
  user reads the headings first; they must give the main idea without the figures.
- Self-contained: no external scripts, fonts or images. Inline SVG + CSS animation + small vanilla JS.
- Colors: ONLY the shell's CSS variables, so dark mode works: --c1..--c5 (+ -bg), --ok / --warn / --hold (+ -bg),
  --ink / --ink2 / --ink3, --line / --line2, --panel / --panel2. In SVG: `fill="var(--c3)"`.
  Concept legend for this site (same concept = same color everywhere):
  <--c1 = ..., --c2 = ..., --c3 = ..., --c4 = ..., --c5 = ..., ok = verified, warn = open issue / refused,
  hold = deferred / pending>
- Classes: .card .grid .g2 .g3 .g4 .fig .fig.wide .cap .src .chip(.c1..c5 .ok .warn .hold .est) .callout(.warn .ok .c3)
  table.tbl inside .tblwrap, .btn(.on) .row .big .muted .tiny, details.qa>summary+.body, h3.q.
- SVG text 12-15 in a ~1000-wide viewBox. For dense diagrams use `<div class="fig wide">`: on phones the SVG keeps
  min-width 720 px and scrolls inside its box. The page itself never scrolls horizontally at 390 px.
- Element ids and SVG marker ids carry a section prefix (e.g. `<id>-ar`) so sections never collide.
- Animations loop gently (CSS keyframes) or are driven by Play / Step / Reset buttons. Respect
  prefers-reduced-motion: the shell disables CSS animation; JS must check
  matchMedia('(prefers-reduced-motion: reduce)') and show the END state, which must be a complete figure.
- Interactive toggles (before/after, flag off/on, family / source selectors) replace words; use them.
- Accuracy: facts only from the research reports you were given, re-verified against the code for every line
  reference you cite (reports can mis-cite). If the code disagrees with a report, the code wins; say so in your reply.
- Names say the physical meaning; no coined labels. Times local (<timezone>).
- Size: 25-65 KB per fragment.

## Verify before returning
Run `<python with PIL> <skill dir>/scripts/preview_section.py <site dir> <id> --out <scratch>/preview`
(add `--dark` for a dark pass; `--wait-ms 4000` for a later animation frame). It prints JS errors and overflow and
writes PNG tiles. LOOK at the desktop and phone tiles (Read tool), light and dark; fix overlaps, clipped text,
unreadable labels, broken colors. Repeat until clean (ERRS=[] and no overflow).

## Return
One short paragraph: the questions your section answers (one line each), what you verified against the code, and
anything you could not verify or found contradicting the reports.
