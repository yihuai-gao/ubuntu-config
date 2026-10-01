#!/usr/bin/env python3
"""PreToolUse gate: force user confirmation of the group name on every cam_uva job submission.

User directive 2026-07-24 (see projects/cosmos3/cam_uva/CLAUDE.md golden rule 6 and the
cam-uva-ask-group-name-before-submit memory): if the user did not explicitly specify a
group name, Claude must ask in chat before submitting. This hook is the mechanical
backstop: it turns every submission tool call into a permission prompt that displays the
group_name about to be used, so a silently defaulted group can never be submitted
without the user seeing it.

Matches:
  - MCP harness submit tools: *lepton_submit_training_job / *slurm_submit_training_job
  - Bash commands that invoke the `submit` CLI or run a submit_job_*.py / submit_vae_bundle.py
Outputs a PreToolUse "ask" decision for matches; outputs nothing otherwise (normal flow).

Debug-job exemption (user directive 2026-07-24): Claude may assign the group name itself
for debug jobs, so submissions to a *_debug project (MCP project_name) or with the -D
flag (submit CLI / submit_job scripts) pass through without the prompt.
"""
import json
import re
import sys

SUBMIT_TOOL = re.compile(r"(lepton|slurm)_submit_training_job$")
# `submit` in command position (start of line or after ; & | ( &&/||, optional VAR=val
# prefixes), or a python invocation of a submit script. Deliberately does NOT match mere
# mentions of submit_job_ in read-only commands like `cat scripts/train/submit_job_x.py`.
BASH_SUBMIT = re.compile(
    r"(?:^|[;&|(]\s*|&&\s+|\|\|\s+)(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*submit\s"
    r"|python[^\n]*submit_job_\w+\.py"
    r"|python[^\n]*submit_vae_bundle\.py"
    r"|-m\s+[\w.]*\bsubmit_job",
    re.M,
)


def main() -> None:
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    tool = d.get("tool_name") or ""
    tool_input = d.get("tool_input") or {}
    if SUBMIT_TOOL.search(tool):
        if str(tool_input.get("project_name") or "").endswith("_debug"):
            return  # debug jobs: Claude may pick the group itself (directive 2026-07-24)
        group = tool_input.get("group_name") or "NOT PROVIDED"
        reason = (
            f"Group-name gate (your directive 2026-07-24): this submission uses group_name = '{group}'. "
            "Approve ONLY if you explicitly specified this group name in chat this session; "
            "deny if Claude defaulted or inferred it."
        )
    elif tool == "Bash" and BASH_SUBMIT.search(tool_input.get("command") or ""):
        if re.search(r"(^|\s)-D(\s|$)", tool_input.get("command") or ""):
            return  # -D = debug project: Claude may pick the group itself
        reason = (
            "Group-name gate (your directive 2026-07-24): this Bash command looks like a job "
            "submission. Approve ONLY if you explicitly specified the group name in chat this "
            "session; deny otherwise."
        )
    else:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


main()
