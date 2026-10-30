# Global Codex rules (all projects)

## Credit budget: the cost is calls × context, not thinking

Every model call re-reads the whole context; cached input is ~70% of my Codex spend. A thread at 130K context
making one call every 15 s for 9 hours (the 2026-10-17 caption campaign: 8,000 calls, 55% of a week's credits,
killed by the workspace spend cap with no final answer) is the failure mode these rules prevent.

- **Bounded tasks only.** Before starting, state the deliverable and a stop condition ("list the gaps and the commands
  that fix them, then stop"). "Make sure everything is done" is not a stop condition: turn it into a checklist first and
  show it to the user.
- **No self-requeue chains.** Do not call `followup_task` to keep a thread alive past its current deliverable. One
  follow-up to finish a running job is fine; a chain of them is not. Deliver, then end the turn.
- **Blocked means stop.** After `request_user_input_async` (or any question to the user), finish only what does not
  depend on the answer, write the handoff, and end the turn. Never keep iterating for hours on an unanswered question.
- **Checkpoint doc every ~200 calls or hour.** Write a short progress file (done / remaining / gates / where the data
  is) so a spend-cap or crash leaves a usable state. The 10-17 run died mid-batch with nothing written to the repo docs.
- **Scripts, not model-per-row work.** When the task is "process / verify / augment N items", write one script that
  handles all N, run it once (background job if long), and review a sample. Never push items through the model in
  batches of 8–20, and never generate `_v1 … _v5` variants of near-identical helper scripts; fix the one script.
- **Keep tool output small.** `wc -l` / `head` / `rg -n` before `cat`; set `max_output_tokens` on every exec; never dump
  files above ~50 KB into context (the 10-17 run pasted 9 MB JSON dumps). Batch independent commands into one exec.
  No polling loops: use `wait_agent` / blocking waits, not `cat status.json` every few seconds.
- **Context hygiene.** One thread per task; start a fresh thread for a new task instead of continuing a 20-hour one.
  If the thread has compacted twice, write the handoff file and tell the user to start a new thread from it.
- **Canonical data writes need the user's explicit yes in this session.** A prompt like "make sure X is ready" authorises
  analysis and a proposal, not rewriting dataset labels, pushing to mirrors or editing harness allowlists.

## Subagents: few, short-context, bounded

- Spawn (`spawn_agent`) only for parts that are independent and bounded; a user saying "spawn 20 agents" means
  "parallelise", not "20": pick the number of real independent parts (usually 3–6) and say so.
- Each subagent gets a self-contained brief (paths, constraint, exact return format ≤ 300 words, stop condition) and
  should finish within a small context (target < 40K tokens). A subagent is a worker that runs a script and reports;
  it is not a second long-lived orchestrator.
- No agent-to-agent chatter loops: the 10-17 run sent 2,000 `send_message` calls between four threads. Send a brief
  once, `wait_agent` for the result, and integrate. Do not relay status back and forth.
- The orchestrator stays small: it holds briefs and results, never the raw tool dumps of its subagents.
