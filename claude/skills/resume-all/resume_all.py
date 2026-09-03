#!/usr/bin/env python3
"""Identify Claude Code sessions that were open (VSCode extension or tmux) for
a workspace but whose processes are dead — machine shutdown, reboot,
vscode-server crash, OOM kill — and resume each one in a detached tmux session.

Why this needs a state file and a timer (all verified 2026-08-24, claude
2.1.241):
  - Every interactive claude process registers ~/.claude/sessions/<pid>.json
    on startup and removes it on graceful exit — INCLUDING SIGTERM, which is
    what a normal OS shutdown sends. Only SIGKILL/crash leaves the entry.
  - Any newly starting claude process garbage-collects dead entries within
    seconds. After a reboot, the first session the user opens (the one they
    run /resume-all in) would sweep the evidence.
  So a systemd user timer runs `resume_all.py --tick` every minute, mirroring
  the set of LIVE sessions into a state file outside ~/.claude. On the first
  tick after a boot (or on resolve), sessions that were live at the last
  pre-boot tick are marked killed-by-shutdown. `resume_all.py` (resolve mode)
  resumes those, plus any dead registry entries it can still see directly.

Resume = `tmux new-session -d -s ccr-<sid8> claude --resume <sid>`; --resume
keeps the same session id, and success is verified by the resumed process
re-registering under that id.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
STATE_DIR = Path.home() / ".local" / "state" / "claude-resume-all"
STATE_FILE = STATE_DIR / "state.json"
LOG_ROOTS = [
    Path.home() / ".vscode-server" / "data" / "logs",
    Path.home() / ".vscode-server-insiders" / "data" / "logs",
    Path.home() / ".cursor-server" / "data" / "logs",
]
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
TMUX_PREFIX = "ccr-"
SHUTDOWN_GRACE_S = 120   # live within this window of the last pre-boot tick
KEEP_KILLED_DAYS = 7     # forget unresumed killed sessions after this long
STALE_TICK_WARN_S = 180  # warn if the timer hasn't ticked for this long
STALL_QUIET_S = 120      # a live session is "stalled" only if its transcript
                         # has been untouched this long (else it is working)
STALL_LOOKBACK = 12      # messages inspected at the transcript tail
LIMIT_RE = re.compile(r"hit your (?:session|usage) limit", re.I)
RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*\(([^)]+)\)", re.I)
API_ERR_RE = re.compile(r"^\s*API Error", re.I)
INTERRUPT_RE = re.compile(r"^\s*\[Request interrupted by user")
DEFAULT_NUDGE = ("The usage limit / interruption is over. Continue from where "
                 "you left off: re-check any background monitors that were "
                 "stopped, restart them if still needed, and finish the task "
                 "you were working on.")


def munge(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def boot_time() -> float:
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("btime "):
            return float(line.split()[1])
    raise RuntimeError("no btime in /proc/stat")


def proc_starttime(pid: int):
    """starttime (clock ticks since boot) from /proc/<pid>/stat, or None."""
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text()
    except OSError:
        return None
    # comm can contain spaces/parens; fields resume after the last ')'.
    tail = stat.rsplit(")", 1)[1].split()
    return tail[19]  # field 22 overall; tail starts at field 3 (state)


def pid_is_this_session(pid: int, proc_start: str) -> bool:
    if proc_starttime(pid) != str(proc_start):
        return False
    try:
        cmdline = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return False
    return b"claude" in cmdline


def load_registry():
    """(live, dead): sid -> registry entry, across ALL workspaces."""
    live, dead = {}, {}
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sid = entry.get("sessionId")
        if not sid or entry.get("kind") != "interactive":
            continue
        if pid_is_this_session(entry.get("pid", -1), entry.get("procStart", "")):
            live[sid] = entry
        else:
            prev = dead.get(sid)
            if prev is None or entry.get("startedAt", 0) > prev.get("startedAt", 0):
                dead[sid] = entry
    return live, dead


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"lastTick": 0, "prevShutdownTick": 0, "sids": {}}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_FILE)


def tick(quiet=True):
    """Refresh the state file from the current registry. Runs every minute
    from the systemd timer, and inline at the start of resolve."""
    now = time.time()
    btime = boot_time()
    state = load_state()
    sids = state["sids"]

    first_tick_after_boot = 0 < state["lastTick"] < btime
    if first_tick_after_boot:
        state["prevShutdownTick"] = state["lastTick"]
        for sid, rec in sids.items():
            if not rec.get("killedAt") and \
                    rec.get("lastSeenLive", 0) >= state["lastTick"] - SHUTDOWN_GRACE_S:
                rec["killedAt"] = state["lastTick"]  # presumed killed by shutdown

    live, dead = load_registry()
    for sid, entry in live.items():
        sids[sid] = {"cwd": entry.get("cwd"), "lastSeenLive": now}
    for sid, entry in dead.items():
        if sid in live:
            continue
        rec = sids.setdefault(
            sid, {"cwd": entry.get("cwd"), "lastSeenLive": now})
        rec.setdefault("killedAt", now)  # SIGKILL/crash: entry left behind

    for sid in list(sids):
        rec = sids[sid]
        if sid in live or sid in dead:
            continue
        if rec.get("killedAt"):
            if now - rec["killedAt"] > KEEP_KILLED_DAYS * 86400:
                del sids[sid]  # stale, forget
        elif not first_tick_after_boot:
            del sids[sid]  # closed cleanly since the last tick

    state["lastTick"] = now
    save_state(state)
    if not quiet:
        nk = sum(1 for r in sids.values() if r.get("killedAt"))
        print(f"tick: {len(live)} live, {nk} killed pending across all workspaces")
    return state


def live_resume_pids():
    """Session ids held by ANY live claude process (--resume <sid> in cmdline).
    Used only to EXCLUDE candidates — it sees other users' processes too."""
    sids = set()
    for f in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            cmd = f.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "claude" not in cmd:
            continue
        m = re.search(r"--resume[= ](%s)" % UUID_RE, cmd)
        if m:
            sids.add(m.group(1))
    return sids


