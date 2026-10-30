# Research subagent prompt template (Opus, read-only)

Spawn with `subagent_type: "general-purpose"`, `model: "opus"`, `run_in_background: true`, one per topic, all in
one message. Fill every <...>; delete lines that do not apply.

```
READ-ONLY research task. Do not edit, create, or delete any files in the repos, no git mutations (read-only
`git diff/log/show` is fine), no network/cloud. Scratch notes only under <scratch dir>.

Goal: <one sentence: the user's question this topic answers>. The result feeds a figure-first explainer website,
so be concrete: file:line references, schema / field names, dtypes, shapes, path patterns, step order.

Sources:
- <repo / worktree absolute path> (read files as they are on disk; uncommitted edits count).
  Merge base <sha>: `git -C <path> diff <sha> -- <file>` shows what the branch changed.
- Key files: <paths or globs; design docs first>.
- Comparison side (if any): <path>.
- Background notes (facts, may be outdated): <memory / doc paths>.

Answer, with evidence:
1. <sub-question>
2. <sub-question>
...
N. What the branch changed in the files above (per file, 1-3 bullets), if a diff is involved.

Return a structured markdown report with those sections, plus:
- a "flow in 6-12 boxes" list (box -> one-line what it does -> file:function) for a diagram,
- a shape / schema table (key | shape | dtype | meaning) for any data sample involved,
- a comparison table (Aspect | A | B | evidence) when the question asks for differences, covering ALL aspects found.
Mark anything inferred as "(inferred)" and anything from notes rather than code as "(mem)".
Dense, 1500-3000 words.
```

After it returns: save the report to `<scratch>/report_<letter>_<topic>.md` (keep every number and file:line),
note the research time, and flag claims that disagree across reports for the builders to re-verify.
