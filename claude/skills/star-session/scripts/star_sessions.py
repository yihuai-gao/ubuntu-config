#!/usr/bin/env python3
"""Star, unstar, and list starred Claude Code sessions.

Stars live in ~/.claude/starred-sessions.json — a small registry pointing at
transcript files under ~/.claude/projects/<project-slug>/<session-id>.jsonl.
Starring never modifies transcripts; unstarring never deletes them.

Stdlib only; no dependencies.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STAR_FILE = Path.home() / ".claude" / "starred-sessions.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
TITLE_MAX = 120


# ---------- store ----------

def load_store() -> dict:
    if STAR_FILE.exists():
        try:
            store = json.loads(STAR_FILE.read_text())
            if isinstance(store, dict) and isinstance(store.get("sessions"), list):
                return store
        except (json.JSONDecodeError, OSError):
            sys.stderr.write(f"warning: could not parse {STAR_FILE}, starting fresh\n")
    return {"version": 1, "sessions": []}


def save_store(store: dict) -> None:
    STAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STAR_FILE.parent), prefix=".starred-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(store, f, indent=2)
            f.write("\n")
        os.replace(tmp, STAR_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------- transcript inspection ----------

def find_transcripts(session_ref: str) -> list[Path]:
    """All transcript files whose session id starts with session_ref."""
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(PROJECTS_DIR.glob(f"*/{session_ref}*.jsonl"))


def session_meta(path: Path) -> dict:
    """Extract title, summary, and cwd from a transcript."""
    title, summary, cwd = None, None, None
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cwd is None and obj.get("cwd"):
            cwd = obj["cwd"]
        if obj.get("type") == "summary" and obj.get("summary"):
            summary = obj["summary"]  # keep the last one seen
        if title is None and obj.get("type") == "user" and not obj.get("isSidechain"):
            msg = obj.get("message") or {}
            content = msg.get("content")
            texts = [content] if isinstance(content, str) else [
                i.get("text", "") for i in content if isinstance(i, dict) and i.get("type") == "text"
            ] if isinstance(content, list) else []
            for t in texts:
                t = re.sub(r"\s+", " ", t).strip()
                # Skip injected system-reminder / command wrapper turns.
                if t and not t.startswith("<"):
                    title = t[:TITLE_MAX]
                    break
    return {"title": title, "summary": summary, "cwd": cwd}


# ---------- commands ----------

def resolve_session_ref(ref: str | None) -> str:
    if ref:
        return ref
    env_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if env_id:
        return env_id
    sys.exit("error: no session id given and CLAUDE_CODE_SESSION_ID is not set; pass a session id")


def cmd_star(args) -> None:
    ref = resolve_session_ref(args.session_id)
    matches = find_transcripts(ref)
    if not matches:
        sys.exit(f"error: no transcript matches session id {ref!r} under {PROJECTS_DIR}")
    if len(matches) > 1 and len({p.stem for p in matches}) > 1:
        listing = "".join(f"  {p.stem}  ({p.parent.name})\n" for p in matches)
        sys.exit(f"error: ambiguous session id prefix {ref!r}:\n{listing}")
    path = max(matches, key=lambda p: p.stat().st_mtime)  # same id in 2 projects: newest wins
    meta = session_meta(path)
    store = load_store()

    entry = next((s for s in store["sessions"] if s["session_id"] == path.stem), None)
    is_new = entry is None
    if is_new:
        entry = {"session_id": path.stem}
        store["sessions"].append(entry)
    entry.update(
        {
            "label": args.label or entry.get("label"),
            "title": meta["title"],
            "summary": meta["summary"],
            "project_slug": path.parent.name,
            "cwd": meta["cwd"],
            "starred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    save_store(store)
    verb = "Starred" if is_new else "Updated star for"
    print(f"{verb} session {path.stem}")
    if entry.get("label"):
        print(f"  label: {entry['label']}")
    print(f"  title: {entry.get('title') or '(no user message)'}")
    print(f"  project: {entry.get('cwd') or path.parent.name}")


def format_entry(entry: dict, missing: bool) -> str:
    starred = entry.get("starred_at", "")
    try:
        starred = datetime.fromisoformat(starred).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    lines = [f"★ {entry['session_id']}  (starred {starred})"]
    if entry.get("label"):
        lines.append(f"   label:   {entry['label']}")
    display_title = entry.get("summary") or entry.get("title") or "(no user message)"
    lines.append(f"   title:   {display_title}")
    lines.append(f"   project: {entry.get('cwd') or entry.get('project_slug', '?')}")
    if missing:
        lines.append("   note:    transcript file no longer exists (deleted or moved)")
    else:
        lines.append(f"   resume:  claude --resume {entry['session_id']}")
    return "\n".join(lines)


def cmd_list(args) -> None:
    store = load_store()
    sessions = store["sessions"]
    if args.project:
        want = str(Path(args.project).resolve())
        sessions = [s for s in sessions if s.get("cwd") == want]
    sessions = sorted(sessions, key=lambda s: s.get("starred_at", ""), reverse=True)
    if not sessions:
        scope = f" for project {args.project}" if args.project else ""
        print(f"No starred sessions{scope}. Star one with: star_sessions.py star [SESSION_ID]")
        return
    for entry in sessions:
        missing = not find_transcripts(entry["session_id"])
        print(format_entry(entry, missing))
        print()
    print(f"({len(sessions)} starred session{'s' if len(sessions) != 1 else ''})")


def cmd_unstar(args) -> None:
    store = load_store()
    ref = args.session_ref
    hits = [
        s for s in store["sessions"]
        if s["session_id"].startswith(ref) or (s.get("label") or "").lower() == ref.lower()
    ]
    if not hits:
        sys.exit(f"error: no starred session matches {ref!r} (by id prefix or exact label)")
    if len(hits) > 1:
        listing = "".join(f"  {s['session_id']}  {s.get('label') or s.get('title') or ''}\n" for s in hits)
        sys.exit(f"error: {ref!r} matches multiple starred sessions:\n{listing}")
    store["sessions"].remove(hits[0])
    save_store(store)
    print(f"Unstarred session {hits[0]['session_id']}")
    if hits[0].get("label") or hits[0].get("title"):
        print(f"  was: {hits[0].get('label') or hits[0].get('title')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Star/unstar/list Claude Code sessions")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_star = sub.add_parser("star", help="star a session (default: the current one)")
    p_star.add_argument("session_id", nargs="?", help="session id or unique prefix; defaults to $CLAUDE_CODE_SESSION_ID")
    p_star.add_argument("--label", help="short human-readable name shown in the starred list")
    p_star.set_defaults(func=cmd_star)

    p_list = sub.add_parser("list", help="list starred sessions, newest star first")
    p_list.add_argument("--project", help="only stars whose session ran in this project directory")
    p_list.set_defaults(func=cmd_list)

    p_unstar = sub.add_parser("unstar", help="remove a star (transcript is untouched)")
    p_unstar.add_argument("session_ref", help="session id, unique id prefix, or exact label")
    p_unstar.set_defaults(func=cmd_unstar)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