def log_candidates(workspace: str, since: float):
    """Session ids from IDE extension logs whose spawn cwd == workspace.
    Over-inclusive (contains cleanly closed tabs); opt-in via --logs."""
    pat = re.compile(
        r"Spawning Claude with SDK query function - cwd: %s,.*resume: (%s)"
        % (re.escape(workspace), UUID_RE)
    )
    sids = set()
    for root in LOG_ROOTS:
        if not root.is_dir():
            continue
        for log in root.glob("*/exthost*/Anthropic.claude-code/*.log"):
            try:
                if log.stat().st_mtime < since:
                    continue
                for line in log.read_text(errors="replace").splitlines():
                    m = pat.search(line)
                    if m:
                        sids.add(m.group(1))
            except OSError:
                continue
    return sids


def transcript_info(proj_dir: Path, sid: str):
    """(path, mtime, title) for a session transcript, or (None, None, None)."""
    p = proj_dir / f"{sid}.jsonl"
    if not p.is_file():
        return None, None, None
    title = None
    try:
        with open(p, errors="replace") as fh:
            for line in fh:
                if '"ai-title"' in line:
                    try:
                        d = json.loads(line)
                        if d.get("type") == "ai-title":
                            title = d.get("aiTitle")
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return p, p.stat().st_mtime, title


def _msg_text(d):
    """Flatten a transcript user/assistant record to (kind, text).
    kind: 'user' | 'assistant' | 'tool' | 'meta'."""
    m = d.get("message") or {}
    c = m.get("content")
    if isinstance(c, str):
        txt = c
    elif isinstance(c, list):
        parts = []
        for x in c:
            if not isinstance(x, dict):
                continue
            t = x.get("type")
            if t == "text":
                parts.append(x.get("text", ""))
            elif t in ("tool_result", "tool_use"):
                return "tool", ""
        txt = " ".join(parts)
    else:
        return "meta", ""
    txt = txt.strip()
    if d.get("type") == "user" and txt.startswith("<") and not INTERRUPT_RE.match(txt):
        return "meta", txt  # task-notification / system attachments
    return d.get("type"), txt


