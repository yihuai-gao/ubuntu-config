#!/usr/bin/env python3
"""Hook that enforces the parallel-subagent rule (user directive 2026-10-06, reaffirmed 2026-10-10 after a session
explored four independent trees serially although the rule stood in three places; 2026-10-26: every command is
checked for delegation first, and several commands without a strict dependency run as several subagents at once).

Events (one script, dispatched on hook_event_name):
  UserPromptSubmit  a new turn: reset the per-session counters and inject a one-line reminder of the rule.
  PreToolUse        Agent / Workflow: the turn has delegated -> the gate is cleared for the turn.
                    Bash `subagent-waive <reason>`: the turn is declared not divisible -> cleared, reason recorded.
                    Read / Grep / Glob / WebFetch / WebSearch / read-only Bash: counted as exploration; once more than
                    THRESHOLD exploration calls have run in the turn without an Agent call or a waiver, every further
                    exploration call is DENIED with the two ways out, until one of them happens.
  Stop              end of a turn without a prompt (wake-ups, notifications): reset the counters.

Calls made by a subagent are never gated (a subagent is where the serial reading belongs): detected by an
agent id / agent type in the payload, and otherwise by a transcript path under a subagent directory.
State: ~/.cache/claude-subagent-gate/<session_id>.json (reset every turn; stale after 2 h).
Debug: ~/.cache/claude-subagent-gate/payload_log.txt (event, tool, top-level keys of every payload seen).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

THRESHOLD = int(os.environ.get("SUBAGENT_GATE_THRESHOLD", "8"))
STATE_DIR = Path.home() / ".cache" / "claude-subagent-gate"
EXPLORE_TOOLS = {"Read", "Grep", "Glob", "WebFetch", "WebSearch"}
DELEGATE_TOOLS = {"Agent", "Workflow"}
READ_ONLY_CMDS = {
    "cat", "head", "tail", "sed", "grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "ls", "tree", "wc", "du", "df",
    "stat", "file", "which", "type", "readlink", "realpath", "jq", "yq", "awk", "cut", "sort", "uniq", "diff", "cmp",
    "curl", "wget", "nl", "column", "tr", "basename", "dirname", "echo", "printf", "test", "[", "true", "pwd",
    "nvidia-smi", "free", "ps", "pgrep", "env", "printenv", "hostname", "date", "md5sum", "sha256sum", "ffprobe",
    "strings", "hexdump", "xxd", "od", "tac", "rev", "comm", "join", "paste", "fold", "expand", "ls-files", "lsblk",
}
GIT_READ_ONLY = {"log", "show", "diff", "status", "blame", "ls-files", "ls-tree", "branch", "worktree", "rev-parse",
                 "describe", "cat-file", "remote", "tag", "shortlog", "grep", "config", "reflog", "stash"}
SHELL_WORDS = {"for", "do", "done", "if", "then", "else", "elif", "fi", "while", "until", "in", "cd", "export", "time",
               "exec", "command", "builtin", "nohup", "sudo"}
WAIVER = re.compile(r"^\s*subagent-waive\b\s*(.*)", re.S)
REMINDER = (
    "SUBAGENTS FIRST (hook-enforced; user 2026-10-26, as strong as possible): before your first tool call, decide "
    "whether this command can run in a separate subagent so it finishes sooner and the main session stays free, and "
    "state the decision in one line; the default is yes, and 'only a few calls' is never the reason for no. Several "
    "commands (one message, or arriving mid-turn) without a strict dependency = several subagents in ONE tool "
    "message, never one agent or the main session working through them in order. "
    "Parallel-subagent rule: when this turn needs more than about {n} read-only tool calls, or reads "
    "more than two independent trees, files or sources, spawn parallel subagents in your FIRST tool message (Agent, "
    "model opus for exploration, research, review and operations; fable only for code implementation). After {n} exploration calls without "
    "an Agent call the gate denies further exploration until you spawn subagents or run "
    "`subagent-waive <one-line reason why this task is not divisible>`."
)


def log_payload(d: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = STATE_DIR / "payload_log.txt"
        if p.exists() and p.stat().st_size > 200_000:
            p.unlink()
        with p.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {d.get('hook_event_name')} {d.get('tool_name')} "
                    f"keys={sorted(d.keys())} agent={d.get('agent_id')}/{d.get('agent_type')}\n")
    except Exception:
        pass


def in_subagent(d: dict) -> bool:
    if d.get("agent_id") or d.get("agent_type") or d.get("parent_session_id"):
        return True
    tp = str(d.get("transcript_path") or "")
    return "/subagents/" in tp or "/agent-" in tp


def state_path(sid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '_', sid or 'nosession')}.json"


def fresh_state() -> dict:
    return {"turn_started": time.time(), "explore_calls": 0, "agent_calls": 0, "waiver": None, "denied": 0}


def load_state(sid: str) -> dict:
    p = state_path(sid)
    try:
        s = json.loads(p.read_text())
        if time.time() - float(s.get("turn_started", 0)) > 7200:
            return fresh_state()
        return s
    except Exception:
        return fresh_state()


def save_state(sid: str, s: dict) -> None:
    try:
        state_path(sid).write_text(json.dumps(s))
    except Exception:
        pass


def is_read_only_bash(command: str) -> bool:
    """True when every simple command of the line is a read-only command (so the call is exploration)."""
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", " ", command, flags=re.S)  # drop heredoc bodies
    cmd = re.sub(r"\$\([^()]*\)", " ", cmd)  # command substitutions are judged by their outer command
    segments = re.split(r"\|\||&&|\||;|\n|\(|\)", cmd)
    seen = False
    for seg in segments:
        words = seg.strip().split()
        words = [w for w in words if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]  # VAR=value prefixes
        while words and words[0] in SHELL_WORDS:
            if words[0] == "cd":
                words = words[2:]
            else:
                words = words[1:]
        if not words:
            continue
        head = os.path.basename(words[0])
        if head == "git":
            if len(words) < 2 or words[1] not in GIT_READ_ONLY:
                return False
        elif head == "sed":
            if "-i" in words or any(w.startswith("-i") for w in words[1:]):
                return False
        elif head not in READ_ONLY_CMDS:
            return False
        seen = True
    return seen


def main() -> None:
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    log_payload(d)
    if in_subagent(d):
        return
    event = d.get("hook_event_name") or ""
    sid = d.get("session_id") or ""
    if event == "UserPromptSubmit":
        save_state(sid, fresh_state())
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": REMINDER.format(n=THRESHOLD)}}))
        return
    if event == "Stop":
        save_state(sid, fresh_state())
        return
    if event != "PreToolUse":
        return
    tool = d.get("tool_name") or ""
    tool_input = d.get("tool_input") or {}
    s = load_state(sid)
    if tool in DELEGATE_TOOLS:
        s["agent_calls"] += 1
        save_state(sid, s)
        return
    command = str(tool_input.get("command") or "") if tool == "Bash" else ""
    m = WAIVER.match(command) if command else None
    if m:
        s["waiver"] = m.group(1).strip() or "(no reason given)"
        save_state(sid, s)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                 "permissionDecisionReason": "subagent rule waived for this turn"}}))
        return
    exploring = tool in EXPLORE_TOOLS or (tool == "Bash" and is_read_only_bash(command))
    if not exploring:
        return
    s["explore_calls"] += 1
    cleared = s["agent_calls"] > 0 or s["waiver"]
    if cleared or s["explore_calls"] <= THRESHOLD:
        save_state(sid, s)
        return
    s["denied"] += 1
    save_state(sid, s)
    reason = (
        f"SUBAGENT GATE: {s['explore_calls']} exploration calls this turn and no Agent call. The user's standing rule: "
        "a divisible task (several files, trees, sources or checks to read) is split across parallel subagents launched "
        "in ONE message, never crawled serially. Do one of these now, then continue: (1) spawn parallel Agent calls "
        "(model opus for exploration, research, review and operations; fable only for code implementation), one self-contained "
        "brief per independent part, and integrate their reports; or (2) if this task is genuinely not divisible, run "
        "`subagent-waive <one-line reason>` (the reason is shown to the user). Further exploration calls are denied "
        "until one of the two happens."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
