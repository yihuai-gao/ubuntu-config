#!/usr/bin/env python3
"""review_worktree.py — inventory the git worktrees of a workspace, find the
Claude Code sessions that work(ed) in each, and classify every worktree as

  active      a session is (or was very recently) working in it   -> keep
  merged      everything it holds is already in the main worktree  -> delete
  superseded  anything else (unlanded + stale/orphaned/overlapping) -> ask user

The script is the detector + git actuator. Messaging live sessions and
spawning subagents is done by Claude following SKILL.md; the JSON output
(--json) carries everything needed for that.

Usage
  review_worktree.py [--workspace PATH] [--hours N] [--json]
  review_worktree.py --delete-merged          # remove every `merged` worktree (with backup)
  review_worktree.py --delete PATH [PATH ..]  # remove specific worktrees (with backup)
  review_worktree.py --context PATH           # markdown context bundle for a subagent
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
BACKUP_ROOT = Path.home() / ".local" / "state" / "claude-review-worktree" / "backups"
GREP = shutil.which("grep") or "/usr/bin/grep"   # subprocess: no shell aliases (ugrep)
TS_RE = re.compile(r'"timestamp":"([^"]+)"')
NOISE_RE = re.compile(r"(^|/)(__pycache__/|\.pytest_cache/|.*\.pyc$|.*\.synctex\.gz$)")
WORKER_MENTIONS = 5   # a session with >= this many path mentions (and no cwd rows) still counts as a worker


# ----------------------------------------------------------------- helpers
def sh(args, cwd=None, check=False, text=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=text, check=check)


def git(cwd, *args, check=False):
    r = sh(["git", "-C", str(cwd), *args], check=check)
    return r.stdout.strip() if r.returncode == 0 else ""


def parse_ts(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def fmt_ts(ts) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def age(ts) -> str:
    if not ts:
        return "-"
    d = time.time() - ts
    if d < 3600:
        return f"{int(d // 60)}m"
    if d < 86400:
        return f"{d / 3600:.1f}h"
    return f"{d / 86400:.1f}d"


# ------------------------------------------------------- session registry
def proc_starttime(pid: int):
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text()
    except OSError:
        return None
    return stat.rsplit(")", 1)[1].split()[19]


def pid_is_this_session(pid: int, proc_start: str) -> bool:
    if proc_starttime(pid) != str(proc_start):
        return False
    try:
        return b"claude" in (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return False


def load_registry():
    """sid -> entry for LIVE interactive sessions (pid + starttime verified)."""
    live = {}
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            e = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sid = e.get("sessionId")
        if sid and e.get("kind") == "interactive" and \
                pid_is_this_session(e.get("pid", -1), e.get("procStart", "")):
            live[sid] = e
    return live


def self_session_ids(live) -> set:
    """Session ids of the claude process running this script (walk ppid chain)."""
    out = set()
    env_sid = os.environ.get("CLAUDE_SESSION_ID")
    if env_sid:
        out.add(env_sid)
    pid_to_sid = {e.get("pid"): sid for sid, e in live.items()}
    pid = os.getpid()
    for _ in range(40):
        if pid in pid_to_sid:
            out.add(pid_to_sid[pid])
        try:
            stat = (Path("/proc") / str(pid) / "stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
        if pid <= 1:
            break
    return out


# ------------------------------------------------------------- worktrees
def list_worktrees(workspace: Path):
    out = git(workspace, "worktree", "list", "--porcelain")
    if not out:
        sys.exit(f"not a git repository (or no worktrees): {workspace}")
    wts, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                wts.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        if k == "worktree":
            cur = {"path": v, "branch": None, "detached": False, "locked": False,
                   "prunable": False, "bare": False}
        elif k == "HEAD":
            cur["head"] = v
        elif k == "branch":
            cur["branch"] = v.replace("refs/heads/", "")
        elif k in ("detached", "locked", "prunable", "bare"):
            cur[k] = True
    return wts[0], wts[1:]


def changed_files(wt: str):
    """[(xy, path)] from `git status --porcelain -z` (renames -> new path)."""
    r = sh(["git", "-C", wt, "status", "--porcelain", "-z", "--untracked-files=all"])
    toks = r.stdout.split("\0")
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if not t:
            i += 1
            continue
        xy, path = t[:2], t[3:]
        if "R" in xy or "C" in xy:
            i += 1  # skip the original path token
        if not NOISE_RE.search(path):
            out.append((xy, path))
        i += 1
    return out


def landed_in_history(wp: Path, path: str, main_path: str, base: str, main_head: str):
    """Commit id if the worktree's current content of `path` was committed verbatim to
    main somewhere in base..main_head (main may have evolved the file afterwards)."""
    if wp.is_dir():
        return None
    blob = git(main_path, "hash-object", str(wp))
    if not blob:
        return None
    commits = git(main_path, "rev-list", f"{base}..{main_head}", "--", path).splitlines()
    for c in commits[:200]:
        if git(main_path, "rev-parse", "--quiet", "--verify", f"{c}:{path}") == blob:
            return c[:7]
    return None


def same_content(a: Path, b: Path) -> bool:
    if a.is_dir() or b.is_dir():
        return False
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def git_facts(wt: dict, main: dict):
    p, mp = wt["path"], main["path"]
    main_head = main["head"]
    f = {"path": p, "name": Path(p).name, "head": wt["head"][:7], "branch": wt["branch"],
         "detached": wt["detached"], "locked": wt["locked"], "prunable": wt["prunable"],
         "exists": Path(p).is_dir()}
    if not f["exists"]:
        f.update(ahead=0, behind=0, unlanded_commits=0, changed=[], landed=[], landed_hist={}, unlanded=[],
                 main_touched=[], main_has_own=[], last_mtime=0, note="directory missing (prunable)")
        return f
    f["ancestor_of_main"] = sh(["git", "-C", p, "merge-base", "--is-ancestor", "HEAD", main_head]).returncode == 0
    f["ahead"] = int(git(p, "rev-list", "--count", f"{main_head}..HEAD") or 0)
    f["behind"] = int(git(p, "rev-list", "--count", f"HEAD..{main_head}") or 0)
    cherry = git(p, "cherry", main_head, "HEAD").splitlines() if f["ahead"] else []
    f["unlanded_commits"] = sum(1 for l in cherry if l.startswith("+"))
    f["commit_subjects"] = git(p, "log", "--format=%h %s", f"{main_head}..HEAD").splitlines()[:10]

    changed = changed_files(p)
    landed, landed_hist, unlanded, main_touched, main_has_own, mtimes = [], {}, [], [], [], []
    for xy, path in changed:
        wp, mpath = Path(p) / path, Path(mp) / path
        try:
            mtimes.append(wp.stat().st_mtime)
        except OSError:
            pass
        deleted = "D" in xy
        if deleted:
            (landed if not mpath.exists() else unlanded).append(path)
            continue
        if same_content(wp, mpath):
            landed.append(path)
            continue
        c = landed_in_history(wp, path, mp, wt["head"], main_head)
        if c:
            landed.append(path)
            landed_hist[path] = c
            continue
        unlanded.append(path)
        if "A" in xy or xy == "??":   # added here (staged, intent-to-add or untracked)
            if mpath.exists():      # main has its own version of a file this worktree adds
                main_has_own.append(path)
        elif sh(["git", "-C", mp, "diff", "--quiet", wt["head"], "--", path]).returncode != 0:
            main_touched.append(path)   # main changed this file since the worktree's base
    f.update(changed=[f"{xy} {path}" for xy, path in changed], landed=landed, landed_hist=landed_hist,
             unlanded=unlanded, main_touched=main_touched, main_has_own=main_has_own,
             last_mtime=max(mtimes) if mtimes else 0)
    if not changed:
        try:  # untouched tree: fall back to the worktree's .git stamp
            f["last_mtime"] = (Path(p) / ".git").stat().st_mtime
        except OSError:
            pass
    return f


# -------------------------------------------------------------- sessions
def grep_count(pattern: str, file: Path) -> int:
    r = sh([GREP, "-c", "-F", pattern, str(file)])
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return 0


def last_match_ts(pattern: str, file: Path) -> float:
    r = sh([GREP, "-F", pattern, str(file)], text=False)
    lines = r.stdout.splitlines()
    for line in reversed(lines):
        m = TS_RE.search(line.decode("utf-8", "replace"))
        if m:
            return parse_ts(m.group(1))
    return 0.0


def transcript_title(path: Path):
    r = sh([GREP, "-F", '"ai-title"', str(path)])
    for line in reversed(r.stdout.splitlines()):
        try:
            d = json.loads(line)
            if d.get("type") == "ai-title":
                return d.get("aiTitle")
        except json.JSONDecodeError:
            pass
    return None


def sessions_for(wt_path: str, live: dict, exclude: set):
    """Sessions whose transcripts (or subagent transcripts) reference wt_path."""
    r = sh([GREP, "-rl", "-F", "--include=*.jsonl", wt_path, str(PROJECTS_DIR)])
    per_sid = {}
    for fp in r.stdout.splitlines():
        f = Path(fp)
        rel = f.relative_to(PROJECTS_DIR).parts
        if len(rel) == 2:                       # <proj>/<sid>.jsonl
            sid, sub = f.stem, False
        elif len(rel) == 4 and rel[2] == "subagents":  # <proj>/<sid>/subagents/agent-x.jsonl
            sid, sub = rel[1], True
        else:
            continue
        if sid in exclude:
            continue
        s = per_sid.setdefault(sid, {"sid": sid, "project": rel[0], "cwd_rows": 0, "mentions": 0,
                                     "last_ts": 0.0, "via_subagent": False, "files": []})
        s["cwd_rows"] += grep_count(f'"cwd":"{wt_path}"', f)
        s["mentions"] += grep_count(wt_path, f)
        s["last_ts"] = max(s["last_ts"], last_match_ts(wt_path, f))
        s["via_subagent"] |= sub
        s["files"].append(str(f))
    out = []
    for sid, s in per_sid.items():
        parent = PROJECTS_DIR / s["project"] / f"{sid}.jsonl"
        s["transcript"] = str(parent) if parent.is_file() else None
        s["transcript_mtime"] = parent.stat().st_mtime if parent.is_file() else 0
        s["title"] = transcript_title(parent) if parent.is_file() else None
        # A session that ran this skill quotes every worktree path in its tool output; without
        # real cwd rows it is a "reviewer", not a worker, and is ignored for classification.
        ran_skill = parent.is_file() and grep_count("review_worktree.py", parent) > 0
        if s["cwd_rows"] > 0:
            s["role"] = "worker"
        elif ran_skill:
            s["role"] = "reviewer"
        else:
            s["role"] = "worker" if s["mentions"] >= WORKER_MENTIONS else "mention"
        e = live.get(sid)
        if e:
            s["live"] = True
            s["status"] = e.get("status", "?")          # busy | idle | waiting
            s["waiting_for"] = e.get("waitingFor")      # e.g. "permission prompt"
            s["peer"] = e.get("name")
            s["pid"] = e.get("pid")
            s["startup_cwd"] = e.get("cwd")
            s["tmux"] = _tmux_window_for_pid(e.get("pid"))
        else:
            s["live"] = False
            s["status"] = "dead"
            s["peer"] = None
        out.append(s)
    out.sort(key=lambda s: (s["role"] != "worker", -s["cwd_rows"], -s["last_ts"]))
    return out


def _tmux_window_for_pid(pid):
    """tmux session name hosting pid, if any (walk ppid chain against pane pids)."""
    r = sh(["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"])
    if r.returncode != 0:
        return None
    panes = {int(a): b for a, b in (l.split(" ", 1) for l in r.stdout.splitlines() if " " in l)}
    for _ in range(20):
        if pid in panes:
            return panes[pid]
        try:
            pid = int((Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return None
        if pid <= 1:
            return None
    return None


# ---------------------------------------------------------- classification
def classify(facts: list, hours: float):
    recent_cut = time.time() - hours * 3600
    by_path = {f["path"]: f for f in facts}
    for f in facts:
        f["reasons"] = []
        workers = [s for s in f["sessions"] if s["role"] == "worker"]
        busy = [s for s in workers if s["live"] and s["status"] == "busy"]
        live_idle = [s for s in workers if s["live"] and s["status"] != "busy"]
        recent_workers = [s for s in workers if s["last_ts"] >= recent_cut]
        tree_recent = f["last_mtime"] >= recent_cut
        clean = not f["unlanded"] and f["unlanded_commits"] == 0

        if not f["exists"]:
            f["category"], f["action"] = "merged", "prune"
            f["reasons"].append("directory is gone; only the .git/worktrees entry remains")
            continue
        if busy:
            f["category"], f["action"] = "active", "keep"
            f["reasons"].append(f"live session {busy[0]['sid'][:8]} is busy (peer {busy[0]['peer']})")
            continue
        if live_idle and (recent_workers or tree_recent):
            s = live_idle[0]
            waiting = s["status"] == "waiting"
            f["category"], f["action"] = "active", ("attend" if waiting else "nudge")
            f["reasons"].append(f"live session {s['sid'][:8]} is {s['status']}"
                                + (f" for {s['waiting_for']}" if s.get("waiting_for") else "")
                                + f" (peer {s['peer']}" + (f", tmux {s['tmux']}" if s.get("tmux") else "") + "); "
                                f"last touched {age(max(s['last_ts'], f['last_mtime']))} ago")
            continue
        if recent_workers or (tree_recent and not clean):
            f["category"], f["action"] = "active", "subagent"
            if recent_workers:
                s = recent_workers[0]
                f["reasons"].append(f"worker session {s['sid'][:8]} is dead; it touched the worktree "
                                    f"{age(s['last_ts'])} ago")
            else:
                f["reasons"].append(f"files edited {age(f['last_mtime'])} ago but no session transcript found")
            continue
        if clean:
            f["category"], f["action"] = "merged", "delete"
            n = len(f["landed"])
            f["reasons"].append("tree identical to main" if n == 0 and not f["ahead"] else
                                f"{n} changed file(s) all identical to main"
                                + (f" ({len(f['landed_hist'])} via an earlier main commit)" if f["landed_hist"] else "")
                                + (f"; {f['ahead']} commit(s) all patch-equivalent in main" if f["ahead"] else ""))
            continue

        # ---- superseded: explain why it is not simply merged
        f["category"], f["action"] = "superseded", "ask"
        n_un, n_all = len(f["unlanded"]), len(f["changed"])
        if workers:
            s = workers[0]
            f["reasons"].append(f"worker session {s['sid'][:8]} {'live-' + s['status'] if s['live'] else 'dead'}; "
                                f"last touched {age(s['last_ts'])} ago"
                                + (f" — {s['title']}" if s.get("title") else ""))
        else:
            f["reasons"].append("no session transcript references this worktree (orphan / transcript expired)")
        f["reasons"].append(f"{n_un}/{n_all} changed file(s) NOT in main"
                            + (f", {len(f['landed'])} already identical" if f["landed"] else "")
                            + (f"; {f['unlanded_commits']} unlanded commit(s)" if f["unlanded_commits"] else "")
                            + f"; last edit {age(f['last_mtime'])} ago")
        if f["landed_hist"]:
            f["reasons"].append(f"{len(f['landed_hist'])} file(s) were committed to main verbatim and main moved on since: "
                                + ", ".join(f"{Path(k).name}@{v}" for k, v in list(f["landed_hist"].items())[:4]))
        if f["main_touched"]:
            f["reasons"].append(f"main changed {len(f['main_touched'])} of those files after the worktree's base "
                                f"({f['behind']} commits behind): " + ", ".join(f["main_touched"][:4]))
        if f["main_has_own"]:
            f["reasons"].append(f"main has its own (different) version of {len(f['main_has_own'])} file(s) this worktree adds: "
                                + ", ".join(Path(x).name for x in f["main_has_own"][:4]))
        # overlap with sibling worktrees
        mine = set(f["unlanded"])
        for g in facts:
            if g is f or not g["exists"]:
                continue
            theirs = {c[3:] for c in g["changed"]}
            if mine and mine <= theirs:
                newer = g["last_mtime"] >= f["last_mtime"]
                f["reasons"].append(f"all its unlanded files are also changed in {g['name']} "
                                    f"({'newer' if newer else 'OLDER'}, {fmt_ts(g['last_mtime'])})"
                                    + (" -> likely superseded by it" if newer else ""))


# ------------------------------------------------------------ actuators
def backup_worktree(f: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = BACKUP_ROOT / f"{f['name']}-{ts}"
    dst.mkdir(parents=True, exist_ok=True)
    p = f["path"]
    (dst / "info.txt").write_text(json.dumps({k: v for k, v in f.items() if k != "sessions"},
                                             indent=1, default=str))
    (dst / "tracked.patch").write_text(sh(["git", "-C", p, "diff", "HEAD"]).stdout)   # staged + unstaged
    others = sh(["git", "-C", p, "ls-files", "--others", "--exclude-standard", "-z"]).stdout.split("\0")
    others = [o for o in others if o and not NOISE_RE.search(o)]
    if others:
        with tarfile.open(dst / "untracked.tar.gz", "w:gz") as tar:
            for o in others:
                try:
                    tar.add(Path(p) / o, arcname=o)
                except OSError:
                    pass
    if f.get("ahead"):
        sh(["git", "-C", p, "bundle", "create", str(dst / "commits.bundle"), "HEAD", f"^{f['main_head']}"])
    return dst


def delete_worktree(f: dict, main: dict):
    print(f"\n-- deleting {f['path']}")
    if f["exists"]:
        b = backup_worktree(f)
        print(f"   backup: {b}")
    r = sh(["git", "-C", main["path"], "worktree", "remove", "--force", f["path"]])
    if r.returncode != 0:
        print(f"   worktree remove failed: {r.stderr.strip()}")
        r = sh(["git", "-C", main["path"], "worktree", "prune"])
        print(f"   worktree prune: rc={r.returncode}")
    else:
        print("   removed")
    br = f.get("branch")
    if br and br != main.get("branch"):
        r = sh(["git", "-C", main["path"], "branch", "-d", br])
        print(f"   branch -d {br}: {'ok' if r.returncode == 0 else r.stderr.strip()}")


def tail_messages(path: Path, n: int):
    """Last n (kind, timestamp, text) user/assistant text records of a transcript."""
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
        c = (d.get("message") or {}).get("content")
        if isinstance(c, str):
            txt = c
        elif isinstance(c, list):
            parts = [x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text"]
            if any(isinstance(x, dict) and x.get("type") in ("tool_use", "tool_result") for x in c):
                continue
            txt = " ".join(parts)
        else:
            continue
        txt = txt.strip()
        if not txt or (d.get("type") == "user" and txt.startswith("<")):
            continue   # task notifications / system attachments
        out.append((d["type"], d.get("timestamp") or "", txt))
    return out[-n:]


def context_bundle(f: dict, main: dict, n: int = 40):
    print(f"# Worktree context: {f['path']}\n")
    print(f"- main worktree: {main['path']} (branch {main.get('branch')}, HEAD {main['head'][:7]})")
    print(f"- worktree HEAD {f['head']} ({'detached' if f['detached'] else f['branch']}); "
          f"{f['ahead']} ahead / {f['behind']} behind main; last edit {fmt_ts(f['last_mtime'])}")
    if f.get("commit_subjects"):
        print("- commits not in main:\n  " + "\n  ".join(f["commit_subjects"]))
    print(f"\n## Changed files ({len(f['changed'])}; {len(f['unlanded'])} not yet in main)\n")
    for c in f["changed"]:
        tag = "LANDED " if c[3:] in f["landed"] else ("UNLANDED" if c[3:] in f["unlanded"] else "        ")
        print(f"  {tag} {c}")
    print("\n## diff --stat vs HEAD\n")
    print(sh(["git", "-C", f["path"], "diff", "HEAD", "--stat"]).stdout)
    print("## Sessions\n")
    for s in f["sessions"]:
        print(f"- {s['sid']} [{s['role']}] {'LIVE ' + s['status'] if s['live'] else 'dead'} "
              f"cwd_rows={s['cwd_rows']} mentions={s['mentions']} last={fmt_ts(s['last_ts'])} "
              f"peer={s.get('peer')} tmux={s.get('tmux')}\n  title: {s.get('title')}\n  transcript: {s.get('transcript')}")
        if s["via_subagent"]:
            print("  subagent transcripts: " + ", ".join(x for x in s["files"] if "/subagents/" in x))
    workers = [s for s in f["sessions"] if s["role"] == "worker" and s.get("transcript")]
    if workers:
        s = workers[0]
        print(f"\n## Last {n} messages of worker session {s['sid'][:8]}\n")
        for kind, ts, txt in tail_messages(Path(s["transcript"]), n):
            print(f"[{ts[:16]}] {kind:9s} {txt.replace(chr(10), ' ')[:600]}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=os.getcwd())
    ap.add_argument("--hours", type=float, default=24, help="recency window for 'active' (default 24)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--delete-merged", action="store_true")
    ap.add_argument("--delete", nargs="*", default=None, metavar="PATH")
    ap.add_argument("--context", metavar="PATH")
    ap.add_argument("--exclude-sid", action="append", default=[], help="ignore this session id (auto: the caller)")
    args = ap.parse_args()

    main_wt, others = list_worktrees(Path(args.workspace).resolve())
    live = load_registry()
    exclude = set(args.exclude_sid) | self_session_ids(live)

    facts = []
    for wt in others:
        f = git_facts(wt, main_wt)
        f["main_head"] = main_wt["head"]
        f["sessions"] = sessions_for(wt["path"], live, exclude) if f["exists"] else []
        facts.append(f)
    classify(facts, args.hours)

    if args.context:
        tgt = str(Path(args.context).resolve())
        for f in facts:
            if f["path"] == tgt:
                context_bundle(f, main_wt)
                return
        sys.exit(f"not a worktree of this workspace: {tgt}")

    if args.json:
        print(json.dumps({"main": main_wt, "excluded_sids": sorted(exclude), "worktrees": facts},
                         indent=1, default=str))
    else:
        print(f"main worktree: {main_wt['path']}  (branch {main_wt.get('branch')}, HEAD {main_wt['head'][:7]})")
        print(f"recency window: {args.hours:g}h   excluded (caller) sessions: {', '.join(s[:8] for s in exclude) or '-'}\n")
        print(f"{'category':10s} {'action':9s} {'worktree':34s} {'HEAD':8s} {'ahead':>5s} {'chg':>4s} {'unld':>4s} {'last edit':>11s}  session")
        for f in facts:
            w = next((s for s in f["sessions"] if s["role"] == "worker"), None)
            sess = "-" if not w else f"{w['sid'][:8]} {'LIVE-' + w['status'] if w['live'] else 'dead'}" + \
                   (f" ({w['peer']})" if w.get("peer") else "")
            print(f"{f['category']:10s} {f['action']:9s} {f['name'][:34]:34s} {f['head']:8s} {f['ahead']:>5d} "
                  f"{len(f['changed']):>4d} {len(f['unlanded']):>4d} {fmt_ts(f['last_mtime']):>11s}  {sess}")
        for f in facts:
            print(f"\n{f['name']}  ->  {f['category']} / {f['action']}   {f['path']}")
            for r in f["reasons"]:
                print(f"   - {r}")
            if f["unlanded"]:
                print("   unlanded: " + ", ".join(f["unlanded"][:8]) + (" ..." if len(f["unlanded"]) > 8 else ""))
            for s in f["sessions"][:4]:
                print(f"   session {s['sid'][:8]} [{s['role']}] {'LIVE-' + s['status'] if s['live'] else 'dead'} "
                      f"cwd_rows={s['cwd_rows']} mentions={s['mentions']} last={fmt_ts(s['last_ts'])}"
                      + (f" peer={s['peer']}" if s.get("peer") else "")
                      + (f" waiting_for={s['waiting_for']!r}" if s.get("waiting_for") else "")
                      + (f" tmux={s['tmux']}" if s.get("tmux") else "")
                      + (f"  — {s['title']}" if s.get("title") else ""))

    if args.delete_merged:
        for f in facts:
            if f["category"] == "merged":
                delete_worktree(f, main_wt)
    if args.delete:
        want = {str(Path(p).resolve()) for p in args.delete}
        for f in facts:
            if f["path"] in want:
                delete_worktree(f, main_wt)
                want.discard(f["path"])
        for p in want:
            print(f"not a worktree of this workspace: {p}")


if __name__ == "__main__":
    main()