def tail_messages(path: Path, n: int):
    """Last n (kind, timestamp, text) user/assistant records of a transcript."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - 4_000_000))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for line in data.splitlines():
        if '"user"' not in line and '"assistant"' not in line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") not in ("user", "assistant"):
            continue
        kind, txt = _msg_text(d)
        ts = d.get("timestamp") or ""
        out.append((kind, ts, txt))
    return out[-n:]


def parse_reset(text: str, said_at: str):
    """Absolute reset time (epoch) from 'resets 5pm (America/Los_Angeles)',
    anchored to the day the message was emitted. None if unparseable."""
    m = RESET_RE.search(text)
    if not m:
        return None
    hh, mm, ampm, tzname = int(m.group(1)), int(m.group(2) or 0), m.group(3), m.group(4)
    if ampm:
        hh = hh % 12 + (12 if ampm.lower() == "pm" else 0)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname)
        said = datetime.fromisoformat(said_at.replace("Z", "+00:00")).astimezone(tz)
    except Exception:
        return None
    reset = said.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if reset < said:
        from datetime import timedelta
        reset += timedelta(days=1)
    return reset.timestamp()


def stall_status(path: Path, mtime: float):
    """Classify a LIVE session from its transcript tail.
    Returns (kind, detail, actionable) or None when it looks healthy/busy.
    kinds: limit | api-error | interrupted | unanswered."""
    if time.time() - mtime < STALL_QUIET_S:
        return None  # transcript still moving: the session is working
    msgs = tail_messages(path, STALL_LOOKBACK)
    if not msgs:
        return None
    # Limit: the last substantive assistant text is the limit banner (kicks
    # after it only produce "No response requested." / empty text).
    for kind, ts, txt in reversed(msgs):
        if kind != "assistant":
            continue
        if not txt or txt == "No response requested.":
            continue
        if LIMIT_RE.search(txt):
            reset = parse_reset(txt, ts)
            if reset is None:
                return "limit", "reset time unknown", True
            if time.time() >= reset:
                return "limit", f"reset {fmt_ts(reset)} passed", True
            return "limit", f"resets {fmt_ts(reset)}", False
        if API_ERR_RE.match(txt):
            return "api-error", txt[:60], True
        break
    last_kind, last_ts, last_txt = msgs[-1]
    if last_kind == "user" and INTERRUPT_RE.match(last_txt):
        return "interrupted", last_txt[:60], True
    if last_kind == "user" and last_txt:
        return "unanswered", last_txt[:60], True
    return None


def stalled(args):
    """List live sessions of this workspace that are idle because of a usage
    limit, an API error, an interruption, or an unanswered prompt (process
    restarted mid-turn). Nudges tmux-hosted ones directly; VSCode-hosted ones
    are emitted for the caller to message (SendMessage peer name)."""
    workspace = str(Path(args.workspace).resolve())
    proj_dir = PROJECTS_DIR / munge(workspace)
    live_reg, _ = load_registry()
    rows = []
    for sid, entry in sorted(live_reg.items()):
        if entry.get("cwd") != workspace:
            continue
        path, mtime, title = transcript_info(proj_dir, sid)
        if path is None:
            continue
        st = stall_status(path, mtime)
        if st is None:
            continue
        kind, detail, actionable = st
        rows.append({"sid": sid, "peer": entry.get("name"), "pid": entry.get("pid"),
                     "kind": kind, "detail": detail, "actionable": actionable,
                     "lastActive": mtime, "title": title or "(untitled)",
                     "tmux": TMUX_PREFIX + sid[:8] if tmux_has(TMUX_PREFIX + sid[:8]) else None})
    print(f"Workspace: {workspace}")
    print(f"{len(rows)} stalled live session(s)\n")
    for r in rows:
        flag = "NUDGE" if r["actionable"] else "wait "
        print(f"  {r['sid'][:8]}  {fmt_ts(r['lastActive']):>11}  {flag}  {r['kind']:<11} "
              f"{r['detail']:<28}  {r['peer'] or '?':<32}  {r['title']}")
    if args.json:
        print("\nJSON: " + json.dumps(rows))
    if not args.nudge:
        return
    print()
    for r in rows:
        if not r["actionable"]:
            continue
        if r["tmux"]:
            for line in ("/compact", args.kick or DEFAULT_NUDGE):
                tmux("send-keys", "-t", r["tmux"], line)
                time.sleep(0.5)
                tmux("send-keys", "-t", r["tmux"], "Enter")
                time.sleep(3)
            print(f"  {r['sid'][:8]}  nudged via tmux {r['tmux']}")
        else:
            print(f"  {r['sid'][:8]}  VSCode-hosted — send '/compact' then the nudge "
                  f"via SendMessage to peer {r['peer']}")


def consume(workspace: str, sid: str):
    """After a verified resume: drop the sid from state and remove any stale
    registry files, so a later run cannot resurrect it a second time."""
    state = load_state()
    if sid in state["sids"]:
        del state["sids"][sid]
        save_state(state)
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if entry.get("sessionId") != sid or entry.get("cwd") != workspace:
            continue
        if pid_is_this_session(entry.get("pid", -1), entry.get("procStart", "")):
            continue
        pid = f.name.split(".")[0]
        for stale in [f, *SESSIONS_DIR.glob(f"{pid}.*.key")]:
            try:
                stale.unlink()
            except OSError:
                pass


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def tmux_has(name: str) -> bool:
    return tmux("has-session", "-t", "=" + name).returncode == 0


def fmt_ts(ts) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def timer_health():
    state = load_state()
    if state["lastTick"] == 0:
        return ("state file has never been written — the snapshot timer is "
                "not installed. Run install_timer.sh from this skill dir; "
                "without it, sessions open at a REBOOT cannot be identified "
                "(claude cleans its registry on SIGTERM).")
    # A pre-boot lastTick is expected right after a reboot, not a fault.
    age = time.time() - state["lastTick"]
    if age > STALE_TICK_WARN_S and state["lastTick"] > boot_time():
        return (f"snapshot timer looks dead (last tick {age/60:.0f} min ago). "
                "Check: systemctl --user status claude-resume-all.timer")
    return None


def resolve(args):
    workspace = str(Path(args.workspace).resolve())
    proj_dir = PROJECTS_DIR / munge(workspace)
    if not proj_dir.is_dir():
        sys.exit(f"No transcript directory for workspace: {proj_dir}")

    warn = timer_health()
    state = tick()  # fold current registry + reboot detection into state
    live_reg, dead_reg = load_registry()
    live_here = {s for s, e in live_reg.items() if e.get("cwd") == workspace}
    live_any = set(live_reg) | live_resume_pids()

    candidates = {}  # sid -> why
    for sid, rec in state["sids"].items():
        if rec.get("cwd") != workspace:
            continue
        if rec.get("killedAt"):
            candidates[sid] = "killed " + fmt_ts(rec["killedAt"])
    for sid, entry in dead_reg.items():
        if entry.get("cwd") == workspace:
            candidates.setdefault(sid, "dead registry entry")
    if args.logs:
        for sid in log_candidates(workspace, time.time() - args.hours * 3600):
            candidates.setdefault(sid, "extension log")
    for sid in args.include:
        candidates[sid] = "explicitly requested"
    for sid in live_here:
        candidates.setdefault(sid, "")

    rows, to_resume = [], []
    for sid, why in sorted(candidates.items()):
        path, mtime, title = transcript_info(proj_dir, sid)
        title = title or "(untitled)"
        if sid in live_any:
            rows.append((sid, "already running", mtime, title))
        elif path is None:
            rows.append((sid, "no transcript, skipped", None, title))
        elif why == "extension log" and mtime < time.time() - args.hours * 3600:
            rows.append((sid, f"idle > {args.hours:g}h, skipped", mtime, title))
        elif tmux_has(TMUX_PREFIX + sid[:8]):
            rows.append((sid, "tmux session exists", mtime, title))
        else:
            rows.append((sid, f"RESUME ({why})", mtime, title))
            to_resume.append((sid, title))

    print(f"Workspace: {workspace}")
    if warn:
        print(f"WARNING: {warn}")
    print(f"{len(live_here)} live session(s), {len(to_resume)} to resume\n")
    for sid, status, mtime, title in rows:
        print(f"  {sid[:8]}  {fmt_ts(mtime):>11}  {status:<28}  {title}")

    if not to_resume or args.dry_run:
        if args.dry_run and to_resume:
            print("\n(dry run — nothing resumed)")
        return

    print()
    spawned = []
    for sid, title in to_resume:
        name = TMUX_PREFIX + sid[:8]
        r = tmux("new-session", "-d", "-s", name, "-c", workspace,
                 "claude", "--resume", sid)
        if r.returncode != 0:
            print(f"  {sid[:8]}  FAILED to spawn tmux: {r.stderr.strip()}")
            continue
        spawned.append((sid, name, title))
        time.sleep(1.5)  # stagger startups

    # Verify: the resumed process must re-register under the same session id.
    deadline = time.time() + 30 + 5 * len(spawned)
    pending = dict.fromkeys(sid for sid, _, _ in spawned)
    while pending and time.time() < deadline:
        time.sleep(2)
        live_now, _ = load_registry()
        for sid in [s for s in pending if s in live_now]:
            del pending[sid]

    ok = 0
    for sid, name, title in spawned:
        if sid in pending:
            pane = tmux("capture-pane", "-t", name, "-p").stdout.strip()[-300:]
            print(f"  {sid[:8]}  NOT VERIFIED in {name} — check `tmux attach -t "
                  f"{name}`; last pane output:\n    {pane or '(no output)'}")
        else:
            ok += 1
            print(f"  {sid[:8]}  resumed in tmux {name}  — {title}")
            consume(workspace, sid)
            if args.kick:
                tmux("send-keys", "-t", name, args.kick)
                time.sleep(0.5)
                tmux("send-keys", "-t", name, "Enter")

    if ok:
        print(f"\n{ok}/{len(spawned)} resumed. Attach: tmux attach -t "
              f"{TMUX_PREFIX}<id8>")
        print("If you reopen one of these in the VSCode extension instead, "
              f"kill its tmux copy first (tmux kill-session -t {TMUX_PREFIX}"
              "<id8>) — two live processes on one session id interleave writes.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tick", action="store_true",
                    help="snapshot mode (run by the systemd timer): refresh "
                         "the state file and exit")
    ap.add_argument("--dry-run", action="store_true", help="list, do not resume")
    ap.add_argument("--logs", action="store_true",
                    help="also mine IDE extension logs for session ids "
                         "(over-includes cleanly-closed tabs; off by default)")
    ap.add_argument("--hours", type=float, default=48,
                    help="lookback window for the --logs fallback (default 48)")
    ap.add_argument("--kick", metavar="PROMPT", default=None,
                    help="send PROMPT to each resumed session after it is up")
    ap.add_argument("--include", nargs="*", default=[], metavar="SESSION_ID",
                    help="extra session ids to resume regardless of source")
    ap.add_argument("--workspace", default=os.getcwd(),
                    help="workspace path (default: cwd)")
    ap.add_argument("--stalled", action="store_true",
                    help="list LIVE sessions idle due to usage limit / API "
                         "error / interruption / unanswered prompt")
    ap.add_argument("--nudge", action="store_true",
                    help="with --stalled: send /compact + a continue prompt "
                         "to tmux-hosted stalled sessions (VSCode-hosted ones "
                         "are listed with their SendMessage peer name)")
    ap.add_argument("--json", action="store_true",
                    help="with --stalled: also print the rows as JSON")
    args = ap.parse_args()

    if args.tick:
        tick(quiet=False)
    elif args.stalled:
        stalled(args)
    else:
        resolve(args)


if __name__ == "__main__":
    main()
