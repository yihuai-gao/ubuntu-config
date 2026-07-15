#!/usr/bin/env python3
"""Full-text search across Claude Code session transcripts.

Scans the JSONL transcript files under ~/.claude/projects/<project-slug>/,
matching sessions whose *message contents* (user + assistant text) contain
all given terms. Prints session IDs with context so a session can be resumed
with `claude --resume <session-id>`.

Stdlib only; no dependencies.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
SNIPPET_RADIUS = 60
MAX_SNIPPETS = 3


def path_to_slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", str(Path(path).resolve()))


def resolve_project_dirs(args) -> list[Path]:
    if args.all_projects:
        return sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir())
    target = args.project or "."
    slug = path_to_slug(target)
    d = PROJECTS_DIR / slug
    if d.is_dir():
        return [d]
    # Fallback: maybe the slug convention differs slightly; try suffix match.
    candidates = [p for p in PROJECTS_DIR.iterdir() if p.is_dir() and p.name.lower() == slug.lower()]
    if candidates:
        return candidates
    sys.stderr.write(
        f"No transcript directory for {target!r} (looked for {slug}).\n"
        f"Available projects:\n"
        + "".join(f"  {p.name}\n" for p in sorted(PROJECTS_DIR.iterdir()) if p.is_dir())
    )
    sys.exit(1)


def extract_texts(obj: dict, include_thinking: bool) -> list[str]:
    """Pull human-readable text out of one transcript line."""
    texts = []
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif include_thinking and item.get("type") == "thinking":
                    texts.append(item.get("thinking", ""))
    if obj.get("type") == "summary" and obj.get("summary"):
        texts.append(obj["summary"])
    return [t for t in texts if t]


def make_matcher(args):
    if args.regex:
        pattern = re.compile(args.terms[0], re.IGNORECASE)
        return lambda text: bool(pattern.search(text)), lambda text: pattern.search(text)
    lowered = [t.lower() for t in args.terms]

    def contains_any(text: str):
        low = text.lower()
        for t in lowered:
            i = low.find(t)
            if i >= 0:
                return _Span(i, i + len(t))
        return None

    return lambda text: contains_any(text) is not None, contains_any


class _Span:
    def __init__(self, start, end):
        self._s, self._e = start, end

    def start(self):
        return self._s

    def end(self):
        return self._e


def snippet(text: str, span) -> str:
    s, e = span.start(), span.end()
    lo, hi = max(0, s - SNIPPET_RADIUS), min(len(text), e + SNIPPET_RADIUS)
    frag = text[lo:s] + "«" + text[s:e] + "»" + text[e:hi]
    frag = re.sub(r"\s+", " ", frag).strip()
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return prefix + frag + suffix


def search_file(path: Path, args, match_any, find_span):
    """Return a result dict if this session matches, else None."""
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return None

    # Cheap pre-filter on the raw file before any JSON parsing.
    if args.regex:
        if not re.search(args.terms[0], raw, re.IGNORECASE):
            return None
    else:
        low = raw.lower()
        if not all(t.lower() in low for t in args.terms):
            return None

    title = None
    hits = 0
    snippets = []
    terms_seen = set()

    for line in raw.splitlines():
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        texts = extract_texts(obj, args.thinking)

        if title is None and obj.get("type") == "user" and not obj.get("isSidechain"):
            for t in texts:
                t_clean = re.sub(r"\s+", " ", t).strip()
                if t_clean and not t_clean.startswith("<"):
                    title = t_clean[:100]
                    break

        matched = next((t for t in texts if match_any(t)), None)
        if matched is None and args.include_tools and match_any(line):
            matched = line
        if matched is None:
            continue

        hits += 1
        if not args.regex:
            low_t = matched.lower()
            terms_seen.update(term for term in args.terms if term.lower() in low_t)
        if len(snippets) < MAX_SNIPPETS:
            span = find_span(matched)
            role = obj.get("message", {}).get("role", obj.get("type", "?"))
            snippets.append(f"[{role}] {snippet(matched, span)}")

    if hits == 0:
        return None
    # AND semantics: the raw pre-filter may pass on tool payloads/metadata,
    # so re-check that every term actually appeared in searched content.
    if not args.regex and terms_seen != set(args.terms):
        return None

    return {
        "session_id": path.stem,
        "project": path.parent.name,
        "mtime": path.stat().st_mtime,
        "title": title or "(no user message)",
        "hits": hits,
        "snippets": snippets,
    }


def main():
    ap = argparse.ArgumentParser(description="Full-text search of Claude Code session transcripts")
    ap.add_argument("terms", nargs="+", help="search terms (session must contain ALL, case-insensitive); with --regex, a single regex pattern")
    ap.add_argument("--project", help="project path to search (default: current directory)")
    ap.add_argument("--all-projects", action="store_true", help="search every project under ~/.claude/projects")
    ap.add_argument("--regex", action="store_true", help="treat the single argument as a regex")
    ap.add_argument("--include-tools", action="store_true", help="also match tool inputs/outputs and metadata (raw JSON)")
    ap.add_argument("--thinking", action="store_true", help="also search assistant thinking blocks")
    ap.add_argument("--limit", type=int, default=10, help="max sessions to show (default 10)")
    args = ap.parse_args()

    if args.regex and len(args.terms) > 1:
        ap.error("--regex takes exactly one pattern")

    match_any, find_span = make_matcher(args)
    results = []
    for proj_dir in resolve_project_dirs(args):
        for f in proj_dir.glob("*.jsonl"):
            r = search_file(f, args, match_any, find_span)
            if r:
                results.append(r)

    results.sort(key=lambda r: r["mtime"], reverse=True)
    shown = results[: args.limit]

    if not results:
        print("No sessions matched.")
        return

    for r in shown:
        when = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M")
        print(f"== {r['session_id']}  ({when}, {r['hits']} matching messages)")
        if args.all_projects:
            print(f"   project: {r['project']}")
        print(f"   title:   {r['title']}")
        for s in r["snippets"]:
            print(f"   {s}")
        print(f"   resume:  claude --resume {r['session_id']}")
        print()

    if len(results) > len(shown):
        print(f"({len(results) - len(shown)} more matching sessions; raise --limit to see them)")


if __name__ == "__main__":
    main()
